#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Offline tests for the forms readiness gate. All people and firms here are fictional.

    uv run --script tests/test_forms_gate.py
"""
from __future__ import annotations

import argparse
import contextlib
from http.client import IncompleteRead
import io
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

import audit_prepared_forms as audit
import build_forms
import download_uscis_forms
import editions
import formats
import forms_workflow
import xfa_tools
from download_uscis_forms import FORM_SPECS, spec_for
from form_question_schema import (
    QUESTION_SCHEMAS,
    SCHEMA_G28_CLIENT,
    SCHEMA_I130_FAMILY_PETITION,
    get_question_schema,
    load_field_list,
    skeleton_plan,
)
from official_blanks import check_schema_covers_the_form, complete_plan
from test_schema_g28 import ANSWERS as G28_ANSWERS, OPTIONAL as G28_OPTIONAL, SIGNATURES as G28_SIGNATURES
from forms_workflow import (
    STATUS_FILLED,
    STATUS_PARTIALLY_FILLED,
    STATUS_PENDING_SIGNATURE,
    question,
)


def write_blank_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as handle:
        writer.write(handle)


XFA_DATA_NS = "http://www.xfa.org/schema/xfa-data/1.0/"


def write_hybrid_pdf(
    path: Path,
    *,
    text: list[tuple[str, tuple[float, float, float, float], int]] = (),
    checkboxes: list[tuple[str, str]] = (),
    data_nodes: list[str] = (),
    global_names: list[str] = (),
    max_lens: dict[str, int] | None = None,
    choices: list[tuple[str, list[str]]] = (),
) -> None:
    """A one-page USCIS-style hybrid form: an XFA dataset plus AcroForm widgets.

    text: (leaf name, rect, field flags) with a Courier 10 pt /DA; max_lens gives a box its /MaxLen.
    choices: (leaf name, options) drop-downs.
    checkboxes: (leaf name, on-state). Widgets sit under form1[0].#subform[0],
    the way USCIS PDFs name them.
    """
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    def stream(data: bytes):
        obj = DecodedStreamObject()
        obj.set_data(data)
        return writer._add_object(obj)

    root_field = DictionaryObject(
        {NameObject("/T"): TextStringObject("form1[0]"), NameObject("/Kids"): ArrayObject()}
    )
    root_ref = writer._add_object(root_field)
    subform = DictionaryObject(
        {
            NameObject("/T"): TextStringObject("#subform[0]"),
            NameObject("/Parent"): root_ref,
            NameObject("/Kids"): ArrayObject(),
        }
    )
    subform_ref = writer._add_object(subform)
    root_field["/Kids"].append(subform_ref)
    annots = ArrayObject()

    def widget(leaf: str, rect, extra: dict) -> None:
        entries = {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/T"): TextStringObject(leaf),
            NameObject("/Rect"): ArrayObject(FloatObject(v) for v in rect),
            NameObject("/F"): NumberObject(4),
            NameObject("/P"): page.indirect_reference,
            NameObject("/Parent"): subform_ref,
            NameObject("/MK"): DictionaryObject(),
        }
        entries.update(extra)
        ref = writer._add_object(DictionaryObject(entries))
        subform["/Kids"].append(ref)
        annots.append(ref)

    for leaf, rect, flags in text:
        extra = {
            NameObject("/FT"): NameObject("/Tx"),
            NameObject("/DA"): TextStringObject("/Cour 10 Tf 0 g"),
            NameObject("/Ff"): NumberObject(flags),
        }
        if max_lens and leaf in max_lens:
            extra[NameObject("/MaxLen")] = NumberObject(max_lens[leaf])
        widget(leaf, rect, extra)
    for position, (leaf, options) in enumerate(choices):
        y = 400 - 20 * position
        widget(
            leaf,
            (300, y, 360, y + 14),
            {
                NameObject("/FT"): NameObject("/Ch"),
                NameObject("/Ff"): NumberObject(1 << 17),  # combo box
                NameObject("/DA"): TextStringObject("/Cour 10 Tf 0 g"),
                NameObject("/Opt"): ArrayObject(TextStringObject(option) for option in options),
            },
        )
    for position, (leaf, state) in enumerate(checkboxes):
        y = 700 - 20 * position
        appearances = DictionaryObject(
            {NameObject(f"/{state}"): stream(b"0 g 0 0 8 8 re f"), NameObject("/Off"): stream(b"")}
        )
        widget(
            leaf,
            (50, y, 60, y + 10),
            {
                NameObject("/FT"): NameObject("/Btn"),
                NameObject("/AP"): DictionaryObject({NameObject("/N"): appearances}),
                NameObject("/AS"): NameObject("/Off"),
            },
        )
    page[NameObject("/Annots")] = annots

    def font(base: str):
        return writer._add_object(
            DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject(base),
                    NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
                }
            )
        )

    nodes = "".join(f"<{name}/>" for name in data_nodes)
    datasets = (
        f'<xfa:datasets xmlns:xfa="{XFA_DATA_NS}"><xfa:data><form1>{nodes}</form1></xfa:data></xfa:datasets>'
    )
    fields = "".join(f'<field name="{name}"><bind match="global"/></field>' for name in global_names)
    template = f'<template><subform name="form1">{fields}</subform></template>'
    writer._root_object[NameObject("/AcroForm")] = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Fields"): ArrayObject([root_ref]),
                NameObject("/DA"): TextStringObject("/Helv 0 Tf 0 g"),
                NameObject("/DR"): DictionaryObject(
                    {
                        NameObject("/Font"): DictionaryObject(
                            {NameObject("/Cour"): font("/Courier"), NameObject("/Helv"): font("/Helvetica")}
                        )
                    }
                ),
                NameObject("/XFA"): ArrayObject(
                    [
                        TextStringObject("template"),
                        stream(template.encode()),
                        TextStringObject("datasets"),
                        stream(datasets.encode()),
                    ]
                ),
            }
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        writer.write(handle)


def write_marriage_place_form(path: Path) -> None:
    """Two unbound place boxes (current and prior marriage) plus a global unit checkbox group."""
    write_hybrid_pdf(
        path,
        text=[
            ("Place[0]", (50, 500, 272, 518), 0),
            ("Place[1]", (50, 450, 272, 468), 0),
            ("Note[0]", (50, 300, 566, 390), 4096),
        ],
        checkboxes=[("Unit[0]", " STE "), ("Unit[1]", " FLR "), ("Unit[2]", " APT ")],
        data_nodes=["Unit", "Note"],
        global_names=["Unit"],
    )


def run_quietly(func, *args, **kwargs):
    """Call func and return (result, stderr text)."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        result = func(*args, **kwargs)
    return result, err.getvalue()


def titles(findings: list[dict[str, object]]) -> list[str]:
    return [str(item["title"]) for item in findings]


def complete_g28_questions(**changes: str) -> list[dict[str, object]]:
    """A complete fictional G-28 plan (test_schema_g28.ANSWERS), every g28_represented_client
    question in schema order, each filled question showing its text answers; `changes` sets boxes."""
    answers = {**G28_ANSWERS, **changes}
    questions = []
    for item in skeleton_plan(SCHEMA_G28_CLIENT)["questions"]:
        key = item["key"]
        status = "not_applicable" if key in G28_OPTIONAL else (
            STATUS_PENDING_SIGNATURE if key in G28_SIGNATURES else STATUS_FILLED)
        values = {box: answers.get(box, "") if status == STATUS_FILLED else "" for box in item["field_values"]}
        visible = [value for box, value in values.items() if value and box not in item.get("choices", {})]
        questions.append(
            question(key=key, label=item["label"], status=status, field_values=values, visible_values=visible)
        )
    return questions


class FormsGateTests(unittest.TestCase):
    def test_downloader_supports_i131(self) -> None:
        self.assertIn("i-131", FORM_SPECS)
        self.assertEqual(FORM_SPECS["i-131"].page_url, "https://www.uscis.gov/i-131")

    def test_downloader_builds_generic_specs(self) -> None:
        spec = spec_for("I-765")
        self.assertEqual(spec.page_url, "https://www.uscis.gov/i-765")
        self.assertTrue(spec.pdf_suffix.endswith("/forms/i-765.pdf"))
        with self.assertRaises(SystemExit):
            spec_for("../etc/passwd")

    def test_complete_g28_plan_has_no_schema_findings(self) -> None:
        with TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "g28.pdf"
            write_blank_pdf(pdf_path)
            findings = audit.schema_findings(
                pdf_path=pdf_path,
                kind="g-28",
                questions=complete_g28_questions(),
                manifest_entry={"question_schema": SCHEMA_G28_CLIENT},
            )
        self.assertEqual(findings, [])

    def test_schema_flags_missing_required_question(self) -> None:
        with TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "g28.pdf"
            write_blank_pdf(pdf_path)
            questions = [
                item
                for item in complete_g28_questions()
                if item["key"] != "client_contact"
            ]
            findings = audit.plan_findings(
                pdf_path=pdf_path,
                kind="g-28",
                manifest_entry={
                    "question_schema": SCHEMA_G28_CLIENT,
                    "questions": questions,
                },
            )

        self.assertTrue(
            any(
                finding["title"] == audit.PREDATES_TITLE
                and finding.get("question_key") == "client_contact"
                and "migrate" in finding["fix"]
                and finding["allowed_statuses"] == ["filled"]
                for finding in findings
            )
        )

    def test_schema_flags_blank_required_value(self) -> None:
        with TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "g28.pdf"
            write_blank_pdf(pdf_path)
            findings = audit.plan_findings(
                pdf_path=pdf_path,
                kind="g-28",
                manifest_entry={
                    "question_schema": SCHEMA_G28_CLIENT,
                    "questions": complete_g28_questions(Line9_DaytimeTelephoneNumber=""),
                },
            )

        self.assertTrue(
            any(
                finding["title"] == "Question plan leaves required form values blank"
                and finding.get("question_key") == "client_contact"
                and "Line9_DaytimeTelephoneNumber" in finding.get("fields", [])
                for finding in findings
            )
        )

    def test_visible_output_gap_is_an_error(self) -> None:
        with TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "g28.pdf"
            write_blank_pdf(pdf_path)
            with patch.object(audit, "extract_pdf_text", return_value="Example Law PLLC"):
                findings = audit.plan_findings(
                    pdf_path=pdf_path,
                    kind="g-28",
                    manifest_entry={
                        "question_schema": SCHEMA_G28_CLIENT,
                        "questions": complete_g28_questions(),
                    },
                )

        self.assertTrue(
            any(
                finding["title"] == "Visible filing copy does not show a filled question value"
                and finding.get("question_key") == "client_identity"
                for finding in findings
            )
        )

    def test_official_blank_defaults_do_not_count_as_unexpected_user_values(self) -> None:
        manifest_entry = {
            "expected_fields": {},
            "allowed_nonempty_bases": [],
            "official_form": {"pdf_path": "/tmp/blank-i131.pdf"},
        }
        with patch.object(
            audit,
            "load_blank_form_values",
            return_value={"P9_Line1_EAD": "0"},
        ):
            findings = audit.intent_findings(
                pdf_path=Path("/tmp/filled-i131.pdf"),
                kind="i-131",
                actual_values={"P9_Line1_EAD": "0"},
                manifest_entry=manifest_entry,
            )

        self.assertFalse(
            any(finding["title"] == "Unexpected non-empty XFA fields are present" for finding in findings)
        )

    def test_field_value_uses_nonempty_indexed_choice_when_base_is_blank(self) -> None:
        values = {
            "CB_AppType": "",
            "CB_AppType[4]": "5",
            "Line4_Checkbox": "",
            "Line4_Checkbox[1]": "A",
        }
        self.assertEqual(audit.field_value(values, "CB_AppType"), "5")
        self.assertEqual(audit.field_value(values, "Line4_Checkbox"), "A")

    def test_field_value_normalizes_escaped_field_names(self) -> None:
        values = {
            "Pt8Line42.a_YesNo[1]": "N",
        }
        self.assertEqual(audit.field_value(values, "Pt8Line42\\.a_YesNo"), "N")

    def test_acro_values_uses_button_widget_appearance_state(self) -> None:
        class FakeRef:
            def __init__(self, obj: object) -> None:
                self._obj = obj

            def get_object(self) -> object:
                return self._obj

        class FakeReader:
            def __init__(self) -> None:
                self.pages = [
                    {
                        "/Annots": [
                            FakeRef(
                                {
                                    "/Subtype": "/Widget",
                                    "/FT": "/Btn",
                                    "/T": "Pt1Line6_CB_Sex[1]",
                                    "/AS": "/M",
                                }
                            )
                        ]
                    }
                ]

            def get_fields(self) -> dict[str, object]:
                return {
                    "form1[0].#subform[1].Pt1Line6_CB_Sex[1]": {
                        "/FT": "/Btn",
                        "/V": None,
                    },
                    "form1[0].#subform[1].Pt1Line7_CityTownOfBirth[0]": {
                        "/FT": "/Tx",
                        "/V": "Springfield",
                    },
                }

        with patch.object(audit, "PdfReader", return_value=FakeReader()):
            values = audit.acro_values(Path("/tmp/fake.pdf"))

        self.assertEqual(values.get("Pt1Line6_CB_Sex[1]"), "M")
        self.assertEqual(values.get("Pt1Line7_CityTownOfBirth"), "Springfield")

    def test_age_from_dob_accepts_iso_dates(self) -> None:
        self.assertEqual(
            audit.age_from_dob("2010-06-15", today=audit.datetime(2026, 3, 23, tzinfo=audit.UTC)),
            15,
        )

    def test_collapse_overlapping_findings_keeps_single_unresolved_blocker(self) -> None:
        findings = [
            {
                "severity": "error",
                "form": "i-131",
                "file": "/tmp/example-i131.pdf",
                "title": "Advance parole travel details are missing",
                "fields": [
                    "P7_Line1_DateOfDeparture",
                    "P7_Line2_Purpose",
                    "P7_Line3_ListCountries",
                    "P7_Line4_CB",
                ],
            },
            {
                "severity": "error",
                "form": "i-131",
                "file": "/tmp/example-i131.pdf",
                "title": "Proposed travel details is still pending client input",
                "question_key": "proposed_travel",
                "fields": [
                    "P7_Line1_DateOfDeparture",
                    "P7_Line2_Purpose",
                    "P7_Line3_ListCountries",
                    "P7_Line4_CB",
                ],
            },
        ]

        collapsed = audit.collapse_overlapping_findings(findings)

        self.assertEqual(len(collapsed), 1)
        self.assertEqual(collapsed[0]["question_key"], "proposed_travel")

    def test_i130_schema_uses_petitioner_legal_name_not_other_names(self) -> None:
        fields = get_question_schema(SCHEMA_I130_FAMILY_PETITION)["required_questions"][
            "petitioner_identity"
        ]["required_fields"]
        self.assertIn("Pt2Line4a_FamilyName", fields)
        self.assertNotIn("Pt2Line5a_FamilyName", fields)

    def test_skeleton_plan_covers_every_required_question(self) -> None:
        plan = skeleton_plan(SCHEMA_G28_CLIENT)
        keys = {item["key"] for item in plan["questions"]}
        self.assertEqual(keys, set(get_question_schema(SCHEMA_G28_CLIENT)["required_questions"]))
        self.assertEqual(plan["kind"], "g-28")


class XfaSyncTests(unittest.TestCase):
    def _acro(self, base: str, field_type: str, states: list[tuple[str, ...]]) -> list[xfa_tools.AcroField]:
        return [
            xfa_tools.AcroField(
                full_name=f"form1[0].#subform[0].{base}[{index}]",
                base=base,
                acro_index=index,
                field_type=field_type,
                on_states=state,
            )
            for index, state in enumerate(states)
        ]

    def test_padded_checkbox_state_is_normalized(self) -> None:
        acro = {"Line3b_Unit": self._acro("Line3b_Unit", "/Btn", [(" STE ",), (" FLR ",), (" APT ",)])}
        fields, changes = xfa_tools.normalize_button_values({"Line3b_Unit": "STE"}, acro)
        self.assertEqual(fields["Line3b_Unit"], " STE ")
        self.assertEqual(changes, {"Line3b_Unit": " STE "})

    def test_global_checkbox_group_turns_on_only_matching_widget(self) -> None:
        acro = {"Line4_Checkbox": self._acro("Line4_Checkbox", "/Btn", [("R",), ("A",), ("P",)])}
        form = ET.fromstring("<form1><Line4_Checkbox>P</Line4_Checkbox></form1>")
        updates, xfa_only = xfa_tools.acro_updates_for(
            touched_bases={"Line4_Checkbox"},
            form_node=form,
            acro=acro,
            global_names={"Line4_Checkbox"},
        )
        self.assertEqual(xfa_only, [])
        self.assertEqual(
            list(updates.values()),
            ["/Off", "/Off", "/P"],
        )

    def test_repeated_text_field_maps_by_occurrence(self) -> None:
        acro = {"Pt4Line49_CountryOfBirth": self._acro("Pt4Line49_CountryOfBirth", "/Tx", [(), ()])}
        form = ET.fromstring(
            "<form1><Pt4Line49_CountryOfBirth/><Pt4Line49_CountryOfBirth>Canada</Pt4Line49_CountryOfBirth></form1>"
        )
        updates, _ = xfa_tools.acro_updates_for(
            touched_bases={"Pt4Line49_CountryOfBirth"},
            form_node=form,
            acro=acro,
            global_names=set(),
        )
        self.assertEqual(list(updates.values()), ["", "Canada"])


PARENT_PAGE_HTML = """
<a href="/sites/default/files/document/forms/i-999.pdf">Form I-999</a>
<a href="/sites/default/files/document/forms/i-999instr.pdf">Instructions for Form I-999</a>
<a href="/sites/default/files/document/forms/i-999a.pdf">Form I-999A, Supplement</a>
<div class="accordion__header" tabindex="0">Edition Date</div>
<div class="accordion__panel"><p>01/02/25<span>.</span> You can find the edition date at the bottom.</p></div>
"""


class DownloaderCompanionFormTests(unittest.TestCase):
    """Bug 1: companion forms such as the I-130A have no uscis.gov page of their own."""

    def _fake_site(self, pages: dict[str, str]):
        def fetch_text(url: str) -> str:
            if url not in pages:
                raise HTTPError(url, 404, "Not Found", hdrs=None, fp=None)
            return pages[url]

        return fetch_text

    def test_known_companion_resolves_from_parent_page(self) -> None:
        spec = spec_for("I-130A")
        self.assertEqual(spec.page_url, "https://www.uscis.gov/i-130")
        self.assertEqual(spec.parent_id, "i-130")
        self.assertEqual(spec.pdf_name, "I-130A.pdf")

    def test_unknown_companion_falls_back_to_parent_page_on_404(self) -> None:
        site = self._fake_site({"https://www.uscis.gov/i-999": PARENT_PAGE_HTML})
        with (
            TemporaryDirectory() as tmpdir,
            patch.object(download_uscis_forms, "fetch_text", site),
            patch.object(download_uscis_forms, "fetch_bytes", return_value=b"%PDF-1.7 test"),
        ):
            entry, _ = run_quietly(
                download_uscis_forms.download_form,
                spec_for("i-999a"),
                Path(tmpdir),
                include_instructions=True,
                overwrite=False,
            )
            self.assertTrue((Path(tmpdir) / "I-999A.pdf").exists())
            self.assertTrue((Path(tmpdir) / "I-999 Instructions.pdf").exists())

        self.assertEqual(entry["page_url"], "https://www.uscis.gov/i-999")
        self.assertEqual(entry["requested_page_url"], "https://www.uscis.gov/i-999a")
        self.assertTrue(entry["pdf_url"].endswith("/forms/i-999a.pdf"))
        self.assertEqual(entry["parent_form"], "i-999")
        self.assertEqual(entry["edition_date"], "01/02/25")
        self.assertIn("I-999 page", entry["edition_source"])
        self.assertEqual(entry["instructions_shared_with"], "i-999")
        self.assertTrue(entry["instructions_url"].endswith("/forms/i-999instr.pdf"))

    def test_404_for_a_form_with_no_parent_is_still_an_error(self) -> None:
        with patch.object(download_uscis_forms, "fetch_text", self._fake_site({})):
            with self.assertRaises(HTTPError):
                download_uscis_forms.fetch_form_page(spec_for("i-999"))

    def test_parent_page_without_the_pdf_names_both_pages(self) -> None:
        site = self._fake_site({"https://www.uscis.gov/i-999": "<p>no links</p>"})
        with patch.object(download_uscis_forms, "fetch_text", site):
            with self.assertRaises(RuntimeError) as caught:
                download_uscis_forms.download_form(
                    spec_for("i-999a"), Path("/nonexistent"), include_instructions=False, overwrite=False
                )
        self.assertIn("https://www.uscis.gov/i-999a or https://www.uscis.gov/i-999", str(caught.exception))


class DownloaderMetadataTests(unittest.TestCase):
    """The downloader records what a file actually is, keeps other forms' entries, and lets a
    form without separate instructions through."""

    SITE = {
        "https://www.uscis.gov/g-1145": (
            '<a href="/sites/default/files/document/forms/g-1145.pdf">G-1145</a>'
            '<div>Edition Date</div><div><p>09/26/14. You can also use previous editions.</p></div>'
        ),
        "https://www.uscis.gov/i-999": PARENT_PAGE_HTML,
    }

    def fetch_text(self, url: str) -> str:
        if url not in self.SITE:
            raise HTTPError(url, 404, "Not Found", hdrs=None, fp=None)
        return self.SITE[url]

    def test_g1145_has_no_instructions_and_that_is_fine(self) -> None:
        self.assertFalse(spec_for("g-1145").has_instructions)
        self.assertTrue(spec_for("g-1450").has_instructions)
        with (
            TemporaryDirectory() as tmpdir,
            patch.object(download_uscis_forms, "fetch_text", self.fetch_text),
            patch.object(download_uscis_forms, "fetch_bytes", return_value=b"%PDF-1.7 test\n%%EOF\n"),
            patch.object(download_uscis_forms, "pdf_footer_edition", return_value="09/26/14"),
        ):
            entry, _ = run_quietly(
                download_uscis_forms.download_form, spec_for("g-1145"), Path(tmpdir),
                include_instructions=True, overwrite=False,
            )
        self.assertIn("none published", entry["instructions_status"])
        self.assertEqual(entry["file_edition"], "09/26/14")
        self.assertNotIn("file_edition_note", entry)

    def test_a_kept_file_records_its_own_edition(self) -> None:
        with (
            TemporaryDirectory() as tmpdir,
            patch.object(download_uscis_forms, "fetch_text", self.fetch_text),
            patch.object(download_uscis_forms, "pdf_footer_edition", return_value="06/30/22"),
        ):
            (Path(tmpdir) / "I-999.pdf").write_bytes(b"%PDF-1.7 old\n%%EOF\n")
            entry, _ = run_quietly(
                download_uscis_forms.download_form, spec_for("i-999"), Path(tmpdir),
                include_instructions=False, overwrite=False,
            )
        self.assertEqual(entry["pdf_status"], "kept existing file (pass --overwrite to replace)")
        self.assertEqual((entry["edition_date"], entry["file_edition"]), ("01/02/25", "06/30/22"))
        self.assertIn("is the 06/30/22 edition; the page now lists 01/02/25", entry["file_edition_note"])

    def test_metadata_is_merged_not_replaced(self) -> None:
        with (
            TemporaryDirectory() as tmpdir,
            patch.object(download_uscis_forms, "fetch_text", self.fetch_text),
            patch.object(download_uscis_forms, "fetch_bytes", return_value=b"%PDF-1.7 test\n%%EOF\n"),
            patch.object(download_uscis_forms, "pdf_footer_edition", return_value="09/26/14"),
        ):
            metadata = Path(tmpdir) / "forms-metadata.json"
            metadata.write_text(json.dumps({"i-130": {"edition_date": "04/01/24"}}))
            argv = ["download_uscis_forms.py", "--output-dir", tmpdir, "--metadata-json", str(metadata), "g-1145"]
            with patch.object(sys, "argv", argv):
                code, _ = run_quietly(download_uscis_forms.main)
            merged = json.loads(metadata.read_text())
        self.assertEqual(code, 0)
        self.assertEqual(sorted(merged), ["g-1145", "i-130"])


class EditionCheckTests(unittest.TestCase):
    """Item 11: a blank of an edition the tools were not built for is not filled silently."""

    def check(self, *, footer: tuple[str, str] | None, same_file: bool = False, same_boxes: bool = True) -> dict:
        with TemporaryDirectory() as tmp:
            blank = Path(tmp) / "I-485.pdf"
            blank.write_bytes(b"%PDF-1.7 a blank\n%%EOF\n")
            built = {
                "edition": "09/18/26",
                "field_list": "I-485.json",
                "sha256": forms_workflow.file_sha256(blank) if same_file else "0" * 64,
                "fields": {"A": {"type": "/Tx", "states": []}},
            }
            with (
                patch.object(editions, "schema_blank", return_value=built),
                patch.object(editions, "footer_edition", return_value=footer),
                patch.object(editions, "blank_layout",
                             return_value={"fields": built["fields"] if same_boxes else {}, "widgets": {}}),
            ):
                return editions.check_blank("i-485", blank)

    def test_statuses(self) -> None:
        self.assertEqual(self.check(footer=None, same_file=True)["status"], editions.MATCH)
        self.assertEqual(self.check(footer=("I-485", "09/18/26"))["status"], editions.SAME_EDITION)
        self.assertEqual(self.check(footer=("I-485", "09/18/26"), same_boxes=False)["status"], editions.CHANGED_BOXES)
        newer = self.check(footer=("I-485", "10/01/27"))
        self.assertEqual((newer["status"], newer["file_edition"]), (editions.NEW_EDITION, "10/01/27"))
        self.assertEqual(self.check(footer=None)["status"], editions.UNREADABLE)
        with TemporaryDirectory() as tmp:
            other = Path(tmp) / "X-1.pdf"
            other.write_bytes(b"%PDF-1.7")
            with patch.object(editions, "footer_edition", return_value=None):
                self.assertEqual(editions.check_blank("x-1", other)["status"], editions.NO_SCHEMA)

    def test_footer_is_read_from_the_first_page_text(self) -> None:
        for text, expected in (
            ("Form I-485 Edition 09/18/26 Page 1 of 24", ("I-485", "09/18/26")),
            ("Form G-28 09/17/18    Page 1 of 4", ("G-28", "09/17/18")),
            ("Form I-130A\nEdition 04/01/24", ("I-130A", "04/01/24")),
            ("no footer here", None),
        ):
            with patch.object(editions, "first_page_text", return_value=text):
                self.assertEqual(editions.footer_edition(Path("/x.pdf")), expected)

    def test_the_open_item_reads_as_the_contract_asks(self) -> None:
        item = editions.suggested_open_item(self.check(footer=("I-485", "10/01/27")))
        self.assertEqual((item["id"], item["type"], item["blocks_filing"]), ("forms-edition-i-485", "attorney_decision", True))
        self.assertIn("new edition of the I-485", item["title"])
        self.assertLess(len(item["title"]), 80)
        self.assertTrue(item["question"].endswith("?") and len(item["question"]) < 140)
        self.assertLess(len(item["recommendation"]), 120)
        self.assertIn("10/01/27 edition", item["detail"])
        for word in ("schema", "workflow", "artifact", "vault"):
            self.assertNotIn(word, json.dumps(item).lower())

    def test_live_check_fails_when_the_page_shows_no_edition(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp) / "Sample"
            blank_dir = matter / "output" / "working" / "forms" / "blank"
            blank_dir.mkdir(parents=True)
            (blank_dir / "I-485.pdf").write_bytes(b"%PDF-1.7")
            current = {"kind": "i-485", "status": editions.MATCH, "file_edition": "09/18/26", "schema_edition": "09/18/26"}
            for live, code in (({"page_url": "https://www.uscis.gov/i-485", "edition_date": "", "edition_note": ""}, 1),
                               ({"page_url": "https://www.uscis.gov/i-485", "edition_date": "09/18/26", "edition_note": ""}, 0)):
                out = io.StringIO()
                with (
                    patch.object(editions, "check_blank", return_value=dict(current)),
                    patch.object(editions, "live_edition", return_value=dict(live)),
                    contextlib.redirect_stdout(out),
                ):
                    self.assertEqual(editions.main([str(matter), "--live"]), code)
                if code:
                    self.assertIn("its edition date could not be found", out.getvalue())

    def test_live_check_fails_when_uscis_gov_cannot_be_reached(self) -> None:
        # The final review reads exit 1 as a finding: an unreachable page is checked by hand, never a pass.
        with TemporaryDirectory() as tmp:
            matter = Path(tmp) / "Sample"
            blank_dir = matter / "output" / "working" / "forms" / "blank"
            blank_dir.mkdir(parents=True)
            (blank_dir / "I-130.pdf").write_bytes(b"%PDF-1.7")
            current = {"kind": "i-130", "status": editions.MATCH, "file_edition": "04/01/24", "schema_edition": "04/01/24"}
            out = io.StringIO()
            with (
                patch.object(editions, "check_blank", return_value=dict(current)),
                patch.object(editions, "live_edition", side_effect=OSError("network is unreachable")),
                contextlib.redirect_stdout(out),
            ):
                self.assertEqual(editions.main([str(matter), "--live"]), 1)
            self.assertIn("I-130: 04/01/24, the edition the form tools were built for; uscis.gov could not be checked "
                          "(network is unreachable)", out.getvalue())

    def test_an_older_blank_is_worded_as_one_and_calls_for_no_decision(self) -> None:
        older = self.check(footer=("I-485", "01/20/25"))
        self.assertEqual(older["status"], editions.NEW_EDITION)
        self.assertTrue(editions.is_older(older))
        self.assertIn("older than the 09/18/26 edition", editions.problem_text(older))
        self.assertIsNone(editions.suggested_open_item(older))
        self.assertIn("--refresh-blank I-485", editions.fix_text(older))
        self.assertIn("--across-editions", editions.fix_text(older))
        self.assertIn("OLDER BLANK", editions.check_lines([older])[0])
        newer = self.check(footer=("I-485", "10/01/27"))
        self.assertFalse(editions.is_older(newer))
        self.assertIn("newer than the 09/18/26 edition", editions.problem_text(newer))
        changed = editions.suggested_open_item(self.check(footer=("I-485", "09/18/26"), same_boxes=False))
        self.assertEqual(changed["title"], "The I-485 blank doesn't match the form tools")
        self.assertIn("--refresh-blank I-485", editions.fix_text(self.check(footer=None)))

    def test_the_open_item_says_what_preparing_on_the_new_edition_does(self) -> None:
        item = editions.suggested_open_item(self.check(footer=("I-485", "10/01/27")))
        self.assertIn("only unchanged boxes filled, every box checked by hand", item["question"])
        self.assertIn("fill only the boxes that are the same", item["detail"])
        self.assertIn("can't pass its check until every box has been checked", item["detail"])

    def test_audit_holds_a_new_edition_form_until_every_filled_box_is_checked(self) -> None:
        check = {"status": "new_edition", "file_edition": "10/01/27", "schema_edition": "09/18/26",
                 "open_item": "forms-edition-i-485", "withheld": {"Pt1Line1a_FamilyName": "moved on page 1"}}
        entry = {"edition_check": check, "expected_fields": {"Pt1Line1b_GivenName": "Alex", "Pt1Line3_DOB": "01/02/1990"}}
        findings = audit.edition_findings(kind="i-485", pdf_path=Path("/x/I-485.pdf"), manifest_entry=entry)
        self.assertEqual(len(findings), 2)
        edition, withheld = findings
        self.assertIn("10/01/27 edition", edition["title"])
        self.assertNotIn("open_item", edition)  # no open item can explain it before the check
        self.assertEqual(edition["unchecked_count"], 2)
        self.assertEqual(withheld["fields"], ["Pt1Line1a_FamilyName"])
        # A partial check, or one for another edition, still holds it.
        entry["new_edition_review"] = {"edition": "10/01/27", "boxes": {"Pt1Line1b_GivenName": "Part 1 item 1.b, same"}}
        self.assertEqual(audit.edition_findings(kind="i-485", pdf_path=Path("/x"), manifest_entry=entry)[0]["unchecked_boxes"],
                         ["Pt1Line3_DOB"])
        entry["new_edition_review"]["boxes"]["Pt1Line3_DOB"] = "Part 1 item 3, same"
        entry["new_edition_review"]["edition"] = "09/18/26"
        self.assertIn("unchecked_boxes", audit.edition_findings(kind="i-485", pdf_path=Path("/x"), manifest_entry=entry)[0])
        entry["new_edition_review"]["edition"] = "10/01/27"
        checked = audit.edition_findings(kind="i-485", pdf_path=Path("/x"), manifest_entry=entry)
        self.assertEqual(checked[0]["open_item"], "forms-edition-i-485")
        self.assertNotIn("open_item", checked[1])  # answers left off the form are never tied
        audit.tie_open_items(checked, entry)
        self.assertNotIn("open_item", checked[1])
        self.assertEqual(audit.edition_findings(kind="i-485", pdf_path=Path("/x"), manifest_entry={}), [])


class DownloaderRetryTests(unittest.TestCase):
    """uscis.gov transfers sometimes end early; the downloader retries before giving up."""

    URL = "https://www.uscis.gov/sites/default/files/document/forms/i-999.pdf"

    def setUp(self) -> None:
        sleeper = patch.object(download_uscis_forms.time, "sleep")
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)

    def fetch_once(self, *results):
        return patch.object(download_uscis_forms, "fetch_once", side_effect=list(results))

    def test_truncated_pdf_is_fetched_again_and_the_whole_file_saved(self) -> None:
        whole = b"%PDF-1.7 whole file\n%%EOF\n"
        with TemporaryDirectory() as tmpdir, self.fetch_once(b"%PDF-1.7 cut off mid-str", whole) as fetch:
            destination = Path(tmpdir) / "I-999.pdf"
            status = download_uscis_forms.download_file(self.URL, destination, overwrite=True)
            self.assertEqual(destination.read_bytes(), whole)
        self.assertEqual(status, "downloaded")
        self.assertEqual(fetch.call_count, 2)
        self.sleep.assert_called_once_with(download_uscis_forms.RETRY_DELAYS[0])

    def test_dropped_connections_are_retried(self) -> None:
        with self.fetch_once(IncompleteRead(b"partial"), ConnectionResetError(), b"<html>page</html>") as fetch:
            payload = download_uscis_forms.fetch_bytes(self.URL)
        self.assertEqual(payload, b"<html>page</html>")
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], list(download_uscis_forms.RETRY_DELAYS))

    def test_gives_up_after_three_attempts(self) -> None:
        with self.fetch_once(*[IncompleteRead(b"partial")] * 3) as fetch:
            with self.assertRaises(IncompleteRead):
                download_uscis_forms.fetch_bytes(self.URL)
        self.assertEqual(fetch.call_count, 3)

    def test_server_errors_are_retried(self) -> None:
        busy = HTTPError(self.URL, 503, "Service Unavailable", hdrs=None, fp=None)
        with self.fetch_once(busy, b"ok") as fetch:
            self.assertEqual(download_uscis_forms.fetch_bytes(self.URL), b"ok")
        self.assertEqual(fetch.call_count, 2)

    def test_404_is_not_retried(self) -> None:
        missing = HTTPError(self.URL, 404, "Not Found", hdrs=None, fp=None)
        with self.fetch_once(missing, b"never reached") as fetch:
            with self.assertRaises(HTTPError):
                download_uscis_forms.fetch_bytes(self.URL)
        self.assertEqual(fetch.call_count, 1)
        self.sleep.assert_not_called()

    def test_bot_check_page_is_reported_not_retried(self) -> None:
        with TemporaryDirectory() as tmpdir, self.fetch_once(b"<html>Access denied</html>") as fetch:
            with self.assertRaises(RuntimeError) as caught:
                download_uscis_forms.download_file(self.URL, Path(tmpdir) / "I-999.pdf", overwrite=True)
        self.assertIn("did not return a PDF", str(caught.exception))
        self.assertEqual(fetch.call_count, 1)

    def test_body_shorter_than_content_length_counts_as_truncated(self) -> None:
        class Response:
            headers = {"Content-Length": "10"}

            def read(self) -> bytes:
                return b"abc"

            def __enter__(self):
                return self

            def __exit__(self, *exc) -> None:
                return None

        with patch.object(download_uscis_forms, "urlopen", return_value=Response()):
            with self.assertRaises(download_uscis_forms.TruncatedDownload):
                download_uscis_forms.fetch_once(self.URL)

def i485_values(**overrides: str) -> dict[str, str]:
    values = {
        "Pt2Line2_CB": "1fA",
        "Pt2Line11_CB": "11A",
        "Pt2Line5_CB": "N",
        "Pt3Line1_CB": "5",
        "Pt2Line1_YN": "N",
        "Pt2Line4_CB": "N",
    }
    values.update(overrides)
    return {key: value for key, value in values.items() if value}


class I485CategoryTests(unittest.TestCase):
    """Bug 2: Part 2 checks follow the category selected in item 3."""

    def _findings(self, values: dict[str, str]) -> list[dict[str, object]]:
        return audit.audit_form("i-485", Path("/tmp/i485.pdf"), values, xfa=values, acro=values)

    def test_family_based_filing_is_not_held_to_employment_fields(self) -> None:
        findings = self._findings(i485_values(Pt2Line3a_CB="3a0"))
        flagged = {field for item in findings for field in item.get("fields", [])}
        for field in ("Pt2Line3b_CB140Assoc", "Pt2Line3b_CB140", "Pt2Line2_Receipt", "Pt2Line2_Date"):
            self.assertNotIn(field, flagged)
        self.assertNotIn("Missing application-basis fields", titles(findings))
        self.assertNotIn("Part 2 item 3 immigrant category is not selected", titles(findings))

    def test_employment_based_filing_still_needs_i140_details(self) -> None:
        findings = self._findings(i485_values(Pt2Line3b_CB140="3b5"))
        match = [item for item in findings if item["title"] == "Employment-based category details are incomplete"]
        self.assertEqual(len(match), 1)
        self.assertEqual(
            set(match[0]["fields"]), {"Pt2Line2_Receipt", "Pt2Line2_Date", "Pt2Line3b_CB140Assoc"}
        )

    def test_relative_details_follow_the_i140_relative_answer(self) -> None:
        findings = self._findings(
            i485_values(
                Pt2Line3b_CB140="3b5",
                Pt2Line3b_CB140Assoc="Y",
                Pt2Line2_Receipt="IOE0000000000",
                Pt2Line2_Date="01/02/2024",
            )
        )
        self.assertIn("Relative who filed or owns the I-140 employer is not described", titles(findings))

    def test_category_must_be_selected_exactly_once(self) -> None:
        self.assertIn(
            "Part 2 item 3 immigrant category is not selected", titles(self._findings(i485_values()))
        )
        both = self._findings(i485_values(Pt2Line3a_CB="3a0", Pt2Line3b_CB140="3b5"))
        self.assertIn("More than one Part 2 item 3 immigrant category is selected", titles(both))

    def test_asylee_category_needs_the_grant_date(self) -> None:
        findings = self._findings(i485_values(Pt2Line3d_AsyleeRefugeeCB="3d0", Pt2Line4_CB=""))
        self.assertIn("Asylum grant or refugee admission date is missing", titles(findings))
        self.assertNotIn("Part 2 item 4 (INA 245(i)) is not answered", titles(findings))


def complete_i130a_values() -> dict[str, str]:
    return {
        "Pt1Line3a_FamilyName": "Sample",
        "Pt1Line3b_GivenName": "Alex",
        "Pt1Line10_FamilyName": "Sample",
        "Pt1Line10_GivenName": "Pat",
        "Pt1Line11_DateofBirth": "01/02/1960",
        "Pt1Line13_CountryofBirth": "Canada",
        "Pt1Line15_CountryofResidence": "Canada",
        "Pt1Line16_FamilyName": "Sample",
        "Pt1Line16_GivenName": "Chris",
        "Pt1Line17_DateofBirth": "03/04/1961",
        "Pt1Line19_CountryofBirth": "Canada",
        "Pt1Line21_CountryofResidence": "Canada",
        "Pt1Line4a_StreetNumberName": "200 Sample Avenue",
        "Pt1Line4b_Unit": "APT",
        "Pt1Line4b_AptSteFlrNumber": "2",
        "Pt1Line4c_CityOrTown": "Springfield",
        "Pt1Line4d_State": "IL",
        "Pt1Line4e_ZipCode": "62702",
        "Pt1Line4h_Country": "United States",
        "Pt1Line5a_DateFrom": "01/01/2025",
        "Pt1Line6a_StreetNumberName": "1 Example Road",
        "Pt1Line6c_CityOrTown": "Toronto",
        "Pt1Line6h_Country": "Canada",
        "Pt1Line7a_DateFrom": "01/01/2020",
        "Pt1Line7b_DateTo": "12/31/2024",
        "Pt2Line1_EmployerOrCompName": "Example Co",
        "Pt2Line2a_StreetNumberName": "5 Example Plaza",
        "Pt2Line2c_CityOrTown": "Springfield",
        "Pt2Line2d_State": "IL",
        "Pt2Line2e_ZipCode": "62701",
        "Pt2Line2h_Country": "USA",
        "Pt2Line3_Occupation": "Analyst",
        "Pt2Line4a_DateFrom": "02/01/2025",
        "Pt3Line1_EmployerOrCompName": "N/A",
        "Pt4Line3_DaytimePhoneNumber1": "5555550124",
        "Pt6Line1a_PreparerFamilyName": "Example",
        "Pt6Line1b_PreparerGivenName": "Jane",
        "Pt6Line2_BusinessName": "Example Law PLLC",
        "Pt6Line4_DaytimePhoneNumber": "5555550100",
        "Pt6Line6_Email": "jane@example.com",
        "Pt6Line7_Checkbox": "B",
        "Pt6Line7b_Checkbox": "Y",
        "CheckBox1": "1",
        "AttorneyStateBarNumber": "00000000",
    }


def g28_manifest(*, subject: str = "beneficiary", bar: str = "00000000") -> dict[str, dict[str, object]]:
    return {
        "/tmp/G-28 - Beneficiary.pdf": {
            "kind": "g-28",
            "subject": subject,
            "expected_fields": {
                "Pt2Line1b_BarNumber": bar,
                "Pt1Line2a_FamilyName": "Example",
                "Pt1Line2b_GivenName": "Jane",
            },
        }
    }


class I130AAuditTests(unittest.TestCase):
    """Bug 3: the I-130A has its own audit kind."""

    def _audit(self, values: dict[str, str], acro: dict[str, str] | None = None):
        return audit.audit_form("i-130a", Path("/tmp/i130a.pdf"), values, xfa=values,
                                acro=values if acro is None else acro)

    def test_i130a_is_an_accepted_kind(self) -> None:
        kind, path = audit.parse_check_arg("i-130a=/tmp/I-130A.pdf")
        self.assertEqual((kind, path), ("i-130a", Path("/tmp/I-130A.pdf")))

    def test_complete_i130a_has_no_errors(self) -> None:
        findings = self._audit(complete_i130a_values())
        self.assertEqual([item for item in findings if item["severity"] == "error"], [])
        self.assertEqual(titles(findings), ["Signature fields are still blank"])

    def test_names_and_parent_dates_of_birth_are_required(self) -> None:
        values = complete_i130a_values()
        del values["Pt1Line3a_FamilyName"], values["Pt1Line17_DateofBirth"]
        findings = self._audit(values)
        by_title = {item["title"]: item["fields"] for item in findings}
        self.assertEqual(by_title["Missing high-signal identity fields"], ["Pt1Line3a_FamilyName"])
        self.assertEqual(
            by_title["Parent 2 (Part 1 items 17-23) is missing name, birth or residence details"],
            ["Pt1Line17_DateofBirth"],
        )

    def test_history_rows_must_be_coherent(self) -> None:
        values = complete_i130a_values()
        values["Pt1Line7a_DateFrom"] = "06/01/2025"  # address 2 starts after it ends
        del values["Pt1Line4b_AptSteFlrNumber"]  # unit type with no number
        values["Pt2Line5_EmployerOrCompName"] = "Old Employer"  # employer 2 started but incomplete
        findings = self._audit(values)
        names = titles(findings)
        self.assertIn("Physical address 2 (Part 1 items 6-7) ends before it starts", names)
        self.assertIn(
            "Physical address 1 (current, Part 1 items 4-5): apartment, suite or floor type and number do not match",
            names,
        )
        incomplete = [item for item in findings if item["title"] == "Employer 2 (Part 2 items 5-8) is incomplete"]
        self.assertEqual(len(incomplete), 1)
        self.assertIn("Pt2Line7_Occupation", incomplete[0]["fields"])
        self.assertIn("Pt2Line8b_DateTo", incomplete[0]["fields"])

    def test_overlapping_addresses_are_a_warning(self) -> None:
        values = complete_i130a_values()
        values["Pt1Line7b_DateTo"] = "03/01/2025"
        overlap = [item for item in self._audit(values) if "ends after" in str(item["title"])]
        self.assertEqual([item["severity"] for item in overlap], ["warning"])

    def test_unemployed_current_row_needs_no_address(self) -> None:
        values = complete_i130a_values()
        for name in [
            "Pt2Line2a_StreetNumberName",
            "Pt2Line2c_CityOrTown",
            "Pt2Line2d_State",
            "Pt2Line2e_ZipCode",
            "Pt2Line2h_Country",
            "Pt2Line3_Occupation",
        ]:
            del values[name]
        values["Pt2Line1_EmployerOrCompName"] = "Unemployed"
        self.assertNotIn("Employer 1 (current, Part 2 items 1-4) is incomplete", titles(self._audit(values)))

    def test_layer_disagreement_is_reported(self) -> None:
        values = complete_i130a_values()
        acro = dict(values, Pt1Line3b_GivenName="Alexander")
        findings = self._audit(values, acro)
        self.assertIn(
            "Visible I-130A output does not reflect stored identity, history, or attorney fields",
            titles(findings),
        )

    def test_attorney_box_agrees_with_the_g28(self) -> None:
        def attorney_box(values: dict[str, str]) -> list[dict[str, object]]:
            form = audit.Form("i-130a", Path("/tmp/i130a.pdf"), values, manifest_entry={"subject": "beneficiary"},
                              intent_manifest=g28_manifest())
            audit.attorney_box_findings(form)
            return form.findings

        values = complete_i130a_values()
        consistent = attorney_box(values)
        self.assertEqual(consistent, [])

        mismatched = attorney_box(dict(values, AttorneyStateBarNumber="99999999", Pt6Line1a_PreparerFamilyName="Other"))
        self.assertIn("Attorney box bar number does not match the G-28", titles(mismatched))
        self.assertIn(
            "Preparer says they are the attorney, but the name differs from the attorney on the G-28",
            titles(mismatched),
        )

        unchecked = dict(values)
        del unchecked["CheckBox1"]
        missing_box = attorney_box(unchecked)
        self.assertIn(
            "A G-28 is prepared for this person, but the attorney box does not say it is attached",
            titles(missing_box),
        )
        self.assertIn(
            "Part 6 says the attorney's representation goes beyond preparing the form, "
            "but the page 1 attorney box does not say a G-28 is attached",
            titles(self._audit(unchecked)),
        )


def courier_widget(value: str, *, width: float, height: float = 18.0, multiline: bool = False, bbox=None):
    return audit.TextWidget(
        name="Field",
        key=("Field", 0),
        page=1,
        value=value,
        width=width,
        height=height,
        font=audit.font_metrics("CourierNewPS-BoldMT", "CourierNewPS-BoldMT", bbox),
        font_size=10.0,
        multiline=multiline,
    )


class OverflowTests(unittest.TestCase):
    """Bug 4: text that does not fit its box is reported as overflow, with the fix."""

    def test_single_line_width_uses_font_metrics(self) -> None:
        # 222 pt box: the generated appearance leaves 216 pt, which is 36 Courier characters at 10 pt.
        self.assertIsNone(audit.text_overflow(courier_widget("A" * 36, width=222)))
        info = audit.text_overflow(courier_widget("A" * 37, width=222))
        self.assertIsNotNone(info)
        self.assertEqual(info["chars_per_line"], 36)

    def test_helvetica_widths_and_auto_size(self) -> None:
        helvetica = audit.font_metrics("Helv", "Helvetica")
        self.assertAlmostEqual(helvetica.width("iiii", 10), 8.88)
        self.assertAlmostEqual(helvetica.width("MMMM", 10), 33.32)
        # Auto-size (0 Tf) shrinks to fit, down to 4 pt: 30 Ms are 100 pt there, 60 are 200 pt.
        auto = audit.TextWidget("Field", ("Field", 0), 1, "M" * 30, 120.0, 18.0, helvetica, 0.0, False)
        self.assertIsNone(audit.text_overflow(auto))
        too_long = audit.TextWidget("Field", ("Field", 0), 1, "M" * 60, 120.0, 18.0, helvetica, 0.0, False)
        self.assertIsNotNone(audit.text_overflow(too_long))  # still too wide at 4 pt
        # An auto-sized multi-line box wraps and shrinks; it overflows only when 4 pt is not enough.
        box = dict(width=120.0, height=30.0, font=helvetica, font_size=0.0, multiline=True)
        self.assertIsNone(audit.text_overflow(audit.TextWidget("F", ("F", 0), 1, "word " * 20, **box)))
        info = audit.text_overflow(audit.TextWidget("F", ("F", 0), 1, "word " * 200, **box))
        self.assertGreater(info["lines"], info["lines_that_fit"])
        self.assertFalse(info["fits_if_rewrapped"])

    def test_multiline_box_counts_lines(self) -> None:
        # The I-485 Part 14 box: 515.9 x 90 pt, Courier New Bold 10 pt (bbox -710..1221) holds 5 lines.
        bbox = (-710.0, 1221.0)
        five = "\n".join(f"line {n}" for n in range(5))
        self.assertIsNone(audit.text_overflow(courier_widget(five, width=515.9, height=90, multiline=True, bbox=bbox)))
        eight = "\n".join(f"line {n}" for n in range(8))
        info = audit.text_overflow(courier_widget(eight, width=515.9, height=90, multiline=True, bbox=bbox))
        self.assertEqual((info["lines"], info["lines_that_fit"]), (8, 5))
        self.assertFalse(info["fits_if_rewrapped"])
        one_long_line = audit.text_overflow(
            courier_widget("word " * 40, width=515.9, height=90, multiline=True, bbox=bbox)
        )
        self.assertTrue(one_long_line["fits_if_rewrapped"])

    def test_clipped_additional_information_is_reported_as_overflow(self) -> None:
        text = "\n".join(f"Entry line {n}" for n in range(1, 9))
        question_item = question(
            key="additional_information",
            label="Part 14 additional information",
            status=STATUS_FILLED,
            field_values={"P14_Line2_AdditionalInfo": text},
            visible_values=["Entry line 8"],
        )
        overflow = {
            ("P14_Line2_AdditionalInfo", 0): {
                **audit.text_overflow(
                    courier_widget(text, width=515.9, height=90, multiline=True, bbox=(-710.0, 1221.0))
                ),
                "field": "P14_Line2_AdditionalInfo",
                "page": 24,
                "value": text,
                "multiline": True,
            }
        }
        manifest_entry = {"questions": [question_item]}
        with TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "i485.pdf"
            write_blank_pdf(pdf_path)
            rendered = "\n".join(f"Entry line {n}" for n in range(1, 6))
            with patch.object(audit, "extract_pdf_text", return_value=rendered):
                plan = audit.plan_findings(
                    pdf_path=pdf_path, kind="i-485", manifest_entry=manifest_entry, overflow=overflow
                )
                old_style = audit.plan_findings(pdf_path=pdf_path, kind="i-485", manifest_entry=manifest_entry)
        self.assertNotIn("Visible filing copy does not show a filled question value", titles(plan))
        self.assertIn("Visible filing copy does not show a filled question value", titles(old_style))

        found = audit.overflow_findings(
            kind="i-485", pdf_path=Path("/tmp/i485.pdf"), overflow=overflow, manifest_entry=manifest_entry
        )
        self.assertEqual(titles(found), ["Text is cut off in a multi-line box on the filing copy"])
        self.assertIn("Continue on an additional-information page", found[0]["fix"])
        self.assertEqual(found[0]["question_key"], "additional_information")
        self.assertEqual((found[0]["lines"], found[0]["lines_that_fit"]), (8, 5))

    def test_overflow_is_read_from_a_filled_form(self) -> None:
        with TemporaryDirectory() as tmpdir:
            blank, filled = Path(tmpdir) / "blank.pdf", Path(tmpdir) / "filled.pdf"
            write_marriage_place_form(blank)
            run_quietly(
                xfa_tools.write_filled_pdf,
                blank,
                filled,
                {"Place[0]": "A" * 40, "Place[1]": "Short", "Note": "fits"},
            )
            report = audit.overflow_report(filled)
        self.assertEqual(set(report), {("Place", 0)})
        self.assertEqual(report[("Place", 0)]["field"], "Place[0]")
        self.assertFalse(report[("Place", 0)]["multiline"])


class SharedDataNodeTests(unittest.TestCase):
    """Bug 5: mapping entries that bind the same XFA data node."""

    def test_empty_value_does_not_overwrite_a_value_for_the_same_node(self) -> None:
        resolved, shared = xfa_tools.resolve_shared_nodes(
            {"Place[0]": "Austin", "Place": ""}, global_names=set()
        )
        self.assertEqual(resolved, {"Place[0]": "Austin"})
        self.assertEqual(len(shared), 1)
        self.assertEqual(shared[0].ignored_empty, ["Place"])
        self.assertIn("same XFA data node", xfa_tools.describe_shared_node(shared[0]))

    def test_different_values_for_one_node_are_an_error_naming_both(self) -> None:
        with self.assertRaises(ValueError) as caught:
            xfa_tools.resolve_shared_nodes({"Place[0]": "Austin", "Place": "Dallas"}, global_names=set())
        message = str(caught.exception)
        self.assertIn("Place[0] = 'Austin'", message)
        self.assertIn("Place = 'Dallas'", message)

    def test_every_index_of_a_global_field_is_one_node(self) -> None:
        resolved, shared = xfa_tools.resolve_shared_nodes(
            {"Unit[0]": " STE ", "Unit[2]": ""}, global_names={"Unit"}
        )
        self.assertEqual(resolved, {"Unit": " STE "})
        self.assertTrue(shared[0].is_global)
        with self.assertRaises(ValueError):
            xfa_tools.resolve_shared_nodes({"Unit[0]": " STE ", "Unit[1]": " FLR "}, global_names={"Unit"})

    def test_distinct_indexes_are_distinct_nodes(self) -> None:
        resolved, shared = xfa_tools.resolve_shared_nodes(
            {"Place[0]": "Austin", "Place[1]": ""}, global_names=set()
        )
        self.assertEqual(resolved, {"Place[0]": "Austin", "Place[1]": ""})
        self.assertEqual(shared, [])

    def test_unbound_second_box_does_not_copy_the_first_value(self) -> None:
        acro = {
            "Place": [
                xfa_tools.AcroField(f"form1[0].#subform[0].Place[{n}]", "Place", n, "/Tx", ()) for n in range(2)
            ]
        }
        form = ET.fromstring("<form1><Place>Austin</Place></form1>")
        updates, _ = xfa_tools.acro_updates_for(
            touched_bases={"Place"}, form_node=form, acro=acro, global_names=set()
        )
        self.assertEqual(list(updates.values()), ["Austin", ""])

    def test_fill_verify_passes_and_explains_the_shared_node(self) -> None:
        with TemporaryDirectory() as tmpdir:
            blank, filled, mapping = (Path(tmpdir) / name for name in ("blank.pdf", "filled.pdf", "map.json"))
            write_marriage_place_form(blank)
            mapping.write_text(json.dumps({"Place[0]": "Austin", "Place": "", "Unit": "STE"}))
            code, stderr = run_quietly(xfa_tools.fill_pdf, blank, filled, mapping, True)
            self.assertEqual(code, 0, stderr)
            self.assertIn("bind the same XFA data node (Place[0])", stderr)
            self.assertIn("verify: stored XFA values and visible AcroForm values match", stderr)
            visible = xfa_tools.extract_visible(filled, ["Place[0]", "Place[1]"])
        self.assertEqual(visible, {"Place[0]": "Austin", "Place[1]": ""})

    def test_fill_rejects_conflicting_values(self) -> None:
        with TemporaryDirectory() as tmpdir:
            blank, filled, mapping = (Path(tmpdir) / name for name in ("blank.pdf", "filled.pdf", "map.json"))
            write_marriage_place_form(blank)
            mapping.write_text(json.dumps({"Place[0]": "Austin", "Place": "Dallas"}))
            with self.assertRaises(ValueError):
                run_quietly(xfa_tools.fill_pdf, blank, filled, mapping, True)
            self.assertFalse(filled.exists())


class ExtractValuesTests(unittest.TestCase):
    """Bug 6: indexed and bare names read the same stored value."""

    def test_indexed_and_bare_names_resolve(self) -> None:
        with TemporaryDirectory() as tmpdir:
            blank, filled = Path(tmpdir) / "blank.pdf", Path(tmpdir) / "filled.pdf"
            write_marriage_place_form(blank)
            run_quietly(xfa_tools.write_filled_pdf, blank, filled, {"Unit": "STE", "Note": "Hello"})
            stored = xfa_tools.extract_values(
                filled, ["Unit", "Unit[0]", "Unit[1]", "Unit[2]", "Note", "Note[0]"]
            )
            visible = xfa_tools.extract_visible(filled, ["Unit[0]", "Unit[1]", "Unit[2]"])
        self.assertEqual(stored["Unit"], " STE ")
        self.assertEqual(stored["Unit[0]"], " STE ")
        # Other boxes of the global group read as unchecked, as they show on the page.
        self.assertEqual((stored["Unit[1]"], stored["Unit[2]"]), ("", ""))
        self.assertEqual((stored["Note"], stored["Note[0]"]), ("Hello", "Hello"))
        for name in ("Unit[0]", "Unit[1]", "Unit[2]"):
            self.assertEqual(stored[name].strip(), str(visible[name] or "").strip(), name)


class LinkedCheckboxDefectTests(unittest.TestCase):
    """Bug 7: the I-864 links Part 6 'Employed' and Part 8 items 1.a/1.b into one group."""

    I864_STATES = {"P6_Line1_Checkbox": {" Y", "A", "B"}}

    def test_known_group_is_recognised_by_name_and_states(self) -> None:
        self.assertEqual(len(forms_workflow.linked_checkbox_defects(self.I864_STATES)), 1)
        self.assertEqual(forms_workflow.linked_checkbox_defects({"P6_Line1_Checkbox": {" Y", "N"}}), [])

    def test_audit_warns_and_asks_for_an_attorney_action_item(self) -> None:
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "i864.pdf"
            write_blank_pdf(source)
            with patch.object(audit, "button_states", return_value=self.I864_STATES):
                findings = audit.known_defect_findings(
                    kind="i-864",
                    pdf_path=Path("/tmp/I-864.pdf"),
                    widget_pdf=source,
                    values={"P6_Line1_Checkbox": " Y"},
                )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "warning")
        self.assertEqual(findings[0]["open_item_type"], "attorney_action")
        self.assertIn("by hand", findings[0]["action"])
        self.assertEqual(findings[0]["currently_checked"], "Part 6 item 1 'Employed'")

    def test_fill_warns_about_the_linked_group(self) -> None:
        with TemporaryDirectory() as tmpdir:
            blank, filled = Path(tmpdir) / "blank.pdf", Path(tmpdir) / "filled.pdf"
            write_hybrid_pdf(
                blank,
                checkboxes=[
                    ("P6_Line1_Checkbox[0]", " Y"),
                    ("P6_Line1_Checkbox[1]", "A"),
                    ("P6_Line1_Checkbox[2]", "B"),
                ],
                data_nodes=["P6_Line1_Checkbox"],
                global_names=["P6_Line1_Checkbox"],
            )
            result, _ = run_quietly(xfa_tools.write_filled_pdf, blank, filled, {"P6_Line1_Checkbox": "A"})
        self.assertEqual(len(result.defects), 1)
        self.assertIn("attorney_action", result.defects[0])
        self.assertIn("so only Part 8 item 1.a", result.defects[0])


class FieldDumpLocationTests(unittest.TestCase):
    """Bug 8: field dumps live with the matter, not in a session scratchpad."""

    def test_default_dump_path_is_matter_local(self) -> None:
        blank = Path("/matters/Sample/output/working/forms/blank/I-485.pdf")
        self.assertEqual(
            forms_workflow.default_field_dump_path(blank),
            Path("/matters/Sample/output/working/forms/fields/I-485.json"),
        )
        self.assertIsNone(forms_workflow.default_field_dump_path(Path("/tmp/I-485.pdf")))

    def test_dump_fields_saves_next_to_the_blank_forms(self) -> None:
        with TemporaryDirectory() as tmpdir:
            forms = Path(tmpdir) / "matter" / "output" / "working" / "forms"
            blank = forms / "blank" / "X-1.pdf"
            write_marriage_place_form(blank)
            code, stderr = run_quietly(xfa_tools.list_fields, blank, None, True)
            dump_path = forms / "fields" / "X-1.json"
            self.assertEqual(code, 0)
            self.assertIn(str(dump_path), stderr)
            dump = json.loads(dump_path.read_text())
        names = {item["name"]: item for item in dump["fields"]}
        self.assertEqual(set(names), {"Place[0]", "Place[1]", "Note", "Unit[0]", "Unit[1]", "Unit[2]"})
        self.assertTrue(names["Unit[0]"]["global"])
        self.assertEqual(names["Unit[1]"]["states"], [" FLR "])
        self.assertEqual(dump["xfa_nodes"], ["Unit", "Note"])

    def test_plan_reads_the_matter_local_dump(self) -> None:
        with TemporaryDirectory() as tmpdir:
            matter = Path(tmpdir) / "matter" / "output"
            blank = matter / "working" / "forms" / "blank" / "X-1.pdf"
            write_marriage_place_form(blank)
            plan_path = matter / "working" / "vault" / "forms" / "main" / "plan.json"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_text(
                json.dumps(
                    {
                        "kind": "x-1",
                        "subject": "beneficiary",
                        "questions": [
                            question(
                                key="place",
                                label="Place",
                                status=STATUS_FILLED,
                                field_values={"Place[0]": "Austin", "Unit": "STE", "Plaec": "typo", "Note[3]": "x"},
                            )
                        ],
                    }
                )
            )
            summary, entry = forms_workflow.apply_plan(
                json.loads(plan_path.read_text()),
                mapping_out=plan_path.parent / "mapping.json",
                filing_copy=matter / "deliverables" / "Forms" / "X-1.pdf",
                blank_pdf=blank,
            )
            dump_path = matter / "working" / "forms" / "fields" / "X-1.json"
            self.assertTrue(dump_path.exists())
        self.assertEqual(summary["field_dump"], str(dump_path.resolve()))
        self.assertEqual(entry["field_dump"], str(dump_path.resolve()))
        self.assertEqual(summary["field_check"]["unknown_fields"], ["Plaec"])
        self.assertEqual(summary["field_check"]["index_out_of_range"], ["Note[3] (the form has 1)"])
        self.assertNotIn("not_an_on_state", summary["field_check"])

    def test_field_check_accepts_names_with_a_literal_dot(self) -> None:
        dump = {
            "fields": [
                {"name": "Pt8Line42.a_YesNo[0]", "base": "Pt8Line42.a_YesNo", "type": "Btn", "states": ["Y"]},
                {"name": "Pt8Line42.a_YesNo[1]", "base": "Pt8Line42.a_YesNo", "type": "Btn", "states": ["N"]},
            ],
            "xfa_nodes": ["Pt8Line42.a_YesNo"],
        }
        check = forms_workflow.mapping_field_check({"Pt8Line42.a_YesNo": "N", "Pt8Line42\\.a_YesNo": "Y"}, dump)
        self.assertEqual(check, {"unknown_fields": [], "index_out_of_range": [], "not_an_on_state": [], "not_a_choice": []})

    def test_drop_down_values_must_be_among_the_choices(self) -> None:
        dump = {
            "fields": [
                {"name": "Pt1Line18_State", "base": "Pt1Line18_State", "type": "Ch", "options": ["", "IL", "TX"]},
                {"name": "Free", "base": "Free", "type": "Tx"},
            ],
            "xfa_nodes": [],
        }
        problems = forms_workflow.mapping_field_check({"Pt1Line18_State": "Illinois", "Free": "x"}, dump)
        self.assertEqual(len(problems["not_a_choice"]), 1)
        self.assertIn("'Illinois' (choices: IL, TX)", problems["not_a_choice"][0])
        self.assertEqual(forms_workflow.mapping_field_check({"Pt1Line18_State": "IL"}, dump)["not_a_choice"], [])
        self.assertIn("not one of the drop-down's choices", forms_workflow.field_check_lines(problems)[0])

    def test_a_dump_from_another_edition_is_rewritten(self) -> None:
        with TemporaryDirectory() as tmpdir:
            forms = Path(tmpdir) / "matter" / "output" / "working" / "forms"
            blank = forms / "blank" / "X-1.pdf"
            write_marriage_place_form(blank)
            stale = forms / "fields" / "X-1.json"
            stale.parent.mkdir(parents=True)
            stale.write_text(json.dumps({"pdf_sha256": "older edition", "fields": [], "xfa_nodes": []}))
            path, dump = forms_workflow.load_field_dump(blank)
        self.assertEqual(path, stale.resolve())
        self.assertNotEqual(dump["pdf_sha256"], "older edition")
        self.assertIn("Place[0]", {item["name"] for item in dump["fields"]})


class SharedSchemaTests(unittest.TestCase):
    """Every question schema is usable as written: a known form kind, a skeleton that builds,
    notes and choices only for fields it declares, and, where a stored field list exists,
    only fields and on-states the current edition actually has. Each form's own test file
    checks what is particular to it."""

    # Schemas for one posture of a form, which leave the other postures' boxes to other schemas:
    # their own test files check what they cover.
    PARTIAL = {"i131_advance_parole_pending_i485", "i360_vawa_self_petition", "i485_family_based",
               "i485_asylee_refugee", "i485_employment_principal", "i485_employment_derivative_child"}
    # Boxes no question holds: the current address's and current employer's Date To, pre-printed PRESENT.
    PRE_PRINTED = {"i130_family_petition": {"Pt2Line13b_DateTo", "Pt2Line43b_DateTo"},
                   "i130a_spouse_beneficiary": {"Pt1Line5b_DateTo", "Pt2Line4b_DateTo"}}

    @staticmethod
    def base(field: str) -> str:
        return field.split("[")[0]

    def test_every_schema_is_well_formed(self) -> None:
        for name, schema in QUESTION_SCHEMAS.items():
            with self.subTest(schema=name):
                self.assertIn(schema["kind"], audit.AUDITORS)
                self.assertTrue(schema["required_questions"])
                plan = skeleton_plan(name)
                self.assertEqual(len(plan["questions"]), len(schema["required_questions"]))
                self.assertTrue(schema["description"])
                self.assertEqual(load_field_list(schema["field_list"])["pdf"], spec_for(schema["kind"]).pdf_name)
                self.assertEqual(plan["schema_edition"], schema["edition"])
                for key, spec in schema["required_questions"].items():
                    self.assertTrue(spec.get("label"), key)
                    fields = set(spec.get("required_fields", []))
                    if not fields:  # a status-only question, such as "physical address, if different"
                        self.assertIn("not_applicable", spec.get("allowed_statuses", []), f"{key} declares no fields")
                    self.assertLessEqual(set(spec.get("required_nonempty_fields_when_filled", [])), fields, key)
                    self.assertLessEqual(set(spec.get("field_notes", {})), fields, key)
                    self.assertLessEqual(set(spec.get("choices", {})), fields, key)

    def test_schema_fields_and_on_states_exist_on_the_form(self) -> None:
        checked = 0
        for name, schema in QUESTION_SCHEMAS.items():
            if not schema.get("field_list"):
                continue
            checked += 1
            known = load_field_list(schema["field_list"])["fields"]
            with self.subTest(schema=name):
                for key, spec in schema["required_questions"].items():
                    for field in spec.get("required_fields", []):
                        self.assertIn(self.base(field), known, f"{key}: {field} is not on the form")
                    for field, options in spec.get("choices", {}).items():
                        states = known.get(self.base(field), {}).get("states", [])
                        for answer, state in options.items():
                            self.assertIn(state, states, f"{key}: {field} has no on-state {state!r} for {answer!r}")
        if checked == 0:
            self.skipTest("no schema names a stored field list yet")

    def test_every_box_belongs_to_one_question_and_every_checkbox_has_its_choices(self) -> None:
        for name in QUESTION_SCHEMAS:
            if name not in self.PARTIAL:
                with self.subTest(schema=name):
                    check_schema_covers_the_form(self, name, self.PRE_PRINTED.get(name, set()))

    def test_a_complete_plan_has_no_schema_findings(self) -> None:
        for name, schema in QUESTION_SCHEMAS.items():
            with self.subTest(schema=name):
                findings = audit.schema_findings(pdf_path=Path("/x.pdf"), kind=schema["kind"],
                                                 questions=complete_plan(name)["questions"],
                                                 manifest_entry={"question_schema": name})
                self.assertEqual(findings, [])

    def test_skeleton_carries_notes_and_choices(self) -> None:
        for name, schema in QUESTION_SCHEMAS.items():
            for key, spec in schema["required_questions"].items():
                if spec.get("field_notes") or spec.get("choices"):
                    question = next(q for q in skeleton_plan(name)["questions"] if q["key"] == key)
                    self.assertEqual(question.get("field_notes", {}), dict(spec.get("field_notes", {})))
                    self.assertEqual(set(question.get("choices", {})), set(spec.get("choices", {})))
                    return
        self.skipTest("no schema has notes or choices yet")

    def test_schema_only_audit_flags_a_blank_output(self) -> None:
        findings = audit.audit_form("i-765", Path("/x/I-765.pdf"), {}, xfa={}, acro={})
        self.assertTrue(findings)
        self.assertNotIn(
            "Prepared form has no populated stored values",
            titles(audit.audit_form("n-400", Path("/x/N-400.pdf"), {"A": "1"}, xfa={}, acro={})),
        )


# --------------------------------------------------------------------------- audit-fix regressions
#
# Fixtures shaped like the parts of the 01/20/25 N-400 and 09/18/26 I-485 that broke: checkbox
# names with a literal dot, nested the way USCIS nests them; Courier New Bold table boxes; and an
# XFA template with global, unbound and grouped fields. All values are fictional.

CNB_WIDTHS = [600] * 256


def write_uscis_like_form(path: Path) -> None:
    """One page with:

    - N-400 item 7.b and 7.c Yes/No boxes: `P9_Line7\\` > `b\\` > `[0]`/`[1]` and
      `P9_Line7\\` > `c[0]`/`c[1]`, so the widgets' own /T are `[0]`, `[1]`, `c[0]`, `c[1]`;
    - `Date[0]`, a centred (/Q 1) 60 x 24 pt date box, and `City[0]`, a 66 x 30 pt multi-line
      table box, both in a Courier New Bold-like font (widths 600, bbox -710..1221);
    - `ANumber[0]`, a plain text box;
    - a template where the Yes/No pairs and ANumber are global (as on the N-400), OtherName is
      unbound and Dob sits in data group Page3.
    """
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    def add(obj):
        return writer._add_object(obj)

    def stream(data: bytes, extra: dict | None = None):
        obj = DecodedStreamObject()
        obj.set_data(data)
        for key, value in (extra or {}).items():
            obj[NameObject(key)] = value
        return add(obj)

    def name(text: str) -> TextStringObject:
        return TextStringObject(text)

    root = DictionaryObject({NameObject("/T"): name("form1[0]"), NameObject("/Kids"): ArrayObject()})
    root_ref = add(root)
    annots = ArrayObject()

    def container(title: str, parent, parent_ref):
        node = DictionaryObject(
            {NameObject("/T"): name(title), NameObject("/Parent"): parent_ref, NameObject("/Kids"): ArrayObject()}
        )
        ref = add(node)
        parent["/Kids"].append(ref)
        return node, ref

    def widget(title: str, parent, parent_ref, rect, extra: dict) -> DictionaryObject:
        entries = {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/T"): name(title),
            NameObject("/Rect"): ArrayObject(FloatObject(v) for v in rect),
            NameObject("/F"): NumberObject(4),
            NameObject("/P"): page.indirect_reference,
            NameObject("/Parent"): parent_ref,
            NameObject("/MK"): DictionaryObject(),
        }
        entries.update(extra)
        annot = DictionaryObject(entries)
        ref = add(annot)
        parent["/Kids"].append(ref)
        annots.append(ref)
        return annot

    def checkbox(title: str, parent, parent_ref, state: str, y: float) -> None:
        states = DictionaryObject(
            {NameObject(f"/{state}"): stream(b"0 g 0 0 8 8 re f"), NameObject("/Off"): stream(b"")}
        )
        widget(
            title,
            parent,
            parent_ref,
            (50, y, 60, y + 10),
            {
                NameObject("/FT"): NameObject("/Btn"),
                NameObject("/AP"): DictionaryObject({NameObject("/N"): states}),
                NameObject("/AS"): NameObject("/Off"),
            },
        )

    def text(title: str, parent, parent_ref, rect, flags: int, quadding: int) -> DictionaryObject:
        return widget(
            title,
            parent,
            parent_ref,
            rect,
            {
                NameObject("/FT"): NameObject("/Tx"),
                NameObject("/DA"): TextStringObject("/CourierNewPS-BoldMT 10.00 Tf 0 g"),
                NameObject("/Ff"): NumberObject(flags),
                NameObject("/Q"): NumberObject(quadding),
            },
        )

    subform, subform_ref = container("#subform[0]", root, root_ref)
    line7, line7_ref = container("P9_Line7\\", subform, subform_ref)
    item_b, item_b_ref = container("b\\", line7, line7_ref)
    checkbox("[0]", item_b, item_b_ref, "N", 700)
    checkbox("[1]", item_b, item_b_ref, "Y", 680)
    checkbox("c[0]", line7, line7_ref, "N", 660)
    checkbox("c[1]", line7, line7_ref, "Y", 640)
    text("Date[0]", subform, subform_ref, (100, 500, 160, 524), 0, 1)
    text("City[0]", subform, subform_ref, (100, 400, 166, 430), 4096, 0)
    text("OtherName[0]", subform, subform_ref, (100, 300, 300, 318), 0, 0)
    page3, page3_ref = container("Page3[0]", root, root_ref)
    text("Dob[0]", page3, page3_ref, (100, 250, 200, 268), 0, 0)
    text("ANumber[0]", subform, subform_ref, (456.5, 720, 576, 738), 0, 0)
    page[NameObject("/Annots")] = annots

    descriptor = add(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/FontDescriptor"),
                NameObject("/FontName"): NameObject("/CourierNewPS-BoldMT"),
                NameObject("/Flags"): NumberObject(34),
                NameObject("/FontBBox"): ArrayObject(NumberObject(v) for v in (-192, -710, 702, 1221)),
                NameObject("/Ascent"): NumberObject(1221),
                NameObject("/Descent"): NumberObject(-710),
                NameObject("/CapHeight"): NumberObject(592),
                NameObject("/ItalicAngle"): NumberObject(0),
                NameObject("/StemV"): NumberObject(100),
            }
        )
    )
    font = add(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/TrueType"),
                NameObject("/BaseFont"): NameObject("/CourierNewPS-BoldMT"),
                NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
                NameObject("/FirstChar"): NumberObject(0),
                NameObject("/LastChar"): NumberObject(255),
                NameObject("/Widths"): ArrayObject(NumberObject(v) for v in CNB_WIDTHS),
                NameObject("/FontDescriptor"): descriptor,
            }
        )
    )
    datasets = (
        f'<xfa:datasets xmlns:xfa="{XFA_DATA_NS}"><xfa:data><form1>'
        "<P9_Line7.b./><P9_Line7.c/><Date/><City/><ANumber/><Page3><Dob/></Page3>"
        "</form1></xfa:data></xfa:datasets>"
    )
    template = (
        '<template xmlns="http://www.xfa.org/schema/xfa-template/3.3/"><subform name="form1">'
        '<subform><field name="P9_Line7.b."><bind match="global"/></field>'
        '<field name="P9_Line7.c"><bind match="global"/></field><field name="Date"/>'
        '<field name="City"/><field name="ANumber"><bind match="global"/></field>'
        '<field name="OtherName"><bind match="none"/></field></subform>'
        '<subform name="Page3"><field name="Dob"/></subform>'
        "</subform></template>"
    )
    writer._root_object[NameObject("/AcroForm")] = add(
        DictionaryObject(
            {
                NameObject("/Fields"): ArrayObject([root_ref]),
                NameObject("/DA"): TextStringObject("/Helv 0 Tf 0 g"),
                NameObject("/DR"): DictionaryObject(
                    {NameObject("/Font"): DictionaryObject({NameObject("/CourierNewPS-BoldMT"): font})}
                ),
                NameObject("/XFA"): ArrayObject(
                    [
                        TextStringObject("template"),
                        stream(template.encode()),
                        TextStringObject("datasets"),
                        stream(datasets.encode()),
                    ]
                ),
            }
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        writer.write(handle)


class DottedFieldNameTests(unittest.TestCase):
    """Audit fix 1: names with a literal dot (N-400 P9_Line7.b., Line12.c_Checkbox; I-485
    Pt8Line42.a_YesNo) are one field, keyed by their escape-aware full name, never split."""

    def test_leaf_names_are_never_split_on_a_dot(self) -> None:
        self.assertEqual(forms_workflow.field_base("P9_Line7.b."), "P9_Line7.b.")
        self.assertEqual(forms_workflow.field_base_and_index("P9_Line7.c[1]"), ("P9_Line7.c", 1))
        self.assertEqual(forms_workflow.field_base_and_index("Pt8Line42\\.a_YesNo"), ("Pt8Line42.a_YesNo", 0))
        self.assertEqual(
            forms_workflow.qualified_base_and_index("form1[0].#subform[6].P9_Line7\\.b\\.[1]"), ("P9_Line7.b.", 1)
        )
        bases = forms_workflow.allowed_nonempty_bases(
            [question(key="q", label="7", status=STATUS_FILLED, field_values={"P9_Line7.b.": "N", "Line12.c_Checkbox": "Y"})]
        )
        self.assertEqual(bases, ["Line12.c_Checkbox", "P9_Line7.b."])

    def test_nested_widgets_are_named_from_their_parent_chain(self) -> None:
        with TemporaryDirectory() as tmpdir:
            blank = Path(tmpdir) / "blank.pdf"
            write_uscis_like_form(blank)
            reader = PdfReader(str(blank))
            names = [forms_workflow.widget_full_name(ref.get_object()) for ref in reader.pages[0]["/Annots"]][:3]
            fields = xfa_tools.acro_fields_by_base(reader)
        self.assertEqual(names[0], "form1[0].#subform[0].P9_Line7\\.b\\.[0]")
        self.assertEqual(forms_workflow.leaf_field_name(names[2]), "P9_Line7.c[0]")
        self.assertEqual([spec.on_states for spec in fields["P9_Line7.b."]], [("N",), ("Y",)])
        self.assertEqual([spec.pages for spec in fields["P9_Line7.b."]], [[1], [1]])  # was [] before the fix
        self.assertNotIn("[0]", fields)
        self.assertNotIn("c", fields)

    def test_answered_item_7b_is_not_an_unexpected_field(self) -> None:
        with TemporaryDirectory() as tmpdir:
            blank, filled, mapping = (Path(tmpdir) / name for name in ("blank.pdf", "filled.pdf", "map.json"))
            write_uscis_like_form(blank)
            mapping.write_text(json.dumps({"P9_Line7.b.": "N", "P9_Line7\\.c": "Y"}))
            code, stderr = run_quietly(xfa_tools.fill_pdf, blank, filled, mapping, True)
            self.assertEqual(code, 0, stderr)
            acro = audit.acro_values(filled)
            xfa = audit.xfa_values(filled)
            values = {**acro, **{key: value for key, value in xfa.items() if value}}
            planned = [question(key="part9", label="Part 9 item 7", status=STATUS_FILLED,
                                field_values={"P9_Line7.b.": "N", "P9_Line7.c": "Y"})]
            entry = forms_workflow.form_manifest_entry(
                kind="n-400", subject="applicant", output_pdf=filled, source_pdf=None,
                questions=planned, fact_table_path=Path(""), sources=[],
            )
            findings = audit.intent_findings(pdf_path=filled, kind="n-400", actual_values=values, manifest_entry=entry)
            # A manifest written by the old plan stored the bases as "" and "c".
            stale = {**entry, "allowed_nonempty_bases": ["", "c"]}
            stale_findings = audit.intent_findings(
                pdf_path=filled, kind="n-400", actual_values=values, manifest_entry=stale
            )
        self.assertEqual(acro.get("P9_Line7.b.[0]"), "N")
        self.assertEqual(acro.get("P9_Line7.c[1]"), "Y")
        self.assertNotIn("[0]", acro)
        self.assertEqual(findings, [])
        self.assertEqual(stale_findings, [])


def i485_audit_values(**overrides: str) -> dict[str, str]:
    """An I-485 that clears every audit rule: an adult asylee who entered without inspection,
    never married, has no children, no mobile phone or email, no work abroad to add, and
    two races. Each test changes one thing."""
    values = {
        "Pt1Line1_FamilyName": "Sample", "Pt1Line1_GivenName": "Alex", "Pt1Line3_DOB": "01/02/1990",
        "Pt1Line3_YN": "N", "Pt1Line4_YN": "N", "Pt1Line5_YN": "N", "Pt1Line6_CB_Sex": "M",
        "Pt1Line7_CityTownOfBirth": "Sampleville", "Pt1Line7_CountryOfBirth": "Examplestan",
        "Pt1Line8_CountryofCitizenshipNationality": "Examplestan",
        "Pt2Line2_CB": "1fA", "Pt2Line11_CB": "11C", "Pt2Line5_CB": "N", "Pt3Line1_CB": "4", "Pt2Line1_YN": "N",
        "Pt2Line3d_AsyleeRefugeeCB": "3d0", "Pt2Line3d_Asylum": "04/04/2023",
        "Pt1Line10_CityTown": "Sampleton", "Pt1Line10_State": "TX", "Pt1Line10_DateofArrival": "01/01/2020",
        "Pt1Line15_Date": "N/A", "Pt1Line13_YN": "Y", "Pt1Line16_YN": "N", "Pt1Line17_YN": "N",
        "Pt1Line18_StreetNumberName": "1 Main St", "Pt1Line18_CityOrTown": "Sampleton", "Pt1Line18_State": "TX",
        "Pt1Line18_ZipCode": "75001", "Pt1Line18_Date": "01/01/2020", "Pt1Line18_YN": "Y",
        "Pt1Line18_last5yrs_YN": "Y", "Pt1Line19_YN": "N", "Pt1Line19_SSA_YN": "N", "Pt1Line19_Consent_YN": "N",
        "Pt3Line3_DaytimePhoneNumber1": "5550000100", "Pt4Line1_YN": "N", "Pt4Line5_YN": "N", "Pt4Line6_YN": "N",
        "CheckBox1": "1", "AttorneyStateBarNumber": "000000", "Pt12Line1_PreparerFamilyName": "Counsel",
        "Pt12Line1a_PreparerGivenName": "Pat", "Pt12Line2_BusinessName": "Sample Law",
        "Pt12Line3_PreparerDaytimePhoneNumber1": "5550000101", "Pt12Line5_PreparerEmail": "pat@example.test",
        "Pt5Line1_FamilyName": "Sample", "Pt5Line1_GivenName": "Parent", "Pt5Line3_DateofBirth": "01/02/1960",
        "Pt5Line5_CityTownOfBirth": "Examplestan", "Pt5Line6_FamilyName": "Sample", "Pt5Line6_GivenName": "Other",
        "Pt5Line8_DateofBirth[0]": "01/02/1962", "Pt5Line10_CityTownOfBirth": "Examplestan",
        "Pt4Line7_EmployerName[0]": "Employer", "Pt4Line7_EmployerName[2]": "Demo Co",
        "Pt4Line7_EmployerName[1]": "Clerk", "Pt4Line7_DateFrom": "01/01/2021",
        "Pt5Line2_YNNA": "A", "Pt6Line1_MaritalStatus": "1", "Pt6Line3_TimesMarried": "None",
        "Pt6Line1_TotalChildren": "None",
        "Pt7Line1_Ethnicity": "N", "Pt7Line2_Race[1]": "WH", "Pt7Line2_Race[2]": "BL",
        "Pt7Line3_HeightFeet": "5", "Pt7Line3_HeightInches": "9", "Pt7Line4_Weight2": "6", "Pt7Line4_Weight3": "0",
        "Pt7Line5_Eyecolor": "BN", "Pt7Line6_Haircolor": "BR", "Pt9Line56_CB": "3", "Pt8Line1_YesNo": "N",
        "Pt8Line13_YesNo": "N",
    }
    values.update(overrides)
    return {key: value for key, value in values.items() if value}


class I485ConditionalRuleTests(unittest.TestCase):
    """Audit fix 2: the I-485 rules no longer reject answers the form allows."""

    def errors(self, values: dict[str, str], manifest_entry: dict | None = None) -> list[dict[str, object]]:
        findings = audit.audit_form("i-485", Path("/tmp/i485.pdf"), values, manifest_entry=manifest_entry)
        return [item for item in findings if item["severity"] == "error"]

    def test_baseline_asylee_without_if_any_answers_has_no_errors(self) -> None:
        self.assertEqual(self.errors(i485_audit_values()), [])

    def test_none_is_a_zero_marriage_count(self) -> None:
        for none in ("None", "NONE", "none", "0"):
            with self.subTest(count=none):
                self.assertEqual(self.errors(i485_audit_values(Pt6Line3_TimesMarried=none)), [])
        prior = i485_audit_values(Pt6Line3_TimesMarried="None", Pt6Line12_FamilyName="Former")
        self.assertIn(
            "Prior-spouse section is populated even though the marriage count does not support it",
            titles(self.errors(prior)),
        )
        self.assertIn("Prior-spouse section is incomplete", titles(self.errors(i485_audit_values(Pt6Line3_TimesMarried="2"))))
        married = i485_audit_values(Pt6Line1_MaritalStatus="2", Pt6Line4_FamilyName="Spouse")
        self.assertIn("Marriage count is None even though a current spouse is listed", titles(self.errors(married)))
        self.assertEqual(
            titles(self.errors(i485_audit_values(Pt6Line3_TimesMarried="Two"))), ["Marriage count is not a number or None"]
        )

    def test_any_one_or_more_race_boxes(self) -> None:
        self.assertEqual(self.errors(i485_audit_values(**{"Pt7Line2_Race[2]": ""})), [])
        three = i485_audit_values(**{"Pt7Line2_Race[0]": "", "Pt7Line2_Race[3]": "AI", "Pt7Line2_Race[4]": "HW"})
        self.assertEqual(self.errors(three), [])
        none = i485_audit_values(**{"Pt7Line2_Race[1]": "", "Pt7Line2_Race[2]": ""})
        self.assertEqual(titles(self.errors(none)), ["Biographic section is incomplete: no race box is checked"])

    def test_passport_and_i94_follow_item_11(self) -> None:
        def flagged(values: dict[str, str]) -> set[str]:
            return {
                field for item in self.errors(values) if item["title"] == "Missing recent-arrival fields"
                for field in item["fields"]
            }

        passport = {"Pt1Line10_PassportNum", "Pt1Line10_ExpDate", "Pt1Line10_Passport"}
        i94 = {"P1Line12_I94", "Pt1Line12_Status", "Pt1Line12_Date"}
        self.assertEqual(flagged(i485_audit_values()), set())  # 11C: entered without inspection
        self.assertEqual(flagged(i485_audit_values(Pt2Line11_CB="11A")), passport | i94)
        self.assertEqual(flagged(i485_audit_values(Pt2Line11_CB="11B")), passport | i94)
        # An asylee who got an I-94 with the grant gives it; a partly filled I-94 row is incomplete.
        self.assertEqual(flagged(i485_audit_values(P1Line12_I94="00000000002")), {"Pt1Line12_Status", "Pt1Line12_Date"})

    def test_if_any_contact_and_principal_a_number(self) -> None:
        self.assertEqual(self.errors(i485_audit_values(Pt3Line4_MobileNumber1="", Pt3Line5_Email="")), [])
        self.assertIn(
            "Applicant contact section is incomplete",
            titles(self.errors(i485_audit_values(Pt3Line3_DaytimePhoneNumber1=""))),
        )
        derivative = i485_audit_values(
            Pt2Line2_CB="1fB", Pt2Line2_FamilyName="Principal", Pt2Line2_GivenName="Pat", Pt1Line2_DOB="01/02/1980"
        )
        self.assertEqual(self.errors(derivative), [])
        self.assertIn(
            "Derivative principal-information block is incomplete",
            titles(self.errors(i485_audit_values(Pt2Line2_CB="1fB"))),
        )

    def test_part4_item8_only_when_started(self) -> None:
        self.assertEqual(self.errors(i485_audit_values()), [])
        started = i485_audit_values(Pt4Line8_EmployerName="Demo Trading Co")
        self.assertIn("Most recent outside-U.S. employer section is incomplete", titles(self.errors(started)))
        minor = i485_audit_values(Pt1Line3_DOB="01/02/2015", Pt4Line8_Occupation="Student")
        self.assertIn("Most recent outside-U.S. school or activity is incomplete", titles(self.errors(minor)))

    def test_concurrent_i140_needs_no_receipt(self) -> None:
        employment = i485_audit_values(
            Pt2Line3d_AsyleeRefugeeCB="", Pt2Line3d_Asylum="", Pt2Line3b_CB140="3b4", Pt2Line3b_CB140Assoc="N",
            Pt2Line4_CB="N", Pt2Line11_CB="11A", Pt1Line10_PassportNum="X0000001", Pt1Line10_ExpDate="03/04/2031",
            Pt1Line10_Passport="Examplestan", P1Line12_I94="00000000001", Pt1Line12_Status="H-1B",
            Pt1Line12_Date="09/30/2027", Pt9Line56_CB="",
        )
        employment.pop("Pt9Line56_CB", None)
        employment["Pt9Line56_CB"] = "23"
        employment.update({"Pt9Line57_HouseholdSize": "1", "Pt9Line53_CB": "1", "Pt9Line59_CB": "1",
                           "Pt9Line60_CB": "1", "Pt9Line61_CB": "7"})
        concurrent = {"questions": [{"key": "underlying_petition", "status": "not_applicable"}]}
        self.assertEqual(self.errors(employment, concurrent), [])
        filed_earlier = {"questions": [{"key": "underlying_petition", "status": "filled"}]}
        missing = [item for item in self.errors(employment, filed_earlier)
                   if item["title"] == "Employment-based category details are incomplete"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(set(missing[0]["fields"]), {"Pt2Line2_Receipt", "Pt2Line2_Date"})
        self.assertEqual(len(self.errors(employment)), 1)  # no plan: the receipt is still asked for

    # A spouse, a marriage and a prior marriage as the form takes them; each test picks one history.
    SPOUSE = {
        "Pt6Line4_FamilyName": "Spouse", "Pt6Line4_GivenName": "Sam", "Pt5Line8_DateofBirth[1]": "03/04/1991",
        "Pt6Line7_Country": "Examplestan", "Part6Line8_StreetName": "1 Main St", "P6Line8_City": "Sampleton",
        "P6Line8_State": "TX", "P6Line8_ZipCode": "75001", "P6Line8_Country": "United States",
        "Pt6Line10_CityTownOfBirth[0]": "Sampleton", "Pt6Line10_State[0]": "TX",
        "Pt6Line10_Country[0]": "United States", "Pt5Line8_DateofBirth[2]": "05/06/2021", "Pt6Line11_YN": "N",
        "Pt5Line2_YNNA": "N",
    }
    PRIOR = {
        "Pt6Line12_FamilyName": "Former", "Pt6Line12_GivenName": "Kim", "Pt5Line8_DateofBirth[3]": "07/08/1988",
        "Pt6Line14_Country": "Examplestan", "Pt6Line15_Country": "Examplestan",
        "Pt6Line16_DateofBirth[0]": "01/01/2012", "Pt6Line16_DateofBirth[1]": "02/02/2016",
        "Pt6Line10_CityTownOfBirth[1]": "Capital City", "Pt6Line10_Country[1]": "Examplestan",
        "Pt6Line18_CityTownOfBirth": "Sampleton", "Pt6Line18_State": "TX", "Pt6Line18_Country": "United States",
        "Pt6Line19_MaritalStatus": "2",
    }

    def test_the_prior_marriage_places_are_required_and_a_us_place_needs_its_state(self) -> None:
        # Item 16 (where the prior marriage took place) and item 17 (where it legally ended).
        for box in ("Pt6Line10_CityTownOfBirth[1]", "Pt6Line10_Country[1]", "Pt6Line18_CityTownOfBirth",
                    "Pt6Line18_Country", "Pt6Line18_State"):
            values = i485_audit_values(Pt6Line1_MaritalStatus="3", Pt6Line3_TimesMarried="1", **{**self.PRIOR, box: ""})
            with self.subTest(box=box):
                missing = self.prior_spouse_errors(values)
                self.assertEqual(titles(missing), ["Prior-spouse section is incomplete"])
                self.assertIn(box, missing[0]["fields"])
        # A marriage that took place abroad needs no state.
        abroad = {**self.PRIOR, "Pt6Line10_State[1]": ""}
        self.assertEqual(self.errors(i485_audit_values(Pt6Line1_MaritalStatus="3", Pt6Line3_TimesMarried="1", **abroad)), [])

    def prior_spouse_errors(self, values: dict[str, str]) -> list[dict[str, object]]:
        return [item for item in self.errors(values) if "Prior-spouse" in str(item["title"])]

    def test_divorced_once_must_list_the_prior_spouse(self) -> None:
        divorced = i485_audit_values(Pt6Line1_MaritalStatus="3", Pt6Line3_TimesMarried="1")
        missing = self.prior_spouse_errors(divorced)
        self.assertEqual(titles(missing), ["Prior-spouse section is incomplete"])
        self.assertIn("Pt6Line16_DateofBirth[1]", missing[0]["fields"])  # when it ended
        self.assertIn("Pt6Line19_MaritalStatus", missing[0]["fields"])  # how it ended
        self.assertEqual(self.errors(i485_audit_values(Pt6Line1_MaritalStatus="3", Pt6Line3_TimesMarried="1", **self.PRIOR)), [])

    def test_widowed_once_must_list_the_late_spouse(self) -> None:
        widowed = i485_audit_values(Pt6Line1_MaritalStatus="4", Pt6Line3_TimesMarried="1")
        self.assertEqual(titles(self.prior_spouse_errors(widowed)), ["Prior-spouse section is incomplete"])
        listed = i485_audit_values(Pt6Line1_MaritalStatus="4", Pt6Line3_TimesMarried="1", **{**self.PRIOR, "Pt6Line19_MaritalStatus": "3"})
        self.assertEqual(self.errors(listed), [])

    def test_married_once_has_no_prior_spouse_and_married_twice_has_one(self) -> None:
        once = i485_audit_values(Pt6Line1_MaritalStatus="2", Pt6Line3_TimesMarried="1", **self.SPOUSE)
        self.assertEqual(self.errors(once), [])
        stray = i485_audit_values(Pt6Line1_MaritalStatus="2", Pt6Line3_TimesMarried="1", **self.SPOUSE, **self.PRIOR)
        self.assertEqual(
            titles(self.prior_spouse_errors(stray)),
            ["Prior-spouse section is populated even though the marriage count does not support it"],
        )
        twice = i485_audit_values(Pt6Line1_MaritalStatus="2", Pt6Line3_TimesMarried="2", **self.SPOUSE)
        self.assertEqual(titles(self.prior_spouse_errors(twice)), ["Prior-spouse section is incomplete"])
        self.assertEqual(
            self.errors(i485_audit_values(Pt6Line1_MaritalStatus="2", Pt6Line3_TimesMarried="2", **self.SPOUSE, **self.PRIOR)), []
        )

    def test_legally_separated_still_has_a_current_spouse(self) -> None:
        separated = i485_audit_values(Pt6Line1_MaritalStatus="7", Pt6Line3_TimesMarried="1")
        self.assertIn("Current spouse section is incomplete", titles(self.errors(separated)))
        self.assertEqual(self.errors(i485_audit_values(Pt6Line1_MaritalStatus="7", Pt6Line3_TimesMarried="1", **self.SPOUSE)), [])

    def test_a_count_that_contradicts_the_status(self) -> None:
        self.assertIn(
            "Marital status says never married, but the marriage count is not None",
            titles(self.errors(i485_audit_values(Pt6Line3_TimesMarried="1"))),
        )
        self.assertIn(
            "Marital status says the applicant was married, but the marriage count is None",
            titles(self.errors(i485_audit_values(Pt6Line1_MaritalStatus="3", Pt6Line3_TimesMarried="None"))),
        )

    def test_how_it_ended_other_needs_the_explanation(self) -> None:
        other = i485_audit_values(Pt6Line1_MaritalStatus="3", Pt6Line3_TimesMarried="1", **{**self.PRIOR, "Pt6Line19_MaritalStatus": "4"})
        self.assertEqual(self.prior_spouse_errors(other)[0]["fields"], ["Pt6Line19_HowMarriageEndedOther"])

    def test_asylee_spouse_abroad_needs_no_state_or_zip(self) -> None:
        abroad = {
            **self.SPOUSE,
            "P6Line8_State": "", "P6Line8_ZipCode": "", "P6Line8_Province": "", "P6Line8_Country": "Examplestan",
            "Pt6Line10_State[0]": "", "Pt6Line10_Country[0]": "Examplestan",
        }
        values = i485_audit_values(Pt6Line1_MaritalStatus="2", Pt6Line3_TimesMarried="1", **abroad)
        self.assertEqual(self.errors(values), [])
        # A spouse in the United States still needs both.
        here = i485_audit_values(Pt6Line1_MaritalStatus="2", Pt6Line3_TimesMarried="1", **{**self.SPOUSE, "P6Line8_ZipCode": ""})
        self.assertEqual(
            [item["fields"] for item in self.errors(here) if item["title"] == "Current spouse section is incomplete"],
            [["P6Line8_ZipCode"]],
        )
        no_state = i485_audit_values(Pt6Line1_MaritalStatus="2", Pt6Line3_TimesMarried="1", **{**self.SPOUSE, "Pt6Line10_State[0]": ""})
        self.assertEqual(
            [item["fields"] for item in self.errors(no_state) if item["title"] == "Current marriage date or place is missing"],
            [["Pt6Line10_State[0]"]],
        )

    def test_foreign_prior_address_needs_no_state_or_zip(self) -> None:
        prior_abroad = {
            "Pt1Line18_last5yrs_YN": "N", "Pt1Line18_PriorStreetName": "5 Harbour Road",
            "Pt1Line18_PriorCity": "Port Example", "Pt1Line18_PriorCountry": "Examplestan",
            "Pt1Line18_PriorDateFrom": "01/01/2015", "Pt1Line18PriorDateTo": "12/31/2019",
        }
        self.assertEqual(self.errors(i485_audit_values(**prior_abroad)), [])
        prior_here = {**prior_abroad, "Pt1Line18_PriorCountry": "United States", "Pt1Line18_PriorState": "TX"}
        flagged = [item for item in self.errors(i485_audit_values(**prior_here)) if "Five-year" in item["title"]]
        self.assertEqual(flagged[0]["fields"], ["Pt1Line18_PriorZipCode"])

    def test_outside_us_row_follows_its_own_question(self) -> None:
        # Not living at the current address for five years says nothing about the outside-U.S. row.
        prior_here = {
            "Pt1Line18_last5yrs_YN": "N", "Pt1Line18_PriorStreetName": "9 Elm St", "Pt1Line18_PriorCity": "Sampleton",
            "Pt1Line18_PriorState": "TX", "Pt1Line18_PriorZipCode": "75002", "Pt1Line18_PriorCountry": "USA",
            "Pt1Line18_PriorDateFrom": "01/01/2015", "Pt1Line18PriorDateTo": "12/31/2019",
        }
        self.assertEqual(self.errors(i485_audit_values(**prior_here)), [])
        not_applicable = {"questions": [{"key": "last_address_outside_us", "status": "not_applicable"}]}
        self.assertEqual(self.errors(i485_audit_values(**prior_here), not_applicable), [])
        asked = {"questions": [{"key": "last_address_outside_us", "status": "filled"}]}
        flagged = [item for item in self.errors(i485_audit_values(), asked)
                   if item["title"] == "Most recent address outside the United States is incomplete"]
        self.assertEqual(len(flagged), 1)
        # Province and postal code are "if any" abroad.
        row = {
            "Pt1Line18_RecentStreetName": "5 Harbour Road", "Pt1Line18_RecentCity": "Port Example",
            "Pt1Line18_RecentCountry": "Examplestan", "Pt1Line18_RecentDateFrom": "01/01/2010",
            "Pt1Line18_RecentDateTo": "12/31/2014",
        }
        self.assertEqual(self.errors(i485_audit_values(**row), asked), [])
        self.assertIn(
            "The address outside the United States (Part 1 item 18) gives the United States as its country",
            titles(self.errors(i485_audit_values(**{**row, "Pt1Line18_RecentCountry": "United States"}), asked)),
        )

    def test_public_charge_factors_follow_the_exemption(self) -> None:
        # The baseline asylee is exempt ("3"): items 57-62 are skipped, and no error says otherwise.
        self.assertEqual(self.errors(i485_audit_values()), [])
        not_exempt = self.errors(i485_audit_values(Pt9Line56_CB="23"))
        self.assertEqual(titles(not_exempt), ["Public-charge items 57-62 are incomplete for an applicant who is not exempt"])
        self.assertFalse(any("Exempt public-charge" in title for title in titles(not_exempt)))
        answered = self.errors(i485_audit_values(Pt9Line57_HouseholdSize="2"))
        self.assertEqual(titles(answered), ["Public-charge items 57-62 are answered, but item 56 selects an exempt category"])

    def test_schema_notes_no_longer_ask_for_na_to_clear_the_audit(self) -> None:
        for name in ("i485_family_based", "i485_asylee_refugee", "i485_employment_principal",
                     "i485_employment_derivative_child"):
            notes = json.dumps(get_question_schema(name)["required_questions"])
            with self.subTest(schema=name):
                self.assertNotIn("the audit still", notes)
                self.assertNotIn("typing N/A in them", notes)


def cnb_widget(value: str, *, width: float, height: float, multiline: bool = False, alignment: int = 0):
    """A text box in the USCIS forms' Courier New Bold 10 pt (font bbox -710..1221)."""
    return audit.TextWidget(
        name="Field", key=("Field", 0), page=1, value=value, width=width, height=height,
        font=audit.font_metrics("CourierNewPS-BoldMT", "CourierNewPS-BoldMT", (-710.0, 1221.0)),
        font_size=10.0, multiline=multiline, alignment=alignment,
    )


class BoxRuleTests(unittest.TestCase):
    """Item 10: an answer longer than its box, or in the wrong format, is an audit error on every form."""

    def test_validators(self) -> None:
        good = {
            formats.DATE: ["01/31/2020", "02/29/2024", "N/A", "D/S", "Indefinite", "present"],
            formats.A_NUMBER: ["1234567", "012345678", "N/A"],
            formats.SSN: ["123456789"],
            formats.RECEIPT: ["IOE0912345678", "msc1234567890"],
            formats.I94: ["12345678901", "123456789A1"],
            formats.ZIP: ["62701"],
            formats.ONLINE_ACCOUNT: ["123456789012"],
            formats.STATE: ["IL", "dc", "PR"],
        }
        bad = {
            formats.DATE: ["2020-01-31", "1/31/2020", "02/30/2023", "13/01/2020", "Jan 31 2020"],
            formats.A_NUMBER: ["A123456789", "123-456-789", "123456", "1234567890"],
            formats.SSN: ["123-45-6789", "12345678"],
            formats.RECEIPT: ["IOE-0912345678", "IOE091234567", "1230912345678"],
            formats.I94: ["1234567890", "123456789012"],
            formats.ZIP: ["1234", "ABCDE"],
            formats.ONLINE_ACCOUNT: ["12345678901"],
            formats.STATE: ["Illinois", "XX"],
        }
        for kind, values in good.items():
            for value in values:
                with self.subTest(kind=kind, value=value):
                    self.assertIsNone(formats.check(kind, value))
        for kind, values in bad.items():
            for value in values:
                with self.subTest(kind=kind, value=value):
                    self.assertIsNotNone(formats.check(kind, value))
        self.assertIsNone(formats.check(formats.ZIP, "62701-1234", max_len=10))
        self.assertIsNotNone(formats.check(formats.ZIP, "62701-1234", max_len=5))
        self.assertIsNone(formats.check(formats.DATE, ""))  # a blank always fits

    def test_a_zip_or_postal_code_column_is_checked_against_its_row(self) -> None:
        # The N-400's residence and employment tables: a ZIP Code on a U.S. row, a postal code abroad.
        for value in ("62701", "SW1A 1AA", "110001", "B-1000", "N/A"):
            with self.subTest(value=value):
                self.assertIsNone(formats.check(formats.ZIP_OR_POSTAL, value))
                self.assertIsNone(formats.check(formats.ZIP_OR_POSTAL, value, us_row=False))
        for value in ("SW1A/1AA", "-", "#12", "62701."):
            with self.subTest(value=value):
                self.assertIsNotNone(formats.check(formats.ZIP_OR_POSTAL, value))
        self.assertIsNone(formats.check(formats.ZIP_OR_POSTAL, "62701", us_row=True))
        self.assertIsNotNone(formats.check(formats.ZIP_OR_POSTAL, "SW1A 1AA", us_row=True))
        self.assertEqual(formats.country_box("P4_Line3_ZipCode2"), "P4_Line3_Country2")
        self.assertEqual(formats.country_box("P7_ZipCode1"), "P7_Country1")

    def test_names_pick_the_number_formats(self) -> None:
        expected = {
            "Pt1Line4_AlienNumber": formats.A_NUMBER, "Pt3Line9_ANumber": formats.A_NUMBER,
            "Pt1Line19_SSN": formats.SSN, "P4_Line10_SocialSecurityNumber": formats.SSN,
            "Pt2Line2_Receipt": formats.RECEIPT, "Line28_ReceiptNumber": formats.RECEIPT,
            "P1Line12_I94": formats.I94, "Part2_Line13_I94RecordNo": formats.I94,
            "Pt4Line21b_ArrivalDeparture": formats.I94, "Line12e_ZipCode": formats.ZIP,
            "Pt1Line1_USCISOnlineAcctNumber": formats.ONLINE_ACCOUNT,
        }
        for name, kind in expected.items():
            self.assertEqual(formats.name_format(name), kind, name)
        for name in ("Part2_Line14_I94ExpDate", "Pt9Line1a_NumberofMembers", "P7_Line1_BalanceofAccounts",
                     "Pt1Line19_SSA_YN", "Pt12Line2_BusinessName"):
            self.assertIsNone(formats.name_format(name), name)

    def test_template_marks_dates_and_zip_codes(self) -> None:
        template = (
            b'<template xmlns="http://www.xfa.org/schema/xfa-template/3.3/"><subform name="form1">'
            b'<field name="DOB"><ui><dateTimeEdit/></ui><format><picture>date{MM/DD/YYYY}</picture></format></field>'
            b'<field name="Zip"><ui><textEdit/></ui><format><picture>text{99999}</picture></format></field>'
            b'<field name="CardExpiry"><ui><dateTimeEdit/></ui><format><picture>date{MM/YYYY}</picture></format></field>'
            b'<field name="Other"><ui><textEdit/></ui></field>'
            b'</subform></template>'
        )
        self.assertEqual(formats.template_kinds(template), {"DOB": formats.DATE, "Zip": formats.ZIP, "CardExpiry": "", "Other": ""})

    def test_a_five_digit_box_is_a_zip_code_only_when_the_form_says_so(self) -> None:
        # The I-130's "How many times have you been married?" box carries the ZIP Code's picture.
        def field(name: str, tip: str, picture: str = "text{99999}") -> bytes:
            pic = f"<format><picture>{picture}</picture></format>" if picture else ""
            return (f'<field name="{name}"><ui><textEdit/></ui>{pic}'
                    f'<assist><toolTip>{tip}</toolTip></assist></field>').encode()

        template = (
            b'<template xmlns="http://www.xfa.org/schema/xfa-template/3.3/"><subform name="form1">'
            + field("Pt2Line16_NumberofMarriages", "16. How many times have you been married? Enter Number of Times Married.")
            + field("Pt2Line10_ZipCode", "10. F. Enter Zip Code.")
            + field("P2_Line2_Code", "2. Current Mailing Address. Enter ZIP Code.")
            + field("P4_Line3_ZipCode1", "Enter City/Town, State, ZIP Code (if outside the United States, indicate "
                    "Province and Country).", picture="")
            + field("P4_Line1_ZipCode", "Current Mailing Address. Enter 5-digit Zip Code.", picture="")
            + b'</subform></template>'
        )
        kinds = formats.template_kinds(template)
        self.assertEqual(kinds["Pt2Line16_NumberofMarriages"], formats.NUMBER)
        self.assertEqual(kinds["Pt2Line10_ZipCode"], formats.ZIP)
        self.assertEqual(kinds["P2_Line2_Code"], formats.ZIP)  # described as a ZIP Code
        self.assertEqual(kinds["P4_Line3_ZipCode1"], formats.ZIP_OR_POSTAL)
        self.assertEqual(kinds["P4_Line1_ZipCode"], "")  # its name makes it a ZIP Code (box_formats)
        self.assertIsNone(formats.check(kinds["Pt2Line16_NumberofMarriages"], "1"))
        self.assertIsNotNone(formats.check(kinds["Pt2Line16_NumberofMarriages"], "one"))

    def test_too_long_and_misformatted_answers_are_errors(self) -> None:
        with TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "form.pdf"
            write_hybrid_pdf(
                pdf,
                text=[
                    ("Pt1Line4_AlienNumber", (50, 600, 200, 618), audit.FIELD_FLAG_COMB),
                    ("Pt1Line3_DOB", (50, 560, 200, 578), 0),
                    ("Pt2Line2_Receipt", (50, 520, 250, 538), 0),
                    ("Pt1Line18_ZipCode", (50, 480, 120, 498), 0),
                    ("Pt1Line18_StreetNumberName", (50, 440, 500, 458), 0),
                ],
                max_lens={"Pt1Line4_AlienNumber": 9, "Pt1Line18_ZipCode": 5},
                choices=[("Pt1Line18_State", ["", "IL", "TX"])],
            )
            values = {
                "Pt1Line4_AlienNumber": "A-123-456-789",
                "Pt1Line3_DOB": "1990-01-02",
                "Pt2Line2_Receipt": "IOE0912345678",
                "Pt1Line18_ZipCode": "62701",
                "Pt1Line18_StreetNumberName": "100 Example Street",
                "Pt1Line18_State": "Illinois",
            }
            findings = audit.box_rule_findings(kind="i-485", pdf_path=pdf, widget_pdf=pdf, values=values)
            clean = audit.box_rule_findings(
                kind="i-485", pdf_path=pdf, widget_pdf=pdf,
                values={**values, "Pt1Line4_AlienNumber": "123456789", "Pt1Line3_DOB": "01/02/1990",
                        "Pt1Line18_State": "IL"},
            )
        by_title = {item["title"]: item["fields"] for item in findings}
        self.assertEqual(by_title["An answer is longer than its box allows"], ["Pt1Line4_AlienNumber"])
        self.assertEqual(by_title["A-Number box holds an answer in the wrong format"], ["Pt1Line4_AlienNumber"])
        self.assertEqual(by_title["Date box holds an answer in the wrong format"], ["Pt1Line3_DOB"])
        self.assertEqual(by_title["State box holds an answer in the wrong format"], ["Pt1Line18_State"])
        self.assertEqual(len(findings), 4)
        self.assertEqual(clean, [])
        # Never a deliberate gap: these titles are not tied to an open item.
        for item in findings:
            self.assertFalse(audit.ABSENCE_TITLE_RE.search(item["title"]), item["title"])

    def test_the_old_iso_date_check_is_gone(self) -> None:
        self.assertFalse(hasattr(audit, "add_iso_date_findings"))


class I864ArithmeticTests(unittest.TestCase):
    """Item 25: the I-864's sums add up, and income is compared with the I-864P guideline."""

    def values(self, **overrides: str) -> dict[str, str]:
        values = {
            "P1_Line1a-f_CB": "1A", "P3_Line28_TotalNumberofImmigrants": "1", "P5_Line2_Yourself": "1",
            "P5_Line3_Married": "0", "P5_Line4_DependentChildren": "1", "P5_Line5_OtherDependents": "0",
            "P5_Line6_Sponsors": "0", "P5_Line7_SameResidence": "0", "Override": "3",
            "P6_Line2_TotalIncome": "40000", "P6_Line5_CurrentIncome": "",
            "P6_Line15_TotalHouseholdIncome": "40000.00", "P4_Line4e_State": "IL",
        }
        values.update(overrides)
        return values

    def findings(self, relationship: str = "", **overrides: str) -> list[dict[str, object]]:
        form = audit.Form("i-864", Path("/x/I-864.pdf"), self.values(**overrides))
        audit.i864_arithmetic_findings(form, petition_relationship=relationship)
        return form.findings

    def test_a_household_that_adds_up_and_meets_the_guideline(self) -> None:
        self.assertEqual(self.findings(), [])  # 3 people: 125% is $34,150

    def test_household_size_must_be_the_sum_of_its_parts(self) -> None:
        wrong = self.findings(Override="2")
        self.assertEqual(titles(wrong)[0], "Household size (Part 5 item 8) is not the sum of items 1-7")
        self.assertEqual(wrong[0]["sum_of_parts"], 3)
        # A part left blank (item 6 is the sponsor's to answer) is reported as missing elsewhere, not summed.
        self.assertEqual([t for t in titles(self.findings(P5_Line6_Sponsors="")) if "sum" in t], [])

    def test_total_income_must_be_the_sum_of_the_income_lines(self) -> None:
        wrong = self.findings(P6_Line5_CurrentIncome="$12,000", P6_Line15_TotalHouseholdIncome="40000")
        self.assertEqual(titles(wrong), ["Total household income (Part 6 item 12) is not the sum of items 7-11"])
        self.assertEqual(wrong[0]["sum_of_parts"], 52000)
        self.assertEqual(self.findings(P6_Line5_CurrentIncome="12,000", P6_Line15_TotalHouseholdIncome="52000"), [])

    def test_income_below_125_percent_is_a_warning_with_a_decision(self) -> None:
        low = self.findings(P6_Line2_TotalIncome="30000", P6_Line15_TotalHouseholdIncome="30000")
        self.assertEqual([f["severity"] for f in low], ["warning"])
        self.assertEqual(low[0]["title"], "Household income is below 125% of the poverty guideline for a household of 3")
        self.assertEqual((low[0]["minimum"], low[0]["open_item_type"]), (34150, "attorney_decision"))
        self.assertIn("joint sponsor", low[0]["suggested_question"])

    def test_active_duty_petitioner_needs_100_percent_only_for_a_spouse_or_child(self) -> None:
        low = {"P4_Line14_Checkboxes": "Y", "P6_Line2_TotalIncome": "30000", "P6_Line15_TotalHouseholdIncome": "30000"}
        self.assertEqual(self.findings("spouse_or_child", **low), [])  # 100% for 3 is $27,320
        parent = self.findings("other", **low)  # a petition for a parent or sibling: 125%
        self.assertEqual((parent[0]["minimum"], "note" in parent[0]), (34150, False))
        unknown = self.findings(**low)  # no I-130 says whom it is for: 125%, with a note
        self.assertEqual(unknown[0]["minimum"], 34150)
        self.assertIn("100% ($27,320)", unknown[0]["note"])

    def test_the_relationship_comes_from_the_packages_i130(self) -> None:
        i864 = {"P2_Line1a_FamilyName": "Sample", "P2_Line1b_GivenName": "Alex"}
        spouse = {"kind": "i-130", "expected_fields": {"Pt1Line1_Spouse": "Y", "Pt4Line4a_FamilyName": "Sample",
                                                       "Pt4Line4b_GivenName": "Alex"}}
        sibling = {"kind": "i-130", "expected_fields": {"Pt1Line1_Siblings": "Y", "Pt4Line4a_FamilyName": "Other",
                                                        "Pt4Line4b_GivenName": "Jo"}}
        self.assertEqual(audit.i130_relationship({}, i864), "")
        self.assertEqual(audit.i130_relationship({"a": spouse}, i864), "spouse_or_child")
        self.assertEqual(audit.i130_relationship({"a": sibling}, i864), "other")
        self.assertEqual(audit.i130_relationship({"a": spouse, "b": sibling}, i864), "spouse_or_child")  # by name
        self.assertEqual(audit.i130_relationship({"a": spouse, "b": sibling}, {}), "")  # several, and no name to match

    def test_alaska_has_its_own_table(self) -> None:
        active = self.findings("spouse_or_child", P4_Line14_Checkboxes="Y", P6_Line2_TotalIncome="30000",
                               P6_Line15_TotalHouseholdIncome="30000")
        self.assertEqual(active, [])
        joint = self.findings(**{"P1_Line1a-f_CB": "1D", "P4_Line14_Checkboxes": "Y",
                                 "P6_Line2_TotalIncome": "30000", "P6_Line15_TotalHouseholdIncome": "30000"})
        self.assertEqual(joint[0]["minimum"], 34150)  # only a petitioning sponsor gets 100%
        alaska = self.findings(P4_Line4e_State="AK", P6_Line2_TotalIncome="40000")
        self.assertEqual(alaska[0]["minimum"], 42688)

    def test_guideline_table(self) -> None:
        import poverty_guidelines as guidelines

        self.assertEqual(guidelines.minimum_income(2), 27050)
        self.assertEqual(guidelines.minimum_income(8, percent=100), 55720)
        self.assertEqual(guidelines.minimum_income(10), 69650 + 2 * 7100)
        self.assertEqual(guidelines.minimum_income(4, state="hi"), 47438)
        self.assertFalse(guidelines.is_stale(guidelines.CHECKED))


class FormRuleTests(unittest.TestCase):
    """Form-specific rules for the N-400, I-751, I-765 (the I-360's are in its schema test)."""

    def test_n400_trips_and_residence(self) -> None:
        from datetime import datetime as dt

        today = dt(2026, 10, 29, tzinfo=audit.UTC)

        def n400(values: dict[str, str]) -> list[dict[str, object]]:
            return audit.audit_form("n-400", Path("/x.pdf"), values, today=today)

        base = {"Part1_Eligibility": "A", "P2_Line9_DateBecamePermanentResident": "01/02/2020"}
        self.assertEqual(n400(base), [])
        long_trip = {**base, "P8_Line1_DateLeft1": "01/01/2024", "P8_Line1_DateReturn1": "09/01/2024",
                     "P9_Line1_Countries1": "Examplestan"}
        titles_ = titles(n400(long_trip))
        self.assertIn("Trip 1 (Part 8) lasted more than six months: continuous residence is presumed broken unless the "
                      "applicant shows otherwise", titles_)
        year = {**long_trip, "P8_Line1_DateReturn1": "03/01/2025"}
        self.assertTrue(any("a year or more" in t for t in titles(n400(year))))
        backwards = {**long_trip, "P8_Line1_DateReturn1": "12/01/2023"}
        self.assertIn("Trip 1 (Part 8) returns before it leaves", titles(n400(backwards)))
        early = {**base, "P2_Line9_DateBecamePermanentResident": "01/02/2023"}
        self.assertTrue(any(t.startswith("Filed before the applicant has 5 years")
                            for t in titles(n400(early))))
        spouse = {"Part1_Eligibility": "B", "P2_Line9_DateBecamePermanentResident": "01/02/2023"}
        self.assertEqual(n400(spouse), [])  # 3 years less 90 days

    def test_i751_one_route_and_its_parts(self) -> None:
        joint = {"Pt3Line1": "A", "P8_Checkbox1": "A", "P5_Line3_DaytimePhoneNumber[1]": "5555550100", "Pt8_Name": "Sam Spouse"}
        self.assertEqual(audit.audit_form("i-751", Path("/x.pdf"), joint), [])
        both = audit.audit_form("i-751", Path("/x.pdf"), {**joint, "Pt3Line1d": "D"})
        self.assertIn("Part 3 selects both a joint petition and a waiver; choose one route", titles(both))
        waiver = {"Pt3Line1d": "D"}
        self.assertEqual(titles(audit.audit_form("i-751", Path("/x.pdf"), waiver)),
                         ["The date the marriage ended (Part 1 item 13) is missing for a death or divorce waiver"])
        signed = audit.audit_form("i-751", Path("/x.pdf"), {**waiver, "P1_Line13_DateMarriageEnded": "01/02/2025"},
                                  manifest_entry={"questions": [{"key": "spouse_signature", "status": "pending_signature"}]})
        self.assertEqual(titles(signed), ["A waiver petition has the spouse's part or signature, which only a joint petition takes"])
        unsigned = audit.audit_form("i-751", Path("/x.pdf"), joint,
                                    manifest_entry={"questions": [{"key": "spouse_signature", "status": "not_applicable"}]})
        self.assertIn("A joint petition needs the spouse's signature, but the plan marks it not applicable", titles(unsigned))

    def test_i765_category_and_its_own_follow_ups(self) -> None:
        c9 = {"section_1": "c", "section_2": "9"}
        self.assertEqual(audit.audit_form("i-765", Path("/x.pdf"), c9), [])
        self.assertEqual(titles(audit.audit_form("i-765", Path("/x.pdf"), {**c9, "PtLine29_YesNo": "N"})),
                         ["Items 28-31 are answered for a category other than the one in item 27"])
        c8 = {"section_1": "c", "section_2": "8"}
        self.assertEqual(titles(audit.audit_form("i-765", Path("/x.pdf"), c8)),
                         ["(c)(8) pending asylum follow-up items are incomplete"])
        self.assertEqual(audit.audit_form("i-765", Path("/x.pdf"), {**c8, "PtLine29_YesNo": "N"}), [])
        stem = {"section_1": "c", "section_2": "3", "section_3": "C", "Line27a_Degree": "MS Comp Sci",
                "Line27b_Everify": "Example Co", "Line27c_EverifyIDNumber": "123456"}
        self.assertEqual(audit.audit_form("i-765", Path("/x.pdf"), stem), [])
        self.assertTrue(audit.audit_form("i-765", Path("/x.pdf"), {"section_1": "(c)", "section_2": "(9)"}))


class OverflowCalibrationTests(unittest.TestCase):
    """Audit fix 3: the overflow model matches what Ghostscript renders on the filing copy
    (measured by rendering each case, and again with the box grown, and comparing pixels)."""

    def test_centred_date_fills_a_60pt_box_edge_to_edge(self) -> None:
        # N-400 Part 7 P7_From1[1], P7_To2: centred (Q 1), 60 x 24 pt. Rendered whole.
        self.assertIsNone(audit.text_overflow(cnb_widget("08/01/2020", width=60, height=24, alignment=1)))
        self.assertIsNotNone(audit.text_overflow(cnb_widget("08/01/20201", width=60, height=24, alignment=1)))
        # Left-aligned, the same date starts 2 pt in and its last digit is cut.
        self.assertIsNotNone(audit.text_overflow(cnb_widget("08/01/2020", width=60, height=24)))

    def test_30pt_table_box_holds_one_line(self) -> None:
        # N-400 Part 4, 6 and 9 tables: the second line's baseline is 1.5 pt below the box.
        self.assertIsNone(audit.text_overflow(cnb_widget("SPRINGFIEL", width=66, height=30, multiline=True)))
        info = audit.text_overflow(cnb_widget("SPRING-\nFIELD", width=66, height=30, multiline=True))
        self.assertEqual((info["lines"], info["lines_that_fit"]), (2, 1))
        self.assertFalse(info["fits_if_rewrapped"])  # so the advice is Part 14, not "break the line"
        info = audit.text_overflow(cnb_widget("biological son or daughter", width=96.15, height=30, multiline=True))
        self.assertEqual((info["lines_that_fit"], info["chars_per_line"]), (1, 15))
        self.assertFalse(info["fits_if_rewrapped"])

    def test_confirmed_line_capacities(self) -> None:
        # (box, height, lines that render whole): I-751 Part 6 item 4, I-485 Part 14, I-765 item 5.d,
        # I-751 Part 11 and I-765 6.d, I-130A Part 7 and I-765 4.d/7.d.
        for width, height, lines in ((216.03, 54, 3), (515.86, 90, 5), (234, 126, 6), (234.02, 162, 8), (234, 180, 9)):
            with self.subTest(height=height):
                text = "\n".join(["LINE"] * lines)
                self.assertIsNone(audit.text_overflow(cnb_widget(text, width=width, height=height, multiline=True)))
                info = audit.text_overflow(cnb_widget(text + "\nLINE", width=width, height=height, multiline=True))
                self.assertEqual(info["lines_that_fit"], lines)

    def test_confirmed_line_widths(self) -> None:
        # Left-aligned text starts 2 pt in and may run to the box edge.
        for width, chars in ((222, 36), (234, 38), (234.02, 38), (216.03, 35), (515.86, 85)):
            with self.subTest(width=width):
                fits = cnb_widget("W" * chars, width=width, height=180, multiline=True)
                self.assertIsNone(audit.text_overflow(fits))
                info = audit.text_overflow(cnb_widget("W" * (chars + 1), width=width, height=180, multiline=True))
                self.assertEqual(info["chars_per_line"], chars)
                self.assertTrue(info["fits_if_rewrapped"])

    def test_alignment_is_read_from_the_filled_form(self) -> None:
        with TemporaryDirectory() as tmpdir:
            blank, filled = Path(tmpdir) / "blank.pdf", Path(tmpdir) / "filled.pdf"
            write_uscis_like_form(blank)
            run_quietly(xfa_tools.write_filled_pdf, blank, filled, {"Date": "08/01/2020", "City": "SPRING-\nFIELD"})
            report = audit.overflow_report(filled)
        self.assertEqual(set(report), {("City", 0)})
        self.assertEqual((report[("City", 0)]["lines"], report[("City", 0)]["lines_that_fit"]), (2, 1))
        found = audit.overflow_findings(kind="n-400", pdf_path=Path("/x/N-400.pdf"), overflow=report, manifest_entry=None)
        self.assertIn("keep one line of up to 10 characters", found[0]["fix"])


class AppearanceClipTests(unittest.TestCase):
    """Audit fix 4: pypdf's text appearances clip with `re W` and no `n`. The open path is
    stroked by Ghostscript as an empty A-Number-sized box near the bottom left of the filing
    copy's pages (on the N-400 page 4, over the Part 5 item 5.b label)."""

    def test_fill_closes_every_clip_with_the_box(self) -> None:
        with TemporaryDirectory() as tmpdir:
            blank, filled = Path(tmpdir) / "blank.pdf", Path(tmpdir) / "filled.pdf"
            write_uscis_like_form(blank)
            run_quietly(xfa_tools.write_filled_pdf, blank, filled, {"ANumber": "012345678", "Date": "08/01/2020"})
            reader = PdfReader(str(filled))
            self.assertEqual(xfa_tools.unclosed_clip_paths(reader), [])
            streams = {
                forms_workflow.leaf_field_name(forms_workflow.widget_full_name(ref.get_object())):
                ref.get_object()["/AP"]["/N"].get_object().get_data()
                for ref in reader.pages[0]["/Annots"]
                if "/AP" in ref.get_object() and ref.get_object().get("/FT") == "/Tx"
            }
        self.assertIn(b"0.000 0.000 119.500 18.000 re\nW\nn\nBT", streams["ANumber[0]"])
        self.assertIn(b"0.000 0.000 60.000 24.000 re\nW\nn\nBT", streams["Date[0]"])


def write_grouped_form(path: Path) -> None:
    """An XFA form whose data is grouped the way the I-765 and the I-485 Part 9 table group it.

    AcroForm tree and template agree, as Acrobat builds them:
      form1[0]
        #subform[0]: Name[0] (global), OtherName[0] and OtherName[1] (<bind match="none"/>),
                     Alias[0] (bound) and Alias[1] (unbound: binding it would take Alias[0]'s data),
                     Race[0] and Race[1] (two bound checkboxes, on-states AS and WH)
        Page3[0]:    Dob[0], City[0]  -> data form1/Page3/Dob, form1/Page3/City
        Table1[0]:   Row1[0].TextField1[0], Row2[0].TextField2[0] -> form1/Table1/RowN/TextFieldN
    """
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    def add(obj):
        return writer._add_object(obj)

    def stream(data: bytes):
        obj = DecodedStreamObject()
        obj.set_data(data)
        return add(obj)

    root = DictionaryObject({NameObject("/T"): TextStringObject("form1[0]"), NameObject("/Kids"): ArrayObject()})
    root_ref = add(root)
    annots = ArrayObject()
    y = [760.0]

    def container(title: str, parent, parent_ref):
        node = DictionaryObject(
            {NameObject("/T"): TextStringObject(title), NameObject("/Parent"): parent_ref, NameObject("/Kids"): ArrayObject()}
        )
        ref = add(node)
        parent["/Kids"].append(ref)
        return node, ref

    def widget(title: str, parent, parent_ref, extra: dict, width: float = 200) -> None:
        y[0] -= 24
        entries = {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/T"): TextStringObject(title),
            NameObject("/Rect"): ArrayObject(FloatObject(v) for v in (50, y[0], 50 + width, y[0] + 18)),
            NameObject("/F"): NumberObject(4),
            NameObject("/P"): page.indirect_reference,
            NameObject("/Parent"): parent_ref,
            NameObject("/MK"): DictionaryObject(),
        }
        entries.update(extra)
        ref = add(DictionaryObject(entries))
        parent["/Kids"].append(ref)
        annots.append(ref)

    def text(title: str, parent, parent_ref) -> None:
        widget(title, parent, parent_ref, {NameObject("/FT"): NameObject("/Tx"), NameObject("/DA"): TextStringObject("/Helv 10 Tf 0 g")})

    def checkbox(title: str, parent, parent_ref, state: str) -> None:
        states = DictionaryObject({NameObject(f"/{state}"): stream(b"0 g 0 0 8 8 re f"), NameObject("/Off"): stream(b"")})
        widget(
            title, parent, parent_ref,
            {NameObject("/FT"): NameObject("/Btn"), NameObject("/AP"): DictionaryObject({NameObject("/N"): states}),
             NameObject("/AS"): NameObject("/Off")},
            width=10,
        )

    main, main_ref = container("#subform[0]", root, root_ref)
    for title in ("Name[0]", "OtherName[0]", "OtherName[1]", "Alias[0]", "Alias[1]"):
        text(title, main, main_ref)
    checkbox("Race[0]", main, main_ref, "AS")
    checkbox("Race[1]", main, main_ref, "WH")
    page3, page3_ref = container("Page3[0]", root, root_ref)
    text("Dob[0]", page3, page3_ref)
    text("City[0]", page3, page3_ref)
    table, table_ref = container("Table1[0]", root, root_ref)
    for row in (1, 2):
        row_node, row_ref = container(f"Row{row}[0]", table, table_ref)
        text(f"TextField{row}[0]", row_node, row_ref)
    page[NameObject("/Annots")] = annots

    template = (
        '<template xmlns="http://www.xfa.org/schema/xfa-template/3.3/">\n<subform name="form1"\n>'
        '<pageSet><pageArea name="Page1"><field name="Barcode"><bind match="none"\n/></field></pageArea></pageSet>'
        '<subform><field name="Name"><bind match="global"\n/></field>'
        '<field name="OtherName"><bind match="none"\n/></field><field name="OtherName"><bind match="none"\n/></field>'
        '<field name="Alias"\n/><field name="Alias"><bind match="none"\n/></field>'
        '<field name="Race"/><field name="Race"/><draw name="Label"/></subform>'
        '<subform name="Page3"><field name="Dob"/><field name="City"/></subform>'
        '<subform name="Table1"><subform name="Row1"><field name="TextField1"/></subform>'
        '<subform name="Row2"><field name="TextField2"/></subform></subform>'
        "</subform\n></template>"
    )
    datasets = (
        f'<xfa:datasets xmlns:xfa="{XFA_DATA_NS}"><xfa:data><form1>'
        "<Name/><Alias/><Race/><Race/><Page3><Dob/><City/></Page3>"
        "<Table1><Row1><TextField1/></Row1><Row2><TextField2/></Row2></Table1>"
        "</form1></xfa:data></xfa:datasets>"
    )
    writer._root_object[NameObject("/AcroForm")] = add(
        DictionaryObject(
            {
                NameObject("/Fields"): ArrayObject([root_ref]),
                NameObject("/DA"): TextStringObject("/Helv 0 Tf 0 g"),
                NameObject("/DR"): DictionaryObject(
                    {
                        NameObject("/Font"): DictionaryObject(
                            {
                                NameObject("/Helv"): add(
                                    DictionaryObject(
                                        {
                                            NameObject("/Type"): NameObject("/Font"),
                                            NameObject("/Subtype"): NameObject("/Type1"),
                                            NameObject("/BaseFont"): NameObject("/Helvetica"),
                                            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
                                        }
                                    )
                                )
                            }
                        )
                    }
                ),
                NameObject("/XFA"): ArrayObject(
                    [
                        TextStringObject("template"),
                        stream(template.encode()),
                        TextStringObject("datasets"),
                        stream(datasets.encode()),
                    ]
                ),
            }
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        writer.write(handle)


def dataset_tree(pdf: Path) -> ET.Element:
    return xfa_tools.dataset_form(ET.fromstring(xfa_tools.xfa_packet(PdfReader(str(pdf)), "datasets")))


def template_bytes(pdf: Path) -> bytes:
    return xfa_tools.xfa_packet(PdfReader(str(pdf)), "template")


class XfaDataBindingTests(unittest.TestCase):
    """Adobe reads each box from the data node its template binds: values in named data groups
    (I-765 form1/PageN, I-485 form1/Table1/RowN) go there, unbound boxes are bound normally in the
    filled source so Adobe shows them, and every reader uses the same node."""

    def fill(self, tmpdir: str, mapping: dict[str, str], *, verify: bool = True) -> tuple[Path, Path, int, str]:
        blank, filled, mapping_path = (Path(tmpdir) / name for name in ("blank.pdf", "filled.pdf", "map.json"))
        write_grouped_form(blank)
        mapping_path.write_text(json.dumps(mapping))
        code, stderr = run_quietly(xfa_tools.fill_pdf, blank, filled, mapping_path, verify)
        return blank, filled, code, stderr

    def test_template_som_names_match_the_widgets(self) -> None:
        with TemporaryDirectory() as tmpdir:
            blank = Path(tmpdir) / "blank.pdf"
            write_grouped_form(blank)
            reader = PdfReader(str(blank))
            fields = xfa_tools.template_fields(template_bytes(blank))
            widgets = {name for name, spec in reader.get_fields().items() if spec.get("/FT")}
        self.assertEqual({field.som for field in fields} - {"form1[0].#pageSet[0].Page1[0].Barcode[0]"}, widgets)
        slots = {field.som: field.slot for field in fields}
        self.assertEqual(slots["form1[0].Page3[0].Dob[0]"].label(), "form1/Page3[0]/Dob[0]")
        self.assertEqual(slots["form1[0].Table1[0].Row2[0].TextField2[0]"].label(), "form1/Table1[0]/Row2[0]/TextField2[0]")
        self.assertEqual(slots["form1[0].#subform[0].Race[1]"].label(), "form1/Race[1]")
        self.assertEqual(slots["form1[0].#subform[0].Name[0]"].binding, "global")
        self.assertEqual(slots["form1[0].#subform[0].OtherName[1]"].binding, "none")

    def test_grouped_values_are_written_where_adobe_reads_them(self) -> None:
        mapping = {"Dob": "01/02/1990", "City": "Testville", "TextField2": "Forklift", "Name": "SAMPLE",
                   "Race[1]": "WH", "Alias": "ALIAS"}
        with TemporaryDirectory() as tmpdir:
            _, filled, code, stderr = self.fill(tmpdir, mapping)
            self.assertEqual(code, 0, stderr)
            data = dataset_tree(filled)
            self.assertEqual(data.find("Page3/Dob").text, "01/02/1990")
            self.assertEqual(data.find("Table1/Row2/TextField2").text, "Forklift")
            self.assertIsNone(data.find("Dob"))  # nothing directly under form1, where Adobe does not look
            self.assertEqual([node.text for node in data.findall("Race")], [None, "WH"])
            self.assertEqual(xfa_tools.extract_values(filled, list(mapping), per_widget=False), mapping)
            self.assertEqual(xfa_tools.adobe_view(filled, list(mapping)), mapping)
            self.assertEqual(xfa_tools.extract_visible(filled, ["Dob", "TextField2", "Race[1]"]),
                             {"Dob": "01/02/1990", "TextField2": "Forklift", "Race[1]": "WH"})
            stored = audit.xfa_values(filled)
            dump = xfa_tools.field_dump(filled)
        self.assertEqual((stored["Dob"], stored["TextField2"], stored["Name"], stored["Race[1]"]),
                         ("01/02/1990", "Forklift", "SAMPLE", "WH"))
        self.assertEqual({item["name"]: item["data"] for item in dump["fields"]}["Dob"], "form1/Page3[0]/Dob[0]")
        self.assertIn("TextField2", dump["xfa_nodes"])

    def test_a_value_outside_its_group_reads_blank_everywhere(self) -> None:
        """What fill wrote before: form1/Dob. Adobe shows the Page3 node, which is empty."""
        with TemporaryDirectory() as tmpdir:
            blank, old = Path(tmpdir) / "blank.pdf", Path(tmpdir) / "old.pdf"
            write_grouped_form(blank)
            reader = PdfReader(str(blank))
            root = ET.fromstring(xfa_tools.xfa_packet(reader, "datasets"))
            xfa_tools.apply_fields(root, {"Dob": "01/02/1990"})  # no bindings: the old top-level node
            writer = PdfWriter(clone_from=reader)
            xfa = writer._root_object["/AcroForm"]["/XFA"]
            stream = DecodedStreamObject()
            stream.set_data(ET.tostring(root))
            xfa[3] = writer._add_object(stream)
            with old.open("wb") as handle:
                writer.write(handle)
            self.assertEqual(xfa_tools.extract_values(old, ["Dob"]), {"Dob": ""})
            mismatches = xfa_tools.verify_output(old, {"Dob": "01/02/1990"}, check_visible=False)
            self.assertIn("Dob", mismatches["xfa"])
            entry = {"expected_fields": {"Dob": "01/02/1990"}}
            findings = audit.adobe_view_findings(kind="i-765", pdf_path=old, xfa_pdf=old, manifest_entry=entry)
        self.assertEqual(titles(findings), ["Adobe shows planned answers blank or different when it opens the XFA source"])
        self.assertEqual(findings[0]["mismatches"], [{"field": "Dob", "expected": "01/02/1990", "adobe_shows": ""}])

    def test_unbound_boxes_are_bound_in_the_filled_source_only(self) -> None:
        with TemporaryDirectory() as tmpdir:
            blank, filled, code, stderr = self.fill(tmpdir, {"OtherName[1]": "ALIAS ONE"})
            self.assertEqual(code, 0, stderr)
            self.assertIn("fill bound them in this file so Adobe shows them", stderr)
            before, after = template_bytes(blank), template_bytes(filled)
            data = dataset_tree(filled)
            view = xfa_tools.adobe_view(filled, ["OtherName[0]", "OtherName[1]"])
            visible = xfa_tools.extract_visible(filled, ["OtherName[0]", "OtherName[1]"])
            findings = audit.adobe_view_findings(
                kind="i-765", pdf_path=filled, xfa_pdf=filled, manifest_entry={"expected_fields": {"OtherName[1]": "ALIAS ONE"}}
            )
        # Both OtherName fields of the group are rebound, so occurrence numbers stay in step.
        self.assertEqual(after, before.replace(b'<field name="OtherName"><bind match="none"', b'<field name="OtherName"><bind match="once"'))
        self.assertEqual(after.count(b'match="once"'), 2)
        self.assertEqual([node.text for node in data.findall("OtherName")], [None, "ALIAS ONE"])
        self.assertEqual(view, {"OtherName[0]": "", "OtherName[1]": "ALIAS ONE"})
        self.assertEqual(visible, {"OtherName[0]": "", "OtherName[1]": "ALIAS ONE"})
        self.assertEqual(findings, [])

    def test_unbound_box_that_would_take_another_fields_data_is_reported(self) -> None:
        with TemporaryDirectory() as tmpdir:
            blank, filled, code, stderr = self.fill(tmpdir, {"Alias[0]": "FIRST", "Alias[1]": "SECOND"})
            self.assertEqual(template_bytes(filled), template_bytes(blank))
        self.assertEqual(code, 1)  # --verify fails: Adobe would show Alias[1] empty
        self.assertIn("could not be bound without taking another field's data", stderr)
        self.assertIn("the template leaves this box unbound", stderr)

    def test_bound_and_global_fields_need_no_template_change(self) -> None:
        with TemporaryDirectory() as tmpdir:
            blank, filled, code, stderr = self.fill(tmpdir, {"Name": "SAMPLE", "Dob": "01/02/1990"})
            self.assertEqual(code, 0, stderr)
            self.assertEqual(template_bytes(filled), template_bytes(blank))
        self.assertNotIn("unbound", stderr)


# The build tests fill a one-page stand-in for the I-765, so its plan names this small schema
# (registered only while those tests run) rather than the real I-765 schema and its field list.
TEST_BUILD_SCHEMA = "test_place_and_note"
TEST_BUILD_SCHEMA_SPEC = {
    "kind": "i-765",
    "description": "Test stand-in: one place box and one note.",
    "required_questions": {
        "place": {"label": "Place of birth", "required_fields": ["Place[0]"], "allowed_statuses": ["filled"]},
        "note": {
            "label": "Additional note",
            "required_fields": ["Note"],
            "allowed_statuses": ["filled", "pending_client_input"],
        },
    },
}


def write_build_matter(root: Path, *, ledger_ids: tuple[str, ...] = ("q-note",)) -> build_forms.Layout:
    """A fictional matter with two plans: an I-765 (audited) and an X-1 (no audit rules)."""
    matter = root.resolve() / "Sample Matter"  # build resolves the matter path
    blank_dir = matter / "output" / "working" / "forms" / "blank"
    blank_dir.mkdir(parents=True)
    write_marriage_place_form(blank_dir / "I-765.pdf")
    write_marriage_place_form(blank_dir / "X-1.pdf")
    layout = build_forms.Layout(matter, "main")
    layout.plans.mkdir(parents=True)
    layout.facts.write_text(json.dumps({"matter": "Sample", "facts": []}))
    for name, kind in (("I-765", "i-765"), ("X-1", "x-1")):
        plan = {
            "kind": kind,
            "subject": "beneficiary",
            **({"question_schema": TEST_BUILD_SCHEMA} if kind == "i-765" else {}),
            "questions": [
                question(key="place", label="Place of birth", status=STATUS_FILLED, field_values={"Place[0]": "Austin"}),
                question(
                    key="note",
                    label="Additional note",
                    status="pending_client_input",
                    field_values={"Note": ""},
                    open_item="q-note",
                ),
            ],
        }
        (layout.plans / f"{name}.plan.json").write_text(json.dumps(plan))
    ledger = matter / "output" / "deliverables" / "open-items.json"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(json.dumps({"items": [{"id": item, "status": "open"} for item in ledger_ids]}))
    return layout


def set_answer(layout: build_forms.Layout, name: str, value: str) -> None:
    path = layout.plans / f"{name}.plan.json"
    plan = json.loads(path.read_text())
    plan["questions"][0]["field_values"]["Place[0]"] = value
    path.write_text(json.dumps(plan))


@unittest.skipUnless(shutil.which("gs") or shutil.which("gswin64c"), "build renders with Ghostscript")
class BuildCommandTests(unittest.TestCase):
    """forms_workflow.py build: plans -> verified filing copies + audit, short summary."""

    def setUp(self) -> None:
        QUESTION_SCHEMAS[TEST_BUILD_SCHEMA] = TEST_BUILD_SCHEMA_SPEC
        self.addCleanup(QUESTION_SCHEMAS.pop, TEST_BUILD_SCHEMA, None)
        # The stand-in form has none of the real I-765's boxes, so only the generic checks run on it.
        patcher = patch.dict(audit.AUDITORS, {"i-765": audit.Form.blank_output})
        patcher.start()
        self.addCleanup(patcher.stop)

    def build(self, layout: build_forms.Layout, **kwargs) -> dict[str, object]:
        report, _ = run_quietly(build_forms.build, layout, **kwargs)
        return report

    def test_build_writes_every_artifact_and_ties_deliberate_gaps(self) -> None:
        with TemporaryDirectory() as tmpdir:
            layout = write_build_matter(Path(tmpdir))
            report = self.build(layout)
            forms = {form["name"]: form for form in report["forms"]}
            for name in ("I-765", "X-1"):
                self.assertTrue((layout.forms_dir / f"{name}.pdf").exists())
                self.assertTrue((layout.source_dir / f"{name} source.pdf").exists())
                self.assertTrue((layout.mappings / f"{name}.mapping.json").exists())
                self.assertEqual(forms[name]["reason"], "new")
                self.assertEqual(forms[name]["verify"], "ok")
            manifest = json.loads(layout.manifest.read_text())["files"]
            entry = manifest[str(layout.forms_dir / "I-765.pdf")]
            self.assertEqual(entry["fact_table_path"], str(layout.facts))
            self.assertEqual(entry["questions"][1]["open_item"], "q-note")
            payload = json.loads(layout.audit.read_text())
            unresolved = [f for f in payload["findings"] if f.get("question_key") == "note"]
            self.assertEqual([f["open_item"] for f in unresolved], ["q-note"])
            manual = [r for r in payload["results"] if r.get("coverage") == "manual"]
            self.assertEqual([r["form"] for r in manual], ["x-1"])
            self.assertEqual(manual[0]["open_questions"][0]["open_item"], "q-note")
            self.assertTrue(layout.state.exists() and layout.log.exists())
            self.assertEqual(build_forms.needs_work(report), [])
            lines = build_forms.summary_lines(report)
        self.assertLessEqual(len(lines), build_forms.SUMMARY_LINES)
        self.assertIn("rebuilt 2 (2 new)", lines[0])
        self.assertTrue(any(line.startswith("Status: clean") for line in lines))
        self.assertTrue(any("no audit rules" in line for line in lines))

    def test_a_blank_of_another_edition_is_not_filled_until_the_attorney_decides(self) -> None:
        newer = {"status": editions.NEW_EDITION, "kind": "i-765", "file_edition": "10/01/27",
                 "schema_edition": "08/21/25", "blank": "", "sha256": ""}

        def check_blank(kind: str, blank: Path, schema_name: str | None = None) -> dict:
            return {**newer, "kind": kind} if kind == "i-765" else {"status": editions.NO_SCHEMA, "kind": kind}

        with TemporaryDirectory() as tmpdir, patch.object(editions, "check_blank", side_effect=check_blank):
            layout = write_build_matter(Path(tmpdir))
            report = self.build(layout)
            forms = {form["name"]: form for form in report["forms"]}
            self.assertIn("not filled: The I-765 blank is the 10/01/27 edition", forms["I-765"]["error"])
            self.assertFalse((layout.forms_dir / "I-765.pdf").exists())
            self.assertEqual([item["id"] for item in report["suggested_open_items"]], ["forms-edition-i-765"])
            lines = build_forms.summary_lines(report)
            self.assertTrue(any("Open items to add" in line and "forms-edition-i-765" in line for line in lines))
            self.assertIn("1 form(s) not built", build_forms.needs_work(report))
            # The attorney decided to prepare it on the new edition. The stand-in schema has no field
            # list, so no box can be shown to be the same: nothing is filled, and the audit holds it.
            ledger = layout.matter / "output" / "deliverables" / "open-items.json"
            ledger.write_text(json.dumps({"items": [{"id": "q-note", "status": "open"},
                                                    {"id": "forms-edition-i-765", "status": "open"}]}))
            allowed = self.build(layout, allow_new_edition={"i-765": "forms-edition-i-765"})
            payload = json.loads(layout.audit.read_text())
            self.assertTrue((layout.forms_dir / "I-765.pdf").exists())
            stored = xfa_tools.extract_values(layout.source_dir / "I-765 source.pdf", ["Place[0]"])
        self.assertEqual(stored, {"Place[0]": ""})
        edition_errors = [f for f in payload["findings"] if "form tools were not built for" in f["title"]
                          or "their boxes changed" in f["title"]]
        self.assertEqual([f.get("open_item") for f in edition_errors], [None, None])
        untied = [f["title"] for f in payload["findings"] if f["severity"] == "error" and not f.get("open_item")]
        self.assertIn("1 answer(s) are not on the form: their boxes changed on the 10/01/27 edition", untied)
        self.assertIn("Prepared form has no populated stored values", untied)
        self.assertIn("3 untied audit error(s)", build_forms.needs_work(allowed))

    def test_an_edit_made_outside_build_is_a_conflict_not_a_silent_refill(self) -> None:
        with TemporaryDirectory() as tmpdir:
            layout = write_build_matter(Path(tmpdir))
            self.build(layout)
            source = layout.source_dir / "I-765 source.pdf"
            # Someone corrects the place in Acrobat instead of in the plan.
            edited = Path(tmpdir) / "edited.pdf"
            run_quietly(xfa_tools.write_filled_pdf, source, edited, {"Place[0]": "Austin, TX"})
            shutil.copyfile(edited, source)
            edited_bytes = source.read_bytes()
            report = self.build(layout)
            form = {f["name"]: f for f in report["forms"]}["I-765"]
            self.assertIn("edited outside build: 1 value(s)", form["error"])
            self.assertIn("Place[0]: plan 'Austin', source 'Austin, TX'", form["error"])
            self.assertEqual(source.read_bytes(), edited_bytes)  # nothing thrown away
            self.assertIn("1 form(s) not built", build_forms.needs_work(report))
            # Once the plan holds the edit, build fills from the plan again.
            set_answer(layout, "I-765", "Austin, TX")
            settled = self.build(layout)
            self.assertEqual({f["name"]: f for f in settled["forms"]}["I-765"]["error"], "")
            self.assertEqual(xfa_tools.extract_values(source, ["Place[0]"]), {"Place[0]": "Austin, TX"})
            # --force discards an edit.
            run_quietly(xfa_tools.write_filled_pdf, source, edited, {"Place[0]": "Elsewhere"})
            shutil.copyfile(edited, source)
            forced = self.build(layout, force=True)
            self.assertEqual({f["name"]: f for f in forced["forms"]}["I-765"]["error"], "")
            self.assertEqual(xfa_tools.extract_values(source, ["Place[0]"]), {"Place[0]": "Austin, TX"})

    def test_a_source_saved_again_without_edits_is_simply_refilled(self) -> None:
        with TemporaryDirectory() as tmpdir:
            layout = write_build_matter(Path(tmpdir))
            self.build(layout)
            source = layout.source_dir / "I-765 source.pdf"
            source.write_bytes(source.read_bytes() + b"\n% resaved\n")
            report = self.build(layout)
        form = {f["name"]: f for f in report["forms"]}["I-765"]
        self.assertEqual((form["error"], form["reason"]), ("", "output changed outside build"))

    def test_allow_new_edition_takes_form_and_open_item(self) -> None:
        self.assertEqual(build_forms.parse_allowed_editions(["I-485=forms-edition-i-485"]), {"i-485": "forms-edition-i-485"})
        with self.assertRaises(build_forms.BuildError):
            build_forms.parse_allowed_editions(["I-485"])

    def test_second_build_refills_only_the_changed_plan(self) -> None:
        with TemporaryDirectory() as tmpdir:
            layout = write_build_matter(Path(tmpdir))
            self.build(layout)
            x1_copy = (layout.forms_dir / "X-1.pdf").read_bytes()
            again = self.build(layout)
            self.assertEqual([form["reason"] for form in again["forms"]], ["", ""])
            set_answer(layout, "I-765", "Dallas")
            changed = self.build(layout)
            reasons = {form["name"]: form["reason"] for form in changed["forms"]}
            self.assertEqual(reasons, {"I-765": "answers changed", "X-1": ""})
            self.assertEqual((layout.forms_dir / "X-1.pdf").read_bytes(), x1_copy)
            stored = xfa_tools.extract_values(layout.source_dir / "I-765 source.pdf", ["Place[0]"])
            lines = build_forms.summary_lines(changed)
            # A plan edit that leaves the answers alone (an open item, a note) refills nothing.
            path = layout.plans / "X-1.plan.json"
            plan = json.loads(path.read_text())
            plan["questions"][1]["notes"] = "Asked the client on intake."
            path.write_text(json.dumps(plan))
            quiet = self.build(layout)
        self.assertEqual(stored, {"Place[0]": "Dallas"})
        self.assertIn("rebuilt 1 (1 answers changed): I-765; unchanged 1", lines[0])
        self.assertEqual([form["reason"] for form in quiet["forms"]], ["", ""])

    def test_untied_errors_and_missing_ledger_ids_need_work(self) -> None:
        with TemporaryDirectory() as tmpdir:
            layout = write_build_matter(Path(tmpdir), ledger_ids=())
            path = layout.plans / "I-765.plan.json"
            plan = json.loads(path.read_text())
            plan["questions"].append(question(key="other", label="Other names", status="missing", field_values={"Place[1]": ""}))
            path.write_text(json.dumps(plan))
            report = self.build(layout)
            problems = build_forms.needs_work(report)
            lines = build_forms.summary_lines(report)
        self.assertIn("1 untied audit error(s)", problems)
        self.assertIn("1 error(s) tied to 1 id(s) not open in the ledger", problems)
        self.assertTrue(any("untied: Other names is missing [Place[1]]" in line for line in lines), lines)
        self.assertTrue(any("not open in output/deliverables/open-items.json: q-note" in line for line in lines))

    def test_verify_failure_and_field_check_are_reported(self) -> None:
        with TemporaryDirectory() as tmpdir:
            layout = write_build_matter(Path(tmpdir))
            path = layout.plans / "I-765.plan.json"
            plan = json.loads(path.read_text())
            plan["questions"][0]["field_values"]["Unit"] = "XYZ"  # not an on-state of the Unit group
            path.write_text(json.dumps(plan))
            report = self.build(layout)
            form = next(form for form in report["forms"] if form["name"] == "I-765")
            lines = build_forms.summary_lines(report)
        self.assertEqual(form["verify"], "failed")
        self.assertIn("not_an_on_state", form["field_check"])
        self.assertTrue(any("verify FAILED" in line for line in lines))
        self.assertTrue(any("field check: 1 not an on-state: Unit = 'XYZ'" in line for line in lines), lines)

    def test_check_only_changes_nothing_and_flags_stale_plans(self) -> None:
        with TemporaryDirectory() as tmpdir:
            layout = write_build_matter(Path(tmpdir))
            self.build(layout)
            before = {path.name: path.read_bytes() for path in layout.forms_dir.iterdir()}
            audit_before = layout.audit.read_bytes()
            set_answer(layout, "I-765", "Dallas")
            report, _ = run_quietly(build_forms.check, layout)
            after = {path.name: path.read_bytes() for path in layout.forms_dir.iterdir()}
            form = next(form for form in report["forms"] if form["name"] == "I-765")
            self.assertTrue(layout.review_audit.exists())
            self.assertEqual(layout.audit.read_bytes(), audit_before)
        self.assertEqual(before, after)
        self.assertEqual(form["stale"], "plan answers changed since the last build")
        self.assertEqual(form["verify"], "failed")
        self.assertIn("1 stale form(s)", build_forms.needs_work(report))

    def test_a_removed_plan_takes_its_filing_copy_with_it(self) -> None:
        with TemporaryDirectory() as tmpdir:
            layout = write_build_matter(Path(tmpdir))
            self.build(layout)
            (layout.plans / "X-1.plan.json").unlink()
            report = self.build(layout)
            self.assertFalse((layout.forms_dir / "X-1.pdf").exists())
            self.assertFalse((layout.source_dir / "X-1 source.pdf").exists())
            manifest = json.loads(layout.manifest.read_text())["files"]
        self.assertEqual(list(manifest), [str(layout.forms_dir / "I-765.pdf")])
        self.assertEqual(report["removed"], ["output/deliverables/Forms/X-1.pdf", "output/working/forms/source/X-1 source.pdf"])

    def test_cli_prints_a_short_summary_and_sets_the_exit_code(self) -> None:
        with TemporaryDirectory() as tmpdir:
            layout = write_build_matter(Path(tmpdir))
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                code = build_forms.main([str(layout.matter)])
        self.assertEqual(code, 0)
        self.assertLessEqual(len(out.getvalue().splitlines()), build_forms.SUMMARY_LINES)
        self.assertLess(len(out.getvalue()), 2500)


def moved_box_blank(source: Path, out: Path, box: str, dy: float = 40.0) -> None:
    """A copy of an official blank with one box moved: a stand-in for a new edition's changed box."""
    writer = PdfWriter(clone_from=PdfReader(str(source)))
    for page in writer.pages:
        for ref in page.get("/Annots") or []:
            annot = ref.get_object()
            if forms_workflow.leaf_field_name(forms_workflow.widget_full_name(annot)).split("[")[0] == box:
                x0, y0, x1, y1 = (float(value) for value in annot["/Rect"])
                annot[NameObject("/Rect")] = ArrayObject([FloatObject(v) for v in (x0, y0 + dy, x1, y1 + dy)])
    with out.open("wb") as handle:
        writer.write(handle)


@unittest.skipUnless(shutil.which("gs") or shutil.which("gswin64c"), "build renders with Ghostscript")
class NewEditionBuildTests(unittest.TestCase):
    """Finding 4: on a blank the tools weren't built for, only the boxes that are the same are filled,
    and the form passes only after a box-by-box check is recorded in the plan."""

    def test_only_unchanged_boxes_are_filled_and_the_form_waits_for_the_check(self) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from official_blanks import official_blank, why_missing

        blank = official_blank("g-1145")
        if blank is None:
            self.skipTest(why_missing("g-1145"))
        with TemporaryDirectory() as tmp:
            matter = Path(tmp).resolve() / "Sample Matter"
            layout = build_forms.Layout(matter, "main")
            layout.blank_dir.mkdir(parents=True)
            moved_box_blank(blank, layout.blank_dir / "G-1145.pdf", "MobilePhoneNumber")
            self.assertEqual(editions.compare_boxes("g-1145", layout.blank_dir / "G-1145.pdf",
                                                    ["LastName", "Email", "MobilePhoneNumber"]),
                             {"MobilePhoneNumber": "moved on page 1"})
            layout.plans.mkdir(parents=True)
            plan = skeleton_plan("g1145_e_notification")
            answers = {"applicant_name": {"LastName": "Sample", "FirstName": "Alex", "MiddleName": ""},
                       "notification_contact": {"Email": "alex@example.com", "MobilePhoneNumber": "5555550100"}}
            for item in plan["questions"]:
                item.update(status="filled", field_values=answers[item["key"]])
            plan_path = layout.plans / "G-1145.plan.json"
            plan_path.write_text(json.dumps(plan))
            ledger = matter / "output" / "deliverables" / "open-items.json"
            ledger.parent.mkdir(parents=True)
            ledger.write_text(json.dumps({"items": [{"id": "forms-edition-g-1145", "status": "open",
                                                     "title": "The G-1145 blank doesn't match the form tools"}]}))

            refused, _ = run_quietly(build_forms.build, layout)
            self.assertIn("--refresh-blank G-1145", refused["forms"][0]["error"])
            self.assertEqual(refused["suggested_open_items"][0]["title"], "The G-1145 blank doesn't match the form tools")

            allowed, _ = run_quietly(build_forms.build, layout, allow_new_edition={"g-1145": "forms-edition-g-1145"})
            source = layout.source_dir / "G-1145 source.pdf"
            stored = xfa_tools.extract_values(source, ["Email", "MobilePhoneNumber", "LastName"])
            self.assertEqual(stored, {"Email": "alex@example.com", "MobilePhoneNumber": "", "LastName": "Sample"})
            payload = json.loads(layout.audit.read_text())
            untied = {f["title"]: f for f in payload["findings"] if f["severity"] == "error" and not f.get("open_item")}
            edition = untied["Prepared on the 09/26/14 edition, which the form tools were not built for (09/26/14)"]
            self.assertEqual(sorted(edition["unchecked_boxes"]), ["Email", "FirstName", "LastName"])
            self.assertEqual(untied["1 answer(s) are not on the form: their boxes changed on the 09/26/14 edition"]["fields"],
                             ["MobilePhoneNumber"])
            self.assertTrue(build_forms.needs_work(allowed))
            self.assertTrue(any("withheld 1 that changed (MobilePhoneNumber)" in line
                                for line in build_forms.summary_lines(allowed)))

            # The preparer drops the mobile number (the email is enough) and records the check of
            # each box filled; the form then passes, its error tied to the attorney's decision.
            plan["questions"][1]["field_values"]["MobilePhoneNumber"] = ""
            plan["new_edition_review"] = {"edition": "09/26/14", "boxes": {
                "LastName": "Family name, same box", "FirstName": "Given name, same box", "Email": "Email, same box"}}
            plan_path.write_text(json.dumps(plan))
            checked, _ = run_quietly(build_forms.build, layout, allow_new_edition={"g-1145": "forms-edition-g-1145"})
            payload = json.loads(layout.audit.read_text())
            # The reviewer's check sees the same form: not stale for its edition, and it verifies.
            review, _ = run_quietly(build_forms.check, layout)
        errors = [f for f in payload["findings"] if f["severity"] == "error"]
        self.assertEqual([f.get("open_item") for f in errors], ["forms-edition-g-1145"])
        self.assertEqual(build_forms.needs_work(checked), [])
        self.assertEqual((review["forms"][0]["stale"], review["forms"][0]["verify"]), ("", "ok"))
        self.assertEqual(build_forms.needs_work(review), [])

    def test_refresh_blank_moves_the_old_blank_aside_and_downloads_the_current(self) -> None:
        def fake_download(spec, output_dir, *, include_instructions, overwrite):
            write_marriage_place_form(output_dir / spec.pdf_name)
            return {"pdf_path": str(output_dir / spec.pdf_name), "edition_date": "09/18/26"}

        with TemporaryDirectory() as tmp:
            layout = build_forms.Layout(Path(tmp) / "Sample", "main")
            layout.blank_dir.mkdir(parents=True)
            write_marriage_place_form(layout.blank_dir / "I-485.pdf")
            (layout.blank_dir / "I-485 Instructions.pdf").write_bytes(b"%PDF-1.7 old instructions")
            with patch.object(build_forms.downloader, "download_form", side_effect=fake_download), \
                    patch.object(editions, "check_blank", return_value={"kind": "i-485", "file_edition": "01/20/25",
                                                                       "schema_edition": "09/18/26", "status": "new_edition"}):
                lines, _ = run_quietly(build_forms.setup, layout, [], [], refresh=["I-485"])
            moved = sorted(path.name for path in (layout.blank_dir / "superseded").iterdir())
            self.assertTrue((layout.blank_dir / "I-485.pdf").exists())
        self.assertEqual(moved, ["I-485 (01-20-25).pdf", "I-485 Instructions (01-20-25).pdf"])
        self.assertTrue(any("the 01/20/25 blank moved to blank/superseded/" in line for line in lines))


class BuildSetupTests(unittest.TestCase):
    def test_new_writes_skeletons_and_fetches_missing_blanks(self) -> None:
        def fake_download(spec, output_dir, *, include_instructions, overwrite):
            write_marriage_place_form(output_dir / spec.pdf_name)
            return {"pdf_path": str(output_dir / spec.pdf_name), "edition_date": "09/17/18"}

        with TemporaryDirectory() as tmpdir:
            matter = Path(tmpdir) / "Sample"
            matter.mkdir()
            layout = build_forms.Layout(matter, "main")
            layout.blank_dir.mkdir(parents=True)
            (layout.blank_dir / "forms-metadata.json").write_text(json.dumps({"i-130": {"edition_date": "04/01/24"}}))
            with patch.object(build_forms.downloader, "download_form", side_effect=fake_download) as download:
                lines, _ = run_quietly(
                    build_forms.setup, layout, ["G-28 - Petitioner=g28_represented_client"], ["i-912"]
                )
                plan = json.loads((layout.plans / "G-28 - Petitioner.plan.json").read_text())
                again, _ = run_quietly(build_forms.setup, layout, ["G-28 - Petitioner=g28_represented_client"], [])
            metadata = json.loads((layout.blank_dir / "forms-metadata.json").read_text())
            fields_saved = (matter / "output" / "working" / "forms" / "fields" / "G-28.json").exists()
        # A first setup of a paper filing (the default) adds the G-1145.
        self.assertEqual(sorted(call.args[0].form_id for call in download.call_args_list), ["g-1145", "g-28", "i-912"])
        self.assertTrue(any("added a G-1145 plan" in line for line in lines))
        self.assertEqual(plan["question_schema"], "g28_represented_client")
        self.assertEqual(plan["fact_table_path"], "form facts.json")
        self.assertEqual(sorted(metadata), ["g-1145", "g-28", "i-130", "i-912"])  # merged, not replaced
        self.assertTrue(fields_saved)
        self.assertTrue(any("09/17/18" in line for line in lines))
        self.assertTrue(any("plan kept (already exists)" in line for line in again))

    def setup_matter(self, root: Path, *, method: str | None = None) -> build_forms.Layout:
        matter = root / "Sample"
        layout = build_forms.Layout(matter, "main")
        layout.blank_dir.mkdir(parents=True)
        for name in ("G-28", "G-1145", "G-1450", "G-1650", "I-130"):
            write_marriage_place_form(layout.blank_dir / f"{name}.pdf")
        if method:
            meta = matter / "output" / "working" / "workflow" / "matter-meta.json"
            meta.parent.mkdir(parents=True)
            meta.write_text(json.dumps({"filing_method": method}))
        return layout

    def test_g1145_is_added_only_to_a_first_paper_setup(self) -> None:
        with TemporaryDirectory() as tmpdir:
            online = self.setup_matter(Path(tmpdir) / "a", method="online")
            run_quietly(build_forms.setup, online, ["G-28=g28_represented_client"], [])
            self.assertFalse((online.plans / "G-1145.plan.json").exists())
            paper = self.setup_matter(Path(tmpdir) / "b", method="paper")
            run_quietly(build_forms.setup, paper, ["G-28=g28_represented_client"], [])
            self.assertEqual(json.loads((paper.plans / "G-1145.plan.json").read_text())["question_schema"], "g1145_e_notification")
            # Removed on purpose: a later setup doesn't bring it back.
            (paper.plans / "G-1145.plan.json").unlink()
            run_quietly(build_forms.setup, paper, ["I-130=i130_family_petition"], [])
            self.assertFalse((paper.plans / "G-1145.plan.json").exists())

    def test_payment_forms_come_from_the_fees_tool(self) -> None:
        fees = {"filing_method": "paper", "payment_forms_needed": [{"form": "I-130", "what": "filing fee", "amount": 675},
                                                                    {"form": "I-485", "what": "filing fee", "amount": 1440}]}
        with TemporaryDirectory() as tmpdir:
            layout = self.setup_matter(Path(tmpdir), method="online")
            fees_json = Path(tmpdir) / "fees.json"
            fees_json.write_text(json.dumps(fees))
            lines, _ = run_quietly(build_forms.setup, layout, [], [], payments=fees_json)
            card = json.loads((layout.plans / "G-1450 - I-485 filing fee.plan.json").read_text())
            run_quietly(build_forms.setup, layout, [], [], payments=fees_json, payment_form="G-1650")
            bank = json.loads((layout.plans / "G-1650 - I-130 filing fee.plan.json").read_text())
            with self.assertRaises(build_forms.BuildError):
                build_forms.setup(layout, [], [], payments=fees_json, payment_form="G-1651")
        self.assertTrue(any("pays the I-485 filing fee, $1,440" in line for line in lines))
        self.assertEqual((card["question_schema"], card["pays_for"]), ("g1450_credit_card_payment", "I-485"))
        self.assertEqual((card["pays_what"], card["pays_amount"], card["fee_order"]), ("filing fee", 1440, 2))
        amount = next(q for q in card["questions"] if q["key"] == "payment_amount")
        self.assertEqual((amount["status"], amount["field_values"]), ("filled", {"AuthorizedPaymentAmt": "1,440"}))
        details = next(q for q in card["questions"] if q["key"] == "card_details")
        self.assertEqual(details["status"], "pending_signature")  # the card holder writes it; the only status allowed
        self.assertEqual((bank["question_schema"], bank["pays_for"]), ("g1650_ach_payment", "I-130"))

    def test_unknown_schema_and_missing_plans_are_input_errors(self) -> None:
        with TemporaryDirectory() as tmpdir:
            matter = Path(tmpdir) / "Sample"
            matter.mkdir()
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(build_forms.main([str(matter)]), 2)
                self.assertEqual(build_forms.main([str(matter), "--new", "I-130=no_such_schema"]), 2)
        self.assertIn("No question plans", err.getvalue())
        self.assertIn("Unknown schema 'no_such_schema'", err.getvalue())


class OpenItemTieTests(unittest.TestCase):
    """The audit ties an error to the open item its plan question names, and nothing else."""

    ENTRY = {
        "questions": [
            question(key="dob", label="Parent DOB", status="pending_client_input",
                     field_values={"Pt5Line3_DateofBirth": "", "Pt5Line8_DateofBirth[0]": ""}, open_item="q-parents"),
            question(key="i94", label="I-94", status="missing", field_values={"P1Line12_I94": ""}, open_item="doc-i94"),
            question(key="name", label="Name", status=STATUS_FILLED, field_values={"Pt1Line1a": "SAMPLE"}, open_item="x"),
            question(key="phone", label="Phone", status="missing", field_values={"Pt3Line3": ""}),
        ]
    }

    def tie(self, findings: list[dict[str, object]]) -> list[dict[str, object]]:
        audit.tie_open_items(findings, self.ENTRY)
        return findings

    def test_unresolved_question_errors_are_tied(self) -> None:
        findings = self.tie([
            {"severity": "error", "title": "Parent DOB is still pending client input", "question_key": "dob"},
            {"severity": "error", "title": "Phone is missing", "question_key": "phone"},  # no open_item on the question
            {"severity": "warning", "title": "I-94 is missing", "question_key": "i94"},
        ])
        self.assertEqual(findings[0]["open_item"], "q-parents")
        self.assertNotIn("open_item", findings[1])
        self.assertNotIn("open_item", findings[2])

    def test_required_section_status_error_is_tied_for_an_open_question(self) -> None:
        title = "Question plan uses an invalid status for a required form section"
        findings = self.tie([
            {"severity": "error", "title": title, "question_key": "i94", "status": "missing"},
            {"severity": "error", "title": title, "question_key": "phone", "status": "missing"},  # no open_item
            {"severity": "error", "title": title, "question_key": "name", "status": STATUS_FILLED},  # filled
        ])
        self.assertEqual(findings[0]["open_item"], "doc-i94")
        self.assertNotIn("open_item", findings[1])
        self.assertNotIn("open_item", findings[2])

    def test_form_specific_absence_errors_are_tied_when_every_field_is_a_deliberate_gap(self) -> None:
        findings = self.tie([
            {"severity": "error", "title": "Missing parent identity fields", "fields": ["Pt5Line8_DateofBirth[0]", "Pt5Line3_DateofBirth"]},
            {"severity": "error", "title": "Missing recent-arrival fields", "fields": ["P1Line12_I94", "Pt5Line3_DateofBirth"]},
            {"severity": "error", "title": "Missing recent-arrival fields", "fields": ["P1Line12_I94", "Pt1Line1a"]},
            {"severity": "error", "title": "Missing identity fields", "fields": ["Pt5Line8_DateofBirth[1]"]},
        ])
        self.assertEqual(findings[0]["open_item"], "q-parents")
        self.assertEqual((findings[1]["open_item"], findings[1]["open_items"]), ("doc-i94", ["doc-i94", "q-parents"]))
        self.assertNotIn("open_item", findings[2])  # Pt1Line1a belongs to a filled question
        self.assertNotIn("open_item", findings[3])  # box [1] is not part of the open question

    def test_mistakes_are_never_tied(self) -> None:
        findings = self.tie([
            {"severity": "error", "title": "Visible I-485 output does not reflect stored identity, basis, or arrival facts", "fields": ["P1Line12_I94"]},
            {"severity": "error", "title": "Unexpected non-empty XFA fields are present", "fields": ["P1Line12_I94"]},
            {"severity": "error", "title": "Question plan leaves required form values blank", "question_key": "name", "fields": ["Pt1Line1a"]},
            {"severity": "error", "title": "Text is cut off in a box", "fields": ["P1Line12_I94"]},
            {"severity": "error", "title": audit.PREDATES_TITLE, "question_key": "i94", "fields": ["P1Line12_I94"]},
        ])
        self.assertEqual([f.get("open_item") for f in findings], [None] * 5)


def old_g28_plan(edition: str = "09/17/18") -> dict[str, object]:
    """A G-28 plan written from an early, smaller version of its schema for the same edition of the
    form (fictional values); with another `edition`, a plan written for another edition."""
    complete = {item["key"]: item for item in complete_g28_questions(Checkbox1dAmNot="Y")}
    attorney = dict(complete["attorney_block"])
    attorney["field_values"] = {
        **attorney["field_values"],
        **complete["attorney_eligibility"]["field_values"],
        **complete["attorney_discipline"]["field_values"],
    }
    return {
        "kind": "g-28",
        "subject": "client",
        "question_schema": SCHEMA_G28_CLIENT,
        "schema_edition": edition,
        "fact_table_path": "form facts.json",
        "questions": [
            attorney,
            complete["representation_scope"],
            {**complete["client_identity"], "fact_ids": ["f-name"], "open_item": ""},
            {**complete["client_contact"], "status": "pending_client_input", "open_item": "q-phone"},
            {"key": "g28_signatures", "label": "Signatures", "status": "pending_signature", "field_values": {}},
            {"key": "client_numbers", "label": "Client A-Number", "status": "filled",
             "field_values": {"Pt3Line9_ANumber": "123456789"}, "visible_values": ["123456789"]},
        ],
    }


class MigrateTests(unittest.TestCase):
    """Item 52: a plan from an older schema moves onto the current skeleton, and the form it fills is unchanged."""

    def test_answers_move_by_key_and_box_and_the_mapping_is_unchanged(self) -> None:
        import form_question_schema as fqs

        plan = old_g28_plan()
        before = forms_workflow.flatten_filled_field_values(forms_workflow.plan_questions(plan))
        migrated, report = fqs.migrate_plan(plan)
        after = forms_workflow.flatten_filled_field_values(forms_workflow.plan_questions(migrated))
        self.assertEqual(after, before)
        by_key = {item["key"]: item for item in migrated["questions"]}
        # Boxes the schema moved to their own questions follow them, as filled answers.
        self.assertEqual(by_key["attorney_eligibility"]["status"], "filled")
        self.assertEqual(by_key["attorney_eligibility"]["field_values"]["Pt2Line1b_BarNumber"], "00000000")
        self.assertEqual(by_key["attorney_discipline"]["field_values"]["Checkbox1dAmNot"], "Y")
        self.assertIn("Moved here by migrate from attorney_block", by_key["attorney_discipline"]["notes"])
        # The client's A-Number now has a question of its own; its visible value goes with it.
        self.assertEqual(by_key["client_account_numbers"]["field_values"]["Pt3Line9_ANumber"], "123456789")
        self.assertEqual(by_key["client_account_numbers"]["visible_values"], ["123456789"])
        self.assertNotIn("123456789", [v for q in migrated["questions"] if q["key"] != "client_account_numbers"
                                       for v in q.get("visible_values", [])])
        # Statuses, facts and open items stay with their question.
        self.assertEqual(by_key["client_contact"]["status"], "pending_client_input")
        self.assertEqual(by_key["client_contact"]["open_item"], "q-phone")
        self.assertEqual(by_key["client_identity"]["fact_ids"], ["f-name"])
        # New questions are left missing and named; an obsolete empty one is kept, not lost.
        self.assertEqual(by_key["attorney_uscis_online_account"]["status"], "missing")
        self.assertIn("attorney_uscis_online_account", report["new"])
        self.assertIn("g28_signatures", report["kept_outside_schema"])
        self.assertEqual(migrated["schema_edition"], get_question_schema(SCHEMA_G28_CLIENT)["edition"])
        findings = audit.schema_findings(
            pdf_path=Path("/x/G-28.pdf"), kind="g-28", questions=migrated["questions"],
            manifest_entry={"question_schema": SCHEMA_G28_CLIENT, "schema_edition": migrated["schema_edition"]},
        )
        self.assertFalse([item for item in findings if item["title"] == audit.PREDATES_TITLE])

    def test_visible_values_follow_their_boxes(self) -> None:
        import form_question_schema as fqs

        plan = old_g28_plan()
        plan["questions"][0]["visible_values"] = ["Example", "00000000", "Example Law PLLC"]
        migrated, _report = fqs.migrate_plan(plan)
        by_key = {item["key"]: item for item in migrated["questions"]}
        self.assertEqual(by_key["attorney_block"]["visible_values"], ["Example"])
        self.assertEqual(sorted(by_key["attorney_eligibility"]["visible_values"]), ["00000000", "Example Law PLLC"])

    def test_a_written_answer_never_moves_into_a_question_left_off_the_form(self) -> None:
        import form_question_schema as fqs

        plan = old_g28_plan()
        # The old plan answered the client's phone under a filled question, while the schema's
        # client_contact question was still waiting on the client.
        plan["questions"].append(
            {"key": "phone_record", "label": "Phone", "status": "filled",
             "field_values": {"Line9_DaytimeTelephoneNumber": "5555550123"}}
        )
        plan["questions"][3]["field_values"] = {}
        before = forms_workflow.flatten_filled_field_values(forms_workflow.plan_questions(plan))
        migrated, report = fqs.migrate_plan(plan)
        after = forms_workflow.flatten_filled_field_values(forms_workflow.plan_questions(migrated))
        self.assertEqual(after["Line9_DaytimeTelephoneNumber"], "5555550123")
        self.assertEqual(after, before)
        self.assertIn("phone_record", report["kept_outside_schema"])

    def test_a_plan_for_another_edition_is_refused_unless_asked_and_then_every_answer_is_rechecked(self) -> None:
        import form_question_schema as fqs

        plan = old_g28_plan("05/23/18")
        with self.assertRaises(fqs.EditionMismatch) as caught:
            fqs.migrate_plan(plan)
        self.assertIn("written for the 05/23/18 edition of the G-28, and the schema is for the 09/17/18", str(caught.exception))
        migrated, report = fqs.migrate_plan(plan, across_editions=True)
        by_key = {item["key"]: item for item in migrated["questions"]}
        # Every answered question waits on a check against the new edition; open ones stay open.
        self.assertEqual(by_key["attorney_block"]["status"], "manual_review")
        self.assertEqual(by_key["attorney_block"]["status_before_migrate"], "filled")
        self.assertEqual(by_key["client_contact"]["status"], "pending_client_input")
        self.assertEqual(by_key["attorney_uscis_online_account"]["status"], "missing")  # new, nothing carried
        self.assertIn("attorney_block", report["to_review"])
        self.assertNotIn("client_contact", report["to_review"])
        self.assertEqual(forms_workflow.flatten_filled_field_values(forms_workflow.plan_questions(migrated)), {})
        self.assertEqual((migrated["migrated_from_edition"], migrated["schema_edition"]), ("05/23/18", "09/17/18"))
        lines = fqs.migrate_report_lines(report)
        self.assertTrue(lines[0].startswith("EDITION CHANGE 05/23/18 -> 09/17/18"), lines[0])
        findings = audit.schema_findings(
            pdf_path=Path("/x/G-28.pdf"), kind="g-28", questions=migrated["questions"],
            manifest_entry={"question_schema": SCHEMA_G28_CLIENT, "schema_edition": migrated["schema_edition"]},
        )
        # The audit holds the form until each is checked: manual_review is no final status.
        self.assertIn(("error", "attorney_block"), [(f["severity"], f.get("question_key")) for f in findings
                                                     if f["title"] == audit.INVALID_STATUS_TITLE])
        # The CLI refuses, exits 2 and writes nothing; --across-editions migrates.
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "G-28.plan.json"
            path.write_text(json.dumps(plan), encoding="utf-8")
            original = path.read_text(encoding="utf-8")
            code, err = run_quietly(fqs.main, ["migrate", str(path)])
            self.assertEqual((code, path.read_text(encoding="utf-8")), (2, original))
            self.assertIn("--across-editions", err)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(fqs.main(["migrate", str(path), "--across-editions"]), 0)
            self.assertIn("EDITION CHANGE 05/23/18 -> 09/17/18", out.getvalue().splitlines()[0])

    def test_the_report_names_only_real_status_problems(self) -> None:
        import form_question_schema as fqs

        plan = old_g28_plan()
        for item in plan["questions"]:
            if item["key"] == "client_identity":
                item["status"] = "missing"  # still to answer: not a problem
            if item["key"] == "representation_scope":
                item["status"] = "pending_signature"  # a final status this question doesn't take
        _migrated, report = fqs.migrate_plan(plan)
        self.assertEqual([item["key"] for item in report["status_not_allowed"]], ["representation_scope"])
        lines = fqs.migrate_report_lines(report)
        self.assertEqual(sum("no longer allowed" in line for line in lines), 1)

    def test_cli_keeps_the_old_plan_and_dry_run_writes_nothing(self) -> None:
        import form_question_schema as fqs

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "G-28.plan.json"
            path.write_text(json.dumps(old_g28_plan()), encoding="utf-8")
            original = path.read_text(encoding="utf-8")
            run_quietly(fqs.main, ["migrate", str(path), "--dry-run"])
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertFalse(path.with_name("G-28.plan.json.premigrate").exists())
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(fqs.main(["migrate", str(path)]), 0)
            self.assertIn("new questions, left missing for you to answer", out.getvalue())
            self.assertEqual(path.with_name("G-28.plan.json.premigrate").read_text(encoding="utf-8"), original)
            self.assertEqual(len(json.loads(path.read_text())["questions"]), len(get_question_schema(SCHEMA_G28_CLIENT)["required_questions"]) + 1)


class ProfileOnlineAccountTests(unittest.TestCase):
    """Item 42: an attorney with no USCIS online account answers the account questions by saying so once."""

    NO_ACCOUNT = {"attorney_name": "Jane Example", "has_uscis_online_account": "no"}

    def account_question(self, plan: dict) -> dict:
        return next(q for q in plan["questions"] if q["key"] == "attorney_uscis_online_account")

    def test_skeleton_starts_the_question_not_applicable(self) -> None:
        settled = self.account_question(skeleton_plan(SCHEMA_G28_CLIENT, profile=self.NO_ACCOUNT))
        self.assertEqual(settled["status"], "not_applicable")
        self.assertIn("no USCIS online account", settled["notes"])
        for profile in (None, {}, {"has_uscis_online_account": "yes"}):
            self.assertEqual(self.account_question(skeleton_plan(SCHEMA_G28_CLIENT, profile=profile))["status"], "missing")

    def test_audit_needs_no_open_item_for_it(self) -> None:
        questions = complete_g28_questions()
        for item in questions:
            if item["key"] == "attorney_uscis_online_account":
                item["status"] = "missing"
        entry = {"question_schema": SCHEMA_G28_CLIENT, "questions": questions}
        with TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "G-28.pdf"
            write_blank_pdf(pdf)
            without = audit.plan_findings(pdf_path=pdf, kind="g-28", manifest_entry=entry)
            settled = audit.plan_findings(pdf_path=pdf, kind="g-28", manifest_entry=entry, profile=self.NO_ACCOUNT)
        self.assertTrue([f for f in without if f.get("question_key") == "attorney_uscis_online_account"])
        self.assertEqual([f for f in settled if f.get("question_key") == "attorney_uscis_online_account"], [])
        # An account number the plan did fill is never overridden.
        filled = {**entry, "questions": [dict(q, field_values={"Pt1Line1_USCISOnlineAcctNumber": "000011112222"})
                                         if q["key"] == "attorney_uscis_online_account" else q for q in questions]}
        self.assertFalse(audit.settled_by_profile(filled["questions"][0], SCHEMA_G28_CLIENT, self.NO_ACCOUNT))

    def test_migrate_and_build_read_the_profile(self) -> None:
        import form_question_schema as fqs

        migrated, report = fqs.migrate_plan(old_g28_plan(), profile=self.NO_ACCOUNT)
        self.assertEqual(self.account_question(migrated)["status"], "not_applicable")
        self.assertNotIn("attorney_uscis_online_account", report["new"])
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".senior-associate").mkdir()
            (root / ".senior-associate" / "attorney-profile.json").write_text(json.dumps(self.NO_ACCOUNT))
            (root / "Matter").mkdir()
            self.assertEqual(build_forms.Layout(root / "Matter", "main").profile["has_uscis_online_account"], "no")
            other = root / "elsewhere.json"
            other.write_text(json.dumps({"has_uscis_online_account": "yes"}))
            self.assertEqual(build_forms.Layout(root / "Matter", "main", profile_path=other).profile["has_uscis_online_account"], "yes")
            self.assertEqual(build_forms.Layout(root / "Nowhere" / "Matter", "main").profile, {})


class SafeAddressTests(unittest.TestCase):
    """Item 28: in a protected matter every client mailing-address box holds the safe address."""

    SAFE = {"in_care_of": "Example Law PLLC", "street": "100 Example Street", "unit": "STE", "number": "200",
            "city": "Springfield", "state": "IL", "zip": "62701", "country": "USA", "source": "profile"}
    I765_SAFE = {
        "Line4a_InCareofName": "Example Law PLLC", "Line4b_StreetNumberName": "100 Example St.",
        "Pt2Line5_Unit": " STE ", "Pt2Line5_AptSteFlrNumber": "200", "Pt2Line5_CityOrTown": "Springfield",
        "Pt2Line5_State": "IL", "Pt2Line5_ZipCode": "62701",
    }

    def findings(self, kind: str, values: dict, *, safe: dict | None = None, profile: dict | None = None,
                 protected: bool = True) -> list[dict]:
        entry = {"safe_mailing_address": safe} if safe else {}
        return audit.safe_address_findings(kind=kind, pdf_path=Path(f"/x/{kind}.pdf"), values=values,
                                           manifest_entry=entry, profile=profile, protected=protected)

    def test_every_box_named_is_on_its_form_and_in_its_question(self) -> None:
        import safe_address

        for kind, groups in safe_address.MAILING_GROUPS.items():
            schema = next(s for s in QUESTION_SCHEMAS.values() if s["kind"] == kind and s.get("field_list"))
            known = load_field_list(schema["field_list"])["fields"]
            for group in groups:
                boxes = [group.mailing] + ([group.same_as_physical[2]] if group.same_as_physical else [])
                for address in boxes:
                    declared = schema["required_questions"][address.question]["required_fields"]
                    for field in address.boxes().values():
                        with self.subTest(kind=kind, field=field):
                            self.assertIn(field.split("[")[0], known)
                            self.assertIn(field, declared)

    def test_the_safe_address_passes_and_another_does_not(self) -> None:
        self.assertEqual(self.findings("i-765", self.I765_SAFE, safe=self.SAFE), [])
        home = {**self.I765_SAFE, "Line4b_StreetNumberName": "9 Home Road", "Pt2Line5_ZipCode": "62704"}
        wrong = self.findings("i-765", home, safe=self.SAFE)
        self.assertEqual(titles(wrong), ["Protected client's mailing address is not the safe address"])
        self.assertEqual(wrong[0]["fields"], ["Line4b_StreetNumberName", "Pt2Line5_ZipCode"])
        self.assertFalse(audit.ABSENCE_TITLE_RE.search(wrong[0]["title"]))
        # Not protected: nothing to check.
        self.assertEqual(self.findings("i-765", home, safe=self.SAFE, protected=False), [])
        # The petitioner's and sponsor's forms carry no protected client's mailing address.
        self.assertEqual(self.findings("i-864", {"P4_Line2b_StreetNumberName": "9 Home Road"}, safe=self.SAFE), [])

    def test_without_a_record_the_profile_address_is_the_safe_address(self) -> None:
        profile = {"mailing_address": "Example Law PLLC, 100 Example Street, Suite 200, Springfield, IL 62701"}
        self.assertEqual(self.findings("i-765", self.I765_SAFE, profile=profile), [])
        home = {**self.I765_SAFE, "Line4b_StreetNumberName": "9 Home Road"}
        self.assertEqual(self.findings("i-765", home, profile=profile)[0]["fields"], ["Line4b_StreetNumberName"])
        unchecked = self.findings("i-765", home)
        self.assertEqual(titles(unchecked), ["Protected client's mailing address can't be checked: no safe address is recorded"])
        self.assertEqual(self.findings("i-765", {}), [])  # left blank for its open item

    def test_a_physical_address_given_as_the_mailing_address_must_be_the_safe_address(self) -> None:
        values = {"Pt1Line18_YN": "Y", "Pt1Line18_StreetNumberName": "9 Home Road", "Pt1Line18_CityOrTown": "Springfield",
                  "Pt1Line18_State": "IL", "Pt1Line18_ZipCode": "62704"}
        wrong = self.findings("i-485", values, safe=self.SAFE)
        self.assertEqual(wrong[0]["where"], "Part 1, item 18 (physical address, given as the mailing address)")
        separate = {**values, "Pt1Line18_YN": "N", "Pt1Line18_CurrentInCareOfName": "Example Law PLLC",
                    "Pt1Line18_CurrentStreetNumberName": "100 Example Street", "Pt1Line18_CurrentUnit": " STE ",
                    "Pt1Line18_CurrentAptSteFlrNumber": "200", "Pt1Line18_CurrentCityOrTown": "Springfield",
                    "Pt1Line18_CurrentState": "IL", "Pt1Line18_CurrentZipCode": "62701"}
        self.assertEqual(self.findings("i-485", separate, safe=self.SAFE), [])

    def test_the_protected_setting_and_the_record_reach_the_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            self.assertFalse(audit.matter_is_protected(matter))
            meta = matter / "output" / "working" / "workflow" / "matter-meta.json"
            meta.parent.mkdir(parents=True)
            meta.write_text(json.dumps({"protected": True, "protected_reason": "attorney"}))
            self.assertTrue(audit.matter_is_protected(matter))
            plan = {**skeleton_plan(SCHEMA_G28_CLIENT), "safe_mailing_address": self.SAFE}
            _summary, entry = forms_workflow.apply_plan(plan, mapping_out=matter / "m.json", filing_copy=matter / "G-28.pdf")
        self.assertEqual(entry["safe_mailing_address"]["street"], "100 Example Street")
        self.assertFalse(audit.matter_is_protected(None))


class VisibleValueBoxTests(unittest.TestCase):
    """A visible value counts only inside its question's own boxes: words printed on the form don't."""

    WORDS = [
        (1, 50, 100, 80, 110, "United"), (1, 82, 100, 110, 110, "States"),  # printed label
        (1, 300, 200, 330, 210, "Sample"), (1, 332, 200, 360, 210, "Town"),  # inside the city box
    ]
    BOXES = {("City", 0): [(1, 295, 195, 450, 215)], ("Country", 0): [(1, 295, 245, 450, 265)]}

    def test_words_are_read_from_the_boxes(self) -> None:
        self.assertEqual(forms_workflow.text_in_boxes(self.WORDS, self.BOXES[("City", 0)]), "Sample Town")
        self.assertEqual(forms_workflow.text_in_boxes(self.WORDS, self.BOXES[("Country", 0)]), "")
        question_ = {"field_values": {"City": "Sample Town"}}
        self.assertEqual(forms_workflow.question_box_text(question_, self.WORDS, self.BOXES), "Sample Town")
        self.assertIsNone(forms_workflow.question_box_text(question_, None, self.BOXES))
        self.assertIsNone(forms_workflow.question_box_text({"field_values": {"Other": "x"}}, self.WORDS, self.BOXES))

    def test_a_value_printed_on_the_form_is_not_an_answer(self) -> None:
        entry = {
            "questions": [
                question(key="country", label="Country", status=STATUS_FILLED,
                         field_values={"Country": "United States"}, visible_values=["United States"]),
                question(key="city", label="City", status=STATUS_FILLED,
                         field_values={"City": "Sample Town"}, visible_values=["Sample Town"]),
            ]
        }
        page_text = "United States ... Sample Town"
        with (
            patch.object(audit, "extract_pdf_text", return_value=page_text),
            patch.object(audit, "pdf_words", return_value=self.WORDS),
            patch.object(audit, "widget_boxes", return_value=self.BOXES),
        ):
            per_box = audit.plan_findings(pdf_path=Path("/x/f.pdf"), kind="x-1", manifest_entry=entry,
                                          widget_pdf=Path("/x/source.pdf"))
            page_only = audit.plan_findings(pdf_path=Path("/x/f.pdf"), kind="x-1", manifest_entry=entry)
        shown = [f for f in per_box if f["title"] == "Visible filing copy does not show a filled question value"]
        self.assertEqual([(f["question_key"], f["values"]) for f in shown], [("country", ["United States"])])
        # Without word positions the old page-text check is all there is.
        self.assertEqual([f for f in page_only if f["title"].startswith("Visible filing copy")], [])


class SchemaDeclarationTests(unittest.TestCase):
    """A plan must name the schema its form has, for the edition the schema was built on."""

    def test_a_plan_without_a_schema_is_an_error_when_the_form_has_one(self) -> None:
        findings = audit.schema_findings(
            pdf_path=Path("/x/G-28.pdf"), kind="g-28", questions=complete_g28_questions(), manifest_entry={}
        )
        self.assertEqual([item["severity"] for item in findings], ["error"])
        self.assertEqual(findings[0]["title"], "Question plan names no schema, but this form has one")
        self.assertIn(SCHEMA_G28_CLIENT, findings[0]["schemas"])
        other = audit.schema_findings(pdf_path=Path("/x/X.pdf"), kind="x-1", questions=[], manifest_entry={})
        self.assertEqual([item["severity"] for item in other], ["warning"])

    def test_the_plan_edition_must_match_the_schema(self) -> None:
        entry = {"question_schema": SCHEMA_G28_CLIENT, "schema_edition": "05/23/18"}
        findings = audit.schema_findings(
            pdf_path=Path("/x/G-28.pdf"), kind="g-28", questions=complete_g28_questions(), manifest_entry=entry
        )
        self.assertEqual(
            titles(findings), ["Question plan was written for the 05/23/18 edition; the schema is for 09/17/18"]
        )
        entry["schema_edition"] = "09/17/18"
        self.assertEqual(
            audit.schema_findings(pdf_path=Path("/x/G-28.pdf"), kind="g-28", questions=complete_g28_questions(), manifest_entry=entry),
            [],
        )

    def test_the_manifest_records_the_plan_edition(self) -> None:
        with TemporaryDirectory() as tmp:
            plan = skeleton_plan(SCHEMA_G28_CLIENT)
            _summary, entry = forms_workflow.apply_plan(
                plan, mapping_out=Path(tmp) / "m.json", filing_copy=Path(tmp) / "G-28.pdf"
            )
        self.assertEqual(entry["schema_edition"], "09/17/18")


class PartiallyFilledTests(unittest.TestCase):
    """A partially filled question writes its known answers and stays open on its blank required boxes."""

    STREET = G28_ANSWERS["Line12a_StreetNumberName"]

    @staticmethod
    def questions(*, city: str = "", open_item: str = "q-city") -> list[dict[str, object]]:
        """The complete G-28 plan with the client's mailing address partly known."""
        result = []
        for item in complete_g28_questions():
            if item["key"] == "client_mailing_address":
                item = question(
                    key=item["key"],
                    label=item["label"],
                    status=STATUS_PARTIALLY_FILLED,
                    field_values={**item["field_values"], "Line12c_CityOrTown": city},
                    visible_values=[PartiallyFilledTests.STREET],
                    open_item=open_item,
                )
            result.append(item)
        return result

    def findings(self, questions: list[dict[str, object]], *, text: str = "") -> list[dict[str, object]]:
        entry = {"question_schema": SCHEMA_G28_CLIENT, "questions": questions}
        with TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "g28.pdf"
            write_blank_pdf(pdf_path)
            with patch.object(audit, "extract_pdf_text", return_value=text):
                findings = audit.plan_findings(pdf_path=pdf_path, kind="g-28", manifest_entry=entry)
        audit.tie_open_items(findings, entry)
        return [finding for finding in findings if finding.get("question_key") == "client_mailing_address"]

    def test_known_answers_are_written_and_blank_ones_are_not(self) -> None:
        mapping = forms_workflow.flatten_filled_field_values(self.questions())
        self.assertEqual(mapping["Line12a_StreetNumberName"], self.STREET)
        self.assertEqual(mapping["Line12h_Country"], "USA")
        self.assertNotIn("Line12c_CityOrTown", mapping)
        pending = [dict(item, status="pending_client_input") for item in self.questions()]
        self.assertNotIn("Line12a_StreetNumberName", forms_workflow.flatten_filled_field_values(pending))

    def test_question_stays_open_on_its_blank_required_boxes_and_is_tied(self) -> None:
        findings = self.findings(self.questions(), text=self.STREET)
        by_title = {finding["title"]: finding for finding in findings}
        self.assertEqual(
            set(by_title),
            {
                "Part 3, Items 13.a-13.h: Client's mailing address is partly filled; its blank boxes are still open",
                audit.INVALID_STATUS_TITLE,  # open until resolved, like a pending question
            },
        )
        self.assertEqual(by_title[audit.INVALID_STATUS_TITLE]["status"], STATUS_PARTIALLY_FILLED)
        partly = by_title["Part 3, Items 13.a-13.h: Client's mailing address is partly filled; its blank boxes are still open"]
        self.assertEqual(partly["fields"], ["Line12c_CityOrTown"])
        self.assertEqual([finding.get("open_item") for finding in findings], ["q-city", "q-city"])

    def test_printed_answers_must_show_on_the_filing_copy(self) -> None:
        titles = [finding["title"] for finding in self.findings(self.questions(), text="Example Law PLLC")]
        self.assertIn("Visible filing copy does not show a filled question value", titles)

    def test_required_boxes_filled_leaves_the_other_blank_boxes_open(self) -> None:
        findings = self.findings(self.questions(city="Springfield"), text=self.STREET)
        partly = next(finding for finding in findings if "partly filled" in finding["title"])
        self.assertEqual(
            partly["fields"],
            ["Line12b_Unit", "Line12b_AptSteFlrNumber", "Line12f_Province", "Line12g_PostalCode"],
        )

    def test_nothing_blank_means_it_should_be_filled(self) -> None:
        title = "Question plan marks a section partially filled but leaves no box blank"
        questions = [
            dict(item, status=STATUS_PARTIALLY_FILLED, open_item="q-contact") if item["key"] == "client_contact" else item
            for item in complete_g28_questions()
        ]
        entry = {"question_schema": SCHEMA_G28_CLIENT, "questions": questions}
        with TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "g28.pdf"
            write_blank_pdf(pdf_path)
            findings = audit.schema_findings(pdf_path=pdf_path, kind="g-28", questions=questions, manifest_entry=entry)
        audit.tie_open_items(findings, entry)
        flagged = [finding for finding in findings if finding["title"] == title]
        self.assertEqual([finding["question_key"] for finding in flagged], ["client_contact"])
        self.assertNotIn("open_item", flagged[0])  # a mistake to fix, never a deliberate gap

    def test_only_its_blank_boxes_tie_an_absence_error(self) -> None:
        entry = {"questions": self.questions()}
        findings = [
            {"severity": "error", "title": "Missing mailing-address fields", "fields": ["Line12c_CityOrTown"]},
            {"severity": "error", "title": "Missing mailing-address fields", "fields": ["Line12a_StreetNumberName"]},
        ]
        audit.tie_open_items(findings, entry)
        self.assertEqual(findings[0]["open_item"], "q-city")
        self.assertNotIn("open_item", findings[1])

    def test_status_line_counts_partial_questions(self) -> None:
        self.assertEqual(forms_workflow.status_line({"filled": 3, STATUS_PARTIALLY_FILLED: 2}), "5 q: 3 filled, 2 partial")


class ShortOutputTests(unittest.TestCase):
    """Every forms tool prints a short summary by default; --full prints everything."""

    def test_dump_fields_caps_its_lines(self) -> None:
        with TemporaryDirectory() as tmpdir:
            blank = Path(tmpdir) / "blank.pdf"
            write_marriage_place_form(blank)
            out, err = io.StringIO(), io.StringIO()
            with patch.object(xfa_tools, "DUMP_LINE_LIMIT", 2), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                xfa_tools.list_fields(blank, None, True, Path(tmpdir) / "fields.json")
            full = io.StringIO()
            with contextlib.redirect_stdout(full), contextlib.redirect_stderr(io.StringIO()):
                xfa_tools.list_fields(blank, None, True, None, True, True)
        self.assertEqual(len(out.getvalue().splitlines()), 2)
        self.assertIn("4 more of 6 lines not shown", err.getvalue())
        self.assertIn("fields.json", err.getvalue())
        self.assertEqual(len(full.getvalue().splitlines()), 6)

    def test_fill_notes_are_one_capped_line_each(self) -> None:
        result = xfa_tools.FillResult(
            fields={},
            xfa_only=[f"Hidden{n}" for n in range(30)],
            normalized={f"Box{n}": " Y " for n in range(20)},
            shared=[],
            defects=[],
            rebound=[f"Name{n}" for n in range(33)],
        )
        short = xfa_tools.fill_messages(result)
        full = xfa_tools.fill_messages(result, full=True)
        self.assertEqual(len(short), 3)
        self.assertTrue(all(len(line) < 400 for line in short))
        self.assertIn("Hidden5, +24 more", short[1])
        self.assertIn("20 checkbox value(s)", short[0])
        self.assertEqual(len(full), 22)  # one line per normalized box, then the two lists in full

    def test_verify_lines_are_capped(self) -> None:
        mismatches = {"xfa": {f"F{n}": {"expected": "A", "stored": ""} for n in range(8)}, "visible": {}}
        lines = xfa_tools.verify_lines(mismatches)
        self.assertEqual(len(lines), 6)
        self.assertEqual(lines[-1].strip(), "+3 more")
        self.assertIn("xfa: F0: expected 'A', stored ''", lines[0])

    def test_audit_summary_lists_counts_and_untied_errors(self) -> None:
        payload = {
            "result_count": 1,
            "error_count": 5,
            "warning_count": 1,
            "tied_error_count": 1,
            "results": [{"form": "i-485", "file": "/m/I-485.pdf"}],
            "findings": [
                {"severity": "error", "file": "/m/I-485.pdf", "title": "A is missing", "question_key": "a", "open_item": "q-a"},
                *[
                    {"severity": "error", "file": "/m/I-485.pdf", "title": f"Missing group {n}", "fields": ["X", "Y", "Z", "W"]}
                    for n in range(4)
                ],
                {"severity": "warning", "file": "/m/I-485.pdf", "title": "Signature fields are still blank"},
            ],
        }
        lines = audit.summary_lines(payload, Path("/m/audit.json"))
        self.assertEqual(lines[0], "audit: 1 form(s), 5 error(s) (1 tied to open items), 1 warning(s) -> /m/audit.json")
        self.assertEqual(lines[1], "  i-485 I-485.pdf: 5 error(s) (1 tied), 1 warning(s)")
        self.assertEqual(lines[2], "    untied: Missing group 0 [X, Y, Z, +1]")
        self.assertEqual(lines[-1], "    +1 more untied error(s) in the JSON")

    def test_extract_values_both_marks_differences(self) -> None:
        with TemporaryDirectory() as tmpdir:
            blank, filled = Path(tmpdir) / "blank.pdf", Path(tmpdir) / "filled.pdf"
            write_marriage_place_form(blank)
            run_quietly(xfa_tools.write_filled_pdf, blank, filled, {"Place[0]": "Austin", "Unit": "STE"})
            args = argparse.Namespace(
                pdf=filled, field_names=["Note"], prefix="Place", both=True, visible=False, json=False, full=False
            )
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                xfa_tools.extract_command(args)
        self.assertEqual(out.getvalue().splitlines(), ["Note\t", "Place[0]\tAustin", "Place[1]\t"])
        self.assertIn("3 names, 0 differ", err.getvalue())

    def test_summary_fits_the_line_budget_with_many_problems(self) -> None:
        forms = [
            {
                "name": f"Form {n}", "kind": "i-485", "schema": "", "status_counts": {"filled": 3, "missing": 2},
                "reason": "new", "stale": "", "error": "", "verify": "failed", "verify_failures": 2,
                "verify_lines": ["  xfa: A: expected 'x', stored ''"], "field_check": {"unknown_fields": ["Bad1", "Bad2"]},
                "warnings": ["warning: long value"],
                "audit": {"coverage": "audit", "errors": 6, "tied": 0, "warnings": 1, "open_items": [],
                          "untied": [f"Missing group {i}" for i in range(6)]},
            }
            for n in range(8)
        ]
        report = {"mode": "build", "matter": "/m", "slug": "main", "forms": forms,
                  "audit": {"errors": 48, "tied": 0, "warnings": 8}, "tied_ids": [], "ledger_found": True,
                  "not_in_ledger": [], "removed": [], "seconds": 1.0}
        lines = build_forms.summary_lines(report)
        self.assertLessEqual(len(lines), build_forms.SUMMARY_LINES)
        self.assertTrue(any("more line(s) in the build log" in line for line in lines))

    def test_skeleton_can_be_written_to_a_file_and_is_not_overwritten(self) -> None:
        import form_question_schema

        with TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "plans" / "G-28.plan.json"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                first = form_question_schema.main(["skeleton", SCHEMA_G28_CLIENT, "--out", str(out)])
                out.write_text("{\"kind\": \"g-28\", \"questions\": []}")
                second = form_question_schema.main(["skeleton", SCHEMA_G28_CLIENT, "--out", str(out)])
                kept = out.read_text()
        self.assertEqual((first, second), (0, 1))
        self.assertIn('"questions": []', kept)


if __name__ == "__main__":
    unittest.main()

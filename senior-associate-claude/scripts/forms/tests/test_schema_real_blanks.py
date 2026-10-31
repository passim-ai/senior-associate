#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Fill real USCIS blanks (the editions the schemas were built against) and check what the
tools say about them. All values are fictional.

    uv run --script tests/test_schema_real_blanks.py

The blanks come from tests/official_blanks.py: a local cache, or uscis.gov the first time. Each
test skips, saying why, when its blank can't be had (offline, or uscis.gov now serves another
edition, which editions.py reports in a real matter).
"""
from __future__ import annotations

import contextlib
import io
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit_prepared_forms as audit  # noqa: E402
import editions  # noqa: E402
import formats  # noqa: E402
import forms_workflow  # noqa: E402
from forms_workflow import question  # noqa: E402
from form_question_schema import QUESTION_SCHEMAS  # noqa: E402
from official_blanks import fictional_plan, fill_and_check, official_blank, why_missing  # noqa: E402
import xfa_tools  # noqa: E402

HAVE_GS = bool(shutil.which("gs") or shutil.which("gswin64c"))


def fill(blank: Path, out: Path, mapping: dict[str, str]) -> xfa_tools.FillResult:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return xfa_tools.write_filled_pdf(blank, out, mapping)


class RealBlankCase:
    """Shared by the form classes below (a mixin, so it doesn't run on its own)."""

    FORM = ""

    @classmethod
    def setUpClass(cls) -> None:
        cls.blank = official_blank(cls.FORM)
        if cls.blank is None:
            raise unittest.SkipTest(why_missing(cls.FORM))


NA = "not_applicable"
# A complete fictional plan for each form, made to hang together where the form's rules need it:
# questions left out, answers set, and boxes left blank (one box of each yes/no pair, one route).
COMPLETE_PLANS: dict[str, dict] = {
    "i129f_fiance_petition": {},
    "i140_worker_petition": {
        "statuses": {"native_alphabet": NA, "amend_or_schedule_a": NA},
        "blank": lambda name: name.endswith(("_No", "_No1", "CheckboxNo"))
        or name in {"Line1b_Status", "Line1b_Self", "Line1c_Other", "Line1c_Explain", "Line5_Hours"},
    },
    # Section A grounds only.
    "i601_inadmissibility_waiver": {"statuses": dict.fromkeys(
        ["t_or_sij_grounds", "tps_health_grounds", "tps_criminal_grounds", "tps_fraud_or_false_claim",
         "tps_smuggling_or_civil_penalty", "tps_other_grounds"], NA)},
    # An eligible applicant: proceedings administratively closed (28.a), an approved I-212 (29.b), a
    # reinstatement notice but no final decision (30.b No), no voluntary departure (31 No); one basis
    # (1.b) and one relationship box in each of Part 4 items 2 and 5.
    "i601a_provisional_waiver": {
        "answers": {"Pt1Checkbox28": "A", "Pt1Checkbox30b_Checkbox": "N", "Pt1Checkbox30_Checkbox": "N"},
        "blank": lambda name: name.startswith(("Pt3Line4_Option", "Pt4Line2", "Pt4Line5"))
        and name not in {"Pt3Line4_Option2", "Pt4Line2a_Checkbox", "Pt4Line5c_Checkbox"},
    },
    "i612_foreign_residence_waiver": {},
    "i693_applicant_part": {},
    "i864a_household_member": {"answers": {"P4_Line3_Assets": "100", "P4_Line4_Assets": "200",
                                           "P4_Line5_Assets": "300", "P4_Line6_TotalAssets": "600"}},
    # An employer's NIW I-140 filed with the I-907 by the petitioner (8.A): no receipt number yet; the
    # preparer is an attorney whose representation extends (7.B).
    "i907_premium_processing": {"answers": {
        "P2_Line1_FormNumberof": "I-140", "P2_Line2_ReceiptNumberof": "", "P2_Line2_ClassorEligRequested": "E21 NIW",
        "P5_Line7a_Checkbox": "", "P5_Line7b_notextends": "", "Part1_Line5_MailingAddress_Country": "United States"}},
}


class EveryBlankTests(unittest.TestCase):
    """Every official blank a schema was built on."""

    def test_each_blank_is_the_edition_its_schemas_were_built_for(self) -> None:
        for name, schema in QUESTION_SCHEMAS.items():
            kind = schema["kind"]
            blank = official_blank(kind)
            with self.subTest(schema=name):
                if blank is None:
                    self.skipTest(why_missing(kind))
                check = editions.check_blank(kind, blank)
                self.assertEqual((check["status"], check["file_edition"]), (editions.MATCH, schema["edition"]))
                self.assertEqual(editions.footer_edition(blank), (kind.upper(), schema["edition"]))

    def test_a_complete_plan_fills_the_official_blank_and_clears_the_audit(self) -> None:
        for name, adjust in COMPLETE_PLANS.items():
            kind = QUESTION_SCHEMAS[name]["kind"]
            blank = official_blank(kind)
            with self.subTest(schema=name):
                if blank is None:
                    self.skipTest(why_missing(kind))
                plan = fictional_plan(name, blank, statuses=adjust.get("statuses"))
                for question in plan["questions"]:
                    for box in question["field_values"]:
                        if box in adjust.get("answers", {}):
                            question["field_values"][box] = adjust["answers"][box]
                        elif adjust.get("blank", lambda _box: False)(box):
                            question["field_values"][box] = ""
                findings = audit.schema_findings(pdf_path=Path("/x.pdf"), kind=kind, questions=plan["questions"],
                                                 manifest_entry={"question_schema": name})
                self.assertEqual(findings, [])
                values = fill_and_check(self, kind, blank, plan)
                self.assertEqual([f for f in audit.audit_form(kind, blank, values) if f["severity"] == "error"], [])


class RealI485Tests(RealBlankCase, unittest.TestCase):
    FORM = "i-485"
    MAPPING = {
        "Pt1Line1_FamilyName": "Sample",
        "Pt1Line1_GivenName": "Alex",
        "Pt1Line3_DOB": "01/02/1990",
        "Pt1Line4_AlienNumber": "012345678",
        "Pt1Line6_CB_Sex": "M",
        "Pt1Line18_StreetNumberName": "100 Example Street",
        "Pt1Line18_CityOrTown": "Springfield",
        "Pt1Line18_State": "IL",
        "Pt1Line18_ZipCode": "62701",
    }

    def test_formats_come_from_the_form(self) -> None:
        box = formats.box_formats(self.blank)
        self.assertEqual(box["Pt1Line3_DOB"], formats.DATE)  # a dateTimeEdit in the XFA template
        self.assertEqual(box["Pt1Line18_ZipCode"], formats.ZIP)
        self.assertEqual(box["Pt1Line4_AlienNumber"], formats.A_NUMBER)
        self.assertEqual(box["Pt1Line18_State"], formats.STATE)  # a drop-down of state codes
        self.assertEqual(box["P1Line12_I94"], formats.I94)

    def test_fill_verify_and_box_rules(self) -> None:
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "I-485 source.pdf"
            result = fill(self.blank, source, self.MAPPING)
            mismatches = xfa_tools.verify_output(source, result.fields, check_visible=True)
            values = audit.merged_values(source)
            clean = audit.box_rule_findings(kind="i-485", pdf_path=source, widget_pdf=source, values=values)
            wrong = fill(self.blank, Path(tmp) / "wrong.pdf", {**self.MAPPING, "Pt1Line4_AlienNumber": "A-12345678",
                                                                "Pt1Line3_DOB": "1990-01-02"})
            bad = audit.box_rule_findings(
                kind="i-485", pdf_path=source, widget_pdf=Path(tmp) / "wrong.pdf",
                values=audit.merged_values(Path(tmp) / "wrong.pdf"),
            )
            dump = xfa_tools.field_dump(self.blank)
        self.assertEqual(mismatches, {"xfa": {}, "visible": {}})
        self.assertTrue(any("Pt1Line4_AlienNumber" in line for line in wrong.length_warnings))
        self.assertEqual(clean, [])
        by_title = {item["title"]: item["fields"] for item in bad}
        self.assertEqual(by_title["An answer is longer than its box allows"], ["Pt1Line4_AlienNumber"])
        self.assertIn("Pt1Line4_AlienNumber", by_title["A-Number box holds an answer in the wrong format"])
        self.assertEqual(by_title["Date box holds an answer in the wrong format"], ["Pt1Line3_DOB"])
        # The drop-down check reads the choices from the real field dump.
        problems = forms_workflow.mapping_field_check({"Pt1Line18_State": "Illinois"}, dump)
        self.assertTrue(problems["not_a_choice"])

    @unittest.skipUnless(HAVE_GS, "rendering a filing copy needs Ghostscript")
    def test_visible_answers_are_read_from_their_own_boxes_on_the_filing_copy(self) -> None:
        if not shutil.which("pdftotext"):
            self.skipTest("word positions need pdftotext (poppler)")
        with TemporaryDirectory() as tmp:
            source, filing = Path(tmp) / "I-485 source.pdf", Path(tmp) / "I-485.pdf"
            fill(self.blank, source, self.MAPPING)
            with contextlib.redirect_stderr(io.StringIO()):
                xfa_tools.render_filing_copy(source, filing)
            entry = {
                "questions": [
                    question(key="name", label="Name", status="filled",
                             field_values={"Pt1Line1_FamilyName": "Sample", "Pt1Line1_GivenName": "Alex"},
                             visible_values=["Sample", "Alex"]),
                    question(key="address", label="Address", status="filled",
                             field_values={"Pt1Line18_StreetNumberName": "100 Example Street", "Pt1Line18_ZipCode": "62701"},
                             visible_values=["100 Example Street", "62701"]),
                    # Words printed on the form never count as an answer.
                    question(key="printed", label="Printed label", status="filled",
                             field_values={"Pt1Line3_DOB": "01/02/1990"}, visible_values=["Date of Birth"]),
                ]
            }
            findings = audit.plan_findings(pdf_path=filing, kind="i-485", manifest_entry=entry, widget_pdf=source)
        shown = [f for f in findings if f["title"] == "Visible filing copy does not show a filled question value"]
        self.assertEqual([(f["question_key"], f["values"]) for f in shown], [("printed", ["Date of Birth"])])


class RealI130Tests(RealBlankCase, unittest.TestCase):
    FORM = "i-130"

    def test_fill_and_verify_a_repeated_and_a_checkbox_answer(self) -> None:
        mapping = {
            "Pt1Line1_Spouse": "Y",
            "Pt2Line4a_FamilyName": "Sample",
            "Pt2Line4b_GivenName": "Jordan",
            "Pt2Line1_AlienNumber": "123456789",
            "Pt2Line8_DateofBirth": "03/04/1985",
            "Pt2Line10_State": "TX",
            "Pt2Line10_ZipCode": "75001",
            # These boxes carry the ZIP Code's five-digit picture but take the number of marriages.
            "Pt2Line16_NumberofMarriages": "1",
            "Pt4Line17_NumberofMarriages": "2",
        }
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "I-130 source.pdf"
            result = fill(self.blank, source, mapping)
            mismatches = xfa_tools.verify_output(source, result.fields, check_visible=True)
            stored = xfa_tools.extract_values(source, ["Pt2Line4a_FamilyName[1]", "Pt2Line1_AlienNumber[1]"])
            findings = audit.box_rule_findings(
                kind="i-130", pdf_path=source, widget_pdf=source, values=audit.merged_values(source)
            )
        self.assertEqual(mismatches, {"xfa": {}, "visible": {}})
        # Global fields repeat on the Additional Information page.
        self.assertEqual(stored, {"Pt2Line4a_FamilyName[1]": "Sample", "Pt2Line1_AlienNumber[1]": "123456789"})
        self.assertEqual(findings, [])

    def test_the_number_of_marriages_is_a_number_not_a_zip_code(self) -> None:
        box = formats.box_formats(self.blank)
        self.assertEqual(box["Pt2Line16_NumberofMarriages"], formats.NUMBER)
        self.assertEqual(box["Pt4Line17_NumberofMarriages"], formats.NUMBER)
        self.assertEqual(box["Pt2Line10_ZipCode"], formats.ZIP)


class RealN400Tests(unittest.TestCase):
    """The N-400's residence and employment tables have one "ZIP Code/Postal Code" column."""

    ROWS = {
        "P4_Line3_PhysicalAddress1": "100 Example Street", "P4_Line3_CityTown1": "Springfield",
        "P4_Line3_State1": "IL", "P4_Line3_ZipCode1": "62701", "P4_Line3_Country1": "USA",
        "P4_Line3_PhysicalAddress2": "1 Sample Road", "P4_Line3_CityTown2": "London",
        "P4_Line3_ZipCode2": "SW1A 1AA", "P4_Line3_Country2": "United Kingdom",
        "P7_EmployerName1": "Example Co", "P7_City1": "Mumbai", "P7_ZipCode1": "400001", "P7_Country1": "India",
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.blank = official_blank("n-400")
        if cls.blank is None:
            raise unittest.SkipTest(why_missing("n-400"))

    def findings(self, mapping: dict[str, str]) -> list[dict[str, object]]:
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "N-400 source.pdf"
            fill(self.blank, source, mapping)
            return audit.box_rule_findings(kind="n-400", pdf_path=source, widget_pdf=source,
                                           values=audit.merged_values(source))

    def test_the_column_takes_a_zip_code_at_home_and_a_postal_code_abroad(self) -> None:
        box = formats.box_formats(self.blank)
        for name in ("P4_Line3_ZipCode1", "P4_Line3_ZipCode3", "P7_ZipCode2"):
            self.assertEqual(box[name], formats.ZIP_OR_POSTAL, name)
        self.assertEqual(box["P4_Line1_ZipCode"], formats.ZIP)  # the mailing address has its own postal code box
        self.assertEqual(self.findings(self.ROWS), [])
        wrong = self.findings({**self.ROWS, "P4_Line3_ZipCode1": "SW1A 1AA"})  # a U.S. row
        self.assertEqual([item["fields"] for item in wrong], [["P4_Line3_ZipCode1"]])
        self.assertEqual(wrong[0]["title"], "ZIP Code or postal code box holds an answer in the wrong format")


class EveryBlankZipCodeTests(unittest.TestCase):
    """Every official blank the schemas were built on: a box read as a ZIP Code is one."""

    def test_only_boxes_named_for_a_zip_code_are_read_as_one(self) -> None:
        from form_question_schema import QUESTION_SCHEMAS

        kinds = sorted({schema["kind"] for schema in QUESTION_SCHEMAS.values() if schema.get("field_list")})
        checked = 0
        for kind in kinds:
            blank = official_blank(kind)
            if blank is None:
                continue
            checked += 1
            box = formats.box_formats(blank)
            with self.subTest(form=kind):
                self.assertEqual(
                    sorted(name for name, fmt in box.items()
                           if fmt in (formats.ZIP, formats.ZIP_OR_POSTAL) and "zip" not in name.lower()),
                    [],
                )
                expected_postal = (
                    {f"P4_Line3_ZipCode{n}" for n in (1, 2, 3)} | {f"P7_ZipCode{n}" for n in (1, 2, 3)}
                    if kind == "n-400" else set()
                )
                self.assertEqual({name for name, fmt in box.items() if fmt == formats.ZIP_OR_POSTAL}, expected_postal)
        if not checked:
            self.skipTest("no official blank available")


if __name__ == "__main__":
    unittest.main()

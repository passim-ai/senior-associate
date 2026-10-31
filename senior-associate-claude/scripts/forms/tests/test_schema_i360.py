#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Offline tests for the I-360 VAWA self-petition question schema (01/20/25 edition). All values
are fictional.

    uv run --script tests/test_schema_i360.py
"""
from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import audit_prepared_forms as audit  # noqa: E402
from form_question_schema import get_question_schema, load_field_list, skeleton_plan  # noqa: E402

SCHEMA = "i360_vawa_self_petition"

# Boxes of the parts for other classifications, which this schema leaves out: Part 6 (Amerasian; its
# item 6.D phone is misnamed Pt4Line6d), Part 7 (widow(er)), Part 8 (special immigrant juvenile), Part 9
# (religious worker; but Pt9Line8a/8b are Part 10 item 8), and Part 2 items 1.D(1) and 1.P.
OTHER_CLASSIFICATION = re.compile(r"^(Pt6|Pt7|Pt8|Pt9(?!Line8[ab]_)|Pt4Line6d_|Pt2Line1d1_|Pt2Line1p_)")

# Every client mailing address on the form: each of its boxes carries the safe mailing address rule.
CLIENT_MAILING_PREFIXES = ("Pt1Line6_", "Pt1Line7_", "Pt3Line2_")

# Sections that serve other filers or apply only in some VAWA cases.
MAY_BE_NOT_APPLICABLE = (
    "attorney_box",
    "filer_identity",
    "filer_mailing_address",
    "last_arrival_and_status",
    "consulate_abroad",
    "foreign_address",
    "children_separate_self_petitions",
    "family_member_1",
    "children_2_to_9",
    "authorized_signatory",
    "interpreter_block",
    "interpreter_signature",
    "preparer_block",
    "preparer_signature",
    "additional_information",
)


def base(field: str) -> str:
    return field.split("[")[0]


def complete_spouse_plan() -> dict:
    """A fictional box-I plan: every question answered or marked not applicable."""
    plan = skeleton_plan(SCHEMA)
    not_applicable = {
        "filer_identity",
        "filer_mailing_address",
        "authorized_signatory",
        "consulate_abroad",
        "children_2_to_9",
    }
    for question in plan["questions"]:
        key = question["key"]
        if key in not_applicable:
            question["status"] = "not_applicable"
            continue
        if "pending_signature" in question["allowed_statuses"]:
            question["status"] = "pending_signature"
            continue
        question["status"] = "filled"
        for field in question["field_values"]:
            choices = question.get("choices", {}).get(field)
            question["field_values"][field] = next(iter(choices.values())) if choices else "X1"
    return plan


class I360SchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = get_question_schema(SCHEMA)
        self.assertIsNotNone(self.schema)
        self.questions = self.schema["required_questions"]
        self.fields = load_field_list(self.schema["field_list"])["fields"]

    def notes(self, key: str) -> dict[str, str]:
        return self.questions[key].get("field_notes", {})

    def test_every_vawa_box_belongs_to_exactly_one_question(self) -> None:
        owners: dict[str, list[str]] = {}
        for key, spec in self.questions.items():
            for field in spec["required_fields"]:
                owners.setdefault(field, []).append(key)
        self.assertEqual({f: k for f, k in owners.items() if len(k) > 1}, {})
        declared = {base(field) for field in owners}
        on_form = {name for name in self.fields if name != "PDF417BarCode1"}
        vawa = {name for name in on_form if not OTHER_CLASSIFICATION.match(name)}
        self.assertEqual(vawa - declared, set())
        self.assertEqual({name for name in declared if OTHER_CLASSIFICATION.match(name)}, set())

    def test_other_classifications_are_named_as_out_of_scope(self) -> None:
        notes = " ".join(self.schema["notes"])
        for part in ("Part 6", "Part 7", "Part 8", "Part 9", "Amerasian", "widow(er)", "juvenile", "religious worker"):
            self.assertIn(part, notes)

    def test_every_checkbox_has_a_choice_for_each_on_state(self) -> None:
        for key, spec in self.questions.items():
            for field in spec["required_fields"]:
                entry = self.fields[base(field)]
                if entry["type"] != "/Btn":
                    continue
                with self.subTest(question=key, field=field):
                    choices = spec.get("choices", {}).get(field, {})
                    if field == "Pt2Line1":
                        # Only the three VAWA classifications are offered.
                        self.assertEqual(sorted(choices.values()), ["I", "J", "K"])
                    else:
                        self.assertEqual(sorted(choices.values()), sorted(entry["states"]))

    def test_statuses(self) -> None:
        for key in MAY_BE_NOT_APPLICABLE:
            self.assertIn("not_applicable", self.questions[key]["allowed_statuses"], key)
        for key in ("filer_mailing_address", "authorized_signatory"):
            self.assertEqual(self.questions[key]["allowed_statuses"], ["not_applicable"], key)
        for key in ("safe_mailing_address", "self_petitioner_mailing_address", "classification", "residence_with_abuser"):
            self.assertEqual(self.questions[key]["allowed_statuses"], ["filled"], key)
        for key in ("petitioner_signature", "interpreter_signature", "preparer_signature"):
            self.assertIn("pending_signature", self.questions[key]["allowed_statuses"], key)

    def test_every_client_mailing_box_carries_the_safe_address_rule(self) -> None:
        mailing = {
            field: key
            for key, spec in self.questions.items()
            for field in spec["required_fields"]
            if field.startswith(CLIENT_MAILING_PREFIXES)
        }
        self.assertIn("Pt1Line7_InCareofName", mailing)
        self.assertIn("Pt3Line2_InCareofName", mailing)
        self.assertEqual(len(mailing), 11 + 10 + 10)
        for field, key in mailing.items():
            with self.subTest(field=field):
                note = self.notes(key).get(field, "")
                self.assertIn("attorney's office address from the attorney profile", note)
                self.assertIn("mailing_address", note)
                self.assertIn("unless the attorney gives another", note)
        for key, field in (
            ("safe_mailing_address", "Pt1Line7_StreetNumberName"),
            ("self_petitioner_mailing_address", "Pt3Line2_StreetNumberName"),
            ("residence_with_abuser", "Pt10Line10_StreetNumberName"),
        ):
            note = self.notes(key)[field]
            self.assertIn("shared with the abuser", note, field)
            self.assertIn("attorney_decision", note, field)

    def test_misleading_boxes_are_pinned(self) -> None:
        self.assertEqual(
            self.questions["marriage_to_abuser"]["required_fields"],
            ["Pt9Line8a_DateOfMarriage", "Pt9Line8b_PlaceOfMarriage"],
        )
        self.assertIn("Pt12Line8_Signature[0]", self.questions["authorized_signatory"]["required_fields"])
        self.assertIn("Pt12Line8_Signature[1]", self.questions["preparer_signature"]["required_fields"])
        interpreter = self.questions["interpreter_block"]["required_fields"]
        for field in ("Pt12Line4_InterpreterDaytimeTelephone", "Pt12Line5_Email", "Pt12_NameofLanguage"):
            self.assertIn(field, interpreter)
        self.assertIn("MOBILE", self.notes("preparer_block")["Pt13ine5_PreparerFaxNumber"])
        self.assertEqual(
            self.questions["preparer_block"]["choices"]["Pt13Line7b_extends"], {"extends": "Y", "does not extend": "N"}
        )
        # Part 15 items 1-2 are Part 1's global name and A-Number boxes.
        self.assertIn("FORM DEFECT", self.notes("filer_identity")["Pt1Line1_FamilyName"])
        self.assertIn("Part 15", self.notes("filer_identity")["Pt1Line4_AlienNumber"])
        self.assertIn("unbound", self.notes("additional_information")["Pt14Line3a_PageNumber"])

    def test_complete_spouse_plan_has_no_schema_findings(self) -> None:
        plan = complete_spouse_plan()
        entry = {"question_schema": SCHEMA}
        findings = audit.schema_findings(
            pdf_path=Path("/x/I-360.pdf"), kind="i-360", questions=plan["questions"], manifest_entry=entry
        )
        self.assertEqual(findings, [])

        safe = next(q for q in plan["questions"] if q["key"] == "safe_mailing_address")
        safe["field_values"]["Pt1Line7_StreetNumberName"] = ""
        findings = audit.schema_findings(
            pdf_path=Path("/x/I-360.pdf"), kind="i-360", questions=plan["questions"], manifest_entry=entry
        )
        self.assertTrue(
            any(
                f["title"] == "Question plan leaves required form values blank"
                and f["question_key"] == "safe_mailing_address"
                for f in findings
            )
        )

        safe["status"] = "not_applicable"
        findings = audit.schema_findings(
            pdf_path=Path("/x/I-360.pdf"), kind="i-360", questions=plan["questions"], manifest_entry=entry
        )
        self.assertTrue(any(f.get("question_key") == "safe_mailing_address" for f in findings))

    def test_schema_only_audit_flags_a_blank_output(self) -> None:
        self.assertTrue(audit.audit_form("i-360", Path("/x/I-360.pdf"), {}, xfa={}, acro={}))
        complete = {"Pt2Line1": "I", "Pt3Line1_FamilyName": "X", "Pt3Line1_GivenName": "Y", "Pt3Line3_DateOfBirth": "01/02/1990",
                    "Pt3Line4_CountryOfBirth": "Examplestan", "Pt10Line1_FamilyName": "Z", "Pt10Line1_GivenName": "W"}
        self.assertEqual(audit.audit_form("i-360", Path("/x/I-360.pdf"), complete, xfa={}, acro={}), [])
        other = audit.audit_form("i-360", Path("/x/I-360.pdf"), {**complete, "Pt2Line1": "A"}, xfa={}, acro={})
        self.assertEqual([f["title"] for f in other],
                         ["Part 2 item 1 selects a classification other than a VAWA self-petition (I, J or K)"])


if __name__ == "__main__":
    unittest.main()

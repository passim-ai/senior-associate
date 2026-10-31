#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Offline tests for the I-751 question schema (04/01/24 edition). All values are fictional.

    uv run --script tests/test_schema_i751.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import audit_prepared_forms as audit  # noqa: E402
from official_blanks import complete_plan  # noqa: E402
from form_question_schema import get_question_schema, load_field_list  # noqa: E402

SCHEMA = "i751_remove_conditions"
SIGNATURES = {"petitioner_signature", "spouse_signature", "interpreter_signature", "preparer_signature"}
PART_8 = (
    "spouse_statement_language",
    "spouse_statement_preparer",
    "spouse_contact",
    "spouse_asc_acknowledgement",
    "spouse_signature",
)
WAIVER = {
    key: "not_applicable"
    for key in PART_8
    + (
        "different_marriage",
        "spouse_physical_address",
        "children",
        "petitioner_statement_preparer",
        "interpreter_block",
        "interpreter_signature",
        "preparer_block",
        "preparer_statement",
        "preparer_signature",
        "additional_information",
        "attorney_box",
    )
}


class I751SchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = get_question_schema(SCHEMA)
        self.assertIsNotNone(self.schema)
        self.questions = self.schema["required_questions"]
        self.fields = load_field_list(self.schema["field_list"])["fields"]

    def owner(self, field: str) -> str:
        return next(key for key, spec in self.questions.items() if field in spec["required_fields"])

    def test_route_specific_questions_may_be_not_applicable(self) -> None:
        for key in PART_8 + ("marriage_ended", "different_marriage", "spouse_physical_address", "children"):
            self.assertIn("not_applicable", self.questions[key]["allowed_statuses"], key)
        for key in ("petitioner_statement_language", "petitioner_contact", "petitioner_asc_acknowledgement",
                    "basis_for_petition", "spouse_relationship", "spouse_identity"):
            self.assertEqual(self.questions[key].get("allowed_statuses", ["filled"]), ["filled"], key)
        self.assertEqual(self.questions["petitioner_signature"]["allowed_statuses"], ["pending_signature", "filled"])
        for key in SIGNATURES:
            self.assertIn("pending_signature", self.questions[key]["allowed_statuses"], key)

    def test_part_3_offers_both_routes(self) -> None:
        choices = self.questions["basis_for_petition"]["choices"]
        states = sorted(state for options in choices.values() for state in options.values())
        self.assertEqual(states, ["A", "B", "C", "D", "E", "F", "G"])

    def test_children_cover_all_five_rows(self) -> None:
        fields = self.questions["children"]["required_fields"]
        self.assertEqual(len(fields), 5 * 16)  # name (3), birth date, A-Number, two yes/no, address (9)
        for index in range(4):
            self.assertIn(f"Line13a_FamilyName[{index}]", fields)
            self.assertIn(f"Line15_AlienNumber[{index}]", fields)
        for address in ("Pt5Line6", "Pt5Line12", "Pt5Line18", "Pt5Line24", "Pt5Line30"):
            self.assertIn(f"{address}_Country", fields)

    def test_part_7_and_part_8_use_their_own_index(self) -> None:
        for name in ("P5_Checkbox2", "P5_Line3_DaytimePhoneNumber", "P5_Line6b_DateofSignature"):
            self.assertTrue(self.owner(f"{name}[0]").startswith("petitioner_"), name)
            self.assertTrue(self.owner(f"{name}[1]").startswith("spouse_"), name)
        self.assertEqual(self.owner("P7_Name"), "petitioner_asc_acknowledgement")
        self.assertEqual(self.owner("Pt8_Name"), "spouse_asc_acknowledgement")

    def test_misleading_boxes_are_pinned(self) -> None:
        self.assertEqual(self.owner("Line17a_InCareofName"), "mailing_address")  # item 15, not 17
        self.assertEqual(self.owner("Line17_Checkbox"), "removal_proceedings")  # item 18
        self.assertEqual(self.owner("Line21_Checkbox"), "other_addresses_since_permanent_residence")  # item 22
        self.assertEqual(self.owner("Pt9Line3_StreetNumberName"), "preparer_block")  # Part 10, not Part 9
        self.assertEqual(self.owner("P6_Line3a_StreetNumberName"), "interpreter_block")
        self.assertIn("WEIGHT", self.questions["height_and_weight"]["field_notes"]["P3_Line9_HeightInches1"])
        self.assertIn("GIVEN", self.questions["spouse_identity"]["field_notes"]["Pt4Line2b_GivenName2"])
        self.assertIn("maxlen 10", self.questions["interpreter_block"]["field_notes"]["P6_Line5_InterpretersEmailAddress"])

    def test_complete_plans_have_no_schema_findings(self) -> None:
        for name, statuses in (("joint", {"marriage_ended": "not_applicable"}), ("waiver", WAIVER)):
            with self.subTest(route=name):
                findings = audit.schema_findings(
                    pdf_path=Path("/x/I-751.pdf"),
                    kind="i-751",
                    questions=complete_plan(SCHEMA, statuses)["questions"],
                    manifest_entry={"question_schema": SCHEMA},
                )
                self.assertEqual(findings, [])

    def test_petitioner_parts_cannot_be_skipped(self) -> None:
        skipped = {"petitioner_signature": "not_applicable", "basis_for_petition": "not_applicable"}
        questions = complete_plan(SCHEMA, skipped)["questions"]
        findings = audit.schema_findings(
            pdf_path=Path("/x/I-751.pdf"), kind="i-751", questions=questions, manifest_entry={"question_schema": SCHEMA}
        )
        self.assertEqual(
            sorted(f["question_key"] for f in findings if f["title"].startswith("Question plan uses an invalid status")),
            ["basis_for_petition", "petitioner_signature"],
        )


if __name__ == "__main__":
    unittest.main()

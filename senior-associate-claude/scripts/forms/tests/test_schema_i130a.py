#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Offline tests for the I-130A question schema (04/01/24 edition). All values are fictional.

    uv run --script tests/test_schema_i130a.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import audit_prepared_forms as audit  # noqa: E402
from official_blanks import complete_plan  # noqa: E402
from form_question_schema import get_question_schema, load_field_list  # noqa: E402

SCHEMA = "i130a_spouse_beneficiary"
# Pre-printed "PRESENT" date-to boxes of the current address and current employer: no question owns them.
SIGNATURES = {"spouse_beneficiary_signature", "interpreter_signature", "preparer_signature"}


class I130ASchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = get_question_schema(SCHEMA)
        self.assertIsNotNone(self.schema)
        self.questions = self.schema["required_questions"]
        self.fields = load_field_list(self.schema["field_list"])["fields"]

    def owner(self, field: str) -> str:
        return next(key for key, spec in self.questions.items() if field in spec["required_fields"])

    def test_history_rows_match_the_audit(self) -> None:
        rows = {
            "physical_address_1_current": audit.I130A_ADDRESS_ROWS[0],
            "physical_address_2": audit.I130A_ADDRESS_ROWS[1],
            "last_address_outside_us": audit.I130A_FOREIGN_ADDRESS_ROW,
            "employer_1_current": audit.I130A_EMPLOYMENT_ROWS[0],
            "employer_2": audit.I130A_EMPLOYMENT_ROWS[1],
            "employment_outside_us": audit.I130A_FOREIGN_EMPLOYMENT_ROW,
        }
        for key, row in rows.items():
            with self.subTest(question=key):
                self.assertLessEqual(set(row.fields()), set(self.questions[key]["required_fields"]))
        # The current rows are required by the audit; their minimum is what the audit needs of any row.
        self.assertEqual(
            set(self.questions["physical_address_1_current"]["required_nonempty_fields_when_filled"]),
            {"Pt1Line4a_StreetNumberName", "Pt1Line4c_CityOrTown", "Pt1Line4h_Country", "Pt1Line5a_DateFrom"},
        )
        # "Unemployed" needs no address or occupation, so only the name and start date are always required.
        self.assertEqual(
            set(self.questions["employer_1_current"]["required_nonempty_fields_when_filled"]),
            {"Pt2Line1_EmployerOrCompName", "Pt2Line4a_DateFrom"},
        )

    def test_audit_high_signal_fields_are_required_when_filled(self) -> None:
        required = {
            "spouse_beneficiary_name": ["Pt1Line3a_FamilyName", "Pt1Line3b_GivenName"],
            "parent_1": ["Pt1Line10_FamilyName", "Pt1Line10_GivenName", "Pt1Line11_DateofBirth",
                         "Pt1Line13_CountryofBirth", "Pt1Line15_CountryofResidence"],
            "parent_2": ["Pt1Line16_FamilyName", "Pt1Line16_GivenName", "Pt1Line17_DateofBirth",
                         "Pt1Line19_CountryofBirth", "Pt1Line21_CountryofResidence"],
            "spouse_beneficiary_contact": ["Pt4Line3_DaytimePhoneNumber1"],
            "preparer_block": ["Pt6Line1a_PreparerFamilyName", "Pt6Line1b_PreparerGivenName",
                               "Pt6Line2_BusinessName", "Pt6Line4_DaytimePhoneNumber", "Pt6Line6_Email"],
        }
        for key, fields in required.items():
            with self.subTest(question=key):
                self.assertLessEqual(set(fields), set(self.questions[key]["required_nonempty_fields_when_filled"]))
                self.assertEqual(self.questions[key].get("allowed_statuses", ["filled"]), ["filled"])
        for name in audit.ATTORNEY_BOX_FIELDS["i-130a"].values():
            if name in self.fields:
                self.owner(name)  # every attorney-box field the audit compares has an owner

    def test_spouse_abroad_need_not_sign(self) -> None:
        for key in ("statement_language", "statement_preparer", "spouse_beneficiary_signature"):
            self.assertIn("not_applicable", self.questions[key]["allowed_statuses"], key)
        for key in SIGNATURES:
            self.assertIn("pending_signature", self.questions[key]["allowed_statuses"], key)
            self.assertIn("filled", self.questions[key]["allowed_statuses"], key)

    def test_misleading_boxes_are_pinned(self) -> None:
        self.assertEqual(self.owner("Pt2Line3_USCISELISActNumber"), "uscis_online_account_number")
        parent_1 = self.questions["parent_1"]["field_notes"]
        self.assertIn("RESIDENCE", parent_1["Pt1Line14_CountryofBirth"])
        self.assertIn("Item 13", parent_1["Pt1Line12CityTownOfBirth"])
        self.assertIn("Item 18", self.questions["parent_2"]["field_notes"]["Pt1Line17_DateofBirth"])
        self.assertIn("MOBILE", self.questions["preparer_block"]["field_notes"]["Pt6Line5_PreparerFaxNumber"])
        interpreter = self.questions["interpreter_block"]["field_notes"]
        self.assertIn("MOBILE", interpreter["Pt5Line4_InterpreterDaytimeTelephone[1]"])
        # Part 1 address rows use padded on-states; every other address on the form does not.
        self.assertEqual(self.questions["physical_address_1_current"]["choices"]["Pt1Line4b_Unit"]["apt"], " APT ")
        self.assertEqual(self.questions["employer_1_current"]["choices"]["Pt2Line2b_Unit"]["apt"], "APT")

    def test_complete_plans_have_no_schema_findings(self) -> None:
        abroad = {
            "physical_address_2": "not_applicable",
            "statement_language": "not_applicable",
            "statement_preparer": "not_applicable",
            "spouse_beneficiary_signature": "not_applicable",
            "interpreter_block": "not_applicable",
            "interpreter_signature": "not_applicable",
            "additional_information": "not_applicable",
        }
        for statuses in ({}, abroad):
            with self.subTest(abroad=bool(statuses)):
                findings = audit.schema_findings(
                    pdf_path=Path("/x/I-130A.pdf"),
                    kind="i-130a",
                    questions=complete_plan(SCHEMA, statuses)["questions"],
                    manifest_entry={"question_schema": SCHEMA},
                )
                self.assertEqual(findings, [])

    def test_contact_and_preparer_cannot_be_skipped(self) -> None:
        skipped = {"spouse_beneficiary_contact": "not_applicable", "preparer_block": "not_applicable"}
        questions = complete_plan(SCHEMA, skipped)["questions"]
        findings = audit.schema_findings(
            pdf_path=Path("/x/I-130A.pdf"), kind="i-130a", questions=questions, manifest_entry={"question_schema": SCHEMA}
        )
        self.assertEqual(
            sorted(f["question_key"] for f in findings if f["title"].startswith("Question plan uses an invalid status")),
            ["preparer_block", "spouse_beneficiary_contact"],
        )


if __name__ == "__main__":
    unittest.main()

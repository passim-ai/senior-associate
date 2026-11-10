#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Offline tests for the I-864 question schema (08/24/26 edition). All values are fictional.

    uv run --script tests/test_schema_i864.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import audit_prepared_forms as audit  # noqa: E402
from official_blanks import complete_plan  # noqa: E402
import forms_workflow  # noqa: E402
from form_question_schema import get_question_schema, load_field_list, skeleton_plan  # noqa: E402

SCHEMA = "i864_household_sponsor"
GLOBAL_BASES = {
    "P1_Line1a-f_CB", "P1_Line1e1_Checkbox", "P1_Line3_Checkbox", "P4_Line1a_FamilyName",
    "P4_Line1b_GivenName", "P4_Line1c_MiddleName", "P4_Line2c_Unit", "P4_Line4b_Unit",
    "P4_Line10_SocialSecurityNumber", "P4_Line11a_Checkbox", "P4_Line11b_Checkbox", "P4_Line11c_Checkbox",
    "P4_Line12_AlienNumber", "P4_Line14_Checkboxes", "P2_Line1a_FamilyName", "P2_Line1b_GivenName",
    "P2_Line1c_MiddleName", "P2_Line2_Unit", "P3_Line1_Checkbox", "P6_Line1_Checkbox", "P6_Line18a_Checkbox",
    "P8_Line2_Checkbox",
}
SIGNATURES = {"sponsor_signature", "interpreter_signature", "preparer_signature"}
# Parts that apply only to some sponsors or households.
OPTIONAL = {
    "attorney_box", "sponsor_physical_address", "sponsor_a_number_and_account", "sponsor_military_service",
    "family_member_1", "family_member_2", "family_member_3", "family_member_4", "household_member_income",
    "assets", "sponsor_statement_language", "interpreter_block", "interpreter_signature", "additional_information",
}
# A fictional petitioning sponsor, household of 2 (the sponsor and the sponsored spouse).
ANSWERS = {
    "P1_Line1a-f_CB": "1A", "P4_Line1a_FamilyName": "Sample", "P4_Line1b_GivenName": "Jane",
    "P4_Line5_CountryOfDomicile": "United States", "P4_Line6_DateOfBirth": "04/17/1990",
    "P4_Line7_CityofBirth": "United States", "P4_Line2b_StreetNumberName": "200 Sample Street",
    "P4_Line2e_CityOrTown": "Springfield", "P4_Line2f_State": "IL", "P4_Line2g_ZipCode": "62702",
    "P4_Line2j_Country": "USA", "P1_Line3_Checkbox": "Y", "P4_Line10_SocialSecurityNumber": "000000000",
    "P2_Line1a_FamilyName": "Ejemplo", "P2_Line1b_GivenName": "Luis", "P2_Line3_CountryCitizenship": "Mexico",
    "P2_Line4_DateOfBirth": "09/02/1990", "P2_Line2_StreetNumberName": "200 Sample Street",
    "P2_Line2_CityOrTown": "Springfield", "P2_Line2_Country": "USA", "P3_Line1_Checkbox": "Y",
    "P3_Line28_TotalNumberofImmigrants": "1", "P5_Line2_Yourself": "1", "P5_Line3_Married": "0",
    "P5_Line4_DependentChildren": "0", "P5_Line5_OtherDependents": "0", "P5_Line6_Sponsors": "0",
    "P5_Line7_SameResidence": "0", "Override": "2", "P6_Line2_TotalIncome": "81200",
    "P6_Line15_TotalHouseholdIncome": "81200", "P6_Line18a_Checkbox": "Y", "P6_Line19a_TaxYear": "2025",
    "P6_Line19a_TotalIncome": "78400", "P6_Line19b_TaxYear": "N/A", "P6_Line19b_TotalIncome": "N/A",
    "P6_Line19c_TaxYear": "N/A", "P6_Line19c_TotalIncome": "N/A",
}


def base(field: str) -> str:
    return field.split("[")[0]


class I864SchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = get_question_schema(SCHEMA)
        self.assertIsNotNone(self.schema)
        self.questions = self.schema["required_questions"]
        self.fields = load_field_list(self.schema["field_list"])["fields"]

    def owner(self, field: str) -> str:
        return next(key for key, spec in self.questions.items() if field in spec["required_fields"])

    def test_global_boxes_are_named_by_their_base(self) -> None:
        for spec in self.questions.values():
            for field in spec["required_fields"]:
                if base(field) in GLOBAL_BASES:
                    self.assertEqual(field, base(field), f"{field}: name a global field by its base")

    def test_basis_covers_every_sponsor_type(self) -> None:
        basis = self.questions["sponsorship_basis"]["choices"]["P1_Line1a-f_CB"]
        self.assertEqual(sorted(basis.values()), ["1A", "1B", "1C", "1D", "1E", "1F"])
        self.assertEqual(self.questions["sponsorship_basis"]["choices"]["P1_Line1e1_Checkbox"], {"first": "1", "second": "2"})

    def test_sponsor_type_parts_may_be_not_applicable(self) -> None:
        for key, spec in self.questions.items():
            allowed = spec.get("allowed_statuses", ["filled"])
            with self.subTest(question=key):
                self.assertEqual("not_applicable" in allowed, key in OPTIONAL)
                if key in SIGNATURES:
                    self.assertLessEqual({"pending_signature", "filled"}, set(allowed))

    def test_linked_checkbox_defect_is_in_the_notes(self) -> None:
        employment = self.questions["sponsor_employment"]
        defect = forms_workflow.KNOWN_LINKED_CHECKBOX_GROUPS[0]
        self.assertEqual(defect["base"], "P6_Line1_Checkbox")
        self.assertEqual(
            {state.strip() for state in employment["choices"]["P6_Line1_Checkbox"].values()}, set(defect["states"])
        )
        self.assertEqual(employment["choices"]["P6_Line1_Checkbox"]["Employed"], " Y")
        self.assertIn("FORM DEFECT", employment["field_notes"]["P6_Line1_Checkbox"])
        self.assertIn("attorney_action", employment["field_notes"]["P6_Line1_Checkbox"])
        self.assertIn("P6_Line1_Checkbox", self.questions["sponsor_statement_language"]["field_notes"]["P8_Line1b_language"])
        self.assertTrue(any("Known form defect" in note for note in self.schema["notes"]))

    def test_misleading_boxes_are_pinned(self) -> None:
        self.assertEqual(self.owner("P4_Line10_SocialSecurityNumber"), "sponsor_ssn")
        self.assertIn("COUNTRY", self.questions["sponsor_identity"]["field_notes"]["P4_Line7_CityofBirth"])
        self.assertEqual(self.owner("P1_Line3_Checkbox"), "sponsor_mailing_address")
        self.assertEqual(self.owner("P3_Line28_TotalNumberofImmigrants"), "household_size")
        self.assertIn("Item 8", self.questions["household_size"]["field_notes"]["Override"])
        self.assertIn("OCCUPATION", self.questions["sponsor_employment"]["field_notes"]["P6_Line1a_NameofEmployer"])
        self.assertEqual(self.owner("P6_Line2_TotalIncome"), "current_income")
        self.assertEqual(self.owner("P6_Line4_Relationship"), "household_member_income")  # item 8, not item 4
        self.assertEqual(self.owner("P6_Line5_CurrentIncome"), "household_member_income")
        self.assertEqual(self.owner("P7Line7_EmailAddress"), "sponsor_contact")
        self.assertEqual(self.owner("P7Line9b_DateofSignature"), "sponsor_signature")
        self.assertIn("MOBILE", self.questions["preparer_block"]["field_notes"]["P10_Line5_PreparersFaxNumber"])
        self.assertEqual(self.owner("P8Line2_InterpretersBusinessName"), "interpreter_block")
        # The three P2_Line5_AlienNumber boxes are three people.
        self.assertEqual(self.owner("P2_Line5_AlienNumber[0]"), "principal_immigrant_identity")
        self.assertEqual(self.owner("P2_Line5_AlienNumber[1]"), "family_member_1")
        self.assertEqual(self.owner("P2_Line5_AlienNumber[2]"), "family_member_3")
        self.assertEqual(self.owner("P3_Line2_SponsoringFamily[1]"), "immigrants_sponsored")
        # Odd padding on the Part 6 on-states.
        self.assertEqual(self.questions["sponsor_employment"]["choices"]["P6_Line5_Checkbox"], {"Retired": "Y "})
        self.assertEqual(self.questions["sponsor_employment"]["choices"]["P6_Line4_Checkbox"], {"Self-Employed": " Y"})
        self.assertIn("recalculates", self.questions["current_income"]["field_notes"]["P6_Line15_TotalHouseholdIncome"])

    def test_schema_agrees_with_the_audit(self) -> None:
        values: dict[str, str] = {}
        for item in skeleton_plan(SCHEMA)["questions"]:
            if item["key"] in OPTIONAL or "filled" not in item["allowed_statuses"]:
                continue
            for field in item["required_nonempty_fields_when_filled"]:
                values[field] = ANSWERS.get(field, "Zztest")
        self.assertEqual([name for name in ANSWERS if name not in values], [])
        values["P4_Line10_SocialSecurityNumber"] = "123456789"  # synthetic, structurally valid
        findings = audit.audit_form("i-864", Path("/x/I-864.pdf"), values, xfa=values, acro=values)
        # Errors and the household-income warning are cleared; only the unsigned signatures remain.
        self.assertEqual([f["title"] for f in findings], ["Signature fields are still blank"])

    def test_complete_plans_have_no_schema_findings(self) -> None:
        minimal = {key: "not_applicable" for key in OPTIONAL}
        for statuses in ({}, minimal):
            with self.subTest(minimal=bool(statuses)):
                findings = audit.schema_findings(
                    pdf_path=Path("/x/I-864.pdf"),
                    kind="i-864",
                    questions=complete_plan(SCHEMA, statuses, answers=ANSWERS)["questions"],
                    manifest_entry={"question_schema": SCHEMA},
                )
                self.assertEqual(findings, [])

    def test_core_parts_cannot_be_skipped(self) -> None:
        skipped = ["sponsorship_basis", "sponsor_ssn", "household_size", "current_income", "tax_year_income", "preparer_block"]
        questions = complete_plan(SCHEMA, {key: "not_applicable" for key in skipped}, answers=ANSWERS)["questions"]
        findings = audit.schema_findings(
            pdf_path=Path("/x/I-864.pdf"), kind="i-864", questions=questions, manifest_entry={"question_schema": SCHEMA}
        )
        self.assertEqual(
            sorted(f["question_key"] for f in findings if f["title"].startswith("Question plan uses an invalid status")),
            sorted(skipped),
        )


if __name__ == "__main__":
    unittest.main()

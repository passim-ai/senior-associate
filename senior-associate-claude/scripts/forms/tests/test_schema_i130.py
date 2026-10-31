#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Offline tests for the I-130 question schema (04/01/24 edition). All values are fictional.

    uv run --script tests/test_schema_i130.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import audit_prepared_forms as audit  # noqa: E402
from official_blanks import complete_plan  # noqa: E402
from form_question_schema import (  # noqa: E402
    SCHEMA_I130_FAMILY_PETITION,
    get_question_schema,
    load_field_list,
    skeleton_plan,
)

SCHEMA = SCHEMA_I130_FAMILY_PETITION
# Pre-printed "PRESENT" date-to boxes of the current address and current employer: no question owns them.
SIGNATURES = {"petitioner_signature", "interpreter_signature", "preparer_signature"}

# Per posture, the questions a typical filing marks not_applicable; everything else is filled.
COMMON_NA = {
    "petitioner_a_number",
    "petitioner_uscis_online_account",
    "beneficiary_a_number",
    "beneficiary_uscis_online_account",
    "beneficiary_ssn",
    "petitioner_spouse_2",
    "beneficiary_spouse_2",
    "other_relative_petition_1",
    "other_relative_petition_2",
    "beneficiary_native_script",
    "interpreter_block",
    "interpreter_signature",
    "additional_information",
}
POSTURES = {
    # U.S. citizen by birth petitions for a spouse in the U.S. who adjusts status.
    "spouse_adjusting": COMMON_NA
    | {
        "child_parent_relationship",
        "sibling_adoption",
        "petitioner_lpr_admission",
        "beneficiary_family_person_2",
        "beneficiary_family_person_3",
        "beneficiary_family_person_4",
        "beneficiary_family_person_5",
        "consular_processing",
    },
    # Naturalized citizen petitions for a widowed parent abroad (consular processing).
    "parent_abroad": COMMON_NA
    | {
        "sibling_adoption",
        "petitioner_lpr_admission",
        "beneficiary_current_marriage",
        "beneficiary_spouse_1",
        "beneficiary_family_person_1",
        "beneficiary_family_person_2",
        "beneficiary_family_person_3",
        "beneficiary_family_person_4",
        "beneficiary_family_person_5",
        "beneficiary_arrival",
        "beneficiary_i94",
        "last_address_together",
        "adjustment_office",
    },
    # Lawful permanent resident petitions for an unmarried child abroad.
    "child_by_lpr": COMMON_NA
    | {
        "sibling_adoption",
        "petitioner_certificate",
        "petitioner_physical_address_2",
        "petitioner_employer_2",
        "beneficiary_current_marriage",
        "beneficiary_spouse_1",
        "beneficiary_family_person_1",
        "beneficiary_family_person_2",
        "beneficiary_family_person_3",
        "beneficiary_family_person_4",
        "beneficiary_family_person_5",
        "beneficiary_arrival",
        "beneficiary_i94",
        "beneficiary_travel_document",
        "last_address_together",
        "adjustment_office",
    },
    # U.S. citizen petitions for a married brother abroad with two children.
    "sibling_abroad": COMMON_NA
    | {
        "child_parent_relationship",
        "petitioner_lpr_admission",
        "beneficiary_family_person_4",
        "beneficiary_family_person_5",
        "beneficiary_arrival",
        "beneficiary_i94",
        "last_address_together",
        "adjustment_office",
    },
}


def base(field: str) -> str:
    return field.split("[")[0]


class I130SchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = get_question_schema(SCHEMA)
        self.assertIsNotNone(self.schema)
        self.questions = self.schema["required_questions"]
        self.fields = load_field_list(self.schema["field_list"])["fields"]

    def owner(self, field: str) -> str:
        return next(key for key, spec in self.questions.items() if field in spec["required_fields"])

    def allowed(self, key: str) -> list[str]:
        return self.questions[key].get("allowed_statuses", ["filled"])

    def test_repeated_boxes_are_split_by_occurrence_between_their_rows(self) -> None:
        self.assertEqual(self.owner("Pt4Line17_DateMarriageEnded[0]"), "beneficiary_spouse_1")
        self.assertEqual(self.owner("Pt4Line17_DateMarriageEnded[1]"), "beneficiary_spouse_2")
        self.assertEqual(self.owner("Pt4Line49_CountryOfBirth[0]"), "beneficiary_family_person_1")
        self.assertEqual(self.owner("Pt4Line49_CountryOfBirth[1]"), "beneficiary_family_person_5")

    def test_every_question_has_a_label_with_its_part_and_items(self) -> None:
        for key, spec in self.questions.items():
            with self.subTest(question=key):
                self.assertRegex(spec["label"], r"^(Part \d|Page 1)")

    def test_misleading_on_states_are_pinned(self) -> None:
        choices = {field: options for spec in self.questions.values() for field, options in spec.get("choices", {}).items()}
        self.assertEqual(choices["Pt4Line20_No"], {"No": "Y"})  # Part 4 item 45
        self.assertEqual(choices["Pt4Line28_No"], {"No": "Y"})  # Part 4 item 53
        self.assertEqual(choices["Pt2Line36_LPR"], {"Lawful Permanent Resident": "N"})
        self.assertEqual(choices["Pt2Line10_Unit"]["Apt."], "APT ")  # trailing space only
        self.assertEqual(choices["Pt2Line10_Unit"]["Ste."], "STE")
        self.assertEqual(choices["Pt8Line3_Unit"]["Flr."], "FLR ")
        self.assertEqual(choices["Pt2Line12_Unit"]["Apt."], " APT ")
        self.assertEqual(choices["Pt2Line41_Unit"]["Apt."], "APT")
        self.assertEqual(choices["Pt4Line18_MaritalStatus"]["Single, Never Married"], "SNM")
        self.assertEqual(choices["Pt6Line1Checkbox"]["1.a. I can read and understand English"], "A")

    def test_misleading_names_are_pinned(self) -> None:
        self.assertEqual(self.owner("Pt2Line11_SSN"), "petitioner_ssn")  # Part 2 item 3
        self.assertEqual(self.owner("Pt2Line11_Yes"), "petitioner_mailing_address")  # item 11
        self.assertEqual(self.owner("Pt2Line23a_checkbox"), "petitioner_citizenship_status")  # item 37
        self.assertEqual(self.owner("Pt2Line36_Yes"), "petitioner_certificate")  # item 38
        self.assertEqual(self.owner("Pt2Line41_Yes"), "petitioner_lpr_admission")  # item 41
        self.assertEqual(self.owner("Pt2Line41_StreetNumberName"), "petitioner_employer_1_current")  # item 43
        self.assertEqual(self.owner("PtLine20a_FamilyName"), "petitioner_spouse_1")
        self.assertEqual(self.owner("P4Line5a_FamilyName"), "beneficiary_other_names")
        self.assertEqual(self.owner("Pt4Line55a_CityOrTown"), "beneficiary_proceedings")  # item 55
        self.assertEqual(self.owner("Pt4Line55a_FamilyName"), "beneficiary_native_script")  # item 57
        self.assertEqual(self.owner("Pt4Line57_StreetNumberName"), "last_address_together")  # item 59
        self.assertEqual(self.owner("Pt4Line60a_CityOrTown"), "adjustment_office")  # item 61
        self.assertEqual(self.owner("Pt4Line61a_CityOrTown"), "consular_processing")  # item 62
        self.assertEqual(self.owner("Part4Line1_Yes"), "petitioner_prior_petitions")  # Part 5 item 1
        self.assertEqual(self.owner("Pt4Line9_Relationship"), "other_relative_petition_2")  # Part 5 item 9
        self.assertEqual(self.owner("P5_Line6a_SignatureofApplicant"), "petitioner_signature")  # Part 6
        self.assertEqual(self.owner("Pt9Line9a_PageNumber"), "additional_information")  # Part 9 item 7.a
        interpreter = self.questions["interpreter_block"]["field_notes"]
        self.assertIn("MOBILE", interpreter["Pt4Line53_DaytimePhoneNumber"])
        self.assertIn("MOBILE", self.questions["preparer_block"]["field_notes"]["Pt8Line5_PreparerFaxNumber"])
        identity = self.questions["beneficiary_identity"]["field_notes"]
        self.assertTrue(identity["Pt4Line7_CityTownOfBirth"].startswith("Item 6"))
        self.assertTrue(identity["Pt4Line9_DateOfBirth"].startswith("Item 8"))
        self.assertIn("unbound", identity["Pt4Line9_Male"])
        self.assertIn("digits", self.questions["petitioner_prior_petitions"]["field_notes"]["Pt5Line5_Result"])

    def test_original_keys_kept(self) -> None:
        for key in (
            "relationship_basis",
            "petitioner_identity",
            "petitioner_mailing_address",
            "beneficiary_identity",
            "petitioner_signature",
            "preparer_signature",
        ):
            self.assertIn(key, self.questions)
        self.assertNotIn("beneficiary_address", self.questions)  # now beneficiary_physical_address
        self.assertIn("Pt4Line11_StreetNumberName", self.questions["beneficiary_physical_address"]["required_fields"])

    def test_relationship_and_status_specific_parts_allow_not_applicable(self) -> None:
        for key in (
            "child_parent_relationship",
            "sibling_adoption",
            "last_address_together",
            "petitioner_current_marriage",
            "petitioner_spouse_1",
            "beneficiary_current_marriage",
            "beneficiary_spouse_1",
            "beneficiary_family_person_1",
            "petitioner_certificate",
            "petitioner_lpr_admission",
            "beneficiary_arrival",
            "beneficiary_i94",
            "adjustment_office",
            "consular_processing",
        ):
            self.assertIn("not_applicable", self.allowed(key), key)
        for key in (
            "relationship_basis",
            "status_through_adoption",
            "petitioner_identity",
            "petitioner_mailing_address",
            "petitioner_physical_address_1_current",
            "petitioner_parent_1",
            "petitioner_parent_2",
            "petitioner_citizenship_status",
            "petitioner_biographic",
            "beneficiary_identity",
            "beneficiary_petitioned_by_others",
            "beneficiary_physical_address",
            "beneficiary_ever_in_us",
            "beneficiary_employment",
            "beneficiary_proceedings",
            "petitioner_prior_petitions",
            "petitioner_statement_language",
            "petitioner_contact",
            "preparer_block",
            "preparer_statement",
        ):
            self.assertEqual(self.allowed(key), ["filled"], key)
        for key in SIGNATURES:
            self.assertEqual(self.allowed(key)[:2], ["pending_signature", "filled"], key)
        self.assertIn("not_applicable", self.allowed("interpreter_signature"))

    def test_complete_plans_have_no_schema_findings(self) -> None:
        for posture, not_applicable in POSTURES.items():
            with self.subTest(posture=posture):
                findings = audit.schema_findings(
                    pdf_path=Path("/x/I-130.pdf"),
                    kind="i-130",
                    questions=complete_plan(SCHEMA, dict.fromkeys(not_applicable, "not_applicable"))["questions"],
                    manifest_entry={"question_schema": SCHEMA},
                )
                self.assertEqual(findings, [])

    def test_core_questions_cannot_be_skipped(self) -> None:
        skipped = dict.fromkeys(["beneficiary_petitioned_by_others", "petitioner_contact"], "not_applicable")
        questions = complete_plan(SCHEMA, skipped)["questions"]
        findings = audit.schema_findings(
            pdf_path=Path("/x/I-130.pdf"), kind="i-130", questions=questions, manifest_entry={"question_schema": SCHEMA}
        )
        self.assertEqual(
            sorted(f["question_key"] for f in findings if f["title"].startswith("Question plan uses an invalid status")),
            ["beneficiary_petitioned_by_others", "petitioner_contact"],
        )


class I130SchemaMeetsAuditTests(unittest.TestCase):
    """The schema and audit_i130 require the same boxes."""

    def setUp(self) -> None:
        self.questions = get_question_schema(SCHEMA)["required_questions"]

    def audit_required(self) -> tuple[set[str], set[str]]:
        """(relationship boxes, other boxes) the audit reports as missing on an otherwise blank form whose
        addresses are abroad, so only the boxes it requires of every filing are left."""
        abroad = {"X": "1", "Pt2Line10_Country": "Canada", "Pt4Line11_Country": "Mexico"}
        findings = audit.audit_form("i-130", Path("/tmp/i130.pdf"), abroad, xfa={}, acro={})
        relationship: set[str] = set()
        others: set[str] = set()
        for item in findings:
            if item["severity"] != "error":
                continue
            target = relationship if "relationship" in item["title"] else others
            target.update(item.get("fields", []))
        return relationship, others

    def test_audit_required_boxes_are_required_by_the_schema(self) -> None:
        relationship, others = self.audit_required()
        self.assertTrue(relationship and others)
        # The audit wants any one of the four relationship boxes: exactly relationship_basis's boxes.
        self.assertEqual(relationship, set(self.questions["relationship_basis"]["required_fields"]))
        required_when_filled = {
            field
            for spec in self.questions.values()
            if spec.get("allowed_statuses", ["filled"]) == ["filled"]
            for field in spec.get("required_nonempty_fields_when_filled", [])
        }
        self.assertEqual(others - required_when_filled, set())

    def test_us_addresses_need_state_zip_and_street(self) -> None:
        def missing(values: dict[str, str]) -> set[str]:
            findings = audit.audit_form("i-130", Path("/tmp/i130.pdf"), values, xfa={}, acro={})
            return {f for item in findings if item["severity"] == "error" for f in item.get("fields", [])}

        us = missing({"X": "1", "Pt2Line10_Country": "United States", "Pt4Line11_Country": "USA"})
        self.assertLessEqual({"Pt2Line10_State", "Pt2Line10_ZipCode", "Pt4Line11_StreetNumberName"}, us)
        abroad = missing({"X": "1", "Pt2Line10_Country": "Canada", "Pt4Line11_Country": "Mexico"})
        self.assertFalse({"Pt2Line10_State", "Pt2Line10_ZipCode", "Pt4Line11_StreetNumberName"} & abroad)

    def test_signature_boxes_the_audit_warns_about_belong_to_signature_questions(self) -> None:
        findings = audit.audit_form("i-130", Path("/tmp/i130.pdf"), {"X": "1"}, xfa={}, acro={})
        warned = {f for item in findings if item["title"] == "Signature fields are still blank" for f in item["fields"]}
        signature_boxes = set(self.questions["petitioner_signature"]["required_fields"]) | set(
            self.questions["preparer_signature"]["required_fields"]
        )
        self.assertEqual(warned, signature_boxes)

    def test_required_boxes_satisfy_the_audit(self) -> None:
        values: dict[str, str] = {"Pt1Line1_Spouse": "Y"}
        for item in skeleton_plan(SCHEMA)["questions"]:
            if item["allowed_statuses"] != ["filled"]:
                continue
            for field in item["required_nonempty_fields_when_filled"]:
                options = item.get("choices", {}).get(field, {})
                if options:
                    values[field] = next(iter(options.values()))
                elif "Date" in field:
                    values[field] = "01/02/2000"
                else:
                    values[field] = "Sample"
        findings = audit.audit_form("i-130", Path("/tmp/i130.pdf"), values, xfa=values, acro=values)
        self.assertEqual([item for item in findings if item["severity"] == "error"], [])


if __name__ == "__main__":
    unittest.main()

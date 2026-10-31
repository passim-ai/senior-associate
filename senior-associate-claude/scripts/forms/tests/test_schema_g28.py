#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Offline tests for the G-28 question schema (09/17/18 edition). All values are fictional.

    uv run --script tests/test_schema_g28.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import audit_prepared_forms as audit  # noqa: E402
from official_blanks import complete_plan  # noqa: E402
from form_question_schema import get_question_schema, load_field_list, skeleton_plan  # noqa: E402

SCHEMA = "g28_represented_client"
# Global fields: every widget of the name is one data node, so the schema names them once, by base name.
GLOBAL_BASES = {
    "Pt1Line2a_FamilyName", "Pt1Line2b_GivenName", "Pt1Line2c_MiddleName",
    "Pt3Line5a_FamilyName", "Pt3Line5b_GivenName", "Pt3Line5c_MiddleName",
    "Line3b_Unit", "Line12b_Unit", "Line4_Checkbox",
}
SIGNATURES = {"client_signature", "attorney_signature", "law_student_signature"}
OPTIONAL = {
    "attorney_uscis_online_account", "accredited_representative", "associated_attorney", "law_student",
    "client_account_numbers", "client_notice_elections", "law_student_signature", "additional_information",
}
# A fictional petitioner's G-28: every box the audit reads, answered.
ANSWERS = {
    "Pt1Line2a_FamilyName": "Counsel", "Pt1Line2b_GivenName": "Alex",
    "Line3a_StreetNumber": "100 Example Avenue", "Line3c_CityOrTown": "Springfield", "Line3d_State": "IL",
    "Line3e_ZipCode": "62701", "Line3h_Country": "USA", "Line4_DaytimeTelephoneNumber": "5555550100",
    "Line7_MobileTelephoneNumber": "alex@example.test", "CheckBox1": "Y",
    "Pt2Line1a_LicensingAuthority": "Supreme Court of Illinois", "Pt2Line1b_BarNumber": "00000000",
    "Pt2Line1d_NameofFirmOrOrganization": "Example Law PLLC", "Line1a_USCIS": "Y",
    "Line1b_ListFormNumber": "I-130, I-864", "Line4_Checkbox": "P",
    "Pt3Line5a_FamilyName": "Sample", "Pt3Line5b_GivenName": "Jane",
    "Line9_DaytimeTelephoneNumber": "5555550111", "Line10_MobileTelephoneNumber": "5555550112",
    "Line11_EMail": "jane@example.test", "Line12a_StreetNumberName": "200 Sample Street",
    "Line12c_CityOrTown": "Springfield", "Line12d_State": "IL", "Line12e_ZipCode": "62702",
    "Line12h_Country": "USA",
}


def base(field: str) -> str:
    return field.split("[")[0]


class G28SchemaTests(unittest.TestCase):
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
        # The two repeated, non-global names in Part 6 are claimed box by box.
        owned = {field for spec in self.questions.values() for field in spec["required_fields"]}
        for name in ("Pt9Line6a_PageNumber", "Pt9Line6b_PartNumber", "Pt9Line6c_ItemNumber", "Pt9Line6d_AdditionalInfo"):
            self.assertLessEqual({f"{name}[0]", f"{name}[1]"}, owned)

    def test_discipline_question_offers_am_not_and_am(self) -> None:
        spec = self.questions["attorney_discipline"]
        self.assertEqual(spec["choices"], {"Checkbox1dAmNot": {"am not": "Y"}, "Checkbox1dAm": {"am": "N"}})
        self.assertNotIn("not_applicable", spec.get("allowed_statuses", ["filled"]))
        self.assertIn("subject_to_discipline_order", spec["field_notes"]["Checkbox1dAmNot"])
        self.assertIn("discipline_order_details", spec["field_notes"]["Checkbox1dAm"])

    def test_attorney_boxes_name_their_profile_key(self) -> None:
        # The README's attorney-profile table, box by box.
        profile = {
            "Pt1Line1_USCISOnlineAcctNumber": "uscis_online_account_number",
            "Pt1Line2a_FamilyName": "attorney_name",
            "Pt1Line2b_GivenName": "attorney_name",
            "Pt1Line2c_MiddleName": "attorney_name",
            "Line3a_StreetNumber": "mailing_address",
            "Line3b_Unit": "mailing_address",
            "Line3b_AptSteFlrNumber": "mailing_address",
            "Line3c_CityOrTown": "mailing_address",
            "Line3d_State": "mailing_address",
            "Line3e_ZipCode": "mailing_address",
            "Line3h_Country": "mailing_address",
            "Line4_DaytimeTelephoneNumber": "phone",
            "Line7_MobileTelephoneNumber": "email",
            "Pt2Line1a_LicensingAuthority": "licensing_authority",
            "Pt2Line1b_BarNumber": "bar_number",
            "Pt2Line1d_NameofFirmOrOrganization": "firm_name",
            "Checkbox1dAmNot": "subject_to_discipline_order",
            "Checkbox1dAm": "subject_to_discipline_order",
        }
        for field, key in profile.items():
            with self.subTest(field=field):
                self.assertIn(f"Profile key {key}", self.questions[self.owner(field)]["field_notes"][field])

    def test_misleading_boxes_are_pinned(self) -> None:
        attorney = self.questions["attorney_block"]["field_notes"]
        self.assertIn("MOBILE", attorney["Line6_EMail"])
        self.assertIn("EMAIL", attorney["Line7_MobileTelephoneNumber"])
        self.assertEqual(self.owner("Line3_Date"), "attorney_signature")
        self.assertEqual(self.owner("Pt5Line2b_DateofSignature"), "law_student_signature")
        self.assertEqual(self.owner("P5_Line6a_SignatureofApplicant"), "client_signature")
        self.assertEqual(self.owner("Pt4Line2a_CheckBox2a"), "client_notice_elections")
        self.assertIn("ACCREDITATION", self.questions["accredited_representative"]["field_notes"]["Line2c_DateExpires"])
        role = self.questions["representation_scope"]["choices"]["Line4_Checkbox"]
        self.assertEqual(role["Respondent (ICE, CBP)"], "B")
        self.assertEqual(role["Beneficiary/Derivative"], "BD")
        # Part 6 item 5 pairs the [1] page/part/item boxes with the [0] text box, and item 6 the reverse.
        part6 = self.questions["additional_information"]["field_notes"]
        self.assertIn("Pt9Line6d_AdditionalInfo[0]", part6["Pt9Line6a_PageNumber[1]"])
        self.assertIn("Pt9Line6d_AdditionalInfo[1]", part6["Pt9Line6a_PageNumber[0]"])
        self.assertIn("VAWA", self.questions["client_mailing_address"]["field_notes"]["Line12a_StreetNumberName"])

    def test_statuses(self) -> None:
        for key, spec in self.questions.items():
            allowed = spec.get("allowed_statuses", ["filled"])
            with self.subTest(question=key):
                self.assertEqual("not_applicable" in allowed, key in OPTIONAL)
                if key in SIGNATURES:
                    self.assertLessEqual({"pending_signature", "filled"}, set(allowed))

    def test_schema_agrees_with_the_audit(self) -> None:
        values: dict[str, str] = {}
        for item in skeleton_plan(SCHEMA)["questions"]:
            if item["key"] in OPTIONAL or "filled" not in item["allowed_statuses"]:
                continue
            for field in item["required_nonempty_fields_when_filled"]:
                values[field] = ANSWERS.get(field, "Zztest")
        # Every box the audit requires is required by the schema, so a complete plan clears it.
        missing = [name for name in ANSWERS if name not in values and name not in {
            "Line10_MobileTelephoneNumber", "Line11_EMail", "Line12d_State", "Line12e_ZipCode"}]
        self.assertEqual(missing, [])
        values.update(ANSWERS)
        findings = audit.audit_form("g-28", Path("/x/G-28.pdf"), values, xfa=values, acro=values)
        self.assertEqual([f["title"] for f in findings], ["Signature fields are still blank"])
        # The I-130A attorney-box check reads these G-28 boxes; the schema requires each of them.
        for key, field in audit.G28_FIELDS.items():
            with self.subTest(g28_field=key):
                self.assertIn(field, self.questions[self.owner(field)]["required_nonempty_fields_when_filled"])

    def test_complete_plans_have_no_schema_findings(self) -> None:
        minimal = {key: "not_applicable" for key in OPTIONAL}
        for statuses in ({}, minimal):
            with self.subTest(minimal=bool(statuses)):
                findings = audit.schema_findings(
                    pdf_path=Path("/x/G-28.pdf"),
                    kind="g-28",
                    questions=complete_plan(SCHEMA, statuses, answers=ANSWERS)["questions"],
                    manifest_entry={"question_schema": SCHEMA},
                )
                self.assertEqual(findings, [])

    def test_attorney_and_client_parts_cannot_be_skipped(self) -> None:
        skipped = ["attorney_block", "attorney_discipline", "attorney_eligibility", "client_contact"]
        questions = complete_plan(SCHEMA, {key: "not_applicable" for key in skipped}, answers=ANSWERS)["questions"]
        findings = audit.schema_findings(
            pdf_path=Path("/x/G-28.pdf"), kind="g-28", questions=questions, manifest_entry={"question_schema": SCHEMA}
        )
        self.assertEqual(
            sorted(f["question_key"] for f in findings if f["title"].startswith("Question plan uses an invalid status")),
            sorted(skipped),
        )


if __name__ == "__main__":
    unittest.main()

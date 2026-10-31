#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Tests for the I-907 schema (04/01/24 edition) and its audit, on the official blank. Values are fictional.

    uv run --script tests/test_schema_i907.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit_prepared_forms as audit  # noqa: E402
from form_question_schema import get_question_schema  # noqa: E402

SCHEMA = "i907_premium_processing"

# A self-petitioner's NIW I-140 filed with its I-907: no company, the same person in Part 1 item 3 and
# Part 2 items 4-5, no receipt number yet.
SELF_PETITION = {
    "Part1_Line8_CheckBox": "A", "P2_Line1_FormNumberof": "I-140", "P2_Line2_ClassorEligRequested": "E21 NIW",
    "Pt1Line3_FamilyName": "Sample", "Pt1Line3_GivenName": "Alex",
    "Part2_Line4_PetitionerApplicantFamilyName": "Sample", "Part2_Line4_PetitionerApplicantGivenName": "Alex",
    "Line_FamilyName": "Sample", "Line_GivenName": "Alex",
    "Part1_Line5_MailingAddress_StreetNumberName": "100 Example Way", "Part1_Line5_MailingAddress_CityTown": "Springfield",
    "Part1_Line5_MailingAddress_State": "IL", "Part1_Line5_MailingAddress_ZipCode": "62701",
    "Part1_Line5_MailingAddress_Country": "United States", "Part1Line6_Checkbox": "Y", "P3_Line1_Checkbox": "Y",
    "P3_Line4_DaytimeTelePhoneNumber": "2175550142",
}


def titles(severity: str, **changes: str) -> list[str]:
    values = {**SELF_PETITION, **changes}
    return [f["title"] for f in audit.audit_form("i-907", Path("/x.pdf"), {k: v for k, v in values.items() if v})
            if f["severity"] == severity]


def errors(**changes: str) -> list[str]:
    return titles("error", **changes)


class I907SchemaTests(unittest.TestCase):

    def test_misnamed_boxes_are_in_the_right_questions(self) -> None:
        questions = get_question_schema(SCHEMA)["required_questions"]
        self.assertIn("Part1_Line8_NameOfCompanyPOC_FamilyName", questions["company_contact_and_ein"]["required_fields"])
        self.assertIn("Part1_Line9_CompanyIRSTaxNumber", questions["company_contact_and_ein"]["required_fields"])  # item 7
        self.assertIn("Part1_Line7_OtherInformationAboutCompanyOrg_StreetNumberName",
                      questions["related_address"]["required_fields"])  # Part 2 item 8
        self.assertIn("P2_Line2_ClassorEligRequested", questions["related_case"]["required_fields"])  # item 3
        self.assertIn("Line_FamilyName", questions["related_beneficiary"]["required_fields"])  # item 5
        self.assertIn("P3_Line5_MobileTelePhoneNumber[1]", questions["requestor_contact"]["required_fields"])  # fax
        self.assertIn("Pt5Line3_SignatureOfPetitioner", questions["requestor_signature"]["required_fields"])
        self.assertIn("P5_Line5_FaxNumber", questions["preparer_block"]["required_fields"])  # item 5, mobile
        self.assertIn("Pt10Line3b_AptSteFlrNumber", questions["preparer_block"]["required_fields"])
        choices = questions["request_type"]["choices"]["Part1_Line8_CheckBox"]
        self.assertEqual(list(choices.values()), ["A", "B", "C", "D"])  # printed order, top to bottom
        self.assertEqual(questions["requestor_statement"]["choices"]["P3_Line1_Checkbox"],
                         {"1.A I can read and understand English": "Y",
                          "1.B The interpreter named in Part 4 read it to me": "N"})

    def test_a_self_petitioners_niw_request_clears(self) -> None:
        self.assertEqual(errors(), [])
        self.assertEqual(titles("warning"), ["Signature fields are still blank"])

    def test_without_a_company_the_names_are_required_and_not_na(self) -> None:
        names = ("Without a company (Part 1 item 4), Part 1 item 3 and Part 2 items 4-5 need names, not blanks, N/A or "
                 "none")
        self.assertIn(names, errors(Line_FamilyName="N/A"))
        self.assertIn(names, errors(Pt1Line3_GivenName="none"))
        self.assertIn(names, errors(Part2_Line4_PetitionerApplicantFamilyName=""))
        # With a company named, N/A in item 4 is an answer; the beneficiary is still required.
        company = {"Part1_Line4_CompanyorOrganizationName": "Example Labs LLC", "Pt1Line3_FamilyName": "",
                   "Pt1Line3_GivenName": "", "Part2_Line4_PetitionerApplicantFamilyName": "N/A",
                   "Part2_Line4_PetitionerApplicantGivenName": "N/A"}
        self.assertNotIn(names, errors(**company))
        self.assertIn("The names in the related case (Part 2 items 4-5) are missing",
                      errors(**company, Line_FamilyName="", Line_GivenName=""))

    def test_who_may_request_it(self) -> None:
        self.assertIn("The beneficiary of the petition is requesting premium processing, which only the petitioner or "
                      "its attorney may",
                      errors(Part2_Line4_PetitionerApplicantFamilyName="Employer", Part2_Line4_PetitionerApplicantGivenName="Pat"))
        self.assertIn("Part 1 item 8 says the applicant requests it, but the I-140 is a petition",
                      errors(Part1_Line8_CheckBox="C"))
        self.assertIn("Part 1 item 8 (who is requesting premium processing) is not selected", errors(Part1_Line8_CheckBox=""))
        attorney = titles("warning", Part1_Line8_CheckBox="B")
        self.assertIn("Part 1 item 8 says an attorney requests it, but the G-28 box on page 1 isn't checked", attorney)
        self.assertNotIn("Part 1 item 8 says an attorney requests it, but the G-28 box on page 1 isn't checked",
                         titles("warning", Part1_Line8_CheckBox="B", FormG28Attach="1"))

    def test_the_related_case(self) -> None:
        self.assertIn("Part 2 item 1 names a form premium processing isn't designated for (the I-129, I-140, I-539 and "
                      "I-765 are)", errors(P2_Line1_FormNumberof="I-130"))
        self.assertIn("The related case's form number or classification (Part 2 items 1 and 3) is missing",
                      errors(P2_Line2_ClassorEligRequested=""))
        self.assertIn("Part 2 item 3 says E21 without NIW or non-NIW, which premium processing designates separately "
                      "(45 or 15 days)", titles("warning", P2_Line2_ClassorEligRequested="E21"))
        self.assertEqual([t for t in titles("warning", P2_Line2_ClassorEligRequested="E21 non-NIW") if "Part 2" in t], [])
        self.assertIn("Receipt number of the related case (Part 2 item 2) isn't 3 letters and 10 digits",
                      errors(P2_Line2_ReceiptNumberof="IOE12345"))
        # An upgrade (a receipt number) needs all of Part 2, the address in item 8 included.
        upgrade = errors(P2_Line2_ReceiptNumberof="IOE0123456789")
        self.assertIn("To upgrade a pending case, the address in the related case (Part 2 item 8) is incomplete", upgrade)
        self.assertNotIn("To upgrade a pending case, the address in the related case (Part 2 item 8) is incomplete",
                         errors(P2_Line2_ReceiptNumberof="IOE0123456789",
                                Part1_Line7_OtherInformationAboutCompanyOrg_StreetNumberName="100 Example Way",
                                Part1_Line7_OtherInformationAboutCompanyOrg_CityTown="Springfield",
                                Part1_Line7_OtherInformationAboutCompanyOrg_State="IL",
                                Part1_Line7_OtherInformationAboutCompanyOrg_ZipCode="62701",
                                Part1_Line7_OtherInformationAboutCompanyOrg_Country="United States"))

    def test_statement_contact_and_preparer(self) -> None:
        self.assertIn("Physical address (Part 1 item 7), needed with 'No' to item 6 is incomplete",
                      errors(Part1Line6_Checkbox="N"))
        self.assertIn("With Part 3 item 1.B, the language or the interpreter (Part 4) is missing",
                      errors(P3_Line1_Checkbox="N"))
        self.assertIn("Requestor's daytime telephone number (Part 3 item 3) is missing",
                      errors(P3_Line4_DaytimeTelePhoneNumber=""))
        self.assertIn("With Part 3 item 2, the preparer's name or Part 5 is missing", errors(P3_Line2_Checkbox="A"))
        preparer = {"P5_Line1_PreparerFamilyName": "Counsel", "P5_Line1_PreparerGivenName": "Jordan"}
        self.assertIn("Part 5 item 7 (7.A not an attorney, 7.B an attorney) is not answered", errors(**preparer))
        self.assertIn("Part 5 item 7.B (extends or does not extend beyond this request) is not answered",
                      errors(**preparer, P5_Line7b_Checkbox="B"))
        self.assertNotIn("Part 5 item 7.B (extends or does not extend beyond this request) is not answered",
                         errors(**preparer, P5_Line7b_Checkbox="B", P5_Line7b_notextends="2"))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Tests for the I-140 schema (06/07/24 edition) and its audit, on the official blank. Values are fictional.

    uv run --script tests/test_schema_i140.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit_prepared_forms as audit  # noqa: E402
from form_question_schema import get_question_schema  # noqa: E402
from official_blanks import official_blank, why_missing  # noqa: E402

SCHEMA = "i140_worker_petition"


class I140SchemaTests(unittest.TestCase):

    def test_repeated_rows_follow_the_page_not_the_index(self) -> None:
        questions = get_question_schema(SCHEMA)["required_questions"]
        four = questions["family_member_4"]["required_fields"]
        self.assertIn("Line2e_CountryOfBirth[4]", four)
        self.assertIn("Line2f_Relationship[4]", four)
        self.assertIn("Line2a_Person2FamilyName[2]", four)
        extra = questions["additional_information"]["required_fields"]
        self.assertLess(extra.index("Pt9Line6a_PageNumber[1]"), extra.index("Pt9Line6a_PageNumber[0]"))

    def test_audit_pairs_and_routes(self) -> None:
        both = {"Line5_Yes": "Y", "Line5_No": "N", "Line1a_Visa": "1a", "Line1c_Other": "Y"}
        titles = [f["title"] for f in audit.audit_form("i-140", Path("/x.pdf"), both) if f["severity"] == "error"]
        self.assertIn("Part 4 item 7 (removal proceedings): more than one box is checked where the form takes one", titles)
        self.assertIn("U.S. Embassy or Consulate for the visa (Part 4 items 1.b-1.c) is missing", titles)
        self.assertIn("Other type of petitioner is not explained", titles)
        company = audit.audit_form("i-140", Path("/x.pdf"), {"Line2_CompanyName": "Example Corp"})
        self.assertIn("A company petitioner's EIN or business details are missing", [f["title"] for f in company])

    def test_part_4_items_9_and_10_and_part_7_pairs(self) -> None:
        def errors(**values: str) -> list[str]:
            return [f["title"] for f in audit.audit_form("i-140", Path("/x.pdf"), values) if f["severity"] == "error"]

        both = "more than one box is checked where the form takes one"
        self.assertIn(f"Part 4 item 10 (duplicate labor certification): {both}", errors(Line8_Yes="Y", Line8_No="N"))
        self.assertIn("Part 4 item 10 (duplicate labor certification) is not answered", errors(Line7_Yes="Y"))
        self.assertNotIn("Part 4 item 10 (duplicate labor certification) is not answered", errors(Line7_No="N"))
        self.assertIn(f"Part 7 person 1 item 5 (applying for adjustment): {both}",
                      errors(Pt7ItemNumber5_CheckboxYes="Y", Pt7ItemNumber5_CheckboxNo="N"))
        listed = errors(**{"Line2a_Person2FamilyName[0]": "Sample", "Pt7ItemNumber11_CheckboxYes": "Y"})
        self.assertIn("Part 7 person 2 item 12 (applying for a visa abroad) is not answered", listed)
        self.assertNotIn("Part 7 person 2 item 11 (applying for adjustment) is not answered", listed)
        self.assertFalse([t for t in errors() if t.startswith("Part 7 person")])  # nobody listed, nothing asked

    def test_who_may_petition_and_the_employers_tax_number(self) -> None:
        def errors(**values: str) -> list[str]:
            return [f["title"] for f in audit.audit_form("i-140", Path("/x.pdf"), values) if f["severity"] == "error"]

        self_petition = "Self-petition in a category that needs a U.S. employer (only 1.a and 1.h may self-petition)"
        self.assertIn(self_petition, errors(Line1b_Self="Y", prt2PetitionType="f"))
        for category in ("a", "h"):
            self.assertNotIn(self_petition, errors(Line1b_Self="Y", prt2PetitionType=category))
        no_number = "An individual employer's EIN or SSN (Part 1 item 4 or 7) is missing"
        individual = {"Pt1Line1a_FamilyName": "Sample", "Pt1Line1b_GivenName": "Alex", "Line1a_Employer": "Y",
                      "prt2PetitionType": "g"}
        self.assertIn(no_number, errors(**individual))
        self.assertNotIn(no_number, errors(**individual, Line7_SSN="123456789"))
        self.assertNotIn(no_number, errors(**individual, Pt1Line3_TaxNumber="123456789"))
        self.assertNotIn(no_number, errors(Line1b_Self="Y", prt2PetitionType="a"))  # no job offer, no employer

    def test_a_self_petition_is_the_beneficiarys_own_with_the_answers_uscis_expects(self) -> None:
        def errors(**values: str) -> list[str]:
            return [f["title"] for f in audit.audit_form("i-140", Path("/x.pdf"), values) if f["severity"] == "error"]

        unanswered = ("Part 1 items 5 and 6 (nonprofit or governmental research; 25 or fewer employees) are not "
                      "answered")
        wrong = "A self-petitioner answers No to Part 1 item 5 and Yes to item 6"
        other_person = "A self-petition's petitioner (Part 1) and beneficiary (Part 3) are different people"
        no_occupation = "An individual petitioner's occupation (Part 5 item 11) is missing"
        same = {"Pt1Line1a_FamilyName": "Sample", "Pt1Line1b_GivenName": "Alex", "Pt3Line1a_FamilyName": "SAMPLE",
                "Pt3Line1b_GivenName": " Alex ", "Line1b_Self": "Y", "prt2PetitionType": "h"}
        self.assertIn(unanswered, errors(Line2_CompanyName="Example Corp"))  # every petitioner answers them
        self.assertIn(unanswered, errors(**same))
        right = errors(**same, P1_Line5_Checkbox="N", P1_Line6_Checkbox="Y", Line3a_Occupation="Engineer")
        for title in (unanswered, wrong, other_person, no_occupation):
            self.assertNotIn(title, right)
        self.assertIn(wrong, errors(**same, P1_Line5_Checkbox="N", P1_Line6_Checkbox="N"))
        self.assertIn(no_occupation, errors(**same))
        self.assertIn(other_person, errors(**{**same, "Pt3Line1b_GivenName": "Jordan"}))
        self.assertIn("A self-petition names a company as the petitioner",
                      errors(**same, Line2_CompanyName="Example Corp"))
        # An employer's NIW petition is a company's, with no self-petitioner answers to check.
        employer = errors(Line2_CompanyName="Example Corp", Line1a_Employer="Y", prt2PetitionType="h",
                          P1_Line5_Checkbox="N", P1_Line6_Checkbox="N")
        self.assertNotIn(wrong, employer)
        self.assertNotIn(no_occupation, employer)

    def test_the_wage_box_takes_cents_after_a_period(self) -> None:
        import formats

        notes = get_question_schema(SCHEMA)["required_questions"]["proposed_employment"]["field_notes"]
        self.assertIn("45.67", notes["Line8_Wages"])
        self.assertNotIn("Digits only", notes["Line8_Wages"])
        blank = official_blank("i-140")
        if blank is None:
            self.skipTest(why_missing("i-140"))
        box = formats.box_formats(blank)
        self.assertEqual((box["Line8_Wages"], box["Line3b_AnnualIncome"]), (formats.AMOUNT, formats.NUMBER))
        self.assertIsNone(formats.check(formats.AMOUNT, "45.67"))
        self.assertIsNone(formats.check(formats.AMOUNT, "150000"))
        self.assertIsNone(formats.check(formats.AMOUNT, "0.00000000"))  # a blank's calculated total
        for wrong in ("$45.67", "150,000", "45,67", "45.67 per hour"):
            self.assertIsNotNone(formats.check(formats.AMOUNT, wrong), wrong)
        self.assertIsNotNone(formats.check(formats.NUMBER, "85,000"))
        self.assertIsNone(formats.check(formats.NUMBER, "85000"))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Tests for the I-601A schema (01/20/25 edition) and its audit, on the official blank. Values are fictional.

    uv run --script tests/test_schema_i601a.py
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit_prepared_forms as audit  # noqa: E402
from form_question_schema import get_question_schema  # noqa: E402

SCHEMA = "i601a_provisional_waiver"


def titles(severity: str, **values: str) -> list[str]:
    return [f["title"] for f in audit.audit_form("i-601a", Path("/x.pdf"), values) if f["severity"] == severity]


def errors(**values: str) -> list[str]:
    return titles("error", **values)


class I601ASchemaTests(unittest.TestCase):

    def test_an_impossible_date_is_not_a_crash(self) -> None:
        # 02/30/2001 is no day: the box rules report it, and the rest of the audit still runs.
        self.assertIsNone(audit.parse_us_date("02/30/2001"))
        self.assertIsNone(audit.age_from_dob("02/30/2001"))
        audit.audit_form("i-601a", Path("/x.pdf"), {"Pt1Line3_DOB": "02/30/2001"})

    def test_misnamed_boxes_are_in_the_right_questions(self) -> None:
        questions = get_question_schema(SCHEMA)["required_questions"]
        self.assertIn("Pt1Checkbox25_Checkbox", questions["other_previous_entries"]["required_fields"])  # item 26
        self.assertIn("Pt1Checkbox30_Checkbox", questions["voluntary_departure"]["required_fields"])  # item 31
        self.assertIn("Pt1Checkbox31_Checkbox", questions["criminal_history"]["required_fields"])  # item 32
        self.assertIn("Pt1Checkbox38a_Checkbox", questions["security_and_human_rights"]["required_fields"])  # item 39.a
        self.assertIn("Pt2Line4_HeightInches1", questions["biographic_information"]["required_fields"])  # weight
        self.assertIn("Pt3Line6a_DV_KCCCaseNumber", questions["dv_case"]["required_fields"])  # item 2.a
        self.assertIn("Pt3Line2a_FamilyName[0]", questions["dv_case"]["required_fields"])  # DV selectee, 2.b
        self.assertIn("Pt3Line2a_FamilyName[1]", questions["immigrant_visa_petition"]["required_fields"])  # petitioner, 3.c
        self.assertIn("Pt6Line2_Name", questions["applicant_statement"]["required_fields"])  # the preparer's name
        self.assertIn("Pt7Line6_NameOfLanguage", questions["interpreter_block"]["required_fields"])
        self.assertIn("Pt7Line6a_Signature", questions["interpreter_signature"]["required_fields"])  # item 7.a
        eyes = questions["biographic_information"]["choices"]["Pt2Checkbox5"]
        self.assertEqual((eyes["Gray"], eyes["Green"]), ("GRN", "GRY"))  # keyed by the printed label (form defect)
        unit = questions["mailing_address"]["choices"]["Pt1Line7c_Unit"]
        self.assertEqual(unit, {"Apt.": " APT", "Ste.": "STE", "Flr.": " FLR"})

    def test_audit_ineligibility_on_the_face_of_the_form(self) -> None:
        closed = "Part 1 item 28.b: removal proceedings that are not administratively closed (or are back on EOIR's " \
                 "calendar) make the applicant ineligible"
        self.assertIn(closed, errors(Pt1Checkbox27="Y", Pt1Checkbox28="B"))
        self.assertNotIn(closed, errors(Pt1Checkbox27="Y", Pt1Checkbox28="A"))
        self.assertIn("Part 1 item 28.a or 28.b (are the removal proceedings administratively closed) is not selected",
                      errors(Pt1Checkbox27="Y"))
        self.assertIn("Follow-up answers are given although the question before them is not answered Yes",
                      errors(Pt1Checkbox27="N", Pt1Checkbox28="A"))
        warned = [f["title"] for f in audit.audit_form("i-601a", Path("/x.pdf"), {"Pt1Checkbox30_Checkbox": "Y"})
                  if f["severity"] == "warning"]
        self.assertIn("Part 1 item 31: an unexpired grant of voluntary departure, which the instructions list as making "
                      "the applicant ineligible", warned)
        self.assertNotIn("Part 1 item 31", " ".join(errors(Pt1Checkbox30_Checkbox="Y")))
        self.assertIn("Part 1 item 30.b: a final decision reinstating a prior order makes the applicant ineligible",
                      errors(Pt1Checkbox30a_Checkbox="Y", Pt1Checkbox30b_Checkbox="Y"))
        self.assertIn("Part 1 item 30.b (a final reinstatement decision) is not answered", errors(Pt1Checkbox30a_Checkbox="Y"))
        no_i212 = "A final order (Part 1 item 29.a) without an approved I-212: its receipt number (item 29.b) is missing"
        self.assertIn(no_i212, titles("warning", Pt1Checkbox29a_Checkbox="Y"))
        self.assertNotIn(no_i212, titles("warning", Pt1Checkbox29a_Checkbox="Y", Pt1Line29b_ReceiptNumber="ZLA0123456789"))

    def test_audit_rejection_grounds_and_the_relatives(self) -> None:
        minor = f"01/15/{date.today().year - 10}"
        self.assertIn("The applicant is under 17 (Part 1 item 11); USCIS rejects an I-601A filed before 17",
                      errors(Pt1Line11_DateOfBirth=minor))
        self.assertIn("U.S. physical address (Part 1 items 9.a-9.e) is missing", errors(Pt1Line8_Checkbox="N"))
        self.assertNotIn("U.S. physical address (Part 1 items 9.a-9.e) is missing", errors(Pt1Line8_Checkbox="Y"))
        self.assertIn("The approved petition's receipt number or the NVC case number (Part 3 items 3.a-3.b) is missing",
                      errors(Pt3Line4_Option2="2"))
        self.assertIn("The DV case number (Part 3 item 2.a) is missing", errors(Pt3Line4_Option1="1"))
        self.assertIn("Part 3 item 1 (the basis for the immigrant visa, 1.a-1.e): more than one box is checked where the "
                      "form takes one", errors(Pt3Line4_Option1="1", Pt3Line4_Option3="3"))
        self.assertIn("Part 4 item 2 (U.S. citizen or LPR spouse or parent) is not answered", errors())
        self.assertIn("The other qualifying relative's name (Part 4 items 4.a-4.b) is missing", errors(Pt4Line3_Checkbox="Y"))
        unexplained = "The Part 9 explanation of a 'Yes' to Part 1 item 26 or items 32-45 is missing"
        self.assertIn(unexplained, errors(Pt1Checkbox34_Checkbox="Y"))  # item 35, charges or convictions
        self.assertNotIn(unexplained, errors(Pt1Checkbox34_Checkbox="Y",
                                             Pt9Line3d_AdditionalInfo="A 2015 citation in Springfield, dismissed."))


if __name__ == "__main__":
    unittest.main()

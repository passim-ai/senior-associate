#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Tests for the I-601 schema (01/20/25 edition) and its audit, on the official blank. Values are fictional.

    uv run --script tests/test_schema_i601.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit_prepared_forms as audit  # noqa: E402
from form_question_schema import get_question_schema  # noqa: E402

SCHEMA = "i601_inadmissibility_waiver"
# A Section A (adjustment or immigrant visa) applicant: the T/SIJ and TPS grounds don't apply.
NOT_SECTION_A = ["t_or_sij_grounds", "tps_health_grounds", "tps_criminal_grounds", "tps_fraud_or_false_claim",
                 "tps_smuggling_or_civil_penalty", "tps_other_grounds"]

# A small adjustment applicant's answers (fictional), complete apart from what each test removes.
BASE = {
    "p1Line3aFamilyName": "Sample", "p1Line3bGivenName": "Alex", "p1Line9Gender": "F", "p1Line10DateofBirth": "01/02/1990",
    "p1Line11CityOrTownOfBirth": "Exampleton", "p1Line13CountryOfBirth": "Atlantis", "p1Line14CountryOfCitzOrNat": "Atlantis",
    "p1Line5StreetNumberName": "100 Example Street", "p1Line5CityOrTown": "Springfield", "p1Line5State": "IL",
    "p1Line5ZipCode": "62701", "p1Line5Country": "United States", "p1Line6YesNo": "Y",
    "p1Line16aYesNo": "N", "p1Line17aYesNo": "N", "p1Line18aYesNo": "N", "p1Line19YesNo": "N",
    "p4Line15CB": "Y", "p4Line40Explanation": "Overstayed a B-2 admission from 2015 to 2017.",
    "p5Line1aFamilyName": "Sample", "p5Line1bGivenName": "Jordan", "p5Line2StreetNumberName": "100 Example Street",
    "p5Line2CityOrTown": "Springfield", "p5Line2State": "IL", "p5Line2ZipCode": "62701", "p5Line2Country": "United States",
    "p5Line5Relationship": "U.S. citizen spouse", "p5Line6ImmigrationStatus": "U.S. citizen",
    "p5Line8DateofBirth": "03/04/1988", "p5Line9ApplicantStatement": "See attached letter.",
    "p6Line9ApplicantStatement": "See attached letter.",
}


def titles(values: dict[str, str]) -> list[str]:
    return [f["title"] for f in audit.audit_form("i-601", Path("/x.pdf"), values) if f["severity"] == "error"]


class I601SchemaTests(unittest.TestCase):

    def test_misnamed_boxes_are_in_the_right_questions(self) -> None:
        questions = get_question_schema(SCHEMA)["required_questions"]
        self.assertIn("p1Line1dCityOrTown", questions["most_recent_entry"]["required_fields"])
        self.assertIn("Pt7Line6a_SignatureofApplicant", questions["applicant_signature"]["required_fields"])
        self.assertIn("p8Line7Signature", questions["interpreter_signature"]["required_fields"])
        self.assertIn("P8Language", questions["interpreter_block"]["required_fields"])
        # Eye color: the printed "Gray" box stores GRN and "Green" stores GRY.
        eyes = questions["biographic_info"]["choices"]["p3Line5EyeColor"]
        self.assertEqual((eyes["Gray"], eyes["Green"]), ("GRN", "GRY"))
        # Every ground the applicant doesn't claim can be not_applicable.
        for key in ("health_grounds", "criminal_grounds", "fraud_misrepresentation", "unlawful_presence", *NOT_SECTION_A):
            self.assertIn("not_applicable", questions[key]["allowed_statuses"], key)

    def test_audit_passes_a_complete_unlawful_presence_waiver(self) -> None:
        self.assertEqual(titles(BASE), [])

    def test_audit(self) -> None:
        relative = {key: value for key, value in BASE.items() if not key.startswith("p5Line")}
        found = titles({**relative, "p4Line23CB": "Y", "p4Line40Explanation": ""})
        self.assertIn("Part 5 names no qualifying relative for Part 4 item 15", found)
        self.assertIn("Part 5 item 9 has no extreme hardship statement for Part 4 item 15", found)
        self.assertIn("Part 4 selects grounds in more than one section (A (immigrant visa, adjustment other than T or SIJ, "
                      "K or V); C (TPS))", found)
        self.assertIn("Part 4 item 40, the statement of the acts, convictions or medical conditions and their dates, is "
                      "blank", found)
        # A VAWA self-petitioner claiming hardship to self needs no relative.
        self.assertNotIn("Part 5 names no qualifying relative for Part 4 item 15", titles({**relative, "p5VAWACB": "Y"}))
        found = titles({**BASE, "p4Line15CB": "", "p4Line18CB": "Y", "p1Line16aYesNo": "Y", "p1Line6YesNo": "N",
                        "p1Line19YesNo": "", "p6Line9ApplicantStatement": ""})
        self.assertIn("Part 4 item 18 is checked but does not say which ground", found)
        self.assertIn("Part 1 item 16.a is Yes, but the I-485 receipt number (item 16.b) is missing", found)
        self.assertIn("Physical address (Part 1 items 7.a-7.h) is incomplete", found)
        self.assertIn("Part 1 item 19 (an I-212 filed with this application) is not answered", found)
        self.assertIn("The discretion statement (Part 6 item 9) is blank", found)
        self.assertIn("No ground of inadmissibility is selected in Part 4 (items 1-39)",
                      titles({**BASE, "p4Line15CB": ""}))
        self.assertIn("Qualifying relative (Part 5 items 1.a-8) is incomplete", titles({**BASE, "p5Line8DateofBirth": ""}))


if __name__ == "__main__":
    unittest.main()

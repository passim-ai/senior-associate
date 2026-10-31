#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Tests for the I-612 schema (04/01/24 edition) and its audit, on the official blank. Values are fictional.

    uv run --script tests/test_schema_i612.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit_prepared_forms as audit  # noqa: E402
from form_question_schema import get_question_schema  # noqa: E402

SCHEMA = "i612_foreign_residence_waiver"


class I612SchemaTests(unittest.TestCase):

    def test_misnamed_boxes_are_in_the_right_questions(self) -> None:
        questions = get_question_schema(SCHEMA)["required_questions"]
        self.assertIn("P1_L4a_FamilyName[1]", questions["spouse"]["required_fields"])
        self.assertIn("P4_L4_DateOfBirth", questions["exchange_program"]["required_fields"])
        self.assertIn("P1_L7c_CityTown[2]", questions["lpr_relative"]["required_fields"])

    def test_audit(self) -> None:
        values = {"Part3_Line1_Checkboxes": "Departure", "Part2_Checkboxes[0]": "B", "Part1_Line8_MaritalStatus": "M "}
        titles = [f["title"] for f in audit.audit_form("i-612", Path("/x.pdf"), values)]
        self.assertIn("The hardship ground names no U.S. citizen or permanent resident spouse or child (Part 4 items 8-22)", titles)
        self.assertIn("The agency or country that gave the grant (Part 2 item 2.b) is missing", titles)
        self.assertIn("A married applicant does not say whether the spouse is included (Part 4 item 7)", titles)


if __name__ == "__main__":
    unittest.main()

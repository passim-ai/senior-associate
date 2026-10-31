#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Tests for the I-693 applicant's-part schema (01/20/25 edition) and its audit, on the official blank. Values are fictional.

    uv run --script tests/test_schema_i693.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit_prepared_forms as audit  # noqa: E402
from form_question_schema import get_question_schema  # noqa: E402

SCHEMA = "i693_applicant_part"


class I693SchemaTests(unittest.TestCase):
    def test_leaves_the_civil_surgeon_alone(self) -> None:
        questions = get_question_schema(SCHEMA)["required_questions"]
        self.assertEqual(questions["civil_surgeon_parts"]["allowed_statuses"], ["not_applicable"])
        self.assertEqual(questions["applicant_signature"]["allowed_statuses"], ["pending_signature"])
        self.assertIn("Pt5Line2_IDNumber", questions["civil_surgeon_parts"]["required_fields"])

    def test_audit_flags_values_in_the_civil_surgeons_parts(self) -> None:
        values = {"Pt1Line1a_FamilyName": "Sample", "Pt5Line2_IDNumber": "X123"}
        findings = audit.audit_form("i-693", Path("/x.pdf"), values)
        self.assertIn("Boxes for the civil surgeon or the applicant's signature hold values typed by the firm",
                      [f["title"] for f in findings])


if __name__ == "__main__":
    unittest.main()

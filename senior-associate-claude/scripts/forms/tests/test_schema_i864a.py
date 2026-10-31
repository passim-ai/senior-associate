#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Tests for the I-864A schema (08/24/26 edition) and its audit, on the official blank. Values are fictional.

    uv run --script tests/test_schema_i864a.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit_prepared_forms as audit  # noqa: E402
from form_question_schema import get_question_schema  # noqa: E402

SCHEMA = "i864a_household_member"


class I864ASchemaTests(unittest.TestCase):

    def test_signature_boxes_go_to_their_signers(self) -> None:
        questions = get_question_schema(SCHEMA)["required_questions"]
        self.assertIn("Pt2Line6_ApplicantSignature[0]", questions["sponsor_signature"]["required_fields"])
        self.assertIn("Pt2Line6_ApplicantSignature[1]", questions["member_signature"]["required_fields"])
        self.assertIn("P2_Line5_SSN", questions["intending_immigrant_4"]["required_fields"])

    def test_audit(self) -> None:
        titles = [f["title"] for f in audit.audit_form("i-864a", Path("/x.pdf"), {
            "P2_Line1-3_Checkbox": "C", "P4_Line3_Assets": "1000", "P4_Line6_TotalAssets": "5000"})]
        self.assertIn("How the household member is related to the sponsor (Part 2 item 3) is missing", titles)
        self.assertIn("Total assets (Part 4 item 6) is not the sum of items 3-5", titles)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Tests for the I-129F schema (01/20/25 edition) and its audit, on the official blank. Values are fictional.

    uv run --script tests/test_schema_i129f.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit_prepared_forms as audit  # noqa: E402
from form_question_schema import get_question_schema  # noqa: E402

SCHEMA = "i129f_fiance_petition"


class I129FSchemaTests(unittest.TestCase):

    def test_an_empty_visible_layer_is_a_mismatch(self) -> None:
        # Once, the I-129F alone read stored values for an empty visible layer, so it never saw this.
        stored = {"Pt1Line6a_FamilyName": "Sample"}
        titles = [f["title"] for f in audit.audit_form("i-129f", Path("/x.pdf"), stored, xfa=stored, acro={})]
        self.assertIn("Visible I-129F output does not reflect stored answers", titles)

    def test_misleading_boxes_are_pinned(self) -> None:
        questions = get_question_schema(SCHEMA)["required_questions"]
        self.assertIn("Pt6Line4_Signature", questions["petitioner_signature"]["required_fields"])
        self.assertIn("Pt1Line11_DateofBirth", questions["beneficiary_parent_1"]["required_fields"])
        self.assertEqual(questions["petitioner_mailing_address"]["choices"]["Pt1Line8_Unit"]["Apt."], " FLR ")
        self.assertEqual(questions["beneficiary_mailing_address"]["choices"]["Pt2Line11_Unit"]["Apt."], " APT ")
        eyes = questions["biographic_info"]["choices"]["Pt4Line5_Checkbox"]
        self.assertEqual((eyes["Gray"], eyes["Green"]), ("GRN", "GRY"))

    def test_audit_follows_the_classification_and_the_yes_answers(self) -> None:
        base = {
            "Pt1Line4a_Checkboxes": "B", "Pt2Line51_Checkboxes": "Y", "Pt2Line53_Checkboxes": "A",
            "Pt1Line37_Checkboxes": "Y",
        }
        titles = [f["title"] for f in audit.audit_form("i-129f", Path("/x.pdf"), base) if f["severity"] == "error"]
        self.assertIn("K-3 petition does not say whether an I-130 was filed (Part 1 item 5)", titles)
        self.assertIn("Part 2 items 51 and 53 must be N/A for a K-3 spouse, and only then", titles)
        self.assertIn("Petitioner's previous spouse is not described", titles)
        abroad = audit.audit_form("i-129f", Path("/x.pdf"), {
            "Pt1Line9_StreetNumberName": "5 Harbour Road", "Pt1Line9_CityOrTown": "Port Example",
            "Pt1Line9_Country": "Examplestan"})
        self.assertFalse([f for f in abroad if "address 1" in f["title"]])
        here = audit.audit_form("i-129f", Path("/x.pdf"), {
            "Pt1Line9_StreetNumberName": "1 Main St", "Pt1Line9_CityOrTown": "Sampleton",
            "Pt1Line9_Country": "United States"})
        self.assertEqual([f["fields"] for f in here if "address 1" in f["title"]], [["Pt1Line9_State", "Pt1Line9_ZipCode"]])

    def test_the_classification_fits_the_i130_the_waiver_and_the_marital_status(self) -> None:
        def errors(**values: str) -> list[str]:
            return [f["title"] for f in audit.audit_form("i-129f", Path("/x.pdf"), values) if f["severity"] == "error"]

        k3 = {"Pt1Line4a_Checkboxes": "B", "Pt1Line5_Checkboxes": "Y", "Pt3Line5_Checkboxes": "D",
              "Pt1Line23_Checkbox": "M", "Pt2Line6_Checkboxes": "M"}
        rules = ("I-130", "waiver", "married", "free to marry", "4.b")
        self.assertEqual([t for t in errors(**k3) if any(word in t for word in rules)], [])
        self.assertIn("K-3 petition says no I-130 was filed (Part 1 item 5); a K-3 needs one filed for the spouse",
                      errors(**{**k3, "Pt1Line5_Checkboxes": "N"}))
        self.assertIn("A K-3 spouse petition asks for a multiple-filer waiver (Part 3 item 5); it takes 5.d",
                      errors(**{**k3, "Pt3Line5_Checkboxes": "A"}))
        self.assertIn("K-3 spouse petition, but the beneficiary (Part 2 item 6) is not shown as married",
                      errors(**{**k3, "Pt2Line6_Checkboxes": "S"}))
        k1 = {"Pt1Line4a_Checkboxes": "A", "Pt1Line23_Checkbox": "D", "Pt2Line6_Checkboxes": "S", "Pt3Line5_Checkboxes": "A"}
        self.assertEqual([t for t in errors(**k1) if any(word in t for word in rules)], [])
        self.assertIn("K-1 petition, but the petitioner (Part 1 item 23) is married; both must be free to marry",
                      errors(**{**k1, "Pt1Line23_Checkbox": "M"}))
        self.assertIn("Other arrests or convictions (Part 3 item 4.b) are not described",
                      errors(**{**k1, "Part3Line4a_Checkboxes": "Y"}))
        self.assertNotIn("Other arrests or convictions (Part 3 item 4.b) are not described",
                         errors(**{**k1, "Part3Line4a_Checkboxes": "Y", "Pt3Line4B_Describe": "A 2015 citation, dismissed."}))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Offline tests for the I-765 question schema (08/21/25 edition). All values are fictional.

    uv run --script tests/test_schema_i765.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import audit_prepared_forms as audit  # noqa: E402
from form_question_schema import get_question_schema, load_field_list, skeleton_plan  # noqa: E402

SCHEMA = "i765_work_authorization"
CATEGORY_SPECIFIC = (
    "stem_opt_c3c",
    "h4_spouse_c26",
    "pending_asylum_c8_arrests",
    "compelling_circumstances_c35_c36",
    "abc_settlement_c8",
)


class I765SchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = get_question_schema(SCHEMA)
        self.assertIsNotNone(self.schema)
        self.questions = self.schema["required_questions"]
        self.fields = load_field_list(self.schema["field_list"])["fields"]

    def test_category_specific_questions_may_be_not_applicable(self) -> None:
        for key in CATEGORY_SPECIFIC + ("physical_address", "other_names_used", "interpreter_block", "preparer_block"):
            self.assertIn("not_applicable", self.questions[key]["allowed_statuses"], key)
        for key in ("applicant_signature", "interpreter_signature", "preparer_signature"):
            self.assertIn("pending_signature", self.questions[key]["allowed_statuses"], key)
            self.assertIn("filled", self.questions[key]["allowed_statuses"], key)

    def test_misleading_boxes_are_pinned(self) -> None:
        # Other names: item 3 is index [1], item 4 is index [0].
        notes = self.questions["other_names_used"]["field_notes"]
        self.assertIn("Item 3.a", notes["Line3a_FamilyName[1]"])
        self.assertIn("Item 4.a", notes["Line3a_FamilyName[0]"])
        # Part 6 item 3.d is the second Pt6Line4d box.
        self.assertIn("Pt6Line4d_AdditionalInfo[1]", self.questions["additional_information"]["required_nonempty_fields_when_filled"])
        # Page 5 unit boxes: on-states differ from the printed labels.
        for key, field in (("interpreter_block", "Pt5Line3b_Unit"), ("preparer_block", "Pt6Line3b_Unit")):
            self.assertEqual(
                self.questions[key]["choices"][field], {"apt": " FLR ", "ste": " APT ", "flr": " STE "}
            )
        self.assertEqual(self.questions["sex"]["choices"]["Line9_Checkbox"], {"male": "Y", "female": "N"})
        self.assertIn("Pt4Line6_Checkbox", self.questions["abc_settlement_c8"]["required_fields"])

    def test_complete_c9_plan_has_no_schema_findings(self) -> None:
        plan = skeleton_plan(SCHEMA)
        for question in plan["questions"]:
            key = question["key"]
            if key in CATEGORY_SPECIFIC or key in ("physical_address", "interpreter_block", "interpreter_signature"):
                question["status"] = "not_applicable"
                continue
            if "pending_signature" in question["allowed_statuses"]:
                question["status"] = "pending_signature"
                continue
            question["status"] = "filled"
            for field in question["field_values"]:
                choices = question.get("choices", {}).get(field)
                question["field_values"][field] = next(iter(choices.values())) if choices else "X1"
        category = next(q for q in plan["questions"] if q["key"] == "eligibility_category")
        category["field_values"].update({"section_1": "c", "section_2": "9", "section_3": ""})
        findings = audit.schema_findings(
            pdf_path=Path("/x/I-765.pdf"),
            kind="i-765",
            questions=plan["questions"],
            manifest_entry={"question_schema": SCHEMA},
        )
        self.assertEqual(findings, [])

        stem = next(q for q in plan["questions"] if q["key"] == "stem_opt_c3c")
        stem["status"] = "filled"
        findings = audit.schema_findings(
            pdf_path=Path("/x/I-765.pdf"),
            kind="i-765",
            questions=plan["questions"],
            manifest_entry={"question_schema": SCHEMA},
        )
        self.assertTrue(
            any(
                f["title"] == "Question plan leaves required form values blank" and f["question_key"] == "stem_opt_c3c"
                for f in findings
            )
        )


if __name__ == "__main__":
    unittest.main()

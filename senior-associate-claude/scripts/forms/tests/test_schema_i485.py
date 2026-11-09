#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Offline tests for the I-485 question schemas (09/18/26 edition). All values are fictional.

    uv run --script tests/test_schema_i485.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import audit_prepared_forms as audit  # noqa: E402
from form_question_schema import (  # noqa: E402
    SCHEMA_I485_EMPLOYMENT_DERIVATIVE_CHILD,
    SCHEMA_I485_EMPLOYMENT_PRINCIPAL,
    get_question_schema,
    load_field_list,
    skeleton_plan,
)

FAMILY = "i485_family_based"
ASYLEE = "i485_asylee_refugee"
SCHEMAS = (FAMILY, ASYLEE, SCHEMA_I485_EMPLOYMENT_PRINCIPAL, SCHEMA_I485_EMPLOYMENT_DERIVATIVE_CHILD)

# Part 2 item 3 boxes that belong to other categories, per posture.
CATEGORY_BOXES = {
    "family": {"Pt2Line3a_CB"},
    "employment": {"Pt2Line3b_CB140", "Pt2Line3b_CB526", "Pt2Line3b_CB140Assoc", "Pt2Relative_CB", "Pt2RelativeType_CB"},
    "asylee": {"Pt2Line3d_AsyleeRefugeeCB", "Pt2Line3d_Asylum", "Pt2Line3d_Refugee"},
    "other": {"Pt2Line3c_CB", "Pt2Line3e_CB", "Pt2Line3f_CB", "Pt2Line3g_CB", "Pt2Line1g_DV", "Pt2Line1g_OtherEligibility"},
}
POSTURE = {
    FAMILY: "family",
    ASYLEE: "asylee",
    SCHEMA_I485_EMPLOYMENT_PRINCIPAL: "employment",
    SCHEMA_I485_EMPLOYMENT_DERIVATIVE_CHILD: "employment",
}


def base(field: str) -> str:
    return field.split("[")[0]


class I485SchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.known = load_field_list("I-485.json")["fields"]

    def test_all_four_postures_exist_on_the_current_edition(self) -> None:
        for name in SCHEMAS:
            schema = get_question_schema(name)
            self.assertIsNotNone(schema, name)
            self.assertEqual(schema["kind"], "i-485")
            self.assertEqual(schema["edition"], "09/18/26")
            self.assertEqual(schema["field_list"], "I-485.json")
            self.assertTrue(schema["description"])

    def test_every_box_a_preparer_answers_is_covered(self) -> None:
        """Only Part 13 (completed at the interview), barcodes, containers and other categories' Part 2
        boxes may be left out of a schema."""
        on_form = {
            name
            for name, entry in self.known.items()
            if entry["type"] and name != "PDF417BarCode2" and not name.startswith("Pt13_")
        }
        for name in SCHEMAS:
            with self.subTest(schema=name):
                covered = {
                    base(field)
                    for spec in get_question_schema(name)["required_questions"].values()
                    for field in spec.get("required_fields", [])
                }
                other_categories = set().union(
                    *(boxes for posture, boxes in CATEGORY_BOXES.items() if posture != POSTURE[name])
                )
                # Item 4 (INA 245(i)) covers only family, employment, special immigrant and DV filings.
                not_asked = {"Pt2Line4_CB"} if POSTURE[name] == "asylee" else set()
                self.assertEqual(on_form - covered - other_categories - not_asked, set())
                self.assertEqual(covered & other_categories, set())

    def test_no_box_belongs_to_two_questions(self) -> None:
        """The plan merges filled questions into one mapping, so a shared box would depend on order."""
        for name in SCHEMAS:
            seen: dict[str, str] = {}
            for key, spec in get_question_schema(name)["required_questions"].items():
                for field in spec.get("required_fields", []):
                    with self.subTest(schema=name, field=field):
                        self.assertNotIn(field, seen, f"{field} in {seen.get(field)} and {key}")
                    seen[field] = key

    def test_field_list_keeps_names_with_a_literal_dot(self) -> None:
        """Items 42.a and 42.b are named Pt8Line42\\.a_YesNo in the PDF. A field list made by splitting
        on every dot stores them as a_YesNo and b_YesNo, and the schema check fails."""
        for name in ("Pt8Line42.a_YesNo", "Pt8Line42.b_YesNo"):
            self.assertEqual(sorted(self.known[name]["states"]), ["N", "Y"])
        self.assertNotIn("a_YesNo", self.known)

    def test_shared_questions_name_the_same_boxes_in_every_posture(self) -> None:
        schemas = [get_question_schema(name)["required_questions"] for name in SCHEMAS]
        shared = set.intersection(*(set(questions) for questions in schemas)) - {"filing_category"}
        for key in shared:
            with self.subTest(question=key):
                fields = {tuple(questions[key]["required_fields"]) for questions in schemas}
                self.assertEqual(len(fields), 1)

    def test_posture_specific_statuses(self) -> None:
        def allowed(name: str, key: str) -> list[str]:
            return get_question_schema(name)["required_questions"][key].get("allowed_statuses", ["filled"])

        self.assertEqual(allowed(ASYLEE, "public_charge_factors"), ["not_applicable"])
        self.assertEqual(allowed(ASYLEE, "public_benefits"), ["not_applicable"])
        self.assertIn("filled", allowed(FAMILY, "public_charge_factors"))
        self.assertEqual(allowed(SCHEMA_I485_EMPLOYMENT_PRINCIPAL, "principal_applicant"), ["not_applicable"])
        self.assertEqual(allowed(SCHEMA_I485_EMPLOYMENT_DERIVATIVE_CHILD, "principal_applicant"), ["filled"])
        self.assertNotIn("Pt2Line4_CB", get_question_schema(ASYLEE)["required_questions"]["filing_category"]["required_fields"])
        for name in SCHEMAS:
            self.assertEqual(allowed(name, "applicant_signature"), ["pending_signature", "filled"])

    def test_misleading_part9_names_point_at_the_right_items(self) -> None:
        notes = get_question_schema(FAMILY)["required_questions"]["part9_fraud_and_misrepresentation"]["field_notes"]
        self.assertTrue(notes["Pt9Line67_YesNo"].startswith("Item 65"))
        self.assertTrue(notes["Pt9Line73_YesNo"].startswith("Item 71"))
        unlawful = get_question_schema(FAMILY)["required_questions"]["part9_removal_and_unlawful_presence"]
        self.assertTrue(unlawful["field_notes"]["Pt9Line76_YesNo"].startswith("Item 74"))
        self.assertNotIn("Pt9Line77_YesNo", unlawful["required_nonempty_fields_when_filled"])  # item 75 is conditional


# Answers a typical filing gives, per posture, on top of the schema's required non-empty boxes.
# The audit also wants at least one of the five race boxes; "if any" boxes (mobile, email) stay blank.
COMMON_ANSWERS = {
    "Pt1Line3_DOB": "01/02/1990",
    "Pt1Line18_YN": "Y",
    "Pt1Line18_last5yrs_YN": "Y",
    "Pt2Line11_CB": "11A",
    "Pt6Line1_MaritalStatus": "1",
    "Pt5Line2_YNNA": "A",
    "Pt6Line3_TimesMarried": "None",
    "Pt6Line1_TotalChildren": "None",
    "Pt7Line2_Race[1]": "WH",
    "Pt7Line2_Race[2]": "BL",
}
POSTURE_ANSWERS = {
    FAMILY: {"Pt2Line2_CB": "1fA", "Pt2Line3a_CB": "3a0", "Pt3Line1_CB": "5", "Pt9Line56_CB": "23",
             "Pt9Line61_CB": "7"},  # not exempt: items 57-62, with a bachelor's degree in item 61
    ASYLEE: {
        "Pt2Line2_CB": "1fA",
        "Pt2Line3d_AsyleeRefugeeCB": "3d0",
        "Pt2Line3d_Asylum": "04/04/2023",
        "Pt3Line1_CB": "4",
        "Pt9Line56_CB": "3",
    },
    SCHEMA_I485_EMPLOYMENT_PRINCIPAL: {
        "Pt2Line2_CB": "1fA",
        "Pt2Line3b_CB140": "3b4",
        "Pt3Line1_CB": "4",
        "Pt9Line56_CB": "23",
        "Pt9Line61_CB": "7",
    },
    SCHEMA_I485_EMPLOYMENT_DERIVATIVE_CHILD: {
        "Pt2Line2_CB": "1fB",
        "Pt2Line3b_CB140": "3b4",
        "Pt2Line2_AlienNumber": "000000001",
        "Pt3Line1_CB": "4",
        "Pt9Line56_CB": "23",
        "Pt9Line61_CB": "7",
    },
}
NOT_APPLICABLE = {"current_spouse", "prior_spouse", "mailing_address", "interpreter", "additional_information"}


class I485SchemaMeetsAuditTests(unittest.TestCase):
    """A plan that fills exactly the boxes the schema requires clears the audit's own I-485 checks."""

    def values_for(self, name: str) -> dict[str, str]:
        answers = {**COMMON_ANSWERS, **POSTURE_ANSWERS[name]}
        values: dict[str, str] = {}
        for item in skeleton_plan(name)["questions"]:
            if item["key"] in NOT_APPLICABLE or "filled" not in item["allowed_statuses"]:
                continue
            for field in item["required_nonempty_fields_when_filled"]:
                options = item.get("choices", {}).get(field, {})
                note = item.get("field_notes", {}).get(field, "")
                if field in answers:
                    values[field] = answers[field]
                elif options == {"Yes": "Y", "No": "N"}:
                    values[field] = "N"
                elif options:
                    values[field] = next(iter(options.values()))
                elif "mm/dd/yyyy" in note or "Date" in field or "DOB" in field:
                    values[field] = "01/02/2000"
                else:
                    values[field] = "Sample"
        values.update({field: value for field, value in answers.items() if field not in values})
        values.update({"Pt5Line3_DateofBirth": "01/01/1970", "Pt5Line8_DateofBirth[0]": "01/01/1971"})
        return values

    def test_required_boxes_satisfy_the_audit(self) -> None:
        for name in SCHEMAS:
            with self.subTest(schema=name):
                values = self.values_for(name)
                findings = audit.audit_form("i-485", Path("/tmp/i485.pdf"), values, xfa=values, acro=values)
                errors = [item for item in findings if item.get("severity") == "error"]
                self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

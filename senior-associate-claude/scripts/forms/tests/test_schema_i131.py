#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Offline tests for the I-131 question schemas (01/20/25 edition). All values are fictional.

    uv run --script tests/test_schema_i131.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import audit_prepared_forms as audit  # noqa: E402
from form_question_schema import (  # noqa: E402
    get_question_schema,
    load_field_list,
    skeleton_plan,
)

ADVANCE_PAROLE = "i131_advance_parole_pending_i485"
TRAVEL_DOCUMENT = "i131_travel_document"
SCHEMAS = (ADVANCE_PAROLE, TRAVEL_DOCUMENT)

# Questions of i131_travel_document that only some application types answer.
TYPE_SPECIFIC = (
    "tps_travel_authorization",
    "advance_parole_basis",
    "initial_parole_program",
    "reparole_program",
    "admission_details",
    "beneficiary_identity",
    "beneficiary_other_names",
    "beneficiary_mailing_address",
    "beneficiary_physical_address",
    "beneficiary_admission_details",
    "replacement_request",
    "replacement_details",
    "document_delivery",
    "pickup_notification",
    "reentry_permit_time_outside",
    "refugee_country_and_travel",
    "refugee_conduct_since_status",
    "refugee_filing_location",
    "proposed_travel",
    "parole_request",
    "reparole_employment_authorization",
)
# Boxes an advance parole applicant (Part 1 item 5.A) never answers, by field-name prefix.
NOT_ADVANCE_PAROLE = (
    "P1_Line4",
    "P1_Line5B",
    "P1_Line5C",
    "P1_Line5E",
    "P1_Line5F",
    "P1_Line5G",
    "P1_Line5H",
    "P1_Line5I",
    "P1_Line5J",
    "P1_Line5K",
    "P1_Line5L",
    "P1_Line5M",
    "P1_Line6",
    "P1_Line8",
    "P1_Line10",
    "P1_Line12",
    "P2_Line",  # Part 2 items 16-27 (filing for someone else)
    "Part2_Line17_",
    "P4_Line7",
    "P4_Line8",
    "P4_Line9",
    "P5_",
    "P6_",
    "Line4c_",
    "P8_",
    "P9_",
)


def base(field: str) -> str:
    return field.split("[")[0]


def questions(name: str) -> dict[str, dict]:
    return get_question_schema(name)["required_questions"]


def fill_plan(name: str, not_applicable: set[str], values: dict[str, dict[str, str]]) -> list[dict]:
    """A skeleton plan with every question answered: not_applicable, pending signature, or filled with
    the first choice or a placeholder, then the given values on top."""
    plan = skeleton_plan(name)
    for question in plan["questions"]:
        key = question["key"]
        if key in not_applicable:
            question["status"] = "not_applicable"
            continue
        if "pending_signature" in question["allowed_statuses"]:
            question["status"] = "pending_signature"
            continue
        question["status"] = "filled"
        for field in question["field_values"]:
            choices = question.get("choices", {}).get(field)
            question["field_values"][field] = next(iter(choices.values())) if choices else "X1"
        question["field_values"].update(values.get(key, {}))
    return plan["questions"]


def schema_findings(name: str, plan_questions: list[dict]) -> list[dict]:
    return audit.schema_findings(
        pdf_path=Path("/x/I-131.pdf"),
        kind="i-131",
        questions=plan_questions,
        manifest_entry={"question_schema": name},
    )


class I131SchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.known = load_field_list("I-131.json")["fields"]

    def test_advance_parole_covers_every_box_it_answers_and_no_other(self) -> None:
        def skipped(field: str) -> bool:
            return field.startswith(NOT_ADVANCE_PAROLE)

        covered: dict[str, str] = {}
        for key, spec in questions(ADVANCE_PAROLE).items():
            for field in spec["required_fields"]:
                self.assertNotIn(base(field), covered, f"{field} in {covered.get(base(field))} and {key}")
                covered[base(field)] = key
        on_form = {name for name, entry in self.known.items() if entry.get("type") and name != "PDF417BarCode1"}
        self.assertEqual({f for f in on_form - set(covered) if not skipped(f)}, set())
        self.assertEqual({f for f in covered if skipped(f)}, set())
        self.assertEqual(
            questions(ADVANCE_PAROLE)["application_type"]["choices"]["CB_AppType"],
            {"5.A. Advance Parole Document: a pending Form I-485": "5"},
        )

    def test_every_checkbox_has_a_choice_for_each_on_state(self) -> None:
        for name in SCHEMAS:
            for key, spec in questions(name).items():
                for field in spec["required_fields"]:
                    if self.known[base(field)]["type"] != "/Btn":
                        continue
                    with self.subTest(schema=name, question=key, field=field):
                        choices = spec.get("choices", {}).get(field, {})
                        self.assertTrue(choices)
                        if name == TRAVEL_DOCUMENT:
                            self.assertEqual(sorted(choices.values()), sorted(self.known[base(field)]["states"]))

    def test_shared_questions_name_the_same_boxes(self) -> None:
        advance, travel = questions(ADVANCE_PAROLE), questions(TRAVEL_DOCUMENT)
        self.assertLessEqual(set(advance), set(travel))
        for key in set(advance) - {"advance_parole_basis"}:
            with self.subTest(question=key):
                self.assertEqual(advance[key]["required_fields"], travel[key]["required_fields"])
        self.assertEqual(advance["advance_parole_basis"]["required_fields"], ["P1_Line5A"])

    def test_statuses_by_posture(self) -> None:
        travel = questions(TRAVEL_DOCUMENT)
        for key in TYPE_SPECIFIC + ("other_names_used", "physical_address", "interpreter_block"):
            self.assertIn("not_applicable", travel[key]["allowed_statuses"], key)
        for name in SCHEMAS:
            for key in ("applicant_signature", "preparer_signature", "interpreter_signature"):
                allowed = questions(name)[key]["allowed_statuses"]
                self.assertIn("pending_signature", allowed, key)
                self.assertIn("filled", allowed, key)
        advance = questions(ADVANCE_PAROLE)
        self.assertEqual(advance["proposed_travel"]["allowed_statuses"], ["pending_client_input", "filled"])
        for key in ("application_type", "admission_details", "replacement_request"):
            self.assertNotIn("allowed_statuses", advance[key], key)  # filled only

        self.assertEqual(advance["removal_proceedings"]["allowed_statuses"], ["filled", "pending_client_input"])

    def test_advance_parole_schema_agrees_with_the_audit(self) -> None:
        """Every box audit_i131 requires for a 5.A filing is non-empty when its question is filled, and
        those questions can't be marked not_applicable."""
        findings = audit.audit_form("i-131", Path("/x/I-131.pdf"), {"CB_AppType": "5"}, xfa={}, acro={})
        required = {field for f in findings if f["severity"] == "error" for field in f["fields"]}
        self.assertIn("P7_Line2_Purpose", required)
        nonempty = {
            field: key
            for key, spec in questions(ADVANCE_PAROLE).items()
            for field in spec.get("required_nonempty_fields_when_filled", [])
        }
        for field in sorted(required):
            with self.subTest(field=field):
                self.assertIn(field, nonempty)
                allowed = questions(ADVANCE_PAROLE)[nonempty[field]].get("allowed_statuses", ["filled"])
                self.assertNotIn("not_applicable", allowed)
        signatures = {field for f in findings if f["severity"] == "warning" for field in f["fields"]}
        declared = {field for spec in questions(ADVANCE_PAROLE).values() for field in spec["required_fields"]}
        self.assertLessEqual(signatures, declared)

    def test_misleading_boxes_are_pinned(self) -> None:
        travel = questions(TRAVEL_DOCUMENT)
        types = travel["application_type"]["choices"]["CB_AppType"]
        self.assertEqual(len(types), 37)
        self.assertEqual(types["5.B. Advance Parole Document: a pending Form I-589"], "6")
        self.assertTrue(next(k for k, v in types.items() if v == "18").startswith("6.A."))
        self.assertTrue(next(k for k, v in types.items() if v == "37").startswith("11."))
        self.assertIn("DAYTIME PHONE", travel["pickup_notification"]["field_notes"]["P4_Line9b_Email"])
        self.assertIn("Admit Until", travel["reparole_program"]["field_notes"]["P1_Line12_DateOfAdmission"])
        conduct = travel["refugee_conduct_since_status"]["choices"]
        self.assertEqual((conduct["Line4c_Yes"], conduct["Line4c_No"]), ({"Yes": "Y"}, {"No": "Y"}))
        self.assertEqual(
            sorted(travel["document_delivery"]["choices"]["P4_Line7a"].values()), ["A", "B"]
        )
        self.assertEqual(travel["applicant_identity"]["choices"]["Part2_Line8_Gender"], {"Male": "M", "Female": "F"})
        self.assertEqual(travel["mailing_address"]["choices"]["Part2_Line3_Unit"]["Apt."], " APT ")

    def test_delcarmen_lara_flag_sits_on_the_trip_purpose(self) -> None:
        for name in SCHEMAS:
            note = questions(name)["proposed_travel"]["field_notes"]["P7_Line2_Purpose"]
            with self.subTest(schema=name):
                self.assertIn("Delcarmen-Lara", note)
                self.assertIn("ATTORNEY REVIEW", note)

    def test_complete_advance_parole_plan_has_no_schema_findings(self) -> None:
        plan = fill_plan(
            ADVANCE_PAROLE,
            {"advance_parole_basis", "physical_address", "replacement_details", "interpreter_block", "interpreter_signature"},
            {"application_type": {"CB_AppType": "5"}},
        )
        self.assertEqual(schema_findings(ADVANCE_PAROLE, plan), [])

        travel = next(q for q in plan if q["key"] == "proposed_travel")
        travel["field_values"]["P7_Line5_ExpectedLengthTrip"] = ""
        findings = schema_findings(ADVANCE_PAROLE, plan)
        self.assertEqual([(f["question_key"], f["fields"]) for f in findings], [("proposed_travel", ["P7_Line5_ExpectedLengthTrip"])])

        travel["status"] = "not_applicable"
        findings = schema_findings(ADVANCE_PAROLE, plan)
        self.assertEqual([f["title"] for f in findings], ["Question plan uses an invalid status for a required form section"])

    def test_complete_reentry_permit_plan_has_no_schema_findings(self) -> None:
        reentry_only = {"replacement_request", "document_delivery", "reentry_permit_time_outside"}
        not_applicable = (set(TYPE_SPECIFIC) - reentry_only) | {
            "physical_address",
            "other_names_used",
            "interpreter_block",
            "interpreter_signature",
            "pickup_notification",
        }
        plan = fill_plan(TRAVEL_DOCUMENT, not_applicable, {"application_type": {"CB_AppType": "1"}})
        self.assertEqual(schema_findings(TRAVEL_DOCUMENT, plan), [])
        for key in ("application_type", "refugee_status", "biographic_information", "prior_documents"):
            question = next(q for q in plan if q["key"] == key)
            question["status"] = "not_applicable"
        findings = schema_findings(TRAVEL_DOCUMENT, plan)
        self.assertEqual(
            sorted(f["question_key"] for f in findings),
            ["application_type", "biographic_information", "prior_documents", "refugee_status"],
        )


if __name__ == "__main__":
    unittest.main()

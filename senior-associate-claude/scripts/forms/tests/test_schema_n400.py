#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""N-400 question schema checks, against the stored 01/20/25 field list. Offline; no PDF needed.

Run through test_forms_gate.py, which loads every tests/test_schema_*.py.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from form_question_schema import get_question_schema, load_field_list  # noqa: E402

SCHEMA = "n400_naturalization"
# Fields the schema leaves out on purpose: the barcode, and the current address's To box, which is
# read-only and pre-printed PRESENT (its From box, index [1], is in the schema).
EXCLUDED_BASES = {"PDF417BarCode1"}
# Global fields: every [n] is one data node, so the schema names them once, by base name.
GLOBAL_BASES = {"Line1_AlienNumber", "P2_Line1_FamilyName", "P2_Line1_GivenName", "P2_Line1_MiddleName"}


def base(field: str) -> str:
    return field.split("[")[0]


class N400SchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = get_question_schema(SCHEMA)
        self.assertIsNotNone(self.schema)
        self.known = load_field_list(self.schema["field_list"])["fields"]
        self.questions = self.schema["required_questions"]

    def declared(self) -> list[tuple[str, str]]:
        return [(key, field) for key, spec in self.questions.items() for field in spec["required_fields"]]

    def test_no_box_is_claimed_by_two_questions(self) -> None:
        owner: dict[str, str] = {}
        for key, field in self.declared():
            name = base(field) if base(field) in GLOBAL_BASES else field
            self.assertNotIn(name, owner, f"{field} is in {owner.get(name)} and {key}")
            owner[name] = key

    def test_global_fields_are_named_once_by_base(self) -> None:
        for _key, field in self.declared():
            if base(field) in GLOBAL_BASES:
                self.assertEqual(field, base(field))

    def test_repeated_names_split_across_parts_use_the_right_index(self) -> None:
        fields = {key: set(spec["required_fields"]) for key, spec in self.questions.items()}
        self.assertIn("P7_From1[0]", fields["children"])  # first child's date of birth
        self.assertIn("P7_From1[1]", fields["employment_and_schools"])  # first job's From date
        self.assertIn("P7_OccupationFieldStudy1[2]", fields["employment_and_schools"])
        self.assertIn("P11_Line1_TotalChildren[0]", fields["children_count"])
        self.assertIn("P11_Line1_TotalChildren[1]", fields["fee_reduction_household"])  # Part 10 item 4
        self.assertIn("P4_Line1_State[0]", fields["current_physical_address"])
        self.assertIn("P4_Line1_State[1]", fields["mailing_address"])
        self.assertIn("P4_Line3_From1[1]", fields["prior_addresses"])  # row 1 To date
        self.assertIn("P4_Line1_DatesofResidence[1]", fields["current_physical_address"])  # From
        self.assertNotIn("P4_Line1_DatesofResidence[0]", fields["current_physical_address"])  # PRESENT
        # P12_SignatureApplicant [0], [1], [2] are the applicant's, interpreter's and preparer's boxes.
        self.assertIn("P12_SignatureApplicant[0]", fields["applicant_signature"])
        self.assertIn("P12_SignatureApplicant[1]", fields["interpreter_signature"])
        self.assertIn("P12_SignatureApplicant[2]", fields["preparer_signature"])

    def test_part9_questions_cover_items_1_to_37(self) -> None:
        part9 = [field for key, field in self.declared() if key.startswith("part9_") and key != "part9_offense_table"]
        yes_no = [field for field in part9 if self.known[base(field)]["states"] in (["Y", "N"], ["N", "Y"])]
        # 1-4, 5.a-b, 6.a-c, 7.a-g, 8.a-b, 9, 10.a-c, 11-14, 15.a-b, 16, 17.a-h, 18-21, 22.a-b,
        # 23-25, 26.a-d, 27-29, 30.a-b, 31-37
        self.assertEqual(len(yes_no), 4 + 2 + 3 + 7 + 2 + 1 + 3 + 4 + 2 + 1 + 8 + 4 + 2 + 3 + 4 + 3 + 2 + 7)

    def test_signatures_and_optional_parts_have_the_right_statuses(self) -> None:
        for key in ("applicant_signature", "interpreter_signature", "preparer_signature"):
            self.assertIn("pending_signature", self.questions[key]["allowed_statuses"])
        for key in ("current_spouse", "current_spouse_employer", "prior_addresses", "children", "trips_outside_us",
                    "part9_offense_table", "interpreter_block", "preparer_block", "additional_information"):
            self.assertIn("not_applicable", self.questions[key]["allowed_statuses"], key)
        self.assertEqual(self.questions["interview_and_oath_signatures"]["allowed_statuses"], ["not_applicable"])


if __name__ == "__main__":
    unittest.main()

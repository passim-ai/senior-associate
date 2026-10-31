"""Question schema for Form I-693, Report of Immigration Medical Examination and Vaccination Record:
the applicant's side only (Parts 1-4).

Built against the 01/20/25 edition (uscis.gov/i-693 and the PDF footer, checked 2026-10-29: for a
civil surgeon signature on or after July 3, 2025, USCIS accepts only the 01/20/25 edition). Field
list: schemas/fields/I-693.json.

The firm prepares Part 1 (information about the applicant), Part 2's contact details, and the
interpreter and preparer blocks if any; the applicant takes the form to the civil surgeon. The
instructions say not to sign until the civil surgeon says so, and to sign in the civil surgeon's
presence, so the applicant's signature is always pending. Parts 5-10 (and the matching boxes of
Part 11) belong to the civil surgeon and the health department: they are one question here that
allows only not_applicable, and the audit reports any of their boxes that holds a value. The
civil surgeon returns the form in a sealed envelope, which USCIS returns if it was opened.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from _common import DATE, FILLED_OR_NA, NOT_APPLICABLE, PENDING_SIGNATURE, UNIT, q

PHONE = "Digits only (maxlen 10)."
FIELD_LIST = "I-693.json"


def applicant_questions() -> dict[str, dict[str, Any]]:
    return {
        "applicant_name": q(
            "Part 1, Item 1: Applicant's full legal name (no nickname)",
            ["Pt1Line1a_FamilyName", "Pt1Line1b_GivenName", "Pt1Line1c_MiddleName"],
            ["Pt1Line1a_FamilyName", "Pt1Line1b_GivenName"],
            notes={"Pt1Line1a_FamilyName": "Global: also fills the name header of every later page."},
        ),
        "physical_address": q(
            "Part 1, Item 2: Applicant's current physical address",
            ["Pt1Line2_StreetNumberName[1]", "Pt1Line2_StreetNumberName[0]", "Pt1Line2_Unit", "Pt1Line2_AptSteFlrNumber",
             "P1Line2_CityOrTown", "P1Line2_State", "P1Line2_ZipCode", "P1Line2_Province", "P1Line2_PostalCode",
             "P1Line2_Country"],
            ["Pt1Line2_StreetNumberName[0]", "P1Line2_CityOrTown", "P1Line2_Country"],
            notes={
                "Pt1Line2_StreetNumberName[1]": "The IN CARE OF name, if any (box [1] of the street name).",
                "Pt1Line2_StreetNumberName[0]": "Street number and name (box [0]; maxlen 34).",
                "P1Line2_State": "U.S. address only: 2-letter state code (drop-down).",
            },
            choices={"Pt1Line2_Unit": UNIT},
        ),
        "other_information": q(
            "Part 1, Item 3: Sex, date of birth, city and country of birth, A-Number and USCIS online account (if any)",
            ["Pt1Line3_Gender", "Pt1Line3_DateOfBirth", "Pt1Line3_CityTownVillageofBirth", "Pt1Line3_CountryofBirth",
             "Pt1Line3e_AlienNumber", "Pt1Line3f_USCISOnlineAcctNumber"],
            ["Pt1Line3_Gender", "Pt1Line3_DateOfBirth", "Pt1Line3_CityTownVillageofBirth", "Pt1Line3_CountryofBirth"],
            notes={"Pt1Line3_DateOfBirth": DATE,
                   "Pt1Line3e_AlienNumber": "If any: 9 digits, no 'A' (global: the header of every later page).",
                   "Pt1Line3f_USCISOnlineAcctNumber": "If any: 12 digits."},
            choices={"Pt1Line3_Gender": {"Male": "M", "Female": "F"}},
        ),
        "vaccination_record_only": q(
            "Part 1, Item 4.A: Eligible for the vaccination record portion only (an overseas panel examination: refugee or "
            "derivative asylee adjusting under INA 209, or a K visa holder)",
            ["Pt1_Line4_ImmMedExamReq"],
            ["Pt1_Line4_ImmMedExamReq"],
            allowed=FILLED_OR_NA,
            notes={"Pt1_Line4_ImmMedExamReq": (
                "Only when the record shows the overseas examination and the exception in the I-693 instructions (FAQ 2-4) "
                "applies; then the applicant and civil surgeon complete Parts 1-5, 7 and 10. Otherwise not_applicable."
            )},
            choices={"Pt1_Line4_ImmMedExamReq": {"Vaccination record only": "A"}},
        ),
        "applicant_contact": q(
            "Part 2, Items 1-3: Applicant's daytime phone, mobile phone (if any), email (if any)",
            ["Pt2Line3_DaytimePhone", "Pt2Line4_Mobilephone", "Pt2Line5_EmailAddress"],
            ["Pt2Line3_DaytimePhone"],
            notes={"Pt2Line3_DaytimePhone": "Item 1, despite the Line3 name. " + PHONE},
        ),
        "applicant_signature": q(
            "Part 2, Item 4: Applicant's signature and date, in the civil surgeon's presence",
            ["Pt2Line6_ApplicantSignature", "Pt2Line6_DateofSignature"],
            allowed=[PENDING_SIGNATURE],
            notes={"Pt2Line6_ApplicantSignature": (
                "Never filled: the applicant signs in ink only when the civil surgeon says to, in the civil surgeon's "
                "presence (instructions)."
            )},
        ),
        "interpreter_block": q(
            "Part 3, Items 1-5 and certification: Interpreter's name, business, phones, email, language",
            ["Pt3Line1_InterpreterFamilyName", "Pt3Line1_InterpreterGivenName", "Pt3Line2_NameofBusinessorOrgName",
             "Pt3Line4_DaytimePhone", "Pt3Line5_MobilePhone", "Pt3Line6_EmailAddress", "Pt3Line_NameOfLanguage"],
            ["Pt3Line1_InterpreterFamilyName", "Pt3Line1_InterpreterGivenName", "Pt3Line4_DaytimePhone",
             "Pt3Line_NameOfLanguage"],
            allowed=FILLED_OR_NA,
            notes={"Pt3Line4_DaytimePhone": "Item 3. " + PHONE, "Pt3Line5_MobilePhone": "Item 4, if any."},
        ),
        "interpreter_signature": q(
            "Part 3, Item 6: Interpreter's signature and date",
            ["Pt3Line7_Signature", "Pt3Line7_DateofSignature"],
            allowed=[NOT_APPLICABLE, PENDING_SIGNATURE],
        ),
        "preparer_block": q(
            "Part 4, Items 1-5: Preparer's name, business, phones, email (from the attorney profile)",
            ["Pt4Line1_PreparerFamilyName", "Pt4Line1_PreparerGivenName", "Pt4Line2_PreparerNameofBusinessorOrgName",
             "Pt4Line3_DaytimePhone", "Pt4Line4_MobilePhone", "Pt4Line5_EmailAddress"],
            ["Pt4Line1_PreparerFamilyName", "Pt4Line1_PreparerGivenName", "Pt4Line3_DaytimePhone"],
            allowed=FILLED_OR_NA,
            notes={"Pt4Line3_DaytimePhone": "Profile key phone. " + PHONE},
        ),
        "preparer_signature": q(
            "Part 4, Item 6: Preparer's signature and date",
            ["Pt4Line8_Signature", "Pt4Line8_DateofSignature"],
            allowed=[NOT_APPLICABLE, PENDING_SIGNATURE],
        ),
    }


def civil_surgeon_question(applicant: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Every other box of the form: the civil surgeon's and health department's, never filled by the tools."""
    fields = json.loads((Path(__file__).resolve().parent / "fields" / FIELD_LIST).read_text(encoding="utf-8"))["fields"]
    taken = {name.split("[")[0] for spec in applicant.values() for name in spec["required_fields"]}
    rest = sorted(
        name for name, entry in fields.items()
        if name not in taken and not name.startswith("PDF417") and "BBox" not in entry.get("states", [])
    )
    choices = {name: {state: state for state in fields[name]["states"]} for name in rest if fields[name]["type"] == "/Btn"}
    return q(
        "Parts 5-10: the civil surgeon's, panel physician's or health department's parts (never filled by the firm)",
        rest,
        allowed=[NOT_APPLICABLE],
        notes={rest[0]: "The civil surgeon completes these. Leave every box blank; the audit reports a value in any of them."},
        choices=choices,
    )


def applicant_part() -> dict[str, Any]:
    questions = applicant_questions()
    questions["civil_surgeon_parts"] = civil_surgeon_question(questions)
    return {
        "kind": "i-693",
        "edition": "01/20/25",
        "field_list": FIELD_LIST,
        "description": (
            "Form I-693 applicant's part (Parts 1-4) for the applicant to take to the civil surgeon; the civil surgeon "
            "completes the rest and returns it sealed."
        ),
        "notes": ["One I-693 per applicant. A required I-693 is filed with the I-485 (I-485 instructions, item 9), sealed.",
                  "The applicant signs only in the civil surgeon's presence, when told to; the signature stays pending."],
        "required_questions": questions,
    }


SCHEMAS = {"i693_applicant_part": applicant_part()}

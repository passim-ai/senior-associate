"""Question schemas for Form I-131, Application for Travel Documents, Parole Documents, and
Arrival/Departure Records (edition 01/20/25, expires 06/30/2027, 14 pages).

Two schemas share one set of question definitions, built fresh for each schema so that every
schema's `required_questions` is complete on its own:

- i131_advance_parole_pending_i485: advance parole for an applicant inside the United States
  with a pending Form I-485 (Part 1 item 5.A). Only the parts an advance parole applicant
  answers are in it.
- i131_travel_document: the whole form, for any document type (reentry permit, refugee travel
  document, TPS travel authorization, advance parole on any item 5 basis, initial parole from
  outside the United States, parole in place, re-parole). The type-specific questions allow
  not_applicable.

Every field name and on-state below was checked against the blank's field list
(schemas/fields/I-131.json) and each box's position, tooltip and XFA binding on the 01/20/25
PDF (uscis.gov/i-131 Edition Date panel, and the footer of the form and the instructions).
Item numbers in labels and notes are the form's; the field notes say where a name misleads.
"""
from __future__ import annotations

from typing import Any

from _common import (DATE, FILLED, FILLED_OR_NA, FOREIGN_ONLY, NOT_APPLICABLE, OPTIONAL_SIGNATURE, PENDING_CLIENT,
                     SIGNATURE_STATUSES, UNIT, YES_NO, q)

EDITION = "01/20/25"
FIELD_LIST = "I-131.json"

ADVANCE_PAROLE = "advance_parole"  # posture of i131_advance_parole_pending_i485
ANY_TYPE = "any_type"  # posture of i131_travel_document


STATE = "U.S. address only: 2-letter state code (drop-down)."
ZIP = "U.S. address only: 5 digits."
CITY = "maxlen 20. Adobe accepts only letters and spaces here: drop periods and hyphens ('St Louis')."
UNIT_NUMBER = "The apartment, suite or floor number only (maxlen 6); pick the unit type in the matching Unit box."
PHONE = "10 digits, no punctuation (maxlen 10)."
RECEIPT = "13 characters, letters and digits only (no dashes), e.g. IOE0123456789."
UNBOUND = (
    "Unbound in the blank's XFA template, so Adobe would show it empty; fill binds it in the filled "
    "source when it has a value."
)
SIGNATURE_NOTE = (
    "Protected box: never typed or signed electronically. Leave it blank; the signer signs in ink. A "
    "stamped or typewritten name is not acceptable."
)
SIGNATURE_DATE = "mm/dd/yyyy. Normally left blank for the signer to date at signing."
LINES_85 = "Break lines yourself: about 85 characters a line (the filing copy does not wrap text)."

APPLICATION_TYPES = {
    "1. Reentry Permit (lawful permanent or conditional permanent resident)": "1",
    "2. Refugee Travel Document (now holds refugee or asylee status)": "2",
    "3. Refugee Travel Document (LPR as a direct result of refugee or asylee status)": "3",
    "4. TPS Travel Authorization Document (TPS beneficiary in the United States)": "4",
    "5.A. Advance Parole Document: a pending Form I-485": "5",
    "5.B. Advance Parole Document: a pending Form I-589": "6",
    "5.C. Advance Parole Document: a pending initial Form I-821 (TPS)": "7",
    "5.D. Advance Parole Document: Deferred Enforced Departure": "8",
    "5.E. Advance Parole Document: approved Form I-821D (DACA)": "9",
    "5.F. Advance Parole Document: approved Form I-914 or I-914 Supplement A (T)": "10",
    "5.G. Advance Parole Document: approved Form I-918 or I-918 Supplement A (U)": "11",
    "5.H. Advance Parole Document: current parolee under INA 212(d)(5)": "12",
    "5.I. Advance Parole Document: approved Form I-817 (Family Unity)": "13",
    "5.J. Advance Parole Document: pending Form I-687": "14",
    "5.K. Advance Parole Document: approved V nonimmigrant status": "15",
    "5.L. Advance Parole Document: CNMI long-term residence": "16",
    "5.M. Advance Parole Document: other": "17",
    "6.A. Initial Parole Document (outside the U.S.): Filipino World War II Veterans Parole (FWVP)": "18",
    "6.B. Initial Parole Document: Immigrant Military Members and Veterans Initiative (IMMVI)": "19",
    "6.C. Initial Parole Document: Intergovernmental Parole Referral": "20",
    "6.D. Initial Parole Document: Family Reunification Task Force (FRTF) process": "21",
    "6.E. Initial Parole Document: other specific parole program or process": "22",
    "7. Initial Parole Document (outside the U.S.), not under a specific program or process": "23",
    "8.A. Initial parole in place: Military Parole in Place": "24",
    "8.B. Initial parole in place: Family Reunification Task Force (FRTF) process": "25",
    "8.C. Initial parole in place: other specific program or process": "26",
    "9. Initial parole in place, not under a specific program or process": "27",
    "10.A. Re-parole: Family Reunification Parole Process": "28",
    "10.B. Re-parole: certain Afghans paroled into the U.S. after July 31, 2021": "29",
    "10.C. Re-parole: certain Ukrainians and immediate family paroled on or after Feb. 11, 2022": "30",
    "10.D. Re-parole: Filipino World War II Veterans Parole (FWVP)": "31",
    "10.E. Re-parole: Immigrant Military Members and Veterans Initiative (IMMVI)": "32",
    "10.F. Re-parole: Central American Minors (CAM) Program": "33",
    "10.G. Re-parole: Family Reunification Task Force (FRTF) process": "34",
    "10.H. Re-parole: Military Parole in Place": "35",
    "10.I. Re-parole: other program or process": "36",
    "11. Re-parole, not under a specific program or process": "37",
}
ADVANCE_PAROLE_TYPES = {"5.A. Advance Parole Document: a pending Form I-485": "5"}

IMMVI_1 = {"(1) A current or former service member": "1"}
IMMVI_2 = {
    "(2) A current spouse, child, or unmarried son or daughter (or their child under 21) of a current or "
    "former service member": "1"
}
IMMVI_3 = {"(3) Current legal guardian or surrogate of a current or former service member": "1"}
MILITARY_PIP_1 = {"(1) A current or former service member": "1"}
MILITARY_PIP_2 = {"(2) A spouse, parent, son, or daughter of a current or former service member": "1"}


def address_fields(prefix: str, city: str = "CityTown") -> list[str]:
    """The ten boxes of a Part 2 or Part 4 address block, in form order."""
    return [
        f"{prefix}_InCareofName",
        f"{prefix}_StreetNumberName",
        f"{prefix}_Unit",
        f"{prefix}_AptSteFlrNumber",
        f"{prefix}_{city}",
        f"{prefix}_State",
        f"{prefix}_ZipCode",
        f"{prefix}_Province",
        f"{prefix}_PostalCode",
        f"{prefix}_Country",
    ]


def address_notes(prefix: str, street_note: str, country_note: str) -> dict[str, str]:
    return {
        f"{prefix}_InCareofName": "If any (maxlen 34).",
        f"{prefix}_StreetNumberName": street_note,
        f"{prefix}_AptSteFlrNumber": UNIT_NUMBER,
        f"{prefix}_CityTown": CITY,
        f"{prefix}_State": STATE,
        f"{prefix}_ZipCode": ZIP,
        f"{prefix}_Province": FOREIGN_ONLY + " maxlen 20.",
        f"{prefix}_PostalCode": FOREIGN_ONLY + " maxlen 9.",
        f"{prefix}_Country": country_note,
    }


def name_rows(prefix: str) -> list[str]:
    fields: list[str] = []
    for row in (1, 2, 3):
        fields += [f"{prefix}_FamilyName{row}", f"{prefix}_GivenName{row}", f"{prefix}_MiddleName{row}"]
    return fields


# --------------------------------------------------------------------------- page 1


def attorney_box() -> dict[str, Any]:
    return q(
        "Page 1 attorney box: Form G-28 is attached to represent the applicant",
        ["G28_Attached"],
        ["G28_Attached"],
        allowed=FILLED_OR_NA,
        notes={
            "G28_Attached": (
                "Select when a G-28 for the applicant is filed with the I-131. This edition's box has no "
                "attorney bar number, Volag number or online account number."
            ),
        },
        choices={"G28_Attached": {"G-28 attached": "Y"}},
    )


# --------------------------------------------------------------------------- Part 1


def application_type(posture: str) -> dict[str, Any]:
    if posture == ADVANCE_PAROLE:
        note = (
            "Part 1 items 1-11 are one checkbox group across pages 1-4. This schema covers item 5.A only "
            "(on-state '5'); any other basis needs i131_travel_document."
        )
        choices = ADVANCE_PAROLE_TYPES
    else:
        note = (
            "Part 1 items 1-11 are one checkbox group across pages 1-4; select exactly one box. The "
            "on-states run '1'-'37' and don't follow the item letters (5.B is '6', 6.A is '18', 11 is '37'): "
            "use the choices. The follow-up boxes for each item are in tps_travel_authorization (item 4), "
            "advance_parole_basis (item 5), initial_parole_program (items 6 and 8) and reparole_program "
            "(items 10-12)."
        )
        choices = APPLICATION_TYPES
    return q(
        "Part 1, Items 1-11: Application type (reentry permit, refugee travel document, TPS travel "
        "authorization, advance parole, initial parole, parole in place, re-parole)",
        ["CB_AppType"],
        ["CB_AppType"],
        notes={"CB_AppType": note},
        choices={"CB_AppType": choices},
    )


def advance_parole_basis(posture: str) -> dict[str, Any]:
    receipt_5a = (
        "Item 5.A: the I-485 receipt number, only when this I-131 is filed separately from (after) the "
        "I-485. " + RECEIPT + " not_applicable when the I-131 is filed together with the I-485."
    )
    if posture == ADVANCE_PAROLE:
        return q(
            "Part 1, Item 5.A: Pending Form I-485 receipt number (if this form is filed separately from it)",
            ["P1_Line5A"],
            ["P1_Line5A"],
            allowed=FILLED_OR_NA,
            notes={"P1_Line5A": receipt_5a},
        )
    receipt = "With item {item} only: " + RECEIPT
    return q(
        "Part 1, Items 5.A-5.M: Advance parole basis details (receipt number, class of admission or "
        "explanation beside the item 5 box selected)",
        ["P1_Line5A", "P1_Line5B", "P1_Line5C", "P1_Line5E", "P1_Line5F", "P1_Line5G", "P1_Line5H", "P1_Line5I",
         "P1_Line5J", "P1_Line5K", "P1_Line5L", "P1_Line5M"],
        allowed=FILLED_OR_NA,
        notes={
            "P1_Line5A": receipt_5a + " Fill only the box beside the item 5 basis selected; 5.D (DED) has no box.",
            "P1_Line5B": receipt.format(item="5.B") + " The pending I-589.",
            "P1_Line5C": receipt.format(item="5.C") + " The pending initial I-821.",
            "P1_Line5E": receipt.format(item="5.E") + " The approved I-821D.",
            "P1_Line5F": receipt.format(item="5.F") + " The approved I-914 or I-914 Supplement A.",
            "P1_Line5G": receipt.format(item="5.G") + " The approved I-918 or I-918 Supplement A.",
            "P1_Line5H": (
                "With item 5.H only: the CLASS OF ADMISSION of the current parole as shown on the I-94, not a "
                "receipt number (letters and digits only)."
            ),
            "P1_Line5I": receipt.format(item="5.I") + " The approved I-817.",
            "P1_Line5J": receipt.format(item="5.J") + " The pending I-687.",
            "P1_Line5K": receipt.format(item="5.K") + " The V status approval.",
            "P1_Line5L": receipt.format(item="5.L") + " The CNMI long-term resident approval.",
            "P1_Line5M": (
                "With item 5.M only: the code or designation USCIS announced for the category, and an "
                "explanation (Instructions, Item Number 5). Three lines of about 77 characters; break them "
                "yourself and continue in Part 13."
            ),
        },
    )


def refugee_status() -> dict[str, Any]:
    return q(
        "Part 1, Item 13: Do you hold status as a refugee, were you paroled as a refugee, or are you a lawful "
        "permanent resident as a direct result of being a refugee?",
        ["P1_Line13_YesNo"],
        ["P1_Line13_YesNo"],
        notes={
            "P1_Line13_YesNo": (
                "Answered on every application. The question asks about refugee status only: an asylee, or an "
                "LPR who adjusted as an asylee, answers No unless they were also admitted or paroled as a refugee."
            ),
        },
        choices={"P1_Line13_YesNo": YES_NO},
    )


# --------------------------------------------------------------------------- Part 2, items 1-15


def mailing_address(posture: str) -> dict[str, Any]:
    fields = address_fields("Part2_Line3")
    if posture == ADVANCE_PAROLE:
        street = (
            "Item 3, maxlen 34. USCIS mails the advance parole document here and cannot mail it abroad. A safe "
            "address (PO box, the attorney's office) is allowed for a VAWA, T or U applicant."
        )
        nonempty = ["Part2_Line3_StreetNumberName", "Part2_Line3_CityTown", "Part2_Line3_State", "Part2_Line3_ZipCode",
                    "Part2_Line3_Country"]
        label = "Part 2, Item 3: Current U.S. mailing address or safe address"
    else:
        street = (
            "Item 3, maxlen 34. USCIS cannot mail a travel document to a foreign address (Part 4 items 7-9 "
            "cover pickup abroad). A safe address (PO box, the attorney's office) is allowed for a VAWA, T or U "
            "applicant."
        )
        nonempty = ["Part2_Line3_StreetNumberName", "Part2_Line3_CityTown", "Part2_Line3_Country"]
        label = "Part 2, Item 3: Current mailing address or safe address"
    return q(
        label,
        fields,
        nonempty,
        notes=address_notes(
            "Part2_Line3",
            street,
            "Item 3 country, also for a U.S. address ('United States'); the audit requires it.",
        ),
        choices={"Part2_Line3_Unit": UNIT},
    )


def admission_details(posture: str) -> dict[str, Any]:
    fields = ["Part2_Line12_ClassofAdmission", "Part2_Line13_I94RecordNo", "Part2_Line14_I94ExpDate",
              "Par2_Line15_eMedicalParoleeID"]
    nonempty = fields[:3]
    exp_note = (
        "Item 14: the Admit Until Date on the I-94. A date box (Adobe accepts digits and slashes only): an I-94 "
        "marked D/S can't go here; leave it blank and say 'D/S' in Part 13. " + DATE
    )
    if posture == ADVANCE_PAROLE:
        coa_note = (
            "Item 12 (the tooltip says Part 1): the class of admission code exactly as on the most recent I-94, "
            "e.g. 'B2', 'F1', 'PAR'. The audit requires items 12-14 on every I-131; an applicant with no I-94 "
            "(entry without inspection) has none, so leave this question manual_review with an open item "
            "explaining why."
        )
        allowed = None
    else:
        coa_note = (
            "Item 12 (the tooltip says Part 1): the class of admission code exactly as on the most recent I-94. "
            "Items 12-15 are asked only for TPS travel authorization, advance parole, parole in place and "
            "re-parole (Part 1 items 4, 5, 8-11), and only if any: not_applicable for a reentry permit, refugee "
            "travel document, initial parole from abroad (items 1-3, 6-7) or an applicant with no I-94."
        )
        allowed = FILLED_OR_NA
    return q(
        "Part 2, Items 12-15: Class of admission, most recent Form I-94 number and authorized-stay expiration "
        "date, eMedical U.S. Parolee ID",
        fields,
        nonempty,
        allowed=allowed,
        notes={
            "Part2_Line12_ClassofAdmission": coa_note,
            "Part2_Line13_I94RecordNo": "Item 13: the 11-character I-94 number (the Departure Number on some versions).",
            "Part2_Line14_I94ExpDate": exp_note,
            "Par2_Line15_eMedicalParoleeID": (
                "Item 15 (named 'Par2'): eMedical U.S. Parolee ID (USPID), if any; most applicants have none, so "
                "leave it blank."
            ),
        },
    )


# --------------------------------------------------------------------------- Part 2, items 16-27


ON_BEHALF = (
    "Items 16-27 only when you file for someone else under Part 1 items 6-11; never when filing for yourself "
    "(question not_applicable)."
)


def beneficiary_address(item: int) -> dict[str, Any]:
    prefix = f"P2_Line{item}"
    which = "mailing" if item == 24 else "physical"
    street = f"Item {item}, their current {which} address, maxlen 34. " + ON_BEHALF
    if item == 25:
        street += " Asked even when it matches item 24: repeat the address."
    return q(
        f"Part 2, Item {item}: Their current {which} address",
        address_fields(prefix),
        [f"{prefix}_StreetNumberName", f"{prefix}_CityTown", f"{prefix}_Country"],
        allowed=FILLED_OR_NA,
        notes=address_notes(prefix, street, f"Item {item} country."),
        choices={f"{prefix}_Unit": UNIT},
    )


# --------------------------------------------------------------------------- Part 3


def biographic_information() -> dict[str, Any]:
    return q(
        "Part 3, Items 1-6: Biographic information of the person who will receive the document (ethnicity, "
        "race, height, weight, eye color, hair color)",
        ["P3_Line1_Ethnicity", "P3_Line2_Race_American", "P3_Line2_Race_Asian", "P3_Line2_Race_Black",
         "P3_Line2_Race_Hawaiian", "P3_Line2_Race_White", "P3_Line3_HeightFeet", "P3_Line3_HeightInches",
         "P3_Line4_Pound1", "P3_Line4_Pound2", "P3_Line4_Pound3", "P3_Line5_EyeColor", "P3_Line6_HairColor"],
        ["P3_Line1_Ethnicity", "P3_Line3_HeightFeet", "P3_Line3_HeightInches", "P3_Line4_Pound1", "P3_Line4_Pound2",
         "P3_Line4_Pound3", "P3_Line5_EyeColor", "P3_Line6_HairColor"],
        notes={
            "P3_Line1_Ethnicity": (
                "Item 1, one box. The person who will receive the document: the beneficiary, not the filer, when "
                "filing for someone else."
            ),
            "P3_Line2_Race_American": (
                "Item 2: each race is a separate box with its own on-state; select every one that applies (at "
                "least one)."
            ),
            "P3_Line3_HeightFeet": "Item 3, drop-down '2'-'8'. Feet and inches, never metric.",
            "P3_Line3_HeightInches": (
                "Drop-down '0'-'11'. The instructions' example says '09', but the list holds '9' (no leading zero)."
            ),
            "P3_Line4_Pound1": (
                "Item 4: weight in pounds, one digit per box (maxlen 1 each): 150 lb is '1', '5', '0'; 95 lb is "
                "'0', '9', '5'. Unknown, under 30 or over 699: '0', '0', '0'. Adobe accepts only 0-6 in this "
                "first box."
            ),
            "P3_Line4_Pound2": "Second digit.",
            "P3_Line4_Pound3": "Third digit.",
        },
        choices={
            "P3_Line1_Ethnicity": {"Hispanic or Latino": "H", "Not Hispanic or Latino": "NH"},
            "P3_Line2_Race_American": {"American Indian or Alaska Native": "I"},
            "P3_Line2_Race_Asian": {"Asian": "A"},
            "P3_Line2_Race_Black": {"Black or African American": "B"},
            "P3_Line2_Race_Hawaiian": {"Native Hawaiian or Other Pacific Islander": "H"},
            "P3_Line2_Race_White": {"White": "W"},
            "P3_Line5_EyeColor": {
                "Black": "BLK",
                "Blue": "BLU",
                "Brown": "BRN",
                "Gray": "GRY",
                "Green": "GRN",
                "Hazel": "HZL",
                "Maroon": "MRN",
                "Pink": "PNK",
                "Unknown/Other": "OTH",
            },
            "P3_Line6_HairColor": {
                "Bald (No Hair)": "BLD",
                "Black": "BLK",
                "Blond": "BND",
                "Brown": "BRN",
                "Gray": "GRY",
                "Red": "RED",
                "Sandy": "SDY",
                "White": "WHT",
                "Unknown/Other": "OTH",
            },
        },
    )


# --------------------------------------------------------------------------- Part 4


def removal_proceedings() -> dict[str, Any]:
    return q(
        "Part 4, Item 1: Has the person who will receive the document been in any exclusion, deportation, "
        "removal, or rescission proceedings?",
        ["P4_Line1_YesNo"],
        ["P4_Line1_YesNo"],
        notes={
            "P4_Line1_YesNo": (
                "Leave blank until the client confirms the answer; record the source and date. Yes needs attorney review before filing: "
                "the Instructions say ICE, not USCIS, generally has jurisdiction over an I-131 for someone in "
                "proceedings or under a final order."
            ),
        },
        choices={"P4_Line1_YesNo": YES_NO},
    )


def prior_documents() -> dict[str, Any]:
    return q(
        "Part 4, Items 2.a-3.c: Ever issued a Reentry Permit or Refugee Travel Document, or an Advance Parole "
        "Document (date issued and disposition of the last one)",
        ["P4_Line2a_YesNo", "P4_Line2b_DateIssued", "P4_Line2c_Disposition", "P4_Line3a_YesNo", "P4_Line3b_DateIssued",
         "P4_Line3c_Disposition"],
        ["P4_Line2a_YesNo", "P4_Line3a_YesNo"],
        notes={
            "P4_Line2a_YesNo": "Item 2.a, EVER issued a Reentry Permit or Refugee Travel Document. Yes needs 2.b-2.c "
            "for the last one.",
            "P4_Line2b_DateIssued": "With 2.a Yes only. " + DATE,
            "P4_Line2c_Disposition": (
                "With 2.a Yes only: 'attached', 'lost', 'stolen', 'damaged/destroyed', 'still in my possession'. "
                "One line of about 55 characters. " + UNBOUND
            ),
            "P4_Line3a_YesNo": (
                "Item 3.a, EVER issued an Advance Parole Document (an I-512L, or an EAD card annotated 'Serves as "
                "I-512 Advance Parole'). Yes needs 3.b-3.c for the last one."
            ),
            "P4_Line3b_DateIssued": "With 3.a Yes only. " + DATE,
            "P4_Line3c_Disposition": "With 3.a Yes only. One line of about 55 characters. " + UNBOUND,
        },
        choices={"P4_Line2a_YesNo": YES_NO, "P4_Line3a_YesNo": YES_NO},
    )


def replacement_request(posture: str) -> dict[str, Any]:
    note = "Item 4. Yes requires replacement_details (items 5-6.b)."
    allowed = None
    if posture == ANY_TYPE:
        note += (
            " Not asked for parole from outside the U.S., parole in place or re-parole (Part 1 items 6-11): "
            "those skip from item 3 to Part 8, so mark it not_applicable."
        )
        allowed = FILLED_OR_NA
    return q(
        "Part 4, Item 4: Are you requesting a replacement Reentry Permit, Refugee Travel Document, Advance "
        "Parole Document, or TPS Travel Authorization Document?",
        ["P4_Line4_YesNo"],
        ["P4_Line4_YesNo"],
        allowed=allowed,
        notes={"P4_Line4_YesNo": note},
        choices={"P4_Line4_YesNo": YES_NO},
    )


def replacement_details() -> dict[str, Any]:
    return q(
        "Part 4, Items 5-6.b: Reason for the replacement, information to correct, and the receipt number of "
        "the I-131 being replaced",
        ["P4_Line5", "P4_Line6a_Name", "P4_Line6a_ANumber", "P4_Line6a_CountryofBirthCitizenship", "P4_Line6a_Terms",
         "P4_Line6a_DOB", "P4_Line6a_Gender", "P4_Line6a_Validity", "P4_Line6a_Photo", "P4_Line6a_Explanation",
         "P4_Line6b_ReceiptNumber"],
        ["P4_Line5", "P4_Line6b_ReceiptNumber"],
        allowed=FILLED_OR_NA,
        notes={
            "P4_Line5": (
                "Item 5, one box, only when item 4 is Yes. Return a damaged or incorrect document with the "
                "application. The fee depends on the reason (Instructions, Item Numbers 2.a.-6.b.)."
            ),
            "P4_Line6a_Name": (
                "Item 6.a, only with item 5 reason 3 or 4 (incorrect information): select every item to correct. "
                "Eight separate boxes."
            ),
            "P4_Line6a_Gender": (
                "Item 6.a 'Sex' (named Gender). Its on-state 'C' repeats Country of Birth/Citizenship's; Validity "
                "Date's 'D' repeats Terms and Conditions', and Photo's 'E' repeats Date of Birth's. They are "
                "separate boxes, so use each box's own choice."
            ),
            "P4_Line6a_Explanation": (
                "Item 6.a explanation of what is incorrect: three lines. " + LINES_85 + " Continue in Part 13."
            ),
            "P4_Line6b_ReceiptNumber": (
                "Item 6.b, every replacement: the receipt number of the I-131 that produced the document being "
                "replaced. " + RECEIPT
            ),
        },
        choices={
            "P4_Line5": {
                "My document was issued, but I did not receive it": "1",
                "I received my document, but then it was lost, stolen, or damaged": "2",
                "I received my document, but it has incorrect information because of an error caused by me or "
                "because my information has changed": "3",
                "I received my document, but it has incorrect information because of an error not caused by me "
                "(such as a USCIS error)": "4",
            },
            "P4_Line6a_Name": {"Name": "A"},
            "P4_Line6a_ANumber": {"A-Number": "B"},
            "P4_Line6a_CountryofBirthCitizenship": {"Country of Birth/Citizenship": "C"},
            "P4_Line6a_Terms": {"Terms and Conditions": "D"},
            "P4_Line6a_DOB": {"Date of Birth": "E"},
            "P4_Line6a_Gender": {"Sex": "C"},
            "P4_Line6a_Validity": {"Validity Date": "D"},
            "P4_Line6a_Photo": {"Photo": "E"},
        },
    )


# --------------------------------------------------------------------------- Parts 5-9


def reentry_permit_time_outside() -> dict[str, Any]:
    boxes = {
        "P5_Line1_Lessthan6": "Less Than 6 Months",
        "P5_Line1_6months": "6 Months to 1 Year",
        "P5_Line1_1to2": "1 to 2 Years",
        "P5_Line1_2to3": "2 to 3 Years",
        "P5_Line1_3to4": "3 to 4 Years",
        "P5_Line1_morethan": "More Than 4 Years",
    }
    return q(
        "Part 5, Item 1: Reentry permit only: total time outside the United States since becoming a permanent "
        "resident (or in the past 5 years, whichever is less)",
        list(boxes),
        allowed=FILLED_OR_NA,
        notes={
            "P5_Line1_Lessthan6": (
                "Part 1 item 1 only. Six separate boxes, each with on-state 'Y': select exactly one (the schema "
                "can't enforce that, so check it). Count the days from the passport stamps or travel history. "
                "More than 4 of the last 5 years generally limits the permit to 1 year (Instructions, Validity "
                "of Reentry Permit)."
            ),
        },
        choices={field: {label: "Y"} for field, label in boxes.items()},
    )


RTD_ONLY = "Refugee travel document only (Part 1 items 2-3)."


DELCARMEN_LARA = (
    "ATTORNEY REVIEW before this is drafted or filed: under Matter of Delcarmen-Lara, 29 I&N Dec. 830 (BIA "
    "2026), a departure on advance parole is a 'departure' for the INA 212(a)(9)(B)(i) unlawful-presence bars "
    "(Matter of Arrabally overruled prospectively, effective Aug. 13, 2026). Confirm the attorney has screened "
    "the applicant's unlawful-presence history for this trip, or record an open item; never describe the trip "
    "as safe."
)


def proposed_travel(posture: str) -> dict[str, Any]:
    if posture == ADVANCE_PAROLE:
        allowed = [PENDING_CLIENT, FILLED]
        applies = ""
    else:
        allowed = [FILLED, PENDING_CLIENT, NOT_APPLICABLE]
        applies = (
            "Advance parole only (Part 1 item 5, any basis); the header limits Part 7 to item 5, so it is "
            "not_applicable for every other type, TPS travel authorization included. "
        )
    return q(
        "Part 7, Items 1-5: Proposed travel (date of intended departure, purpose, countries, number of trips, "
        "expected length of trip)",
        ["P7_Line1_DateOfDeparture", "P7_Line2_Purpose", "P7_Line3_ListCountries", "P7_Line4_CB",
         "P7_Line5_ExpectedLengthTrip"],
        ["P7_Line1_DateOfDeparture", "P7_Line2_Purpose", "P7_Line3_ListCountries", "P7_Line4_CB",
         "P7_Line5_ExpectedLengthTrip"],
        allowed=allowed,
        notes={
            "P7_Line1_DateOfDeparture": applies + "Item 1. " + DATE,
            "P7_Line2_Purpose": (
                "Item 2, purpose of the trip, from the client's own account: four lines. " + LINES_85 + " Continue "
                "in Part 13. A DACA recipient's purpose must be educational, employment or humanitarian, not "
                "vacation (Instructions). " + DELCARMEN_LARA
            ),
            "P7_Line3_ListCountries": "Item 3: every country to be visited, four lines. " + LINES_85,
            "P7_Line4_CB": "Item 4: one trip or more than one trip.",
            "P7_Line5_ExpectedLengthTrip": (
                "Item 5: expected length of the trip in days, digits only (a numeric box; Adobe takes at most 3 "
                "digits). " + UNBOUND
            ),
        },
        choices={"P7_Line4_CB": {"One Trip": "O", "More than one trip": "M"}},
    )


# --------------------------------------------------------------------------- Parts 10-13


def additional_information() -> dict[str, Any]:
    fields: list[str] = []
    for item in range(3, 8):
        fields += [
            f"Part13_Line{item}_PageNumber",
            f"Part13_Line{item}_PartNumber",
            f"Part13_Line{item}_ItemNumber",
            f"Part13_Line{item}_AdditionalInfo",
        ]
    return q(
        "Part 13, Items 3-7: Additional information (page, part, item and text for each continuation)",
        fields,
        fields[:4],
        allowed=FILLED_OR_NA,
        notes={
            "Part13_Line3_PageNumber": (
                "Item 3 page number (digits, maxlen 2). Items 1-2 (name, A-Number) fill themselves from Part 2. "
                "Item 3's page, part and item boxes are unbound in the blank's XFA template (Adobe would show "
                "them empty); fill binds each one it fills in the filled source."
            ),
            "Part13_Line3_PartNumber": "maxlen 6, e.g. '7'.",
            "Part13_Line3_ItemNumber": "maxlen 6, e.g. '2'.",
            "Part13_Line3_AdditionalInfo": "Three lines per block. " + LINES_85,
            "Part13_Line7_AdditionalInfo": (
                "Three lines. More entries go on a separate sheet with the name, A-Number, page, part and item, "
                "signed and dated."
            ),
        },
    )


# --------------------------------------------------------------------------- schemas


COMMON_NOTES = [
    "Edition 01/20/25 (expires 06/30/2027), 14 pages. Part 1 items 1-11 are one checkbox group, CB_AppType, "
    "whose on-states ('1'-'37') don't follow the item letters: use the choices.",
    "Global fields share one value: the Part 2 name (Part2_Line1_*) and A-Number (Part2_Line5_AlienNumber) print "
    "again in Part 13 items 1-2. Set them once in Part 2.",
    "Sixteen boxes are unbound in the blank's XFA template (Adobe would show them empty): the Part 2 item 2 other "
    "names, Part 4 items 2.c and 3.c, Part 7 item 5, Part 8 item 2 and the Part 13 item 3 page, part and item. "
    "fill binds each one it fills in the filled source.",
    "Multi-line boxes don't wrap on the filing copy: break lines yourself (about 85 characters a line in the "
    "516 pt boxes). Single-line boxes hold one line; continue anything longer in Part 13 with its page, part "
    "and item.",
    "This edition has no fee-exemption or fee-waiver items and no applicant-statement checkboxes: Part 10 is "
    "contact information, the certification and the signature. Fees are in Form G-1055.",
    "The instructions say to type N/A when a question doesn't apply. Leave boxes blank instead and mark the "
    "question not_applicable; the comb boxes (A-Number, SSN, online account number) take digits only. In Adobe, "
    "name, city and country boxes accept only letters, spaces (and hyphens, in names).",
]


def schema(description: str, notes: list[str], questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "kind": "i-131",
        "edition": EDITION,
        "field_list": FIELD_LIST,
        "description": description,
        "notes": COMMON_NOTES + notes,
        "required_questions": questions,
    }


def applicant_part2(posture: str) -> dict[str, dict[str, Any]]:
    return {
        "applicant_identity": q(
            "Part 2, Items 1 and 6-9: Your full name, country of birth, country of citizenship or nationality, "
            "sex, date of birth",
            ["Part2_Line1_FamilyName", "Part2_Line1_GivenName", "Part2_Line1_MiddleName", "Part2_Line6_CountryOfBirth",
             "Part2_Line7_CountryOfCitizenshiporNationality", "Part2_Line8_Gender", "Part2_Line9_DateOfBirth"],
            ["Part2_Line1_FamilyName", "Part2_Line1_GivenName", "Part2_Line6_CountryOfBirth",
             "Part2_Line7_CountryOfCitizenshiporNationality", "Part2_Line8_Gender", "Part2_Line9_DateOfBirth"],
            notes={
                "Part2_Line1_FamilyName": (
                    "Item 1, current legal name (the filer's own name when filing for someone else). Global: also "
                    "prints in Part 13 item 1, where the box holds about 28 characters (34 here)."
                ),
                "Part2_Line1_GivenName": "Global: also prints in Part 13 item 1.",
                "Part2_Line1_MiddleName": "Global: also prints in Part 13 item 1. Blank if none.",
                "Part2_Line6_CountryOfBirth": "Item 6: the current name of the country, not a historical or local name.",
                "Part2_Line7_CountryOfCitizenshiporNationality": (
                    "Item 7: 'Stateless' if none, with an explanation in Part 13."
                ),
                "Part2_Line8_Gender": "Item 8, Sex: 'M' Male, 'F' Female (the Female box comes first in the field "
                "list).",
                "Part2_Line9_DateOfBirth": "Item 9. " + DATE + " USCIS rejects an I-131 with no date of birth.",
            },
            choices={"Part2_Line8_Gender": {"Male": "M", "Female": "F"}},
        ),
        "other_names_used": q(
            "Part 2, Item 2: Other names used (aliases, maiden name, nicknames), three rows",
            name_rows("Part2_Line2"),
            ["Part2_Line2_FamilyName1", "Part2_Line2_GivenName1"],
            allowed=FILLED_OR_NA,
            notes={
                "Part2_Line2_FamilyName1": (
                    "Row 1. All nine item 2 boxes are unbound in the blank's XFA template (Adobe would show them "
                    "empty); fill binds each one it fills in the filled source. The instructions ask for the date "
                    "of birth used with each other name, but the form has no box for it: give a different one in "
                    "Part 13. A fourth name goes in Part 13."
                ),
                "Part2_Line2_FamilyName2": "Row 2.",
                "Part2_Line2_FamilyName3": "Row 3.",
            },
        ),
        "mailing_address": mailing_address(posture),
        "physical_address": q(
            "Part 2, Item 4: Current physical address (if different from the mailing address)",
            address_fields("Part2_Line4"),
            ["Part2_Line4_StreetNumberName", "Part2_Line4_CityTown", "Part2_Line4_Country"],
            allowed=FILLED_OR_NA,
            notes=address_notes("Part2_Line4",
                                "Item 4, only when it differs from item 3; otherwise not_applicable. maxlen 34.",
                                "Item 4 country ('United States' for a U.S. address)."),
            choices={"Part2_Line4_Unit": UNIT},
        ),
        "a_number": q(
            "Part 2, Item 5: Alien Registration Number (A-Number), if any",
            ["Part2_Line5_AlienNumber"],
            ["Part2_Line5_AlienNumber"],
            allowed=FILLED_OR_NA,
            notes={
                "Part2_Line5_AlienNumber": (
                    "9 digits, no 'A' (comb box); pad an 8-digit number with a leading zero. Global: also prints in "
                    "Part 13 item 2. The instructions say N/A if none, but the box takes digits only: leave it blank "
                    "and mark the question not_applicable."
                ),
            },
        ),
        "social_security_number": q(
            "Part 2, Item 10: U.S. Social Security number, if any",
            ["Part2_Line10_SSN"],
            ["Part2_Line10_SSN"],
            allowed=FILLED_OR_NA,
            notes={"Part2_Line10_SSN": "9 digits, no dashes (comb box). None: leave blank and mark not_applicable."},
        ),
        "uscis_online_account_number": q(
            "Part 2, Item 11: USCIS Online Account Number, if any",
            ["Part2_Line11_USCISOnlineAcctNumber"],
            ["Part2_Line11_USCISOnlineAcctNumber"],
            allowed=FILLED_OR_NA,
            notes={
                "Part2_Line11_USCISOnlineAcctNumber": (
                    "12 characters (comb box). Only an applicant with a receipt number beginning IOE has one. The "
                    "applicant's own number, not the attorney's."
                ),
            },
        ),
        "admission_details": admission_details(posture),
    }


def signature_parts() -> dict[str, dict[str, Any]]:
    return {
        "applicant_contact": q(
            "Part 10, Items 1-3: Applicant's daytime phone, mobile phone, email",
            ["Part10_Line1_DayPhone", "Part10_Line2_MobilePhone", "Part10_Line3_Email"],
            ["Part10_Line1_DayPhone"],
            notes={
                "Part10_Line1_DayPhone": "Item 1. " + PHONE,
                "Part10_Line2_MobilePhone": "Item 2, if any. " + PHONE,
                "Part10_Line3_Email": "Item 3, if any (about 38 characters fit).",
            },
        ),
        "applicant_signature": q(
            "Part 10, Item 4: Applicant's signature and date",
            ["Part10_Line4_ApplicantSignature", "Part10_Line4_DateofSignature"],
            allowed=SIGNATURE_STATUSES,
            notes={
                "Part10_Line4_ApplicantSignature": SIGNATURE_NOTE + " A parent or legal guardian may sign for the "
                "applicant.",
                "Part10_Line4_DateofSignature": SIGNATURE_DATE,
            },
        ),
        "interpreter_block": q(
            "Part 11, Items 1-5 and certification: Interpreter's name, business, phones, email, language",
            ["Part11_Line1_InterpreterFamilyName", "Part11_Line1_InterpreterGivenName",
             "Part11_Line2_NameofBusinessorOrgName", "Part11_Line3_DayPhone", "Part11_Line4_MobilePhone",
             "Part11_Line5_Email", "P11_Language"],
            ["Part11_Line1_InterpreterFamilyName", "Part11_Line1_InterpreterGivenName", "Part11_Line3_DayPhone",
             "P11_Language"],
            allowed=FILLED_OR_NA,
            notes={
                "Part11_Line2_NameofBusinessorOrgName": "Item 2, if any (maxlen 34; Adobe accepts letters, digits and "
                "spaces only).",
                "Part11_Line3_DayPhone": "Item 3. " + PHONE,
                "Part11_Line4_MobilePhone": "Item 4, if any. " + PHONE,
                "Part11_Line5_Email": "Item 5, if any (about 38 characters fit).",
                "P11_Language": "The language in the certification ('fluent in English and ___'), maxlen 18.",
            },
        ),
        "interpreter_signature": q(
            "Part 11, Item 6: Interpreter's signature and date",
            ["Part11_Line6_InterpreterSig", "Part11_Line6_DateofSignature"],
            allowed=OPTIONAL_SIGNATURE,
            notes={
                "Part11_Line6_InterpreterSig": "maxlen 1. " + SIGNATURE_NOTE,
                "Part11_Line6_DateofSignature": SIGNATURE_DATE,
            },
        ),
        "preparer_block": q(
            "Part 12, Items 1-5: Preparer's name, business, phones, email (from the attorney profile)",
            ["Part12_Line1_FamilyName", "Part12_Line1_GivenName", "Part12_Line2_NameofBusinessorOrgName",
             "Part12_Line3_DayPhone", "Part12_Line4_MobilePhone", "Part12_Line5_Email"],
            ["Part12_Line1_FamilyName", "Part12_Line1_GivenName", "Part12_Line2_NameofBusinessorOrgName",
             "Part12_Line3_DayPhone", "Part12_Line5_Email"],
            notes={
                "Part12_Line1_FamilyName": (
                    "From the attorney profile, never from another matter. The audit requires the whole block "
                    "(email included). This edition has no preparer address, fax or attorney statement boxes."
                ),
                "Part12_Line2_NameofBusinessorOrgName": (
                    "Firm name, maxlen 34. Adobe accepts letters, digits and spaces only: drop commas, periods and "
                    "ampersands ('Example Law PLLC')."
                ),
                "Part12_Line3_DayPhone": "Item 3. " + PHONE,
                "Part12_Line4_MobilePhone": "Item 4, if any. " + PHONE,
                "Part12_Line5_Email": "Item 5 (about 38 characters fit).",
            },
        ),
        "preparer_signature": q(
            "Part 12, Item 6: Preparer's signature and date",
            ["Part12_Line6_PreparerSig", "Part12_Line6_DateofSignature"],
            allowed=SIGNATURE_STATUSES,
            notes={
                "Part12_Line6_PreparerSig": "maxlen 1. " + SIGNATURE_NOTE,
                "Part12_Line6_DateofSignature": SIGNATURE_DATE,
            },
        ),
        "additional_information": additional_information(),
    }


SCHEMAS = {
    "i131_advance_parole_pending_i485": schema(
        "Form I-131 advance parole for an applicant inside the United States with a pending Form I-485 (Part 1 "
        "item 5.A), filed with the I-485 or after it.",
        [
            "Part 1: select 5.A (on-state '5'). Its receipt box takes the I-485 receipt number only when this "
            "I-131 is filed after the I-485; a concurrent filing leaves it blank (advance_parole_basis "
            "not_applicable). Answer item 13 (refugee status) too.",
            "Not in this schema, because advance parole doesn't use them: Part 1 items 1-4 and 6-12, Part 2 items "
            "16-27 (filing for someone else), Part 4 items 7-9 (delivery of a reentry permit or refugee travel "
            "document), and Parts 5, 6, 8 and 9. Leave those boxes blank.",
            "Part 2 items 12-14: the audit requires the class of admission, I-94 number and I-94 expiration. An "
            "applicant with no I-94 leaves admission_details manual_review with an open item.",
            "Part 4: answer items 1-4; items 5-6.b only for a replacement. Then Part 7.",
            "Part 7 item 2 carries an attorney-review flag (Matter of Delcarmen-Lara, BIA 2026): read the field "
            "note before drafting the purpose of the trip.",
        ],
        {
            **{
                "attorney_box": attorney_box(),
                "application_type": application_type(ADVANCE_PAROLE),
                "advance_parole_basis": advance_parole_basis(ADVANCE_PAROLE),
                "refugee_status": refugee_status(),
            },
            **applicant_part2(ADVANCE_PAROLE),
            "biographic_information": biographic_information(),
            "removal_proceedings": removal_proceedings(),
            "prior_documents": prior_documents(),
            "replacement_request": replacement_request(ADVANCE_PAROLE),
            "replacement_details": replacement_details(),
            "proposed_travel": proposed_travel(ADVANCE_PAROLE),
            **signature_parts(),
        },
    ),
    "i131_travel_document": schema(
        "Form I-131 for any document type: reentry permit, refugee travel document, TPS travel authorization, "
        "advance parole on any item 5 basis, initial parole from abroad, parole in place or re-parole; "
        "type-specific parts allow not_applicable.",
        [
            "Select one Part 1 box, then answer by type (every other type-specific question not_applicable). "
            "Reentry permit (item 1): Part 4 items 1-4 and 7 (8-9 with 7.b), Part 5. Refugee travel document "
            "(items 2-3): Part 4 items 1-4 and 7-9, Part 6. TPS travel authorization (item 4): item 4 receipt, "
            "Part 2 items 12-15, Part 4 items 1-4. Advance parole (item 5): the item 5 follow-up box, Part 2 items "
            "12-15, Part 4 items 1-4, Part 7. Initial parole from abroad (items 6-7), parole in place (8-9) and "
            "re-parole (10-11): Part 4 items 1-3, Part 8, Part 2 items 16-27 when filing for someone else; "
            "items 8-11 also Part 2 items 12-15; re-parole also Part 1 item 12 and, optionally, Part 9.",
            "Part 1 item 13 (refugee status), Part 2 items 1-11, Part 3, Part 4 items 1-3, and Parts 10 and 12 "
            "are answered on every application. Part 4 items 5-6.b only for a replacement.",
            "Filing for someone else (items 6-11): Part 2 items 1-11 are the filer's own details and items 16-27 "
            "the other person's; Part 3 describes the person who will receive the document.",
            "Part 7 item 2 carries an attorney-review flag (Matter of Delcarmen-Lara, BIA 2026): read the field "
            "note before drafting the purpose of an advance parole trip.",
        ],
        {
            **{
                "attorney_box": attorney_box(),
                "application_type": application_type(ANY_TYPE),
                "tps_travel_authorization": q(
                    "Part 1, Item 4: Receipt number of the last approved Form I-821 (TPS travel authorization only)",
                    ["P1_Line4"],
                    ["P1_Line4"],
                    allowed=FILLED_OR_NA,
                    notes={
                        "P1_Line4": "With item 4 only: the receipt number of the last APPROVED Form I-821. " + RECEIPT,
                    },
                ),
                "advance_parole_basis": advance_parole_basis(ANY_TYPE),
                "initial_parole_program": q(
                    "Part 1, Items 6.A-6.E and 8.A-8.C: Initial parole or parole-in-place program details",
                    ["P1_Line6A", "P1_Line6B_1", "P1_Line6B_2", "P1_Line6B_3", "P1_Line6C1", "P1_Line6C2", "P1_Line6D",
                     "P1_Line6E", "P1_Line8A_1", "P1_Line8A_2", "P1_Line8B", "P1_Line8C"],
                    allowed=FILLED_OR_NA,
                    notes={
                        "P1_Line6A": "With item 6.A (FWVP) only: the Form I-130 receipt number. " + RECEIPT,
                        "P1_Line6B_1": (
                            "With item 6.B (IMMVI) only: select one of 6.B(1)-(3). Each is its own box with on-state "
                            "'1', not part of the CB_AppType group."
                        ),
                        "P1_Line6C1": "With item 6.C only: the U.S. federal executive branch agency making the "
                        "referral (maxlen 100).",
                        "P1_Line6C2": "With item 6.C only: the agency representative's official email address (maxlen "
                        "38).",
                        "P1_Line6D": "With item 6.D only: the FRTF Task Force Registration Number (maxlen 11).",
                        "P1_Line6E": "With item 6.E only: the specific parole program or process (one line, about 77 "
                        "characters).",
                        "P1_Line8A_1": (
                            "With item 8.A (Military PIP, own behalf only) only: select 8.A(1) or (2). Each is its own "
                            "box with on-state '1'."
                        ),
                        "P1_Line8B": "With item 8.B only: the FRTF Task Force Registration Number (maxlen 11).",
                        "P1_Line8C": "With item 8.C only: the specific program or process (maxlen 100).",
                    },
                    choices={
                        "P1_Line6B_1": IMMVI_1,
                        "P1_Line6B_2": IMMVI_2,
                        "P1_Line6B_3": IMMVI_3,
                        "P1_Line8A_1": MILITARY_PIP_1,
                        "P1_Line8A_2": MILITARY_PIP_2,
                    },
                ),
                "reparole_program": q(
                    "Part 1, Items 10.E, 10.H, 10.I and 12: Re-parole program details and the Admit Until Date/Parole "
                    "on Form I-94",
                    ["P1_Line10E_1", "P1_Line10E_2", "P1_Line10E_3", "P1_Line10H_1", "P1_Line10H_2", "P1_Line10I",
                     "P1_Line12_DateOfAdmission"],
                    ["P1_Line12_DateOfAdmission"],
                    allowed=FILLED_OR_NA,
                    notes={
                        "P1_Line10E_1": "With item 10.E (IMMVI) only: select one of 10.E(1)-(3). Each is its own box "
                        "with on-state '1'.",
                        "P1_Line10H_1": "With item 10.H (Military PIP) only: select 10.H(1) or (2). Each is its own "
                        "box with on-state '1'.",
                        "P1_Line10I": "With item 10.I only: the specific program or process (maxlen 100).",
                        "P1_Line12_DateOfAdmission": (
                            "Item 12, required with item 10 or 11. Despite the name, it is the Admit Until Date "
                            "(paroled-until date) shown on the I-94, not the date of admission. " + DATE
                        ),
                    },
                    choices={
                        "P1_Line10E_1": IMMVI_1,
                        "P1_Line10E_2": IMMVI_2,
                        "P1_Line10E_3": IMMVI_3,
                        "P1_Line10H_1": MILITARY_PIP_1,
                        "P1_Line10H_2": MILITARY_PIP_2,
                    },
                ),
                "refugee_status": refugee_status(),
            },
            **applicant_part2(ANY_TYPE),
            "beneficiary_identity": q(
                "Part 2, Items 16 and 18-23: Information about them (name, date of birth, countries, phone, email, "
                "A-Number) when filing on behalf of someone else",
                ["P2_Line16_FamilyName", "P2_Line16_GivenName", "P2_Line16_MiddleName", "P2_Line18_DateOfBirth",
                 "P2_Line19_CountryOfBirth", "P2_Line20_CountryOfCitizenship", "P2_Line21_DaytimeTelephoneNumber",
                 "P2_Line22_Email", "P2_Line23_AlienNumber"],
                ["P2_Line16_FamilyName", "P2_Line16_GivenName", "P2_Line18_DateOfBirth", "P2_Line19_CountryOfBirth",
                 "P2_Line20_CountryOfCitizenship"],
                allowed=FILLED_OR_NA,
                notes={
                    "P2_Line16_FamilyName": "Item 16, the other person's legal name. " + ON_BEHALF,
                    "P2_Line18_DateOfBirth": "Item 18. " + DATE,
                    "P2_Line21_DaytimeTelephoneNumber": "Item 21: digits only, up to 15, so a foreign number with "
                    "country code fits.",
                    "P2_Line22_Email": "Item 22, if any (about 42 characters fit).",
                    "P2_Line23_AlienNumber": "Item 23, if any: 9 digits, no 'A' (comb box).",
                },
            ),
            "beneficiary_other_names": q(
                "Part 2, Item 17: Their other names used, three rows",
                name_rows("Part2_Line17"),
                ["Part2_Line17_FamilyName1", "Part2_Line17_GivenName1"],
                allowed=FILLED_OR_NA,
                notes={
                    "Part2_Line17_FamilyName1": "Row 1 (named 'Part2_Line17', unlike the other P2_ boxes of items "
                    "16-27). " + ON_BEHALF,
                    "Part2_Line17_FamilyName2": "Row 2.",
                    "Part2_Line17_FamilyName3": "Row 3.",
                },
            ),
            "beneficiary_mailing_address": beneficiary_address(24),
            "beneficiary_physical_address": beneficiary_address(25),
            "beneficiary_admission_details": q(
                "Part 2, Items 26-27: Their class of admission and most recent Form I-94 number, if any",
                ["P2_Line26_ClassofAdmission", "P2_Line27_I94RecordNo"],
                ["P2_Line26_ClassofAdmission", "P2_Line27_I94RecordNo"],
                allowed=FILLED_OR_NA,
                notes={
                    "P2_Line26_ClassofAdmission": (
                        "Item 26: the code on their most recent I-94. not_applicable when they have no I-94 (e.g. "
                        "outside the U.S. for an initial parole request). " + ON_BEHALF
                    ),
                    "P2_Line27_I94RecordNo": "Item 27: their 11-character I-94 number.",
                },
            ),
            "biographic_information": biographic_information(),
            "removal_proceedings": removal_proceedings(),
            "prior_documents": prior_documents(),
            "replacement_request": replacement_request(ANY_TYPE),
            "replacement_details": replacement_details(),
            "document_delivery": q(
                "Part 4, Items 7.a-7.b: Where to send the Reentry Permit or Refugee Travel Document",
                ["P4_Line7a", "P4_Line7b_CityOrTown", "P4_Line7b_Country"],
                ["P4_Line7a"],
                allowed=FILLED_OR_NA,
                notes={
                    "P4_Line7a": (
                        "Reentry permit and refugee travel document only (Part 1 items 1-3); every other type skips "
                        "items 7-9 (not_applicable). One group: 7.a is 'A', 7.b is 'B' (index [0] is 7.b). With 7.b "
                        "the document must be picked up abroad; complete pickup_notification."
                    ),
                    "P4_Line7b_CityOrTown": "With 7.b only: city of the U.S. Embassy, Consulate or office abroad. " + CITY,
                    "P4_Line7b_Country": "With 7.b only.",
                },
                choices={
                    "P4_Line7a": {
                        "7.a. To the U.S. address shown in Part 2, Item 3": "A",
                        "7.b. To a U.S. Embassy, U.S. Consulate, USCIS international field office, or DHS office "
                        "overseas": "B",
                    },
                },
            ),
            "pickup_notification": q(
                "Part 4, Items 8.a-9.c: Where to send the notice to pick up the document abroad (address, phone, "
                "email)",
                ["P4_Line8_CB"] + address_fields("P4_Line9a") + ["P4_Line9b_Email", "P4_Line9c_Email"],
                ["P4_Line8_CB"],
                allowed=FILLED_OR_NA,
                notes={
                    **address_notes("P4_Line9a", "With 8.b only (maxlen 34).", "With 8.b only."),
                    "P4_Line8_CB": "Items 8.a-8.b, only when item 7.b was selected: where to send the pickup notice.",
                    "P4_Line9b_Email": (
                        "Item 9.b, the DAYTIME PHONE NUMBER despite the 'Email' name: digits only, up to 15. The email "
                        "is P4_Line9c_Email."
                    ),
                    "P4_Line9c_Email": "Item 9.c, the email address (about 40 characters fit).",
                },
                choices={
                    "P4_Line8_CB": {
                        "8.a. To the address shown in Part 2, Item 3": "A",
                        "8.b. To the address shown in Part 4, Item 9.a": "B",
                    },
                    "P4_Line9a_Unit": UNIT,
                },
            ),
            "reentry_permit_time_outside": reentry_permit_time_outside(),
            "refugee_country_and_travel": q(
                "Part 6, Items 1-2: Country from which you are a refugee or asylee; do you plan to travel there?",
                ["P6_Line1_CountryRefugee", "P6_Line2_YesNo"],
                ["P6_Line1_CountryRefugee", "P6_Line2_YesNo"],
                allowed=FILLED_OR_NA,
                notes={
                    "P6_Line1_CountryRefugee": (
                        RTD_ONLY + " Item 1: the country that was the basis of the refugee or asylee approval, even if "
                        "it was the country of last habitual residence rather than nationality."
                    ),
                    "P6_Line2_YesNo": (
                        "Item 2. Yes needs an explanation in Part 13 and attorney review before filing (Instructions, "
                        "Travel Warning Regarding Voluntary Re-availment)."
                    ),
                },
                choices={"P6_Line2_YesNo": YES_NO},
            ),
            "refugee_conduct_since_status": q(
                "Part 6, Items 3.a-4.c: Since refugee admission or asylum grant: returned to that country, obtained "
                "its passport or benefits, reacquired its nationality, acquired a new nationality, or obtained refugee "
                "or asylee status elsewhere",
                ["P6_Line3a_YesNo", "P6_Line3b_YesNo", "P6_Line3c_YesNo", "P6_Line4a_YesNo", "P6_Line4b_YesNo",
                 "Line4c_Yes", "Line4c_No"],
                ["P6_Line3a_YesNo", "P6_Line3b_YesNo", "P6_Line3c_YesNo", "P6_Line4a_YesNo", "P6_Line4b_YesNo"],
                allowed=FILLED_OR_NA,
                notes={
                    "P6_Line3a_YesNo": (
                        RTD_ONLY + " Answer only with dated client confirmation; every Yes needs an "
                        "explanation in Part 13 and attorney review."
                    ),
                    "Line4c_Yes": (
                        "Item 4.c is two separate boxes, each with on-state 'Y' (named without the P6_ prefix): set "
                        "Line4c_Yes to 'Y' for Yes, or Line4c_No to 'Y' for No, never both."
                    ),
                    "Line4c_No": "Item 4.c No (on-state 'Y').",
                },
                choices={
                    "P6_Line3a_YesNo": YES_NO,
                    "P6_Line3b_YesNo": YES_NO,
                    "P6_Line3c_YesNo": YES_NO,
                    "P6_Line4a_YesNo": YES_NO,
                    "P6_Line4b_YesNo": YES_NO,
                    "Line4c_Yes": {"Yes": "Y"},
                    "Line4c_No": {"No": "Y"},
                },
            ),
            "refugee_filing_location": q(
                "Part 6, Items 5-6.c: Filing before departing the United States; if not, current location and "
                "countries visited since leaving",
                ["P6_Line5_YesNo", "P6_Line6a_YesNo", "P6_Line6b_CityOrTown", "P6_Line6c_Country"],
                ["P6_Line5_YesNo"],
                allowed=FILLED_OR_NA,
                notes={
                    "P6_Line5_YesNo": RTD_ONLY + " Item 5. Yes skips items 6.a-6.c; No requires them.",
                    "P6_Line6a_YesNo": "Item 6.a, only when item 5 is No.",
                    "P6_Line6b_CityOrTown": "Item 6.b, with 6.a Yes: city and country of the current location, one "
                    "line.",
                    "P6_Line6c_Country": "Item 6.c, with 6.a Yes: other countries visited since leaving the U.S., one "
                    "line.",
                },
                choices={"P6_Line5_YesNo": YES_NO, "P6_Line6a_YesNo": YES_NO},
            ),
            "proposed_travel": proposed_travel(ANY_TYPE),
            "parole_request": q(
                "Part 8, Items 1-3.b: Initial parole, parole in place or re-parole only: how the person qualifies, "
                "expected length of stay, intended arrival date and the consulate or office to notify",
                ["P8_Line1_Explain", "P8_Line2_ExpectedLengthTripinUS", "P8_Line3a_DateOfIntendedArrival",
                 "P8_Line3b_CityOrTown", "P8_Line3b_Country"],
                ["P8_Line1_Explain", "P8_Line2_ExpectedLengthTripinUS"],
                allowed=FILLED_OR_NA,
                notes={
                    "P8_Line1_Explain": (
                        "Part 1 items 6-11 only. Item 1: the urgent humanitarian reason or significant public benefit, "
                        "in four lines here (" + LINES_85[:-1] + "); the full explanation goes in Part 13 or a "
                        "statement with the evidence."
                    ),
                    "P8_Line2_ExpectedLengthTripinUS": (
                        "Item 2: expected length of stay in the U.S. (maxlen 30), e.g. '2 years'. Named "
                        "'Trip'. " + UNBOUND
                    ),
                    "P8_Line3a_DateOfIntendedArrival": "Item 3.a, only when the person is outside the U.S. " + DATE,
                    "P8_Line3b_CityOrTown": "Item 3.b, outside the U.S. only: city of the embassy, consulate or USCIS "
                    "office to notify. " + CITY,
                    "P8_Line3b_Country": "Item 3.b country.",
                },
            ),
            "reparole_employment_authorization": q(
                "Part 9, Item 1: Requesting an Employment Authorization Document upon approval of re-parole (Part 1 "
                "items 10-11)",
                ["P9_Line1_EAD"],
                ["P9_Line1_EAD"],
                allowed=FILLED_OR_NA,
                notes={
                    "P9_Line1_EAD": (
                        "Re-parole (Part 1 items 10-11) only, and only when the EAD is requested; otherwise "
                        "not_applicable. One box: the Instructions speak of selecting Yes or No, but the form has only "
                        "this box. The blank stores '0' here by default."
                    ),
                },
                choices={"P9_Line1_EAD": {"I am requesting an EAD upon approval of my new period of parole": "1"}},
            ),
            **signature_parts(),
        },
    ),
}

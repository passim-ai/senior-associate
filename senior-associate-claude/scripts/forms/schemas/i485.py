"""Question schemas for Form I-485 (edition 09/18/26).

Four postures share one set of question definitions, built fresh for each schema so that
every schema's `required_questions` is complete on its own:

- i485_family_based: immediate relative or family-preference beneficiary (Part 2 item 3.a);
- i485_asylee_refugee: INA 209 adjustment of an asylee or refugee (Part 2 item 3.d);
- i485_employment_principal and i485_employment_derivative_child: Part 2 item 3.b.

Every field name and checkbox on-state below was checked against the blank's field list
(schemas/fields/I-485.json) and each box's position and tooltip on the 09/18/26 PDF. Many
names on this edition do not match their part or item number; the field notes say which
box is which wherever a name misleads.
"""
from __future__ import annotations

from typing import Any

from _common import (DATE, FILLED, FILLED_OR_NA, FOREIGN_ONLY, NOT_APPLICABLE, PENDING_SIGNATURE, SIGNATURE_STATUSES,
                     UNIT, YES_NO, q)

EDITION = "09/18/26"
FIELD_LIST = "I-485.json"

NA_ONLY = [NOT_APPLICABLE]

UNIT_PLAIN = {"Apt.": "APT", "Ste.": "STE", "Flr.": "FLR"}
# Part 1 item 18 physical and mailing address unit boxes carry padded on-states.

STATE = "2-letter state code (drop-down)."
US_ONLY = "U.S. address only."


def yes_no_group(
    label: str,
    items: list[tuple[str, str, str | None]],
    *,
    extra_fields: list[str] | None = None,
    extra_notes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """A group of Part 9 yes/no items: (item number and short text, field, condition or None).

    Conditional items stay out of the non-empty list; their note says when to answer them.
    """
    fields = [field for _, field, _ in items]
    notes = {}
    for item, field, condition in items:
        notes[field] = f"Item {item}." + (f" Answer only if {condition}; otherwise leave blank." if condition else "")
    notes.update(extra_notes or {})
    return q(
        label,
        fields + list(extra_fields or []),
        [field for _, field, condition in items if not condition],
        notes=notes,
        choices={field: YES_NO for field in fields},
    )


# --------------------------------------------------------------------------- Part 2


EOIR_NOTE = "Item 1: filing with EOIR while in removal, exclusion, rescission, or deportation proceedings."
FILING_TYPE = {"Principal Applicant": "1fA", "Derivative Applicant": "1fB"}
CSPA_NOTE = "Item 5: 21 or older and applying as a child under the Child Status Protection Act."
SECTION_245I_NOTE = (
    "Item 4: applying under INA 245(i) (family, employment, special immigrant and Diversity Visa "
    "categories only)."
)

FAMILY_CATEGORIES = {
    "Spouse of a U.S. citizen": "3a0",
    "Unmarried child under 21 of a U.S. citizen": "3a1",
    "Parent of a U.S. citizen (citizen 21 or older)": "3a2",
    "K-1 fiance(e) or K-2 child of a fiance(e) of a U.S. citizen": "3a3",
    "Widow or widower of a U.S. citizen": "3a4",
    "Spouse, child, or parent of a deceased U.S. active-duty service member (NDAA)": "3a5",
    "Unmarried son or daughter of a U.S. citizen, 21 or older (F1)": "3a6",
    "Married son or daughter of a U.S. citizen (F3)": "3a7",
    "Brother or sister of a U.S. citizen (citizen 21 or older) (F4)": "3a8",
    "Spouse of a lawful permanent resident (F2A)": "3a9",
    "Unmarried child under 21 of a lawful permanent resident (F2A)": "3a10",
    "Unmarried son or daughter of a lawful permanent resident, 21 or older (F2B)": "3a11",
    "VAWA self-petitioning spouse of a U.S. citizen or LPR": "3a12",
    "VAWA self-petitioning child of a U.S. citizen or LPR": "3a13",
    "VAWA self-petitioning parent of a U.S. citizen (citizen 21 or older)": "3a14",
}

I140_CATEGORIES = {
    "Alien of extraordinary ability (EB-1A)": "3b1",
    "Outstanding professor or researcher (EB-1B)": "3b2",
    "Multinational executive or manager (EB-1C)": "3b3",
    "Advanced degree or exceptional ability, no National Interest Waiver (EB-2)": "3b4",
    "Professional (EB-3)": "3b5",
    "Skilled worker (EB-3)": "3b6",
    "Other worker (EB-3)": "3b7",
    "National Interest Waiver (EB-2 NIW)": "3b8",
}


def employment_filing_category(*, derivative: bool) -> dict[str, Any]:
    who = (
        "Must be Derivative Applicant (1fB); select the principal's category in item 3.b."
        if derivative
        else "Principal Applicant (1fA)."
    )
    return q(
        "Part 2 items 1-5: EOIR proceedings; principal or derivative; employment-based category (3.b); "
        "INA 245(i); CSPA",
        ["Pt2Line1_YN", "Pt2Line2_CB", "Pt2Line3b_CB140", "Pt2Line3b_CB526", "Pt2Line4_CB", "Pt2Line5_CB"],
        ["Pt2Line1_YN", "Pt2Line2_CB", "Pt2Line4_CB", "Pt2Line5_CB"],
        notes={
            "Pt2Line1_YN": EOIR_NOTE,
            "Pt2Line2_CB": who,
            "Pt2Line3b_CB140": "Form I-140 categories. Select exactly one box in all of item 3 (this or CB526).",
            "Pt2Line3b_CB526": "Alien investor (Form I-526 or I-526E) only; a single box, not part of the CB140 group.",
            "Pt2Line4_CB": SECTION_245I_NOTE,
            "Pt2Line5_CB": CSPA_NOTE,
        },
        choices={
            "Pt2Line1_YN": YES_NO,
            "Pt2Line2_CB": FILING_TYPE,
            "Pt2Line3b_CB140": I140_CATEGORIES,
            "Pt2Line3b_CB526": {"Alien investor (EB-5)": "3b0"},
            "Pt2Line4_CB": YES_NO,
            "Pt2Line5_CB": YES_NO,
        },
    )


def underlying_petition(posture: str) -> dict[str, Any]:
    receipt_note = {
        "family": (
            "Receipt number of the I-130, I-360 or I-129F, 13 characters, no dashes. not_applicable when "
            "the I-485 is filed together with the I-130 (no receipt yet)."
        ),
        "employment": (
            "Receipt number of the I-140 or I-526/I-526E (the principal's, for a derivative), 13 characters, "
            "no dashes. not_applicable only when the I-140 is filed together with this I-485 (no receipt "
            "yet); the audit then asks for neither the receipt number nor the priority date."
        ),
        "asylee_refugee": (
            "If any: the I-730 receipt number for a follow-to-join beneficiary, or the I-589 receipt number "
            "for an affirmative grant. Asylum granted by an immigration judge may have none."
        ),
    }[posture]
    date_note = {
        "family": f"Priority date on the I-797, if any. {DATE}",
        "employment": f"Priority date on the I-797. {DATE}",
        "asylee_refugee": "No priority date applies to asylees and refugees; leave it blank (the form asks 'if any').",
    }[posture]
    nonempty = ["Pt2Line2_Receipt", "Pt2Line2_Date"] if posture == "employment" else ["Pt2Line2_Receipt"]
    return q(
        "Part 2 item 2: receipt number and priority date of the underlying petition (if any)",
        ["Pt2Line2_Receipt", "Pt2Line2_Date"],
        nonempty,
        allowed=FILLED_OR_NA,
        notes={"Pt2Line2_Receipt": receipt_note, "Pt2Line2_Date": date_note},
    )


def principal_applicant(allowed: list[str]) -> dict[str, Any]:
    return q(
        "Part 2 item 2: principal applicant's name, A-Number and date of birth (derivative applicants only)",
        ["Pt2Line2_FamilyName", "Pt2Line2_GivenName", "Pt2Line2_MiddleName", "Pt2Line2_AlienNumber", "Pt1Line2_DOB"],
        ["Pt2Line2_FamilyName", "Pt2Line2_GivenName", "Pt1Line2_DOB"],
        allowed=allowed,
        notes={
            "Pt2Line2_AlienNumber": "Principal's A-Number, 9 digits, if any; leave blank if the principal has none.",
            "Pt1Line2_DOB": f"The PRINCIPAL's date of birth (the name says Pt1). {DATE}",
        },
    )


# --------------------------------------------------------------------------- Part 3


def affidavit_of_support_exemption(note: str) -> dict[str, Any]:
    return q(
        "Part 3 item 1: affidavit of support (I-864) exemption, or why none is requested",
        ["Pt3Line1_CB"],
        ["Pt3Line1_CB"],
        notes={"Pt3Line1_CB": note},
        choices={
            "Pt3Line1_CB": {
                "1.a 40 qualifying quarters of work": "0",
                "1.b Under 18 child of a U.S. citizen who will automatically naturalize (INA 320)": "1",
                "1.c Widow or widower of a U.S. citizen (I-360)": "2",
                "1.d VAWA self-petitioner": "3",
                "1.e Not required by statute to submit an I-864 or request an exemption": "4",
                "1.f No exemption; an I-864 is required and submitted": "5",
            }
        },
    )


# --------------------------------------------------------------------------- Part 4


def current_employment(*, school: bool = False) -> dict[str, Any]:
    subject = "school attended" if school else "employment or school"
    return q(
        f"Part 4 item 7: current or most recent {subject} (one row; the rest of the last 5 years in Part 14)",
        ["Pt4Line7_EmployerName[0]", "Pt4Line7_EmployerName[2]", "Pt4Line7_EmployerName[1]", "Part4Line7_StreetName[0]",
         "P4Line7_Unit", "P4Line7_Number", "P4Line7_City", "P4Line7_State", "P4Line7_ZipCode", "P4Line7_Province",
         "P4Line7_PostalCode", "P4Line7_Country", "Pt4Line7_DateFrom", "Pt4Line7_DateTo", "Part4Line7_StreetName[1]"],
        ["Pt4Line7_EmployerName[2]", "Pt4Line7_EmployerName[1]", "Pt4Line7_DateFrom"],
        notes={
            "Pt4Line7_EmployerName[0]": (
                "Left box under the label 'Employer or School (current or most recent)'. The form gives no "
                "further instruction; it reads as asking which kind of entry this is (Employer, School, "
                "Self-employed, Unemployed, Retired). The name itself goes in [2]."
            ),
            "Pt4Line7_EmployerName[2]": (
                "Right box, 'Name of Employer, Company, or School'. N/A when unemployed or retired. "
                "34 characters at most."
            ),
            "Pt4Line7_EmployerName[1]": (
                "Full-width box, 'Your Occupation'. If unemployed or retired, say so. 34 characters at most."
            ),
            "Part4Line7_StreetName[0]": "Street number and name of the employer or school. 34 characters at most.",
            "P4Line7_State": f"{US_ONLY} {STATE}",
            "P4Line7_ZipCode": US_ONLY,
            "P4Line7_Province": FOREIGN_ONLY,
            "P4Line7_PostalCode": FOREIGN_ONLY,
            "Pt4Line7_DateFrom": DATE,
            "Pt4Line7_DateTo": f"{DATE[:-1]}, or PRESENT for the current entry.",
            "Part4Line7_StreetName[1]": (
                "NOT an address: 'If unemployed or retired, source of financial support'. Leave blank otherwise."
            ),
        },
        choices={"P4Line7_Unit": UNIT_PLAIN},
    )


# --------------------------------------------------------------------------- Part 7


def children() -> dict[str, Any]:
    child_fields = []
    notes = {
        "Pt6Line1_TotalChildren": (
            "Part 7 item 1 (the name says Pt6): number of ALL living children, including adult, step and "
            "adopted children; None if zero. 5 characters at most."
        ),
    }
    choices = {}
    for line, label in (("Pt7Line2", "Child 1 (item 2)"), ("Pt7Line3", "Child 2 (item 3)")):
        child_fields += [
            f"{line}_FamilyName",
            f"{line}_GivenName",
            f"{line}_MiddleName",
            f"{line}_AlienNumber",
            f"{line}_DateofBirth",
            f"{line}_Country",
            f"{line}_Relationship",
            f"{line}_YN",
        ]
        notes[f"{line}_FamilyName"] = (
            f"{label}. Not Part 8 race or ethnicity, whose boxes also start Pt7. Children 3 and up go in Part 14."
        )
        notes[f"{line}_DateofBirth"] = DATE
        notes[f"{line}_Country"] = "Country of birth."
        notes[f"{line}_Relationship"] = "Biological child, stepchild, legally adopted child, and so on. 34 characters at most."
        notes[f"{line}_YN"] = "Is this child also applying now on a separate Form I-485?"
        choices[f"{line}_YN"] = YES_NO
    return q(
        "Part 7 items 1-3: total number of living children, and children 1 and 2",
        ["Pt6Line1_TotalChildren"] + child_fields,
        ["Pt6Line1_TotalChildren"],
        notes=notes,
        choices=choices,
    )


# --------------------------------------------------------------------------- Part 8


RACES = [
    ("Pt7Line2_Race[0]", "Asian", "AS"),
    ("Pt7Line2_Race[1]", "White", "WH"),
    ("Pt7Line2_Race[2]", "Black or African American", "BL"),
    ("Pt7Line2_Race[3]", "American Indian or Alaska Native", "AI"),
    ("Pt7Line2_Race[4]", "Native Hawaiian or Other Pacific Islander", "HW"),
]


# --------------------------------------------------------------------------- Part 9


def organization_history() -> dict[str, Any]:
    org_fields = {
        1: [
            ("Pt9Line2_Organization1", "Organization 1 name (item 2)."),
            ("Pt9Line3_CityTownOfBirth", "Organization 1 city or town (item 3); the name says birth."),
            ("Pt9Line3_State", "Organization 1 state or province (item 3)."),
            ("Pt9Line3_Country", "Organization 1 country (item 3)."),
            ("Pt9Line4_FamilyName", "Organization 1 NATURE of the organization (item 4); the name says family name."),
            ("Pt9Line4_Involvement", "Organization 1 nature of your involvement, role or positions (item 4)."),
            ("Pt9Line5_DateFrom", f"Organization 1 membership from (item 5). {DATE}"),
            ("Pt9Line5_DateTo", f"Organization 1 membership to (item 5). {DATE}"),
        ],
        2: [
            ("Pt9Line6_Organization2", "Organization 2 name (item 6)."),
            ("Pt9Line7_CityTownOfBirth", "Organization 2 city or town (item 7)."),
            ("Pt9Line7_State", "Organization 2 state or province (item 7)."),
            ("Pt9Line7_Country", "Organization 2 country (item 7)."),
            ("Pt9Line8_FamilyName", "Organization 2 NATURE of the organization (item 8); the name says family name."),
            ("Pt9Line8_Involvement", "Organization 2 nature of your involvement (item 8)."),
            ("Pt9Line9_DateFrom", f"Organization 2 membership from (item 9). {DATE}"),
            ("Pt9Line9_DateTo", f"Organization 2 membership to (item 9). {DATE}"),
        ],
    }
    fields = ["Pt8Line1_YesNo"] + [field for rows in org_fields.values() for field, _ in rows]
    notes = {
        "Pt8Line1_YesNo": (
            "Part 9 item 1: EVER a member of or associated with any organization, party, club, union, "
            "society or similar group anywhere. Often Yes (unions, parties, religious or student groups); "
            "ask the client rather than default. If Yes, items 2-9; more than two organizations go in Part 14."
        )
    }
    notes.update({field: note for rows in org_fields.values() for field, note in rows})
    return q(
        "Part 9 items 1-9: organization memberships and associations (two rows; more in Part 14)",
        fields,
        ["Pt8Line1_YesNo"],
        notes=notes,
        choices={"Pt8Line1_YesNo": YES_NO},
    )


PUBLIC_CHARGE_CATEGORIES = {
    "VAWA self-petitioner (I-360)": "5",
    "Special immigrant juvenile (I-360)": "6",
    "Certain Afghan or Iraqi national (I-360 or DS-157)": "0",
    "Asylee (I-589 or I-730)": "3",
    "Refugee (I-590 or I-730)": "1",
    "U nonimmigrant under INA 245(m)": "2",
    "Any other category while in valid U nonimmigrant status": "4",
    "T nonimmigrant under INA 245(l)": "9",
    "Any other category with a pending prima facie I-914 or in valid T status": "12",
    "Cuban Adjustment Act": "7",
    "Cuban Adjustment Act, battered spouse or child": "10",
    "HRIFA dependent": "11",
    "HRIFA dependent, battered spouse or child": "8",
    "Cuban and Haitian entrant (IRCA section 202)": "17",
    "Lautenberg parolee": "18",
    "National of Vietnam, Cambodia or Laos (Pub. L. 106-429 section 586)": "19",
    "Registry (continuous residence since before 1/1/1972)": "13",
    "Amerasian Homecoming Act": "15",
    "Polish or Hungarian parolee": "16",
    "NACARA section 203": "14",
    "American Indian born in Canada or Texas Band of Kickapoo": "20",
    "Liberian Refugee Immigration Fairness (NDAA FY2020 section 7611)": "21",
    "Syrian national (Pub. L. 106-378)": "24",
    "Spouse, child or parent of a U.S. active-duty service member (NDAA)": "22",
    "Not exempt: will complete items 57-64": "23",
}


def public_charge(note: str) -> dict[str, Any]:
    return q(
        "Part 9 item 56: public charge exemption category, or not exempt",
        ["Pt9Line56_CB"],
        ["Pt9Line56_CB"],
        notes={"Pt9Line56_CB": note},
        choices={"Pt9Line56_CB": PUBLIC_CHARGE_CATEGORIES},
    )


def public_charge_factors(allowed: list[str]) -> dict[str, Any]:
    skills = [f"TextField{n}" for n in range(1, 9)]
    return q(
        "Part 9 items 57-62: household size and family status, income, assets, liabilities, education, "
        "skills (only if not exempt in item 56)",
        ["Pt9Line57_HouseholdSize", "Pt9Line53_CB", "Pt9Line59_CB", "Pt9Line60_CB", "Pt9Line61_CB", "Pt9Line61_diploma"]
        + skills,
        ["Pt9Line57_HouseholdSize", "Pt9Line53_CB", "Pt9Line59_CB", "Pt9Line60_CB", "Pt9Line61_CB", "TextField1"],
        allowed=allowed,
        notes={
            "Pt9Line57_HouseholdSize": (
                "Item 57, in the applicant's own words. A stated household size must match the people whose "
                "income, assets and liabilities are counted in items 58-60 (and the I-864 household)."
            ),
            "Pt9Line53_CB": "Item 58, annual household income (the name says 53). Exclude means-tested benefits.",
            "Pt9Line59_CB": "Item 59, total household assets.",
            "Pt9Line60_CB": "Item 60, total household liabilities.",
            "Pt9Line61_CB": "Item 61, highest education completed; pick the nearest equivalent.",
            "Pt9Line61_diploma": "Only with 'Less than a high school diploma' (C): highest grade completed.",
            "TextField1": "Item 62, skills, row 1 of 8 (TextField1-TextField8): certifications, licenses, trades, "
            "languages.",
        },
        choices={
            "Pt9Line53_CB": {
                "$0-27,000": "A",
                "$27,001-52,000": "B",
                "$52,001-85,000": "C",
                "$85,001-141,000": "D",
                "Over $141,000": "E",
            },
            "Pt9Line59_CB": {
                "$0-18,400": "A",
                "$18,401-136,000": "B",
                "$136,001-321,400": "C",
                "$321,401-707,100": "D",
                "Over $707,100": "E",
            },
            "Pt9Line60_CB": {
                "$0": "A",
                "$1-10,100": "B",
                "$10,101-57,700": "C",
                "$57,701-186,800": "D",
                "Over $186,800": "E",
            },
            "Pt9Line61_CB": {
                "Less than a high school diploma": "C",
                "High school diploma, GED, or alternative credential": "2",
                "1 or more years of college credit, no degree": "1",
                "Associate's degree": "3",
                "Bachelor's degree": "7",
                "Master's degree": "4",
                "Professional degree (JD, MD, DMD)": "5",
                "Doctorate degree": "6",
            },
        },
    )


def public_benefits(allowed: list[str]) -> dict[str, Any]:
    columns = {
        1: "means-tested public benefit received",
        2: f"start date ({DATE[:-1]})",
        3: f"end date ({DATE[:-1]})",
        4: "dollar amount, if applicable",
        5: "reason received",
    }
    table = [f"Pt8Line68c_Column{c}Row{r}" for r in range(1, 5) for c in range(1, 6)]
    notes = {
        "Pt9Line63_YesNo": "Item 63: ever received any means-tested public benefit (past or current).",
    }
    notes.update(
        {
            f"Pt8Line68c_Column{c}Row1": f"Item 64 table (only if item 63 is Yes), column {c}: {text}. Rows 1-4 are Row1-Row4."
            for c, text in columns.items()
        }
    )
    return q(
        "Part 9 items 63-64: ever received means-tested public benefits; which, when, how much, why "
        "(only if not exempt in item 56)",
        ["Pt9Line63_YesNo"] + table,
        ["Pt9Line63_YesNo"],
        allowed=allowed,
        notes=notes,
        choices={"Pt9Line63_YesNo": YES_NO},
    )


# --------------------------------------------------------------------------- Parts 10-14


def additional_information() -> dict[str, Any]:
    fields: list[str] = []
    notes: dict[str, str] = {}
    for block in range(4):
        item = block + 2
        fields += [
            f"Pt9Line3a_PageNumber[{block}]",
            f"Pt9Line3b_PartNumber[{block}]",
            f"Pt9Line3c_ItemNumber[{block}]",
            f"P14_Line{item}_AdditionalInfo",
        ]
    notes["Pt9Line3a_PageNumber[0]"] = (
        "Part 14 item 2 page number (the Pt9Line3a/3b/3c names belong to Part 14). Block n of items 2-5 uses "
        "Pt9Line3a/3b/3c[n-2] with P14_Line<n>_AdditionalInfo. 2 characters at most."
    )
    notes["Pt9Line3b_PartNumber[0]"] = "Part number for item 2; 6 characters at most."
    notes["Pt9Line3c_ItemNumber[0]"] = "Item number for item 2; 6 characters at most."
    notes["P14_Line2_AdditionalInfo"] = (
        "About five lines of 84 characters per block; break lines yourself. Part 14 item 1 (name) and the "
        "A-Number fill from Part 1. Use a continuation sheet after four blocks."
    )
    return q(
        "Part 14 items 2-5: additional information (continuations of any item, and explanations of Part 9 "
        "Yes answers), with page, part and item numbers",
        fields,
        ["Pt9Line3a_PageNumber[0]", "Pt9Line3b_PartNumber[0]", "Pt9Line3c_ItemNumber[0]", "P14_Line2_AdditionalInfo"],
        allowed=FILLED_OR_NA,
        notes=notes,
    )


# --------------------------------------------------------------------------- schemas


COMMON_NOTES = [
    "Edition 09/18/26. Field names often do not match their part or item: Part 8 boxes start Pt7, "
    "Part 10 boxes start Pt3, Part 7 item 1 is Pt6Line1_TotalChildren, Part 9 mixes Pt8 and Pt9 names, "
    "and Part 9 items 65-84 are Pt9Line67-Pt9Line86. Use the field notes, not the names.",
    "Global fields share one value everywhere: the A-Number (Pt1Line4_AlienNumber) prints at the top of every "
    "page and the Part 1 name prints in Part 14 item 1. Map only the base name.",
    "The instructions (How To Complete, item 3) say to type N/A when a question does not apply and None "
    "when a count is zero. Leave check boxes blank instead. Boxes marked '(if any)' (mobile phone, email, "
    "A-Numbers, receipt numbers) stay blank when there is nothing to report, as do the items the form asks "
    "for only in some cases: Part 1 item 10 (passport) after an entry without inspection, item 12 when no "
    "I-94 was issued, and Part 4 item 8 when it would repeat item 7. The audit does not require them then.",
    "Part 9 yes/no items: leave blank until confirmed by the client; record the source and date, and explain "
    "every Yes in Part 14. Conditional items (20-21, 29, 35.b, 40, 75, 84) stay blank unless their trigger "
    "is Yes.",
    "Part 14 (question additional_information) is the one place for every continuation: address and "
    "employment history beyond one row, children 3+, organizations 3+, prior spouses 2+, and Part 9 "
    "explanations. Each block names its page, part and item.",
    "Part 13 (signature at interview, Pt13_* boxes) is completed only at the interview; leave it blank.",
]


def shared_tail(
    *,
    aos_note: str,
    public_charge_note: str,
    public_charge_details: list[str],
    school: bool = False,
) -> dict[str, dict[str, Any]]:
    """Parts 3-14, the same on every posture except the notes and allowed statuses passed in."""
    return {
        "affidavit_of_support_exemption": affidavit_of_support_exemption(aos_note),
        "immigrant_visa_abroad": q(
            "Part 4 items 1-4: ever applied for an immigrant visa abroad; consulate, decision and date",
            ["Pt4Line1_YN", "Pt4Line2_CityTown", "Pt4Line2_CityTownOfBirth", "Pt4Line3_Decision", "Pt4Line4_Date"],
            ["Pt4Line1_YN"],
            notes={
                "Pt4Line2_CityTown": "Only if Yes: city of the U.S. embassy or consulate.",
                "Pt4Line2_CityTownOfBirth": "Only if Yes: COUNTRY of the embassy or consulate (the name says birth).",
                "Pt4Line3_Decision": "Only if Yes: approved, refused, denied, withdrawn, and so on.",
                "Pt4Line4_Date": f"Only if Yes: date of the decision. {DATE}",
            },
            choices={"Pt4Line1_YN": YES_NO},
        ),
        "prior_adjustment_or_rescission": q(
            "Part 4 items 5-6: previously applied for permanent residence in the U.S.; ever held LPR status "
            "later rescinded",
            ["Pt4Line5_YN", "Pt4Line6_YN"],
            ["Pt4Line5_YN", "Pt4Line6_YN"],
            notes={"Pt4Line5_YN": "Item 5.", "Pt4Line6_YN": "Item 6 (rescission under INA 246)."},
            choices={"Pt4Line5_YN": YES_NO, "Pt4Line6_YN": YES_NO},
        ),
        "current_employment": current_employment(school=school),
        "last_employment_outside_us": q(
            "Part 4 item 8: most recent employer or school outside the United States (if not already listed)",
            ["Pt4Line8_EmployerName", "Pt4Line8_Occupation", "P4Line8_StreetName", "P4Line8_Unit", "P4Line8_Number",
             "P4Line8_City", "P4Line8_State", "P4Line8_ZipCode", "P4Line8_Province", "P4Line8_PostalCode",
             "P4Line8_Country", "Pt4Line8_DateFrom", "Pt4Line8_DateTo", "Part4Line8_StreetName"],
            ["Pt4Line8_EmployerName", "Pt4Line8_Occupation", "P4Line8_Country", "Pt4Line8_DateFrom", "Pt4Line8_DateTo"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt4Line8_EmployerName": (
                    "Name of employer, company or school. 34 characters at most. Item 8 asks for this only if it "
                    "is not already listed in item 7: with nothing to add (never worked or studied abroad, or "
                    "already listed), mark the question not_applicable and leave the row blank."
                ),
                "Pt4Line8_Occupation": "If unemployed or retired, say so. 34 characters at most.",
                "P4Line8_StreetName": "Street number and name. 34 characters at most.",
                "P4Line8_State": "Leave blank for a foreign address.",
                "P4Line8_ZipCode": "Leave blank for a foreign address.",
                "Pt4Line8_DateFrom": DATE,
                "Pt4Line8_DateTo": DATE,
                "Part4Line8_StreetName": (
                    "NOT an address: 'If unemployed or retired, source of financial support' for item 8."
                ),
            },
            choices={"P4Line8_Unit": UNIT_PLAIN},
        ),
        "parents": q(
            "Part 5 items 1-2, 4-6, 8: each parent's legal name, name at birth (if different) and country of birth",
            ["Pt5Line1_FamilyName", "Pt5Line1_GivenName", "Pt5Line1_MiddleName", "Pt5Line2_FamilyName",
             "Pt5Line2_GivenName", "Pt5Line2_MiddleName", "Pt5Line5_CityTownOfBirth", "Pt5Line6_FamilyName",
             "Pt5Line6_GivenName", "Pt5Line6_MiddleName", "Pt5Line7_FamilyName", "Pt5Line7_GivenName",
             "Pt5Line7_MiddleName", "Pt5Line10_CityTownOfBirth"],
            ["Pt5Line1_FamilyName", "Pt5Line1_GivenName", "Pt5Line5_CityTownOfBirth", "Pt5Line6_FamilyName",
             "Pt5Line6_GivenName", "Pt5Line10_CityTownOfBirth"],
            notes={
                "Pt5Line1_FamilyName": "Parent 1 legal name (item 1).",
                "Pt5Line2_FamilyName": "Parent 1 name at birth (item 2), only if different from the legal name.",
                "Pt5Line5_CityTownOfBirth": "Parent 1 COUNTRY of birth (item 4); the name says city.",
                "Pt5Line6_FamilyName": "Parent 2 legal name (item 5).",
                "Pt5Line7_FamilyName": "Parent 2 name at birth (item 6), only if different from the legal name.",
                "Pt5Line10_CityTownOfBirth": "Parent 2 COUNTRY of birth (item 8); the name says city.",
            },
        ),
        "parents_dates_of_birth": q(
            "Part 5 items 3 and 7: each parent's date of birth",
            ["Pt5Line3_DateofBirth", "Pt5Line8_DateofBirth[0]"],
            ["Pt5Line3_DateofBirth", "Pt5Line8_DateofBirth[0]"],
            notes={
                "Pt5Line3_DateofBirth": f"Parent 1 (item 3). {DATE}",
                "Pt5Line8_DateofBirth[0]": (
                    f"Parent 2 (item 7). {DATE} Pt5Line8_DateofBirth[1]-[3] are spouse and marriage dates in Part 6."
                ),
            },
        ),
        "marital_status": q(
            "Part 6 items 1-3: marital status; spouse in the U.S. armed forces or Coast Guard; times married",
            ["Pt6Line1_MaritalStatus", "Pt5Line2_YNNA", "Pt6Line3_TimesMarried"],
            ["Pt6Line1_MaritalStatus", "Pt5Line2_YNNA", "Pt6Line3_TimesMarried"],
            notes={
                "Pt5Line2_YNNA": "Part 6 item 2 (the name says Pt5). N/A ('A') if not married.",
                "Pt6Line3_TimesMarried": (
                    "Count every marriage, including the current one, annulled ones and remarriages to the same "
                    "person; None if never married. 5 characters at most."
                ),
            },
            choices={
                "Pt6Line1_MaritalStatus": {
                    "Single, never married": "1",
                    "Married": "2",
                    "Divorced": "3",
                    "Widowed": "4",
                    "Marriage annulled": "5",
                    "Legally separated": "7",
                },
                "Pt5Line2_YNNA": {"Yes": "Y", "No": "N", "N/A": "A"},
            },
        ),
        "current_spouse": q(
            "Part 6 items 4-10: current spouse's name, A-Number, date and country of birth, address; date and "
            "place of marriage; spouse applying with you",
            ["Pt6Line4_FamilyName", "Pt6Line4_GivenName", "Pt6Line4_MiddleName", "Pt6Line5_AlienNumber",
             "Pt5Line8_DateofBirth[1]", "Pt6Line7_Country", "Part6Line8_StreetName", "P6Line8_Unit", "P6Line8_Number",
             "P6Line8_City", "P6Line8_State", "P6Line8_ZipCode", "P6Line8_Province", "P6Line8_PostalCode",
             "P6Line8_Country", "Pt6Line10_CityTownOfBirth[0]", "Pt6Line10_State[0]", "Pt6Line10_Country[0]",
             "Pt5Line8_DateofBirth[2]", "Pt6Line11_YN"],
            ["Pt6Line4_FamilyName", "Pt6Line4_GivenName", "Pt5Line8_DateofBirth[1]", "Pt6Line7_Country",
             "Part6Line8_StreetName", "P6Line8_City", "P6Line8_Country", "Pt6Line10_CityTownOfBirth[0]",
             "Pt6Line10_Country[0]", "Pt5Line8_DateofBirth[2]", "Pt6Line11_YN"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt6Line5_AlienNumber": "Spouse's A-Number, 9 digits, if any.",
                "Pt5Line8_DateofBirth[1]": f"Current spouse's DATE OF BIRTH (item 6). {DATE}",
                "Pt6Line7_Country": "Current spouse's country of BIRTH (item 7).",
                "Part6Line8_StreetName": "Spouse's current physical address (item 8). 34 characters at most.",
                "P6Line8_State": f"{US_ONLY} {STATE}",
                "P6Line8_ZipCode": US_ONLY,
                "P6Line8_Province": FOREIGN_ONLY,
                "P6Line8_PostalCode": FOREIGN_ONLY,
                "P6Line8_Country": "Country of the spouse's address.",
                "Pt6Line10_CityTownOfBirth[0]": "City or town of the current MARRIAGE (item 9); the name says birth.",
                "Pt6Line10_State[0]": "State or province of the current marriage (free text).",
                "Pt6Line10_Country[0]": "Country of the current marriage.",
                "Pt5Line8_DateofBirth[2]": f"DATE OF MARRIAGE to the current spouse (item 9). {DATE}",
                "Pt6Line11_YN": "Item 10: is the current spouse applying with you?",
            },
            choices={"P6Line8_Unit": UNIT_PLAIN, "Pt6Line11_YN": YES_NO},
        ),
        "prior_spouse": q(
            "Part 6 items 11-18: prior spouse (one row; more prior marriages in Part 14)",
            ["Pt6Line12_FamilyName", "Pt6Line12_GivenName", "Pt6Line12_MiddleName", "Pt5Line8_DateofBirth[3]",
             "Pt6Line14_Country", "Pt6Line15_Country", "Pt6Line16_DateofBirth[0]", "Pt6Line10_CityTownOfBirth[1]",
             "Pt6Line10_State[1]", "Pt6Line10_Country[1]", "Pt6Line18_CityTownOfBirth", "Pt6Line18_State",
             "Pt6Line18_Country", "Pt6Line16_DateofBirth[1]", "Pt6Line19_MaritalStatus",
             "Pt6Line19_HowMarriageEndedOther"],
            ["Pt6Line12_FamilyName", "Pt6Line12_GivenName", "Pt5Line8_DateofBirth[3]", "Pt6Line14_Country",
             "Pt6Line15_Country", "Pt6Line16_DateofBirth[0]", "Pt6Line10_CityTownOfBirth[1]", "Pt6Line10_Country[1]",
             "Pt6Line18_CityTownOfBirth", "Pt6Line18_Country", "Pt6Line16_DateofBirth[1]", "Pt6Line19_MaritalStatus"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt6Line12_FamilyName": "Prior spouse's legal name, family name before the marriage (item 11).",
                "Pt5Line8_DateofBirth[3]": f"Prior spouse's date of birth (item 12). {DATE}",
                "Pt6Line14_Country": "Prior spouse's country of BIRTH (item 13).",
                "Pt6Line15_Country": "Prior spouse's country of CITIZENSHIP or nationality (item 14).",
                "Pt6Line16_DateofBirth[0]": f"DATE OF MARRIAGE to the prior spouse (item 15). {DATE}",
                "Pt6Line10_CityTownOfBirth[1]": "City of the prior MARRIAGE (item 16); the name says birth.",
                "Pt6Line10_State[1]": "State or province of the prior marriage (item 16); the audit asks for it when "
                "the country is the United States.",
                "Pt6Line10_Country[1]": "Country of the prior marriage (item 16).",
                "Pt6Line18_CityTownOfBirth": "City where the prior marriage legally ENDED (item 17).",
                "Pt6Line18_State": "State or province where it ended (item 17); the audit asks for it when the country "
                "is the United States.",
                "Pt6Line18_Country": "Country where it ended (item 17).",
                "Pt6Line16_DateofBirth[1]": f"DATE the prior marriage legally ended (item 17). {DATE}",
                "Pt6Line19_MaritalStatus": "How the prior marriage ended (item 18).",
                "Pt6Line19_HowMarriageEndedOther": "With Other only: explain.",
            },
            choices={
                "Pt6Line19_MaritalStatus": {"Annulled": "1", "Divorced": "2", "Spouse deceased": "3", "Other": "4"}
            },
        ),
        "children": children(),
        "biographic_info": q(
            "Part 8 items 1-6: ethnicity, race, height, weight, eye color, hair color",
            (
                ["Pt7Line1_Ethnicity"]
                + [field for field, _, _ in RACES]
                + ["Pt7Line3_HeightFeet", "Pt7Line3_HeightInches", "Pt7Line4_Weight1", "Pt7Line4_Weight2",
                   "Pt7Line4_Weight3", "Pt7Line5_Eyecolor", "Pt7Line6_Haircolor"]
            ),
            ["Pt7Line1_Ethnicity", "Pt7Line3_HeightFeet", "Pt7Line3_HeightInches", "Pt7Line4_Weight2",
             "Pt7Line4_Weight3", "Pt7Line5_Eyecolor", "Pt7Line6_Haircolor"],
            notes={
                **{field: f"Race box '{label}'. Separate box, not a group: map each race that applies by its [n]." for field, label, _ in RACES},
                "Pt7Line1_Ethnicity": "Part 8 item 1 (Part 8 boxes are named Pt7).",
                "Pt7Line3_HeightFeet": "Drop-down, '2' to '8'.",
                "Pt7Line3_HeightInches": "Drop-down, '0' to '11'.",
                "Pt7Line4_Weight1": "Hundreds digit of the weight in pounds; leave blank under 100.",
                "Pt7Line4_Weight2": "Tens digit.",
                "Pt7Line4_Weight3": "Units digit.",
                "Pt7Line5_Eyecolor": "Eye 'BN' is Brown and 'BL' is Black.",
                "Pt7Line6_Haircolor": "Hair 'BN' is BLOND; Brown is 'BR'. 'NH' is bald.",
            },
            choices={
                **{field: {label: state} for field, label, state in RACES},
                "Pt7Line1_Ethnicity": {"Hispanic or Latino": "H", "Not Hispanic or Latino": "N"},
                "Pt7Line5_Eyecolor": {
                    "Black": "BL",
                    "Blue": "BU",
                    "Brown": "BN",
                    "Gray": "GR",
                    "Green": "GN",
                    "Hazel": "HA",
                    "Maroon": "MA",
                    "Pink": "PN",
                    "Unknown/Other": "UN",
                },
                "Pt7Line6_Haircolor": {
                    "Bald (no hair)": "NH",
                    "Black": "BL",
                    "Blond": "BN",
                    "Brown": "BR",
                    "Gray": "GR",
                    "Red": "RD",
                    "Sandy": "SA",
                    "White": "WH",
                    "Unknown/Other": "OT",
                },
            },
        ),
        "organization_history": organization_history(),
        "part9_prior_denials_and_proceedings": yes_no_group(
            "Part 9 items 10-11 and 14-18: denied admission or a visa; removal proceedings, final orders, "
            "reinstatement, voluntary departure, applications for relief",
            [
                ("10 (ever denied admission)", "Pt9Line10_YesNo", None),
                ("11 (ever denied a visa)", "Pt9Line11_YesNo", None),
                ("14 (ever in removal, exclusion, rescission or deportation proceedings)", "Pt8Line18_YesNo", None),
                ("15 (ever issued a final order of removal)", "Pt8Line19_YesNo", None),
                ("16 (prior final order reinstated)", "Pt8Line20_YesNo", None),
                ("17 (granted voluntary departure but failed to depart)", "Pt8Line17_YesNo", None),
                ("18 (ever applied for relief or protection from removal)", "Pt8Line23_YesNo", None),
            ],
        ),
        "part9_status_violations": yes_no_group(
            "Part 9 items 12-13: worked without authorization; violated nonimmigrant status",
            [
                ("12 (ever worked in the U.S. without authorization)", "Pt9Line12_YesNo", None),
                ("13 (ever violated the terms or conditions of nonimmigrant status)", "Pt8Line13_YesNo", None),
            ],
        ),
        "part9_j_exchange_visitor": yes_no_group(
            "Part 9 items 19-21: J exchange visitor subject to the two-year foreign residence requirement; "
            "complied; waiver",
            [
                ("19 (ever a J-1/J-2 subject to the two-year requirement)", "Pt8Line24a_YesNo", None),
                ("20 (complied with the requirement)", "Pt8Line24b_YesNo", "item 19 is Yes"),
                ("21 (waiver granted or favorable DOS "
                "recommendation)", "Pt8Line24c_YesNo", "item 19 is Yes and item "
                "20 is No"),
            ],
        ),
        "part9_arrests_and_convictions": yes_no_group(
            "Part 9 items 22-25: arrests, citations, charges, detention; crimes committed; pleas and "
            "convictions; sentences and restraints (explain each Yes in Part 14)",
            [
                ("22 (ever arrested, cited, charged, detained, or in a diversion program; "
                "traffic tickets count)", "Pt8Line22_YesNo", None),
                ("23 (ever committed a crime, even if never arrested)", "Pt9Line23_YesNo", None),
                ("24 (ever pled guilty to or been convicted of a crime or offense)", "Pt9Line24_YesNo", None),
                ("25 (ever ordered punished or had liberty restrained: jail, probation, "
                "classes, community service)", "Pt8Line25_YesNo", None),
            ],
        ),
        "part9_other_criminal_grounds": yes_no_group(
            "Part 9 items 26-41: controlled substances, prostitution and vice, immunity, religious-freedom "
            "violations, human trafficking, money laundering",
            [
                ("26 (violated a controlled substance law)", "Pt8Line26_YesNo", None),
                ("27 (trafficked or aided trafficking in controlled substances)", "Pt8Line27_YesNo", None),
                ("28 (spouse, son or daughter of a drug trafficker and benefited in the "
                "last 5 years)", "Pt8Line28_YesNo", None),
                ("29 (knew or should have known the benefit came from "
                "trafficking)", "Pt8Line29_YesNo", "item 28 is Yes"),
                ("30 (engaged in prostitution)", "Pt8Line30_YesNo", None),
                ("31 (procured or imported prostitutes)", "Pt8Line31_YesNo", None),
                ("32 (received proceeds from prostitution)", "Pt8Line32_YesNo", None),
                ("33 (intend illegal gambling or commercialized vice)", "Pt8Line33_YesNo", None),
                ("34 (exercised immunity to avoid prosecution)", "Pt8Line34_YesNo", None),
                ("35.a (ever served as a foreign government official)", "Pt8Line35a_YesNo", None),
                ("35.b (responsible for violations of religious freedom)", "Pt8Line35b_YesNo", "item 35.a is Yes"),
                ("36 (sex trafficking)", "Pt8Line36_YesNo", None),
                ("37 (trafficked a person into involuntary servitude)", "Pt8Line37_YesNo", None),
                ("38 (aided or colluded in trafficking in persons)", "Pt8Line38_YesNo", None),
                ("39 (spouse, son or daughter of a trafficker and benefited in the last 5 "
                "years)", "Pt9Line39_YesNo", None),
                ("40 (knew or should have known the benefit came from "
                "trafficking)", "Pt8Line40_YesNo", "item 39 is Yes"),
                ("41 (money laundering)", "Pt8Line41_YesNo", None),
            ],
        ),
        "part9_security_grounds": yes_no_group(
            "Part 9 items 42.a-42.d, 43.b-43.i, 44-47 and 52-55: espionage, export violations, overthrow, "
            "terrorist activity and support, weapons, totalitarian party, torture, genocide, killing, "
            "child soldiers",
            [
                ("42.a (intend espionage or sabotage)", "Pt8Line42.a_YesNo", None),
                ("42.b (intend export-control violations)", "Pt8Line42.b_YesNo", None),
                ("42.c (intend to oppose or overthrow the U.S. Government by force)", "Pt8Line42c_YesNo", None),
                ("42.d (intend any other unlawful activity)", "Pt8Line42d_YesNo", None),
                ("43.b (kidnapping, assassination, hijacking or sabotage)", "Pt8Line43b_YesNo", None),
                ("43.c (used a weapon or explosive to endanger people or property)", "Pt8Line43c_YesNo", None),
                ("43.d (threatened or planned 43.b-43.c)", "Pt8Line43d_YesNo", None),
                ("43.e (incited 43.b-43.c)", "Pt8Line43e_YesNo", None),
                ("43.f (member of a group that did 43.b-43.e)", "Pt8Line43fYesNo", None),
                ("43.g (recruited for or solicited for such a group)", "Pt8Line43g_YesNo", None),
                ("43.h (supported 43.b-43.e activities)", "Pt8Line43h_YesNo", None),
                ("43.i (supported a person or group that did 43.b-43.e)", "Pt8Line43i_YesNo", None),
                ("44 (intend 43.b-43.e activities)", "Pt8Line44_YesNo", None),
                ("45 (intend activity endangering U.S. security)", "Pt8Line45_YesNo", None),
                ("46 (spouse or child of someone who did 43.b-43.i)", "Pt8Line46_YesNo", None),
                ("47 (sold or transported weapons to be used against people)", "Pt8Line47_YesNo", None),
                ("52 (member of or affiliated with the Communist or another totalitarian "
                "party)", "Pt8Line52_YesNo", None),
                ("53.a (torture)", "Pt8Line53a_YesNo", None),
                ("53.b (genocide)", "Pt8Line53b_YesNo", None),
                ("53.c (killing or trying to kill any person)", "Pt8Line53c_YesNo", None),
                ("53.d (severely injuring or trying to injure any person)", "Pt8Line53d_YesNo", None),
                ("54 (recruited or used anyone under 15 in an armed force or group)", "Pt8Line54_YesNo", None),
                ("55 (used anyone under 15 in hostilities)", "Pt8Line55_YesNo", None),
            ],
            extra_notes={
                "Pt8Line42.a_YesNo": "Item 42.a. The field name contains a literal dot; map it exactly as written.",
                "Pt8Line42.b_YesNo": "Item 42.b. The field name contains a literal dot; map it exactly as written.",
                "Pt8Line43fYesNo": "Item 43.f. No underscore before YesNo.",
                "Pt8Line52_YesNo": (
                    "Item 52. Often Yes for nationals of current or former one-party states (compulsory party or "
                    "youth-league membership); ask rather than default."
                ),
            },
        ),
        "part9_military_and_armed_groups": yes_no_group(
            "Part 9 items 43.a and 48-51: weapons or military-type training; detention facilities; groups "
            "using weapons; military or police service; armed groups (explain each Yes in Part 14)",
            [
                ("43.a (ever received weapons, paramilitary or military-type training)", "Pt8Line43a_YesNo", None),
                ("48 (worked or served in a prison, jail, detention or labor camp, or "
                "detained people)", "Pt8Line48_YesNo", None),
                ("49 (member of a group or unit in which weapons were used or threatened)", "Pt8Line49_YesNo", None),
                ("50 (ever served in or helped any military or police unit)", "Pt8Line50_YesNo", None),
                ("51 (ever served in or helped any armed group: paramilitary, self-defense, "
                "rebel, guerrilla)", "Pt8Line51_YesNo", None),
            ],
            extra_notes={
                "Pt8Line50_YesNo": (
                    "Item 50. Compulsory military service, military registration with training, and police "
                    "service all count; ask the client rather than default. A Yes needs country, unit, rank and "
                    "dates in Part 14."
                ),
            },
        ),
        "public_charge": public_charge(public_charge_note),
        "public_charge_factors": public_charge_factors(public_charge_details),
        "public_benefits": public_benefits(public_charge_details),
        "part9_fraud_and_misrepresentation": yes_no_group(
            "Part 9 items 65-71: missed removal proceedings, fraudulent documents, misrepresentation, false "
            "claim to U.S. citizenship, stowaway, alien smuggling, INA 274C penalty",
            [
                ("65 (failed to attend a removal proceeding on or after 4/1/1997; attach a "
                "statement if Yes)", "Pt9Line67_YesNo", None),
                ("66 (ever submitted altered, fraudulent or counterfeit documents to the "
                "U.S. Government)", "Pt9Line68_YesNo", None),
                ("67 (ever lied or misrepresented to obtain a visa, entry or immigration "
                "benefit)", "Pt9Line69_YesNo", None),
                ("68 (ever falsely claimed U.S. citizenship)", "Pt9Line70_YesNo", None),
                ("69 (ever a stowaway)", "Pt9Line71_YesNo", None),
                ("70 (ever helped anyone enter illegally)", "Pt9Line72_YesNo", None),
                ("71 (under a final INA 274C civil penalty order)", "Pt9Line73_YesNo", None),
            ],
            extra_notes={
                "Pt9Line67_YesNo": (
                    "Item 65. From here to item 84 every field number is 2 higher than its item number."
                ),
            },
        ),
        "part9_removal_and_unlawful_presence": yes_no_group(
            "Part 9 items 72-76.b: removed or departed under an order; entry without inspection; unlawful "
            "presence; trafficking as its cause; illegal reentry",
            [
                ("72 (ever excluded, deported or removed, or departed under such an order)", "Pt9Line74_YesNo", None),
                ("73 (ever entered without inspection and admission or parole)", "Pt9Line75_YesNo", None),
                ("74 (unlawfully present since 4/1/1997; give the dates in Part 14)", "Pt9Line76_YesNo", None),
                ("75 (severe trafficking was a central reason for the unlawful "
                "presence)", "Pt9Line77_YesNo", "item 74 "
                "is Yes"),
                ("76.a (reentered or tried to reenter without inspection after over 1 year "
                "unlawful presence)", "Pt9Line78a_YesNo", None),
                ("76.b (reentered or tried to reenter without inspection after removal)", "Pt9Line78b_YesNo", None),
            ],
            extra_notes={
                "Pt9Line76_YesNo": (
                    "Item 74 (the name says 76). Any overstay or entry without inspection since 4/1/1997 makes "
                    "this Yes; work it out from the I-94 and status records, not by default."
                ),
            },
        ),
        "part9_miscellaneous_conduct": yes_no_group(
            "Part 9 items 77-84: polygamy, accompanying a helpless inadmissible alien, child custody, unlawful "
            "voting, renouncing citizenship for taxes, armed-forces exemption or desertion, draft evasion",
            [
                ("77 (plan to practice polygamy)", "Pt9Line79_YesNo", None),
                ("78 (accompanying a helpless inadmissible alien under INA 232(c))", "Pt9Line80_YesNo", None),
                ("79 (withheld custody of a U.S. citizen child abroad)", "Pt9Line81_YesNo", None),
                ("80 (ever voted unlawfully)", "Pt9Line82_YesNo", None),
                ("81 (renounced U.S. citizenship to avoid taxes)", "Pt9Line83_YesNo", None),
                ("82.a (applied for exemption from U.S. armed forces or NSTC service as an "
                "alien)", "Pt9Line84a_YesNo", None),
                ("82.b (relieved or discharged from that service as an alien)", "Pt9Line84b_YesNo", None),
                ("82.c (convicted of desertion from the U.S. armed forces)", "Pt9Line84c_YesNo", None),
                ("83 (left or stayed outside the U.S. to evade service in wartime or "
                "emergency)", "Pt9Line85_YesNo", None),
            ],
            extra_fields=["Pt9Line86_Nationality"],
            extra_notes={
                "Pt9Line86_Nationality": (
                    "Item 84 (text): only if item 83 is Yes, the nationality or immigration status immediately "
                    "before leaving."
                ),
            },
        ),
        "applicant_contact": q(
            "Part 10 items 1-3: applicant's daytime phone, mobile phone, email",
            ["Pt3Line3_DaytimePhoneNumber1", "Pt3Line4_MobileNumber1", "Pt3Line5_Email"],
            ["Pt3Line3_DaytimePhoneNumber1"],
            notes={
                "Pt3Line3_DaytimePhoneNumber1": "Part 10 item 1 (Part 10 boxes are named Pt3). 10 digits, no "
                "punctuation.",
                "Pt3Line4_MobileNumber1": "Item 2, if any. 10 digits. Leave blank if none.",
                "Pt3Line5_Email": "Item 3, if any. 38 characters at most. Leave blank if none.",
            },
        ),
        "applicant_signature": q(
            "Part 10 item 4: applicant's signature and date",
            ["Pt3Line7a_Signature", "Pt3Line7b_DateofSignature"],
            allowed=SIGNATURE_STATUSES,
            notes={
                "Pt3Line7a_Signature": "Signed in ink by the applicant (or parent or guardian); never typed.",
                "Pt3Line7b_DateofSignature": f"Dated by the signer. {DATE}",
            },
        ),
        "interpreter": q(
            "Part 11 items 1-5 and certification language: interpreter's name, organization, contact details, language",
            ["Pt11Line1a_FamilyName", "Pt11Line1b_GivenName", "Pt11Line2_OrgName", "P3_Line4_DaytimeTelePhoneNumber",
             "P3_Line5_MobileTelePhoneNumber", "P3_Line6_Email", "Part11_NameofLanguage"],
            ["Pt11Line1a_FamilyName", "Pt11Line1b_GivenName", "P3_Line4_DaytimeTelePhoneNumber", "Part11_NameofLanguage"],
            allowed=[NOT_APPLICABLE, FILLED],
            notes={
                "Pt11Line2_OrgName": "34 characters at most.",
                "P3_Line4_DaytimeTelePhoneNumber": "Interpreter's daytime phone (Part 11 item 3; the name says P3).",
                "P3_Line5_MobileTelePhoneNumber": "Interpreter's mobile phone (item 4).",
                "P3_Line6_Email": "Interpreter's email (item 5).",
                "Part11_NameofLanguage": "Language in the certification ('fluent in English and ...'). 18 characters "
                "at most.",
            },
        ),
        "interpreter_signature": q(
            "Part 11 item 6: interpreter's signature and date",
            ["P12_SignatureApplicant", "P13_DateofSignature"],
            allowed=[NOT_APPLICABLE, PENDING_SIGNATURE, FILLED],
            notes={
                "P12_SignatureApplicant": "The INTERPRETER's signature (Part 11 item 6), despite the name. Signed in "
                "ink.",
                "P13_DateofSignature": f"The interpreter's signature date, not Part 13. {DATE}",
            },
        ),
        "preparer_block": q(
            "Part 12 items 1-5: preparer's name, business, phones, email (from the attorney profile)",
            ["Pt12Line1_PreparerFamilyName", "Pt12Line1a_PreparerGivenName", "Pt12Line2_BusinessName",
             "Pt12Line3_PreparerDaytimePhoneNumber1", "Pt12Line4_PreparerMobileNumber", "Pt12Line5_PreparerEmail"],
            ["Pt12Line1_PreparerFamilyName", "Pt12Line1a_PreparerGivenName", "Pt12Line2_BusinessName",
             "Pt12Line3_PreparerDaytimePhoneNumber1", "Pt12Line5_PreparerEmail"],
            notes={
                "Pt12Line2_BusinessName": "Firm name; 34 characters at most. This edition has no preparer address or "
                "statement boxes.",
                "Pt12Line3_PreparerDaytimePhoneNumber1": "10 digits, no punctuation.",
                "Pt12Line4_PreparerMobileNumber": "If any. 10 digits.",
                "Pt12Line5_PreparerEmail": "38 characters at most.",
            },
        ),
        "preparer_signature": q(
            "Part 12 item 6: preparer's signature and date",
            ["P12Line6_SignaturePreparer", "P12Line6a_DateofSignature"],
            allowed=SIGNATURE_STATUSES,
            notes={"P12Line6a_DateofSignature": DATE},
        ),
        "additional_information": additional_information(),
    }


def part1() -> dict[str, dict[str, Any]]:
    return {
        "attorney_box": q(
            "Page 1 attorney box: Form G-28 attached, Volag number, attorney State Bar number, "
            "attorney USCIS online account number",
            ["CheckBox1", "AttorneyStateBarNumber", "VolagNumber", "USCISOnlineAcctNumber"],
            ["CheckBox1", "AttorneyStateBarNumber"],
            notes={
                "CheckBox1": "Form G-28 is attached.",
                "AttorneyStateBarNumber": "Attorney's bar number from the attorney profile; 9 characters at most.",
                "VolagNumber": "Accredited representatives only; leave blank for an attorney.",
                "USCISOnlineAcctNumber": (
                    "The attorney's USCIS online account number (12 characters), if the profile has one. The "
                    "applicant's own number is Part 1 item 9. Blank when the profile says has_uscis_online_account "
                    "\"no\"."
                ),
            },
            choices={"CheckBox1": {"G-28 attached": "1"}},
        ),
        "applicant_identity": q(
            "Part 1 items 1, 3, 6-8: legal name, date of birth, sex, place of birth, country of "
            "citizenship or nationality",
            ["Pt1Line1_FamilyName", "Pt1Line1_GivenName", "Pt1Line1_MiddleName", "Pt1Line3_DOB", "Pt1Line6_CB_Sex",
             "Pt1Line7_CityTownOfBirth", "Pt1Line7_CountryOfBirth", "Pt1Line8_CountryofCitizenshipNationality"],
            ["Pt1Line1_FamilyName", "Pt1Line1_GivenName", "Pt1Line3_DOB", "Pt1Line6_CB_Sex", "Pt1Line7_CityTownOfBirth",
             "Pt1Line7_CountryOfBirth", "Pt1Line8_CountryofCitizenshipNationality"],
            notes={
                "Pt1Line1_FamilyName": (
                    "Global field: the same value prints in Part 14 item 1. Set the base name once; "
                    "do not also map Pt1Line1_FamilyName[1]."
                ),
                "Pt1Line1_GivenName": "Global field; also prints in Part 14 item 1.",
                "Pt1Line1_MiddleName": "Global field; also prints in Part 14 item 1. Leave blank if none.",
                "Pt1Line3_DOB": DATE,
            },
            choices={"Pt1Line6_CB_Sex": {"Male": "M", "Female": "F"}},
        ),
        "other_names_used": q(
            "Part 1 item 2: other names used since birth (two rows)",
            ["Pt1Line2_FamilyName", "Pt1Line2_GivenName", "Pt1Line2_MiddleName", "Pt1Line2a_FamilyName",
             "Pt1Line2a_GivenName", "Pt1Line2a_MiddleName"],
            ["Pt1Line2_FamilyName"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt1Line2_FamilyName": (
                    "Row 1. If the applicant has used no other name, the instructions (How To Complete, "
                    "item 3) say to type N/A: mark the question filled with N/A here."
                ),
                "Pt1Line2a_FamilyName": "Row 2. More names go in Part 14 (question additional_information).",
            },
        ),
        "other_birth_dates": q(
            "Part 1 item 3: ever used another date of birth, and which",
            ["Pt1Line3_YN", "Pt1Line3A_OtherDOB", "Pt1Line3B_OtherDOB"],
            ["Pt1Line3_YN"],
            notes={
                "Pt1Line3A_OtherDOB": f"Only if Yes. {DATE}",
                "Pt1Line3B_OtherDOB": f"Only if Yes. {DATE}",
            },
            choices={"Pt1Line3_YN": YES_NO},
        ),
        "identity_numbers": q(
            "Part 1 items 4-5: A-Number, and any other A-Numbers used or assigned",
            ["Pt1Line4_YN", "Pt1Line4_AlienNumber", "Pt1Line5_YN", "Pt1Line5A_ANumber", "Pt1Line5B_ANumber"],
            ["Pt1Line4_YN", "Pt1Line5_YN"],
            notes={
                "Pt1Line4_AlienNumber": (
                    "Only if item 4 is Yes. 9 digits, no 'A' or dashes. Global field: it fills the A-Number "
                    "box at the top of every page. Leave blank if none."
                ),
                "Pt1Line5A_ANumber": "Only if item 5 is Yes. 9 digits.",
                "Pt1Line5B_ANumber": "Only if item 5 is Yes. 9 digits.",
            },
            choices={"Pt1Line4_YN": YES_NO, "Pt1Line5_YN": YES_NO},
        ),
        "uscis_online_account": q(
            "Part 1 item 9: applicant's USCIS online account number, if any",
            ["Pt1Line9_USCISAccountNumber"],
            ["Pt1Line9_USCISAccountNumber"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt1Line9_USCISAccountNumber": (
                    "12 characters, from a USCIS notice for a form filed online (receipt numbers starting IOE)."
                )
            },
        ),
        "last_arrival_travel_document": q(
            "Part 1 item 10: passport or travel document used at last arrival, and nonimmigrant visa",
            ["Pt1Line10_PassportNum", "Pt1Line10_ExpDate", "Pt1Line10_Passport", "Pt1Line10_VisaNum",
             "Pt1Line10_NonImmDate"],
            ["Pt1Line10_PassportNum", "Pt1Line10_ExpDate", "Pt1Line10_Passport"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt1Line10_PassportNum": (
                    "Passport or travel document number used at the last arrival. Item 10 asks for it only if "
                    "the applicant last entered using a passport or travel document: after an entry without "
                    "inspection (item 11 is 11C), mark the question not_applicable and leave these boxes blank. "
                    "The audit requires them after an admission or parole (11A or 11B)."
                ),
                "Pt1Line10_ExpDate": f"Expiration date of that document. {DATE}",
                "Pt1Line10_Passport": "Country that issued the document (the name says Passport).",
                "Pt1Line10_VisaNum": "Nonimmigrant visa foil number used at that arrival, if any.",
                "Pt1Line10_NonImmDate": f"Date that visa was issued. {DATE}",
            },
        ),
        "last_arrival_place_and_date": q(
            "Part 1 item 10: place and date of last arrival in the United States",
            ["Pt1Line10_CityTown", "Pt1Line10_State", "Pt1Line10_DateofArrival"],
            ["Pt1Line10_CityTown", "Pt1Line10_State", "Pt1Line10_DateofArrival"],
            notes={
                "Pt1Line10_State": STATE,
                "Pt1Line10_DateofArrival": DATE,
            },
        ),
        "last_arrival_manner": q(
            "Part 1 item 11: when I last arrived (admitted as, paroled as, without admission or parole, other)",
            ["Pt2Line11_CB", "Pt1Line11_Admitted", "Pt1Line11_Paroled", "Pt1Line11_Other"],
            ["Pt2Line11_CB"],
            notes={
                "Pt2Line11_CB": "Part 1 item 11, despite the Pt2 prefix.",
                "Pt1Line11_Admitted": "With 11A only: the admission class (for example, B-2 visitor).",
                "Pt1Line11_Paroled": "With 11B only: the parole type (for example, humanitarian parole).",
                "Pt1Line11_Other": "With 11D only: explain.",
            },
            choices={
                "Pt2Line11_CB": {
                    "Inspected and admitted as": "11A",
                    "Inspected and paroled as": "11B",
                    "Came in without admission or parole": "11C",
                    "Other": "11D",
                }
            },
        ),
        "i94_record": q(
            "Part 1 item 12: most recent Form I-94 (name, number, authorized stay, status)",
            ["P1Line12_FamilyName", "P1Line13_GivenName", "P1Line12_I94", "Pt1Line12_Date", "Pt1Line12_Status"],
            ["P1Line12_FamilyName", "P1Line13_GivenName", "P1Line12_I94", "Pt1Line12_Date", "Pt1Line12_Status"],
            allowed=FILLED_OR_NA,
            notes={
                "P1Line12_FamilyName": (
                    "Family name exactly as printed on the I-94. Item 12 applies only if an I-94 was issued: "
                    "with none (an entry without inspection and no later I-94), mark the question "
                    "not_applicable and leave the boxes blank."
                ),
                "P1Line13_GivenName": "Item 12 given name on the I-94 (the name says Line13).",
                "P1Line12_I94": "I-94 number, 11 characters.",
                "Pt1Line12_Date": f"Authorized stay expiration on the I-94, {DATE[:-1]}, or D/S.",
                "Pt1Line12_Status": "Class of admission or parole on the I-94 (for example, B-2); 20 characters at "
                "most.",
            },
        ),
        "first_presence_and_current_status": q(
            "Part 1 items 13-15: first physical presence at last arrival; current status if changed; "
            "status expiration",
            ["Pt1Line13_YN", "Pt1Line14_Status", "Pt1Line15_Date"],
            ["Pt1Line13_YN", "Pt1Line15_Date"],
            notes={
                "Pt1Line14_Status": (
                    "Current immigration status only if it changed since the last arrival; 20 characters at "
                    "most. Otherwise N/A."
                ),
                "Pt1Line15_Date": f"Expiration of the current status, {DATE[:-1]}, or D/S.",
            },
            choices={"Pt1Line13_YN": YES_NO},
        ),
        "crewman": q(
            "Part 1 items 16-17: ever issued an alien crewman visa; last arrived to join a vessel or as crew",
            ["Pt1Line16_YN", "Pt1Line17_YN"],
            ["Pt1Line16_YN", "Pt1Line17_YN"],
            notes={"Pt1Line16_YN": "Item 16 (see the instructions' alien crewman definition).", "Pt1Line17_YN": "Item "
            "17."},
            choices={"Pt1Line16_YN": YES_NO, "Pt1Line17_YN": YES_NO},
        ),
        "current_address": q(
            "Part 1 item 18: current U.S. physical address, date first resided there, and whether it is "
            "the mailing address",
            ["Part1_Item18_InCareOfName", "Pt1Line18_StreetNumberName", "Pt1Line18US_Unit",
             "Pt1Line18US_AptSteFlrNumber", "Pt1Line18_CityOrTown", "Pt1Line18_State", "Pt1Line18_ZipCode",
             "Pt1Line18_Date", "Pt1Line18_YN"],
            ["Pt1Line18_StreetNumberName", "Pt1Line18_CityOrTown", "Pt1Line18_State", "Pt1Line18_ZipCode",
             "Pt1Line18_Date", "Pt1Line18_YN"],
            notes={
                "Pt1Line18_StreetNumberName": "34 characters at most.",
                "Pt1Line18US_Unit": "The on-states are padded with spaces (' APT ').",
                "Pt1Line18US_AptSteFlrNumber": "Only with a unit type; 6 characters at most.",
                "Pt1Line18_CityOrTown": "20 characters at most.",
                "Pt1Line18_State": STATE,
                "Pt1Line18_ZipCode": "5 digits.",
                "Pt1Line18_Date": f"Date first resided at this address. {DATE}",
                "Pt1Line18_YN": "Is this also the current mailing address?",
            },
            choices={"Pt1Line18US_Unit": UNIT, "Pt1Line18_YN": YES_NO},
        ),
        "mailing_address": q(
            "Part 1 item 18: current mailing address, if different from the physical address",
            ["Pt1Line18_CurrentInCareOfName", "Pt1Line18_CurrentStreetNumberName", "Pt1Line18_CurrentUnit",
             "Pt1Line18_CurrentAptSteFlrNumber", "Pt1Line18_CurrentCityOrTown", "Pt1Line18_CurrentState",
             "Pt1Line18_CurrentZipCode"],
            ["Pt1Line18_CurrentStreetNumberName", "Pt1Line18_CurrentCityOrTown", "Pt1Line18_CurrentState",
             "Pt1Line18_CurrentZipCode"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt1Line18_CurrentStreetNumberName": (
                    "The 'Current' boxes are the MAILING address; the physical address is Pt1Line18_*. "
                    "Only if Pt1Line18_YN is No. 34 characters at most. In a VAWA matter, use the safe mailing "
                    "address the matter contract sets (the attorney's office unless the attorney gives another), "
                    "with Pt1Line18_YN No and the physical address still from the record (Instructions, item 7)."
                ),
                "Pt1Line18_CurrentInCareOfName": "In a VAWA matter, the firm or attorney the safe mailing address is "
                "in care of.",
                "Pt1Line18_CurrentUnit": "The on-states are padded with spaces (' APT ').",
                "Pt1Line18_CurrentCityOrTown": "20 characters at most.",
                "Pt1Line18_CurrentState": STATE,
            },
            choices={"Pt1Line18_CurrentUnit": UNIT},
        ),
        "address_history_last_five_years": q(
            "Part 1 item 18: resided at current address for 5 years; if not, prior address (one row; more "
            "in Part 14)",
            ["Pt1Line18_last5yrs_YN", "Pt1Line18_PriorInCareOfName", "Pt1Line18_PriorStreetName",
             "Pt1Line18_PriorAddress_Unit", "Pt1Line18_PriorAddress_Number", "Pt1Line18_PriorCity",
             "Pt1Line18_PriorState", "Pt1Line18_PriorZipCode", "Pt1Line18_PriorProvince", "Pt1Line18_PriorPostalCode",
             "Pt1Line18_PriorCountry", "Pt1Line18_PriorDateFrom", "Pt1Line18PriorDateTo"],
            ["Pt1Line18_last5yrs_YN"],
            notes={
                "Pt1Line18_last5yrs_YN": (
                    "If No, fill the prior-address row with the address before the current one, and put any "
                    "older addresses in the last 5 years in Part 14."
                ),
                "Pt1Line18_PriorStreetName": "34 characters at most.",
                "Pt1Line18_PriorState": f"{US_ONLY} {STATE}",
                "Pt1Line18_PriorZipCode": US_ONLY,
                "Pt1Line18_PriorProvince": FOREIGN_ONLY,
                "Pt1Line18_PriorPostalCode": FOREIGN_ONLY,
                "Pt1Line18_PriorDateFrom": DATE,
                "Pt1Line18PriorDateTo": f"No underscore after Line18. {DATE}",
            },
            choices={"Pt1Line18_last5yrs_YN": YES_NO, "Pt1Line18_PriorAddress_Unit": UNIT_PLAIN},
        ),
        "last_address_outside_us": q(
            "Part 1 item 18: most recent address outside the United States where you lived more than one "
            "year (if not already listed)",
            ["Pt1Line18_RecentStreetName", "Pt1Line18_RecentUnit", "Pt1Line18_RecentNumber", "Pt1Line18_RecentCity",
             "Pt1Line18_RecentState", "Pt1Line18_RecentZipCode", "Pt1Line18_RecentProvince",
             "Pt1Line18_RecentPostalCode", "Pt1Line18_RecentCountry", "Pt1Line18_RecentDateFrom",
             "Pt1Line18_RecentDateTo"],
            ["Pt1Line18_RecentStreetName", "Pt1Line18_RecentCity", "Pt1Line18_RecentCountry",
             "Pt1Line18_RecentDateFrom", "Pt1Line18_RecentDateTo"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt1Line18_RecentStreetName": "The 'Recent' boxes are this outside-U.S. row. 34 characters at most.",
                "Pt1Line18_RecentState": f"Leave blank for a foreign address. {STATE}",
                "Pt1Line18_RecentZipCode": "Leave blank for a foreign address.",
                "Pt1Line18_RecentProvince": "Belongs to this row, though its tooltip says Prior Address.",
                "Pt1Line18_RecentPostalCode": "Belongs to this row, though its tooltip says Prior Address.",
                "Pt1Line18_RecentDateFrom": DATE,
                "Pt1Line18_RecentDateTo": DATE,
            },
            choices={"Pt1Line18_RecentUnit": UNIT_PLAIN},
        ),
        "social_security_card": q(
            "Part 1 item 19: SSA ever issued a card (and SSN); want SSA to issue a card; consent to disclosure",
            ["Pt1Line19_YN", "Pt1Line19_SSN", "Pt1Line19_SSA_YN", "Pt1Line19_Consent_YN"],
            ["Pt1Line19_YN", "Pt1Line19_SSA_YN", "Pt1Line19_Consent_YN"],
            notes={
                "Pt1Line19_SSN": "Only if Pt1Line19_YN is Yes. 9 digits, no dashes.",
                "Pt1Line19_SSA_YN": "If Yes, the consent answer must also be Yes.",
            },
            choices={"Pt1Line19_YN": YES_NO, "Pt1Line19_SSA_YN": YES_NO, "Pt1Line19_Consent_YN": YES_NO},
        ),
    }


def schema(description: str, notes: list[str], questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "kind": "i-485",
        "edition": EDITION,
        "field_list": FIELD_LIST,
        "description": description,
        "notes": COMMON_NOTES + notes,
        "required_questions": questions,
    }


def employment(*, derivative: bool) -> dict[str, Any]:
    questions = part1()
    questions.update(
        {
            "filing_category": employment_filing_category(derivative=derivative),
            "underlying_petition": underlying_petition("employment"),
            "principal_applicant": principal_applicant([FILLED] if derivative else NA_ONLY),
            "i140_relative_interest": q(
                "Part 2 item 3.b: did a relative file the I-140 or own 5% or more of the petitioning business; "
                "if so, the relationship and the relative's status",
                ["Pt2Line3b_CB140Assoc", "Pt2Relative_CB", "Pt2RelativeType_CB"],
                ["Pt2Line3b_CB140Assoc"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt2Line3b_CB140Assoc": (
                        "I-140 filings only (not_applicable for I-526). For a derivative, answer about the principal. "
                        "A Yes means an I-864 is required (Part 3 item 1.f)."
                    ),
                    "Pt2Relative_CB": "Only if Yes.",
                    "Pt2RelativeType_CB": "Only if Yes.",
                },
                choices={
                    "Pt2Line3b_CB140Assoc": {"N/A (I-140 self-petition)": "NA", "No": "N", "Yes": "Y"},
                    "Pt2Relative_CB": {
                        "Father": "1",
                        "Mother": "2",
                        "Child": "3",
                        "Adult son": "4",
                        "Adult daughter": "5",
                        "Brother": "6",
                        "Sister": "7",
                        "None of these": "8",
                    },
                    "Pt2RelativeType_CB": {
                        "U.S. citizen": "1",
                        "U.S. national": "2",
                        "Lawful permanent resident": "3",
                        "None of these": "4",
                    },
                },
            ),
        }
    )
    questions.update(
        shared_tail(
            aos_note=(
                "1.f only when a relative filed the I-140 or owns 5% or more of the petitioning business "
                "(Part 2 relative question Yes); otherwise 1.e."
            ),
            public_charge_note="Not exempt (23) for employment-based applicants; answer items 57-64.",
            public_charge_details=FILLED_OR_NA,
            school=derivative,
        )
    )
    if derivative:
        return schema(
            "Employment-based adjustment of a derivative child of an I-140 or I-526 principal (Part 2 item 3.b, "
            "Derivative Applicant).",
            [
                "Part 2: Derivative Applicant (1fB), the principal's 3.b category, and the principal's name, "
                "A-Number and date of birth. Item 5 (CSPA) matters for children near 21.",
                "Part 4 item 7 is usually the school attended; a minor may have no item 8 entry.",
                "Part 6: an unmarried child marks Single (1), spouse N/A, times married None; Part 7 total None.",
            ],
            questions,
        )
    return schema(
        "Employment-based adjustment of the principal beneficiary of an I-140 or I-526/I-526E (Part 2 item 3.b, "
        "Principal Applicant).",
        [
            "Part 2: Principal Applicant (1fA), one 3.b box, the I-140 relative question, and the I-140 or "
            "I-526 receipt number and priority date.",
        ],
        questions,
    )


SCHEMAS = {
    "i485_family_based": schema(
        "Family-based adjustment: immediate relative, fiance(e), widow(er), family-preference or VAWA "
        "beneficiary (Part 2 item 3.a), principal or preference derivative.",
        [
            "Part 2: select one 3.a box, answer item 4 (245(i)) and item 5 (CSPA); leave 3.b-3.g blank.",
            "Part 2 item 2: the I-130 (or I-360/I-129F) receipt number and priority date when one exists; "
            "a concurrent I-130/I-485 filing has none yet.",
            "Overstays and unauthorized work are common in immediate-relative cases (Part 9 items 12, 13, 74); "
            "derive them from the I-94 and status history rather than defaulting to No.",
        ],
        {
            **part1(),
            "filing_category": q(
                "Part 2 items 1-5: EOIR proceedings; principal or derivative; family-based category (3.a); "
                "INA 245(i); CSPA",
                ["Pt2Line1_YN", "Pt2Line2_CB", "Pt2Line3a_CB", "Pt2Line4_CB", "Pt2Line5_CB"],
                ["Pt2Line1_YN", "Pt2Line2_CB", "Pt2Line3a_CB", "Pt2Line4_CB", "Pt2Line5_CB"],
                notes={
                    "Pt2Line1_YN": EOIR_NOTE,
                    "Pt2Line2_CB": (
                        "Derivative only for the spouse or child of a family-preference or VAWA principal; "
                        "immediate relatives have no derivatives."
                    ),
                    "Pt2Line3a_CB": "Select exactly one box in all of item 3. A derivative selects the principal's "
                    "category.",
                    "Pt2Line4_CB": SECTION_245I_NOTE,
                    "Pt2Line5_CB": CSPA_NOTE,
                },
                choices={
                    "Pt2Line1_YN": YES_NO,
                    "Pt2Line2_CB": FILING_TYPE,
                    "Pt2Line3a_CB": FAMILY_CATEGORIES,
                    "Pt2Line4_CB": YES_NO,
                    "Pt2Line5_CB": YES_NO,
                },
            ),
            "underlying_petition": underlying_petition("family"),
            "principal_applicant": principal_applicant(FILLED_OR_NA),
            **shared_tail(
                aos_note=(
                    "1.f for most I-130 and K-1/K-2 beneficiaries (an I-864 is filed). 1.c for a widow(er), 1.d for "
                    "a VAWA self-petitioner, 1.b or 1.a only when the record shows it."
                ),
                public_charge_note=(
                    "Not exempt (23) for most family-based applicants, then answer items 57-64. VAWA "
                    "self-petitioners select 5; the NDAA spouse, child or parent of a service member selects 22."
                ),
                public_charge_details=FILLED_OR_NA,
            ),
        },
    ),
    "i485_asylee_refugee": schema(
        "Asylee or refugee adjustment under INA 209 (Part 2 item 3.d), principal or derivative "
        "(including I-730 beneficiaries).",
        [
            "Part 2: select one 3.d box with its grant or admission date, answer item 5 (CSPA), and leave "
            "item 4 (245(i)) blank: it covers only family, employment, special immigrant and DV categories.",
            "Part 3 is 1.e and Part 9 item 56 is the asylee (3) or refugee (1) exemption; items 57-64 stay blank.",
            "Part 1 items 10-12: an asylee who entered without inspection has no passport or I-94 for the "
            "last arrival (item 11 is 11C). A refugee's I-94 shows the refugee admission. If USCIS issued an "
            "I-94 with the asylum grant, it is the most recent I-94 for item 12.",
            "Part 1 items 14-15: current status Asylee or Refugee; neither status has an expiration date.",
            "Part 9: read the asylum or refugee file before drafting. Items 14 and 18 (proceedings, applications "
            "for relief or protection) are Yes for asylum granted in court and usually for any asylum "
            "applicant; fraudulent travel documents (66-67), entry without inspection (73), unlawful presence "
            "(74), military or police service (43.a, 48-51) and party membership (52) are common in these files. "
            "Inadmissibility that applies may need an I-602 waiver.",
        ],
        {
            **part1(),
            "filing_category": q(
                "Part 2 items 1-3 and 5: EOIR proceedings; principal or derivative; asylee or refugee (3.d) with "
                "grant or admission date; CSPA",
                ["Pt2Line1_YN", "Pt2Line2_CB", "Pt2Line3d_AsyleeRefugeeCB", "Pt2Line3d_Asylum", "Pt2Line3d_Refugee",
                 "Pt2Line5_CB"],
                ["Pt2Line1_YN", "Pt2Line2_CB", "Pt2Line3d_AsyleeRefugeeCB", "Pt2Line5_CB"],
                notes={
                    "Pt2Line1_YN": EOIR_NOTE,
                    "Pt2Line2_CB": (
                        "Derivative for an asylee or refugee spouse or child who got status through the principal "
                        "(including I-730 follow-to-join); then complete the principal applicant block."
                    ),
                    "Pt2Line3d_AsyleeRefugeeCB": "Select exactly one box in all of item 3.",
                    "Pt2Line3d_Asylum": f"With 3d0 only: date asylum was granted (approval notice or IJ order). {DATE}",
                    "Pt2Line3d_Refugee": f"With 3d1 only: date of initial admission as a refugee (I-94). {DATE}",
                    "Pt2Line5_CB": CSPA_NOTE,
                },
                choices={
                    "Pt2Line1_YN": YES_NO,
                    "Pt2Line2_CB": FILING_TYPE,
                    "Pt2Line3d_AsyleeRefugeeCB": {"Asylum status (INA 208)": "3d0", "Refugee status (INA 207)": "3d1"},
                    "Pt2Line5_CB": YES_NO,
                },
            ),
            "underlying_petition": underlying_petition("asylee_refugee"),
            "principal_applicant": principal_applicant(FILLED_OR_NA),
            **shared_tail(
                aos_note="1.e: asylees and refugees are not required by statute to file an I-864 or request an "
                "exemption.",
                public_charge_note="Asylee 3, refugee 1. Both are exempt: skip items 57-64.",
                public_charge_details=NA_ONLY,
            ),
        },
    ),
    "i485_employment_principal": employment(derivative=False),
    "i485_employment_derivative_child": employment(derivative=True),
}

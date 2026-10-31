"""Question schema for Form I-360 filed by a VAWA self-petitioner (edition 01/20/25).

Built against the 01/20/25 edition: the uscis.gov/i-360 Edition Date panel (checked 10/28/2026)
and the footer of both the form and the instructions. Field list: schemas/fields/I-360.json. The
audit's I-360 rules (audit_prepared_forms.audit_i360) check only the VAWA classification and the
self-petitioner's and abuser's names, so this schema is what holds the rest of a plan to the form.

One schema, i360_vawa_self_petition, covers the three VAWA classifications in Part 2 item 1: I
(self-petitioning spouse of an abusive U.S. citizen or LPR), J (self-petitioning child of one) and
K (self-petitioning parent of an abusive U.S. citizen son or daughter). The parts for other
classifications (Part 6 Amerasian, Part 7 widow(er), Part 8 special immigrant juvenile, Part 9
religious worker, and Part 2 items 1.D(1) and 1.P) are not in it.

Every field name and checkbox on-state below was checked against the field list and each box's
tooltip and position on the 01/20/25 PDF. Several names carry the wrong part: Part 10 item 8 is
Pt9Line8a/8b, the Part 13 interpreter's phones, email, language and signature are Pt12*, the
Part 14 preparer's boxes are Pt13* (with Pt12Line8_Signature[1] as the preparer's signature),
and Part 15 is Pt14*. The field notes say which box is which.
"""
from __future__ import annotations

from functools import partial
from typing import Any

from _common import (DATE, FILLED, FILLED_OR_NA, FOREIGN_ONLY, NOT_APPLICABLE, PENDING_SIGNATURE, SIGNATURE_STATUSES,
                     UNIT, YES_NO, q)

EDITION = "01/20/25"
FIELD_LIST = "I-360.json"

FILLED_ONLY = [FILLED]
NA_ONLY = [NOT_APPLICABLE]
SIGNATURE_OR_NA = [PENDING_SIGNATURE, FILLED, NOT_APPLICABLE]

# Every Apt./Ste./Flr. group on this edition: padded on-states, each matching its printed label
# (checked by widget position on every page).

STATE = "U.S. address only: 2-letter state code (drop-down)."
ZIP = "U.S. address only: 5 digits."
PHONE = "10 digits, no punctuation (maxlen 10)."
A_NUMBER = "9 digits, no 'A' or dashes (the form prints 'A-'); pad an 8-digit number with a leading zero."
UNIT_NUMBER = "The apartment, suite or floor number only (maxlen 6); pick the unit type in the matching Unit box."
STREET = "maxlen 34."
CITY = "maxlen 20."
COUNTRY_US = "Country; United States for a U.S. address."

# The plugin's safe mailing address rule for VAWA filings. It goes on every box of every client
# mailing address on this form.
SAFE_MAILING = (
    "VAWA safe mailing address: use the attorney's office address from the attorney profile "
    "(mailing_address) unless the attorney gives another safe address. Never the client's home or "
    "any address the abuser knows or can reach."
)
SHARED_HOME = (
    "The client's physical (home) address still comes from the record, and it goes in no mailing box. "
    "If the physical address is shared with the abuser, add an attorney_decision open item rather "
    "than deciding alone."
)
IN_CARE_OF = (
    "In Care Of Name (maxlen 34). With the attorney's office as the safe address, the firm's name from the "
    "profile (firm_name), or the attorney's (attorney_name) when there is no firm name, so USCIS mail reaches "
    "the office; with another safe address, the name the attorney gives. "
)
NO_PROFILE_ADDRESS = (
    "If the profile has no mailing_address, leave the address blank and tie the question to one "
    "attorney_action open item, blocking filing, asking the attorney to add it."
)

SIGNATURE_NOTE = (
    "Protected box: it can't be typed or signed electronically. Leave it blank; the signer signs in ink."
)
SIGNATURE_DATE = (
    "mm/dd/yyyy. Normally left blank for the signer to date at signing; type a date only on the "
    "attorney's instruction."
)
PART15_TEXT = (
    "About 82 characters a line; the filing copy does not wrap, so break the lines with newlines or the "
    "audit reports the text cut off."
)


# Every I-360 question lists its statuses: [filled] unless it names others.
q = partial(q, allowed=FILLED_ONLY)


def client_mailing_address(
    prefix: str,
    *,
    lead: str,
    extra_fields: tuple[str, ...] = (),
    extra_notes: dict[str, str] | None = None,
) -> tuple[list[str], dict[str, str]]:
    """The boxes of one client mailing address, each carrying the safe mailing address rule."""
    fields = [
        f"{prefix}_InCareofName",
        *extra_fields,
        f"{prefix}_StreetNumberName",
        f"{prefix}_Unit",
        f"{prefix}_AptSteFlrNumber",
        f"{prefix}_CityOrTown",
        f"{prefix}_State",
        f"{prefix}_ZipCode",
        f"{prefix}_Province",
        f"{prefix}_PostalCode",
        f"{prefix}_Country",
    ]
    notes = {
        f"{prefix}_InCareofName": IN_CARE_OF + SAFE_MAILING,
        f"{prefix}_StreetNumberName": (
            f"{lead} Street number and name, {STREET} {SAFE_MAILING} {NO_PROFILE_ADDRESS} {SHARED_HOME}"
        ),
        f"{prefix}_Unit": f"Unit type of the safe mailing address; set it with the unit number or leave both blank. "
        f"{SAFE_MAILING}",
        f"{prefix}_AptSteFlrNumber": f"{UNIT_NUMBER} {SAFE_MAILING}",
        f"{prefix}_CityOrTown": f"{CITY} {SAFE_MAILING}",
        f"{prefix}_State": f"{STATE} {SAFE_MAILING}",
        f"{prefix}_ZipCode": f"{ZIP} {SAFE_MAILING}",
        f"{prefix}_Province": f"{FOREIGN_ONLY} {SAFE_MAILING}",
        f"{prefix}_PostalCode": f"{FOREIGN_ONLY} {SAFE_MAILING}",
        f"{prefix}_Country": f"{COUNTRY_US} {SAFE_MAILING}",
    }
    notes.update(extra_notes or {})
    return fields, notes


# --------------------------------------------------------------------------- Part 1


def filer_mailing_address() -> dict[str, Any]:
    fields, notes = client_mailing_address(
        "Pt1Line6",
        lead="Part 1 item 6 is for someone filing for another person; a VAWA self-petitioner skips it (form note; "
        "uscis.gov Form Filing Tips: 'skip Part 1 and complete Part 3'), and the safe address goes in item 7. "
        "Leave every item 6 box blank. If one is ever filled, it is a client mailing address:",
        extra_fields=("Pt1Line6_OrganizationName",),
        extra_notes={
            "Pt1Line6_OrganizationName": "Organization Name, if applicable (maxlen 34): an organization petitioner "
            "only. Blank for a VAWA self-petitioner. " + SAFE_MAILING,
        },
    )
    return q(
        "Part 1, Item 6: Mailing Address of the person or organization filing (skipped by a VAWA self-petitioner)",
        fields,
        allowed=NA_ONLY,
        notes=notes,
        choices={"Pt1Line6_Unit": UNIT},
    )


def safe_mailing_address() -> dict[str, Any]:
    fields, notes = client_mailing_address(
        "Pt1Line7",
        lead="Part 1 item 7, where USCIS sends the notices for this petition (Instructions, VAWA section: a PO box, "
        "a friend, the attorney, a community organization, or any address where the client can safely and "
        "punctually receive mail).",
    )
    return q(
        "Part 1, Item 7: Alternate and/or Safe Mailing Address (In Care Of Name, street, unit, city, state, ZIP "
        "Code, province, postal code, country)",
        fields,
        ["Pt1Line7_StreetNumberName", "Pt1Line7_CityOrTown", "Pt1Line7_State", "Pt1Line7_ZipCode"],
        allowed=FILLED_ONLY,
        notes=notes,
        choices={"Pt1Line7_Unit": UNIT},
    )


# --------------------------------------------------------------------------- Part 2


VAWA_CLASSIFICATIONS = {
    "I. Self-Petitioning Spouse of Abusive U.S. citizen or Lawful Permanent Resident": "I",
    "J. Self-Petitioning Child of Abusive U.S. citizen or Lawful Permanent Resident": "J",
    "K. VAWA Self-Petitioning Parent of a U.S. citizen son or daughter": "K",
}


# --------------------------------------------------------------------------- Part 3


def self_petitioner_mailing_address() -> dict[str, Any]:
    fields, notes = client_mailing_address(
        "Pt3Line2",
        lead="Part 3 item 2, the self-petitioner's mailing address. uscis.gov's Form Filing Tips treat it as a "
        "correspondence address that item 7 replaces when it is unsafe, and the I-360 has no box for a home "
        "address, so it takes the same safe mailing address as Part 1 item 7.",
    )
    return q(
        "Part 3, Item 2: Mailing Address (In Care Of Name, street, unit, city, state, ZIP Code, province, postal "
        "code, country)",
        fields,
        ["Pt3Line2_StreetNumberName", "Pt3Line2_CityOrTown", "Pt3Line2_State", "Pt3Line2_ZipCode"],
        allowed=FILLED_ONLY,
        notes=notes,
        choices={"Pt3Line2_Unit": UNIT},
    )


# --------------------------------------------------------------------------- Part 5


PART5_ROWS = [(f"Pt5Line{line}", line - 1, line) for line in range(2, 11)]  # (prefix, person, item)


def family_member_1() -> dict[str, Any]:
    prefix = "Pt5Line2"
    return q(
        "Part 5, Item 2: Person 1 (family name, given name, middle name, date of birth, country of birth, "
        "relationship Spouse or Child, A-Number if any)",
        [
            f"{prefix}_FamilyName",
            f"{prefix}_GivenName",
            f"{prefix}_MiddleName",
            f"{prefix}_DateOfBirth",
            f"{prefix}_CountryOfBirth",
            f"{prefix}_Relationship",
            f"{prefix}_AlienNumber",
        ],
        [
            f"{prefix}_FamilyName",
            f"{prefix}_GivenName",
            f"{prefix}_DateOfBirth",
            f"{prefix}_CountryOfBirth",
            f"{prefix}_Relationship",
        ],
        allowed=FILLED_OR_NA,
        notes={
            f"{prefix}_FamilyName": (
                "Part 5 lists the self-petitioner's spouse and children. List every child the record shows, of any "
                "age or marital status; only unmarried children under 21 at filing can be derivatives, of a "
                "self-petitioning spouse or child. A self-petitioning parent (box K) cannot confer derivative "
                "status: a listed child is not denied but derives nothing (3 USCIS-PM D.2(I)). Whether to list the "
                "abuser here as Spouse while the marriage continues is an attorney_decision: Part 10 already "
                "identifies the abuser. not_applicable when there is no spouse or child to list."
            ),
            f"{prefix}_DateOfBirth": DATE,
            f"{prefix}_CountryOfBirth": "Country of birth.",
            f"{prefix}_Relationship": "Person 1 is the only row with a Spouse box; persons 2-9 are children only.",
            f"{prefix}_AlienNumber": "If any. " + A_NUMBER,
        },
        choices={f"{prefix}_Relationship": {"Spouse": "S", "Child": "C"}},
    )


def children_2_to_9() -> dict[str, Any]:
    fields: list[str] = []
    notes: dict[str, str] = {}
    choices: dict[str, dict[str, str]] = {}
    for prefix, person, item in PART5_ROWS[1:]:
        fields += [
            f"{prefix}_FamilyName",
            f"{prefix}_GivenName",
            f"{prefix}_MiddleName",
            f"{prefix}_DateOfBirth",
            f"{prefix}_CountryOfBirth",
            f"{prefix}_Relationship",
            f"{prefix}_AlienNumber",
        ]
        notes[f"{prefix}_FamilyName"] = f"Item {item}, Person {person}."
        notes[f"{prefix}_DateOfBirth"] = DATE
        notes[f"{prefix}_Relationship"] = "A single 'Child' box (on-state '1'). Check it on every filled row."
        choices[f"{prefix}_Relationship"] = {"Child": "1"}
    notes["Pt5Line3_FamilyName"] = (
        "Item 3, Person 2. Fill rows in order; a row is blank or complete. Children beyond Person 9 go in Part 15. "
        "Persons 7-9 (items 8-10, Pt5Line8-10) print on page 6."
    )
    notes["Pt5Line3_AlienNumber"] = "If any. " + A_NUMBER
    return q(
        "Part 5, Items 3-10: Persons 2-9 (children: name, date of birth, country of birth, Child box, A-Number "
        "if any)",
        fields,
        ["Pt5Line3_FamilyName", "Pt5Line3_GivenName", "Pt5Line3_DateOfBirth", "Pt5Line3_CountryOfBirth",
         "Pt5Line3_Relationship"],
        allowed=FILLED_OR_NA,
        notes=notes,
        choices=choices,
    )


# --------------------------------------------------------------------------- Part 15


def additional_information() -> dict[str, Any]:
    fields: list[str] = []
    notes: dict[str, str] = {}
    for item in (3, 4, 5, 6):
        fields += [
            f"Pt14Line{item}a_PageNumber",
            f"Pt14Line{item}b_PartNumber",
            f"Pt14Line{item}c_ItemNumber",
            f"Pt14Line{item}d_AdditionalInfo",
        ]
    notes["Pt14Line3a_PageNumber"] = (
        "Part 15 item 3.A, despite the 'Pt14' names: every Part 15 box is named Pt14. Page number (maxlen 2). Items "
        "3.A-3.C are unbound in the blank's XFA template; fill binds them in the source, so Adobe shows them. Part 15 "
        "items 1-2 (name, A-Number) are Part 1's global boxes (question filer_identity)."
    )
    notes["Pt14Line3b_PartNumber"] = "Part number (maxlen 6), e.g. '4'."
    notes["Pt14Line3c_ItemNumber"] = "Item number (maxlen 6), e.g. '6'."
    notes["Pt14Line3d_AdditionalInfo"] = "Item 3.D, about 4 lines. " + PART15_TEXT
    notes["Pt14Line4d_AdditionalInfo"] = "Item 4.D, about 4 lines. " + PART15_TEXT
    notes["Pt14Line5d_AdditionalInfo"] = "Item 5.D, about 5 lines. " + PART15_TEXT
    notes["Pt14Line6d_AdditionalInfo"] = (
        "Item 6.D, about 5 lines. " + PART15_TEXT + " More entries go on a copy of the page or a separate sheet with "
        "the name, A-Number, page, part and item, signed and dated."
    )
    return q(
        "Part 15, Items 3-6: Additional Information (Page Number, Part Number, Item Number, text): other periods "
        "of living with the abuser, explanations of Yes answers to Part 4 items 5-6, children beyond Person 9",
        fields,
        ["Pt14Line3a_PageNumber", "Pt14Line3b_PartNumber", "Pt14Line3c_ItemNumber", "Pt14Line3d_AdditionalInfo"],
        allowed=FILLED_OR_NA,
        notes=notes,
    )


# --------------------------------------------------------------------------- schema


NOTES = [
    "Edition 01/20/25 (uscis.gov/i-360 Edition Date panel, checked 10/28/2026; form and instructions footers). "
    "The page says pages from different editions may be rejected.",
    "Scope: the VAWA self-petitioning spouse (Part 2 box I) or child (J) of an abusive U.S. citizen or LPR, and "
    "the VAWA self-petitioning parent (K) of an abusive U.S. citizen son or daughter at least 21. The parts for "
    "other classifications are NOT in this schema: Part 6 (Amerasian), Part 7 (widow(er)), Part 8 (special "
    "immigrant juvenile), Part 9 (religious worker), Part 2 item 1.D(1) and item 1.P's description. Leave their "
    "boxes blank; the audit flags any unexpected value. Part 1 items 1-6 and Part 12 serve someone filing for "
    "another person or an organization; they are here so the plan marks them not_applicable explicitly.",
    "Who fills what: a self-petitioner skips Part 1 items 1-6 (form note; uscis.gov Form Filing Tips: 'skip Part 1 "
    "and complete Part 3') except item 7, completes Parts 2-5, 10 and 11, and uses Part 13 (interpreter), Part 14 "
    "(preparer) and Part 15 as needed.",
    "Safe mailing address: every client mailing-address box (Part 1 item 7, Part 3 item 2, and Part 1 item 6 if "
    "ever used, In Care Of Name included) takes the attorney's office address from the attorney profile "
    "(mailing_address), in care of the firm, unless the attorney gives another safe address; with no "
    "mailing_address in the profile, leave them blank behind one blocking attorney_action open item. The I-360 "
    "has no box for the client's "
    "current home address. The one physical address it asks for is Part 10 item 10, the last address shared with "
    "the abuser, which comes from the record. If the client's physical address is shared with the abuser, add an "
    "attorney_decision open item rather than deciding alone.",
    "Confidentiality: a VAWA filing is protected by 8 U.S.C. 1367 (Instructions, DHS Privacy Notice), and USCIS "
    "gives information only to the self-petitioner or the G-28 attorney (Part 10 note). The Part 11 phone and "
    "email must be ones the abuser cannot reach.",
    "FORM DEFECT: Part 15 items 1-2 (name, A-Number) are the same global boxes as Part 1 items 1 and 4, which a "
    "self-petitioner skips. Filling Part 15's header fills Part 1 items 1 and 4 too. Leave both blank by default "
    "(question filer_identity); filling them needs an attorney_decision open item.",
    "Field names that mislead: Part 10 item 8 is Pt9Line8a/8b; the Part 13 interpreter's phones, email, language "
    "and signature are Pt12Line4/5*, Pt12_NameofLanguage and Pt12Line6*; the Part 14 preparer's name, business, "
    "phones, email, statement and date are Pt13*, the preparer's mobile is Pt13ine5_PreparerFaxNumber, and the "
    "preparer's signature is Pt12Line8_Signature[1]; every Part 15 box is Pt14*. Pt4Line6d_DaytimeTelephoneNumber is "
    "the Amerasian father's phone (Part 6 item 6.D), not a Part 4 box: leave it blank. Use the field notes, not the "
    "names.",
    "By classification: a spouse answers Part 5 item 1 and Part 10 item 8; a child or parent marks Part 5 item 1 "
    "not_applicable and types N/A in Part 10 items 8.A and 8.B. Spouses and children may list unmarried children "
    "under 21 as derivatives; a parent cannot confer derivative status (3 USCIS-PM D.2(I)).",
    "Blank, N/A or None: the instructions (How To Complete, item 3) say N/A for a question that does not apply and "
    "None for a zero count. Part 3 items 8-15 say the opposite: leave the space blank. Checkboxes stay blank, and "
    "boxes marked 'if any' stay blank when there is nothing to report.",
    "Part 4 items 5-6 (removal proceedings, unauthorized work) come from the record, never a default; explain every "
    "Yes in Part 15, with the other periods of living with the abuser (Part 10 item 9).",
    "Where to file depends on the classification, where the self-petitioner lives (not the safe mailing address) "
    "and any concurrent I-485: check uscis.gov/i-360 and its Direct Filing Addresses page at filing. USCIS changed "
    "the I-360 filing locations on 10/07/2026.",
]


SCHEMAS = {
    "i360_vawa_self_petition": {
        "kind": "i-360",
        "edition": EDITION,
        "field_list": FIELD_LIST,
        "description": (
            "Form I-360 VAWA self-petition: abused spouse or child of a U.S. citizen or LPR, or abused parent of a "
            "U.S. citizen son or daughter (Part 2 box I, J or K), with the safe mailing address."
        ),
        "notes": list(NOTES),
        "required_questions": {
            "attorney_box": q(
                "Page 1 attorney box: Select this box if Form G-28 or G-28I is attached; Attorney State Bar Number "
                "(if applicable); Attorney or Accredited Representative USCIS Online Account Number (if any)",
                ["CheckBox1", "AttorneyStateBarNumber", "USCISOnlineAcctNumber"],
                ["CheckBox1"],
                allowed=FILLED_OR_NA,
                notes={
                    "CheckBox1": "Select when a G-28 for the self-petitioner is filed with the I-360. Only the "
                    "self-petitioner and the G-28 attorney get information about a VAWA filing (Part 10 note).",
                    "AttorneyStateBarNumber": "From the attorney profile (bar_number); blank for an accredited "
                    "representative.",
                    "USCISOnlineAcctNumber": "The attorney's or representative's own USCIS online account number, if "
                    "any (maxlen 12). Not the self-petitioner's. Blank when the profile says has_uscis_online_account "
                    "\"no\".",
                },
                choices={"CheckBox1": {"G-28 or G-28I attached": "1"}},
            ),
            "filer_identity": q(
                "Part 1, Items 1-5: Your Full Name; USCIS Online Account Number; U.S. Social Security Number; "
                "A-Number; Individual IRS Tax Number (skipped by a VAWA self-petitioner), and Part 15, Items 1-2, the "
                "same name and A-Number boxes",
                ["Pt1Line1_FamilyName", "Pt1Line1_GivenName", "Pt1Line1_MiddleName", "Pt1Line2_OnlineAcctNumber",
                 "Pt1Line3_SSN", "Pt1Line4_AlienNumber", "Pt1Line5_IRSTaxNumber"],
                ["Pt1Line1_FamilyName", "Pt1Line1_GivenName"],
                allowed=[NOT_APPLICABLE, FILLED],
                notes={
                    "Pt1Line1_FamilyName": (
                        "Part 1 item 1 is for someone filing for another person; a VAWA self-petitioner skips to item "
                        "7 (form note) and gives their own details in Part 3. Mark the question not_applicable. FORM "
                        "DEFECT: the name and A-Number boxes are global and also print in Part 15 items 1-2 "
                        "(Pt1Line1_*[1], Pt1Line4_AlienNumber[1]), so Part 15's name and A-Number can't be filled "
                        "without filling Part 1 items 1 and 4 too. Leaving them blank is the default. If the attorney "
                        "wants the name on Part 15, mark the question filled with the self-petitioner's Part 3 name "
                        "(and A-Number, if any) and record that choice as an attorney_decision open item. Never map "
                        "the [1] boxes separately."
                    ),
                    "Pt1Line1_GivenName": "Global: also Part 15 item 1. Blank for a VAWA self-petitioner unless the "
                    "attorney decides otherwise (see Pt1Line1_FamilyName).",
                    "Pt1Line1_MiddleName": "Global: also Part 15 item 1.",
                    "Pt1Line2_OnlineAcctNumber": "Part 1 item 2 (maxlen 12). Leave blank for a VAWA self-petitioner.",
                    "Pt1Line3_SSN": "Part 1 item 3 (maxlen 9). Leave blank; the self-petitioner's SSN is Part 3 item 5.",
                    "Pt1Line4_AlienNumber": (
                        "Part 1 item 4. Global: also Part 15 item 2. Leave blank unless the attorney decided to fill "
                        "Part 15's header; the self-petitioner's A-Number is Part 3 item 6 "
                        "(Pt3Line6_AlienNumber). " + A_NUMBER
                    ),
                    "Pt1Line5_IRSTaxNumber": "Part 1 item 5 (maxlen 9). Leave blank for a VAWA self-petitioner.",
                },
            ),
            "filer_mailing_address": filer_mailing_address(),
            "safe_mailing_address": safe_mailing_address(),
            "classification": q(
                "Part 2, Item 1: Classification Requested (select only one box): I, J or K",
                ["Pt2Line1"],
                ["Pt2Line1"],
                notes={
                    "Pt2Line1": (
                        "One global group for all sixteen boxes A-P; the widgets are not in letter order ([7] is I, "
                        "[11] J, [10] K), so use the choices. I: spouse or former spouse of an abusive U.S. citizen or "
                        "LPR (or a parent of a child the spouse abused). J: child of an abusive U.S. citizen or LPR "
                        "parent. K: parent of an abusive U.S. citizen son or daughter who is at least 21 when the "
                        "petition is filed (Instructions, VAWA section); an LPR son or daughter does not qualify. "
                        "Boxes A-H and L-P, item 1.D(1) (Pt2Line1d1_yes/no) and item 1.P's description "
                        "(Pt2Line1p_Describe) belong to other classifications and stay blank."
                    ),
                },
                choices={"Pt2Line1": VAWA_CLASSIFICATIONS},
            ),
            "self_petitioner_name": q(
                "Part 3, Item 1: Your Full Name (the self-petitioner)",
                ["Pt3Line1_FamilyName", "Pt3Line1_GivenName", "Pt3Line1_MiddleName"],
                ["Pt3Line1_FamilyName", "Pt3Line1_GivenName"],
                notes={
                    "Pt3Line1_FamilyName": "The self-petitioner's legal name. Part 3 is required for a VAWA "
                    "self-petitioner, and whenever Part 1 item 7 is used (Part 3 note). Not global: Part 15's name box "
                    "is Part 1's.",
                    "Pt3Line1_MiddleName": "Blank if none.",
                },
            ),
            "self_petitioner_mailing_address": self_petitioner_mailing_address(),
            "self_petitioner_other_information": q(
                "Part 3, Items 3-7: Date of Birth; Country of Birth; U.S. Social Security Number (if any); A-Number "
                "(if any); Marital Status",
                ["Pt3Line3_DateOfBirth", "Pt3Line4_CountryOfBirth", "Pt3Line5_SSN", "Pt3Line6_AlienNumber",
                 "Pt3Line7_MaritalStatus"],
                ["Pt3Line3_DateOfBirth", "Pt3Line4_CountryOfBirth", "Pt3Line7_MaritalStatus"],
                notes={
                    "Pt3Line3_DateOfBirth": DATE,
                    "Pt3Line4_CountryOfBirth": "The country as named at the time of birth.",
                    "Pt3Line5_SSN": "9 digits, no dashes (maxlen 9). Blank if none.",
                    "Pt3Line6_AlienNumber": "The self-petitioner's A-Number, if any. " + A_NUMBER + " Not global: the "
                    "Part 15 item 2 A-Number box is Part 1's (Pt1Line4_AlienNumber).",
                    "Pt3Line7_MaritalStatus": "Status on the filing date. A self-petitioning spouse divorced from the "
                    "abuser is Divorced (and must file within two years of a divorce connected to the abuse); Widowed "
                    "if the U.S. citizen abuser died (Part 10 item 4).",
                },
                choices={
                    "Pt3Line7_MaritalStatus": {"Single": "S", "Married": "M", "Divorced": "D", "Widowed": "W"},
                },
            ),
            "last_arrival_and_status": q(
                "Part 3, Items 8-15 (if in the United States): Date of Last Arrival; Form I-94 or I-95 Number; "
                "Passport Number; Travel Document Number; Country of Issuance; Expiration Date; Current Nonimmigrant "
                "Status; Date current status expired or will expire",
                ["Pt3Line8_DateOfLastArrival", "Pt3Line9_I94", "Pt3Line10_Passport", "Pt3Line11_TravelDoc",
                 "Pt3Line12_CountryOfIssuanceDocument", "Pt3Line13_ExpDate", "Pt3Line14_CurrentUSCISStatus",
                 "Pt3Line15_DateOfExpired"],
                ["Pt3Line8_DateOfLastArrival"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt3Line8_DateOfLastArrival": (
                        "Only if the self-petitioner is in the United States; mark the question not_applicable if "
                        "abroad. Items 8-15 are the one place this form says to leave a box BLANK, not N/A, when it "
                        "does not apply or the answer is none (an entry without inspection has no I-94 or passport "
                        "entry). " + DATE
                    ),
                    "Pt3Line9_I94": "Form I-94 or I-95 number of the last arrival (maxlen 11). Blank if none was "
                    "issued.",
                    "Pt3Line10_Passport": "Passport used at the last arrival, even if expired (maxlen 30).",
                    "Pt3Line11_TravelDoc": "Travel document number, if one was used instead (maxlen 30).",
                    "Pt3Line12_CountryOfIssuanceDocument": "Country that issued that passport or travel document.",
                    "Pt3Line13_ExpDate": "Expiration date of that passport or travel document. " + DATE,
                    "Pt3Line14_CurrentUSCISStatus": "Item 14, current nonimmigrant status as the record shows it "
                    "(about 41 characters), e.g. 'B-2 visitor (expired)' or 'Parolee'. Blank when the self-petitioner "
                    "has none.",
                    "Pt3Line15_DateOfExpired": "Date that status expired or will expire, from the I-94 or I-95 (not "
                    "the visa). "
                    + DATE,
                },
            ),
            "consulate_abroad": q(
                "Part 4, Item 1: U.S. Consulate (City or Town, Country) where the self-petitioner prefers to apply for "
                "an immigrant visa, if outside the U.S., ineligible to adjust, or not adjusting",
                ["Pt4Line1a_CityOrTown", "Part4Line1b_Country"],
                ["Pt4Line1a_CityOrTown", "Part4Line1b_Country"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt4Line1a_CityOrTown": "City of the U.S. Consulate (maxlen 20). not_applicable when the "
                    "self-petitioner will adjust status in the United States. A self-petitioner abroad may file only "
                    "if the abuser is a U.S. government employee or uniformed services member, or the abuse occurred "
                    "in the United States (Instructions, VAWA section).",
                    "Part4Line1b_Country": "Country of that consulate. Named 'Part4', not 'Pt4'.",
                },
            ),
            "foreign_address": q(
                "Part 4, Item 2: Foreign address (or city and country of last foreign residence) when a U.S. address "
                "is in Part 3; name and address in the native alphabet if it does not use Roman letters",
                ["Pt4Line2a_FamilyName", "Pt4Line2a_GivenName", "Pt4Line2a_MiddleName", "Pt4Line2b_StreetNumberName",
                 "Pt4Line2b_Unit", "Pt4Line2b_AptSteFlrNumber", "Pt4Line2b_CityOrTown", "Pt4Line2b_Province",
                 "Pt4Line2b_PostalCode", "Pt4Line2b_Country"],
                ["Pt4Line2a_FamilyName", "Pt4Line2a_GivenName", "Pt4Line2b_CityOrTown", "Pt4Line2b_Country"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt4Line2a_FamilyName": (
                        "Item 2.A. Required whenever Part 3 item 2 is a U.S. address, which the safe mailing address "
                        "almost always is. The same name as Part 3 in Roman letters; native script only if the native "
                        "alphabet is not Roman, and the filing copy's Courier font may not render it (write it by hand "
                        "then, with an attorney_action open item)."
                    ),
                    "Pt4Line2b_StreetNumberName": "Item 2.B, the foreign address; with none kept, leave the street "
                    "blank and give the city and country of the last foreign residence. " + STREET,
                    "Pt4Line2b_AptSteFlrNumber": UNIT_NUMBER,
                    "Pt4Line2b_CityOrTown": CITY,
                    "Pt4Line2b_Province": "Province or state (maxlen 20). This address has no U.S. state or ZIP box.",
                    "Pt4Line2b_PostalCode": "maxlen 9.",
                },
                choices={"Pt4Line2b_Unit": UNIT},
            ),
            "sex": q(
                "Part 4, Item 3: Sex of the beneficiary",
                ["Pt4Line3_Sex"],
                ["Pt4Line3_Sex"],
                notes={
                    "Pt4Line3_Sex": "As on the birth certificate issued at or closest to birth, or the secondary "
                    "evidence submitted (Instructions, How To Complete, item 6).",
                },
                choices={"Pt4Line3_Sex": {"Male": "M", "Female": "F"}},
            ),
            "other_petitions_filed": q(
                "Part 4, Items 4.A-4.B: Are you filing any other petitions or applications with this one? If Yes, how "
                "many?",
                ["Pt4Line4a", "Pt4Line4b_HowMany"],
                ["Pt4Line4a"],
                notes={
                    "Pt4Line4a": "Count what goes in the same envelope: an I-485 filed concurrently (a U.S. citizen "
                    "abuser, or an LPR abuser with a visa number available), and any I-765 or I-131 filed with it.",
                    "Pt4Line4b_HowMany": "Only if 4.A is Yes: the number, in figures (maxlen 5). Blank if No.",
                },
                choices={"Pt4Line4a": YES_NO},
            ),
            "removal_proceedings": q(
                "Part 4, Item 5: Is the beneficiary in removal proceedings?",
                ["Pt4Line5"],
                ["Pt4Line5"],
                notes={
                    "Pt4Line5": "From the record (NTA, EOIR case status, prior orders), never a default. Yes needs an "
                    "explanation in Part 15 (court, A-Number, next hearing, status of the case).",
                },
                choices={"Pt4Line5": YES_NO},
            ),
            "unauthorized_employment": q(
                "Part 4, Item 6: Has the beneficiary ever worked in the U.S. without permission?",
                ["Pt4Line6"],
                ["Pt4Line6"],
                notes={
                    "Pt4Line6": "From the employment and status history, never a default. Yes needs an explanation in "
                    "Part 15 (employer, dates).",
                },
                choices={"Pt4Line6": YES_NO},
            ),
            "adjustment_attached": q(
                "Part 4, Item 7: Is an application for adjustment of status attached to this petition?",
                ["Pt4Line7"],
                ["Pt4Line7"],
                notes={
                    "Pt4Line7": "Yes only when an I-485 goes in the same envelope. A self-petitioner abroad cannot "
                    "file an I-485.",
                },
                choices={"Pt4Line7": YES_NO},
            ),
            "children_separate_self_petitions": q(
                "Part 5, Item 1: If you are filing as a self-petitioning spouse, have any of your children filed "
                "separate self-petitions?",
                ["Pt5Line1_Checkbox"],
                ["Pt5Line1_Checkbox"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt5Line1_Checkbox": "Self-petitioning spouse (Part 2 box I) only; not_applicable for a child or "
                    "parent. A child the abuser also abused may file their own I-360 (box J) instead of, or as well "
                    "as, being a derivative here.",
                },
                choices={"Pt5Line1_Checkbox": YES_NO},
            ),
            "family_member_1": family_member_1(),
            "children_2_to_9": children_2_to_9(),
            "abuser_identity": q(
                "Part 10, Items 1-4: Full Name of U.S. citizen or Lawful Permanent Resident Abuser; Date of Birth; "
                "Country of Birth; Date of Death",
                ["Pt10Line1_FamilyName", "Pt10Line1_GivenName", "Pt10Line1_MiddleName", "Pt10Line2_DateOfBirth",
                 "Pt10Line3_CountryOfBirth", "Pt10Line4_DateOfDeath"],
                ["Pt10Line1_FamilyName", "Pt10Line1_GivenName", "Pt10Line2_DateOfBirth", "Pt10Line3_CountryOfBirth"],
                notes={
                    "Pt10Line1_FamilyName": "The abuser's legal name from the status evidence (birth or naturalization "
                    "certificate, passport, green card) and the marriage or birth record. This information is "
                    "protected by 8 U.S.C. 1367; never contact the abuser to confirm it.",
                    "Pt10Line2_DateOfBirth": DATE,
                    "Pt10Line3_CountryOfBirth": "The abuser's country of birth.",
                    "Pt10Line4_DateOfDeath": "Only if the abuser has died: a U.S. citizen abuser's death allows a "
                    "self-petition within two years of it (Instructions, VAWA NOTE). Blank otherwise. " + DATE,
                },
            ),
            "abuser_status": q(
                "Part 10, Item 5: Your abuser is now, or was, a (select one): A. U.S. citizen born in the U.S.; B. "
                "U.S. citizen born abroad to U.S. citizen parents; C. U.S. citizen through naturalization (A-Number if "
                "known); D. U.S. Lawful Permanent Resident (A-Number if any); E. Other (Explain)",
                ["Pt10Line5_Checkbox", "Pt10Line5c1_AlienNumber", "Pt10Line5d1_AlienNumber", "Pt10Line5e_Explain"],
                ["Pt10Line5_Checkbox"],
                notes={
                    "Pt10Line5_Checkbox": "One global group. Answer from the abuser's status evidence. A U.S. citizen "
                    "abuser makes the self-petitioner an immediate relative; an LPR abuser a family preference "
                    "(F2A/F2B) self-petitioner. An abuser who lost status because of domestic violence keeps the box "
                    "of the status held (self-petition within two years of the loss).",
                    "Pt10Line5c1_AlienNumber": "Item 5.C(1), with box C only: the naturalized abuser's A-Number, if "
                    "known. "
                    + A_NUMBER,
                    "Pt10Line5d1_AlienNumber": "Item 5.D(1), with box D only: the LPR abuser's A-Number, if any. " + A_NUMBER,
                    "Pt10Line5e_Explain": "Item 5.E, with box E only (one line, about 79 characters; more in Part 15).",
                },
                choices={
                    "Pt10Line5_Checkbox": {
                        "A. U.S. citizen born in the United States": "A",
                        "B. U.S. citizen born abroad to U.S. citizen parents": "B",
                        "C. U.S. citizen through naturalization": "C",
                        "D. U.S. Lawful Permanent Resident": "D",
                        "E. Other (Explain)": "E",
                    },
                },
            ),
            "marriage_counts": q(
                "Part 10, Items 6-7: How many times have you been married? How many times was your abuser married (if "
                "known)?",
                ["Pt10Line6_NumberofMarriages", "Pt10Line7_NumberofAbuseMarriages"],
                ["Pt10Line6_NumberofMarriages"],
                notes={
                    "Pt10Line6_NumberofMarriages": "In figures, counting the marriage to the abuser (maxlen 3). None "
                    "if never married (a self-petitioning child or parent may be).",
                    "Pt10Line7_NumberofAbuseMarriages": "The abuser's marriages, if known (maxlen 3). Blank if "
                    "unknown. Prior marriages of either spouse need proof they ended before this marriage.",
                },
            ),
            "marriage_to_abuser": q(
                "Part 10, Items 8.A-8.B: When did you and your abuser get married? Where did you and your abuser get "
                "married? (N/A for a self-petitioning child or parent)",
                ["Pt9Line8a_DateOfMarriage", "Pt9Line8b_PlaceOfMarriage"],
                ["Pt9Line8a_DateOfMarriage", "Pt9Line8b_PlaceOfMarriage"],
                notes={
                    "Pt9Line8a_DateOfMarriage": "Part 10 item 8.A, despite the 'Pt9' name (Pt9 boxes are otherwise the "
                    "religious worker part). Date of the marriage to the abuser, from the marriage "
                    "certificate: " + DATE + " A "
                    "self-petitioning child or parent types N/A, as the item says; the question is still filled.",
                    "Pt9Line8b_PlaceOfMarriage": "Part 10 item 8.B, despite the 'Pt9' name. City, state or province, "
                    "and country of the marriage (one line, about 82 characters). N/A for a self-petitioning child or "
                    "parent.",
                },
            ),
            "residence_with_abuser": q(
                "Part 10, Items 9-11: When did you live with your abuser (From, To); the last address at which you "
                "lived together with your abuser; the last dates you lived together at this address (From, To)",
                ["Pt10Line9_DateFrom", "Pt10Line9_DateTo", "Pt10Line10_StreetNumberName", "Pt10Line10_Unit",
                 "Pt10Line10_AptSteFlrNumber", "Pt10Line10_CityOrTown", "Pt10Line10_State", "Pt10Line10_ZipCode",
                 "Pt10Line10_Province", "Pt10Line10_PostalCode", "Pt10Line10_Country", "Pt10Line11_DateFrom",
                 "Pt10Line11_DateTo"],
                ["Pt10Line9_DateFrom", "Pt10Line9_DateTo", "Pt10Line10_StreetNumberName", "Pt10Line10_CityOrTown",
                 "Pt10Line10_Country", "Pt10Line11_DateFrom", "Pt10Line11_DateTo"],
                notes={
                    "Pt10Line9_DateFrom": "Item 9, the period of shared residence (joint residence is an eligibility "
                    "element). "
                    + DATE + " Put any other periods of living together, off and on, in Part 15 with page 14, Part 10, "
                    "item 9.",
                    "Pt10Line9_DateTo": DATE,
                    "Pt10Line10_StreetNumberName": (
                        "Item 10, a PHYSICAL address from the record (lease, utility bills, declarations), never the "
                        "safe mailing "
                        "address; " + STREET + " If the self-petitioner still lives there, this is the "
                        "physical address shared with the abuser: add an attorney_decision open item rather than "
                        "deciding alone, and keep it out of every mailing box."
                    ),
                    "Pt10Line10_Unit": "Unit type; set it with Pt10Line10_AptSteFlrNumber or leave both blank.",
                    "Pt10Line10_AptSteFlrNumber": UNIT_NUMBER,
                    "Pt10Line10_CityOrTown": CITY,
                    "Pt10Line10_State": STATE,
                    "Pt10Line10_ZipCode": ZIP,
                    "Pt10Line10_Province": FOREIGN_ONLY,
                    "Pt10Line10_PostalCode": FOREIGN_ONLY,
                    "Pt10Line10_Country": COUNTRY_US,
                    "Pt10Line11_DateFrom": "Item 11, the dates the self-petitioner and the abuser lived together at "
                    "the item 10 address. " + DATE,
                    "Pt10Line11_DateTo": "The last date they lived together there. " + DATE,
                },
                choices={"Pt10Line10_Unit": UNIT},
            ),
            "ead_request": q(
                "Part 10, Item 12: I am currently residing in the United States and I request an Employment "
                "Authorization Document",
                ["Pt10Line12"],
                ["Pt10Line12"],
                notes={
                    "Pt10Line12": "Yes asks USCIS to issue a (c)(31) EAD if the self-petition is approved; No if the "
                    "client will request employment authorization separately, for example a (c)(14) EAD based on "
                    "deferred action (Instructions, VAWA Employment Authorization). Only a self-petitioner residing in "
                    "the United States can answer Yes.",
                },
                choices={"Pt10Line12": YES_NO},
            ),
            "petitioner_statement": q(
                "Part 11, Items 1-2: Petitioner's Statement Regarding the Interpreter (A or B, with the language) and "
                "Regarding the Preparer",
                ["Pt11Line1_Checkbox", "Pt11Line1b_Language", "Pt11Line2_Checkbox", "Pt11Line2_RepresentativeName"],
                ["Pt11Line1_Checkbox"],
                notes={
                    "Pt11Line1_Checkbox": "Item 1.A (reads and understands English) or 1.B (an interpreter read it), "
                    "one only. Part 11 is the self-petitioner's own statement; Part 12 is never used for a "
                    "self-petition.",
                    "Pt11Line1b_Language": "Item 1.B only: the language the interpreter used. The same language as "
                    "Part 13's certification (Pt12_NameofLanguage).",
                    "Pt11Line2_Checkbox": "Item 2: select when an attorney or other preparer (Part 14) prepared the "
                    "petition.",
                    "Pt11Line2_RepresentativeName": "Item 2: the preparer's name, printed in 'the preparer named in "
                    "Part 14., ___, prepared this petition'. Fill it whenever Pt11Line2_Checkbox is selected.",
                },
                choices={
                    "Pt11Line1_Checkbox": {
                        "A. I can read and understand English": "A",
                        "B. The interpreter named in Part 13 read to me": "B",
                    },
                    "Pt11Line2_Checkbox": {"At my request, the preparer named in Part 14 prepared this petition": "C"},
                },
            ),
            "petitioner_contact": q(
                "Part 11, Items 3-5: Petitioner's Daytime Telephone Number; Mobile Telephone Number (if any); Email "
                "Address (if any)",
                ["Pt11Line3_DaytimePhoneNumber1", "Pt11Line4_MobileNumber1", "Pt11Line5_Email"],
                ["Pt11Line3_DaytimePhoneNumber1"],
                notes={
                    "Pt11Line3_DaytimePhoneNumber1": PHONE + " A number the self-petitioner can answer safely, one the "
                    "abuser does not share or monitor. If no number is safe, add an attorney_decision open item (some "
                    "attorneys give the office number) rather than deciding alone.",
                    "Pt11Line4_MobileNumber1": PHONE + " If any, and only if safe.",
                    "Pt11Line5_Email": "If any, and only an account the abuser cannot read.",
                },
            ),
            "petitioner_signature": q(
                "Part 11, Item 6: Petitioner's Signature and Date of Signature",
                ["Pt11Line6_Signature", "Pt11Line6_DateofSignature"],
                allowed=SIGNATURE_STATUSES,
                notes={
                    "Pt11Line6_Signature": SIGNATURE_NOTE + " The self-petitioner signs; a parent or legal guardian "
                    "may sign for one under 14 (Instructions, Signature). USCIS rejects an unsigned petition.",
                    "Pt11Line6_DateofSignature": SIGNATURE_DATE,
                },
            ),
            "authorized_signatory": q(
                "Part 12, Items 1-8: Statement, contact information, declaration and signature of a petitioner filing "
                "for another person or an organization's authorized signatory (not used by a VAWA self-petitioner)",
                ["Pt12Line1_Checkbox", "Pt12Line1b_Language", "Pt12Line2_Checkbox", "Pt12Line2_RepresentativeName",
                 "Pt12Line3_AuthorizedSignatoryFamilyName", "Pt12Line3_AuthorizedSignatoryGivenName",
                 "Pt12Line4_AuthorizedSignatoryTitle", "Pt12Line5_DaytimePhoneNumber", "Pt12Line6_MobileNumber1",
                 "Pt12Line7_Email", "Pt12Line8_Signature[0]", "Pt12Line8_DateofSignature"],
                allowed=NA_ONLY,
                notes={
                    "Pt12Line1_Checkbox": "Part 12 is for someone petitioning for another person or signing for an "
                    "organization; a self-petitioner completes Part 11 instead (Instructions, How To Complete, items "
                    "7-8). Leave Part 12 blank.",
                    "Pt12Line8_Signature[0]": "Part 12 item 8. Index [1] of this name is the PREPARER's signature in "
                    "Part 14 item 8 (question preparer_signature).",
                    "Pt12Line5_DaytimePhoneNumber": "Part 12 item 5. Not the interpreter's boxes, which are also named "
                    "Pt12 (Pt12Line4_InterpreterDaytimeTelephone, Pt12Line5_InterpreterMobileTelephone, "
                    "Pt12Line5_Email).",
                },
                choices={
                    "Pt12Line1_Checkbox": {
                        "A. I can read and understand English": "A",
                        "B. The interpreter named in Part 13 read to me": "B",
                    },
                    "Pt12Line2_Checkbox": {"At my request, the preparer named in Part 14 prepared this petition": "C"},
                },
            ),
            "interpreter_block": q(
                "Part 13, Items 1-6 and certification: Interpreter's Full Name; Business or Organization Name; Mailing "
                "Address; Daytime and Mobile Telephone; Email; the language in the certification",
                ["Pt13Line1_InterpreterFamilyName", "Pt13Line1_InterpreterGivenName",
                 "Pt13Line2_InterpreterBusinessorOrg", "Pt13Line3_StreetNumberName", "Pt13Line3_Unit",
                 "Pt13Line3_AptSteFlrNumber", "Pt13Line3_CityOrTown", "Pt13Line3_State", "Pt13Line3_ZipCode",
                 "Pt13Line3_Province", "Pt13Line3_PostalCode", "Pt13Line3_Country",
                 "Pt12Line4_InterpreterDaytimeTelephone", "Pt12Line5_InterpreterMobileTelephone", "Pt12Line5_Email",
                 "Pt12_NameofLanguage"],
                ["Pt13Line1_InterpreterFamilyName", "Pt13Line1_InterpreterGivenName", "Pt13Line3_StreetNumberName",
                 "Pt13Line3_CityOrTown", "Pt13Line3_Country", "Pt12Line4_InterpreterDaytimeTelephone",
                 "Pt12_NameofLanguage"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt13Line1_InterpreterFamilyName": "Only when Part 11 item 1.B is selected; otherwise "
                    "not_applicable.",
                    "Pt13Line2_InterpreterBusinessorOrg": "If any (maxlen 34).",
                    "Pt13Line3_StreetNumberName": "The interpreter's own mailing address (maxlen 30, shorter than "
                    "other street boxes).",
                    "Pt13Line3_Unit": "Unit type; set it with the unit number or leave both blank.",
                    "Pt13Line3_AptSteFlrNumber": UNIT_NUMBER,
                    "Pt13Line3_CityOrTown": CITY,
                    "Pt13Line3_State": STATE,
                    "Pt13Line3_ZipCode": ZIP,
                    "Pt13Line3_Province": FOREIGN_ONLY,
                    "Pt13Line3_PostalCode": FOREIGN_ONLY,
                    "Pt13Line3_Country": COUNTRY_US,
                    "Pt12Line4_InterpreterDaytimeTelephone": "Part 13 item 4, despite the 'Pt12' name. " + PHONE,
                    "Pt12Line5_InterpreterMobileTelephone": "Part 13 item 5, despite the 'Pt12' name. If any. " + PHONE,
                    "Pt12Line5_Email": "Part 13 item 6, the INTERPRETER's email, despite the 'Pt12Line5' name. If any.",
                    "Pt12_NameofLanguage": "The language in 'I am fluent in English and ___' (about 30 characters); "
                    "the same as Part 11 item 1.B (Pt11Line1b_Language).",
                },
                choices={"Pt13Line3_Unit": UNIT},
            ),
            "interpreter_signature": q(
                "Part 13, Item 7: Interpreter's Signature and Date of Signature",
                ["Pt12Line6_Signature", "Pt12Line6_DateofSignature"],
                allowed=SIGNATURE_OR_NA,
                notes={
                    "Pt12Line6_Signature": "Part 13 item 7, despite the 'Pt12Line6' name (maxlen 1). " + SIGNATURE_NOTE,
                    "Pt12Line6_DateofSignature": "Part 13 item 7's date. " + SIGNATURE_DATE,
                },
            ),
            "preparer_block": q(
                "Part 14, Items 1-7: Preparer's Full Name; Business or Organization Name; Mailing Address; Daytime "
                "Telephone; Mobile Number; Email; Preparer's Statement (7.A or 7.B, extends or does not extend)",
                ["Pt13Line1_PreparerFamilyName", "Pt13Line1_PreparerGivenName", "Pt13Line2_BusinessName",
                 "Pt14Line3_StreetNumberName", "Pt14Line3_Unit", "Pt14Line3_AptSteFlrNumber", "Pt14Line3_CityOrTown",
                 "Pt14Line3_State", "Pt14Line3_ZipCode", "Pt14Line3_Province", "Pt14Line3_PostalCode",
                 "Pt14Line3_Country", "Pt13Line4_DaytimePhoneNumber1", "Pt13ine5_PreparerFaxNumber", "Pt13Line6_Email",
                 "Pt13Line7_Checkbox", "Pt13Line7b_extends"],
                ["Pt13Line1_PreparerFamilyName", "Pt13Line1_PreparerGivenName", "Pt14Line3_StreetNumberName",
                 "Pt14Line3_CityOrTown", "Pt14Line3_Country", "Pt13Line4_DaytimePhoneNumber1", "Pt13Line7_Checkbox"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt13Line1_PreparerFamilyName": "Part 14 item 1, despite the 'Pt13' name. From the attorney "
                    "profile when the attorney prepared the petition; never from another matter.",
                    "Pt13Line1_PreparerGivenName": "Part 14 item 1.",
                    "Pt13Line2_BusinessName": "Part 14 item 2, firm or organization (maxlen 34).",
                    "Pt14Line3_StreetNumberName": "Part 14 item 3 (this address box is correctly named Pt14). The "
                    "preparer's office, from the profile's mailing_address. " + STREET,
                    "Pt14Line3_Unit": "Unit type; set it with the unit number or leave both blank.",
                    "Pt14Line3_AptSteFlrNumber": UNIT_NUMBER,
                    "Pt14Line3_CityOrTown": CITY,
                    "Pt14Line3_State": STATE,
                    "Pt14Line3_ZipCode": ZIP,
                    "Pt14Line3_Province": FOREIGN_ONLY,
                    "Pt14Line3_PostalCode": FOREIGN_ONLY,
                    "Pt14Line3_Country": COUNTRY_US,
                    "Pt13Line4_DaytimePhoneNumber1": "Part 14 item 4. " + PHONE,
                    "Pt13ine5_PreparerFaxNumber": "Part 14 item 5, the preparer's MOBILE number, despite the 'Fax' "
                    "name and the missing 'L' in 'Pt13ine5'. If any. " + PHONE,
                    "Pt13Line6_Email": "Part 14 item 6, if any.",
                    "Pt13Line7_Checkbox": "Part 14 item 7.A (not an attorney or accredited representative) or 7.B "
                    "(attorney or accredited representative).",
                    "Pt13Line7b_extends": "With 7.B only: whether the representation extends beyond preparing this "
                    "petition. An attorney who files a G-28 answers 'extends'. Blank with 7.A.",
                },
                choices={
                    "Pt14Line3_Unit": UNIT,
                    "Pt13Line7_Checkbox": {
                        "A. I am not an attorney or accredited representative": "A",
                        "B. I am an attorney or accredited representative": "B",
                    },
                    "Pt13Line7b_extends": {"extends": "Y", "does not extend": "N"},
                },
            ),
            "preparer_signature": q(
                "Part 14, Item 8: Preparer's Signature and Date of Signature",
                ["Pt12Line8_Signature[1]", "Pt13Line8_DateofSignature"],
                allowed=SIGNATURE_OR_NA,
                notes={
                    "Pt12Line8_Signature[1]": "Part 14 item 8, the PREPARER's signature: index [1] of a Part 12 name "
                    "(index [0] is Part 12's signatory). " + SIGNATURE_NOTE,
                    "Pt13Line8_DateofSignature": "Part 14 item 8's date, despite the 'Pt13' name. " + SIGNATURE_DATE,
                },
            ),
            "additional_information": additional_information(),
        },
    },
}

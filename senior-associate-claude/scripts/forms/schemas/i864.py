"""Question schema for Form I-864, Affidavit of Support Under Section 213A of the INA.

Built against the 08/24/26 edition (uscis.gov/i-864 and the PDF footer). Field list:
schemas/fields/I-864.json. Every box on the form except the barcode belongs to exactly one
question; global boxes are named once, by base name.

On this edition the field names follow an older part order: Part 2 (the sponsor) is P4_*,
Part 3 (the principal immigrant) is P2_*, Part 4 (the immigrants sponsored) is P3_*. The field
notes say which box is which wherever a name misleads. The audit's I-864 rules
(audit_prepared_forms.audit_i864) require the boxes in the non-empty lists of
sponsorship_basis, sponsor_identity, sponsor_mailing_address, principal_immigrant_identity,
principal_immigrant_mailing_address, household_size, current_income and tax_year_income.
"""
from __future__ import annotations

from typing import Any

from _common import DATE, FILLED_OR_NA, FOREIGN_ONLY, OPTIONAL_SIGNATURE, SIGNATURE_STATUSES, UNIT, YES_NO, q

EDITION = "08/24/26"
FIELD_LIST = "I-864.json"


# Every address unit group on this edition carries padded on-states.

STATE = "U.S. address only: 2-letter state code (drop-down)."
ZIP = "U.S. address only: 5-digit ZIP Code."
PHONE = "10 digits, no punctuation (maxlen 10)."
MONEY = "Digits only, no '$' or commas (e.g. 81200 or 81200.00); Adobe treats the box as a number."
A_NUMBER = "If any: 9 digits, no 'A'."
ACCOUNT = "If any: 12 characters, only with an IOE receipt."


# --------------------------------------------------------------------------- Part 4 (immigrants sponsored)


FAMILY_ROWS = [
    # (item, family, given, middle, relationship, date of birth, A-Number, account number)
    (4, "P3_Line3a_FamilyName", "P3_Line3b_GivenName", "P3_Line3c_MiddleName", "P3_Line4_Relationship",
     "P3_Line_DateOfBirth", "P2_Line5_AlienNumber[1]", "P3_Line7_AcctIdentifier"),
    (5, "P3_Line8a_FamilyName", "P3_Line8b_GivenName", "P3_Line8c_MiddleName", "P3_Line9_Relationship",
     "P3_Line10_DateOfBirth", "P3_Line11_AlienNumber", "P3_Line12_AcctIdentifier"),
    (6, "P3_Line13a_FamilyName", "P3_Line13b_GivenName", "P3_Line13c_MiddleName", "P3_Line14_Relationship",
     "P3_Line15_DateOfBirth", "P2_Line5_AlienNumber[2]", "P3_Line17_AcctIdentifier"),
    (7, "P3_Line18a_FamilyName", "P3_Line18b_GivenName", "P3_Line18c_MiddleName", "P3_Line19_Relationship",
     "P3_Line20_DateOfBirth", "P3_Line21_AlienNumber", "P3_Line22_AcctIdentifier"),
]


def family_member(row: int) -> dict[str, Any]:
    item, family, given, middle, relationship, dob, a_number, account = FAMILY_ROWS[row - 1]
    notes = {
        family: (
            f"Part 4 item {item}, Family Member {row}: only when item 2 or 3 is selected; otherwise "
            "not_applicable. Name and relationship boxes are unbound in the XFA template (fill binds them "
            "when filled). Maxlen 30; more members go in Part 11."
        ),
        relationship: "Relationship to the principal immigrant (maxlen 30), e.g. Spouse, Son, Daughter.",
        dob: DATE,
        a_number: A_NUMBER,
        account: ACCOUNT,
    }
    if a_number.startswith("P2_Line5_AlienNumber"):
        notes[a_number] = A_NUMBER + f" Box {a_number[-3:]} of the principal immigrant's A-Number name."
    return q(
        f"Part 4, Item {item}: Family Member {row} (name, relationship to the principal immigrant, date of "
        "birth, A-Number, online account number)",
        [family, given, middle, relationship, dob, a_number, account],
        [family, given, relationship, dob],
        allowed=FILLED_OR_NA,
        notes=notes,
    )


# --------------------------------------------------------------------------- Parts 9-11


def additional_information() -> dict[str, Any]:
    fields: list[str] = []
    for item in range(3, 7):
        fields += [
            f"P11_Line{item}a_PageNumber",
            f"P11_Line{item}b_PartNumber",
            f"P11_Line{item}c_ItemNumber",
            f"P11_Line{item}d_AdditionalInfo",
        ]
    return q(
        "Part 11, Items 3-6: Additional information (page, part, item, text)",
        fields,
        ["P11_Line3a_PageNumber", "P11_Line3b_PartNumber", "P11_Line3c_ItemNumber", "P11_Line3d_AdditionalInfo"],
        allowed=FILLED_OR_NA,
        notes={
            "P11_Line3a_PageNumber": (
                "Page number only (maxlen 2); part and item boxes hold 6 characters. Items 1-2 (the sponsor's "
                "name and A-Number) fill from Part 2."
            ),
            "P11_Line3d_AdditionalInfo": (
                "Each 'd' box holds 5 lines of 85 characters (Courier 10 pt) and does not wrap: break the lines "
                "yourself. Uses: family members past item 7, more household members past item 11, domicile "
                "abroad, a foreign phone number."
            ),
        },
    )


def required_questions() -> dict[str, dict[str, Any]]:
    questions: dict[str, dict[str, Any]] = {
        "attorney_box": q(
            "Page 1 attorney box: Form G-28 attached, attorney State Bar number, attorney USCIS online account number",
            ["G28-CheckBox1", "AttorneyStateBarNumber", "USCISOnlineAcctNumber"],
            ["G28-CheckBox1", "AttorneyStateBarNumber"],
            allowed=FILLED_OR_NA,
            notes={
                "G28-CheckBox1": (
                    "Select when a G-28 for the sponsor is filed with the I-864 (on-state 1; the blank stores 0). "
                    "not_applicable when no attorney represents the sponsor."
                ),
                "AttorneyStateBarNumber": "Profile key bar_number: the same value as the sponsor's G-28 "
                "Pt2Line1b_BarNumber.",
                "USCISOnlineAcctNumber": (
                    "The ATTORNEY's online account number (profile key uscis_online_account_number, 12 characters), if "
                    "any; the same as G-28 Pt1Line1_USCISOnlineAcctNumber. The sponsor's own is Part 2 item 11. Blank "
                    "when the profile says has_uscis_online_account \"no\"."
                ),
            },
            choices={"G28-CheckBox1": {"G-28 attached": "1"}},
        ),
        "sponsorship_basis": q(
            "Part 1, Items 1.a-1.f: Basis for filing (petitioner, relative who filed or 5% owner of the entity "
            "that filed an I-140, only or one of two joint sponsors, substitute sponsor)",
            ["P1_Line1a-f_CB", "P1_Line1b_Relationship", "P1_Line1c_InterestIn", "P1_Line1c_Relationship",
             "P1_Line1e1_Checkbox", "P1_Line1f_Relationship"],
            ["P1_Line1a-f_CB"],
            notes={
                "P1_Line1a-f_CB": (
                    "One global group; select only one. 1.a: the petitioner on the I-130 (or I-129F, I-600, I-800). "
                    "1.d/1.e: a joint sponsor (need not be related). 1.f: substitute sponsor after the petitioner died."
                ),
                "P1_Line1b_Relationship": "Only with 1.b: the sponsor's relationship to the intending immigrant.",
                "P1_Line1c_InterestIn": "Only with 1.c: the business that filed the I-140 (maxlen 34).",
                "P1_Line1c_Relationship": "Only with 1.c: relationship to the intending immigrant (maxlen 38).",
                "P1_Line1e1_Checkbox": "Only with 1.e: first or second of two joint sponsors (one global group).",
                "P1_Line1f_Relationship": "Only with 1.f: the sponsor is the intending immigrant's ... (maxlen 38).",
            },
            choices={
                "P1_Line1a-f_CB": {
                    "1.a I am the petitioner": "1A",
                    "1.b I filed an alien worker petition (relative)": "1B",
                    "1.c I have an ownership interest of at least 5 percent": "1C",
                    "1.d I am the only joint sponsor": "1D",
                    "1.e I am the first or second of two joint sponsors": "1E",
                    "1.f I am the substitute sponsor": "1F",
                },
                "P1_Line1e1_Checkbox": {"first": "1", "second": "2"},
            },
        ),
        "sponsor_identity": q(
            "Part 2, Items 1 and 5-7: Sponsor's full legal name, country of domicile, date of birth, country of birth",
            ["P4_Line1a_FamilyName", "P4_Line1b_GivenName", "P4_Line1c_MiddleName", "P4_Line5_CountryOfDomicile",
             "P4_Line6_DateOfBirth", "P4_Line7_CityofBirth"],
            ["P4_Line1a_FamilyName", "P4_Line1b_GivenName", "P4_Line5_CountryOfDomicile", "P4_Line6_DateOfBirth",
             "P4_Line7_CityofBirth"],
            notes={
                "P4_Line1a_FamilyName": (
                    "Part 2 item 1 (the P4 names are Part 2 on this edition); maxlen 30. Global: also prints in "
                    "Part 11 item 1. Set the base name once."
                ),
                "P4_Line1b_GivenName": "Maxlen 18. Global: also Part 11 item 1.",
                "P4_Line1c_MiddleName": "If any; maxlen 18. Global: also Part 11 item 1.",
                "P4_Line5_CountryOfDomicile": (
                    "Item 5. Normally 'United States'. A sponsor living abroad who claims U.S. domicile must explain "
                    "and document it (Part 11)."
                ),
                "P4_Line6_DateOfBirth": "Item 6. " + DATE,
                "P4_Line7_CityofBirth": "Item 7, the sponsor's COUNTRY of birth, despite the CityofBirth name.",
            },
        ),
        "sponsor_mailing_address": q(
            "Part 2, Items 2-3: Sponsor's current mailing address, and whether it is the physical address",
            ["P4_Line2a_InCareOf", "P4_Line2b_StreetNumberName", "P4_Line2c_Unit", "P4_Line2d_AptSteFlrNumber",
             "P4_Line2e_CityOrTown", "P4_Line2f_State", "P4_Line2g_ZipCode", "P4_Line2h_Province",
             "P4_Line2i_PostalCode", "P4_Line2j_Country", "P1_Line3_Checkbox"],
            ["P4_Line2b_StreetNumberName", "P4_Line2e_CityOrTown", "P4_Line2f_State", "P4_Line2g_ZipCode",
             "P4_Line2j_Country", "P1_Line3_Checkbox"],
            notes={
                "P4_Line2a_InCareOf": "In care of name, if any (maxlen 34).",
                "P4_Line2b_StreetNumberName": (
                    "Maxlen 34. The audit requires a state and ZIP Code here; a sponsor whose mailing address is "
                    "abroad needs an attorney_decision open item."
                ),
                "P4_Line2c_Unit": "Unit type; one global group. Set it with P4_Line2d_AptSteFlrNumber or leave both "
                "blank.",
                "P4_Line2d_AptSteFlrNumber": "Unit number (maxlen 6).",
                "P4_Line2e_CityOrTown": "Maxlen 20.",
                "P4_Line2f_State": STATE,
                "P4_Line2g_ZipCode": ZIP,
                "P4_Line2h_Province": FOREIGN_ONLY,
                "P4_Line2i_PostalCode": FOREIGN_ONLY,
                "P1_Line3_Checkbox": (
                    "Part 2 item 3 despite the P1 name: is the mailing address also the physical address? No means "
                    "sponsor_physical_address is filled."
                ),
            },
            choices={"P4_Line2c_Unit": dict(UNIT), "P1_Line3_Checkbox": dict(YES_NO)},
        ),
        "sponsor_physical_address": q(
            "Part 2, Item 4: Sponsor's physical address (if different from the mailing address)",
            ["P4_Line4a_StreetNumberName", "P4_Line4b_Unit", "P4_Line4c_AptSteFlrNumber", "P4_Line4d_CityOrTown",
             "P4_Line4e_State", "P4_Line4f_ZipCode", "P4_Line4g_Province", "P4_Line4h_PostalCode", "P4_Line4i_Country"],
            ["P4_Line4a_StreetNumberName", "P4_Line4d_CityOrTown", "P4_Line4i_Country"],
            allowed=FILLED_OR_NA,
            notes={
                "P4_Line4a_StreetNumberName": "Only when item 3 is No; otherwise not_applicable. Maxlen 34.",
                "P4_Line4b_Unit": "Unit type; one global group. Set it with P4_Line4c_AptSteFlrNumber or leave both "
                "blank.",
                "P4_Line4c_AptSteFlrNumber": "Unit number (maxlen 6).",
                "P4_Line4d_CityOrTown": "Maxlen 20.",
                "P4_Line4e_State": STATE,
                "P4_Line4f_ZipCode": ZIP,
                "P4_Line4g_Province": FOREIGN_ONLY,
                "P4_Line4h_PostalCode": FOREIGN_ONLY,
            },
            choices={"P4_Line4b_Unit": dict(UNIT)},
        ),
        "sponsor_ssn": q(
            "Part 2, Item 8: Sponsor's U.S. Social Security Number (required)",
            ["P4_Line10_SocialSecurityNumber"],
            ["P4_Line10_SocialSecurityNumber"],
            notes={
                "P4_Line10_SocialSecurityNumber": (
                    "Item 8 despite the Line10 name. 9 digits, no dashes. Required of every sponsor: from the Social "
                    "Security card or a tax document, never from memory."
                ),
            },
        ),
        "sponsor_status": q(
            "Part 2, Item 9: Sponsor's immigration status (U.S. citizen, U.S. national, lawful permanent resident)",
            ["P4_Line11a_Checkbox", "P4_Line11b_Checkbox", "P4_Line11c_Checkbox"],
            notes={
                "P4_Line11a_Checkbox": (
                    "Item 9 despite the Line11 names: three separate boxes; set exactly one. Joint and substitute "
                    "sponsors attach proof of status."
                ),
            },
            choices={
                "P4_Line11a_Checkbox": {"I am a U.S. citizen": "A"},
                "P4_Line11b_Checkbox": {"I am a U.S. national": "B"},
                "P4_Line11c_Checkbox": {"I am a lawful permanent resident": "C"},
            },
        ),
        "sponsor_a_number_and_account": q(
            "Part 2, Items 10-11: Sponsor's A-Number and USCIS Online Account Number (if any)",
            ["P4_Line12_AlienNumber", "P4_Line13_AcctIdentifier"],
            allowed=FILLED_OR_NA,
            notes={
                "P4_Line12_AlienNumber": (
                    "Item 10 despite the Line12 name. " + A_NUMBER + " Global: also prints in Part 11 item 2. "
                    "not_applicable when the sponsor has neither number."
                ),
                "P4_Line13_AcctIdentifier": "Item 11, the SPONSOR's online account number. " + ACCOUNT,
            },
        ),
        "sponsor_military_service": q(
            "Part 2, Item 12: Sponsor on active duty in the U.S. Armed Forces or U.S. Coast Guard (petitioning "
            "sponsors only)",
            ["P4_Line14_Checkboxes"],
            ["P4_Line14_Checkboxes"],
            allowed=FILLED_OR_NA,
            notes={
                "P4_Line14_Checkboxes": (
                    "Item 12 despite the Line14 name; one global group. Petitioning sponsors only: not_applicable "
                    "for a joint or substitute sponsor. Yes (active duty, not training) lowers the requirement to "
                    "100% of the guidelines for a spouse or child; it needs evidence. Answer from the record."
                ),
            },
            choices={"P4_Line14_Checkboxes": dict(YES_NO)},
        ),
        "principal_immigrant_identity": q(
            "Part 3, Items 1 and 3-7: Principal immigrant's name, citizenship, date of birth, A-Number, online "
            "account number, daytime phone",
            ["P2_Line1a_FamilyName", "P2_Line1b_GivenName", "P2_Line1c_MiddleName", "P2_Line3_CountryCitizenship",
             "P2_Line4_DateOfBirth", "P2_Line5_AlienNumber[0]", "Pt2_Line6_USCISOnlineAcctNumber",
             "P2_Line7_DaytimePhoneNumber"],
            ["P2_Line1a_FamilyName", "P2_Line1b_GivenName", "P2_Line3_CountryCitizenship", "P2_Line4_DateOfBirth"],
            notes={
                "P2_Line1a_FamilyName": "Part 3 item 1 (the P2 names are Part 3 on this edition); maxlen 30.",
                "P2_Line1b_GivenName": "Maxlen 18.",
                "P2_Line1c_MiddleName": "If any; maxlen 18.",
                "P2_Line4_DateOfBirth": DATE,
                "P2_Line5_AlienNumber[0]": (
                    "Item 5, the principal immigrant's A-Number. " + A_NUMBER + " Boxes [1] and [2] of this name are "
                    "Part 4 family members 1 and 3. Leave this value out of visible_values: the rendered text reads "
                    "this spaced-out box out of order, so the audit cannot find it; check it on the render."
                ),
                "Pt2_Line6_USCISOnlineAcctNumber": "Item 6. " + ACCOUNT,
                "P2_Line7_DaytimePhoneNumber": (
                    "Item 7. " + PHONE + " A longer foreign number goes in Part 11, citing Page 3, Part 3, Item 7."
                ),
            },
        ),
        "principal_immigrant_mailing_address": q(
            "Part 3, Item 2: Principal immigrant's current mailing address",
            ["P2_Line2_InCareOf", "P2_Line2_StreetNumberName", "P2_Line2_Unit", "P2_Line2_AptSteFlrNumber",
             "P2_Line2_CityOrTown", "P2_Line2_State", "P2_Line2_ZipCode", "P2_Line2_Province", "P2_Line2_PostalCode",
             "P2_Line2_Country"],
            ["P2_Line2_StreetNumberName", "P2_Line2_CityOrTown", "P2_Line2_Country"],
            notes={
                "P2_Line2_InCareOf": "In care of name, if any (maxlen 34).",
                "P2_Line2_StreetNumberName": "Maxlen 34.",
                "P2_Line2_Unit": "Unit type; one global group. Set it with P2_Line2_AptSteFlrNumber or leave both "
                "blank.",
                "P2_Line2_AptSteFlrNumber": "Unit number (maxlen 6).",
                "P2_Line2_CityOrTown": "Maxlen 20.",
                "P2_Line2_State": STATE,
                "P2_Line2_ZipCode": ZIP,
                "P2_Line2_Province": FOREIGN_ONLY,
                "P2_Line2_PostalCode": FOREIGN_ONLY,
            },
            choices={"P2_Line2_Unit": dict(UNIT)},
        ),
        "immigrants_sponsored": q(
            "Part 4, Items 1-3: Sponsoring the principal immigrant; family members immigrating within six months "
            "or more than six months later",
            ["P3_Line1_Checkbox", "P3_Line2_SponsoringFamily[0]", "P3_Line2_SponsoringFamily[1]"],
            ["P3_Line1_Checkbox"],
            notes={
                "P3_Line1_Checkbox": (
                    "Part 4 item 1 (the P3 names are Part 4 on this edition); one global group. No only for a second "
                    "joint sponsor covering family members alone, or for family members following more than six "
                    "months later."
                ),
                "P3_Line2_SponsoringFamily[0]": (
                    "Item 2: family members immigrating with the principal or within six months, listed in items "
                    "4-7. Blank when there are none (a spouse petition with no derivatives)."
                ),
                "P3_Line2_SponsoringFamily[1]": (
                    "Item 3 despite the Line2 name: family members immigrating more than six months later."
                ),
            },
            choices={
                "P3_Line1_Checkbox": dict(YES_NO),
                "P3_Line2_SponsoringFamily[0]": {"Family members within six months": "Y"},
                "P3_Line2_SponsoringFamily[1]": {"Family members more than six months later": "Y"},
            },
        ),
    }
    for row in range(1, 5):
        questions[f"family_member_{row}"] = family_member(row)
    questions.update(
        {
            "household_size": q(
                "Part 5, Items 1-8: Sponsor's household size (persons sponsored, yourself, spouse, dependent children, "
                "other dependents, prior sponsored immigrants, I-864A relatives, total)",
                ["P3_Line28_TotalNumberofImmigrants", "P5_Line2_Yourself", "P5_Line3_Married",
                 "P5_Line4_DependentChildren", "P5_Line5_OtherDependents", "P5_Line6_Sponsors",
                 "P5_Line7_SameResidence", "Override"],
                ["P3_Line28_TotalNumberofImmigrants", "P5_Line2_Yourself", "P5_Line3_Married",
                 "P5_Line4_DependentChildren", "P5_Line5_OtherDependents", "P5_Line6_Sponsors",
                 "P5_Line7_SameResidence", "Override"],
                notes={
                    "P3_Line28_TotalNumberofImmigrants": (
                        "Part 5 item 1 despite the P3 name: everyone sponsored on this affidavit (the principal "
                        "immigrant plus Part 4 items 4-7)."
                    ),
                    "P5_Line2_Yourself": "Item 2: always 1 (read-only in Adobe and pre-filled 1 in the blank).",
                    "P5_Line3_Married": (
                        "Item 3: 1 if married, 0 if not or if the spouse is the sponsored immigrant already counted in "
                        "item 1. Enter 0, never blank, in items 3-7."
                    ),
                    "P5_Line4_DependentChildren": "Item 4: unmarried children under 21 not already counted in item 1.",
                    "P5_Line5_OtherDependents": "Item 5: every other dependent claimed on the most recent federal "
                    "return.",
                    "P5_Line6_Sponsors": (
                        "Item 6: immigrants the sponsor still supports under an earlier I-864 or I-864EZ. Only the "
                        "sponsor knows; do not assume 0."
                    ),
                    "P5_Line7_SameResidence": "Item 7: relatives combining income with an I-864A.",
                    "Override": "Item 8, household size, despite the Override name: the sum of items 1-7 (not "
                    "calculated).",
                },
            ),
            "sponsor_employment": q(
                "Part 6, Items 1-6: Sponsor is currently employed (occupation, employers 1-2), self-employed, retired, "
                "unemployed",
                ["P6_Line1_Checkbox", "P6_Line1a_NameofEmployer", "P6_Line1a1_NameofEmployer",
                 "P6_Line1a2_NameofEmployer", "P6_Line4_Checkbox", "P6_Line4a_SelfEmployedAs", "P6_Line5_Checkbox",
                 "P6_Line5a_DateRetired", "P6_Line6_Checkbox", "P6_Line6a_DateofUnemployment"],
                notes={
                    "P6_Line1_Checkbox": (
                        "Item 1 'Employed' (on-state ' Y'). FORM DEFECT: this one global group is also Part 8 items "
                        "1.a (A) and 1.b (B), so only one of the three can be checked. Set ' Y' when the sponsor is "
                        "employed and leave Part 8 1.a/1.b for the sponsor to mark by hand at signing (attorney_action "
                        "open item). Use A or B here only when the sponsor is not employed. Select every item 1-6 that "
                        "applies."
                    ),
                    "P6_Line1a_NameofEmployer": "Item 1, the OCCUPATION ('Employed as a/an'), despite the "
                    "NameofEmployer name.",
                    "P6_Line1a1_NameofEmployer": "Item 2, Name of Employer 1 (maxlen 34).",
                    "P6_Line1a2_NameofEmployer": "Item 3, Name of Employer 2, if any (maxlen 34).",
                    "P6_Line4_Checkbox": "Item 4 Self-Employed (on-state ' Y', leading space).",
                    "P6_Line4a_SelfEmployedAs": "Item 4 occupation. Attach the Schedule C, D, E or F filed with the "
                    "return.",
                    "P6_Line5_Checkbox": "Item 5 Retired (on-state 'Y ', trailing space).",
                    "P6_Line5a_DateRetired": "Retired since. " + DATE,
                    "P6_Line6_Checkbox": "Item 6 Unemployed (on-state ' Y').",
                    "P6_Line6a_DateofUnemployment": "Unemployed since. " + DATE,
                },
                choices={
                    "P6_Line1_Checkbox": {
                        "Employed": " Y",
                        "Part 8 1.a I can read and understand English (linked box; see note)": "A",
                        "Part 8 1.b The interpreter read it to me (linked box; see note)": "B",
                    },
                    "P6_Line4_Checkbox": {"Self-Employed": " Y"},
                    "P6_Line5_Checkbox": {"Retired": "Y "},
                    "P6_Line6_Checkbox": {"Unemployed": " Y"},
                },
            ),
            "current_income": q(
                "Part 6, Items 7 and 12: Sponsor's current individual annual income, and current annual household "
                "income",
                ["P6_Line2_TotalIncome", "P6_Line15_TotalHouseholdIncome"],
                ["P6_Line2_TotalIncome", "P6_Line15_TotalHouseholdIncome"],
                notes={
                    "P6_Line2_TotalIncome": (
                        "Item 7 despite the Line2 name: current earned or retirement income (employer letter, pay "
                        "stubs). " + MONEY
                    ),
                    "P6_Line15_TotalHouseholdIncome": (
                        "Item 12: item 7 plus the current income in items 8-11. " + MONEY + " Adobe recalculates this "
                        "box from items 7-11 and shows the sum, so enter exactly that sum."
                    ),
                },
            ),
            "household_member_income": q(
                "Part 6, Items 8-11 and 13-14: Income of household members (name, relationship, current income), "
                "Form I-864A filed, or the intending immigrant needs none",
                ["P6_Line3_Name", "P6_Line4_Relationship", "P6_Line5_CurrentIncome", "P6_Line6_Name",
                 "P6_Line7_Relationship", "P6_Line8_CurrentIncome", "P6_Line9_Name", "P6_Line10_Relationship",
                 "P6_Line11_CurrentIncome", "P6_Line12_Name", "P6_Line13_Relationship", "P6_Line14_CurrentIncome",
                 "P6_Line16_CompletedForm", "P6_Line17_NotNeedComplete", "P6_Line17_Name"],
                ["P6_Line3_Name", "P6_Line4_Relationship", "P6_Line5_CurrentIncome"],
                allowed=FILLED_OR_NA,
                notes={
                    "P6_Line3_Name": (
                        "Item 8, Person 1 (maxlen 38). The names mislead: items 8-11 are P6_Line3/4/5, 6/7/8, 9/10/11 "
                        "and 12/13/14 (name, relationship, income), not items 3-14. not_applicable when the sponsor "
                        "relies on their own income alone."
                    ),
                    "P6_Line4_Relationship": "Item 8 relationship (maxlen 38), not item 4.",
                    "P6_Line5_CurrentIncome": "Item 8 current income, not item 5. " + MONEY,
                    "P6_Line8_CurrentIncome": "Item 9 current income. " + MONEY,
                    "P6_Line11_CurrentIncome": "Item 10 current income. " + MONEY,
                    "P6_Line14_CurrentIncome": "Item 11 current income. " + MONEY,
                    "P6_Line16_CompletedForm": "Item 13: the people in items 8-11 completed Forms I-864A, filed with "
                    "this affidavit.",
                    "P6_Line17_NotNeedComplete": (
                        "Item 14: a person in items 8-11 is the intending immigrant with no accompanying dependents, "
                        "so needs no I-864A."
                    ),
                    "P6_Line17_Name": (
                        "The unlabeled box at the end of item 14: that intending immigrant's name (maxlen 38). In "
                        "Acrobat, ticking item 17 clears this box."
                    ),
                },
                choices={
                    "P6_Line16_CompletedForm": {"I-864As completed and filed": "Y"},
                    "P6_Line17_NotNeedComplete": {"Intending immigrant needs no I-864A": "Y"},
                },
            ),
            "tax_filing_history": q(
                "Part 6, Items 15 and 17: Federal income tax return filed for each of the three most recent tax years; "
                "not required to file",
                ["P6_Line18a_Checkbox", "P6_Line17_IWasNotReq"],
                ["P6_Line18a_Checkbox"],
                notes={
                    "P6_Line18a_Checkbox": (
                        "Item 15 despite the Line18a name; one global group. Answer from transcripts or the sponsor; "
                        "one transcript covers one year only."
                    ),
                    "P6_Line17_IWasNotReq": (
                        "Item 17: not required to file because income was below the filing threshold; attach the "
                        "explanation and evidence."
                    ),
                },
                choices={
                    "P6_Line18a_Checkbox": dict(YES_NO),
                    "P6_Line17_IWasNotReq": {"I was not required to file": "Y"},
                },
            ),
            "tax_year_income": q(
                "Part 6, Items 16.a-16.c: Total income on the federal returns for the most recent, 2nd and 3rd most "
                "recent tax years",
                ["P6_Line19a_TaxYear", "P6_Line19a_TotalIncome", "P6_Line19b_TaxYear", "P6_Line19b_TotalIncome",
                 "P6_Line19c_TaxYear", "P6_Line19c_TotalIncome"],
                ["P6_Line19a_TaxYear", "P6_Line19a_TotalIncome", "P6_Line19b_TaxYear", "P6_Line19b_TotalIncome",
                 "P6_Line19c_TaxYear", "P6_Line19c_TotalIncome"],
                notes={
                    "P6_Line19a_TaxYear": (
                        "Item 16.a despite the Line19 names: the most recent tax year counting from the signing date "
                        "(4 digits). Its transcript or return is required. Do not leave 16 blank."
                    ),
                    "P6_Line19a_TotalIncome": (
                        "Total income on the return (Form 1040 total income), 'zero' if it was zero, 'N/A' if not "
                        "required to file. Otherwise " + MONEY[0].lower() + MONEY[1:]
                    ),
                    "P6_Line19b_TaxYear": (
                        "Item 16.b. 'N/A' in both 16.b boxes when no second return is submitted (the instructions' "
                        "wording; the filing copy shows it, though Adobe treats the income box as a number)."
                    ),
                    "P6_Line19c_TaxYear": "Item 16.c. 'N/A' in both boxes when no third return is submitted.",
                },
            ),
            "assets": q(
                "Part 7, Items 1-10: Assets used to supplement income (sponsor's, household members', principal "
                "immigrant's, total)",
                ["P7_Line1_BalanceofAccounts", "P7_Line2_RealEstate", "P7_Line3_StocksBonds", "P7_Line4_Total",
                 "P7_Line5_TotalAssetsHouseholdMembers", "P7_Line6_BalanceofAccounts", "P7_Line7_RealEstate",
                 "P7_Line8_StocksBonds", "P7_Line9_Total", "P7_Line10_TotalValueAssets"],
                ["P7_Line10_TotalValueAssets"],
                allowed=FILLED_OR_NA,
                notes={
                    "P7_Line1_BalanceofAccounts": (
                        "Only when household income in Part 6 item 12 (or item 16) is below the I-864P figure for the "
                        "household size; otherwise not_applicable. Items 1-3 are the sponsor's assets. " + MONEY
                    ),
                    "P7_Line4_Total": "Item 4 = items 1-3. Adobe recalculates it; enter the exact sum.",
                    "P7_Line5_TotalAssetsHouseholdMembers": "Item 5: assets from every I-864A Part 4 item 6. " + MONEY,
                    "P7_Line6_BalanceofAccounts": "Items 6-8 are the principal immigrant's assets, only if sponsored "
                    "here. " + MONEY,
                    "P7_Line9_Total": "Item 9 = items 6-8. Adobe recalculates it; enter the exact sum.",
                    "P7_Line10_TotalValueAssets": (
                        "Item 10 = items 4, 5 and 9 (Adobe recalculates it). It must reach 5 times the shortfall "
                        "(3 times for a U.S. citizen's spouse or child 18 or older)."
                    ),
                },
            ),
            "sponsor_statement_language": q(
                "Part 8, Item 1.b: Language the interpreter used (the sponsor's 1.a/1.b choice is marked by hand)",
                ["P8_Line1b_language"],
                ["P8_Line1b_language"],
                allowed=FILLED_OR_NA,
                notes={
                    "P8_Line1b_language": (
                        "Only when an interpreter read the affidavit to the sponsor (maxlen about 31 characters); "
                        "otherwise not_applicable. The 1.a and 1.b boxes are P6_Line1_Checkbox, linked with Part 6 "
                        "'Employed' (see sponsor_employment): the sponsor marks 1.a or 1.b by hand at signing."
                    ),
                },
            ),
            "sponsor_statement_preparer": q(
                "Part 8, Item 2: At my request, the preparer named in Part 10 prepared this affidavit",
                ["P8_Line2_Checkbox", "P8_Line2_Attorney"],
                ["P8_Line2_Checkbox", "P8_Line2_Attorney"],
                notes={
                    "P8_Line2_Checkbox": "Select when the firm prepared the affidavit.",
                    "P8_Line2_Attorney": "The preparer's full name as in Part 10 item 1 (profile key attorney_name).",
                },
                choices={"P8_Line2_Checkbox": {"Prepared at my request by the preparer in Part 10": "Y"}},
            ),
            "sponsor_contact": q(
                "Part 8, Items 3-5: Sponsor's daytime phone, mobile phone, email",
                ["P8_Line3_DaytimeTelephoneNumber", "P8_Line4_MobileTelephoneNumber", "P7Line7_EmailAddress"],
                ["P8_Line3_DaytimeTelephoneNumber"],
                notes={
                    "P8_Line3_DaytimeTelephoneNumber": "Item 3. " + PHONE,
                    "P8_Line4_MobileTelephoneNumber": "Item 4, if any. " + PHONE,
                    "P7Line7_EmailAddress": "Item 5, the sponsor's email, if any, despite the P7 name (maxlen 38).",
                },
            ),
            "sponsor_signature": q(
                "Part 8, Item 6: Sponsor's signature and date",
                ["P8_Line9a_ApplicantSignature", "P7Line9b_DateofSignature"],
                allowed=SIGNATURE_STATUSES,
                notes={
                    "P8_Line9a_ApplicantSignature": "Item 6, signed in ink by the sponsor; never typed.",
                    "P7Line9b_DateofSignature": "Item 6 date, despite the P7 name; dated by the sponsor at signing.",
                },
            ),
            "interpreter_block": q(
                "Part 9, Items 1-5 and certification: Interpreter's name, business, phones, email, language",
                ["P9_Line1a_InterpretersFamilyName", "P9_Line1b_InterpretersGivenName",
                 "P8Line2_InterpretersBusinessName", "P9_Line4_InterpretersDaytimePhoneNumber[0]",
                 "P9_Line4_InterpretersDaytimePhoneNumber[1]", "P9_Line5_InterpretersEmailAddress", "P9_Language"],
                ["P9_Line1a_InterpretersFamilyName", "P9_Line1b_InterpretersGivenName",
                 "P9_Line4_InterpretersDaytimePhoneNumber[0]", "P9_Language"],
                allowed=FILLED_OR_NA,
                notes={
                    "P9_Line1a_InterpretersFamilyName": (
                        "Only when an interpreter was used; otherwise not_applicable. This edition has no interpreter "
                        "address boxes."
                    ),
                    "P8Line2_InterpretersBusinessName": "Item 2, despite the P8 name (maxlen 34).",
                    "P9_Line4_InterpretersDaytimePhoneNumber[0]": "Item 3, daytime phone. " + PHONE,
                    "P9_Line4_InterpretersDaytimePhoneNumber[1]": "Item 4, the MOBILE phone (second box of this name), "
                    "if any.",
                    "P9_Line5_InterpretersEmailAddress": "Item 5, if any (maxlen 38).",
                    "P9_Language": "The language in the certification; the same as Part 8 item 1.b (about 21 "
                    "characters fit).",
                },
            ),
            "interpreter_signature": q(
                "Part 9, Item 6: Interpreter's signature and date",
                ["P9_Line6a_InterpretersSignature", "P9_Line6b_DateofSignature"],
                allowed=OPTIONAL_SIGNATURE,
                notes={"P9_Line6a_InterpretersSignature": "Only with an interpreter; signed in ink."},
            ),
            "preparer_block": q(
                "Part 10, Items 1-5: Preparer's name, business, daytime phone, mobile phone, email",
                ["P10_Line1a_PreparersFamilyName", "P10_Line1b_PreparersGivenName", "P10_Line2_PreparersBusinessName",
                 "P10_Line4_PreparersDaytimePhoneNumber", "P10_Line5_PreparersFaxNumber",
                 "P10_Line6_PreparersEmailAddress"],
                ["P10_Line1a_PreparersFamilyName", "P10_Line1b_PreparersGivenName", "P10_Line2_PreparersBusinessName",
                 "P10_Line4_PreparersDaytimePhoneNumber", "P10_Line6_PreparersEmailAddress"],
                notes={
                    "P10_Line1a_PreparersFamilyName": (
                        "Profile key attorney_name (family name), as on the G-28. This edition has no preparer address "
                        "or attorney statement boxes."
                    ),
                    "P10_Line1b_PreparersGivenName": "Profile key attorney_name (given name).",
                    "P10_Line2_PreparersBusinessName": "Profile key firm_name (maxlen 34).",
                    "P10_Line4_PreparersDaytimePhoneNumber": "Item 3 despite the Line4 name. Profile key phone. " + PHONE,
                    "P10_Line5_PreparersFaxNumber": "Item 4, the preparer's MOBILE phone, despite the Fax name; if any.",
                    "P10_Line6_PreparersEmailAddress": "Item 5. Profile key email (maxlen 38).",
                },
            ),
            "preparer_signature": q(
                "Part 10, Item 6: Preparer's signature and date",
                ["P10_Line8a_PreparersSignature", "P10_Line8b_DateofSignature"],
                allowed=SIGNATURE_STATUSES,
                notes={"P10_Line8a_PreparersSignature": "Item 6 despite the Line8 names; signed in ink by the preparer."},
            ),
            "additional_information": additional_information(),
        }
    )
    return questions


SCHEMAS = {
    "i864_household_sponsor": {
        "kind": "i-864",
        "edition": EDITION,
        "field_list": FIELD_LIST,
        "description": (
            "Form I-864 for one sponsor: the petitioning sponsor, a joint or substitute sponsor, or a relative "
            "who filed (or 5% owner of the entity that filed) an I-140. One plan per sponsor."
        ),
        "notes": [
            "Edition 08/24/26. Field names follow an older part order: Part 2 (sponsor) boxes are P4_*, Part 3 "
            "(principal immigrant) P2_*, Part 4 (immigrants sponsored) P3_*; Part 5 item 1 is "
            "P3_Line28_TotalNumberofImmigrants and item 8 is Override; Part 6 items 8-11 are P6_Line3-P6_Line14 "
            "and items 16.a-16.c P6_Line19a-c; the sponsor's email and signature date are P7Line7 and P7Line9b. "
            "Use the field notes, not the names.",
            "Known form defect: Part 6 item 1 'Employed' and Part 8 items 1.a and 1.b are one checkbox group "
            "(P6_Line1_Checkbox, on-states ' Y', A, B). Check Employed if it applies, leave 1.a/1.b for the "
            "sponsor to mark by hand at signing, and add an attorney_action open item for that.",
            "Sponsor-type parts: item 12 military service is for petitioning sponsors only (not_applicable for "
            "joint and substitute sponsors); Part 4 family members, Part 6 items 8-14 and Part 7 assets are "
            "not_applicable when unused. A second joint sponsor covering family members alone answers Part 4 "
            "item 1 No.",
            "Adobe calculates Part 6 item 12 (items 7-11) and Part 7 items 4, 9 and 10, and shows Part 5 item 2 "
            "as a read-only 1. Enter the exact sums, digits only; the filing copy shows what the plan writes.",
            "Global fields share one value: the sponsor's name (P4_Line1a/1b/1c) and A-Number "
            "(P4_Line12_AlienNumber) also print in Part 11 items 1-2. Map only the base name.",
            "Unbound in the XFA template: the Part 4 family members' name and relationship boxes. fill binds "
            "any it fills, so Adobe shows them.",
            "The audit requires the basis, the sponsor's name, domicile, date of birth and U.S. mailing address "
            "with state and ZIP Code, the principal immigrant's name, date of birth and mailing address, and "
            "warns while Part 5 items 1 and 7, Part 6 item 12 or any of items 16.a-16.c is blank.",
        ],
        "required_questions": required_questions(),
    },
}

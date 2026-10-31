"""Question schema for Form I-864A, Contract Between Sponsor and Household Member.

Built against the 08/24/26 edition (uscis.gov/i-864a Edition Date panel and the PDF footer of the
form and its instructions, checked 2026-10-29). Field list: schemas/fields/I-864A.json; every box
of the form belongs to one question.

The household member's income and assets count toward the sponsor's I-864 (Part 6 items 8-11 and
13 there), so the facts must agree with the sponsor's I-864: the same intending immigrants, the
same relationship, and the same current income. The sponsor signs Part 5 and the household member
Part 6.

Boxes that mislead on this edition: the four signature boxes are one name,
Pt2Line6_ApplicantSignature [0] the sponsor (Part 5 item 10), [1] the household member (Part 6 item
7), [2] the interpreter, [3] the preparer, each with the same index of Pt2Line6_DateofSignature;
intending immigrant 4's A-Number box is P2_Line5_SSN; P5_SponsorName and Part9_Iamfluent[0] are the
sponsor's and the household member's names in the opening sentences of Parts 5 and 6, and
P5_IntendingMigrants and Part9_Iamfluent[1] the number of intending immigrants there. In Part 9,
Pt11Line5d_AdditionalInfo [2], [1] and [0] are the text of items 3, 4 and 5. The sponsor's
statement (Part 5 items 5.a, 5.b and 6) is one checkbox group on this edition, so item 6 (a
preparer) can't be checked together with 5.a or 5.b: check 5.a or 5.b, name the preparer in
P5Line5c_language anyway, and have the sponsor mark item 6 by hand at signing.
"""
from __future__ import annotations

from typing import Any

from _common import DATE, FILLED, FILLED_OR_NA, NOT_APPLICABLE, SIGNATURE_STATUSES, UNIT, YES_NO, q

STATE = "U.S. address only: 2-letter state code (drop-down)."
ZIP = "U.S. address only: 5-digit ZIP Code."
MONEY = "Digits only, no '$' or commas."
PHONE = "Digits only (maxlen 10)."
SIGNATURE = "Leave blank: the signer signs the printed form in ink (it can't be signed electronically)."


def address(label: str, prefix: str, *, in_care_of: bool, allowed: list[str] | None = None) -> dict[str, Any]:
    names = ([f"{prefix}_InCareOfName"] if in_care_of else []) + [
        f"{prefix}_StreetNumberName", f"{prefix}_Unit", f"{prefix}_AptSteFlrNumber", f"{prefix}_CityOrTown",
        f"{prefix}_State", f"{prefix}_ZipCode", f"{prefix}_Province", f"{prefix}_PostalCode", f"{prefix}_Country",
    ]
    return q(
        label, names, [f"{prefix}_StreetNumberName", f"{prefix}_CityOrTown", f"{prefix}_Country"], allowed=allowed,
        notes={f"{prefix}_State": STATE, f"{prefix}_ZipCode": ZIP,
               f"{prefix}_Country": "The country, USA for a U.S. address."},
        choices={f"{prefix}_Unit": UNIT},
    )


def immigrant(number: int) -> dict[str, Any]:
    if number == 4:
        names = ["Part2Line4a_FamilyName", "Part2Line4a_GivenName", "Part2Line4a_MiddleName"]
        dob, a_number, account = "P2_Line8_DateOfBirth", "P2_Line5_SSN", "P2_Line6_USCISELISAcctNumber"
    else:
        names = [f"P5_Line{number}a_FamilyName", f"P5_Line{number}b_GivenName", f"P5_Line{number}c_MiddleName"]
        dob, a_number, account = (f"P5_Line{number}d_DateOfBirth", f"P5_Line{number}e_ANumber",
                                  f"P5_Line{number}f_USCISAcctNumber")
    notes = {dob: DATE, a_number: "If any: 9 digits, no 'A'.", account: "If any: 12 digits."}
    if number == 4:
        notes[a_number] = "Immigrant 4's A-NUMBER, despite the SSN name. If any: 9 digits, no 'A'."
    return q(
        f"Part 5, Item {number}: Intending immigrant {number} (name, date of birth, A-Number and online account, if any)",
        [*names, dob, a_number, account],
        [names[0], names[1], dob],
        allowed=[FILLED] if number == 1 else FILLED_OR_NA,
        notes=notes,
    )


def contract() -> dict[str, Any]:
    questions: dict[str, dict[str, Any]] = {
        "attorney_box": q(
            "Page 1 attorney box: G-28 attached, bar number, attorney's USCIS online account number",
            ["G28-CheckBox1", "AttorneyStateBarNumber", "USCISOnlineAccountNumber"],
            ["G28-CheckBox1", "AttorneyStateBarNumber"],
            allowed=FILLED_OR_NA,
            notes={"AttorneyStateBarNumber": "Profile key bar_number; only with a G-28 for the household member.",
                   "USCISOnlineAccountNumber": "The attorney's account number, if any. Blank when the profile says "
                   "has_uscis_online_account \"no\"."},
            choices={"G28-CheckBox1": {"G-28 or G-28I attached": "1"}},
        ),
        "member_name": q(
            "Part 1, Item 1: Household member's full name",
            ["P1_Line1a_FamilyName", "P1_Line1b_GivenName", "P1_Line1c_MiddleName"],
            ["P1_Line1a_FamilyName", "P1_Line1b_GivenName"],
        ),
        "member_mailing_address": address("Part 1, Item 2: Household member's mailing address", "P1_Line2", in_care_of=True),
        "mailing_same_as_physical": q(
            "Part 1, Item 3: Is the mailing address the same as the physical address?",
            ["P1_Line3_CB"], ["P1_Line3_CB"], choices={"P1_Line3_CB": YES_NO},
        ),
        "member_physical_address": address(
            "Part 1, Item 4: Household member's physical address (only if item 3 is No)", "P1_Line4", in_care_of=False,
            allowed=FILLED_OR_NA,
        ),
        "member_other_information": q(
            "Part 1, Items 5-9: Date and country of birth, SSN, A-Number and USCIS online account (if any)",
            ["P1_Line5_DateOfBirth", "P1_Line6_CountryofBirth", "P1_Line7_SSN", "P1_Line8_AlienNumber",
             "P1_Line9_USCISOnlineAcctNumber"],
            ["P1_Line5_DateOfBirth", "P1_Line6_CountryofBirth"],
            notes={"P1_Line5_DateOfBirth": DATE, "P1_Line7_SSN": "If any: 9 digits.",
                   "P1_Line8_AlienNumber": "If any: 9 digits, no 'A' (global, also on page 8)."},
        ),
        "relationship_to_sponsor": q(
            "Part 2: The household member is the intending immigrant and the sponsor's spouse (1), the intending immigrant "
            "and a household member (2), or not the intending immigrant (3) and related to the sponsor as",
            ["P2_Line1-3_Checkbox", "P2_Line3_A_Relationship", "P2_Line3_A_Other"],
            ["P2_Line1-3_Checkbox"],
            notes={"P2_Line3_A_Relationship": "Only with item 3: how the member is related to the sponsor.",
                   "P2_Line3_A_Other": "Only with 'Other dependent': specify."},
            choices={
                "P2_Line1-3_Checkbox": {"1 Intending immigrant and the sponsor's spouse": "A",
                                        "2 Intending immigrant and a member of the sponsor's household": "B",
                                        "3 Not the intending immigrant; the sponsor's household member": "C"},
                "P2_Line3_A_Relationship": {"Spouse": "1", "Son or daughter (at least 18)": "2", "Parent": "3",
                                            "Brother or sister": "4", "Other dependent": "5"},
            },
        ),
        "employment_and_income": q(
            "Part 3, Items 1-7: Employed (occupation, employers), self-employed, retired or unemployed; current individual "
            "annual income",
            ["P3_Line1_Employment", "P3_Line1a_Employed", "P3_Line2_Employed", "P3_Line3_Employed", "P3_Line4_Employment",
             "P3_Line4a_SelfEmployedDescription", "P3_Line5_Employment", "P3_Line5a_EmployedDate", "P3_Line6_Employment",
             "P3_Line6a_EmployedDate", "P3_Line2_CurrentIncome"],
            ["P3_Line2_CurrentIncome"],
            notes={
                "P3_Line1_Employment": "Items 1, 4, 5 and 6 are one checkbox group: employed, self-employed, retired or "
                "unemployed. The audit asks for one.",
                "P3_Line1a_Employed": "Item 1, the occupation (unbound; fill binds it).",
                "P3_Line2_Employed": "Item 2, employer 1.",
                "P3_Line5a_EmployedDate": "Retired since. " + DATE,
                "P3_Line6a_EmployedDate": "Unemployed since. " + DATE,
                "P3_Line2_CurrentIncome": "Item 7, current individual annual income (the figure the sponsor's I-864 Part 6 "
                "lists for this member). " + MONEY,
            },
            choices={"P3_Line1_Employment": {"Employed": "A"}, "P3_Line4_Employment": {"Self-employed": "B"},
                     "P3_Line5_Employment": {"Retired": "C"}, "P3_Line6_Employment": {"Unemployed": "D"}},
        ),
        "tax_returns": q(
            "Part 4, Items 1-2: Filed federal tax returns for the three most recent years; total income for each",
            ["P4_Line1_CB", "P4_Line2a_TaxYear", "P4_Line2a_TotalIncome", "P4_Line2b_TaxYear", "P4_Line2b_TotalIncome",
             "P4_Line2c_TaxYear", "P4_Line2c_TotalIncome"],
            ["P4_Line1_CB", "P4_Line2a_TaxYear", "P4_Line2a_TotalIncome"],
            notes={"P4_Line1_CB": "Attach the most recent year's return or transcript.",
                   "P4_Line2a_TaxYear": "Most recent tax year, 4 digits.", "P4_Line2a_TotalIncome": MONEY},
            choices={"P4_Line1_CB": YES_NO},
        ),
        "assets": q(
            "Part 4, Items 3-6: Assets (only if needed): cash and accounts, real estate net value, other assets, total",
            ["P4_Line3_Assets", "P4_Line4_Assets", "P4_Line5_Assets", "P4_Line6_TotalAssets"],
            ["P4_Line6_TotalAssets"],
            allowed=FILLED_OR_NA,
            notes={"P4_Line6_TotalAssets": "Item 6: the sum of items 3-5. " + MONEY},
        ),
        "sponsor_promise": q(
            "Part 5, opening: the sponsor's name and the number of intending immigrants",
            ["P5_SponsorName", "P5_IntendingMigrants"],
            ["P5_SponsorName", "P5_IntendingMigrants"],
            notes={"P5_SponsorName": "The SPONSOR's full name, despite its tooltip ('I, THE SPONSOR, ...').",
                   "P5_IntendingMigrants": "How many intending immigrants (items 1-4), as a number."},
        ),
        "sponsor_statement": q(
            "Part 5, Items 5.a-6: Sponsor reads English, or the interpreter read it (language); a preparer prepared it (name)",
            ["P5Line5_Checkbox", "P5Line5b_language", "P5Line5c_language"],
            ["P5Line5_Checkbox"],
            notes={
                "P5Line5_Checkbox": "Form defect: 5.a, 5.b and 6 are one checkbox group. Check 5.a or 5.b; item 6 is marked "
                "by hand at signing when a preparer prepared it (add an attorney_action open item for that).",
                "P5Line5b_language": "Item 5.b, the language.",
                "P5Line5c_language": "Item 6, the PREPARER's name, despite the name.",
            },
            choices={"P5Line5_Checkbox": {"5.a Reads English": "A", "5.b The interpreter read it": "B",
                                          "6 A preparer prepared it": "C"}},
        ),
        "sponsor_contact": q(
            "Part 5, Items 7-9: Sponsor's daytime phone, mobile phone (if any), email (if any)",
            ["Pt2Line3_DaytimePhone", "Pt2Line4_Mobilephone", "Pt2Line5_EmailAddress"],
            ["Pt2Line3_DaytimePhone"],
            notes={"Pt2Line3_DaytimePhone": "The SPONSOR's, despite the Pt2 name. " + PHONE},
        ),
        "sponsor_signature": q(
            "Part 5, Item 10: Sponsor's signature and date",
            ["Pt2Line6_ApplicantSignature[0]", "Pt2Line6_DateofSignature[0]"],
            allowed=SIGNATURE_STATUSES,
            notes={"Pt2Line6_ApplicantSignature[0]": "Box [0] is the sponsor's. " + SIGNATURE},
        ),
        "member_promise": q(
            "Part 6, opening: the household member's name and the number of intending immigrants",
            ["Part9_Iamfluent[0]", "Part9_Iamfluent[1]"],
            ["Part9_Iamfluent[0]", "Part9_Iamfluent[1]"],
            notes={"Part9_Iamfluent[0]": "The HOUSEHOLD MEMBER's full name ('I, THE HOUSEHOLD MEMBER, ...').",
                   "Part9_Iamfluent[1]": "How many intending immigrants, as a number."},
        ),
        "member_statement": q(
            "Part 6, Items 1.a-2: Household member reads English, or the interpreter read it (language); a preparer "
            "prepared it (name)",
            ["Part6_Line1_Checkbox", "P6Line1b_language", "Part6_Line2_Checkbox", "P6Line2_Attorney"],
            ["Part6_Line1_Checkbox"],
            notes={"P6Line1b_language": "Item 1.b, the language.", "P6Line2_Attorney": "Item 2, the preparer's name."},
            choices={"Part6_Line1_Checkbox": {"1.a Reads English": "A", "1.b The interpreter read it": "B"},
                     "Part6_Line2_Checkbox": {"2 A preparer prepared it": "Y"}},
        ),
        "member_contact": q(
            "Part 6, Items 3-5: Household member's daytime phone, mobile phone (if any), email (if any)",
            ["P7Line5_DaytimeTelephoneNumber", "P7Line6_MobileTelephoneNumber", "P7Line7_EmailAddress"],
            ["P7Line5_DaytimeTelephoneNumber"],
            notes={"P7Line5_DaytimeTelephoneNumber": "Part 6 item 3, despite the P7 name. " + PHONE},
        ),
        "member_signature": q(
            "Part 6, Items 6-7: Household member's printed name, signature and date",
            ["P7Line6a_EmailAddress", "Pt2Line6_ApplicantSignature[1]", "Pt2Line6_DateofSignature[1]"],
            allowed=SIGNATURE_STATUSES,
            notes={"P7Line6a_EmailAddress": "Item 6, the household member's PRINTED NAME, despite the name.",
                   "Pt2Line6_ApplicantSignature[1]": "Box [1] is the household member's. " + SIGNATURE},
        ),
        "interpreter_block": q(
            "Part 7, Items 1-5 and certification: Interpreter's name, business, phones, email, language",
            ["P8Line1a_InterpretersFamilyName", "P8Line1b_InterpretersGivenName", "P8Line2_InterpretersBusinessName",
             "P8Line4_InterpretersDaytimePhoneNumber[0]", "P8Line4_InterpretersDaytimePhoneNumber[1]",
             "P8Line5_InterpretersEmailAddress", "P8_Language"],
            ["P8Line1a_InterpretersFamilyName", "P8Line1b_InterpretersGivenName",
             "P8Line4_InterpretersDaytimePhoneNumber[0]", "P8_Language"],
            allowed=FILLED_OR_NA,
            notes={"P8Line4_InterpretersDaytimePhoneNumber[1]": "Item 4, the interpreter's MOBILE (box [1])."},
        ),
        "interpreter_signature": q(
            "Part 7, Item 6: Interpreter's signature and date",
            ["Pt2Line6_ApplicantSignature[2]", "Pt2Line6_DateofSignature[2]"],
            allowed=[NOT_APPLICABLE, *SIGNATURE_STATUSES],
            notes={"Pt2Line6_ApplicantSignature[2]": "Box [2] is the interpreter's. " + SIGNATURE},
        ),
        "preparer_block": q(
            "Part 8, Items 1-5: Preparer's name, business, phones, email (from the attorney profile)",
            ["P9Line1a_PreparersFamilyName", "P9Line1b_PreparersGivenName", "P9Line2_PreparersBusinessName",
             "P9Line4_PreparersDaytimePhoneNumber", "P9Line5_PreparersFaxNumber", "P9Line6_PreparersEmailAddress"],
            ["P9Line1a_PreparersFamilyName", "P9Line1b_PreparersGivenName", "P9Line4_PreparersDaytimePhoneNumber"],
            allowed=FILLED_OR_NA,
            notes={"P9Line5_PreparersFaxNumber": "Item 4, the preparer's MOBILE, despite the name.",
                   "P9Line4_PreparersDaytimePhoneNumber": "Profile key phone. " + PHONE},
        ),
        "preparer_signature": q(
            "Part 8, Item 6: Preparer's signature and date",
            ["Pt2Line6_ApplicantSignature[3]", "Pt2Line6_DateofSignature[3]"],
            allowed=[NOT_APPLICABLE, *SIGNATURE_STATUSES],
            notes={"Pt2Line6_ApplicantSignature[3]": "Box [3] is the preparer's. " + SIGNATURE},
        ),
        "additional_information": q(
            "Part 9: Name and A-Number at the top, and items 3-6 (page, part, item and text)",
            ["Pt1Line1a_FamilyName", "Pt1Line1b_GivenName", "Pt1Line1c_MiddleName", "Pt1Line3e_AlienNumber",
             "Pt11Line3a_PageNumber", "Pt11Line3b_PartNumber", "Pt11Line3c_ItemNumber", "Pt11Line5d_AdditionalInfo[2]",
             "Pt11Line4a_PageNumber", "Pt11Line4b_PartNumber", "Pt11Line4c_ItemNumber", "Pt11Line5d_AdditionalInfo[1]",
             "Pt11Line5a_PageNumber", "Pt11Line5b_PartNumber", "Pt11Line5c_ItemNumber", "Pt11Line5d_AdditionalInfo[0]",
             "Pt11Line6a_PageNumber", "Pt11Line6b_PartNumber", "Pt11Line6c_ItemNumber", "Pt11Line6d_AdditionalInfo"],
            ["Pt1Line1a_FamilyName", "Pt1Line1b_GivenName", "Pt11Line3a_PageNumber", "Pt11Line3b_PartNumber",
             "Pt11Line3c_ItemNumber", "Pt11Line5d_AdditionalInfo[2]"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt1Line1a_FamilyName": "The household member's name again: these header boxes are not linked to Part 1.",
                "Pt11Line5d_AdditionalInfo[2]": "Item 3's text is box [2]; item 4's is [1]; item 5's is [0].",
            },
        ),
    }
    for number in range(1, 5):
        questions[f"intending_immigrant_{number}"] = immigrant(number)
    return {
        "kind": "i-864a",
        "edition": "08/24/26",
        "field_list": "I-864A.json",
        "description": (
            "Form I-864A for one household member whose income or assets the sponsor's I-864 counts (or the intending "
            "immigrant spouse or household member)."
        ),
        "notes": [
            "The intending immigrants, the relationship and the current income must agree with the sponsor's I-864 (Part 6 "
            "items 8-13 there).",
            "Both the sponsor (Part 5) and the household member (Part 6) sign in ink.",
        ],
        "required_questions": questions,
    }


SCHEMAS = {"i864a_household_member": contract()}

"""Question schema for Form I-140, Immigrant Petition for Alien Workers.

Built against the 06/07/24 edition (uscis.gov/i-140 Edition Date panel and the PDF footer of the
form and its instructions, checked 2026-10-29). Field list: schemas/fields/I-140.json; every box
of the form belongs to one question except Button1, the ZIP Code lookup push button.

The petitioner is usually the employer: a company fills Part 1 item 2 and the EIN; an individual
(or a self-petitioner, EB-1A or NIW) fills items 1.a-1.c and the SSN. Most yes/no questions on
this edition are two separate checkboxes (Line5_Yes and Line5_No, say): check exactly one, and
the audit says when both or neither is checked.

Repeated rows that mislead: Part 7's persons 2-6 share box names with an index, but not in the
same order for every box. The names and dates of birth go in order ([0] person 2 ... [4] person
6); the country of birth and the relationship go [0] person 2, [1] person 3, [2] person 5,
[3] person 6, [4] person 4 (read from where each box sits). In Part 11, items 6 and 7 are
Pt9Line6*: the page, part and item boxes are [1] for item 6 and [0] for item 7, while the text
boxes are [0] for item 6 and [1] for item 7. The field_notes repeat this where it matters.
"""
from __future__ import annotations

from typing import Any

from _common import DATE, FILLED, FILLED_OR_NA, FOREIGN_ONLY, MANUAL_REVIEW, NOT_APPLICABLE, PENDING_SIGNATURE, UNIT, q

STATE = "U.S. address only: 2-letter state code (drop-down)."
ZIP = "U.S. address only: 5-digit ZIP Code."
PHONE = "Digits only (maxlen 10)."
MONEY = "A number in digits, with a period before any cents and no '$' or commas: 2500000 or 2500000.50."
WHOLE_DOLLARS = "Whole dollars in digits only, no '$' or commas: 85000 (the form adds the commas)."
WAGE = (
    "A number, with a period before any cents and no '$' or commas: 45.67 an hour, or 150000 a year (the form "
    "shows 150,000.00). Never drop the period: 4567 would read $4,567.00."
)
SIGNATURE = "Leave blank: the signer signs the printed form in ink."
PAIR = "Two separate boxes: check exactly one (the yes box takes 'Y', the no box 'N')."


def pair(yes: str, no: str) -> dict[str, dict[str, str]]:
    return {yes: {"Yes": "Y"}, no: {"No": "N"}}


def yes_no(label: str, yes: str, no: str, *, allowed: list[str] | None = None, note: str = "") -> dict[str, Any]:
    return q(label, [yes, no], allowed=allowed, notes={yes: (note + " " + PAIR).strip()}, choices=pair(yes, no))


# Part 7 persons 2-6: (item of the name, name index, date-of-birth index, country index, relationship index,
# adjustment item, visa item).
PERSONS = [
    (7, 0, 0, 0, 0, 11, 12),
    (13, 1, 1, 1, 1, 17, 18),
    (19, 2, 2, 4, 4, 23, 24),
    (25, 3, 3, 2, 2, 29, 30),
    (31, 4, 4, 3, 3, 35, 36),
]


def person(number: int) -> dict[str, Any]:
    if number == 1:
        names = ["Line1a_Person1FamilyName", "Line1b_Person1GivenName", "Line1c_Person1MiddleName"]
        dob, country, relation, adjust, visa, item = (
            "Line1d_Person1DateOfBirth", "Line1e_CountryOfBirth", "Line1f_Relationship", 5, 6, 1,
        )
    else:
        item, n, d, c, r, adjust, visa = PERSONS[number - 2]
        names = [f"Line2a_Person2FamilyName[{n}]", f"Line2b_Person2GivenName[{n}]", f"Line2c_Person2MiddleName[{n}]"]
        dob, country, relation = f"Line2d_DateOfBirth[{d}]", f"Line2e_CountryOfBirth[{c}]", f"Line2f_Relationship[{r}]"
    yes_a, no_a = f"Pt7ItemNumber{adjust}_CheckboxYes", f"Pt7ItemNumber{adjust}_CheckboxNo"
    yes_v, no_v = f"Pt7ItemNumber{visa}_CheckboxYes", f"Pt7ItemNumber{visa}_CheckboxNo"
    return q(
        f"Part 7, Person {number} (items {item}-{visa}): spouse or child of the beneficiary; name, date and country "
        "of birth, relationship, applying for adjustment, applying for a visa abroad",
        [*names, dob, country, relation, yes_a, no_a, yes_v, no_v],
        [names[0], names[1], dob, country, relation],
        allowed=FILLED_OR_NA,
        notes={
            names[0]: "Unbound in the XFA template (fill binds it).",
            dob: DATE,
            country: "Country of birth." + ("" if number == 1 else " The index of this row's country box is not the name's."),
            relation: "Relationship to the beneficiary (Spouse, Son, Daughter); maxlen 28.",
            yes_a: f"Item {adjust}, applying for adjustment of status. " + PAIR,
            yes_v: f"Item {visa}, applying for a visa abroad. " + PAIR,
        },
        choices={**pair(yes_a, no_a), **pair(yes_v, no_v)},
    )


def additional_information() -> dict[str, Any]:
    rows = [(3, "Pt9Line3a_PageNumber", "Pt9Line3b_PartNumber", "Pt9Line3c_ItemNumber", "Pt9Line3d_AdditionalInfo"),
            (4, "Pt9Line4a_PageNumber", "Pt9Line4b_PartNumber", "Pt9Line4c_ItemNumber", "Pt9Line4d_AdditionalInfo"),
            (5, "Pt9Line5a_PageNumber", "Pt9Line5b_PartNumber", "Pt9Line5c_ItemNumber", "Pt9Line5d_AdditionalInfo"),
            (6, "Pt9Line6a_PageNumber[1]", "Pt9Line6b_PartNumber[1]", "Pt9Line6c_ItemNumber[1]", "Pt9Line6d_AdditionalInfo[0]"),
            (7, "Pt9Line6a_PageNumber[0]", "Pt9Line6b_PartNumber[0]", "Pt9Line6c_ItemNumber[0]", "Pt9Line6d_AdditionalInfo[1]")]
    return q(
        "Part 11, Items 3-7: Additional information (page, part, item and text, five entries)",
        [name for row in rows for name in row[1:]],
        list(rows[0][1:]),
        allowed=FILLED_OR_NA,
        notes={
            "Pt9Line3a_PageNumber": "Page, part and item boxes are unbound in the XFA template (fill binds them).",
            "Pt9Line6a_PageNumber[1]": "Item 6's page box is index [1]; its text box is Pt9Line6d_AdditionalInfo[0].",
            "Pt9Line6a_PageNumber[0]": "Item 7's page box is index [0]; its text box is Pt9Line6d_AdditionalInfo[1].",
            "Pt9Line3d_AdditionalInfo": "The box doesn't wrap: break long text into lines that fit.",
        },
    )


def worker_petition() -> dict[str, Any]:
    questions: dict[str, dict[str, Any]] = {
        "attorney_box": q(
            "Page 1 attorney box: G-28 attached, attorney's bar number and USCIS online account number",
            ["G28CheckBox", "attyStateBarNumber", "attyUSCISOnlineNum"],
            ["G28CheckBox", "attyStateBarNumber"],
            allowed=FILLED_OR_NA,
            notes={
                "attyStateBarNumber": "Profile key bar_number (maxlen 15).",
                "attyUSCISOnlineNum": "The attorney's account number, if the profile has one (12 digits). Blank when the "
                "profile says has_uscis_online_account \"no\".",
            },
            choices={"G28CheckBox": {"G-28 or G-28I attached": "Y"}},
        ),
        "petitioner_name": q(
            "Part 1, Items 1.a-2: Petitioner's name (an individual, items 1.a-1.c) or company or organization name (item 2)",
            ["Pt1Line1a_FamilyName", "Pt1Line1b_GivenName", "Pt1Line1c_MiddleName", "Line2_CompanyName"],
            notes={
                "Pt1Line1a_FamilyName": "Only when an individual files (a self-petitioner, say); global, also on page 8.",
                "Line2_CompanyName": "The employer's legal name (maxlen 34). The audit asks for this or the individual's name.",
            },
        ),
        "petitioner_mailing_address": q(
            "Part 1, Items 3.a-3.i: Petitioner's mailing address",
            ["Line6a_InCareofName", "Line6b_StreetNumberName", "Line6c_Unit", "Line6c_AptSteFlrNumber", "Line6d_CityOrTown",
             "Line6e_State", "Line6f_ZipCode", "Line6h_Province", "Line6g_PostalCode", "Line6i_Country"],
            ["Line6b_StreetNumberName", "Line6d_CityOrTown", "Line6i_Country"],
            notes={"Line6e_State": STATE, "Line6f_ZipCode": ZIP, "Line6h_Province": "Item 3.g. " + FOREIGN_ONLY,
                   "Line6g_PostalCode": "Item 3.h. " + FOREIGN_ONLY},
            choices={"Line6c_Unit": UNIT},
        ),
        "petitioner_numbers_and_size": q(
            "Part 1, Items 4-8: EIN, nonprofit or governmental research organization, 25 or fewer full-time employees, "
            "SSN and USCIS online account number",
            ["Pt1Line3_TaxNumber", "P1_Line5_Checkbox", "P1_Line6_Checkbox", "Line7_SSN", "Pt1Line8_USCISOnlineActNumber"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt1Line3_TaxNumber": "Item 4, the IRS EIN: 9 digits, no dashes (global, also on page 8). A company files "
                "with one; the audit asks for it with a company name.",
                "P1_Line5_Checkbox": "Item 5; it and item 6 set the Asylum Program Fee (G-1055). Every petitioner answers both "
                "or USCIS rejects the petition; a self-petitioner answers No here and Yes to item 6 (uscis.gov/i-140 "
                "filing tips, updated 07/24/2026).",
                "Line7_SSN": "Item 7, an individual petitioner's SSN, if any.",
                "Pt1Line8_USCISOnlineActNumber": "Item 8, the petitioner's own account, if any.",
            },
            choices={"P1_Line5_Checkbox": {"Yes": "Y", "No": "N"}, "P1_Line6_Checkbox": {"Yes": "Y", "No": "N"}},
        ),
        "petition_type": q(
            "Part 2, Item 1: Petition type (select only one)",
            ["prt2PetitionType"],
            ["prt2PetitionType"],
            choices={
                "prt2PetitionType": {
                    "1.a Alien of extraordinary ability": "a",
                    "1.b Outstanding professor or researcher": "b",
                    "1.c Multinational executive or manager": "c",
                    "1.d Advanced degree professional or exceptional ability, not seeking an NIW": "d",
                    "1.e Professional (bachelor's degree or foreign equivalent)": "e",
                    "1.f Skilled worker (at least two years of training or experience)": "f",
                    "1.g Any other worker (less than two years)": "g",
                    "1.h National interest waiver (advanced degree or exceptional ability)": "h",
                }
            },
        ),
        "amend_or_schedule_a": q(
            "Part 2, Item 2: To amend a previously filed petition (with its receipt number), or for the Schedule A, "
            "Group I or II designation",
            ["Line2_Petition", "Line2a_ReceiptNumber"],
            ["Line2_Petition"],
            allowed=FILLED_OR_NA,
            notes={"Line2a_ReceiptNumber": "Only to amend: the earlier petition's receipt number (3 letters, 10 digits)."},
            choices={"Line2_Petition": {"To amend a previously filed petition": "A", "Schedule A, Group I or II": "S"}},
        ),
        "beneficiary_name": q(
            "Part 3, Items 1.a-1.c: Beneficiary's full name",
            ["Pt3Line1a_FamilyName", "Pt3Line1b_GivenName", "Pt3Line1c_MiddleName"],
            ["Pt3Line1a_FamilyName", "Pt3Line1b_GivenName"],
        ),
        "beneficiary_mailing_address": q(
            "Part 3, Items 2.a-2.i: Beneficiary's mailing address",
            ["Line2a_InCareofName[0]", "Line2b_StreetNumberName", "Line2c_Unit", "Line2c_AptSteFlrNumber", "Line2d_CityOrTown",
             "Line2e_State", "Line2f_ZipCode", "Line2h_Province", "Line2g_PostalCode", "Line2i_Country"],
            ["Line2b_StreetNumberName", "Line2d_CityOrTown", "Line2i_Country"],
            notes={"Line2a_InCareofName[0]": "Item 2.a, in care of (box [1] is Part 4 item 5.a).", "Line2e_State": STATE,
                   "Line2f_ZipCode": ZIP, "Line2h_Province": "Item 2.g. " + FOREIGN_ONLY,
                   "Line2g_PostalCode": "Item 2.h. " + FOREIGN_ONLY},
            choices={"Line2c_Unit": UNIT},
        ),
        "beneficiary_other_information": q(
            "Part 3, Items 3-9: Date and place of birth, country of citizenship, A-Number and SSN (if any)",
            ["Line5_DateOfBirth", "Line6_CityTownOfBirth", "Line7_StateProvinceOfBirth", "Line8_Country", "Line9_Country",
             "Pt3Line8_AlienNumber", "Line12_SSN"],
            ["Line5_DateOfBirth", "Line6_CityTownOfBirth", "Line8_Country", "Line9_Country"],
            notes={
                "Line5_DateOfBirth": "Item 3. " + DATE,
                "Line6_CityTownOfBirth": "Item 4 (unbound; fill binds it).",
                "Line8_Country": "Item 6, country of BIRTH.",
                "Line9_Country": "Item 7, country of citizenship or nationality.",
                "Pt3Line8_AlienNumber": "Item 8, if any: 9 digits, no 'A'.",
                "Line12_SSN": "Item 9, if any: 9 digits.",
            },
        ),
        "beneficiary_in_us": q(
            "Part 3, Items 10-15: If the beneficiary is in the United States: last arrival, I-94, status, passport or "
            "travel document",
            ["Line13_DateOArrival", "Line14a_ArrivalDeparture", "Line14e_ExpDate[1]", "Line15_CurrentNon", "Line14b_Passport",
             "Line14c_TravelDoc", "Line14d_CountryOfIssuance", "Line14e_ExpDate[0]"],
            ["Line13_DateOArrival", "Line15_CurrentNon"],
            allowed=FILLED_OR_NA,
            notes={
                "Line13_DateOArrival": "Item 10, date of last arrival. " + DATE,
                "Line14a_ArrivalDeparture": "Item 11.a, I-94 number (11 characters).",
                "Line14e_ExpDate[1]": "Item 11.b, the stay's expiration on the I-94 (" + DATE[:-1] + " or D/S).",
                "Line15_CurrentNon": "Item 11.c, current status as the I-94 shows it (class of admission, or paroled).",
                "Line14e_ExpDate[0]": "Item 15, passport or travel document expiration. " + DATE,
            },
        ),
        "processing": q(
            "Part 4, Items 1.a-2.b: Visa abroad at a U.S. Embassy or Consulate (city, country), or adjustment of status in "
            "the United States; the current or last country of residence",
            ["Line1a_Visa", "Line1a_CityorTown", "Line1a_Country", "Line1b_Status", "Line1b_Country"],
            ["Line1b_Country"],
            notes={
                "Line1a_Visa": "Item 1.a; check it or Line1b_Status (item 2.a), not both. With 1.a, give the post's city and country.",
                "Line1b_Country": "Item 2.b: current country of residence, or the last country of permanent residence abroad.",
            },
            choices={"Line1a_Visa": {"Visa abroad": "1a"}, "Line1b_Status": {"Adjustment of status": "1b"}},
        ),
        "foreign_address": q(
            "Part 4, Items 3.a-3.f: The beneficiary's foreign address, when Part 3 gives a U.S. one",
            ["Line2a_StreetNumberName", "Line2b_Unit", "Line2b_AptSteFlrNumber", "Line2c_CityOrTown", "Line2e_Province",
             "Line2d_PostalCode", "Line2f_Country"],
            ["Line2a_StreetNumberName", "Line2c_CityOrTown", "Line2f_Country"],
            allowed=FILLED_OR_NA,
            notes={"Line2e_Province": "Item 3.d.", "Line2d_PostalCode": "Item 3.e."},
            choices={"Line2b_Unit": UNIT},
        ),
        "native_alphabet": q(
            "Part 4, Items 4.a-5.g: Name and foreign address in the native alphabet (only if it isn't Roman letters)",
            ["Line3a_FamilyName2", "Line3b_GivenName2", "Line3c_MiddleName2", "Line2a_InCareofName[1]",
             "Line3d_StreetNumberName", "Line3e_Unit", "Line3e_AptSteFlrNumber", "Line3f_CityOrTown", "Line3h_Province",
             "Line3g_PostalCode", "Line3i_Country"],
            ["Line3a_FamilyName2", "Line3b_GivenName2", "Line3d_StreetNumberName", "Line3f_CityOrTown", "Line3i_Country"],
            allowed=[NOT_APPLICABLE, FILLED, MANUAL_REVIEW],
            notes={
                "Line3a_FamilyName2": (
                    "Non-Roman script doesn't render on the filing copy. Leave these boxes blank, mark the question "
                    "manual_review with an open item, and have them handwritten."
                ),
                "Line2a_InCareofName[1]": "Item 5.a, in care of, in the native alphabet.",
                "Line3h_Province": "Item 5.e.",
                "Line3g_PostalCode": "Item 5.f.",
            },
            choices={"Line3e_Unit": UNIT},
        ),
        "other_filings": q(
            "Part 4, Items 6.a-6.b: Other petitions or applications filed with this I-140, and which",
            ["Line4_Yes", "Line4_No", "Line4_Form485", "Line4_Form131", "Line4_Form765", "Line4_OtherAttach"],
            notes={"Line4_Yes": "Item 6.a. " + PAIR, "Line4_Form485": "Item 6.b, only with Yes: every form filed with it.",
                   "Line4_OtherAttach": "Other: explain in Part 11."},
            choices={**pair("Line4_Yes", "Line4_No"), "Line4_Form485": {"Form I-485": "Y"},
                     "Line4_Form131": {"Form I-131": "Y"}, "Line4_Form765": {"Form I-765": "Y"},
                     "Line4_OtherAttach": {"Other": "Y"}},
        ),
        "removal_proceedings": yes_no("Part 4, Item 7: Is the beneficiary in removal proceedings?", "Line5_Yes", "Line5_No",
                                      note="A Yes needs the case details in Part 11."),
        "prior_immigrant_petitions": yes_no(
            "Part 4, Item 8: Has any immigrant visa petition ever been filed by or for the beneficiary?", "Line6_Yes", "Line6_No",
            note="A Yes needs the case details in Part 11.",
        ),
        "labor_certification_elsewhere": yes_no("Part 4, Item 9: Filing without the original labor certification because it was submitted with another I-140?",
                                                "Line7_Yes", "Line7_No"),
        "duplicate_labor_certification": yes_no(
            "Part 4, Item 10: If so, asking USCIS to request a duplicate labor certification from DOL?", "Line8_Yes", "Line8_No",
            allowed=FILLED_OR_NA,
        ),
        "petitioner_type": q(
            "Part 5, Item 1: Type of petitioner (employer, self, or other)",
            ["Line1a_Employer", "Line1b_Self", "Line1c_Other", "Line1c_Explain"],
            notes={"Line1a_Employer": "Three separate boxes: check exactly one.", "Line1c_Explain": "Only with Other: who."},
            choices={"Line1a_Employer": {"Employer": "Y"}, "Line1b_Self": {"Self": "Y"}, "Line1c_Other": {"Other": "Y"}},
        ),
        "employer_information": q(
            "Part 5, Items 2-10: A company's type of business, date established, U.S. employees, gross and net income, "
            "NAICS code, and the labor certification's case number, filing and expiration dates",
            ["Line2a_TypeofBusiness", "Line2b_DateEstablished", "Line2c_NumberofEmployees", "Line2d_GrossAnnualIncome",
             "Line2e_NetAnnualIncome", "Line2f_NAICSCode", "Line2g_LaborCertification", "Line2h_LaborCertification",
             "Line2i_LaborCertificationDate"],
            ["Line2a_TypeofBusiness", "Line2b_DateEstablished", "Line2c_NumberofEmployees", "Line2d_GrossAnnualIncome",
             "Line2e_NetAnnualIncome", "Line2f_NAICSCode"],
            allowed=FILLED_OR_NA,
            notes={
                "Line2b_DateEstablished": DATE,
                "Line2d_GrossAnnualIncome": MONEY,
                "Line2e_NetAnnualIncome": MONEY,
                "Line2f_NAICSCode": "6 digits, no dashes.",
                "Line2g_LaborCertification": "Item 8, the DOL case number (maxlen 15), when there is a labor certification.",
                "Line2h_LaborCertification": "Item 9, the labor certification's DOL filing DATE, despite the name. " + DATE,
                "Line2i_LaborCertificationDate": "Item 10, its expiration date. " + DATE,
            },
        ),
        "individual_petitioner": q(
            "Part 5, Items 11-12: An individual petitioner's occupation and annual income",
            ["Line3a_Occupation", "Line3b_AnnualIncome"],
            ["Line3a_Occupation"],
            allowed=FILLED_OR_NA,
            notes={"Line3b_AnnualIncome": WHOLE_DOLLARS},
        ),
        "proposed_employment": q(
            "Part 6, Items 1-8: Job title, SOC code, job description, full-time, hours, permanent, new position, wages",
            ["Line1_JobTitle", "Line2_SOCCode1", "Line2_SOCCode2", "Line3_JobDescription", "Line4_Yes1", "Line4_No1",
             "Line5_Hours", "Line6_Yes1", "Line6_No1", "Line7_Yes1", "Line7_No1", "Line8_Wages", "Line8_Per"],
            ["Line1_JobTitle", "Line2_SOCCode1", "Line2_SOCCode2", "Line3_JobDescription", "Line8_Wages", "Line8_Per"],
            notes={
                "Line2_SOCCode1": "SOC code: the first 2 digits here, the last 4 in Line2_SOCCode2 (e.g. 15 and 1252).",
                "Line3_JobDescription": "For an NIW (1.h), the proposed endeavor in the same words as the letter and the "
                "ETA-9089 Appendix A; items 1-2 are the occupation through which it is pursued.",
                "Line4_Yes1": "Item 4, full-time. " + PAIR,
                "Line5_Hours": "Item 5, only if not full-time: hours per week.",
                "Line6_Yes1": "Item 6, permanent. " + PAIR,
                "Line7_Yes1": "Item 7, new position. " + PAIR,
                "Line8_Wages": WAGE,
                "Line8_Per": "hour, week, month or year (maxlen 5).",
            },
            choices={**pair("Line4_Yes1", "Line4_No1"), **pair("Line6_Yes1", "Line6_No1"), **pair("Line7_Yes1", "Line7_No1")},
        ),
        "worksite_address": q(
            "Part 6, Items 9.a-9.e: Where the beneficiary will work, if different from the Part 1 address",
            ["Line9a_StreetNumberName", "Line9b_Unit", "Line9b_AptSteFlrNumber", "Line9c_CityOrTown", "Line9d_State",
             "Line9e_ZipCode"],
            ["Line9a_StreetNumberName", "Line9c_CityOrTown", "Line9d_State", "Line9e_ZipCode"],
            allowed=FILLED_OR_NA,
            notes={"Line9d_State": STATE},
            choices={"Line9b_Unit": UNIT},
        ),
        "petitioner_signatory": q(
            "Part 8, Items 1-8: Authorized signatory's name, title, phones, email; petitioner's signature and date",
            ["Part7_Item3a_FamilyName", "Part7_Item3b_GivenName", "Part7_Item4_Title", "Part7_Item5_DayPhone",
             "Part7_Item6_MobilePhone", "Part7_Item7_Email"],
            ["Part7_Item3a_FamilyName", "Part7_Item3b_GivenName", "Part7_Item4_Title", "Part7_Item5_DayPhone"],
            notes={"Part7_Item3a_FamilyName": "Part 8 despite the Part7 name: the person who signs for the petitioner.",
                   "Part7_Item5_DayPhone": PHONE},
        ),
        "petitioner_signature": q(
            "Part 8, Item 8: Petitioner's signature and date",
            ["Line1a_SignatureofPetitioner", "Part7_Item8b_Date"],
            allowed=[PENDING_SIGNATURE, FILLED],
            notes={"Line1a_SignatureofPetitioner": SIGNATURE, "Part7_Item8b_Date": DATE},
        ),
        "interpreter_block": q(
            "Part 9, Items 1-6: Interpreter's name, business, phones, email, language",
            ["Part8_Item1a_FamilyName", "Part8_Item1b_GivenName", "Part8_Item2_OrgName", "Part8_Item4_DayPhone",
             "Part8_Item5_MobilePhone", "Part8_Item6_Email", "Part8_Item6_Language"],
            ["Part8_Item1a_FamilyName", "Part8_Item1b_GivenName", "Part8_Item4_DayPhone", "Part8_Item6_Language"],
            allowed=FILLED_OR_NA,
            notes={"Part8_Item1a_FamilyName": "Part 9 despite the Part8 name."},
        ),
        "interpreter_signature": q(
            "Part 9, Item 7: Interpreter's signature and date",
            ["Part6_Line6a_InterpretersSignature", "Part8_Item7b_Date"],
            allowed=[NOT_APPLICABLE, PENDING_SIGNATURE, FILLED],
            notes={"Part6_Line6a_InterpretersSignature": SIGNATURE, "Part8_Item7b_Date": DATE},
        ),
        "preparer_block": q(
            "Part 10, Items 1-5: Preparer's name, business, phones, email (from the attorney profile)",
            ["Part10_Item1_FamilyName", "Part10_Item1_GivenName", "Part10_Item2_OrgName", "Part10_Item3_DayPhone",
             "Part10_Item4_MobilePhone", "Part10_Item5_Email"],
            ["Part10_Item1_FamilyName", "Part10_Item1_GivenName", "Part10_Item3_DayPhone"],
            allowed=FILLED_OR_NA,
            notes={"Part10_Item1_FamilyName": "Profile key attorney_name (family name); firm_name in Part10_Item2_OrgName.",
                   "Part10_Item3_DayPhone": "Profile key phone. " + PHONE},
        ),
        "preparer_signature": q(
            "Part 10, Item 6: Preparer's signature and date",
            ["Part10_Item6_SignatureofPetitioner", "Part10_Item6__Date"],
            allowed=[NOT_APPLICABLE, PENDING_SIGNATURE, FILLED],
            notes={"Part10_Item6_SignatureofPetitioner": "The PREPARER's signature despite the name. " + SIGNATURE,
                   "Part10_Item6__Date": DATE},
        ),
        "additional_information": additional_information(),
    }
    for number in range(1, 7):
        questions[f"family_member_{number}"] = person(number)
    return {
        "kind": "i-140",
        "edition": "06/07/24",
        "field_list": "I-140.json",
        "description": (
            "Form I-140 for any employment-based category (EB-1, EB-2 including NIW, EB-3), by an employer or a "
            "self-petitioner, with the beneficiary's spouse and children."
        ),
        "notes": [
            "Part 7 lists the beneficiary's spouse and every child, whether or not they will immigrate; more than six "
            "go in Part 11.",
            "A company petitioner fills Part 1 item 2, the EIN and Part 5 items 2-7; an individual fills items 1.a-1.c and "
            "Part 5 items 11-12.",
            "A self-petitioner (EB-1A or NIW) is the beneficiary: Part 1 and Part 3 name the same person, and Part 5 item 1 "
            "is Self.",
        ],
        "required_questions": questions,
    }


SCHEMAS = {"i140_worker_petition": worker_petition()}

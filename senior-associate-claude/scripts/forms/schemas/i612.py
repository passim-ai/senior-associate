"""Question schema for Form I-612, Application for Waiver of the Foreign Residence Requirement
(INA 212(e)), on the exceptional-hardship or persecution ground.

Built against the 04/01/24 edition (uscis.gov/i-612 Edition Date panel and the PDF footer of the
form and its instructions, checked 2026-10-29). Field list: schemas/fields/I-612.json; every box
of the form belongs to one question except Button1, the ZIP Code lookup push button.

Most box names on this edition carry another part's or item's number; the field_notes name the
item each box really is, read from where it sits on the page. The ones that matter most:
P1_L4a/b/c_*[1] are the SPOUSE's name (Part 3 item 3), not other names; P4_L4_DateOfBirth is the
date of last entry as a J-1 (Part 4 item 4); P1_L7c_CityTown and P1_L7d_State are [0] the item 8
address, [1] the J-1 port of entry (Part 4 item 5), [2] where the spouse or child became a
permanent resident (Part 4 item 21); P4_L23_DateOfBirth is a certificate's date of issuance;
Part8_Line5_MobileTelephoneNumber[1] is the interpreter's mobile. Part 8 items 6 and 7 use the
I-140's trick: page, part and item boxes [1] for item 6 and [0] for item 7, text [0] and [1].
"""
from __future__ import annotations

from typing import Any

from _common import DATE, FILLED, FILLED_OR_NA, NOT_APPLICABLE, PENDING_SIGNATURE, UNIT, q

STATE = "U.S. address only: 2-letter state code (drop-down)."
ZIP = "U.S. address only: 5-digit ZIP Code."
PHONE = "Digits only."
SIGNATURE = "Protected box; the signer signs the printed form in ink."


def relative(label: str, names: list[str], dob: str, birth: str, citizenship: str, last_residence: str,
             *, notes: dict[str, str] | None = None) -> dict[str, Any]:
    return q(
        label,
        [*names, dob, birth, citizenship, last_residence],
        [names[0], names[1], dob, birth, citizenship],
        allowed=FILLED_OR_NA,
        notes={dob: DATE, last_residence: "Country of last foreign residence.", **(notes or {})},
    )


def additional_information() -> dict[str, Any]:
    rows = [(3, "Pt9Line3a_PageNumber", "Pt9Line3b_PartNumber", "Pt9Line3c_ItemNumber", "Pt9Line3d_AdditionalInfo"),
            (4, "Pt9Line4a_PageNumber", "Pt9Line4b_PartNumber", "Pt9Line4c_ItemNumber", "Pt9Line4d_AdditionalInfo"),
            (5, "Pt9Line5a_PageNumber", "Pt9Line5b_PartNumber", "Pt9Line5c_ItemNumber", "Pt9Line5d_AdditionalInfo"),
            (6, "Pt9Line6a_PageNumber[1]", "Pt9Line6b_PartNumber[1]", "Pt9Line6c_ItemNumber[1]", "Pt9Line6d_AdditionalInfo[0]"),
            (7, "Pt9Line6a_PageNumber[0]", "Pt9Line6b_PartNumber[0]", "Pt9Line6c_ItemNumber[0]", "Pt9Line6d_AdditionalInfo[1]")]
    return q(
        "Part 8, Items 3-7: Additional information (page, part, item and text, five entries)",
        [name for row in rows for name in row[1:]],
        list(rows[0][1:]),
        allowed=FILLED_OR_NA,
        notes={
            "Pt9Line3a_PageNumber": "Page, part and item boxes are unbound in the XFA template (fill binds them).",
            "Pt9Line6a_PageNumber[1]": "Item 6's page box is index [1]; its text box is Pt9Line6d_AdditionalInfo[0].",
            "Pt9Line6a_PageNumber[0]": "Item 7's page box is index [0]; its text box is Pt9Line6d_AdditionalInfo[1].",
        },
    )


def waiver_application() -> dict[str, Any]:
    questions: dict[str, dict[str, Any]] = {
        "applicant_numbers": q(
            "Part 1, Items 1-3: A-Number, USCIS online account number and Social Security number (each if any)",
            ["Pt1Line1_AlienNumber", "P1_Line2_AcctIdentifier", "Line13_SSN"],
            allowed=FILLED_OR_NA,
            notes={"Pt1Line1_AlienNumber": "If any: 9 digits, no 'A' (global, repeated on page 7).",
                   "Line13_SSN": "Item 3 despite the Line13 name: 9 digits."},
        ),
        "applicant_name": q(
            "Part 1, Items 4.a-4.c: Full name",
            ["Pt1Line2a_FamilyName", "Pt1Line2b_FirstName", "Pt1Line2c_MiddleName"],
            ["Pt1Line2a_FamilyName", "Pt1Line2b_FirstName"],
        ),
        "other_names": q(
            "Part 1, Items 5.a-6.c: Other names used, two rows (more in Part 8)",
            ["P1_L4a_FamilyName[0]", "P1_L4b_FirstName[0]", "P1_L4c_MiddleName[0]", "P1_L5a_FamilyName", "P1_L5b_FirstName",
             "P1_L5c_MiddleName"],
            ["P1_L4a_FamilyName[0]", "P1_L4b_FirstName[0]"],
            allowed=FILLED_OR_NA,
            notes={"P1_L4a_FamilyName[0]": "Item 5.a: only box [0]; box [1] is the spouse's name in Part 3."},
        ),
        "mailing_address": q(
            "Part 1, Items 7.a-7.h: Mailing address",
            ["P1_L6a_StreetNumberName", "Part1_Line6b_Unit", "P1_L6b_AptSteFlrNumber", "P1_L6c_CityTown", "P1_L6d_State",
             "P1_L6e_ZipCode", "P1_L6f_Province", "P1_L6g_PostalCode", "P1_L6h_Country"],
            ["P1_L6a_StreetNumberName", "P1_L6c_CityTown", "P1_L6h_Country"],
            notes={"P1_L6a_StreetNumberName": "Item 7, despite the L6 names (maxlen 25).", "P1_L6d_State": STATE,
                   "P1_L6e_ZipCode": ZIP},
            choices={"Part1_Line6b_Unit": UNIT},
        ),
        "last_us_address": q(
            "Part 1, Items 8.a-8.e: If living abroad, the last address in the United States",
            ["P1_L7a_StreetNumberName", "Part1_Line7b_Unit", "P1_7b_AptSteFlrNumber", "P1_L7c_CityTown[0]", "P1_L7d_State[0]",
             "P1_L7e_ZipCode"],
            ["P1_L7a_StreetNumberName", "P1_L7c_CityTown[0]", "P1_L7d_State[0]", "P1_L7e_ZipCode"],
            allowed=FILLED_OR_NA,
            notes={"P1_L7c_CityTown[0]": "Item 8.c is box [0]; [1] and [2] belong to Part 4 items 5 and 21.",
                   "P1_L7d_State[0]": STATE},
            choices={"Part1_Line7b_Unit": UNIT},
        ),
        "applicant_other_information": q(
            "Part 1, Items 9-14: Marital status, date and city of birth, country of birth, citizenship, last foreign residence",
            ["Part1_Line8_MaritalStatus", "P1_L8_DateOfBirth", "P1_L9_CityTown", "P1_L10_CountryOfBirth",
             "P1_L11_CountryOfCitizenshipNationality", "P1_L12_CountryOfFor"],
            ["Part1_Line8_MaritalStatus", "P1_L8_DateOfBirth", "P1_L9_CityTown", "P1_L10_CountryOfBirth",
             "P1_L11_CountryOfCitizenshipNationality", "P1_L12_CountryOfFor"],
            notes={"P1_L8_DateOfBirth": "Item 10. " + DATE, "P1_L12_CountryOfFor": "Item 14, country of last foreign residence."},
            choices={"Part1_Line8_MaritalStatus": {
                "Single, Never Married": "SNM ", "Married": "M ", "Divorced": "D", "Widowed": "W", "Separated": "S",
                "Marriage Annulled": "MA", "Other": "O"}},
        ),
        "reason_subject_to_212e": q(
            "Part 2, Items 1-4: Why the applicant is subject to the two-year foreign residence requirement (all that apply)",
            ["Part2_Checkboxes[1]", "Part2_Checkboxes[0]", "Part2_Line9b_PlaceOfEntry", "Part2_Checkboxes[2]",
             "Part2_Checkboxes[3]"],
            notes={
                "Part2_Checkboxes[1]": "Four separate boxes, any that apply: [1] item 1 (government-financed program), [0] item "
                "2.a (government grant), [2] item 3 (skills list), [3] item 4 (graduate medical education). The audit asks "
                "for at least one.",
                "Part2_Line9b_PlaceOfEntry": "Item 2.b despite the name: the agency or country that gave the grant (only with 2.a).",
            },
            choices={
                "Part2_Checkboxes[1]": {"1 Government-financed exchange program": "A"},
                "Part2_Checkboxes[0]": {"2.a Government grant, stipend or allowance": "B"},
                "Part2_Checkboxes[2]": {"3 Skills list (specialized knowledge)": "C"},
                "Part2_Checkboxes[3]": {"4 Graduate medical education on or after 01/10/1977": "D"},
            },
        ),
        "waiver_ground": q(
            "Part 3, Items 1-2: Waiver ground: exceptional hardship to a U.S. citizen or LPR spouse or child, or persecution "
            "on return",
            ["Part3_Line1_Checkboxes"],
            ["Part3_Line1_Checkboxes"],
            notes={"Part3_Line1_Checkboxes": (
                "Select only one. Either ground needs a signed statement with the evidence; the hardship statement "
                "includes both spouses' income and savings (form, page 2)."
            )},
            choices={"Part3_Line1_Checkboxes": {
                "1 Departure would impose exceptional hardship on a USC or LPR spouse or child": "Departure",
                "2 Would be subject to persecution on return": "Return"}},
        ),
        "spouse": relative(
            "Part 3, Items 3.a-7: Spouse (a J-2 dependent included in this application)",
            ["P1_L4a_FamilyName[1]", "P1_L4b_FirstName[1]", "P1_L4c_MiddleName[1]"], "P4_L13_DateOfBirth[0]",
            "P4_L14_CountryOfBirth[0]", "P4_L15_CitizenshioOrNationality[0]", "P4_L16_CountryOfLastForRes[0]",
            notes={"P1_L4a_FamilyName[1]": "The spouse's name is box [1] of the P1_L4 'other names' boxes."},
        ),
        "child_1": relative(
            "Part 3, Items 8.a-12: Child 1 (J-2 dependent included in this application)",
            ["P4_L12a_FamilyName", "P4_L12b_FirstName", "P4_L12c_MiddleName"], "P4_L13_DateOfBirth[1]",
            "P4_L14_CountryOfBirth[1]", "P4_L15_CitizenshioOrNationality[1]", "P4_L16_CountryOfLastForRes[1]",
        ),
        "child_2": relative(
            "Part 3, Items 13.a-17: Child 2",
            ["P4_L17a_FamilyName", "P4_L17b_FirstName", "P4_L17c_MiddleName"], "P4_L18_DateOfBirth[0]",
            "P4_L19_CountryOfBirth[0]", "P4_L20_CitizenshioOrNationality[0]", "P4_L21_CountryOfLastForRes[0]",
        ),
        "child_3": relative(
            "Part 3, Items 18.a-22: Child 3 (more in Part 8)",
            ["P4_L22a_FamilyName", "P4_L22b_FirstName", "P4_L22c_MiddleName"], "P4_L18_DateOfBirth[1]",
            "P4_L19_CountryOfBirth[1]", "P4_L20_CitizenshioOrNationality[1]", "P4_L21_CountryOfLastForRes[1]",
        ),
        "exchange_program": q(
            "Part 4, Items 1-6: Exchange program numbers or sponsors, field of activity, occupation, last J-1 entry and port "
            "of entry, last departure",
            ["P4_L1_AddInfo", "P4_L2_Checkboxes", "P4_L3_Occupation", "P4_L4_DateOfBirth", "P1_L7c_CityTown[1]",
             "P1_L7d_State[1]", "P4_L6_DateOfDepart"],
            ["P4_L1_AddInfo", "P4_L2_Checkboxes", "P4_L3_Occupation", "P4_L4_DateOfBirth", "P1_L7c_CityTown[1]",
             "P1_L7d_State[1]"],
            notes={
                "P4_L1_AddInfo": "Item 1: every exchange program number and name, or every sponsor (the DS-2019s).",
                "P4_L4_DateOfBirth": "Item 4, the date of last entry as a J-1, despite the DateOfBirth name. " + DATE,
                "P1_L7c_CityTown[1]": "Item 5, the port of entry of that arrival: city (box [1]).",
                "P1_L7d_State[1]": "Item 5, the port of entry's state (box [1]).",
                "P4_L6_DateOfDepart": "Item 6, only if now abroad: date of the most recent departure. " + DATE,
            },
            choices={"P4_L2_Checkboxes": {
                "Agriculture": "a", "Business Administration": "b", "Education": "c", "Engineering": "d", "Humanities": "e",
                "Medicine": "f", "Natural and Physical Sciences": "g", "Social Sciences": "h", "Other": "i"}},
        ),
        "spouse_in_application": q(
            "Part 4, Item 7: If married: the spouse is included, files a separate application, or is not included",
            ["P3_L4a_Checkboxes"],
            ["P3_L4a_Checkboxes"],
            allowed=FILLED_OR_NA,
            choices={"P3_L4a_Checkboxes": {
                "7.a My spouse is included in this application": "Included",
                "7.b My spouse is filing a separate application": "Separate",
                "7.c My spouse is not included in this application": "Not Included"}},
        ),
        "usc_relative": q(
            "Part 4, Items 8.a-17: The U.S. citizen spouse or child who would suffer exceptional hardship: name, how citizenship "
            "was acquired, naturalization or citizenship certificate",
            ["P4_L27a_FamilyName", "P4_L27b_FirstName", "P4_L27c_MiddleName", "Part4_Line9_Checkboxes", "P4_L29a_NatCertNumber",
             "P4_L29b_DateOfNat", "P1_L12_CityTown", "P1_L12_State", "P4_L11a_chbxyesno", "P4_L30a_NatCertNumber[0]",
             "P4_L23_DateOfBirth[0]", "P4_L30a_NatCertNumber[1]", "P4_L23_DateOfBirth[1]"],
            ["P4_L27a_FamilyName", "P4_L27b_FirstName", "Part4_Line9_Checkboxes"],
            allowed=FILLED_OR_NA,
            notes={
                "P4_L27a_FamilyName": "Only with Part 3 item 1 (hardship) and a U.S. citizen relative; more people in Part 8.",
                "P4_L29a_NatCertNumber": "Items 10-12, only with 9.b naturalization: certificate number, date, place.",
                "P4_L29b_DateOfNat": DATE,
                "P1_L12_CityTown": "Item 12, place of naturalization (city), despite the P1 name.",
                "P1_L12_State": "Item 12, place of naturalization (state).",
                "P4_L11a_chbxyesno": "Item 13, only with 9.c parents: has the spouse or child a Certificate of Citizenship?",
                "P4_L30a_NatCertNumber[0]": "Item 14, the spouse's certificate number (box [0]).",
                "P4_L23_DateOfBirth[0]": "Item 15, its date of ISSUANCE, despite the name. " + DATE,
                "P4_L30a_NatCertNumber[1]": "Item 16, the child's certificate number (box [1]).",
                "P4_L23_DateOfBirth[1]": "Item 17, its date of issuance. " + DATE,
            },
            choices={"Part4_Line9_Checkboxes": {"Birth in the United States": "A", "Naturalization": "B", "Parents": "C"},
                     "P4_L11a_chbxyesno": {"Yes": "Y", "No": "N"}},
        ),
        "lpr_relative": q(
            "Part 4, Items 18.a-22: The permanent resident spouse or child who would suffer exceptional hardship: name, "
            "A-Number, date, place and basis of becoming a permanent resident",
            ["P4_L31a_FamilyName", "P4_L31b_GivenName", "P4_L31c_MiddleName", "P4_L32_AlienNumber", "P4_L33_DateOfAdj",
             "P1_L7c_CityTown[2]", "P1_L7d_State[2]", "P4_L16_BasisAdj"],
            ["P4_L31a_FamilyName", "P4_L31b_GivenName", "P4_L33_DateOfAdj", "P4_L16_BasisAdj"],
            allowed=FILLED_OR_NA,
            notes={
                "P4_L32_AlienNumber": "Item 19, if any: 9 digits.",
                "P4_L33_DateOfAdj": DATE,
                "P1_L7c_CityTown[2]": "Item 21, where the spouse or child became a permanent resident: city (box [2]).",
                "P1_L7d_State[2]": "Item 21: state (box [2]).",
                "P4_L16_BasisAdj": "Item 22: the preference category (for example F-2A).",
            },
        ),
        "applicant_statement": q(
            "Part 5, Items 1-2: Reads English, or the interpreter read it (and the language); a preparer prepared it (name)",
            ["Part8_Line1_Checkbox", "Part8_Line1b_NameofInterpreter", "Part8_Line2_Checkbox", "Part8_Line2_Consent"],
            ["Part8_Line1_Checkbox"],
            notes={
                "Part8_Line1b_NameofInterpreter": "Item 1.b: the LANGUAGE, despite the name; only with 1.b.",
                "Part8_Line2_Checkbox": "Item 2: checked when a preparer prepared it; Part8_Line2_Consent is the preparer's name.",
            },
            choices={"Part8_Line1_Checkbox": {"1.a I can read and understand English": "A",
                                              "1.b The interpreter read it to me": "B"},
                     "Part8_Line2_Checkbox": {"2 A preparer prepared this application": "C"}},
        ),
        "applicant_contact": q(
            "Part 5, Items 3-5: Applicant's daytime phone, mobile phone (if any), email (if any)",
            ["Part8_Line4_DaytimeTelephoneNumber", "Part8_Line5_MobileTelephoneNumber[0]", "Part8_Line6_Email"],
            ["Part8_Line4_DaytimeTelephoneNumber"],
            notes={"Part8_Line4_DaytimeTelephoneNumber": PHONE,
                   "Part8_Line5_MobileTelephoneNumber[0]": "The applicant's mobile is box [0]; [1] is the interpreter's."},
        ),
        "applicant_signature": q(
            "Part 5, Item 6: Applicant's signature and date",
            ["P5_Line6a_SignatureofApplicant", "Part8_Line3b_DateofSignature"],
            allowed=[PENDING_SIGNATURE, FILLED],
            notes={"P5_Line6a_SignatureofApplicant": SIGNATURE, "Part8_Line3b_DateofSignature": DATE},
        ),
        "interpreter_block": q(
            "Part 6, Items 1-6: Interpreter's name, business, mailing address, phones, email, language",
            ["Part9_Line1a_InterpreterFamilyName", "Part9_Line1b_InterpreterGivenName", "Part9_Line2_BusinessName",
             "Part9_Line3a_StreetNumberName", "Part9_Line3b_Unit", "Part9_Line3b_AptSteFlrNumber", "Part9_Line3c_CityTown",
             "Part9_Line3d_State", "Part9_Line3e_ZipCode", "Part9_Line3f_Province", "Part9_Line3g_PostalCode",
             "Part9_Line3h_Country", "Part9_Line4_InterpreterDaytimeTelephoneNumber", "Part8_Line5_MobileTelephoneNumber[1]",
             "Part9_Line5_Email", "Part9_Iamfluent"],
            ["Part9_Line1a_InterpreterFamilyName", "Part9_Line1b_InterpreterGivenName", "Part9_Line3a_StreetNumberName",
             "Part9_Line3c_CityTown", "Part9_Line3h_Country", "Part9_Line4_InterpreterDaytimeTelephoneNumber",
             "Part9_Iamfluent"],
            allowed=FILLED_OR_NA,
            notes={"Part8_Line5_MobileTelephoneNumber[1]": "The interpreter's mobile (box [1]).",
                   "Part9_Iamfluent": "The language the interpreter is fluent in."},
            choices={"Part9_Line3b_Unit": UNIT},
        ),
        "interpreter_signature": q(
            "Part 6: Interpreter's signature and date",
            ["Part9_Line6a_Signature", "Part9_Line6b_DateofSignature"],
            allowed=[NOT_APPLICABLE, PENDING_SIGNATURE, FILLED],
            notes={"Part9_Line6a_Signature": SIGNATURE, "Part9_Line6b_DateofSignature": DATE},
        ),
        "preparer_block": q(
            "Part 7, Items 1-7: Preparer's name, business, address, phones, email (from the attorney profile), and statement",
            ["Part10_Line1a_PreparerFamilyName", "Part10_Line1b_PreparerGivenName", "Part10_Line2_BusinessName",
             "P10_Line3a_StreetNumberName", "P10_Line3b_Unit", "P10_Line3b_AptSteFlrNumber", "P10_Line3c_CityOrTown",
             "P10_Line3d_State", "P10_Line3e_ZipCode", "P10_Line3f_Province", "P10_Line3g_PostalCode", "P10_Line3h_Country",
             "P10_Line4_PreparerDaytimeTelephoneNumber", "P10_Line5_PreparerFaxNumber", "P10_Line6_EmailAddress",
             "P10_Line7_Checkbox", "Part7Line7b_Checkbox"],
            ["Part10_Line1a_PreparerFamilyName", "Part10_Line1b_PreparerGivenName", "P10_Line3a_StreetNumberName",
             "P10_Line3c_CityOrTown", "P10_Line3h_Country", "P10_Line4_PreparerDaytimeTelephoneNumber", "P10_Line7_Checkbox"],
            allowed=FILLED_OR_NA,
            notes={
                "Part10_Line1a_PreparerFamilyName": "From the attorney profile (attorney_name, firm_name, mailing_address, phone, email).",
                "P10_Line5_PreparerFaxNumber": "The preparer's MOBILE, despite the name (if any).",
                "P10_Line7_Checkbox": "7.a not an attorney; 7.b an attorney or accredited representative (then answer Part7Line7b_Checkbox).",
                "Part7Line7b_Checkbox": "With 7.b: the representation extends (Y) or does not extend (N) beyond preparing this form; "
                "Y means a G-28 is filed with it.",
            },
            choices={"P10_Line3b_Unit": UNIT,
                     "P10_Line7_Checkbox": {"7.a Not an attorney or accredited representative": "A",
                                            "7.b An attorney or accredited representative": "B"},
                     "Part7Line7b_Checkbox": {"Extends beyond preparing this application": "Y",
                                              "Does not extend beyond it": "N"}},
        ),
        "preparer_signature": q(
            "Part 7, Item 8: Preparer's signature and date",
            ["P10_Line8a_SignatureofPreparer", "P10_Line8b_DateOfSignature"],
            allowed=[NOT_APPLICABLE, PENDING_SIGNATURE, FILLED],
            notes={"P10_Line8a_SignatureofPreparer": SIGNATURE, "P10_Line8b_DateOfSignature": DATE},
        ),
        "additional_information": additional_information(),
    }
    return {
        "kind": "i-612",
        "edition": "04/01/24",
        "field_list": "I-612.json",
        "description": (
            "Form I-612 waiver of the two-year foreign residence requirement of INA 212(e) on the exceptional hardship or "
            "persecution ground (not an IGA, no-objection or Conrad waiver, which are requested through the State Department)."
        ),
        "notes": [
            "The hardship ground needs the U.S. citizen or permanent resident spouse or child in Part 4 items 8-22 and a "
            "signed statement with both spouses' income and savings; the persecution ground needs a signed statement.",
            "J-2 dependents included in the application go in Part 3 items 3-22 (more in Part 8).",
        ],
        "required_questions": questions,
    }


SCHEMAS = {"i612_foreign_residence_waiver": waiver_application()}

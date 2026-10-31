"""Question schema for Form I-130A, Supplemental Information for Spouse Beneficiary.

Built against the 04/01/24 edition (the edition the I-130 page lists for the I-130A, and the
footer of the PDF). Field list: schemas/fields/I-130A.json. The audit's I-130A rules
(audit_prepared_forms.audit_i130a) use the same address and employment rows.
"""
from __future__ import annotations

from _common import DATE, FILLED, FILLED_OR_NA, NOT_APPLICABLE, PENDING_SIGNATURE, SIGNATURE_STATUSES, q

UNIT_PADDED = {"apt": " APT ", "ste": " STE ", "flr": " FLR "}  # Part 1 address rows
UNIT_PLAIN = {"apt": "APT", "ste": "STE", "flr": "FLR"}  # every other address on this form

US_ONLY = "U.S. addresses only: 2-letter state code; leave blank for a foreign address."
ZIP = "U.S. addresses only: 5-digit ZIP Code."
FOREIGN_ONLY = "Foreign addresses only."

SCHEMAS = {
    "i130a_spouse_beneficiary": {
        "kind": "i-130a",
        "edition": "04/01/24",
        "field_list": "I-130A.json",
        "description": (
            "Form I-130A for the spouse beneficiary of an I-130, whether the spouse lives in the "
            "United States or abroad."
        ),
        "notes": [
            "Every spouse beneficiary completes the I-130A. A spouse beneficiary who resides outside the "
            "United States does not have to sign it (form page 1; I-130 Instructions, Who May File, NOTE 1). "
            "For that spouse only, the Part 4 statement and signature may be not_applicable; the contact "
            "details are still given.",
            "Address history (Part 1) and employment history (Part 2) cover the last five years, current "
            "first. Rows past the two on the form go in Part 7, cited to Page 1, Part 1, Items 4-7 or "
            "Page 2-3, Part 2, Items 5-8.",
            "Pt1Line5b_DateTo and Pt2Line4b_DateTo (the current address's and current employer's 'Date To') "
            "are pre-printed PRESENT. They are not in this schema; leave them alone.",
            "Part 7 items 1-2 (name, A-Number) repeat Part 1 automatically: Pt1Line3a/3b/3c and "
            "Pt1Line1_AlienNumber are global fields. Set them once in Part 1.",
            "Write N/A in a box the instructions require answered but that does not apply (How To "
            "Complete, item 3), e.g. Part 3 item 1 when the last foreign job is already in Part 2.",
            "Part 5 (interpreter) and Part 6 (preparer) ask for the person only if different from the "
            "I-130's. The audit still requires the Part 6 preparer block, so fill it whenever an attorney "
            "or preparer prepared the form.",
            "Form defect: Pt1Line12CityTownOfBirth (Parent 1's city of birth) is unbound in the XFA "
            "template (bind match=none). fill writes it and the filing copy shows it, but Adobe opening "
            "the XFA source shows that box empty. Check it on the filing copy, not in Acrobat.",
        ],
        "required_questions": {
            "attorney_box": q(
                "Page 1 attorney box: G-28 attached, Volag number, bar number, online account number",
                ["CheckBox1", "VolagNumber", "AttorneyStateBarNumber", "USCISOnlineAcctNumber"],
                ["CheckBox1", "AttorneyStateBarNumber"],
                allowed=FILLED_OR_NA,
                notes={
                    "CheckBox1": "Select when a G-28 for the spouse beneficiary is filed with the I-130A. The audit "
                    "compares it, the bar number and the online account number with the G-28.",
                    "VolagNumber": "Accredited representatives only, if any.",
                    "USCISOnlineAcctNumber": "The attorney's or representative's USCIS online account number, if any "
                    "(maxlen 12). Blank when the profile says has_uscis_online_account \"no\".",
                },
                choices={"CheckBox1": {"g28_attached": "1"}},
            ),
            "a_number": q(
                "Part 1, Item 1: Alien Registration Number (A-Number), if any",
                ["Pt1Line1_AlienNumber"],
                ["Pt1Line1_AlienNumber"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt1Line1_AlienNumber": "9 digits, no 'A'. Global: also fills Part 7 item 2.",
                },
            ),
            "uscis_online_account_number": q(
                "Part 1, Item 2: USCIS Online Account Number, if any",
                ["Pt2Line3_USCISELISActNumber"],
                ["Pt2Line3_USCISELISActNumber"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt2Line3_USCISELISActNumber": "Part 1 item 2, despite the Pt2Line3 name. 12 digits; only if the "
                    "spouse beneficiary has an IOE receipt.",
                },
            ),
            "spouse_beneficiary_name": q(
                "Part 1, Item 3: Your full name (spouse beneficiary)",
                ["Pt1Line3a_FamilyName", "Pt1Line3b_GivenName", "Pt1Line3c_MiddleName"],
                ["Pt1Line3a_FamilyName", "Pt1Line3b_GivenName"],
                notes={
                    "Pt1Line3a_FamilyName": "Global: also fills Part 7 item 1.a.",
                    "Pt1Line3c_MiddleName": "N/A if none.",
                },
            ),
            "physical_address_1_current": q(
                "Part 1, Items 4-5: Physical Address 1 (current) and date from",
                ["Pt1Line4a_StreetNumberName", "Pt1Line4b_Unit", "Pt1Line4b_AptSteFlrNumber", "Pt1Line4c_CityOrTown",
                 "Pt1Line4d_State", "Pt1Line4e_ZipCode", "Pt1Line4f_Province", "Pt1Line4g_PostalCode",
                 "Pt1Line4h_Country", "Pt1Line5a_DateFrom"],
                ["Pt1Line4a_StreetNumberName", "Pt1Line4c_CityOrTown", "Pt1Line4h_Country", "Pt1Line5a_DateFrom"],
                notes={
                    "Pt1Line4b_Unit": "Unit type; set together with Pt1Line4b_AptSteFlrNumber or leave both blank.",
                    "Pt1Line4d_State": US_ONLY,
                    "Pt1Line4e_ZipCode": ZIP,
                    "Pt1Line4f_Province": FOREIGN_ONLY,
                    "Pt1Line4g_PostalCode": FOREIGN_ONLY,
                    "Pt1Line5a_DateFrom": DATE + " Date To (5.b) is pre-printed PRESENT.",
                },
                choices={"Pt1Line4b_Unit": dict(UNIT_PADDED)},
            ),
            "physical_address_2": q(
                "Part 1, Items 6-7: Physical Address 2 and dates",
                ["Pt1Line6a_StreetNumberName", "Pt1Line6b_Unit", "Pt1Line6b_AptSteFlrNumber", "Pt1Line6c_CityOrTown",
                 "Pt1Line6d_State", "Pt1Line6e_ZipCode", "Pt1Line6f_Province", "Pt1Line6g_PostalCode",
                 "Pt1Line6h_Country", "Pt1Line7a_DateFrom", "Pt1Line7b_DateTo"],
                ["Pt1Line6a_StreetNumberName", "Pt1Line6c_CityOrTown", "Pt1Line6h_Country", "Pt1Line7a_DateFrom",
                 "Pt1Line7b_DateTo"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt1Line6a_StreetNumberName": "The address before the current one. not_applicable only if the "
                    "current address covers the whole five years. Older addresses go in Part 7.",
                    "Pt1Line6d_State": US_ONLY,
                    "Pt1Line6e_ZipCode": ZIP,
                    "Pt1Line6f_Province": FOREIGN_ONLY,
                    "Pt1Line6g_PostalCode": FOREIGN_ONLY,
                    "Pt1Line7a_DateFrom": DATE,
                    "Pt1Line7b_DateTo": DATE + " Should not be after the current address's 5.a.",
                },
                choices={"Pt1Line6b_Unit": dict(UNIT_PADDED)},
            ),
            "last_address_outside_us": q(
                "Part 1, Items 8-9: Last physical address outside the U.S. of more than one year",
                ["Pt1Line8a_StreetNumberName", "Pt1Line8b_Unit", "Pt1Line8b_AptSteFlrNumber", "Pt1Line8c_CityOrTown",
                 "Pt1Line8d_Province", "Pt1Line8e_PostalCode", "Pt1Line8f_Country", "Pt1Line9a_DateFrom",
                 "Pt1Line9b_DateTo"],
                ["Pt1Line8a_StreetNumberName", "Pt1Line8c_CityOrTown", "Pt1Line8f_Country", "Pt1Line9a_DateFrom",
                 "Pt1Line9b_DateTo"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt1Line8a_StreetNumberName": "Give it even if it is also listed in items 4-7, including a "
                    "spouse beneficiary who lives abroad now. not_applicable only if the spouse never lived "
                    "outside the U.S. for more than a year. This row has no state or ZIP Code boxes.",
                    "Pt1Line8b_Unit": "Unit type; set together with Pt1Line8b_AptSteFlrNumber.",
                    "Pt1Line9a_DateFrom": DATE,
                    "Pt1Line9b_DateTo": DATE,
                },
                choices={"Pt1Line8b_Unit": dict(UNIT_PADDED)},
            ),
            "parent_1": q(
                "Part 1, Items 10-16: Parent 1 (name at birth, date of birth, sex, birthplace, residence)",
                ["Pt1Line10_FamilyName", "Pt1Line10_GivenName", "Pt1Line10_MiddleName", "Pt1Line11_DateofBirth",
                 "Pt1Line12_Male", "Pt1Line12_Female", "Pt1Line12CityTownOfBirth", "Pt1Line13_CountryofBirth",
                 "Pt1Line14_CountryofBirth", "Pt1Line15_CountryofResidence"],
                ["Pt1Line10_FamilyName", "Pt1Line10_GivenName", "Pt1Line11_DateofBirth", "Pt1Line13_CountryofBirth",
                 "Pt1Line15_CountryofResidence"],
                notes={
                    "Pt1Line10_FamilyName": "Item 10.a asks for the maiden name (family name at birth).",
                    "Pt1Line11_DateofBirth": DATE,
                    "Pt1Line12_Male": "Item 12 sex: two separate boxes; set only one.",
                    "Pt1Line12CityTownOfBirth": "Item 13, city/town/village of birth (maxlen 38).",
                    "Pt1Line13_CountryofBirth": "Item 14, country of birth.",
                    "Pt1Line14_CountryofBirth": "Item 15, city/town/village of RESIDENCE, despite the name.",
                    "Pt1Line15_CountryofResidence": "Item 16, country of residence. For a deceased parent, write "
                    "'Deceased' in items 15 and 16 if that is the firm's practice, and say so in Part 7.",
                },
                choices={
                    "Pt1Line12_Male": {"male": "Y"},
                    "Pt1Line12_Female": {"female": "Y"},
                },
            ),
            "parent_2": q(
                "Part 1, Items 17-23: Parent 2 (name, date of birth, sex, birthplace, residence)",
                ["Pt1Line16_FamilyName", "Pt1Line16_GivenName", "Pt1Line16_MiddleName", "Pt1Line17_DateofBirth",
                 "Pt1Line19_Male", "Pt1Line19_Female", "Pt1Line18_CityTownOfBirth", "Pt1Line19_CountryofBirth",
                 "Pt1Line20_CityTownVillageofRes", "Pt1Line21_CountryofResidence"],
                ["Pt1Line16_FamilyName", "Pt1Line16_GivenName", "Pt1Line17_DateofBirth", "Pt1Line19_CountryofBirth",
                 "Pt1Line21_CountryofResidence"],
                notes={
                    "Pt1Line16_FamilyName": "Item 17.a (the Pt1Line16 names are item 17).",
                    "Pt1Line17_DateofBirth": "Item 18. " + DATE,
                    "Pt1Line19_Male": "Item 19 sex: two separate boxes; set only one.",
                    "Pt1Line18_CityTownOfBirth": "Item 20, city/town/village of birth (maxlen 20).",
                    "Pt1Line19_CountryofBirth": "Item 21, country of birth.",
                    "Pt1Line20_CityTownVillageofRes": "Item 22, city/town/village of residence.",
                    "Pt1Line21_CountryofResidence": "Item 23, country of residence.",
                },
                choices={
                    "Pt1Line19_Male": {"male": "Y"},
                    "Pt1Line19_Female": {"female": "Y"},
                },
            ),
            "employer_1_current": q(
                "Part 2, Items 1-4: Employer 1 (current employment, or 'Unemployed')",
                ["Pt2Line1_EmployerOrCompName", "Pt2Line2a_StreetNumberName", "Pt2Line2b_Unit",
                 "Pt2Line2b_AptSteFlrNumber", "Pt2Line2c_CityOrTown", "Pt2Line2d_State", "Pt2Line2e_ZipCode",
                 "Pt2Line2f_Province", "Pt2Line2g_PostalCode", "Pt2Line2h_Country", "Pt2Line3_Occupation",
                 "Pt2Line4a_DateFrom"],
                ["Pt2Line1_EmployerOrCompName", "Pt2Line4a_DateFrom"],
                notes={
                    "Pt2Line1_EmployerOrCompName": "If currently unemployed, type 'Unemployed' (the form's "
                    "instruction) and leave the address blank. Otherwise the address, occupation and dates are "
                    "all required (the audit checks the row). maxlen 34.",
                    "Pt2Line2d_State": US_ONLY,
                    "Pt2Line2e_ZipCode": ZIP,
                    "Pt2Line2f_Province": FOREIGN_ONLY,
                    "Pt2Line2g_PostalCode": FOREIGN_ONLY,
                    "Pt2Line4a_DateFrom": DATE + " Date To (4.b) is pre-printed PRESENT.",
                },
                choices={"Pt2Line2b_Unit": dict(UNIT_PLAIN)},
            ),
            "employer_2": q(
                "Part 2, Items 5-8: Employer 2 and dates",
                ["Pt2Line5_EmployerOrCompName", "Pt2Line6_StreetNumberName", "Pt2Line6_Unit",
                 "Pt2Line6_AptSteFlrNumber", "Pt2Line6_CityOrTown", "Pt2Line6_State", "Pt2Line6_ZipCode",
                 "Pt2Line6_Province", "Pt2Line6_PostalCode", "Pt2Line6_Country", "Pt2Line7_Occupation",
                 "Pt2Line8a_DateFrom", "Pt2Line8b_DateTo"],
                ["Pt2Line5_EmployerOrCompName", "Pt2Line8a_DateFrom", "Pt2Line8b_DateTo"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt2Line5_EmployerOrCompName": "The job (or period of unemployment) before Employer 1. "
                    "not_applicable only if Employer 1 covers the whole five years. Older jobs go in Part 7.",
                    "Pt2Line6_StreetNumberName": "Item 6.a. The Pt2Line6_* names have no a-h letters; the tooltip "
                    "letters are 6.a street, 6.b unit, 6.c city, 6.d state, 6.e ZIP, 6.f province, 6.g postal "
                    "code, 6.h country.",
                    "Pt2Line6_State": US_ONLY,
                    "Pt2Line6_ZipCode": ZIP,
                    "Pt2Line6_Province": FOREIGN_ONLY,
                    "Pt2Line6_PostalCode": FOREIGN_ONLY,
                    "Pt2Line8a_DateFrom": DATE,
                    "Pt2Line8b_DateTo": DATE,
                },
                choices={"Pt2Line6_Unit": dict(UNIT_PLAIN)},
            ),
            "employment_outside_us": q(
                "Part 3, Items 1-4: Last employment outside the U.S. (if not shown above)",
                ["Pt3Line1_EmployerOrCompName", "Pt3Line2a_StreetNumberName", "Pt3Line2b_Unit",
                 "Pt3Line2b_AptSteFlrNumber", "Pt3Line2c_CityOrTown", "Pt3Line2d_State", "Pt3Line2e_ZipCode",
                 "Pt3Line2f_Province", "Pt3Line2g_PostalCode", "Pt3Line2h_Country", "Pt3Line3_Occupation",
                 "Pt3Line4a_DateFrom", "Pt3Line4b_DateTo"],
                ["Pt3Line1_EmployerOrCompName"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt3Line1_EmployerOrCompName": "If the last foreign job is already in Part 2, type 'N/A' here "
                    "and leave the rest blank (the audit accepts a row answered N/A). If the spouse never "
                    "worked outside the U.S., say so in Part 7 (the form's instruction). Otherwise complete "
                    "the row: address, occupation and both dates.",
                    "Pt3Line2d_State": "Normally blank: this is a job outside the United States.",
                    "Pt3Line2e_ZipCode": "Normally blank: this is a job outside the United States.",
                    "Pt3Line4a_DateFrom": DATE,
                    "Pt3Line4b_DateTo": DATE,
                },
                choices={"Pt3Line2b_Unit": dict(UNIT_PLAIN)},
            ),
            "statement_language": q(
                "Part 4, Item 1.a/1.b: Reads English, or an interpreter read the form (language)",
                ["Pt4Line1Checkbox", "Pt4Line1b_Language"],
                ["Pt4Line1Checkbox"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt4Line1Checkbox": "One global group: box [0] is 1.b (on-state B), box [1] is 1.a (on-state A). "
                    "Set the base name once. not_applicable only for a spouse beneficiary who resides "
                    "abroad and will not sign.",
                    "Pt4Line1b_Language": "Only with 1.b: the language the interpreter used.",
                },
                choices={"Pt4Line1Checkbox": {"reads_english": "A", "interpreter": "B"}},
            ),
            "statement_preparer": q(
                "Part 4, Item 2: Prepared at my request by the preparer named in Part 6",
                ["Pt4_Checkbox", "Pt4Line2_RepresentativeName"],
                ["Pt4_Checkbox", "Pt4Line2_RepresentativeName"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt4Line2_RepresentativeName": "The preparer's full name, matching Part 6 item 1.",
                },
                choices={"Pt4_Checkbox": {"preparer_used": "C"}},
            ),
            "spouse_beneficiary_contact": q(
                "Part 4, Items 3-5: Spouse beneficiary's daytime phone, mobile phone, email",
                ["Pt4Line3_DaytimePhoneNumber1", "Pt4Line4_MobileNumber1", "Pt4Line5_Email"],
                ["Pt4Line3_DaytimePhoneNumber1"],
                notes={
                    "Pt4Line3_DaytimePhoneNumber1": "Required by the audit even for a spouse abroad. Digits only "
                    "(maxlen 13, room for a country code).",
                    "Pt4Line4_MobileNumber1": "If any; maxlen 13.",
                    "Pt4Line5_Email": "If any; maxlen 38.",
                },
            ),
            "spouse_beneficiary_signature": q(
                "Part 4, Item 6: Spouse beneficiary's signature and date",
                ["Pt4Line6a_Signature", "Pt4Line6b_DateofSignature"],
                allowed=[PENDING_SIGNATURE, FILLED, NOT_APPLICABLE],
                notes={
                    "Pt4Line6a_Signature": "Signed in ink; never typed. not_applicable only for a spouse beneficiary "
                    "who resides outside the U.S. (the form does not require that spouse's signature).",
                    "Pt4Line6b_DateofSignature": "Dated by the signer at signing.",
                },
            ),
            "interpreter_block": q(
                "Part 5, Items 1-6: Interpreter's name, business, mailing address, contact, language",
                ["Pt5Line1a_InterpreterFamilyName", "Pt5Line1b_InterpreterGivenName",
                 "Pt5Line2_InterpreterBusinessorOrg", "Pt5Line3a_StreetNumberName", "Pt5Line3b_Unit",
                 "Pt5Line3b_AptSteFlrNumber", "Pt5Line3c_CityOrTown", "Pt5Line3d_State", "Pt5Line3e_ZipCode",
                 "Pt5Line3f_Province", "Pt5Line3g_PostalCode", "Pt5Line3h_Country",
                 "Pt5Line4_InterpreterDaytimeTelephone[0]", "Pt5Line4_InterpreterDaytimeTelephone[1]", "Pt5Line5_Email",
                 "Pt5_NameofLanguage"],
                ["Pt5Line1a_InterpreterFamilyName", "Pt5Line1b_InterpreterGivenName", "Pt5Line3a_StreetNumberName",
                 "Pt5Line3c_CityOrTown", "Pt5Line3h_Country", "Pt5Line4_InterpreterDaytimeTelephone[0]",
                 "Pt5_NameofLanguage"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt5Line1a_InterpreterFamilyName": "Only if an interpreter was used and is different from the "
                    "I-130's interpreter (the form's instruction); otherwise not_applicable.",
                    "Pt5Line4_InterpreterDaytimeTelephone[0]": "Item 4, daytime phone; maxlen 10, so 10 digits only.",
                    "Pt5Line4_InterpreterDaytimeTelephone[1]": "Item 5, the interpreter's MOBILE phone (the second box "
                    "of the same name), if any; maxlen 13.",
                    "Pt5Line5_Email": "Item 6, email, if any.",
                    "Pt5_NameofLanguage": "The language in the interpreter's certification; same as Part 4 item 1.b.",
                    "Pt5Line3d_State": US_ONLY,
                    "Pt5Line3e_ZipCode": ZIP,
                    "Pt5Line3f_Province": FOREIGN_ONLY,
                    "Pt5Line3g_PostalCode": FOREIGN_ONLY,
                },
                choices={"Pt5Line3b_Unit": dict(UNIT_PLAIN)},
            ),
            "interpreter_signature": q(
                "Part 5, Item 7: Interpreter's signature and date",
                ["Pt5Line6a_Signature", "Pt5Line6b_DateofSignature"],
                allowed=[PENDING_SIGNATURE, FILLED, NOT_APPLICABLE],
                notes={
                    "Pt5Line6a_Signature": "Item 7.a despite the Line6 name; signed in ink.",
                    "Pt5Line6b_DateofSignature": "Item 7.b.",
                },
            ),
            "preparer_block": q(
                "Part 6, Items 1-6: Preparer's name, business, mailing address and contact",
                ["Pt6Line1a_PreparerFamilyName", "Pt6Line1b_PreparerGivenName", "Pt6Line2_BusinessName",
                 "Pt6Line3a_StreetNumberName", "Pt6Line3b_Unit", "Pt6Line3b_AptSteFlrNumber", "Pt6Line3c_CityOrTown",
                 "Pt6Line3d_State", "Pt6Line3e_ZipCode", "Pt6Line3f_Province", "Pt6Line3g_PostalCode",
                 "Pt6Line3h_Country", "Pt6Line4_DaytimePhoneNumber", "Pt6Line5_PreparerFaxNumber", "Pt6Line6_Email"],
                ["Pt6Line1a_PreparerFamilyName", "Pt6Line1b_PreparerGivenName", "Pt6Line2_BusinessName",
                 "Pt6Line3a_StreetNumberName", "Pt6Line3c_CityOrTown", "Pt6Line3h_Country",
                 "Pt6Line4_DaytimePhoneNumber", "Pt6Line6_Email"],
                notes={
                    "Pt6Line1a_PreparerFamilyName": "From the attorney profile. The audit requires this block and, "
                    "when 7.b is selected, compares the name with the G-28.",
                    "Pt6Line5_PreparerFaxNumber": "Item 5, the preparer's MOBILE phone, despite the Fax name; if any.",
                    "Pt6Line3d_State": US_ONLY,
                    "Pt6Line3e_ZipCode": ZIP,
                    "Pt6Line3f_Province": FOREIGN_ONLY,
                    "Pt6Line3g_PostalCode": FOREIGN_ONLY,
                },
                choices={"Pt6Line3b_Unit": dict(UNIT_PLAIN)},
            ),
            "preparer_statement": q(
                "Part 6, Item 7: Preparer's statement (not an attorney, or attorney: extends / does not extend)",
                ["Pt6Line7_Checkbox", "Pt6Line7b_Checkbox"],
                ["Pt6Line7_Checkbox"],
                notes={
                    "Pt6Line7_Checkbox": "Global group: A = 7.a not an attorney, B = 7.b attorney or accredited "
                    "representative.",
                    "Pt6Line7b_Checkbox": "Only with 7.b. 'extends' means the page 1 G-28 box must be selected "
                    "(the audit checks it).",
                },
                choices={
                    "Pt6Line7_Checkbox": {"not_attorney": "A", "attorney_or_accredited_rep": "B"},
                    "Pt6Line7b_Checkbox": {"extends": "Y", "does_not_extend": "N"},
                },
            ),
            "preparer_signature": q(
                "Part 6, Item 8: Preparer's signature and date",
                ["Pt6Line8a_Signature", "Pt6Line8b_DateofSignature"],
                allowed=SIGNATURE_STATUSES,
                notes={"Pt6Line8a_Signature": "Signed in ink; never typed."},
            ),
            "additional_information": q(
                "Part 7, Items 3-7: Additional information (page, part, item, text)",
                ["Pt7Line3a_PageNumber", "Pt7Line3b_PartNumber", "Pt7Line3c_ItemNumber", "Pt7Line3d_AdditionalInfo",
                 "Pt7Line4a_PageNumber", "Pt7Line4b_PartNumber", "Pt7Line4c_ItemNumber", "Pt7Line4d_AdditionalInfo",
                 "Pt7Line5a_PageNumber", "Pt7Line5b_PartNumber", "Pt7Line5c_ItemNumber", "Pt7Line5d_AdditionalInfo",
                 "Pt7Line6a_PageNumber", "Pt7Line6b_PartNumber", "Pt7Line6c_ItemNumber", "Pt7Line6d_AdditionalInfo",
                 "Pt7Line7a_PageNumber", "Pt7Line7b_PartNumber", "Pt7Line7c_ItemNumber", "Pt7Line7d_AdditionalInfo"],
                ["Pt7Line3a_PageNumber", "Pt7Line3b_PartNumber", "Pt7Line3c_ItemNumber", "Pt7Line3d_AdditionalInfo"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt7Line3a_PageNumber": "Page number only (maxlen 2). Part (b) and item (c) boxes hold 6 "
                    "characters, e.g. '1' and '6-7'.",
                    "Pt7Line3d_AdditionalInfo": "Each 'd' box holds 9 lines of 38 characters (Courier 10 pt) and "
                    "does not wrap: break the lines yourself (the audit reports clipped text). Use entries 3-7 "
                    "in order; extra address or employment rows, and 'never worked outside the U.S.' for "
                    "Part 3, go here.",
                },
            ),
        },
    },
}

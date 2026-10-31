"""Question schema for Form I-765, Application for Employment Authorization.

Built against the 08/21/25 edition (uscis.gov/i-765 Edition Date panel and the PDF footer of
both the form and the instructions). Field list: schemas/fields/I-765.json. The audit's I-765
rules (audit_prepared_forms.audit_i765) check only the eligibility category and its own follow-up
items 28-31, so this schema is what holds the rest of a plan to the form.

Item numbers below are the form's. Many field names on this edition carry an older item number
(Line19_DOB is item 16, Line19_Checkbox is item 12, PtLine29_YesNo is item 30) or the wrong
part (Pt5Line3* is the Part 4 interpreter's address, Pt6Line3* the Part 5 preparer's address,
Pt4Line6_Checkbox is Part 3 item 6); the field_notes say which is which.
"""
from __future__ import annotations

from _common import DATE, FILLED, FILLED_OR_NA, NOT_APPLICABLE, PENDING_SIGNATURE, SIGNATURE_STATUSES, q

YES_NO = {"yes": "Y", "no": "N"}
UNIT = {"apt": " APT ", "ste": " STE ", "flr": " FLR "}
# Part 4 item 3.b and Part 5 item 3.b: each box's on-state names a different unit from the label
# printed beside it (in both the XFA template and the AcroForm). Keyed by the printed label, so the
# filing copy shows the right box; the stored value reads differently (see the field_notes).
UNIT_PAGE5 = {"apt": " FLR ", "ste": " APT ", "flr": " STE "}

STATE = "U.S. addresses only: 2-letter state code."
ZIP = "U.S. addresses only: 5-digit ZIP Code."
FOREIGN_ONLY = "Foreign addresses only."
PHONE = "10 digits, no punctuation (maxlen 10)."
UNIT_NUMBER = "The apartment, suite or floor number only (maxlen 6); pick the unit type in the matching Unit box."
UNIT_PAGE5_NOTE = (
    "Form defect on this edition: the on-states do not match the printed labels. ' FLR ' checks the "
    "box printed 'Apt.', ' APT ' checks 'Ste.', ' STE ' checks 'Flr.'. Use the choices (keyed by the "
    "printed label), never the plain unit code."
)
SIGNATURE = (
    "Protected box (maxlen 1); it cannot be typed or signed electronically. Leave it blank: the "
    "signer signs in ink."
)
SIGNATURE_DATE = (
    "mm/dd/yyyy. Normally left blank for the signer to date at signing; type a date only on the "
    "attorney's instruction."
)

PART6_TEXT = (
    "The filing copy does not wrap text: break it into lines of about 38 characters with newlines, "
    "or the audit reports it cut off."
)

CATEGORY_NOTE = (
    "Categories with their own follow-up items: (c)(3)(C) STEM OPT (item 28), (c)(26) H-4 spouse of an "
    "H-1B (item 29), (c)(8) pending asylum (item 30, plus Part 3 item 6 for ABC class members), "
    "(c)(35)/(c)(36) compelling circumstances (item 31). (c)(9) pending adjustment and (a)(5) asylee "
    "have no follow-up items on this edition: write the category here and mark items 28-31 "
    "not_applicable."
)

SCHEMAS = {
    "i765_work_authorization": {
        "kind": "i-765",
        "edition": "08/21/25",
        "field_list": "I-765.json",
        "description": (
            "Form I-765 employment authorization for any eligibility category, initial, replacement or "
            "renewal, with the category-specific items for (c)(3)(C), (c)(26), (c)(8) and (c)(35)/(c)(36)."
        ),
        "notes": [
            "Enter one eligibility category only (Part 2 item 27). An asylee or refugee who has filed an "
            "I-485 files under (a)(5) or (a)(3), not (c)(9); a pending asylum applicant files under (c)(8) "
            "and a granted asylee under (a)(5) (Instructions, Who May File).",
            "The category-specific questions (stem_opt_c3c, h4_spouse_c26, pending_asylum_c8_arrests, "
            "compelling_circumstances_c35_c36, abc_settlement_c8) are not_applicable for every other "
            "category. (c)(9) and (a)(5) have no category-specific items on this edition.",
            "This edition has no Social Security card questions. Earlier editions asked whether SSA "
            "should issue a card, for consent to disclosure and for the parents' names; the 08/21/25 "
            "form keeps only item 13, the SSN if known. Don't look for those boxes.",
            "Item 17 asks only for the I-94 number. The instructions also mention the I-94 expiration "
            "date, but the form has no box for it; don't force it into another box.",
            "Part 6 items 1.a-1.c and 2 (name and A-Number at the top of the page) repeat Part 2 items "
            "1.a-1.c and 8 automatically: Line1a/1b/1c and Line7_AlienNumber are global fields. Set them "
            "once in Part 2.",
            "Write N/A in a text box the instructions require answered but that does not apply "
            "(How To Complete, item 3). The A-Number, SSN and I-94 boxes take digits only, so leave "
            "those blank and mark the question not_applicable.",
            "Name, place-of-birth and degree boxes accept only letters, spaces and hyphens in Adobe "
            "(no apostrophes or periods).",
        ],
        "required_questions": {
            "attorney_box": q(
                "Page 1 attorney box: G-28 attached, attorney bar number, online account number",
                ["CheckBox1", "attorneyBarNumber", "USCISELISAcctNumber"],
                ["CheckBox1"],
                allowed=FILLED_OR_NA,
                notes={
                    "CheckBox1": "Select when a G-28 for the applicant is filed with the I-765.",
                    "attorneyBarNumber": "Attorney's state bar number, if applicable (maxlen 15); blank for an "
                    "accredited representative.",
                    "USCISELISAcctNumber": "The attorney's or representative's USCIS online account number, if "
                    "any (12 characters). Not the applicant's (that is Part 2 item 9). Blank when the profile says has_uscis_online_account \"no\".",
                },
                choices={"CheckBox1": {"g28_attached": "1"}},
            ),
            "reason_for_applying": q(
                "Part 1, Items 1.a-1.c: Reason for applying (initial, replacement, renewal)",
                ["Part1_Checkbox"],
                ["Part1_Checkbox"],
                notes={
                    "Part1_Checkbox": "One box only. Renewal (1.c) needs a copy of the previous EAD. A "
                    "correction needed because of USCIS error is not 1.b: it needs no new I-765.",
                },
                choices={
                    "Part1_Checkbox": {"initial": "1", "replacement": "2", "renewal": "3"},
                },
            ),
            "applicant_name": q(
                "Part 2, Items 1.a-1.c: Your full legal name",
                ["Line1a_FamilyName", "Line1b_GivenName", "Line1c_MiddleName"],
                ["Line1a_FamilyName", "Line1b_GivenName"],
                notes={
                    "Line1a_FamilyName": "Global: also fills Part 6 item 1.a.",
                    "Line1b_GivenName": "Global: also fills Part 6 item 1.b.",
                    "Line1c_MiddleName": "Global: also fills Part 6 item 1.c. Blank if none.",
                },
            ),
            "other_names_used": q(
                "Part 2, Items 2.a-4.c: Other names used (aliases, maiden name, nicknames)",
                ["Line2a_FamilyName", "Line2b_GivenName", "Line2c_MiddleName", "Line3a_FamilyName[1]",
                 "Line3b_GivenName[1]", "Line3c_MiddleName[1]", "Line3a_FamilyName[0]", "Line3b_GivenName[0]",
                 "Line3c_MiddleName[0]"],
                ["Line2a_FamilyName", "Line2b_GivenName"],
                allowed=FILLED_OR_NA,
                notes={
                    "Line2a_FamilyName": "Item 2.a, the first other name.",
                    "Line3a_FamilyName[1]": "Item 3.a, the second other name. Item 3 is index [1].",
                    "Line3b_GivenName[1]": "Item 3.b.",
                    "Line3c_MiddleName[1]": "Item 3.c.",
                    "Line3a_FamilyName[0]": "Item 4.a, the third other name. Item 4 is index [0], above item 3's "
                    "[1] in the field list but below it on the page.",
                    "Line3b_GivenName[0]": "Item 4.b.",
                    "Line3c_MiddleName[0]": "Item 4.c.",
                },
            ),
            "mailing_address": q(
                "Part 2, Items 5.a-5.f: Your U.S. mailing address",
                ["Line4a_InCareofName", "Line4b_StreetNumberName", "Pt2Line5_Unit", "Pt2Line5_AptSteFlrNumber",
                 "Pt2Line5_CityOrTown", "Pt2Line5_State", "Pt2Line5_ZipCode"],
                ["Line4b_StreetNumberName", "Pt2Line5_CityOrTown", "Pt2Line5_State", "Pt2Line5_ZipCode"],
                notes={
                    "Line4a_InCareofName": "Item 5.a (named 'Line4a'), in care of name, if any (maxlen 34).",
                    "Line4b_StreetNumberName": "Item 5.b (named 'Line4b'), street number and name (maxlen 34). "
                    "The EAD is mailed here; use the attorney's address only if the client wants the card sent "
                    "there (Instructions, Item Numbers 5.a-5.f). In a VAWA matter, use the safe mailing address the "
                    "matter contract sets (the attorney's office unless the attorney gives another); item 6 is then "
                    "No unless the client lives there, and items 7.a-7.e give the physical address from the record.",
                    "Pt2Line5_AptSteFlrNumber": UNIT_NUMBER,
                    "Pt2Line5_CityOrTown": "maxlen 20.",
                    "Pt2Line5_State": STATE,
                    "Pt2Line5_ZipCode": ZIP,
                },
                choices={"Pt2Line5_Unit": dict(UNIT)},
            ),
            "mailing_same_as_physical": q(
                "Part 2, Item 6: Is your current mailing address the same as your physical address?",
                ["Part2Line5_Checkbox"],
                ["Part2Line5_Checkbox"],
                notes={
                    "Part2Line5_Checkbox": "Item 6, despite the 'Line5' name. 'No' requires physical_address "
                    "(items 7.a-7.e).",
                },
                choices={"Part2Line5_Checkbox": dict(YES_NO)},
            ),
            "physical_address": q(
                "Part 2, Items 7.a-7.e: U.S. physical address (if different from mailing)",
                ["Pt2Line7_StreetNumberName", "Pt2Line7_Unit", "Pt2Line7_AptSteFlrNumber", "Pt2Line7_CityOrTown",
                 "Pt2Line7_State", "Pt2Line7_ZipCode"],
                ["Pt2Line7_StreetNumberName", "Pt2Line7_CityOrTown", "Pt2Line7_State", "Pt2Line7_ZipCode"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt2Line7_StreetNumberName": "Only when item 6 is 'No'; otherwise not_applicable (maxlen 34).",
                    "Pt2Line7_AptSteFlrNumber": UNIT_NUMBER,
                    "Pt2Line7_CityOrTown": "maxlen 20.",
                    "Pt2Line7_State": STATE,
                    "Pt2Line7_ZipCode": ZIP,
                },
                choices={"Pt2Line7_Unit": dict(UNIT)},
            ),
            "a_number": q(
                "Part 2, Item 8: Alien Registration Number (A-Number), if any",
                ["Line7_AlienNumber"],
                ["Line7_AlienNumber"],
                allowed=FILLED_OR_NA,
                notes={
                    "Line7_AlienNumber": "Item 8 (named 'Line7'). 9 digits, no 'A'; pad an 8-digit number with a "
                    "leading zero. Global: also fills Part 6 item 2.",
                },
            ),
            "uscis_online_account_number": q(
                "Part 2, Item 9: USCIS Online Account Number, if any",
                ["Line8_ElisAccountNumber"],
                ["Line8_ElisAccountNumber"],
                allowed=FILLED_OR_NA,
                notes={
                    "Line8_ElisAccountNumber": "Item 9 (named 'Line8'). The applicant's own 12-character account "
                    "number, not the attorney's.",
                },
            ),
            "sex": q(
                "Part 2, Item 10: Sex",
                ["Line9_Checkbox"],
                ["Line9_Checkbox"],
                notes={
                    "Line9_Checkbox": "Item 10 (named 'Line9'). 'Y' is Male and 'N' is Female; use the choices.",
                },
                choices={"Line9_Checkbox": {"male": "Y", "female": "N"}},
            ),
            "marital_status": q(
                "Part 2, Item 11: Marital status",
                ["Line10_Checkbox"],
                ["Line10_Checkbox"],
                notes={
                    "Line10_Checkbox": "Item 11 (named 'Line10'). Status on the date of filing.",
                },
                choices={
                    "Line10_Checkbox": {
                        "single": "Single",
                        "married": "Married",
                        "divorced": "Divorced",
                        "widowed": "Widowed",
                    },
                },
            ),
            "previously_filed_i765": q(
                "Part 2, Item 12: Have you previously filed Form I-765?",
                ["Line19_Checkbox"],
                ["Line19_Checkbox"],
                notes={
                    "Line19_Checkbox": "Item 12, despite the 'Line19' name (Line19_DOB is item 16). 'Yes' calls "
                    "for copies of prior EADs, if available.",
                },
                choices={"Line19_Checkbox": dict(YES_NO)},
            ),
            "social_security_number": q(
                "Part 2, Item 13: Social Security number (SSN), if known",
                ["Line12b_SSN"],
                ["Line12b_SSN"],
                allowed=FILLED_OR_NA,
                notes={
                    "Line12b_SSN": "Item 13 (named 'Line12b'). 9 digits, no dashes. The only Social Security "
                    "item on this edition: there are no SSA card-issuance or consent questions.",
                },
            ),
            "citizenship": q(
                "Part 2, Items 14.a-14.b: Country or countries of citizenship or nationality",
                ["Line17a_CountryOfBirth", "Line17b_CountryOfBirth"],
                ["Line17a_CountryOfBirth"],
                notes={
                    "Line17a_CountryOfBirth": "Item 14.a, a country of CITIZENSHIP despite the name; country of "
                    "birth is Line18c_CountryOfBirth. Stateless: write 'Stateless' and explain in Part 6.",
                    "Line17b_CountryOfBirth": "Item 14.b, a second country of citizenship, if any. More go in "
                    "Part 6.",
                },
            ),
            "place_and_date_of_birth": q(
                "Part 2, Items 15.a-16: Place of birth (city, state or province, country) and date of birth",
                ["Line18a_CityTownOfBirth", "Line18b_CityTownOfBirth", "Line18c_CountryOfBirth", "Line19_DOB"],
                ["Line18a_CityTownOfBirth", "Line18c_CountryOfBirth", "Line19_DOB"],
                notes={
                    "Line18a_CityTownOfBirth": "Item 15.a, city, town or village of birth.",
                    "Line18b_CityTownOfBirth": "Item 15.b, STATE or PROVINCE of birth despite the name; N/A if "
                    "none.",
                    "Line18c_CountryOfBirth": "Item 15.c, the country as it was named at the time of birth.",
                    "Line19_DOB": "Item 16 (named 'Line19'). " + DATE,
                },
            ),
            "i94_number": q(
                "Part 2, Item 17: Form I-94 Arrival-Departure Record Number, if any",
                ["Line20a_I94Number"],
                ["Line20a_I94Number"],
                allowed=FILLED_OR_NA,
                notes={
                    "Line20a_I94Number": "Item 17 (named 'Line20a'). 11 characters (comb box). The form has no box "
                    "for the I-94 expiration date.",
                },
            ),
            "passport_or_travel_document": q(
                "Part 2, Items 18-21: Passport or travel document number, issuing country, expiration date",
                ["Line20b_Passport", "Line20c_TravelDoc", "Line20d_CountryOfIssuance", "Line20e_ExpDate"],
                ["Line20d_CountryOfIssuance", "Line20e_ExpDate"],
                allowed=FILLED_OR_NA,
                notes={
                    "Line20b_Passport": "Item 18, number of the most recently issued passport, even if expired.",
                    "Line20c_TravelDoc": "Item 19, travel document number, if any.",
                    "Line20d_CountryOfIssuance": "Item 20, country that issued the passport or travel document.",
                    "Line20e_ExpDate": "Item 21, expiration date of that passport or travel document. " + DATE,
                },
            ),
            "last_arrival_and_status": q(
                "Part 2, Items 22-26: Last arrival date and place, status at arrival, current status, SEVIS",
                ["Line21_DateOfLastEntry", "place_entry", "Line23_StatusLastEntry", "Line24_CurrentStatus",
                 "Line26_SEVISnumber"],
                ["Line21_DateOfLastEntry", "place_entry", "Line23_StatusLastEntry", "Line24_CurrentStatus"],
                notes={
                    "Line21_DateOfLastEntry": "Item 22 (named 'Line21'), date of last arrival, on or about. " + DATE,
                    "place_entry": "Item 23, place of last arrival (port of entry).",
                    "Line23_StatusLastEntry": "Item 24 (named 'Line23'), status at last arrival, e.g. 'B-2 visitor', "
                    "'F-1 student', 'parolee' or 'no status'.",
                    "Line24_CurrentStatus": "Item 25 (named 'Line24'), current status or category, e.g. 'F-1 "
                    "student', 'asylee', 'parolee', 'deferred action' or 'no status'.",
                    "Line26_SEVISnumber": "Item 26, SEVIS number if any, without the printed 'N-' (maxlen 11).",
                },
            ),
            "eligibility_category": q(
                "Part 2, Item 27: Eligibility category, e.g. (a)(5), (c)(9), (c)(8), (c)(3)(C)",
                ["section_1", "section_2", "section_3"],
                ["section_1", "section_2"],
                notes={
                    "section_1": "First box: the letter only, lower case, no parentheses (the form prints them). "
                    "'a' for (a)(5); 'c' for (c)(9), (c)(8), (c)(3)(C), (c)(26), (c)(35), (c)(36). "
                    + CATEGORY_NOTE,
                    "section_2": "Middle box: the number only (maxlen 3). '5' for (a)(5), '9' for (c)(9), '8' for "
                    "(c)(8), '3' for (c)(3)(C), '26' for (c)(26), '35' for (c)(35), '36' for (c)(36).",
                    "section_3": "Last box: the third element only, if the category has one: 'C' for (c)(3)(C), "
                    "'iii' for (c)(17)(iii). Blank for (a)(5), (c)(9), (c)(8), (c)(26), (c)(35), (c)(36).",
                },
            ),
            "stem_opt_c3c": q(
                "Part 2, Items 28.a-28.c: (c)(3)(C) STEM OPT degree, E-Verify employer name and ID",
                ["Line27a_Degree", "Line27b_Everify", "Line27c_EverifyIDNumber"],
                ["Line27a_Degree", "Line27b_Everify", "Line27c_EverifyIDNumber"],
                allowed=FILLED_OR_NA,
                notes={
                    "Line27a_Degree": "Category (c)(3)(C) only. Item 28.a (named 'Line27a'). Degree level and "
                    "major, but the box holds 16 characters (letters, spaces, hyphens): abbreviate (e.g. 'MS "
                    "Computer Sci') and give the full degree in Part 6 if it does not fit.",
                    "Line27b_Everify": "Item 28.b, employer's name exactly as listed in E-Verify.",
                    "Line27c_EverifyIDNumber": "Item 28.c, employer's E-Verify company ID or a valid E-Verify client "
                    "company ID.",
                },
            ),
            "h4_spouse_c26": q(
                "Part 2, Item 29: (c)(26) receipt number of the H-1B spouse's most recent I-797 for Form I-129",
                ["Line28_ReceiptNumber"],
                ["Line28_ReceiptNumber"],
                allowed=FILLED_OR_NA,
                notes={
                    "Line28_ReceiptNumber": "Category (c)(26) only. Item 29 (named 'Line28'). 13 characters, e.g. "
                    "three letters and ten digits, no dashes.",
                },
            ),
            "pending_asylum_c8_arrests": q(
                "Part 2, Item 30: (c)(8) Have you EVER been arrested for and/or convicted of any crime?",
                ["PtLine29_YesNo"],
                ["PtLine29_YesNo"],
                allowed=FILLED_OR_NA,
                notes={
                    "PtLine29_YesNo": "Category (c)(8) only. Item 30, despite the 'Line29' name. Criminal history "
                    "question: a 'No' rests on the record and the client's review before signing; 'Yes' needs "
                    "certified court dispositions (Instructions, Special Filing Instructions for (c)(8)).",
                },
                choices={"PtLine29_YesNo": dict(YES_NO)},
            ),
            "compelling_circumstances_c35_c36": q(
                "Part 2, Items 31.a-31.b: (c)(35)/(c)(36) I-140 receipt number and arrest/conviction question",
                ["Line30a_ReceiptNumber", "PtLine30b_YesNo"],
                ["Line30a_ReceiptNumber", "PtLine30b_YesNo"],
                allowed=FILLED_OR_NA,
                notes={
                    "Line30a_ReceiptNumber": "Categories (c)(35) and (c)(36) only. Item 31.a (named 'Line30a'). "
                    "(c)(35): the receipt number of the applicant's own I-140 approval notice; (c)(36): the "
                    "spouse's or parent's. 13 characters, no dashes.",
                    "PtLine30b_YesNo": "Item 31.b. Criminal history question; 'Yes' needs court dispositions "
                    "(Instructions, Employment-Based Nonimmigrant Categories, Items 8-9).",
                },
                choices={"PtLine30b_YesNo": dict(YES_NO)},
            ),
            "applicant_statement": q(
                "Part 3, Items 1.a-2: Applicant's statement (reads English or used an interpreter; preparer used)",
                ["Pt3Line1Checkbox", "Pt3Line1b_Language", "Part3_Checkbox", "Pt3Line2_RepresentativeName"],
                ["Pt3Line1Checkbox"],
                notes={
                    "Pt3Line1Checkbox": "Item 1.a or 1.b, one only.",
                    "Pt3Line1b_Language": "Item 1.b only: the language the interpreter used. Must match Part 4's "
                    "certification language (Part4_NameofLanguage).",
                    "Part3_Checkbox": "Item 2: select when an attorney or other preparer (Part 5) prepared the form.",
                    "Pt3Line2_RepresentativeName": "Item 2: the preparer's name, printed in the sentence 'the "
                    "preparer named in Part 5., ___, prepared this application'. Fill it whenever Part3_Checkbox "
                    "is selected.",
                },
                choices={
                    "Pt3Line1Checkbox": {"reads_english": "A", "interpreter": "B"},
                    "Part3_Checkbox": {"preparer_used": "C"},
                },
            ),
            "applicant_contact": q(
                "Part 3, Items 3-5: Applicant's daytime phone, mobile phone, email",
                ["Pt3Line3_DaytimePhoneNumber1", "Pt3Line4_MobileNumber1", "Pt3Line5_Email"],
                ["Pt3Line3_DaytimePhoneNumber1"],
                notes={
                    "Pt3Line3_DaytimePhoneNumber1": PHONE,
                    "Pt3Line4_MobileNumber1": PHONE + " If any.",
                    "Pt3Line5_Email": "If any (maxlen 38).",
                },
            ),
            "abc_settlement_c8": q(
                "Part 3, Item 6: Salvadoran or Guatemalan national eligible for ABC settlement benefits",
                ["Pt4Line6_Checkbox"],
                ["Pt4Line6_Checkbox"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt4Line6_Checkbox": "Part 3 item 6, despite the 'Pt4' name. Category (c)(8) ABC class members "
                    "only (Instructions, Part 3 Item Number 6); not_applicable for everyone else.",
                },
                choices={"Pt4Line6_Checkbox": {"abc_class_member": "A"}},
            ),
            "applicant_signature": q(
                "Part 3, Items 7.a-7.b: Applicant's signature and date",
                ["Pt3Line7a_Signature", "Pt3Line7b_DateofSignature"],
                ["Pt3Line7b_DateofSignature"],
                allowed=SIGNATURE_STATUSES,
                notes={
                    "Pt3Line7a_Signature": SIGNATURE + " A parent or legal guardian signs for an applicant under 14.",
                    "Pt3Line7b_DateofSignature": SIGNATURE_DATE,
                },
            ),
            "interpreter_block": q(
                "Part 4, Items 1.a-6 and certification: Interpreter's name, address, contact, language",
                ["Pt4Line1a_InterpreterFamilyName", "Pt4Line1b_InterpreterGivenName",
                 "Pt4Line2_InterpreterBusinessorOrg", "Pt5Line3a_StreetNumberName", "Pt5Line3b_Unit",
                 "Pt5Line3b_AptSteFlrNumber", "Pt5Line3c_CityOrTown", "Pt5Line3d_State", "Pt5Line3e_ZipCode",
                 "Pt5Line3f_Province", "Pt5Line3g_PostalCode", "Pt5Line3h_Country",
                 "Pt4Line4_InterpreterDaytimeTelephone", "Pt4Line5_MobileNumber", "Pt4Line6_Email",
                 "Part4_NameofLanguage"],
                ["Pt4Line1a_InterpreterFamilyName", "Pt4Line1b_InterpreterGivenName", "Pt5Line3a_StreetNumberName",
                 "Pt5Line3c_CityOrTown", "Pt5Line3h_Country", "Pt4Line4_InterpreterDaytimeTelephone",
                 "Part4_NameofLanguage"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt4Line2_InterpreterBusinessorOrg": "Item 2, if any (maxlen 34).",
                    "Pt5Line3a_StreetNumberName": "Part 4 item 3.a, the INTERPRETER's street, despite the 'Pt5' "
                    "name (Pt6Line3* is the preparer's address). maxlen 34.",
                    "Pt5Line3b_Unit": UNIT_PAGE5_NOTE,
                    "Pt5Line3b_AptSteFlrNumber": UNIT_NUMBER,
                    "Pt5Line3c_CityOrTown": "Part 4 item 3.c (maxlen 20).",
                    "Pt5Line3d_State": STATE,
                    "Pt5Line3e_ZipCode": ZIP,
                    "Pt5Line3f_Province": FOREIGN_ONLY,
                    "Pt5Line3g_PostalCode": FOREIGN_ONLY,
                    "Pt5Line3h_Country": "Part 4 item 3.h.",
                    "Pt4Line4_InterpreterDaytimeTelephone": PHONE,
                    "Pt4Line5_MobileNumber": PHONE + " If any.",
                    "Pt4Line6_Email": "Part 4 item 6, the interpreter's email, if any (maxlen 38). Not the Part 3 "
                    "item 6 ABC box (Pt4Line6_Checkbox).",
                    "Part4_NameofLanguage": "The language in the interpreter's certification; same as Part 3 item "
                    "1.b (Pt3Line1b_Language).",
                },
                choices={"Pt5Line3b_Unit": dict(UNIT_PAGE5)},
            ),
            "interpreter_signature": q(
                "Part 4, Items 7.a-7.b: Interpreter's signature and date",
                ["Pt4Line6a_Signature", "Pt4Line6b_DateofSignature"],
                ["Pt4Line6b_DateofSignature"],
                allowed=[PENDING_SIGNATURE, FILLED, NOT_APPLICABLE],
                notes={
                    "Pt4Line6a_Signature": "Item 7.a (named 'Pt4Line6a'). " + SIGNATURE,
                    "Pt4Line6b_DateofSignature": "Item 7.b (named 'Pt4Line6b'). " + SIGNATURE_DATE,
                },
            ),
            "preparer_block": q(
                "Part 5, Items 1.a-7.b: Preparer's name, business, address, contact and statement",
                ["Pt5Line1a_PreparerFamilyName", "Pt5Line1b_PreparerGivenName", "Pt5Line2_BusinessName",
                 "Pt6Line3a_StreetNumberName", "Pt6Line3b_Unit", "Pt6Line3b_AptSteFlrNumber", "Pt6Line3c_CityOrTown",
                 "Pt6Line3d_State", "Pt6Line3e_ZipCode", "Pt6Line3f_Province", "Pt6Line3g_PostalCode",
                 "Pt6Line3h_Country", "Pt5Line4_DaytimePhoneNumber1", "Pt5Line5_PreparerFaxNumber", "Pt5Line6_Email",
                 "Part5Line7_Checkbox", "Part5Line7b_Checkbox"],
                ["Pt5Line1a_PreparerFamilyName", "Pt5Line1b_PreparerGivenName", "Pt6Line3a_StreetNumberName",
                 "Pt6Line3c_CityOrTown", "Pt6Line3h_Country", "Pt5Line4_DaytimePhoneNumber1", "Part5Line7_Checkbox"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt5Line1a_PreparerFamilyName": "From the attorney profile when the attorney prepared the form; "
                    "never from another matter.",
                    "Pt5Line2_BusinessName": "Item 2, firm or organization, if any (maxlen 34).",
                    "Pt6Line3a_StreetNumberName": "Part 5 item 3.a, the PREPARER's street, despite the 'Pt6' name "
                    "(Pt5Line3* is the interpreter's address). maxlen 34.",
                    "Pt6Line3b_Unit": UNIT_PAGE5_NOTE,
                    "Pt6Line3b_AptSteFlrNumber": UNIT_NUMBER,
                    "Pt6Line3c_CityOrTown": "Part 5 item 3.c (maxlen 20).",
                    "Pt6Line3d_State": STATE,
                    "Pt6Line3e_ZipCode": ZIP,
                    "Pt6Line3f_Province": FOREIGN_ONLY,
                    "Pt6Line3g_PostalCode": FOREIGN_ONLY,
                    "Pt6Line3h_Country": "Part 5 item 3.h.",
                    "Pt5Line4_DaytimePhoneNumber1": PHONE,
                    "Pt5Line5_PreparerFaxNumber": "Item 5, the preparer's MOBILE number, if any, despite the 'Fax' "
                    "name. " + PHONE,
                    "Pt5Line6_Email": "If any (maxlen 38).",
                    "Part5Line7_Checkbox": "Item 7.a (not an attorney or accredited representative) or 7.b "
                    "(attorney or accredited representative).",
                    "Part5Line7b_Checkbox": "Item 7.b only: whether the representation extends beyond preparing "
                    "this application. Blank with 7.a. An attorney who files a G-28 normally answers 'extends'.",
                },
                choices={
                    "Pt6Line3b_Unit": dict(UNIT_PAGE5),
                    "Part5Line7_Checkbox": {"not_attorney": "A", "attorney_or_accredited_rep": "B"},
                    "Part5Line7b_Checkbox": {"extends": "Y", "does_not_extend": "N"},
                },
            ),
            "preparer_signature": q(
                "Part 5, Items 8.a-8.b: Preparer's signature and date",
                ["Pt5Line8a_Signature", "Pt5Line8b_DateofSignature"],
                ["Pt5Line8b_DateofSignature"],
                allowed=[PENDING_SIGNATURE, FILLED, NOT_APPLICABLE],
                notes={
                    "Pt5Line8a_Signature": SIGNATURE,
                    "Pt5Line8b_DateofSignature": SIGNATURE_DATE,
                },
            ),
            "additional_information": q(
                "Part 6, Items 3.a-7.d: Additional information (page, part, item, text)",
                ["Pt6Line3a_PageNumber", "Pt6Line3b_PartNumber", "Pt6Line3c_ItemNumber", "Pt6Line4d_AdditionalInfo[1]",
                 "Pt6Line4a_PageNumber", "Pt6Line4b_PartNumber", "Pt6Line4c_ItemNumber", "Pt6Line4d_AdditionalInfo[0]",
                 "Pt6Line5a_PageNumber", "Pt6Line5b_PartNumber", "Pt6Line5c_ItemNumber", "Pt6Line5d_AdditionalInfo",
                 "Pt6Line6a_PageNumber", "Pt6Line6b_PartNumber", "Pt6Line6c_ItemNumber", "Pt6Line6d_AdditionalInfo",
                 "Pt6Line7a_PageNumber", "Pt6Line7b_PartNumber", "Pt6Line7c_ItemNumber", "Pt6Line7d_AdditionalInfo"],
                ["Pt6Line3a_PageNumber", "Pt6Line3b_PartNumber", "Pt6Line3c_ItemNumber", "Pt6Line4d_AdditionalInfo[1]"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt6Line3a_PageNumber": "Item 3.a, page number (maxlen 2). Part 6 items 1-2 (name, A-Number) "
                    "fill themselves from Part 2.",
                    "Pt6Line3b_PartNumber": "maxlen 6, e.g. '2'.",
                    "Pt6Line3c_ItemNumber": "maxlen 6, e.g. '28.a'.",
                    "Pt6Line4d_AdditionalInfo[1]": "Item 3.d's text box. There is no Pt6Line3d: item 3.d is "
                    "Pt6Line4d_AdditionalInfo[1]. About 9 lines. " + PART6_TEXT,
                    "Pt6Line4d_AdditionalInfo[0]": "Item 4.d's text box. About 9 lines. " + PART6_TEXT,
                    "Pt6Line5d_AdditionalInfo": "Item 5.d. About 6 lines (a shorter box). " + PART6_TEXT,
                    "Pt6Line6d_AdditionalInfo": "Item 6.d. About 8 lines. " + PART6_TEXT,
                    "Pt6Line7d_AdditionalInfo": "Item 7.d. About 9 lines. " + PART6_TEXT
                    + " More entries go on a separate sheet with the name, A-Number, page, part and item, "
                    "signed and dated.",
                },
            ),
        },
    },
}

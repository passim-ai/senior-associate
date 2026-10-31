"""Question schema for Form G-28, Notice of Entry of Appearance as Attorney or Accredited Representative.

Built against the 09/17/18 edition, the one uscis.gov/g-28 lists (it says the 09/17/18 and 05/23/18
editions may still be used despite the 05/31/2021 expiration printed on the form). Field list:
schemas/fields/G-28.json. Every box on the form except the barcode belongs to exactly one question.

The attorney-side questions (Part 1, Part 2 item 1, Part 5 item 1) come only from the attorney
profile; their field notes name the profile key behind each box (REFERENCE.md, "Attorney profile: the G-28 mapping").
The audit's G-28 rules (audit_prepared_forms.audit_g28) require the boxes listed in the
non-empty lists of attorney_block, attorney_eligibility and representation_scope, and the
I-130A attorney box is compared with this form's bar number, online account number and name.
Both address unit groups on this form carry padded on-states.
"""
from __future__ import annotations

from _common import DATE, FILLED_OR_NA, FOREIGN_ONLY, OPTIONAL_SIGNATURE, SIGNATURE_STATUSES, UNIT, q

EDITION = "09/17/18"
FIELD_LIST = "G-28.json"

STATE = "U.S. address only: 2-letter state code (drop-down)."
ZIP = "U.S. address only: 5-digit ZIP Code."
PHONE = "10 digits, no punctuation (maxlen 10)."


SCHEMAS = {
    "g28_represented_client": {
        "kind": "g-28",
        "edition": EDITION,
        "field_list": FIELD_LIST,
        "description": (
            "Form G-28 for one represented person (petitioner, applicant, beneficiary), filed with a USCIS "
            "application or petition; one plan per client."
        ),
        "notes": [
            "Edition 09/17/18: uscis.gov/g-28 lists it and says the 09/17/18 and 05/23/18 editions may still be "
            "used despite the 05/31/2021 expiration printed on the form.",
            "One G-28 per represented party, each its own plan and filing copy ('G-28 - Petitioner', "
            "'G-28 - Beneficiary'). The attorney parts are identical on every copy; Part 3 and Part 4 are the "
            "client's.",
            "Attorney boxes (Part 1, Part 2 item 1, Part 5) come only from the attorney profile; each field note "
            "names its profile key. A key the profile lacks leaves its question missing with an attorney_action "
            "open item. Never invent a value or reuse one from another matter.",
            "Names mislead: Line6_EMail is the attorney's MOBILE phone (item 5) and Line7_MobileTelephoneNumber "
            "the attorney's EMAIL (item 6); Checkbox1dAmNot/Checkbox1dAm are item 1.c; Line2c_DateExpires is the "
            "date of accreditation; Part 3 items 6-13 are Pt3Line5*, Line9-Line12*; Part 4 items 1.a-1.c are "
            "Pt4Line2a-2c; the client's signature is P5_Line6a; Part 6 boxes are Pt9*.",
            "Global fields share one value: the client's name (Pt3Line5a/5b/5c) also prints in Part 6 item 1, "
            "and the unit groups and Part 3 item 5 (Line4_Checkbox) are single groups. Map only the base name.",
            "Unbound in the XFA template (Adobe shows them empty unless fill binds them, which it does for any "
            "box it fills): Line3_Date, Line2c_DateExpires, and every Part 6 page, part and item box.",
            "The audit requires Part 3 item 1.a (USCIS) and 1.b, the attorney's name, address, phone and email, "
            "licensing authority, bar number and firm name, and warns while any client contact or mailing box "
            "(mobile and email included) is blank.",
        ],
        "required_questions": {
            "attorney_uscis_online_account": {
                **q(
                    "Part 1, Item 1: Attorney's USCIS Online Account Number (if any)",
                    ["Pt1Line1_USCISOnlineAcctNumber"],
                    ["Pt1Line1_USCISOnlineAcctNumber"],
                    allowed=FILLED_OR_NA,
                    notes={
                        "Pt1Line1_USCISOnlineAcctNumber": (
                            "Profile key uscis_online_account_number; 12 digits. not_applicable, with no open item, "
                            "when the profile's has_uscis_online_account is \"no\" (the skeleton and the audit apply "
                            "that themselves). A profile with neither key leaves this question missing "
                            "(attorney_action). The I-130A attorney box must match it."
                        ),
                    },
                ),
                # The attorney said in "Your details" that they have no USCIS online account.
                "not_applicable_when_profile": {"has_uscis_online_account": "no"},
            },
            "attorney_block": q(
                "Part 1, Items 2.a-7: Attorney's name, address, daytime phone, mobile phone, email, fax",
                ["Pt1Line2a_FamilyName", "Pt1Line2b_GivenName", "Pt1Line2c_MiddleName", "Line3a_StreetNumber",
                 "Line3b_Unit", "Line3b_AptSteFlrNumber", "Line3c_CityOrTown", "Line3d_State", "Line3e_ZipCode",
                 "Line3f_Province", "Line3g_PostalCode", "Line3h_Country", "Line4_DaytimeTelephoneNumber",
                 "Line6_EMail", "Line7_MobileTelephoneNumber", "Pt1ItemNumber7_FaxNumber"],
                ["Pt1Line2a_FamilyName", "Pt1Line2b_GivenName", "Line3a_StreetNumber", "Line3c_CityOrTown",
                 "Line3d_State", "Line3e_ZipCode", "Line3h_Country", "Line4_DaytimeTelephoneNumber",
                 "Line7_MobileTelephoneNumber"],
                notes={
                    "Pt1Line2a_FamilyName": (
                        "Profile key attorney_name (family name). If the name does not split cleanly into family and "
                        "given names, ask. The I-130A preparer check compares it."
                    ),
                    "Pt1Line2b_GivenName": "Profile key attorney_name (given name).",
                    "Pt1Line2c_MiddleName": "Profile key attorney_name (middle name), if any.",
                    "Line3a_StreetNumber": "Profile key mailing_address: street number and name (maxlen 34).",
                    "Line3b_Unit": (
                        "Profile key mailing_address: unit type. One global group; set it with "
                        "Line3b_AptSteFlrNumber or leave both blank."
                    ),
                    "Line3b_AptSteFlrNumber": "Profile key mailing_address: unit number (maxlen 6).",
                    "Line3c_CityOrTown": "Profile key mailing_address: city (maxlen 20).",
                    "Line3d_State": "Profile key mailing_address. " + STATE,
                    "Line3e_ZipCode": "Profile key mailing_address. " + ZIP,
                    "Line3f_Province": FOREIGN_ONLY,
                    "Line3g_PostalCode": FOREIGN_ONLY,
                    "Line3h_Country": "Profile key mailing_address: country (USA or United States for a U.S. office).",
                    "Line4_DaytimeTelephoneNumber": "Item 4. Profile key phone. " + PHONE,
                    "Line6_EMail": (
                        "Item 5, the attorney's MOBILE phone, despite the EMail name (maxlen 10). No profile key: "
                        "leave blank unless the attorney gives one."
                    ),
                    "Line7_MobileTelephoneNumber": (
                        "Item 6, the attorney's EMAIL address, despite the Mobile name (maxlen 38). Profile key email."
                    ),
                    "Pt1ItemNumber7_FaxNumber": "Item 7, fax, if any (maxlen 10). No profile key: blank unless given.",
                },
                choices={"Line3b_Unit": dict(UNIT)},
            ),
            "attorney_eligibility": q(
                "Part 2, Items 1.a, 1.b, 1.d: I am an attorney (licensing authority), bar number, law firm",
                ["CheckBox1", "Pt2Line1a_LicensingAuthority", "Pt2Line1b_BarNumber",
                 "Pt2Line1d_NameofFirmOrOrganization"],
                ["CheckBox1", "Pt2Line1a_LicensingAuthority", "Pt2Line1b_BarNumber",
                 "Pt2Line1d_NameofFirmOrOrganization"],
                notes={
                    "CheckBox1": "Item 1.a. Select for an attorney (USCIS rejects a G-28 without Part 2 item 1 or 2).",
                    "Pt2Line1a_LicensingAuthority": (
                        "Profile key licensing_authority (maxlen 66), e.g. 'Supreme Court of Texas'. Every "
                        "jurisdiction where the attorney is admitted; more go in Part 6, citing Page 1, Part 2, Item "
                        "1.a."
                    ),
                    "Pt2Line1b_BarNumber": (
                        "Profile key bar_number (maxlen 10). The audit requires it and compares it with the I-130A "
                        "attorney box."
                    ),
                    "Pt2Line1d_NameofFirmOrOrganization": (
                        "Item 1.d. Profile key firm_name (maxlen 30); the audit requires it. A longer name goes in "
                        "Part 6."
                    ),
                },
                choices={"CheckBox1": {"I am an attorney": "Y"}},
            ),
            "attorney_discipline": q(
                "Part 2, Item 1.c: I am not / am subject to any order suspending, enjoining, restraining, "
                "disbarring, or otherwise restricting me in the practice of law",
                ["Checkbox1dAmNot", "Checkbox1dAm"],
                notes={
                    "Checkbox1dAmNot": (
                        "Item 1.c despite the '1d' name. Profile key subject_to_discipline_order: 'no' -> this box "
                        "(on-state Y). Two separate boxes: set exactly one. If the key is missing, leave both blank "
                        "and keep the question missing (attorney_action); never assume 'am not'."
                    ),
                    "Checkbox1dAm": (
                        "Item 1.c. Profile key subject_to_discipline_order: 'yes' -> this box (on-state N, not Y). "
                        "Then put discipline_order_details in Part 6, citing Page 1, Part 2, Item 1.c."
                    ),
                },
                choices={
                    "Checkbox1dAmNot": {"am not": "Y"},
                    "Checkbox1dAm": {"am": "N"},
                },
            ),
            "accredited_representative": q(
                "Part 2, Items 2.a-2.c: Accredited representative of a recognized organization, organization name, "
                "date of accreditation",
                ["CheckBox2", "Line2b_NameofOrganization", "Line2c_DateExpires"],
                ["CheckBox2", "Line2b_NameofOrganization", "Line2c_DateExpires"],
                allowed=FILLED_OR_NA,
                notes={
                    "CheckBox2": "Accredited representatives only; not_applicable for an attorney.",
                    "Line2b_NameofOrganization": "Recognized organization (maxlen 30).",
                    "Line2c_DateExpires": (
                        "Item 2.c, the date of ACCREDITATION despite the 'Expires' name. " + DATE + " Unbound in the "
                        "XFA template; fill binds it when filled."
                    ),
                },
                choices={"CheckBox2": {"I am an accredited representative": "Y"}},
            ),
            "associated_attorney": q(
                "Part 2, Item 3: I am associated with the attorney or representative of record (limited purpose)",
                ["CheckBox3", "Line3_NameofAttorneyOrRep"],
                ["CheckBox3", "Line3_NameofAttorneyOrRep"],
                allowed=FILLED_OR_NA,
                notes={
                    "CheckBox3": (
                        "Only for a stand-in appearing for a limited purpose for the attorney of record (filed in "
                        "person); normally not_applicable."
                    ),
                    "Line3_NameofAttorneyOrRep": "Name of the attorney of record (maxlen 30).",
                },
                choices={"CheckBox3": {"I am associated with": "Y"}},
            ),
            "law_student": q(
                "Part 2, Items 4.a-4.b: Law student or law graduate under the attorney's supervision, and name",
                ["CheckBox4", "Line4b_LawStudent"],
                ["CheckBox4", "Line4b_LawStudent"],
                allowed=FILLED_OR_NA,
                notes={
                    "CheckBox4": (
                        "Only when a law student or graduate appears on this same G-28; then law_student_signature "
                        "is required too. Normally not_applicable."
                    ),
                    "Line4b_LawStudent": "Name of the law student or law graduate (maxlen 38).",
                },
                choices={"CheckBox4": {"I am a law student or law graduate": "Y"}},
            ),
            "representation_scope": q(
                "Part 3, Items 1.a-5: Appearance before USCIS (form numbers), receipt number, and the client's role "
                "(Applicant, Petitioner, Requestor, Beneficiary/Derivative, Respondent)",
                ["Line1a_USCIS", "Line1b_ListFormNumber", "Line2a_ICE", "Line2b_ListMatter", "Line3a_CBP",
                 "Line3b_ListSpecificMatter", "Pt3Line4_ReceiptNumber", "Line4_Checkbox"],
                ["Line1a_USCIS", "Line1b_ListFormNumber", "Line4_Checkbox"],
                notes={
                    "Line1a_USCIS": "Item 1.a. Select only one agency; this schema is for USCIS filings (the audit "
                    "requires it).",
                    "Line1b_ListFormNumber": (
                        "Item 1.b: the forms this client's appearance covers, e.g. 'I-130, I-864' for the petitioner "
                        "and 'I-485, I-130A' for the beneficiary (maxlen 30). A longer list goes in Part 6, citing "
                        "Page 2, Part 3, Item 1.b."
                    ),
                    "Line2a_ICE": "Item 2.a, ICE. Leave blank with USCIS selected.",
                    "Line2b_ListMatter": "Item 2.b, ICE matter. Leave blank.",
                    "Line3a_CBP": "Item 3.a, CBP. Leave blank with USCIS selected.",
                    "Line3b_ListSpecificMatter": "Item 3.b, CBP matter. Leave blank.",
                    "Pt3Line4_ReceiptNumber": (
                        "Item 4, receipt number of a pending application or petition, if any (13 characters, e.g. "
                        "IOE0123456789). Blank for a new filing."
                    ),
                    "Line4_Checkbox": (
                        "Item 5, one global group. Use the choices: 'B' is Respondent (ICE, CBP) and 'BD' is "
                        "Beneficiary/Derivative. A petitioner's G-28 takes Petitioner; an adjustment applicant's takes "
                        "Applicant."
                    ),
                },
                choices={
                    "Line1a_USCIS": {"USCIS": "Y"},
                    "Line2a_ICE": {"ICE": "Y"},
                    "Line3a_CBP": {"CBP": "Y"},
                    "Line4_Checkbox": {
                        "Applicant": "A",
                        "Petitioner": "P",
                        "Requestor": "R",
                        "Beneficiary/Derivative": "BD",
                        "Respondent (ICE, CBP)": "B",
                    },
                },
            ),
            "client_identity": q(
                "Part 3, Items 6.a-7.b: Client's name (and, for an entity client, entity name and signatory title)",
                ["Pt3Line5a_FamilyName", "Pt3Line5b_GivenName", "Pt3Line5c_MiddleName", "Pt3Line7a_NameOfEntity",
                 "Pt3Line7b_TitleofEntity"],
                ["Pt3Line5a_FamilyName", "Pt3Line5b_GivenName"],
                notes={
                    "Pt3Line5a_FamilyName": (
                        "Item 6.a despite the Line5 name. Global: also prints in Part 6 item 1.a. Set the base name "
                        "once."
                    ),
                    "Pt3Line5b_GivenName": "Item 6.b. Global: also Part 6 item 1.b.",
                    "Pt3Line5c_MiddleName": "Item 6.c, if any. Global: also Part 6 item 1.c.",
                    "Pt3Line7a_NameOfEntity": "Entity clients only (maxlen 34); blank for a person.",
                    "Pt3Line7b_TitleofEntity": "Entity clients only: the authorized signatory's title; blank for a "
                    "person.",
                },
            ),
            "client_account_numbers": q(
                "Part 3, Items 8-9: Client's USCIS Online Account Number and A-Number (if any)",
                ["Pt3Line8_USCISOnlineAcctNumber", "Pt3Line9_ANumber"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt3Line8_USCISOnlineAcctNumber": (
                        "Item 8, if any: 12 characters, only with an IOE receipt. not_applicable when the client has "
                        "neither number."
                    ),
                    "Pt3Line9_ANumber": "Item 9, if any: 9 digits, no 'A'.",
                },
            ),
            "client_contact": q(
                "Part 3, Items 10-12: Client's daytime phone, mobile phone, email",
                ["Line9_DaytimeTelephoneNumber", "Line10_MobileTelephoneNumber", "Line11_EMail"],
                ["Line9_DaytimeTelephoneNumber"],
                notes={
                    "Line9_DaytimeTelephoneNumber": "Item 10 despite the Line9 name. " + PHONE,
                    "Line10_MobileTelephoneNumber": (
                        "Item 11, if any. " + PHONE + " The audit warns while it or the email is blank."
                    ),
                    "Line11_EMail": "Item 12, if any (maxlen 38).",
                },
            ),
            "client_mailing_address": q(
                "Part 3, Items 13.a-13.h: Client's mailing address",
                ["Line12a_StreetNumberName", "Line12b_Unit", "Line12b_AptSteFlrNumber", "Line12c_CityOrTown",
                 "Line12d_State", "Line12e_ZipCode", "Line12f_Province", "Line12g_PostalCode", "Line12h_Country"],
                ["Line12a_StreetNumberName", "Line12c_CityOrTown", "Line12h_Country"],
                notes={
                    "Line12a_StreetNumberName": (
                        "Item 13.a despite the Line12 names (maxlen 34). The client's own mailing address, not the "
                        "firm's, unless the firm is the safe mailing address on the filing. In a VAWA or other "
                        "protected matter, use the safe mailing address (the attorney's office address from the "
                        "profile unless the attorney gave another), never an address the abuser can see."
                    ),
                    "Line12b_Unit": "Unit type; one global group. Set it with Line12b_AptSteFlrNumber or leave both "
                    "blank.",
                    "Line12b_AptSteFlrNumber": "Unit number (maxlen 6).",
                    "Line12c_CityOrTown": "Maxlen 20.",
                    "Line12d_State": STATE + " The audit warns while blank.",
                    "Line12e_ZipCode": ZIP + " The audit warns while blank.",
                    "Line12f_Province": FOREIGN_ONLY,
                    "Line12g_PostalCode": FOREIGN_ONLY,
                },
                choices={"Line12b_Unit": dict(UNIT)},
            ),
            "client_notice_elections": q(
                "Part 4, Items 1.a-1.c: Client's requests to send original notices and secure documents to the "
                "attorney, or the I-94 notice to the client",
                ["Pt4Line2a_CheckBox2a", "Pt4Line2b_CheckBox2b", "Pt4Line2c_CheckBox2c"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt4Line2a_CheckBox2a": (
                        "Item 1.a despite the '2a' name: original notices to the attorney's business address. These "
                        "are the client's elections: select only on the client's or attorney's instruction. With no "
                        "election, leave all three blank (USCIS's default) and mark the question filled or "
                        "not_applicable. In a VAWA or other protected matter, recommend 1.a and 1.b to the attorney as "
                        "an attorney_decision, so notices and documents come to the office rather than the client's "
                        "home."
                    ),
                    "Pt4Line2b_CheckBox2b": (
                        "Item 1.b: secure identity documents (green card, EAD, travel document) to the attorney's U.S. "
                        "business address. With 1.b, an I-94 notice also goes to the attorney unless 1.c is selected."
                    ),
                    "Pt4Line2c_CheckBox2c": "Item 1.c: send the notice containing the I-94 to the client.",
                },
                choices={
                    "Pt4Line2a_CheckBox2a": {"Send original notices to my attorney": "Y"},
                    "Pt4Line2b_CheckBox2b": {"Send secure identity documents to my attorney": "Y"},
                    "Pt4Line2c_CheckBox2c": {"Send my I-94 notice to me": "Y"},
                },
            ),
            "client_signature": q(
                "Part 4, Items 2.a-2.b: Signature of client (or authorized signatory) and date",
                ["P5_Line6a_SignatureofApplicant", "Pt4Line2b_DateofSignature"],
                allowed=SIGNATURE_STATUSES,
                notes={
                    "P5_Line6a_SignatureofApplicant": (
                        "Part 4 item 2.a despite the P5 name. Signed in ink by the client (a parent or guardian for a "
                        "client under 14); never typed."
                    ),
                    "Pt4Line2b_DateofSignature": "Dated by the client at signing. " + DATE,
                },
            ),
            "attorney_signature": q(
                "Part 5, Items 1.a-1.b: Signature of attorney and date",
                ["Line1_Signature", "Line3_Date"],
                allowed=SIGNATURE_STATUSES,
                notes={
                    "Line1_Signature": "Signed in ink by the attorney; never typed.",
                    "Line3_Date": (
                        "Item 1.b, the ATTORNEY's signature date (Pt5Line2b_DateofSignature is the law student's). "
                        "Unbound in the XFA template; fill binds it if a date is ever filled."
                    ),
                },
            ),
            "law_student_signature": q(
                "Part 5, Items 2.a-2.b: Signature of law student or law graduate and date",
                ["Line2_SignatureStudent", "Pt5Line2b_DateofSignature"],
                allowed=OPTIONAL_SIGNATURE,
                notes={
                    "Line2_SignatureStudent": "Only with Part 2 item 4.a; otherwise not_applicable.",
                    "Pt5Line2b_DateofSignature": "Item 2.b, the law student's date, not the attorney's (Line3_Date).",
                },
            ),
            "additional_information": q(
                "Part 6, Items 2-6: Additional information (page, part, item, text)",
                ["Pt9Line3a_PageNumber", "Pt9Line3b_PartNumber", "Pt9Line3c_ItemNumber", "Pt9Line3d_AdditionalInfo",
                 "Pt9Line4a_PageNumber", "Pt9Line4b_PartNumber", "Pt9Line4c_ItemNumber", "Pt9Line4d_AdditionalInfo",
                 "Pt9Line5a_PageNumber", "Pt9Line5b_PartNumber", "Pt9Line5c_ItemNumber", "Pt9Line5d_AdditionalInfo",
                 "Pt9Line6a_PageNumber[1]", "Pt9Line6b_PartNumber[1]", "Pt9Line6c_ItemNumber[1]",
                 "Pt9Line6d_AdditionalInfo[0]", "Pt9Line6a_PageNumber[0]", "Pt9Line6b_PartNumber[0]",
                 "Pt9Line6c_ItemNumber[0]", "Pt9Line6d_AdditionalInfo[1]"],
                ["Pt9Line3a_PageNumber", "Pt9Line3b_PartNumber", "Pt9Line3c_ItemNumber", "Pt9Line3d_AdditionalInfo"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt9Line3a_PageNumber": (
                        "Part 6 item 2.a despite the Pt9 names: Pt9Line3* is item 2, Pt9Line4* item 3, Pt9Line5* item "
                        "4. Page number only (maxlen 2); part and item boxes hold 6 characters, e.g. '2' and '1.c'. "
                        "Item 1 (name) fills from Part 3."
                    ),
                    "Pt9Line3d_AdditionalInfo": (
                        "Items 2-4 'd' boxes hold 10 lines of 38 characters (Courier 10 pt) and do not wrap: break the "
                        "lines yourself (the audit reports clipped text). Uses: discipline_order_details (Page 1, Part "
                        "2, Item 1.c), more licensing authorities (Item 1.a), forms that do not fit Part 3 item 1.b."
                    ),
                    "Pt9Line6a_PageNumber[1]": (
                        "Item 5's page, part and item are the [1] boxes of Pt9Line6a/6b/6c, but its text is "
                        "Pt9Line6d_AdditionalInfo[0]."
                    ),
                    "Pt9Line6d_AdditionalInfo[0]": "Item 5.d text: 9 lines of 38 characters.",
                    "Pt9Line6a_PageNumber[0]": (
                        "Item 6's page, part and item are the [0] boxes, with text Pt9Line6d_AdditionalInfo[1]."
                    ),
                    "Pt9Line6d_AdditionalInfo[1]": "Item 6.d text: 9 lines of 38 characters.",
                },
            ),
        },
    },
}

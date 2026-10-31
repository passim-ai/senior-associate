"""Question schema for Form I-907, Request for Premium Processing Service.

Built against the 04/01/24 edition (uscis.gov/i-907 Edition Date panel and the PDF footer of the
form and its instructions, checked 2026-10-30). Field list: schemas/fields/I-907.json; every box
of the form belongs to one question.

Written for an I-907 filed with an I-140, or to upgrade a pending one (an EB-2 national interest
waiver, E21 NIW, in particular), and usable for the other forms designated for premium processing
(I-129, I-539, I-765). One I-907 per petition or application (instructions, page 2).

Box names that mislead, read from where each box sits on the page:
- Part 2 items 6-8 carry Part 1 names: Part1_Line8_NameOfCompanyPOC_* is Part 2 item 6 (the
  company's point of contact), Part1_Line9_CompanyIRSTaxNumber is item 7 (the EIN), and
  Part1_Line7_OtherInformationAboutCompanyOrg_* is item 8 (the address of the petitioner, applicant
  or company named in the related case). Part1_Line7_PhysicalAddress_* is Part 1 item 7.
- P2_Line2_ClassorEligRequested is Part 2 item 3; P2_Line2_ReceiptNumberof is item 2.
- Line_FamilyName/GivenName/MiddleName are Part 2 item 5, the beneficiary.
- Part 3: P3_Line4_DaytimeTelePhoneNumber is item 3; P3_Line5_MobileTelePhoneNumber[0] is item 4
  (mobile) and [1] is item 5, the FAX number (both tooltips say mobile); P3_Line6_Email is item 6;
  Pt5Line3_SignatureOfPetitioner and P3_DateofSignature are item 7, the requestor's signature.
- Part 4: P4_Line4_DaytimeTelePhoneNumber[0] is item 4 (daytime) and [1] item 5 (mobile);
  P4_Line5_Email is item 6; P4_Line6_Language is the language in the certification;
  P4_Line6_Signature and P4_Line6_DateofSignature are item 7.
- Part 5: P5_Line5_FaxNumber is item 5, printed "Preparer's Mobile Telephone Number (if any)";
  Pt10Line3b_AptSteFlrNumber is item 3's apartment, suite or floor number.
- Part 6: Pt9Line3* is item 3, Pt9Line4*[0] item 4 and Pt9Line4*[1] item 5. Pt1Line3_* and
  Pt1Line1_AlienRegistrationNumber are global: they also fill Part 6 items 1-2.
- Part 1 item 8's on-states follow the printed order, top to bottom: A petitioner, B attorney for
  the petitioner, C applicant, D attorney for the applicant. Part 3 item 1 stores Y for 1.A (reads
  English) and N for 1.B (an interpreter read it).
- Part1_Line9_CompanyIRSTaxNumber and the Part 6 page, part and item boxes are unbound in the XFA
  template (fill binds them).
"""
from __future__ import annotations

from typing import Any

from _common import DATE, FILLED, FILLED_OR_NA, FOREIGN_ONLY, NOT_APPLICABLE, PENDING_SIGNATURE, UNIT, YES_NO, q

STATE = "U.S. address only: 2-letter state code (drop-down)."
ZIP = "U.S. address only: 5-digit ZIP Code."
PHONE = "Digits only (maxlen 10)."
SIGNATURE = "Leave blank: the signer signs the printed form in ink (a typed or stamped name is not accepted)."
NO_NA = ("When Part 1 item 4 (company) is blank, USCIS rejects the I-907 unless this is filled, and 'N/A' or "
         "'none' doesn't count (uscis.gov/i-907, filing tips).")


def address(prefix: str, *, apt: str | None = None) -> list[str]:
    """An address row's boxes in form order: street, unit, number, city, state, ZIP Code, province,
    postal code, country."""
    return [f"{prefix}StreetNumberName", f"{prefix}Unit", apt or f"{prefix}AptSteFlrNumber", f"{prefix}CityTown",
            f"{prefix}State", f"{prefix}ZipCode", f"{prefix}Province", f"{prefix}PostalCode", f"{prefix}Country"]


def address_notes(prefix: str) -> dict[str, str]:
    return {f"{prefix}State": STATE, f"{prefix}ZipCode": ZIP, f"{prefix}Province": FOREIGN_ONLY,
            f"{prefix}PostalCode": FOREIGN_ONLY}


def premium_processing() -> dict[str, Any]:
    mailing = "Part1_Line5_MailingAddress_"
    physical = "Part1_Line7_PhysicalAddress_"
    related = "Part1_Line7_OtherInformationAboutCompanyOrg_"
    questions: dict[str, dict[str, Any]] = {
        "attorney_box": q(
            "Page 1 attorney box: G-28 attached, attorney State Bar number, attorney's USCIS online account number",
            ["FormG28Attach", "AttyStateBarNumber", "USCISOnlineAcctNumber"],
            ["FormG28Attach"],
            allowed=FILLED_OR_NA,
            notes={
                "FormG28Attach": "Select when a G-28 for the requestor goes with the I-907. An attorney who requests "
                "premium processing files a G-28 unless one is already filed in the case; a new attorney's G-28 "
                "replaces the earlier one (instructions, page 1).",
                "AttyStateBarNumber": "Profile key bar_number, if applicable.",
                "USCISOnlineAcctNumber": "The attorney's account number, if the profile has one (12 digits). Blank when "
                "the profile says has_uscis_online_account \"no\".",
            },
            choices={"FormG28Attach": {"G-28 or G-28I attached": "1"}},
        ),
        "requestor_numbers": q(
            "Part 1, Items 1-2: The requestor's A-Number and USCIS online account number (each if any)",
            ["Pt1Line1_AlienRegistrationNumber", "Pt1Line2_USCISOnlineActNumber"],
            allowed=FILLED_OR_NA,
            notes={"Pt1Line1_AlienRegistrationNumber": "If any: 9 digits, no 'A' (global: also Part 6 item 2). "
                   "N/A for a company or when there is none.",
                   "Pt1Line2_USCISOnlineActNumber": "Only with an earlier IOE receipt: 12 digits; not the A-Number."},
        ),
        "requestor_name": q(
            "Part 1, Item 3: Full name of the person filing this request",
            ["Pt1Line3_FamilyName", "Pt1Line3_GivenName", "Pt1Line3_MiddleName"],
            ["Pt1Line3_FamilyName", "Pt1Line3_GivenName"],
            allowed=FILLED_OR_NA,
            notes={"Pt1Line3_FamilyName": "Global: also fills Part 6 item 1. A self-petitioner gives their own name "
                   "here and checks 8.A. " + NO_NA},
        ),
        "company_in_related_case": q(
            "Part 1, Item 4: Company or organization named in the related case (if filed on behalf of one)",
            ["Part1_Line4_CompanyorOrganizationName"],
            ["Part1_Line4_CompanyorOrganizationName"],
            allowed=FILLED_OR_NA,
            notes={"Part1_Line4_CompanyorOrganizationName": "An employer petitioner's name (maxlen 34). Blank for a "
                   "self-petitioner, and then Part 1 item 3 and Part 2 items 4-5 must all be given."},
        ),
        "mailing_address": q(
            "Part 1, Item 5: Requestor's mailing address",
            ["Part1_Line5_MailingAddress_InCareofName", *address(mailing)],
            [f"{mailing}StreetNumberName", f"{mailing}CityTown", f"{mailing}Country"],
            notes={**address_notes(mailing), f"{mailing}StreetNumberName": "maxlen 34.",
                   f"{mailing}CityTown": "maxlen 20."},
            choices={f"{mailing}Unit": UNIT},
        ),
        "physical_same_as_mailing": q(
            "Part 1, Item 6: Is the current mailing address the same as the physical address?",
            ["Part1Line6_Checkbox"],
            ["Part1Line6_Checkbox"],
            notes={"Part1Line6_Checkbox": "'No' requires physical_address (item 7)."},
            choices={"Part1Line6_Checkbox": YES_NO},
        ),
        "physical_address": q(
            "Part 1, Item 7: Physical address (if different from the mailing address)",
            address(physical),
            [f"{physical}StreetNumberName", f"{physical}CityTown", f"{physical}Country"],
            allowed=FILLED_OR_NA,
            notes=address_notes(physical),
            choices={f"{physical}Unit": UNIT},
        ),
        "request_type": q(
            "Part 1, Item 8: Who is requesting premium processing (select only one)",
            ["Part1_Line8_CheckBox"],
            ["Part1_Line8_CheckBox"],
            notes={"Part1_Line8_CheckBox": "A petition (I-129, I-140) takes 8.A or 8.B; an application (I-539, I-765) "
                   "8.C or 8.D. The beneficiary of a petition may not file it (instructions, page 5); a self-petitioner "
                   "is the petitioner (8.A). 8.B and 8.D need a G-28 unless one is already filed in the case."},
            choices={"Part1_Line8_CheckBox": {
                "8.A I am the petitioner": "A",
                "8.B I am the attorney or accredited representative for the petitioner": "B",
                "8.C I am the applicant": "C",
                "8.D I am the attorney or accredited representative for the applicant": "D",
            }},
        ),
        "related_case": q(
            "Part 2, Items 1-3: Form number, receipt number and classification of the related petition or application",
            ["P2_Line1_FormNumberof", "P2_Line2_ReceiptNumberof", "P2_Line2_ClassorEligRequested"],
            ["P2_Line1_FormNumberof", "P2_Line2_ClassorEligRequested"],
            notes={
                "P2_Line1_FormNumberof": "Item 1: I-140 (or I-129, I-539, I-765).",
                "P2_Line2_ReceiptNumberof": "Item 2: only to upgrade a pending case: its receipt number, 3 letters and "
                "10 digits (maxlen 13). Blank when filed together with the petition, which has no receipt yet "
                "(instructions, page 3).",
                "P2_Line2_ClassorEligRequested": "Item 3, despite the Line2 name: for an I-140 the classification, such "
                "as E21 NIW (45 days) or E21 non-NIW, E11, E12 (15 days), E13 (45 days), E31, E32, EW3 (instructions, "
                "page 5).",
            },
        ),
        "related_petitioner_or_applicant": q(
            "Part 2, Item 4: Petitioner or applicant in the related case",
            ["Part2_Line4_PetitionerApplicantFamilyName", "Part2_Line4_PetitionerApplicantGivenName",
             "Part2_Line4_PetitionerApplicantMiddleName"],
            ["Part2_Line4_PetitionerApplicantFamilyName", "Part2_Line4_PetitionerApplicantGivenName"],
            allowed=FILLED_OR_NA,
            notes={"Part2_Line4_PetitionerApplicantFamilyName": "An individual petitioner or applicant; a "
                   "self-petitioner's own name. Required with a petition (instructions, page 3). " + NO_NA},
        ),
        "related_beneficiary": q(
            "Part 2, Item 5: Beneficiary in the related case",
            ["Line_FamilyName", "Line_GivenName", "Line_MiddleName"],
            ["Line_FamilyName", "Line_GivenName"],
            allowed=FILLED_OR_NA,
            notes={"Line_FamilyName": "Item 5, despite the plain name (maxlen 30): the petition's beneficiary, the "
                   "self-petitioner again for an NIW. Required with a petition; not asked for an application. " + NO_NA},
        ),
        "company_contact_and_ein": q(
            "Part 2, Items 6-7: The company's point of contact (name and position title) and its EIN (if any)",
            ["Part1_Line8_NameOfCompanyPOC_FamilyName", "Part1_Line8_NameOfCompanyPOC_GivenName",
             "Part1_Line8_NameOfCompanyPOC_MiddleName", "Part1_Line8_NameOfCompanyPOC_TitleofPOC",
             "Part1_Line9_CompanyIRSTaxNumber"],
            ["Part1_Line8_NameOfCompanyPOC_FamilyName", "Part1_Line8_NameOfCompanyPOC_GivenName",
             "Part1_Line8_NameOfCompanyPOC_TitleofPOC"],
            allowed=FILLED_OR_NA,
            notes={"Part1_Line8_NameOfCompanyPOC_FamilyName": "Part 2 item 6 despite the Part1 name; only for a company "
                   "or organization.",
                   "Part1_Line9_CompanyIRSTaxNumber": "Part 2 item 7 despite the Part1 name: the EIN, 9 digits (if "
                   "any). Unbound in the XFA template (fill binds it)."},
        ),
        "related_address": q(
            "Part 2, Item 8: Address of the petitioner, applicant, company or organization named in the related case",
            address(related),
            [f"{related}StreetNumberName", f"{related}CityTown", f"{related}Country"],
            allowed=FILLED_OR_NA,
            notes={**address_notes(related), f"{related}StreetNumberName": "Part 2 item 8 despite the Part1 name. "
                   "Required to upgrade a pending petition (items 1-8 all; instructions, page 3)."},
            choices={f"{related}Unit": UNIT},
        ),
        "requestor_statement": q(
            "Part 3, Items 1-2: Reads English (1.A) or an interpreter read it (1.B, and the language); a preparer "
            "prepared it (2, and the preparer's name)",
            ["P3_Line1_Checkbox", "P3_Line1_B_Language", "P3_Line2_Checkbox", "P3_Line2_NameofRepresentative"],
            ["P3_Line1_Checkbox"],
            notes={"P3_Line1_B_Language": "Only with 1.B: the language.",
                   "P3_Line2_NameofRepresentative": "Item 2: the preparer named in Part 5, only with item 2 checked."},
            choices={"P3_Line1_Checkbox": {"1.A I can read and understand English": "Y",
                                           "1.B The interpreter named in Part 4 read it to me": "N"},
                     "P3_Line2_Checkbox": {"2 The preparer named in Part 5 prepared this request": "A"}},
        ),
        "requestor_contact": q(
            "Part 3, Items 3-6: Requestor's daytime phone, mobile phone, fax and email (each but the first if any)",
            ["P3_Line4_DaytimeTelePhoneNumber", "P3_Line5_MobileTelePhoneNumber[0]", "P3_Line5_MobileTelePhoneNumber[1]",
             "P3_Line6_Email"],
            ["P3_Line4_DaytimeTelePhoneNumber"],
            notes={"P3_Line4_DaytimeTelePhoneNumber": "Item 3. " + PHONE,
                   "P3_Line5_MobileTelePhoneNumber[0]": "Item 4, mobile. " + PHONE,
                   "P3_Line5_MobileTelePhoneNumber[1]": "Item 5, the FAX number (its tooltip says mobile). " + PHONE,
                   "P3_Line6_Email": "Item 6."},
        ),
        "requestor_signature": q(
            "Part 3, Item 7: Requestor's signature and date",
            ["Pt5Line3_SignatureOfPetitioner", "P3_DateofSignature"],
            allowed=[PENDING_SIGNATURE, FILLED],
            notes={"Pt5Line3_SignatureOfPetitioner": "Part 3 item 7 despite the name. " + SIGNATURE + " Without a "
                   "handwritten signature USCIS returns the request and the fee (instructions, page 2).",
                   "P3_DateofSignature": DATE},
        ),
        "interpreter_block": q(
            "Part 4, Items 1-6 and certification: Interpreter's name, business, mailing address, phones, email, language",
            ["P4_Line1_InterpreterFamilyName", "P4_Line1_InterpreterGivenName", "P4_Line2_NameofBusinessorOrgName",
             *address("P4_Line3_"), "P4_Line4_DaytimeTelePhoneNumber[0]", "P4_Line4_DaytimeTelePhoneNumber[1]",
             "P4_Line5_Email", "P4_Line6_Language"],
            ["P4_Line1_InterpreterFamilyName", "P4_Line1_InterpreterGivenName", "P4_Line3_StreetNumberName",
             "P4_Line3_CityTown", "P4_Line3_Country", "P4_Line4_DaytimeTelePhoneNumber[0]", "P4_Line6_Language"],
            allowed=FILLED_OR_NA,
            notes={**address_notes("P4_Line3_"),
                   "P4_Line4_DaytimeTelePhoneNumber[0]": "Item 4, daytime. " + PHONE,
                   "P4_Line4_DaytimeTelePhoneNumber[1]": "Item 5, MOBILE despite the name. " + PHONE,
                   "P4_Line5_Email": "Item 6.",
                   "P4_Line6_Language": "The language in the interpreter's certification, the same as Part 3 item 1.B."},
            choices={"P4_Line3_Unit": UNIT},
        ),
        "interpreter_signature": q(
            "Part 4, Item 7: Interpreter's signature and date",
            ["P4_Line6_Signature", "P4_Line6_DateofSignature"],
            allowed=[NOT_APPLICABLE, PENDING_SIGNATURE, FILLED],
            notes={"P4_Line6_Signature": "Item 7 despite the Line6 name. " + SIGNATURE, "P4_Line6_DateofSignature": DATE},
        ),
        "preparer_block": q(
            "Part 5, Items 1-7: Preparer's name, business, mailing address, phones, email (from the attorney profile), "
            "and statement",
            ["P5_Line1_PreparerFamilyName", "P5_Line1_PreparerGivenName", "P5_Line2_NameofBusinessorOrgName",
             *address("P5_Line3_", apt="Pt10Line3b_AptSteFlrNumber"), "P5_Line4_DaytimeTelePhoneNumber",
             "P5_Line5_FaxNumber", "P5_Line6_EmailAddress", "P5_Line7a_Checkbox", "P5_Line7b_Checkbox",
             "P5_Line7b_extends", "P5_Line7b_notextends"],
            ["P5_Line1_PreparerFamilyName", "P5_Line1_PreparerGivenName", "P5_Line3_StreetNumberName",
             "P5_Line3_CityTown", "P5_Line3_Country", "P5_Line4_DaytimeTelePhoneNumber"],
            allowed=FILLED_OR_NA,
            notes={
                "P5_Line1_PreparerFamilyName": "From the attorney profile (attorney_name, firm_name, mailing_address, "
                "phone, email).",
                **address_notes("P5_Line3_"),
                "Pt10Line3b_AptSteFlrNumber": "Item 3's apartment, suite or floor number, despite the Pt10 name.",
                "P5_Line4_DaytimeTelePhoneNumber": "Item 4. " + PHONE,
                "P5_Line5_FaxNumber": "Item 5, printed 'Preparer's Mobile Telephone Number (if any)' despite the name "
                "and tooltip. " + PHONE,
                "P5_Line7a_Checkbox": "7.A not an attorney; 7.B an attorney or accredited representative: check exactly "
                "one. With 7.B, check exactly one of extends and does not extend.",
                "P5_Line7b_extends": "'Extends' beyond preparing this request goes with a G-28 (page 1 box).",
            },
            choices={"P5_Line3_Unit": UNIT,
                     "P5_Line7a_Checkbox": {"7.A Not an attorney or accredited representative": "A"},
                     "P5_Line7b_Checkbox": {"7.B An attorney or accredited representative": "B"},
                     "P5_Line7b_extends": {"Representation extends beyond this request": "1"},
                     "P5_Line7b_notextends": {"Representation does not extend beyond this request": "2"}},
        ),
        "preparer_signature": q(
            "Part 5, Item 8: Preparer's signature and date",
            ["P5_Line8_Signature", "P5_Line8_DateofSignature"],
            allowed=[NOT_APPLICABLE, PENDING_SIGNATURE, FILLED],
            notes={"P5_Line8_Signature": SIGNATURE, "P5_Line8_DateofSignature": DATE},
        ),
        "additional_information": q(
            "Part 6, Items 3-5: Additional information (page, part, item and text, three entries)",
            ["Pt9Line3a_PageNumber", "Pt9Line3b_PartNumber", "Pt9Line3c_ItemNumber", "Pt9Line3d_AdditionalInfo",
             "Pt9Line4a_PageNumber[0]", "Pt9Line4b_PartNumber[0]", "Pt9Line4c_ItemNumber[0]", "Pt9Line4d_AdditionalInfo[0]",
             "Pt9Line4a_PageNumber[1]", "Pt9Line4b_PartNumber[1]", "Pt9Line4c_ItemNumber[1]", "Pt9Line4d_AdditionalInfo[1]"],
            ["Pt9Line3a_PageNumber", "Pt9Line3b_PartNumber", "Pt9Line3c_ItemNumber", "Pt9Line3d_AdditionalInfo"],
            allowed=FILLED_OR_NA,
            notes={"Pt9Line3a_PageNumber": "Item 3 (page maxlen 2; part and item 6 each). Items 1-2 (name, A-Number) "
                   "repeat Part 1 automatically (global boxes). The page, part and item boxes are unbound in the XFA "
                   "template (fill binds them).",
                   "Pt9Line4a_PageNumber[0]": "Item 4 is box [0], item 5 box [1]."},
        ),
    }
    return {
        "kind": "i-907",
        "edition": "04/01/24",
        "field_list": "I-907.json",
        "description": (
            "Form I-907 request for premium processing of an I-140 (an EB-2 NIW, say), filed with it or to upgrade it "
            "once pending; also usable for an I-129, I-539 or I-765."
        ),
        "notes": [
            "One I-907 per petition or application (instructions, page 2). The petitioner (a self-petitioner included) "
            "or the petitioner's attorney requests it; the beneficiary of a petition may not (instructions, page 5).",
            "Filed together with the petition, Part 2 items 1, 3, 4 and 5 are required and item 2 stays blank; to "
            "upgrade a pending petition, items 1-8 all, the receipt number included (instructions, page 3). USCIS "
            "rejects the I-907 and returns the fee otherwise.",
            "For an I-129 or I-140 with Part 1 item 4 blank (no company), Part 1 item 3 and Part 2 items 4 and 5 must "
            "all be given, and 'N/A' or 'none' is not acceptable (uscis.gov/i-907 filing tips).",
            "The premium processing fee is paid separately from every other fee (G-1055, ed. 10/26/26: $2,965 for an "
            "I-140). An I-140 filed with an I-907 goes by mail (uscis.gov/i-140); a standalone I-907 for a pending I-140 "
            "with an IOE receipt may go by PDF upload or mail.",
            "Premium processing for an E13 or E21 NIW I-140 is 45 days, for the other I-140 classifications 15 "
            "(instructions, page 5; the premium processing page counts them as business days).",
        ],
        "required_questions": questions,
    }


SCHEMAS = {"i907_premium_processing": premium_processing()}

"""Question schema for Form I-601, Application for Waiver of Grounds of Inadmissibility.

Built against the 01/20/25 edition (uscis.gov/i-601 Edition Date panel and the PDF footer of the
form and its instructions, checked 2026-10-30). Field list: schemas/fields/I-601.json; every box
of the form belongs to one question.

Most box names on this edition carry their own part and item. The ones that don't, read from where
each box sits on the page: p1Line1dCityOrTown is Part 2 item 1.d (the U.S. city lived in);
Pt7Line6a_SignatureofApplicant and p7Line6DateofSignature are Part 7 items 4.a-4.b;
p8Line7Signature and p8Line7DateofSignature are Part 8 items 6.a-6.b; P8Language is the language
in the interpreter's certification; box [1] of p1Line3a/3b/3c and of p1Line1ANum is the Part 10
header (global, so filled from Part 1).

Defect of this edition, read from where each box sits next to its printed label and from each
widget's own on-state (not yet opened in Acrobat): Part 3 item 5, eye color, the box printed "Gray"
stores GRN and the box printed "Green" stores GRY (their tooltips name them the same way). The
choices are keyed by the printed label. The unit, yes/no, sex, ethnicity, race and hair boxes match
their labels.

Unbound in the XFA template (fill binds them): Part 1 items 11, 12, 15.a and 15.b
(p1Line11CityOrTownOfBirth, p1Line12ProvinceOfBirth, p1Line15aCaseNumber, p1Line15bCity,
p1Line15bCountry) and the five race boxes of Part 3 item 2 (p3Line2Race[0]-[4]).

Part 4 has one checkbox per ground, in three sections by the benefit sought: A (items 1-18) an
immigrant visa, adjustment other than T or SIJ, or K or V status; B (item 19) adjustment based on T
status or SIJ classification; C (items 20-39) TPS. The questions group the grounds by kind within a
section, so every ground not claimed is not_applicable; item 40 is the statement for all of them.
Part 11 is only for a Class A tuberculosis condition, and its health department parts are completed
by the health departments, never by the firm.
"""
from __future__ import annotations

from typing import Any

from _common import DATE, FILLED, FILLED_OR_NA, NOT_APPLICABLE, PENDING_SIGNATURE, UNIT, YES_NO, q

STATE = "U.S. address only: 2-letter state code (drop-down)."
ZIP = "U.S. address only: 5-digit ZIP Code."
PHONE = "Digits only (maxlen 10)."
A_NUMBER = "If any: 9 digits, no 'A'."
SIGNATURE = "Protected box; the signer signs the printed form in ink."
NO_WRAP = "The box doesn't wrap: break long text into lines that fit (the audit reports a cut-off line)."
LETTER = "With a separate letter, write here that a letter is attached; it is filed with the I-601."
SECTION_A = "Section A: an immigrant visa, adjustment other than T or SIJ, or K or V status."
SECTION_C = "Section C: TPS applicants only."


def grounds(label: str, boxes: dict[int, str], *, notes: dict[str, str] | None = None,
            text: str = "") -> dict[str, Any]:
    """Part 4 grounds: one checkbox per item (p4Line<N>CB, on-state Y), any that apply, and the
    'specify' box of an 'Other' item. A one-ground question filled has its box (and text) filled."""
    fields = [f"p4Line{item}CB" for item in boxes] + ([text] if text else [])
    single = fields if len(boxes) == 1 else []
    return q(
        label,
        fields,
        single,
        allowed=FILLED_OR_NA,
        notes=notes,
        choices={f"p4Line{item}CB": {f"{item} {what}": "Y"} for item, what in boxes.items()},
    )


def relative(part: int, label: str, given: str, middle: str, more_box: str, more: str,
             *, notes: dict[str, str] | None = None) -> dict[str, Any]:
    """Part 5 or 6, items 1.a-8: a relative's name, physical address, contact, relationship, status,
    A-Number and date of birth, and the box for more relatives in Part 10."""
    p = f"p{part}Line"
    fields = [f"{p}1aFamilyName", given, middle, f"{p}2StreetNumberName", f"{p}2Unit", f"{p}2AptSteFlrNumber",
              f"{p}2CityOrTown", f"{p}2State", f"{p}2ZipCode", f"{p}2Province", f"{p}2PostalCode", f"{p}2Country",
              f"{p}3DayPhone", f"{p}4Email", f"{p}5Relationship", f"{p}6ImmigrationStatus", f"{p}7AlienNumber",
              f"{p}8DateofBirth", more_box]
    return q(
        label,
        fields,
        [f"{p}1aFamilyName", given, f"{p}2StreetNumberName", f"{p}2CityOrTown", f"{p}2Country", f"{p}5Relationship",
         f"{p}6ImmigrationStatus", f"{p}8DateofBirth"],
        allowed=FILLED_OR_NA,
        notes={f"{p}2State": STATE, f"{p}2ZipCode": ZIP, f"{p}3DayPhone": "If any. " + PHONE,
               f"{p}7AlienNumber": A_NUMBER, f"{p}8DateofBirth": DATE,
               more_box: f"Check when Part 10 gives {more} (items 1.a-8 for each).", **(notes or {})},
        choices={f"{p}2Unit": UNIT, more_box: {"More relatives in Part 10": "Y"}},
    )


def additional_information() -> dict[str, Any]:
    rows = [[f"p10Line{item}{box}" for box in ("aPageNumber", "bPartNumber", "cItemNumber", "dAdditionalInfo")]
            for item in (3, 4, 5, 6)]
    return q(
        "Part 10, Items 3-6: Additional information (page, part, item and text, four entries)",
        [name for row in rows for name in row],
        rows[0],
        allowed=FILLED_OR_NA,
        notes={
            "p10Line3aPageNumber": "Items 1.a-2 (name and A-Number) repeat Part 1 (global boxes). Page box maxlen 2, "
            "part and item boxes maxlen 6.",
            "p10Line3dAdditionalInfo": NO_WRAP,
        },
    )


def waiver_application() -> dict[str, Any]:
    questions: dict[str, dict[str, Any]] = {
        "attorney_box": q(
            "Page 1 attorney box: G-28 or G-28I attached, attorney's state bar number and USCIS online account number",
            ["G28CheckBox", "attyStateBarNumber", "attyUSCISOnlineNum"],
            ["G28CheckBox", "attyStateBarNumber"],
            allowed=FILLED_OR_NA,
            notes={
                "attyStateBarNumber": "Profile key bar_number.",
                "attyUSCISOnlineNum": "The attorney's account number, if the profile has one (12 digits). Blank when the "
                "profile says has_uscis_online_account \"no\".",
            },
            choices={"G28CheckBox": {"G-28 or G-28I attached": "Y"}},
        ),
        "applicant_numbers": q(
            "Part 1, Items 1, 2 and 8: A-Number, USCIS online account number and U.S. Social Security number (each if any)",
            ["p1Line1ANum", "p1Line2USCISOnlineNum", "p1Line8SSN"],
            allowed=FILLED_OR_NA,
            notes={"p1Line1ANum": A_NUMBER + " Global: also the Part 10 header (item 2, page 9).",
                   "p1Line2USCISOnlineNum": "If any: 12 digits.",
                   "p1Line8SSN": "Item 8, if any: 9 digits. Any other SSN ever used goes in Part 10 (instructions)."},
        ),
        "applicant_name": q(
            "Part 1, Items 3.a-3.c: Full legal name",
            ["p1Line3aFamilyName", "p1Line3bGivenName", "p1Line3cMiddleName"],
            ["p1Line3aFamilyName", "p1Line3bGivenName"],
            notes={"p1Line3aFamilyName": "Global: box [1] is the Part 10 header (items 1.a-1.c, page 9), filled from here."},
        ),
        "other_names": q(
            "Part 1, Items 4.a-4.c: Other names used, including maiden names, aliases and nicknames (one row; more in Part 10)",
            ["p1Line4aFamilyName", "p1Line4bGivenName", "p1Line4cMiddleName"],
            ["p1Line4aFamilyName", "p1Line4bGivenName"],
            allowed=FILLED_OR_NA,
        ),
        "mailing_address": q(
            "Part 1, Items 5.a-5.i: Mailing address (a U.S. address if one is available)",
            ["p1Line5InCareofName", "p1Line5StreetNumberName", "p1Line5Unit", "p1Line5AptSteFlrNumber", "p1Line5CityOrTown",
             "p1Line5State", "p1Line5ZipCode", "p1Line5Province", "p1Line5PostalCode", "p1Line5Country"],
            ["p1Line5StreetNumberName", "p1Line5CityOrTown", "p1Line5Country"],
            notes={"p1Line5StreetNumberName": "Item 5.b (maxlen 34).", "p1Line5State": STATE, "p1Line5ZipCode": ZIP},
            choices={"p1Line5Unit": UNIT},
        ),
        "physical_address_same": q(
            "Part 1, Item 6: Is the current physical address the same as the mailing address?",
            ["p1Line6YesNo"],
            ["p1Line6YesNo"],
            choices={"p1Line6YesNo": YES_NO},
        ),
        "physical_address": q(
            "Part 1, Items 7.a-7.h: Physical address (only when item 6 is No)",
            ["p1Line7StreetNumberName", "p1Line7Unit", "p1Line7AptSteFlrNumber", "p1Line7CityTown", "p1Line7State",
             "p1Line7ZipCode", "p1Line7Province", "p1Line7PostalCode", "p1Line7Country"],
            ["p1Line7StreetNumberName", "p1Line7CityTown", "p1Line7Country"],
            allowed=FILLED_OR_NA,
            notes={"p1Line7StreetNumberName": "Item 7.a (maxlen 34).", "p1Line7State": STATE, "p1Line7ZipCode": ZIP},
            choices={"p1Line7Unit": UNIT},
        ),
        "applicant_other_information": q(
            "Part 1, Items 9-14: Sex, date of birth, city, province and country of birth, country of citizenship or nationality",
            ["p1Line9Gender", "p1Line10DateofBirth", "p1Line11CityOrTownOfBirth", "p1Line12ProvinceOfBirth",
             "p1Line13CountryOfBirth", "p1Line14CountryOfCitzOrNat"],
            ["p1Line9Gender", "p1Line10DateofBirth", "p1Line11CityOrTownOfBirth", "p1Line13CountryOfBirth",
             "p1Line14CountryOfCitzOrNat"],
            notes={
                "p1Line10DateofBirth": DATE,
                "p1Line11CityOrTownOfBirth": "Unbound in the XFA template (fill binds it), as are items 12 and 15.",
                "p1Line12ProvinceOfBirth": "If applicable.",
                "p1Line13CountryOfBirth": "The country's name when the applicant was born, even if it has changed.",
                "p1Line14CountryOfCitzOrNat": "Stateless: the last country of citizenship; more than one: the country that "
                "issued the last passport (instructions).",
            },
            choices={"p1Line9Gender": {"Male": "M", "Female": "F"}},
        ),
        "consular_case": q(
            "Part 1, Items 15.a-15.b: A visa applicant already interviewed by a consular officer: DOS case number (if "
            "available) and the city and country of the U.S. Embassy or Consulate",
            ["p1Line15aCaseNumber", "p1Line15bCity", "p1Line15bCountry"],
            ["p1Line15bCity", "p1Line15bCountry"],
            allowed=FILLED_OR_NA,
        ),
        "pending_i485": q(
            "Part 1, Items 16.a-16.b: Filed after an I-485 already filed? Its receipt number",
            ["p1Line16aYesNo", "p1Line16bReceiptNumber"],
            ["p1Line16aYesNo"],
            notes={"p1Line16bReceiptNumber": "Only with Yes, and then required: 3 letters and 10 digits."},
            choices={"p1Line16aYesNo": YES_NO},
        ),
        "pending_i821": q(
            "Part 1, Items 17.a-17.b: Filed after an I-821 (TPS) already filed? Its receipt number, if any",
            ["p1Line17aYesNo", "p1Line17bReceiptNumber"],
            ["p1Line17aYesNo"],
            notes={"p1Line17bReceiptNumber": "Only with Yes, if any: 3 letters and 10 digits."},
            choices={"p1Line17aYesNo": YES_NO},
        ),
        "consent_to_reapply": q(
            "Part 1, Items 18.a-19: Form I-212 filed before (receipt number if any, where and when filed); I-212 filed "
            "with this application",
            ["p1Line18aYesNo", "p1Line18bReceiptNumber", "p1Line18cFilingLocation", "p1Line18dDateFiled", "p1Line19YesNo"],
            ["p1Line18aYesNo", "p1Line19YesNo"],
            notes={
                "p1Line18bReceiptNumber": "Only with 18.a Yes, if any: 3 letters and 10 digits.",
                "p1Line18cFilingLocation": "With 18.a Yes: the USCIS office, port of entry or immigration court.",
                "p1Line18dDateFiled": "With 18.a Yes. " + DATE,
            },
            choices={"p1Line18aYesNo": YES_NO, "p1Line19YesNo": YES_NO},
        ),
        "most_recent_entry": q(
            "Part 2, Items 1.a-1.d: Most recent arrival in the United States: date, status at entry, place of entry, U.S. "
            "city or town lived in",
            ["p2Line1aDateEntered", "p2Line1bImmigrationStatus", "p2Line1cLocation", "p1Line1dCityOrTown"],
            ["p2Line1aDateEntered", "p2Line1bImmigrationStatus", "p2Line1cLocation", "p1Line1dCityOrTown"],
            allowed=FILLED_OR_NA,
            notes={
                "p2Line1aDateEntered": "Not applicable only for an applicant never in the United States. " + DATE,
                "p2Line1bImmigrationStatus": "The status at entry, by letter and number (for example B-2).",
                "p1Line1dCityOrTown": "Item 1.d despite the p1 name: the U.S. city or town where the applicant lived.",
            },
        ),
        "previous_stay": q(
            "Part 2, Items 2.a-2.e: The stay before that: date entered, date departed, status at entry, place of entry, "
            "U.S. city or town lived in (more stays in Part 10)",
            ["p2Line2aDateEntered", "p2Line2bDepartureDate", "p2Line2cImmigrationStatus", "p2Line2dLocation",
             "p2Line2eCityOrTown"],
            ["p2Line2aDateEntered", "p2Line2bDepartureDate", "p2Line2cImmigrationStatus", "p2Line2dLocation",
             "p2Line2eCityOrTown"],
            allowed=FILLED_OR_NA,
            notes={"p2Line2aDateEntered": DATE, "p2Line2bDepartureDate": "Page 3. " + DATE},
        ),
        "biographic_info": q(
            "Part 3, Items 1 and 3-6: Ethnicity, height, weight, eye color, hair color (for a USCIS filing)",
            ["p3Line1Ethnicity", "p3Line3HeightFeet", "p3Line3HeightInches", "p3Line4Weight1", "p3Line4Weight2",
             "p3Line4Weight3", "p3Line5EyeColor", "p3Line6HairColor"],
            ["p3Line1Ethnicity", "p3Line3HeightFeet", "p3Line3HeightInches", "p3Line4Weight1", "p3Line4Weight2",
             "p3Line4Weight3", "p3Line5EyeColor", "p3Line6HairColor"],
            allowed=FILLED_OR_NA,
            notes={
                "p3Line1Ethnicity": "Part 3 is headed 'for USCIS applicant only': not_applicable only when the I-601 is "
                "filed with another agency (an immigration court).",
                "p3Line3HeightFeet": "Drop-down '2' to '8'.",
                "p3Line3HeightInches": "Drop-down '0' to '11' (the instructions' '09' is '9' here).",
                "p3Line4Weight1": "Weight in pounds, one digit per box: 1 hundreds, 2 tens, 3 units (95 pounds: 0, 9, 5). "
                "Under 30 or over 699 pounds, or unknown: 0, 0, 0 (instructions).",
                "p3Line5EyeColor": "Form defect: the box printed 'Gray' stores GRN and the box printed 'Green' stores GRY. "
                "Use the choices (keyed by the printed label).",
            },
            choices={
                "p3Line1Ethnicity": {"Hispanic or Latino": "H", "Not Hispanic or Latino": "N"},
                "p3Line5EyeColor": {
                    "Black": "BLK", "Blue": "BLU", "Brown": "BRO", "Gray": "GRN", "Green": "GRY", "Hazel": "HAZ",
                    "Maroon": "MAR", "Pink": "PNK", "Unknown/Other": "UNK"},
                "p3Line6HairColor": {
                    "Bald (No hair)": "BAL", "Black": "BLK", "Blond": "BLN", "Brown": "BRO", "Gray": "GRY", "Red": "RED",
                    "Sandy": "SDY", "White": "WHI", "Unknown/Other": "UNK"},
            },
        ),
        "race": q(
            "Part 3, Item 2: Race (any that apply; five separate boxes)",
            [f"p3Line2Race[{index}]" for index in range(5)],
            allowed=FILLED_OR_NA,
            notes={"p3Line2Race[0]": "Each box is its own field with the on-state Y; check every race that applies. "
                   "Unbound in the XFA template (fill binds them). Not applicable with Part 3 (see biographic_info)."},
            choices={f"p3Line2Race[{index}]": {label: "Y"} for index, label in enumerate((
                "Native Hawaiian or Other Pacific Islander", "American Indian or Alaska Native", "White", "Asian",
                "Black or African American"))},
        ),
        # Part 4, Section A (items 1-18).
        "health_grounds": grounds(
            "Part 4, Section A, Items 1-3: Health-related grounds, INA 212(a)(1): communicable disease, vaccination "
            "exemption, physical or mental disorder with harmful behavior",
            {1: "Communicable disease of public health significance",
             2: "Vaccination exemption (religious beliefs or moral convictions)",
             3: "Physical or mental disorder with associated harmful behavior"},
            notes={
                "p4Line1CB": SECTION_A + " Item 1 (212(g)(1)) rests on a qualifying relative in Part 5 or the VAWA box; a "
                "Class A tuberculosis condition also needs Part 11.",
                "p4Line3CB": "Attach the medical history and report the instructions list.",
            },
        ),
        "criminal_grounds": grounds(
            "Part 4, Section A, Items 4-10: Criminal grounds, INA 212(a)(2): moral turpitude, simple possession of 30 "
            "grams or less of marijuana, two or more convictions, prostitution, procuring, commercialized vice, serious "
            "criminal activity with immunity asserted",
            {4: "Crime involving moral turpitude",
             5: "Single offense of simple possession of 30 grams or less of marijuana",
             6: "Two or more convictions with combined sentences of 5 years or more",
             7: "Prostitution",
             8: "Procuring prostitutes or persons for prostitution in the past 10 years",
             9: "Other unlawful commercialized vice",
             10: "Serious criminal activity, immunity from prosecution asserted"},
            notes={"p4Line4CB": SECTION_A + " Item 40 gives the date of every conviction and the disposition of every "
                   "arrest, with certified court records. The 212(h) waiver rests on 15 years and rehabilitation, "
                   "prostitution only, extreme hardship to a qualifying relative (Part 5), or VAWA."},
        ),
        "totalitarian_membership": grounds(
            "Part 4, Section A, Item 11: Member of or affiliated with the Communist or another totalitarian party, INA "
            "212(a)(3)(D)",
            {11: "Member of or affiliated with a totalitarian party"},
            notes={"p4Line11CB": "The 212(a)(3)(D)(iv) waiver needs a U.S. citizen parent, spouse, son, daughter, brother "
                   "or sister, a permanent resident spouse, son or daughter, or a K-1 petitioner (Part 5)."},
        ),
        "fraud_misrepresentation": grounds(
            "Part 4, Section A, Item 12: Immigration fraud or misrepresentation of a material fact, INA 212(a)(6)(C)(i)",
            {12: "Immigration fraud or misrepresentation"},
            notes={"p4Line12CB": "The 212(i) waiver: extreme hardship to a U.S. citizen or permanent resident spouse or "
                   "parent or the K petitioner (Part 5 and its item 9), or a VAWA self-petitioner. A false claim to "
                   "U.S. citizenship made on or after 09/30/1996 can't be waived on this form (instructions)."},
        ),
        "smuggling_or_civil_penalty": grounds(
            "Part 4, Section A, Items 13-14: Alien smuggling, INA 212(a)(6)(E); civil penalty under INA 274C, INA "
            "212(a)(6)(F)",
            {13: "Alien smuggling", 14: "Subject of a final order for violating INA 274C (civil penalty)"},
            notes={"p4Line13CB": "Waivable only for a spouse, parent, son or daughter smuggled, and only for a returning "
                   "permanent resident or an immediate-relative, family-preference (not fourth) or K applicant "
                   "(instructions)."},
        ),
        "unlawful_presence": grounds(
            "Part 4, Section A, Item 15: The 3-year or 10-year unlawful presence bar, INA 212(a)(9)(B)",
            {15: "3-year or 10-year unlawful presence bar"},
            notes={"p4Line15CB": "The 212(a)(9)(B)(v) waiver: extreme hardship to a U.S. citizen or permanent resident "
                   "spouse or parent (or the K petitioner), named in Part 5 and explained in its item 9. A provisional "
                   "waiver before the consular interview is Form I-601A, not this form."},
        ),
        "prior_removal_or_reentry": grounds(
            "Part 4, Section A, Items 16-17: Previously removed, INA 212(a)(9)(A); unlawful presence or a removal order, "
            "then reentry without admission, INA 212(a)(9)(C)",
            {16: "Previously removed (NACARA and HRIFA only)",
             17: "Reentered or tried to after a removal order or over a year of unlawful presence (NACARA, HRIFA, VAWA)"},
            notes={"p4Line16CB": "Item 16 is only for NACARA and HRIFA applicants, item 17 only for those and approved "
                   "VAWA self-petitioners; anyone else files Form I-212 (form)."},
        ),
        "other_ground": grounds(
            "Part 4, Section A, Item 18: Other ground (specify)",
            {18: "Other"},
            text="p4Line18OtherSpecify",
            notes={"p4Line18OtherSpecify": "The ground or conduct not listed in items 1-17."},
        ),
        # Part 4, Section B (item 19).
        "t_or_sij_grounds": grounds(
            "Part 4, Section B, Item 19: Adjustment based on T nonimmigrant status or SIJ classification: the grounds "
            "(specify)",
            {19: "T or SIJ adjustment grounds (specify)"},
            text="p4Line19OtherSpecify",
            notes={"p4Line19OtherSpecify": "The grounds that apply. An SIJ need not complete Part 5 (instructions)."},
        ),
        # Part 4, Section C (items 20-39), TPS.
        "tps_health_grounds": grounds(
            "Part 4, Section C (TPS), Items 20-22: Communicable disease; physical or mental disorder with harmful "
            "behavior; drug abuser or addict",
            {20: "Communicable disease of public health significance",
             21: "Physical or mental disorder with associated harmful behavior",
             22: "Drug abuser or drug addict"},
            notes={"p4Line20CB": SECTION_C},
        ),
        "tps_criminal_grounds": grounds(
            "Part 4, Section C (TPS), Items 23-27: Simple possession of 30 grams or less of marijuana; prostitution; "
            "procuring; commercialized vice; serious criminal activity with immunity asserted",
            {23: "Single offense of simple possession of 30 grams or less of marijuana",
             24: "Prostitution",
             25: "Procuring prostitutes or persons for prostitution in the past 10 years",
             26: "Other unlawful commercialized vice",
             27: "Serious criminal activity, immunity from prosecution asserted"},
            notes={"p4Line23CB": SECTION_C},
        ),
        "tps_fraud_or_false_claim": grounds(
            "Part 4, Section C (TPS), Items 29-30: Immigration fraud or misrepresentation; false claim to U.S. citizenship",
            {29: "Immigration fraud or misrepresentation", 30: "False claim to U.S. citizenship"},
            notes={"p4Line29CB": SECTION_C},
        ),
        "tps_smuggling_or_civil_penalty": grounds(
            "Part 4, Section C (TPS), Items 31-32: Alien smuggling; civil penalty under INA 274C",
            {31: "Alien smuggling", 32: "Subject of a final order for violating INA 274C (civil penalty)"},
            notes={"p4Line31CB": SECTION_C},
        ),
        "tps_other_grounds": grounds(
            "Part 4, Section C (TPS), Items 28 and 33-39: Missed removal proceeding; draft evasion; polygamy; guardian of "
            "a helpless alien; child custody withheld; unlawful voting; citizenship renounced to avoid tax; other (specify)",
            {28: "Did not attend or remain at a removal proceeding",
             33: "Left or stayed outside the U.S. to evade military service",
             34: "Polygamy",
             35: "Guardian accompanying a helpless inadmissible alien",
             36: "Withheld custody of a U.S. citizen child abroad",
             37: "Unlawful voter",
             38: "Renounced U.S. citizenship to avoid taxation",
             39: "Other"},
            text="p4Line39OtherSpecify",
            notes={"p4Line28CB": SECTION_C,
                   "p4Line39OtherSpecify": "Only with item 39: the ground or conduct not listed in items 20-38."},
        ),
        "inadmissibility_statement": q(
            "Part 4, Item 40: Statement of the acts, convictions or medical conditions that make the applicant "
            "inadmissible, with their dates",
            ["p4Line40Explanation"],
            ["p4Line40Explanation"],
            notes={"p4Line40Explanation": (
                "When each act happened, the date of every conviction and diagnosis, and every arrest's disposition. "
                "Continue in Part 10 or attach a letter and say so here (the form's 'Item Number 39' for that note "
                "means this box). " + NO_WRAP
            )},
        ),
        "vawa_self_hardship": q(
            "Part 5: VAWA self-petitioner claiming extreme hardship to self",
            ["p5VAWACB"],
            ["p5VAWACB"],
            allowed=FILLED_OR_NA,
            notes={"p5VAWACB": "With hardship to self only, items 1.a-8 may stay blank and item 9 explains it."},
            choices={"p5VAWACB": {"VAWA self-petitioner claiming extreme hardship to self": "Y"}},
        ),
        "qualifying_relative": relative(
            5,
            "Part 5, Items 1.a-8: Qualifying relative the waiver rests on: name, physical address, phone and email (if "
            "any), relationship, immigration status, A-Number (if any), date of birth; box for more in Part 10",
            "p5Line1bGivenName", "p5Line1cMiddleName", "p5AddlRelatives", "more qualifying relatives",
            notes={
                "p5Line1aFamilyName": "The U.S. citizen or permanent resident relative the ground's waiver needs (Part 4 "
                "items 1, 11, 12, 15; a qualifying relative is one route for items 4-10). A K-1 or K-2 applicant names "
                "the K petitioner (or parent) as the instructions say. Not needed for SIJ, T or TPS.",
                "p5Line5Relationship": "For example 'U.S. citizen spouse'; a K-1 applicant writes 'Prospective Spouse', a "
                "K-2 child under 18 'Prospective Step-Parent' (instructions).",
                "p5Line6ImmigrationStatus": "For example 'U.S. citizen' or 'Lawful permanent resident'.",
            },
        ),
        "hardship_statement": q(
            "Part 5, Item 9: Statement of the extreme hardship to the qualifying relative (or to a VAWA self-petitioner)",
            ["p5Line9ApplicantStatement"],
            ["p5Line9ApplicantStatement"],
            allowed=FILLED_OR_NA,
            notes={"p5Line9ApplicantStatement": "Required for a ground waived on extreme hardship (Part 4 items 12 and 15). "
                   + LETTER + " " + NO_WRAP},
        ),
        "other_relative": relative(
            6,
            "Part 6, Items 1.a-8: Another relative with ties to the United States: name, physical address, phone and "
            "email (if any), relationship, immigration status, A-Number (if any), date of birth; box for more in Part 10",
            "Pt6Line1b_GivenName", "Pt6Line1c_MiddleName", "p6OtherRelatives", "more relatives with U.S. ties",
            notes={"p6Line1aFamilyName": "Optional: a relative the applicant wants considered. The name boxes are on "
                   "page 6, the rest on page 7.",
                   "p6Line2CityOrTown": "maxlen 20."},
        ),
        "discretion_statement": q(
            "Part 6, Item 9: Statement why the waiver should be granted as a matter of discretion (the favorable factors "
            "outweigh the unfavorable)",
            ["p6Line9ApplicantStatement"],
            ["p6Line9ApplicantStatement"],
            notes={"p6Line9ApplicantStatement": "Required in every case (instructions, What Evidence Must You Submit); an "
                   "SIJ explains humanitarian purposes, family unity or the public interest here. " + LETTER + " "
                   + NO_WRAP},
        ),
        "applicant_contact": q(
            "Part 7, Items 1-3: Applicant's daytime phone, mobile phone (if any), email (if any)",
            ["p7Line1DayPhone", "p7Line2MobilePhone", "p7Line3Email"],
            ["p7Line1DayPhone"],
            notes={"p7Line1DayPhone": PHONE, "p7Line3Email": "maxlen 38."},
        ),
        "applicant_signature": q(
            "Part 7, Items 4.a-4.b: Applicant's signature and date",
            ["Pt7Line6a_SignatureofApplicant", "p7Line6DateofSignature"],
            allowed=[PENDING_SIGNATURE, FILLED],
            notes={"Pt7Line6a_SignatureofApplicant": "Item 4.a despite the Line6 name. A parent or legal guardian may sign "
                   "for an applicant under 14 or mentally incompetent. " + SIGNATURE,
                   "p7Line6DateofSignature": "Item 4.b. " + DATE},
        ),
        "interpreter_block": q(
            "Part 8, Items 1.a-5 and the certification: Interpreter's name, business, phones, email, and the language",
            ["p8Line1aFamilyName", "p8Line1bGivenName", "p8Line2OrgName", "p8Line3DayPhone", "p8Line4MobilePhone",
             "p8Line5Email", "P8Language"],
            ["p8Line1aFamilyName", "p8Line1bGivenName", "p8Line3DayPhone", "P8Language"],
            allowed=FILLED_OR_NA,
            notes={"p8Line3DayPhone": PHONE, "p8Line4MobilePhone": "If any. " + PHONE,
                   "P8Language": "The language in the certification ('fluent in English and ...'); it has no item number."},
        ),
        "interpreter_signature": q(
            "Part 8, Items 6.a-6.b: Interpreter's signature and date",
            ["p8Line7Signature", "p8Line7DateofSignature"],
            allowed=[NOT_APPLICABLE, PENDING_SIGNATURE, FILLED],
            notes={"p8Line7Signature": "Item 6.a despite the Line7 name (maxlen 1). " + SIGNATURE,
                   "p8Line7DateofSignature": "Item 6.b. " + DATE},
        ),
        "preparer_block": q(
            "Part 9, Items 1.a-5: Preparer's name, business, phones, email (from the attorney profile)",
            ["p9Line1aFamilyName", "p9Line1bGivenName", "p9Line2BusinessName", "p9Line3DayPhone", "p9Line4MobilePhone",
             "p9Line5Email"],
            ["p9Line1aFamilyName", "p9Line1bGivenName", "p9Line3DayPhone"],
            allowed=FILLED_OR_NA,
            notes={"p9Line1aFamilyName": "From the attorney profile (attorney_name, firm_name, phone, email). This edition "
                   "has no preparer address and no attorney statement box.",
                   "p9Line3DayPhone": PHONE, "p9Line4MobilePhone": "If any. " + PHONE},
        ),
        "preparer_signature": q(
            "Part 9, Items 6.a-6.b: Preparer's signature and date",
            ["p9Line6aSignature", "p9Line6bDateofSignature"],
            allowed=[NOT_APPLICABLE, PENDING_SIGNATURE, FILLED],
            notes={"p9Line6aSignature": "maxlen 1. " + SIGNATURE, "p9Line6bDateofSignature": DATE},
        ),
        "additional_information": additional_information(),
        "tb_applicant_statement": q(
            "Part 11, Items 1.a-1.b: Class A tuberculosis condition: the applicant's statement, signature and date",
            ["p11Line1aSignature", "p11Line1bAppDateofSignature"],
            allowed=[NOT_APPLICABLE, PENDING_SIGNATURE, FILLED],
            notes={"p11Line1aSignature": "Only with a Class A tuberculosis condition (Part 4 item 1 or 20). " + SIGNATURE,
                   "p11Line1bAppDateofSignature": DATE},
        ),
        "tb_planned_residence": q(
            "Part 11, Items 8.a-8.e: Class A tuberculosis condition: the U.S. address where the applicant or sponsor plans "
            "to reside",
            ["p11Line8StreetNumberName", "p11Line8Unit", "p11Line8AptSteFlrNumber", "p11Line8CityTown", "p11Line8State",
             "p11Line8ZipCode"],
            ["p11Line8StreetNumberName", "p11Line8CityTown", "p11Line8State", "p11Line8ZipCode"],
            allowed=FILLED_OR_NA,
            notes={"p11Line8StreetNumberName": "Only with a Class A tuberculosis condition: the applicant or sponsor "
                   "arranges the care and has the health departments complete their sections (maxlen 34).",
                   "p11Line8State": STATE, "p11Line8ZipCode": ZIP},
            choices={"p11Line8Unit": UNIT},
        ),
        "tb_local_health_department": q(
            "Part 11, Items 2.a-7: Statement by the local (city or county) health department and its physician",
            ["p11Line2Health", "p11Line3NameofHealthDepartment", "p11Line4StreetNumberName", "p11Line4Unit",
             "p11Line4AptSteFlrNumber", "p11Line4CityTown", "p11Line4State", "p11Line4ZipCode", "p11Line5aSignature",
             "p11Line5bDateofSignature", "p11Line5cFamilyName", "p11Line5dGivenName", "p11Line6DayPhone", "p11Line7Email"],
            allowed=[NOT_APPLICABLE],
            notes={"p11Line2Health": "The physician at the local health department completes and signs these; the firm "
                   "leaves every box blank."},
            choices={"p11Line2Health": {"2.a City Health Department": "A", "2.b County Health Department": "B"},
                     "p11Line4Unit": UNIT},
        ),
        "tb_state_health_department": q(
            "Part 11, Items 9.a-13: Endorsement of the state health department official",
            ["p11Line9aSignature", "p11Line9bDateofSignature", "p11Line10NameofState", "p11Line11StreetNumberName",
             "p11Line11Unit", "p11Line11AptSteFlrNumber", "p11Line11CityOrTown", "p11Line11State", "p11Line11ZipCode",
             "p11Line12DayPhone", "p11Line13Email"],
            allowed=[NOT_APPLICABLE],
            notes={"p11Line9aSignature": "The state health department official completes and signs these; the firm leaves "
                   "every box blank."},
            choices={"p11Line11Unit": UNIT},
        ),
    }
    return {
        "kind": "i-601",
        "edition": "01/20/25",
        "field_list": "I-601.json",
        "description": (
            "Form I-601 waiver of grounds of inadmissibility for an immigrant visa, adjustment, K or V status, T or SIJ "
            "adjustment, or TPS (not the I-601A provisional unlawful presence waiver)."
        ),
        "notes": [
            "Select grounds only in the Part 4 section for the benefit sought (A, B or C); every other ground question is "
            "not_applicable, and item 40 explains the grounds selected.",
            "Fraud (item 12) and unlawful presence (item 15) need the qualifying relative in Part 5 and the hardship "
            "statement in its item 9 (or the VAWA box); the discretion statement in Part 6 item 9 is required in every case.",
        ],
        "required_questions": questions,
    }


SCHEMAS = {"i601_inadmissibility_waiver": waiver_application()}

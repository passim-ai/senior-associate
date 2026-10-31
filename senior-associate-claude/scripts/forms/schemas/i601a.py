"""Question schema for Form I-601A, Application for Provisional Unlawful Presence Waiver (INA
212(a)(9)(B)(v), filed in the United States before the consular immigrant visa interview).

Built against the 01/20/25 edition (uscis.gov/i-601a Edition Date panel and the PDF footer of the
form and its instructions, checked 2026-10-30). Field list: schemas/fields/I-601A.json; every box
of the form belongs to one question.

Box names that carry another item's number, read from where each box sits on the page:
Pt1Checkbox25_Checkbox is Part 1 item 26 (other previous entries); Pt1Checkbox30_Checkbox is item 31
(voluntary departure), while Pt1Checkbox30a/30b are items 30.a/30.b; from there on every name is one
below its item: Pt1Checkbox31-37 are items 32-38, Pt1Checkbox38a-38e are 39.a-39.e, 39a/39b are
40.a/40.b and Pt1Checkbox40-44 are items 41-45. Pt2Line4_HeightInches1-3 are the WEIGHT digits (Part
2 item 4). In Part 3, Pt3Line4_Option1-5 are item 1.a-1.e (the basis), Pt3Line6a_DV_KCCCaseNumber is
item 2.a, Pt3Line2a/2b/2c_* box [0] is the DV selectee's name (items 2.b-2.d) and box [1] the
petitioner's name (items 3.c-3.e), and Pt3Line3_CompanyOrOrgName is item 3.f. Pt6Line2_Name is the
preparer's name in Part 6 item 2. In Part 7, Pt7Line6_NameOfLanguage is the language of the
interpreter's certification (no item number), Pt7Line6_EmailAddress is item 6 and
Pt7Line6a_Signature/6b_DateofSignature are items 7.a/7.b. Pt1Line4a/4b/4c and Pt1Line1_AlienNumber
are global: they also fill Part 9 items 1.a-2.

Defects of this edition:
- Part 2 item 5, eye color: the box printed "Gray" stores GRN and the box printed "Green" stores GRY
  (their tooltips follow the printed labels; the on-states are swapped), as on the I-129F 01/20/25.
  The choices are keyed by the printed label, so the filing copy shows the right box.
- Part 4 items 4.a-4.c (the other qualifying relative's name) are unbound in the XFA template
  (fill binds them).
- Part 8 item 7.b has no box for "extends / does not extend beyond the preparation of this
  application"; the attorney marks it by hand at signing.
- The instructions' Processing Information still lists a rejection for "Part 3, Item Number 5"
  (DOS acting before January 3, 2013, to schedule the interview); this edition has no such item, so
  nothing here asks or checks it.
"""
from __future__ import annotations

from typing import Any

from _common import DATE, FILLED, FILLED_OR_NA, NOT_APPLICABLE, PENDING_SIGNATURE, UNIT, YES_NO, q

ON_OR_ABOUT = "mm/dd/yyyy, on or about (the form takes an approximate date)."
STATE = "U.S. address only: 2-letter state code (drop-down)."
ZIP = "U.S. address only: 5-digit ZIP Code."
PHONE = "Digits only."
SIGNATURE = "Protected box; the signer signs the printed form in ink."
PWI = "Status at entry (for example B-2, parolee); PWI for an entry without inspection (instructions, items 17-26)."


def yes_no(label: str, items: list[tuple[str, str]], *, notes: dict[str, str] | None = None) -> dict[str, Any]:
    """Yes/no questions, each one global checkbox group (Y or N). items: (box, item number)."""
    boxes = [box for box, _ in items]
    misnamed = {box: f"Item {item}, despite the name." for box, item in items
                if box.split("_")[0].removeprefix("Pt1Checkbox") != item.replace(".", "")}
    return q(label, boxes, boxes, notes={**misnamed, **(notes or {})}, choices={box: YES_NO for box in boxes})


def entry(label: str, place: str, state: str, date_from: str, date_to: str | None, status: str,
          *, allowed: list[str] | None = None) -> dict[str, Any]:
    """An entry row in form order: the last entry asks the date first (item 17), a previous entry the
    place first (items 20.a and 23.a)."""
    dates = [date_from] + ([date_to] if date_to else [])
    fields = [*dates, place, state, status] if date_to is None else [place, state, *dates, status]
    return q(
        label,
        fields,
        [name for name in fields if name != state],
        allowed=allowed,
        notes={place: "Actual or approximate city or town of the port of entry.",
               state: "The port of entry's state: 2-letter code (drop-down).",
               **{date: ON_OR_ABOUT for date in dates}, status: PWI},
    )


def address(prefix: str) -> list[str]:
    """Item 3.a-3.h, the interpreter's (Pt7Line) or preparer's (Pt8Line) mailing address."""
    return [f"{prefix}3a_StreetNumberName", f"{prefix}3b_Unit", f"{prefix}3b_AptSteFlrNumber", f"{prefix}3c_CityOrTown",
            f"{prefix}3d_State", f"{prefix}3e_ZipCode", f"{prefix}3f_Province", f"{prefix}3g_PostalCode",
            f"{prefix}3h_Country"]


def additional_information() -> dict[str, Any]:
    rows = [[f"Pt9Line{n}a_PageNumber", f"Pt9Line{n}b_PartNumber", f"Pt9Line{n}c_ItemNumber", f"Pt9Line{n}d_AdditionalInfo"]
            for n in range(3, 8)]
    return q(
        "Part 9, Items 3-7: Additional information (page, part, item and text, five entries)",
        [name for row in rows for name in row],
        rows[0],
        allowed=FILLED_OR_NA,
        notes={
            "Pt9Line3a_PageNumber": "Page number (maxlen 2); part and item hold 6 characters each. Items 1.a-2 (name, "
            "A-Number) repeat Part 1 automatically (global boxes).",
            "Pt9Line3d_AdditionalInfo": "Each 'Yes' to Part 1 items 32-38 needs the place, date and a brief description, "
            "and each 'Yes' to items 39.a-45 a complete explanation; a 'Yes' to item 26 lists the other entries; a "
            "stateless applicant explains it (item 14).",
        },
    )


def provisional_waiver() -> dict[str, Any]:
    criminal = [("Pt1Checkbox31_Checkbox", "32"), ("Pt1Checkbox32_Checkbox", "33"), ("Pt1Checkbox33_Checkbox", "34"),
                ("Pt1Checkbox34_Checkbox", "35"), ("Pt1Checkbox35_Checkbox", "36"), ("Pt1Checkbox36_Checkbox", "37"),
                ("Pt1Checkbox37_Checkbox", "38")]
    security = [("Pt1Checkbox38a_Checkbox", "39.a"), ("Pt1Checkbox38b_Checkbox", "39.b"), ("Pt1Checkbox38c_Checkbox", "39.c"),
                ("Pt1Checkbox38d_Checkbox", "39.d"), ("Pt1Checkbox38e_Checkbox", "39.e"), ("Pt1Checkbox39a_Checkbox", "40.a"),
                ("Pt1Checkbox39b_Checkbox", "40.b"), ("Pt1Checkbox40_Checkbox", "41"), ("Pt1Checkbox41_Checkbox", "42"),
                ("Pt1Checkbox42_Checkbox", "43"), ("Pt1Checkbox43_Checkbox", "44"), ("Pt1Checkbox44_Checkbox", "45")]
    race = {"Pt2Checkbox2_1": "White", "Pt2Checkbox2_2": "Asian", "Pt2Checkbox2_3": "Black or African American",
            "Pt2Checkbox2_4": "American Indian or Alaska Native", "Pt2Checkbox2_5": "Native Hawaiian or Other Pacific Islander"}
    basis = {"Pt3Line4_Option1": ("1.a Diversity Visa Program selectee or derivative", "1"),
             "Pt3Line4_Option2": ("1.b Immediate relative petition (I-130)", "2"),
             "Pt3Line4_Option3": ("1.c Preference-based family petition (I-130), including derivatives", "3"),
             "Pt3Line4_Option4": ("1.d Employment-based petition (I-140), including derivatives", "4"),
             "Pt3Line4_Option5": ("1.e Special immigrant/widow petition (I-360), including derivatives", "5")}
    relation = {"a": ("U.S. citizen spouse", "A"), "b": ("U.S. citizen parent", "B"), "c": ("LPR spouse", "C"),
                "d": ("LPR parent", "D")}
    questions: dict[str, dict[str, Any]] = {
        "attorney_box": q(
            "Page 1 attorney box: G-28 attached, attorney State Bar number, attorney's USCIS online account number",
            ["CheckBox1", "AttorneyStateBarNumber", "USCISOnlineAcctNumber"],
            ["CheckBox1"],
            allowed=FILLED_OR_NA,
            notes={
                "CheckBox1": "Select when a G-28 for the applicant is filed with the I-601A.",
                "AttorneyStateBarNumber": "If applicable; blank for an accredited representative.",
                "USCISOnlineAcctNumber": "The attorney's or representative's account number, if any (12 digits); not the "
                "applicant's (Part 1 item 3). Blank when the profile says has_uscis_online_account \"no\".",
            },
            choices={"CheckBox1": {"g28_attached": "1"}},
        ),
        "applicant_numbers": q(
            "Part 1, Items 1-3: A-Number, U.S. Social Security number and USCIS online account number (each if any)",
            ["Pt1Line1_AlienNumber", "Pt1Line2_SSN", "Pt1Line3_USCISELISAcctNumber"],
            allowed=FILLED_OR_NA,
            notes={"Pt1Line1_AlienNumber": "If any: 9 digits, no 'A' (global: also Part 9 item 2).",
                   "Pt1Line2_SSN": "If any: 9 digits (the instructions say N/A when there is none).",
                   "Pt1Line3_USCISELISAcctNumber": "Only with an earlier IOE receipt: 12 digits; not the A-Number."},
        ),
        "applicant_name": q(
            "Part 1, Items 4.a-4.c: Full legal name",
            ["Pt1Line4a_FamilyName", "Pt1Line4b_GivenName", "Pt1Line4c_MiddleName"],
            ["Pt1Line4a_FamilyName", "Pt1Line4b_GivenName"],
            notes={"Pt1Line4a_FamilyName": "Global: also fills Part 9 items 1.a-1.c. USCIS rejects an I-601A without the "
                   "full name (instructions, Processing Information)."},
        ),
        "other_names": q(
            "Part 1, Items 5.a-6.c: Other names used (maiden, married names, nicknames), two rows (more in Part 9)",
            ["Pt1Line5a_FamilyName", "Pt1Line5b_GivenName", "Pt1Line5c_MiddleName", "Pt1Line6a_FamilyName",
             "Pt1Line6b_GivenName", "Pt1Line6c_MiddleName"],
            ["Pt1Line5a_FamilyName", "Pt1Line5b_GivenName"],
            allowed=FILLED_OR_NA,
        ),
        "mailing_address": q(
            "Part 1, Items 7.a-7.f: U.S. mailing address",
            ["Pt1Line7a_InCareofName", "Pt1Line7b_StreetNumberName", "Pt1Line7c_Unit", "Pt1Line7c_AptSteFlrNumber",
             "Pt1Line7d_CityOrTown", "Pt1Line7e_State", "Pt1Line7f_ZipCode"],
            ["Pt1Line7b_StreetNumberName", "Pt1Line7d_CityOrTown", "Pt1Line7e_State", "Pt1Line7f_ZipCode"],
            notes={
                "Pt1Line7b_StreetNumberName": "A U.S. address: the applicant must have one to file (maxlen 34).",
                "Pt1Line7c_Unit": "This group's on-states are ' APT', 'STE' and ' FLR' (not the padded ones of items 9.b "
                "and Parts 7-8); use the choices.",
                "Pt1Line7d_CityOrTown": "maxlen 20.",
                "Pt1Line7e_State": STATE,
                "Pt1Line7f_ZipCode": ZIP,
            },
            choices={"Pt1Line7c_Unit": {"Apt.": " APT", "Ste.": "STE", "Flr.": " FLR"}},
        ),
        "physical_same_as_mailing": q(
            "Part 1, Item 8: Is the current physical address the same as the mailing address?",
            ["Pt1Line8_Checkbox"],
            ["Pt1Line8_Checkbox"],
            notes={"Pt1Line8_Checkbox": "'No' requires physical_address (items 9.a-9.e)."},
            choices={"Pt1Line8_Checkbox": YES_NO},
        ),
        "physical_address": q(
            "Part 1, Items 9.a-9.e: U.S. physical address (if different from the mailing address)",
            ["Pt1Line9a_StreetNumberName", "Pt1Line9b_Unit", "Pt1Line9b_AptSteFlrNumber", "Pt1Line9c_CityOrTown",
             "Pt1Line9d_State", "Pt1Line9e_ZipCode"],
            ["Pt1Line9a_StreetNumberName", "Pt1Line9c_CityOrTown", "Pt1Line9d_State", "Pt1Line9e_ZipCode"],
            allowed=FILLED_OR_NA,
            notes={"Pt1Line9a_StreetNumberName": "Only with 'No' to item 8; USCIS rejects an I-601A without a U.S. "
                   "physical address (maxlen 34).",
                   "Pt1Line9c_CityOrTown": "maxlen 20.", "Pt1Line9d_State": STATE, "Pt1Line9e_ZipCode": ZIP},
            choices={"Pt1Line9b_Unit": UNIT},
        ),
        "applicant_other_information": q(
            "Part 1, Items 10-14: Sex, date of birth, city and country of birth, country of citizenship or nationality",
            ["Pt1Line10_Sex", "Pt1Line11_DateOfBirth", "Pt1Line12_CityOrTownOfBirth", "Pt1Line13_CountryOfBirth",
             "Pt1Line14_CountryOfCitizenship"],
            ["Pt1Line10_Sex", "Pt1Line11_DateOfBirth", "Pt1Line12_CityOrTownOfBirth", "Pt1Line13_CountryOfBirth",
             "Pt1Line14_CountryOfCitizenship"],
            notes={"Pt1Line11_DateOfBirth": DATE + " The applicant must be at least 17 when filing (USCIS rejects it "
                   "otherwise).",
                   "Pt1Line14_CountryOfCitizenship": "'Stateless' if none, explained in Part 9."},
            choices={"Pt1Line10_Sex": {"Male": "M", "Female": "F"}},
        ),
        "parents": q(
            "Part 1, Items 15.a-16.b: Mother's and father's full legal names",
            ["Pt1Line15a_MotherFamilyName", "Pt1Line15b_GivenName", "Pt1Line16a_FamilyName", "Pt1Line16b_GivenName"],
            ["Pt1Line15a_MotherFamilyName", "Pt1Line15b_GivenName", "Pt1Line16a_FamilyName", "Pt1Line16b_GivenName"],
            notes={"Pt1Line16a_FamilyName": "Item 16.a is the FATHER's family name; 15.a-15.b are the mother's."},
        ),
        "last_entry": entry(
            "Part 1, Items 17-19: Last entry into the United States (date, place, status at entry)",
            "Pt1Line18a_PlaceOfEntry", "Pt1Line18b_State", "Pt1Line17_DateOfEntry", None, "Pt1Line19_ImmigrationStatus",
        ),
        "previous_entry_1": entry(
            "Part 1, Items 20.a-22: Previous entry 1 (place, from and to dates, status at entry)",
            "Pt1Line20a_PlaceOfEntry", "Pt1Line20b_State", "Pt1Line21a_DateFrom", "Pt1Line21b_DateTo",
            "Pt1Line22_ImmigrationStatus", allowed=FILLED_OR_NA,
        ),
        "previous_entry_2": entry(
            "Part 1, Items 23.a-25: Previous entry 2 (more in Part 9 with item 26)",
            "Pt1Line23a_PlaceOfEntry", "Pt1Line23b_State", "Pt1Line24a_DateFrom", "Pt1Line24b_DateTo",
            "Pt1Line25_ImmigrationStatus", allowed=FILLED_OR_NA,
        ),
        "other_previous_entries": q(
            "Part 1, Item 26: Are there other previous entries? (Yes: list them in Part 9)",
            ["Pt1Checkbox25_Checkbox"],
            ["Pt1Checkbox25_Checkbox"],
            notes={"Pt1Checkbox25_Checkbox": "Item 26, despite the name. 'Yes' lists each other entry's place, dates "
                   "and status in Part 9."},
            choices={"Pt1Checkbox25_Checkbox": YES_NO},
        ),
        "removal_proceedings": q(
            "Part 1, Items 27-28.b: Currently in removal, exclusion or deportation proceedings; if so, administratively "
            "closed (28.a) or not (28.b)",
            ["Pt1Checkbox27", "Pt1Checkbox28"],
            ["Pt1Checkbox27"],
            notes={"Pt1Checkbox28": "Only with 'Yes' to item 27; one group: [0] is 28.a (page 2), [1] is 28.b (page 3). "
                   "28.b makes the applicant ineligible; 28.a needs the EOIR administrative closure order."},
            choices={"Pt1Checkbox27": YES_NO,
                     "Pt1Checkbox28": {"28.a Administratively closed and not back on EOIR's calendar": "A",
                                       "28.b Not administratively closed, or back on EOIR's calendar": "B"}},
        ),
        "final_order": q(
            "Part 1, Items 29.a-29.b: Subject to a final order of removal, exclusion or deportation; receipt number of "
            "the approved I-212",
            ["Pt1Checkbox29a_Checkbox", "Pt1Line29b_ReceiptNumber"],
            ["Pt1Checkbox29a_Checkbox"],
            notes={"Pt1Line29b_ReceiptNumber": "Only with 'Yes' to 29.a: the APPROVED Form I-212's receipt number (3 "
                   "letters, 10 digits); without an approved I-212 a final order makes the applicant ineligible."},
            choices={"Pt1Checkbox29a_Checkbox": YES_NO},
        ),
        "reinstatement": q(
            "Part 1, Items 30.a-30.b: Served with a Form I-871 notice of intent to reinstate; served with a final "
            "reinstatement decision",
            ["Pt1Checkbox30a_Checkbox", "Pt1Checkbox30b_Checkbox"],
            ["Pt1Checkbox30a_Checkbox"],
            notes={"Pt1Checkbox30b_Checkbox": "Only with 'Yes' to 30.a; a final reinstatement decision ('Yes') makes "
                   "the applicant ineligible."},
            choices={"Pt1Checkbox30a_Checkbox": YES_NO, "Pt1Checkbox30b_Checkbox": YES_NO},
        ),
        "voluntary_departure": q(
            "Part 1, Item 31: Subject to an unexpired grant of voluntary departure from an immigration judge or the BIA",
            ["Pt1Checkbox30_Checkbox"],
            ["Pt1Checkbox30_Checkbox"],
            notes={"Pt1Checkbox30_Checkbox": "Item 31, despite the name (30.a and 30.b are Pt1Checkbox30a/30b). 'Yes' "
                   "makes the applicant ineligible; a withdrawn or terminated grant is 'No' (see items 27-29.a)."},
            choices={"Pt1Checkbox30_Checkbox": YES_NO},
        ),
        "criminal_history": yes_no(
            "Part 1, Items 32-38: False information, smuggling, arrests, charges or convictions, drug trafficking, "
            "prostitution (each 'Yes' explained in Part 9)",
            criminal,
            notes={"Pt1Checkbox33_Checkbox": "Item 34, despite the name: an arrest without a charge still needs the "
                   "arresting authority's or court's statement.",
                   "Pt1Checkbox34_Checkbox": "Item 35, despite the name: 'Yes' needs every court disposition."},
        ),
        "security_and_human_rights": yes_no(
            "Part 1, Items 39.a-45: Torture, killing, injury, sexual violence, religious persecution, armed units, "
            "detention, weapons, child soldiers (each 'Yes' explained in Part 9)",
            security,
        ),
        "biographic_information": q(
            "Part 2, Items 1-6: Ethnicity, race (all that apply), height, weight, eye and hair color",
            ["Pt2Checkbox1", *race, "Pt2Line3_HeightFeet", "Pt2Line3_HeightInches", "Pt2Line4_HeightInches1",
             "Pt2Line4_HeightInches2", "Pt2Line4_HeightInches3", "Pt2Checkbox5", "Pt2Checkbox6"],
            ["Pt2Checkbox1", "Pt2Line3_HeightFeet", "Pt2Line3_HeightInches", "Pt2Line4_HeightInches1",
             "Pt2Line4_HeightInches2", "Pt2Line4_HeightInches3", "Pt2Checkbox5", "Pt2Checkbox6"],
            notes={
                "Pt2Checkbox2_1": "Race: five separate boxes, check all that apply (the audit asks for at least one).",
                "Pt2Line4_HeightInches1": "Item 4, WEIGHT in pounds despite the HeightInches names: one digit per box "
                "(for 95 pounds, 0, 9, 5); 000 if unknown, under 30 or over 699.",
                "Pt2Checkbox5": "Form defect: the box printed 'Gray' stores GRN and the box printed 'Green' stores GRY. "
                "Use the choices (keyed by the printed label).",
            },
            choices={
                "Pt2Checkbox1": {"Hispanic or Latino": "H", "Not Hispanic or Latino": "N"},
                **{box: {label: "Y"} for box, label in race.items()},
                "Pt2Checkbox5": {"Black": "BLK", "Blue": "BLU", "Brown": "BRO", "Gray": "GRN", "Green": "GRY",
                                 "Hazel": "HAZ", "Maroon": "MAR", "Pink": "PNK", "Unknown/Other": "UNK"},
                "Pt2Checkbox6": {"Bald (No hair)": "BAL", "Black": "BLK", "Blond": "BLN", "Brown": "BRO", "Gray": "GRY",
                                 "Red": "RED", "Sandy": "SDY", "White": "WHI", "Unknown/Other": "UNK"},
            },
        ),
        "immigrant_visa_basis": q(
            "Part 3, Item 1: Basis for immigrating (select only one of 1.a-1.e)",
            list(basis),
            notes={"Pt3Line4_Option1": "Item 1, despite the Line4 names: five separate boxes, 1.a-1.e in order; check "
                   "exactly one (the audit checks)."},
            choices={box: {label: state} for box, (label, state) in basis.items()},
        ),
        "dv_case": q(
            "Part 3, Items 2.a-2.d: Diversity Visa case: KCC case number; the principal selectee's name (for a derivative)",
            ["Pt3Line6a_DV_KCCCaseNumber", "Pt3Line2a_FamilyName[0]", "Pt3Line2b_GivenName[0]", "Pt3Line2c_MiddleName[0]"],
            ["Pt3Line6a_DV_KCCCaseNumber"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt3Line6a_DV_KCCCaseNumber": "Item 2.a despite the Line6a name: the DV case number KCC assigned (maxlen "
                "14), from the DV Entrant Status Check printout. Only with 1.a.",
                "Pt3Line2a_FamilyName[0]": "Items 2.b-2.d are box [0], only for a derivative (the spouse or parent who "
                "was selected); box [1] is the petitioner in items 3.c-3.e.",
            },
        ),
        "immigrant_visa_petition": q(
            "Part 3, Items 3.a-3.f: The approved I-130, I-140 or I-360: USCIS receipt number, DOS (NVC) case number, "
            "petitioner's name or company",
            ["Pt3Line3a_USCISReceiptNumber", "Pt3Line3b_CSC_NVCCaseNumber", "Pt3Line2a_FamilyName[1]",
             "Pt3Line2b_GivenName[1]", "Pt3Line2c_MiddleName[1]", "Pt3Line3_CompanyOrOrgName"],
            ["Pt3Line3a_USCISReceiptNumber", "Pt3Line3b_CSC_NVCCaseNumber"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt3Line3a_USCISReceiptNumber": "Only with 1.b-1.e: the approved petition's receipt number (3 letters, "
                "10 digits).",
                "Pt3Line3b_CSC_NVCCaseNumber": "The NVC case number printed on the DOS immigrant visa fee receipt (maxlen "
                "13); it must match the petition in 3.a. The fee receipt goes on top of the application.",
                "Pt3Line2a_FamilyName[1]": "Items 3.c-3.e, the petitioner, are box [1]; box [0] is the DV selectee. A "
                "self-petitioner writes 'Self'.",
                "Pt3Line3_CompanyOrOrgName": "Item 3.f: an employer petitioner's name (maxlen 34).",
            },
        ),
        "qualifying_relative": q(
            "Part 4, Items 1.a-2.d: The qualifying relative (U.S. citizen or LPR spouse or parent) and the relationship",
            ["Pt4Line1a_FamilyName", "Pt4Line1b_GivenName", "Pt4Line1c_MiddleName",
             *[f"Pt4Line2{letter}_Checkbox" for letter in relation]],
            ["Pt4Line1a_FamilyName", "Pt4Line1b_GivenName"],
            notes={"Pt4Line2a_Checkbox": "Four separate boxes, 2.a-2.d; check exactly one. A U.S. citizen or LPR child "
                   "is not a qualifying relative (instructions)."},
            choices={f"Pt4Line2{letter}_Checkbox": {f"2.{letter} {label}": state}
                     for letter, (label, state) in relation.items()},
        ),
        "more_qualifying_relatives": q(
            "Part 4, Item 3: Is there more than one qualifying relative?",
            ["Pt4Line3_Checkbox"],
            ["Pt4Line3_Checkbox"],
            notes={"Pt4Line3_Checkbox": "'Yes' requires other_qualifying_relative (items 4.a-5.d); more in Part 9."},
            choices={"Pt4Line3_Checkbox": YES_NO},
        ),
        "other_qualifying_relative": q(
            "Part 4, Items 4.a-5.d: The other qualifying relative and the relationship",
            ["Pt4Line4a_FamilyName", "Pt4Line4b_GivenName", "Pt4Line4c_MiddleName",
             *[f"Pt4Line5{letter}_Checkbox" for letter in relation]],
            ["Pt4Line4a_FamilyName", "Pt4Line4b_GivenName"],
            allowed=FILLED_OR_NA,
            notes={"Pt4Line4a_FamilyName": "Only with 'Yes' to item 3. The name boxes are unbound in the XFA template "
                   "(fill binds them).",
                   "Pt4Line5a_Checkbox": "Four separate boxes, 5.a-5.d; check exactly one."},
            choices={f"Pt4Line5{letter}_Checkbox": {f"5.{letter} {label}": state}
                     for letter, (label, state) in relation.items()},
        ),
        "hardship_statement": q(
            "Part 5: Statement from applicant (extreme hardship to the qualifying relatives, and why USCIS should approve "
            "as a matter of discretion)",
            ["Pt5Line1_ApplicantStatement"],
            ["Pt5Line1_ApplicantStatement"],
            notes={"Pt5Line1_ApplicantStatement": "One tall box on page 6; continue in Part 9 (or point to an attached "
                   "statement). Break long text into lines that fit."},
        ),
        "applicant_statement": q(
            "Part 6, Items 1-2: Reads English, or the interpreter read it (and the language); a preparer prepared it "
            "(name)",
            ["Pt6Checkbox1", "Pt6Line1b_NameofLanguage", "Pt6Checkbox2", "Pt6Line2_Name"],
            ["Pt6Checkbox1"],
            notes={"Pt6Line1b_NameofLanguage": "Only with 1.b: the language.",
                   "Pt6Line2_Name": "Item 2: the preparer's name, despite the plain name; only with item 2 checked."},
            choices={"Pt6Checkbox1": {"1.a I can read and understand English": "A",
                                      "1.b The interpreter read it to me": "B"},
                     "Pt6Checkbox2": {"2 A preparer prepared this application": "C"}},
        ),
        "applicant_contact": q(
            "Part 6, Items 3-5: Applicant's daytime phone, mobile phone (if any), email (if any)",
            ["Pt6Line3_DaytimeTelephoneNumber", "Pt6Line4_MobileTelephoneNumber", "Pt6Line5_Email"],
            ["Pt6Line3_DaytimeTelephoneNumber"],
            notes={"Pt6Line3_DaytimeTelephoneNumber": PHONE, "Pt6Line4_MobileTelephoneNumber": PHONE},
        ),
        "applicant_signature": q(
            "Part 6, Items 6.a-6.b: Applicant's signature and date (page 7)",
            ["Pt6Line6a_SignatureofApplicant", "Pt6Line6b_DateofSignature"],
            allowed=[PENDING_SIGNATURE, FILLED],
            notes={"Pt6Line6a_SignatureofApplicant": SIGNATURE + " Unsigned, USCIS rejects it.",
                   "Pt6Line6b_DateofSignature": DATE},
        ),
        "interpreter_block": q(
            "Part 7, Items 1-6 and certification: Interpreter's name, business, mailing address, phones, email, language",
            ["Pt7Line1a_InterpreterFamilyName", "Pt7Line1b_InterpreterGivenName", "Pt7Line2_NameofBusinessorOrgName",
             *address("Pt7Line"), "Pt7Line4_DaytimeTelephoneNumber3", "Pt7Line5_MobileTelephoneNumber",
             "Pt7Line6_EmailAddress", "Pt7Line6_NameOfLanguage"],
            ["Pt7Line1a_InterpreterFamilyName", "Pt7Line1b_InterpreterGivenName", "Pt7Line3a_StreetNumberName",
             "Pt7Line3c_CityOrTown", "Pt7Line3h_Country", "Pt7Line4_DaytimeTelephoneNumber3", "Pt7Line6_NameOfLanguage"],
            allowed=FILLED_OR_NA,
            notes={"Pt7Line3d_State": STATE, "Pt7Line3e_ZipCode": ZIP,
                   "Pt7Line6_EmailAddress": "Item 6, the interpreter's email (if any).",
                   "Pt7Line6_NameOfLanguage": "The language in the interpreter's certification (no item number), the same "
                   "as Part 6 item 1.b."},
            choices={"Pt7Line3b_Unit": UNIT},
        ),
        "interpreter_signature": q(
            "Part 7, Items 7.a-7.b: Interpreter's signature and date",
            ["Pt7Line6a_Signature", "Pt7Line6b_DateofSignature"],
            allowed=[NOT_APPLICABLE, PENDING_SIGNATURE, FILLED],
            notes={"Pt7Line6a_Signature": "Item 7.a despite the Line6a name. " + SIGNATURE,
                   "Pt7Line6b_DateofSignature": "Item 7.b. " + DATE},
        ),
        "preparer_block": q(
            "Part 8, Items 1-7: Preparer's name, business, mailing address, phones, email (from the attorney profile), "
            "and statement",
            ["Pt8Line1a_PreparerFamilyName", "Pt8Line1b_PreparerGivenName", "Pt8Line2_BusinessName", *address("Pt8Line"),
             "Pt8Line4_DaytimeTelephoneNumber", "Pt8Line5_MobileTelephoneNumber", "Pt8Line6_EmailAddress",
             "Pt8Line7_Checkbox"],
            ["Pt8Line1a_PreparerFamilyName", "Pt8Line1b_PreparerGivenName", "Pt8Line3a_StreetNumberName",
             "Pt8Line3c_CityOrTown", "Pt8Line3h_Country", "Pt8Line4_DaytimeTelephoneNumber", "Pt8Line7_Checkbox"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt8Line1a_PreparerFamilyName": "From the attorney profile (attorney_name, firm_name, mailing_address, "
                "phone, email).",
                "Pt8Line3d_State": STATE, "Pt8Line3e_ZipCode": ZIP,
                "Pt8Line7_Checkbox": "7.a not an attorney; 7.b an attorney or accredited representative. 7.b has no box "
                "for 'extends / does not extend beyond the preparation of this application': the attorney marks it by "
                "hand at signing (an attorney_action), and 'extends' goes with a G-28 (page 1 box).",
            },
            choices={"Pt8Line3b_Unit": UNIT,
                     "Pt8Line7_Checkbox": {"7.a Not an attorney or accredited representative": "A",
                                           "7.b An attorney or accredited representative": "B"}},
        ),
        "preparer_signature": q(
            "Part 8, Items 8.a-8.b: Preparer's signature and date",
            ["Pt8Line8a_SignatureofPreparer", "Pt8Line8b_DateofSignature"],
            allowed=[NOT_APPLICABLE, PENDING_SIGNATURE, FILLED],
            notes={"Pt8Line8a_SignatureofPreparer": SIGNATURE, "Pt8Line8b_DateofSignature": DATE},
        ),
        "additional_information": additional_information(),
    }
    return {
        "kind": "i-601a",
        "edition": "01/20/25",
        "field_list": "I-601A.json",
        "description": (
            "Form I-601A provisional waiver of the unlawful presence bars (INA 212(a)(9)(B)) for an immigrant visa "
            "applicant in the United States with an approved I-130, I-140 or I-360 (or a DV selection), based on "
            "extreme hardship to a U.S. citizen or LPR spouse or parent."
        ),
        "notes": [
            "Who may file: physically present in the United States, at least 17, with a DOS immigrant visa case "
            "(an approved petition and the DOS immigrant visa fee paid, or a DV selection), inadmissible only for "
            "unlawful presence. Not eligible: an I-485 pending with USCIS, removal proceedings not administratively "
            "closed, a final order without an approved I-212, a final reinstatement decision, an unexpired grant of "
            "voluntary departure (instructions).",
            "The I-601A is a standalone filing: filed with an I-485, I-130, I-212, I-131 or I-765 it is rejected. A "
            "G-1145 may go with it.",
            "Evidence the form doesn't hold: the DOS immigrant visa fee receipt on top (not for DV), the petition "
            "approval notice or the DV Entrant Status Check printout, proof of the qualifying relative's citizenship or "
            "LPR status and of the relationship (when the relative is not the petitioner, or the case is employment "
            "or DV based), the EOIR administrative closure order, and arrest and court records.",
            "Write N/A in a box that does not apply but needs an answer, and None for a zero (How To Complete, item 3).",
        ],
        "required_questions": questions,
    }


SCHEMAS = {"i601a_provisional_waiver": provisional_waiver()}

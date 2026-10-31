"""Question schema for Form I-130, Petition for Alien Relative (edition 04/01/24).

One schema for every relationship (spouse, parent, child, brother or sister) and for a U.S.
citizen or lawful permanent resident petitioner; the parts that depend on the relationship or
the petitioner's status allow not_applicable. Every box on the form belongs to exactly one
question, except the two pre-printed PRESENT boxes (Pt2Line13b_DateTo, Pt2Line43b_DateTo).

Every field name and on-state below was checked against the blank's field list
(schemas/fields/I-130.json), and every checkbox against the printed label beside it on the
04/01/24 PDF. Many names on this edition do not match their part or item number (most of
Part 4 and Part 5); the field notes say which box is which wherever a name misleads. The
audit's I-130 rules (audit_prepared_forms.audit_i130) require the boxes this schema lists as
non-empty in relationship_basis, petitioner_identity, petitioner_mailing_address,
beneficiary_identity and beneficiary_physical_address.
"""
from __future__ import annotations

from typing import Any

from _common import DATE, FILLED, FILLED_OR_NA, NOT_APPLICABLE, PENDING_SIGNATURE, SIGNATURE_STATUSES, UNIT, q

EDITION = "04/01/24"
FIELD_LIST = "I-130.json"


# The unit boxes of this edition carry three different on-state spellings (the padded one is UNIT). Use the
# row's own.
UNIT_PLAIN = {"Apt.": "APT", "Ste.": "STE", "Flr.": "FLR"}
UNIT_MAILING = {"Apt.": "APT ", "Ste.": "STE", "Flr.": "FLR"}  # Part 2 item 10.c only
UNIT_PREPARER = {"Apt.": "APT", "Ste.": "STE", "Flr.": "FLR "}  # Part 8 item 3.b only

STATE = "U.S. addresses only: 2-letter state code (drop-down)."
ZIP = "U.S. addresses only: 5-digit ZIP Code."
FOREIGN_ONLY = "Foreign addresses only."
STREET = (
    "About 27 characters fit on the filing copy (maxlen 34, but the box is narrower and the audit "
    "reports clipped text); continue a longer street in Part 9."
)
UNIT_NOTE = "Unit type; set together with the Apt./Ste./Flr. number box, or leave both blank."
NAME = "About 28 characters fit."
NA_IF_NONE = "Type N/A if none (How To Complete, item 3), or mark the question not_applicable."


def address_fields(
    street: str,
    unit: str,
    number: str,
    city: str,
    state: str | None,
    zip_code: str | None,
    province: str | None,
    postal: str | None,
    country: str | None,
) -> list[str]:
    return [name for name in (street, unit, number, city, state, zip_code, province, postal, country) if name]


def address_notes(
    street: str, unit: str, state: str | None, zip_code: str | None, province: str | None, postal: str | None
) -> dict[str, str]:
    notes = {street: STREET, unit: UNIT_NOTE}
    if state:
        notes[state] = STATE
    if zip_code:
        notes[zip_code] = ZIP
    if province:
        notes[province] = FOREIGN_ONLY
    if postal:
        notes[postal] = FOREIGN_ONLY
    return notes


def yes_no(yes: str, no: str, *, no_state: str = "N") -> dict[str, dict[str, str]]:
    return {yes: {"Yes": "Y"}, no: {"No": no_state}}


# --------------------------------------------------------------------------- Part 2, petitioner


def petitioner_parent(number: int) -> dict[str, Any]:
    if number == 1:
        family, given, middle = "Pt2Line24_FamilyName", "Pt2Line24_GivenName", "Pt2Line24_MiddleName"
        dob, male, female = "Pt2Line25_DateofBirth", "Pt2Line26_Male", "Pt2Line26_Female"
        birth, city, residence = "Pt2Line27_CountryofBirth", "Pt2Line28_CityTownOrVillageOfResidence", "Pt2Line29_CountryOfResidence"
        items, part9 = "24-29", "Page 3, Part 2, Items 24-29"
    else:
        family, given, middle = "Pt2Line30a_FamilyName", "Pt2Line30b_GivenName", "Pt2Line30c_MiddleName"
        dob, male, female = "Pt2Line31_DateofBirth", "Pt2Line32_Male", "Pt2Line32_Female"
        birth, city, residence = "Pt2Line33_CountryofBirth", "Pt2Line34_CityTownOrVillageOfResidence", "Pt2Line35_CountryOfResidence"
        items, part9 = "30-35", "Page 3, Part 2, Items 30-35"
    return q(
        f"Part 2, Items {items}: Petitioner's Parent {number} (name, date of birth, sex, country of birth, "
        "city and country of residence)",
        [family, given, middle, dob, male, female, birth, city, residence],
        [family, given, dob, birth, residence],
        notes={
            family: (
                "Current legal name; give a mother's family name at birth (maiden name) in Part 9 "
                f"({part9}) if it differs. About 27 characters fit."
            ),
            dob: DATE,
            male: "Sex: two separate boxes; set only one.",
            city: (
                "City/town/village of residence. For a deceased parent, the firm's practice is 'Deceased' in "
                "the residence boxes, explained in Part 9."
            ),
        },
        choices={male: {"Male": "Y"}, female: {"Female": "Y"}},
    )


# --------------------------------------------------------------------------- Part 3


def petitioner_biographic() -> dict[str, Any]:
    races = [
        ("Pt3Line2_Race_White", "White", "W"),
        ("Pt3Line2_Race_Asian", "Asian", "A"),
        ("Pt3Line2_Race_Black", "Black or African American", "B"),
        ("Pt3Line2_Race_AmericanIndianAlaskaNative", "American Indian or Alaska Native", "AA"),
        ("Pt3Line2_Race_NativeHawaiianOtherPacificIslander", "Native Hawaiian or Other Pacific Islander", "N"),
    ]
    return q(
        "Part 3, Items 1-6: Petitioner's ethnicity, race, height, weight, eye color, hair color",
        [
            "Pt3Line1_Ethnicity",
            *(name for name, _, _ in races),
            "Pt3Line3_HeightFeet",
            "Pt3Line3_HeightInches",
            "Pt3Line4_Pound1",
            "Pt3Line4_Pound2",
            "Pt3Line4_Pound3",
            "Pt3Line5_EyeColor",
            "Pt3Line6_HairColor",
        ],
        ["Pt3Line1_Ethnicity", "Pt3Line3_HeightFeet", "Pt3Line3_HeightInches", "Pt3Line4_Pound1", "Pt3Line4_Pound2",
         "Pt3Line4_Pound3", "Pt3Line5_EyeColor", "Pt3Line6_HairColor"],
        notes={
            "Pt3Line1_Ethnicity": "The petitioner's own biographic data (not the beneficiary's). One global group; set "
            "it once.",
            "Pt3Line2_Race_White": "Item 2: five separate boxes; set every one that applies, at least one.",
            "Pt3Line3_HeightFeet": "Drop-down, 2-8.",
            "Pt3Line3_HeightInches": "Drop-down, 0-11 with no leading zero ('9', not the '09' the instructions show).",
            "Pt3Line4_Pound1": (
                "Weight is three 1-digit boxes: Pound1 hundreds, Pound2 tens, Pound3 units (150 lb = 1, 5, 0; "
                "95 lb = 0, 9, 5). Unknown, or under 30 or over 699 pounds: 0, 0, 0."
            ),
            "Pt3Line5_EyeColor": "One global group; set it once.",
            "Pt3Line6_HairColor": "One global group (printed on page 5); set it once.",
        },
        choices={
            "Pt3Line1_Ethnicity": {"Hispanic or Latino": "H", "Not Hispanic or Latino": "NH"},
            **{name: {label: state} for name, label, state in races},
            "Pt3Line5_EyeColor": {
                "Black": "BLK",
                "Blue": "BLU",
                "Brown": "BRN",
                "Gray": "GRAY",
                "Green": "GRN",
                "Hazel": "HZL",
                "Maroon": "MRN",
                "Pink": "PNK",
                "Unknown/Other": "OTH",
            },
            "Pt3Line6_HairColor": {
                "Bald (No hair)": "BLD",
                "Black": "BLK",
                "Blond": "BND",
                "Brown": "BRN",
                "Gray": "GRY",
                "Red": "RED",
                "Sandy": "SDY",
                "White": "WHT",
                "Unknown/Other": "OTH",
            },
        },
    )


# --------------------------------------------------------------------------- Part 4, beneficiary


FAMILY_ROWS = [
    # (items, family, given, middle, relationship, date of birth, country of birth)
    ("25-28", "Pt4Line30a_FamilyName", "Pt4Line30b_GivenName", "Pt4Line30c_MiddleName",
     "Pt4Line31_Relationship", "Pt4Line32_DateOfBirth", "Pt4Line49_CountryOfBirth[0]"),
    ("29-32", "Pt4Line34a_FamilyName", "Pt4Line34b_GivenName", "Pt4Line34c_MiddleName",
     "Pt4Line35_Relationship", "Pt4Line36_DateOfBirth", "Pt4Line37_CountryOfBirth"),
    ("33-36", "Pt4Line38a_FamilyName", "Pt4Line38b_GivenName", "Pt4Line38c_MiddleName",
     "Pt4Line39_Relationship", "Pt4Line40_DateOfBirth", "Pt4Line41_CountryOfBirth"),
    ("37-40", "Pt4Line42a_FamilyName", "Pt4Line42b_GivenName", "Pt4Line42c_MiddleName",
     "Pt4Line43_Relationship", "Pt4Line44_DateOfBirth", "Pt4Line45_CountryOfBirth"),
    ("41-44", "Pt4Line46a_FamilyName", "Pt4Line46b_GivenName", "Pt4Line46c_MiddleName",
     "Pt4Line47_Relationship", "Pt4Line48_DateOfBirth", "Pt4Line49_CountryOfBirth[1]"),
]


def beneficiary_family_person(person: int) -> dict[str, Any]:
    items, family, given, middle, relationship, dob, country = FAMILY_ROWS[person - 1]
    first, last = items.split("-")
    notes = {
        family: f"Item {first}.a despite the {family.split('_')[0]} name. {NAME}",
        relationship: "e.g. Spouse, Son, Daughter, Stepson. About 28 characters fit.",
        dob: DATE,
        country: f"Item {last}.",
    }
    if person == 1:
        notes[family] = (
            "Item 25.a despite the Line30 name. The beneficiary's spouse and children, spouse first (the "
            "petitioner, in a spouse petition). not_applicable only if the beneficiary has neither. " + NAME
        )
        notes[country] = "Item 28. Pt4Line49_CountryOfBirth repeats: [0] is Person 1 (item 28), [1] is Person 5 (item 44)."
    elif person == 5:
        notes[family] = (
            f"Item 41.a despite the Line46 name. More children go in Part 9 (Page 7, Part 4, Items 41-44). {NAME}"
        )
        notes[country] = "Item 44: the second box of Pt4Line49_CountryOfBirth."
    return q(
        f"Part 4, Items {items}: Beneficiary's family, Person {person} (name, relationship, date of birth, "
        "country of birth)",
        [family, given, middle, relationship, dob, country],
        [family, given, relationship, dob, country],
        allowed=FILLED_OR_NA,
        notes=notes,
    )


# --------------------------------------------------------------------------- Part 5


def other_relative_petition(number: int) -> dict[str, Any]:
    if number == 1:
        family, given, middle, relationship, items = (
            "Pt4Line6a_FamilyName", "Pt4Line6b_GivenName", "Pt4Line6c_MiddleName", "Pt4Line7_Relationship", "6-7"
        )
    else:
        family, given, middle, relationship, items = (
            "Pt4Line8a_FamilyName", "Pt4Line8b_GivenName", "Pt4Line8c_MiddleName", "Pt4Line9_Relationship", "8-9"
        )
    first, last = items.split("-")
    notes = {
        family: (
            f"Part 5 item {first}.a despite the Pt4 name. Relatives for whom the petitioner is filing separate "
            f"petitions now; not_applicable if none. {NAME}"
        ),
        relationship: (
            f"Part 5 item {last} despite the Pt4 name (not Part 4 item {last}). e.g. Stepson. About 28 "
            "characters fit (maxlen 29)."
        ),
    }
    if number == 2:
        notes[family] += " More relatives go in Part 9 (Page 9, Part 5, Items 8-9)."
    return q(
        f"Part 5, Items {items}: Separate petition for another relative, Relative {number} (name, relationship)",
        [family, given, middle, relationship],
        [family, given, relationship],
        allowed=FILLED_OR_NA,
        notes=notes,
    )


# --------------------------------------------------------------------------- Parts 6-9


def additional_information() -> dict[str, Any]:
    entries = [
        ("Pt9Line3a_PageNumber", "Pt9Line3b_PartNumber", "Pt9Line3c_ItemNumber", "Pt9Line3d_AdditionalInfo"),
        ("Pt9Line4a_PageNumber", "Pt9Line4b_PartNumber", "Pt9Line4c_ItemNumber", "Pt9Line4d_AdditionalInfo"),
        ("Pt9Line5a_PageNumber", "Pt9Line5b_PartNumber", "Pt9Line5c_ItemNumber", "Pt9Line5d_AdditionalInfo"),
        ("Pt9Line6a_PageNumber", "Pt9Line6b_PartNumber", "Pt9Line6c_ItemNumber", "Pt9Line6d_AdditionalInfo"),
        ("Pt9Line9a_PageNumber", "Pt9Line7b_PartNumber", "Pt9Line7c_ItemNumber", "Pt9Line7d_AdditionalInfo"),
    ]
    return q(
        "Part 9, Items 3-7: Additional information (page, part, item, text)",
        [name for entry in entries for name in entry],
        list(entries[0]),
        allowed=FILLED_OR_NA,
        notes={
            "Pt9Line3a_PageNumber": (
                "Page number only (maxlen 2); the part (b) and item (c) boxes hold 6 characters, e.g. '2' and "
                "'14-15'. Items 1-2 (name, A-Number) fill themselves from Part 2 (global fields)."
            ),
            "Pt9Line3d_AdditionalInfo": (
                "Each 'd' box holds 9 lines of 38 characters (Courier 10 pt) and does not wrap: break the lines "
                "yourself (the audit reports clipped text). Use entries 3-7 in order; extra address, employment, "
                "spouse, child and prior-petition rows go here, and so do explanations of approximate dates."
            ),
            "Pt9Line9a_PageNumber": "Item 7.a despite the Line9 name (its b, c, d boxes are Pt9Line7*).",
        },
    )


SCHEMA_NOTES = [
    "One schema for every relationship and petitioner status. Relationship-specific questions allow "
    "not_applicable: child_parent_relationship (child or parent), sibling_adoption (brother/sister), "
    "last_address_together (spouse). Status-specific: petitioner_certificate (U.S. citizen), "
    "petitioner_lpr_admission (LPR). A spouse petition also needs Form I-130A "
    "(schema i130a_spouse_beneficiary).",
    "Five-year histories: Part 2 items 12-15 (addresses) and 42-49 (employment), current first. Rows past "
    "the two on the form go in Part 9, cited by page, part and item.",
    "Pt2Line13b_DateTo and Pt2Line43b_DateTo (the current address's and current employer's Date To) are "
    "pre-printed PRESENT. They are in no question; leave them alone.",
    "Part 9 items 1-2 (name, A-Number) repeat Part 2 automatically: Pt2Line4a/4b/4c and "
    "Pt2Line1_AlienNumber are global fields. Set them once in Part 2.",
    "Type N/A in a box the instructions require answered but that does not apply, and None for a count "
    "of zero (How To Complete, item 3). An approximate date is explained in Part 9 (item 4).",
    "Most Part 4 and Part 5 field names don't match their item numbers (Pt4Line7_CityTownOfBirth is item 6, "
    "Pt4Line20_Yes is item 45, Pt4Line57_* is item 59, Part4Line1_Yes is Part 5 item 1, Pt4Line6a-9 are "
    "Part 5 items 6-9). Read each question's field notes.",
    "On-states: most Yes/No pairs are Y/N, but the 'No' boxes of Part 4 items 45 and 53 are 'Y', and Part 2 "
    "item 36's Lawful Permanent Resident box is 'N'. The unit boxes use three spellings ('APT', ' APT ', "
    "'APT '). Take every value from the question's choices.",
    "Street boxes hold about 27 characters on the filing copy (maxlen 34) and name boxes about 28.",
    "Form defect: the beneficiary's sex boxes (Pt4Line9_Male, Pt4Line9_Female) are unbound in the XFA "
    "template (bind match=none). fill binds the box it writes, so Adobe shows it.",
    "Answer Part 4 item 61 (adjustment_office) or item 62 (consular_processing), and mark the other "
    "not_applicable.",
    "Part 4 items 57-58 (native-script name and address) can't be typed into the PDF: the filing copy "
    "prints '?' for non-Roman characters. See beneficiary_native_script.",
]


def family_petition() -> dict[str, Any]:
    questions: dict[str, dict[str, Any]] = {
        "attorney_box": q(
            "Page 1 attorney box: Form G-28 attached, Volag number, attorney State Bar number, attorney "
            "USCIS online account number",
            ["CheckBox1", "VolagNumber", "AttorneyStateBarNumber", "USCISOnlineAcctNumber"],
            ["CheckBox1", "AttorneyStateBarNumber"],
            allowed=FILLED_OR_NA,
            notes={
                "CheckBox1": "Select when a G-28 for the petitioner is filed with the I-130 (Part 8 item 7.b "
                "'extends').",
                "VolagNumber": "Accredited representatives only; leave blank for an attorney.",
                "AttorneyStateBarNumber": "From the attorney profile; maxlen 10.",
                "USCISOnlineAcctNumber": (
                    "The attorney's USCIS online account number (12 digits), if the profile has one. The petitioner's "
                    "own number is Part 2 item 2. Blank when the profile says has_uscis_online_account \"no\"."
                ),
            },
            choices={"CheckBox1": {"Form G-28 is attached": "1"}},
        ),
        "relationship_basis": q(
            "Part 1, Item 1: I am filing this petition for my (spouse, parent, brother/sister, child)",
            ["Pt1Line1_Spouse", "Pt1Line1_Parent", "Pt1Line1_Siblings", "Pt1Line1_Child"],
            notes={
                "Pt1Line1_Spouse": (
                    "Four separate boxes: set exactly one to Y and leave the others blank (the audit errors "
                    "when none is set). A spouse petition also needs Form I-130A."
                ),
                "Pt1Line1_Child": "Also for a son or daughter 21 or older.",
            },
            choices={
                "Pt1Line1_Spouse": {"Spouse": "Y"},
                "Pt1Line1_Parent": {"Parent": "Y"},
                "Pt1Line1_Siblings": {"Brother/Sister": "Y"},
                "Pt1Line1_Child": {"Child": "Y"},
            },
        ),
        "child_parent_relationship": q(
            "Part 1, Item 2: For a child or parent petition, how the parent-child relationship arose",
            ["Pt1Line2_InWedlock", "Pt1Line2_Stepchild", "Pt1Line2_OutOfWedlock", "Pt1Line2_AdoptedChild"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt1Line2_InWedlock": (
                    "Child and parent petitions only; not_applicable for a spouse or sibling petition. Four "
                    "separate boxes: set exactly one."
                ),
                "Pt1Line2_AdoptedChild": "Not an orphan or Hague Convention adoptee (those use Form I-600/I-800).",
            },
            choices={
                "Pt1Line2_InWedlock": {"Child born to parents married to each other at the time of birth": "Y"},
                "Pt1Line2_Stepchild": {"Stepchild/Stepparent": "Y"},
                "Pt1Line2_OutOfWedlock": {"Child born to parents not married to each other at the time of birth": "Y"},
                "Pt1Line2_AdoptedChild": {"Child was adopted (not an Orphan or Hague Convention adoptee)": "Y"},
            },
        ),
        "sibling_adoption": q(
            "Part 1, Item 3: If the beneficiary is your brother/sister, are you related by adoption?",
            ["Pt1Line3_Yes", "Pt1Line3_No"],
            allowed=FILLED_OR_NA,
            notes={"Pt1Line3_Yes": "Sibling petitions only; not_applicable otherwise. Set one of the two boxes."},
            choices=yes_no("Pt1Line3_Yes", "Pt1Line3_No"),
        ),
        "status_through_adoption": q(
            "Part 1, Item 4: Did you gain lawful permanent resident status or citizenship through adoption?",
            ["Pt1Line4_Yes", "Pt1Line4_No"],
            notes={
                "Pt1Line4_Yes": (
                    "Asked of every petitioner, whatever the relationship. Set one of the two boxes. 'Yes' bars a "
                    "petition for a natural parent (Instructions, Who May Not File)."
                ),
            },
            choices=yes_no("Pt1Line4_Yes", "Pt1Line4_No"),
        ),
        "petitioner_a_number": q(
            "Part 2, Item 1: Petitioner's Alien Registration Number (A-Number), if any",
            ["Pt2Line1_AlienNumber"],
            ["Pt2Line1_AlienNumber"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt2Line1_AlienNumber": (
                    "9 digits, no 'A' (pad an 8-digit number with a leading 0). Global field: it also prints in "
                    "Part 9 item 2; set the base name once. A non-citizen U.S. national need not give one "
                    "(Instructions, Who May File, NOTE 3)."
                ),
            },
        ),
        "petitioner_uscis_online_account": q(
            "Part 2, Item 2: Petitioner's USCIS Online Account Number, if any",
            ["Pt2Line2_USCISOnlineActNumber"],
            ["Pt2Line2_USCISOnlineActNumber"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt2Line2_USCISOnlineActNumber": (
                    "12 digits. Only if the petitioner has a receipt number beginning IOE (Instructions, How To "
                    "Complete, item 5); it is not the A-Number."
                ),
            },
        ),
        "petitioner_ssn": q(
            "Part 2, Item 3: Petitioner's U.S. Social Security Number, if any",
            ["Pt2Line11_SSN"],
            ["Pt2Line11_SSN"],
            allowed=FILLED_OR_NA,
            notes={"Pt2Line11_SSN": "Item 3 despite the Line11 name. 9 digits, no dashes."},
        ),
        "petitioner_identity": q(
            "Part 2, Items 4, 6-9: Petitioner's full legal name, city and country of birth, date of birth, sex",
            ["Pt2Line4a_FamilyName", "Pt2Line4b_GivenName", "Pt2Line4c_MiddleName", "Pt2Line6_CityTownOfBirth",
             "Pt2Line7_CountryofBirth", "Pt2Line8_DateofBirth", "Pt2Line9_Male", "Pt2Line9_Female"],
            ["Pt2Line4a_FamilyName", "Pt2Line4b_GivenName", "Pt2Line6_CityTownOfBirth", "Pt2Line7_CountryofBirth",
             "Pt2Line8_DateofBirth"],
            notes={
                "Pt2Line4a_FamilyName": (
                    "The petitioner's legal name is item 4 (Pt2Line4*); Pt2Line5* is 'Other Names Used'. Global "
                    f"field: it also prints in Part 9 item 1.a; set the base name once. {NAME}"
                ),
                "Pt2Line4b_GivenName": "Global; also prints in Part 9 item 1.b.",
                "Pt2Line4c_MiddleName": "Global; also prints in Part 9 item 1.c. Leave blank if none.",
                "Pt2Line8_DateofBirth": DATE,
                "Pt2Line9_Male": "Item 9 sex: two separate boxes; set only one.",
            },
            choices={"Pt2Line9_Male": {"Male": "Y"}, "Pt2Line9_Female": {"Female": "Y"}},
        ),
        "petitioner_other_names": q(
            "Part 2, Item 5: Other names used (aliases, maiden name, nicknames); one row",
            ["Pt2Line5a_FamilyName", "Pt2Line5b_GivenName", "Pt2Line5c_MiddleName"],
            ["Pt2Line5a_FamilyName"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt2Line5a_FamilyName": f"{NA_IF_NONE} More names go in Part 9 (Page 2, Part 2, Item 5). {NAME}",
            },
        ),
        "petitioner_mailing_address": q(
            "Part 2, Items 10-11: Petitioner's mailing address; is it the same as the physical address?",
            ["Pt2Line10_InCareofName", *address_fields("Pt2Line10_StreetNumberName", "Pt2Line10_Unit",
                                                       "Pt2Line10_AptSteFlrNumber", "Pt2Line10_CityOrTown",
                                                       "Pt2Line10_State", "Pt2Line10_ZipCode", "Pt2Line10_Province",
                                                       "Pt2Line10_PostalCode",
                                                       "Pt2Line10_Country"), "Pt2Line11_Yes", "Pt2Line11_No"],
            ["Pt2Line10_StreetNumberName", "Pt2Line10_CityOrTown", "Pt2Line10_Country"],
            notes={
                **address_notes("Pt2Line10_StreetNumberName", "Pt2Line10_Unit", "Pt2Line10_State", "Pt2Line10_ZipCode",
                                "Pt2Line10_Province", "Pt2Line10_PostalCode"),
                "Pt2Line10_InCareofName": "Item 10.a, if any; maxlen 34.",
                "Pt2Line10_Unit": (
                    "Item 10.c. This row's on-states are spelled 'APT ' (trailing space), 'STE', 'FLR'; use "
                    "the choices."
                ),
                "Pt2Line10_State": (
                    "Item 10.e. State and ZIP Code (10.f) for a U.S. address, which the audit requires; leave "
                    "them blank for a mailing address abroad and use Province and Postal Code."
                ),
                "Pt2Line10_Country": "Item 10.i.",
                "Pt2Line11_Yes": (
                    "Item 11, mailing address same as physical address: two separate boxes, set one. The "
                    "current physical address still goes in items 12-13 (question "
                    "petitioner_physical_address_1_current)."
                ),
            },
            choices={"Pt2Line10_Unit": UNIT_MAILING, **yes_no("Pt2Line11_Yes", "Pt2Line11_No")},
        ),
        "petitioner_physical_address_1_current": q(
            "Part 2, Items 12-13: Physical Address 1 (current) and date from (five-year address history)",
            [*address_fields("Pt2Line12_StreetNumberName", "Pt2Line12_Unit", "Pt2Line12_AptSteFlrNumber",
                             "Pt2Line12_CityOrTown", "Pt2Line12_State", "Pt2Line12_ZipCode", "Pt2Line12_Province",
                             "Pt2Line12_PostalCode", "Pt2Line12_Country"), "Pt2Line13a_DateFrom"],
            ["Pt2Line12_StreetNumberName", "Pt2Line12_CityOrTown", "Pt2Line12_Country", "Pt2Line13a_DateFrom"],
            notes={
                **address_notes("Pt2Line12_StreetNumberName", "Pt2Line12_Unit", "Pt2Line12_State", "Pt2Line12_ZipCode",
                                "Pt2Line12_Province", "Pt2Line12_PostalCode"),
                "Pt2Line12_StreetNumberName": (
                    "The current physical address. Give it even when it is also the mailing address: 13.a carries the "
                    "move-in date that starts the five-year history. " + STREET
                ),
                "Pt2Line13a_DateFrom": DATE + " Date To (13.b) is pre-printed PRESENT; leave it alone.",
            },
            choices={"Pt2Line12_Unit": UNIT},
        ),
        "petitioner_physical_address_2": q(
            "Part 2, Items 14-15: Physical Address 2 and dates",
            [*address_fields("Pt2Line14_StreetNumberName", "Pt2Line14_Unit", "Pt2Line14_AptSteFlrNumber",
                             "Pt2Line14_CityOrTown", "Pt2Line14_State", "Pt2Line14_ZipCode", "Pt2Line14_Province",
                             "Pt2Line14_PostalCode", "Pt2Line14_Country"), "Pt2Line15a_DateFrom", "Pt2Line15b_DateTo"],
            ["Pt2Line14_StreetNumberName", "Pt2Line14_CityOrTown", "Pt2Line14_Country", "Pt2Line15a_DateFrom",
             "Pt2Line15b_DateTo"],
            allowed=FILLED_OR_NA,
            notes={
                **address_notes("Pt2Line14_StreetNumberName", "Pt2Line14_Unit", "Pt2Line14_State", "Pt2Line14_ZipCode",
                                "Pt2Line14_Province", "Pt2Line14_PostalCode"),
                "Pt2Line14_StreetNumberName": (
                    "The address before the current one. not_applicable only if Physical Address 1 covers the whole "
                    "five years. Older addresses in the five years go in Part 9 (Page 2, Part 2, Items "
                    "14-15). " + STREET
                ),
                "Pt2Line15a_DateFrom": DATE,
                "Pt2Line15b_DateTo": DATE + " Should not be after 13.a. Approximate dates are explained in Part 9.",
            },
            choices={"Pt2Line14_Unit": UNIT},
        ),
        "petitioner_marital_status": q(
            "Part 2, Items 16-17: How many times have you been married; current marital status",
            ["Pt2Line16_NumberofMarriages", "Pt2Line17_Single", "Pt2Line17_Married", "Pt2Line17_Divorced",
             "Pt2Line17_Widowed", "Pt2Line17_Separated", "Pt2Line17_Annulled"],
            ["Pt2Line16_NumberofMarriages"],
            notes={
                "Pt2Line16_NumberofMarriages": "A number, including the current marriage; 'None' if never married "
                "(maxlen 5).",
                "Pt2Line17_Single": "Six separate boxes: set exactly one.",
            },
            choices={
                "Pt2Line17_Single": {"Single, Never Married": "Y"},
                "Pt2Line17_Married": {"Married": "Y"},
                "Pt2Line17_Divorced": {"Divorced": "Y"},
                "Pt2Line17_Widowed": {"Widowed": "Y"},
                "Pt2Line17_Separated": {"Separated": "Y"},
                "Pt2Line17_Annulled": {"Annulled": "Y"},
            },
        ),
        "petitioner_current_marriage": q(
            "Part 2, Items 18-19: Date and place of current marriage (if married)",
            ["Pt2Line18_DateOfMarriage", "Pt2Line19a_CityTown", "Pt2Line19b_State", "Pt2Line19c_Province", "Pt2Line19d_Country"],
            ["Pt2Line18_DateOfMarriage", "Pt2Line19a_CityTown", "Pt2Line19d_Country"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt2Line18_DateOfMarriage": DATE + " not_applicable if the petitioner is not currently married.",
                "Pt2Line19a_CityTown": "maxlen 20.",
                "Pt2Line19b_State": STATE,
                "Pt2Line19c_Province": FOREIGN_ONLY,
            },
        ),
        "petitioner_spouse_1": q(
            "Part 2, Items 20-21: Spouse 1 (current spouse first) name and date marriage ended",
            ["PtLine20a_FamilyName", "Pt2Line20b_GivenName", "Pt2Line20c_MiddleName", "Pt2Line21_DateMarriageEnded"],
            ["PtLine20a_FamilyName", "Pt2Line20b_GivenName"],
            allowed=FILLED_OR_NA,
            notes={
                "PtLine20a_FamilyName": (
                    "Item 20.a; the name has no '2' (PtLine20a, not Pt2Line20a). The current spouse goes here "
                    f"(the beneficiary of a spouse petition), else the most recent prior spouse. {NAME}"
                ),
                "Pt2Line21_DateMarriageEnded": DATE + " Leave blank for a current marriage.",
            },
        ),
        "petitioner_spouse_2": q(
            "Part 2, Items 22-23: Spouse 2 (prior spouse) name and date marriage ended",
            ["Pt2Line22a_FamilyName", "Pt2Line22b_GivenName", "Pt2Line22c_MiddleName", "Pt2Line23_DateMarriageEnded"],
            ["Pt2Line22a_FamilyName", "Pt2Line22b_GivenName", "Pt2Line23_DateMarriageEnded"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt2Line22a_FamilyName": (
                    "not_applicable if the petitioner has had only one spouse. More prior spouses go in Part 9 "
                    f"(Page 3, Part 2, Items 22-23). {NAME}"
                ),
                "Pt2Line23_DateMarriageEnded": DATE,
            },
        ),
        "petitioner_parent_1": petitioner_parent(1),
        "petitioner_parent_2": petitioner_parent(2),
        "petitioner_citizenship_status": q(
            "Part 2, Items 36-37: I am a U.S. citizen or lawful permanent resident; citizenship acquired through",
            ["Pt2Line36_USCitizen", "Pt2Line36_LPR", "Pt2Line23a_checkbox", "Pt2Line23b_checkbox",
             "Pt2Line23c_checkbox"],
            notes={
                "Pt2Line36_USCitizen": (
                    "Item 36: two separate boxes, set one. A non-citizen U.S. national selects Lawful Permanent "
                    "Resident (Instructions, Who May File, NOTE 3)."
                ),
                "Pt2Line36_LPR": "The Lawful Permanent Resident box's on-state is 'N', not 'Y'.",
                "Pt2Line23a_checkbox": (
                    "Item 37 despite the Line23 names: citizens only, three separate boxes (birth in the U.S., "
                    "naturalization, parents), set one. Leave all three blank for an LPR."
                ),
            },
            choices={
                "Pt2Line36_USCitizen": {"U.S. Citizen": "Y"},
                "Pt2Line36_LPR": {"Lawful Permanent Resident": "N"},
                "Pt2Line23a_checkbox": {"Birth in the United States": "Y"},
                "Pt2Line23b_checkbox": {"Naturalization": "Y"},
                "Pt2Line23c_checkbox": {"Parents": "Y"},
            },
        ),
        "petitioner_certificate": q(
            "Part 2, Items 38-39: Certificate of Naturalization or Citizenship obtained? Number, place and date of "
            "issuance",
            ["Pt2Line36_Yes", "Pt2Line36_No", "Pt2Line37a_CertificateNumber", "Pt2Line37b_PlaceOfIssuance",
             "Pt2Line37c_DateOfIssuance"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt2Line36_Yes": (
                    "Item 38 despite the Line36 name (the item 36 boxes are Pt2Line36_USCitizen/LPR). Citizens "
                    "only; not_applicable for an LPR petitioner. Set one of the two boxes."
                ),
                "Pt2Line37a_CertificateNumber": "Item 39.a, only if item 38 is Yes.",
                "Pt2Line37b_PlaceOfIssuance": "Item 39.b: city and state (or USCIS office) shown on the certificate.",
                "Pt2Line37c_DateOfIssuance": "Item 39.c. " + DATE,
            },
            choices=yes_no("Pt2Line36_Yes", "Pt2Line36_No"),
        ),
        "petitioner_lpr_admission": q(
            "Part 2, Items 40-41: LPR petitioner's class of admission, date and place of admission; LPR through "
            "marriage?",
            ["Pt2Line40a_ClassOfAdmission", "Pt2Line40b_DateOfAdmission", "Pt2Line40d_CityOrTown", "Pt2Line40e_State",
             "Pt2Line41_Yes", "Pt2Line41_No"],
            ["Pt2Line40a_ClassOfAdmission", "Pt2Line40b_DateOfAdmission", "Pt2Line40d_CityOrTown", "Pt2Line40e_State"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt2Line40a_ClassOfAdmission": (
                    "LPR petitioners only; not_applicable for a U.S. citizen. The category code on the green card "
                    "(e.g. IR1, E21)."
                ),
                "Pt2Line40b_DateOfAdmission": DATE + " The 'Resident Since' date.",
                "Pt2Line40d_CityOrTown": "Item 40.c despite the 40d name: city of the port of entry or adjusting "
                "office.",
                "Pt2Line40e_State": "Item 40.d despite the 40e name. 2-letter state code (drop-down).",
                "Pt2Line41_Yes": (
                    "Item 41, LPR status through marriage to a U.S. citizen or LPR: set one. 'Yes' on a spouse "
                    "petition brings in the five-year bar of INA 204(a)(2)(A) on petitioning for a new spouse."
                ),
            },
            choices=yes_no("Pt2Line41_Yes", "Pt2Line41_No"),
        ),
        "petitioner_employer_1_current": q(
            "Part 2, Items 42-45: Employer 1 (current employment, or 'Unemployed'), occupation, date from",
            ["Pt2Line40_EmployerOrCompName", *address_fields("Pt2Line41_StreetNumberName", "Pt2Line41_Unit",
                                                             "Pt2Line41_AptSteFlrNumber", "Pt2Line41_CityOrTown",
                                                             "Pt2Line41_State", "Pt2Line41_ZipCode",
                                                             "Pt2Line41_Province", "Pt2Line41_PostalCode",
                                                             "Pt2Line41_Country"), "Pt2Line42_Occupation", "Pt2Line43a_DateFrom"],
            ["Pt2Line40_EmployerOrCompName", "Pt2Line43a_DateFrom"],
            notes={
                **address_notes("Pt2Line41_StreetNumberName", "Pt2Line41_Unit", "Pt2Line41_State", "Pt2Line41_ZipCode",
                                "Pt2Line41_Province", "Pt2Line41_PostalCode"),
                "Pt2Line40_EmployerOrCompName": (
                    "Item 42 despite the Line40 name. Type 'Unemployed' if currently unemployed (the form's "
                    "instruction) and leave the address and occupation blank. maxlen 34."
                ),
                "Pt2Line41_StreetNumberName": "Item 43.a despite the Line41 name (the item 41 boxes are "
                "Pt2Line41_Yes/No). " + STREET,
                "Pt2Line41_Country": "Item 43.h; maxlen 29.",
                "Pt2Line42_Occupation": "Item 44 despite the Line42 name.",
                "Pt2Line43a_DateFrom": "Item 45.a. " + DATE + " Date To (45.b) is pre-printed PRESENT; leave it alone.",
            },
            choices={"Pt2Line41_Unit": UNIT_PLAIN},
        ),
        "petitioner_employer_2": q(
            "Part 2, Items 46-49: Employer 2, occupation and dates",
            ["Pt2Line44_EmployerOrOrgName", *address_fields("Pt2Line45_StreetNumberName", "Pt2Line45_Unit",
                                                            "Pt2Line45_AptSteFlrNumber", "Pt2Line45_CityOrTown",
                                                            "Pt2Line45_State", "Pt2Line45_ZipCode",
                                                            "Pt2Line45_Province", "Pt2Line45_PostalCode",
                                                            "Pt2Line45_Country"), "Pt2Line46_Occupation", "Pt2Line47a_DateFrom", "Pt2Line47b_DateTo"],
            ["Pt2Line44_EmployerOrOrgName", "Pt2Line47a_DateFrom", "Pt2Line47b_DateTo"],
            allowed=FILLED_OR_NA,
            notes={
                **address_notes("Pt2Line45_StreetNumberName", "Pt2Line45_Unit", "Pt2Line45_State", "Pt2Line45_ZipCode",
                                "Pt2Line45_Province", "Pt2Line45_PostalCode"),
                "Pt2Line44_EmployerOrOrgName": (
                    "Item 46 despite the Line44 name. The job (or period of unemployment) before Employer 1; "
                    "not_applicable only if Employer 1 covers the whole five years. Older jobs in the five years "
                    "go in Part 9 (Page 4, Part 2, Items 46-49). maxlen 34."
                ),
                "Pt2Line45_StreetNumberName": "Item 47.a despite the Line45 name. " + STREET,
                "Pt2Line46_Occupation": "Item 48 despite the Line46 name.",
                "Pt2Line47a_DateFrom": "Item 49.a. " + DATE,
                "Pt2Line47b_DateTo": "Item 49.b. " + DATE,
            },
            choices={"Pt2Line45_Unit": UNIT_PLAIN},
        ),
        "petitioner_biographic": petitioner_biographic(),
        "beneficiary_a_number": q(
            "Part 4, Item 1: Beneficiary's Alien Registration Number (A-Number), if any",
            ["Pt4Line1_AlienNumber"],
            ["Pt4Line1_AlienNumber"],
            allowed=FILLED_OR_NA,
            notes={"Pt4Line1_AlienNumber": "9 digits, no 'A'."},
        ),
        "beneficiary_uscis_online_account": q(
            "Part 4, Item 2: Beneficiary's USCIS Online Account Number, if any",
            ["Pt4Line2_USCISOnlineActNumber"],
            ["Pt4Line2_USCISOnlineActNumber"],
            allowed=FILLED_OR_NA,
            notes={"Pt4Line2_USCISOnlineActNumber": "12 digits; only with a receipt number beginning IOE."},
        ),
        "beneficiary_ssn": q(
            "Part 4, Item 3: Beneficiary's U.S. Social Security Number, if any",
            ["Pt4Line3_SSN"],
            ["Pt4Line3_SSN"],
            allowed=FILLED_OR_NA,
            notes={"Pt4Line3_SSN": "9 digits, no dashes."},
        ),
        "beneficiary_identity": q(
            "Part 4, Items 4, 6-9: Beneficiary's full name, city and country of birth, date of birth, sex",
            ["Pt4Line4a_FamilyName", "Pt4Line4b_GivenName", "Pt4Line4c_MiddleName", "Pt4Line7_CityTownOfBirth",
             "Pt4Line8_CountryOfBirth", "Pt4Line9_DateOfBirth", "Pt4Line9_Male", "Pt4Line9_Female"],
            ["Pt4Line4a_FamilyName", "Pt4Line4b_GivenName", "Pt4Line7_CityTownOfBirth", "Pt4Line8_CountryOfBirth",
             "Pt4Line9_DateOfBirth"],
            notes={
                "Pt4Line4a_FamilyName": NAME,
                "Pt4Line4c_MiddleName": "Leave blank if none.",
                "Pt4Line7_CityTownOfBirth": "Item 6 despite the Line7 name; maxlen 38.",
                "Pt4Line8_CountryOfBirth": "Item 7 despite the Line8 name.",
                "Pt4Line9_DateOfBirth": "Item 8 despite the Line9 name. " + DATE,
                "Pt4Line9_Male": (
                    "Item 9 sex: two separate boxes; set only one. Form defect: both boxes are unbound in the XFA "
                    "template (bind match=none); fill binds the one it writes, so Adobe shows it."
                ),
            },
            choices={"Pt4Line9_Male": {"Male": "Y"}, "Pt4Line9_Female": {"Female": "Y"}},
        ),
        "beneficiary_other_names": q(
            "Part 4, Item 5: Beneficiary's other names used (aliases, maiden name, nicknames); one row",
            ["P4Line5a_FamilyName", "Pt4Line5b_GivenName", "Pt4Line5c_MiddleName"],
            ["P4Line5a_FamilyName"],
            allowed=FILLED_OR_NA,
            notes={
                "P4Line5a_FamilyName": (
                    f"Item 5.a; the name starts 'P4', not 'Pt4'. {NA_IF_NONE} More names go in Part 9 "
                    f"(Page 5, Part 4, Item 5). {NAME}"
                ),
            },
        ),
        "beneficiary_petitioned_by_others": q(
            "Part 4, Item 10: Has anyone else ever filed a petition for the beneficiary?",
            ["Pt4Line10_Yes", "Pt4Line10_No", "Pt4Line10_Unknown"],
            notes={
                "Pt4Line10_Yes": (
                    "Three separate boxes: set exactly one. Anyone other than this petitioner (an earlier spouse, "
                    "an employer's I-140, a parent's I-130). 'Unknown' only if neither the petitioner nor the "
                    "beneficiary knows (the form's note). Explain a 'Yes' in Part 9 (Page 5, Part 4, Item 10)."
                ),
            },
            choices={
                "Pt4Line10_Yes": {"Yes": "Y"},
                "Pt4Line10_No": {"No": "N"},
                "Pt4Line10_Unknown": {"Unknown": "U"},
            },
        ),
        "beneficiary_physical_address": q(
            "Part 4, Item 11: Beneficiary's physical address",
            address_fields("Pt4Line11_StreetNumberName", "Pt4Line11_Unit", "Pt4Line11_AptSteFlrNumber",
                           "Pt4Line11_CityOrTown", "Pt4Line11_State", "Pt4Line11_ZipCode", "Pt4Line11_Province",
                           "Pt4Line11_PostalCode", "Pt4Line11_Country"),
            ["Pt4Line11_CityOrTown", "Pt4Line11_Country"],
            notes={
                **address_notes("Pt4Line11_StreetNumberName", "Pt4Line11_Unit", "Pt4Line11_State", "Pt4Line11_ZipCode",
                                "Pt4Line11_Province", "Pt4Line11_PostalCode"),
                "Pt4Line11_StreetNumberName": (
                    "Required for a U.S. address. For a home abroad with no street number or name, leave 11.a and 11.b "
                    "blank, as the form says. " + STREET
                ),
                "Pt4Line11_Country": "maxlen 29.",
            },
            choices={"Pt4Line11_Unit": UNIT_PLAIN},
        ),
        "beneficiary_us_address": q(
            "Part 4, Item 12: Address in the United States where the beneficiary intends to live ('SAME' if item 11)",
            ["Pt4Line12a_StreetNumberName", "Pt4Line12b_Unit", "Pt4Line12b_AptSteFlrNumber", "Pt4Line12c_CityOrTown",
             "Pt4Line12d_State", "Pt4Line12e_ZipCode"],
            ["Pt4Line12a_StreetNumberName"],
            notes={
                "Pt4Line12a_StreetNumberName": (
                    "Type SAME here, and nothing else in the row, when it is the item 11 address (the form's "
                    "instruction). " + STREET
                ),
                "Pt4Line12b_Unit": UNIT_NOTE,
                "Pt4Line12d_State": "2-letter state code (drop-down).",
                "Pt4Line12e_ZipCode": "5-digit ZIP Code.",
            },
            choices={"Pt4Line12b_Unit": UNIT},
        ),
        "beneficiary_foreign_address": q(
            "Part 4, Item 13: Beneficiary's address outside the United States ('SAME' if item 11)",
            ["Pt4Line13_StreetNumberName", "Pt4Line13_Unit", "Pt4Line13_AptSteFlrNumber", "Pt4Line13_CityOrTown",
             "Pt4Line13_Province", "Pt4Line13_PostalCode", "Pt4Line13_Country"],
            ["Pt4Line13_StreetNumberName"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt4Line13_StreetNumberName": (
                    "Item 13.a. SAME when item 11 is the address abroad (the form's instruction). A beneficiary "
                    "living in the U.S. with no address abroad: type N/A here (filled) or mark not_applicable. "
                    + STREET
                ),
                "Pt4Line13_Unit": UNIT_NOTE,
                "Pt4Line13_Province": "Item 13.d.",
                "Pt4Line13_PostalCode": "Item 13.e.",
                "Pt4Line13_Country": "Item 13.f.",
            },
            choices={"Pt4Line13_Unit": UNIT},
        ),
        "beneficiary_contact": q(
            "Part 4, Items 14-16: Beneficiary's daytime phone, mobile phone, email (if any)",
            ["Pt4Line14_DaytimePhoneNumber", "Pt4Line15_MobilePhoneNumber", "Pt4Line16_EmailAddress"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt4Line14_DaytimePhoneNumber": "If any. Digits only; maxlen 15, room for a country code.",
                "Pt4Line15_MobilePhoneNumber": "If any; maxlen 15.",
                "Pt4Line16_EmailAddress": "If any. About 38 characters fit.",
            },
        ),
        "beneficiary_marital_status": q(
            "Part 4, Items 17-18: How many times has the beneficiary been married; current marital status",
            ["Pt4Line17_NumberofMarriages", "Pt4Line18_MaritalStatus"],
            ["Pt4Line17_NumberofMarriages", "Pt4Line18_MaritalStatus"],
            notes={
                "Pt4Line17_NumberofMarriages": "A number, including the current marriage; 'None' if never married "
                "(maxlen 5).",
                "Pt4Line18_MaritalStatus": "One global group (unlike the petitioner's six separate boxes); set it once.",
            },
            choices={
                "Pt4Line18_MaritalStatus": {
                    "Single, Never Married": "SNM",
                    "Married": "M",
                    "Divorced": "D",
                    "Widowed": "W",
                    "Separated": "S",
                    "Annulled": "A",
                },
            },
        ),
        "beneficiary_current_marriage": q(
            "Part 4, Items 19-20: Date and place of the beneficiary's current marriage (if married)",
            ["Pt4Line19_DateOfMarriage", "Pt4Line20a_CityTown", "Pt4Line20b_State", "Pt4Line20c_Province", "Pt4Line20d_Country"],
            ["Pt4Line19_DateOfMarriage", "Pt4Line20a_CityTown", "Pt4Line20d_Country"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt4Line19_DateOfMarriage": DATE + " not_applicable if the beneficiary is not currently married.",
                "Pt4Line20a_CityTown": "maxlen 20.",
                "Pt4Line20b_State": STATE,
                "Pt4Line20c_Province": FOREIGN_ONLY,
            },
        ),
        "beneficiary_spouse_1": q(
            "Part 4, Items 21-22: Beneficiary's Spouse 1 (current spouse first) name and date marriage ended",
            ["Pt4Line16a_FamilyName", "Pt4Line16b_GivenName", "Pt4Line16c_MiddleName", "Pt4Line17_DateMarriageEnded[0]"],
            ["Pt4Line16a_FamilyName", "Pt4Line16b_GivenName"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt4Line16a_FamilyName": (
                    "Item 21.a despite the Line16 name. The current spouse (the petitioner, in a spouse petition), "
                    f"else the most recent prior spouse. {NAME}"
                ),
                "Pt4Line17_DateMarriageEnded[0]": (
                    "Item 22. Pt4Line17_DateMarriageEnded repeats: [0] is Spouse 1 (item 22), [1] is Spouse 2 "
                    f"(item 24). {DATE} Leave blank for a current marriage."
                ),
            },
        ),
        "beneficiary_spouse_2": q(
            "Part 4, Items 23-24: Beneficiary's Spouse 2 (prior spouse) name and date marriage ended",
            ["Pt4Line18a_FamilyName", "Pt4Line18b_GivenName", "Pt4Line18c_MiddleName", "Pt4Line17_DateMarriageEnded[1]"],
            ["Pt4Line18a_FamilyName", "Pt4Line18b_GivenName", "Pt4Line17_DateMarriageEnded[1]"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt4Line18a_FamilyName": (
                    "Item 23.a despite the Line18 name. not_applicable if the beneficiary has had only one spouse; "
                    f"more prior spouses go in Part 9 (Page 6, Part 4, Items 23-24). {NAME}"
                ),
                "Pt4Line17_DateMarriageEnded[1]": "Item 24: the second box of Pt4Line17_DateMarriageEnded. " + DATE,
            },
        ),
        **{f"beneficiary_family_person_{n}": beneficiary_family_person(n) for n in range(1, 6)},
        "beneficiary_ever_in_us": q(
            "Part 4, Item 45: Was the beneficiary EVER in the United States?",
            ["Pt4Line20_Yes", "Pt4Line20_No"],
            notes={
                "Pt4Line20_Yes": "Item 45 despite the Line20 name. Two separate boxes; set one.",
                "Pt4Line20_No": "The No box's on-state is 'Y', not 'N'.",
            },
            choices=yes_no("Pt4Line20_Yes", "Pt4Line20_No", no_state="Y"),
        ),
        "beneficiary_arrival": q(
            "Part 4, Items 46.a and 46.c: Beneficiary in the U.S. now: class of admission and date of arrival",
            ["Pt4Line21a_ClassOfAdmission", "Pt4Line21c_DateOfArrival"],
            ["Pt4Line21a_ClassOfAdmission", "Pt4Line21c_DateOfArrival"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt4Line21a_ClassOfAdmission": (
                    "Only if the beneficiary is in the U.S. now; not_applicable otherwise. A drop-down of codes, "
                    "not free text: B2 (not 'B-2'), F1, H1B, K1, PAR (parole), EWI (entry without inspection)."
                ),
                "Pt4Line21c_DateOfArrival": DATE,
            },
        ),
        "beneficiary_i94": q(
            "Part 4, Items 46.b and 46.d: Form I-94 number and date authorized stay expired or will expire",
            ["Pt4Line21b_ArrivalDeparture", "Pt4Line21d_DateExpired"],
            ["Pt4Line21b_ArrivalDeparture", "Pt4Line21d_DateExpired"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt4Line21b_ArrivalDeparture": (
                    "The 11-character I-94 number (maxlen 11). not_applicable if the beneficiary is not in the U.S. "
                    "or entered without inspection (no I-94)."
                ),
                "Pt4Line21d_DateExpired": DATE + " Or 'D/S' for duration of status, as the I-94 shows.",
            },
        ),
        "beneficiary_travel_document": q(
            "Part 4, Items 47-50: Passport number, travel document number, country of issuance, expiration date",
            ["Pt4Line22_PassportNumber", "Pt4Line23_TravelDocNumber", "Pt4Line24_CountryOfIssuance", "Pt4Line25_ExpDate"],
            ["Pt4Line24_CountryOfIssuance", "Pt4Line25_ExpDate"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt4Line22_PassportNumber": (
                    "The passport or travel document the beneficiary used to travel to the U.S., even if expired "
                    "(Instructions, item 7); give one of 47 or 48. not_applicable if the beneficiary never "
                    "traveled on one."
                ),
                "Pt4Line23_TravelDocNumber": "Only if a travel document other than a passport was used.",
                "Pt4Line25_ExpDate": DATE,
            },
        ),
        "beneficiary_employment": q(
            "Part 4, Items 51-52: Beneficiary's current employer (or 'Unemployed') and date employment began",
            ["Pt4Line26_NameOfCompany", *address_fields("Pt4Line26_StreetNumberName", "Pt4Line26_Unit",
                                                        "Pt4Line26_AptSteFlrNumber", "Pt4Line26_CityOrTown",
                                                        "Pt4Line26_State", "Pt4Line26_ZipCode", "Pt4Line26_Province",
                                                        "Pt4Line26_PostalCode",
                                                        "Pt4Line26_Country"), "Pt4Line27_DateEmploymentBegan"],
            ["Pt4Line26_NameOfCompany"],
            notes={
                **address_notes("Pt4Line26_StreetNumberName", "Pt4Line26_Unit", "Pt4Line26_State", "Pt4Line26_ZipCode",
                                "Pt4Line26_Province", "Pt4Line26_PostalCode"),
                "Pt4Line26_NameOfCompany": (
                    "Item 51.a. Current employer, in the U.S. or abroad; 'Unemployed' if none (the form's "
                    "instruction), with the rest of the row blank. maxlen 38."
                ),
                "Pt4Line26_StreetNumberName": "Item 51.b. " + STREET,
                "Pt4Line27_DateEmploymentBegan": "Item 52 despite the Line27 name. " + DATE,
            },
            choices={"Pt4Line26_Unit": UNIT},
        ),
        "beneficiary_proceedings": q(
            "Part 4, Items 53-56: Was the beneficiary EVER in immigration proceedings? Type, place and date",
            ["Pt4Line28_Yes", "Pt4Line28_No", "Pt4Line54_Removal", "Pt4Line54_Exclusion", "Pt4Line54_Rescission",
             "Pt4Line54_JudicialProceedings", "Pt4Line55a_CityOrTown", "Pt4Line55b_State", "Pt4Line56_Date"],
            notes={
                "Pt4Line28_Yes": "Item 53 despite the Line28 name. Two separate boxes; set one.",
                "Pt4Line28_No": "The No box's on-state is 'Y', not 'N'.",
                "Pt4Line54_Removal": "Item 54, only with a Yes: four separate boxes; set each type that applies.",
                "Pt4Line55a_CityOrTown": (
                    "Item 55.a, only with a Yes. Not a name: the beneficiary's native-script name is "
                    "Pt4Line55a_FamilyName (item 57.a). maxlen 20."
                ),
                "Pt4Line55b_State": "Item 55.b. 2-letter state code (drop-down).",
                "Pt4Line56_Date": "Item 56, only with a Yes. " + DATE + " More proceedings go in Part 9.",
            },
            choices={
                **yes_no("Pt4Line28_Yes", "Pt4Line28_No", no_state="Y"),
                "Pt4Line54_Removal": {"Removal": "Y"},
                "Pt4Line54_Exclusion": {"Exclusion/Deportation": "Y"},
                "Pt4Line54_Rescission": {"Rescission": "Y"},
                "Pt4Line54_JudicialProceedings": {"Other Judicial Proceedings": "Y"},
            },
        ),
        "beneficiary_native_script": q(
            "Part 4, Items 57-58: Beneficiary's name and foreign address in the native written language (if not Roman "
            "letters)",
            ["Pt4Line55a_FamilyName", "Pt4Line55b_GivenName", "Pt4Line55c_MiddleName", "Pt4Line56_StreetNumberName",
             "Pt4Line56_Unit", "Pt4Line56_AptSteFlrNumber", "Pt4Line56_CityOrTown", "Pt4Line56_Province",
             "Pt4Line56_PostalCode", "Pt4Line56_Country"],
            ["Pt4Line55a_FamilyName", "Pt4Line55b_GivenName"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt4Line55a_FamilyName": (
                    "Item 57.a despite the Line55 name. not_applicable when the native language uses Roman letters. "
                    "The filing copy can't show non-Roman script: fill's appearances print '?' for each character "
                    "(checked with Cyrillic), and the audit's visible-value check skips text without 3 Latin "
                    "letters or digits, so nothing flags it. Leave items 57-58 blank in the PDF, mark the question "
                    "manual_review with an open item, and have them written by hand on the printed copy."
                ),
                "Pt4Line56_StreetNumberName": "Item 58.a despite the Line56 name (the address abroad, in native "
                "script).",
                "Pt4Line56_Unit": UNIT_NOTE,
                "Pt4Line56_Province": "Item 58.d.",
                "Pt4Line56_PostalCode": "Item 58.e.",
                "Pt4Line56_Country": "Item 58.f.",
            },
            choices={"Pt4Line56_Unit": UNIT},
        ),
        "last_address_together": q(
            "Part 4, Items 59-60: Spouse petition: last address where you and the beneficiary physically lived "
            "together, and dates",
            [*address_fields("Pt4Line57_StreetNumberName", "Pt4Line57_Unit", "Pt4Line57_AptSteFlrNumber",
                             "Pt4Line57_CityOrTown", "Pt4Line57_State", "Pt4Line57_ZipCode", "Pt4Line57_Province",
                             "Pt4Line57_PostalCode", "Pt4Line57_Country"), "Pt4Line58a_DateFrom", "Pt4Line58b_DateTo"],
            ["Pt4Line57_StreetNumberName"],
            allowed=FILLED_OR_NA,
            notes={
                **address_notes("Pt4Line57_StreetNumberName", "Pt4Line57_Unit", "Pt4Line57_State", "Pt4Line57_ZipCode",
                                "Pt4Line57_Province", "Pt4Line57_PostalCode"),
                "Pt4Line57_StreetNumberName": (
                    "Item 59.a despite the Line57 name. Spouse petitions only; not_applicable otherwise. 'Never lived "
                    "together' here, with the rest blank, if the spouses never lived together (the form's "
                    "instruction). "
                    + STREET
                ),
                "Pt4Line58a_DateFrom": "Item 60.a despite the Line58 name. " + DATE,
                "Pt4Line58b_DateTo": "Item 60.b. " + DATE + " Type PRESENT if the spouses live there now.",
            },
            choices={"Pt4Line57_Unit": UNIT},
        ),
        "adjustment_office": q(
            "Part 4, Item 61: Beneficiary in the U.S. will apply for adjustment of status at the USCIS office in "
            "(city, state)",
            ["Pt4Line60a_CityOrTown", "Pt4Line60b_State"],
            ["Pt4Line60a_CityOrTown", "Pt4Line60b_State"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt4Line60a_CityOrTown": (
                    "Item 61.a despite the Line60 name. The USCIS field office with jurisdiction over the "
                    "beneficiary's residence. Answer item 61 or item 62 (consular_processing), not both. maxlen 20."
                ),
                "Pt4Line60b_State": "Item 61.b. 2-letter state code (drop-down).",
            },
        ),
        "consular_processing": q(
            "Part 4, Item 62: Beneficiary will apply for an immigrant visa abroad at the U.S. Embassy or Consulate in",
            ["Pt4Line61a_CityOrTown", "Pt4Line61b_Province", "Pt4Line61c_Country"],
            ["Pt4Line61a_CityOrTown", "Pt4Line61c_Country"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt4Line61a_CityOrTown": (
                    "Item 62.a despite the Line61 name. Usually the consulate in the country of last residence; "
                    "another post may decline the case (the form's note). maxlen 20."
                ),
                "Pt4Line61b_Province": "Item 62.b, if any.",
                "Pt4Line61c_Country": "Item 62.c.",
            },
        ),
        "petitioner_prior_petitions": q(
            "Part 5, Items 1-5: Have you EVER previously filed a petition for this beneficiary or any other alien? "
            "Name, place, date filed, result",
            ["Part4Line1_Yes", "Part4Line1_No", "Pt5Line2a_FamilyName", "Pt5Line2b_GivenName", "Pt5Line2c_MiddleName",
             "Pt5Line3a_CityOrTown", "Pt5Line3b_State", "Pt5Line4_DateFiled", "Pt5Line5_Result"],
            notes={
                "Part4Line1_Yes": (
                    "Part 5 item 1 despite the 'Part4' names. Two separate boxes; set one. Any earlier petition by "
                    "this petitioner, for anyone."
                ),
                "Pt5Line2a_FamilyName": "Item 2.a, only with a Yes: the earlier beneficiary. More petitions go in Part "
                "9 (Page 8, Part 5, Items 2-5).",
                "Pt5Line3a_CityOrTown": "Item 3.a: where it was filed. maxlen 20.",
                "Pt5Line3b_State": "Item 3.b. 2-letter state code (drop-down).",
                "Pt5Line4_DateFiled": DATE,
                "Pt5Line5_Result": (
                    "Item 5, e.g. approved, denied, withdrawn (maxlen 33). Acrobat's keystroke filter on this box "
                    "accepts only digits and '/', so it can't be retyped in Acrobat; fill writes it and the filing "
                    "copy shows it."
                ),
            },
            choices=yes_no("Part4Line1_Yes", "Part4Line1_No"),
        ),
        "other_relative_petition_1": other_relative_petition(1),
        "other_relative_petition_2": other_relative_petition(2),
        "petitioner_statement_language": q(
            "Part 6, Item 1.a/1.b: Petitioner reads English, or the interpreter in Part 7 read the petition (language)",
            ["Pt6Line1Checkbox", "Pt6Line1b_Language"],
            ["Pt6Line1Checkbox"],
            notes={
                "Pt6Line1Checkbox": "One global group: box [0] is 1.a (A), box [1] is 1.b (B). Set the base name once.",
                "Pt6Line1b_Language": "Only with 1.b: the language the interpreter used (same as Part 7's "
                "certification).",
            },
            choices={
                "Pt6Line1Checkbox": {
                    "1.a. I can read and understand English": "A",
                    "1.b. The interpreter named in Part 7. read to me": "B",
                },
            },
        ),
        "petitioner_statement_preparer": q(
            "Part 6, Item 2: At my request, the preparer named in Part 8. prepared this petition",
            ["Pt6Line2_Checkbox", "Pt6Line2_RepresentativeName"],
            ["Pt6Line2_Checkbox", "Pt6Line2_RepresentativeName"],
            notes={
                "Pt6Line2_RepresentativeName": "The preparer's full name, matching Part 8 item 1. About 34 characters "
                "fit.",
            },
            choices={"Pt6Line2_Checkbox": {"At my request, the preparer named in Part 8. prepared this petition": "C"}},
        ),
        "petitioner_contact": q(
            "Part 6, Items 3-5: Petitioner's daytime phone, mobile phone (if any), email (if any)",
            ["Pt6Line3_DaytimePhoneNumber", "Pt6Line4_MobileNumber", "Pt6Line5_Email"],
            ["Pt6Line3_DaytimePhoneNumber"],
            notes={
                "Pt6Line3_DaytimePhoneNumber": "Required. 10 digits, no punctuation (maxlen 10: no room for a country "
                "code).",
                "Pt6Line4_MobileNumber": "If any; maxlen 10.",
                "Pt6Line5_Email": "If any; maxlen 38.",
            },
        ),
        "petitioner_signature": q(
            "Part 6, Item 6: Petitioner's signature and date",
            ["P5_Line6a_SignatureofApplicant", "Pt6Line6b_DateofSignature"],
            allowed=SIGNATURE_STATUSES,
            notes={
                "P5_Line6a_SignatureofApplicant": "Part 6 item 6.a despite the P5 name. Signed in ink; never typed.",
                "Pt6Line6b_DateofSignature": "Dated by the petitioner at signing.",
            },
        ),
        "interpreter_block": q(
            "Part 7, Items 1-6: Interpreter's name, business, mailing address, phones, email, and certified language",
            [
                "Pt7Line1a_InterpreterFamilyName",
                "Pt7Line1b_InterpreterGivenName",
                "Pt7Line2_InterpreterBusinessorOrg",
                *address_fields("Pt7Line3_StreetNumberName", "Pt7Line3_Unit", "Pt7Line3_AptSteFlrNumber",
                                "Pt7Line3_CityOrTown", "Pt7Line3_State", "Pt7Line3_ZipCode", "Pt7Line3_Province",
                                "Pt7Line3_PostalCode", "Pt7Line3_Country"),
                "Pt7Line4_InterpreterDaytimeTelephone",
                "Pt4Line53_DaytimePhoneNumber",
                "Pt7Line5_Email",
                "Pt7_NameofLanguage",
            ],
            ["Pt7Line1a_InterpreterFamilyName", "Pt7Line1b_InterpreterGivenName", "Pt7Line3_StreetNumberName",
             "Pt7Line3_CityOrTown", "Pt7Line3_Country", "Pt7Line4_InterpreterDaytimeTelephone", "Pt7_NameofLanguage"],
            allowed=FILLED_OR_NA,
            notes={
                **address_notes("Pt7Line3_StreetNumberName", "Pt7Line3_Unit", "Pt7Line3_State", "Pt7Line3_ZipCode",
                                "Pt7Line3_Province", "Pt7Line3_PostalCode"),
                "Pt7Line1a_InterpreterFamilyName": "Only if an interpreter was used (Part 6 item 1.b); otherwise "
                "not_applicable.",
                "Pt7Line2_InterpreterBusinessorOrg": "If any; maxlen 38.",
                "Pt7Line3_Country": "maxlen 29.",
                "Pt7Line4_InterpreterDaytimeTelephone": "Item 4, daytime phone: 10 digits (maxlen 10).",
                "Pt4Line53_DaytimePhoneNumber": (
                    "Item 5, the interpreter's MOBILE phone, despite the Pt4Line53 name; if any (maxlen 10)."
                ),
                "Pt7Line5_Email": "Item 6 despite the Line5 name; if any (maxlen 38).",
                "Pt7_NameofLanguage": "The language in the certification, same as Part 6 item 1.b. About 23 characters "
                "fit.",
            },
            choices={"Pt7Line3_Unit": UNIT_PLAIN},
        ),
        "interpreter_signature": q(
            "Part 7, Item 7: Interpreter's signature and date",
            ["Pt7Line7a_Signature", "Pt7Line7b_DateofSignature"],
            allowed=[PENDING_SIGNATURE, FILLED, NOT_APPLICABLE],
            notes={
                "Pt7Line7a_Signature": "Signed in ink (the box's maxlen is 1, so nothing can be typed). not_applicable "
                "with no interpreter.",
            },
        ),
        "preparer_block": q(
            "Part 8, Items 1-6: Preparer's name, business, mailing address, phones and email",
            [
                "Pt8Line1a_PreparerFamilyName",
                "Pt8Line1b_PreparerGivenName",
                "Pt8Line2_BusinessName",
                *address_fields("Pt8Line3_StreetNumberName", "Pt8Line3_Unit", "Pt8Line3_AptSteFlrNumber",
                                "Pt8Line3_CityOrTown", "Pt8Line3_State", "Pt8Line3_ZipCode", "Pt8Line3_Province",
                                "Pt8Line3_PostalCode", "Pt8Line3_Country"),
                "Pt8Line4_DaytimePhoneNumber",
                "Pt8Line5_PreparerFaxNumber",
                "Pt8Line6_Email",
            ],
            ["Pt8Line1a_PreparerFamilyName", "Pt8Line1b_PreparerGivenName", "Pt8Line2_BusinessName",
             "Pt8Line3_StreetNumberName", "Pt8Line3_CityOrTown", "Pt8Line3_Country", "Pt8Line4_DaytimePhoneNumber",
             "Pt8Line6_Email"],
            notes={
                **address_notes("Pt8Line3_StreetNumberName", "Pt8Line3_Unit", "Pt8Line3_State", "Pt8Line3_ZipCode",
                                "Pt8Line3_Province", "Pt8Line3_PostalCode"),
                "Pt8Line1a_PreparerFamilyName": "From the attorney profile.",
                "Pt8Line2_BusinessName": "The firm; maxlen 34.",
                "Pt8Line3_Unit": "This row's Flr. on-state is 'FLR ' (trailing space); use the choices.",
                "Pt8Line3_AptSteFlrNumber": "maxlen 5 (one less than the other unit-number boxes).",
                "Pt8Line4_DaytimePhoneNumber": "10 digits (maxlen 10).",
                "Pt8Line5_PreparerFaxNumber": "Item 5, the preparer's MOBILE phone, despite the Fax name; if any "
                "(maxlen 10).",
                "Pt8Line6_Email": "maxlen 38.",
            },
            choices={"Pt8Line3_Unit": UNIT_PREPARER},
        ),
        "preparer_statement": q(
            "Part 8, Item 7: Preparer's statement (not an attorney; or attorney whose representation extends / does "
            "not extend)",
            ["Pt8Line7_Checkbox", "Pt8Line7b_Checkbox"],
            ["Pt8Line7_Checkbox"],
            notes={
                "Pt8Line7_Checkbox": "One global group: A = 7.a not an attorney, B = 7.b attorney or accredited "
                "representative.",
                "Pt8Line7b_Checkbox": "Only with 7.b. 'extends' goes with a G-28 and the page 1 G-28 box "
                "(attorney_box).",
            },
            choices={
                "Pt8Line7_Checkbox": {
                    "7.a. I am not an attorney or accredited representative": "A",
                    "7.b. I am an attorney or accredited representative": "B",
                },
                "Pt8Line7b_Checkbox": {"extends": "Y", "does not extend": "N"},
            },
        ),
        "preparer_signature": q(
            "Part 8, Item 8: Preparer's signature and date",
            ["Pt8Line8a_Signature", "Pt8Line8b_DateofSignature"],
            allowed=SIGNATURE_STATUSES,
            notes={"Pt8Line8a_Signature": "Signed in ink (the box's maxlen is 1, so nothing can be typed)."},
        ),
        "additional_information": additional_information(),
    }
    return {
        "kind": "i-130",
        "edition": EDITION,
        "field_list": FIELD_LIST,
        "description": (
            "Form I-130 for any relative (spouse, parent, child, brother or sister) by a U.S. citizen or "
            "lawful permanent resident petitioner, for adjustment in the U.S. or consular processing."
        ),
        "notes": list(SCHEMA_NOTES),
        "required_questions": questions,
    }


SCHEMAS = {"i130_family_petition": family_petition()}

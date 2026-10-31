"""Question schema for Form I-129F, Petition for Alien Fiance(e) (K-1 fiance(e) or K-3 spouse).

Built against the 01/20/25 edition (uscis.gov/i-129f Edition Date panel and the PDF footer of the
form and its instructions, checked 2026-10-29). Field list: schemas/fields/I-129F.json; every box
of the form belongs to one question.

This edition has no attorney box on page 1 and no box for the petitioner's signature other than
the protected signature field, which is misnamed Pt6Line4_Signature (it sits in Part 5, item 4).

Defects of this edition, read from where each box sits next to its printed label (the method that
reproduces the I-765's known page-5 defect), not yet opened in Acrobat:
- The unit boxes of Part 1 items 8, 9, 11, 14 and 18 and Part 2 items 12, 14, 17 and 21: ' FLR '
  checks the box printed "Apt.", ' APT ' checks "Ste." and ' STE ' checks "Flr.". The choices below
  are keyed by the printed label, so the filing copy shows the right box. The other unit groups
  (Part 2 items 11, 44, 45, 47, 50 and 60) are correct.
- Part 4 item 5, eye color: the box printed "Gray" stores GRN and the box printed "Green" stores
  GRY (their tooltips name them the other way round). The choices are keyed by the printed label.
- Part 3 item 3 (a-c, "select all that apply") is one global checkbox group, so only one of the
  three can be checked: check the one that applies most directly and explain the others in Part 8.

Many names carry the wrong item number (Pt1Line20_Checkboxes is item 41; Pt1Line11_DateofBirth is
the beneficiary's parent's date of birth, Part 2 item 25; Pt2Line28c-28f are item 50's native-
alphabet address); the field_notes say which is which.
"""
from __future__ import annotations

from typing import Any

from _common import (DATE, FILLED, FILLED_OR_NA, FOREIGN_ONLY, MANUAL_REVIEW, NOT_APPLICABLE, PENDING_SIGNATURE, UNIT,
                     YES_NO, q)

SEX = {"Male": "M", "Female": "F"}
MARITAL = {"Single": "S", "Married": "M", "Divorced": "D", "Widowed": "W"}
# Keyed by the printed label: on these groups each on-state checks a different label (module note).
UNIT_MISLABELED = {"Apt.": " FLR ", "Ste.": " APT ", "Flr.": " STE "}
UNIT_NO_PADDING = {"Apt.": "APT ", "Ste.": "STE ", "Flr.": "FLR "}

STATE = "U.S. address only: 2-letter state code (drop-down)."
ZIP = "U.S. address only: 5-digit ZIP Code."
PHONE = "Digits only, no punctuation (maxlen 10)."
MISLABELED_NOTE = (
    "Form defect: the on-states don't match the printed labels on this group. Use the choices (keyed by the "
    "printed label), never the plain unit code."
)
SIGNATURE = "Protected box (maxlen 1); it can't be typed or signed electronically. The signer signs in ink."


def address(
    label: str,
    prefix: str,
    *,
    unit: dict[str, str],
    in_care_of: str = "",
    dates: tuple[str, str] | None = None,
    allowed: list[str] | None = None,
    extra_notes: dict[str, str] | None = None,
    names: dict[str, str] | None = None,
) -> dict[str, Any]:
    """A street address row: <prefix>_StreetNumberName, _Unit, _AptSteFlrNumber, _CityOrTown, _State,
    _ZipCode, _Province, _PostalCode, _Country (names overrides any of these), with optional dates."""
    boxes = {
        "street": f"{prefix}_StreetNumberName",
        "unit": f"{prefix}_Unit",
        "number": f"{prefix}_AptSteFlrNumber",
        "city": f"{prefix}_CityOrTown",
        "state": f"{prefix}_State",
        "zip": f"{prefix}_ZipCode",
        "province": f"{prefix}_Province",
        "postal": f"{prefix}_PostalCode",
        "country": f"{prefix}_Country",
        **(names or {}),
    }
    fields = ([in_care_of] if in_care_of else []) + [boxes[key] for key in boxes if boxes[key]]
    nonempty = [boxes["street"], boxes["city"], boxes["country"]]
    notes = {
        boxes["street"]: "maxlen 25.",
        boxes["number"]: "The apartment, suite or floor number (maxlen 6), with the unit type.",
        boxes["city"]: "maxlen 20.",
        boxes["country"]: "Write the country, United States included.",
    }
    if boxes.get("state"):
        notes[boxes["state"]] = STATE
    if boxes.get("zip"):
        notes[boxes["zip"]] = ZIP
    if boxes.get("province"):
        notes[boxes["province"]] = FOREIGN_ONLY
    if boxes.get("postal"):
        notes[boxes["postal"]] = FOREIGN_ONLY
    if unit is UNIT_MISLABELED:
        notes[boxes["unit"]] = MISLABELED_NOTE
    if dates:
        fields += list(dates)
        nonempty.append(dates[0])
        notes[dates[0]] = "Date From. " + DATE
        notes[dates[1]] = "Date To. " + DATE + " PRESENT for the current address (the blank prints it)."
    notes.update(extra_notes or {})
    return q(label, fields, nonempty, allowed=allowed, notes=notes, choices={boxes["unit"]: unit})


def employer(
    label: str, name: str, prefix: str, occupation: str, dates: tuple[str, str], *, unit: dict[str, str],
    allowed: list[str] | None = None,
) -> dict[str, Any]:
    spec = address(label, prefix, unit=unit, allowed=allowed)
    spec["required_fields"] = [name] + spec["required_fields"] + [occupation, *dates]
    spec["required_nonempty_fields_when_filled"] = [name, occupation, dates[0]]
    spec["field_notes"].update(
        {
            name: "Full name of the employer (maxlen 34); 'Unemployed' or 'Self-employed' when that is the record, "
            "with the dates. The address boxes then stay blank for unemployment.",
            occupation: "Occupation (specify).",
            dates[0]: "Employment start date. " + DATE,
            dates[1]: "Employment end date. " + DATE + " Blank or PRESENT for the current job.",
        }
    )
    return spec


def parent(label: str, names: tuple[str, str, str], dob: str, sex: str, birth: str, city: str, country: str,
           notes: dict[str, str] | None = None) -> dict[str, Any]:
    return q(
        label,
        [*names, dob, sex, birth, city, country],
        [names[0], names[1], dob, sex, birth, country],
        notes={
            dob: DATE,
            birth: "Country of BIRTH, despite the CountryOfCitzOrNationality name.",
            city: "City, town or village of RESIDENCE (unbound in the XFA template; fill binds it). 'Deceased' if so.",
            country: "Country of RESIDENCE. 'Deceased' if so.",
            **(notes or {}),
        },
        choices={sex: SEX},
    )


def petitioner() -> dict[str, dict[str, Any]]:
    return {
        "classification": q(
            "Part 1, Item 4: Classification requested for the beneficiary (K-1 fiance(e) or K-3 spouse)",
            ["Pt1Line4a_Checkboxes"],
            ["Pt1Line4a_Checkboxes"],
            choices={"Pt1Line4a_Checkboxes": {"Fiance(e) (K-1 visa)": "A", "Spouse (K-3 visa)": "B"}},
        ),
        "k3_i130_filed": q(
            "Part 1, Item 5: For a K-3 spouse, has the petitioner filed Form I-130? (evidence of filing goes with the petition)",
            ["Pt1Line5_Checkboxes"],
            ["Pt1Line5_Checkboxes"],
            allowed=FILLED_OR_NA,
            notes={"Pt1Line5_Checkboxes": (
                "K-3 only; not_applicable for a K-1 fiance(e). A K-3 needs Yes: the I-130 filed before or with this "
                "petition, with its evidence (the audit reports No)."
            )},
            choices={"Pt1Line5_Checkboxes": YES_NO},
        ),
        "petitioner_numbers": q(
            "Part 1, Items 1-3: Petitioner's A-Number, USCIS online account number and Social Security number (each if any)",
            ["Pt1Line1_AlienNumber", "Pt1Line2_AcctIdentifier", "Pt1Line3_SSN"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt1Line1_AlienNumber": "If any: 9 digits, no 'A' (one global value, repeated on page 12).",
                "Pt1Line2_AcctIdentifier": "If any: 12 digits.",
                "Pt1Line3_SSN": "If any: 9 digits, no dashes.",
            },
        ),
        "petitioner_name": q(
            "Part 1, Items 6.a-6.c: Petitioner's full legal name",
            ["Pt1Line6a_FamilyName", "Pt1Line6b_GivenName", "Pt1Line6c_MiddleName"],
            ["Pt1Line6a_FamilyName", "Pt1Line6b_GivenName"],
            notes={"Pt1Line6a_FamilyName": "Global: also fills the page 12 header (maxlen 30)."},
        ),
        "petitioner_other_names": q(
            "Part 1, Items 7.a-7.c: Other names used (aliases, maiden name, nicknames; more in Part 8)",
            ["Pt1Line7a_FamilyName", "Pt1Line7b_GivenName", "Pt1Line7c_MiddleName"],
            ["Pt1Line7a_FamilyName", "Pt1Line7b_GivenName"],
            allowed=FILLED_OR_NA,
        ),
        "petitioner_mailing_address": address(
            "Part 1, Items 8.a-8.i: Petitioner's mailing address",
            "Pt1Line8",
            unit=UNIT_MISLABELED,
            in_care_of="Pt1Line8_InCareofName",
            extra_notes={"Pt1Line8_InCareofName": "In care of name, if any (maxlen 34)."},
        ),
        "mailing_same_as_physical": q(
            "Part 1, Item 8.j: Is the mailing address the same as the physical address?",
            ["Pt1Line8j_Checkboxes"],
            ["Pt1Line8j_Checkboxes"],
            notes={"Pt1Line8j_Checkboxes": "Either way, give the current physical address in items 9.a-10.b."},
            choices={"Pt1Line8j_Checkboxes": YES_NO},
        ),
        "petitioner_address_1": address(
            "Part 1, Items 9.a-10.b: Physical address 1 (current), with dates (address history covers five years)",
            "Pt1Line9",
            unit=UNIT_MISLABELED,
            dates=("Pt1Line10a_DateFrom", "Pt1Line10b_ToFrom"),
        ),
        "petitioner_address_2": address(
            "Part 1, Items 11.a-12.b: Physical address 2, with dates (more in Part 8 to cover five years)",
            "Pt1Line11",
            unit=UNIT_MISLABELED,
            dates=("Pt1Line12a_DateFrom", "Pt1Line12b_ToFrom"),
            allowed=FILLED_OR_NA,
        ),
        "petitioner_employer_1": employer(
            "Part 1, Items 13-16.b: Employer 1 (current or most recent; employment history covers five years)",
            "Pt1Line13_NameofEmployer", "Pt1Line14", "Pt1Line15_Occupation",
            ("Pt1Line16a_DateFrom", "Pt1Line16b_ToFrom"), unit=UNIT_MISLABELED,
        ),
        "petitioner_employer_2": employer(
            "Part 1, Items 17-20.b: Employer 2 (more in Part 8 to cover five years)",
            "Pt1Line17_NameofEmployer", "Pt1Line18", "Pt1Line19_Occupation",
            ("Pt1Line20a_DateFrom", "Pt1Line20b_ToFrom"), unit=UNIT_MISLABELED, allowed=FILLED_OR_NA,
        ),
        "petitioner_birth_and_status": q(
            "Part 1, Items 21-26: Sex, date of birth, marital status, city, province or state, and country of birth",
            ["Pt1Line21_Checkbox", "Pt1Line22_DateofBirth", "Pt1Line23_Checkbox", "Pt1Line24_CityTownOfBirth",
             "Pt1Line25_ProvinceOrStateOfBirth", "Pt1Line26_CountryOfCitzOrNationality"],
            ["Pt1Line21_Checkbox", "Pt1Line22_DateofBirth", "Pt1Line23_Checkbox", "Pt1Line24_CityTownOfBirth",
             "Pt1Line26_CountryOfCitzOrNationality"],
            notes={
                "Pt1Line22_DateofBirth": DATE,
                "Pt1Line24_CityTownOfBirth": "Unbound in the XFA template; fill binds it (maxlen 20).",
                "Pt1Line26_CountryOfCitzOrNationality": "Item 26, country of BIRTH, despite the name.",
            },
            choices={"Pt1Line21_Checkbox": SEX, "Pt1Line23_Checkbox": MARITAL},
        ),
        "petitioner_parent_1": parent(
            "Part 1, Items 27.a-31.b: Parent 1's name, date of birth, sex, country of birth, city and country of residence",
            ("Pt1Line27a_FamilyName", "Pt1Line27b_GivenName", "Pt1Line27c_MiddleName"), "Pt1Line28_DateofBirth",
            "Pt1Line29_Checkbox", "Pt1Line30_CountryOfCitzOrNationality", "Pt1Line31_CityTownOfBirth",
            "Pt1Line31_CountryOfCitzOrNationality",
        ),
        "petitioner_parent_2": parent(
            "Part 1, Items 32.a-36.b: Parent 2's name, date of birth, sex, country of birth, city and country of residence",
            ("Pt1Line32a_FamilyName", "Pt1Line32b_GivenName", "Pt1Line32c_MiddleName"), "Pt1Line33_DateofBirth",
            "Pt1Line34_Checkbox", "Pt1Line35_CountryOfCitzOrNationality", "Pt1Line36a_CityTownOfBirth",
            "Pt1Line36b_CountryOfCitzOrNationality",
        ),
        "petitioner_previously_married": q(
            "Part 1, Item 37: Has the petitioner ever been previously married?",
            ["Pt1Line37_Checkboxes"],
            ["Pt1Line37_Checkboxes"],
            choices={"Pt1Line37_Checkboxes": YES_NO},
        ),
        "petitioner_prior_spouse": q(
            "Part 1, Items 38.a-39: Previous spouse's name and the date the marriage ended (more in Part 8)",
            ["Pt1Line38a_FamilyName", "Pt1Line38b_GivenName", "Pt1Line38c_MiddleName", "Pt1Line39_DateMarriageEnded"],
            ["Pt1Line38a_FamilyName", "Pt1Line38b_GivenName", "Pt1Line39_DateMarriageEnded"],
            allowed=FILLED_OR_NA,
            notes={"Pt1Line39_DateMarriageEnded": DATE + " Only with item 37 Yes."},
        ),
        "petitioner_citizenship": q(
            "Part 1, Items 40-41: How the petitioner became a U.S. citizen; has a certificate of naturalization or citizenship",
            ["Pt1Line40_Checkbox", "Pt1Line20_Checkboxes"],
            ["Pt1Line40_Checkbox", "Pt1Line20_Checkboxes"],
            notes={"Pt1Line20_Checkboxes": "Item 41, despite the Line20 name."},
            choices={
                "Pt1Line40_Checkbox": {
                    "Birth in the United States": "A", "Naturalization": "B", "U.S. citizen parents": "C",
                },
                "Pt1Line20_Checkboxes": YES_NO,
            },
        ),
        "petitioner_certificate": q(
            "Part 1, Items 42.a-42.c: Certificate number, place and date of issuance",
            ["Pt1Line21a_CertificateNumber", "Pt1Line21b_PlaceofIssuance", "Pt1Line21c_DateOfIssuance"],
            ["Pt1Line21a_CertificateNumber", "Pt1Line21b_PlaceofIssuance", "Pt1Line21c_DateOfIssuance"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt1Line21a_CertificateNumber": "Item 42.a despite the Line21 name; only with item 41 Yes.",
                "Pt1Line21c_DateOfIssuance": DATE,
            },
        ),
        "prior_i129f": q(
            "Part 1, Item 43: Has the petitioner ever filed Form I-129F for any other beneficiary?",
            ["Pt1Line43_Checkboxes"],
            ["Pt1Line43_Checkboxes"],
            choices={"Pt1Line43_Checkboxes": YES_NO},
        ),
        "prior_i129f_details": q(
            "Part 1, Items 44-47: That beneficiary's A-Number and name, the date filed and the action taken (more in Part 8)",
            ["Pt1Line44_AlienNumber", "Pt1Line45a_FamilyName", "Pt1Line45b_GivenName", "Pt1Line45c_MiddleName",
             "Pt1Line46_DateOfFiling", "Pt1Line47_Result"],
            ["Pt1Line45a_FamilyName", "Pt1Line45b_GivenName", "Pt1Line46_DateOfFiling", "Pt1Line47_Result"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt1Line44_AlienNumber": "If any: 9 digits, no 'A'.",
                "Pt1Line46_DateOfFiling": DATE,
                "Pt1Line47_Result": "Approved, denied, revoked or withdrawn (maxlen 30; unbound, fill binds it).",
            },
        ),
        "petitioner_children": q(
            "Part 1, Item 48: Does the petitioner have any children under 18?",
            ["Pt1Line48_Checkboxes"],
            ["Pt1Line48_Checkboxes"],
            choices={"Pt1Line48_Checkboxes": YES_NO},
        ),
        "petitioner_children_ages": q(
            "Part 1, Items 49.a-49.b: Ages of the children under 18 (more in Part 8)",
            ["Pt1Line49a_Age", "Pt1Line49b_Age"],
            ["Pt1Line49a_Age"],
            allowed=FILLED_OR_NA,
            notes={"Pt1Line49a_Age": "Age in years (maxlen 2). Only with item 48 Yes."},
        ),
        "places_resided_since_18": q(
            "Part 1, Items 50.a-51.b: Every U.S. state and foreign country lived in since age 18 (more in Part 8)",
            ["Pt1Line50a_State", "Pt1Line50b_CountryOfCitzOrNationality", "Pt1Line51a_State",
             "Pt1Line51b_CountryOfCitzOrNationality"],
            ["Pt1Line50b_CountryOfCitzOrNationality"],
            notes={
                "Pt1Line50a_State": "U.S. state (drop-down), with United States as the country; blank for a foreign country.",
                "Pt1Line50b_CountryOfCitzOrNationality": "The country of this residence.",
            },
        ),
    }


def beneficiary() -> dict[str, dict[str, Any]]:
    return {
        "beneficiary_name": q(
            "Part 2, Items 1.a-1.c: Beneficiary's full legal name",
            ["Pt2Line1a_FamilyName", "Pt2Line1b_GivenName", "Pt2Line1c_MiddleName"],
            ["Pt2Line1a_FamilyName", "Pt2Line1b_GivenName"],
            notes={"Pt2Line1a_FamilyName": "Unbound in the XFA template; fill binds it (maxlen 30)."},
        ),
        "beneficiary_numbers": q(
            "Part 2, Items 2-3: Beneficiary's A-Number and U.S. Social Security number (each if any)",
            ["Pt2Line2_AlienNumber", "Pt2Line3_SSN"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt2Line2_AlienNumber": "If any: 9 digits, no 'A'. The instructions say N/A when there is none.",
                "Pt2Line3_SSN": "If any: 9 digits.",
            },
        ),
        "beneficiary_birth_and_status": q(
            "Part 2, Items 4-9: Date of birth, sex, marital status, city and country of birth, citizenship",
            ["Pt2Line4_DateOfBirth", "Pt2Line5_Checkboxes", "Pt2Line6_Checkboxes", "Pt2Line7_CityTownOfBirth",
             "Pt2Line8_CountryOfBirth", "Pt2Line9_CountryofCitzOrNationality"],
            ["Pt2Line4_DateOfBirth", "Pt2Line5_Checkboxes", "Pt2Line6_Checkboxes", "Pt2Line7_CityTownOfBirth",
             "Pt2Line8_CountryOfBirth", "Pt2Line9_CountryofCitzOrNationality"],
            notes={
                "Pt2Line4_DateOfBirth": DATE,
                "Pt2Line9_CountryofCitzOrNationality": "'Stateless' with an explanation in Part 8 when the beneficiary has none.",
            },
            choices={"Pt2Line5_Checkboxes": SEX, "Pt2Line6_Checkboxes": MARITAL},
        ),
        "beneficiary_other_names": q(
            "Part 2, Items 10.a-10.c: Beneficiary's other names used (more in Part 8)",
            ["Pt2Line10a_FamilyName", "Pt2Line10b_GivenName", "Pt2Line10c_MiddleName"],
            ["Pt2Line10a_FamilyName", "Pt2Line10b_GivenName"],
            allowed=FILLED_OR_NA,
        ),
        "beneficiary_mailing_address": address(
            "Part 2, Items 11.a-11.i: Beneficiary's mailing address (the U.S. one, if any)",
            "Pt2Line11",
            unit=UNIT,
            in_care_of="Pt2Line11_InCareOfName",
            extra_notes={"Pt2Line11_InCareOfName": "In care of name, if any (maxlen 34)."},
        ),
        "beneficiary_address_1": address(
            "Part 2, Items 12.a-13.b: Beneficiary's physical address 1 (current), with dates (five years of history)",
            "Pt2Line12",
            unit=UNIT_MISLABELED,
            dates=("Pt2Line13a_DateFrom", "Pt2Line13b_ToFrom"),
        ),
        "beneficiary_address_2": address(
            "Part 2, Items 14.a-15.b: Beneficiary's physical address 2, with dates (more in Part 8)",
            "Pt2Line14",
            unit=UNIT_MISLABELED,
            dates=("Pt2Line15a_DateFrom", "Pt2Line15b_ToFrom"),
            allowed=FILLED_OR_NA,
        ),
        "beneficiary_employer_1": employer(
            "Part 2, Items 16-19.b: Beneficiary's employer 1 (five years of history)",
            "Pt2Line16_NameofEmployer", "Pt2Line17", "Pt2Line18_Occupation",
            ("Pt2Line19a_DateFrom", "Pt2Line19b_ToFrom"), unit=UNIT_MISLABELED,
        ),
        "beneficiary_employer_2": employer(
            "Part 2, Items 20-23.b: Beneficiary's employer 2 (more in Part 8)",
            "Pt2Line20_NameofEmployer", "Pt2Line21", "Pt2Line22_Occupation",
            ("Pt2Line23a_DateFrom", "Pt2Line23b_ToFrom"), unit=UNIT_MISLABELED, allowed=FILLED_OR_NA,
        ),
        "beneficiary_parent_1": parent(
            "Part 2, Items 24.a-28.b: Beneficiary's parent 1",
            ("Pt2Line24a_FamilyName", "Pt2Line24b_GivenName", "Pt2Line24c_MiddleName"), "Pt1Line11_DateofBirth",
            "Pt2Line26_Checkbox", "Pt2Line27_CountryOfCitzOrNationality", "Pt2Line28a_CityTownOfBirth",
            "Pt2Line28b_CountryOfCitzOrNationality",
            notes={"Pt1Line11_DateofBirth": "Part 2 item 25, this parent's date of birth, despite the Pt1Line11 name. " + DATE},
        ),
        "beneficiary_parent_2": parent(
            "Part 2, Items 29.a-33.b: Beneficiary's parent 2",
            ("Pt2Line29a_FamilyName", "Pt2Line29b_GivenName", "Pt2Line29c_MiddleName"), "Pt2Line30_DateofBirth",
            "Pt2Line31_Checkbox", "Pt2Line32_CountryOfCitzOrNationality", "Pt2Line33a_CityTownOfBirth",
            "Pt2Line33b_CountryOfCitzOrNationality",
        ),
        "beneficiary_previously_married": q(
            "Part 2, Item 34: Has the beneficiary ever been previously married?",
            ["Pt2Line34_Checkboxes"],
            ["Pt2Line34_Checkboxes"],
            choices={"Pt2Line34_Checkboxes": YES_NO},
        ),
        "beneficiary_prior_spouse": q(
            "Part 2, Items 35.a-36: Beneficiary's previous spouse and the date the marriage ended (more in Part 8)",
            ["Pt2Line35a_FamilyName", "Pt2Line35b_GivenName", "Pt2Line35c_MiddleName", "Pt2Line36_DateMarriageEnded"],
            ["Pt2Line35a_FamilyName", "Pt2Line35b_GivenName", "Pt2Line36_DateMarriageEnded"],
            allowed=FILLED_OR_NA,
            notes={"Pt2Line36_DateMarriageEnded": DATE},
        ),
        "beneficiary_ever_in_us": q(
            "Part 2, Item 37: Has the beneficiary ever been in the United States?",
            ["Pt2Line37_Checkboxes"],
            ["Pt2Line37_Checkboxes"],
            choices={"Pt2Line37_Checkboxes": YES_NO},
        ),
        "beneficiary_last_entry": q(
            "Part 2, Items 38.a-38.h: If in the U.S. now, how the beneficiary last arrived: class, I-94, arrival date, "
            "stay expiry, passport or travel document",
            ["Pt2Line38a_LastArrivedAs", "Pt2Line38b_ArrivalDeparture", "Pt2Line38c_DateofArrival",
             "Pt2Line38d_DateExpired", "Pt2Line38e_Passport", "Pt2Line38f_TravelDoc", "Pt2Line38g_CountryOfIssuance",
             "Pt2Line38h_ExpDate"],
            ["Pt2Line38a_LastArrivedAs", "Pt2Line38c_DateofArrival"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt2Line38a_LastArrivedAs": "Class of admission as the I-94 shows it (visitor, student, without inspection...).",
                "Pt2Line38b_ArrivalDeparture": "I-94 number, 11 characters, if any.",
                "Pt2Line38c_DateofArrival": DATE,
                "Pt2Line38d_DateExpired": "Authorized stay expires or expired, as the I-94 shows (" + DATE[:-1] + " or D/S).",
                "Pt2Line38h_ExpDate": "Passport or travel document expiration. " + DATE,
            },
        ),
        "beneficiary_has_children": q(
            "Part 2, Item 39: Does the beneficiary have any children?",
            ["Pt2Line39_Checkboxes"],
            ["Pt2Line39_Checkboxes"],
            choices={"Pt2Line39_Checkboxes": YES_NO},
        ),
        "beneficiary_child_1": q(
            "Part 2, Items 40.a-44.h: Beneficiary's child (name, country and date of birth, lives with the beneficiary, "
            "address if not); more children in Part 8",
            ["Pt2Line40a_FamilyName", "Pt2Line40b_GivenName", "Pt2Line40c_MiddleName", "Pt2Line41_CountryOfBirth",
             "Pt2Line42_DateofBirth", "Pt2Line43_Checkboxes", "Pt2Line44_StreetNumberName", "Pt2Line44_Unit",
             "Pt2Line44_AptSteFlrNumber", "Pt2Line44_CityOrTown", "Pt2Line44_State", "Pt2Line44_ZipCode",
             "Pt2Line44_Province", "Pt2Line44_PostalCode", "Pt2Line44_Country"],
            ["Pt2Line40a_FamilyName", "Pt2Line40b_GivenName", "Pt2Line41_CountryOfBirth", "Pt2Line42_DateofBirth",
             "Pt2Line43_Checkboxes"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt2Line42_DateofBirth": DATE,
                "Pt2Line44_StreetNumberName": "Item 44, only when the child does NOT live with the beneficiary (item 43 No).",
                "Pt2Line44_State": STATE,
                "Pt2Line44_ZipCode": ZIP,
            },
            choices={"Pt2Line43_Checkboxes": YES_NO, "Pt2Line44_Unit": UNIT},
        ),
        "beneficiary_us_address": q(
            "Part 2, Items 45.a-46: U.S. address where the beneficiary intends to live, and its daytime phone",
            ["Pt2Line45a_StreetNumberName", "Pt2Line45b_Unit", "Pt2Line45b_AptSteFlrNumber", "Pt2Line45c_CityOrTown",
             "Pt2Line45d_State", "Pt2Line45e_ZipCode", "Pt2Line46_DayTimeTelephoneNumber"],
            ["Pt2Line45a_StreetNumberName", "Pt2Line45c_CityOrTown", "Pt2Line45d_State", "Pt2Line45e_ZipCode"],
            notes={"Pt2Line45d_State": STATE, "Pt2Line46_DayTimeTelephoneNumber": PHONE},
            choices={"Pt2Line45b_Unit": UNIT},
        ),
        "beneficiary_address_abroad": address(
            "Part 2, Items 47.a-48: Beneficiary's physical address abroad, and its daytime phone",
            "Pt2Line47",
            unit=UNIT,
            names={"state": "", "zip": ""},
            extra_notes={"Pt2Line48_DaytimeTelephoneNum": "Daytime phone at that address (maxlen 10)."},
        ),
        "beneficiary_native_alphabet": q(
            "Part 2, Items 49.a-50.f: Beneficiary's name and address abroad in the native alphabet (only if it doesn't "
            "use Roman letters)",
            ["Pt2Line49a_FamilyName", "Pt2Line49b_GivenName", "Pt2Line49c_MiddleName", "Pt2Line50_StreetNumberName",
             "Pt2Line50_Unit", "Pt2Line50_AptSteFlrNumber", "Pt2Line28c_CityOrTown", "Pt2Line28d_Province",
             "Pt2Line28e_PostalCode", "Pt2Line28f_Country"],
            ["Pt2Line49a_FamilyName", "Pt2Line49b_GivenName", "Pt2Line50_StreetNumberName", "Pt2Line28c_CityOrTown",
             "Pt2Line28f_Country"],
            allowed=[NOT_APPLICABLE, FILLED, MANUAL_REVIEW],
            notes={
                "Pt2Line49a_FamilyName": (
                    "Non-Roman script doesn't render on the filing copy (it prints '?'). Leave these boxes blank, mark "
                    "the question manual_review with an open item, and have them handwritten."
                ),
                "Pt2Line28c_CityOrTown": "Item 50.c despite the Pt2Line28 name; 50.d-50.f are Pt2Line28d-28f.",
            },
            choices={"Pt2Line50_Unit": {"Apt.": " APT ", "Ste.": " STE ", "Flr.": " FLR "}},
        ),
        "related_to_beneficiary": q(
            "Part 2, Items 51-52: Is the fiance(e) related to the petitioner, and how",
            ["Pt2Line51_Checkboxes", "Pt2Line52_Relationship"],
            ["Pt2Line51_Checkboxes"],
            notes={
                "Pt2Line51_Checkboxes": "N/A when the beneficiary is the petitioner's spouse (K-3).",
                "Pt2Line52_Relationship": "Only with Yes: nature and degree (e.g. third cousin). Unbound; fill binds it.",
            },
            choices={"Pt2Line51_Checkboxes": {"Yes": "Y", "No": "N", "N/A, beneficiary is my spouse": "A"}},
        ),
        "met_in_person": q(
            "Part 2, Items 53-54: Met in person in the two years before filing; the circumstances, or the reasons for a waiver",
            ["Pt2Line53_Checkboxes", "Pt2Line54_Describe"],
            ["Pt2Line53_Checkboxes"],
            notes={
                "Pt2Line53_Checkboxes": "N/A when the beneficiary is the petitioner's spouse.",
                "Pt2Line54_Describe": (
                    "With Yes: the circumstances of the in-person meeting. With No: the reasons for the exemption "
                    "(extreme hardship, or strict and long-established custom), with evidence. Long text continues in Part 8."
                ),
            },
            choices={"Pt2Line53_Checkboxes": {"Yes": "Y", "No": "N", "N/A, beneficiary is my spouse": "A"}},
        ),
        "met_through_imb": q(
            "Part 2, Item 55: Did the petitioner meet the beneficiary through an international marriage broker (IMB)?",
            ["Pt2Line55_Checkboxes"],
            ["Pt2Line55_Checkboxes"],
            choices={"Pt2Line55_Checkboxes": YES_NO},
        ),
        "imb_details": q(
            "Part 2, Items 56-61: The IMB's name, contact name, organization, website, address and phone",
            ["Pt2Line56_IMBName", "Pt2Line57a_IMBFamilyName", "Pt2Line57b_IMB_GivenName", "Pt2Line58_IMBOrgName",
             "Pt2Line59_IMBWebsite", "Pt2Line60a_StreetNumberName", "Pt2Line60_Unit", "Pt2Line60_AptSteFlrNumber",
             "Pt2Line60_CityOrTown", "Pt2Line60_Province", "Pt2Line60_PostalCode", "Pt2Line60_Country",
             "Pt2Line61_DaytimeTelephoneNum"],
            ["Pt2Line58_IMBOrgName", "Pt2Line60a_StreetNumberName", "Pt2Line60_CityOrTown", "Pt2Line60_Country"],
            allowed=FILLED_OR_NA,
            notes={"Pt2Line58_IMBOrgName": "Only with item 55 Yes; attach the IMB's signed consent form."},
            choices={"Pt2Line60_Unit": UNIT_NO_PADDING},
        ),
        "consulate": q(
            "Part 2, Items 62.a-62.b: U.S. Embassy or Consulate where the beneficiary will apply for the visa",
            ["Pt2Line62a_CityTown", "Pt2Line62b_Country"],
            ["Pt2Line62a_CityTown", "Pt2Line62b_Country"],
            notes={"Pt2Line62a_CityTown": "City of the post (unbound; fill binds it)."},
        ),
    }


def other_information() -> dict[str, dict[str, Any]]:
    return {
        "protection_orders": q(
            "Part 3, Item 1: Has the petitioner ever been subject to a temporary or permanent protection or restraining order?",
            ["Pt3Line1_Checkboxes"],
            ["Pt3Line1_Checkboxes"],
            notes={"Pt3Line1_Checkboxes": "A fact from the record and the petitioner; Yes needs the court records."},
            choices={"Pt3Line1_Checkboxes": YES_NO},
        ),
        "specified_offenses": q(
            "Part 3, Items 2.a-2.c: Arrests or convictions for domestic violence, the listed violent crimes, or three or "
            "more controlled substance or alcohol offenses",
            ["P3Line2a_Checkboxes", "P3Line2b_Checkboxes", "P3Line2c_Checkboxes"],
            ["P3Line2a_Checkboxes", "P3Line2b_Checkboxes", "P3Line2c_Checkboxes"],
            notes={"P3Line2a_Checkboxes": "Any Yes needs certified court and police records (IMBRA)."},
            choices={"P3Line2a_Checkboxes": YES_NO, "P3Line2b_Checkboxes": YES_NO, "P3Line2c_Checkboxes": YES_NO},
        ),
        "battered_exception": q(
            "Part 3, Item 3: If convicted, the circumstances that apply (self-defense; violated an order issued for your "
            "own protection; connected to being battered or subjected to extreme cruelty)",
            ["Pt3Line3_Checkboxes"],
            ["Pt3Line3_Checkboxes"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt3Line3_Checkboxes": (
                    "Form defect: one global group, so only one box can be checked though the form says select all that "
                    "apply. Check the one that applies most directly and explain the others in Part 8."
                ),
            },
            choices={
                "Pt3Line3_Checkboxes": {
                    "Acting in self-defense": "A",
                    "Violated a protection order issued for my own protection": "B",
                    "Committed or was arrested for a crime connected to having been battered": "C",
                }
            },
        ),
        "other_arrests": q(
            "Part 3, Items 4.a-4.b: Any other arrest, citation or conviction (alcohol- or drug-related, or a fine of $500 "
            "or more), and the details",
            ["Part3Line4a_Checkboxes", "Pt3Line4B_Describe"],
            ["Part3Line4a_Checkboxes"],
            notes={"Pt3Line4B_Describe": "Only with Yes: what happened and how it ended; more in Part 8."},
            choices={"Part3Line4a_Checkboxes": YES_NO},
        ),
        "multiple_filer_waiver": q(
            "Part 3, Item 5: Multiple-filer waiver requested (general, extraordinary circumstances, mandatory), or not applicable",
            ["Pt3Line5_Checkboxes"],
            ["Pt3Line5_Checkboxes"],
            notes={
                "Pt3Line5_Checkboxes": (
                    "Not applicable when the beneficiary is the petitioner's spouse or the petitioner isn't a multiple "
                    "filer (IMBRA limits). Which waiver applies is the attorney's call."
                ),
            },
            choices={
                "Pt3Line5_Checkboxes": {
                    "Multiple filer, no permanent restraining orders or convictions (general waiver)": "A",
                    "Multiple filer, prior protection order or conviction (extraordinary circumstances waiver)": "B",
                    "Multiple filer, conviction resulting from domestic violence (mandatory waiver)": "C",
                    "Not applicable: beneficiary is my spouse or I am not a multiple filer": "D",
                }
            },
        ),
    }


def biographic() -> dict[str, dict[str, Any]]:
    race = [f"Pt4Line2_Checkbox[{n}]" for n in range(5)]
    labels = ["Native Hawaiian or Other Pacific Islander", "American Indian or Alaska Native", "White", "Asian",
              "Black or African American"]
    return {
        "biographic_info": q(
            "Part 4, Items 1 and 3-6: Petitioner's ethnicity, height, weight, eye and hair color",
            ["Pt4Line1_Checkbox", "Pt4Line3_HeightFeet", "Pt4Line3_HeightInches", "Pt4Line4_HeightInches1",
             "Pt4Line4_HeightInches2", "Pt4Line4_HeightInches3", "Pt4Line5_Checkbox", "Pt4Line6_HairColor"],
            ["Pt4Line1_Checkbox", "Pt4Line3_HeightFeet", "Pt4Line3_HeightInches", "Pt4Line4_HeightInches1",
             "Pt4Line5_Checkbox", "Pt4Line6_HairColor"],
            notes={
                "Pt4Line4_HeightInches1": (
                    "Weight in pounds, one digit per box despite the HeightInches names: 1-3 hundreds, 2 tens, 3 units "
                    "(for 95 pounds, 0, 9, 5)."
                ),
                "Pt4Line5_Checkbox": (
                    "Form defect: the box printed 'Gray' stores GRN and the box printed 'Green' stores GRY. Use the "
                    "choices (keyed by the printed label)."
                ),
            },
            choices={
                "Pt4Line1_Checkbox": {"Hispanic or Latino": "H", "Not Hispanic or Latino": "N"},
                "Pt4Line5_Checkbox": {
                    "Black": "BLK", "Blue": "BLU", "Brown": "BRO", "Gray": "GRN", "Green": "GRY", "Hazel": "HAZ",
                    "Maroon": "MAR", "Pink": "PNK", "Unknown/Other": "UNK",
                },
                "Pt4Line6_HairColor": {
                    "Bald (no hair)": "BAL", "Black": "BLK", "Blond": "BLN", "Brown": "BRO", "Gray": "GRY", "Red": "RED",
                    "Sandy": "SDY", "White": "WHI", "Unknown/Other": "UNK",
                },
            },
        ),
        "race": q(
            "Part 4, Item 2: Race (any one or more; five separate boxes)",
            race,
            notes={race[0]: "Each box is its own field with the on-state Y; check every one that applies."},
            choices={field: {label: "Y"} for field, label in zip(race, labels)},
        ),
    }


def signatures() -> dict[str, dict[str, Any]]:
    return {
        "petitioner_contact": q(
            "Part 5, Items 1-3: Petitioner's daytime phone, mobile phone (if any), email (if any)",
            ["Pt5Line1_DaytimePhoneNumber1", "Pt5Line2_MobileNumber1", "Pt5Line3_Email"],
            ["Pt5Line1_DaytimePhoneNumber1"],
            notes={"Pt5Line1_DaytimePhoneNumber1": PHONE, "Pt5Line2_MobileNumber1": PHONE},
        ),
        "petitioner_signature": q(
            "Part 5, Item 4: Petitioner's signature and date",
            ["Pt6Line4_Signature", "Pt5Line4_DateOfSignature"],
            allowed=[PENDING_SIGNATURE, FILLED],
            notes={
                "Pt6Line4_Signature": "The PETITIONER's signature (Part 5 item 4), despite the Pt6 name. " + SIGNATURE,
                "Pt5Line4_DateOfSignature": DATE + " Normally left for the petitioner to date at signing.",
            },
        ),
        "interpreter_block": q(
            "Part 6, Items 1-5 and certification: Interpreter's name, business, phones, email, and language",
            ["Pt6Line1_InterpreterFamilyName", "Pt6Line1_InterpreterGivenName", "Pt6Line2_NameofBusinessorOrgName",
             "Pt6Line4_InterpreterDaytimeTelephone[0]", "Pt6Line4_InterpreterDaytimeTelephone[1]", "Pt6Line5_Email",
             "Pt6_NameOfLanguage"],
            ["Pt6Line1_InterpreterFamilyName", "Pt6Line1_InterpreterGivenName", "Pt6Line4_InterpreterDaytimeTelephone[0]",
             "Pt6_NameOfLanguage"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt6Line4_InterpreterDaytimeTelephone[0]": "Item 3, daytime phone. " + PHONE,
                "Pt6Line4_InterpreterDaytimeTelephone[1]": "Item 4, MOBILE phone (if any), despite the name. " + PHONE,
            },
        ),
        "interpreter_signature": q(
            "Part 6, Item 6: Interpreter's signature and date",
            ["Pt6Line6_Signature", "Pt6Line6_DateofSignature"],
            allowed=[NOT_APPLICABLE, PENDING_SIGNATURE, FILLED],
            notes={"Pt6Line6_Signature": SIGNATURE, "Pt6Line6_DateofSignature": DATE},
        ),
        "preparer_block": q(
            "Part 7, Items 1-5: Preparer's name, business, phones, email (from the attorney profile)",
            ["Pt7Line1_PreparerFamilyName", "Pt7Line1b_PreparerGivenName", "Pt7Line2_NameofBusinessorOrgName",
             "Pt7Line3_DaytimePhoneNumber1", "Pt7Line4_PreparerMobileNumber", "Pt7Line5_Email"],
            ["Pt7Line1_PreparerFamilyName", "Pt7Line1b_PreparerGivenName", "Pt7Line3_DaytimePhoneNumber1"],
            allowed=FILLED_OR_NA,
            notes={
                "Pt7Line1_PreparerFamilyName": "Profile key attorney_name (family name); the firm in Pt7Line2 (firm_name).",
                "Pt7Line3_DaytimePhoneNumber1": "Profile key phone. " + PHONE,
                "Pt7Line5_Email": "Profile key email.",
            },
        ),
        "preparer_signature": q(
            "Part 7, Item 6: Preparer's signature and date",
            ["Pt7Line6_SignatureofPreparer", "Pt7Line6_DateofSignature"],
            allowed=[NOT_APPLICABLE, PENDING_SIGNATURE, FILLED],
            notes={"Pt7Line6_SignatureofPreparer": SIGNATURE, "Pt7Line6_DateofSignature": DATE},
        ),
        "additional_information": q(
            "Part 8, Items 3-7: Additional information (page, part, item and text, five entries)",
            [f"Line{n}{part}" for n in range(3, 8) for part in ("a_PageNumber", "b_PartNumber", "c_ItemNumber", "d_AdditionalInfo")],
            ["Line3a_PageNumber", "Line3b_PartNumber", "Line3c_ItemNumber", "Line3d_AdditionalInfo"],
            allowed=FILLED_OR_NA,
            notes={
                "Line3a_PageNumber": "Page, part and item boxes are unbound in the XFA template (fill binds them).",
                "Line3d_AdditionalInfo": (
                    "The box doesn't wrap: break long text into lines that fit, or the audit reports it cut off."
                ),
            },
        ),
    }


def k_petition() -> dict[str, Any]:
    questions: dict[str, dict[str, Any]] = {}
    for part in (petitioner(), beneficiary(), other_information(), biographic(), signatures()):
        questions.update(part)
    # The abroad address's phone belongs to item 48, listed with the address.
    questions["beneficiary_address_abroad"]["required_fields"].append("Pt2Line48_DaytimeTelephoneNum")
    return {
        "kind": "i-129f",
        "edition": "01/20/25",
        "field_list": "I-129F.json",
        "description": (
            "Form I-129F by a U.S. citizen for a K-1 fiance(e) (or a K-3 spouse with a pending I-130), with every "
            "history row, the IMBRA questions and the biographic part."
        ),
        "notes": [
            "Address and employment histories cover the last five years for both people; rows beyond the two the form "
            "has go in Part 8 with page, part and item.",
            "Part 3 (protection orders, specified offenses) is the petitioner's own record under IMBRA: answer from the "
            "record and the petitioner; a Yes needs certified court records, and the multiple-filer waiver is the "
            "attorney's call.",
            "This edition has no attorney box; the G-28 is filed with it.",
        ],
        "required_questions": questions,
    }


SCHEMAS = {"i129f_fiance_petition": k_petition()}

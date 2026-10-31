"""Question schema for Form I-751, Petition to Remove Conditions on Residence.

Built against the 04/01/24 edition (uscis.gov/i-751 and the PDF footer). Field list:
schemas/fields/I-751.json. Covers both filing routes: the joint petition (Part 3 item 1.a or
1.b, with the Part 8 statement and signature of the spouse or stepparent) and the waiver or
individual filing request (Part 3 items 1.c-1.g: deceased spouse, divorce or annulment,
battery or extreme cruelty, extreme hardship), where Part 8 is not applicable.
"""
from __future__ import annotations

from _common import DATE, FILLED, FILLED_OR_NA, NOT_APPLICABLE, PENDING_SIGNATURE, SIGNATURE_STATUSES, q

UNIT = {"apt": " APT ", "ste": " STE ", "flr": " FLR "}  # every address on this form uses padded states
YES_NO = {"yes": "Y", "no": "N"}

US_ONLY = "U.S. addresses only: 2-letter state code."
ZIP = "U.S. addresses only: 5-digit ZIP Code."
FOREIGN_ONLY = "Foreign addresses only."
JOINT_ONLY = (
    "Joint petition only (Part 3 item 1.a or 1.b): the spouse or stepparent named in Part 4 completes "
    "Part 8. not_applicable for a waiver or individual filing request (items 1.c-1.g)."
)


def child_fields(name: list[str], living: str, applying: str, address: str) -> list[str]:
    """One Part 5 child row: name, date of birth, A-Number, two yes/no answers, physical address."""
    return name + [
        living,
        applying,
        f"{address}_StreetNumberName",
        f"{address}_Unit",
        f"{address}_AptSteFlrNumber",
        f"{address}_CityOrTown",
        f"{address}_State",
        f"{address}_ZipCode",
        f"{address}_Province",
        f"{address}_PostalCode",
        f"{address}_Country",
    ]


CHILDREN = [
    # (item numbers, name/DOB/A-Number fields, living-with-you, applying-with-you, address prefix)
    ("1-6", ["Line1a_FamilyName3", "Line1b_GivenName3", "Line1c_MiddleName3", "Line2_DateOfBirth2", "Line3_AlienNumber"],
     "Part5Line5", "Part5Line6", "Pt5Line6"),
    ("7-12", ["Line13a_FamilyName[0]", "Line13b_GivenName[0]", "Line13c_MiddleName[0]", "Line14_DateOfBirth[0]",
              "Line15_AlienNumber[0]"], "Part5Line11", "Part5Line12", "Pt5Line12"),
    ("13-18", ["Line13a_FamilyName[1]", "Line13b_GivenName[1]", "Line13c_MiddleName[1]", "Line14_DateOfBirth[1]",
               "Line15_AlienNumber[1]"], "Part5Line17", "Part5Line18", "Pt5Line18"),
    ("19-24", ["Line13a_FamilyName[2]", "Line13b_GivenName[2]", "Line13c_MiddleName[2]", "Line14_DateOfBirth[2]",
               "Line15_AlienNumber[2]"], "Part5Line23", "Part5Line24", "Pt5Line24"),
    ("25-30", ["Line13a_FamilyName[3]", "Line13b_GivenName[3]", "Line13c_MiddleName[3]", "Line14_DateOfBirth[3]",
               "Line15_AlienNumber[3]"], "Part5Line29", "Part5Line30", "Pt5Line30"),
]

CHILDREN_FIELDS = [
    field
    for _, name, living, applying, address in CHILDREN
    for field in child_fields(name, living, applying, address)
]
CHILDREN_CHOICES = {
    field: dict(YES_NO) for _, _, living, applying, _ in CHILDREN for field in (living, applying)
}
CHILDREN_CHOICES.update({f"{address}_Unit": dict(UNIT) for *_, address in CHILDREN})


SCHEMAS = {
    "i751_remove_conditions": {
        "kind": "i-751",
        "edition": "04/01/24",
        "field_list": "I-751.json",
        "description": (
            "Form I-751 for a conditional resident, filed jointly with the spouse (or stepparent) or as a "
            "waiver or individual filing request."
        ),
        "notes": [
            "Route: Part 3 item 1.a or 1.b is the joint petition; 1.c-1.g is the waiver or individual filing "
            "request (several waiver boxes may be selected together). The route decides Part 1 item 13, "
            "Part 4's address and Part 8.",
            "Joint petition: the spouse (or stepparent) in Part 4 completes and signs Part 8 (form Part 7 "
            "NOTE). Waiver: Part 8 is not_applicable; a battery or extreme cruelty filer never needs the "
            "spouse's signature.",
            "A dependent child who got conditional residence with the parent (or within 90 days) is listed "
            "in Part 5 and is covered by this petition. Children who must file separately use their own "
            "I-751 (I-751 Instructions, Who May File).",
            "Part 11 items 1-2 (name, A-Number) repeat Part 1 automatically: Pt1Line1a/1b/1c and "
            "P1_Line7_AlienNumber are global fields. Set them once in Part 1.",
            "Explanations the form sends to Part 11: other names past two (items 2-3), a 'Yes' to item 20 "
            "(arrests) or item 22 (other addresses since becoming a permanent resident, with dates), "
            "children past five, and 'stateless' citizenship.",
            "Write N/A in a box that does not apply but needs an answer (How To Complete, item 3).",
            "The Part 7 and Part 8 statements, contact boxes and signature dates share field names: the "
            "first box ([0]) is the petitioner's (Part 7), the second ([1]) is the spouse's (Part 8). "
            "Always write the index.",
            "Form defect: these boxes are unbound in the XFA template (bind match=none): other names "
            "(P1_Line2*/P1_Line3*), every child's name (Line1a/1b/1c_*3, Line13a/13b/13c_*), and the "
            "Part 11 page, part and item numbers (P8_Line3a-7c). fill writes them and the filing copy "
            "shows them, but Adobe opening the XFA source shows them empty. Check them on the filing "
            "copy, not in Acrobat.",
        ],
        "required_questions": {
            "attorney_box": q(
                "Page 1 attorney box: G-28 attached, bar number, online account number",
                ["G28", "AttorneyStateBarNumber", "USCISELISAcctNumber"],
                ["G28", "AttorneyStateBarNumber"],
                allowed=FILLED_OR_NA,
                notes={
                    "G28": "Select when a G-28 is filed with the petition.",
                    "AttorneyStateBarNumber": "maxlen 15.",
                    "USCISELISAcctNumber": "The attorney's or representative's USCIS online account number, if any "
                    "(the field and tooltip say ELIS; maxlen 12). Blank when the profile says has_uscis_online_account \"no\".",
                },
                choices={"G28": {"g28_attached": "1"}},
            ),
            "conditional_resident_name": q(
                "Part 1, Item 1: Your full name (conditional resident)",
                ["Pt1Line1a_FamilyName", "Pt1Line1b_GivenName", "Pt1Line1c_MiddleName"],
                ["Pt1Line1a_FamilyName", "Pt1Line1b_GivenName"],
                notes={
                    "Pt1Line1a_FamilyName": "Global: also fills Part 11 item 1.a.",
                    "Pt1Line1c_MiddleName": "N/A if none.",
                },
            ),
            "other_names_used": q(
                "Part 1, Items 2-3: Other names used (aliases, maiden name, nicknames)",
                ["P1_Line2a_FamilyName", "P1_Line2b_GivenName", "P1_Line2c_MiddleName", "P1_Line3a_FamilyName",
                 "P1_Line3b_GivenName", "P1_Line3c_MiddleName"],
                ["P1_Line2a_FamilyName"],
                allowed=FILLED_OR_NA,
                notes={
                    "P1_Line2a_FamilyName": "Include the name before the qualifying marriage if it changed. If "
                    "none, type 'N/A' here and mark the question filled. More than two names go in Part 11.",
                },
            ),
            "birth_and_citizenship": q(
                "Part 1, Items 4-6: Date of birth, country of birth, country of citizenship or nationality",
                ["P1_Line4_DateOfBirth", "P1_Line5_CountryOfBirth", "P1_Line6_CountryOfCitizenship"],
                ["P1_Line4_DateOfBirth", "P1_Line5_CountryOfBirth", "P1_Line6_CountryOfCitizenship"],
                notes={
                    "P1_Line4_DateOfBirth": DATE,
                    "P1_Line6_CountryOfCitizenship": "All that apply; 'stateless' with an explanation in Part 11.",
                },
            ),
            "a_number": q(
                "Part 1, Item 7: A-Number",
                ["P1_Line7_AlienNumber"],
                ["P1_Line7_AlienNumber"],
                notes={
                    "P1_Line7_AlienNumber": "9 digits, no 'A' (from the green card). Global: also fills Part 11 item 2.",
                },
            ),
            "ssn": q(
                "Part 1, Item 8: U.S. Social Security Number, if any",
                ["P1_Line8_SSN"],
                ["P1_Line8_SSN"],
                allowed=FILLED_OR_NA,
                notes={"P1_Line8_SSN": "9 digits, no dashes."},
            ),
            "uscis_online_account_number": q(
                "Part 1, Item 9: USCIS Online Account Number, if any",
                ["P1_Line9_AcctIdentifier"],
                ["P1_Line9_AcctIdentifier"],
                allowed=FILLED_OR_NA,
                notes={
                    "P1_Line9_AcctIdentifier": "12 digits; only with an IOE receipt (tooltip says ELIS).",
                },
            ),
            "marital_status_and_marriage": q(
                "Part 1, Items 10-12: Marital status, date and place of marriage",
                ["Part1_Line10_MaritalStatus", "P1_Line11_DateOfMarriage", "P1_Line12_PlaceOfMarriage"],
                ["Part1_Line10_MaritalStatus", "P1_Line11_DateOfMarriage", "P1_Line12_PlaceOfMarriage"],
                notes={
                    "Part1_Line10_MaritalStatus": "Current status. Global group.",
                    "P1_Line11_DateOfMarriage": DATE + " The marriage through which conditional residence was "
                    "gained (from the marriage certificate).",
                    "P1_Line12_PlaceOfMarriage": "City and state or country, in one box.",
                },
                choices={
                    "Part1_Line10_MaritalStatus": {"single": "S", "married": "M", "divorced": "D", "widowed": "W"},
                },
            ),
            "marriage_ended": q(
                "Part 1, Item 13: Date the qualifying marriage ended (divorce or death)",
                ["P1_Line13_DateMarriageEnded"],
                ["P1_Line13_DateMarriageEnded"],
                allowed=FILLED_OR_NA,
                notes={
                    "P1_Line13_DateMarriageEnded": DATE + " Waiver routes 1.c (death) and 1.d (divorce or "
                    "annulment), and any other filing where that marriage has ended; not_applicable while it "
                    "continues.",
                },
            ),
            "conditional_residence_expiration": q(
                "Part 1, Item 14: Conditional residence expires on",
                ["P1_Line14_CRExpiresOn"],
                ["P1_Line14_CRExpiresOn"],
                notes={
                    "P1_Line14_CRExpiresOn": DATE + " The 'Card Expires' date on the conditional green card. A "
                    "joint petition is filed in the 90 days before it.",
                },
            ),
            "mailing_address": q(
                "Part 1, Item 15: Mailing address",
                ["Line17a_InCareofName", "Line17b_Street_Number_Name", "Line17c_Unit", "Line17c_Apt_Ste_Flr_Number",
                 "Line17d_City_Town", "Pt1Line15e_State", "Pt1Line15f_ZipCode"],
                ["Line17b_Street_Number_Name", "Line17d_City_Town", "Pt1Line15e_State", "Pt1Line15f_ZipCode"],
                notes={
                    "Line17a_InCareofName": "Item 15.a despite the Line17 name: the Line17a-17d boxes are the MAILING "
                    "address (item 15). If any.",
                    "Line17b_Street_Number_Name": "Item 15.b. The form has no country, province or postal code here: "
                    "the mailing address must be in the United States.",
                    "Line17c_Unit": "Item 15.c unit type; set together with Line17c_Apt_Ste_Flr_Number.",
                    "Line17d_City_Town": "Item 15.d.",
                    "Pt1Line15e_State": US_ONLY,
                    "Pt1Line15f_ZipCode": ZIP,
                },
                choices={"Line17c_Unit": dict(UNIT)},
            ),
            "physical_address": q(
                "Part 1, Items 16-17: Physical address different from mailing? If yes, physical address",
                ["Line16_Checkbox", "Pt1Line17_InCareofName", "Pt1Line17_StreetNumberName", "Pt1Line17_Unit",
                 "Pt1Line17_AptSteFlrNumber", "Pt1Line17_CityOrTown", "Pt1Line17_State", "Pt1Line17_ZipCode"],
                ["Line16_Checkbox"],
                notes={
                    "Line16_Checkbox": "Item 16. With 'yes', fill item 17 (street, city, state, ZIP); with 'no', "
                    "leave item 17 blank.",
                    "Pt1Line17_InCareofName": "Item 17.a; the form prints an In Care Of box here too. Usually blank.",
                    "Pt1Line17_State": US_ONLY,
                    "Pt1Line17_ZipCode": ZIP,
                },
                choices={"Line16_Checkbox": dict(YES_NO), "Pt1Line17_Unit": dict(UNIT)},
            ),
            "removal_proceedings": q(
                "Part 1, Item 18: Are you in removal, deportation, or rescission proceedings?",
                ["Line17_Checkbox"],
                ["Line17_Checkbox"],
                notes={"Line17_Checkbox": "Item 18, despite the Line17 name."},
                choices={"Line17_Checkbox": dict(YES_NO)},
            ),
            "fee_paid_to_non_attorney": q(
                "Part 1, Item 19: Was a fee paid to anyone other than an attorney for this petition?",
                ["Line18_Checkbox"],
                ["Line18_Checkbox"],
                notes={"Line18_Checkbox": "Item 19, despite the Line18 name."},
                choices={"Line18_Checkbox": dict(YES_NO)},
            ),
            "criminal_history": q(
                "Part 1, Item 20: Ever arrested, detained, charged, indicted, fined, imprisoned, or committed a crime?",
                ["Line19_Checkbox"],
                ["Line19_Checkbox"],
                notes={
                    "Line19_Checkbox": "Item 20, despite the Line19 name. 'Yes' needs an explanation in Part 11 "
                    "and the court records the instructions list; leave it open for the attorney if the record "
                    "suggests anything.",
                },
                choices={"Line19_Checkbox": dict(YES_NO)},
            ),
            "different_marriage": q(
                "Part 1, Item 21: If married, is this a different marriage than the one that gave conditional status?",
                ["Line20_Checkbox"],
                ["Line20_Checkbox"],
                allowed=FILLED_OR_NA,
                notes={
                    "Line20_Checkbox": "Item 21, despite the Line20 name. Joint petition: 'no'. not_applicable when "
                    "not currently married (widowed or divorced and not remarried).",
                },
                choices={"Line20_Checkbox": dict(YES_NO)},
            ),
            "other_addresses_since_permanent_residence": q(
                "Part 1, Item 22: Resided at any other address since becoming a permanent resident?",
                ["Line21_Checkbox"],
                ["Line21_Checkbox"],
                notes={
                    "Line21_Checkbox": "Item 22, despite the Line21 name. 'Yes' requires every address since "
                    "becoming a permanent resident, with dates, in Part 11.",
                },
                choices={"Line21_Checkbox": dict(YES_NO)},
            ),
            "spouse_government_service_abroad": q(
                "Part 1, Item 23: Spouse or parent's spouse serving with or employed by the U.S. Government abroad?",
                ["Line22_Checkbox"],
                ["Line22_Checkbox"],
                notes={"Line22_Checkbox": "Item 23, despite the Line22 name."},
                choices={"Line22_Checkbox": dict(YES_NO)},
            ),
            "ethnicity_and_race": q(
                "Part 2, Items 1-2: Ethnicity (one) and race (all that apply)",
                ["P3_checkbox6", "P3_checkbox7_White", "P3_checkbox7_Asian", "P3_checkbox7_Black",
                 "P3_checkbox7_Indian", "P3_checkbox7_Hawaiian"],
                ["P3_checkbox6"],
                notes={
                    "P3_checkbox6": "Part 2 item 1 despite the P3 name. Global group.",
                    "P3_checkbox7_White": "Race boxes are separate; select every one that applies (at least one).",
                },
                choices={
                    "P3_checkbox6": {"hispanic_or_latino": "H", "not_hispanic_or_latino": "N"},
                    "P3_checkbox7_White": {"white": "Y"},
                    "P3_checkbox7_Asian": {"asian": "Y"},
                    "P3_checkbox7_Black": {"black_or_african_american": "Y"},
                    "P3_checkbox7_Indian": {"american_indian_or_alaska_native": "Y"},
                    "P3_checkbox7_Hawaiian": {"native_hawaiian_or_other_pacific_islander": "Y"},
                },
            ),
            "height_and_weight": q(
                "Part 2, Items 3-4: Height (feet, inches) and weight (pounds)",
                ["P3_Line8_HeightFeet", "P3_Line8_HeightInches", "P3_Line9_HeightInches1", "P3_Line9_HeightInches2",
                 "P3_Line9_HeightInches3"],
                ["P3_Line8_HeightFeet", "P3_Line8_HeightInches", "P3_Line9_HeightInches1", "P3_Line9_HeightInches2",
                 "P3_Line9_HeightInches3"],
                notes={
                    "P3_Line8_HeightFeet": "Drop-down, values '2'-'8'.",
                    "P3_Line8_HeightInches": "Drop-down, values '0'-'11' (no leading zero, although the "
                    "instructions say '09').",
                    "P3_Line9_HeightInches1": "WEIGHT, despite the name: first digit of the weight in pounds. "
                    "Three one-digit boxes, e.g. 1, 6, 5 for 165 lb or 0, 9, 8 for 98 lb; 0, 0, 0 if unknown "
                    "(I-751 Instructions, Part 2 item 4).",
                    "P3_Line9_HeightInches2": "WEIGHT, second digit.",
                    "P3_Line9_HeightInches3": "WEIGHT, third digit.",
                },
            ),
            "eye_and_hair_color": q(
                "Part 2, Items 5-6: Eye color and hair color",
                ["P3_checkbox10", "P3_checkbox11"],
                ["P3_checkbox10", "P3_checkbox11"],
                notes={
                    "P3_checkbox10": "Item 5 eye color, global group.",
                    "P3_checkbox11": "Item 6 hair color, global group.",
                },
                choices={
                    "P3_checkbox10": {
                        "black": "BLK", "blue": "BLU", "brown": "BRO", "gray": "GRY", "green": "GRN",
                        "hazel": "HAZ", "maroon": "MAR", "pink": "PNK", "unknown_other": "UNK",
                    },
                    "P3_checkbox11": {
                        "bald": "BAL", "black": "BLK", "blond": "BLN", "brown": "BRO", "gray": "GRY",
                        "red": "RED", "sandy": "SDY", "white": "WHI", "unknown_other": "UNK",
                    },
                },
            ),
            "basis_for_petition": q(
                "Part 3, Item 1: Basis for petition (joint filing 1.a/1.b, or waiver 1.c-1.g)",
                ["Pt3Line1", "Pt3Line1c", "Pt3Line1d", "Pt3Line1e", "Pt3Line1f", "Pt3Line1g"],
                notes={
                    "Pt3Line1": "Joint filing: one global group, A = 1.a with my spouse, B = 1.b with my parent's "
                    "spouse. Leave it blank for a waiver.",
                    "Pt3Line1c": "Waiver 1.c, spouse deceased. The waiver boxes 1.c-1.g are separate fields; select "
                    "every one that applies, and none of them with 1.a/1.b. Exactly one route must be "
                    "chosen; the schema cannot check that, so confirm it.",
                    "Pt3Line1d": "Waiver 1.d, good-faith marriage ended by divorce or annulment.",
                    "Pt3Line1e": "Waiver 1.e, battered or extreme cruelty by the U.S. citizen or LPR spouse.",
                    "Pt3Line1f": "Waiver 1.f, child battered or subjected to extreme cruelty by the parent's "
                    "spouse or the conditional resident parent.",
                    "Pt3Line1g": "Waiver 1.g, extreme hardship.",
                },
                choices={
                    "Pt3Line1": {"joint_with_spouse": "A", "joint_with_parents_spouse": "B"},
                    "Pt3Line1c": {"waiver_spouse_deceased": "C"},
                    "Pt3Line1d": {"waiver_divorce_or_annulment": "D"},
                    "Pt3Line1e": {"waiver_battery_or_extreme_cruelty": "E"},
                    "Pt3Line1f": {"waiver_child_battery_or_extreme_cruelty": "F"},
                    "Pt3Line1g": {"waiver_extreme_hardship": "G"},
                },
            ),
            "spouse_relationship": q(
                "Part 4, Item 1: Relationship (spouse or former spouse, or parent's spouse or former spouse)",
                ["Part4_Relationship"],
                ["Part4_Relationship"],
                notes={
                    "Part4_Relationship": "Global group: box [0] is 1.b (B), box [1] is 1.a (A). Part 4 is the U.S. "
                    "citizen or LPR spouse (or stepparent) through whom conditional residence was gained, on "
                    "every route, including a deceased or former spouse.",
                },
                choices={
                    "Part4_Relationship": {"spouse_or_former_spouse": "A", "parents_spouse_or_former_spouse": "B"},
                },
            ),
            "spouse_identity": q(
                "Part 4, Items 2-5: Spouse's (or stepparent's) name, date of birth, SSN, A-Number",
                ["Pt4Line2a_FamilyName2", "Pt4Line2b_GivenName2", "Pt4Line2c_MiddleName2", "Line3_DateOfBirth",
                 "Line4_SSN", "Line5_AlienNumber"],
                ["Pt4Line2a_FamilyName2", "Pt4Line2b_GivenName2", "Line3_DateOfBirth"],
                notes={
                    "Pt4Line2b_GivenName2": "Item 2.b GIVEN name; the tooltip wrongly says '(Family Name)'.",
                    "Line3_DateOfBirth": "Part 4 item 3. " + DATE,
                    "Line4_SSN": "Part 4 item 4, if any; 9 digits.",
                    "Line5_AlienNumber": "Part 4 item 5, if any (an LPR spouse has one); 9 digits.",
                },
            ),
            "spouse_physical_address": q(
                "Part 4, Item 6: Spouse's (or stepparent's) physical address",
                ["Pt4Line6_StreetNumberName", "Pt4Line6_Unit", "Pt4Line6_AptSteFlrNumber", "Pt4Line6_CityOrTown",
                 "Pt4Line6_State", "Pt4Line6_ZipCode", "Pt4Line6_Province", "Pt4Line6_PostalCode", "Pt4Line6_Country"],
                ["Pt4Line6_StreetNumberName", "Pt4Line6_CityOrTown", "Pt4Line6_Country"],
                allowed=FILLED_OR_NA,
                notes={
                    "Pt4Line6_StreetNumberName": "Joint petition: usually the couple's address. not_applicable for "
                    "a deceased spouse (or write 'Deceased' with the attorney's approval), and leave it to the "
                    "attorney for an abuse waiver or an unknown address.",
                    "Pt4Line6_State": US_ONLY,
                    "Pt4Line6_ZipCode": ZIP,
                    "Pt4Line6_Province": FOREIGN_ONLY,
                    "Pt4Line6_PostalCode": FOREIGN_ONLY,
                },
                choices={"Pt4Line6_Unit": dict(UNIT)},
            ),
            "children": q(
                "Part 5, Items 1-30: Children 1-5 (name, date of birth, A-Number, living with you, applying with you, address)",
                CHILDREN_FIELDS,
                ["Line1a_FamilyName3", "Line1b_GivenName3", "Line2_DateOfBirth2", "Part5Line5", "Part5Line6"],
                allowed=FILLED_OR_NA,
                notes={
                    "Line1a_FamilyName3": "Child 1, items 1-6: Line1a/1b/1c_*3 names, Line2_DateOfBirth2, "
                    "Line3_AlienNumber, Part5Line5 (living with you), Part5Line6 (applying with you), Pt5Line6_* "
                    "address. List ALL children, not only those applying.",
                    "Line13a_FamilyName[0]": "Children 2-5 share the Line13a/13b/13c, Line14_DateOfBirth and "
                    "Line15_AlienNumber names: [0] child 2 (items 7-12), [1] child 3 (13-18), [2] child 4 (19-24), "
                    "[3] child 5 (25-30). Always write the index. More children go in Part 11.",
                    "Part5Line5": "Child 1 yes/no boxes: Part5Line5/6. Child 2: Part5Line11/12; child 3: 17/18; "
                    "child 4: 23/24; child 5: 29/30. The on-states are Y and N, in varying box order.",
                    "Part5Line6": "'Applying with you' = yes only for a child who got conditional residence with "
                    "you or within 90 days.",
                    "Pt5Line6_StreetNumberName": "Child 1 address (item 6). Children 2-5: Pt5Line12_*, Pt5Line18_*, "
                    "Pt5Line24_*, Pt5Line30_* (each: StreetNumberName, Unit, AptSteFlrNumber, CityOrTown, State, "
                    "ZipCode, Province, PostalCode, Country).",
                    "Line3_AlienNumber": "Child 1 A-Number, if any; 9 digits.",
                },
                choices=CHILDREN_CHOICES,
            ),
            "accommodations": q(
                "Part 6, Items 1-4: Accommodations for disabilities or impairments",
                ["Part6Line1", "Part6Line2", "Part6Line3", "Pt6Line4a_chbx", "Pt6Line4_DeafOrHardOfHearing",
                 "Pt6Line4b_chbx", "Pt6Line4_BlindOrSightImpaired", "Pt6Line4c_chbx", "Pt6Line4_AccomodationRequested"],
                ["Part6Line1", "Part6Line2", "Part6Line3"],
                notes={
                    "Part6Line1": "Item 1 (you), item 2 Part6Line2 (spouse), item 3 Part6Line3 (included children). "
                    "Items 4.a-4.c only after a 'yes'. Each 4.a-4.c text box holds 3 lines of 35 characters; "
                    "break the lines yourself and continue in Part 11.",
                    "Pt6Line4_DeafOrHardOfHearing": "Item 4.a text, with Pt6Line4a_chbx; name the sign language if any.",
                    "Pt6Line4_BlindOrSightImpaired": "Item 4.b text, with Pt6Line4b_chbx.",
                    "Pt6Line4_AccomodationRequested": "Item 4.c text, with Pt6Line4c_chbx.",
                },
                choices={
                    "Part6Line1": dict(YES_NO),
                    "Part6Line2": dict(YES_NO),
                    "Part6Line3": dict(YES_NO),
                    "Pt6Line4a_chbx": {"deaf_or_hard_of_hearing": "A"},
                    "Pt6Line4b_chbx": {"blind_or_low_vision": "B"},
                    "Pt6Line4c_chbx": {"other_disability": "C"},
                },
            ),
            "petitioner_statement_language": q(
                "Part 7, Item 1.a/1.b: Petitioner reads English, or an interpreter read the petition (language)",
                ["P5_Checkbox1", "Pt5Line1b_Language"],
                ["P5_Checkbox1"],
                notes={
                    "P5_Checkbox1": "Part 7 despite the P5 name. Global group: A = 1.a, B = 1.b.",
                    "Pt5Line1b_Language": "Only with 1.b; then complete Part 9.",
                },
                choices={"P5_Checkbox1": {"reads_english": "A", "interpreter": "B"}},
            ),
            "petitioner_statement_preparer": q(
                "Part 7, Item 2: Preparer used (name; is or is not an attorney or accredited representative)",
                ["P5_Checkbox2[0]", "P5_Line2_NameofRepresentative", "P5_Checkbox2_Who"],
                ["P5_Checkbox2[0]", "P5_Line2_NameofRepresentative", "P5_Checkbox2_Who"],
                allowed=FILLED_OR_NA,
                notes={
                    "P5_Checkbox2[0]": "The Part 7 item 2 box. P5_Checkbox2 is NOT global: [1] is Part 8's item 2 "
                    "box. Always write [0].",
                    "P5_Line2_NameofRepresentative": "The preparer's full name, matching Part 10.",
                    "P5_Checkbox2_Who": "Global group: Y = 'is', N = 'is not' an attorney or accredited representative.",
                },
                choices={
                    "P5_Checkbox2[0]": {"preparer_used": "Y"},
                    "P5_Checkbox2_Who": {"is_attorney_or_accredited_rep": "Y", "is_not": "N"},
                },
            ),
            "petitioner_contact": q(
                "Part 7, Items 3-5: Petitioner's daytime phone, mobile phone, email",
                ["P5_Line3_DaytimePhoneNumber[0]", "P5_Line4_MobilePhoneNumber[0]", "P5_Line5_EmailAddress[0]"],
                ["P5_Line3_DaytimePhoneNumber[0]"],
                notes={
                    "P5_Line3_DaytimePhoneNumber[0]": "Part 7 item 3; [1] is the spouse's (Part 8). 10 digits "
                    "(maxlen 10).",
                    "P5_Line4_MobilePhoneNumber[0]": "Part 7 item 4, if any; 10 digits.",
                    "P5_Line5_EmailAddress[0]": "Part 7 item 5, if any; maxlen 38.",
                },
            ),
            "petitioner_asc_acknowledgement": q(
                "Part 7: Acknowledgement of Appointment at USCIS ASC ('I, [name], understand ...')",
                ["P7_Name"],
                ["P7_Name"],
                notes={
                    "P7_Name": "The petitioner's full name in the Part 7 acknowledgement (page 6). Part 8's is Pt8_Name.",
                },
            ),
            "petitioner_signature": q(
                "Part 7, Item 6: Petitioner's signature and date",
                ["P5_Line6a_SignatureofPetitioner", "P5_Line6b_DateofSignature[0]"],
                allowed=SIGNATURE_STATUSES,
                notes={
                    "P5_Line6a_SignatureofPetitioner": "Signed in ink; a parent may sign for a child under 14.",
                    "P5_Line6b_DateofSignature[0]": "Petitioner's date; [1] is the spouse's (Part 8).",
                },
            ),
            "spouse_statement_language": q(
                "Part 8, Item 1.a/1.b: Spouse reads English, or an interpreter read the petition (language)",
                ["P8_Checkbox1", "Pt7Line1b_Language"],
                ["P8_Checkbox1"],
                allowed=FILLED_OR_NA,
                notes={
                    "P8_Checkbox1": JOINT_ONLY + " Global group: A = 1.a, B = 1.b.",
                    "Pt7Line1b_Language": "Part 8 item 1.b language, despite the Pt7 name.",
                },
                choices={"P8_Checkbox1": {"reads_english": "A", "interpreter": "B"}},
            ),
            "spouse_statement_preparer": q(
                "Part 8, Item 2: Preparer used by the spouse (name; is or is not an attorney)",
                ["P5_Checkbox2[1]", "P7Line2_NameofRepresentative", "P7_Checkbox2_Who"],
                ["P5_Checkbox2[1]", "P7Line2_NameofRepresentative", "P7_Checkbox2_Who"],
                allowed=FILLED_OR_NA,
                notes={
                    "P5_Checkbox2[1]": JOINT_ONLY + " This is the Part 8 item 2 box (second box of P5_Checkbox2).",
                    "P7Line2_NameofRepresentative": "Part 8 item 2 preparer name, despite the P7 name.",
                    "P7_Checkbox2_Who": "Part 8 item 2. Global group: Y = 'is', N = 'is not' an attorney.",
                },
                choices={
                    "P5_Checkbox2[1]": {"preparer_used": "Y"},
                    "P7_Checkbox2_Who": {"is_attorney_or_accredited_rep": "Y", "is_not": "N"},
                },
            ),
            "spouse_contact": q(
                "Part 8, Items 3-5: Spouse's daytime phone, mobile phone, email",
                ["P5_Line3_DaytimePhoneNumber[1]", "P5_Line4_MobilePhoneNumber[1]", "P5_Line5_EmailAddress[1]"],
                ["P5_Line3_DaytimePhoneNumber[1]"],
                allowed=FILLED_OR_NA,
                notes={
                    "P5_Line3_DaytimePhoneNumber[1]": JOINT_ONLY + " 10 digits (maxlen 10).",
                    "P5_Line4_MobilePhoneNumber[1]": "If any; 10 digits.",
                    "P5_Line5_EmailAddress[1]": "If any; maxlen 38.",
                },
            ),
            "spouse_asc_acknowledgement": q(
                "Part 8: Spouse's Acknowledgement of Appointment at USCIS ASC ('I, [name], understand ...')",
                ["Pt8_Name"],
                ["Pt8_Name"],
                allowed=FILLED_OR_NA,
                notes={"Pt8_Name": JOINT_ONLY + " The spouse's (or stepparent's) full name (page 8)."},
            ),
            "spouse_signature": q(
                "Part 8, Item 6: Spouse's (or stepparent's) signature and date",
                ["P5_Line6a_SignatureofSpouse", "P5_Line6b_DateofSignature[1]"],
                allowed=[PENDING_SIGNATURE, FILLED, NOT_APPLICABLE],
                notes={
                    "P5_Line6a_SignatureofSpouse": JOINT_ONLY + " Signed in ink.",
                    "P5_Line6b_DateofSignature[1]": "The spouse's date (second box of the name).",
                },
            ),
            "interpreter_block": q(
                "Part 9, Items 1-5: Interpreter's name, business, mailing address, contact; certification language",
                ["P6_Line1a_InterpretersFamilyName", "P6_Line1b_InterpretersGivenName", "P6_Line2_NameofBusinessor",
                 "P6_Line3a_StreetNumberName", "Pt9Line3_Unit", "Pt9Line3_AptSteFlrNumber", "Pt9Line3_CityOrTown",
                 "Pt9Line3_State", "Pt9Line3_ZipCode", "Pt9Line3_Province", "Pt9Line3_PostalCode", "Pt9Line3_Country",
                 "P6_Line4_InterpretersDaytimePhoneNumber", "P6_Line5_InterpretersEmailAddress", "P6_Language"],
                ["P6_Line1a_InterpretersFamilyName", "P6_Line1b_InterpretersGivenName", "P6_Line3a_StreetNumberName",
                 "Pt9Line3_CityOrTown", "Pt9Line3_Country", "P6_Line4_InterpretersDaytimePhoneNumber", "P6_Language"],
                allowed=FILLED_OR_NA,
                notes={
                    "P6_Line1a_InterpretersFamilyName": "Part 9 despite the P6 name. Only when Part 7 (or 8) item "
                    "1.b is selected.",
                    "P6_Line3a_StreetNumberName": "Interpreter's street (item 3.a). The rest of this address is "
                    "Pt9Line3_*. Do not confuse with Pt9Line3_StreetNumberName, which is the PREPARER's street.",
                    "P6_Line4_InterpretersDaytimePhoneNumber": "10 digits (maxlen 10). The form has no interpreter "
                    "mobile box.",
                    "P6_Line5_InterpretersEmailAddress": "Form defect: maxlen 10, so almost no email fits. Put the "
                    "email in Part 11 (Page 8, Part 9, Item 5) and leave this box blank or 'See Part 11'.",
                    "P6_Language": "Certification language, same as Part 7 item 1.b (maxlen 18).",
                    "Pt9Line3_State": US_ONLY,
                    "Pt9Line3_ZipCode": ZIP,
                    "Pt9Line3_Province": FOREIGN_ONLY,
                    "Pt9Line3_PostalCode": FOREIGN_ONLY,
                },
                choices={"Pt9Line3_Unit": dict(UNIT)},
            ),
            "interpreter_signature": q(
                "Part 9, Item 6: Interpreter's signature and date",
                ["P6_Line6a_Signature", "P6_Line6b_DateofSignature"],
                allowed=[PENDING_SIGNATURE, FILLED, NOT_APPLICABLE],
                notes={"P6_Line6a_Signature": "Signed in ink (page 9)."},
            ),
            "preparer_block": q(
                "Part 10, Items 1-6: Preparer's name, business, mailing address and contact",
                ["P7_Line1a_FamilyName", "P7_Line1b_PreparersGivenName", "P7_Line2_NameofBusinessor",
                 "Pt9Line3_StreetNumberName", "Pt10Line3_Unit", "Pt10Line3_AptSteFlrNumber", "P7_Line3c_CityTown",
                 "P7_Line3d_State", "P7_Line3e_ZipCode", "P7_Line3f_Province", "P7_Line3g_PostalCode",
                 "P7_Line3h_Country", "P7_Line4_PreparersDaytimePhoneNumber", "P7_Line5_PreparersFaxNumber",
                 "P7_Line6_PreparersEmailAddress"],
                ["P7_Line1a_FamilyName", "P7_Line1b_PreparersGivenName", "Pt9Line3_StreetNumberName",
                 "P7_Line3c_CityTown", "P7_Line3h_Country", "P7_Line4_PreparersDaytimePhoneNumber"],
                allowed=FILLED_OR_NA,
                notes={
                    "P7_Line1a_FamilyName": "Part 10 despite the P7 name; from the attorney profile. not_applicable "
                    "only if the petitioner prepared the petition alone.",
                    "Pt9Line3_StreetNumberName": "The PREPARER's street (Part 10 item 3.a), despite the Pt9 name.",
                    "P7_Line3d_State": US_ONLY,
                    "P7_Line3e_ZipCode": ZIP,
                    "P7_Line3f_Province": FOREIGN_ONLY,
                    "P7_Line3g_PostalCode": FOREIGN_ONLY,
                    "P7_Line4_PreparersDaytimePhoneNumber": "10 digits (maxlen 10).",
                    "P7_Line5_PreparersFaxNumber": "Item 5 is a FAX number on this form (not mobile); if any.",
                    "P7_Line6_PreparersEmailAddress": "If any; maxlen 38.",
                },
                choices={"Pt10Line3_Unit": dict(UNIT)},
            ),
            "preparer_statement": q(
                "Part 10, Item 7: Preparer's statement (not an attorney, or attorney: extends / does not extend)",
                ["P7_checkbox7[0]", "P7_checkbox7[1]", "Pt10Item7b_Extends", "Pt10Item7b_NotExtend"],
                allowed=FILLED_OR_NA,
                notes={
                    "P7_checkbox7[0]": "7.a, not an attorney. P7_checkbox7 is NOT a global group: [0] (on-state A) "
                    "and [1] (on-state B) are separate boxes, so write the index and set only one.",
                    "P7_checkbox7[1]": "7.b, attorney or accredited representative.",
                    "Pt10Item7b_Extends": "With 7.b only. 'Extends' and 'does not extend' are two separate fields; "
                    "set one. 'Extends' means a G-28 must be filed (select the page 1 G-28 box).",
                },
                choices={
                    "P7_checkbox7[0]": {"not_attorney": "A"},
                    "P7_checkbox7[1]": {"attorney_or_accredited_rep": "B"},
                    "Pt10Item7b_Extends": {"extends": "Y"},
                    "Pt10Item7b_NotExtend": {"does_not_extend": "N"},
                },
            ),
            "preparer_signature": q(
                "Part 10, Item 8: Preparer's signature and date",
                ["P7_Line8a_SignatureofPreparer", "P7_Line8b_DateofSignature"],
                allowed=[PENDING_SIGNATURE, FILLED, NOT_APPLICABLE],
                notes={"P7_Line8a_SignatureofPreparer": "Signed in ink (page 10)."},
            ),
            "additional_information": q(
                "Part 11, Items 3-7: Additional information (page, part, item, text)",
                [
                    f"P8_Line{n}{suffix}"
                    for n in range(3, 8)
                    for suffix in ("a_PageNumber", "b_PartNumber", "c_ItemNumber", "d_AdditionalInfo")
                ],
                ["P8_Line3a_PageNumber", "P8_Line3b_PartNumber", "P8_Line3c_ItemNumber", "P8_Line3d_AdditionalInfo"],
                allowed=FILLED_OR_NA,
                notes={
                    "P8_Line3a_PageNumber": "Part 11 despite the P8 names. Page maxlen 2; part and item maxlen 6, "
                    "except entries 4 and 7 (part maxlen 4, item maxlen 9).",
                    "P8_Line3d_AdditionalInfo": "Each 'd' box holds 8 lines of 38 characters (Courier 10 pt) and "
                    "does not wrap: break the lines yourself (the audit reports clipped text). Use entries 3-7 in "
                    "order; attach a continuation sheet for more.",
                },
            ),
        },
    },
}

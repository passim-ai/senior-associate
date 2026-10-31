"""Question schema for Form N-400, Application for Naturalization.

Built against the 01/20/25 edition (the edition date on uscis.gov/n-400 and in the PDF footer,
14 pages). Field list: schemas/fields/N-400.json.

The field names in this edition are carried over from older editions and mostly carry the old
part numbers (P7_ is biographic data, P10_ is marital history, P11_/P12_ are Part 9 questions),
and many tooltips number the parts differently again (they call Residence "Part 3", Biographic
"Part 4", Marital History "Part 7"). The labels below use the form's printed part and item
numbers; the field names were matched to items by their position on the page.
"""
from __future__ import annotations

from _common import DATE, FILLED, FILLED_OR_NA, NOT_APPLICABLE, PENDING_SIGNATURE, SIGNATURE_STATUSES, q

YN = {"yes": "Y", "no": "N"}
UNIT = {"apt": "APT", "ste": "STE", "flr": "FLR"}
PHONE = "10 digits, no punctuation (maxlen 10)."

PART9_DEFAULT_NO = (
    "An eligibility yes/no question: 'No' may be entered when nothing in the record suggests "
    "otherwise (forms-preparer skill). A 'Yes' needs an explanation in Part 14."
)


def yn(*fields: str) -> dict[str, dict[str, str]]:
    return {field: dict(YN) for field in fields}


TRIP_COUNTRIES = ["P9_Line1_Countries1"] + [f"P8_Line1_Countries{n}" for n in range(2, 7)]
CRIME_ROWS = range(1, 6)

SCHEMAS = {
    "n400_naturalization": {
        "kind": "n-400",
        "edition": "01/20/25",
        "field_list": "N-400.json",
        "description": (
            "Form N-400 for any eligibility basis (general 5-year, 3-year marriage, VAWA, 319(b), "
            "military, other), with every history row and every Part 9 question."
        ),
        "notes": [
            "Field names keep older editions' part numbers and many tooltips number the parts "
            "differently again. Go by the labels and field_notes here, not by the name or tooltip.",
            "Look-back periods depend on the Part 1 basis (Instructions, Parts 4, 7 and 8). Residence: "
            "5 years for 1.a, 1.f and 1.g; 3 years for 1.b and 1.c; current address only for 1.d and 1.e. "
            "Employment and schools: 5 years for 1.a, 1.f and 1.g; 3 years for 1.b, 1.c and 1.d; 1 year "
            "for 1.e. Trips: 5 years for 1.a, 1.f and 1.g; 3 years for 1.b and 1.c; none for 1.d and 1.e "
            "(trips_outside_us is then not_applicable).",
            "The form has room for the current address plus 3 prior addresses, 3 children, 3 employment "
            "rows, 6 trips and 5 offenses. Put further rows in Part 14 (additional_information), citing "
            "page, part and item, for example Page 3, Part 4, Item 1 or Page 6, Part 8, Item 1.",
            "Part 5 items 4.a-8 are answered only when filing under Part 1 item 1.b or 1.d (form page 4). "
            "For every other basis current_spouse and current_spouse_employer are not_applicable, even "
            "for a married applicant; items 1-3 are still answered. This edition asks no details of "
            "prior spouses, only the number of marriages (item 3) and the spouse's number of marriages "
            "(item 7); the termination evidence goes in the packet.",
            "Global fields: Line1_AlienNumber fills the A-Number box at the top of every page, and "
            "P2_Line1_FamilyName/GivenName/MiddleName also fill the name in Part 14 item 1. Set them once, "
            "by base name.",
            "Form defect (01/20/25): Line3_GivenName1/2, Line3_MiddleName1/2 (other names used), "
            "Part2Line4a_GivenName/MiddleName (new name), P10_Line4a_FamilyName/GivenName/MiddleName "
            "(current spouse's name), P10_Line4g_Employer (spouse's number of marriages) and "
            "P11_Line3A/B/C (Part 14 item 2 page, part, item) have bind='none' in the XFA template. The "
            "filing copy shows them, but Adobe opening the XFA source shows those boxes blank. Review "
            "the filing copy, not the source in Acrobat, and don't re-save the source from Acrobat.",
            "Some boxes are read-only in the blank until the controlling answer is selected in Adobe "
            "(Part1Line5_OtherExplain, DropDownList1, the Part 2 item 3 new-name boxes, the Apt/Ste/Flr "
            "numbers, P10_Line5b_DateBecame, P9_NobilityTitles). fill writes them regardless; fill them "
            "only when the controlling answer calls for them.",
            "Part 9 yes/no questions: the default 'No' rule of the forms-preparer skill covers items "
            "1-2, 5.a-21, 23-24 and 27-29. Items 3-4 (taxes), 22.a-22.c (Selective Service), 25-26.d "
            "(U.S. armed forces) and 30.a-30.b (titles) are facts from the record. Items 31-32 and 34-37 "
            "expect 'Yes' and item 33 expects 'No'; any other answer is an attorney_decision. Items 8.a "
            "and 12 are often 'Yes' for anyone who did compulsory military service: check the employment "
            "history and the client's account before defaulting them to 'No'.",
            "Box sizes: the table boxes of Parts 4, 6, 7 and 9 (item 15) are narrow, fixed at 10 pt, and "
            "neither wrap nor shrink; the field_notes give their capacity in characters. The 30 pt table "
            "boxes of Parts 4, 6 and 9 hold one line on the filing copy (a second line is cut off and the "
            "audit reports it): restate anything longer in Part 14. The Part 7 date boxes are centred and "
            "hold a mm/dd/yyyy date edge to edge.",
            "Parts 15 and 16 are signed at the interview. Leave them blank (interview_and_oath_signatures "
            "is always not_applicable).",
            "Dates are mm/dd/yyyy throughout. The form has no attorney/G-28 box; the attorney appears "
            "only as the Part 13 preparer.",
        ],
        "required_questions": {
            # ------------------------------------------------------------------ Part 1
            "eligibility_basis": q(
                "Part 1, Item 1: Reason for filing (select one basis)",
                ["Part1_Eligibility", "Part1Line5_OtherExplain", "DropDownList1"],
                ["Part1_Eligibility"],
                notes={
                    "Part1_Eligibility": "One global group; the on-state letter matches the item letter (A-G).",
                    "Part1Line5_OtherExplain": "Only with 1.g (Other): the reason for filing.",
                    "DropDownList1": "Only with 1.d (319(b)) and a residence outside the United States: the "
                    "USCIS field office for the interview. A choice list whose options begin with a space, "
                    "e.g. ' Texas - USCIS Houston Field Office' (dump-fields --acro lists them).",
                },
                choices={
                    "Part1_Eligibility": {
                        "general_provision": "A",
                        "spouse_of_us_citizen": "B",
                        "vawa": "C",
                        "spouse_of_us_citizen_qualified_employment_abroad": "D",
                        "military_service_during_hostilities": "E",
                        "one_year_honorable_military_service": "F",
                        "other": "G",
                    },
                },
            ),
            "a_number": q(
                "Part 1: Your A-Number (top of every page)",
                ["Line1_AlienNumber"],
                ["Line1_AlienNumber"],
                allowed=FILLED_OR_NA,
                notes={
                    "Line1_AlienNumber": "9 digits, no 'A' (maxlen 9); pad an 8-digit number with a leading 0. "
                    "Global: one value fills the box on all 14 pages. Every permanent resident has one; "
                    "not_applicable only for a military applicant who was never issued one.",
                },
            ),
            # ------------------------------------------------------------------ Part 2
            "applicant_legal_name": q(
                "Part 2, Item 1: Your current legal name",
                ["P2_Line1_FamilyName", "P2_Line1_GivenName", "P2_Line1_MiddleName"],
                ["P2_Line1_FamilyName", "P2_Line1_GivenName"],
                notes={
                    "P2_Line1_FamilyName": "Global: also fills Part 14 item 1 on page 13.",
                },
            ),
            "other_names_used": q(
                "Part 2, Item 2: Other names used since birth",
                ["Line2_FamilyName1", "Line3_GivenName1", "Line3_MiddleName1", "Line2_FamilyName2", "Line3_GivenName2",
                 "Line3_MiddleName2"],
                ["Line2_FamilyName1", "Line3_GivenName1"],
                allowed=FILLED_OR_NA,
                notes={
                    "Line3_GivenName1": "Row 1 given name (the family name is Line2_FamilyName1). Unbound in the "
                    "XFA layer, as are the other Line3_* boxes (see notes).",
                    "Line2_FamilyName2": "Row 2. More than two other names go in Part 14 (Page 1, Part 2, Item 2).",
                },
            ),
            "name_change": q(
                "Part 2, Item 3: Would you like to legally change your name? (and the new name)",
                ["P2_Line34_NameChange", "Part2Line3_FamilyName", "Part2Line4a_GivenName", "Part2Line4a_MiddleName"],
                ["P2_Line34_NameChange"],
                notes={
                    "P2_Line34_NameChange": "Optional item, but answer it: 'No' unless the client asked for a "
                    "name change.",
                    "Part2Line3_FamilyName": "New family name, only with 'Yes'. The given and middle names are "
                    "Part2Line4a_GivenName and Part2Line4a_MiddleName (unbound in the XFA layer).",
                },
                choices=yn("P2_Line34_NameChange"),
            ),
            "uscis_online_account_number": q(
                "Part 2, Item 4: USCIS Online Account Number, if any",
                ["P2_Line6_USCISELISAcctNumber"],
                ["P2_Line6_USCISELISAcctNumber"],
                allowed=FILLED_OR_NA,
                notes={
                    "P2_Line6_USCISELISAcctNumber": "The applicant's own account number (12 digits, maxlen 12), "
                    "not the attorney's.",
                },
            ),
            "applicant_identity": q(
                "Part 2, Items 5, 6, 8, 9: Sex, date of birth, country of birth, country of citizenship",
                ["P2_Line7_Gender", "P2_Line8_DateOfBirth", "P2_Line10_CountryOfBirth",
                 "P2_Line11_CountryOfNationality"],
                ["P2_Line7_Gender", "P2_Line8_DateOfBirth", "P2_Line10_CountryOfBirth",
                 "P2_Line11_CountryOfNationality"],
                notes={
                    "P2_Line7_Gender": "Item 5.",
                    "P2_Line8_DateOfBirth": "Item 6, " + DATE + " Other dates of birth ever used go in Part 14.",
                    "P2_Line10_CountryOfBirth": "Item 8 (the name says Line10).",
                    "P2_Line11_CountryOfNationality": "Item 9 (the name says Line11). Further nationalities go "
                    "in Part 14 (Page 2, Part 2, Item 9).",
                },
                choices={"P2_Line7_Gender": {"male": "M", "female": "F"}},
            ),
            "permanent_resident_date": q(
                "Part 2, Item 7: Date you became a lawful permanent resident",
                ["P2_Line9_DateBecamePermanentResident"],
                ["P2_Line9_DateBecamePermanentResident"],
                allowed=FILLED_OR_NA,
                notes={
                    "P2_Line9_DateBecamePermanentResident": DATE + " The 'Resident Since' date on the green "
                    "card. not_applicable only for a non-LPR military applicant (1.e).",
                },
            ),
            "parent_us_citizen": q(
                "Part 2, Item 10: Was your mother or father a U.S. citizen before your 18th birthday?",
                ["P2_Line10_claimdisability"],
                ["P2_Line10_claimdisability"],
                notes={
                    "P2_Line10_claimdisability": "Despite the name, this is item 10 (U.S. citizen parent), not a "
                    "disability question. A 'Yes' means the applicant may already be a citizen (N-600): "
                    "attorney_decision.",
                },
                choices=yn("P2_Line10_claimdisability"),
            ),
            "disability_test_exception": q(
                "Part 2, Item 11: Disability or impairment preventing the English/civics tests (Form N-648)",
                ["P2_Line11_claimdisability"],
                ["P2_Line11_claimdisability"],
                notes={
                    "P2_Line11_claimdisability": "'Yes' requires a completed Form N-648 with the filing. This "
                    "edition has no accommodations part: accommodation requests go through the appointment "
                    "notice or uscis.gov/accommodationsinfo, not the form.",
                },
                choices=yn("P2_Line11_claimdisability"),
            ),
            "social_security_update": q(
                "Part 2, Items 12.a-12.c: Social Security card, SSN and consent for disclosure",
                ["Line12a_Checkbox", "Line12b_SSN", "Line12.c_Checkbox"],
                ["Line12a_Checkbox"],
                notes={
                    "Line12b_SSN": "Only with 12.a 'Yes', if the applicant has an SSN: 9 digits, no dashes (maxlen 9).",
                    "Line12.c_Checkbox": "Only with 12.a 'Yes', and then it must be 'Yes' for a card to issue. "
                    "The name contains a literal dot.",
                },
                choices=yn("Line12a_Checkbox", "Line12.c_Checkbox"),
            ),
            # ------------------------------------------------------------------ Part 3
            "biographic_info": q(
                "Part 3, Items 1-6: Ethnicity, race, height, weight, eye color, hair color",
                ["P7_Line1_Ethnicity", "P7_Line2_Race[0]", "P7_Line2_Race[1]", "P7_Line2_Race[2]", "P7_Line2_Race[3]",
                 "P7_Line2_Race[4]", "P7_Line3_HeightFeet", "P7_Line3_HeightInches", "P7_Line4_Pounds1",
                 "P7_Line4_Pounds2", "P7_Line4_Pounds3", "P7_Line5_Eye", "P7_Line6_Hair"],
                ["P7_Line1_Ethnicity", "P7_Line3_HeightFeet", "P7_Line3_HeightInches", "P7_Line4_Pounds1",
                 "P7_Line4_Pounds2", "P7_Line4_Pounds3", "P7_Line5_Eye", "P7_Line6_Hair"],
                notes={
                    "P7_Line2_Race[0]": "Race boxes are separate (select all that apply) and not global: write each "
                    "selected box by its index. [1] Asian and [3] Native Hawaiian/Pacific Islander share the "
                    "on-state 'A'. At least one race box should be selected.",
                    "P7_Line3_HeightFeet": "Choice list '2'-'8'.",
                    "P7_Line3_HeightInches": "Choice list '0'-'11' (no leading zero, whatever the instructions say).",
                    "P7_Line4_Pounds1": "Weight is three one-digit boxes (hundreds, tens, units): 165 lb is '1', '6', "
                    "'5'; 98 lb is '0', '9', '8'. Unknown, under 30 or over 699: '0', '0', '0'.",
                },
                choices={
                    "P7_Line1_Ethnicity": {"hispanic_or_latino": "Y", "not_hispanic_or_latino": "N"},
                    "P7_Line2_Race[0]": {"american_indian_or_alaska_native": "I"},
                    "P7_Line2_Race[1]": {"asian": "A"},
                    "P7_Line2_Race[2]": {"black_or_african_american": "B"},
                    "P7_Line2_Race[3]": {"native_hawaiian_or_other_pacific_islander": "A"},
                    "P7_Line2_Race[4]": {"white": "W"},
                    "P7_Line5_Eye": {
                        "black": "BLK",
                        "blue": "BLU",
                        "brown": "BRO",
                        "gray": "GRY",
                        "green": "GRN",
                        "hazel": "HAZ",
                        "maroon": "MAR",
                        "pink": "PNK",
                        "unknown_other": "XXX",
                    },
                    "P7_Line6_Hair": {
                        "bald": "BAL",
                        "black": "BLK",
                        "blond": "BLN",
                        "brown": "BRO",
                        "gray": "GRY",
                        "red": "RED",
                        "sandy": "SDY",
                        "white": "WHI",
                        "unknown_other": "XXX",
                    },
                },
            ),
            # ------------------------------------------------------------------ Part 4
            "current_physical_address": q(
                "Part 4, Item 1: Current physical address and date you moved in",
                ["P4_Line1_InCareOfName", "P4_Line1_StreetName", "P4_Line1_Unit", "P4_Line1_Number", "P4_Line1_City",
                 "P4_Line1_State[0]", "P4_Line1_ZipCode", "P4_Line1_Province", "P4_Line1_PostalCode",
                 "P4_Line1_Country", "P4_Line1_DatesofResidence[1]"],
                ["P4_Line1_StreetName", "P4_Line1_City", "P4_Line1_DatesofResidence[1]"],
                notes={
                    "P4_Line1_StreetName": "The P4_Line1_* boxes on page 3 are the current PHYSICAL address, though "
                    "their tooltips say 'Current Mailing Address'. The mailing address is P5_Line1b_* on page 4.",
                    "P4_Line1_Number": "Apt/Ste/Flr number, with P4_Line1_Unit.",
                    "P4_Line1_State[0]": "Choice list of 2-letter codes (options carry a leading space; fill "
                    "with 'TX'). U.S. addresses only. [1] is the mailing address's state on page 4.",
                    "P4_Line1_ZipCode": "U.S. addresses only: 5 digits (maxlen 5).",
                    "P4_Line1_Province": "Foreign addresses only, with P4_Line1_PostalCode and P4_Line1_Country.",
                    "P4_Line1_DatesofResidence[1]": "Dates of Residence FROM (" + DATE + ") Index [1] is the From "
                    "box; [0] is the read-only To box pre-printed PRESENT. Leave [0] alone.",
                },
                choices={"P4_Line1_Unit": dict(UNIT)},
            ),
            "prior_addresses": q(
                "Part 4, Item 1: Prior physical addresses in the look-back period (3 rows)",
                [
                    field
                    for n in (1, 2, 3)
                    for field in (
                        f"P4_Line3_PhysicalAddress{n}",
                        f"P4_Line3_CityTown{n}",
                        f"P4_Line3_State{n}",
                        f"P4_Line3_ZipCode{n}",
                        f"P4_Line3_Country{n}",
                        "P4_Line3_From1[0]" if n == 1 else f"P4_Line3_From{n}",
                        "P4_Line3_From1[1]" if n == 1 else f"P4_Line3_To{n}",
                    )
                ],
                ["P4_Line3_PhysicalAddress1", "P4_Line3_CityTown1", "P4_Line3_Country1", "P4_Line3_From1[0]",
                 "P4_Line3_From1[1]"],
                allowed=FILLED_OR_NA,
                notes={
                    "P4_Line3_PhysicalAddress1": "Most recent prior address first. Street number and name, with "
                    "any apartment. not_applicable when the current address covers the whole look-back period. "
                    "The row boxes are fixed 10 pt and neither wrap nor shrink, and on the rendered filing copy "
                    "only their first line shows whole (see notes). Keep each box to one line, about 26 "
                    "characters here, and give a longer address in full in Part 14 (Page 3, Part 4, Item 1).",
                    "P4_Line3_CityTown1": "About 9 characters on one line: abbreviate a longer city name and give it "
                    "in full in Part 14.",
                    "P4_Line3_State1": "'State/Province' column: a 2-letter code, or a foreign province of about 8 "
                    "characters.",
                    "P4_Line3_ZipCode1": "'ZIP Code/Postal Code' column (about 9 characters).",
                    "P4_Line3_Country1": "Only 42 pt wide, about 6 characters: 'USA', or a short form with the full "
                    "country name in Part 14.",
                    "P4_Line3_From1[0]": "Row 1 From, " + DATE,
                    "P4_Line3_From1[1]": "Row 1 To, despite the name (" + DATE + ") Rows 2-3 use P4_Line3_To2/To3.",
                },
            ),
            "mailing_same_as_physical": q(
                "Part 4, Item 2: Is your current physical address also your current mailing address?",
                ["Pt3_Line2a_Checkbox"],
                ["Pt3_Line2a_Checkbox"],
                choices=yn("Pt3_Line2a_Checkbox"),
            ),
            "mailing_address": q(
                "Part 4, Item 3: Current mailing address (safe mailing address, if applicable)",
                ["P5_Line1b_InCareOfName", "P5_Line1b_StreetName", "P5_Line1b_Unit", "P5_Line1b_Number",
                 "P5_Line1b_City", "P4_Line1_State[1]", "P5_Line1b_ZipCode", "P5_Line1b_Province",
                 "P5_Line1b_PostalCode", "P5_Line1b_Country"],
                ["P5_Line1b_StreetName", "P5_Line1b_City"],
                allowed=FILLED_OR_NA,
                notes={
                    "P5_Line1b_StreetName": "Only when item 2 is 'No'; otherwise not_applicable. A G-28 attorney's "
                    "address goes in P5_Line1b_InCareOfName only on the client's instruction.",
                    "P4_Line1_State[1]": "The mailing address's state is index [1] of the physical address's state "
                    "field (choice list, 2-letter code). P5_Line1b has no state box of its own.",
                    "P5_Line1b_ZipCode": "U.S. addresses only: 5 digits (maxlen 5).",
                },
                choices={"P5_Line1b_Unit": dict(UNIT)},
            ),
            # ------------------------------------------------------------------ Part 5
            "marital_status": q(
                "Part 5, Items 1 and 3: Current marital status; how many times you have been married",
                ["P10_Line1_MaritalStatus", "Part9Line3_TimesMarried"],
                ["P10_Line1_MaritalStatus"],
                notes={
                    "Part9Line3_TimesMarried": "Item 3 (maxlen 3). Count every marriage, including the current "
                    "one, annulled, customary and religious marriages, and each marriage to the same person. "
                    "Leave blank for single, never married.",
                },
                choices={
                    "P10_Line1_MaritalStatus": {
                        "single_never_married": "S",
                        "married": "M",
                        "divorced": "D",
                        "widowed": "W",
                        "separated": "E",
                        "marriage_annulled": "A",
                    },
                },
            ),
            "spouse_military": q(
                "Part 5, Item 2: If currently married, is your spouse a current member of the U.S. armed forces?",
                ["P7_Line2_Forces"],
                ["P7_Line2_Forces"],
                allowed=FILLED_OR_NA,
                notes={
                    "P7_Line2_Forces": "Every currently married (or separated) applicant answers, whatever the "
                    "basis; not_applicable otherwise.",
                },
                choices=yn("P7_Line2_Forces"),
            ),
            "current_spouse": q(
                "Part 5, Items 4.a-7: Current spouse (only for Part 1 basis 1.b or 1.d)",
                ["P10_Line4a_FamilyName", "P10_Line4a_GivenName", "P10_Line4a_MiddleName", "P10_Line4d_DateofBirth",
                 "P10_Line4e_DateEnterMarriage", "P10_Line5_Citizen", "P10_Line5a_When", "P10_Line5b_DateBecame",
                 "P7_Line6_ANumber", "P10_Line4g_Employer"],
                ["P10_Line4a_FamilyName", "P10_Line4a_GivenName", "P10_Line4d_DateofBirth",
                 "P10_Line4e_DateEnterMarriage", "P10_Line5_Citizen", "P10_Line5a_When", "P10_Line4g_Employer"],
                allowed=FILLED_OR_NA,
                notes={
                    "P10_Line4a_FamilyName": "Item 4.a, with P10_Line4a_GivenName/MiddleName. All three are unbound "
                    "in the XFA layer (see notes).",
                    "P10_Line4d_DateofBirth": "Item 4.b, spouse's date of birth (" + DATE + ")",
                    "P10_Line4e_DateEnterMarriage": "Item 4.c, date of the current marriage (" + DATE + ")",
                    "P10_Line5_Citizen": "Item 4.d, despite the name: is the spouse's physical address the same as "
                    "yours? 'No' means the spouse's address goes in Part 14 (Page 4, Part 5, Item 4.d).",
                    "P10_Line5a_When": "Item 5.a: when the spouse became a U.S. citizen.",
                    "P10_Line5b_DateBecame": "Item 5.b, only with 5.a 'Other' (" + DATE + ")",
                    "P7_Line6_ANumber": "Item 6, spouse's A-Number if any: 9 digits, no 'A'.",
                    "P10_Line4g_Employer": "Item 7, despite the name: how many times the spouse has been married "
                    "(maxlen 3). Unbound in the XFA layer.",
                },
                choices={
                    "P10_Line5_Citizen": {"same_address_yes": "Y", "same_address_no": "N"},
                    "P10_Line5a_When": {"by_birth_in_us": "B", "other": "O"},
                },
            ),
            "current_spouse_employer": q(
                "Part 5, Item 8: Current spouse's current employer or company (only for basis 1.d)",
                ["TextField1"],
                ["TextField1"],
                allowed=FILLED_OR_NA,
                notes={"TextField1": "Only for Part 1 item 1.d (319(b) qualified employment abroad)."},
            ),
            # ------------------------------------------------------------------ Part 6
            "children_count": q(
                "Part 6, Item 1: Total number of children under 18",
                ["P11_Line1_TotalChildren[0]"],
                ["P11_Line1_TotalChildren[0]"],
                notes={
                    "P11_Line1_TotalChildren[0]": "Children UNDER 18 only in this edition, including stepchildren, "
                    "adopted, missing, and those living elsewhere. '0' if none (maxlen 3). Index [1] of this name "
                    "is Part 10 item 4 on page 11.",
                },
            ),
            "children": q(
                "Part 6, Item 2: Children under 18 (3 rows: name, date of birth, residence, relationship, support)",
                [
                    field
                    for n, support in ((1, "P9_Line5a"), (2, "P6_ChildTwo"), (3, "P6_ChildThree"))
                    for field in (
                        f"P7_EmployerName{n}",
                        f"P7_From{n}[0]",
                        f"P7_OccupationFieldStudy{n}[0]",
                        f"P7_OccupationFieldStudy{n}[1]",
                        support,
                    )
                ],
                ["P7_EmployerName1", "P7_From1[0]", "P7_OccupationFieldStudy1[0]", "P7_OccupationFieldStudy1[1]",
                 "P9_Line5a"],
                allowed=FILLED_OR_NA,
                notes={
                    "P7_EmployerName1": "Despite the name, row 1's son or daughter's name (first and family name). "
                    "Rows 2-3: P7_EmployerName2/3. More than 3 children go in Part 14 (Page 5, Part 6, Item 2), "
                    "as does the address of a child who does not live with the applicant.",
                    "P7_From1[0]": "Row 1 child's date of birth (" + DATE + ") Index [0] only: P7_From1[1] is the "
                    "Part 7 employment From date.",
                    "P7_OccupationFieldStudy1[0]": "Row 1 Residence column. Type one of the valid options: 'resides "
                    "with me', 'does not reside with me', or 'unknown/missing'. About 16 characters show on one "
                    "line, and only the first line shows whole on the filing copy (see notes): write 'does not "
                    "reside' + newline + 'with me', and say it in full in the Part 14 entry that gives that "
                    "child's address.",
                    "P7_OccupationFieldStudy1[1]": "Row 1 Relationship column: 'biological son or daughter', "
                    "'stepchild', or 'legally adopted son or daughter'. About 15 characters a line: write "
                    "'biological son' + newline + 'or daughter'. The second line is clipped on the current "
                    "filing copy (see notes), so also state the full relationship in Part 14 (Page 5, Part 6, "
                    "Item 2) unless it is 'stepchild'. Index [2] is the Part 7 occupation.",
                    "P9_Line5a": "Row 1: are you providing support for this son or daughter? Rows 2-3 are "
                    "P6_ChildTwo and P6_ChildThree.",
                },
                choices=yn("P9_Line5a", "P6_ChildTwo", "P6_ChildThree"),
            ),
            # ------------------------------------------------------------------ Part 7
            "employment_and_schools": q(
                "Part 7, Item 1: Employment and schools in the look-back period, current first (3 rows)",
                [
                    field
                    for n in (1, 2, 3)
                    for field in (
                        f"P5_EmployerName{n}",
                        f"P7_City{n}",
                        f"P7_State{n}",
                        f"P7_ZipCode{n}",
                        f"P7_Country{n}",
                        f"P7_From{n}[1]",
                        *([] if n == 1 else [f"P7_To{n}"]),
                        f"P7_OccupationFieldStudy{n}[2]",
                    )
                ],
                ["P5_EmployerName1", "P7_City1", "P7_From1[1]", "P7_OccupationFieldStudy1[2]"],
                notes={
                    "P5_EmployerName1": "Row 1 is the current or most recent activity; its To date is pre-printed "
                    "PRESENT and has no box. Use 'self-employed', 'unemployed' or 'retired' as the name where "
                    "that applies. The Part 7 boxes hold ONE line at a fixed 10 pt (no wrap, no shrink): name "
                    "about 14 characters, city 10, state/province 6, ZIP/postal code 8, country 8, occupation 13. "
                    "Abbreviate, or put a short form here and the full row in Part 14 (Page 5, Part 7, Item 1).",
                    "P7_City1": "City or town: about 10 characters, one line.",
                    "P7_State1": "'State/Province' column: a 2-letter code, or a province of about 6 characters.",
                    "P7_ZipCode1": "'ZIP Code/Postal Code' column, about 8 characters.",
                    "P7_Country1": "Country, about 8 characters, e.g. 'USA'.",
                    "P7_From1[1]": "Row 1 From (" + DATE + ") Index [1]: P7_From1[0] is the first child's date "
                    "of birth. Rows 2-3: P7_From2[1], P7_From3[1], with To in P7_To2, P7_To3.",
                    "P7_OccupationFieldStudy1[2]": "Row 1 occupation or field of study, about 13 characters. Index "
                    "[2]: [0] and [1] are the first child's residence and relationship.",
                },
            ),
            # ------------------------------------------------------------------ Part 8
            "trips_outside_us": q(
                "Part 8, Item 1: Trips outside the United States in the look-back period, most recent first (6 rows)",
                [
                    field
                    for n in range(1, 7)
                    for field in (
                        f"P8_Line1_DateLeft{n}",
                        f"P8_Line1_DateReturn{n}",
                        TRIP_COUNTRIES[n - 1],
                    )
                ],
                ["P8_Line1_DateLeft1", "P8_Line1_DateReturn1", "P9_Line1_Countries1"],
                allowed=FILLED_OR_NA,
                notes={
                    "P8_Line1_DateLeft1": "Leave out day trips completed within 24 hours. not_applicable when there "
                    "were no trips, or for bases 1.d and 1.e. More than 6 trips go in Part 14 (Page 6, Part 8, "
                    "Item 1). A trip over 6 months needs continuous-residence evidence.",
                    "P9_Line1_Countries1": "Row 1 countries, despite the P9_ name; rows 2-6 are "
                    "P8_Line1_Countries2-6. maxlen 55.",
                },
            ),
            # ------------------------------------------------------------------ Part 9
            "part9_citizenship_voting_taxes": q(
                "Part 9, Items 1-4: Claims to U.S. citizenship, voting, overdue taxes, nonresident tax filing",
                ["P9_Line1", "P9_Line2", "P9_Line3", "P9_Line4"],
                ["P9_Line1", "P9_Line2", "P9_Line3", "P9_Line4"],
                notes={
                    "P9_Line1": PART9_DEFAULT_NO + " Applies to items 1-2.",
                    "P9_Line3": "Items 3-4 are tax facts: answer from the tax transcripts or the client, not by "
                    "default.",
                },
                choices=yn("P9_Line1", "P9_Line2", "P9_Line3", "P9_Line4"),
            ),
            "part9_communist_totalitarian": q(
                "Part 9, Items 5.a-5.b: Communist or totalitarian party; advocating overthrow or violence",
                ["P9_5a", "P9_5b"],
                ["P9_5a", "P9_5b"],
                notes={"P9_5a": PART9_DEFAULT_NO},
                choices=yn("P9_5a", "P9_5b"),
            ),
            "part9_terrorist_group_support": q(
                "Part 9, Items 6.a-6.c: Membership in or support of a group that used weapons, kidnapping or sabotage",
                ["P12_6a", "P12_6b", "P12_6c"],
                ["P12_6a", "P12_6b", "P12_6c"],
                notes={"P12_6a": PART9_DEFAULT_NO + " The P12_ prefix is a leftover; these are Part 9."},
                choices=yn("P12_6a", "P12_6b", "P12_6c"),
            ),
            "part9_torture_genocide_persecution": q(
                "Part 9, Items 7.a-7.g: Torture, genocide, killing, injuring, sexual violence, religious or other persecution",
                ["P9_Line7a", "P9_Line7.b.", "P9_Line7.c", "P11_7d", "P9_Line7.e", "P9_Line7.f", "P9_Line7.g"],
                ["P9_Line7a", "P9_Line7.b.", "P9_Line7.c", "P11_7d", "P9_Line7.e", "P9_Line7.f", "P9_Line7.g"],
                notes={
                    "P9_Line7a": PART9_DEFAULT_NO,
                    "P9_Line7.b.": "Item 7.b. The names of 7.b-7.c and 7.e-7.g contain literal dots (7.b ends with "
                    "one); 7.d is P11_7d.",
                },
                choices=yn("P9_Line7a", "P9_Line7.b.", "P9_Line7.c", "P11_7d", "P9_Line7.e", "P9_Line7.f",
                           "P9_Line7.g"),
            ),
            "part9_armed_groups_weapons_detention": q(
                "Part 9, Items 8.a-14: Military, police or armed groups, detention, weapons, training, child soldiers",
                ["P9_Line8a", "P9_Line8b", "P9_Line9", "P9_Line10a", "P9_Line10b", "P9_Line10c", "P9_Line11",
                 "P9_Line12", "P9_Line13", "P9_Line14"],
                ["P9_Line8a", "P9_Line8b", "P9_Line9", "P9_Line10a", "P9_Line11", "P9_Line12", "P9_Line13",
                 "P9_Line14"],
                notes={
                    "P9_Line8a": PART9_DEFAULT_NO + " But 8.a (military or police unit) and 12 (weapons or "
                    "military-type training) are 'Yes' for anyone who did compulsory military service: check the "
                    "employment history first. A 'Yes' to 8.a/8.b needs country, unit, rank and dates in Part 14.",
                    "P9_Line10b": "10.b and 10.c only if 10.a is 'Yes'; otherwise leave blank.",
                },
                choices=yn("P9_Line8a", "P9_Line8b", "P9_Line9", "P9_Line10a", "P9_Line10b", "P9_Line10c", "P9_Line11",
                           "P9_Line12", "P9_Line13", "P9_Line14"),
            ),
            "part9_crimes_and_offenses": q(
                "Part 9, Items 15.a-16: Crimes not arrested for; arrests, citations, charges; completed probation or parole",
                ["P9_Line15a", "P9_Line15b", "P12_Line16"],
                ["P9_Line15a", "P9_Line15b"],
                notes={
                    "P9_Line15a": PART9_DEFAULT_NO + " Any arrest, citation (traffic citations included), charge "
                    "or court record in the file makes 15.a/15.b an attorney_decision, never a default; the "
                    "items must also list offenses committed under 18 and sealed or expunged records.",
                    "P12_Line16": "Item 16, only if the applicant received a suspended sentence, probation or parole; "
                    "otherwise leave blank.",
                },
                choices=yn("P9_Line15a", "P9_Line15b", "P12_Line16"),
            ),
            "part9_offense_table": q(
                "Part 9, Item 15 table: Each crime or offense (5 rows)",
                [
                    field
                    for n in CRIME_ROWS
                    for field in (
                        f"P12_Line29_why{n}",
                        f"P12_Line29_Date{n}",
                        f"P12_Line29_DateOfConv{n}",
                        f"P12_Line29_Outcome{n}[1]",
                        f"P12_Line29_Outcome{n}[0]",
                        f"P12_Line29_Outcome{n}[2]",
                    )
                ],
                ["P12_Line29_why1", "P12_Line29_Date1", "P12_Line29_Outcome1[1]", "P12_Line29_Outcome1[0]"],
                allowed=FILLED_OR_NA,
                notes={
                    "P12_Line29_why1": "Only when 15.a or 15.b is 'Yes'; otherwise not_applicable. Row 1 crime or "
                    "offense (crime of conviction, if convicted). More than 5 go in Part 14 (Page 8, Part 9, "
                    "Item 15). The text boxes in this table are fixed 10 pt with no wrap, and only their first "
                    "line shows whole on the filing copy (see notes): about 19 characters here, 14 for the place, "
                    "17 for the result, 10 for the sentence. Use short forms and give the full account in Part 14.",
                    "P12_Line29_Date1": "Date of the crime or offense (" + DATE + ")",
                    "P12_Line29_DateOfConv1": "Date of conviction or guilty plea, if any (" + DATE + ")",
                    "P12_Line29_Outcome1[1]": "Index [1] is the PLACE (city or town, state, country), the third column.",
                    "P12_Line29_Outcome1[0]": "Index [0] is the RESULT or disposition (no charges filed, convicted, "
                    "charges dismissed, ...), the fourth column.",
                    "P12_Line29_Outcome1[2]": "Index [2] is the SENTENCE, if any (about 10 characters).",
                },
            ),
            "part9_good_moral_character": q(
                "Part 9, Items 17.a-19: Prostitution, drugs, polygamy, marriage fraud, smuggling, gambling, support, false statements",
                ["P11_Line17A", "P11_Line17B", "P11_Line17C", "P12_Line17d", "P12_Line17e", "P12_Line17f",
                 "P12_Line17g", "P12_Line17h", "P12_Line18", "P12_Line19"],
                ["P11_Line17A", "P11_Line17B", "P11_Line17C", "P12_Line17d", "P12_Line17e", "P12_Line17f",
                 "P12_Line17g", "P12_Line17h", "P12_Line18", "P12_Line19"],
                notes={
                    "P11_Line17A": PART9_DEFAULT_NO + " 17.g (failure to support dependents) must agree with Part 6 "
                    "support answers and any child-support orders.",
                    "P12_Line17e": "The tooltips of the 'No' boxes of 17.e, 17.f and 18 say 'Select Yes'; the "
                    "on-states below are right.",
                },
                choices=yn("P11_Line17A", "P11_Line17B", "P11_Line17C", "P12_Line17d", "P12_Line17e", "P12_Line17f",
                           "P12_Line17g", "P12_Line17h", "P12_Line18", "P12_Line19"),
            ),
            "part9_removal_proceedings": q(
                "Part 9, Items 20-21: Removal, rescission or deportation proceedings; removed or deported",
                ["P12_Line20", "P12_Line21"],
                ["P12_Line20", "P12_Line21"],
                notes={"P12_Line20": PART9_DEFAULT_NO},
                choices=yn("P12_Line20", "P12_Line21"),
            ),
            "part9_selective_service": q(
                "Part 9, Items 22.a-22.c: Selective Service (male in the U.S. between 18 and 26; registration)",
                ["P9_Line22a", "Pt9_Line22b", "P9_Line22c_Date", "P9_Line22c_SSNumber"],
                ["P9_Line22a"],
                notes={
                    "P9_Line22a": "A fact from sex, date of birth and U.S. entry history, not a default: 'No' for a "
                    "female applicant, or a male who was a lawful nonimmigrant for the whole period.",
                    "Pt9_Line22b": "Only with 22.a 'Yes'. Note the 'Pt9_' prefix.",
                    "P9_Line22c_Date": "Only with 22.b 'Yes': registration date (" + DATE + ")",
                    "P9_Line22c_SSNumber": "Selective Service number (maxlen 10), not a Social Security number.",
                },
                choices=yn("P9_Line22a", "Pt9_Line22b"),
            ),
            "part9_military_service": q(
                "Part 9, Items 23-29: Draft evasion, military exemption, U.S. armed forces service, deployment, discharge, desertion",
                ["P12_Line23", "P12_Line24", "P12_Line25", "P12_Line26a", "P12_Line26b", "P12_Line26c", "P11_Line26d",
                 "P12_Line27", "P12_Line28", "P9_Line29"],
                ["P12_Line23", "P12_Line24", "P12_Line25"],
                notes={
                    "P12_Line23": PART9_DEFAULT_NO + " Applies to 23-24, and to 27-29 when 25 is 'Yes'.",
                    "P12_Line25": "A fact. With 'No', leave 26.a-29 blank (the form says go to 30.a).",
                    "P12_Line26a": "26.a only with 25 'Yes'; 26.b and 26.c only with 26.a 'Yes'.",
                    "P11_Line26d": "Item 26.d (former service member residing outside the U.S.), only with 26.a "
                    "'No'. Its tooltip wrongly asks whether you are stationed overseas.",
                },
                choices=yn("P12_Line23", "P12_Line24", "P12_Line25", "P12_Line26a", "P12_Line26b", "P12_Line26c",
                           "P11_Line26d", "P12_Line27", "P12_Line28", "P9_Line29"),
            ),
            "part9_titles_of_nobility": q(
                "Part 9, Items 30.a-30.b: Hereditary title or order of nobility; willing to give it up",
                ["P12_Line30a", "P12_Line30b", "P9_NobilityTitles"],
                ["P12_Line30a"],
                notes={
                    "P12_Line30a": "A fact; 'No' unless the record shows a title.",
                    "P12_Line30b": "Only with 30.a 'Yes'.",
                    "P9_NobilityTitles": "The '(list titles)' blank in 30.b, only with 30.a 'Yes'. Its tooltip "
                    "wrongly says applicant's daytime telephone.",
                },
                choices=yn("P12_Line30a", "P12_Line30b"),
            ),
            "part9_oath_and_constitution": q(
                "Part 9, Items 31-37: Support the Constitution, understand and take the Oath, bear arms, noncombatant and civilian service",
                ["P12_Line31", "P12_Line32", "P12_Line33", "P12_Line34", "P12_Line35", "P12_Line36", "P12_Line37"],
                ["P12_Line31", "P12_Line32", "P12_Line33"],
                notes={
                    "P12_Line31": "Not a default-'No' block: the expected answers are 'Yes' to 31, 32 and 34-37 and "
                    "'No' to 33. Any other answer is an attorney_decision. The 'Yes' box's tooltip says 'Select No'.",
                    "P12_Line33": "Unable to take the Oath because of a disability. With 'Yes', leave 34-37 blank.",
                },
                choices=yn("P12_Line31", "P12_Line32", "P12_Line33", "P12_Line34", "P12_Line35", "P12_Line36",
                           "P12_Line37"),
            ),
            # ------------------------------------------------------------------ Part 10
            "fee_reduction_request": q(
                "Part 10, Item 1: Household income at or below 400% of the Federal Poverty Guidelines (fee reduction)",
                ["P10_Line1_Citizen"],
                ["P10_Line1_Citizen"],
                notes={
                    "P10_Line1_Citizen": "Despite the name (and a tooltip about the spouse's address), this is Part 10 "
                    "item 1 on page 11. 'No' unless the attorney has decided to request the reduced fee.",
                },
                choices=yn("P10_Line1_Citizen"),
            ),
            "fee_reduction_household": q(
                "Part 10, Items 2-5.b: Household income, size, earners, head of household",
                ["P10_Line2_TotalHouseholdIn", "P10_Line3_HouseHoldSize", "P11_Line1_TotalChildren[1]", "P10_Line5a",
                 "P10_Line5b_NameOfHousehold"],
                ["P10_Line2_TotalHouseholdIn", "P10_Line3_HouseHoldSize", "P11_Line1_TotalChildren[1]", "P10_Line5a"],
                allowed=FILLED_OR_NA,
                notes={
                    "P10_Line2_TotalHouseholdIn": "Only with item 1 'Yes'. Whole dollars, digits only (maxlen 7, no "
                    "'$' or commas).",
                    "P10_Line3_HouseHoldSize": "Item 3 (maxlen 7).",
                    "P11_Line1_TotalChildren[1]": "Item 4, despite the name: household members earning income, "
                    "including the applicant. Index [0] is the Part 6 children count.",
                    "P10_Line5a": "Item 5.a: I am the head of household.",
                    "P10_Line5b_NameOfHousehold": "Item 5.b, only with 5.a 'No'.",
                },
                choices=yn("P10_Line5a"),
            ),
            # ------------------------------------------------------------------ Part 11
            "applicant_contact": q(
                "Part 11, Items 1-3: Applicant's daytime phone, mobile phone, email",
                ["P12_Line3_Telephone", "P12_Line3_Mobile", "P12_Line5_Email"],
                ["P12_Line3_Telephone"],
                notes={
                    "P12_Line3_Telephone": PHONE,
                    "P12_Line3_Mobile": PHONE,
                    "P12_Line5_Email": "maxlen 38.",
                },
            ),
            "applicant_signature": q(
                "Part 11, Item 4: Applicant's signature and date",
                ["P12_SignatureApplicant[0]", "P13_DateofSignature"],
                allowed=SIGNATURE_STATUSES,
                notes={
                    "P12_SignatureApplicant[0]": "Signed by hand in ink; leave blank (pending_signature). Index [0] is "
                    "the applicant; [1] is the interpreter and [2] the preparer.",
                },
            ),
            # ------------------------------------------------------------------ Part 12
            "interpreter_block": q(
                "Part 12, Items 1-5: Interpreter's name, organization, contact details, language",
                ["P14_Line1_nterpreterFamilyName", "P14_Line1_nterpreterGivenName", "P14_Line2_NameofBusinessorOrgName",
                 "P14_Line4_Telephone", "P14_Line5_Mobile", "P14_Line5_EmailAddress", "P14_NameOfLanguage"],
                ["P14_Line1_nterpreterFamilyName", "P14_Line1_nterpreterGivenName", "P14_Line4_Telephone",
                 "P14_NameOfLanguage"],
                allowed=FILLED_OR_NA,
                notes={
                    "P14_Line1_nterpreterFamilyName": "Only if an interpreter read the form to the applicant; "
                    "otherwise not_applicable. Note the 'nterpreter' spelling.",
                    "P14_Line4_Telephone": "Item 3, daytime phone. " + PHONE,
                    "P14_Line5_Mobile": "Item 4, mobile phone. " + PHONE,
                    "P14_Line5_EmailAddress": "Item 5, email.",
                    "P14_NameOfLanguage": "The language in the certification ('fluent in English and ___').",
                },
            ),
            "interpreter_signature": q(
                "Part 12, Item 6: Interpreter's signature and date",
                ["P12_SignatureApplicant[1]", "P14_DateofSignature"],
                allowed=[PENDING_SIGNATURE, FILLED, NOT_APPLICABLE],
                notes={
                    "P12_SignatureApplicant[1]": "The interpreter's signature box, despite the name.",
                },
            ),
            # ------------------------------------------------------------------ Part 13
            "preparer_block": q(
                "Part 13, Items 1-5: Preparer's name, business, contact details",
                ["P15_Line1_PreparerFamilyName", "P15_Line1_PreparerGivenName", "P15_Line2_NameofBusinessorOrgName",
                 "P15_Line4_Telephone", "P15_Line5_Mobile", "P15_Line6_Email"],
                ["P15_Line1_PreparerFamilyName", "P15_Line1_PreparerGivenName", "P15_Line4_Telephone"],
                allowed=FILLED_OR_NA,
                notes={
                    "P15_Line1_PreparerFamilyName": "The attorney or preparer, from the attorney profile. This "
                    "edition has no bar number or G-28 box.",
                    "P15_Line4_Telephone": "Item 3, daytime phone. " + PHONE,
                    "P15_Line5_Mobile": "Item 4, mobile phone. " + PHONE,
                    "P15_Line6_Email": "Item 5, email (maxlen 38).",
                },
            ),
            "preparer_signature": q(
                "Part 13, Item 6: Preparer's signature and date",
                ["P12_SignatureApplicant[2]", "P15_DateofSignature"],
                allowed=[PENDING_SIGNATURE, FILLED, NOT_APPLICABLE],
                notes={
                    "P12_SignatureApplicant[2]": "The preparer's signature box, despite the name.",
                },
            ),
            # ------------------------------------------------------------------ Part 14
            "additional_information": q(
                "Part 14, Items 2-5: Additional information (page, part, item, text)",
                [
                    f"P11_Line{n}{suffix}" for n in (3, 4, 5, 6) for suffix in ("A", "B", "C", "D")
                ],
                ["P11_Line3A", "P11_Line3B", "P11_Line3C", "P11_Line3D"],
                allowed=FILLED_OR_NA,
                notes={
                    "P11_Line3A": "Item 2's page number (maxlen 2). The names run one ahead of the items: P11_Line3* "
                    "is item 2, P11_Line4* item 3, P11_Line5* item 4, P11_Line6* item 5. P11_Line3A/B/C are "
                    "unbound in the XFA layer (see notes).",
                    "P11_Line3B": "Part number, e.g. '9' (maxlen 6).",
                    "P11_Line3C": "Item number, e.g. '15.b' (maxlen 6).",
                    "P11_Line3D": "The explanation: a multi-line box. Item 1 (name) and the A-Number repeat "
                    "automatically. More than four entries need a continuation sheet signed and dated by the "
                    "applicant.",
                },
            ),
            # ------------------------------------------------------------------ Parts 15-16
            "interview_and_oath_signatures": q(
                "Parts 15-16: Signature at interview and Oath of Allegiance (completed at the interview)",
                ["Part15USCISName", "Part15DateofSignature[0]", "Part15ApplicantsSignature", "Part15USCISSignature",
                 "ApplicantsSignature", "Part15DateofSignature[1]"],
                allowed=[NOT_APPLICABLE],
                notes={
                    "ApplicantsSignature": "Part 16 (Oath) signature; Part15DateofSignature[1] is its date. Leave "
                    "every box in Parts 15-16 blank.",
                },
            ),
        },
    },
}

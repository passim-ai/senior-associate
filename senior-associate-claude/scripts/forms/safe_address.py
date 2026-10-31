"""The safe mailing address of a protected client (8 U.S.C. 1367), box by box on each form.

In a matter the attorney or the document review marked protected (VAWA, T or U; the matter's
settings, `scripts.matter_state.read_meta(matter)["protected"]`), every mailing-address box of
the protected client, on every form, holds the safe mailing address: the attorney's office from
the profile's `mailing_address`, in care of the firm (or the attorney), unless the attorney gave
another for this client. The matter contract's "VAWA and other protected cases" says where each
form puts it; MAILING_GROUPS below are those boxes.

The safe address the audit compares with is the plan's own record, `safe_mailing_address`:

    {"in_care_of": "Example Law PLLC", "street": "100 Example Street", "unit": "STE", "number": "200",
     "city": "Springfield", "state": "IL", "zip": "62701", "country": "USA",
     "source": "profile" | "attorney"}

and, when the plan has none, the profile's `mailing_address` text (each filled box must appear in
it). The forms of the petitioner or sponsor (I-130, I-130A, I-864) carry no mailing address of
the protected client and are not checked.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

SAFE_KEYS = ("in_care_of", "street", "unit", "number", "city", "state", "zip", "province", "postal", "country")


@dataclass(frozen=True)
class AddressBoxes:
    question: str  # the plan question that holds these boxes
    label: str  # where the form asks for it, for the finding
    street: str
    city: str
    in_care_of: str = ""
    unit: str = ""
    number: str = ""
    state: str = ""
    zip: str = ""
    province: str = ""
    postal: str = ""
    country: str = ""

    def boxes(self) -> dict[str, str]:
        return {key: getattr(self, key) for key in SAFE_KEYS if getattr(self, key)}


@dataclass(frozen=True)
class MailingGroup:
    mailing: AddressBoxes
    # A form that asks whether the mailing address is the physical address: (box, the answer that
    # means "the same", the physical address boxes). With that answer the physical address is the
    # mailing address, so it is the one that must be the safe address.
    same_as_physical: tuple[str, str, AddressBoxes] | None = None


MAILING_GROUPS: dict[str, list[MailingGroup]] = {
    "g-28": [
        MailingGroup(
            AddressBoxes(
                "client_mailing_address", "Part 3, items 13.a-13.h", street="Line12a_StreetNumberName",
                unit="Line12b_Unit", number="Line12b_AptSteFlrNumber", city="Line12c_CityOrTown",
                state="Line12d_State", zip="Line12e_ZipCode", province="Line12f_Province",
                postal="Line12g_PostalCode", country="Line12h_Country",
            )
        )
    ],
    "i-485": [
        MailingGroup(
            AddressBoxes(
                "mailing_address", "Part 1, item 18 (mailing address)", in_care_of="Pt1Line18_CurrentInCareOfName",
                street="Pt1Line18_CurrentStreetNumberName", unit="Pt1Line18_CurrentUnit",
                number="Pt1Line18_CurrentAptSteFlrNumber", city="Pt1Line18_CurrentCityOrTown",
                state="Pt1Line18_CurrentState", zip="Pt1Line18_CurrentZipCode",
            ),
            same_as_physical=(
                "Pt1Line18_YN",
                "Y",
                AddressBoxes(
                    "current_address", "Part 1, item 18 (physical address, given as the mailing address)",
                    in_care_of="Part1_Item18_InCareOfName", street="Pt1Line18_StreetNumberName",
                    unit="Pt1Line18US_Unit", number="Pt1Line18US_AptSteFlrNumber", city="Pt1Line18_CityOrTown",
                    state="Pt1Line18_State", zip="Pt1Line18_ZipCode",
                ),
            ),
        )
    ],
    "i-765": [
        MailingGroup(
            AddressBoxes(
                "mailing_address", "Part 2, items 5.a-5.f", in_care_of="Line4a_InCareofName",
                street="Line4b_StreetNumberName", unit="Pt2Line5_Unit", number="Pt2Line5_AptSteFlrNumber",
                city="Pt2Line5_CityOrTown", state="Pt2Line5_State", zip="Pt2Line5_ZipCode",
            )
        )
    ],
    "i-131": [
        MailingGroup(
            AddressBoxes(
                "mailing_address", "Part 2, item 3", in_care_of="Part2_Line3_InCareofName",
                street="Part2_Line3_StreetNumberName", unit="Part2_Line3_Unit", number="Part2_Line3_AptSteFlrNumber",
                city="Part2_Line3_CityTown", state="Part2_Line3_State", zip="Part2_Line3_ZipCode",
                province="Part2_Line3_Province", postal="Part2_Line3_PostalCode", country="Part2_Line3_Country",
            )
        )
    ],
    "i-360": [
        MailingGroup(
            AddressBoxes(
                "safe_mailing_address", "Part 1, item 7", in_care_of="Pt1Line7_InCareofName",
                street="Pt1Line7_StreetNumberName", unit="Pt1Line7_Unit", number="Pt1Line7_AptSteFlrNumber",
                city="Pt1Line7_CityOrTown", state="Pt1Line7_State", zip="Pt1Line7_ZipCode",
                province="Pt1Line7_Province", postal="Pt1Line7_PostalCode", country="Pt1Line7_Country",
            )
        ),
        MailingGroup(
            AddressBoxes(
                "self_petitioner_mailing_address", "Part 3, item 2", in_care_of="Pt3Line2_InCareofName",
                street="Pt3Line2_StreetNumberName", unit="Pt3Line2_Unit", number="Pt3Line2_AptSteFlrNumber",
                city="Pt3Line2_CityOrTown", state="Pt3Line2_State", zip="Pt3Line2_ZipCode",
                province="Pt3Line2_Province", postal="Pt3Line2_PostalCode", country="Pt3Line2_Country",
            )
        ),
    ],
    "i-751": [
        MailingGroup(
            AddressBoxes(
                "mailing_address", "Part 1, item 15", in_care_of="Line17a_InCareofName",
                street="Line17b_Street_Number_Name", unit="Line17c_Unit", number="Line17c_Apt_Ste_Flr_Number",
                city="Line17d_City_Town", state="Pt1Line15e_State", zip="Pt1Line15f_ZipCode",
            )
        )
    ],
    "n-400": [
        MailingGroup(
            AddressBoxes(
                "mailing_address", "Part 4, item 3", in_care_of="P5_Line1b_InCareOfName",
                street="P5_Line1b_StreetName", unit="P5_Line1b_Unit", number="P5_Line1b_Number",
                city="P5_Line1b_City", state="P4_Line1_State[1]", zip="P5_Line1b_ZipCode",
                province="P5_Line1b_Province", postal="P5_Line1b_PostalCode", country="P5_Line1b_Country",
            ),
            same_as_physical=(
                "Pt3_Line2a_Checkbox",
                "Y",
                AddressBoxes(
                    "current_physical_address", "Part 4, item 1 (physical address, given as the mailing address)",
                    in_care_of="P4_Line1_InCareOfName", street="P4_Line1_StreetName", unit="P4_Line1_Unit",
                    number="P4_Line1_Number", city="P4_Line1_City", state="P4_Line1_State[0]",
                    zip="P4_Line1_ZipCode", province="P4_Line1_Province", postal="P4_Line1_PostalCode",
                    country="P4_Line1_Country",
                ),
            ),
        )
    ],
}

_ABBREVIATIONS = {
    "street": "st", "avenue": "ave", "road": "rd", "boulevard": "blvd", "drive": "dr", "lane": "ln",
    "court": "ct", "place": "pl", "suite": "ste", "floor": "flr", "fl": "flr", "apartment": "apt",
    "north": "n", "south": "s", "east": "e", "west": "w", "highway": "hwy", "parkway": "pkwy",
    "number": "no",
}
_US = {"united states", "united states of america", "usa", "us", "u s", "u s a"}


def normalize(text: object) -> str:
    """Lower case, no punctuation, one space, common street words abbreviated: "100 Example
    Street, Suite 200" and "100 Example St Ste 200" compare equal."""
    words = re.sub(r"[^0-9a-z]+", " ", str(text or "").casefold()).split()
    joined = " ".join(words)
    if joined in _US:
        return "us"
    return " ".join(_ABBREVIATIONS.get(word, word) for word in words)


def mismatches(
    boxes: AddressBoxes,
    values: dict[str, str],
    safe: dict[str, Any] | None,
    profile_address: str,
) -> list[dict[str, str]]:
    """The boxes of this address that don't hold the safe address (empty when they all do).

    Against the plan's record each box is compared with its part of the address; against the
    profile's free-text address, each filled box must appear in it.
    """
    wrong: list[dict[str, str]] = []
    profile_text = f" {normalize(profile_address)} "
    for part, field in boxes.boxes().items():
        stored = str(values.get(field, "")).strip()
        if safe:
            expected = str(safe.get(part, "") or "").strip()
            if part == "country" and not expected and normalize(stored) == "us":
                continue  # a U.S. safe address recorded without its country
            if normalize(stored) != normalize(expected):
                wrong.append({"field": field, "part": part, "stored": stored, "safe": expected})
        elif stored and part not in ("country", "in_care_of", "unit"):
            if f" {normalize(stored)} " not in profile_text:
                wrong.append({"field": field, "part": part, "stored": stored, "safe": profile_address})
    return wrong

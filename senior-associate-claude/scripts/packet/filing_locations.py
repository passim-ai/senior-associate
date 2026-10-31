#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Whether a paper filing goes to the "Attn: 1367" lockbox, from its lead form and its basis.

    uv run --script filing_locations.py --form I-485 --basis vawa [--json]

Since Oct. 7, 2026, certain forms filed in connection with VAWA, T nonimmigrant status or U
nonimmigrant status go to the "Attn: 1367" lockbox for the state where the client lives,
listed at https://www.uscis.gov/Certain-VAWA-T-U-Filing-Locations. Which filings go there is
each form's own address page's call, by form and basis. It is not the same as a matter being
protected under 8 U.S.C. 1367: an I-751 with a battery or extreme cruelty waiver is protected,
but the I-751's address page sends every I-751 to its own lockbox by state.

The lead form is the one whose address page decides where the package goes: the I-360 for a
VAWA self-petition (with any I-485, I-765 and I-131 filed with it), the I-485 for an adjustment
and the forms filed with it, the I-751, or a form filed on its own. The answer is
"1367 lockbox", "form page" (the form's own address page, not the 1367 lockbox), or None when
these tools haven't checked that form's page: check it by hand. Every route below was read on
the page named beside it; re-check the pages when a run depends on them.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _packet_common import ToolError, run_cli  # noqa: E402

LOCKBOX_PAGE = "https://www.uscis.gov/Certain-VAWA-T-U-Filing-Locations"
CHECKED = "2026-10-29"
LOCKBOX = "1367 lockbox"
FORM_PAGE = "form page"
ONLINE = "online"

VAWA = "vawa"  # a VAWA self-petition (I-360 abused spouse, child or parent), or a filing based on one
T = "t"  # T nonimmigrant status
U = "u"  # U nonimmigrant status
CAA_ABUSED = "cuban_adjustment_abused"  # abused spouse or child under the Cuban Adjustment Act
HRIFA_BATTERED = "hrifa_battered"  # battered spouse or child applying under HRIFA
ABUSE_WAIVER = "abuse_waiver"  # the I-751's battery or extreme cruelty waiver
OTHER = "other"  # any other basis
BASES = (VAWA, T, U, CAA_ABUSED, HRIFA_BATTERED, ABUSE_WAIVER, OTHER)
_ALIASES = {
    "vawa": VAWA, "vawa_self_petition": VAWA, "self_petition": VAWA, "battered_spouse": VAWA,
    "abused_spouse": VAWA, "t": T, "t_nonimmigrant": T, "u": U, "u_nonimmigrant": U,
    "caa_abused": CAA_ABUSED, "cuban_adjustment_abused": CAA_ABUSED, "hrifa_battered": HRIFA_BATTERED,
    "abuse_waiver": ABUSE_WAIVER, "battery_or_extreme_cruelty": ABUSE_WAIVER,
    "battery_or_extreme_cruelty_waiver": ABUSE_WAIVER, "other": OTHER, "none": OTHER,
}

# form -> (bases its address page sends to the 1367 lockbox, the page, its "updated" date, what it says).
# Any other basis for a form listed here goes to the form's own address page (FORM_PAGE).
ROUTES: dict[str, tuple[frozenset[str], str, str, str]] = {
    "I-360": (
        frozenset({VAWA}),
        "https://www.uscis.gov/i-360-addresses", "10/07/2026",
        "A self-petitioning abused spouse, child or parent (of a U.S. citizen or permanent resident) files at the "
        "VAWA, T and U filing page, with any concurrent I-485; every other I-360 category uses the lockbox charts.",
    ),
    "I-485": (
        frozenset({VAWA, T, U, CAA_ABUSED, HRIFA_BATTERED}),
        "https://www.uscis.gov/i-485-addresses", "10/07/2026",
        "A VAWA self-petitioner (an accepted, approved or concurrent I-360 as an abused spouse, child or parent), a T or "
        "U nonimmigrant, an abused spouse or child under the Cuban Adjustment Act, and a battered spouse or child under "
        "HRIFA file at the VAWA, T and U filing page.",
    ),
    "I-765": (
        frozenset({VAWA, T, U, CAA_ABUSED}),
        "https://www.uscis.gov/i-765-addresses", "10/07/2026",
        "(c)(9) with an I-485 based on an I-360 as a battered spouse, child or parent, T or U status, or the Cuban "
        "Adjustment Act's abused spouse or child; (c)(14) U or VAWA deferred action; (a)(16) filed separately from the "
        "I-914; (a)(19); (a)(20); (c)(25); (c)(31); (c)(40). An I-765 that depends on an I-485 is filed with it, at the "
        "I-485's location; an (a)(16) filed with the I-914 follows the I-914's page.",
    ),
    "I-131": (
        frozenset({VAWA, T, U}),
        "https://www.uscis.gov/i-131-addresses", "10/07/2026",
        "Item 5.A with or based on a pending I-485 as an abused spouse, child or parent, or a T- or U-based I-485; "
        "item 5.F (approved I-914) and item 5.G (approved I-918). Other I-131s filed with an I-485 go with the I-485.",
    ),
    **{
        form: (
            frozenset({VAWA, T, U}),
            LOCKBOX_PAGE, "10/07/2026",
            f"The VAWA, T and U filing page lists the {form} when it is filed in connection with VAWA, T nonimmigrant "
            "status or U nonimmigrant status.",
        )
        for form in ("I-102", "I-192", "I-212", "I-290B", "I-539", "I-824")
    },
    "I-601": (
        frozenset({VAWA, T, U}),
        "https://www.uscis.gov/i-601-addresses", "10/07/2026",
        "An approved VAWA self-petitioner seeking an immigrant visa and a T nonimmigrant filing with or based on a "
        "pending I-485 file at the VAWA, T and U filing page, which also lists the I-601 filed in connection with U "
        "status. Otherwise: filed with an I-485, follow the I-485 instructions; with a pending I-485, the Chicago "
        "\"Attn: AOS\" lockbox for an MSC or IOE receipt (or none) and the Dallas \"Attn: NFB\" lockbox for EAC, LIN, "
        "SRC or WAC; after a consular officer's finding abroad (immigrant, K or V visa), the Phoenix \"Attn: I-601 "
        "Foreign Filers\" lockbox; with a TPS I-821, the Federal Register notice; in removal proceedings, the "
        "immigration court.",
    ),
}
# Forms whose address page was read and sends every basis to its own lockbox.
OWN_PAGE_ONLY: dict[str, tuple[str, str, str]] = {
    "I-751": (
        "https://www.uscis.gov/i-751-direct-filing-addresses", "09/24/2024",
        "Every I-751, a battery or extreme cruelty waiver included, goes to the Elgin or Phoenix \"Attn: I-751\" "
        "lockbox for the petitioner's state; the page has no VAWA, T or U route.",
    ),
    "I-140": (
        "https://www.uscis.gov/i-140-addresses", "10/23/2026",
        "The lockbox depends on what goes with the I-140 and the state where the beneficiary will work: filed alone, "
        "the Dallas or Chicago \"Attn: I-140\" lockbox; with an I-485, the Dallas \"Attn: NFB\" lockbox; with an "
        "I-907 (with or without an I-485), the Elgin or Phoenix \"Attn: Premium I-140\" lockbox. A standalone I-907 "
        "to upgrade a pending I-140 goes to the Chicago or Dallas \"Attn: I-907\" lockbox (changed Oct. 7, 2026). The "
        "page has no VAWA, T or U route.",
    ),
    "I-601A": (
        "https://www.uscis.gov/i-601a", "06/01/2026",
        "Every I-601A goes to the Chicago \"Attn: I-601A\" lockbox (P.O. Box 4599); the page has no VAWA, T or U "
        "route, and the I-601A is filed alone, never with another form.",
    ),
}


def normalize_form(text: str) -> str:
    match = re.search(r"\b([GIN])[-\s]?(\d{2,4}[A-Z]?)\b", str(text or "").upper())
    return f"{match.group(1)}-{match.group(2)}" if match else ""


def normalize_basis(text: str) -> str:
    key = re.sub(r"[\s\-/]+", "_", str(text or "").strip().lower()).strip("_")
    return _ALIASES.get(key, "")


def normalize_location(text: str) -> str:
    """What a letter's `filing_location` names: the 1367 lockbox, the form's own page, or online."""
    value = " ".join(str(text or "").split())
    if not value:
        return ""
    if re.search(r"1367|Certain-VAWA-T-U", value, re.IGNORECASE):
        return LOCKBOX
    if value.lower() == ONLINE:
        return ONLINE
    return FORM_PAGE


def route(form: str, basis: str) -> dict:
    """{form, basis, location (LOCKBOX, FORM_PAGE or None), page, updated, rule, lockbox_page, checked}."""
    lead, why = normalize_form(form), normalize_basis(basis)
    result = {"form": lead, "basis": why, "location": None, "page": "", "updated": "", "rule": "",
              "lockbox_page": LOCKBOX_PAGE, "checked": CHECKED}
    if not lead or not why:
        result["rule"] = "Give the lead form (for example I-485) and a basis: " + ", ".join(BASES) + "."
        return result
    if lead in OWN_PAGE_ONLY:
        page, updated, rule = OWN_PAGE_ONLY[lead]
        result.update(location=FORM_PAGE, page=page, updated=updated, rule=rule)
    elif lead in ROUTES:
        bases, page, updated, rule = ROUTES[lead]
        if why == ABUSE_WAIVER:
            result["rule"] = "The battery or extreme cruelty waiver basis belongs to the I-751."
            return result
        result.update(location=LOCKBOX if why in bases else (FORM_PAGE if why == OTHER else None),
                      page=page, updated=updated, rule=rule)
        if result["location"] is None:
            result["rule"] = f"{rule} The tools haven't checked a {why} {lead} on that page: check it by hand."
    else:
        result["rule"] = (f"These tools haven't checked the {lead}'s address page: read it, and the VAWA, T and U "
                          "filing page, for this basis, and record what they say and the date.")
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Whether a paper filing goes to the Attn: 1367 lockbox.")
    ap.add_argument("--form", help="The lead form, for example I-360, I-485, I-751.")
    ap.add_argument("--basis", help="The basis it's filed on: " + ", ".join(BASES) + ".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if not args.form or not args.basis:
        raise ToolError("Give --form and --basis.")
    result = route(args.form, args.basis)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    where = {LOCKBOX: f"the \"Attn: 1367\" lockbox for the client's state ({LOCKBOX_PAGE})",
             FORM_PAGE: f"the form's own address page ({result['page']}), not the 1367 lockbox",
             None: "not checked by these tools"}[result["location"]]
    print(f"{result['form'] or args.form}, {result['basis'] or args.basis}: {where}.")
    print(result["rule"])
    if result["updated"]:
        print(f"Page updated {result['updated']}; checked {CHECKED}. Re-check it before filing.")
    return 0 if result["location"] else 1


if __name__ == "__main__":
    run_cli(main)

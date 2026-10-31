"""HHS poverty guidelines for the I-864 affidavit of support (USCIS Form I-864P).

The figures below are copied from https://www.uscis.gov/i-864p, "effective beginning Mar. 1, 2026"
(checked 2026-10-29; the page was last updated 2026-02-27). HHS publishes new guidelines each
year and USCIS updates the I-864P page soon after, usually in March: when EFFECTIVE is more than
a year old, the audit says the table may be out of date. To update, replace the three tables and
the dates from the current page.

The 125% column applies to every sponsor except one on active duty in the U.S. armed forces or
Coast Guard (not for training) who petitions for a spouse or child, who needs 100%. The I-864
doesn't say whom the petition is for, so the audit takes that from the package's I-130. A sponsor domiciled in Alaska
or Hawaii uses that state's table; everyone else (the 48 contiguous states, the District of
Columbia, Puerto Rico, the U.S. Virgin Islands, Guam and the Northern Mariana Islands, or a
sponsor abroad) uses the first.
"""
from __future__ import annotations

from datetime import date

SOURCE = "https://www.uscis.gov/i-864p"
EFFECTIVE = date(2026, 3, 1)
CHECKED = date(2026, 10, 29)

# region -> {"100": (households of 2..8), "125": (...), "add_100": per extra person, "add_125": ...}
TABLES: dict[str, dict[str, object]] = {
    "contiguous": {
        "100": (21640, 27320, 33000, 38680, 44360, 50040, 55720),
        "125": (27050, 34150, 41250, 48350, 55450, 62550, 69650),
        "add_100": 5680,
        "add_125": 7100,
    },
    "AK": {
        "100": (27050, 34150, 41250, 48350, 55450, 62550, 69650),
        "125": (33813, 42688, 51563, 60438, 69313, 78188, 87063),
        "add_100": 7100,
        "add_125": 8875,
    },
    "HI": {
        "100": (24890, 31420, 37950, 44480, 51010, 57540, 64070),
        "125": (31113, 39275, 47438, 55600, 63763, 71925, 80088),
        "add_100": 6530,
        "add_125": 8163,
    },
}


def region_for(state: str) -> str:
    code = str(state or "").strip().upper()
    return code if code in ("AK", "HI") else "contiguous"


def minimum_income(household_size: int, *, state: str = "", percent: int = 125) -> int:
    """The least current household income that meets the I-864 requirement for this household."""
    if household_size < 2:
        household_size = 2  # the sponsor plus at least one sponsored immigrant
    table = TABLES[region_for(state)]
    column = tuple(table[str(percent)])  # type: ignore[arg-type]
    if household_size <= 8:
        return int(column[household_size - 2])
    return int(column[-1]) + (household_size - 8) * int(table[f"add_{percent}"])  # type: ignore[arg-type]


def is_stale(today: date | None = None) -> bool:
    """True when the table is more than a year old, so a newer I-864P has probably been published."""
    today = today or date.today()
    return (today - EFFECTIVE).days > 366

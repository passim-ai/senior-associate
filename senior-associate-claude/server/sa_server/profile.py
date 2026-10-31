"""Your details: the attorney's name, firm and bar number for the G-28, each form's preparer section and the letter."""
from __future__ import annotations

import json
import os
from typing import Any

from .common import read_json
from .context import Context

PROFILE_KEYS = ("attorney_name", "firm_name", "mailing_address", "phone", "email", "bar_number", "licensing_authority", "uscis_online_account_number",
                "has_uscis_online_account", "subject_to_discipline_order", "discipline_order_details")
# What the G-28 and the letter's signature can't do without. The firm name is optional: a solo attorney may have none.
PROFILE_NEEDED = {
    "attorney_name": "your name",
    "mailing_address": "mailing address",
    "phone": "phone",
    "email": "email",
    "bar_number": "bar number",
    "licensing_authority": "licensing authority",
    "subject_to_discipline_order": "the G-28 discipline question",
}
# The G-28 Part 2 item 1.c answer is "no" or "yes"; with "yes", the details go in the G-28's Part 6.
DISCIPLINE_ANSWERS = {"no", "yes"}
# "no": the attorney has no USCIS online account, so every question about one is not applicable (CONTRACTS §12).
ACCOUNT_ANSWERS = {"no", "yes"}
PROFILE_LIMITS = {"discipline_order_details": 2000}


def load_profile(ctx: Context) -> dict[str, str]:
    data = read_json(ctx.profile_path)
    if not isinstance(data, dict):
        return {}
    return {k: str(data[k]).strip() for k in PROFILE_KEYS if isinstance(data.get(k), str) and data[k].strip()}


def save_profile(ctx: Context, profile: dict[str, Any]) -> dict[str, str]:
    clean = {
        k: str(profile[k]).strip()[: PROFILE_LIMITS.get(k, 300)]
        for k in PROFILE_KEYS
        if isinstance(profile.get(k), str) and str(profile[k]).strip()
    }
    if clean.get("subject_to_discipline_order") not in DISCIPLINE_ANSWERS:
        clean.pop("subject_to_discipline_order", None)
    if clean.get("subject_to_discipline_order") != "yes":
        clean.pop("discipline_order_details", None)
    if clean.get("has_uscis_online_account") not in ACCOUNT_ANSWERS:
        clean.pop("has_uscis_online_account", None)
    # The number the attorney typed is kept as typed: "no" makes it not applicable, and switching back finds it again.
    path = ctx.profile_path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return clean

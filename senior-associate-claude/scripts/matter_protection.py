#!/usr/bin/env python3
"""Whether a matter is protected under 8 U.S.C. 1367 (VAWA, T and U), for every runtime script that treats one
differently: the privacy lint, closeout, stage workspaces and the network gate.

The source of truth is the matter's settings, ``matter_state.read_meta(matter)["protected"]``: set by the app's
catalog when the matter is created, by the attorney, or by the document review when the record shows battery or
extreme cruelty, trafficking or a qualifying crime (``run_matter_workflow.py set-protected``). A matter started before
that flag existed still counts as protected when its recorded case type names a protected case.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.matter_access import WORKFLOW_RECORD_DIRS
from scripts.matter_state import read_meta

# A recorded case type that can only be a protected case. An I-360 alone isn't one (it also covers special
# immigrant juveniles and religious workers), nor an I-751 waiver (divorce and hardship waivers aren't); the
# document review marks those when the record shows abuse.
PROTECTED_CASE_TYPE = re.compile(
    r"\b(?:vawa|self[- ]?petition\w*|battered|extreme\s+cruelty|abuse|i-?914|i-?918|[tu][- ]visa|"
    r"[tu][- ]nonimmigrant|traffick\w*)\b",
    re.IGNORECASE,
)


def protected_case_type(matter_type: str | None) -> bool:
    return bool(matter_type and PROTECTED_CASE_TYPE.search(matter_type))


def recorded_case_types(matter: Path) -> list[str]:
    """The case types the matter's workflow records name, in every layout."""
    types: list[str] = []
    for relative in WORKFLOW_RECORD_DIRS:
        root = Path(matter) / relative
        if not root.is_dir():
            continue
        for path in sorted(root.glob("**/matter_status.json")):
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            matter_type = (state.get("matter") or {}).get("matter_type") if isinstance(state, dict) else None
            if isinstance(matter_type, str) and matter_type.strip():
                types.append(matter_type)
    return types


def protection(matter: Path, matter_type: str | None = None, meta: dict | None = None) -> dict[str, object]:
    """Whether the matter is protected, and why: the one rule every part of the plugin uses (the app's server for
    the matter's card, list, timeline and briefs; the runtime for the lint, closeout, workspaces and the gate).

    ``{"protected": True, "reason": <the setting's reason: catalog, attorney or docs_review>}`` when the matter's
    settings mark it; ``{"protected": True, "reason": "case_type"}`` when only its case type does (a matter from
    before the setting, or a case described in words that can only be protected); else ``{"protected": False,
    "reason": ""}``. ``matter_type`` is the case type of the record being read (by default, every recorded one);
    ``meta`` the settings already read, when the caller has them."""
    settings = read_meta(Path(matter)) if meta is None else meta
    if settings.get("protected"):
        return {"protected": True, "reason": str(settings.get("protected_reason") or "attorney")}
    types = [matter_type] if matter_type is not None else recorded_case_types(Path(matter))
    if any(protected_case_type(value) for value in types):
        return {"protected": True, "reason": "case_type"}
    return {"protected": False, "reason": ""}


def is_protected_matter(matter: Path, matter_type: str | None = None) -> bool:
    """True when the matter's settings mark it protected, or its case type can only be a protected case."""
    return bool(protection(matter, matter_type)["protected"])

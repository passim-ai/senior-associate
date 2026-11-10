"""The words a tool gate should keep out of research for one matter (CONTRACTS §13): the parties' names and the
client's identifiers.

They come from the runtime's ``scripts/privacy_terms.py`` (``matter_privacy_terms``), the same list the workflow's
privacy lint refuses on screen, so the gate and the lint block the same words; the server adds the client's name as
the matter's folder carries it, which covers the time before any fact table exists.

Returned only to the app, which checks Claude's research calls against them; never logged, never written anywhere.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from scripts.privacy_terms import matter_privacy_terms

from .catalog import MATTER_TYPES
from .readmodel import FORM_NUMBER_RE

MIN_LENGTH = 2
# Words that can't stand alone as a term without blocking ordinary legal questions.
TOO_COMMON = {"the", "and", "for", "with", "none", "unknown", "n/a", "yes", "no", "not", "applicable", "same", "mr", "mrs", "ms",
              "de", "del", "la", "los", "las", "van", "von", "bin", "packet", "client", "documents", "docs", "waiver",
              "petition", "joint", "matter", "new", "rfe", "noid", "response", "sample"}


def _from_folder_name(name: str) -> list[str]:
    """The client's name as the folder carries it ("Garcia I-130 I-485" → "Garcia"), without form numbers or the
    words a case type adds."""
    shorts = {w.casefold() for t in MATTER_TYPES for w in t["short"].split()}
    words = [w for w in re.split(r"[\s,()]+", FORM_NUMBER_RE.sub(" ", name)) if w]
    return [w for w in words if len(w) >= MIN_LENGTH and w.casefold() not in TOO_COMMON | shorts and not w.isdigit()]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        value = " ".join(str(value).split())
        if value and value.casefold() not in seen:
            seen.add(value.casefold())
            out.append(value)
    return out


def terms_payload(matter: Path) -> dict[str, Any]:
    """{terms, names, full_names, identifiers}: ``terms`` everything, longest first; ``names`` single words to match
    whole-word and without regard to case; ``identifiers`` to match with spaces and dashes removed, digits to digits."""
    from scripts.matter_state import read_meta
    found = matter_privacy_terms(matter)
    initial = read_meta(matter).get("client_name", "")
    if initial:
        initial = " ".join(FORM_NUMBER_RE.sub(" ", initial).split())
    names = _dedupe((_from_folder_name(initial) if initial else _from_folder_name(matter.name)) + list(found.get("names") or []))
    full_names = _dedupe(([initial] if initial else []) + list(found.get("full_names") or []))
    identifiers = _dedupe(list(found.get("identifiers") or []))
    terms = sorted(_dedupe(full_names + names + identifiers), key=lambda t: (-len(t), t.casefold()))
    return {"status": "privacy_terms", "terms": terms, "names": names, "full_names": full_names, "identifiers": identifiers}

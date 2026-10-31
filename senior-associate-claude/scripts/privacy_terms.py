#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The words that identify the people in a matter: their names and identifying numbers, from the forms fact table.

    uv run --script privacy_terms.py "<matter>" [--json]

The workflow's privacy lint refuses a stage summary or blocker that names a party, because the app shows those on
screen; the app's tool gate (the server's ``privacy_terms`` op) refuses research queries that carry them. Both read
``matter_privacy_terms`` here, so they block the same words. The terms are client data: print them only to the
caller, never into a log.

Sources, newest layout first: ``output/working/vault/forms/<slug>/form facts.json`` (and the older
``output/vault/forms/`` and ``output/forms/`` layouts), plus a ``parties`` list in the document review's
``document inventory.json`` when it has one, which covers the steps before the forms exist.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterator

FACT_TABLE_GLOBS = (
    "output/working/vault/forms/*/form facts.json",
    "output/vault/forms/*/form facts.json",
    "output/forms/*form facts.json",
)
INVENTORY_GLOBS = (
    "output/working/vault/docs-review/*/document inventory.json",
    "output/vault/docs-review/*/document inventory.json",
)

# A fact whose key or party has one of these words isn't a client's or relative's name ("employer_name").
NOT_A_PERSON_WORDS = frozenset(
    """
    attorney attorneys preparer interpreter firm organization organisation employer employers employment job jobs
    occupation workplace company business institution university college school hospital church agency bank court
    office city town county country state province street place file document form account user username filename
    program ship vessel airline
    """.split()
)
NAME_KEY = re.compile(r"name", re.IGNORECASE)


def not_a_person(*labels: str) -> bool:
    return any(
        segment in NOT_A_PERSON_WORDS
        for label in labels
        for segment in re.split(r"[^a-z0-9]+", label.casefold())
    )
IDENTIFIER_KEY = re.compile(
    r"a_?number|alien|uscis_?(?:account|number)|receipt|passport|i_?94|ssn|social_?security|"
    r"date_?of_?birth|birth_?date|dob|travel_?document|national_?id|driver",
    re.IGNORECASE,
)
# Name parts too common in ordinary writing to refuse on sight, and words a summary uses anyway.
COMMON_WORDS = frozenset(
    """
    the and for not none unknown same above below other new old none n/a
    petitioner beneficiary applicant sponsor attorney client spouse mother father child son daughter
    form forms part item exhibit letter packet review draft final cover
    january february march april may june july august september october november december
    monday tuesday wednesday thursday friday saturday sunday
    will may grace hope faith joy rose mark bill frank grant case bond price young king rich long little
    love page ward hall field lane park court street united states america
    mr mrs ms dr jr sr ii iii iv
    """.split()
)
MIN_NAME_LENGTH = 3
MIN_IDENTIFIER_LENGTH = 6


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def name_tokens(text: str) -> list[str]:
    """The distinctive words of a name: three letters or more, not a common word."""
    tokens: list[str] = []
    for token in re.findall(r"[^\W\d_]+(?:['’][^\W\d_]+)?", text):
        if len(token) >= MIN_NAME_LENGTH and token.casefold() not in COMMON_WORDS:
            tokens.append(token)
    return tokens


def _fact_rows(payload: Any) -> Iterator[tuple[str, str, Any]]:
    """(party, key, value) for each fact, across the shapes the forms tools have written."""
    facts = payload.get("facts") if isinstance(payload, dict) else payload
    if not isinstance(facts, list):
        return
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        party = str(fact.get("subject") or fact.get("party") or "")
        key = str(fact.get("key") or fact.get("field") or fact.get("name") or "")
        yield party, key, fact.get("value")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def matter_privacy_terms(matter: Path) -> dict[str, Any]:
    """{"names": [...], "full_names": [...], "identifiers": [...], "sources": [...]} for the matter's parties.

    ``names`` are single words to match whole-word and case-insensitively; ``full_names`` the names as written;
    ``identifiers`` numbers and dates as written (match them with separators removed too). Empty lists before the
    document review or the forms record anyone.
    """
    matter = Path(matter)
    names: dict[str, str] = {}
    full_names: dict[str, str] = {}
    identifiers: dict[str, str] = {}
    sources: list[str] = []

    def add_name(text: str) -> None:
        text = " ".join(text.split())
        if not text or len(text) > 120:
            return
        tokens = name_tokens(text)
        if not tokens:
            return
        full_names.setdefault(text.casefold(), text)
        for token in tokens:
            names.setdefault(token.casefold(), token)

    for pattern in FACT_TABLE_GLOBS:
        for path in sorted(matter.glob(pattern)):
            payload = _read_json(path)
            if payload is None:
                continue
            sources.append(path.relative_to(matter).as_posix())
            for party, key, value in _fact_rows(payload):
                if not_a_person(party, key):
                    continue
                if NAME_KEY.search(key):
                    for text in _strings(value):
                        add_name(text)
                elif IDENTIFIER_KEY.search(key):
                    for text in _strings(value):
                        text = text.strip()
                        compact = re.sub(r"[\s-]", "", text)
                        if len(compact) >= MIN_IDENTIFIER_LENGTH and re.search(r"\d", compact):
                            identifiers.setdefault(text.casefold(), text)

    for pattern in INVENTORY_GLOBS:
        for path in sorted(matter.glob(pattern)):
            payload = _read_json(path)
            parties = payload.get("parties") if isinstance(payload, dict) else None
            if not isinstance(parties, list):
                continue
            sources.append(path.relative_to(matter).as_posix())
            for party in parties:
                if isinstance(party, str):
                    add_name(party)
                elif isinstance(party, dict):
                    if not_a_person(str(party.get("role") or "")):
                        continue
                    for key in ("name", "legal_name", "other_names", "names"):
                        for text in _strings(party.get(key)):
                            add_name(text)

    return {
        "names": sorted(names.values(), key=str.casefold),
        "full_names": sorted(full_names.values(), key=str.casefold),
        "identifiers": sorted(identifiers.values()),
        "sources": sources,
    }


def find_terms(text: str, terms: dict[str, Any]) -> list[str]:
    """The kinds of party terms a text contains ("name", "identifier"), without repeating the terms themselves."""
    found: list[str] = []
    if not text:
        return found
    for token in terms.get("names") or []:
        # A whole word, and not the start of a contraction: "Don" isn't in "don't", but "Ann's" is Ann.
        pattern = rf"(?<![^\W\d_])(?<![^\W\d_]['’]){re.escape(token)}(?![^\W\d_])(?!['’](?:t|ve|re|ll|d|m)\b)"
        if re.search(pattern, text, re.IGNORECASE):
            found.append("name")
            break
    compact_text = re.sub(r"[\s-]", "", text).casefold()
    # Numbers are compared digits to digits, so "A 201-555-019" and "201555019" are the same A-number.
    joined_digits = re.sub(r"(?<=\d)[\s./-]+(?=\d)", "", text)
    for value in terms.get("identifiers") or []:
        compact = re.sub(r"[\s-]", "", value).casefold()
        digits = re.sub(r"\D", "", value)
        if (compact and compact in compact_text) or (
            len(digits) >= MIN_IDENTIFIER_LENGTH and re.search(rf"(?<!\d){digits}(?!\d)", joined_digits)
        ):
            found.append("identifier")
            break
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description="Print the names and identifiers of a matter's parties.")
    parser.add_argument("matter", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    matter = args.matter.expanduser().resolve()
    if not matter.is_dir():
        print(f"Matter folder not found: {matter}", file=sys.stderr)
        return 1
    terms = matter_privacy_terms(matter)
    if args.json:
        print(json.dumps(terms, indent=2, ensure_ascii=False))
    else:
        print(f"{len(terms['names'])} name word(s), {len(terms['identifiers'])} identifier(s) from {len(terms['sources'])} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

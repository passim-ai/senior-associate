#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""What the research behind the cover letter covered, in the words the app and the memo show.

Read from the researcher's own records: the support matrix (every authority the letter cites), the legal currency
review (what was checked for later treatment and for change, and when) and, when the researcher looked for them, the
unpublished decisions on similar facts. Nothing here judges the law. It counts what the records say was done, and it
says plainly when BIA Edge wasn't used, so the attorney sees what the letter's law rests on before filing.

    uv run --script scripts/research_summary.py "<matter>"          the lines for the memo's Sources checked
    uv run --script scripts/research_summary.py "<matter>" --json   the summary as the app reads it
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.matter_state import read_json

RESEARCH = Path("output/working/vault/research")
CURRENCY = Path("output/working/workflow/legal currency review.json")
MATRIX_NAME = "support matrix.json"
SIMILAR_NAME = "similar decisions.md"
LIBRARY = "BIA Edge"

# A reported decision, as the matrix writes one: a reporter cite, "Matter of", or a caption.
CASE = re.compile(r"I\s?&\s?N\s+Dec\.|\bF\.\s?(?:2d|3d|4th|Supp|App)|\bU\.S\.\s+\d|\bS\.\s?Ct\.|\bMatter of\b|\sv\.\s", re.I)
LIMITED = re.compile(r"\b(caution|negative|overruled|vacated|superseded|abrogated|reversed)\b", re.I)
UNCHECKED = re.compile(r"not checked|unchecked|couldn['’]t be checked|could not be checked", re.I)
STANDARD_SOURCE = re.compile(r"^authorities/", re.I)
# Why the letter was researched without the library, as the researcher records it on the receipt.
REASONS = {
    "no_access": "the Passim account had no research access",
    "not_connected": f"{LIBRARY} wasn’t connected",
    "refused": "the privacy check held the research back",
}
UPDATE_CHECKS = {"agency_policy", "regulations", "agency_decisions", "controlling_circuit"}
SHOWN = 4


def find_matrix(matter: Path) -> Path | None:
    """The letter's support matrix: the newest one under the research folder (the chat's notes keep none)."""
    root = matter / RESEARCH
    if not root.is_dir():
        return None
    found = [p for p in root.glob(f"*/{MATRIX_NAME}") if p.is_file() and not p.is_symlink()]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def long_date(day: date) -> str:
    return f"{day:%B} {day.day}, {day.year}"


def _n(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def _key(row: dict[str, Any]) -> str:
    return " ".join(str(row.get("citation") or row.get("authority") or "").split()).casefold()


def _is_case(row: dict[str, Any]) -> bool:
    return bool(row.get("document_id")) or bool(CASE.search(f"{row.get('authority') or ''} {row.get('citation') or ''}"))


def _short(text: Any, limit: int = 160) -> str:
    words = " ".join(str(text or "").split())
    return words if len(words) <= limit else words[: limit - 1].rsplit(" ", 1)[0] + "…"


def research_summary(matter: Path, today: date | None = None) -> dict[str, Any] | None:
    """The research as it stands, or None when the letter hasn't been researched (or its matrix can't be read)."""
    matrix_path = find_matrix(matter)
    if matrix_path is None:
        return None
    matrix = read_json(matrix_path).data
    propositions = matrix.get("propositions") if isinstance(matrix, dict) else None
    if not isinstance(propositions, list):
        return None
    today = today or date.today()

    authorities: dict[str, dict[str, Any]] = {}
    cases: dict[str, dict[str, Any]] = {}
    adverse: set[str] = set()
    researched = 0
    not_researched: list[str] = []
    for prop in propositions:
        if not isinstance(prop, dict):
            continue
        rows = [r for r in prop.get("support") or [] if isinstance(r, dict) and _key(r)]
        for row in rows:
            authorities[_key(row)] = row
            if _is_case(row):
                cases[_key(row)] = row
        for entry in prop.get("adverse") or []:
            name = _key(entry) if isinstance(entry, dict) else " ".join(str(entry).split()).casefold()
            if name:
                adverse.add(name)
        if str(prop.get("case_law") or "").strip().casefold() == "not researched":
            not_researched.append(_short(prop.get("proposition")))
        elif rows and not all(STANDARD_SOURCE.search(str(r.get("source") or "")) for r in rows):
            researched += 1
    if not authorities:
        return None

    limited = [str(r.get("authority") or r.get("citation")) for r in cases.values() if LIMITED.search(str(r.get("validity") or ""))]
    unchecked = [str(r.get("authority") or r.get("citation")) for r in cases.values() if UNCHECKED.search(str(r.get("validity") or ""))]

    receipt = read_json(matter / CURRENCY).data
    receipt = receipt if isinstance(receipt, dict) else {}
    checks = [c for c in receipt.get("checks") or [] if isinstance(c, dict)] if isinstance(receipt.get("checks"), list) else []
    connector = receipt.get("connector") if isinstance(receipt.get("connector"), dict) else {}
    treated = any(c.get("category") == "adverse_treatment" and c.get("status") == "checked" for c in checks)
    if connector.get("available") is False or (receipt and not treated):
        state = "without"
    elif treated:
        state = "checked"
    else:
        state = "unrecorded"
    reason = str(connector.get("reason") or "") if state == "without" else ""
    reason = reason if reason in REASONS else ""

    hits = [h for c in checks if c.get("category") in UPDATE_CHECKS and c.get("status") == "checked"
            for h in (c.get("hits") if isinstance(c.get("hits"), list) else []) if isinstance(h, dict)]
    applied = sum(1 for h in hits if h.get("disposition") == "applied")
    unresolved = [_short(u, 240) for u in receipt.get("unresolved") or [] if str(u).strip()] if isinstance(receipt.get("unresolved"), list) else []

    checked = _day(receipt.get("checked_at")) if state == "checked" else None
    # Without the library the authorities stand as verified on their own dates: the oldest is what the letter rests on.
    verified = min((d for d in (_day(r.get("checked")) for r in authorities.values()) if d), default=None)
    age = max(0, (today - checked).days) if checked else None

    similar_path = matrix_path.parent / SIMILAR_NAME
    similar = 0
    if similar_path.is_file():
        try:
            similar = sum(1 for line in similar_path.read_text(encoding="utf-8").splitlines() if line.startswith("### "))
        except (OSError, UnicodeDecodeError):
            similar = 0

    a, c = len(authorities), len(cases)
    cites = f"The letter cites {_n(a, 'authority', 'authorities')}" + (
        f", {'one' if c == 1 else c} of them {'a case' if c == 1 else 'cases'}" if c else ", none of them a case")
    lines: list[str] = []
    if state == "checked":
        headline = f"Checked {long_date(checked)} with {LIBRARY}" if checked else f"Checked with {LIBRARY}"
        lines.append(cites + ".")
        if c:
            done = c - len(unchecked)
            treatment = (f"Later treatment was checked for {'the case' if c == 1 else f'all {c} cases'}" if not unchecked
                         else f"Later treatment was checked for {done} of the {c} cases; {len(unchecked)} couldn’t be checked")
            clean = done - len(limited)
            if limited and clean > 0:
                treatment += (f": {_n(len(limited), 'carries', 'carry')} a limit that the research notes explain, and nothing "
                              f"adverse was found for the other {clean}.")
            elif limited:
                treatment += f": {_n(len(limited), 'carries', 'carry')} a limit that the research notes explain."
            else:
                treatment += ", and nothing adverse was found." if not unchecked else "; nothing adverse was found for the rest."
            lines.append(treatment)
        if researched:
            lines.append(f"{_n(researched, 'point was', 'points were')} researched for this client beyond the standard authorities"
                         + (f", and {_n(len(adverse), 'adverse authority was', 'adverse authorities were')} identified and answered." if adverse else "."))
        if hits:
            lines.append(f"{_n(len(hits), 'recent decision or policy update was', 'recent decisions and policy updates were')} reviewed; "
                         + ("none bears on the letter." if not applied
                            else f"{applied} {'was' if applied == 1 else 'were'} taken into account in the research."))
    elif state == "without":
        headline = f"Researched without {LIBRARY}"
        why = REASONS.get(reason)
        lines.append(f"When the letter was researched, {why}." if why else f"{LIBRARY} wasn’t used when the letter was researched.")
        rest = cites + (f", as last verified {long_date(verified)}." if verified else ".")
        lines.append(rest + " Nothing after that was checked: not the cases’ later treatment, and not new decisions or policy.")
        if not_researched:
            lines.append(f"{_n(len(not_researched), 'point', 'points')} specific to this client got no case-law research.")
    else:
        headline = "Researched; the check of the law wasn’t recorded"
        lines.append(cites + ". When they were last checked for later treatment and change wasn’t recorded.")
    if similar:
        lines.append(f"{_n(similar, 'unpublished decision', 'unpublished decisions')} on similar facts {'is' if similar == 1 else 'are'} "
                     "summarized in the memo. They are not precedent, and the letter doesn’t cite them.")

    return {
        "state": state,
        "reason": reason,
        "headline": headline,
        "lines": lines,
        # A clean check is what the library held on that date, never a guarantee.
        "caveat": ("A clean check means no adverse treatment was found in the library that day. It isn’t a guarantee that "
                   "a case is still good law.") if state == "checked" and c else "",
        "checked_at": checked.isoformat() if checked else "",
        "age_days": age,
        "verified_at": verified.isoformat() if verified else "",
        "authorities": a,
        "cases": c,
        "limited": limited[:SHOWN],
        "unchecked": unchecked[:SHOWN],
        "researched": researched,
        "adverse": len(adverse),
        "updates": len(hits),
        "applied": applied,
        "unresolved": unresolved[:SHOWN],
        "not_researched": not_researched[:SHOWN],
        "not_researched_count": len(not_researched),
        "similar": similar,
    }


def memo_lines(summary: dict[str, Any] | None) -> list[str]:
    """The same summary as the memo's Sources checked opens with."""
    if not summary:
        return ["Research: the cover letter hasn’t been researched yet."]
    out = [f"**Research: {summary['headline'][:1].lower()}{summary['headline'][1:]}.** " + " ".join(summary["lines"])]
    out += [f"- No case-law research: {text}" for text in summary["not_researched"]]
    out += [f"- Still open: {text}" for text in summary["unresolved"]]
    if summary["caveat"]:
        out.append(summary["caveat"])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize the research behind a matter's cover letter.")
    parser.add_argument("matter_root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.matter_root.is_dir():
        print(f"{args.matter_root} isn't a matter folder.", file=sys.stderr)
        return 1
    summary = research_summary(args.matter_root)
    print(json.dumps(summary, indent=2, ensure_ascii=False) if args.json else "\n".join(memo_lines(summary)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

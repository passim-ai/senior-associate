#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""What the research behind the cover letter covered, in the words the app and the memo show.

Read from the researcher's own records: the support matrix (the authorities behind each point of the letter), the legal currency
review (what was checked for later treatment and for change, and when) and, when the researcher looked for them, the
unpublished decisions on similar facts. Nothing here judges the law. It counts what the records say was done, and it
says plainly when BIA Edge wasn't used, so the attorney sees what the letter's law rests on before filing.

    uv run --script scripts/research_summary.py "<matter>"          the lines for the memo's Sources checked
    uv run --script scripts/research_summary.py "<matter>" --json   the summary as the app reads it
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
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
UNCHECKED = re.compile(r"not checked|unchecked|couldn['’]t be checked|could not be checked|incomplete|not reviewed|not completed", re.I)
# The row says, in so many words, that a review of later treatment found nothing against the case. Anything short
# of that (treatment history exists, coverage unknown, no validity at all) is not counted as a clean check.
CLEAN = re.compile(r"\b(?:none|no|nothing)\b[^.;:]{0,60}\b(?:adverse|negative)\b", re.I)
# The library's status word for a case, as the researcher copies it into the row, and the ones that flag it.
STATUS = re.compile(r"\bImmCite\s+([a-z_]+)", re.I)
# A review that says it left something over: "31 of 32 citing decisions reviewed", "one unreviewed" (unless the row
# goes on to say those were since read).
PART_REVIEWED = re.compile(r"\b(\d+)\s+of\s+(\d+)\b[^.;]{0,80}\b(?:reviewed|read|checked)\b", re.I)
LEFT_OVER = re.compile(r"\bunreviewed\b(?![^.;]*\bnow\s+(?:checked|reviewed|read)\b)", re.I)
FLAGGED = {"caution", "negative", "overruled", "vacated", "superseded"}
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


def _written(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
    except OSError:
        return ""


def long_date(day: date) -> str:
    return f"{day:%B} {day.day}, {day.year}"


def _n(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def _key(row: dict[str, Any]) -> str:
    return " ".join(str(row.get("citation") or row.get("authority") or "").split()).casefold()


def _is_case(row: dict[str, Any]) -> bool:
    return bool(row.get("document_id")) or bool(CASE.search(f"{row.get('authority') or ''} {row.get('citation') or ''}"))


def _incomplete(text: str) -> bool:
    """The row itself says the review of later treatment was not done, or not done in full."""
    if UNCHECKED.search(text) or LEFT_OVER.search(text):
        return True
    return any(int(done) < int(total) for done, total in PART_REVIEWED.findall(text))


def treatment_of(validity: Any) -> str:
    """How a case's row records its later treatment: limited, clean, or unknown (not checked, or not said).

    The row usually opens with the library's own status word ("ImmCite caution: ..."); that word decides when it is
    there. Otherwise the row's words do, and only an express statement that nothing adverse was found counts as clean.
    """
    text = str(validity or "")
    named = STATUS.search(text)
    status = named.group(1).casefold() if named else ""
    if status in FLAGGED:
        return "limited"
    if status.startswith("unchecked") or status == "not_applicable" or _incomplete(text):
        return "unknown"
    # "No negative treatment" is not a limit: read the limiting words in what is left once the clean phrase is out.
    if not status and LIMITED.search(CLEAN.sub(" ", text)):
        return "limited"
    return "clean" if CLEAN.search(text) else "unknown"


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
        if str(prop.get("recommendation") or "").strip().casefold() == "drop":
            # The research recommends taking the point out of the letter: its support isn't what the letter rests on.
            rows = []
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

    by_treatment: dict[str, list[str]] = {"limited": [], "clean": [], "unknown": []}
    for r in cases.values():
        by_treatment[treatment_of(r.get("validity"))].append(str(r.get("authority") or r.get("citation")))
    limited, unchecked = by_treatment["limited"], by_treatment["unknown"]

    receipt = read_json(matter / CURRENCY).data
    receipt = receipt if isinstance(receipt, dict) else {}
    checks = [c for c in receipt.get("checks") or [] if isinstance(c, dict)] if isinstance(receipt.get("checks"), list) else []
    connector = receipt.get("connector") if isinstance(receipt.get("connector"), dict) else {}
    treated = any(c.get("category") == "adverse_treatment" and c.get("status") == "checked" for c in checks)
    if connector.get("available") is False:
        state = "without"
    elif treated or connector.get("available") is True:
        # The library answered. Whether the check of later treatment was finished is said apart (`treated`).
        state = "checked"
    elif receipt:
        # A receipt from before the library's use was recorded, with no treatment check: researched without it.
        state = "without"
    else:
        state = "unrecorded"
    reason = str(connector.get("reason") or "") if state == "without" else ""
    reason = reason if reason in REASONS else ""

    hits = [h for c in checks if c.get("category") in UPDATE_CHECKS and c.get("status") == "checked"
            for h in (c.get("hits") if isinstance(c.get("hits"), list) else []) if isinstance(h, dict)]
    applied = sum(1 for h in hits if h.get("disposition") == "applied")
    covered = sum(1 for h in hits if h.get("disposition") == "already_covered")
    inapplicable = sum(1 for h in hits if h.get("disposition") == "not_applicable")
    undecided = len(hits) - applied - covered - inapplicable
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
    # The support the research gives the letter. (An authority the letter only answers is counted with the adverse ones.)
    cites = f"The research supports the letter with {_n(a, 'authority', 'authorities')}" + (
        f", {'one' if c == 1 else c} of them {'a case' if c == 1 else 'cases'}" if c else ", none of them a case")
    lines: list[str] = []
    if state == "checked":
        headline = f"Checked {long_date(checked)} with {LIBRARY}" if checked else f"Checked with {LIBRARY}"
        lines.append(cites + ".")
        if not treated:
            headline += "; the check of later treatment wasn’t finished"
            if c:
                lines.append("The check of the cases’ later treatment wasn’t finished.")
        elif c:
            unknown, clean = len(unchecked), len(by_treatment["clean"])
            done = c - unknown
            if done == 0:
                lines.append("The research records no completed check of later treatment for "
                             + ("the case." if c == 1 else f"any of the {c} cases."))
            else:
                treatment = (f"Later treatment was checked for {'the case' if c == 1 else f'all {c} cases'}" if not unknown
                             else f"Later treatment was checked for {done} of the {c} cases")
                if limited and clean:
                    treatment += (f": {_n(len(limited), 'carries', 'carry')} a limit that the research notes explain, and nothing "
                                  f"adverse was found for the other {clean}.")
                elif limited:
                    treatment += f": {_n(len(limited), 'carries', 'carry')} a limit that the research notes explain."
                else:
                    treatment += ", and nothing adverse was found."
                if unknown:
                    treatment += f" For the other {'one' if unknown == 1 else unknown}, the research records no completed check."
                lines.append(treatment)
        if researched:
            lines.append(f"{_n(researched, 'point was', 'points were')} researched for this client beyond the standard authorities"
                         + (f", and {_n(len(adverse), 'adverse authority was', 'adverse authorities were')} identified and answered." if adverse else "."))
        if hits:
            reviewed = f"{_n(len(hits), 'recent decision or policy update was', 'recent decisions and policy updates were')} reviewed"
            parts = []
            if applied:
                parts.append(f"{applied} {'was' if applied == 1 else 'were'} taken into account in the research")
            if covered:
                parts.append(f"{covered} {'was' if covered == 1 else 'were'} already covered by the research")
            if undecided:
                parts.append(f"{undecided} {'has' if undecided == 1 else 'have'} no decision recorded")
            if inapplicable and parts:
                parts.append(f"{inapplicable} {'doesn’t' if inapplicable == 1 else 'don’t'} apply to this letter")
            lines.append(f"{reviewed}: {'; '.join(parts)}." if parts else f"{reviewed}; none applies to this letter.")
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
                   "a case is still good law.") if state == "checked" and treated and c else "",
        # False when the library answered but the check of the cases' later treatment wasn't finished.
        "treatment_checked": treated if state == "checked" else False,
        "checked_at": checked.isoformat() if checked else "",
        # When the receipt file itself was last written: how a law check knows the receipt is its own work.
        "receipt_at": _written(matter / CURRENCY),
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

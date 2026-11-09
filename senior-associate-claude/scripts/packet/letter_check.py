#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "reportlab>=4.0",
# ]
# ///
"""Mechanical check of a cover letter before the independent review.

    uv run --script letter_check.py "<matter>" [--slug main] [--research-slug SLUG] [--json]
        [--letter MD] [--audit JSON] [--plan JSON] [--matrix JSON] [--facts JSON] [--notes MD] [--output JSON]

Three checks, each from files the writer and researcher already keep:

1. Authorities: every case, statute, regulation, Policy Manual chapter, policy memo and
   Federal Register cite in the letter is in the support matrix, or in an entry of the matter's
   chat research notes recorded as verified (matched at the level of the case's reporter cite,
   or the statute or regulation section, or the Policy Manual chapter).
2. Exhibits: the render audit is clean, and the exhibit plan lists the same exhibits in the
   same order and sections, each with a source, a placeholder and its open item, or a
   physical marker and its open item.
3. Facts: every sentence that states a date, an amount, a count or an identifier cites an
   exhibit (in the sentence or the one after it) or appears in the writer's fact table, and
   every age or duration ("29 years old", "for three years") is in the fact table.

Defaults (under <matter>/output/working/vault/): cover-letter/<slug>/cover letter.md,
cover letter audit.json, exhibit plan.json and letter facts.json, and
research/<research slug>/support matrix.json, and research/chat/research notes.md when it
exists. Writes cover-letter/<slug>/letter check.json; the letter is ready for review only when
its error_count is 0.

The chat research notes are the matter chat's record of authorities it verified, one entry per
proposition. The check reads, from each entry, only these lines:

    ## R2. <the proposition>
    - Authority: <the full cite: reporter cite, INA or 8 U.S.C. section, C.F.R. section, chapter>
    - Verified: <the date, 2026-10-29 or 10/29/2026 or Oct. 29, 2026> · <the validity result>

An entry counts as verified when its Verified line starts with a date and doesn't record
negative treatment (overruled, vacated, reversed, superseded, abrogated, negative). Its other
lines (Quote, URL, Applies, Adverse) are for the reader; an authority named only on an Adverse
line isn't covered.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _packet_common import ToolError, read_utf8, run_cli  # noqa: E402
import render_letter  # noqa: E402

VAULT = Path("output") / "working" / "vault"
CHAT_NOTES = Path("research") / "chat" / "research notes.md"  # under VAULT

# ---------------------------------------------------------------------------
# Authorities
# ---------------------------------------------------------------------------
_REPORTERS = r"(?:I\s?&\s?N\s?Dec\.|U\.\s?S\.|S\.\s?Ct\.|F\.\s?(?:2d|3d|4th)|F\.\s?Supp\.\s?(?:2d|3d)?|F\.\s?App'?x)"
# Each full cite, and its key: the level at which a cite is matched against the research (the case's first
# page, the section, the Policy Manual chapter).
_CITES = (
    (re.compile(r"\b(\d{1,4})\s+(" + _REPORTERS + r")\s+(\d{1,5})\b"),
     lambda m: f"case {m[1]} {m[2].replace(' ', '')} {m[3]}"),
    (re.compile(r"\bINA\s*(?:§§?|sections?|sec\.)?\s*(\d{3}[A-Z]?)\b", re.IGNORECASE), lambda m: f"INA {m[1].upper()}"),
    (re.compile(r"\b8\s*U\.\s?S\.\s?C\.\s*(?:§§?)?\s*(\d{4}[a-z]?)\b"), lambda m: f"8 USC {m[1]}"),
    (re.compile(r"\b(\d{1,2})\s*C\.\s?F\.\s?R\.\s*(?:§§?|parts?|pt\.)?\s*(\d{1,4}(?:\.\d{1,4})?)"),
     lambda m: f"{m[1]} CFR {m[2]}"),
    (re.compile(r"\b(\d{1,2})\s*USCIS-PM\s*([A-Z])(\.\d{1,2})?"), lambda m: f"{m[1]} USCIS-PM {m[2]}{m[3] or ''}"),
    (re.compile(r"\b(P[AM]-\d{3}-\d{4}|PA-\d{4}-\d{2})\b"), lambda m: m[1].upper()),
    (re.compile(r"\b(\d{2,3})\s*Fed\.\s?Reg\.\s*(\d{3,6})\b"), lambda m: f"{m[1]} FR {m[2]}"),
)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\u00a0", " ").replace("\u2011", "-")
    return re.sub(r"\s+", " ", text)


def authority_keys(text: str) -> list[tuple[str, str]]:
    """(key, as written) for every full authority cite in text. Short forms ("19 I&N Dec. at 3") are skipped."""
    text = _norm(text)
    return [(key(m), m.group(0)) for rx, key in _CITES for m in rx.finditer(text)]


def _matrix_keys(matrix: dict) -> set[str]:
    keys: set[str] = set()
    for prop in matrix.get("propositions") or []:
        if not isinstance(prop, dict):
            continue
        for row in (prop.get("support") or []) + (prop.get("adverse") or []):
            if not isinstance(row, dict):
                continue
            text = " ".join(str(row.get(k) or "") for k in ("authority", "citation", "pinpoint"))
            keys.update(k for k, _ in authority_keys(text))
    return keys


_NOTE_HEAD_RE = re.compile(r"^#{1,4}\s*(R\d+)\b")
_NOTE_FIELD_RE = re.compile(r"^\s*[-*]?\s*(Authority|Verified)\s*:\s*(.*)$", re.IGNORECASE)
# A Verified line starts with the date: 2026-10-29, 10/29/2026 or Oct. 29, 2026.
_MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
_NOTE_DATE = re.compile(
    r"^\W*(?:(?:19|20)\d{2}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/(?:19|20)\d{2}|" + _MONTHS + r"\s+\d{1,2},\s+(?:19|20)\d{2})\b"
)
_NOTE_NEGATIVE_RE = re.compile(r"\b(?:overruled|vacated|reversed|superseded|abrogated|withdrawn|unverified|unchecked|not checked|negative)\b", re.IGNORECASE)


def chat_note_keys(path: Path | None) -> tuple[dict[str, str], dict[str, str]]:
    """({authority key: entry id} verified, {authority key: entry id} not verified) from the chat
    research notes; see the module note for the lines read."""
    verified: dict[str, str] = {}
    unverified: dict[str, str] = {}
    if path is None or not path.is_file():
        return verified, unverified
    entries: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        head = _NOTE_HEAD_RE.match(line.strip())
        if head:
            entries.append({"id": head.group(1).upper(), "authority": "", "verified": ""})
            continue
        field_ = _NOTE_FIELD_RE.match(line)
        if field_ and entries:
            entries[-1][field_.group(1).lower()] += " " + field_.group(2).strip()
    for entry in entries:
        when = entry["verified"].strip()
        ok = bool(_NOTE_DATE.match(when)) and not _NOTE_NEGATIVE_RE.search(when)
        for key, _ in authority_keys(entry["authority"]):
            (verified if ok else unverified).setdefault(key, entry["id"])
    for key in verified:
        unverified.pop(key, None)
    return verified, unverified


def _covered(key: str, matrix: set[str]) -> bool:
    if key in matrix:
        return True
    if " USCIS-PM " in key:
        # A chapter cite is covered by the same chapter; a part cite ("7 USCIS-PM B") by any chapter of it.
        return any(m == key or m.startswith(key + ".") for m in matrix)
    return False


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------
_FACT_RES = (
    re.compile(r"\b" + _MONTHS + r"\s+(?:\d{1,2},\s+)?(?:19|20)\d{2}\b"),
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b(?:19|20)\d{2}-\d{2}-\d{2}\b"),
    re.compile(r"\b(?:19|20)\d{2}\b"),
    re.compile(r"\$\s?\d"),
    re.compile(r"\bA-?\s?\d{3}-?\d{3}-?\d{3}\b|\b[A-Z]{3}\d{10}\b"),
    re.compile(r"\b\d+(?:,\d{3})*\s+(?:months?|years?|weeks?|days?|children|pages?|statements?|photographs?|"
               r"photos?|accounts?|policies|letters|affidavits|trips?|percent)\b", re.IGNORECASE),
)
# Citations and their parentheticals carry years and numbers that are not facts about the client.
_CITATION_NOISE = re.compile(
    r"\((?:[^()]*?\b(?:BIA|AAO|AG|A\.G\.|Cir\.|D\.[A-Z.]+|U\.S\.|S\.\s?Ct\.)[^()]*?)?(?:19|20)\d{2}\)"
    r"|\b\d{1,4}\s+" + _REPORTERS + r"\s+\d{1,5}(?:,\s*\d{1,5}(?:[-–]\d{1,5})?)?"
    r"|\b\d{1,4}\s+" + _REPORTERS + r"\s+at\s+\d{1,5}"
    r"|\b\d{1,2}\s*C\.\s?F\.\s?R\.\s*§*\s*[\d.()a-zA-Z]+"
    r"|\b8\s*U\.\s?S\.\s?C\.\s*§*\s*[\d()a-zA-Z]+"
    r"|\bINA\s*§*\s*[\d()A-Za-z]+"
    r"|\b\d{1,2}\s*USCIS-PM\s*[A-Z][\d.()A-Z]*"
    r"|\b\d{2,3}\s*Fed\.\s?Reg\.\s*\d+(?:\s*\([^)]*\))?"
    r"|\bP[AM]-\d{3}-\d{4}|\bPA-\d{4}-\d{2}"
    r"|\bPub\.\s?L\.\s*(?:No\.\s*)?\d+-\d+"
    r"|\b(?:Form|Forms)\s+[A-Z]-\d+[A-Z]?|\b[GIN]-\d{2,4}[A-Z]?\b"
    r"|\((?:[^()]*?\b(?:updated|accessed|checked|ed\.|edition)[^()]*)\)",
    re.IGNORECASE,
)
_SENTENCE_RE = re.compile(r"(?<=[.!?])[\"'”’)]*\s+(?=[\"'“‘(*]*[A-Z])")
_ABBREV_END = re.compile(r"\b(?:Mr|Ms|Mrs|Dr|No|Nos|Inc|Co|Corp|St|Ave|Ex|Exs|Exh|Dec|Reg|Cir|Supp|App|U\.S|v|al|ed|p|pp|"
                         r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov)\.$"
                         # a middle initial ("Jane A. Example"), but not an exhibit label ("See Exhibit A.")
                         r"|(?<!xhibit )(?<!xhibits )(?<!Ex\. )(?<!Exs\. )(?<!Tab )(?<!and )\b[A-Z]\.$")


def sentences(text: str) -> list[str]:
    parts = _SENTENCE_RE.split(_norm(text).strip())
    out: list[str] = []
    for part in parts:
        if out and _ABBREV_END.search(out[-1]):
            out[-1] += " " + part
        else:
            out.append(part)
    return [s for s in out if s.strip()]


_LAW_YEAR_RE = re.compile(
    r"\b(?:19|20)\d{2}\s+(?:civics\s+test|fee\s+(?:rule|schedule)|(?:interim\s+)?final\s+rule|rule|edition|"
    r"amendments?|Act|policy|memo(?:randum)?)\b",
    re.IGNORECASE,
)


def is_fact_sentence(sentence: str) -> bool:
    """A sentence stating a dated or numeric fact about the client, not a statement of the law."""
    text = _norm(sentence)
    if render_letter.is_legal_statement(text):
        return False
    stripped = _LAW_YEAR_RE.sub(" ", render_letter._PERIOD_LAW_RE.sub(" ", _CITATION_NOISE.sub(" ", text)))
    return any(rx.search(stripped) for rx in _FACT_RES)


def _fold(text: str) -> str:
    text = _norm(text).replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"[*_]", "", text).lower()


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------
def _load_json(path: Path, what: str, errors: list[str]) -> dict | None:
    if not path.is_file():
        errors.append(f"The {what} is missing ({path.name}).")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"The {what} ({path.name}) can't be read: {exc}.")
        return None
    if not isinstance(data, dict):
        errors.append(f"The {what} ({path.name}) must be a JSON object.")
        return None
    return data


def check_letter(matter: Path, letter_md: Path, audit_path: Path, plan_path: Path, matrix_path: Path,
                 facts_path: Path, notes_path: Path | None = None) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    if not letter_md.is_file():
        raise ToolError(f"The letter source is missing: {letter_md}")
    letter = render_letter.parse_letter(read_utf8(letter_md))
    style = letter.front["exhibit_labels"]
    known = {e.label for e in letter.exhibits}
    body = [b for b in letter.blocks if b.kind in render_letter._BODY_KINDS]
    texts = [render_letter.plain(b.runs) for b in body]

    # 1. Authorities against the support matrix and the chat research notes recorded as verified.
    matrix = _load_json(matrix_path, "support matrix", errors)
    matrix_keys = _matrix_keys(matrix) if matrix else set()
    if notes_path is None:
        notes_path = matter / VAULT / CHAT_NOTES
    noted, unverified = chat_note_keys(notes_path)
    authorities: list[dict] = []
    seen: set[str] = set()
    for text in texts:
        for key, written in authority_keys(text):
            if key in seen:
                continue
            seen.add(key)
            ok = _covered(key, matrix_keys)
            note = next((entry for k, entry in noted.items() if _covered(key, {k})), None)
            authorities.append({"cite": written, "key": key, "in_matrix": ok, "chat_note": note})
            if matrix and not ok and not note:
                pending = next((entry for k, entry in unverified.items() if _covered(key, {k})), None)
                why = (f" Chat research note {pending} names it, but without a Verified date (or with negative "
                       "treatment), so it doesn't count." if pending else "")
                errors.append(f"Authority not in the support matrix: {written}. Cite only what the research verified "
                              f"(the support matrix, or a verified chat research note), or have the researcher add it.{why}")

    # 2. Exhibits: the audit is clean and the plan matches it.
    audit = _load_json(audit_path, "render audit", errors)
    plan = _load_json(plan_path, "exhibit plan", errors)
    audit_exhibits = (audit or {}).get("exhibits") or []
    plan_exhibits = (plan or {}).get("exhibits") or []
    if audit is not None and audit.get("finding_count", 0):
        errors.append(f"The render audit has {audit['finding_count']} finding(s); fix the letter and render it again.")
    if audit is not None and plan is not None:
        if len(plan_exhibits) != len(audit_exhibits):
            errors.append(f"The exhibit plan lists {len(plan_exhibits)} exhibits but the letter lists {len(audit_exhibits)}.")
        for n, (p, a) in enumerate(zip(plan_exhibits, audit_exhibits), start=1):
            if not isinstance(p, dict):
                errors.append(f"Exhibit plan entry {n} isn't an object.")
                continue
            plabel = str(p.get("label") or "").strip()
            if plabel.upper() != str(a.get("label") or "").upper():
                errors.append(f"Exhibit plan entry {n} is labeled {plabel or '(none)'} but the letter's exhibit {n} is "
                              f"{a.get('label')}; copy the labels from the audit.")
            if (p.get("section") or None) != (a.get("section") or None):
                errors.append(f"Exhibit {a.get('label')} is in section {p.get('section')!r} in the plan but "
                              f"{a.get('section')!r} in the letter.")
            if _fold(str(p.get("description") or "")) != _fold(str(a.get("description") or "")):
                warnings.append(f"Exhibit {a.get('label')}'s description differs between the plan and the letter.")
            sources = p.get("sources") or []
            if p.get("placeholder") or p.get("physical"):
                if not p.get("open_item"):
                    errors.append(f"Exhibit {a.get('label')} is a {'placeholder' if p.get('placeholder') else 'physical item'} "
                                  "without its open item.")
            elif not sources:
                errors.append(f"Exhibit {a.get('label')} has no source document, placeholder or physical marker.")
            for s in sources:
                if not (matter / str(s)).is_file():
                    errors.append(f"Exhibit {a.get('label')}'s source {s} isn't in the matter folder.")

    # 3. Facts against the fact table.
    facts_data = _load_json(facts_path, "fact table", errors) if facts_path.exists() else None
    if facts_data is None and not facts_path.exists():
        errors.append(f"The fact table is missing ({facts_path.name}); list each dated or numeric fact with its source.")
    facts = [f for f in (facts_data or {}).get("facts") or [] if isinstance(f, dict)]
    folded_letter = _fold(" ".join(texts))
    usable: list[str] = []
    for n, f in enumerate(facts, start=1):
        text = str(f.get("text") or "").strip()
        if not text:
            errors.append(f"Fact table entry {n} has no text.")
            continue
        if not str(f.get("source") or "").strip():
            errors.append(f"Fact table entry {n} ({text[:60]!r}) has no source.")
            continue
        if _fold(text) not in folded_letter:
            warnings.append(f"Fact table entry {n} ({text[:60]!r}) isn't in the letter any more.")
        usable.append(_fold(text))
    fact_sentences = sourced = 0
    for b, text in zip(body, texts):
        if b.kind in ("quote", "h1", "h2", "h3"):
            continue
        sents = sentences(text)
        for i, s in enumerate(sents):
            if not is_fact_sentence(s):
                continue
            fact_sentences += 1
            nxt = sents[i + 1] if i + 1 < len(sents) else ""
            cites = render_letter.cited_labels(s, style, known) or render_letter.cited_labels(nxt, style, known)
            in_table = any(u in _fold(s) for u in usable)
            if cites or in_table:
                sourced += 1
            else:
                errors.append(f"Fact without a source: {s[:120]!r}. Cite the exhibit that proves it, or add it to the "
                              "fact table with its document.")
    phrases = render_letter.computed_phrases(letter)
    for p in phrases:
        if not any(_fold(p["text"]) in u for u in usable):
            errors.append(f"Age or duration not in the fact table: {p['text']!r}. Recompute it from the documents as of "
                          "the letter's date and add it with its source.")

    return {
        "checked_at": _dt.datetime.now().replace(microsecond=0).isoformat(),
        "letter": str(letter_md),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "authorities": authorities,
        "exhibits": {"plan": len(plan_exhibits), "letter": len(audit_exhibits)},
        "facts": {"fact_sentences": fact_sentences, "sourced": sourced, "computed_phrases": len(phrases),
                  "fact_table_entries": len(facts)},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check a cover letter against its support matrix, exhibit plan and fact table.")
    ap.add_argument("matter", type=Path, help="Matter folder")
    ap.add_argument("--slug", default="main", help="The cover-letter vault slug (default: main)")
    ap.add_argument("--research-slug", help="The research vault slug (default: the same as --slug)")
    for name in ("letter", "audit", "plan", "matrix", "facts", "notes", "output"):
        ap.add_argument(f"--{name}", type=Path, help=f"Override the {name} path")
    ap.add_argument("--json", action="store_true", help="Print the whole result as JSON")
    args = ap.parse_args(argv)
    matter = args.matter.expanduser().resolve()
    if not matter.is_dir():
        raise ToolError(f"Matter folder not found: {matter}")
    cl = matter / VAULT / "cover-letter" / args.slug
    rs = matter / VAULT / "research" / (args.research_slug or args.slug)
    paths = {
        "letter": args.letter or cl / "cover letter.md",
        "audit": args.audit or cl / "cover letter audit.json",
        "plan": args.plan or cl / "exhibit plan.json",
        "matrix": args.matrix or rs / "support matrix.json",
        "facts": args.facts or cl / "letter facts.json",
        "notes": args.notes or matter / VAULT / CHAT_NOTES,
    }
    paths = {k: Path(v).expanduser().resolve() for k, v in paths.items()}
    result = check_letter(matter, paths["letter"], paths["audit"], paths["plan"], paths["matrix"], paths["facts"],
                          paths["notes"])
    out = (args.output.expanduser().resolve() if args.output else cl / "letter check.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(result | {"output": str(out)}, indent=2, ensure_ascii=False))
        return 0
    status = "clean" if result["error_count"] == 0 else "NOT READY"
    print(f"Letter check: {status}: {result['error_count']} error(s), {result['warning_count']} warning(s); "
          f"{len(result['authorities'])} authorities, {result['facts']['fact_sentences']} fact sentences")
    print(f"Written:      {out}")
    for e in result["errors"][:5]:
        print(f"  - error: {e[:160]}")
    if result["error_count"] > 5:
        print(f"  ... {result['error_count'] - 5} more in the file's errors[].")
    return 0


if __name__ == "__main__":
    run_cli(main)

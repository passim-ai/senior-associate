"""Plain text for the attorney's screen.

The skills write each open item's `question`, `recommendation` and `detail` for the screen. Matters built before
that kept one `detail` that every step appended to, with item ids, review codes, paths and dated notes. For those,
the screen gets the first sentence or two of the original detail, cut at a sentence, with the machinery taken out.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .catalog import STAGE_LABELS

DETAIL_LIMIT = 300
QUESTION_LIMIT = 160
RECOMMENDATION_LIMIT = 200
TITLE_LIMIT = 160

# Abbreviations a sentence doesn't end on. The second set only counts before a number ("No. 12", "17 I&N Dec. 22").
ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "st", "jr", "sr", "inc", "corp", "co", "ltd", "llc", "pllc", "v", "vs", "etc", "al",
    "approx", "cf", "cir", "supp", "fed", "reg", "stat", "seq", "dept", "gov", "govt",
    # addresses, here and abroad ("Av. Juárez 120", "Col. Centro")
    "ave", "av", "avda", "blvd", "rd", "ste", "apt", "bldg", "fl", "hwy", "pkwy", "ln", "ct", "sq", "mt", "ft", "col", "esq",
}
ABBREVIATIONS_BEFORE_NUMBER = {
    "no", "nos", "vol", "pt", "pts", "ch", "p", "pp", "sec", "secs", "art", "para", "ex", "exh", "n", "nn", "fig",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
}
_SENTENCE_END = re.compile(r"[.!?][\"'”’)\]]*\s+(?=[\"'“‘(\[]?[A-Z0-9])")
_INITIALISM = re.compile(r"(?:[A-Za-z]\.)+[A-Za-z]")

_STAGE_ID_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, STAGE_LABELS), key=len, reverse=True)) + r"|senior_associate)\b")
_SNAKE_WORDS = {
    "attorney_decision": "decision", "attorney_action": "task for you", "client_document": "client document",
    "client_question": "question for the client", "blocks_filing": "needed before filing", "ready_to_file": "ready to file",
    "packet_status": "packet status", "needed_for": "needed for",
}
_CODE_RE = re.compile(r"\b(?:ADJ|FR|CLR|PR|DR|BLK)\d+[a-z]?\b")
_FINDING_CODES_RE = re.compile(r"\s*\b(?:[Ff]indings?|[Rr]eview)\s+(?:(?:ADJ|FR|CLR|PR|DR|BLK)\d+[a-z]?)(?:\s*(?:,|and|&)\s*(?:ADJ|FR|CLR|PR|DR|BLK)\d+[a-z]?)*")
_PCODE_RE = re.compile(r"\bP\d{1,2}[a-z]?(?:\s*[-–]\s*P?\d{1,2})?\b")
_ISO_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:T[\d:.]+(?:Z|[+-]\d{2}:?\d{2})?)?\b")
_PATH_RE = re.compile(r"(?:\b(?:output|vault|working|deliverables|workflow)/|/Users/|/private/|~/|\b[\w-]+\.(?:md|json|jsonl|py|log)\b)")
_GENERIC_ID_RE = re.compile(r"(?<![\w-])(?:doc|q|decide|decision|action|risk|blk)-[a-z0-9]+(?:-[a-z0-9]+)*(?![\w-])")
_PROCESS_WORDS_RE = re.compile(r"\b(?:finding|findings|re-review|rerouted?|marked blocking|senior associate|stage|vault)\b", re.I)

# A note a step appended to an older detail: "Forms: …", "Cover letter (draft 2026-10-28): …", "Adjudicator (2026-10-28): …".
_NOTE_LEADS = (
    "forms", "forms review", "cover letter", "cover letter review", "letter review", "packet", "packet review",
    "packet re-review", "research", "researcher", "adjudicator", "reviewer", "re-review", "integration", "final review",
    "docs review", "document review", "officer's review", "assembly", "handoff", "senior associate", "update",
)
_NOTE_RE = re.compile(r"^\(?([A-Z][\w'’-]*(?: [\w'’-]+){0,3})\s*(\([^()]*\))?:\s")
_RECOMMEND_RE = re.compile(
    r"^(?:Our |My |Claude's )?(?:Recommendation|Recommended|Recommend|We recommend|I recommend|Claude recommends)\b\s*[:,—-]?\s*(.+)$",
    re.I | re.S,
)


def _is_abbreviation(word: str, next_char: str) -> bool:
    w = word.lstrip("(\"'“‘[").rstrip(")\"'”’]")
    if not w:
        return False
    if _INITIALISM.fullmatch(w) or re.fullmatch(r"[A-Z]", w):
        return True
    low = w.lower()
    if low in ABBREVIATIONS:
        return True
    return low in ABBREVIATIONS_BEFORE_NUMBER and next_char.isdigit()


def split_sentences(text: str) -> list[str]:
    """Sentences, without splitting on "U.S.", "e.g.", "Matter of X, 17 I&N Dec. 22" and the like."""
    text = re.sub(r"\s+", " ", text or "").strip()
    out: list[str] = []
    start = 0
    for m in _SENTENCE_END.finditer(text):
        if text[m.start()] == ".":
            before = text[start:m.start()]
            word = before.rsplit(" ", 1)[-1] if before else ""
            if _is_abbreviation(word, text[m.end():m.end() + 1]):
                continue
        out.append(text[start:m.end()].strip())
        start = m.end()
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out


def _parentheticals(text: str) -> list[tuple[int, int]]:
    """(start, end) of each top-level, balanced parenthetical."""
    spans: list[tuple[int, int]] = []
    depth, start = 0, -1
    for i, ch in enumerate(text):
        if ch == "(":
            if depth == 0:
                start = i
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
            if depth == 0:
                spans.append((start, i + 1))
    return spans


def _id_pattern(known_ids: set[str] | frozenset[str]) -> re.Pattern[str] | None:
    ids = sorted((i for i in known_ids if i and len(i) > 2), key=len, reverse=True)
    if not ids:
        return None
    return re.compile(r"(?<![\w-])(?:" + "|".join(map(re.escape, ids)) + r")(?![\w-])")


def _looks_like_id(token: str) -> bool:
    rest = token.split("-", 1)[1] if "-" in token else ""
    return rest.count("-") >= 1 or any(ch.isdigit() for ch in rest)


def _has_id(text: str, ids_re: re.Pattern[str] | None) -> bool:
    if ids_re is not None and ids_re.search(text):
        return True
    return any(_looks_like_id(m.group(0)) for m in _GENERIC_ID_RE.finditer(text))


def _is_noise(text: str, ids_re: re.Pattern[str] | None) -> bool:
    """Machinery the attorney shouldn't read: an item id, a path, a step id or a review code. A date is not
    machinery by itself ("expires 2027-01-05"); only a step's dated stamp is (see _is_stamp)."""
    return bool(_has_id(text, ids_re) or _PATH_RE.search(text) or _STAGE_ID_RE.search(text) or _CODE_RE.search(text))


# A step's stamp in parentheses: "(draft 2026-10-28)", "(2026-10-28)", "(Re-review, 2026-10-28)".
_STAMP_RE = re.compile(
    r"^\s*(?:(?:draft|updated|update|re-review|review|reviewed|research|integration|adjudicator|reviewer|packet|forms|"
    r"cover letter|handoff|final review|officer's review)\b[\s,;:]*)*\d{4}-\d{2}-\d{2}(?:T[\d:.Z+-]*)?\s*$",
    re.I,
)


def _tidy(text: str) -> str:
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\s+([,.;:!?)])", r"\1", text)
    text = re.sub(r"([(])\s+", r"\1", text)
    text = re.sub(r"[,;]\s*([.!?])", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = text.replace("`", "")
    return text.strip(" ,;")


def strip_machinery(text: str, ids_re: re.Pattern[str] | None = None) -> str:
    """Take out what's for Claude, not the attorney: parentheticals that hold ids, paths, codes or dated notes,
    review codes, and step ids (which become their plain names)."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", str(text)).replace("`", "")
    for start, end in reversed(_parentheticals(text)):
        inner = text[start + 1:end - 1]
        if (
            _is_noise(inner, ids_re) or _PCODE_RE.search(inner) or _STAMP_RE.match(inner)
            or (_PROCESS_WORDS_RE.search(inner) and len(inner) < 160)
            or inner.lower().startswith(("see ", "needs ", "new item", "item ", "open item"))
        ):
            text = text[:start].rstrip() + text[end:]
    text = _FINDING_CODES_RE.sub("", text)
    text = _CODE_RE.sub("", text)
    for snake, plain in _SNAKE_WORDS.items():
        text = text.replace(snake, plain)
    text = _STAGE_ID_RE.sub(lambda m: STAGE_LABELS.get(m.group(1), "Claude").lower(), text)
    text = _ISO_RE.sub(_date_in_words, text)
    return _tidy(text)


def _date_in_words(m: re.Match[str]) -> str:
    """2026-10-28 → October 28, 2026, the way the attorney writes a date."""
    try:
        d = datetime.strptime(m.group(0)[:10], "%Y-%m-%d")
    except ValueError:
        return m.group(0)
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def _replace_ids(text: str, ids_re: re.Pattern[str] | None) -> str:
    if ids_re is not None:
        text = ids_re.sub("a related open item", text)
    return _GENERIC_ID_RE.sub(lambda m: "a related open item" if _looks_like_id(m.group(0)) else m.group(0), text)


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def cut_text(text: str, limit: int) -> str:
    """At most `limit` characters, cut at a sentence if one ends in the last part, else at a clause or a word,
    never mid-word."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    kept = ""
    for sentence in split_sentences(text):
        joined = f"{kept} {sentence}".strip()
        if len(joined) > limit:
            break
        kept = joined
    if kept and len(kept) >= limit * 0.4:
        return kept
    window = text[: limit - 1]
    for mark in ("; ", ": ", " — ", ", "):
        at = window.rfind(mark)
        if at >= limit * 0.4:
            return window[:at].rstrip(" ,;:—") + "…"
    at = window.rfind(" ")
    return (window[:at] if at > 0 else window).rstrip(" ,;:—") + "…"


def _is_note_lead(sentence: str) -> bool:
    m = _NOTE_RE.match(sentence)
    if not m:
        return False
    lead, paren = m.group(1).lower(), m.group(2) or ""
    if lead in _NOTE_LEADS:
        return True
    return bool(paren) and bool(_ISO_RE.search(paren) or _STAGE_ID_RE.search(paren))


def _base_sentences(detail: str) -> tuple[list[str], list[str]]:
    """The detail as first written, and the notes steps appended after it."""
    sentences = split_sentences(detail)
    for i, s in enumerate(sentences):
        if _is_note_lead(s):
            return sentences[:i], sentences[i:]
    return sentences, []


def _drop_note_lead(sentence: str) -> str:
    m = _NOTE_RE.match(sentence)
    return sentence[m.end():] if m and _is_note_lead(sentence) else sentence


def plain_detail(detail: str, ids_re: re.Pattern[str] | None = None, limit: int = DETAIL_LIMIT) -> str:
    """The first sentence or two of what the item says, cut at a sentence within `limit`, without machinery.
    A detail written to the open-item rules comes through unchanged."""
    detail = re.sub(r"\s+", " ", str(detail or "")).strip()
    if not detail:
        return ""
    base, notes = _base_sentences(detail)
    candidates = base or [_drop_note_lead(s) for s in notes]
    kept: list[str] = []
    for raw in candidates:
        sentence = strip_machinery(raw, ids_re)
        if not sentence or _is_noise(sentence, ids_re) or len(sentence) < 3:
            continue
        joined = " ".join(kept + [sentence])
        if len(joined) > limit:
            if not kept:
                kept.append(cut_text(sentence, limit))
            break
        kept.append(sentence)
    return _capitalize(" ".join(kept).strip())


def _title_as_question(title: str) -> str:
    """An older decision's title as the question to the attorney: "Whether to file an I-765" → "File an I-765?"."""
    t = title.strip().rstrip(".")
    if not t or t.endswith("?"):
        return t
    m = re.match(r"^whether and how to (.+)$", t, re.I)
    if m:
        return f"{_capitalize(m.group(1))}, and if so, how?"
    m = re.match(r"^whether to (.+)$", t, re.I)
    if m:
        return f"{_capitalize(m.group(1))}?"
    m = re.match(r"^whether (.+)$", t, re.I)
    if m:
        return f"{_capitalize(m.group(1))}?"
    m = re.match(r"^how to (.+)$", t, re.I)
    if m:
        return f"How should we {m.group(1)}?"
    m = re.match(r"^how (.+?) should (.+)$", t, re.I)
    if m:
        return f"How should {m.group(1)} {m.group(2)}?"
    m = re.match(r"^(what|which|who|when|where|why) (.+)$", t, re.I)
    if m:
        return f"{_capitalize(t)}?"
    return t


def plain_question(question: Any, title: str, ids_re: re.Pattern[str] | None = None) -> str:
    q = strip_machinery(str(question or ""), ids_re)
    if not q:
        q = _title_as_question(strip_machinery(title, ids_re))
    q = _replace_ids(q, ids_re)
    return _capitalize(cut_text(q, QUESTION_LIMIT))


def plain_recommendation(recommendation: Any, detail: str, ids_re: re.Pattern[str] | None = None) -> str:
    """The item's recommendation, or for an older decision a "Recommendation: …" sentence in the detail as first
    written. The notes steps appended later are left alone: a recommendation there is often about one option only,
    and offering it as the answer to the whole question could mislead."""
    rec = str(recommendation or "").strip()
    if not rec:
        base, _notes = _base_sentences(re.sub(r"\s+", " ", str(detail or "")))
        for sentence in base:
            m = _RECOMMEND_RE.match(sentence)
            if m:
                rec = m.group(1)
                break
    if not rec:
        return ""
    rec = _replace_ids(strip_machinery(rec, ids_re), ids_re)
    return _capitalize(cut_text(rec, RECOMMENDATION_LIMIT))


def plain_title(title: str, ids_re: re.Pattern[str] | None = None) -> str:
    return cut_text(_replace_ids(strip_machinery(title, ids_re), ids_re), TITLE_LIMIT)


def split_stage_prefix(text: str) -> tuple[str, str]:
    """("Forms review: the I-94 date is missing") → ("The I-94 date is missing", "Forms review")."""
    m = re.match(r"^\s*([A-Za-z_' -]{2,40}?)\s*:\s+(.+)$", text or "", re.S)
    if m:
        lead = m.group(1).strip()
        label = STAGE_LABELS.get(lead) or next((v for v in STAGE_LABELS.values() if v.lower() == lead.lower()), "")
        if label:
            return _capitalize(m.group(2).strip()), label
    return (text or "").strip(), ""

#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "python-docx>=1.1",
#   "pypdf>=5.0",
#   "reportlab>=4.0",
# ]
# ///
"""Render a USCIS cover letter written in Letter Markdown to .docx and .pdf.

    uv run --script render_letter.py LETTER.md [--profile ATTORNEY.json]
        [--out-dir DIR] [--name BASENAME] [--renderer auto|libreoffice|reportlab]
        [--summary-json PATH] [--json]

Writes BASENAME.docx, BASENAME.pdf and BASENAME.render.json (the full summary and
mechanical audit). Stdout is short: the output paths, a one-line audit count and
the first few findings; --json prints the whole summary instead.
The PDF comes from LibreOffice converting the .docx when LibreOffice is
installed, otherwise from reportlab drawing the same source.
The Markdown dialect is documented in README.md next to this script.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

sys.dont_write_bytecode = True  # never leave __pycache__ inside the plugin folder
sys.path.insert(0, str(Path(__file__).resolve().parent))
import filing_locations  # noqa: E402
from _packet_common import (  # noqa: E402
    ToolError,
    find_soffice,
    numbered_canvas,
    output_base,
    read_utf8,
    register_serif_fonts,
    run_cli,
    soffice_convert_to_pdf,
    unsupported_chars,
)

# ---------------------------------------------------------------------------
# Layout constants (inches / points). Both renderers use the same numbers.
# ---------------------------------------------------------------------------
PAGE_W, PAGE_H = 8.5, 11.0
MARGIN = 1.0
BODY_PT = 12
LEADING = 13.8  # what Word calls "single" spacing for 12 pt Times New Roman
PARA_INDENT = 0.5  # first-line indent of body paragraphs
RE_HANG = 0.75  # "RE:" label width
H2_LABEL_AT, H2_TEXT_AT = 0.5, 1.0  # roman proof subheads: numeral at 0.5", text at 1.0"
LIST_LABEL_AT, LIST_TEXT_AT = 0.5, 0.875
QUOTE_INDENT = 0.75
EXHIBIT_LABEL_AT = 0.5
SIGNATURE_GAP_PT = 44
RULE_AFTER_PT = 18  # space under the letterhead's rule
LETTERHEAD_PT = {"firm": 16, "name": 12, "detail": 10.5}
LEADING_FOR = {16: 19, 10.5: 12.5}  # reportlab line spacing for the letterhead's other sizes

PROFILE_KEYS = ("attorney_name", "firm_name", "mailing_address", "phone", "email", "bar_number", "licensing_authority")
FRONT_KEYS = set(
    "date delivery to re salutation closing signer_title cc exhibit_labels exhibit_prefix exhibit_start page_numbers "
    "smart_quotes matter_type length_budget filing_method protected filing_location lead_form filing_basis".split()
)
LIST_KEYS = {"to", "re", "cc"}

# Words of argument (paragraphs, quotes and lists; not headings or the exhibit index) a letter
# of each matter type should need. Keys are the authorities-file names in
# skills/coverletter/references/research.md. Above budget is a warning: trim, or set
# `length_budget` in the front matter when the attorney wants the longer letter.
LENGTH_BUDGETS = {
    "i130_standalone": 1000, "i130_i485": 1500, "i751_joint": 1200, "i751_waiver": 2500, "n400": 900, "i765": 600,
    "i131": 700, "i129f": 1000, "i612": 3000, "i601a": 3000, "i601": 3000, "i140_niw": 6000, "i140_i485": 3000,
    "i485_asylee_refugee": 900, "i360_vawa": 3000,
}
# Responses argue whatever the notice raises; they get no budget.
UNBUDGETED_TYPES = {"rfe_response", "noid_response", "response", "other"}
STALE_DATE_DAYS = 7


def _today() -> _dt.date:
    """The render date. Tests replace this to stay independent of the calendar."""
    return _dt.date.today()


# ---------------------------------------------------------------------------
# Document model
# ---------------------------------------------------------------------------
@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False


@dataclass
class Block:
    kind: str  # para h1 h2 h3 quote bullet number exh_section exh_item pagebreak signature
    runs: list[Run] = field(default_factory=list)
    marker: str = ""  # numeral, bullet or exhibit label drawn in the hanging position
    last_in_group: bool = False
    first_in_group: bool = False


@dataclass
class Exhibit:
    label: str
    display: str
    section: str | None
    description: str


class Audit:
    """Mechanical audit of the letter.

    findings (errors and warnings) are defects in the letter itself; the letter
    should not pass review while any remain. notes are informational only
    (renderer fallbacks, optional profile fields left out) and never block.
    """

    def __init__(self) -> None:
        self.findings: list[dict] = []
        self.notes: list[str] = []

    def error(self, title: str, detail: str) -> None:
        self._add("error", title, detail)

    def warn(self, title: str, detail: str) -> None:
        self._add("warning", title, detail)

    def note(self, text: str) -> None:
        if text not in self.notes:
            self.notes.append(text)

    def _add(self, severity: str, title: str, detail: str) -> None:
        finding = {"severity": severity, "title": title, "detail": detail}
        if finding not in self.findings:
            self.findings.append(finding)


@dataclass
class Letter:
    front: dict
    blocks: list[Block]
    exhibits: list[Exhibit]
    audit: Audit
    exhibit_hang: float  # inches from label start to text start
    prefix: str = "Exhibit"


# ---------------------------------------------------------------------------
# Inline Markdown
# ---------------------------------------------------------------------------
# A backslash escape stands for its character. The five that are markup are held as private-use
# characters while the inline markup is parsed, then put back.
_HELD = "\\*_<`"
_ESCAPES = {"\\" + c: chr(0xE000 + n) for n, c in enumerate(_HELD)} | {"\\" + c: c for c in "#[]>-"}
_UNESCAPE = {chr(0xE000 + n): c for n, c in enumerate(_HELD)}

_INLINE_RE = re.compile(
    r"\*\*\*(?=\S)(?P<bi>.+?)(?<=\S)\*\*\*"
    r"|\*\*(?=\S)(?P<b>.+?)(?<=\S)\*\*"
    r"|\*(?=[^\s*])(?P<i>.+?)(?<=[^\s*])\*"
    r"|(?<![\w])_(?=[^\s_])(?P<i2>.+?)(?<=[^\s_])_(?![\w])"
    r"|<u>(?P<u>.+?)</u>"
    r"|`(?P<code>[^`]+)`"
    r"|\[(?P<ltext>[^\]]+)\]\((?P<lurl>[^)\s]+)\)",
    re.DOTALL,
)


def _smarten(text: str) -> str:
    # An apostrophe that stands for dropped century digits ('96, '90s) is never an opening quote.
    text = re.sub(r"'(?=\d{2}s?\b)", "’", text)
    # A quote opens after a space, an opening bracket or dash, or the other kind of opening quote
    # ("'Extreme' cruelty" opens with a double quote and then a single one).
    text = re.sub(r'(^|[\s(\[{—–*_/‘-])"', lambda m: m.group(1) + "“", text)
    text = text.replace('"', "”")
    text = re.sub(r"(^|[\s(\[{—–*_/“-])'", lambda m: m.group(1) + "‘", text)
    return text.replace("'", "’")


def _parse_inline_raw(text: str, bold: bool, italic: bool, underline: bool) -> list[Run]:
    runs: list[Run] = []
    pos = 0
    for m in _INLINE_RE.finditer(text):
        if m.start() > pos:
            runs.append(Run(text[pos : m.start()], bold, italic, underline))
        if m.group("bi") is not None:
            runs += _parse_inline_raw(m.group("bi"), True, not italic, underline)
        elif m.group("b") is not None:
            runs += _parse_inline_raw(m.group("b"), True, italic, underline)
        elif m.group("i") is not None:
            # Italic inside italic flips back to roman (the legal convention for a
            # case name inside an italicized sentence).
            runs += _parse_inline_raw(m.group("i"), bold, not italic, underline)
        elif m.group("i2") is not None:
            runs += _parse_inline_raw(m.group("i2"), bold, not italic, underline)
        elif m.group("u") is not None:
            runs += _parse_inline_raw(m.group("u"), bold, italic, True)
        elif m.group("code") is not None:
            runs.append(Run(m.group("code"), bold, italic, underline))
        else:  # link: keep the visible text only
            runs += _parse_inline_raw(m.group("ltext"), bold, italic, underline)
        pos = m.end()
    if pos < len(text):
        runs.append(Run(text[pos:], bold, italic, underline))
    return runs


class InlineParser:
    def __init__(self, smart_quotes: bool, audit: Audit):
        self.smart_quotes = smart_quotes
        self.audit = audit

    def __call__(self, text: str, bold: bool = False, italic: bool = False) -> list[Run]:
        raw = text
        for k, v in _ESCAPES.items():
            text = text.replace(k, v)
        if self.smart_quotes:
            text = _smarten(text)
        # Keep "§ 1151" and "¶ 3" on one line.
        text = re.sub(r"(§§?|¶¶?) (?=\S)", "\\1\u00a0", text)
        # ...and "Ms. Example", "Exhibit C".
        text = re.sub(r"\b(Mr|Ms|Mrs|Dr|Hon)\. (?=[A-Z])", "\\1.\u00a0", text)
        text = re.sub(r"\b(Exhibits?|Exh\.|Tabs?) (?=[A-Z0-9]{1,3}\b)", "\\1\u00a0", text)
        runs = _parse_inline_raw(text, bold, italic, False)
        leftover = "".join(r.text for r in runs)
        snippet = raw if len(raw) <= 70 else raw[:67] + "..."
        if "*" in leftover:
            self.audit.error(
                "Unresolved Markdown",
                f"An emphasis marker was left as literal text in {snippet!r}. Close each *italic* / **bold** "
                "on the same paragraph, or escape a literal asterisk as \\*.",
            )
        if re.search(r"</?[A-Za-z][^>]*>", leftover):
            self.audit.error(
                "Unresolved Markdown",
                f"An HTML tag was left as literal text in {snippet!r}. Only <u>...</u> is supported.",
            )
        if re.search(r"\[\^[^\]]+\]", leftover):
            self.audit.error(
                "Unsupported footnote",
                f"Footnotes are not supported, so {snippet!r} shows the marker literally. Move the text inline.",
            )
        placeholder = _PLACEHOLDER_RE.search(leftover)
        if placeholder:
            self.audit.error(
                "Unfilled placeholder",
                f"{placeholder.group(0)!r} in {snippet!r} looks like drafting text that was never filled in.",
            )
        for r in runs:
            for k, v in _UNESCAPE.items():
                r.text = r.text.replace(k, v)
        return merge_runs(runs)


def merge_runs(runs: list[Run]) -> list[Run]:
    """Join neighboring runs of the same emphasis and drop empty ones."""
    merged: list[Run] = []
    for r in runs:
        if not r.text:
            continue
        if merged and (merged[-1].bold, merged[-1].italic, merged[-1].underline) == (r.bold, r.italic, r.underline):
            merged[-1].text += r.text
        else:
            merged.append(r)
    return merged


_PLACEHOLDER_RE = re.compile(
    r"\[(?:insert|tbd|todo|tk|citation|cite|date|name|fill|placeholder|confirm)\b[^\]]*\]"
    r"|\{\{[^}]*\}\}|\bTBD\b|\bTODO\b|\bX{3,}\b|\?{3,}",
    re.IGNORECASE,
)


def plain(runs: list[Run]) -> str:
    return "".join(r.text for r in runs)


def markup(runs: list[Run]) -> str:
    """Runs as reportlab paragraph markup."""
    out = []
    for r in runs:
        t = xml_escape(r.text)
        if r.underline:
            t = f"<u>{t}</u>"
        if r.italic:
            t = f"<i>{t}</i>"
        if r.bold:
            t = f"<b>{t}</b>"
        out.append(t)
    return "".join(out)


def docx_runs(p, runs: list[Run], size: float | None = None, bold: bool = False) -> None:
    """Add runs to a python-docx paragraph with their emphasis (and `bold` on all of them)."""
    from docx.shared import Pt

    for r in runs:
        run = p.add_run(r.text)
        run.bold = r.bold or bold or None
        run.italic = r.italic or None
        run.underline = r.underline or None
        if size:
            run.font.size = Pt(size)


# ---------------------------------------------------------------------------
# Labels and numerals
# ---------------------------------------------------------------------------
def to_roman(n: int) -> str:
    out = ""
    for value, sym in (
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
        (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ):
        while n >= value:
            out += sym
            n -= value
    return out


def exhibit_label(index: int, style: str) -> str:
    """0 -> A ... 25 -> Z, 26 -> AA, 27 -> BB ... (or 1, 2, 3 for numbers)."""
    if style == "numbers":
        return str(index + 1)
    return chr(ord("A") + index % 26) * (index // 26 + 1)


def _label_index(label: str, style: str) -> int | None:
    """The inverse of exhibit_label, or None when label isn't one this tool assigns."""
    if style == "numbers":
        return int(label) - 1 if label.isdigit() and int(label) > 0 else None
    if label.isalpha() and label.isupper() and len(set(label)) == 1:
        return (len(label) - 1) * 26 + ord(label[0]) - ord("A")
    return None


def label_offset(start: str, style: str) -> int:
    start = start.strip()
    index = _label_index(start.upper(), style)
    if index is None and style == "numbers":
        raise ToolError(f"exhibit_start must be a whole number like 4 when exhibit_labels is numbers (got {start!r}).")
    if index is None:
        raise ToolError(f"exhibit_start must be a letter label like D or BB (got {start!r}).")
    return index


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
_PAGEBREAK = "PAGEBREAK"
_SIGNATURE = "SIGNATURE"
_KEY_RE = re.compile(r"^([A-Za-z][\w-]*)\s*:\s*(.*)$")
_HAND_LABEL_RE = re.compile(
    r"^(?:exhibit|exh\.?|tab)\s+([A-Z0-9]{1,4}(?:-\d+)?)\s*[:.)–—-]\s*", re.IGNORECASE
)
_LOWER_ROMAN_RE = re.compile(r"^[ivxlc]+[.)]\s+")
_LABEL_STYLES = {**dict.fromkeys(("letters", "letter", "alpha", "alphabetic"), "letters"),
                 **dict.fromkeys(("numbers", "number", "numeric", "digits"), "numbers")}


def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def parse_front_matter(lines: list[str], audit: Audit) -> tuple[dict, int]:
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or lines[i].strip() != "---":
        audit.error(
            "Missing front matter",
            "No block between two '---' lines at the top of the file, so the date, delivery line, "
            "USCIS address and RE block were left out.",
        )
        return {}, 0
    front: dict = {}
    current: str | None = None
    j = i + 1
    while j < len(lines):
        line = lines[j]
        if line.strip() == "---":
            break
        j += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indented = line[:1] in (" ", "\t")
        item = re.match(r"^\s*-\s+(.*)$", line)
        if (indented or item) and current is not None:
            text = item.group(1) if item else line.strip()
            value = front.get(current)
            if not isinstance(value, list):
                value = [] if not value else [value]
            value.append(_unquote(text))
            front[current] = value
            continue
        m = _KEY_RE.match(line)
        if not m:
            raise ToolError(
                f"Front matter line {j} is not 'key: value' or an indented '- item': {line.strip()!r}"
            )
        key = m.group(1).lower().replace("-", "_")
        if key not in FRONT_KEYS:
            audit.warn(
                "Unknown front-matter key",
                f"{m.group(1)!r} was ignored (a typo?). Known keys: {', '.join(sorted(FRONT_KEYS))}.",
            )
        current = key
        front[key] = _unquote(m.group(2)) if m.group(2).strip() else []
    else:
        raise ToolError("The front matter opened with '---' is never closed. Add a '---' line after it.")
    for key in LIST_KEYS:
        if key in front and isinstance(front[key], str):
            front[key] = [front[key]]
    for key in list(front):
        if key not in LIST_KEYS and isinstance(front[key], list):
            front[key] = " ".join(front[key])
    return front, j + 1


def _truthy(value, default: bool) -> bool:
    if value is None or value == "" or value == []:
        return default
    return str(value).strip().lower() not in ("false", "no", "off", "0")


def parse_letter(source: str) -> Letter:
    audit = Audit()
    text = source.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    text = re.sub(r"<!--\s*page\s*-?break\s*-->", f"\n\n{_PAGEBREAK}\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<!--\s*signature\s*-->", f"\n\n{_SIGNATURE}\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    lines = text.split("\n")
    front, start = parse_front_matter(lines, audit)

    smart = _truthy(front.get("smart_quotes"), True)
    inline = InlineParser(smart, audit)
    style = _LABEL_STYLES.get(str(front.get("exhibit_labels") or "letters").strip().lower())
    if style is None:
        raise ToolError(f"exhibit_labels must be 'letters' or 'numbers' (got {front.get('exhibit_labels')!r}).")
    front["exhibit_labels"] = style
    offset = label_offset(str(front["exhibit_start"]), style) if front.get("exhibit_start") else 0
    raw_prefix = front.get("exhibit_prefix")
    prefix = "Exhibit" if raw_prefix is None else (str(raw_prefix).strip() if raw_prefix else "")

    blocks: list[Block] = []
    exhibits: list[Exhibit] = []
    para: list[str] = []
    h2_count = 0
    body = lines[start:]
    n = len(body)

    def flush() -> None:
        if para:
            joined = " ".join(s.strip() for s in para)
            if joined.lstrip().startswith("|"):
                audit.error("Unsupported table", "Tables are not supported; a table was rendered as plain text. Use a list.")
            blocks.append(Block("para", inline(joined)))
            para.clear()

    i = 0
    while i < n:
        line = body[i]
        s = line.strip()
        fence = re.match(r"^(```|~~~)\s*([\w-]*)\s*(.*)$", s)
        if fence:
            flush()
            closer = fence.group(1)
            info = fence.group(2).lower()
            j = i + 1
            while j < n and body[j].strip() != closer:
                j += 1
            if j >= n:
                raise ToolError(
                    f"The {closer}{info} block that starts on body line {i + 1} is never closed. "
                    f"Add a line containing only {closer} after the last exhibit."
                )
            inner = body[i + 1 : j]
            if info in ("exhibits", "exhibit"):
                _parse_exhibits(inner, blocks, exhibits, inline, style, offset, prefix, audit)
            else:
                audit.error(
                    "Unresolved Markdown",
                    f"Fenced block '{closer}{info}' is not part of the dialect; its lines were rendered as plain "
                    "paragraphs. Use ```exhibits for the exhibit list.",
                )
                for raw in inner:
                    if raw.strip():
                        blocks.append(Block("para", inline(raw.strip())))
            i = j + 1
            continue
        if not s:
            flush()
            i += 1
            continue
        if s in (_PAGEBREAK, _SIGNATURE):
            flush()
            blocks.append(Block("pagebreak" if s == _PAGEBREAK else "signature"))
            i += 1
            continue
        hm = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", s)
        if hm:
            flush()
            level = len(hm.group(1))
            title = hm.group(2)
            if level == 1:
                h2_count = 0
                blocks.append(Block("h1", inline(title, bold=True)))
            elif level == 2:
                h2_count += 1
                title = _LOWER_ROMAN_RE.sub("", title, count=1)
                blocks.append(Block("h2", inline(title, italic=True), marker=f"{to_roman(h2_count).lower()}."))
            else:
                if level > 3:
                    audit.warn("Heading too deep", f"Level-{level} heading {title!r} was rendered like ### (bold, unnumbered).")
                blocks.append(Block("h3", inline(title, bold=True)))
            i += 1
            continue
        if s.startswith(">"):
            flush()
            quote_lines: list[str] = []
            while i < n and body[i].strip().startswith(">"):
                quote_lines.append(re.sub(r"^>\s?", "", body[i].strip()))
                i += 1
            chunk: list[str] = []
            for ql in quote_lines + [""]:
                if ql.strip():
                    chunk.append(ql.strip())
                elif chunk:
                    blocks.append(Block("quote", inline(" ".join(chunk))))
                    chunk = []
            continue
        bullet = re.match(r"^[-*+]\s+(.*)$", s)
        number = re.match(r"^(\d{1,3})[.)]\s+(.*)$", s) if not para else None
        if bullet or number:
            flush()
            kind = "bullet" if bullet else "number"
            pattern = r"^[-*+]\s+(.*)$" if bullet else r"^\d{1,3}[.)]\s+(.*)$"
            first_no = int(number.group(1)) if number else 1
            items: list[list[str]] = []
            while i < n:
                cur = body[i]
                cs = cur.strip()
                im = re.match(pattern, cs)
                if im:
                    items.append([im.group(1)])
                elif cs and cur[:1] == " " and items:
                    items[-1].append(cs)
                elif not cs and i + 1 < n and re.match(pattern, body[i + 1].strip()):
                    pass  # blank line between items of the same list
                else:
                    break
                i += 1
            for k, item in enumerate(items):
                marker = "•" if kind == "bullet" else f"{first_no + k}."
                blocks.append(
                    Block(kind, inline(" ".join(item)), marker=marker,
                          first_in_group=k == 0, last_in_group=k == len(items) - 1)
                )
            continue
        para.append(s)
        i += 1
    flush()

    if not any(b.kind not in ("pagebreak", "signature") for b in blocks):
        audit.error("Empty letter body", "There is no text after the front matter.")
    if not front.get("to"):
        audit.error("Missing USCIS address block", "Add a front-matter 'to:' list with the USCIS address lines.")
    if not front.get("re"):
        audit.error("Missing RE block", "Add a front-matter 're:' list (form, petitioner, beneficiary, receipt number).")
    if not front.get("date"):
        today = _today()
        front["date"] = f"{today:%B} {today.day}, {today.year}"
        audit.warn("Missing date", f"No 'date:' in the front matter; today's date ({front['date']}) was used.")

    hang = _exhibit_hang([e.display for e in exhibits])
    return Letter(front, blocks, exhibits, audit, hang, prefix)


def _parse_exhibits(lines, blocks, exhibits, inline, style, offset, prefix, audit: Audit) -> None:
    section: str | None = None
    hand_labels: set[str] = set()
    pending: list[tuple[str, object]] = []  # ("section", text) or ("item", [lines])
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        hm = re.match(r"^#{1,6}\s+(.*)$", s)
        im = re.match(r"^(?:[-*+]|\d{1,3}[.)])\s+(.*)$", s)
        if hm:
            pending.append(("section", hm.group(1).strip()))
        elif im:
            pending.append(("item", [im.group(1).strip()]))
        elif raw[:1] == " " and pending and pending[-1][0] == "item":
            pending[-1][1].append(s)
        elif s.endswith(":"):
            pending.append(("section", s))
        else:
            audit.warn(
                "Unrecognized exhibit-list line",
                f"{s!r} is neither '# Section' nor '- item'; it was treated as an exhibit item.",
            )
            pending.append(("item", [s]))
    if not any(kind == "item" for kind, _ in pending):
        audit.error("Empty exhibit list", "The ```exhibits block has no '- item' lines.")
    first_block = len(blocks)
    for kind, payload in pending:
        if kind == "section":
            section = str(payload)
            blocks.append(Block("exh_section", inline(section, bold=True)))
            continue
        desc = " ".join(payload)  # type: ignore[arg-type]
        label = exhibit_label(offset + len(exhibits), style)
        hand = _HAND_LABEL_RE.match(desc)
        if hand:
            written = hand.group(1).upper()
            desc = desc[hand.end():]
            if written in hand_labels:
                audit.error(
                    "Duplicate exhibit label",
                    f"Two exhibit items were written as {prefix} {written}. Labels are assigned in order; "
                    "remove hand-written labels and check the body citations.",
                )
            elif written != label.upper():
                audit.error(
                    "Exhibit label mismatch",
                    f"{desc[:50]!r} was written as {prefix} {written} but is {prefix} {label} in the rendered list "
                    "(labels are assigned in order, so a label was skipped or repeated). Remove hand-written labels "
                    "and make the body citations match the rendered list.",
                )
            else:
                audit.note(f"Removed the hand-written label {prefix} {written}; it matched the assigned label.")
            hand_labels.add(written)
        display = f"{prefix} {label}".strip()
        runs = inline(desc)
        exhibits.append(Exhibit(label, display, section, plain(runs)))
        blocks.append(Block("exh_item", runs, marker=display))
    if len(blocks) > first_block:
        blocks[first_block].first_in_group = True
        blocks[-1].last_in_group = True


def _exhibit_hang(displays: list[str]) -> float:
    """Width (inches) from the exhibit label's left edge to the description's left edge."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    widest = max((stringWidth(d, "Times-Roman", BODY_PT) for d in displays), default=0) / 72
    hang = max(0.875, widest + 0.2)
    return round(hang * 8 + 0.4999) / 8  # round up to 1/8"


# ---------------------------------------------------------------------------
# Attorney profile
# ---------------------------------------------------------------------------
def load_profile(path: Path | None, audit: Audit) -> dict:
    if path is None:
        audit.note("No attorney profile given (--profile); the letterhead and signature details were left out.")
        return {}
    if not path.is_file():
        raise ToolError(f"Attorney profile not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ToolError(f"Attorney profile {path} is not valid JSON (line {exc.lineno}: {exc.msg}).") from None
    if not isinstance(data, dict):
        raise ToolError(f"Attorney profile {path} must be a JSON object with keys like attorney_name and firm_name.")
    profile: dict = {}
    for key, value in data.items():
        if key not in PROFILE_KEYS:
            audit.note(f"Unknown attorney-profile key {key!r} was ignored.")
            continue
        if value is None:
            continue
        if key == "mailing_address":
            lines = value if isinstance(value, list) else str(value).split("\n")
            lines = [str(x).strip() for x in lines if str(x).strip()]
            if len(lines) == 1:
                m = re.match(r"^(.*\S)\s*,\s*([^,]+,\s*[A-Z]{2}\.?\s+\d{5}(?:-\d{4})?)$", lines[0])
                if m:
                    lines = [m.group(1), m.group(2)]
            if lines:
                profile[key] = lines
        else:
            text = str(value).strip()
            if text:
                profile[key] = text
    missing = [k for k in PROFILE_KEYS if k not in profile]
    if missing:
        audit.note(f"Attorney profile has no {', '.join(missing)}; those lines were omitted.")
    return profile


def letterhead_lines(profile: dict) -> list[tuple[str, str]]:
    """(kind, text) pairs: kind is 'firm', 'name' or 'detail'."""
    out: list[tuple[str, str]] = []
    firm, name = profile.get("firm_name"), profile.get("attorney_name")
    if firm:
        out.append(("firm", firm))
        if name:
            out.append(("name", name))
    elif name:
        out.append(("firm", name))
    if profile.get("mailing_address"):
        out.append(("detail", "  ·  ".join(profile["mailing_address"])))
    contact = [x for x in (_phone(profile), profile.get("email")) if x]
    if contact:
        out.append(("detail", "  ·  ".join(contact)))
    return out


def _phone(profile: dict) -> str | None:
    phone = profile.get("phone")
    return f"Tel. {phone}" if phone and not re.match(r"^(tel|phone|ph)\b", phone, re.IGNORECASE) else phone


def signature_lines(profile: dict, front: dict) -> list[tuple[str, str]]:
    """(kind, text) pairs after the closing: kind is 'name' or 'detail'."""
    out: list[tuple[str, str]] = []
    if profile.get("attorney_name"):
        out.append(("name", profile["attorney_name"]))
    if front.get("signer_title"):
        out.append(("detail", str(front["signer_title"])))
    if profile.get("firm_name"):
        out.append(("detail", profile["firm_name"]))
    out += [("detail", x) for x in (*profile.get("mailing_address", []), _phone(profile), profile.get("email")) if x]
    bar, auth = profile.get("bar_number"), profile.get("licensing_authority")
    if bar and auth:
        out.append(("detail", f"Bar No. {bar} ({auth})"))
    elif bar:
        out.append(("detail", f"Bar No. {bar}"))
    elif auth:
        out.append(("detail", f"Licensing authority: {auth}"))
    return out


# ---------------------------------------------------------------------------
# The letter as paragraphs. Both renderers draw this one list.
# ---------------------------------------------------------------------------
@dataclass
class Para:
    """One paragraph, in the terms both renderers share: inches for indents, points for spacing."""

    runs: list[Run]
    align: str = "left"  # left, center or justify
    left: float = 0.0  # where the text starts
    right: float = 0.0
    first: float = 0.0  # first-line indent of a paragraph without a marker
    before: float = 0.0
    after: float = 0.0
    keep_next: bool = False
    size: float | None = None  # font size, when not the body's
    marker: Run | None = None  # the "RE:", numeral, bullet or exhibit label hanging at marker_at
    marker_at: float = 0.0
    typed: bool = False  # the .docx types the marker and its tab into the text (the cc: lines)
    rule_below: bool = False  # the letterhead's rule, then RULE_AFTER_PT


PAGEBREAK = "pagebreak"


def letter_paragraphs(letter: Letter, profile: dict, inline: InlineParser) -> list:
    """The letter in order: each item a Para, PAGEBREAK, or a list of Paras kept on one page (the signature)."""
    front = letter.front
    head = letterhead_lines(profile)
    out: list = [Para([Run(text, bold=kind == "firm")], align="center", size=LETTERHEAD_PT[kind],
                      after=2 if kind == "firm" else 0, rule_below=n == len(head) - 1) for n, (kind, text) in enumerate(head)]
    out.append(Para([Run(str(front["date"]))], after=12))
    if front.get("delivery"):
        out.append(Para(inline(str(front["delivery"]), italic=True), after=12))
    to_lines, re_lines = front.get("to") or [], front.get("re") or []
    out += [Para(inline(line), after=12 if n == len(to_lines) - 1 else 0) for n, line in enumerate(to_lines)]
    out += [Para(inline(line, bold=True), left=RE_HANG, after=12 if n == len(re_lines) - 1 else 0,
                 marker=Run("RE:", bold=True) if n == 0 else None) for n, line in enumerate(re_lines)]
    out.append(Para(inline(str(front.get("salutation") or "Dear Sir or Madam:")), after=12))
    signed = False
    for b in letter.blocks:
        group_after = 12 if b.last_in_group else 6
        if b.kind == "para":
            out.append(Para(b.runs, align="justify", first=PARA_INDENT, after=12))
        elif b.kind in ("h1", "exh_section"):
            before, after = (6, 12) if b.kind == "h1" else (0 if b.first_in_group else 12, 6)
            out.append(Para([Run(r.text, True, r.italic, True) for r in b.runs], before=before, after=after, keep_next=True))
        elif b.kind == "h2":
            out.append(Para(b.runs, left=H2_TEXT_AT, after=12, keep_next=True, marker=Run(b.marker, italic=True),
                            marker_at=H2_LABEL_AT))
        elif b.kind == "h3":
            out.append(Para(b.runs, after=12, keep_next=True))
        elif b.kind == "quote":
            out.append(Para(b.runs, align="justify", left=QUOTE_INDENT, right=QUOTE_INDENT, after=12))
        elif b.kind in ("bullet", "number"):
            out.append(Para(b.runs, align="justify", left=LIST_TEXT_AT, after=group_after, marker=Run(b.marker),
                            marker_at=LIST_LABEL_AT))
        elif b.kind == "exh_item":
            out.append(Para(b.runs, left=EXHIBIT_LABEL_AT + letter.exhibit_hang, after=group_after, marker=Run(b.marker),
                            marker_at=EXHIBIT_LABEL_AT))
        elif b.kind == "pagebreak":
            out.append(PAGEBREAK)
        elif b.kind == "signature" and not signed:
            out += _signature(letter, profile, inline)
            signed = True
    return out if signed else out + _signature(letter, profile, inline)


def _signature(letter: Letter, profile: dict, inline: InlineParser) -> list:
    """The closing and the signature lines, kept on one page, then the cc lines."""
    lines = signature_lines(profile, letter.front)
    kept = [Para(inline(str(letter.front.get("closing") or "Respectfully submitted,")), keep_next=True)]
    kept += [Para([Run(text, bold=kind == "name")], before=SIGNATURE_GAP_PT if n == 0 else 0, keep_next=n < len(lines) - 1)
             for n, (kind, text) in enumerate(lines)] or [Para([Run("")], before=SIGNATURE_GAP_PT)]
    return [kept] + [Para(inline(line), left=0.5, before=12 if n == 0 else 0, marker=Run("cc:" if n == 0 else ""), typed=True)
                     for n, line in enumerate(letter.front.get("cc") or [])]


def _title_and_author(letter: Letter, profile: dict, inline: InlineParser) -> tuple[str, str]:
    title = plain(inline(letter.front["re"][0])) if letter.front.get("re") else "Cover letter"
    return title, profile.get("attorney_name") or profile.get("firm_name") or ""


# ---------------------------------------------------------------------------
# DOCX renderer
# ---------------------------------------------------------------------------
def build_docx(letter: Letter, profile: dict, inline: InlineParser, out_path: Path, pdf_bound: bool = False) -> None:
    """Write the .docx. pdf_bound=True adds invisible word joiners inside citations such as
    201(b)(2)(A)(i) so LibreOffice does not break the line between ")" and "(" (Word never
    does); that copy is only used for PDF conversion, so the editable .docx stays clean."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(PAGE_W), Inches(PAGE_H)
    sec.left_margin = sec.right_margin = sec.top_margin = sec.bottom_margin = Inches(MARGIN)
    sec.header_distance = sec.footer_distance = Inches(0.5)

    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(BODY_PT)
    rpr = normal.element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.append(fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(attr), "Times New Roman")
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        fonts.attrib.pop(qn(attr), None)
    npf = normal.paragraph_format
    npf.space_before = Pt(0)
    npf.space_after = Pt(0)
    npf.line_spacing = 1.0
    npf.widow_control = True
    try:
        doc.styles["Footer"].font.size = Pt(10)
    except KeyError:
        pass

    align = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}
    break_before = False
    for item in letter_paragraphs(letter, profile, inline):
        if item is PAGEBREAK:
            break_before = True
            continue
        for para in item if isinstance(item, list) else [item]:  # Word keeps the signature together with keep_next
            p = doc.add_paragraph()
            pf = p.paragraph_format
            first = -(para.left - para.marker_at) if para.marker is not None else para.first
            pf.alignment = align[para.align]
            pf.first_line_indent = Inches(first) if first else None
            pf.left_indent = Inches(para.left) if para.left else None
            pf.right_indent = Inches(para.right) if para.right else None
            pf.space_before = Pt(para.before)
            pf.space_after = Pt(RULE_AFTER_PT if para.rule_below else para.after)
            pf.keep_with_next = para.keep_next
            pf.widow_control = True
            if break_before:
                pf.page_break_before = True
                break_before = False
            runs = para.runs
            if para.marker is not None:
                pf.tab_stops.add_tab_stop(Inches(para.left), WD_TAB_ALIGNMENT.LEFT)
                lead = replace(para.marker, text=para.marker.text + "\t")
                runs = merge_runs([lead, *runs]) if para.typed else [lead, *runs]
            if pdf_bound:
                runs = [replace(r, text=r.text.replace(")(", ")⁠(")) for r in runs]
            docx_runs(p, runs, para.size)
            if para.rule_below:
                bdr, bottom = OxmlElement("w:pBdr"), OxmlElement("w:bottom")
                for k, v in (("w:val", "single"), ("w:sz", "6"), ("w:space", "4"), ("w:color", "000000")):
                    bottom.set(qn(k), v)
                bdr.append(bottom)
                p._p.get_or_add_pPr().append(bdr)

    # Footer "Page N of M" on pages 2+
    if _truthy(letter.front.get("page_numbers"), True):
        sec.different_first_page_header_footer = True
        fp = sec.footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER

        def field(instr: str) -> None:
            fld, r, rpr_, sz, t = (OxmlElement(tag) for tag in ("w:fldSimple", "w:r", "w:rPr", "w:sz", "w:t"))
            fld.set(qn("w:instr"), instr)
            sz.set(qn("w:val"), "20")
            t.text = "1"
            rpr_.append(sz)
            r.append(rpr_)
            r.append(t)
            fld.append(r)
            fp._p.append(fld)

        fp.add_run("Page ").font.size = Pt(10)
        field("PAGE")
        fp.add_run(" of ").font.size = Pt(10)
        field("NUMPAGES")

    props = doc.core_properties
    props.title, props.author = _title_and_author(letter, profile, inline)
    props.last_modified_by = props.author
    props.comments = ""
    props.created = props.modified = _dt.datetime.now().replace(microsecond=0)
    doc.save(str(out_path))


# ---------------------------------------------------------------------------
# reportlab renderer (used when LibreOffice is not installed)
# ---------------------------------------------------------------------------
def build_pdf_reportlab(letter: Letter, profile: dict, inline: InlineParser, out_path: Path) -> str:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import HRFlowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer

    fonts = register_serif_fonts()
    align = {"left": TA_LEFT, "center": TA_CENTER, "justify": TA_JUSTIFY}

    def flowable(p: Para, before: float | None = None, keep: bool | None = None) -> Paragraph:
        marker = p.marker or Run("")
        style = ParagraphStyle(
            "p", fontName=fonts.regular, fontSize=p.size or BODY_PT, leading=LEADING_FOR.get(p.size, LEADING),
            alignment=align[p.align], allowWidows=0, allowOrphans=0, firstLineIndent=p.first * inch,
            leftIndent=p.left * inch, rightIndent=p.right * inch, spaceBefore=p.before if before is None else before,
            spaceAfter=p.after, keepWithNext=int(p.keep_next if keep is None else keep), bulletIndent=p.marker_at * inch,
            bulletFontName=fonts.bold if marker.bold else fonts.italic if marker.italic else fonts.regular,
            bulletFontSize=BODY_PT,
        )
        return Paragraph(markup(p.runs), style, bulletText=marker.text or None)

    story: list = []
    for item in letter_paragraphs(letter, profile, inline):
        if item is PAGEBREAK:
            story.append(PageBreak())
        elif isinstance(item, list):
            # Kept on one page, spaced with a Spacer; the gap left for a signature with no lines is only its space.
            kept = []
            for p in item:
                if p.before:
                    kept.append(Spacer(1, p.before))
                if plain(p.runs):
                    kept.append(flowable(p, before=0, keep=False))
            story.append(KeepTogether(kept))
        else:
            story.append(flowable(item))
            if item.rule_below:
                story.append(HRFlowable(width="100%", thickness=0.75, color=colors.black, spaceBefore=5,
                                        spaceAfter=RULE_AFTER_PT))

    title, author = _title_and_author(letter, profile, inline)
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=(PAGE_W * inch, PAGE_H * inch),
        leftMargin=MARGIN * inch, rightMargin=MARGIN * inch,
        topMargin=MARGIN * inch, bottomMargin=MARGIN * inch,
        title=title, author=author, creator="render_letter.py (reportlab)",
    )
    show_numbers = _truthy(letter.front.get("page_numbers"), True)
    doc.build(story, canvasmaker=numbered_canvas(fonts.regular, 10, lambda page, total: show_numbers and page > 1))

    front = letter.front
    all_text = " ".join(plain(b.runs) for b in letter.blocks) + json.dumps(front, ensure_ascii=False) + json.dumps(profile, ensure_ascii=False)
    bad = unsupported_chars(all_text, fonts)
    if bad:
        letter.audit.error(
            "Characters the PDF font cannot draw",
            "The reportlab fallback font shows these as boxes: " + " ".join(sorted(bad))
            + ". Install LibreOffice, or Times New Roman / Liberation Serif, and render again.",
        )
    return fonts.description


# ---------------------------------------------------------------------------
# Cross-checks over the parsed letter
# ---------------------------------------------------------------------------
_CITE_KEY_RE = re.compile(r"\b(?i:exhibits?|exhs?\.|exs?\.|tabs?)[\s\u00a0]+")
# Only the label shapes this tool assigns: one letter repeated (A, AA, BBB) or a number.
_LABEL_RE = re.compile(r"([A-Z])\1*(?![A-Za-z])|\d{1,3}(?!\d)")
_DASHES = "-\u2013\u2014"
_CONNECTOR_RE = re.compile(
    r"[\s\u00a0]*(?:(?P<range>[-\u2013\u2014]|(?:to|through|thru)\b)"
    r"|(?P<list>,[\s\u00a0]*(?:and|&)\b|,[\s\u00a0]*&|,|and\b|&))[\s\u00a0]*"
)
# A number followed by a reporter is a citation, not an exhibit ("Exhibit 4 and 8 C.F.R. \u00a7 204.2").
_REPORTER_TAIL_RE = re.compile(
    r"[\s\u00a0]*(?:C\.?\s?F\.?\s?R\b|U\.?\s?S\.?\s?C\b|U\.\s?S\.|USCIS|I\s?&\s?N|Fed\.\s?Reg|F\.\s?(?:\d|Supp)"
    r"|S\.\s?Ct|Stat\.|Pub\.\s?L|INA\b)"
)
# A number followed by what it counts is a quantity, not an exhibit ("Exhibit 3, 12 photos").
_COUNT_TAIL_RE = re.compile(
    r"(?:[\s\u00a0]*%|[\s\u00a0]+(?:years?|months?|weeks?|days?|hours?|photos?|photographs?|pictures?|pages?|"
    r"statements?|cop(?:y|ies)|letters?|affidavits?|declarations?|children|percent|times|trips?|accounts?|"
    r"receipts?|bills?|returns?|documents?|records?|of)\b)",
    re.IGNORECASE,
)
_FORMS_SECTION_RE = re.compile(r"\s*(?:the\s+)?forms?\b", re.IGNORECASE)
_BODY_KINDS = ("para", "h1", "h2", "h3", "quote", "bullet", "number")
_CONTENT_KINDS = ("para", "quote", "bullet", "number", "exh_item", "exh_section")
_HEADING_LEVEL = {"h1": 1, "h2": 2, "h3": 3}


def _label_at(text: str, pos: int) -> tuple[str, int] | None:
    """The exhibit label starting at pos, or None when what is there is not a label.

    A label must end the word: "I-94", "I-485", "I&N", "IRS", "A1", "U.S.", "8 C.F.R.", "8 CFR"
    and "12 photos" are not labels. A dash glued to a label is allowed only when another label
    of the same kind follows it, as in "A-C" or "3-5".
    """
    m = _LABEL_RE.match(text, pos)
    if not m:
        return None
    end = m.end()
    nxt = text[end : end + 1]
    if nxt and nxt in _DASHES:
        after = _LABEL_RE.match(text, end + 1)
        if not after or after.group(0).isdigit() != m.group(0).isdigit():
            return None
        tail = text[after.end() : after.end() + 1]
        if tail and (tail.isalnum() or tail in "_&" or tail in _DASHES):
            return None
    elif nxt and (nxt.isalnum() or nxt in "_&"):
        return None
    if nxt == "." and len(m.group(0)) == 1 and text[end + 1 : end + 2].isalpha():
        return None  # "U.S.", an initial
    if _REPORTER_TAIL_RE.match(text, end):
        return None
    if m.group(0).isdigit() and _COUNT_TAIL_RE.match(text, end):
        return None
    return m.group(0), end


def cited_labels(text: str, style: str, known: set[str] | None = None) -> list[str]:
    """Exhibit labels cited in running text: 'Exhibit C', 'Exhibits F–H', 'Exs. 3 and 5'.

    After "Exhibit"/"Ex."/"Tab", labels are read one at a time, joined by a list word
    (",", "and", "&") or a range word (a dash, "to", "through"). A range counts only when
    both ends are labels of the same kind, so "Exhibit A to I-485" cites A alone and
    "Exhibit C, I-94 record" cites C alone. When known (the letter's exhibit labels) is
    given, a label after the first must be one of them, and a lone "A" or "I" followed by a
    word is read as the word it usually is ("Exhibit B, I am").
    """
    out: list[str] = []
    for km in _CITE_KEY_RE.finditer(text):
        first = _label_at(text, km.end())
        if first is None:
            continue
        labels = [first[0]]
        prev, pos = first
        while True:
            cm = _CONNECTOR_RE.match(text, pos)
            if not cm:
                break
            nxt = _label_at(text, cm.end())
            if nxt is not None and known is not None:
                if nxt[0] not in known:
                    nxt = None
                elif nxt[0] in ("A", "I") and re.match(r"[\s\u00a0]+[a-z]", text[nxt[1]:]) \
                        and not re.match(r"[\s\u00a0]+(?:and|to|through|thru|at)\b", text[nxt[1]:]):
                    nxt = None
            if cm.group("range"):
                if nxt is not None and prev.isdigit() == nxt[0].isdigit():
                    a, b = _label_index(prev, style), _label_index(nxt[0], style)
                    if a is not None and b is not None and a < b:
                        labels += [exhibit_label(i, style) for i in range(a + 1, b + 1)]
                    else:
                        labels.append(nxt[0])
                    prev, pos = nxt
                    continue
                break
            if nxt is None:
                break
            labels.append(nxt[0])
            prev, pos = nxt
        out += labels
    return out


def _from_roman(text: str) -> int:
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    total = 0
    for i, ch in enumerate(text):
        v = values[ch]
        total += -v if i + 1 < len(text) and values[text[i + 1]] > v else v
    return total


def audit_letter(letter: Letter, profile: dict) -> dict[str, bool]:
    """Add cross-check findings; return {label: cited_in_body}."""
    audit, blocks, style, prefix = letter.audit, letter.blocks, letter.front["exhibit_labels"], letter.prefix

    # Exhibit citations in the body versus the exhibit list.
    # Scan block by block so "Index of Exhibits" + the next heading "IV. Conclusion" is not read as "Exhibits IV".
    listed = [e.label for e in letter.exhibits]
    cited = [label for b in blocks if b.kind in _BODY_KINDS
             for label in cited_labels(plain(b.runs), style, set(listed))]
    name = lambda labels: ", ".join(f"{prefix} {x}".strip() for x in labels)  # noqa: E731
    missing = sorted(set(cited) - set(listed), key=lambda x: (_label_index(x, style) is None, _label_index(x, style) or 0, x))
    if missing:
        span = f"{listed[0]}-{listed[-1]}" if listed else "no exhibits"
        audit.error(
            "Exhibit cited but not listed",
            f"The body cites {name(missing)}, but the exhibit list has {span}. Fix the citation or add the exhibit.",
        )
    # The forms are enclosed, not argued, so an exhibit filed under a "Forms" section needs no citation.
    exempt = {e.label for e in letter.exhibits if e.section and _FORMS_SECTION_RE.match(e.section)}
    uncited = [x for x in listed if x not in set(cited) and x not in exempt]
    if cited and uncited:
        one = len(uncited) == 1
        audit.warn(
            "Exhibit listed but never cited",
            f"{name(uncited)} {'appears' if one else 'appear'} in the exhibit list but the body never cites "
            f"{'it' if one else 'them'}. Cite each exhibit where it supports the argument, or remove it from the list.",
        )
    if listed and not cited:
        audit.note("The body does not cite exhibits by label; the citation cross-check was skipped.")

    # Empty sections.
    for i, b in enumerate(blocks):
        if b.kind in _HEADING_LEVEL:
            level = _HEADING_LEVEL[b.kind]
            has_content = False
            for nb in blocks[i + 1 :]:
                if nb.kind in _HEADING_LEVEL and _HEADING_LEVEL[nb.kind] <= level:
                    break
                if nb.kind in _CONTENT_KINDS:
                    has_content = True
                    break
            if not has_content:
                title = (b.marker + " " if b.marker else "") + plain(b.runs)
                audit.warn("Empty section", f"Heading {title!r} has no text under it.")
        elif b.kind == "exh_section":
            nxt = blocks[i + 1] if i + 1 < len(blocks) else None
            if nxt is None or nxt.kind != "exh_item":
                audit.warn("Empty exhibit section", f"Exhibit-list section {plain(b.runs)!r} has no items under it.")

    # Major headings numbered I., II., III. in order.
    numerals = []
    for b in blocks:
        if b.kind == "h1":
            m = re.match(r"^([IVXLC]+)[.)]\s", plain(b.runs))
            if m:
                numerals.append((m.group(1), _from_roman(m.group(1))))
    for (prev_txt, prev), (cur_txt, cur) in zip(numerals, numerals[1:]):
        if cur != prev + 1:
            audit.warn(
                "Heading numbering out of order",
                f"Major heading {cur_txt}. follows {prev_txt}.; number the # headings I., II., III. in order.",
            )
    if numerals and numerals[0][1] != 1:
        audit.warn("Heading numbering out of order", f"The first numbered major heading is {numerals[0][0]}., not I.")

    # Signature.
    if not profile.get("attorney_name"):
        audit.error(
            "Missing signature",
            "The signature block has no attorney name. Pass --profile with attorney_name (and firm details).",
        )
    markers = sum(1 for b in blocks if b.kind == "signature")
    if markers > 1:
        audit.warn("Repeated signature marker", f"<!-- signature --> appears {markers} times; only the first was used.")

    cited_set = set(cited)
    return {label: label in cited_set for label in listed}


# ---------------------------------------------------------------------------
# Content checks: date, computed phrases, length, filing method
# ---------------------------------------------------------------------------
_DATE_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%b. %d, %Y", "%d %B %Y", "%Y-%m-%d", "%m/%d/%Y")


def parse_letter_date(value) -> _dt.date | None:
    """The letter's front-matter date as a date, or None when it can't be read."""
    s = " ".join(str(value or "").replace(" ", " ").split())
    s = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", s)
    s = re.sub(r"\bSept\b", "Sep", s)
    for fmt in _DATE_FORMATS:
        try:
            return _dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


_UNITS = "one|two|three|four|five|six|seven|eight|nine"
_NUM = (
    r"(?:\d{1,3}|(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](?:" + _UNITS + r"))?"
    r"|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|" + _UNITS + r")"
)
_SPAN = r"(?:years?|months?|weeks?|days?)"
_COMPUTED_RES = (
    ("age", re.compile(r"\b" + _NUM + r"[- ]years?[- ]old\b", re.IGNORECASE)),
    ("age", re.compile(r"\b(?:aged?|age of)\s+" + _NUM + r"\b", re.IGNORECASE)),
    ("duration", re.compile(
        r"\b" + _NUM + r"[- ]" + _SPAN + r"(?:[- ]long)?[- ](?:marriage|relationship|courtship|engagement|separation"
        r"|residence|union|cohabitation|stay|absence|trip|gap|history)\b", re.IGNORECASE)),
    ("duration", re.compile(
        r"\b(?:for|over|nearly|almost|more than|about|approximately|past|last)\s+" + _NUM + r"\s+" + _SPAN + r"\b",
        re.IGNORECASE)),
    ("duration", re.compile(
        r"\b" + _NUM + r"\s+" + _SPAN + r"\s+(?:of\s+marriage|together|married|ago|of\s+(?:continuous\s+)?residence)\b",
        re.IGNORECASE)),
)


# A sentence that states the law rather than a fact about the client: it cites an authority,
# states a rule ("must", "is required"), or speaks of the agency without naming a party.
_AUTHORITY_RE = re.compile(
    r"\bMatter of\b|\bI\s?&\s?N\s?Dec\.|\bU\.\s?S\.\s?C\.|\bC\.\s?F\.\s?R\.|\bINA\s*(?:§|section\s+|sec\.\s*)?\d{3}"
    r"|\bUSCIS-PM\b|\bPolicy Manual\b|\bP[AM]-\d{3}-\d{4}\b|\bPA-\d{4}-\d{2}\b|\bPolicy Alert\b|\bFed\.\s?Reg\."
    r"|\bPub\.\s?L\.|\b\d+\s+F\.\s?(?:2d|3d|4th|Supp)|\b\d+\s+U\.\s?S\.\s+\d|\bv\.\s+[A-Z]"
)
_RULE_RE = re.compile(
    r"\b(?:must|shall|may not|cannot|is required|are required|required to|requires that|is eligible|are eligible|"
    r"eligibility|the statute|the regulations?|the Act)\b",
    re.IGNORECASE,
)
_AGENCY_RE = re.compile(r"\b(?:USCIS|DHS|Congress|(?i:the)\s+(?:Board|Service|Department|agency))\b")
_PARTY_RE = re.compile(
    r"\b(?:Mr|Ms|Mrs|Dr)\.|\b(?:petitioner|beneficiary|applicant|couple|client|spouse|husband|wife|son|daughter|"
    r"she|he|they|her|his|their|them)\b",
    re.IGNORECASE,
)
# Statutory periods and deadlines are law: "within 90 days", "the two-year period".
_PERIOD_LAW_RE = re.compile(
    r"\b(?:within|during(?:\s+the)?)\s+(?:\d{1,3}|[a-z]+(?:-[a-z]+)?)[- ](?:days?|weeks?|months?|years?)\b"
    r"|\b(?:\d{1,3}|[a-z]+(?:-[a-z]+)?)[- ](?:day|week|month|year)s?[- ]period\b",
    re.IGNORECASE,
)


def is_legal_statement(sentence: str) -> bool:
    """True when a sentence states the law (a citation, a rule, the agency's practice), not a client fact."""
    if _AUTHORITY_RE.search(sentence) or _RULE_RE.search(sentence):
        return True
    return bool(_AGENCY_RE.search(sentence) and not _PARTY_RE.search(sentence))


def computed_phrases(letter: Letter) -> list[dict]:
    """Ages and durations in the body, which go stale and must be recomputed against the documents."""
    found: list[dict] = []
    seen: set[tuple[int, int, int]] = set()
    for bi, b in enumerate(letter.blocks):
        if b.kind not in _BODY_KINDS:
            continue
        text = plain(b.runs)
        law_spans = [(p.start(), p.end()) for p in _PERIOD_LAW_RE.finditer(text)]
        for kind, rx in _COMPUTED_RES:
            for m in rx.finditer(text):
                if any(bi == s[0] and m.start() < s[2] and s[1] < m.end() for s in seen):
                    continue  # overlaps a phrase already found
                seen.add((bi, m.start(), m.end()))
                a = max(0, text.rfind(".", 0, m.start()) + 1)
                z = text.find(".", m.end())
                context = text[a : (z + 1 if z != -1 else len(text))].strip()
                if is_legal_statement(context) or any(a2 < m.end() and m.start() < z2 for a2, z2 in law_spans):
                    continue  # the law's own periods ("for five years" in a rule) don't go stale
                if len(context) > 160:
                    context = context[:157].rstrip() + "..."
                found.append({"text": m.group(0), "kind": kind, "context": context})
    return found


_WORD_KINDS = ("para", "quote", "bullet", "number")


def _matter_type_key(value) -> str:
    s = str(value or "").strip().lower()
    s = re.sub(r"[\s/]+", "_", s).replace("-", "")
    return s


def audit_content(letter: Letter) -> dict:
    """Date, computed-phrase, length and filing-method checks. Returns the facts the summary reports."""
    audit, front = letter.audit, letter.front
    today = _today()
    info = dict.fromkeys(("matter_type", "filing_method", "protected", "filing_location", "word_count", "length_budget",
                          "letter_date", "render_date", "computed_phrases"))  # in the summary's order
    info["render_date"] = today.isoformat()

    # A letter dated more than a week from the day it is rendered is stale (or post-dated).
    letter_date = parse_letter_date(front.get("date"))
    info["letter_date"] = letter_date.isoformat() if letter_date else None
    if letter_date is None:
        audit.warn(
            "Unreadable date",
            f"The front-matter date {str(front.get('date'))!r} isn't a date like 'October 28, 2026', so its age "
            "couldn't be checked. Write it as Month D, YYYY.",
        )
    else:
        offset = (letter_date - today).days
        if abs(offset) > STALE_DATE_DAYS:
            when = f"{-offset} days before" if offset < 0 else f"{offset} days after"
            audit.warn(
                "Letter date is stale",
                f"The letter is dated {front['date']}, {when} today. Date it for the day it will be signed, and "
                "recompute every age and duration in it as of that day.",
            )

    phrases = computed_phrases(letter)
    info["computed_phrases"] = phrases
    if phrases:
        shown = "; ".join(repr(p["text"]) for p in phrases[:4]) + (" ..." if len(phrases) > 4 else "")
        audit.note(
            f"{len(phrases)} age or duration phrase{'s' if len(phrases) != 1 else ''} ({shown}) must be recomputed "
            "from the documents as of the letter's date; the list is in computed_phrases."
        )

    # Length against the matter type's budget.
    words = sum(len(plain(b.runs).split()) for b in letter.blocks if b.kind in _WORD_KINDS)
    info["word_count"] = words
    matter_type = _matter_type_key(front.get("matter_type")) if front.get("matter_type") else None
    info["matter_type"] = matter_type
    budget = None
    if front.get("length_budget"):
        raw = str(front["length_budget"]).replace(",", "").strip()
        if raw.isdigit() and int(raw) > 0:
            budget = int(raw)
        else:
            audit.warn("Unreadable length budget", f"length_budget must be a whole number of words (got {front['length_budget']!r}).")
    elif matter_type in LENGTH_BUDGETS:
        budget = LENGTH_BUDGETS[matter_type]
    elif matter_type and matter_type not in UNBUDGETED_TYPES:
        audit.warn(
            "Unknown matter type",
            f"matter_type {front['matter_type']!r} isn't one of {', '.join(sorted(LENGTH_BUDGETS))}, "
            f"{', '.join(sorted(UNBUDGETED_TYPES))}; the length wasn't checked.",
        )
    elif not matter_type:
        audit.note("No matter_type in the front matter, so the letter's length wasn't checked against a budget.")
    info["length_budget"] = budget
    if budget and words > budget:
        audit.warn(
            "Letter longer than its budget",
            f"The argument runs {words:,} words; the budget for this matter type is {budget:,}. Cut what the record "
            "doesn't need (an issue the record doesn't raise is a question for the attorney, not a section), or set "
            "length_budget when the attorney wants the longer letter.",
        )

    # An online filing has no mailing logistics.
    method = str(front.get("filing_method") or "paper").strip().lower()
    info["filing_method"] = method
    if method not in ("paper", "online"):
        audit.warn("Unknown filing method", f"filing_method must be paper or online (got {front.get('filing_method')!r}).")
    elif method == "online":
        mailing = [line for line in front.get("to") or []
                   if re.search(r"\b\d{5}(?:-\d{4})?\b|\bP\.?\s?O\.?\s+Box\b|\bAttn\b|\bLockbox\b", line, re.IGNORECASE)]
        if front.get("delivery") or mailing:
            what = "the delivery line" if front.get("delivery") else "a mailing address in the 'to' block"
            audit.warn(
                "Mailing details in an online filing",
                f"This letter is for an online filing but has {what}. Address it to U.S. Citizenship and "
                "Immigration Services only, with no delivery line, lockbox or street address (a protected "
                "matter too: online there is no Attn: 1367 lockbox).",
            )

    # Where a paper filing goes is the lead form's address page's call, by form and basis
    # (filing_locations.py): a VAWA, T or U filing of certain forms goes to the "Attn: 1367" lockbox,
    # an I-751 abuse waiver to the I-751's own lockbox. The letter names the location it chose.
    named = filing_locations.normalize_location(front.get("filing_location"))
    rule = filing_locations.route(front.get("lead_form") or "", front.get("filing_basis") or "")
    has_basis = bool(rule["form"] and rule["basis"])
    info["filing_location"] = {"named": named or None, "expected": rule["location"], "lead_form": rule["form"],
                               "filing_basis": rule["basis"], "page": rule["page"]}
    protected = _truthy(front.get("protected"), False)
    info["protected"] = protected
    to_1367 = any(re.search(r"\b1367\b", line) for line in front.get("to") or [])
    if method == "online":
        if named and named != filing_locations.ONLINE:
            audit.warn(
                "Filing location in an online filing",
                "An online filing is submitted in the online account: there is no lockbox or address. Set "
                "filing_location to online, or leave it out.",
            )
    elif method == "paper":
        if named == filing_locations.ONLINE:
            audit.warn("Online filing location on a paper filing",
                       "filing_location says online, but filing_method is paper. Make them agree.")
            named = ""
        if (front.get("lead_form") or front.get("filing_basis")) and rule["location"] is None:
            audit.note(f"Filing location not checked by the tools: {rule['rule']}")
        elif rule["location"] and named and named != rule["location"]:
            say = {filing_locations.LOCKBOX: "the \"Attn: 1367\" lockbox for the client's state "
                                             f"({filing_locations.LOCKBOX_PAGE})",
                   filing_locations.FORM_PAGE: f"the {rule['form']}'s own address page ({rule['page']}), not the "
                                               "1367 lockbox"}
            audit.error(
                "Filing location doesn't match the form and its basis",
                f"The letter names {say[named]}, but a {rule['basis']} {rule['form']} goes to "
                f"{say[rule['location']]} (that page, updated {rule['updated']}). Fix filing_location and the "
                "'to' block, or the lead form and basis.",
            )
        if (protected or rule["location"] == filing_locations.LOCKBOX) and not named:
            audit.warn(
                "Filing location not named",
                "Name where this paper filing goes: filing_location: 1367 lockbox when the lead form's address page "
                "sends this basis to uscis.gov/Certain-VAWA-T-U-Filing-Locations, or filing_location: form page "
                "(an I-751 abuse waiver goes to the I-751's own lockbox), with lead_form and filing_basis.",
            )
        if protected and not has_basis:
            audit.warn(
                "Filing basis not named",
                "Put lead_form (the form whose address page decides where the package goes, for example I-360 or "
                "I-485) and filing_basis (vawa, t, u, cuban_adjustment_abused, hrifa_battered, abuse_waiver or "
                "other) in the front matter, so the filing location can be checked.",
            )
        where = named or rule["location"]
        if where == filing_locations.LOCKBOX and not to_1367:
            audit.warn(
                "Letter not addressed to the 1367 lockbox",
                "This filing goes to the \"Attn: 1367\" lockbox for the client's state of residence "
                "(uscis.gov/Certain-VAWA-T-U-Filing-Locations). Put it in the 'to' block.",
            )
        elif where == filing_locations.FORM_PAGE and to_1367:
            page = f" ({rule['page']})" if rule["page"] else ""
            audit.error(
                "Letter addressed to the 1367 lockbox",
                "The 'to' block names the \"Attn: 1367\" lockbox, but this filing goes to the form's own address "
                f"page{page}. Address it there.",
            )

    # A protected matter (8 U.S.C. 1367): on paper and online alike, the letter invokes it and asks
    # USCIS to use the safe mailing address.
    if protected:
        body = " ".join(plain(b.runs) for b in letter.blocks if b.kind in _BODY_KINDS)
        if not re.search(r"\b1367\b", body):
            audit.warn(
                "Protected matter without 8 U.S.C. 1367",
                "This is a protected matter, but the letter never invokes 8 U.S.C. § 1367. Say near the top that the "
                "filing is protected by it, and ask USCIS to send everything to the safe mailing address.",
            )
        if not re.search(r"\bsafe\s+(?:mailing\s+)?address", body, re.IGNORECASE):
            audit.warn(
                "Protected matter without the safe mailing address",
                "Ask USCIS to send every notice and document to the safe mailing address on the forms (\"Please "
                "direct all correspondence to the safe mailing address on the enclosed forms, in care of counsel.\").",
            )
    return info


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _page_count(pdf: Path) -> int:
    from pypdf import PdfReader

    return len(PdfReader(str(pdf)).pages)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Render a Letter Markdown cover letter to .docx and .pdf (see README.md).",
    )
    ap.add_argument("letter", type=Path, help="Letter Markdown file (.md)")
    ap.add_argument("--profile", type=Path, help="Attorney profile JSON (attorney_name, firm_name, mailing_address, phone, email, bar_number, licensing_authority)")
    ap.add_argument("--out-dir", type=Path, help="Folder for the outputs (default: the letter's folder)")
    ap.add_argument("--name", help="Base file name for the outputs (default: the letter's file name without .md)")
    ap.add_argument("--renderer", choices=("auto", "libreoffice", "reportlab"), default="auto",
                    help="auto (default) = LibreOffice if installed, else reportlab")
    ap.add_argument("--summary-json", type=Path,
                    help="Where to write the JSON summary/audit (default: <out-dir>/<name>.render.json)")
    ap.add_argument("--json", action="store_true",
                    help="Print the whole JSON summary to stdout instead of the short summary")
    args = ap.parse_args(argv)

    src = args.letter.expanduser().resolve()
    if not src.is_file():
        raise ToolError(f"Letter file not found: {src}")
    letter = parse_letter(read_utf8(src))
    profile = load_profile(args.profile.expanduser().resolve() if args.profile else None, letter.audit)
    cited = audit_letter(letter, profile)
    content = audit_content(letter)

    out_dir, name = output_base(src, args.out_dir, args.name)
    docx_path = out_dir / f"{name}.docx"
    pdf_path = out_dir / f"{name}.pdf"
    summary_path = (args.summary_json.expanduser().resolve() if args.summary_json
                    else out_dir / f"{name}.render.json")
    if summary_path.suffix.lower() in (".docx", ".pdf", ".md"):
        raise ToolError("--summary-json must be a .json path, not the letter or its outputs.")
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.generated_files import check_generated, record_generated
    receipt = out_dir / f".{name}.generated.json"
    try:
        check_generated([docx_path, pdf_path], receipt)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc

    # Inline warnings were already collected while parsing; build with a parser that does not repeat them.
    quiet = InlineParser(_truthy(letter.front.get("smart_quotes"), True), Audit())
    build_docx(letter, profile, quiet, docx_path)

    renderer = None
    detail = ""
    fallback_reason = None
    soffice = find_soffice() if args.renderer in ("auto", "libreoffice") else None
    if args.renderer == "libreoffice" and not soffice:
        raise ToolError(
            "--renderer libreoffice was requested but LibreOffice was not found. Install it from "
            "https://www.libreoffice.org, set SOFFICE_PATH to its soffice executable, or use --renderer reportlab."
        )
    if soffice:
        try:
            with tempfile.TemporaryDirectory(prefix="sa-letter-") as tmp:
                pdf_docx = Path(tmp) / "letter.docx"
                build_docx(letter, profile, quiet, pdf_docx, pdf_bound=True)
                soffice_convert_to_pdf(pdf_docx, pdf_path, soffice)
            renderer, detail = "libreoffice", f"LibreOffice at {soffice} converted {docx_path.name}"
        except ToolError as exc:
            if args.renderer == "libreoffice":
                raise
            fallback_reason = str(exc)
    if renderer is None:
        with tempfile.TemporaryDirectory(prefix="sa-letter-") as tmp:
            tmp_pdf = Path(tmp) / "letter.pdf"
            font_desc = build_pdf_reportlab(letter, profile, quiet, tmp_pdf)
            shutil.move(str(tmp_pdf), str(pdf_path))
        renderer, detail = "reportlab", f"reportlab drew the PDF directly with {font_desc}"
        if fallback_reason:
            letter.audit.note(f"LibreOffice failed, so reportlab drew the PDF instead: {fallback_reason}")

    summary = {
        "ok": True,
        "renderer": renderer,
        "renderer_detail": detail,
        "docx": str(docx_path),
        "pdf": str(pdf_path),
        "page_count": _page_count(pdf_path),
        "exhibit_labels": letter.front["exhibit_labels"],
        "exhibits": [
            {"label": e.label, "display": e.display, "section": e.section, "description": e.description,
             "cited_in_body": cited.get(e.label, False)}
            for e in letter.exhibits
        ],
        **content,
        "finding_count": len(letter.audit.findings),
        "error_count": sum(1 for f in letter.audit.findings if f["severity"] == "error"),
        "findings": letter.audit.findings,
        "notes": letter.audit.notes,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary["summary_json"] = str(summary_path)
    record_generated([docx_path, pdf_path], receipt)
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print_summary(summary)
    return 0


MAX_PRINTED_FINDINGS = 5
MAX_FINDING_CHARS = 160


def print_summary(summary: dict) -> None:
    """Print the output paths and a short audit; everything else is in the summary JSON."""
    pages = summary["page_count"]
    print(f"Letter:  {summary['pdf']} ({pages} page{'s' if pages != 1 else ''}, {summary['renderer']})")
    print(f"Docx:    {summary['docx']}")
    print(f"Summary: {summary['summary_json']}")
    count, errors = summary["finding_count"], summary["error_count"]
    status = "clean" if count == 0 else "NOT READY"
    print(f"Audit:   {status}: {count} finding{'s' if count != 1 else ''} ({errors} error{'s' if errors != 1 else ''}), "
          f"{len(summary['exhibits'])} exhibits, {len(summary['notes'])} note{'s' if len(summary['notes']) != 1 else ''}")
    ranked = sorted(summary["findings"], key=lambda f: f["severity"] != "error")  # errors first, order kept
    for f in ranked[:MAX_PRINTED_FINDINGS]:
        line = f"{f['severity']}: {f['title']}: {f['detail']}"
        if len(line) > MAX_FINDING_CHARS:
            line = line[: MAX_FINDING_CHARS - 3].rstrip() + "..."
        print(f"  - {line}")
    if count > MAX_PRINTED_FINDINGS:
        print(f"  ... {count - MAX_PRINTED_FINDINGS} more in the summary's findings[].")


if __name__ == "__main__":
    run_cli(main)

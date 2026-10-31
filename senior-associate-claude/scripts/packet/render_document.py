#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "python-docx>=1.1",
#   "pypdf>=5.0",
#   "reportlab>=4.0",
# ]
# ///
"""Render a plain Markdown page (the attorney memo, the client request, a filing checklist, a translation
certificate) to PDF and .docx.

    uv run --script render_document.py DOC.md [--out-dir DIR] [--name BASENAME] [--formats pdf,docx]

Supports `#`/`##`/`###` headings, paragraphs, `-` bullets, `1.` numbered lists, `- [ ]`
and `- [x]` checklist items (drawn as boxes), `| a | b |` tables, `**bold**`, `*italic*`, and lines of
underscores for filling in by hand. There is no letterhead, no exhibit list and no audit:
for cover letters use render_letter.py. Prints the paths written.

A PDF is refused (exit 2, nothing written) when the text has characters the installed font can't draw, or
right-to-left script the renderer can't lay out: keep the Markdown alone then.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _packet_common import (  # noqa: E402
    ToolError,
    numbered_canvas,
    output_base,
    read_utf8,
    register_serif_fonts,
    run_cli,
    unsupported_chars,
)
from render_letter import Audit, InlineParser, Run, docx_runs, markup  # noqa: E402

BOX_EMPTY, BOX_DONE = "☐", "☑"
TABLE_RULE = re.compile(r"^:?-{3,}:?$")
RIGHT_TO_LEFT = re.compile("[\u0590-\u08ff\ufb1d-\ufdff\ufe70-\ufeff]")  # Hebrew, Arabic, Syriac, Thaana


@dataclass
class Block:
    kind: str  # h1 h2 h3 para bullet number check rule table
    runs: list[Run] = field(default_factory=list)
    marker: str = ""
    checked: bool = False
    level: int = 0
    last: bool = False  # a list's last item; for a table, that it has ended
    rows: list[list[list[Run]]] = field(default_factory=list)  # a table's cells
    header: bool = False  # a table's first row is its header


def table_cells(line: str) -> list[str]:
    s = line.strip()[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", s)]


def parse(source: str) -> list[Block]:
    inline = InlineParser(True, Audit())
    blocks: list[Block] = []
    para: list[str] = []
    numbering = 0

    def flush() -> None:
        if para:
            blocks.append(Block("para", inline(" ".join(s.strip() for s in para))))
            para.clear()

    lines = re.sub(r"<!--.*?-->", "", source.replace("\r\n", "\n"), flags=re.DOTALL).split("\n")
    for raw in lines:
        s = raw.strip()
        indent = len(raw) - len(raw.lstrip(" "))
        if not s:
            flush()
            if blocks and blocks[-1].kind in ("bullet", "number", "check", "table"):
                blocks[-1].last = True
            continue
        if s.startswith("|"):
            flush()
            cells = table_cells(s)
            if not (blocks and blocks[-1].kind == "table" and not blocks[-1].last):
                blocks.append(Block("table"))
            table = blocks[-1]
            if len(table.rows) == 1 and not table.header and all(TABLE_RULE.match(c) for c in cells):
                table.header = True
            else:
                table.rows.append([inline(c) for c in cells])
            continue
        hm = re.match(r"^(#{1,3})\s+(.*)$", s)
        check = re.match(r"^[-*]\s+\[([ xX])\]\s+(.*)$", s)
        bullet = re.match(r"^[-*]\s+(.*)$", s)
        number = re.match(r"^(\d{1,3})[.)]\s+(.*)$", s)
        if hm:
            flush()
            level = len(hm.group(1))
            blocks.append(Block(f"h{level}", inline(hm.group(2), bold=True)))
            numbering = 0
        elif re.fullmatch(r"(?:-{3,}|\*{3,})", s):
            flush()
            blocks.append(Block("rule"))
        elif check:
            flush()
            blocks.append(Block("check", inline(check.group(2)), checked=check.group(1) != " ", level=min(indent // 2, 1)))
        elif bullet:
            flush()
            blocks.append(Block("bullet", inline(bullet.group(1)), marker="•", level=min(indent // 2, 1)))
        elif number and (not para or number.group(1) == "1"):  # as in Markdown, only a 1. interrupts a paragraph
            flush()
            numbering = int(number.group(1))
            blocks.append(Block("number", inline(number.group(2)), marker=f"{numbering}.", level=min(indent // 2, 1)))
        elif blocks and blocks[-1].kind in ("bullet", "number", "check") and indent >= 2 and not para:
            blocks[-1].runs += inline(" " + s)
        else:
            para.append(s)
    flush()
    if blocks and blocks[-1].kind in ("bullet", "number", "check"):
        blocks[-1].last = True
    if not blocks:
        raise ToolError("The document is empty.")
    return blocks


def _texts(blocks: list[Block]) -> list[str]:
    out = []
    for b in blocks:
        out += [r.text for r in b.runs] + [b.marker]
        out += [r.text for row in b.rows for cell in row for r in cell]
    return out


def check_fonts(blocks: list[Block], fonts) -> None:
    """Refuse a PDF that would show empty boxes or right-to-left text drawn backwards."""
    text = "".join(_texts(blocks))
    if RIGHT_TO_LEFT.search(text):
        raise ToolError("The document has right-to-left text (such as Arabic or Hebrew), which the PDF renderer can't "
                        "lay out. Keep the Markdown file alone.")
    if fonts.unicode:
        from reportlab.pdfbase import pdfmetrics

        drawable = pdfmetrics.getFont(fonts.regular).face.charToGlyph
        absent = {ch for ch in text if ord(ch) not in drawable}
    else:
        absent = unsupported_chars(text, fonts)
    absent = sorted(ch for ch in absent if not ch.isspace())
    if absent:
        raise ToolError(f"The font ({fonts.description}) can't draw {len(absent)} character(s) in the document, such "
                        f"as {' '.join(absent[:8])}, so the PDF would show empty boxes. Keep the Markdown file alone.")


def _title(blocks: list[Block]) -> str:
    first = next((b for b in blocks if b.kind == "h1"), None)
    return "".join(r.text for r in first.runs) if first else "Document"


def build_pdf(blocks: list[Block], out: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.pdfbase.pdfmetrics import getAscent
    from reportlab.platypus import Flowable, HRFlowable, Paragraph, SimpleDocTemplate, Table, TableStyle

    class CheckItem(Flowable):
        """A checklist line with its box drawn as lines: empty for an open step, with a check
        mark inside for a done one (a font's box glyphs can't be relied on to differ)."""

        SIZE = 8.0

        def __init__(self, para: Paragraph, checked: bool, box_x: float):
            super().__init__()
            self.para, self.checked, self.box_x = para, checked, box_x
            self.spaceBefore, self.spaceAfter = para.style.spaceBefore, para.style.spaceAfter

        def wrap(self, avail_width, avail_height):
            self.width, self.height = self.para.wrap(avail_width, avail_height)
            return self.width, self.height

        def draw(self):
            style = self.para.style
            self.para.drawOn(self.canv, 0, 0)
            baseline = self.height - getAscent(style.fontName, style.fontSize)
            x, y, size = self.box_x, baseline - 1.2, self.SIZE
            c = self.canv
            c.saveState()
            c.setLineWidth(0.8)
            c.rect(x, y, size, size, stroke=1, fill=0)
            if self.checked:
                c.setLineWidth(1.3)
                path = c.beginPath()
                path.moveTo(x + 1.6, y + 4.2)
                path.lineTo(x + 3.4, y + 1.8)
                path.lineTo(x + 6.6, y + 6.6)
                c.drawPath(path, stroke=1, fill=0)
            c.restoreState()

    fonts = register_serif_fonts()
    check_fonts(blocks, fonts)
    base = ParagraphStyle("base", fontName=fonts.regular, fontSize=11.5, leading=14.5, alignment=TA_LEFT,
                          spaceAfter=8, bulletFontName=fonts.regular, bulletFontSize=11.5)
    styles = {
        "h1": ParagraphStyle("h1", parent=base, fontName=fonts.bold, fontSize=16, leading=20, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=base, fontName=fonts.bold, fontSize=13, leading=16, spaceBefore=8,
                             spaceAfter=6, keepWithNext=1),
        "h3": ParagraphStyle("h3", parent=base, fontName=fonts.bold, fontSize=11.5, spaceBefore=4, spaceAfter=4,
                             keepWithNext=1),
        "para": base,
    }
    cell_style = ParagraphStyle("cell", parent=base, fontSize=10, leading=12.5, spaceAfter=0, splitLongWords=1)
    head_style = ParagraphStyle("head", parent=cell_style, fontName=fonts.bold)

    def table(b: Block) -> Table:
        ncols = max(len(r) for r in b.rows)
        rows = [r + [[]] * (ncols - len(r)) for r in b.rows]
        # Columns share the width by how much text they hold, none narrower than about an inch.
        width = 6.5 * inch
        avg = [max(6.0, sum(len("".join(x.text for x in r[k])) for r in rows) / len(rows)) for k in range(ncols)]
        widths = [width * a / sum(avg) for a in avg]
        floor = min(0.9 * inch, width / ncols)
        narrow = {k for k, w in enumerate(widths) if w < floor}
        if narrow:
            rest = sum(w for k, w in enumerate(widths) if k not in narrow)
            widths = [floor if k in narrow else w * (width - floor * len(narrow)) / rest for k, w in enumerate(widths)]
        data = [[Paragraph(markup(cell), head_style if b.header and i == 0 else cell_style) for cell in row]
                for i, row in enumerate(rows)]
        t = Table(data, colWidths=widths, repeatRows=1 if b.header else 0, hAlign="LEFT")
        commands = [("GRID", (0, 0), (-1, -1), 0.5, colors.Color(0.55, 0.55, 0.55)),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
        if b.header:
            commands.append(("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.92, 0.92, 0.92)))
        t.setStyle(TableStyle(commands))
        t.spaceBefore, t.spaceAfter = 2, 10
        return t

    story = []
    for b in blocks:
        if b.kind == "rule":
            story.append(HRFlowable(width="100%", thickness=0.6, spaceBefore=4, spaceAfter=10))
        elif b.kind == "table":
            story.append(table(b))
        elif b.kind in styles:
            story.append(Paragraph(markup(b.runs), styles[b.kind]))
        else:
            left = (0.3 + 0.3 * b.level) * inch
            style = ParagraphStyle(f"li{b.level}", parent=base, leftIndent=left + 0.25 * inch, bulletIndent=left,
                                   spaceAfter=8 if b.last else 4)
            if b.kind == "check":
                story.append(CheckItem(Paragraph(markup(b.runs), style), b.checked, left))
            else:
                story.append(Paragraph(markup(b.runs), style, bulletText=b.marker))

    doc = SimpleDocTemplate(str(out), pagesize=(8.5 * inch, 11 * inch), leftMargin=inch, rightMargin=inch,
                            topMargin=0.9 * inch, bottomMargin=0.9 * inch, title=_title(blocks),
                            creator="render_document.py")
    doc.build(story, canvasmaker=numbered_canvas(fonts.regular, 9, lambda page, total: total > 1))


def build_docx(blocks: list[Block], out: Path) -> None:
    from docx import Document
    from docx.shared import Inches, Pt

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    sec.left_margin = sec.right_margin = Inches(1)
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(11.5)
    for b in blocks:
        if b.kind == "rule":
            doc.add_paragraph("_" * 60)
            continue
        if b.kind == "table":
            ncols = max(len(r) for r in b.rows)
            t = doc.add_table(rows=len(b.rows), cols=ncols)
            t.style = "Table Grid"
            for i, row in enumerate(b.rows):
                for k, cell in enumerate(row):
                    docx_runs(t.cell(i, k).paragraphs[0], cell, 10, bold=b.header and i == 0)
            doc.add_paragraph()
            continue
        size = {"h1": 16, "h2": 13, "h3": 11.5}.get(b.kind)
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.space_after = Pt(8 if b.kind in ("para", "h1") or b.last else 4)
        prefix = ""
        if b.kind in ("bullet", "number", "check"):
            left = 0.3 + 0.3 * b.level
            pf.left_indent = Inches(left + 0.25)
            pf.first_line_indent = Inches(-0.25)
            prefix = (BOX_DONE if b.checked else BOX_EMPTY) if b.kind == "check" else b.marker
            p.add_run(prefix + "\t")
            pf.tab_stops.add_tab_stop(Inches(left + 0.25))
        docx_runs(p, b.runs, size)
    doc.core_properties.title = _title(blocks)
    doc.save(str(out))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render a plain Markdown page to PDF and .docx.")
    ap.add_argument("source", type=Path, help="Markdown file")
    ap.add_argument("--out-dir", type=Path, help="Folder for the outputs (default: the source's folder)")
    ap.add_argument("--name", help="Base file name (default: the source's name without .md)")
    ap.add_argument("--formats", default="pdf,docx", help="pdf, docx, or pdf,docx (default)")
    args = ap.parse_args(argv)
    src = args.source.expanduser().resolve()
    if not src.is_file():
        raise ToolError(f"File not found: {src}")
    formats = {f.strip().lower() for f in args.formats.split(",") if f.strip()}
    if not formats or not formats <= {"pdf", "docx"}:
        raise ToolError("--formats must be pdf, docx, or pdf,docx.")
    blocks = parse(read_utf8(src))
    out_dir, name = output_base(src, args.out_dir, args.name)
    if "pdf" in formats:
        build_pdf(blocks, out_dir / f"{name}.pdf")
        print(f"PDF:  {out_dir / f'{name}.pdf'}")
    if "docx" in formats:
        build_docx(blocks, out_dir / f"{name}.docx")
        print(f"Docx: {out_dir / f'{name}.docx'}")
    return 0


if __name__ == "__main__":
    run_cli(main)

#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest>=8",
#   "python-docx>=1.1",
#   "pypdf[crypto]>=5.0",
#   "reportlab>=4.0",
#   "pillow>=10.0",
#   "pillow-heif>=0.16; sys_platform == 'darwin' or (sys_platform == 'linux' and (platform_machine == 'x86_64' or platform_machine == 'aarch64')) or (sys_platform == 'win32' and platform_machine == 'AMD64')",
# ]
# ///
"""End-to-end tests for render_letter.py and assemble_packet.py.

    uv run --script tests/test_packet_tools.py        (from scripts/packet, or use the full path)

Every fixture (PDFs, images, forms, a letter) is generated on the fly in a temp folder.
The LibreOffice tests are skipped when LibreOffice is not installed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
sys.path.insert(0, str(TOOLS))

import pytest  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

import _packet_common  # noqa: E402
import assemble_packet  # noqa: E402
import fees  # noqa: E402
import filing_locations  # noqa: E402
import letter_check  # noqa: E402
import render_document  # noqa: E402
import render_letter  # noqa: E402
import translations  # noqa: E402
from _packet_common import ToolError  # noqa: E402

LETTER_MD = """---
date: October 28, 2026
delivery: Via FedEx Priority Overnight
to:
  - U.S. Citizenship and Immigration Services
  - Attn: I-130
  - 2501 S. State Hwy. 121 Business, Suite 400
  - Lewisville, TX 75067
re:
  - Form I-130, Petition for Alien Relative
  - "Petitioner: Jane Example"
  - "Beneficiary: John Example"
signer_title: Counsel for Petitioner
---

# I. Introduction

Undersigned counsel represents Petitioner Jane Example, who files this petition for her husband, John Example, under INA § 201(b)(2)(A)(i).

# II. The Marriage Is Bona Fide

The petitioner must show the marriage was not entered into to evade the immigration laws. *Matter of Laureano*, 19 I&N Dec. 1 (BIA 1983).

## Joint Residence

They live together. *See* Exhibit C.

## ii. Commingled Finances

They share a bank account.

> Evidence to establish intent could take many forms.

- first bullet
- second bullet

```exhibits
# Forms
- Form G-28
- Exhibit B: Form I-130, Petition for Alien Relative
# Evidence of Bona Fide Marriage
- Joint lease
- Bank statements
  continued on a second line
# Identity
- Passport of *Jane Example*
- Birth certificate
```

# III. Conclusion

Please approve the petition.
"""

PROFILE = {
    "attorney_name": "A. Counsel, Esq.",
    "firm_name": "Example Law PLLC",
    "mailing_address": "1200 Example Avenue, Suite 400, Austin, TX 78701",
    "phone": "(512) 555-0142",
    "email": "acounsel@examplelaw.test",
    "bar_number": "24000000",
    "licensing_authority": "State Bar of Texas",
}


RENDER_DAY = __import__("datetime").date(2026, 10, 29)


@pytest.fixture(autouse=True)
def fixed_render_day(monkeypatch):
    """Every letter is rendered on the same day, so date checks don't depend on the calendar."""
    monkeypatch.setattr(render_letter, "_today", lambda: RENDER_DAY)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def outline_entries(pdf: Path) -> list[tuple[int, str, int]]:
    """(depth, title, 1-based page) for every bookmark, in order."""
    reader = PdfReader(str(pdf))
    out: list[tuple[int, str, int]] = []

    def walk(nodes, depth):
        for node in nodes:
            if isinstance(node, list):
                walk(node, depth + 1)
            else:
                out.append((depth, node.title, reader.get_destination_page_number(node) + 1))

    walk(reader.outline, 0)
    return out


def _text_pdf(path: Path, pages: int = 1, rotate: int = 0, size=None, **encryption) -> Path:
    """A PDF with one line of text a page ("<stem> page N"), turned by rotate degrees or encrypted if asked."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=size or letter)
    for i in range(1, pages + 1):
        c.drawString(72, 700, f"{path.stem} page {i}")
        c.showPage()
    c.save()
    if rotate or encryption:
        w = PdfWriter(clone_from=PdfReader(str(path)))
        for page in w.pages if rotate else []:
            page.rotate(rotate)
        if encryption:
            w.encrypt(**encryption)
        w.write(str(path))
    return path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def fx(tmp_path_factory) -> dict:
    from PIL import Image
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.pdfgen import canvas

    d = tmp_path_factory.mktemp("fixtures")

    def form_pdf(name, value):
        path = d / name
        c = canvas.Canvas(str(path), pagesize=letter)
        c.drawString(72, 720, f"Form {name}")
        c.acroForm.textfield(name="Pt1Line1_FamilyName", value=value, x=72, y=650, width=200, height=20)
        c.showPage()
        c.save()
        return path

    fx = {
        "dir": d,
        "three": _text_pdf(d / "three pages.pdf", 3),
        "a4": _text_pdf(d / "a4 certificate.pdf", 2, size=A4),
        "owner_only": _text_pdf(d / "owner only.pdf", user_password="", owner_password="owner"),
        "locked": _text_pdf(d / "locked.pdf", user_password="secret", owner_password="secret"),
        "form1": form_pdf("form one.pdf", "Example"),
        "form2": form_pdf("form two.pdf", "Witness"),
    }
    corrupt = d / "corrupt.pdf"
    corrupt.write_bytes(b"%PDF-1.7\n" + b"\x00garbage" * 50)
    fx["corrupt"] = corrupt

    Image.new("RGB", (1600, 900), (30, 90, 160)).save(d / "landscape.png")
    fx["png"] = d / "landscape.png"
    exif = Image.Exif()
    exif[0x0112] = 6  # stored landscape, displayed rotated to portrait
    Image.new("RGB", (1200, 800), (200, 120, 40)).save(d / "rotated.jpg", exif=exif.tobytes(), quality=90)
    fx["jpg"] = d / "rotated.jpg"

    (d / "attorney.json").write_text(json.dumps(PROFILE), encoding="utf-8")
    fx["profile"] = d / "attorney.json"
    return fx


def _render(folder: Path, md: str, name: str = "l", profile: Path | None = None, *args: str,
            renderer: str = "reportlab", summary: Path | None = None) -> dict:
    """Write md to folder/<name>.md, render it, and return its summary (from --summary-json when given)."""
    folder.mkdir(parents=True, exist_ok=True)
    src = folder / f"{name}.md"
    src.write_text(md, encoding="utf-8")
    options = (["--profile", str(profile)] if profile else []) + (["--summary-json", str(summary)] if summary else [])
    assert render_letter.main([str(src), "--renderer", renderer, *options, *args]) == 0
    return json.loads((summary or folder / f"{name}.render.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# render_letter.py
# ---------------------------------------------------------------------------
def test_render_letter_reportlab(fx):
    from docx.shared import Inches

    summary = _render(fx["dir"] / "rl", LETTER_MD, "Cover Letter", fx["profile"])
    pdf, docx_path = Path(summary["pdf"]), Path(summary["docx"])
    assert summary["renderer"] == "reportlab"
    assert pdf.is_file() and docx_path.is_file()
    assert summary["page_count"] == len(PdfReader(str(pdf)).pages) >= 1

    labels = [e["label"] for e in summary["exhibits"]]
    assert labels == ["A", "B", "C", "D", "E", "F"]  # continuous across sections
    assert [e["section"] for e in summary["exhibits"]] == ["Forms", "Forms"] + ["Evidence of Bona Fide Marriage"] * 2 + ["Identity"] * 2
    assert summary["exhibits"][1]["description"] == "Form I-130, Petition for Alien Relative"  # hand label stripped
    assert summary["exhibits"][3]["description"] == "Bank statements continued on a second line"
    assert summary["exhibits"][4]["description"] == "Passport of Jane Example"
    assert any("hand-written label Exhibit B" in n for n in summary["notes"])  # matched its slot: a note only
    # Only Exhibit C is cited in the body, so the audit flags the uncited ones (and nothing else).
    assert summary["finding_count"] == 1 and summary["error_count"] == 0
    assert summary["findings"][0]["title"] == "Exhibit listed but never cited"
    assert [e["cited_in_body"] for e in summary["exhibits"]] == [False, False, True, False, False, False]

    text = "\n".join(p.extract_text() for p in PdfReader(str(pdf)).pages)
    for needle in ("Example Law PLLC", "RE:", "Jane Example", "Exhibit F", "Respectfully submitted", "Bar No. 24000000"):
        assert needle in text, needle

    from docx import Document

    doc = Document(str(docx_path))
    paras = doc.paragraphs
    h1 = next(p for p in paras if p.text == "I. Introduction")
    assert all(r.bold and r.underline for r in h1.runs)
    body = next(p for p in paras if p.text.startswith("Undersigned counsel"))
    assert body.paragraph_format.first_line_indent == Inches(0.5)
    assert not body.text.startswith("\t")
    assert "§ 201" in body.text  # section sign kept with its number
    h2s = [p for p in paras if p.text.startswith(("i.\t", "ii.\t"))]
    assert [p.text for p in h2s] == ["i.\tJoint Residence", "ii.\tCommingled Finances"]  # numbering not doubled
    assert all(r.italic for p in h2s for r in p.runs)
    case = next(p for p in paras if "Laureano" in p.text)
    assert any(r.italic and "Matter of Laureano" in r.text for r in case.runs)
    exhibit_a = next(p for p in paras if p.text.startswith("Exhibit A\t"))
    pf = exhibit_a.paragraph_format
    assert pf.first_line_indent < 0 and pf.left_indent > Inches(1)
    section = next(p for p in paras if p.text == "Evidence of Bona Fide Marriage")
    assert all(r.bold and r.underline for r in section.runs)
    assert doc.core_properties.author == "A. Counsel, Esq."


@pytest.mark.skipif(_packet_common.find_soffice() is None, reason="LibreOffice not installed")
def test_render_letter_libreoffice(fx):
    summary = _render(fx["dir"] / "lo", LETTER_MD, "Cover Letter", fx["profile"], renderer="libreoffice")
    assert summary["renderer"] == "libreoffice"
    pdf = Path(summary["pdf"])
    assert summary["page_count"] == len(PdfReader(str(pdf)).pages) >= 1
    text = "\n".join(p.extract_text() for p in PdfReader(str(pdf)).pages)
    assert "Example Law PLLC" in text and "Exhibit F" in text


def test_render_letter_numbers_and_start(tmp_path):
    front = "---\ndate: October 27, 2026\nexhibit_labels: {}\nexhibit_start: {}\nre: Form I-130\nto: USCIS\n---\n\n"
    body = "Body.\n\n```exhibits\n- One\n- Two\n```\n"
    summary = _render(tmp_path, front.format("numbers", 4) + body, "n")
    assert [e["display"] for e in summary["exhibits"]] == ["Exhibit 4", "Exhibit 5"]
    assert any("No attorney profile" in n for n in summary["notes"])
    assert [f["title"] for f in summary["findings"]] == ["Missing signature"]
    assert summary["error_count"] == 1
    # Letter labels start at exhibit_start too, and run on past Z.
    letters = _render(tmp_path, front.format("letters", "zz") + body, "z")
    assert [e["display"] for e in letters["exhibits"]] == ["Exhibit ZZ", "Exhibit AAA"]


CLEAN_MD = """---
date: October 28, 2026
to:
  - USCIS
  - Attn: I-130
re:
  - Form I-130, Petition for Alien Relative
  - "Petitioner: Jane Example"
---

# I. Introduction

Ms. Example is a U.S. citizen. *See* Exhibit A. The couple married in 2024. *See* Exhibits B–C and Ex. D.

# II. Index of Exhibits

Exhibits are listed below.

```exhibits
# Citizenship
- U.S. passport
# Marriage
- Marriage certificate
- Joint lease
- Photographs
```

# III. Conclusion

Index of Exhibits

IV. Approve the petition.
"""

BROKEN_MD = """---
date: October 28, 2026
to: USCIS
deliver: Via FedEx
---

# I. Introduction

The *Matter of Laureano standard applies [INSERT CITE]. *See* Exhibit Z and Exhibit A.

# III. Argument

## Empty proof block

# IV. Index

```exhibits
# Civil documents
- Exhibit A: Form I-130
- Exhibit C: Marriage certificate
# Nothing here
```
"""


def test_render_letter_audit_clean(fx, tmp_path, capsys):
    audit = tmp_path / "audit" / "cover letter audit.json"
    summary = _render(tmp_path, CLEAN_MD, "clean", fx["profile"], summary=audit)
    assert summary["finding_count"] == 0 and summary["error_count"] == 0 and summary["findings"] == []
    assert all(e["cited_in_body"] for e in summary["exhibits"])  # A, B-C range, Ex. D
    assert not (tmp_path / "clean.render.json").exists()  # --summary-json replaces the default path
    out = capsys.readouterr().out
    assert "Audit:   clean: 0 findings (0 errors), 4 exhibits" in out and len(out.splitlines()) == 4
    _render(tmp_path, CLEAN_MD, "clean", fx["profile"], "--json", summary=audit)
    printed = json.loads(capsys.readouterr().out)  # --json: the whole summary, as written
    assert printed["summary_json"] == str(audit) and printed["exhibits"] == summary["exhibits"]


def test_render_letter_audit_findings(tmp_path, capsys):
    capsys.readouterr()
    summary = _render(tmp_path, BROKEN_MD, "broken")  # still renders

    # Stdout is short: paths, one audit line, the first five findings (errors first), and a pointer to the rest.
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0].startswith("Letter:  ") and str(tmp_path / "broken.pdf") in lines[0]
    assert any(l.startswith("Summary: ") and "broken.render.json" in l for l in lines)
    assert "Audit:   NOT READY: 12 findings (6 errors)" in out
    shown = [l for l in lines if l.startswith("  - ")]
    assert len(shown) == 5 and all(l.startswith("  - error: ") for l in shown)
    assert all(len(l) <= 4 + render_letter.MAX_FINDING_CHARS for l in shown)
    assert "7 more in the summary's findings[]" in lines[-1]
    assert '"findings"' not in out and len(lines) == 10
    titles = {f["title"]: f["severity"] for f in summary["findings"]}
    assert titles == {
        "Unknown front-matter key": "warning",
        "Unresolved Markdown": "error",
        "Unfilled placeholder": "error",
        "Exhibit label mismatch": "error",
        "Empty exhibit section": "warning",
        "Missing RE block": "error",
        "Exhibit cited but not listed": "error",
        "Exhibit listed but never cited": "warning",
        "Empty section": "warning",
        "Heading numbering out of order": "warning",
        "Missing signature": "error",
    }, titles
    assert summary["finding_count"] == len(summary["findings"]) == 12  # "Empty section" is reported twice
    assert summary["error_count"] == 6
    cited = next(f for f in summary["findings"] if f["title"] == "Exhibit cited but not listed")
    assert "Exhibit Z" in cited["detail"]


def test_letter_labels_past_z_and_exhibit_start():
    assert [render_letter.exhibit_label(i, "letters") for i in (25, 26, 27)] == ["Z", "AA", "BB"]
    # exhibit_start reads back every label the tool assigns, and nothing else.
    assert all(render_letter.label_offset(render_letter.exhibit_label(i, style), style) == i
               for style in ("letters", "numbers") for i in range(80))
    for start, style in (("AB", "letters"), ("4", "letters"), ("", "letters"), ("0", "numbers"), ("D", "numbers")):
        with pytest.raises(ToolError, match="exhibit_start must be"):
            render_letter.label_offset(start, style)


def test_cited_labels():
    known = {"letters": {render_letter.exhibit_label(i, "letters") for i in range(12)},
             "numbers": {render_letter.exhibit_label(i, "numbers") for i in range(15)}}
    # (text, label style, read against the letter's exhibit list, the labels it cites)
    cases = [
        ("See Exhibits F–H and Exhibit K; Exs. B, D.", "letters", False, ["F", "G", "H", "K", "B", "D"]),
        ("See Exhibits 3 through 5.", "numbers", False, ["3", "4", "5"]),
        ("the exhibits below and Exhibit USCIS", "letters", False, []),
        # Form numbers, agency names and reporters after a label are not more labels.
        ("See Exhibit C, I-94 record.", "letters", False, ["C"]),
        ("See Exhibit B, I-797C receipt notice.", "letters", False, ["B"]),
        ("See Exhibit A, IRS transcripts.", "letters", False, ["A"]),
        ("See Exhibits A and B, DHS records.", "letters", False, ["A", "B"]),
        ("See Exhibit A, I&N Dec. 1.", "letters", False, ["A"]),
        ("Exhibit A to I-485 shows the entry.", "letters", False, ["A"]),  # "to" is a range only between two labels
        ("See Exhibit 4 and 8 C.F.R. § 204.2.", "numbers", False, ["4"]),
        ("See Exhibit 4, 8 U.S.C. § 1154.", "numbers", False, ["4"]),
        ("See Exhibit AB.", "letters", False, []),  # not a label this tool assigns
        # Real citations still read in full.
        ("See Exhibits AA–CC.", "letters", False, ["AA", "BB", "CC"]),
        ("See Exhibits A to C, and Exhibit E.", "letters", False, ["A", "B", "C", "E"]),
        ("See Exhibits A, B, and C.", "letters", False, ["A", "B", "C"]),
        ("See Exhibit D at 2.", "letters", False, ["D"]),
        # With the exhibit list, a word after the first label is read as a word.
        ("See Exhibit D, U.S. passport.", "letters", True, ["D"]),
        ("See Exhibit D and U.S. passport.", "letters", True, ["D"]),
        ("See Exhibit 3, 12 photos.", "numbers", True, ["3"]),
        ("See Ex. 4, 5 years of tax returns.", "numbers", True, ["4"]),
        ("See Exhibit 7, 1 photo.", "numbers", True, ["7"]),
        ("See Exhibit 12, 8 CFR 204.2.", "numbers", True, ["12"]),
        ("See Exhibit 3, 8 USC 1186a.", "numbers", True, ["3"]),
        ("See Exhibit B, I am told.", "letters", True, ["B"]),
        ("See Exhibit B and I am told.", "letters", True, ["B"]),
        ("See Exhibit B, A copy of the lease.", "letters", True, ["B"]),
        ("See Exhibits A and I.", "letters", True, ["A", "I"]),
        ("See Exhibits 3, 4 and 5.", "numbers", True, ["3", "4", "5"]),
        ("See Exhibits 12 and 20.", "numbers", True, ["12"]),  # 20 isn't an exhibit in this letter
        ("See Exhibit Z.", "letters", True, ["Z"]),  # a missing exhibit is still caught
    ]
    for text, style, with_list, want in cases:
        runs = render_letter.InlineParser(True, render_letter.Audit())(text)
        assert render_letter.cited_labels(render_letter.plain(runs), style, known[style] if with_list else None) == want, text


def test_smart_quotes():
    def smart(text):
        return render_letter.plain(render_letter.InlineParser(True, render_letter.Audit())(text))

    assert smart('"\'Extreme\' cruelty" is defined') == "“‘Extreme’ cruelty” is defined"
    assert smart('the "\'contrite\' phase"') == "the “‘contrite’ phase”"
    assert smart("born in '96, raised in the '90s") == "born in ’96, raised in the ’90s"
    assert smart("the couple's 'home'") == "the couple’s ‘home’"


def _letter(body: str, **front) -> str:
    head = {"date": "October 28, 2026", "to": "USCIS", "re": "Form I-130"} | front
    lines = "".join(f"{k}: {v}\n" for k, v in head.items() if v is not None)
    return f"---\n{lines}---\n\n{body}\n"


def test_stale_date_and_computed_phrases(fx, tmp_path):
    body = ("Mr. Example is 29 years old. The couple's eighteen-month marriage followed a courtship of two years, "
            "and they have lived together for three years.")
    summary = _render(tmp_path, _letter(body, date="September 1, 2026"), "stale", fx["profile"])
    titles = [f["title"] for f in summary["findings"]]
    assert titles == ["Letter date is stale"]
    assert "58 days before today" in summary["findings"][0]["detail"]
    assert summary["letter_date"] == "2026-09-01" and summary["render_date"] == "2026-10-29"
    phrases = [(p["kind"], p["text"]) for p in summary["computed_phrases"]]
    assert ("age", "29 years old") in phrases
    assert ("duration", "eighteen-month marriage") in phrases
    assert ("duration", "for three years") in phrases
    assert any("recomputed" in n for n in summary["notes"])

    fresh = _render(tmp_path, _letter("No ages here.", date="November 4, 2026"), "fresh", fx["profile"])
    assert fresh["findings"] == [] and fresh["computed_phrases"] == []  # 6 days ahead is within the window
    bad = _render(tmp_path, _letter("Body.", date="sometime soon"), "bad", fx["profile"])
    assert [f["title"] for f in bad["findings"]] == ["Unreadable date"]


def test_length_budget(fx, tmp_path):
    body = "\n\n".join(["The applicant has a pending adjustment application. " * 8] * 13)  # 728 words
    long = _render(tmp_path, _letter(body, matter_type="I-765"), "long", fx["profile"])
    assert long["matter_type"] == "i765" and long["word_count"] == 728 and long["length_budget"] == 600
    assert [f["title"] for f in long["findings"]] == ["Letter longer than its budget"]
    assert "728 words" in long["findings"][0]["detail"] and "600" in long["findings"][0]["detail"]
    allowed = _render(tmp_path, _letter(body, matter_type="i765", length_budget=900), "allowed", fx["profile"])
    assert allowed["findings"] == [] and allowed["length_budget"] == 900
    response = _render(tmp_path, _letter(body, matter_type="rfe_response"), "response", fx["profile"])
    assert response["findings"] == [] and response["length_budget"] is None
    unknown = _render(tmp_path, _letter("Body.", matter_type="i999"), "unknown", fx["profile"])
    assert [f["title"] for f in unknown["findings"]] == ["Unknown matter type"]


def test_forms_section_needs_no_citation(fx, tmp_path):
    body = ("Ms. Example is a citizen. *See* Exhibit C.\n\n```exhibits\n# Forms and Fees\n- Form G-28\n- Form I-130\n"
            "# Citizenship\n- U.S. passport\n- Birth certificate\n```")
    summary = _render(tmp_path, _letter(body), "forms", fx["profile"])
    uncited = [f for f in summary["findings"] if f["title"] == "Exhibit listed but never cited"]
    assert len(uncited) == 1 and "Exhibit D" in uncited[0]["detail"] and "Exhibit A" not in uncited[0]["detail"]


def test_online_filing_has_no_mailing_details(fx, tmp_path):
    mailed = _render(tmp_path, _letter("Body.", filing_method="online", delivery="Via FedEx"), "mailed", fx["profile"])
    assert [f["title"] for f in mailed["findings"]] == ["Mailing details in an online filing"]
    lockbox = _letter("Body.", filing_method="online").replace("to: USCIS\n", "to:\n  - USCIS\n  - P.O. Box 660867\n")
    assert [f["title"] for f in _render(tmp_path, lockbox, "lockbox", fx["profile"])["findings"]] == [
        "Mailing details in an online filing"]
    online = _render(tmp_path, _letter("Body.", filing_method="online"), "online", fx["profile"])
    assert online["findings"] == [] and online["filing_method"] == "online"


def test_builtin_font_character_error(fx, tmp_path, monkeypatch):
    builtin = _packet_common.SerifFonts("Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic",
                                        unicode=False, description="built-in Times")
    monkeypatch.setattr(render_letter, "register_serif_fonts", lambda: builtin)
    summary = _render(tmp_path, _letter("The beneficiary, Nguyễn Văn An, is the petitioner's husband."),
                         "font", fx["profile"])
    err = next(f for f in summary["findings"] if f["title"] == "Characters the PDF font cannot draw")
    assert err["severity"] == "error" and "ễ" in err["detail"] and "ă" in err["detail"]
    assert "é" not in err["detail"]  # cp1252 covers Western European accents


def test_letterhead_signature_and_footer(fx, tmp_path):
    body = "First page.\n\n<!-- pagebreak -->\n\nSecond page.\n\n<!-- pagebreak -->\n\nThird page."
    summary = _render(tmp_path, _letter(body, signer_title="Counsel for Petitioner", cc="Jane Example"),
                         "sig", fx["profile"])
    pages = [p.extract_text() for p in PdfReader(summary["pdf"]).pages]
    assert len(pages) == 3
    head = pages[0]
    for needle in ("Example Law PLLC", "A. Counsel, Esq.", "1200 Example Avenue, Suite 400", "Austin, TX 78701",
                   "Tel. (512) 555-0142", "acounsel@examplelaw.test"):
        assert needle in head, needle
    tail = pages[-1]
    for needle in ("Respectfully submitted,", "A. Counsel, Esq.", "Counsel for Petitioner",
                   "Bar No. 24000000 (State Bar of Texas)", "cc:", "Jane Example"):
        assert needle in tail, needle
    assert "Page 1 of" not in pages[0]  # numbered from page 2 on
    assert "Page 2 of 3" in pages[1] and "Page 3 of 3" in pages[2]

    from docx import Document

    doc = Document(summary["docx"])
    sec = doc.sections[0]
    assert sec.different_first_page_header_footer
    footer_xml = sec.footer._element.xml
    assert 'w:instr="PAGE"' in footer_xml and 'w:instr="NUMPAGES"' in footer_xml
    unnumbered = _render(tmp_path, _letter(body, page_numbers="false"), "nonum", fx["profile"])
    assert "Page 2 of" not in PdfReader(unnumbered["pdf"]).pages[1].extract_text()


def test_render_letter_errors(tmp_path):
    md = tmp_path / "bad.md"
    md.write_text("---\ndate: x\n---\n\n```exhibits\n- One\n", encoding="utf-8")
    with pytest.raises(ToolError, match="never closed"):
        render_letter.main([str(md), "--renderer", "reportlab"])
    with pytest.raises(ToolError, match="not found"):
        render_letter.main([str(tmp_path / "missing.md")])


# ---------------------------------------------------------------------------
# assemble_packet.py
# ---------------------------------------------------------------------------
def test_assemble_packet(fx, capsys):
    letter_pdf = Path(_render(fx["dir"] / "for-packet", LETTER_MD, "Cover Letter", fx["profile"])["pdf"])
    letter_pages = len(PdfReader(str(letter_pdf)).pages)
    d = fx["dir"]
    sources = [fx["three"], fx["a4"], fx["png"], fx["jpg"], fx["owner_only"], fx["form1"], fx["form2"], letter_pdf]
    before = {p: sha(p) for p in sources}
    plan = {
        "output": "out/Test Packet.pdf",
        "title": "Test Packet",
        "items": [
            {"kind": "pdf", "path": str(letter_pdf), "description": "Cover Letter"},
            {"kind": "pdf", "path": fx["form1"].name, "description": "Form one"},
            {"kind": "pdf", "path": fx["form2"].name, "description": "Form two"},
            {"kind": "separator", "label": "Exhibit A", "description": "Bank statements", "section": "Finances"},
            {"kind": "pdf", "path": fx["three"].name, "pages": "2-3", "label": "Exhibit A", "section": "Finances"},
            {"kind": "pdf", "path": fx["a4"].name, "label": "Exhibit B", "description": "Certificate", "section": "Finances"},
            {"kind": "separator", "label": "Exhibit C", "description": "Photos", "section": "Life together"},
            {"kind": "image", "paths": [fx["png"].name, fx["jpg"].name], "label": "Exhibit C", "section": "Life together"},
            {"kind": "pdf", "path": fx["owner_only"].name, "label": "Exhibit D", "description": "Permissions-only PDF", "section": "Life together"},
            {"kind": "placeholder", "label": "Exhibit E", "description": "Joint lease", "note": "Client to send", "section": "Life together"},
        ],
    }
    plan_path = d / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    capsys.readouterr()
    assert assemble_packet.main([str(plan_path)]) == 0
    summary_out = capsys.readouterr().out

    out = d / "out" / "Test Packet.pdf"
    umask = os.umask(0)
    os.umask(umask)
    assert out.stat().st_mode & 0o777 == 0o666 & ~umask  # not mkstemp's owner-only mode
    manifest = json.loads((d / "out" / "Test Packet.manifest.json").read_text(encoding="utf-8"))
    reader = PdfReader(str(out))
    expected_counts = [letter_pages, 1, 1, 1, 2, 2, 1, 2, 1, 1]
    assert [it["page_count"] for it in manifest["items"]] == expected_counts
    assert manifest["total_pages"] == len(reader.pages) == sum(expected_counts)

    # Page ranges are contiguous and recorded per source.
    nxt = 1
    for it in manifest["items"]:
        assert it["packet_start"] == nxt and it["packet_end"] == nxt + it["page_count"] - 1
        nxt = it["packet_end"] + 1
    by_index = {it["index"]: it for it in manifest["items"]}
    assert by_index[5]["sources"][0]["pages"] == "2-3"
    assert by_index[5]["sources"][0]["source_page_count"] == 3
    assert [Path(s["path"]).name for s in by_index[8]["sources"]] == ["landscape.png", "rotated.jpg"]
    assert manifest["placeholders"] == [
        {"index": 10, "label": "Exhibit E", "description": "Joint lease", "note": "Client to send",
         "packet_page": by_index[10]["packet_start"]}
    ]
    assert [e["label"] for e in manifest["exhibits"]] == ["Exhibit A", "Exhibit B", "Exhibit C", "Exhibit D", "Exhibit E"]
    assert manifest["exhibits"][0]["packet_start"] == by_index[4]["packet_start"]
    assert manifest["exhibits"][0]["packet_end"] == by_index[5]["packet_end"]
    assert any("A4" in w for w in manifest["warnings"])

    # Content landed where the manifest says.
    page = lambda n: reader.pages[n - 1]  # noqa: E731
    assert "three pages page 2" in page(by_index[5]["packet_start"]).extract_text()
    assert "EXHIBIT A" in page(by_index[4]["packet_start"]).extract_text()
    assert "TO BE SUPPLIED" in page(by_index[10]["packet_start"]).extract_text()
    img_png, img_jpg = page(by_index[8]["packet_start"]), page(by_index[8]["packet_end"])
    assert float(img_png.mediabox.width) > float(img_png.mediabox.height)  # landscape image, landscape page
    assert float(img_jpg.mediabox.width) < float(img_jpg.mediabox.height)  # EXIF-rotated photo, portrait page
    a4 = page(by_index[6]["packet_start"])
    assert round(float(a4.mediabox.width)) == 595  # mixed sizes kept, not distorted

    # Bookmarks: one per item, exhibits nested under sections.
    marks = outline_entries(out)
    assert marks[0] == (0, "Cover Letter", 1)
    assert (0, "Finances", by_index[4]["packet_start"]) in marks
    assert (1, "Exhibit A - Bank statements", by_index[4]["packet_start"]) in marks
    assert (2, "three pages.pdf, pp. 2-3", by_index[5]["packet_start"]) in marks
    assert (1, "Exhibit B - Certificate", by_index[6]["packet_start"]) in marks
    assert (0, "Life together", by_index[7]["packet_start"]) in marks
    assert (1, "Exhibit E - Joint lease [TO BE SUPPLIED]", by_index[10]["packet_start"]) in marks
    for it in manifest["items"]:
        assert it["bookmark"], it

    # Fillable forms keep their own values instead of sharing one field name.
    fields = reader.get_fields() or {}
    values = sorted(str(f.get("/V")) for name, f in fields.items() if name.endswith("Pt1Line1_FamilyName"))
    assert values == ["Example", "Witness"]

    # Stdout is a short summary; the page map lives in the manifest and --table prints it.
    lines = summary_out.splitlines()
    assert lines[0].startswith("Packet:   ") and f"({manifest['total_pages']} pages," in lines[0]
    assert lines[1] == f"Manifest: {d / 'out' / 'Test Packet.manifest.json'}"
    assert "Items:    10; exhibits: 5 (1 to be supplied)" in lines
    assert f"DRAFT: 1 placeholder: Exhibit E (p. {by_index[10]['packet_start']})" in lines
    assert any(l.startswith("WARNING: ") and "A4" in l for l in lines)
    assert "Joint lease" not in summary_out and "separator" not in summary_out  # no per-item table
    assert len(lines) <= 8
    assert assemble_packet.main([str(plan_path), "--table"]) == 0
    table_out = capsys.readouterr().out
    assert "separator   Exhibit A - Bank statements" in table_out
    assert len(table_out.splitlines()) == len(lines) + len(plan["items"]) - 1  # table replaces the page-map hint

    assert {p: sha(p) for p in sources} == before  # sources never modified


def _plan(tmp_path: Path, items: list[dict], **top) -> Path:
    p = tmp_path / "plan.json"
    p.write_text(json.dumps({"output": "packet.pdf", "items": items} | top), encoding="utf-8")
    return p


def _run_plan(tmp_path: Path, items: list[dict], *args, **top) -> tuple[dict, Path]:
    assert assemble_packet.main([str(_plan(tmp_path, items, **top)), *args]) == 0
    return json.loads((tmp_path / "packet.manifest.json").read_text(encoding="utf-8")), tmp_path / "packet.pdf"


def test_assembly_renews_a_fresh_lease_and_leaves_any_other_alone(fx, tmp_path, monkeypatch):
    # A long assembly is a sign of life for the run that holds the matter, never for a run that has gone.
    import datetime as dt

    sys.path.insert(0, str(TOOLS.parents[1]))
    from scripts import matter_state

    now = dt.datetime.now(tz=dt.timezone.utc)

    def assemble(name: str, minutes_ago: int | None) -> dict | None:
        matter = tmp_path / name
        packet_dir = matter / "output" / "working" / "vault" / "packet" / "main"
        packet_dir.mkdir(parents=True)
        shutil.copyfile(fx["three"], matter / "three pages.pdf")
        if minutes_ago is not None:
            assert matter_state.acquire_lease(matter, "run-1", "build", "orchestrator",
                                              now=now - dt.timedelta(minutes=minutes_ago))[0]
        plan = packet_dir / "packet plan.json"
        plan.write_text(json.dumps({"output": str(matter / "output" / "deliverables" / "Packet.pdf"),
                                    "items": [{"kind": "pdf", "path": str(matter / "three pages.pdf")},
                                              {"kind": "placeholder", "description": "Lease"}]}), encoding="utf-8")
        monkeypatch.setattr(matter_state, "_last_sign_of_life", {})
        assert assemble_packet.main([str(plan)]) == 0
        return matter_state.read_lease(matter)

    renewed = assemble("fresh", 10)
    assert dt.datetime.fromisoformat(renewed["heartbeat_at"]) > now - dt.timedelta(minutes=1)
    stale = assemble("stale", 40)
    assert dt.datetime.fromisoformat(stale["heartbeat_at"]) < now - dt.timedelta(minutes=39)  # left alone
    assert assemble("none", None) is None  # no lease is ever made



def test_assemble_errors(fx, tmp_path, monkeypatch):
    with pytest.raises(ToolError, match=r"locked\.pdf.*password"):
        assemble_packet.main([str(_plan(tmp_path, [{"kind": "pdf", "path": str(fx["locked"])}]))])
    with pytest.raises(ToolError, match=r"corrupt\.pdf.*damaged"):
        assemble_packet.main([str(_plan(tmp_path, [{"kind": "pdf", "path": str(fx["corrupt"])}]))])
    with pytest.raises(ToolError, match="has 3 pages"):
        assemble_packet.main([str(_plan(tmp_path, [{"kind": "pdf", "path": str(fx["three"]), "pages": "2-5"}]))])
    with pytest.raises(ToolError, match="not a PDF; it looks like a PNG"):
        assemble_packet.main([str(_plan(tmp_path, [{"kind": "pdf", "path": str(fx["png"])}]))])
    with pytest.raises(ToolError, match="needs a \"label\""):
        assemble_packet.main([str(_plan(tmp_path, [{"kind": "separator", "description": "x"}]))])
    spaced = tmp_path / "Marriage certificate .pdf"
    shutil.copyfile(fx["three"], spaced)
    with pytest.raises(ToolError, match="similar file exists"):
        assemble_packet.main([str(_plan(tmp_path, [{"kind": "pdf", "path": str(tmp_path / "Marriage certificate.pdf")}]))])
    docx = tmp_path / "x.docx"
    docx.write_bytes(b"PK\x03\x04")
    monkeypatch.setattr(assemble_packet, "find_soffice", lambda: None)
    with pytest.raises(ToolError, match="needs LibreOffice"):
        assemble_packet.main([str(_plan(tmp_path, [{"kind": "docx", "path": str(docx)}]))])
    assert not (tmp_path / "packet.pdf").exists()


def _noise_png(path: Path, w: int, h: int, seed: int = 1) -> Path:
    import random

    from PIL import Image

    rnd = random.Random(seed)
    Image.frombytes("RGB", (w, h), bytes(rnd.getrandbits(8) for _ in range(w * h * 3))).save(path)
    return path


def test_split_exhibit_inherits_section(tmp_path):
    _text_pdf(tmp_path / "lease.pdf", 2)
    _text_pdf(tmp_path / "bills.pdf", 1)
    manifest, pdf = _run_plan(tmp_path, [
        {"kind": "separator", "label": "Exhibit A", "description": "Lease", "section": "Residence"},
        {"kind": "pdf", "path": "lease.pdf", "label": "Exhibit A"},  # no section: takes the separator's
        {"kind": "pdf", "path": "bills.pdf", "label": "Exhibit B", "description": "Bills", "section": "Residence"},
    ])
    assert [it["section"] for it in manifest["items"]] == ["Residence"] * 3
    assert [(e["label"], e["items"]) for e in manifest["exhibits"]] == [("Exhibit A", [1, 2]), ("Exhibit B", [3])]
    marks = outline_entries(pdf)
    assert [m[:2] for m in marks] == [(0, "Residence"), (1, "Exhibit A - Lease"), (2, "lease.pdf"), (1, "Exhibit B - Bills")]
    assert not any("two separate places" in w for w in manifest["warnings"])


def test_reused_or_split_label_is_an_error(tmp_path):
    _text_pdf(tmp_path / "a.pdf")
    with pytest.raises(ToolError, match=r"used at item 1 and again at item 3"):
        _run_plan(tmp_path, [{"kind": "pdf", "path": "a.pdf", "label": "Exhibit A"},
                             {"kind": "pdf", "path": "a.pdf", "label": "Exhibit B"},
                             {"kind": "pdf", "path": "a.pdf", "label": "exhibit a"}])
    with pytest.raises(ToolError, match=r"An exhibit belongs to one section"):
        _run_plan(tmp_path, [{"kind": "pdf", "path": "a.pdf", "label": "Exhibit A", "section": "One"},
                             {"kind": "pdf", "path": "a.pdf", "label": "Exhibit A", "section": "Two"}])


def _matter(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A matter folder with a client document and a stage workspace holding its copy."""
    matter = tmp_path / "Example Matter"
    (matter / "client docs").mkdir(parents=True)
    original = _text_pdf(matter / "client docs" / "Lease.pdf", 2)
    ws = matter / "output" / "security" / "stage-workspaces" / "packet_assembly-20261029"
    copy = ws / "files" / "client docs" / "Lease.pdf"
    copy.parent.mkdir(parents=True)
    shutil.copyfile(original, copy)
    vault = matter / "output" / "working" / "vault" / "packet" / "main"
    vault.mkdir(parents=True)
    return matter, copy, vault


def test_sources_are_matter_relative_with_hashes(tmp_path):
    matter, copy, vault = _matter(tmp_path)
    ws = copy.parents[2]
    (ws / "stage manifest.json").write_text(json.dumps({"files": [  # as scripts/secure_stage.py writes it
        {"original_path": str(matter / "client docs" / "Lease.pdf"), "relative_path": "client docs/Lease.pdf",
         "workspace_path": str(copy), "original_sha256": "0" * 64}]}), encoding="utf-8")
    plan = vault / "packet plan.json"
    plan.write_text(json.dumps({"base_dir": str(matter), "output": "output/deliverables/Filing Packet.pdf", "items": [
        {"kind": "pdf", "path": str(copy), "label": "Exhibit A", "description": "Lease", "section": "Residence"},
        {"kind": "pdf", "path": "client docs/Lease.pdf", "pages": "2", "label": "Exhibit B", "section": "Residence"},
    ]}), encoding="utf-8")
    assert assemble_packet.main([str(plan), "--manifest", str(vault / "packet manifest.json")]) == 0
    manifest = json.loads((vault / "packet manifest.json").read_text(encoding="utf-8"))
    assert manifest["matter_root"] == str(matter.resolve())
    first, second = (it["sources"][0] for it in manifest["items"])
    assert first["path"] == second["path"] == "client docs/Lease.pdf"  # the copy maps back to the original
    assert first["mapped_from_working_copy"] is True and "mapped_from_working_copy" not in second
    assert first["sha256"] == second["sha256"] == sha(matter / "client docs" / "Lease.pdf")
    assert any("changed after the working copy was made" in w for w in manifest["warnings"])  # stated hash differs

    # Without a stage manifest, the copy's place under files/ names the original.
    (ws / "stage manifest.json").unlink()
    assert assemble_packet.main([str(plan), "--manifest", str(vault / "m2.json")]) == 0
    m2 = json.loads((vault / "m2.json").read_text(encoding="utf-8"))
    assert m2["items"][0]["sources"][0]["path"] == "client docs/Lease.pdf"
    assert not any("changed after" in w for w in m2["warnings"])

    # A plan based inside a workspace is refused, and so is a copy whose original is gone.
    bad = vault / "bad plan.json"
    bad.write_text(json.dumps({"base_dir": str(ws / "files"), "output": str(vault / "x.pdf"),
                               "items": [{"kind": "pdf", "path": "client docs/Lease.pdf"}]}), encoding="utf-8")
    with pytest.raises(ToolError, match="temporary copy of the matter's files"):
        assemble_packet.main([str(bad)])
    (matter / "client docs" / "Lease.pdf").unlink()
    with pytest.raises(ToolError, match="no longer in the matter folder"):
        assemble_packet.main([str(plan)])


def test_images_not_upscaled_and_one_bookmark_per_photo(tmp_path):
    from PIL import Image

    Image.new("RGB", (120, 80), (10, 10, 10)).save(tmp_path / "tiny.jpg")
    Image.new("RGB", (1600, 1200), (40, 90, 160)).save(tmp_path / "wedding.jpg")
    frames = [Image.new("L", (850, 1100), shade) for shade in (40, 120, 200)]
    frames[0].save(tmp_path / "scan.tiff", save_all=True, append_images=frames[1:])
    heic = False
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
        Image.new("RGB", (800, 600), (100, 150, 200)).save(tmp_path / "photo.heic")
        heic = True
    except Exception:  # noqa: BLE001 - HEIC encoding unavailable on this platform
        pass
    photos = ["tiny.jpg", "wedding.jpg"] + (["photo.heic"] if heic else [])
    captions = ["Engagement, May 2024", "Wedding, June 2024"] + (["Anniversary, June 2025"] if heic else [])
    manifest, pdf = _run_plan(tmp_path, [
        {"kind": "separator", "label": "Exhibit A", "description": "Photographs", "section": "Life together"},
        {"kind": "image", "paths": photos, "captions": captions, "label": "Exhibit A"},
        {"kind": "image", "path": "scan.tiff", "label": "Exhibit B", "description": "Scanned letter", "section": "Life together"},
    ])
    reader = PdfReader(str(pdf))
    by_index = {it["index"]: it for it in manifest["items"]}
    tiny = reader.pages[by_index[2]["packet_start"] - 1]
    drawn = re.findall(rb"([\d.]+) 0 0 ([\d.]+) [\d.]+ [\d.]+ cm\s*/\S+ Do", tiny.get_contents().get_data())
    assert (float(drawn[0][0]), float(drawn[0][1])) == (120.0, 80.0)  # one point per pixel, not page width
    assert any("tiny.jpg is only 120 x 80 pixels" in w for w in manifest["warnings"])
    assert by_index[3]["page_count"] == 3  # each TIFF frame on its own page
    marks = outline_entries(pdf)
    start = by_index[2]["packet_start"]
    expected = [(2, c, start + k) for k, c in enumerate(captions)]
    assert [m for m in marks if m[0] == 2] == expected  # each photo directly under the exhibit
    assert [s["packet_start"] for s in by_index[2]["sources"]] == [start + k for k in range(len(photos))]
    assert all(len(s["sha256"]) == 64 for s in by_index[2]["sources"])
    if heic:
        assert by_index[2]["sources"][2]["path"].endswith("photo.heic")


def test_stamps_index_and_rotated_pages(tmp_path, fx):
    _text_pdf(tmp_path / "letter.pdf", 2)
    _text_pdf(tmp_path / "statements.pdf", 3)
    _text_pdf(tmp_path / "sideways.pdf", 1, rotate=90)
    shutil.copyfile(fx["form1"], tmp_path / "form.pdf")
    items = [
        {"kind": "pdf", "path": "letter.pdf", "description": "Cover Letter"},
        {"kind": "pdf", "path": "form.pdf", "description": "Form I-130"},
        {"kind": "index"},
        {"kind": "separator", "label": "Exhibit A", "description": "Bank statements", "section": "Finances"},
        {"kind": "pdf", "path": "statements.pdf", "label": "Exhibit A"},
        {"kind": "pdf", "path": "sideways.pdf", "label": "Exhibit A"},
        {"kind": "separator", "label": "Exhibit B", "description": "Joint lease", "section": "Residence"},
        {"kind": "placeholder", "label": "Exhibit B", "description": "Joint lease", "note": "Client to send"},
    ]
    manifest, pdf = _run_plan(tmp_path, items)
    reader = PdfReader(str(pdf))
    total = manifest["total_pages"]
    by_index = {it["index"]: it for it in manifest["items"]}
    text = lambda n: reader.pages[n - 1].extract_text()  # noqa: E731
    assert "packet p." not in text(1).lower()  # the cover letter is left as it is
    assert "packet p." not in text(by_index[2]["packet_start"]).lower()  # so is the form
    assert by_index[1]["role"] == "cover_letter" and by_index[2]["role"] == "form"
    assert by_index[1]["stamped"] is False and by_index[2]["stamped"] is False
    assert f"Packet p. {by_index[3]['packet_start']} of {total}" in text(by_index[3]["packet_start"])
    a = by_index[5]["packet_start"]
    assert f"Ex. A, p. 1/4 (packet p. {a} of {total})" in text(a)
    assert f"Ex. A, p. 3/4 (packet p. {a + 2} of {total})" in text(a + 2)
    side = reader.pages[by_index[6]["packet_start"] - 1]
    assert side.get("/Rotate", 0) == 0 and float(side.mediabox.width) > float(side.mediabox.height)
    assert f"Ex. A, p. 4/4" in side.extract_text()  # stamped upright on the turned page
    index_text = text(by_index[3]["packet_start"])
    assert "Index of Exhibits" in index_text and "Finances" in index_text and "Bank statements" in index_text
    assert f"{a}-{a + 3}" in index_text  # content pages, without the separator
    assert f"to be supplied, p. {by_index[8]['packet_start']}" in index_text
    assert manifest["exhibits"][0]["packet_start"] == by_index[4]["packet_start"]

    unmarked, pdf2 = _run_plan(tmp_path, items, "--no-stamps")
    assert unmarked["stamps"] is False
    assert all("packet p." not in p.extract_text().lower() for p in PdfReader(str(pdf2)).pages)


def test_notes_payment_order_and_online(tmp_path):
    _text_pdf(tmp_path / "letter.pdf")
    _text_pdf(tmp_path / "G-1450.pdf")
    items = [{"kind": "pdf", "path": "letter.pdf", "description": "Cover Letter"},
             {"kind": "pdf", "path": "G-1450.pdf", "description": "Form G-1450, card payment for the I-130"}]
    notes = ["Two passport photos of the beneficiary", "Sealed I-693 envelope"]
    manifest, _ = _run_plan(tmp_path, items, notes=notes)
    assert manifest["notes"] == notes and manifest["filing_method"] == "paper"
    assert any("payment form goes on top of a paper packet" in w for w in manifest["warnings"])
    on_top, _ = _run_plan(tmp_path, items[::-1])
    assert not any("payment form" in w for w in on_top["warnings"])
    online, _ = _run_plan(tmp_path, items[::-1], filing_method="online")
    assert any("paid in the USCIS online account" in w for w in online["warnings"])
    with pytest.raises(ToolError, match='"notes" must be a list'):
        _run_plan(tmp_path, items, notes=[1, 2])
    with pytest.raises(ToolError, match='"filing_method" must be'):
        _run_plan(tmp_path, items, filing_method="fax")


@pytest.mark.skipif(assemble_packet.find_ghostscript() is None, reason="Ghostscript not installed")
def test_max_mb_resamples_scans_and_photos(tmp_path):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    scan = tmp_path / "scan.pdf"
    c = canvas.Canvas(str(scan), pagesize=letter)
    c.drawImage(str(_noise_png(tmp_path / "noise.png", 1500, 1900)), 36, 36, 540, 720)
    c.showPage()
    c.save()
    from PIL import Image

    Image.open(_noise_png(tmp_path / "photo.png", 1400, 1000, seed=2)).save(tmp_path / "photo.jpg", quality=95)
    items = [{"kind": "pdf", "path": "scan.pdf", "label": "Exhibit A", "description": "Scan"},
             {"kind": "image", "path": "photo.jpg", "label": "Exhibit B", "description": "Photo"}]
    full, pdf = _run_plan(tmp_path, items)
    before = full["file_size_bytes"]
    target = before / 1_048_576 / 2
    small, pdf = _run_plan(tmp_path, items, "--max-mb", f"{target:.2f}")
    assert small["file_size_bytes"] <= target * 1_048_576 < before
    assert small["compression"]["dpi"] in (150, 100) and small["compression"]["ghostscript"] is True
    assert small["items"][0]["sources"][0]["resampled"] is True
    assert small["items"][0]["sources"][0]["sha256"] == sha(scan)  # the manifest still names the original
    assert len(PdfReader(str(pdf)).pages) == 2


def test_split_for_online_upload(tmp_path):
    def photo_pdf(name, pages, seed):
        paths = []
        for k in range(pages):
            p = tmp_path / f"{name}-{k}.png"
            _noise_png(p, 220, 220, seed=seed * 10 + k)
            paths.append(p.name)
        return paths

    _text_pdf(tmp_path / "letter.pdf")
    items = [
        {"kind": "pdf", "path": "letter.pdf", "description": "Cover Letter"},
        {"kind": "image", "paths": photo_pdf("b", 2, 1), "label": "Exhibit A", "description": "Photos", "section": "Marriage"},
        {"kind": "image", "paths": photo_pdf("c", 2, 2), "label": "Exhibit B", "description": "More photos", "section": "Marriage"},
        {"kind": "image", "paths": photo_pdf("d", 3, 3), "label": "Exhibit C", "description": "Big exhibit", "section": "Marriage"},
    ]
    manifest, pdf = _run_plan(tmp_path, items, "--split-max-mb", "0.35", "--no-stamps", filing_method="online")
    files = manifest["upload_files"]
    out_dir = Path(manifest["upload_dir"])
    assert out_dir.name == "packet upload files"
    assert files[0]["file"] == "01 Cover Letter.pdf" and files[0]["pages"] == "1"
    marriage = [f for f in files if f["category"] == "Marriage"]
    assert len(marriage) >= 3 and all("(part " in f["file"] for f in marriage)
    assert all(f["size_bytes"] <= 0.35 * 1_048_576 for f in files)
    covered = [p for f in files for p in range(1, manifest["total_pages"] + 1)
               if any(int(a) <= p <= int(b or a) for a, _, b in (r.partition("-") for r in f["pages"].split(",")))]
    assert covered == list(range(1, manifest["total_pages"] + 1))  # every page once, in order
    assert sorted(x.name for x in out_dir.iterdir() if not x.name.startswith(".")) == [f["file"] for f in files] + [
        "Upload map.md"]
    assert all(len(PdfReader(str(out_dir / f["file"])).pages) == f["page_count"] for f in files)
    # An evidence file's name says which exhibits it holds, so the letter's exhibit list finds it.
    assert marriage[0]["file"].startswith("02 Marriage (Exhibit") and "(part 1 of" in marriage[0]["file"]
    assert all(f["role"] == "evidence" for f in marriage) and files[0]["role"] == "cover_letter"
    # Re-running replaces the old upload files instead of leaving stale ones.
    again, _ = _run_plan(tmp_path, items[:1], "--split-max-mb", filing_method="online")
    assert sorted(x.name for x in out_dir.iterdir() if not x.name.startswith(".")) == ["01 Cover Letter.pdf",
                                                                                         "Upload map.md"]


def test_upload_map_follows_the_filing_channels(tmp_path):
    for name in ("letter", "g28", "i485", "i130", "i765", "i864", "marriage", "lease"):
        _text_pdf(tmp_path / f"{name}.pdf")
    forms = [("g28", "Form G-28"), ("i485", "Form I-485"), ("i130", "Form I-130"), ("i765", "Form I-765"),
             ("i864", "Form I-864")]
    items = [{"kind": "pdf", "path": "letter.pdf", "description": "Cover Letter"}]
    # The forms share a section, but the online account takes each form as its own PDF.
    items += [{"kind": "pdf", "path": f"{n}.pdf", "description": d, "section": "Forms", "role": "form"} for n, d in forms]
    items += [{"kind": "separator", "label": "Exhibit A", "description": "Marriage certificate", "section": "Marriage"},
              {"kind": "pdf", "path": "marriage.pdf", "label": "Exhibit A"},
              {"kind": "separator", "label": "Exhibit B", "description": "Lease", "section": "Marriage"},
              {"kind": "pdf", "path": "lease.pdf", "label": "Exhibit B"}]
    fees_json = tmp_path / "fees.json"
    fees_json.write_text(json.dumps(fees.calculate(["G-28", "I-485", "I-130", "I-765", "I-864"], "online", [])),
                         encoding="utf-8")
    manifest, _ = _run_plan(tmp_path, items, "--split-max-mb", "--channels", str(fees_json), filing_method="online")
    names = [f["file"] for f in manifest["upload_files"]]
    assert names == ["01 Cover Letter.pdf", "02 Form G-28.pdf", "03 Form I-485.pdf", "04 Form I-130.pdf",
                     "05 Form I-765.pdf", "06 Form I-864.pdf", "07 Marriage (Exhibits A, B).pdf"]
    umap = manifest["upload_map"]
    [sub] = umap["submissions"]
    assert sub["lead"] == "I-485" and umap["unplaced"] == [] and umap["general"] == []
    said = {row["file"]: row["upload_as"] for row in sub["files"]}
    assert said["03 Form I-485.pdf"].startswith("the I-485 form PDF") and "signed in ink" in said["03 Form I-485.pdf"]
    assert said["04 Form I-130.pdf"].startswith("a companion form: add the I-130")
    assert said["06 Form I-864.pdf"].startswith("the I-864, with the I-485") and "both" in said["06 Form I-864.pdf"]
    assert said["07 Marriage (Exhibits A, B).pdf"] == "evidence"
    # One G-28 for three forms: the account needs one for each party and form.
    assert any("hold 1 G-28 for 3 forms" in w for w in manifest["warnings"])
    assert not any("No upload file holds" in w for w in manifest["warnings"])
    page = Path(umap["file"]).read_text(encoding="utf-8")
    assert "## Submission 1: I-485 with I-130, I-765 (PDF upload)" in page
    assert "\"Upload a Filled-Out PDF Form\"" in page and "`07 Marriage (Exhibits A, B).pdf`: evidence" in page

    # A split filing is two packets; a form in the wrong one is a warning in either.
    split_json = tmp_path / "split.json"
    split_json.write_text(json.dumps(fees.calculate(["I-485", "I-765"], "online", ["vawa"])), encoding="utf-8")
    online, _ = _run_plan(tmp_path, items[:1] + items[2:4], "--split-max-mb", "--channels", str(split_json),
                          filing_method="online")
    assert any("the I-765 goes on paper in this filing" in w for w in online["warnings"]) is False
    with_i765 = items[:1] + [items[2], items[4]]
    online, _ = _run_plan(tmp_path, with_i765, "--split-max-mb", "--channels", str(split_json), filing_method="online")
    assert any("the I-765 goes on paper in this filing" in w for w in online["warnings"])
    assert online["upload_map"]["unplaced"][0]["file"] == "03 Form I-765.pdf"
    assert "## On paper" in Path(online["upload_map"]["file"]).read_text(encoding="utf-8")
    paper, _ = _run_plan(tmp_path, [items[2]], "--channels", str(split_json))
    assert any("the I-485 goes online in this filing" in w for w in paper["warnings"])
    # A G-28 that names its form goes with that form's submission; a missing prepared form is a warning.
    _text_pdf(tmp_path / "g28-i130.pdf")
    named = [items[0], {"kind": "pdf", "path": "g28-i130.pdf", "description": "Form G-28 - I-130", "role": "form"},
             items[2]]
    manifest, _ = _run_plan(tmp_path, named, "--split-max-mb", "--channels", str(fees_json), filing_method="online")
    rows = {r["file"]: r for r in manifest["upload_map"]["submissions"][0]["files"]}
    assert rows["02 Form G-28 for the I-130.pdf"]["upload_as"] == "the G-28 for the I-130"
    assert any("No upload file holds the I-130" in w for w in manifest["warnings"])
    assert any("No upload file holds the I-864" in w for w in manifest["warnings"])



def test_upload_names_are_short_and_each_g28_says_its_form(tmp_path):
    g28_title = "Form G-28, Notice of Entry of Appearance as Attorney or Accredited Representative"
    assert assemble_packet._safe_name(g28_title) == "Form G-28"
    assert assemble_packet._safe_name("Joint " * 20) == ("Joint " * 13).strip()
    forms_dir = tmp_path / "Forms"
    forms_dir.mkdir()
    for name in ("G-28 - I-130", "I-130", "I-130A", "G-28 - I-485", "I-485"):
        _text_pdf(forms_dir / f"{name}.pdf")
    _text_pdf(tmp_path / "letter.pdf")
    titles = {"I-130": "Form I-130, Petition for Alien Relative",
              "I-130A": "Form I-130A, Supplemental Information for Spouse Beneficiary",
              "I-485": "Form I-485, Application to Register Permanent Residence or Adjust Status"}
    items = [{"kind": "pdf", "path": "letter.pdf", "description": "Cover Letter"}]
    items += [{"kind": "pdf", "path": f"Forms/{n}.pdf", "description": titles.get(n, g28_title), "section": "Forms",
               "role": "form"} for n in ("G-28 - I-130", "I-130", "I-130A", "G-28 - I-485", "I-485")]
    fees_json = tmp_path / "fees.json"
    fees_json.write_text(json.dumps(fees.calculate(["G-28", "I-130", "I-130A", "I-485"], "online", [])),
                         encoding="utf-8")
    manifest, _ = _run_plan(tmp_path, items, "--split-max-mb", "--channels", str(fees_json), filing_method="online")
    names = [f["file"] for f in manifest["upload_files"]]
    # Cut at a clause, never mid-word, and the two G-28s don't share a name.
    assert names == ["01 Cover Letter.pdf", "02 Form G-28 for the I-130.pdf", "03 Form I-130, Petition for Alien Relative.pdf",
                     "04 Form I-130A, Supplemental Information for Spouse Beneficiary.pdf", "05 Form G-28 for the I-485.pdf",
                     "06 Form I-485, Application to Register Permanent Residence or Adjust Status.pdf"]
    rows = {r["file"]: r["upload_as"] for r in manifest["upload_map"]["submissions"][0]["files"]}
    assert rows["05 Form G-28 for the I-485.pdf"] == "the G-28 for the I-485"
    # The I-130A rides in the I-485's upload, but it supplements the I-130.
    assert rows[names[3]].startswith("evidence for the I-130, which files with the I-485: the I-130A")

@pytest.mark.skipif(_packet_common.find_soffice() is None, reason="LibreOffice not installed")
def test_docx_item(tmp_path):
    from docx import Document

    doc = Document()
    doc.add_paragraph("Affidavit of a family friend about the couple.")
    doc.save(str(tmp_path / "affidavit.docx"))
    manifest, pdf = _run_plan(tmp_path, [{"kind": "docx", "path": "affidavit.docx", "label": "Exhibit A",
                                          "description": "Affidavit"}])
    assert manifest["items"][0]["page_count"] == 1
    assert "Affidavit of a family friend" in PdfReader(str(pdf)).pages[0].extract_text()
    assert manifest["items"][0]["sources"][0]["sha256"] == sha(tmp_path / "affidavit.docx")


# ---------------------------------------------------------------------------
# fees.py, render_document.py, translations.py, letter_check.py
# ---------------------------------------------------------------------------
def test_fees_paper_family_packet(tmp_path, capsys):
    result = fees.calculate(["I-130", "I-130A", "i485", "I-864", "I-765", "I-131", "G-28"], "paper", [])
    by_form = {line["form"]: line for line in result["lines"]}
    assert {f: by_form[f]["fee"] for f in by_form} == {
        "I-130": 675, "I-130A": 0, "I-485": 1440, "I-864": 0, "I-765": 260, "I-131": 630, "G-28": 0}
    assert by_form["I-765"]["category"] == "with_pending_i485"  # filed with a fee-paying I-485
    assert by_form["I-131"]["category"] == "advance_parole"
    assert result["total"] == 3005
    assert [p["form"] for p in result["payment_forms_needed"]] == ["I-130", "I-485", "I-765", "I-131"]
    assert "G-1450" in by_form["I-130"]["payment"] and by_form["I-864"]["payment"] == "no fee"
    assert any("own payment form" in n and "on top" in n for n in result["notes"])
    assert result["fee_schedule"]["edition"] == "10/26/26"
    flat = json.dumps(result).lower()
    assert "card number" not in flat and "routing" not in flat  # never asks for payment details


def test_fees_online_and_categories(tmp_path):
    online = fees.calculate(["I-130", "I-485", "I-765"], "online", [])
    assert [line["fee"] for line in online["lines"]] == [625, 1390, 260] and online["total"] == 2275
    assert all(line["payment"] == "pay in the USCIS online account" for line in online["lines"])
    assert online["payment_forms_needed"] == []
    vawa = fees.calculate(["I-360", "I-485", "I-765"], "paper", ["vawa"])
    assert vawa["total"] == 0 and [line["category"] for line in vawa["lines"]] == ["vawa", "vawa", "vawa"]
    child = fees.calculate(["I-485"], "paper", ["I-485=under14_with_parent"])
    assert child["lines"][0]["fee"] == 950
    eb = fees.calculate(["I-140"], "paper", ["self_petitioner"])
    assert eb["lines"][0]["additional_fees"] == [{"name": "Asylum Program Fee", "amount": 300, "separate_payment": False}]
    assert eb["total"] == 1015 and [p["amount"] for p in eb["lines"][0]["payments"]] == [1015]
    asylum = fees.calculate(["I-765"], "paper", ["c8_initial"])
    assert asylum["lines"][0]["fee"] == 0 and asylum["total"] == 570
    # A form USCIS takes only on paper goes on paper, priced and paid as paper, and the attorney is told why.
    fiance = fees.calculate(["I-129F"], "online", [])
    assert fiance["problems"] == [] and fiance["lines"][0]["filing_method"] == "paper"
    assert fiance["lines"][0]["fee"] == 675 and "G-1450" in fiance["lines"][0]["payment"]
    assert [p["form"] for p in fiance["payment_forms_needed"]] == ["I-129F"]
    assert any("I-129F goes on paper" in d for d in fiance["channels"]["decisions"])
    with pytest.raises(ToolError, match="depends on what is requested"):
        fees.calculate(["I-131"], "paper", [])
    with pytest.raises(ToolError, match="No fee entry for I-589"):
        fees.calculate(["I-589"], "paper", [])
    with pytest.raises(ToolError, match="doesn't apply to any"):
        fees.calculate(["I-130"], "paper", ["vawa"])


def test_fees_output_path_is_inside_the_matter(tmp_path, monkeypatch, capsys):
    # A relative --output lands in the matter folder, wherever the command runs from (it once landed in the cwd).
    matter, elsewhere = tmp_path / "matter", tmp_path / "elsewhere"
    matter.mkdir()
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    rel = "output/working/vault/forms/main/fees.json"
    assert fees.main([str(matter), "--forms", "I-130", "--filing-method", "paper", "--output", rel]) == 0
    assert json.loads((matter / rel).read_text(encoding="utf-8"))["total"] == 675
    assert list(elsewhere.iterdir()) == []
    absolute = tmp_path / "fees.json"
    assert fees.main([str(matter), "--forms", "I-130", "--filing-method", "paper", "--output", str(absolute)]) == 0
    assert absolute.is_file()


def test_online_fees_say_nothing_about_payment_forms_or_card_details():
    # An online (c)(8) I-765 is paid in the account: no G-1450/G-1650, no card or bank details to leave blank.
    for forms, cats in ((["I-765"], ["c8_initial"]), (["I-765"], ["c8_renewal"]), (["I-130", "I-485", "I-765"], []),
                        (["I-140"], ["self_petitioner"])):
        online = fees.calculate(forms, "online", cats)
        said = " ".join(online["notes"] + [line["payment"] for line in online["lines"]]
                        + [p["payment"] for line in online["lines"] for p in line["payments"]])
        for word in ("G-1450", "G-1650", "G-1651", "payment form", "card or bank details", "on top", "checks"):
            assert word not in said, (forms, word)
        assert online["payment_forms_needed"] == [] and "https://www.uscis.gov/g-1450" not in online["sources"]
        assert any("online account" in n and "Pay.gov" in n for n in online["notes"])
    renewal = fees.calculate(["I-765"], "online", ["c8_renewal"])
    assert [(p["what"], p["amount"], p["payment"]) for p in renewal["lines"][0]["payments"]] == [
        ("filing fee", 470, "pay in the USCIS online account"),
        ("Pub. L. 119-21 fee", 275, "pay in the USCIS online account")]
    assert "2 payments" in renewal["lines"][0]["payment"]
    assert any("separate payment concurrent" in n and "online account" in n for n in renewal["notes"])
    paper = fees.calculate(["I-765"], "paper", ["c8_renewal"])
    assert any("card or bank details" in n for n in paper["notes"])
    assert any("card or bank details" in n for n in fees.calculate(["I-130"], "paper", [])["notes"])


def test_render_document_checklist(tmp_path):
    md = tmp_path / "Filing Checklist.md"
    md.write_text(
        "# Filing checklist\n\nJane Example for John Example, Form I-130 and I-485.\n\n## Fees\n\n"
        "- [ ] Form G-1450 for the I-130: **$675**\n- [x] Form G-1450 for the I-485: $1,440\n\n"
        "## Signatures\n\n1. Jane signs the I-130, Part 6.\n2. John signs the I-485, Part 10.\n\n"
        "Checked by: ______________________\n", encoding="utf-8")
    assert render_document.main([str(md)]) == 0
    pdf, docx_path = tmp_path / "Filing Checklist.pdf", tmp_path / "Filing Checklist.docx"
    text = PdfReader(str(pdf)).pages[0].extract_text()
    for needle in ("Filing checklist", "Form G-1450 for the I-130: $675", "1.", "Jane signs the I-130", "Checked by:"):
        assert needle in text, needle
    from docx import Document

    paras = [p.text for p in Document(str(docx_path)).paragraphs]
    assert "☐\tForm G-1450 for the I-130: $675" in paras and "☑\tForm G-1450 for the I-485: $1,440" in paras
    assert render_document.main([str(md), "--formats", "pdf", "--name", "only pdf"]) == 0
    assert (tmp_path / "only pdf.pdf").is_file() and not (tmp_path / "only pdf.docx").exists()


def test_render_document_memo_tables_and_lists(tmp_path):
    # The attorney memo: a case-assessment table, and a numbered list right under a bold label (no blank line).
    md = tmp_path / "Attorney Memo.md"
    md.write_text(
        "# Attorney memo: Jane Example for John Example, I-130\n\n## Needed before filing\n"
        "**Your decisions (2)**\n1. **File now?** The lease is late.\n2. **Add the I-864A?** Income is close.\n\n"
        "## Case assessment\n| Element | Evidence | Strength |\n| --- | --- | --- |\n"
        "| Bona fide marriage | Exh. C (lease); Exh. D (bank \\| joint) | **Strong** |\n| Status | Exh. A | Complete |\n\n"
        "Officer's strongest objection: thin records.\n", encoding="utf-8")
    assert render_document.main([str(md)]) == 0
    text = PdfReader(str(tmp_path / "Attorney Memo.pdf")).pages[0].extract_text()
    assert "Your decisions (2)" in text.splitlines()  # its own line: the list isn't run into the label
    for needle in ("Element", "Evidence", "Bona fide marriage", "bank | joint", "Strong", "thin records"):
        assert needle in text, needle
    assert "---" not in text and "| Status" not in text
    from docx import Document

    table = Document(str(tmp_path / "Attorney Memo.docx")).tables[0]
    assert [[c.text.replace("\xa0", " ") for c in row.cells] for row in table.rows] == [
        ["Element", "Evidence", "Strength"], ["Bona fide marriage", "Exh. C (lease); Exh. D (bank | joint)", "Strong"],
        ["Status", "Exh. A", "Complete"]]
    assert table.rows[0].cells[0].paragraphs[0].runs[0].bold


def test_render_document_refuses_text_the_pdf_cannot_show(tmp_path):
    # Right-to-left script would come out backwards; the Markdown stays the attorney's copy.
    md = tmp_path / "Client Request (Arabic).md"
    md.write_text("# طلب المستندات\n\nيرجى إرسال جواز السفر.\n", encoding="utf-8")
    with pytest.raises(render_document.ToolError, match="right-to-left"):
        render_document.main([str(md), "--formats", "pdf"])
    assert not (tmp_path / "Client Request (Arabic).pdf").exists()
    spanish = tmp_path / "Client Request (Spanish).md"
    spanish.write_text("# Documentos que necesitamos\n\n1. Envíe el pasaporte de Begoña, por favor.\n", encoding="utf-8")
    assert render_document.main([str(spanish), "--formats", "pdf"]) == 0
    assert "Begoña" in PdfReader(str(tmp_path / "Client Request (Spanish).pdf")).pages[0].extract_text()


def test_open_and_done_checklist_items_are_drawn_differently(tmp_path):
    # An open step is an empty box; a done step has a check mark in its box (both used to print as one filled glyph).
    def ops(name: str, item: str) -> list[str]:
        md = tmp_path / f"{name}.md"
        md.write_text(f"# Steps\n\n{item}\n", encoding="utf-8")
        assert render_document.main([str(md), "--formats", "pdf"]) == 0
        stream = PdfReader(str(tmp_path / f"{name}.pdf")).pages[0].get_contents().get_data().decode("latin-1")
        return re.findall(r"(?<![A-Za-z])(re|m|l|S|f|B|Tj)(?![A-Za-z])", stream)

    open_ops, done_ops = ops("open", "- [ ] Mail the packet"), ops("done", "- [x] Mail the packet")
    assert open_ops.count("re") == done_ops.count("re") == 1  # each item has one box
    assert "f" not in open_ops and "B" not in open_ops  # the open box is outlined, never filled
    assert open_ops.count("l") == 0 and done_ops.count("l") == 2  # the check mark: two strokes, only when done
    assert "ZapfDingbats" not in (tmp_path / "open.pdf").read_bytes().decode("latin-1")
    if shutil.which("pdftoppm"):  # and on the page: the done box carries more ink than the open one
        def ink(name: str) -> int:
            # At 150 dpi the box sits 1.3 in from the page's left edge, left of the text at 1.55 in.
            subprocess.run(["pdftoppm", "-r", "150", "-gray", "-f", "1", "-l", "1", "-x", "185", "-y", "150", "-W", "43",
                            "-H", "150", str(tmp_path / f"{name}.pdf"), str(tmp_path / name)], check=True)
            pgm = next(tmp_path.glob(f"{name}*.pgm")).read_bytes()
            return sum(1 for byte in pgm[-43 * 150:] if byte < 128)

        assert ink("done") > ink("open") > 0


def test_translation_certificate_template_renders(tmp_path):
    template = TOOLS.parents[1] / "skills" / "docs-review" / "references" / "translation-certificate.md"
    copy = tmp_path / "translation certificate - birth certificate.md"
    shutil.copyfile(template, copy)
    assert render_document.main([str(copy), "--out-dir", str(tmp_path)]) == 0
    text = " ".join(PdfReader(str(tmp_path / f"{copy.stem}.pdf")).pages[0].extract_text().split())
    assert "Certificate of Translation" in text
    assert "competent to translate" in text and "complete and accurate" in text  # 8 C.F.R. 103.2(b)(3)
    assert "How to use it" not in text  # the guidance comment isn't rendered


def test_translation_needs_from_extracts(tmp_path, capsys):
    matter = tmp_path / "matter"
    extracts = matter / "output" / "working" / "extracts"
    extracts.mkdir(parents=True)
    (extracts / "index.json").write_text(json.dumps({"version": 1, "files": {
        "civil/Birth certificate.pdf": {"sha256": "a" * 64, "pages": 2, "chars": 900, "method": "text",
                                        "language": "es", "non_english_pages": [1, 2], "needs_translation": True},
        "civil/Marriage record.pdf": {"sha256": "b" * 64, "pages": 4, "chars": 3000, "method": "text",
                                      "language": "pt", "non_english_pages": [3, 4], "needs_translation": True},
        "id/Passport.pdf": {"sha256": "c" * 64, "pages": 1, "chars": 300, "method": "text",
                            "language": "en", "non_english_pages": [], "needs_translation": False},
        "photos/IMG_0001.jpg": {"sha256": "d" * 64, "pages": 1, "chars": 0, "method": "none",
                                "language": "unknown", "non_english_pages": [], "needs_translation": False},
    }}), encoding="utf-8")
    result = translations.translation_needs(matter)
    assert [(n["path"], n["language_name"], n["pages"]) for n in result["needs_translation"]] == [
        ("civil/Birth certificate.pdf", "Spanish", "all"), ("civil/Marriage record.pdf", "Portuguese", "3-4")]
    assert re.fullmatch(r"doc-translation-birth-certificate-[0-9a-f]{6}", result["needs_translation"][0]["suggested_item_id"])
    assert [u["path"] for u in result["unreadable"]] == ["photos/IMG_0001.jpg"]
    assert translations.main([str(matter)]) == 0
    out = capsys.readouterr().out
    assert "Needs a certified translation: 2" in out and "Portuguese, pages 3-4" in out
    with pytest.raises(ToolError, match="Run scripts/extract_documents.py"):
        translations.translation_needs(tmp_path)


def test_a_script_is_never_named_as_one_language(tmp_path):
    matter = tmp_path / "matter"
    extracts = matter / "output" / "working" / "extracts"
    extracts.mkdir(parents=True)
    (extracts / "index.json").write_text(json.dumps({"version": 1, "files": {
        # As the extractor writes it now, and as an earlier one did (the script's commonest language as the code).
        "a/Birth record.pdf": {"sha256": "a" * 64, "pages": 1, "method": "text", "language": "cyrillic",
                               "language_name": "a language written in Cyrillic script", "script_only": True,
                               "non_english_pages": [1], "needs_translation": True},
        "b/Diploma.pdf": {"sha256": "b" * 64, "pages": 1, "method": "text", "language": "ar",
                          "language_name": "Arabic script (Arabic, Persian, Urdu, or another)",
                          "non_english_pages": [1], "needs_translation": True},
        "c/Record.pdf": {"sha256": "c" * 64, "pages": 1, "method": "text", "language": "hi",
                         "non_english_pages": [1], "needs_translation": True},
        "d/Acta.pdf": {"sha256": "d" * 64, "pages": 1, "method": "text", "language": "es", "language_name": "Spanish",
                       "non_english_pages": [1], "needs_translation": True},
    }}), encoding="utf-8")
    named = [(n["language_name"], n["script_only"]) for n in translations.translation_needs(matter)["needs_translation"]]
    assert named == [("a language written in Cyrillic script", True), ("a language written in Arabic script", True),
                     ("a language written in Devanagari script", True), ("Spanish", False)]


CHECK_MD = """---
date: October 28, 2026
to:
  - USCIS
re:
  - Form I-130, Petition for Alien Relative
matter_type: i130_standalone
---

# I. Introduction

Ms. Example petitions for her husband under INA § 201(b)(2)(A)(i) and 8 C.F.R. § 204.2(a)(2). *See* Exhibit A.

# II. The Marriage Is Bona Fide

The question is the couple's intent when they married. *Matter of Laureano*, 19 I&N Dec. 1, 3 (BIA 1983); 6 USCIS-PM B.6(C). They married on June 18, 2022. *See* Exhibit B. They opened a joint account in March 2023, and they have lived together for two years.

```exhibits
# Forms
- Form I-130
# Marriage
- Marriage certificate
```
"""


def _letter_matter(tmp_path, fx) -> Path:
    matter = tmp_path / "matter"
    cl = matter / "output" / "working" / "vault" / "cover-letter" / "main"
    rs = matter / "output" / "working" / "vault" / "research" / "main"
    cl.mkdir(parents=True)
    rs.mkdir(parents=True)
    (matter / "Marriage certificate.pdf").write_bytes(b"%PDF-1.4\n")
    _render(cl, CHECK_MD, "cover letter", fx["profile"], "--out-dir", str(tmp_path / "deliverables"), "--name",
            "Cover Letter", summary=cl / "cover letter audit.json")
    (cl / "exhibit plan.json").write_text(json.dumps({"labels": "letters", "exhibits": [
        {"label": "A", "section": "Forms", "description": "Form I-130", "placeholder": True, "open_item": "form-i130"},
        {"label": "B", "section": "Marriage", "description": "Marriage certificate", "sources": ["Marriage certificate.pdf"]},
    ]}), encoding="utf-8")
    (rs / "support matrix.json").write_text(json.dumps({"propositions": [
        {"id": "P1", "support": [{"authority": "INA § 201(b)(2)(A)(i)", "citation": "8 U.S.C. § 1151(b)(2)(A)(i)"},
                                 {"authority": "8 C.F.R. § 204.2(a)(2)"}]},
        {"id": "P2", "support": [{"authority": "Matter of Laureano", "citation": "19 I&N Dec. 1 (BIA 1983)"},
                                 {"authority": "6 USCIS-PM B.6(C)(1)"}]},
    ]}), encoding="utf-8")
    (cl / "letter facts.json").write_text(json.dumps({"facts": [
        {"text": "opened a joint account in March 2023", "source": "Joint account statements.pdf p. 1"},
        {"text": "lived together for two years", "source": "Lease 2024.pdf; Lease 2025.pdf", "as_of": "2026-10-28"},
    ]}), encoding="utf-8")
    return matter


def test_letter_check_clean_and_each_failure(tmp_path, fx, capsys):
    matter = _letter_matter(tmp_path, fx)
    cl = matter / "output" / "working" / "vault" / "cover-letter" / "main"
    capsys.readouterr()
    assert letter_check.main([str(matter)]) == 0
    result = json.loads((cl / "letter check.json").read_text(encoding="utf-8"))
    assert result["error_count"] == 0, result["errors"]
    assert {a["key"] for a in result["authorities"]} == {
        "INA 201", "8 CFR 204.2", "case 19 I&NDec. 1", "6 USCIS-PM B.6"}
    assert result["facts"] == {"fact_sentences": 2, "sourced": 2, "computed_phrases": 1, "fact_table_entries": 2}
    assert "Letter check: clean" in capsys.readouterr().out

    # An authority the research never verified.
    md = cl / "cover letter.md"
    md.write_text(CHECK_MD.replace("6 USCIS-PM B.6(C).", "6 USCIS-PM B.6(C); *Matter of McKee*, 17 I&N Dec. 332 (BIA 1980)."),
                  encoding="utf-8")
    result = letter_check.check_letter(matter, md, cl / "cover letter audit.json", cl / "exhibit plan.json",
                                       matter / "output/working/vault/research/main/support matrix.json",
                                       cl / "letter facts.json")
    assert [e for e in result["errors"] if "support matrix" in e] == [
        "Authority not in the support matrix: 17 I&N Dec. 332. Cite only what the research verified (the support "
        "matrix, or a verified chat research note), or have the researcher add it."]
    md.write_text(CHECK_MD, encoding="utf-8")

    # The plan drifts from the letter, and a placeholder loses its open item.
    plan = json.loads((cl / "exhibit plan.json").read_text(encoding="utf-8"))
    plan["exhibits"][1]["label"] = "C"
    del plan["exhibits"][0]["open_item"]
    (cl / "exhibit plan.json").write_text(json.dumps(plan), encoding="utf-8")
    # A dated fact without a source, and an age missing from the fact table.
    (cl / "letter facts.json").write_text(json.dumps({"facts": []}), encoding="utf-8")
    assert letter_check.main([str(matter), "--json"]) == 0
    errors = json.loads(capsys.readouterr().out)["errors"]
    assert any("labeled C but the letter's exhibit 2 is B" in e for e in errors)
    assert any("placeholder without its open item" in e for e in errors)
    assert any(e.startswith("Fact without a source: 'They opened a joint account in March 2023") for e in errors)
    assert any("Age or duration not in the fact table: 'for two years'" in e for e in errors)
    assert not any("June 18, 2022" in e for e in errors)  # the next sentence cites Exhibit B


def test_letter_check_accepts_authorities_verified_in_the_chat_research_notes(tmp_path, fx):
    # Matter chat may cite an authority it verified and recorded in its research notes; the next check takes it.
    matter = _letter_matter(tmp_path, fx)
    cl = matter / "output" / "working" / "vault" / "cover-letter" / "main"
    notes = matter / "output" / "working" / "vault" / "research" / "chat" / "research notes.md"
    notes.parent.mkdir(parents=True)
    md = cl / "cover letter.md"
    md.write_text(CHECK_MD.replace("6 USCIS-PM B.6(C).", "6 USCIS-PM B.6(C); *Matter of McKee*, 17 I&N Dec. 332, 333-34 "
                                   "(BIA 1980); 8 C.F.R. § 216.5(e)(2)."), encoding="utf-8")

    def errors() -> list[str]:
        result = letter_check.check_letter(matter, md, cl / "cover letter audit.json", cl / "exhibit plan.json",
                                           matter / "output/working/vault/research/main/support matrix.json",
                                           cl / "letter facts.json")
        return [e for e in result["errors"] if "support matrix" in e]

    def entry(n: int, authority: str, verified: str) -> str:
        return (f"## R{n}. A proposition.\n- Authority: {authority}\n- Quote: \"words\"\n- URL: https://example.com\n"
                f"- Verified: {verified}\n- Applies: a line\n- Adverse: none found\n\n")

    notes.write_text(entry(1, "*Matter of McKee*, 17 I&N Dec. 332, 333-34 (BIA 1980); BIA Edge document_id 41",
                           "2026-10-29 · treatment_available, no adverse entries")
                     + entry(2, "8 C.F.R. § 216.5(e)(2)", "Oct. 29, 2026 · current regulation"), encoding="utf-8")
    assert errors() == []
    # A note without a Verified date, or one that records negative treatment, doesn't count.
    notes.write_text(entry(1, "*Matter of McKee*, 17 I&N Dec. 332 (BIA 1980)", "pending")
                     + entry(2, "8 C.F.R. § 216.5(e)(2)", "10/29/2026 · overruled in part"), encoding="utf-8")
    found = errors()
    assert len(found) == 2 and "Chat research note R1 names it" in found[0] and "Chat research note R2" in found[1]
    # An authority named only on an Adverse line isn't covered.
    notes.write_text("## R1. A proposition.\n- Authority: 8 C.F.R. § 216.5(e)(2)\n- Verified: 2026-10-29\n"
                     "- Adverse: *Matter of McKee*, 17 I&N Dec. 332 (BIA 1980)\n", encoding="utf-8")
    assert [e.split(".")[0] for e in errors()] == ["Authority not in the support matrix: 17 I&N Dec"]
    assert letter_check.main([str(matter), "--notes", str(tmp_path / "none.md")]) == 0  # another notes file


def test_letter_check_refuses_a_letter_that_is_not_utf8(tmp_path):
    # A letter saved in another encoding is an input to fix (exit 2), not a traceback.
    (tmp_path / "matter").mkdir()
    letter = tmp_path / "cover letter.md"
    letter.write_bytes("---\ndate: 28 octobre 2026, café\n---\n".encode("latin-1"))
    with pytest.raises(ToolError, match="is not UTF-8 text"):
        letter_check.main([str(tmp_path / "matter"), "--letter", str(letter)])


def test_fact_sentences_ignore_citation_years():
    assert not letter_check.is_fact_sentence("The central question is intent. Matter of Laureano, 19 I&N Dec. 1, 3 (BIA 1983).")
    assert not letter_check.is_fact_sentence("See 91 Fed. Reg. 65306 (Oct. 14, 2026); Form I-130 (ed. 04/01/24).")
    assert letter_check.is_fact_sentence("The couple has lived at 455 Sample Street since August 2024.")
    assert letter_check.is_fact_sentence("They share 14 months of joint statements.")
    assert letter_check.sentences("Jane A. Example filed. See Exhibit A. They married in 2022.") == [
        "Jane A. Example filed.", "See Exhibit A.", "They married in 2022."]


# ---------------------------------------------------------------------------
# Regressions from the independent review
# ---------------------------------------------------------------------------
def _matter_plan(matter: Path, items: list[dict], name: str = "plan.json", **top) -> Path:
    (matter / "output" / "deliverables").mkdir(parents=True, exist_ok=True)
    plan = matter / "output" / name
    plan.write_text(json.dumps({"base_dir": str(matter), "output": "output/deliverables/Packet.pdf",
                                "items": items} | top), encoding="utf-8")
    return plan


def test_split_dir_never_deletes_files_it_did_not_write(tmp_path):
    matter = tmp_path / "matter"
    (matter / "docs").mkdir(parents=True)
    statement = _text_pdf(matter / "docs" / "01 Bank statement.pdf")
    before = sha(statement)
    plan = _matter_plan(matter, [{"kind": "pdf", "path": "docs/01 Bank statement.pdf", "label": "Exhibit A",
                                  "description": "Bank statement", "section": "Finances"}], filing_method="online")
    with pytest.raises(ToolError, match="inside the matter's output/deliverables"):
        assemble_packet.main([str(plan), "--split-max-mb", "--split-dir", str(matter / "docs")])
    assert statement.is_file() and sha(statement) == before
    # A folder in the deliverables that holds a source is refused too.
    shared = matter / "output" / "deliverables" / "Shared"
    shared.mkdir()
    lease = _text_pdf(shared / "01 Lease.pdf")
    plan2 = _matter_plan(matter, [{"kind": "pdf", "path": "output/deliverables/Shared/01 Lease.pdf",
                                   "label": "Exhibit A", "description": "Lease"}], name="plan2.json")
    with pytest.raises(ToolError, match="holds documents the packet is built from"):
        assemble_packet.main([str(plan2), "--split-max-mb", "--split-dir", str(shared)])
    assert lease.is_file()
    # The default folder: written, then replaced on a re-run; a file the tool didn't write stops it.
    assert assemble_packet.main([str(plan), "--split-max-mb"]) == 0
    uploads = matter / "output" / "deliverables" / "Packet upload files"
    assert sorted(x.name for x in uploads.iterdir() if not x.name.startswith(".")) == [
        "01 Finances (Exhibit A).pdf", "Upload map.md"]
    assert assemble_packet.main([str(plan), "--split-max-mb"]) == 0
    stranger = uploads / "02 Notes.pdf"
    _text_pdf(stranger)
    with pytest.raises(ToolError, match="files this tool didn't write"):
        assemble_packet.main([str(plan), "--split-max-mb"])
    assert stranger.is_file() and (uploads / "01 Finances (Exhibit A).pdf").is_file()
    stranger.unlink()
    # The upload map is the tool's only while the tool wrote it: one written by someone else stops it too.
    (uploads / assemble_packet.UPLOADS_RECORD).unlink()
    (matter / "output" / "deliverables" / "Packet.manifest.json").unlink()
    with pytest.raises(ToolError, match=r"didn't write \(01 Finances \(Exhibit A\).pdf, Upload map.md\)"):
        assemble_packet.main([str(plan), "--split-max-mb"])


def test_a_split_filings_paper_run_leaves_the_online_upload_files_rebuildable(tmp_path):
    # The paper part writes its own packet; even sharing the manifest path, the online re-run still owns its files.
    matter = tmp_path / "matter"
    (matter / "docs").mkdir(parents=True)
    _text_pdf(matter / "docs" / "lease.pdf")
    online = _matter_plan(matter, [{"kind": "pdf", "path": "docs/lease.pdf", "label": "Exhibit A",
                                    "description": "Lease", "section": "Residence"}], filing_method="online")
    paper = _matter_plan(matter, [{"kind": "pdf", "path": "docs/lease.pdf", "label": "Exhibit A",
                                   "description": "Lease"}], name="paper.json",
                         output="output/deliverables/Packet (paper part).pdf")
    shared = str(matter / "output" / "deliverables" / "Packet.manifest.json")
    assert assemble_packet.main([str(online), "--split-max-mb"]) == 0
    assert assemble_packet.main([str(paper), "--manifest", shared]) == 0
    assert assemble_packet.main([str(online), "--split-max-mb"]) == 0
    uploads = matter / "output" / "deliverables" / "Packet upload files"
    assert sorted(x.name for x in uploads.iterdir() if not x.name.startswith(".")) == [
        "01 Residence (Exhibit A).pdf", "Upload map.md"]


def _text_positions(page) -> list[tuple[str, float]]:
    """(text, y on the page) for each text run, with the content's transforms applied."""
    out: list[tuple[str, float]] = []

    def visit(text, cm, tm, font, size):
        if text.strip():
            out.append((text.strip(), tm[4] * cm[1] + tm[5] * cm[3] + cm[5]))

    page.extract_text(visitor_text=visit)
    return out


def test_stamps_never_cover_page_content(tmp_path):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    statement = tmp_path / "statement.pdf"
    c = canvas.Canvas(str(statement), pagesize=letter)
    c.drawString(72, 700, "Statement body")
    c.drawRightString(596, 12, "Account ending 0000 Page 1 of 2")  # a footer right where a stamp would go
    c.showPage()
    c.save()
    manifest, pdf = _run_plan(tmp_path, [
        {"kind": "separator", "label": "Exhibit A", "description": "Bank statement", "section": "Finances"},
        {"kind": "pdf", "path": "statement.pdf", "label": "Exhibit A"}])
    page = PdfReader(str(pdf)).pages[1]
    text = page.extract_text()
    assert "Account ending 0000 Page 1 of 2" in text and "Statement body" in text  # nothing lost
    assert f"Ex. A, p. 1/1 (packet p. 2 of 2)" in text
    assert (float(page.mediabox.width), float(page.mediabox.height)) == (612.0, 792.0)  # still Letter
    band = assemble_packet.STAMP_BAND_PT
    positions = _text_positions(page)
    footer = [y for t, y in positions if "Account ending" in t]
    stamp = [y for t, y in positions if t.startswith("Ex. A")]
    assert footer and min(footer) >= band  # the page's own content sits above the band
    assert stamp and max(stamp) < band  # the stamp sits in it


def test_forms_letter_and_payment_are_never_stamped_or_resampled(tmp_path, monkeypatch):
    matter = tmp_path / "matter"
    forms = matter / "output" / "deliverables" / "Forms"
    forms.mkdir(parents=True)
    _text_pdf(forms / "I-130.pdf", 2)  # a flattened filing copy: no form fields left
    _text_pdf(forms / "G-1450 - I-130.pdf")
    _text_pdf(matter / "output" / "deliverables" / "Cover Letter.pdf")
    (matter / "docs").mkdir()
    _text_pdf(matter / "docs" / "lease.pdf")
    _text_pdf(matter / "docs" / "schedule.pdf", 2)
    plan = _matter_plan(matter, [
        {"kind": "pdf", "path": "output/deliverables/Forms/G-1450 - I-130.pdf", "description": "Payment"},
        {"kind": "pdf", "path": "output/deliverables/Cover Letter.pdf", "description": "Cover Letter"},
        {"kind": "pdf", "path": "output/deliverables/Forms/I-130.pdf", "description": "Petition"},
        {"kind": "separator", "label": "Exhibit A", "description": "Lease and its schedule", "section": "Residence"},
        {"kind": "pdf", "path": "docs/schedule.pdf", "label": "Exhibit A", "role": "form"},
        {"kind": "pdf", "path": "docs/lease.pdf", "label": "Exhibit A"},
    ])
    assert assemble_packet.main([str(plan), "--manifest", str(matter / "m.json")]) == 0
    manifest = json.loads((matter / "m.json").read_text(encoding="utf-8"))
    by_index = {it["index"]: it for it in manifest["items"]}
    assert [by_index[i]["role"] for i in (1, 2, 3, 5, 6)] == ["payment", "cover_letter", "form", "form", "exhibit"]
    assert [by_index[i]["stamped"] for i in (1, 2, 3, 5, 6)] == [False, False, False, False, True]
    reader = PdfReader(str(matter / "output" / "deliverables" / "Packet.pdf"))
    for i in (1, 2, 3, 5):
        for n in range(by_index[i]["packet_start"], by_index[i]["packet_end"] + 1):
            assert "packet p." not in reader.pages[n - 1].extract_text().lower()
    # The exhibit's page count includes the two unstamped pages before it.
    assert "Ex. A, p. 3/3" in reader.pages[by_index[6]["packet_start"] - 1].extract_text()

    # --max-mb never sends a form, the payment form or the letter to Ghostscript, and a failed
    # resample isn't reported as done.
    sent: list[str] = []

    def fake_compress(src, dest, dpi, gs):
        sent.append(Path(src).name)
        return False

    monkeypatch.setattr(assemble_packet, "_compress_pdf", fake_compress)
    monkeypatch.setattr(assemble_packet, "find_ghostscript", lambda: "/usr/bin/true")
    assert assemble_packet.main([str(plan), "--manifest", str(matter / "m2.json"), "--max-mb", "0.0001"]) == 0
    small = json.loads((matter / "m2.json").read_text(encoding="utf-8"))
    assert set(sent) == {"lease.pdf"}
    assert small["compression"]["resampled_items"] == []
    assert not any(s.get("resampled") for it in small["items"] for s in it["sources"])


def _prepared_forms(matter: Path, built_in: Path | None = None, **extra: dict) -> Path:
    """A matter's filing copies and the forms step's manifest of them, as forms_workflow.py build writes it:
    keyed by absolute path (in `built_in` when the forms were built while the matter was in another folder)."""
    forms = matter / "output" / "deliverables" / "Forms"
    forms.mkdir(parents=True, exist_ok=True)
    entries = {
        "G-1450 - I-130 filing fee.pdf": {"kind": "g-1450", "pays_for": "I-130", "pays_what": "filing fee",
                                          "pays_amount": 675, "fee_order": 1},
        "G-1450 - I-765 filing fee.pdf": {"kind": "g-1450", "pays_for": "I-765", "pays_what": "filing fee",
                                          "pays_amount": 520, "fee_order": 2},
        "G-1450 - I-765 Pub. L. 119-21 fee.pdf": {"kind": "g-1450", "pays_for": "I-765",
                                                  "pays_what": "Pub. L. 119-21 fee", "pays_amount": 275, "fee_order": 3},
        "G-1145.pdf": {"kind": "g-1145"},
        "I-130.pdf": {"kind": "i-130"},
        **extra,
    }
    for name in entries:
        _text_pdf(forms / name)
    where = (built_in or matter) / "output" / "deliverables" / "Forms"
    vault = matter / "output" / "working" / "vault" / "forms" / "main"
    vault.mkdir(parents=True, exist_ok=True)
    manifest = vault / "form intent manifest.json"
    manifest.write_text(json.dumps({"files": {str(where / name): dict(entry, questions=[])
                                              for name, entry in entries.items()}}), encoding="utf-8")
    return manifest


def test_payment_forms_go_on_top_in_fee_order_then_the_g1145_then_the_letter(tmp_path):
    matter = tmp_path / "matter"
    _prepared_forms(matter, built_in=Path("/Volumes/Old Drive/Example Matter"))  # the matter moved since
    _text_pdf(matter / "output" / "deliverables" / "Cover Letter.pdf")
    _text_pdf(matter / "output" / "deliverables" / "Forms" / "G-1450 - I-130.pdf")  # an earlier build's copy
    (matter / "docs").mkdir()
    _text_pdf(matter / "docs" / "lease.pdf")
    forms = "output/deliverables/Forms"
    plan = _matter_plan(matter, [
        {"kind": "pdf", "path": "output/deliverables/Cover Letter.pdf", "description": "Cover Letter"},
        {"kind": "pdf", "path": f"{forms}/I-130.pdf", "description": "Petition"},
        {"kind": "pdf", "path": f"{forms}/G-1145.pdf", "description": "E-notification"},
        {"kind": "pdf", "path": f"{forms}/G-1450 - I-765 Pub. L. 119-21 fee.pdf", "description": "Payment"},
        {"kind": "pdf", "path": f"{forms}/G-1450 - I-130 filing fee.pdf", "description": "Payment"},
        {"kind": "pdf", "path": f"{forms}/G-1450 - I-130.pdf", "description": "Payment"},
        {"kind": "separator", "label": "Exhibit A", "description": "Lease", "section": "Residence"},
        {"kind": "pdf", "path": "docs/lease.pdf", "label": "Exhibit A"},
    ])
    assert assemble_packet.main([str(plan), "--manifest", str(matter / "m.json")]) == 0
    manifest = json.loads((matter / "m.json").read_text(encoding="utf-8"))
    # The fee order and the G-1145 come from the forms step's manifest; the earlier copy isn't moved.
    assert [it["index"] for it in manifest["items"]] == [5, 4, 3, 1, 2, 6, 7, 8]
    assert [it["role"] for it in manifest["items"][:5]] == ["payment", "payment", "form", "cover_letter", "form"]
    order = manifest["filing_order"]
    assert order["moved"] is True
    assert order["checked_with"] == ["output/working/vault/forms/main/form intent manifest.json"]
    assert [(f["what"], f.get("fee_order")) for f in order["front"]] == [
        ("payment", 1), ("payment", 3), ("g-1145", None), ("cover_letter", None)]
    assert order["front"][1]["pays_what"] == "Pub. L. 119-21 fee"
    warnings = manifest["warnings"]
    assert any("item 6" in w and "isn't one the forms step prepared" in w for w in warnings)
    assert any("payment form for the I-765 filing fee (G-1450 - I-765 filing fee.pdf) isn't in the packet" in w
               for w in warnings)
    assert not any("goes at the top" in w for w in warnings)
    reader = PdfReader(str(matter / "output" / "deliverables" / "Packet.pdf"))
    assert reader.pages[0].extract_text().startswith("G-1450 - I-130 filing fee")
    line = assemble_packet.front_matter_line(order)
    assert line == ("on top, the payment forms in fee order (I-130 filing fee; I-765 Pub. L. 119-21 fee), then the "
                    "G-1145, then the cover letter; placed by the tool, not in the plan's order")

    # A front item that carries an exhibit label stays put, and the check says so; a repeated place is flagged.
    _prepared_forms(matter, **{"G-1650 - I-130 filing fee.pdf": {"kind": "g-1650", "pays_for": "I-130",
                                                                  "pays_what": "filing fee", "fee_order": 1}})
    plan = _matter_plan(matter, [
        {"kind": "pdf", "path": "output/deliverables/Cover Letter.pdf", "description": "Cover Letter"},
        {"kind": "pdf", "path": f"{forms}/G-1450 - I-130 filing fee.pdf"},
        {"kind": "pdf", "path": f"{forms}/G-1650 - I-130 filing fee.pdf"},
        {"kind": "pdf", "path": f"{forms}/G-1450 - I-765 filing fee.pdf"},
        {"kind": "pdf", "path": f"{forms}/G-1450 - I-765 Pub. L. 119-21 fee.pdf"},
        {"kind": "pdf", "path": f"{forms}/G-1145.pdf", "label": "Exhibit A", "section": "Forms"},
    ])
    assert assemble_packet.main([str(plan), "--manifest", str(matter / "m2.json")]) == 0
    second = json.loads((matter / "m2.json").read_text(encoding="utf-8"))
    assert [it["index"] for it in second["items"]] == [2, 3, 4, 5, 1, 6]
    assert any("item 6" in w and "the G-1145 goes at the top" in w and "exhibit label" in w for w in second["warnings"])
    assert any("all have place 1 in the fee order" in w for w in second["warnings"])


def test_an_online_packet_has_no_payment_form_or_g1145(tmp_path):
    matter = tmp_path / "matter"
    _prepared_forms(matter)
    _text_pdf(matter / "output" / "deliverables" / "Cover Letter.pdf")
    forms = "output/deliverables/Forms"
    items = [
        {"kind": "pdf", "path": "output/deliverables/Cover Letter.pdf", "description": "Cover Letter"},
        {"kind": "pdf", "path": f"{forms}/G-1145.pdf"},
        {"kind": "pdf", "path": f"{forms}/G-1450 - I-130 filing fee.pdf"},
        {"kind": "pdf", "path": f"{forms}/I-130.pdf"},
    ]
    plan = _matter_plan(matter, items, filing_method="online")
    assert assemble_packet.main([str(plan), "--manifest", str(matter / "m.json")]) == 0
    manifest = json.loads((matter / "m.json").read_text(encoding="utf-8"))
    assert [it["index"] for it in manifest["items"]] == [1, 2, 3, 4]  # nothing moves online
    assert manifest["filing_order"]["front"] == []
    assert any("item 2" in w and "G-1145 doesn't belong in the packet" in w for w in manifest["warnings"])
    assert any("item 3" in w and "paid in the USCIS online account" in w for w in manifest["warnings"])
    assert not any("isn't in the packet" in w for w in manifest["warnings"])


def test_resampled_photos_are_reported(tmp_path):
    from PIL import Image

    Image.new("RGB", (3000, 2000), (90, 120, 150)).save(tmp_path / "photo.jpg", quality=95)
    _text_pdf(tmp_path / "doc.pdf")
    manifest, _ = _run_plan(tmp_path, [
        {"kind": "image", "path": "photo.jpg", "label": "Exhibit A", "description": "Photo"},
        {"kind": "pdf", "path": "doc.pdf", "label": "Exhibit B", "description": "Doc"}], "--max-mb", "0.0001")
    assert manifest["items"][0]["sources"][0].get("resampled") is True  # drawn again at a lower resolution
    assert manifest["compression"]["resampled_items"][0] == 1


def test_workspace_copy_with_a_moved_matter_folder(tmp_path):
    matter, copy, vault = _matter(tmp_path)
    ws = copy.parents[2]
    (ws / "stage manifest.json").write_text(json.dumps({"files": [
        {"original_path": "/Volumes/Old Drive/Example Matter/client docs/Lease.pdf",  # where the matter used to be
         "relative_path": "client docs/Lease.pdf", "workspace_path": "/Volumes/Old Drive/ws/Lease.pdf"}]}),
        encoding="utf-8")
    plan = vault / "packet plan.json"
    plan.write_text(json.dumps({"base_dir": str(matter), "output": "output/deliverables/Filing Packet.pdf",
                                "items": [{"kind": "pdf", "path": str(copy), "label": "Exhibit A"}]}), encoding="utf-8")
    assert assemble_packet.main([str(plan), "--manifest", str(vault / "m.json")]) == 0
    source = json.loads((vault / "m.json").read_text(encoding="utf-8"))["items"][0]["sources"][0]
    assert source["path"] == "client docs/Lease.pdf" and source["mapped_from_working_copy"] is True


def test_fees_general_exemptions_and_separate_payments():
    vawa = fees.calculate(["I-360", "I-485", "I-765", "I-131"], "paper", ["vawa"])
    assert vawa["total"] == 0 and vawa["lines"][3]["fee"] == 0
    assert "general fee exemptions" in vawa["lines"][3]["category_label"]
    refugee = fees.calculate(["I-485", "I-765", "I-131"], "paper", ["refugee"])
    assert refugee["total"] == 0
    assert fees.calculate(["I-131"], "paper", ["refugee", "I-131=reentry_permit"])["total"] == 0
    assert fees.calculate(["I-131"], "paper", ["refugee", "I-131=tps_travel"])["total"] == 630  # not on the list
    assert fees.calculate(["I-131"], "paper", ["military", "I-131=reentry_permit"])["total"] == 0
    renewal = fees.calculate(["I-765"], "paper", ["c8_renewal"])
    assert [(p["what"], p["amount"]) for p in renewal["lines"][0]["payments"]] == [
        ("filing fee", 520), ("Pub. L. 119-21 fee", 275)]
    assert [(p["what"], p["amount"]) for p in renewal["payment_forms_needed"]] == [
        ("filing fee", 520), ("Pub. L. 119-21 fee", 275)]
    assert "2 separate payments" in renewal["lines"][0]["payment"]
    assert any("separate payment concurrent" in n for n in renewal["notes"])
    parole = fees.calculate(["I-485", "I-131"], "paper", [])
    note = next(n for n in parole["notes"] if "Immigration Parole Fee" in n)
    assert "$1,050" in note and "adjustment of status" in note


def test_legal_statements_are_not_client_facts():
    for s in ("Adjustment is discretionary. USCIS, PM-602-0199 (May 21, 2026), p. 5.",
              "USCIS has taken no paper checks since October 28, 2025.",
              "The petitioner must show both parties intend to marry within 90 days of the beneficiary's admission.",
              "A joint petition is filed during the 90 days before the second anniversary.",
              "The 2025 civics test applies.",
              "The Board so held in 2019.",
              "See Policy Alert PA-2025-19 (Aug. 29, 2025)."):
        assert not letter_check.is_fact_sentence(s), s
    for s in ("They married on June 18, 2022.", "USCIS approved her petition on May 1, 2024.",
              "The couple has lived together since August 2024."):
        assert letter_check.is_fact_sentence(s), s
    letter = render_letter.parse_letter(_letter(
        "Hardship is limited to the two-year period of conditional residence. A joint petition is filed during the "
        "90-day period before the card expires. An applicant must have resided continuously for five years. The "
        "couple has been married for three years. *See* Exhibit A.\n\n```exhibits\n- Lease\n```"))
    assert [p["text"] for p in render_letter.computed_phrases(letter)] == ["for three years"]


PROTECTED_BODY = ("This filing is protected by 8 U.S.C. § 1367. Please direct all correspondence to the safe mailing "
                  "address on the enclosed forms, in care of counsel.")
TO_1367 = "to:\n  - USCIS\n  - \"Attn: 1367\"\n  - P.O. Box 20020\n"
TO_I751 = "to:\n  - USCIS\n  - \"Attn: I-751\"\n  - P.O. Box 21200\n"


def _titles(tmp_path, fx, text, name):
    return [f["title"] for f in _render(tmp_path, text, name, fx["profile"])["findings"]]


def test_filing_location_rule_is_the_form_and_its_basis():
    # Read on the forms' address pages (updated 10/07/2026; the I-751's 09/24/2024), checked 2026-10-29.
    lockbox, own = filing_locations.LOCKBOX, filing_locations.FORM_PAGE
    cases = {("I-360", "vawa"): lockbox, ("I-485", "VAWA"): lockbox, ("I-485", "t"): lockbox, ("I-485", "u"): lockbox,
             ("I-485", "cuban adjustment abused"): lockbox, ("I-485", "hrifa_battered"): lockbox,
             ("I-765", "vawa"): lockbox, ("I-131", "u"): lockbox, ("I-601", "t"): lockbox,
             ("I-751", "abuse_waiver"): own, ("I-751", "other"): own, ("I-360", "other"): own, ("I-485", "other"): own,
             ("I-914", "t"): None, ("N-400", "vawa"): None, ("I-485", "abuse_waiver"): None, ("I-485", ""): None}
    for (form, basis), want in cases.items():
        assert filing_locations.route(form, basis)["location"] == want, (form, basis)
    assert filing_locations.normalize_location("Attn: 1367 lockbox") == lockbox
    assert filing_locations.normalize_location("https://www.uscis.gov/Certain-VAWA-T-U-Filing-Locations") == lockbox
    assert filing_locations.normalize_location("I-751 lockbox (form page)") == own


def test_waiver_filing_routes_and_fees():
    # I-601A page (updated 06/01/2026) and I-601 addresses page (10/07/2026); G-1055 ed. 10/26/26. Checked 2026-10-30.
    lockbox, own = filing_locations.LOCKBOX, filing_locations.FORM_PAGE
    for basis in ("vawa", "other"):
        r = filing_locations.route("I-601A", basis)
        assert (r["location"], r["page"]) == (own, "https://www.uscis.gov/i-601a")
    r = filing_locations.route("I-601", "other")
    assert (r["location"], r["page"]) == (own, "https://www.uscis.gov/i-601-addresses")
    assert "Phoenix" in r["rule"] and "receipt" in r["rule"]
    assert all(filing_locations.route("I-601", b)["location"] == lockbox for b in ("vawa", "t", "u"))
    assert fees.calculate(["I-601A"], "paper", [])["total"] == 795
    assert fees.calculate(["I-601A"], "paper", ["vawa"])["total"] == 0
    assert fees.calculate(["I-601"], "paper", [])["total"] == 1050
    assert fees.calculate(["I-601"], "paper", ["nacara"])["total"] == 0
    # An I-601 filed with an online I-485 goes on paper, as its own part.
    split = fees.calculate(["G-28", "I-130", "I-485", "I-601"], "online", [])
    assert split["split"] and split["channels"]["paper"] == {"forms": ["I-601"], "g28_for": ["I-601"]}


def test_national_interest_waiver_route_fees_and_letter_budget():
    # I-140 addresses page (updated 10/23/2026); G-1055 ed. 10/26/26. Checked 2026-10-30.
    for basis in ("vawa", "other"):
        r = filing_locations.route("I-140", basis)
        assert (r["location"], r["page"]) == (filing_locations.FORM_PAGE, "https://www.uscis.gov/i-140-addresses")
    rule = filing_locations.route("I-140", "other")["rule"]
    assert "Attn: NFB" in rule and "Premium I-140" in rule and "Attn: I-907" in rule
    self_petition = fees.calculate(["G-28", "I-140"], "paper", ["I-140=self_petitioner"])
    assert self_petition["total"] == 1015  # $715 and the $300 Asylum Program Fee
    premium = fees.calculate(["G-28", "I-140", "I-907"], "paper", ["I-140=self_petitioner"])
    assert premium["total"] == 1015 + 2965
    assert [p["form"] for p in premium["payment_forms_needed"]] == ["I-140", "I-907"]  # paid separately
    assert render_letter.LENGTH_BUDGETS["i140_niw"] == 6000


def test_protected_paper_letters_go_where_the_form_and_basis_send_them(fx, tmp_path):
    def letter(to, **front):
        text = _letter(PROTECTED_BODY, protected="true", **front)
        return text.replace("to: USCIS\n", to) if to else text

    vawa = {"lead_form": "I-360", "filing_basis": "vawa"}
    waiver = {"lead_form": "I-751", "filing_basis": "abuse_waiver"}
    assert _titles(tmp_path, fx, letter(TO_1367, filing_location="1367 lockbox", **vawa), "v1") == []
    assert _titles(tmp_path, fx, letter(None, filing_location="1367 lockbox", **vawa), "v2") == [
        "Letter not addressed to the 1367 lockbox"]
    # An I-751 abuse waiver is protected, but goes to the I-751's own lockbox, never the 1367 one.
    assert _titles(tmp_path, fx, letter(TO_I751, filing_location="form page", **waiver), "w1") == []
    assert _titles(tmp_path, fx, letter(TO_1367, filing_location="1367 lockbox", **waiver), "w2") == [
        "Filing location doesn't match the form and its basis"]
    assert _titles(tmp_path, fx, letter(TO_1367, filing_location="form page", **waiver), "w3") == [
        "Letter addressed to the 1367 lockbox"]
    # A protected letter names its location and basis, so the audit can check them.
    assert _titles(tmp_path, fx, letter(TO_1367), "n1") == ["Filing location not named", "Filing basis not named"]
    # A form the tools haven't checked: a note, never a guess.
    unknown = _render(tmp_path, letter(TO_1367, filing_location="1367 lockbox", lead_form="I-914", filing_basis="t"),
                         "u1", fx["profile"])
    assert unknown["findings"] == [] and any("not checked by the tools" in n for n in unknown["notes"])
    assert unknown["filing_location"]["named"] == filing_locations.LOCKBOX


def test_protected_letters_online_and_the_safe_address(fx, tmp_path):
    online = _render(tmp_path, _letter(PROTECTED_BODY, protected="true", filing_method="online"), "po", fx["profile"])
    assert online["findings"] == [] and online["protected"] is True  # online: no lockbox, still 1367
    named = _letter(PROTECTED_BODY, protected="true", filing_method="online", filing_location="1367 lockbox")
    assert _titles(tmp_path, fx, named, "pon") == ["Filing location in an online filing"]
    boxed = _letter(PROTECTED_BODY, protected="true", filing_method="online").replace("to: USCIS\n", TO_1367)
    assert _titles(tmp_path, fx, boxed, "pob") == ["Mailing details in an online filing"]
    silent = _render(tmp_path, _letter("Body.", protected="true", filing_method="online"), "ps", fx["profile"])
    assert [f["title"] for f in silent["findings"]] == [
        "Protected matter without 8 U.S.C. 1367", "Protected matter without the safe mailing address"]
    no_safe = _letter("This filing is protected by 8 U.S.C. § 1367.", protected="true", filing_method="online")
    assert _titles(tmp_path, fx, no_safe, "pns") == ["Protected matter without the safe mailing address"]


def test_translation_ids_differ_for_same_named_files(tmp_path):
    matter = tmp_path / "matter"
    extracts = matter / "output" / "working" / "extracts"
    extracts.mkdir(parents=True)
    entry = {"sha256": "a" * 64, "pages": 1, "chars": 500, "method": "text", "language": "es",
             "non_english_pages": [1], "needs_translation": True}
    (extracts / "index.json").write_text(json.dumps({"version": 1, "files": {
        "petitioner/Birth certificate.pdf": entry, "beneficiary/Birth certificate.pdf": entry}}), encoding="utf-8")
    ids = [n["suggested_item_id"] for n in translations.translation_needs(matter)["needs_translation"]]
    assert len(set(ids)) == 2 and all(i.startswith("doc-translation-birth-certificate-") for i in ids)
    assert ids == [n["suggested_item_id"] for n in translations.translation_needs(matter)["needs_translation"]]  # stable


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not on PATH")
def test_cli_through_uv(fx, tmp_path):
    plan = _plan(tmp_path, [{"kind": "separator", "label": "Exhibit A", "description": "Test"},
                            {"kind": "pdf", "path": str(fx["three"]), "pages": "1"}])
    ok = subprocess.run(["uv", "run", "--script", str(TOOLS / "assemble_packet.py"), str(plan)],
                        capture_output=True, text=True, timeout=600)
    assert ok.returncode == 0, ok.stderr
    assert "2 pages" in ok.stdout
    bad = subprocess.run(["uv", "run", "--script", str(TOOLS / "assemble_packet.py"), str(tmp_path / "nope.json")],
                         capture_output=True, text=True, timeout=600)
    assert bad.returncode == 2 and "ERROR: Plan file not found" in bad.stderr
    help_ = subprocess.run(["uv", "run", "--script", str(TOOLS / "render_letter.py"), "--help"],
                           capture_output=True, text=True, timeout=600)
    assert help_.returncode == 0 and "--profile" in help_.stdout


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", *sys.argv[1:]]))

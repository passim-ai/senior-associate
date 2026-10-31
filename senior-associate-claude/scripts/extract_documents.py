#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf[crypto]>=4", "python-docx>=1.1"]
# ///
"""Extract the text of a matter's client documents once, for every step to read.

    uv run --script extract_documents.py "<matter>" [--json]

For each client document (anything outside output/), writes ``output/working/extracts/<sha256>.txt`` (pages separated
by form feeds) and records it in ``output/working/extracts/index.json``:

    {"version": 1, "files": {"<path relative to the matter>": {"sha256", "pages", "chars", "method": "text|none",
     "language": "en|es|...|cyrillic|unknown", "language_name", "script_only": bool, "non_english_pages": [3, 4],
     "needs_translation": bool,
     "pages_without_text": [1, 2]}}}

A re-run extracts only new or changed files (by sha256) and drops the ones that left the matter. PDFs are read with
pdftotext when it's installed (Poppler), otherwise with pypdf; Word files with python-docx; text files directly.
Images and scans get ``method: "none"`` and their pages count as pages without text: someone has to look at them.

Language is a heuristic per page: stopwords for English, Spanish, Portuguese, French, Haitian Creole and
Vietnamese; the script for Chinese, Japanese and Korean. The Arabic, Cyrillic and Devanagari scripts each write many
languages, so a page in one of them is named by its script only (``arabic-script``, ``cyrillic``, ``devanagari``;
``language_name`` "a language written in Cyrillic script", ``script_only`` true), never as one language. A page
needs translation when its text is mostly in a language other than English. The extracts are client data: they stay
in output/working/, which closeout keeps.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.matter_access import NotAMatterFolder, require_matter_folder
from scripts.matter_state import sha256_file, sign_of_life

logging.getLogger("pypdf").setLevel(logging.ERROR)

EXTRACTS_DIR = Path("output/working/extracts")
INDEX_NAME = "index.json"
INDEX_VERSION = 1
IGNORED_DIRS = {".git", ".venv", "__pycache__", "node_modules"}
TEXT_SUFFIXES = {".txt", ".md", ".csv", ".rtf"}
PDF_SUFFIXES = {".pdf"}
DOCX_SUFFIXES = {".docx"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".heic", ".heif", ".tif", ".tiff", ".gif", ".bmp", ".webp"}
# A page with fewer letters than this is a scan, a photo, or a blank: no language is guessed for it.
MIN_PAGE_LETTERS = 40
# Matched words a language needs before it can be named for a page.
MIN_STOPWORD_HITS = 4

STOPWORDS: dict[str, frozenset[str]] = {
    "en": frozenset(
        "the and of to in is for that this with was on by be are as at from or have has his her their date name "
        "born birth certificate issued united states county state registered marriage".split()
    ),
    "es": frozenset(
        "el la los las de del y en que por para con una un es fue se al su sus como nacimiento acta registro "
        "civil fecha nombre padre madre lugar estado municipio libro hoja certifica".split()
    ),
    "pt": frozenset(
        "o a os as de do da dos das em no na um uma para com não que é foi pelo pela certidão nascimento "
        "registro civil data nome pai mãe cartório filho filha".split()
    ),
    "fr": frozenset(
        "le la les des et est du une pour dans que qui pas sur avec au il elle nous vous sont été née né acte "
        "naissance état civil date nom père mère mairie".split()
    ),
    "ht": frozenset(
        "ak nan pou li yo mwen ou se pa sa te gen kote tout lè konsa paske men ki fèt manman papa non dat "
        "batistè leta sivil".split()
    ),
    "vi": frozenset(
        "và của là có không được người này cho với các những ngày tháng năm sinh tên cha mẹ nơi giấy khai "
        "đăng ký".split()
    ),
}
LANGUAGE_NAMES = {
    "en": "English",
    "es": "Spanish",
    "pt": "Portuguese",
    "fr": "French",
    "ht": "Haitian Creole",
    "vi": "Vietnamese",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    # A script many languages share: only the script is known.
    "arabic-script": "a language written in Arabic script",
    "cyrillic": "a language written in Cyrillic script",
    "devanagari": "a language written in Devanagari script",
    "unknown": "unknown",
}
SCRIPT_ONLY = frozenset({"arabic-script", "cyrillic", "devanagari"})
# What an earlier extractor wrote for those scripts, as if each were one language.
LEGACY_SCRIPT_CODES = {"ar": "arabic-script", "ru": "cyrillic", "hi": "devanagari"}
SCRIPTS = (
    ("ko", re.compile(r"[가-힯ᄀ-ᇿ]")),
    ("ja", re.compile(r"[぀-ヿ]")),
    ("zh", re.compile(r"[一-鿿]")),
    ("arabic-script", re.compile(r"[؀-ۿݐ-ݿ]")),
    ("cyrillic", re.compile(r"[Ѐ-ӿ]")),
    ("devanagari", re.compile(r"[ऀ-ॿ]")),
)


def language_fields(language: str) -> dict[str, Any]:
    """The index's words for a document's language: its code, its name, and whether only the script is known."""
    language = LEGACY_SCRIPT_CODES.get(language, language)
    return {"language": language, "language_name": LANGUAGE_NAMES.get(language, language),
            "script_only": language in SCRIPT_ONLY}
WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def page_language(text: str) -> str:
    """The language of one page's text, or "unknown" when there's too little text to tell."""
    letters = sum(1 for ch in text if ch.isalpha())
    if letters < MIN_PAGE_LETTERS:
        return "unknown"
    # A script other than Latin settles it when it carries a good share of the letters.
    for code, pattern in SCRIPTS:
        if len(pattern.findall(text)) >= max(10, letters * 0.2):
            return code
    words = [word.casefold() for word in WORD.findall(text)]
    hits = Counter()
    for word in words:
        for code, stopwords in STOPWORDS.items():
            if word in stopwords:
                hits[code] += 1
    if not hits:
        return "unknown"
    # Vietnamese marks most syllables; its tone letters settle a close call with French or Portuguese.
    if re.search(r"[ơưđăạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]", text, re.IGNORECASE):
        hits["vi"] += 3
    language, count = hits.most_common(1)[0]
    if count < MIN_STOPWORD_HITS:
        return "unknown"
    # A bilingual page (a passport, a certificate printed in two languages) that is at least half English reads
    # as English: it doesn't need a translation.
    if language != "en" and hits["en"] * 2 >= count:
        return "en"
    return language


def document_language(page_languages: list[str], page_chars: list[int]) -> str:
    weights: Counter[str] = Counter()
    for language, chars in zip(page_languages, page_chars):
        if language != "unknown":
            weights[language] += chars
    return weights.most_common(1)[0][0] if weights else "unknown"


def pdf_pages_pdftotext(path: Path) -> list[str] | None:
    tool = shutil.which("pdftotext") or next(
        (candidate for candidate in ("/opt/homebrew/bin/pdftotext", "/usr/local/bin/pdftotext") if os.access(candidate, os.X_OK)),
        None,
    )
    if not tool:
        return None
    try:
        result = subprocess.run([tool, "-layout", "-enc", "UTF-8", str(path), "-"], capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.decode("utf-8", errors="replace")
    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    return pages


def pdf_pages_pypdf(path: Path) -> list[str] | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(str(path))
        return [(page.extract_text() or "") for page in reader.pages]
    except Exception:
        return None


def docx_text(path: Path) -> list[str] | None:
    try:
        from docx import Document
    except ImportError:
        return None
    try:
        document = Document(str(path))
    except Exception:
        return None
    return ["\n".join(paragraph.text for paragraph in document.paragraphs)]


def extract_pages(path: Path) -> tuple[list[str], str]:
    """(pages, method). method is "text" when any text came out, "none" otherwise."""
    suffix = path.suffix.casefold()
    pages: list[str] | None = None
    if suffix in PDF_SUFFIXES:
        pages = pdf_pages_pdftotext(path)
        if pages is None:
            pages = pdf_pages_pypdf(path)
    elif suffix in DOCX_SUFFIXES:
        pages = docx_text(path)
    elif suffix in TEXT_SUFFIXES:
        try:
            pages = [path.read_text(encoding="utf-8", errors="replace")]
        except OSError:
            pages = None
    elif suffix in IMAGE_SUFFIXES:
        pages = [""]
    if not pages:
        return [""], "none"
    method = "text" if any(page.strip() for page in pages) else "none"
    return pages, method


def client_documents(matter: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(matter):
        relative_dir = Path(dirpath).relative_to(matter)
        dirnames[:] = sorted(
            name for name in dirnames
            if not name.startswith(".") and name not in IGNORED_DIRS and not (relative_dir == Path(".") and name == "output")
        )
        for name in sorted(filenames):
            if name.startswith((".", "~$")):
                continue
            found.append(Path(dirpath) / name)
    return found


def read_index(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": INDEX_VERSION, "files": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), dict):
        return {"version": INDEX_VERSION, "files": {}}
    return payload


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(tmp, path)


def extract_matter(matter: Path) -> dict[str, Any]:
    """Bring the extracts up to date. Returns the index plus counts of what this run did."""
    matter = matter.resolve()
    folder = matter / EXTRACTS_DIR
    index_path = folder / INDEX_NAME
    index = read_index(index_path)
    previous: dict[str, Any] = index["files"]
    files: dict[str, Any] = {}
    extracted = reused = 0
    for path in client_documents(matter):
        relative = path.relative_to(matter).as_posix()
        try:
            digest = sha256_file(path)
        except OSError:
            continue
        entry = previous.get(relative)
        if isinstance(entry, dict) and entry.get("sha256") == digest and (folder / f"{digest}.txt").is_file():
            # An earlier run's words for a script-only language are brought up to date without reading it again.
            files[relative] = {**entry, **language_fields(str(entry.get("language") or "unknown"))}
            reused += 1
            continue
        pages, method = extract_pages(path)
        page_chars = [len(page.strip()) for page in pages]
        languages = [page_language(page) for page in pages]
        language = document_language(languages, page_chars)
        non_english = [number for number, code in enumerate(languages, start=1) if code not in {"en", "unknown"}]
        write_atomic(folder / f"{digest}.txt", "\f".join(pages))
        files[relative] = {
            "sha256": digest,
            "pages": len(pages),
            "chars": sum(page_chars),
            "method": method,
            **language_fields(language),
            "non_english_pages": non_english,
            "needs_translation": bool(non_english),
            "pages_without_text": [number for number, chars in enumerate(page_chars, start=1) if chars < MIN_PAGE_LETTERS],
        }
        extracted += 1
    # Extracts of documents that left the matter (removed, replaced) go too.
    keep = {entry["sha256"] for entry in files.values()}
    removed = 0
    if folder.is_dir():
        for stale in folder.glob("*.txt"):
            if stale.stem not in keep:
                stale.unlink()
                removed += 1
    index = {"version": INDEX_VERSION, "files": files}
    write_atomic(index_path, json.dumps(index, indent=2, ensure_ascii=False) + "\n")
    return {**index, "extracted": extracted, "reused": reused, "removed": removed}


def summary_lines(result: dict[str, Any], matter: Path) -> list[str]:
    files = result["files"]
    translate = [path for path, entry in files.items() if entry.get("needs_translation")]
    no_text = [path for path, entry in files.items() if entry.get("method") == "none"]
    lines = [
        f"Extracts: {len(files)} document(s) ({result['extracted']} extracted now, {result['reused']} unchanged) in "
        f"{matter / EXTRACTS_DIR}. Read index.json, then <sha256>.txt, before opening the PDFs.",
        f"Need a translation: {len(translate)}" + (f" ({'; '.join(translate[:10])}{'; ...' if len(translate) > 10 else ''})" if translate else "") + ".",
        f"No text (scans or photos; look at them): {len(no_text)}" + (f" ({'; '.join(no_text[:10])}{'; ...' if len(no_text) > 10 else ''})" if no_text else "") + ".",
    ]
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract the text of a matter's client documents, once, for every step.")
    parser.add_argument("matter", type=Path)
    parser.add_argument("--json", action="store_true", help="Print the whole index.")
    args = parser.parse_args()
    try:
        matter = require_matter_folder(args.matter)
    except NotAMatterFolder as exc:
        print(str(exc), file=sys.stderr)
        return 1
    sign_of_life(matter)  # extracting is a sign the run is alive
    result = extract_matter(matter)
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else "\n".join(summary_lines(result, matter)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

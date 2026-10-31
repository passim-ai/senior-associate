#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""List the client documents (or pages) that need a certified English translation.

    uv run --script translations.py "<matter>" [--json]

Reads output/working/extracts/index.json, which scripts/extract_documents.py writes (one
entry per client document: its language and the pages that aren't in English). Prints
each document that needs a translation, with the pages, and each document whose text
couldn't be read (an image or a scan), which someone has to look at. It reads only that
index; run extract_documents.py first.

8 C.F.R. 103.2(b)(3): every foreign-language document needs a full English translation,
certified by the translator as complete and accurate, with the translator's
certification of competence. A summary or a translation of only some pages is partial.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _packet_common import ToolError, page_ranges, run_cli  # noqa: E402

INDEX = Path("output") / "working" / "extracts" / "index.json"
LANGUAGES = {
    "en": "English", "es": "Spanish", "pt": "Portuguese", "fr": "French", "ht": "Haitian Creole",
    "vi": "Vietnamese", "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "unknown": "an unidentified language",
}
# A script many languages share is all the extracts can tell: the document is named by its script, never as one
# language, in the open item and the certificate. "ar", "ru" and "hi" are what an earlier extractor wrote for them.
SCRIPT_ONLY = {
    "arabic-script": "a language written in Arabic script", "ar": "a language written in Arabic script",
    "cyrillic": "a language written in Cyrillic script", "ru": "a language written in Cyrillic script",
    "devanagari": "a language written in Devanagari script", "hi": "a language written in Devanagari script",
}


def language_words(entry: dict) -> tuple[str, bool]:
    """(how to name the document's language, whether only its script is known). The extracts' own name is used when
    it has one; a script is never named as one language."""
    lang = str(entry.get("language") or "unknown")
    if entry.get("script_only") or lang in SCRIPT_ONLY:
        return SCRIPT_ONLY.get(lang) or str(entry.get("language_name") or "a language the translator will name"), True
    named = entry.get("language_name")
    if isinstance(named, str) and named.strip() and named != "unknown":
        return named.strip(), False
    return LANGUAGES.get(lang, lang), False


def _item_id(path: str) -> str:
    """A stable open-item id for one document: its name, plus a short hash of its path in the matter,
    so two files with the same name in different folders get different items."""
    stem = re.sub(r"[^a-z0-9]+", "-", Path(path).stem.lower()).strip("-")[:32] or "document"
    digest = hashlib.sha256(Path(path).as_posix().encode("utf-8")).hexdigest()[:6]
    return f"doc-translation-{stem}-{digest}"


def translation_needs(matter: Path) -> dict:
    index_path = matter / INDEX
    if not index_path.is_file():
        raise ToolError(
            f"No document extracts for this matter yet ({INDEX}). Run scripts/extract_documents.py on the matter first."
        )
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolError(f"{index_path} can't be read ({exc}). Run scripts/extract_documents.py again.") from None
    files = index.get("files") if isinstance(index, dict) else None
    if not isinstance(files, dict):
        raise ToolError(f"{index_path} has no \"files\" map. Run scripts/extract_documents.py again.")
    needs, unreadable = [], []
    for rel, entry in sorted(files.items()):
        if not isinstance(entry, dict):
            continue
        method = entry.get("method")
        total = entry.get("pages")
        if method == "none":
            unreadable.append({"path": rel, "pages": total,
                               "reason": "no text layer (an image or a scan): look at it to see its language"})
            continue
        if not entry.get("needs_translation"):
            continue
        lang = str(entry.get("language") or "unknown")
        foreign = [p for p in entry.get("non_english_pages") or [] if isinstance(p, int)]
        whole = not foreign or (isinstance(total, int) and len(set(foreign)) >= total)
        named, script_only = language_words(entry)
        needs.append({
            "path": rel,
            "language": lang,
            "language_name": named,
            "script_only": script_only,
            "page_count": total,
            "pages": "all" if whole else page_ranges(sorted(set(foreign)), ", "),
            "suggested_item_id": _item_id(rel),
        })
    return {"index": str(index_path), "needs_translation": needs, "unreadable": unreadable}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="List the client documents that need a certified English translation.")
    ap.add_argument("matter", type=Path, help="Matter folder")
    ap.add_argument("--json", action="store_true", help="Print the result as JSON")
    args = ap.parse_args(argv)
    matter = args.matter.expanduser().resolve()
    if not matter.is_dir():
        raise ToolError(f"Matter folder not found: {matter}")
    result = translation_needs(matter)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    needs, unreadable = result["needs_translation"], result["unreadable"]
    print(f"Needs a certified translation: {len(needs)}")
    for n in needs:
        where = "every page" if n["pages"] == "all" else f"pages {n['pages']}"
        print(f"  - {n['path']}: {n['language_name']}, {where}")
    if unreadable:
        print(f"No text to check (look at these): {len(unreadable)}")
        for u in unreadable:
            print(f"  - {u['path']}")
    return 0


if __name__ == "__main__":
    run_cli(main)

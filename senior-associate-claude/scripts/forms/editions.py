#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Which edition of a USCIS form a blank is, and whether the bundled tools were built for it.

Each question schema was built against one official blank, whose field list (schemas/fields/)
records that file's sha256 and where each of its boxes sits. A blank with the same sha256 is that
file. Another file is checked by the edition printed in its footer ("Form I-485 Edition
09/18/26"): the same edition re-posted with the same boxes is fine; a different edition, or the
same edition with different boxes, is one the tools were not built for, and `build` won't fill it
(see build_forms.py). Each case is worded for what it is: a newer edition is the attorney's
decision; an older blank than the tools know just needs the current blank downloaded (build
--refresh-blank) and the plan migrated.

When the attorney decides to prepare a form on a new edition anyway, compare_boxes tells which
of the plan's boxes are the same on it (same name, kind of box, choices, length limit, page and
position) and which changed; build fills only the same ones.

    editions.py MATTER [--live] [--json]

checks every blank in MATTER/output/working/forms/blank/ against the edition its schema was
built for and, with --live, against the Edition Date panel of the form's uscis.gov page today.
Exit 0 when every blank is current, 1 when any is not (or a page could not be read, or its
edition date could not be found), 2 on bad input.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import logging
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.getLogger("pypdf").setLevel(logging.ERROR)

FOOTER_RE = re.compile(r"Form\s+(?P<form>[A-Z]{1,2}-\d+[A-Z]*)\s+(?:Edition\s+)?(?P<edition>\d{2}/\d{2}/\d{2})\b")

# Check results. Only MATCH and SAME_EDITION are fillable without the attorney deciding.
MATCH = "match"  # the very file the schema was built against
SAME_EDITION = "same_edition"  # another file of the same edition, with the same boxes
NEW_EDITION = "new_edition"  # a different edition
CHANGED_BOXES = "changed_boxes"  # the same edition printed, but the boxes differ
UNREADABLE = "unreadable"  # no edition in the footer, and not the schema's file
NO_SCHEMA = "no_schema"  # no schema with a field list for this form: nothing to compare
FILLABLE = {MATCH, SAME_EDITION, NO_SCHEMA}


def first_page_text(pdf_path: Path) -> str:
    """Text of the first page: pdftotext when installed, else pypdf (enough for the footer)."""
    if shutil.which("pdftotext"):
        result = subprocess.run(
            ["pdftotext", "-f", "1", "-l", "1", str(pdf_path), "-"],
            check=False, capture_output=True, text=True, errors="replace",
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(pdf_path))
        if not reader.pages:
            return ""
        return reader.pages[0].extract_text() or ""
    except Exception:  # noqa: BLE001 - an unreadable file simply has no footer to read
        return ""


def footer_edition(pdf_path: Path) -> tuple[str, str] | None:
    """(form, edition) printed in the blank's footer, such as ("I-485", "09/18/26"), or None."""
    match = FOOTER_RE.search(" ".join(first_page_text(pdf_path).split()))
    return (match.group("form"), match.group("edition")) if match else None


def schema_blank(kind: str, schema_name: str | None = None) -> dict[str, Any] | None:
    """The edition, field list and blank sha256 a schema was built against: the named schema, or
    else the first of this form's schemas that names a field list (they all share one)."""
    from form_question_schema import QUESTION_SCHEMAS, load_field_list

    if schema_name:
        candidates = [QUESTION_SCHEMAS[schema_name]] if schema_name in QUESTION_SCHEMAS else []
    else:
        candidates = list(QUESTION_SCHEMAS.values())
    for schema in candidates:
        if schema.get("kind") != kind or not schema.get("field_list"):
            continue
        field_list = load_field_list(schema["field_list"])
        return {
            "edition": str(schema.get("edition") or ""),
            "field_list": schema["field_list"],
            "sha256": field_list.get("pdf_sha256", ""),
            "fields": field_list.get("fields", {}),
            "widgets": field_list.get("widgets", {}),
        }
    return None


def blank_layout(blank: Path) -> dict[str, Any]:
    """The blank's boxes as the stored field lists record them: {"fields": ..., "widgets": ...}."""
    import tempfile

    from form_question_schema import save_field_list

    with tempfile.TemporaryDirectory() as tmp:
        return save_field_list(blank, Path(tmp) / "fields.json")


POSITION_TOLERANCE = 1.5  # points: a re-saved file rounds a little; a moved box moves more


def _rects(entries: list[str]) -> list[tuple[int, list[float]]]:
    rects = []
    for entry in entries:
        page, *box = str(entry).split()
        rects.append((int(page), [float(value) for value in box]))
    return rects


def box_change(base: str, built: dict[str, Any], new: dict[str, Any]) -> str:
    """Why a box differs between the blank the tools were built for and a new one ("" when it is the
    same box): gone, another kind of box, other choices, another length limit, another page or
    place. Positions are compared only when both sides record them; with none recorded for the
    tools' blank, every box counts as changed."""
    old_field, new_field = built["fields"].get(base), new["fields"].get(base)
    if old_field is None:
        return "not on the blank the tools were built for"
    if new_field is None:
        return "not on the new blank"
    if old_field.get("type") != new_field.get("type"):
        return "another kind of box"
    if sorted(old_field.get("states") or []) != sorted(new_field.get("states") or []):
        return "other choices"
    if old_field.get("maxlen") != new_field.get("maxlen"):
        return "another length limit"
    old_rects, new_rects = _rects(built.get("widgets", {}).get(base, [])), _rects(new.get("widgets", {}).get(base, []))
    if not old_rects:
        return "its place on the form is not recorded"
    if len(old_rects) != len(new_rects):
        return "another number of boxes"
    for (old_page, old_box), (new_page, new_box) in zip(old_rects, new_rects):
        if old_page != new_page:
            return f"moved from page {old_page} to page {new_page}"
        if any(abs(a - b) > POSITION_TOLERANCE for a, b in zip(old_box, new_box)):
            return f"moved on page {new_page}"
    return ""


def compare_boxes(kind: str, blank: Path, boxes: list[str], schema_name: str | None = None) -> dict[str, str]:
    """{box: why it changed} for each of these boxes (a plan's answered boxes) that is not the same
    box on this blank as on the blank the tools were built for. Every box counts as changed when
    the tools have no field list for the form."""
    from forms_workflow import field_base

    built = schema_blank(kind.strip().lower(), schema_name)
    if built is None:
        return {box: "the form tools have no field list for this form" for box in boxes}
    new = blank_layout(blank)
    changed: dict[str, str] = {}
    for box in boxes:
        why = box_change(field_base(box), built, new)
        if why:
            changed[box] = why
    return changed


def check_blank(kind: str, blank: Path, schema_name: str | None = None) -> dict[str, Any]:
    """How a matter's blank compares with the edition the tools (the plan's schema, when it
    names one) were built for."""
    kind = kind.strip().lower()
    with blank.open("rb") as handle:
        sha256 = hashlib.file_digest(handle, "sha256").hexdigest()
    result: dict[str, Any] = {"kind": kind, "blank": str(blank), "sha256": sha256}
    built = schema_blank(kind, schema_name)
    if built is not None and result["sha256"] == built["sha256"]:
        # The very file the schema was built against: its edition is the schema's.
        return {**result, "file_edition": built["edition"], "schema_edition": built["edition"], "status": MATCH}
    footer = footer_edition(blank)
    result["file_edition"] = footer[1] if footer else ""
    if built is None:
        result["status"] = NO_SCHEMA
        return result
    result["schema_edition"] = built["edition"]
    if not footer:
        result["status"] = UNREADABLE
    elif footer[1] != built["edition"]:
        result["status"] = NEW_EDITION
    else:
        new = blank_layout(blank)
        same = new["fields"] == built["fields"] and not any(
            box_change(base, built, new) for base in built["fields"] if built.get("widgets")
        )
        result["status"] = SAME_EDITION if same else CHANGED_BOXES
    return result


def form_label(kind: str) -> str:
    return kind.upper()


def edition_date(text: str) -> date | None:
    """An edition printed mm/dd/yy (or mm/dd/yyyy) as a date, or None."""
    parts = str(text or "").strip().split("/")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    month, day, year = (int(part) for part in parts)
    try:
        return date(year + 2000 if year < 100 else year, month, day)
    except ValueError:
        return None


def is_older(check: dict[str, Any]) -> bool:
    """True when the matter's blank is an older edition than the one the tools were built for."""
    found, built = edition_date(check.get("file_edition", "")), edition_date(check.get("schema_edition", ""))
    return bool(check.get("status") == NEW_EDITION and found and built and found < built)


def problem_text(check: dict[str, Any]) -> str:
    """One plain sentence on why a blank can't be filled as it is (empty when it can)."""
    form, built = form_label(check["kind"]), check.get("schema_edition", "")
    if check["status"] == NEW_EDITION and is_older(check):
        return (
            f"The {form} blank in this matter is the {check['file_edition']} edition, older than the {built} "
            "edition the form tools were built for."
        )
    if check["status"] == NEW_EDITION:
        return (
            f"The {form} blank is the {check['file_edition']} edition, newer than the {built} edition the form "
            "tools were built for."
        )
    if check["status"] == CHANGED_BOXES:
        return (
            f"The {form} blank says it is the {built} edition, but its boxes differ from the {built} blank "
            "the form tools were built for."
        )
    if check["status"] == UNREADABLE:
        return f"The {form} blank's edition can't be read from its footer, and it isn't the {built} blank the form tools know."
    return ""


# What `build --allow-new-edition` does, in the attorney's words: the open item must promise no more.
ALLOW_TEXT = (
    "If you choose to prepare it on this blank, the form tools fill only the boxes that are the same on it, "
    "leave the changed ones blank to be completed by hand, and the form can't pass its check until every box "
    "has been checked against the current instructions."
)


def fix_text(check: dict[str, Any]) -> str:
    """What to do about a blank the tools can't fill as it is, for the build summary."""
    form = form_label(check["kind"])
    refresh = f"download the current blank with --refresh-blank {form}"
    if is_older(check):
        return (
            f"{refresh} (it moves this one aside), then, if the plan was written for the {check['file_edition']} edition, "
            "migrate it with --across-editions and check each answer; then build again. No attorney decision is needed."
        )
    if check["status"] in (CHANGED_BOXES, UNREADABLE):
        return f"{refresh} first; if the current blank still doesn't match, add the attorney_decision open item"
    return "add the attorney_decision open item"


def suggested_open_item(check: dict[str, Any]) -> dict[str, Any] | None:
    """The attorney decision a blank the tools weren't built for calls for, in the open-items format,
    or None when it calls for none (an older blank: download the current one and migrate)."""
    if is_older(check):
        return None
    form = form_label(check["kind"])
    built = check.get("schema_edition", "")
    page = f"uscis.gov/{check['kind']}"
    if check["status"] == NEW_EDITION:
        edition = check.get("file_edition") or "new"
        title = f"USCIS published a new edition of the {form}"
        question = (
            f"Prepare the {form} on the {edition} edition now (only unchanged boxes filled, every box checked by hand) "
            "or wait for updated tools?"
        )
        recommendation = f"Wait, if {page} still accepts the {built} edition; otherwise prepare it on the new one."
    else:
        title = f"The {form} blank doesn't match the form tools"
        question = (
            f"Prepare the {form} on this blank (only matching boxes filled, every box checked by hand) or wait for "
            "updated tools?"
        )
        recommendation = f"Check {page} first: if it offers the {built} edition, use that blank instead."
    return {
        "id": f"forms-edition-{check['kind']}",
        "type": "attorney_decision",
        "title": title[:79],
        "question": question,
        "recommendation": recommendation,
        "detail": (
            f"{problem_text(check)} So the {form} was not filled. {ALLOW_TEXT} The {form} page on uscis.gov says "
            "which editions USCIS accepts and until when."
        ),
        "needed_for": form,
        "blocks_filing": True,
        "status": "open",
        "stage": "forms_preparer",
    }


def live_edition(kind: str) -> dict[str, str]:
    """The Edition Date panel of the form's uscis.gov page today: {page_url, edition_date, edition_note}."""
    import download_uscis_forms as downloader

    spec = downloader.spec_for(kind)
    page_url, page_html, _parent = downloader.fetch_form_page(spec)
    edition_date, edition_note = downloader.extract_edition(page_html)
    return {"page_url": page_url, "edition_date": edition_date, "edition_note": edition_note}


def matter_blanks(matter: Path) -> list[tuple[str, Path]]:
    """(kind, blank) for every blank form in a matter (instructions are not forms)."""
    blank_dir = matter / "output" / "working" / "forms" / "blank"
    if not blank_dir.is_dir():
        return []
    return [
        (path.stem.lower(), path)
        for path in sorted(blank_dir.glob("*.pdf"))
        if not path.stem.lower().endswith("instructions")
    ]


def check_matter(matter: Path, *, live: bool = False) -> list[dict[str, Any]]:
    checks = []
    for kind, blank in matter_blanks(matter):
        check = check_blank(kind, blank)
        if live:
            try:
                check["live"] = live_edition(kind)
            except Exception as exc:  # noqa: BLE001 - report it with the form, keep going
                check["live"] = {"error": str(exc)}
            if not check["live"].get("error") and not str(check["live"].get("edition_date") or "").strip():
                # A page that loads but whose Edition Date panel can't be read tells nothing: the form
                # may well have a newer edition. That is a failed check, never a pass.
                page = check["live"].get("page_url") or "the form's uscis.gov page"
                check["live"]["error"] = f"{page} was read, but its edition date could not be found"
        checks.append(check)
    return checks


def check_lines(checks: list[dict[str, Any]]) -> list[str]:
    lines = []
    for check in checks:
        form = form_label(check["kind"])
        edition = check.get("file_edition") or "edition not printed"
        if check["status"] in (MATCH, SAME_EDITION):
            text = f"{form}: {edition}, the edition the form tools were built for"
        elif check["status"] == NO_SCHEMA:
            text = f"{form}: {edition} (no form tools for this form; prepared by hand)"
        elif is_older(check):
            text = f"{form}: OLDER BLANK: {problem_text(check)} Download the current blank (build --refresh-blank {form})"
        else:
            text = f"{form}: NOT CURRENT FOR THE TOOLS: {problem_text(check)}"
        live = check.get("live")
        if live:
            if live.get("error"):
                text += f"; uscis.gov could not be checked ({live['error'][:120]})"
            elif live.get("edition_date") and live["edition_date"] != check.get("file_edition"):
                text += f"; uscis.gov now lists {live['edition_date']}: {live.get('edition_note', '')[:200]}"
            elif live.get("edition_date"):
                text += f"; uscis.gov lists the same edition ({live['page_url']})"
        lines.append(text)
    return lines


def needs_attention(checks: list[dict[str, Any]]) -> bool:
    for check in checks:
        if check["status"] not in FILLABLE:
            return True
        live = check.get("live") or {}
        if live.get("error") or (live.get("edition_date") and live["edition_date"] != check.get("file_edition")):
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("matter", type=Path)
    parser.add_argument("--live", action="store_true", help="Also compare with each form's uscis.gov page today.")
    parser.add_argument("--json", action="store_true", help="Print the checks as JSON.")
    args = parser.parse_args(argv)
    matter = args.matter.expanduser().resolve()
    if not matter.is_dir():
        print(f"error: matter folder not found: {matter}", file=sys.stderr)
        return 2
    checks = check_matter(matter, live=args.live)
    if not checks:
        print(f"error: no blank forms in {matter / 'output/working/forms/blank'}", file=sys.stderr)
        return 2
    print(json.dumps(checks, indent=2) if args.json else "\n".join(check_lines(checks)))
    return 1 if needs_attention(checks) else 0


if __name__ == "__main__":
    sys.exit(main())

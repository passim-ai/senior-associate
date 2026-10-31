#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Question-plan helpers for USCIS form preparation, and the forms CLI.

    build MATTER [--slug SLUG] [--new NAME=SCHEMA ...] [--blank FORM ...]
          [--force] [--check-only [--audit-out PATH]] [--allow-new-edition FORM=ID] [--full]
    editions MATTER [--live] [--json]

`build` is the whole forms pipeline in one command: from the question plans in
<matter>/output/working/vault/forms/<slug>/plans/ it downloads missing blanks, writes
the mappings and the intent manifest, fills with verify, renders the filing copies,
audits every form and prints a short summary (see build_forms.py).

`editions` checks every blank in the matter against the edition the tools were built for and,
with --live, against the form's uscis.gov page today (see editions.py).
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import inspect
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

from pypdf import PdfReader


FIELD_INDEX_RE = re.compile(r"^(?P<base>.+?)\[(?P<index>\d+)\]$")
NON_ALNUM_RE = re.compile(r"[^0-9a-z]+")


STATUS_FILLED = "filled"
# Some boxes answered from the record, one or more required boxes still unknown: the known
# answers go on the form, the blank required boxes wait on the question's open item.
STATUS_PARTIALLY_FILLED = "partially_filled"
STATUS_NOT_APPLICABLE = "not_applicable"
STATUS_PENDING_CLIENT = "pending_client_input"
STATUS_PENDING_SIGNATURE = "pending_signature"
STATUS_MISSING = "missing"
STATUS_MANUAL_REVIEW = "manual_review"

ALL_STATUSES = {
    STATUS_FILLED,
    STATUS_PARTIALLY_FILLED,
    STATUS_NOT_APPLICABLE,
    STATUS_PENDING_CLIENT,
    STATUS_PENDING_SIGNATURE,
    STATUS_MISSING,
    STATUS_MANUAL_REVIEW,
}

RESOLVED_STATUSES = {
    STATUS_FILLED,
    STATUS_NOT_APPLICABLE,
}

# Statuses whose field_values are written to the form.
WRITTEN_STATUSES = {
    STATUS_FILLED,
    STATUS_PARTIALLY_FILLED,
}


# Checkbox groups that USCIS linked by mistake: one data value drives boxes that
# answer different questions, so only one of them can ever be checked. Matched by
# the group's name and its on-states, so a corrected edition stops matching.
KNOWN_LINKED_CHECKBOX_GROUPS: list[dict[str, Any]] = [
    {
        "form": "I-864 (08/24/26 edition)",
        "base": "P6_Line1_Checkbox",
        "states": {
            "Y": "Part 6 item 1 'Employed'",
            "A": "Part 8 item 1.a (sponsor reads English)",
            "B": "Part 8 item 1.b (interpreter read it to the sponsor)",
        },
        "problem": (
            "P6_Line1_Checkbox is one checkbox group shared by Part 6 item 1 'Employed' and "
            "Part 8 items 1.a and 1.b, so only one of the three can be checked."
        ),
        "action": (
            "Check 'Employed' if it applies and leave Part 8 item 1.a/1.b unmarked in the PDF. "
            "The sponsor marks 1.a or 1.b by hand at signing. Add an attorney_action open item "
            "for that hand-marking."
        ),
        "brief": (
            "Part 6 item 1 and Part 8 items 1.a/1.b share one checkbox: check 'Employed' if it applies, "
            "leave 1.a/1.b unmarked, add an attorney_action open item for the sponsor to mark them by hand."
        ),
    },
]


def linked_checkbox_defects(states_by_base: dict[str, set[str]]) -> list[dict[str, Any]]:
    """Known linked-checkbox defects present on a form, given each base's on-states."""
    found = []
    for defect in KNOWN_LINKED_CHECKBOX_GROUPS:
        states = {state.strip() for state in states_by_base.get(defect["base"], set())}
        if states and set(defect["states"]) <= states:
            found.append(defect)
    return found


def file_sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def default_field_dump_path(pdf_path: Path) -> Path | None:
    """Where the field dump of a matter's blank form lives.

    A blank at <matter>/output/working/forms/blank/I-485.pdf has its dump at
    <matter>/output/working/forms/fields/I-485.json. Other locations have no default.
    """
    pdf_path = pdf_path.expanduser().resolve()
    if pdf_path.parent.name == "blank" and pdf_path.parent.parent.name == "forms":
        return pdf_path.parent.parent / "fields" / f"{pdf_path.stem}.json"
    return None


def load_field_dump(blank_pdf: Path | None) -> tuple[Path | None, dict[str, Any] | None]:
    """Read the field dump of a matter's blank form (default_field_dump_path).

    The dump is written from the blank when it is missing, and rewritten when it was
    made from a different file (a newer edition downloaded since), so the mapping is
    never checked against a stale field list.
    """
    path = default_field_dump_path(blank_pdf) if blank_pdf else None
    if path is None:
        return None, None
    dump = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if blank_pdf.exists() and (dump is None or dump.get("pdf_sha256") != file_sha256(blank_pdf)):
        import xfa_tools  # local import: xfa_tools imports this module

        xfa_tools.save_field_dump(blank_pdf, path)
        dump = json.loads(path.read_text(encoding="utf-8"))
    return path, dump


def mapping_field_check(mapping: dict[str, str], dump: dict[str, Any]) -> dict[str, list[str]]:
    """Mapping keys the form does not have, checkbox values that are not on-states, and
    drop-down values that are not among the drop-down's choices."""
    widgets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in dump.get("fields", []):
        widgets[str(item.get("base") or field_base(str(item.get("name") or "")))].append(item)
    xfa_nodes = set(dump.get("xfa_nodes", []))

    unknown: list[str] = []
    out_of_range: list[str] = []
    bad_states: list[str] = []
    bad_options: list[str] = []
    for name, value in mapping.items():
        # A mapping key is a leaf name; some contain a literal dot (Pt8Line42.a_YesNo), so
        # it is not split into a field hierarchy.
        base, index = field_base_and_index(name)
        specs = widgets.get(base, [])
        if not specs:
            if base not in xfa_nodes:
                unknown.append(name)
            continue
        is_global = any(spec.get("global") for spec in specs)
        if has_explicit_index(name) and index >= len(specs) and not is_global:
            out_of_range.append(f"{name} (the form has {len(specs)})")
        if all(spec.get("type") == "Btn" for spec in specs):
            states = {str(state).strip() for spec in specs for state in spec.get("states", [])}
            if str(value).strip() not in states:
                bad_states.append(f"{name} = {value!r} (on-states: {sorted(states)})")
        elif all(spec.get("type") == "Ch" for spec in specs):
            # A drop-down shows only its own choices: anything else is stored but shown blank or
            # refused by Adobe (a state drop-down takes "IL", not "Illinois").
            options = {str(option).strip() for spec in specs for option in spec.get("options", [])} - {""}
            if options and str(value).strip() not in options:
                shown = sorted(options)
                listed = ", ".join(shown[:12]) + (f", +{len(shown) - 12} more" if len(shown) > 12 else "")
                bad_options.append(f"{name} = {value!r} (choices: {listed})")
    return {
        "unknown_fields": unknown,
        "index_out_of_range": out_of_range,
        "not_an_on_state": bad_states,
        "not_a_choice": bad_options,
    }


def leaf_field_name(full_name: str) -> str:
    """Last part of a fully qualified PDF field name, escape-aware.

    `form1[0].#subform[6].P9_Line7\\.b\\.[0]` is the field `P9_Line7.b.[0]`: a dot after a
    backslash is part of the name, the other dots separate the field hierarchy. Use this
    only on qualified names read from a PDF (`get_fields()` keys, `widget_full_name`). A
    mapping key or plan field name is already a leaf; use `field_base_and_index` on it.
    """
    parts: list[str] = []
    current: list[str] = []
    escaped = False
    for char in full_name:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == ".":
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    if escaped:
        current.append("\\")
    parts.append("".join(current))
    return parts[-1]


def field_base_and_index(name: str) -> tuple[str, int]:
    """(base, occurrence index) of a field name as plans, mappings and dumps write it.

    The name is a leaf such as `Pt1Line6_CB_Sex[1]`, `P9_Line7.b.` or `Pt8Line42\\.a_YesNo`.
    Escapes are dropped and only a trailing `[n]` is split off: a dot is part of the name,
    never a hierarchy separator. For a qualified name read from a PDF, use
    `qualified_base_and_index`.
    """
    leaf = name.replace("\\", "")
    match = FIELD_INDEX_RE.match(leaf)
    if match is None:
        return leaf, 0
    return match.group("base"), int(match.group("index"))


def has_explicit_index(name: str) -> bool:
    """Whether a leaf name ends in its own `[n]` (`Name[0]`), not just the bare `Name`."""
    return FIELD_INDEX_RE.match(name.replace("\\", "")) is not None


def qualified_base_and_index(full_name: str) -> tuple[str, int]:
    """(base, occurrence index) of a fully qualified PDF field name (`form1[0]....Name[n]`)."""
    return field_base_and_index(leaf_field_name(full_name))


def field_base(name: str) -> str:
    return field_base_and_index(name)[0]


def widget_full_name(annot: Any) -> str:
    """Fully qualified field name of a widget annotation, built from its /Parent chain.

    A widget's own /T can be only the last part of a nested name: the N-400 item 7.b boxes
    are `P9_Line7\\` > `b\\` > `[0]`, so the widget alone is named `[0]`. Joining the /T
    of every ancestor gives `...P9_Line7\\.b\\.[0]`, which `leaf_field_name` reads as
    `P9_Line7.b.[0]`, the same name `get_fields()` reports.
    """
    parts: list[str] = []
    node = annot
    for _depth in range(64):  # a malformed /Parent loop cannot hang the caller
        if node is None:
            break
        node = node.get_object() if hasattr(node, "get_object") else node
        title = node.get("/T")
        if title is not None:
            parts.append(str(title))
        node = node.get("/Parent")
    return ".".join(reversed(parts))


def normalize_visible_text(value: str) -> str:
    return NON_ALNUM_RE.sub("", value.casefold())


def visible_value_present(rendered_text: str, expected: str) -> bool:
    normalized_expected = normalize_visible_text(expected)
    if not normalized_expected:
        return True
    return normalized_expected in normalize_visible_text(rendered_text)


_WORD_RE = re.compile(
    r'<word xMin="(?P<x0>[\d.]+)" yMin="(?P<y0>[\d.]+)" xMax="(?P<x1>[\d.]+)" yMax="(?P<y1>[\d.]+)">(?P<text>.*?)</word>'
)


def pdf_words(pdf_path: Path) -> list[tuple[int, float, float, float, float, str]] | None:
    """Every word of a PDF with its page and box (top-left origin, points), from `pdftotext -bbox`.

    None when poppler isn't installed or can't read the file; callers then fall back to the
    page text."""
    if not shutil.which("pdftotext"):
        return None
    result = subprocess.run(
        ["pdftotext", "-bbox", str(pdf_path), "-"], check=False, capture_output=True, text=True, errors="replace"
    )
    if result.returncode != 0:
        return None
    import html

    words: list[tuple[int, float, float, float, float, str]] = []
    for page_number, chunk in enumerate(result.stdout.split("<page ")[1:], start=1):
        for match in _WORD_RE.finditer(chunk):
            words.append(
                (
                    page_number,
                    float(match.group("x0")),
                    float(match.group("y0")),
                    float(match.group("x1")),
                    float(match.group("y1")),
                    html.unescape(match.group("text")),
                )
            )
    return words


def widget_boxes(pdf_path: Path) -> dict[tuple[str, int], list[tuple[int, float, float, float, float]]]:
    """(field base, occurrence) -> the page and box of each of its widgets, top-left origin.

    The occurrence is the field's place among the fields of that name in field-tree order, the
    `[n]` plans and mappings use (xfa_tools.acro_fields_by_base): two boxes both named
    `GivenName[0]` in different subforms are `GivenName[0]` and `GivenName[1]`."""
    reader = PdfReader(str(pdf_path))
    occurrence: dict[str, tuple[str, int]] = {}
    seen: dict[str, int] = defaultdict(int)
    for full_name, spec in (reader.get_fields() or {}).items():
        if not spec.get("/FT"):
            continue
        base, _index = qualified_base_and_index(full_name)
        occurrence[full_name] = (base, seen[base])
        seen[base] += 1
    boxes: dict[tuple[str, int], list[tuple[int, float, float, float, float]]] = defaultdict(list)
    for page_number, page in enumerate(reader.pages, start=1):
        media = [float(value) for value in page.mediabox]
        left, top = media[0], media[3]
        for annot_ref in page.get("/Annots") or []:
            annot = annot_ref.get_object()
            if annot.get("/Subtype") != "/Widget":
                continue
            full_name = widget_full_name(annot)
            name = leaf_field_name(full_name)
            if not name:
                continue
            x0, y0, x1, y1 = (float(value) for value in annot.get("/Rect", [0, 0, 0, 0]))
            boxes[occurrence.get(full_name) or field_base_and_index(name)].append(
                (page_number, min(x0, x1) - left, top - max(y0, y1), max(x0, x1) - left, top - min(y0, y1))
            )
    return boxes


def text_in_boxes(
    words: list[tuple[int, float, float, float, float, str]],
    boxes: list[tuple[int, float, float, float, float]],
    *,
    slack: float = 1.5,
) -> str:
    """The words whose centre lies inside any of the boxes, in reading order."""
    found = []
    for page, x0, y0, x1, y1, text in words:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        for box_page, bx0, by0, bx1, by1 in boxes:
            if page == box_page and bx0 - slack <= cx <= bx1 + slack and by0 - slack <= cy <= by1 + slack:
                found.append((page, round(y0), x0, text))
                break
    return " ".join(text for *_rest, text in sorted(found))


def question_box_text(
    question: dict[str, Any],
    words: list[tuple[int, float, float, float, float, str]] | None,
    boxes: dict[tuple[str, int], list[tuple[int, float, float, float, float]]] | None,
) -> str | None:
    """What the filing copy shows inside this question's own boxes, or None when that can't be
    told (no word positions, or none of its boxes has a widget). A box named without "[n]" counts
    every widget of that name."""
    if words is None or not boxes:
        return None
    rects: list[tuple[int, float, float, float, float]] = []
    for name in dict(question.get("field_values") or {}):
        base, index = field_base_and_index(str(name))
        if has_explicit_index(str(name)):
            rects.extend(boxes.get((base, index), []))
        else:
            rects.extend(rect for (other, _index), found in boxes.items() if other == base for rect in found)
    return text_in_boxes(words, rects) if rects else None


def ghostscript() -> str | None:
    return shutil.which("gs") or shutil.which("gswin64c") or shutil.which("gswin32c")


def extract_pdf_text(pdf_path: Path) -> str:
    """Rendered text of a PDF: pdftotext (poppler), else Ghostscript txtwrite, else pypdf.

    pypdf is a last resort: it cannot decode the TrueType fonts Ghostscript embeds for
    filled values, so it reports filled answers as missing from a rendered filing copy.
    """
    gs = ghostscript()
    commands = []
    if shutil.which("pdftotext"):
        commands.append(["pdftotext", str(pdf_path), "-"])
    if gs:
        commands.append(
            [gs, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=txtwrite", "-o", "-", str(pdf_path)]
        )
    for command in commands:
        result = subprocess.run(command, check=False, capture_output=True, text=True, errors="replace")
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout

    reader = PdfReader(str(pdf_path))
    chunks: list[str] = []
    for page in reader.pages:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks)


def question(
    *,
    key: str,
    label: str,
    status: str,
    field_values: dict[str, str] | None = None,
    visible_values: list[str] | None = None,
    fact_ids: list[str] | None = None,
    required: bool = True,
    unresolved_severity: str = "error",
    notes: str = "",
    open_item: str = "",
) -> dict[str, Any]:
    item = {
        "key": key,
        "label": label,
        "status": status,
        "required": required,
        "unresolved_severity": unresolved_severity,
        "field_values": dict(field_values or {}),
        "visible_values": [value for value in (visible_values or []) if str(value).strip()],
        "fact_ids": list(fact_ids or []),
        "notes": notes,
    }
    # The open-items ledger id that explains a deliberate gap. The audit ties this
    # question's "unresolved" error (and form-specific blanks in its fields) to it.
    if str(open_item or "").strip():
        item["open_item"] = str(open_item).strip()
    return item


QUESTION_KEYS = set(inspect.signature(question).parameters)


def flatten_filled_field_values(questions: list[dict[str, Any]]) -> dict[str, str]:
    """The non-empty answers of every filled or partially filled question, by field name."""
    fields: dict[str, str] = {}
    for item in questions:
        if item.get("status") not in WRITTEN_STATUSES:
            continue
        for field_name, value in dict(item.get("field_values", {})).items():
            text = str(value).strip()
            if text:
                fields[field_name] = text
    return fields


def allowed_nonempty_bases(questions: list[dict[str, Any]]) -> list[str]:
    bases = {field_base(name) for name in flatten_filled_field_values(questions)}
    return sorted(bases)


def unresolved_questions(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in questions
        if item.get("required", True) and item.get("status") not in RESOLVED_STATUSES
    ]


def form_manifest_entry(
    *,
    kind: str,
    subject: str,
    output_pdf: Path,
    source_pdf: Path | None,
    questions: list[dict[str, Any]],
    fact_table_path: Path,
    sources: list[str],
    official_form: dict[str, Any] | None = None,
    question_schema: str | None = None,
    schema_edition: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "kind": kind,
        "subject": subject,
        "questions": questions,
        "fact_table_path": str(fact_table_path),
        "expected_fields": flatten_filled_field_values(questions),
        "allowed_nonempty_bases": allowed_nonempty_bases(questions),
        "sources": sources,
    }
    if source_pdf is not None:
        entry["source_pdf"] = str(source_pdf)
    if official_form:
        entry["official_form"] = official_form
    if question_schema:
        entry["question_schema"] = question_schema
    if schema_edition:
        entry["schema_edition"] = schema_edition
    return entry


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- CLI


def _absolute(path: Path | None) -> Path | None:
    return path.expanduser().resolve() if path is not None else None


def plan_questions(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """A plan's questions, normalized, with unknown statuses refused, and a payment form plan
    that holds card or bank details refused (payment_plan_problems)."""
    questions = [
        question(**{k: v for k, v in item.items() if k in QUESTION_KEYS})
        for item in plan.get("questions", [])
    ]
    bad_status = [item["key"] for item in questions if item["status"] not in ALL_STATUSES]
    if bad_status:
        raise ValueError(f"Unknown status on question(s): {bad_status}. Allowed: {sorted(ALL_STATUSES)}")
    problems = payment_plan_problems(
        str(plan.get("kind") or ""), questions, str(plan.get("question_schema") or "")
    )
    if problems:
        form = str(plan.get("kind") or "").upper()
        raise ValueError(
            f"the {form} plan holds what only the payer may write, so nothing was written for this form: "
            + "; ".join(problems)
            + ". The payer writes the card or bank details by hand and signs; clear these boxes in the plan "
            "(those questions stay pending_signature, their boxes blank) and build again."
        )
    return questions


# The payment forms' boxes that the card or bank account holder fills in by hand at signing: the
# card number, expiry, CVV and type with the holder's billing address and contact details (G-1450);
# the account type, business name, checking or savings, routing and account numbers and the bank's
# name (G-1650). The tools never write a value in one. A plan that holds one is refused before
# anything is written (plan_questions), and a fill refuses one too (xfa_tools.write_filled_pdf), so
# such a value reaches no mapping, manifest, build record, log or PDF.
PAYMENT_BY_HAND: dict[str, tuple[str, ...]] = {
    "g-1450": (
        "Pt1Line2b_StreetNumberName", "CCHolderAptSteFlr_Unit", "CCHolderAptSteFlrNumber", "CityOrTown", "State",
        "ZipCode", "DaytimeTelephoneNumber", "Email", "CreditCardNumber_1", "CreditCardNumber_2",
        "CreditCardNumber_3", "CreditCardNumber_4[0]", "CreditCardNumber_4[1]", "CreditCardTypeChBx", "ExpirationDate",
    ),
    "g-1650": ("CB_AccountType", "BusinessName", "CB_CreditCardType", "RoutingNumber", "AccountNumber", "BankName"),
}
# Boxes only that payment form has: how a fill tells the payment form's blank from any other.
PAYMENT_FORM_MARKERS: dict[str, tuple[str, ...]] = {
    "g-1450": ("AuthorizedPaymentAmt", "CreditCardNumber_1", "CreditCardTypeChBx"),
    "g-1650": ("AuthorizedPaymentAmt", "RoutingNumber", "AccountNumber"),
}
# Nine digits or more, spaced or dashed: a card, account or routing number. Nothing the tools prepare
# on a payment form (names and an amount of at most seven characters) looks like one.
LONG_NUMBER_RE = re.compile(r"\d(?:[\s-]*\d){8,}")


def payment_by_hand_bases(kind: str) -> set[str]:
    return {field_base(name) for name in PAYMENT_BY_HAND.get(kind.strip().lower(), ())}


def payment_form_of(bases: set[str] | list[str]) -> str:
    """The payment form ("g-1450" or "g-1650") whose blank has these boxes, or ""."""
    present = set(bases)
    return next((kind for kind, markers in PAYMENT_FORM_MARKERS.items() if set(markers) <= present), "")


def payment_plan_problems(kind: str, questions: list[dict[str, Any]], schema_name: str = "") -> list[str]:
    """Why a G-1450 or G-1650 plan can't be used, naming questions and boxes, never their values
    ([] for any other form). Whatever a question's status, it may write no box the payer fills in
    by hand, no box that isn't one of its own question's boxes in the schema, and no long number
    (a card, account or routing number) in a box, a visible value or its notes."""
    kind = kind.strip().lower()
    if kind not in PAYMENT_BY_HAND:
        return []
    from form_question_schema import QUESTION_SCHEMAS  # local import: it imports this module

    schema = QUESTION_SCHEMAS.get(schema_name) if schema_name else None
    if schema is None or schema.get("kind") != kind:
        schema = next((item for item in QUESTION_SCHEMAS.values() if item.get("kind") == kind), None)
    owned = {
        str(key): {field_base_and_index(str(name)) for name in spec.get("required_fields", [])}
        for key, spec in dict((schema or {}).get("required_questions") or {}).items()
    }
    by_hand = payment_by_hand_bases(kind)
    problems: list[str] = []
    for item in questions:
        key = str(item.get("key") or "")
        written = [
            str(name)
            for name, value in dict(item.get("field_values") or {}).items()
            if str(value if value is not None else "").strip()
        ]
        hand = [name for name in written if field_base(name) in by_hand]
        if hand:
            problems.append(f"{key} has card or bank details in {', '.join(hand)}")
        stray = [name for name in written if name not in hand and field_base_and_index(name) not in owned.get(key, set())]
        if stray:
            problems.append(f"{key} writes boxes that are not its own ({', '.join(stray)})")
        texts = [str(value) for value in dict(item.get("field_values") or {}).values()]
        texts += [str(value) for value in list(item.get("visible_values") or [])] + [str(item.get("notes") or "")]
        if any(LONG_NUMBER_RE.search(text) for text in texts):
            problems.append(f"{key} holds a long number (a card, account or routing number?) in its answers or notes")
    return problems


def apply_plan(
    plan: dict[str, Any],
    *,
    mapping_out: Path,
    filing_copy: Path | None = None,
    source_pdf: Path | None = None,
    blank_pdf: Path | None = None,
    fact_table_base: Path | None = None,
    withheld: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Write a plan's fill mapping; return (summary, manifest entry or None).

    The manifest entry is built when `filing_copy` is given. A relative
    `fact_table_path` is read against `fact_table_base`. `withheld` boxes keep their answers in
    the plan but go neither into the mapping nor into what the manifest expects on the form
    (build withholds the boxes that changed on a new edition of the blank).
    """
    questions = plan_questions(plan)
    withheld = set(withheld or ())
    mapping = {box: value for box, value in flatten_filled_field_values(questions).items() if box not in withheld}
    mapping_out.parent.mkdir(parents=True, exist_ok=True)
    dump_json(mapping_out, mapping)

    blank_pdf = _absolute(blank_pdf)
    fields_path, field_dump = load_field_dump(blank_pdf)

    entry = None
    if filing_copy is not None:
        fact_table = str(plan.get("fact_table_path") or "").strip()
        fact_path = Path(fact_table).expanduser() if fact_table else None
        if fact_path is not None and not fact_path.is_absolute() and fact_table_base is not None:
            fact_path = fact_table_base / fact_path
        entry = form_manifest_entry(
            kind=str(plan["kind"]).lower(),
            subject=str(plan.get("subject") or ""),
            output_pdf=filing_copy,
            source_pdf=source_pdf,
            questions=questions,
            fact_table_path=_absolute(fact_path) if fact_path else Path(""),
            sources=list(plan.get("sources", [])),
            official_form={"pdf_path": str(blank_pdf)} if blank_pdf else None,
            question_schema=plan.get("question_schema"),
            schema_edition=plan.get("schema_edition"),
        )
        if not fact_path:
            entry["fact_table_path"] = ""
        if withheld:
            entry["expected_fields"] = dict(mapping)
            entry["allowed_nonempty_bases"] = sorted({field_base(name) for name in mapping})
            entry["withheld_boxes"] = sorted(withheld)
        if isinstance(plan.get("new_edition_review"), dict):
            # The preparer's box-by-box check of a form prepared on a new edition (see the audit).
            entry["new_edition_review"] = dict(plan["new_edition_review"])
        if str(plan.get("pays_for") or "").strip():
            # The fee a G-1450 or G-1650 pays: the form, which of its fees, the amount, and its place in
            # the fees tool's list (the order the payment forms go on top of a paper packet).
            entry["pays_for"] = str(plan["pays_for"]).strip()
            for key in ("pays_what", "pays_amount", "fee_order"):
                if plan.get(key) not in (None, ""):
                    entry[key] = plan[key]
        if isinstance(plan.get("safe_mailing_address"), dict):
            # A protected client's safe mailing address, as the preparer recorded it; the audit
            # checks every mailing-address box against it.
            entry["safe_mailing_address"] = dict(plan["safe_mailing_address"])
        if field_dump is not None:
            entry["field_dump"] = str(fields_path)

    counts = Counter(item["status"] for item in questions)
    summary: dict[str, Any] = {
        "mapping": str(mapping_out),
        "mapped_fields": len(mapping),
        "status_counts": dict(counts),
        "unresolved_required": [
            {"key": item["key"], "label": item["label"], "status": item["status"]}
            for item in unresolved_questions(questions)
        ],
    }
    if field_dump is not None:
        summary["field_dump"] = str(fields_path)
        problems = {key: items for key, items in mapping_field_check(mapping, field_dump).items() if items}
        if problems:
            summary["field_check"] = problems
    elif fields_path is not None:
        summary["field_dump"] = f"not found: {fields_path}"
    return summary, entry


STATUS_SHORT = {
    STATUS_FILLED: "filled",
    STATUS_PARTIALLY_FILLED: "partial",
    STATUS_NOT_APPLICABLE: "n/a",
    STATUS_PENDING_CLIENT: "client",
    STATUS_PENDING_SIGNATURE: "signature",
    STATUS_MISSING: "missing",
    STATUS_MANUAL_REVIEW: "review",
}


def status_line(counts: dict[str, int]) -> str:
    """'53 q: 40 filled, 6 n/a, 5 client, 2 signature' in a fixed status order."""
    total = sum(counts.values())
    parts = [f"{counts[status]} {STATUS_SHORT[status]}" for status in STATUS_SHORT if counts.get(status)]
    return f"{total} q: " + ", ".join(parts) if parts else f"{total} q"


def capped(items: list[str], limit: int) -> str:
    """'a, b, c, +4 more'."""
    shown = ", ".join(str(item) for item in items[:limit])
    return shown + (f", +{len(items) - limit} more" if len(items) > limit else "")


def field_check_lines(problems: dict[str, list[str]], limit: int = 3) -> list[str]:
    labels = {
        "unknown_fields": "not on the form",
        "index_out_of_range": "[n] past the last box",
        "not_an_on_state": "not an on-state",
        "not_a_choice": "not one of the drop-down's choices",
    }
    return [
        f"field check: {len(items)} {labels.get(key, key)}: {capped(items, limit)}"
        for key, items in problems.items()
        if items
    ]




def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    import build_forms  # local import: build_forms imports this module

    build_parser_ = subparsers.add_parser(
        "build",
        help="Plans -> blanks, mappings, manifest, verified fill, filing copies and audit, in one step.",
        description=build_forms.__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    build_forms.add_build_arguments(build_parser_)

    editions_parser = subparsers.add_parser(
        "editions", help="Check each blank's edition against the tools and, with --live, uscis.gov."
    )
    editions_parser.add_argument("matter", type=Path)
    editions_parser.add_argument("--live", action="store_true")
    editions_parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "build":
        import build_forms

        return build_forms.run(args)
    if args.command == "editions":
        import editions

        return editions.main([str(args.matter)] + (["--live"] if args.live else []) + (["--json"] if args.json else []))
    return 2


if __name__ == "__main__":
    sys.exit(main())

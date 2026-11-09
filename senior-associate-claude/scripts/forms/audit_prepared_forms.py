#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Audit prepared USCIS form PDFs before review, packet assembly or handoff.

    audit_prepared_forms.py --output-json OUT.json [--intent-manifest MANIFEST.json]
        --check KIND=/abs/path/form.pdf [--check ...] [--full]

KIND is any form with a question schema (form_question_schema.py list). Exit code 1
when any finding has severity "error". The JSON holds every finding; stdout gets a short
summary (--full prints the JSON too). An error that is exactly a deliberate gap is tied to
the open item its plan question names ("open_item"), so the summary separates tied errors
from the ones still to fix. REFERENCE.md says what is and is not checked.
"""
from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pypdf import PdfReader

# pypdf logs "Ignoring padding error" for some encrypted USCIS strings; it is harmless.
logging.getLogger("pypdf").setLevel(logging.ERROR)

from form_question_schema import QUESTION_SCHEMAS, get_question_schema, load_profile, profile_not_applicable
import formats
from forms_workflow import (
    FIELD_INDEX_RE,
    PAYMENT_BY_HAND,
    STATUS_FILLED,
    STATUS_MANUAL_REVIEW,
    STATUS_MISSING,
    STATUS_NOT_APPLICABLE,
    STATUS_PARTIALLY_FILLED,
    STATUS_PENDING_CLIENT,
    STATUS_PENDING_SIGNATURE,
    WRITTEN_STATUSES,
    extract_pdf_text,
    field_base_and_index,
    leaf_field_name,
    linked_checkbox_defects,
    payment_by_hand_bases,
    normalize_visible_text,
    pdf_words,
    qualified_base_and_index,
    question_box_text,
    visible_value_present,
    widget_boxes,
    widget_full_name,
)
from xfa_tools import acro_fields_by_base, adobe_view, display_value, global_bound_names, stored_values


ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
US_DATE_RE = re.compile(r"^(?P<month>\d{2})/(?P<day>\d{2})/(?P<year>\d{4})$")

# How the forms name the United States in a country box. A state and ZIP Code exist only for a
# U.S. address: a row abroad has neither, so every rule that asks for them asks this first.
US_COUNTRY_NAMES = {
    "united states", "united states of america", "usa", "us", "u.s.", "u.s.a.", "u.s", "u.s.a",
}


def is_us_country(value: str) -> bool:
    return " ".join(str(value or "").split()).casefold() in US_COUNTRY_NAMES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit prepared USCIS form PDFs.")
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--intent-manifest", type=Path)
    parser.add_argument(
        "--check",
        action="append",
        default=[],
        help="Audit target in the form kind=/absolute/path/to/form.pdf",
    )
    parser.add_argument("--full", action="store_true", help="Also print the whole audit JSON.")
    parser.add_argument(
        "--profile", type=Path, help="The attorney profile (has_uscis_online_account, mailing_address), if any."
    )
    parser.add_argument(
        "--matter", type=Path, help="The matter folder, for its settings (a protected matter's safe address)."
    )
    return parser.parse_args()


# Field names: a plan, mapping or values key is a leaf name (`P9_Line7.b.`, `Name[2]`) and goes
# through field_base_and_index, which never splits on a dot. A qualified name read from the
# PDF (`form1[0]....P9_Line7\.b\.[0]`) goes through qualified_base_and_index, and a widget's
# name is built from its whole /Parent chain (widget_full_name), never from its own /T alone.


def canonical_field_name(field_name: str) -> str:
    return field_name.replace("\\", "")


def normalized_fields_key(finding: dict[str, object]) -> tuple[str, ...]:
    fields = finding.get("fields")
    if not isinstance(fields, list):
        return ()
    normalized = [
        canonical_field_name(str(field)).strip()
        for field in fields
        if str(field).strip()
    ]
    return tuple(sorted(set(normalized)))


def collapse_overlapping_findings(findings: list[dict[str, object]]) -> list[dict[str, object]]:
    unresolved_field_sets: set[tuple[str, str, tuple[str, ...]]] = set()
    for finding in findings:
        if not finding.get("question_key"):
            continue
        fields_key = normalized_fields_key(finding)
        if not fields_key:
            continue
        unresolved_field_sets.add(
            (
                str(finding.get("form") or ""),
                str(finding.get("file") or ""),
                fields_key,
            )
        )

    collapsed: list[dict[str, object]] = []
    for finding in findings:
        fields_key = normalized_fields_key(finding)
        title = str(finding.get("title") or "").casefold()
        overlaps_unresolved = (
            not finding.get("question_key")
            and bool(fields_key)
            and (
                str(finding.get("form") or ""),
                str(finding.get("file") or ""),
                fields_key,
            )
            in unresolved_field_sets
        )
        if overlaps_unresolved and ("missing" in title or "incomplete" in title):
            continue
        collapsed.append(finding)
    return collapsed


def occurrence_key(base: str, index: int, total: int) -> str:
    if total == 1 and index == 0:
        return base
    return f"{base}[{index}]"


# Stored XFA values, each read from the data node Adobe reads for its box (xfa_tools.data_node): on
# the I-765 a box's value lives in its page's data group (form1/Page3/Line19_DOB), so a value stored
# directly under form1 reads as blank here, as it does in Adobe.
xfa_values = stored_values


def acro_values(pdf_path: Path) -> dict[str, str]:
    reader = PdfReader(str(pdf_path))
    values: dict[str, str] = {}
    button_fields: list[tuple[str, int, str]] = []
    button_max_index_by_base: dict[str, int] = defaultdict(int)
    for page in reader.pages:
        for annot_ref in page.get("/Annots", []):
            annot = annot_ref.get_object()
            if str(annot.get("/Subtype") or "") != "/Widget":
                continue
            holder = annot
            if "/T" not in annot and annot.get("/Parent") is not None:
                holder = annot["/Parent"].get_object()
            if str(annot.get("/FT") or holder.get("/FT") or "") != "/Btn":
                continue
            field_name = leaf_field_name(widget_full_name(annot)).strip()
            if not field_name:
                continue
            base, index = field_base_and_index(field_name)
            value = display_value(annot.get("/AS"))
            button_fields.append((base, index, value))
            if index > button_max_index_by_base[base]:
                button_max_index_by_base[base] = index
    for base, index, value in button_fields:
        key = occurrence_key(base, index, button_max_index_by_base[base] + 1)
        if value:
            values[key] = value

    parsed_fields: list[tuple[str, int, str]] = []
    max_index_by_base: dict[str, int] = defaultdict(int)
    for full_name, spec in (reader.get_fields() or {}).items():
        base, index = qualified_base_and_index(full_name)
        if str(spec.get("/FT") or "") == "/Btn":
            continue
        value = display_value(spec.get("/V"))
        parsed_fields.append((base, index, value))
        if index > max_index_by_base[base]:
            max_index_by_base[base] = index
    for base, index, value in parsed_fields:
        key = occurrence_key(base, index, max_index_by_base[base] + 1)
        if value:
            values[key] = value
    return values


def merged(xfa: dict[str, str], acro: dict[str, str]) -> dict[str, str]:
    """The stored XFA values, with the visible layer's where the XFA has none."""
    return {**xfa, **{name: value for name, value in acro.items() if value and not xfa.get(name)}}


def merged_values(pdf_path: Path) -> dict[str, str]:
    return merged(xfa_values(pdf_path), acro_values(pdf_path))


def field_value(values: dict[str, str], field_name: str) -> str:
    field_name = canonical_field_name(field_name)
    if field_name in values and values[field_name].strip():
        return values[field_name]
    match = FIELD_INDEX_RE.match(field_name)
    if match is None:
        indexed_name = f"{field_name}[0]"
        if indexed_name in values and values[indexed_name].strip():
            return values.get(indexed_name, "")
        indexed_values: list[tuple[int, str]] = []
        prefix = f"{field_name}["
        for key, value in values.items():
            if not key.startswith(prefix):
                continue
            indexed_match = FIELD_INDEX_RE.match(key)
            if indexed_match is None:
                continue
            indexed_values.append((int(indexed_match.group("index")), value))
        nonempty = [value for _index, value in sorted(indexed_values) if value.strip()]
        if len(nonempty) == 1:
            return nonempty[0]
        return ""
    if int(match.group("index")) == 0 and values.get(match.group("base"), "").strip():
        return values.get(match.group("base"), "")
    return ""


def canonical_date_string(value: str) -> str:
    text = value.strip()
    if ISO_DATE_RE.fullmatch(text):
        return text
    match = US_DATE_RE.fullmatch(text)
    if match is None:
        return text
    return f"{match.group('year')}-{match.group('month')}-{match.group('day')}"


def values_equivalent(expected: str, actual: str) -> bool:
    if expected.strip() == actual.strip():
        return True
    return canonical_date_string(expected) == canonical_date_string(actual)


def load_intent_manifest(path: Path | None) -> dict[str, dict[str, object]]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("files", {})


def load_fact_index(manifest_entry: dict[str, object] | None) -> dict[str, dict[str, object]]:
    if not manifest_entry:
        return {}
    fact_table_path = manifest_entry.get("fact_table_path")
    if not fact_table_path:
        return {}
    path = Path(str(fact_table_path))
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    facts = payload.get("facts", [])
    return {str(item["id"]): dict(item) for item in facts if "id" in item}


@lru_cache(maxsize=None)
def merged_values_for_path(path_text: str) -> dict[str, str]:
    path = Path(path_text)
    if not path.exists():
        return {}
    return merged_values(path)


def load_blank_form_values(manifest_entry: dict[str, object] | None) -> dict[str, str]:
    if not manifest_entry:
        return {}
    official_form = manifest_entry.get("official_form")
    if not isinstance(official_form, dict):
        return {}
    pdf_path = str(official_form.get("pdf_path") or "").strip()
    if not pdf_path:
        return {}
    return merged_values_for_path(pdf_path)


# A required section left missing, pending or for review is a deliberate gap when its question
# names an open item, so tie_open_items ties this error to that item like the question's own error.
INVALID_STATUS_TITLE = "Question plan uses an invalid status for a required form section"
# A plan written from an older version of its schema: the fix is the same for each symptom.
PREDATES_TITLE = "Question plan predates its schema; run form_question_schema.py migrate"
MIGRATE_FIX = (
    "The plan was written from an older version of its schema. Run "
    "`form_question_schema.py migrate \"<plan>\"`: it moves every answer onto the current skeleton by "
    "question key and box name, keeps each status, and lists the new questions to answer."
)


def schemas_for_kind(kind: str) -> list[str]:
    return sorted(name for name, schema in QUESTION_SCHEMAS.items() if schema.get("kind") == kind)


def unresolved_question_title(question: dict[str, object]) -> str:
    label = str(question.get("label") or question.get("key") or "Question")
    status = str(question.get("status") or "")
    if status == STATUS_PENDING_SIGNATURE:
        return f"{label} is still pending signature"
    if status == STATUS_PENDING_CLIENT:
        return f"{label} is still pending client input"
    if status == STATUS_MANUAL_REVIEW:
        return f"{label} requires attorney review"
    if status == STATUS_MISSING:
        return f"{label} is missing"
    if status == STATUS_PARTIALLY_FILLED:
        return f"{label} is partly filled; its blank boxes are still open"
    return f"{label} is unresolved"


def open_boxes(question: dict[str, object], schema_name: str) -> list[str]:
    """The boxes a partially filled question still owes: the schema's required boxes it leaves
    blank, or, when it fills all of those (a form rule can need more, such as a prior address's
    move-in date), every box it declares and leaves blank."""
    values = {str(name): str(value) for name, value in dict(question.get("field_values", {})).items()}
    blank = [name for name, value in values.items() if not value.strip()]
    schema = get_question_schema(schema_name) if schema_name else None
    spec = dict(schema.get("required_questions", {})).get(str(question.get("key"))) if schema else None
    required = [str(name) for name in list((spec or {}).get("required_nonempty_fields_when_filled", []))]
    return [name for name in required if not values.get(name, "").strip()] or blank


def settled_by_profile(question: dict[str, object], schema_name: str, profile: dict[str, object] | None) -> bool:
    """True when the attorney profile makes this unanswered question not applicable (the G-28's
    attorney online account when the attorney has none): no error, and no open item to tie."""
    if not profile or str(question.get("status") or "") == STATUS_FILLED:
        return False
    if any(str(value).strip() for value in dict(question.get("field_values") or {}).values()):
        return False
    schema = get_question_schema(schema_name) if schema_name else None
    spec = dict(schema.get("required_questions", {})).get(str(question.get("key"))) if schema else None
    return bool(spec and profile_not_applicable(spec, profile))


def schema_findings(
    *,
    pdf_path: Path,
    kind: str,
    questions: list[dict[str, object]],
    manifest_entry: dict[str, object],
    profile: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    schema_name = str(manifest_entry.get("question_schema") or "").strip()
    if not schema_name:
        # Without a schema nothing checks that the plan covers the form, so a plan for a form the
        # tools have a schema for must name it; only a form with no schema may go without.
        available = schemas_for_kind(kind)
        found: dict[str, object] = finding(
            kind,
            pdf_path,
            "Question plan names no schema, but this form has one"
            if available
            else "Question plan does not declare a shared schema",
            severity="error" if available else "warning",
        )
        if available:
            found["schemas"] = available
            found["fix"] = (
                "Set the plan's question_schema to the one that fits (form_question_schema.py list), then run "
                "form_question_schema.py migrate on the plan to add the questions it doesn't cover."
            )
        findings.append(found)
        return findings

    schema = get_question_schema(schema_name)
    if schema is None:
        findings.append(
            finding(kind, pdf_path, "Question plan references an unknown shared schema", question_schema=schema_name)
        )
        return findings

    schema_kind = str(schema.get("kind") or "").strip()
    if schema_kind and schema_kind != kind:
        findings.append(finding(kind, pdf_path, "Question plan schema does not match the audited form type",
                                question_schema=schema_name, schema_kind=schema_kind))

    plan_edition = str(manifest_entry.get("schema_edition") or "").strip()
    schema_edition = str(schema.get("edition") or "").strip()
    if plan_edition and schema_edition and plan_edition != schema_edition:
        findings.append(
            finding(
                kind,
                pdf_path,
                f"Question plan was written for the {plan_edition} edition; the schema is for {schema_edition}",
                question_schema=schema_name,
                plan_edition=plan_edition,
                schema_edition=schema_edition,
                fix=MIGRATE_FIX + " Then check every answer against the current edition's instructions.",
            )
        )

    question_index = {
        str(question.get("key")): question
        for question in questions
        if str(question.get("key") or "").strip()
    }

    for key, spec in dict(schema.get("required_questions", {})).items():
        question = question_index.get(key)
        if question is None:
            findings.append(finding(kind, pdf_path, PREDATES_TITLE, problem="a required form section is missing",
                                    question_key=key, question_schema=schema_name,
                                    allowed_statuses=list(spec.get("allowed_statuses", [STATUS_FILLED])),
                                    fix=MIGRATE_FIX))
            continue

        status = str(question.get("status") or "")
        allowed_statuses = list(spec.get("allowed_statuses", [STATUS_FILLED]))
        if settled_by_profile(question, schema_name, profile):
            continue
        if status not in allowed_statuses:
            findings.append(finding(kind, pdf_path, INVALID_STATUS_TITLE, question_key=key, question_schema=schema_name,
                                    status=status, allowed_statuses=allowed_statuses,
                                    fix=f"Use one of: {', '.join(allowed_statuses)}."))

        if status == STATUS_NOT_APPLICABLE:
            continue

        field_values = {
            str(field_name): str(value)
            for field_name, value in dict(question.get("field_values", {})).items()
        }
        required_fields = [str(name) for name in list(spec.get("required_fields", []))]
        missing_fields = [field_name for field_name in required_fields if field_name not in field_values]
        if missing_fields:
            findings.append(finding(kind, pdf_path, PREDATES_TITLE, problem="a section lacks boxes the schema lists",
                                    question_key=key, question_schema=schema_name, fields=missing_fields,
                                    fix=MIGRATE_FIX))

        if status == STATUS_PARTIALLY_FILLED and not open_boxes(question, schema_name):
            findings.append(finding(kind, pdf_path,
                                    "Question plan marks a section partially filled but leaves no box blank",
                                    question_key=key, question_schema=schema_name))

        if status != STATUS_FILLED:
            continue

        required_nonempty_fields = [
            str(name)
            for name in list(spec.get("required_nonempty_fields_when_filled", []))
        ]
        missing_nonempty = [
            field_name
            for field_name in required_nonempty_fields
            if not field_values.get(field_name, "").strip()
        ]
        if missing_nonempty:
            findings.append(finding(kind, pdf_path, "Question plan leaves required form values blank", question_key=key,
                                    question_schema=schema_name, fields=missing_nonempty))

    return findings


def plan_findings(
    *,
    pdf_path: Path,
    kind: str,
    manifest_entry: dict[str, object] | None,
    overflow: dict[tuple[str, int], dict[str, object]] | None = None,
    profile: dict[str, object] | None = None,
    widget_pdf: Path | None = None,
) -> list[dict[str, object]]:
    """Plan coverage, visible values and fact sources.

    A visible value must show inside the question's own boxes: words printed on the form itself
    ("Yes", "None", "United States") don't count. The boxes come from `widget_pdf` (the source
    whose widgets the filing copy was rendered from) and the words' positions from pdftotext;
    without either, the value is looked for anywhere in the page text.

    `profile` is the attorney profile: a question it makes not applicable (settled_by_profile)
    is treated as not_applicable even if the plan left it missing.

    `overflow` maps (base, index) of fields whose text is cut off on the filing copy
    (see overflow_report). A visible value that is missing only because its field
    overflows is left to the overflow finding, which names the real fix, instead of
    being reported as a value that does not show.
    """
    if not manifest_entry:
        return []

    questions = list(manifest_entry.get("questions", []))
    if not questions:
        return []

    findings = schema_findings(
        pdf_path=pdf_path,
        kind=kind,
        questions=questions,
        manifest_entry=manifest_entry,
        profile=profile,
    )
    fact_index = load_fact_index(manifest_entry)
    schema_name = str(manifest_entry.get("question_schema") or "").strip()

    rendered_text = ""
    words = boxes = None
    if any(
        str(question.get("status")) in WRITTEN_STATUSES and list(question.get("visible_values", []))
        for question in questions
    ):
        rendered_text = extract_pdf_text(pdf_path)
        if widget_pdf is not None:
            words = pdf_words(pdf_path)
            boxes = widget_boxes(widget_pdf) if words is not None else None

    for question in questions:
        status = str(question.get("status") or "")
        required = bool(question.get("required", True))
        fields = sorted(dict(question.get("field_values", {})).keys())
        if status == STATUS_PARTIALLY_FILLED:
            fields = open_boxes(question, schema_name)
        notes = str(question.get("notes") or "").strip()
        if settled_by_profile(question, schema_name, profile):
            continue

        if required and status not in {STATUS_FILLED, STATUS_NOT_APPLICABLE}:
            found = finding(kind, pdf_path, unresolved_question_title(question),
                            severity=str(question.get("unresolved_severity") or "error"),
                            question_key=question.get("key"))
            if fields:
                found["fields"] = fields
            if notes:
                found["notes"] = notes
            findings.append(found)
            if status != STATUS_PARTIALLY_FILLED:
                continue  # a partly filled question's printed answers are checked below

        if status not in WRITTEN_STATUSES:
            continue

        visible_values = [
            value
            for value in list(question.get("visible_values", []))
            if len(re.sub(r"[^0-9A-Za-z]+", "", str(value))) >= 3
        ]
        own_text = question_box_text(question, words, boxes) if visible_values else None
        shown_in = own_text if own_text is not None else rendered_text
        missing_visible = [
            value
            for value in visible_values
            if (own_text is not None or rendered_text) and not visible_value_present(shown_in, str(value))
        ]
        if missing_visible and overflow:
            missing_visible = [
                value
                for value in missing_visible
                if not visible_value_in_overflowing_field(str(value), question, overflow)
            ]
        if missing_visible:
            findings.append(finding(kind, pdf_path, "Visible filing copy does not show a filled question value",
                                    question_key=question.get("key"), question_label=question.get("label"),
                                    values=missing_visible))

        fact_ids = [str(item) for item in list(question.get("fact_ids", []))]
        from answer_integrity import confirmed, sensitive_question
        from form_question_schema import get_question_schema
        spec = ((get_question_schema(schema_name) or {}).get("required_questions") or {}).get(str(question.get("key")), {})
        if (spec.get("requires_client_confirmation") or sensitive_question(question, kind)) and not confirmed(question, fact_index):
            findings.append(finding(kind, pdf_path, "Sensitive answer needs a documented client confirmation",
                                    question_key=question.get("key"), fields=fields,
                                    fix="Leave unsupported answers blank and ask the client; link the dated confirmation in fact_ids."))
        if fact_ids:
            fact_records = [fact_index[fact_id] for fact_id in fact_ids if fact_id in fact_index]
            if fact_records and all(
                str(record.get("source_kind")) == "prior_prepared_form" for record in fact_records
            ):
                findings.append(finding(kind, pdf_path, "Filled answer relies only on prior prepared form artifacts",
                                        severity="warning", question_key=question.get("key"),
                                        question_label=question.get("label"), fact_ids=fact_ids))
    return findings


def parse_us_date(value: str) -> datetime | None:
    """The date in a box, or None when it isn't one: blank, another format, or no such day (02/30/2001), which
    the box rules report as not a real calendar date."""
    text = value.strip()
    if ISO_DATE_RE.fullmatch(text):
        year, month, day = (int(part) for part in text.split("-"))
    elif match := US_DATE_RE.fullmatch(text):
        year, month, day = int(match.group("year")), int(match.group("month")), int(match.group("day"))
    else:
        return None
    try:
        return datetime(year, month, day, tzinfo=UTC)
    except ValueError:
        return None


def age_from_dob(value: str, *, today: datetime | None = None) -> int | None:
    dob = parse_us_date(value)
    if dob is None:
        return None
    today = today or datetime.now(UTC)
    years = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        years -= 1
    return years


def new_edition_review_gaps(check: dict[str, object], manifest_entry: dict[str, object]) -> list[str]:
    """The boxes filled on a new edition that the plan's box-by-box check doesn't cover ([] when it
    covers every one). The check is the plan's `new_edition_review`: {"edition": the blank's
    edition, "boxes": {box: what was checked}}, one non-empty note for every box build filled."""
    filled = [str(name) for name in dict(manifest_entry.get("expected_fields") or {})]
    review = dict(manifest_entry.get("new_edition_review") or {})
    edition = str(check.get("file_edition") or "").strip()
    if not review or (edition and str(review.get("edition") or "").strip() != edition):
        return filled or ["(the whole form)"]
    noted = {
        field_base_and_index(str(name))
        for name, note in dict(review.get("boxes") or {}).items()
        if str(note or "").strip()
    }
    return [name for name in filled if field_base_and_index(name) not in noted]


def edition_findings(*, kind: str, pdf_path: Path, manifest_entry: dict[str, object] | None) -> list[dict[str, object]]:
    """A form filled on a blank the tools were not built for (build --allow-new-edition, after the
    attorney's decision). build filled only the boxes that are the same on it; still, the same box
    can ask something else on another edition, so the form doesn't pass until the plan records a
    box-by-box check of every box filled (new_edition_review). Until then the error is tied to
    nothing, so no open item can explain it away; with the check recorded, it is tied to the
    attorney's decision. The answers whose boxes changed are not on the form: that error is never
    tied (the questions that hold them go to manual_review with an open item of their own)."""
    entry = dict(manifest_entry or {})
    check = dict(entry.get("edition_check") or {})
    if not check or check.get("status") in {"match", "same_edition", "no_schema"}:
        return []
    edition = str(check.get("file_edition") or "unknown")
    gaps = new_edition_review_gaps(check, entry)
    found: dict[str, object] = finding(
        kind,
        pdf_path,
        f"Prepared on the {edition} edition, which the form tools were not built for ({check.get('schema_edition')})",
        edition_check={key: value for key, value in check.items() if key != "withheld"},
    )
    if gaps:
        found["unchecked_boxes"] = gaps[:40]
        found["unchecked_count"] = len(gaps)
        found["fix"] = (
            f"Check each box the build filled against the {edition} edition's form and instructions, and record it in "
            f"the plan: \"new_edition_review\": {{\"edition\": \"{edition}\", \"boxes\": {{\"<box>\": \"<item it is on "
            "this edition, same meaning>\"}}}, one note per box. A box that now asks something else: take its answer "
            "off the plan (manual_review, with an open item) instead."
        )
    elif check.get("open_item"):
        found["open_item"] = str(check["open_item"])
    findings = [found]
    withheld = dict(check.get("withheld") or {})
    if withheld:
        findings.append(
            finding(
                kind,
                pdf_path,
                f"{len(withheld)} answer(s) are not on the form: their boxes changed on the {edition} edition",
                fields=sorted(withheld),
                changes=withheld,
                fix="Set each question that holds one of these boxes to manual_review with an open item to complete it "
                "by hand on the new edition (or wait for updated form tools); build never fills a box that changed.",
            )
        )
    return findings


def matter_is_protected(matter: Path | None) -> bool:
    """The matter's protected setting (8 U.S.C. 1367), from its matter-meta.json; False without a matter."""
    if matter is None:
        return False
    plugin_root = str(Path(__file__).resolve().parents[2])
    if plugin_root not in sys.path:
        sys.path.insert(0, plugin_root)
    from scripts.matter_state import read_meta

    return bool(read_meta(matter).get("protected"))


def safe_address_findings(
    *,
    kind: str,
    pdf_path: Path,
    values: dict[str, str],
    manifest_entry: dict[str, object] | None,
    profile: dict[str, object] | None,
    protected: bool,
) -> list[dict[str, object]]:
    """In a protected matter every mailing-address box of the client holds the safe address."""
    import safe_address

    groups = safe_address.MAILING_GROUPS.get(kind, [])
    if not protected or not groups:
        return []
    safe = (manifest_entry or {}).get("safe_mailing_address")
    safe = dict(safe) if isinstance(safe, dict) and any(str(v).strip() for v in safe.values()) else None
    profile_address = str((profile or {}).get("mailing_address") or "").strip()
    fix = (
        "This client is protected (8 U.S.C. 1367): every mailing-address box holds the safe mailing address, the "
        "attorney's office address in care of the firm (or the attorney), unless the attorney gave another. Record it "
        "in the plan's safe_mailing_address and use it in each mailing-address box; the physical address stays in its "
        "own boxes."
    )
    findings: list[dict[str, object]] = []
    for group in groups:
        boxes = group.mailing
        if group.same_as_physical:
            answer_box, same_answer, physical = group.same_as_physical
            if field_value(values, answer_box).strip() == same_answer:
                boxes = physical  # the form takes the physical address as the mailing address
        stored = {field: field_value(values, field) for field in boxes.boxes().values()}
        if not any(value.strip() for value in stored.values()):
            continue  # nothing written: the question's own status and open item cover it
        if safe is None and not profile_address:
            findings.append(
                finding(
                    kind,
                    pdf_path,
                    "Protected client's mailing address can't be checked: no safe address is recorded",
                    fields=list(stored),
                    where=boxes.label,
                    fix=fix + " With no attorney mailing address in Your details, leave the boxes empty and add the "
                    "attorney_action open item the matter contract describes.",
                )
            )
            continue
        wrong = safe_address.mismatches(boxes, stored, safe, profile_address)
        if wrong:
            findings.append(
                finding(
                    kind,
                    pdf_path,
                    "Protected client's mailing address is not the safe address",
                    fields=[item["field"] for item in wrong],
                    where=boxes.label,
                    mismatches=wrong,
                    compared_with="the plan's safe_mailing_address" if safe else "the profile's mailing_address",
                    fix=fix,
                )
            )
    return findings


def final_output_findings(
    *,
    pdf_path: Path,
    kind: str,
    manifest_entry: dict[str, object] | None,
) -> list[dict[str, object]]:
    if not manifest_entry or "source_pdf" not in manifest_entry:
        return []

    findings: list[dict[str, object]] = []
    source_pdf = Path(str(manifest_entry["source_pdf"]))
    if not source_pdf.exists():
        findings.append(finding(kind, pdf_path, "Rendered filing copy is missing its XFA source companion",
                                source_file=str(source_pdf)))
        return findings

    reader = PdfReader(str(pdf_path))
    acroform = reader.trailer["/Root"].get("/AcroForm")
    has_xfa = False
    field_count = 0
    if acroform:
        acroform = acroform.get_object()
        has_xfa = "/XFA" in acroform
        field_count = len(reader.get_fields() or {})
    if has_xfa or field_count:
        findings.append(finding(kind, pdf_path,
                                "Final filing copy is still live or fillable instead of rendered static output",
                                has_xfa=has_xfa, field_count=field_count))
    return findings


def intent_findings(
    *,
    pdf_path: Path,
    kind: str,
    actual_values: dict[str, str],
    manifest_entry: dict[str, object] | None,
) -> list[dict[str, object]]:
    if not manifest_entry:
        return []

    findings: list[dict[str, object]] = []
    expected_fields = {
        canonical_field_name(str(field_name)): str(expected_value)
        for field_name, expected_value in dict(manifest_entry.get("expected_fields", {})).items()
    }
    # The bases of the planned fields are recomputed here, not only read from the manifest: a
    # manifest written before dotted names were handled stores "P9_Line7.b." as "" and
    # "P9_Line7.c" as "c", and would flag every answered N-400 item 7.b until re-planned.
    allowed_nonempty_bases = {
        canonical_field_name(str(base_name))
        for base_name in list(manifest_entry.get("allowed_nonempty_bases", []))
    } | {field_base_and_index(field_name)[0] for field_name in expected_fields}
    blank_values = load_blank_form_values(manifest_entry)

    mismatched = []
    for field_name, expected_value in expected_fields.items():
        actual_value = field_value(actual_values, field_name).strip()
        if not values_equivalent(expected_value, actual_value):
            mismatched.append(
                {
                    "field": field_name,
                    "expected": expected_value,
                    "actual": actual_value,
                }
            )
    if mismatched:
        findings.append(
            finding(kind, pdf_path, "XFA values do not match the declared form intent", mismatches=mismatched)
        )

    unexpected = []
    for field_name, value in sorted(actual_values.items()):
        if not value.strip():
            continue
        base_name, _index = field_base_and_index(field_name)
        if base_name.startswith("PDF417BarCode"):
            continue
        blank_value = field_value(blank_values, field_name).strip()
        if blank_value and values_equivalent(blank_value, value):
            continue
        if base_name not in allowed_nonempty_bases:
            unexpected.append(field_name)
    if unexpected:
        findings.append(
            finding(kind, pdf_path, "Unexpected non-empty XFA fields are present", fields=unexpected)
        )
    return findings


# An unselected checkbox stores "0" (or nothing) in the XFA data and "Off" in the AcroForm.
UNCHECKED = {"", "0", "Off"}


def finding(kind: str, pdf_path: Path, title: str, *, severity: str = "error", **detail: object) -> dict[str, object]:
    return {"severity": severity, "form": kind, "file": str(pdf_path), "title": title, **detail}


@dataclass
class Form:
    """One form under audit: what its auditor (AUDITORS) reads, and the findings it adds."""

    kind: str
    pdf_path: Path
    values: dict[str, str]  # the stored values: XFA, with the visible layer filling its gaps
    xfa: dict[str, str] | None = None  # the stored XFA values alone (default: values)
    acro: dict[str, str] | None = None  # the visible AcroForm values alone (default: values)
    manifest_entry: dict[str, object] | None = None
    intent_manifest: dict[str, dict[str, object]] = field(default_factory=dict)  # every form of the package
    today: datetime | None = None
    findings: list[dict[str, object]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.xfa = self.values if self.xfa is None else self.xfa
        self.acro = self.values if self.acro is None else self.acro

    def value(self, box: str) -> str:
        return field_value(self.values, box).strip()

    def filled(self, boxes: list[str]) -> bool:
        return any(self.value(box) for box in boxes)

    def checked(self, box: str) -> bool:
        return self.value(box) not in UNCHECKED

    def plan_status(self, key: str) -> str:
        """Status of question `key` in the form's question plan, or "" when there is none."""
        for question in list((self.manifest_entry or {}).get("questions", [])):
            if str(question.get("key") or "") == key:
                return str(question.get("status") or "")
        return ""

    def add(self, title: str, fields: list[str] | None = None, *, severity: str = "error", **detail: object) -> None:
        if fields is not None:
            detail = {"fields": fields, **detail}
        self.findings.append(finding(self.kind, self.pdf_path, title, severity=severity, **detail))

    def missing(self, title: str, fields: list[str], *, severity: str = "error") -> None:
        """A finding that names the boxes of `fields` left blank, when there are any."""
        blank = [box for box in fields if not self.value(box)]
        if blank:
            self.add(title, blank, severity=severity)

    def blank_output(self) -> None:
        if not any(str(value).strip() for value in self.values.values()):
            self.add("Prepared form has no populated stored values")

    def layers(self, title: str, fields: list[str], *, xfa: dict[str, str] | None = None,
               acro: dict[str, str] | None = None) -> None:
        """A finding for the boxes whose visible value (what the filing copy is rendered from) is not
        the stored one."""
        xfa = self.xfa if xfa is None else xfa
        acro = self.acro if acro is None else acro
        mismatches = []
        for box in fields:
            expected = field_value(xfa, box).strip()
            actual = field_value(acro, box).strip()
            if expected and not values_equivalent(expected, actual):
                mismatches.append({"field": box, "stored": expected, "visible": actual})
        if mismatches:
            self.add(title, mismatches=mismatches)

    def one_of(self, label: str, boxes: list[str], *, required: bool = True) -> str:
        """Separate checkboxes of which exactly one must be checked (a yes box and a no box, say).
        Returns the box that is checked, or ""."""
        checked = [box for box in boxes if self.checked(box)]
        if len(checked) > 1:
            self.add(f"{label}: more than one box is checked where the form takes one", checked)
        elif not checked and required:
            self.add(f"{label} is not answered", boxes)
        return checked[0] if len(checked) == 1 else ""

    def conditional(self, rules: list[tuple[str, str, str, list[str]]]) -> list[str]:
        """For each (answer box, answer, title, follow-up boxes): when the box holds that answer, the
        follow-up boxes must be filled; when it holds another answer, they must be empty. Returns
        every box involved, for the layer check."""
        involved: list[str] = []
        for box, answer, title, follow_up in rules:
            involved += [box, *follow_up]
            given = self.value(box)
            if given == answer:
                self.missing(title, follow_up)
            elif given and self.filled(follow_up):
                self.findings.append(finding(
                    self.kind, self.pdf_path,
                    "Follow-up answers are given although the question before them is not answered Yes",
                    question_box=box, fields=[name for name in follow_up if self.value(name)], answer=given,
                ))
        return involved

    def address_missing(self, street: str, city: str, state: str, zip_code: str, country: str) -> list[str]:
        """The boxes a started address row still needs: street, city and country, and a state and
        ZIP Code only when the country is the United States."""
        needed = [street, city, country] + ([state, zip_code] if is_us_country(self.value(country)) else [])
        return [name for name in needed if name and not self.value(name)]


def audit_form(kind: str, pdf_path: Path, values: dict[str, str], **context: object) -> list[dict[str, object]]:
    """The form's own rules (AUDITORS[kind]) on its stored values; `context` is any other Form field."""
    form = Form(kind, pdf_path, values, **context)  # type: ignore[arg-type]
    AUDITORS[kind](form)
    from consistency import check_consistency
    check_consistency(form)
    return form.findings


def count_answer(text: str) -> int | None:
    """A count as the form takes it: digits, or "None" (how the instructions say to write zero).

    Returns None when the box is blank or holds something that is not a count.
    """
    cleaned = text.strip().rstrip(".").upper()
    if cleaned in {"NONE", "N/A", "NA"}:
        return 0
    return int(cleaned) if cleaned.isdigit() else None


# Part 6 item 1 on-states. "Information About Your Current Marriage (including if you are legally
# separated)": a legally separated applicant still has a current spouse to describe.
I485_NEVER_MARRIED = "1"
I485_CURRENTLY_MARRIED = {"2", "7"}  # married, legally separated
I485_PREVIOUSLY_MARRIED = {"3", "4", "5"}  # divorced, widowed, marriage annulled
I485_MARRIAGE_ENDED_OTHER = "4"  # Part 6 item 18 "Other"
I485_NOT_EXEMPT = "23"  # Part 9 item 56 "I do not fall under any of the exempt categories"

# Part 8 item 2: five separate race boxes (not a group); any one or more may be checked.
I485_RACE_FIELDS = [f"Pt7Line2_Race[{index}]" for index in range(5)]


# Part 2 item 3: one immigrant category, chosen from these groups. The category
# decides which other Part 2 answers apply (an I-140 question means nothing on a
# family-based filing).
I485_CATEGORY_GROUPS: dict[str, list[str]] = {
    "family": ["Pt2Line3a_CB"],
    "employment": ["Pt2Line3b_CB140", "Pt2Line3b_CB526"],
    "special_immigrant": ["Pt2Line3c_CB"],
    "asylee_refugee": ["Pt2Line3d_AsyleeRefugeeCB"],
    "trafficking_crime_victim": ["Pt2Line3e_CB"],
    "special_program": ["Pt2Line3f_CB"],
    "additional_option": ["Pt2Line3g_CB"],
}
I485_CATEGORY_FIELDS = [name for names in I485_CATEGORY_GROUPS.values() for name in names]
I485_DIVERSITY_VISA = "3g0"
I485_OTHER_ELIGIBILITY = "3g4"


def i485_category_findings(form: Form, *, concurrent_petition: bool = False) -> list[str]:
    """Check the Part 2 answers that depend on the category selected in item 3.

    Returns the fields involved, for the layer-agreement check.
    """
    categories: dict[str, str] = {}  # category group -> the on-state checked in it
    for group, names in I485_CATEGORY_GROUPS.items():
        checked = next((form.value(name) for name in names if form.value(name)), "")
        if checked:
            categories[group] = checked
    involved = list(I485_CATEGORY_FIELDS)
    if not categories:
        form.add("Part 2 item 3 immigrant category is not selected", list(I485_CATEGORY_FIELDS))
        return involved
    if len(categories) > 1:
        form.add(
            "More than one Part 2 item 3 immigrant category is selected",
            [
                name
                for group in categories
                for name in I485_CATEGORY_GROUPS[group]
                if form.value(name)
            ],
        )

    # Item 4 (INA 245(i)) applies to family, employment, special immigrant and DV filings.
    if {"family", "employment", "special_immigrant"} & set(categories) or (
        categories.get("additional_option") == I485_DIVERSITY_VISA
    ):
        involved.append("Pt2Line4_CB")
        form.missing("Part 2 item 4 (INA 245(i)) is not answered", ["Pt2Line4_CB"])

    if "employment" in categories:
        # Item 2 asks for the underlying petition's receipt number and priority date "(if any)".
        # An I-140 filed together with the I-485 has no receipt yet; the plan says so by marking
        # its underlying_petition question not_applicable.
        employment_fields = [] if concurrent_petition else ["Pt2Line2_Receipt", "Pt2Line2_Date"]
        if form.value("Pt2Line3b_CB140"):
            employment_fields.append("Pt2Line3b_CB140Assoc")
        for name in ("Pt2Line2_Receipt", "Pt2Line2_Date", *employment_fields):
            if name not in involved:
                involved.append(name)
        form.missing("Employment-based category details are incomplete", employment_fields)
        if form.value("Pt2Line3b_CB140Assoc") == "Y":
            involved.extend(["Pt2Relative_CB", "Pt2RelativeType_CB"])
            form.missing("Relative who filed or owns the I-140 employer is not described",
                         ["Pt2Relative_CB", "Pt2RelativeType_CB"])

    asylee_choice = categories.get("asylee_refugee", "")
    date_field = {"3d0": "Pt2Line3d_Asylum", "3d1": "Pt2Line3d_Refugee"}.get(asylee_choice)
    if date_field:
        involved.append(date_field)
        form.missing("Asylum grant or refugee admission date is missing", [date_field])

    option = categories.get("additional_option", "")
    option_field = {
        I485_DIVERSITY_VISA: "Pt2Line1g_DV",
        I485_OTHER_ELIGIBILITY: "Pt2Line1g_OtherEligibility",
    }.get(option)
    if option_field:
        involved.append(option_field)
        form.missing("Diversity Visa rank number or other eligibility is missing", [option_field])
    return involved


def audit_i485(form: Form) -> None:
    """I-485 rules. Boxes the form marks "(if any)" or asks for only in some cases are
    required only in those cases: an empty "if any" box is the correct answer when there is
    nothing to report, so these rules never push a preparer to type N/A to clear them."""
    applicant_age = age_from_dob(form.value("Pt1Line3_DOB"))
    application_basis = form.value("Pt2Line2_CB")
    marital_status = form.value("Pt6Line1_MaritalStatus")
    currently_married = marital_status in I485_CURRENTLY_MARRIED
    times_married = form.value("Pt6Line3_TimesMarried")
    marriage_count = count_answer(times_married)  # "None" is zero
    child_count = form.value("Pt6Line1_TotalChildren")
    children = count_answer(child_count)
    last_arrival = form.value("Pt2Line11_CB")

    identity_fields = ["Pt1Line1_FamilyName", "Pt1Line1_GivenName", "Pt1Line3_DOB", "Pt1Line3_YN", "Pt1Line4_YN",
                       "Pt1Line5_YN", "Pt1Line7_CityTownOfBirth", "Pt1Line7_CountryOfBirth",
                       "Pt1Line8_CountryofCitizenshipNationality", "Pt1Line6_CB_Sex"]
    form.missing("Missing high-signal identity fields", identity_fields)
    if form.value("Pt1Line4_YN") == "Y":
        form.missing("A-number field is missing even though the applicant answered yes", ["Pt1Line4_AlienNumber"])

    # Every applicant answers these, whatever the category.
    application_basis_fields = ["Pt2Line2_CB", "Pt2Line11_CB", "Pt2Line5_CB", "Pt3Line1_CB", "Pt2Line1_YN"]
    form.missing("Missing application-basis fields", application_basis_fields)
    category_detail_fields = i485_category_findings(
        form, concurrent_petition=form.plan_status("underlying_petition") == STATUS_NOT_APPLICABLE
    )
    if application_basis == "1fB":
        # The principal's A-Number is asked for "(if any)".
        form.missing("Derivative principal-information block is incomplete",
                     ["Pt2Line2_FamilyName", "Pt2Line2_GivenName", "Pt1Line2_DOB"])

    # Item 10 asks for the passport or travel document only "if you last entered the United
    # States using" one, and item 12 for the I-94 only "if you were issued" one. Both are
    # expected after an inspected admission or parole (item 11 A or B); after an entry without
    # inspection (C) or "Other" (D) they are required only once the preparer starts them.
    passport_fields = ["Pt1Line10_PassportNum", "Pt1Line10_ExpDate", "Pt1Line10_Passport"]
    i94_fields = ["P1Line12_I94", "Pt1Line12_Status", "Pt1Line12_Date"]
    inspected = last_arrival in {"11A", "11B"}
    arrival_fields = ["Pt1Line10_CityTown", "Pt1Line10_State", "Pt1Line10_DateofArrival", "Pt1Line15_Date",
                      "Pt1Line13_YN", "Pt1Line16_YN", "Pt1Line17_YN"]
    for group in (passport_fields, i94_fields):
        if inspected or form.filled(group):
            arrival_fields.extend(group)
    form.missing("Missing recent-arrival fields", arrival_fields)
    arrival_fields = sorted(set(arrival_fields) | set(passport_fields) | set(i94_fields))

    current_address_fields = ["Pt1Line18_StreetNumberName", "Pt1Line18_CityOrTown", "Pt1Line18_State",
                              "Pt1Line18_ZipCode"]
    form.missing("Missing current-address fields", current_address_fields)

    address_history_toggle_fields = ["Pt1Line18_Date", "Pt1Line18_YN", "Pt1Line18_last5yrs_YN"]
    form.missing("Missing address-history starter fields", address_history_toggle_fields)
    # Item 18's prior-address row is asked for when the applicant has not lived at the current
    # address for five years. It may be abroad: a state and ZIP Code exist only for a U.S. row,
    # and a province or postal code only where the country has one, so neither is required.
    if form.value("Pt1Line18_last5yrs_YN") == "N":
        prior_fields = ["Pt1Line18_PriorStreetName", "Pt1Line18_PriorCity"]
        if is_us_country(form.value("Pt1Line18_PriorCountry")):
            prior_fields += ["Pt1Line18_PriorState", "Pt1Line18_PriorZipCode"]
        prior_fields += ["Pt1Line18_PriorCountry", "Pt1Line18_PriorDateFrom", "Pt1Line18PriorDateTo"]
        form.missing("Five-year address history is incomplete", prior_fields)

    # The most recent address outside the United States where the applicant lived more than a
    # year is a question of its own, unrelated to the five-year answer: it is asked "if not
    # already listed", so it is required when its plan question isn't not_applicable (with no
    # plan, once the row is started). Province and postal code are "if any" abroad.
    outside_row = ["Pt1Line18_RecentStreetName", "Pt1Line18_RecentCity", "Pt1Line18_RecentCountry",
                   "Pt1Line18_RecentDateFrom", "Pt1Line18_RecentDateTo"]
    outside_status = form.plan_status("last_address_outside_us")
    outside_started = form.filled(
        outside_row + ["Pt1Line18_RecentProvince", "Pt1Line18_RecentPostalCode", "Pt1Line18_RecentState"]
    )
    if (outside_status and outside_status != STATUS_NOT_APPLICABLE) or (not outside_status and outside_started):
        form.missing("Most recent address outside the United States is incomplete", outside_row)
    if is_us_country(form.value("Pt1Line18_RecentCountry")):
        form.add("The address outside the United States (Part 1 item 18) gives the United States as its country",
                 ["Pt1Line18_RecentCountry"])

    form.missing("Social Security section is incomplete", ["Pt1Line19_YN", "Pt1Line19_SSA_YN", "Pt1Line19_Consent_YN"])

    # Part 10: the mobile number and email are asked for "(if any)".
    applicant_contact_fields = ["Pt3Line3_DaytimePhoneNumber1", "Pt3Line4_MobileNumber1", "Pt3Line5_Email"]
    form.missing("Applicant contact section is incomplete", ["Pt3Line3_DaytimePhoneNumber1"])
    if form.value("Pt1Line19_YN") == "Y":
        form.missing("Existing Social Security number is missing", ["Pt1Line19_SSN"])

    form.missing("Prior immigrant or adjustment history section is incomplete",
                 ["Pt4Line1_YN", "Pt4Line5_YN", "Pt4Line6_YN"])

    form.missing(
        "Missing attorney/preparer block",
        ["CheckBox1", "AttorneyStateBarNumber", "Pt12Line1_PreparerFamilyName", "Pt12Line1a_PreparerGivenName",
         "Pt12Line2_BusinessName", "Pt12Line3_PreparerDaytimePhoneNumber1", "Pt12Line5_PreparerEmail"],
    )

    form.missing(
        "Missing parent identity fields",
        ["Pt5Line1_FamilyName", "Pt5Line1_GivenName", "Pt5Line3_DateofBirth", "Pt5Line5_CityTownOfBirth",
         "Pt5Line6_FamilyName", "Pt5Line6_GivenName", "Pt5Line8_DateofBirth[0]", "Pt5Line10_CityTownOfBirth"],
    )

    form.layers(
        "Visible I-485 output does not reflect stored identity, basis, or arrival facts",
        identity_fields
        + application_basis_fields
        + category_detail_fields
        + arrival_fields
        + current_address_fields
        + address_history_toggle_fields
        + applicant_contact_fields
        + ["Pt1Line18_PriorStreetName", "Pt1Line18_RecentStreetName", "Pt1Line19_YN", "Pt1Line19_SSA_YN",
           "Pt1Line19_Consent_YN", "Pt1Line19_SSN", "Pt4Line1_YN", "Pt4Line5_YN", "Pt4Line6_YN", "Pt5Line3_DateofBirth",
           "Pt5Line5_CityTownOfBirth", "Pt5Line8_DateofBirth[0]", "Pt5Line10_CityTownOfBirth"],
    )

    current_row_fields = ["Pt4Line7_EmployerName[0]", "Pt4Line7_EmployerName[1]", "Pt4Line7_EmployerName[2]",
                          "Part4Line7_StreetName[0]", "P4Line7_City", "P4Line7_State", "P4Line7_ZipCode",
                          "P4Line7_Country", "Pt4Line7_DateFrom"]
    current_row_name_fields = [form.value(field) for field in current_row_fields[:3]]
    current_row_has_address = any(
        form.value(field)
        for field in (
            "Part4Line7_StreetName[0]",
            "P4Line7_City",
            "P4Line7_State",
            "P4Line7_ZipCode",
            "P4Line7_Country",
            "Pt4Line7_DateFrom",
        )
    )
    if not form.filled(current_row_fields):
        severity = "warning" if applicant_age is not None and applicant_age < 18 else "error"
        title = (
            "Current employment or school row is blank for a minor applicant"
            if severity == "warning"
            else "Current employment or school row is blank"
        )
        form.add(title, current_row_fields, severity=severity)
    elif current_row_has_address and sum(1 for value in current_row_name_fields if value) < 1:
        form.add(
            "Current employment or school row has an address but no employer or school name",
            ["Pt4Line7_EmployerName[0]", "Pt4Line7_EmployerName[1]", "Pt4Line7_EmployerName[2]",
             "Part4Line7_StreetName[0]"],
        )
    form.layers("Visible I-485 output does not reflect stored current employment or school fields", current_row_fields)

    outside_activity_fields = ["Pt4Line8_EmployerName", "Pt4Line8_Occupation", "P4Line8_StreetName", "P4Line8_City",
                               "P4Line8_PostalCode", "P4Line8_Country", "Pt4Line8_DateFrom", "Pt4Line8_DateTo"]
    # Item 8 asks for the most recent employment outside the United States "if not already
    # listed above", so it is blank for anyone who never worked or studied abroad or whose
    # entry is already in item 7. A row that has been started must be complete.
    outside_row_started = form.filled(outside_activity_fields)
    if outside_row_started and applicant_age is not None and applicant_age < 18:
        form.missing("Most recent outside-U.S. school or activity is incomplete",
                     ["Pt4Line8_Occupation", "Pt4Line8_DateFrom", "Pt4Line8_DateTo"])
    elif outside_row_started:
        form.missing(
            "Most recent outside-U.S. employer section is incomplete",
            ["Pt4Line8_EmployerName", "Pt4Line8_Occupation", "P4Line8_Country", "Pt4Line8_DateFrom", "Pt4Line8_DateTo"],
        )
    form.layers("Visible I-485 output does not reflect stored outside-U.S. activity fields", outside_activity_fields)

    form.missing("Marital-status or total-children fields are incomplete",
                 ["Pt5Line2_YNNA", "Pt6Line1_MaritalStatus", "Pt6Line3_TimesMarried", "Pt6Line1_TotalChildren"])

    current_spouse_name_fields = ["Pt6Line4_FamilyName", "Pt6Line4_GivenName", "Pt6Line4_MiddleName"]
    # The spouse's address and the place of marriage may be abroad: their state and ZIP Code are
    # asked for only when that row's country is the United States (a spouse abroad has neither,
    # and a marriage abroad may have no state or province).
    current_spouse_required_fields = ["Pt5Line8_DateofBirth[1]", "Pt6Line7_Country", "Part6Line8_StreetName",
                                      "P6Line8_City"]
    if is_us_country(form.value("P6Line8_Country")):
        current_spouse_required_fields += ["P6Line8_State", "P6Line8_ZipCode"]
    current_spouse_required_fields.append("P6Line8_Country")
    current_marriage_fact_fields = ["Pt6Line10_CityTownOfBirth[0]"]
    if is_us_country(form.value("Pt6Line10_Country[0]")):
        current_marriage_fact_fields.append("Pt6Line10_State[0]")
    current_marriage_fact_fields += ["Pt6Line10_Country[0]", "Pt5Line8_DateofBirth[2]", "Pt6Line11_YN"]
    current_spouse_all_fields = current_spouse_name_fields + ["Pt5Line8_DateofBirth[1]", "Pt6Line7_Country",
                                                              "Part6Line8_StreetName", "P6Line8_City", "P6Line8_State",
                                                              "P6Line8_ZipCode", "P6Line8_Country",
                                                              "Pt6Line10_CityTownOfBirth[0]", "Pt6Line10_State[0]",
                                                              "Pt6Line10_Country[0]", "Pt5Line8_DateofBirth[2]",
                                                              "Pt6Line11_YN"]
    # A count that contradicts the status. (Married with a count of None is reported below.)
    if marital_status == I485_NEVER_MARRIED and marriage_count:
        form.add("Marital status says never married, but the marriage count is not None",
                 ["Pt6Line1_MaritalStatus", "Pt6Line3_TimesMarried"], value=times_married)
    elif marital_status in I485_PREVIOUSLY_MARRIED and marriage_count == 0:
        form.add("Marital status says the applicant was married, but the marriage count is None",
                 ["Pt6Line1_MaritalStatus", "Pt6Line3_TimesMarried"], value=times_married)
    if currently_married or form.filled(current_spouse_name_fields):
        if not times_married:
            form.add("Marriage count is blank even though a current spouse is listed", ["Pt6Line3_TimesMarried"])
        elif marriage_count == 0:
            form.add("Marriage count is None even though a current spouse is listed", ["Pt6Line3_TimesMarried"],
                     value=times_married)
        form.missing("Current spouse section is incomplete", current_spouse_required_fields)
        form.missing("Current marriage date or place is missing", current_marriage_fact_fields)
        form.layers("Visible I-485 output does not reflect stored current spouse fields", current_spouse_all_fields)
    elif form.filled(current_spouse_all_fields):
        form.add("Current-spouse fields are populated even though marital status is not married",
                 current_spouse_all_fields)

    prior_spouse_fields = ["Pt6Line12_FamilyName", "Pt6Line12_GivenName", "Pt6Line12_MiddleName",
                           "Pt5Line8_DateofBirth[3]", "Pt6Line14_Country", "Pt6Line15_Country",
                           "Pt6Line16_DateofBirth[0]", "Pt6Line10_CityTownOfBirth[1]", "Pt6Line10_State[1]",
                           "Pt6Line10_Country[1]", "Pt6Line18_CityTownOfBirth", "Pt6Line18_State", "Pt6Line18_Country",
                           "Pt6Line16_DateofBirth[1]", "Pt6Line19_MaritalStatus", "Pt6Line19_HowMarriageEndedOther"]
    # Item 3 counts every marriage, the current one included, and takes a number or "None" (the
    # instructions' way to write zero). The prior marriages are that count less the current
    # marriage when there is one (married or legally separated): a divorced or widowed applicant
    # married once lists that spouse, and so does one married twice who is married now.
    if times_married and marriage_count is None:
        form.add("Marriage count is not a number or None", ["Pt6Line3_TimesMarried"], value=times_married,
                 fix="Type the number of marriages in digits, or None if never married.")
    prior_marriages = (
        max(marriage_count - (1 if currently_married else 0), 0) if marriage_count is not None else None
    )
    if not prior_marriages and form.filled(prior_spouse_fields):
        form.add("Prior-spouse section is populated even though the marriage count does not support it",
                 prior_spouse_fields)
    elif prior_marriages:
        prior_required = ["Pt6Line12_FamilyName", "Pt6Line12_GivenName", "Pt5Line8_DateofBirth[3]", "Pt6Line14_Country",
                          "Pt6Line15_Country", "Pt6Line16_DateofBirth[0]", "Pt6Line16_DateofBirth[1]",
                          "Pt6Line19_MaritalStatus"]
        # Item 16, where the prior marriage took place, and item 17, where it legally ended: city and
        # country, and the state when that country is the United States, as for the current marriage.
        for city, state, country in (
            ("Pt6Line10_CityTownOfBirth[1]", "Pt6Line10_State[1]", "Pt6Line10_Country[1]"),
            ("Pt6Line18_CityTownOfBirth", "Pt6Line18_State", "Pt6Line18_Country"),
        ):
            prior_required += [city, country] + ([state] if is_us_country(form.value(country)) else [])
        if form.value("Pt6Line19_MaritalStatus") == I485_MARRIAGE_ENDED_OTHER:
            prior_required.append("Pt6Line19_HowMarriageEndedOther")
        form.missing("Prior-spouse section is incomplete", prior_required)

    has_children = bool(child_count) and children != 0
    if has_children or form.filled(["Pt7Line2_FamilyName", "Pt7Line3_FamilyName"]):
        child_fields = ["Pt7Line2_YN", "Pt7Line3_YN", "Pt7Line2_FamilyName", "Pt7Line2_GivenName",
                        "Pt7Line2_DateofBirth", "Pt7Line2_Country", "Pt7Line2_Relationship"]
        if children is None or children >= 2:
            child_fields.extend(
                ["Pt7Line3_FamilyName", "Pt7Line3_GivenName", "Pt7Line3_DateofBirth", "Pt7Line3_Country",
                 "Pt7Line3_Relationship"]
            )
        form.missing("Children section is incomplete", child_fields)
        form.layers(
            "Visible I-485 output does not reflect stored children fields",
            ["Pt7Line2_YN", "Pt7Line3_YN", "Pt7Line2_FamilyName", "Pt7Line2_GivenName", "Pt7Line3_FamilyName",
             "Pt7Line3_GivenName"],
        )

    biographic_fields = ["Pt7Line1_Ethnicity", "Pt7Line3_HeightFeet", "Pt7Line3_HeightInches", "Pt7Line4_Weight2",
                         "Pt7Line4_Weight3", "Pt7Line5_Eyecolor", "Pt7Line6_Haircolor"]
    form.missing("Biographic section is incomplete", biographic_fields)
    # Race is five separate boxes; one or more may be checked. Each box is read by its own
    # index: a bare "Pt7Line2_Race" lookup reads only one of them.
    if not form.filled(I485_RACE_FIELDS):
        form.add("Biographic section is incomplete: no race box is checked", list(I485_RACE_FIELDS))
    form.layers("Visible I-485 output does not reflect stored biographic fields", biographic_fields + I485_RACE_FIELDS)

    public_charge_fields = ["Pt9Line56_CB"]
    form.missing("Public-charge section is incomplete", public_charge_fields)
    # Item 56: an exempt category, or "23", not exempt. Only an applicant who is not exempt
    # completes items 57-64; one in an exempt category goes straight to item 65.
    public_charge_category = form.value("Pt9Line56_CB")
    public_charge_factor_fields = ["Pt9Line57_HouseholdSize", "Pt9Line53_CB", "Pt9Line59_CB", "Pt9Line60_CB",
                                   "Pt9Line61_CB"]
    exempt = public_charge_category and public_charge_category != I485_NOT_EXEMPT
    if exempt and form.filled(public_charge_factor_fields):
        form.add(
            "Public-charge items 57-62 are answered, but item 56 selects an exempt category",
            [name for name in public_charge_factor_fields if form.value(name)],
            fix="An exempt applicant skips items 57-64 (the form says to go to item 65): clear them, or "
            "correct item 56.",
        )
    if public_charge_category == I485_NOT_EXEMPT:
        form.missing("Public-charge items 57-62 are incomplete for an applicant who is not exempt",
                     public_charge_factor_fields)
        if form.value("Pt9Line61_CB") == "C":
            form.missing("Current grade or diploma text is missing", ["Pt9Line61_diploma"])
    form.layers(
        "Visible I-485 output does not reflect stored public-charge fields",
        ["Pt9Line56_CB", "Pt9Line57_HouseholdSize", "Pt9Line53_CB", "Pt9Line59_CB", "Pt9Line60_CB", "Pt9Line61_CB",
         "Pt9Line61_diploma"],
    )

    form.missing("Organization-membership history toggle is incomplete", ["Pt8Line1_YesNo"])
    if form.value("Pt8Line1_YesNo") == "Y":
        form.missing(
            "First organization-membership row is incomplete",
            ["Pt9Line2_Organization1", "Pt9Line3_CityTownOfBirth", "Pt9Line3_Country", "Pt9Line4_FamilyName",
             "Pt9Line4_Involvement", "Pt9Line5_DateFrom", "Pt9Line5_DateTo"],
        )
        if form.filled(["Pt9Line6_Organization2", "Pt9Line7_CityTownOfBirth", "Pt9Line7_Country", "Pt9Line8_FamilyName",
                        "Pt9Line8_Involvement", "Pt9Line9_DateFrom", "Pt9Line9_DateTo"]):
            form.missing(
                "Second organization-membership row is incomplete",
                ["Pt9Line6_Organization2", "Pt9Line7_CityTownOfBirth", "Pt9Line7_Country", "Pt9Line8_FamilyName",
                 "Pt9Line8_Involvement", "Pt9Line9_DateFrom", "Pt9Line9_DateTo"],
            )
    form.layers("Visible I-485 output does not reflect stored organization-membership fields",
                ["Pt8Line1_YesNo", "Pt9Line2_Organization1", "Pt9Line6_Organization2"])

    form.missing("Routine inadmissibility defaults are incomplete", ["Pt8Line13_YesNo"])
    if form.value("Pt8Line22_YesNo") == "Y" or form.value("Pt9Line24_YesNo") == "Y":
        form.missing("Criminal-history disclosure addendum is incomplete",
                     ["Pt8Line22_YesNo", "Pt9Line24_YesNo", "P14_Line2_AdditionalInfo"])

    form.missing(
        "Signature fields are still blank",
        ["Pt3Line7a_Signature", "Pt3Line7b_DateofSignature", "P12Line6_SignaturePreparer", "P12Line6a_DateofSignature"],
        severity="warning",
    )


def audit_g28(form: Form) -> None:
    attorney_fields = ["Line1a_USCIS", "Line1b_ListFormNumber", "Pt2Line1a_LicensingAuthority", "Pt2Line1b_BarNumber",
                       "Pt1Line2a_FamilyName", "Pt1Line2b_GivenName", "Pt2Line1d_NameofFirmOrOrganization",
                       "Line3a_StreetNumber", "Line3c_CityOrTown", "Line3d_State", "Line3e_ZipCode", "Line3h_Country",
                       "Line4_DaytimeTelephoneNumber", "Line7_MobileTelephoneNumber"]
    form.missing("Missing attorney block", attorney_fields)
    client_fields = ["Pt3Line5a_FamilyName", "Pt3Line5b_GivenName", "Line9_DaytimeTelephoneNumber",
                     "Line10_MobileTelephoneNumber", "Line11_EMail", "Line12a_StreetNumberName", "Line12c_CityOrTown",
                     "Line12d_State", "Line12e_ZipCode", "Line12h_Country"]
    form.missing("Client contact block is incomplete", client_fields, severity="warning")
    form.layers("Visible G-28 output does not reflect stored attorney or client fields",
                attorney_fields + client_fields)
    form.missing("Signature fields are still blank",
                 ["Line1_Signature", "Line3_Date", "P5_Line6a_SignatureofApplicant", "Pt4Line2b_DateofSignature"],
                 severity="warning")


def audit_i130(form: Form) -> None:
    form.blank_output()
    relationship_fields = ["Pt1Line1_Spouse", "Pt1Line1_Parent", "Pt1Line1_Child", "Pt1Line1_Siblings"]
    if not form.filled(relationship_fields):
        form.add("Petition relationship basis is not selected", relationship_fields)
    petitioner_fields = [
        "Pt2Line4a_FamilyName",  # Part 2 item 4 legal name (Pt2Line5* is "Other Names Used")
        "Pt2Line4b_GivenName",
        "Pt2Line8_DateofBirth",
        "Pt2Line7_CountryofBirth",
        "Pt2Line10_StreetNumberName",
        "Pt2Line10_CityOrTown",
        "Pt2Line10_Country",
    ]
    # A state and ZIP Code exist only for a U.S. address; a petitioner living abroad has neither.
    if is_us_country(form.value("Pt2Line10_Country")):
        petitioner_fields[6:6] = ["Pt2Line10_State", "Pt2Line10_ZipCode"]
    beneficiary_fields = ["Pt4Line4a_FamilyName", "Pt4Line4b_GivenName", "Pt4Line9_DateOfBirth",
                          "Pt4Line8_CountryOfBirth", "Pt4Line11_CityOrTown", "Pt4Line11_Country"]
    # The form leaves 11.a-b blank for a home abroad with no street number or name.
    if is_us_country(form.value("Pt4Line11_Country")):
        beneficiary_fields.insert(4, "Pt4Line11_StreetNumberName")
    form.missing("Missing high-signal petitioner fields", petitioner_fields)
    form.missing("Missing high-signal beneficiary fields", beneficiary_fields)
    form.layers("Visible I-130 output does not reflect stored petitioner or beneficiary fields",
                relationship_fields + petitioner_fields + beneficiary_fields)
    form.missing(
        "Signature fields are still blank",
        ["P5_Line6a_SignatureofApplicant", "Pt6Line6b_DateofSignature", "Pt8Line8a_Signature",
         "Pt8Line8b_DateofSignature"],
        severity="warning",
    )


NOT_APPLICABLE_WORDS = {"n/a", "na", "none", "not applicable"}
NO_EMPLOYER_WORDS = {"unemployed", "retired"}


@dataclass(frozen=True)
class HistoryRow:
    """One address or employment row of a history table, by field name."""

    label: str
    street: str
    city: str
    country: str
    date_from: str
    date_to: str | None = None  # None: the current row, which runs to the present
    state: str | None = None
    zip_code: str | None = None
    unit: str | None = None
    unit_number: str | None = None
    employer: str | None = None
    occupation: str | None = None

    def fields(self) -> list[str]:
        names = [
            self.employer,
            self.occupation,
            self.street,
            self.unit,
            self.unit_number,
            self.city,
            self.state,
            self.zip_code,
            self.country,
            self.date_from,
            self.date_to,
        ]
        return [name for name in names if name]


def history_row_findings(form: Form, row: HistoryRow, *, required: bool) -> None:
    """A history row is either blank (when optional) or complete and internally coherent."""

    def get(name: str | None) -> str:
        return form.value(name) if name else ""

    employer = get(row.employer).casefold()
    content_fields = [name for name in row.fields() if name != row.unit]
    if employer in NOT_APPLICABLE_WORDS and not any(
        get(name) for name in content_fields if name != row.employer
    ):
        return  # the row is answered "N/A"
    if not any(get(name) for name in content_fields):
        if required:
            form.add(f"{row.label} is blank", content_fields)
        return

    needed = [row.date_from] + ([row.date_to] if row.date_to else [])
    if row.employer:
        needed.insert(0, row.employer)
    if employer not in NO_EMPLOYER_WORDS:
        if row.occupation:
            needed.append(row.occupation)
        needed.extend([row.street, row.city, row.country])
        if is_us_country(get(row.country)):
            needed.extend(name for name in (row.state, row.zip_code) if name)
    missing = [name for name in needed if not get(name)]
    if missing:
        form.add(f"{row.label} is incomplete", missing)

    if row.unit and row.unit_number and bool(get(row.unit)) != bool(get(row.unit_number)):
        form.add(f"{row.label}: apartment, suite or floor type and number do not match", [row.unit, row.unit_number])

    if row.date_to:
        start, end = parse_us_date(get(row.date_from)), parse_us_date(get(row.date_to))
        if start and end and start > end:
            form.add(f"{row.label} ends before it starts", [row.date_from, row.date_to])


def history_overlap_findings(form: Form, rows: list[HistoryRow]) -> None:
    """Rows are listed newest first; an older row should end before the newer one starts."""
    for newer, older in zip(rows, rows[1:]):
        if not older.date_to:
            continue
        starts = parse_us_date(form.value(newer.date_from))
        ended = parse_us_date(form.value(older.date_to))
        if starts and ended and ended > starts:
            form.add(f"{older.label} ends after {newer.label} starts", [older.date_to, newer.date_from],
                     severity="warning")


I130A_ADDRESS_ROWS = [
    HistoryRow(label="Physical address 1 (current, Part 1 items 4-5)", street="Pt1Line4a_StreetNumberName",
               unit="Pt1Line4b_Unit", unit_number="Pt1Line4b_AptSteFlrNumber", city="Pt1Line4c_CityOrTown",
               state="Pt1Line4d_State", zip_code="Pt1Line4e_ZipCode", country="Pt1Line4h_Country",
               date_from="Pt1Line5a_DateFrom"),
    HistoryRow(label="Physical address 2 (Part 1 items 6-7)", street="Pt1Line6a_StreetNumberName",
               unit="Pt1Line6b_Unit", unit_number="Pt1Line6b_AptSteFlrNumber", city="Pt1Line6c_CityOrTown",
               state="Pt1Line6d_State", zip_code="Pt1Line6e_ZipCode", country="Pt1Line6h_Country",
               date_from="Pt1Line7a_DateFrom", date_to="Pt1Line7b_DateTo"),
]
I130A_FOREIGN_ADDRESS_ROW = HistoryRow(label="Last address outside the United States (Part 1 items 8-9)",
                                       street="Pt1Line8a_StreetNumberName", unit="Pt1Line8b_Unit",
                                       unit_number="Pt1Line8b_AptSteFlrNumber", city="Pt1Line8c_CityOrTown",
                                       country="Pt1Line8f_Country", date_from="Pt1Line9a_DateFrom",
                                       date_to="Pt1Line9b_DateTo")
I130A_EMPLOYMENT_ROWS = [
    HistoryRow(label="Employer 1 (current, Part 2 items 1-4)", employer="Pt2Line1_EmployerOrCompName",
               street="Pt2Line2a_StreetNumberName", unit="Pt2Line2b_Unit", unit_number="Pt2Line2b_AptSteFlrNumber",
               city="Pt2Line2c_CityOrTown", state="Pt2Line2d_State", zip_code="Pt2Line2e_ZipCode",
               country="Pt2Line2h_Country", occupation="Pt2Line3_Occupation", date_from="Pt2Line4a_DateFrom"),
    HistoryRow(label="Employer 2 (Part 2 items 5-8)", employer="Pt2Line5_EmployerOrCompName",
               street="Pt2Line6_StreetNumberName", unit="Pt2Line6_Unit", unit_number="Pt2Line6_AptSteFlrNumber",
               city="Pt2Line6_CityOrTown", state="Pt2Line6_State", zip_code="Pt2Line6_ZipCode",
               country="Pt2Line6_Country", occupation="Pt2Line7_Occupation", date_from="Pt2Line8a_DateFrom",
               date_to="Pt2Line8b_DateTo"),
]
I130A_FOREIGN_EMPLOYMENT_ROW = HistoryRow(label="Last employment outside the United States (Part 3)",
                                          employer="Pt3Line1_EmployerOrCompName", street="Pt3Line2a_StreetNumberName",
                                          unit="Pt3Line2b_Unit", unit_number="Pt3Line2b_AptSteFlrNumber",
                                          city="Pt3Line2c_CityOrTown", state="Pt3Line2d_State",
                                          zip_code="Pt3Line2e_ZipCode", country="Pt3Line2h_Country",
                                          occupation="Pt3Line3_Occupation", date_from="Pt3Line4a_DateFrom",
                                          date_to="Pt3Line4b_DateTo")


def audit_i130a(form: Form) -> None:
    """I-130A (04/01/24 edition): Supplemental Information for Spouse Beneficiary."""
    form.blank_output()

    identity_fields = ["Pt1Line3a_FamilyName", "Pt1Line3b_GivenName"]
    form.missing("Missing high-signal identity fields", identity_fields)
    parent_groups = {
        "Parent 1 (Part 1 items 10-16) is missing name, birth or residence details": ["Pt1Line10_FamilyName",
                                                                                      "Pt1Line10_GivenName",
                                                                                      "Pt1Line11_DateofBirth",
                                                                                      "Pt1Line13_CountryofBirth",
                                                                                      "Pt1Line15_CountryofResidence"],
        "Parent 2 (Part 1 items 17-23) is missing name, birth or residence details": ["Pt1Line16_FamilyName",
                                                                                      "Pt1Line16_GivenName",
                                                                                      "Pt1Line17_DateofBirth",
                                                                                      "Pt1Line19_CountryofBirth",
                                                                                      "Pt1Line21_CountryofResidence"],
    }
    for title, fields in parent_groups.items():
        form.missing(title, fields)

    for position, row in enumerate(I130A_ADDRESS_ROWS):
        history_row_findings(form, row, required=position == 0)
    history_overlap_findings(form, I130A_ADDRESS_ROWS)
    history_row_findings(form, I130A_FOREIGN_ADDRESS_ROW, required=False)
    for position, row in enumerate(I130A_EMPLOYMENT_ROWS):
        history_row_findings(form, row, required=position == 0)
    history_row_findings(form, I130A_FOREIGN_EMPLOYMENT_ROW, required=False)

    contact_fields = ["Pt4Line3_DaytimePhoneNumber1"]
    form.missing("Spouse beneficiary daytime phone is missing", contact_fields)

    preparer_fields = ["Pt6Line1a_PreparerFamilyName", "Pt6Line1b_PreparerGivenName", "Pt6Line2_BusinessName",
                       "Pt6Line4_DaytimePhoneNumber", "Pt6Line6_Email"]
    form.missing("Missing attorney/preparer block", preparer_fields)
    if form.value("Pt6Line7b_Checkbox") == "Y" and not form.value("CheckBox1"):
        form.add(
            "Part 6 says the attorney's representation goes beyond preparing the form, "
            "but the page 1 attorney box does not say a G-28 is attached",
            ["Pt6Line7b_Checkbox", "CheckBox1"],
        )

    attorney_box_fields = ["CheckBox1", "AttorneyStateBarNumber", "USCISOnlineAcctNumber"]
    history_fields = [
        name
        for row in I130A_ADDRESS_ROWS
        + [I130A_FOREIGN_ADDRESS_ROW]
        + I130A_EMPLOYMENT_ROWS
        + [I130A_FOREIGN_EMPLOYMENT_ROW]
        for name in row.fields()
    ]
    form.layers(
        "Visible I-130A output does not reflect stored identity, history, or attorney fields",
        identity_fields
        + [name for fields in parent_groups.values() for name in fields]
        + history_fields
        + contact_fields
        + preparer_fields
        + attorney_box_fields
        + ["Pt6Line7_Checkbox", "Pt6Line7b_Checkbox"],
    )
    form.missing(
        "Signature fields are still blank",
        ["Pt4Line6a_Signature", "Pt4Line6b_DateofSignature", "Pt6Line8a_Signature", "Pt6Line8b_DateofSignature"],
        severity="warning",
    )


# Page 1 attorney box of forms that carry one, compared with the G-28 for the same
# person: "G-28 is attached", the attorney's bar number and USCIS online account
# number, and (optionally) the preparer named in the form's preparer part.
ATTORNEY_BOX_FIELDS: dict[str, dict[str, str]] = {
    "i-130a": {
        "g28_attached": "CheckBox1",
        "bar_number": "AttorneyStateBarNumber",
        "account_number": "USCISOnlineAcctNumber",
        "preparer_family": "Pt6Line1a_PreparerFamilyName",
        "preparer_given": "Pt6Line1b_PreparerGivenName",
        "preparer_is_attorney": "Pt6Line7_Checkbox",
        "attorney_state": "B",
    },
    # No attorney-statement box on the I-864, so the preparer-name comparison is skipped.
    "i-864": {
        "g28_attached": "G28-CheckBox1",
        "bar_number": "AttorneyStateBarNumber",
        "account_number": "USCISOnlineAcctNumber",
        "preparer_family": "P10_Line1a_PreparersFamilyName",
        "preparer_given": "P10_Line1b_PreparersGivenName",
        "preparer_is_attorney": "",
        "attorney_state": "none",
    },
}
G28_FIELDS = {
    "bar_number": "Pt2Line1b_BarNumber",
    "account_number": "Pt1Line1_USCISOnlineAcctNumber",
    "family": "Pt1Line2a_FamilyName",
    "given": "Pt1Line2b_GivenName",
}


def attorney_box_findings(form: Form) -> None:
    """The form's attorney box and preparer part agree with each other and with the G-28."""
    spec = ATTORNEY_BOX_FIELDS.get(form.kind)
    if spec is None:
        return
    attached, bar_number, account = (form.value(spec[key]) for key in ("g28_attached", "bar_number", "account_number"))
    if attached and not bar_number:
        form.add("Attorney box says a G-28 is attached but gives no bar number", [spec["bar_number"]])
    if bar_number and not attached:
        form.add("Attorney box gives a bar number but does not say a G-28 is attached",
                 [spec["g28_attached"], spec["bar_number"]])

    g28_entries = [entry for entry in form.intent_manifest.values() if str(entry.get("kind")) == "g-28"]
    subject = str((form.manifest_entry or {}).get("subject") or "").strip().casefold()
    same_person = [
        entry for entry in g28_entries if subject and str(entry.get("subject") or "").strip().casefold() == subject
    ]
    if not g28_entries:
        if attached and form.intent_manifest:
            form.add("Attorney box says a G-28 is attached, but the intent manifest has no G-28",
                     [spec["g28_attached"]], severity="warning")
        return
    if same_person and not attached:
        form.add("A G-28 is prepared for this person, but the attorney box does not say it is attached",
                 [spec["g28_attached"]])
    candidates = same_person or g28_entries

    def g28_value(key: str, entry: dict[str, object]) -> str:
        return str(dict(entry.get("expected_fields", {})).get(G28_FIELDS[key], "")).strip()

    for key, stored in (("bar_number", bar_number), ("account_number", account)):
        expected = {g28_value(key, entry) for entry in candidates} - {""}
        if stored and expected and stored not in expected:
            form.add(f"Attorney box {key.replace('_', ' ')} does not match the G-28", [spec[key]], stored=stored,
                     g28=sorted(expected))

    if form.value(spec["preparer_is_attorney"]) == spec["attorney_state"]:
        preparer = (form.value(spec["preparer_family"]).casefold(), form.value(spec["preparer_given"]).casefold())
        attorneys = {
            (g28_value("family", entry).casefold(), g28_value("given", entry).casefold()) for entry in candidates
        } - {("", "")}
        if all(preparer) and attorneys and preparer not in attorneys:
            form.add("Preparer says they are the attorney, but the name differs from the attorney on the G-28",
                     [spec["preparer_family"], spec["preparer_given"]])


# I-131 (01/20/25) Part 1 on-states of CB_AppType: advance parole is items 5.A-5.M ("5"-"17"). The
# last-admission items 12-14 are asked for items 4, 5 and 8-11 only ("4"-"17", "24"-"37").
I131_ADVANCE_PAROLE = {str(n) for n in range(5, 18)}
I131_ADMISSION_ITEMS = {"4"} | I131_ADVANCE_PAROLE | {str(n) for n in range(24, 38)}


def audit_i131(form: Form) -> None:
    app_type = form.value("CB_AppType")
    identity_fields = ["Part2_Line1_FamilyName", "Part2_Line1_GivenName", "Part2_Line6_CountryOfBirth",
                       "Part2_Line7_CountryOfCitizenshiporNationality", "Part2_Line9_DateOfBirth"]
    admission_fields = ["Part2_Line12_ClassofAdmission", "Part2_Line13_I94RecordNo", "Part2_Line14_I94ExpDate"]
    if app_type in I131_ADMISSION_ITEMS:
        identity_fields += admission_fields
    form.missing("Missing high-signal identity fields", identity_fields)
    address_fields = ["Part2_Line3_StreetNumberName", "Part2_Line3_CityTown", "Part2_Line3_Country"]
    if is_us_country(form.value("Part2_Line3_Country")):
        address_fields[2:2] = ["Part2_Line3_State", "Part2_Line3_ZipCode"]  # a parole applicant abroad has neither
    form.missing("Missing current-address fields", address_fields)
    preparer_fields = ["Part12_Line1_FamilyName", "Part12_Line1_GivenName", "Part12_Line2_NameofBusinessorOrgName",
                       "Part12_Line3_DayPhone", "Part12_Line5_Email"]
    form.missing("Missing attorney/preparer block", preparer_fields)
    form.layers("Visible I-131 output does not reflect stored identity or preparer fields",
                identity_fields + admission_fields + address_fields + preparer_fields)
    if app_type in I131_ADVANCE_PAROLE:
        trip_fields = ["P7_Line1_DateOfDeparture", "P7_Line2_Purpose", "P7_Line3_ListCountries", "P7_Line4_CB",
                       "P7_Line5_ExpectedLengthTrip"]
        if not any(form.values.get(field, "").strip() for field in trip_fields):
            form.add("Advance parole travel details are missing", trip_fields)
    form.missing(
        "Signature fields are still blank",
        ["Part10_Line4_ApplicantSignature", "Part10_Line4_DateofSignature", "Part12_Line6_PreparerSig",
         "Part12_Line6_DateofSignature"],
        severity="warning",
    )


def audit_i864(form: Form) -> None:
    form.blank_output()
    basis_fields = ["P1_Line1a-f_CB", "P1_Line1b_Relationship", "P1_Line1c_InterestIn", "P1_Line1c_Relationship",
                    "P1_Line1f_Relationship"]
    if not form.filled(basis_fields):
        form.add("Sponsorship basis is not completed", basis_fields)
    sponsor_fields = ["P4_Line1a_FamilyName", "P4_Line1b_GivenName", "P4_Line2b_StreetNumberName",
                      "P4_Line2e_CityOrTown", "P4_Line2f_State", "P4_Line2g_ZipCode", "P4_Line2j_Country",
                      "P4_Line5_CountryOfDomicile", "P4_Line6_DateOfBirth"]
    immigrant_fields = ["P2_Line1a_FamilyName", "P2_Line1b_GivenName", "P2_Line2_StreetNumberName",
                        "P2_Line2_CityOrTown", "P2_Line2_Country", "P2_Line4_DateOfBirth"]
    income_fields = ["P3_Line28_TotalNumberofImmigrants", "P5_Line7_SameResidence", "P6_Line15_TotalHouseholdIncome",
                     "P6_Line19a_TaxYear", "P6_Line19a_TotalIncome", "P6_Line19b_TaxYear", "P6_Line19b_TotalIncome",
                     "P6_Line19c_TaxYear", "P6_Line19c_TotalIncome"]
    form.missing("Missing high-signal sponsor fields", sponsor_fields)
    form.missing("Missing principal immigrant fields", immigrant_fields)
    form.missing("Household size or income support fields are incomplete", income_fields, severity="warning")
    form.layers("Visible I-864 output does not reflect stored sponsor, immigrant, or income fields",
                sponsor_fields + immigrant_fields + income_fields)
    i864_arithmetic_findings(form, petition_relationship=i130_relationship(form.intent_manifest, form.values))
    form.missing(
        "Signature fields are still blank",
        ["P8_Line9a_ApplicantSignature", "P7Line9b_DateofSignature", "P10_Line8a_PreparersSignature",
         "P10_Line8b_DateofSignature"],
        severity="warning",
    )


I864_HOUSEHOLD_PARTS = [
    ("P3_Line28_TotalNumberofImmigrants", "item 1, persons sponsored"),
    ("P5_Line2_Yourself", "item 2, yourself"),
    ("P5_Line3_Married", "item 3, spouse"),
    ("P5_Line4_DependentChildren", "item 4, dependent children"),
    ("P5_Line5_OtherDependents", "item 5, other dependents"),
    ("P5_Line6_Sponsors", "item 6, prior sponsored immigrants"),
    ("P5_Line7_SameResidence", "item 7, relatives with an I-864A"),
]
I864_HOUSEHOLD_TOTAL = "Override"  # Part 5 item 8, despite its name
I864_INCOME_PARTS = [
    ("P6_Line2_TotalIncome", "item 7, the sponsor's current income"),
    ("P6_Line5_CurrentIncome", "item 8"),
    ("P6_Line8_CurrentIncome", "item 9"),
    ("P6_Line11_CurrentIncome", "item 10"),
    ("P6_Line14_CurrentIncome", "item 11"),
]
I864_INCOME_TOTAL = "P6_Line15_TotalHouseholdIncome"  # Part 6 item 12


def parse_amount(text: str) -> float | None:
    """A count or dollar amount as typed in a box ("81200", "81,200.00", "$81,200"), or None."""
    cleaned = str(text or "").strip().replace("$", "").replace(",", "").replace(" ", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


SPOUSE_OR_CHILD = "spouse_or_child"
OTHER_RELATIVE = "other"


def i130_relationship(intent_manifest: dict[str, dict[str, object]], i864_values: dict[str, str]) -> str:
    """What the I-130 in this package petitions for, for the I-864's sponsor: "spouse_or_child",
    "other", or "" when the package has no I-130 that says (the I-864 itself doesn't ask).

    With more than one I-130, the one whose beneficiary is the I-864's principal immigrant counts;
    when none or several match, the answer is known only if every I-130 says the same."""

    def kind_of(entry: dict[str, object]) -> str:
        answers = dict(entry.get("expected_fields") or {})
        if any(str(answers.get(box) or "").strip() == "Y" for box in ("Pt1Line1_Spouse", "Pt1Line1_Child")):
            return SPOUSE_OR_CHILD
        if any(str(answers.get(box) or "").strip() == "Y" for box in ("Pt1Line1_Parent", "Pt1Line1_Siblings")):
            return OTHER_RELATIVE
        return ""

    petitions = [entry for entry in intent_manifest.values() if str(entry.get("kind") or "").lower() == "i-130"]
    if not petitions:
        return ""
    immigrant = tuple(field_value(i864_values, box).strip().casefold() for box in ("P2_Line1a_FamilyName", "P2_Line1b_GivenName"))
    matching = [
        entry for entry in petitions
        if all(immigrant)
        and tuple(str(dict(entry.get("expected_fields") or {}).get(box) or "").strip().casefold()
                  for box in ("Pt4Line4a_FamilyName", "Pt4Line4b_GivenName")) == immigrant
    ]
    kinds = {kind_of(entry) for entry in (matching if len(matching) == 1 else petitions)}
    return kinds.pop() if len(kinds) == 1 else ""


def i864_arithmetic_findings(form: Form, *, petition_relationship: str = "") -> None:
    """Part 5 item 8 is the sum of items 1-7; Part 6 item 12 is the sum of items 7-11; and the
    household income is compared with the I-864P poverty guideline for that household: 125%,
    or 100% for a sponsor on active duty who petitions for a spouse or child (uscis.gov/i-864p).
    The I-864 doesn't say whom the petition is for; `petition_relationship` comes from the
    package's I-130 (i130_relationship), and without one the 125% minimum stands, with a note."""
    import poverty_guidelines as guidelines

    total_text = form.value(I864_HOUSEHOLD_TOTAL)
    parts = {name: parse_amount(form.value(name)) for name, _label in I864_HOUSEHOLD_PARTS}
    household = parse_amount(total_text)
    if total_text and None not in parts.values():
        expected = sum(parts.values())  # type: ignore[arg-type]
        if household is None or abs(household - expected) > 0.001:
            form.add("Household size (Part 5 item 8) is not the sum of items 1-7",
                     [I864_HOUSEHOLD_TOTAL] + [name for name, _ in I864_HOUSEHOLD_PARTS], value=total_text,
                     sum_of_parts=int(expected) if expected == int(expected) else expected,
                     fix="Make item 8 the sum of items 1-7, or correct the item that is wrong.")

    income_text = form.value(I864_INCOME_TOTAL)
    income = parse_amount(income_text)
    sponsor_income = parse_amount(form.value(I864_INCOME_PARTS[0][0]))
    if income_text and sponsor_income is not None:
        expected = sum(parse_amount(form.value(name)) or 0.0 for name, _ in I864_INCOME_PARTS)
        if income is None or abs(income - expected) > 0.5:
            form.add(
                "Total household income (Part 6 item 12) is not the sum of items 7-11",
                [I864_INCOME_TOTAL] + [name for name, _ in I864_INCOME_PARTS],
                value=income_text,
                sum_of_parts=round(expected, 2),
                fix="Make item 12 the sum of the sponsor's income (item 7) and the household members' "
                "incomes (items 8-11); Adobe recalculates it from those boxes, so a different figure "
                "shows one way on the filing copy and another in Adobe.",
            )

    if income is not None and household is not None and household >= 1:
        active_duty = form.value("P4_Line14_Checkboxes") == "Y"
        petitioner = form.value("P1_Line1a-f_CB").upper() == "1A"
        percent = 100 if active_duty and petitioner and petition_relationship == SPOUSE_OR_CHILD else 125
        state = form.value("P4_Line4e_State") or form.value("P4_Line2f_State")
        size = int(household)
        minimum = guidelines.minimum_income(size, state=state, percent=percent)
        if income < minimum:
            region = {"AK": "Alaska", "HI": "Hawaii"}.get(guidelines.region_for(state), "the 48 contiguous states")
            note = ""
            if percent == 100:
                note = (
                    "100% applies only to an active-duty sponsor petitioning for a spouse or child; for anyone "
                    "else the minimum is 125%."
                )
            elif active_duty and petitioner and petition_relationship != OTHER_RELATIVE:
                lower = guidelines.minimum_income(size, state=state, percent=100)
                note = (
                    f"The sponsor is on active duty. If the petition is for the sponsor's spouse or child, the "
                    f"minimum is 100% (${lower:,}); no I-130 in this package says so, so 125% is used here."
                )
            form.add(
                f"Household income is below {percent}% of the poverty guideline for a household of {size}",
                [I864_INCOME_TOTAL, I864_HOUSEHOLD_TOTAL],
                severity="warning",
                household_income=income,
                household_size=size,
                minimum=minimum,
                guideline=f"Form I-864P, {percent}% for {region}, effective {guidelines.EFFECTIVE:%m/%d/%Y} "
                f"({guidelines.SOURCE})",
                open_item_type="attorney_decision",
                suggested_question="Add a joint sponsor, or rely on the sponsor's assets, to meet the I-864 income "
                "requirement?",
                detail=f"The current household income of ${income:,.0f} is below the ${minimum:,} the guideline asks "
                f"for a household of {size}. The sponsor can make up the difference with a joint sponsor's I-864, a "
                "household member's I-864A, or assets (Part 7): generally five times the shortfall, three times for "
                "the spouse or child of a U.S. citizen.",
                **({"note": note} if note else {}),
            )
        if guidelines.is_stale():
            form.add("The bundled I-864P poverty guidelines may be out of date", severity="warning",
                     guideline=f"effective {guidelines.EFFECTIVE:%m/%d/%Y}; check {guidelines.SOURCE}")


def audit_i129f(form: Form) -> None:
    """I-129F (01/20/25): the classification and the answers that follow from it, the yes/no
    questions and their follow-up rows, the consulate, and U.S. rows' state and ZIP Code."""
    form.blank_output()
    form.missing(
        "Petitioner or beneficiary identity is incomplete",
        ["Pt1Line4a_Checkboxes", "Pt1Line6a_FamilyName", "Pt1Line6b_GivenName", "Pt1Line22_DateofBirth",
                "Pt1Line40_Checkbox", "Pt2Line1a_FamilyName", "Pt2Line1b_GivenName", "Pt2Line4_DateOfBirth",
                "Pt2Line8_CountryOfBirth", "Pt2Line9_CountryofCitzOrNationality"],
    )
    form.missing(
        "Yes/no questions of Parts 1-3 are not answered",
        ["Pt1Line8j_Checkboxes", "Pt1Line37_Checkboxes", "Pt1Line20_Checkboxes", "Pt1Line43_Checkboxes",
                "Pt1Line48_Checkboxes", "Pt2Line34_Checkboxes", "Pt2Line37_Checkboxes", "Pt2Line39_Checkboxes",
                "Pt2Line51_Checkboxes", "Pt2Line53_Checkboxes", "Pt2Line55_Checkboxes", "Pt3Line1_Checkboxes",
                "P3Line2a_Checkboxes", "P3Line2b_Checkboxes", "P3Line2c_Checkboxes", "Part3Line4a_Checkboxes",
                "Pt3Line5_Checkboxes"],
    )
    form.missing("U.S. Embassy or Consulate (Part 2 items 62.a-62.b) is missing",
                 ["Pt2Line62a_CityTown", "Pt2Line62b_Country"])
    classification = form.value("Pt1Line4a_Checkboxes")
    spouse_answers = {"Pt2Line51_Checkboxes": form.value("Pt2Line51_Checkboxes"),
                      "Pt2Line53_Checkboxes": form.value("Pt2Line53_Checkboxes")}
    if classification == "B":  # K-3 spouse
        form.missing("K-3 petition does not say whether an I-130 was filed (Part 1 item 5)", ["Pt1Line5_Checkboxes"])
        # Instructions, Part 1 items 4.a-5 and evidence item 9.A: a K-3 petition is for a spouse for
        # whom the petitioner has filed (or files with it) an I-130, with evidence of that filing.
        if form.value("Pt1Line5_Checkboxes") == "N":
            form.add(
                "K-3 petition says no I-130 was filed (Part 1 item 5); a K-3 needs one filed for the spouse",
                ["Pt1Line5_Checkboxes"],
                fix="File the I-130 first or with this petition (its receipt, or the I-130 itself, is the evidence) "
                       "and answer Yes; without one, the K-3 classification isn't available.",
            )
        # Instructions, Part 3 items 5.a-5.d: "If you are filing for your spouse, waivers are not
        # required. Select the box for Item Number 5.d."
        waiver = form.value("Pt3Line5_Checkboxes")
        if waiver and waiver != "D":
            form.add("A K-3 spouse petition asks for a multiple-filer waiver (Part 3 item 5); it takes 5.d",
                     ["Pt3Line5_Checkboxes"], value=waiver,
                     fix="Select 5.d (not applicable: the beneficiary is my spouse).")
    # Who may file: a K-1 petitioner and fiance(e) are legally free to marry; a K-3 is for a spouse.
    marital = {"petitioner (Part 1 item 23)": "Pt1Line23_Checkbox", "beneficiary (Part 2 item 6)": "Pt2Line6_Checkboxes"}
    for who, box in marital.items():
        status = form.value(box)
        if not status or classification not in {"A", "B"}:
            continue
        if classification == "A" and status == "M":
            form.add(
                f"K-1 petition, but the {who} is married; both must be free to marry",
                [box, "Pt1Line4a_Checkboxes"],
                fix="A married petitioner and beneficiary file for K-3 (with an I-130) instead; check the "
                       "marital status against the divorce, annulment or death record.",
            )
        if classification == "B" and status != "M":
            form.add(f"K-3 spouse petition, but the {who} is not shown as married", [box, "Pt1Line4a_Checkboxes"])
    wrong_na = [box for box, answer in spouse_answers.items()
                if answer and ((answer == "A") != (classification == "B"))]
    if classification and wrong_na:
        form.add("Part 2 items 51 and 53 must be N/A for a K-3 spouse, and only then", wrong_na,
                 classification="K-3 spouse" if classification == "B" else "K-1 fiance(e)")
    involved = form.conditional(
        [
            ("Pt1Line37_Checkboxes", "Y", "Petitioner's previous spouse is not described",
             ["Pt1Line38a_FamilyName", "Pt1Line38b_GivenName", "Pt1Line39_DateMarriageEnded"]),
            ("Pt1Line20_Checkboxes", "Y", "Certificate of naturalization or citizenship details are incomplete",
             ["Pt1Line21a_CertificateNumber", "Pt1Line21b_PlaceofIssuance", "Pt1Line21c_DateOfIssuance"]),
            ("Pt1Line43_Checkboxes", "Y", "Earlier I-129F filing is not described",
             ["Pt1Line45a_FamilyName", "Pt1Line45b_GivenName", "Pt1Line46_DateOfFiling", "Pt1Line47_Result"]),
            ("Pt1Line48_Checkboxes", "Y", "Ages of the petitioner's children under 18 are missing", ["Pt1Line49a_Age"]),
            ("Pt2Line34_Checkboxes", "Y", "Beneficiary's previous spouse is not described",
             ["Pt2Line35a_FamilyName", "Pt2Line35b_GivenName", "Pt2Line36_DateMarriageEnded"]),
            ("Pt2Line39_Checkboxes", "Y", "Beneficiary's child is not described",
             ["Pt2Line40a_FamilyName", "Pt2Line40b_GivenName", "Pt2Line41_CountryOfBirth", "Pt2Line42_DateofBirth",
              "Pt2Line43_Checkboxes"]),
            ("Pt2Line51_Checkboxes", "Y", "Nature and degree of the relationship (Part 2 item 52) is missing",
             ["Pt2Line52_Relationship"]),
            ("Pt2Line55_Checkboxes", "Y", "International marriage broker details are incomplete",
             ["Pt2Line58_IMBOrgName", "Pt2Line60a_StreetNumberName", "Pt2Line60_CityOrTown", "Pt2Line60_Country"]),
            ("Part3Line4a_Checkboxes", "Y", "Other arrests or convictions (Part 3 item 4.b) are not described",
             ["Pt3Line4B_Describe"]),
        ],
    )
    if form.value("Pt2Line53_Checkboxes") in {"Y", "N"}:
        form.missing("The in-person meeting (or the reasons for a waiver) is not described in Part 2 item 54",
                     ["Pt2Line54_Describe"])
    rows = [
        ("Petitioner's mailing address (Part 1 item 8)", "Pt1Line8"), ("Petitioner's address 1 (Part 1 item 9)", "Pt1Line9"),
        ("Petitioner's address 2 (Part 1 item 11)", "Pt1Line11"), ("Petitioner's employer 1 (Part 1 item 14)", "Pt1Line14"),
        ("Petitioner's employer 2 (Part 1 item 18)", "Pt1Line18"), ("Beneficiary's mailing address (Part 2 item 11)", "Pt2Line11"),
        ("Beneficiary's address 1 (Part 2 item 12)", "Pt2Line12"), ("Beneficiary's address 2 (Part 2 item 14)", "Pt2Line14"),
        ("Beneficiary's employer 1 (Part 2 item 17)", "Pt2Line17"), ("Beneficiary's employer 2 (Part 2 item 21)", "Pt2Line21"),
        ("Beneficiary's child's address (Part 2 item 44)", "Pt2Line44"),
    ]
    for label, prefix in rows:
        boxes = [f"{prefix}_StreetNumberName", f"{prefix}_CityOrTown", f"{prefix}_State", f"{prefix}_ZipCode", f"{prefix}_Country"]
        involved += boxes
        if not form.filled(boxes):
            continue
        missing = form.address_missing(*boxes)
        if missing:
            form.add(f"{label} is incomplete", missing)
    form.layers("Visible I-129F output does not reflect stored answers",
                involved + ["Pt1Line4a_Checkboxes", "Pt1Line6a_FamilyName", "Pt2Line1a_FamilyName"])
    form.missing("Signature fields are still blank", ["Pt6Line4_Signature", "Pt5Line4_DateOfSignature"],
                 severity="warning")


# Part 7's persons: (family name box, item "applying for adjustment", item "applying for a visa
# abroad"); persons 2-6 share box names by index (schemas/i140.py PERSONS).
I140_PERSONS = [("Line1a_Person1FamilyName", 5, 6)] + [
    (f"Line2a_Person2FamilyName[{index}]", adjust, adjust + 1) for index, adjust in enumerate((11, 17, 23, 29, 35))
]
I140_SELF_PETITION_CATEGORIES = {"a", "h"}  # extraordinary ability; national interest waiver


def audit_i140(form: Form) -> None:
    """I-140 (06/07/24): who petitions, the category, processing, the yes/no pairs, the proposed
    employment, Part 7's rows, and U.S. rows' state and ZIP Code."""
    form.blank_output()
    company = form.value("Line2_CompanyName")
    if not company and not form.filled(["Pt1Line1a_FamilyName", "Pt1Line1b_GivenName"]):
        form.add("Petitioner's name or company name is missing",
                 ["Line2_CompanyName", "Pt1Line1a_FamilyName", "Pt1Line1b_GivenName"])
    if company:
        form.missing(
            "A company petitioner's EIN or business details are missing",
            ["Pt1Line3_TaxNumber", "Line2a_TypeofBusiness", "Line2b_DateEstablished", "Line2c_NumberofEmployees"],
        )
    elif form.filled(["Pt1Line1a_FamilyName", "Pt1Line1b_GivenName"]):
        form.missing("An individual petitioner's occupation (Part 5 item 11) is missing", ["Line3a_Occupation"])
    # uscis.gov/i-140 filing tips (updated 07/24/2026): USCIS rejects an I-140 without an answer to Part 1
    # items 5 and 6, which set the Asylum Program Fee, and "Self-petitioners should select No" to item 5
    # and "Yes" to item 6 (the reduced fee, $300 for a self-petitioner on G-1055).
    form.missing(
        "Part 1 items 5 and 6 (nonprofit or governmental research; 25 or fewer employees) are not "
              "answered",
        ["P1_Line5_Checkbox", "P1_Line6_Checkbox"],
    )
    form.missing(
        "Petition type or beneficiary identity is missing",
        ["prt2PetitionType", "Pt3Line1a_FamilyName", "Pt3Line1b_GivenName", "Line5_DateOfBirth",
                "Line8_Country", "Line9_Country", "Line1b_Country"],
    )
    if form.value("Line2_Petition") == "A":
        form.missing("Receipt number of the petition being amended is missing", ["Line2a_ReceiptNumber"])
    route = form.one_of("Part 4 item 1.a or 2.a (visa abroad or adjustment)", ["Line1a_Visa", "Line1b_Status"])
    if route == "Line1a_Visa":
        form.missing("U.S. Embassy or Consulate for the visa (Part 4 items 1.b-1.c) is missing",
                     ["Line1a_CityorTown", "Line1a_Country"])
    labor_elsewhere = form.value("Line7_Yes") == "Y"
    pairs = [
        ("Part 4 item 6.a (other petitions filed with it)", "Line4_Yes", "Line4_No", True),
        ("Part 4 item 7 (removal proceedings)", "Line5_Yes", "Line5_No", True),
        ("Part 4 item 8 (earlier immigrant petitions)", "Line6_Yes", "Line6_No", True),
        ("Part 4 item 9 (labor certification with another I-140)", "Line7_Yes", "Line7_No", True),
        # Item 10 follows a Yes to item 9 ("If you answered Yes ... are you requesting a duplicate?").
        ("Part 4 item 10 (duplicate labor certification)", "Line8_Yes", "Line8_No", labor_elsewhere),
        ("Part 6 item 4 (full-time)", "Line4_Yes1", "Line4_No1", True),
        ("Part 6 item 6 (permanent)", "Line6_Yes1", "Line6_No1", True),
        ("Part 6 item 7 (new position)", "Line7_Yes1", "Line7_No1", True),
    ]
    # Part 7: each spouse or child listed says whether they will adjust here and whether they will
    # apply for a visa abroad, each one yes/no pair (I140_PERSONS: family name box, the two items).
    for number, (family, adjust, visa) in enumerate(I140_PERSONS, start=1):
        listed = bool(form.value(family))
        for item, what in ((adjust, "applying for adjustment"), (visa, "applying for a visa abroad")):
            pairs.append((f"Part 7 person {number} item {item} ({what})", f"Pt7ItemNumber{item}_CheckboxYes",
                          f"Pt7ItemNumber{item}_CheckboxNo", listed))
    for label, yes, no, required in pairs:
        form.one_of(label, [yes, no], required=required)
    if form.value("Line4_Yes") == "Y" and not form.filled(["Line4_Form485", "Line4_Form131", "Line4_Form765", "Line4_OtherAttach"]):
        form.add("Part 4 item 6.b does not say which forms are filed with the I-140",
                 ["Line4_Form485", "Line4_Form131", "Line4_Form765", "Line4_OtherAttach"])
    if form.value("Line4_No1") == "N":
        form.missing("Hours per week for a part-time position (Part 6 item 5) are missing", ["Line5_Hours"])
    petitioner = form.one_of("Part 5 item 1 (type of petitioner)", ["Line1a_Employer", "Line1b_Self", "Line1c_Other"])
    if petitioner == "Line1c_Other":
        form.missing("Other type of petitioner is not explained", ["Line1c_Explain"])
    if petitioner == "Line1b_Self":
        answers = tuple(form.value(box) for box in ("P1_Line5_Checkbox", "P1_Line6_Checkbox"))
        if all(answers) and answers != ("N", "Y"):
            form.add(
                "A self-petitioner answers No to Part 1 item 5 and Yes to item 6",
                ["P1_Line5_Checkbox", "P1_Line6_Checkbox"],
                value="/".join(answers),
                fix="USCIS's I-140 filing tips tell self-petitioners to select No to item 5 and Yes to "
                       "item 6; the answers set the Asylum Program Fee ($300 for a self-petitioner).",
            )
        # A self-petition is the beneficiary's own: Part 1 names the same person as Part 3.
        names = [" ".join(field_value(form.values, box).split()).casefold() for box in
                 ("Pt1Line1a_FamilyName", "Pt1Line1b_GivenName", "Pt3Line1a_FamilyName", "Pt3Line1b_GivenName")]
        petitioner_name, beneficiary_name = names[:2], names[2:]
        if company:
            form.add(
                "A self-petition names a company as the petitioner",
                ["Line1b_Self", "Line2_CompanyName"],
                value=company,
                fix="A self-petitioner files for themselves: Part 1 gives their own name (items 1.a-1.c), "
                       "not a company's. If a company files, check Employer in Part 5 item 1.",
            )
        elif all(petitioner_name) and all(beneficiary_name) and petitioner_name != beneficiary_name:
            form.add(
                "A self-petition's petitioner (Part 1) and beneficiary (Part 3) are different people",
                ["Line1b_Self", "Pt1Line1a_FamilyName", "Pt1Line1b_GivenName",
                           "Pt3Line1a_FamilyName", "Pt3Line1b_GivenName"],
            )
    # Instructions, "IRS Tax or Social Security Numbers": only extraordinary ability (Part 2 item
    # 1.a) and the NIW (1.h) may be filed without a U.S. employer's permanent job offer, so only
    # they may be self-petitions; every other category is filed by the employer, who "must have and
    # provide an IRS Employer Identification Number or a Social Security Number in Part 1" (or USCIS
    # rejects the petition).
    category = form.value("prt2PetitionType").lower()
    if petitioner == "Line1b_Self" and category and category not in I140_SELF_PETITION_CATEGORIES:
        form.add("Self-petition in a category that needs a U.S. employer (only 1.a and 1.h may self-petition)",
                 ["Line1b_Self", "prt2PetitionType"], value=category)
    needs_employer = petitioner == "Line1a_Employer" or (category and category not in I140_SELF_PETITION_CATEGORIES)
    if needs_employer and not company and not form.filled(["Pt1Line3_TaxNumber", "Line7_SSN"]):
        form.add(
            "An individual employer's EIN or SSN (Part 1 item 4 or 7) is missing",
            ["Pt1Line3_TaxNumber", "Line7_SSN"],
            fix="Give the employer's EIN or, for an individual employer without one, the SSN; USCIS "
                   "rejects an employer's I-140 without either.",
        )
    form.missing(
        "Proposed employment (Part 6) is incomplete",
        ["Line1_JobTitle", "Line2_SOCCode1", "Line2_SOCCode2", "Line3_JobDescription", "Line8_Wages", "Line8_Per"],
    )
    rows = [
        ("Petitioner's mailing address (Part 1 item 3)", ["Line6b_StreetNumberName", "Line6d_CityOrTown", "Line6e_State",
                                                          "Line6f_ZipCode", "Line6i_Country"]),
        ("Beneficiary's mailing address (Part 3 item 2)", ["Line2b_StreetNumberName", "Line2d_CityOrTown", "Line2e_State",
                                                           "Line2f_ZipCode", "Line2i_Country"]),
    ]
    for label, boxes in rows:
        missing = form.address_missing(*boxes) if form.filled(boxes) else boxes[:2] + boxes[4:]
        if missing:
            form.add(f"{label} is incomplete", missing)
    form.missing("Signature fields are still blank", ["Line1a_SignatureofPetitioner", "Part7_Item8b_Date"],
                 severity="warning")


# I-601 Part 4: one checkbox per ground, p4Line<N>CB (on-state Y), in three sections by the benefit
# sought. The form: "Only select the applicable grounds listed under the immigration benefit you are
# seeking."
I601_GROUND_SECTIONS = {
    "A (immigrant visa, adjustment other than T or SIJ, K or V)": range(1, 19),
    "B (T or SIJ adjustment)": range(19, 20),
    "C (TPS)": range(20, 40),
}
# Section A grounds whose waiver rests on a family relationship (instructions, Reasons for
# Inadmissibility): 1, communicable disease (212(g)(1)); 11, totalitarian party (212(a)(3)(D)(iv));
# 12, fraud or misrepresentation (212(i)); 15, unlawful presence (212(a)(9)(B)(v)). Part 5 names the
# relative, or a VAWA self-petitioner checks its Part 5 box. (For the criminal grounds, 212(h), a
# relative is only one of four routes.)
I601_RELATIVE_GROUNDS = (1, 11, 12, 15)
# Of those, 12 and 15 are waived on extreme hardship, which Part 5 item 9 explains.
I601_HARDSHIP_GROUNDS = (12, 15)


def audit_i601(form: Form) -> None:
    """I-601 (01/20/25): identity and addresses, the Part 1 yes/no items and their follow-ups, at
    least one ground and all in one section of Part 4 with the item 40 statement, the relative and
    hardship statement a relative-based ground needs, the discretion statement, and started rows."""
    form.blank_output()
    form.missing(
        "Applicant's name, sex, date or place of birth, or citizenship is missing (Part 1 items 3, 9-14)",
        ["p1Line3aFamilyName", "p1Line3bGivenName", "p1Line9Gender", "p1Line10DateofBirth",
                "p1Line11CityOrTownOfBirth", "p1Line13CountryOfBirth", "p1Line14CountryOfCitzOrNat"],
    )
    same = form.value("p1Line6YesNo")
    if not same:
        form.add("Part 1 item 6 (is the physical address the mailing address?) is not answered", ["p1Line6YesNo"])
    rows = [
        ("Mailing address (Part 1 items 5.a-5.i)", ["p1Line5StreetNumberName", "p1Line5CityOrTown", "p1Line5State",
                                                    "p1Line5ZipCode", "p1Line5Country"], True),
        # "If you answered "No" to Item Number 6., provide your physical address in Item Numbers 7.a. - 7.h."
        ("Physical address (Part 1 items 7.a-7.h)", ["p1Line7StreetNumberName", "p1Line7CityTown", "p1Line7State",
                                                     "p1Line7ZipCode", "p1Line7Country"], same == "N"),
    ]
    for label, boxes, required in rows:
        missing = form.address_missing(*boxes) if required else []
        if missing:
            form.add(f"{label} is incomplete", missing)
    # Items 16.a-19 are asked of everyone; 16.b (the I-485 receipt) and 18.c-18.d follow a Yes (17.b and
    # 18.b are "if any").
    for item, box, follow_up, title in (
        ("16.a (an I-485 already filed)", "p1Line16aYesNo", ["p1Line16bReceiptNumber"],
         "Part 1 item 16.a is Yes, but the I-485 receipt number (item 16.b) is missing"),
        ("17.a (an I-821 already filed)", "p1Line17aYesNo", [], ""),
        ("18.a (an I-212 filed before)", "p1Line18aYesNo", ["p1Line18cFilingLocation", "p1Line18dDateFiled"],
         "Part 1 item 18.a is Yes, but where or when the I-212 was filed (items 18.c-18.d) is missing"),
        ("19 (an I-212 filed with this application)", "p1Line19YesNo", [], ""),
    ):
        answer = form.value(box)
        if not answer:
            form.add(f"Part 1 item {item} is not answered", [box])
        elif answer == "Y" and follow_up:
            form.missing(title, follow_up)
    for label, boxes in (
        ("Most recent U.S. entry (Part 2 items 1.a-1.d)", ["p2Line1aDateEntered", "p2Line1bImmigrationStatus",
                                                           "p2Line1cLocation", "p1Line1dCityOrTown"]),
        ("Earlier U.S. stay (Part 2 items 2.a-2.e)", ["p2Line2aDateEntered", "p2Line2bDepartureDate",
                                                      "p2Line2cImmigrationStatus", "p2Line2dLocation", "p2Line2eCityOrTown"]),
    ):
        if form.filled(boxes):
            form.missing(f"{label} is incomplete", boxes)

    checked = {item for item in range(1, 40) if form.checked(f"p4Line{item}CB")}
    if not checked:
        form.add("No ground of inadmissibility is selected in Part 4 (items 1-39)",
                 [f"p4Line{item}CB" for item in range(1, 40)])
    sections = [name for name, items in I601_GROUND_SECTIONS.items() if checked & set(items)]
    if len(sections) > 1:
        form.add("Part 4 selects grounds in more than one section (" + "; ".join(sections) + ")",
                 [f"p4Line{item}CB" for item in sorted(checked)],
                 fix="Select grounds only in the section for the benefit sought (A, B or C), as the form says.")
    for item, text in ((18, "p4Line18OtherSpecify"), (19, "p4Line19OtherSpecify"), (39, "p4Line39OtherSpecify")):
        if item in checked:
            form.missing(f"Part 4 item {item} is checked but does not say which ground", [text])
    if checked:
        form.missing(
            "Part 4 item 40, the statement of the acts, convictions or medical conditions and their "
            "dates, is blank",
            ["p4Line40Explanation"],
        )

    def items_text(items: list[int]) -> str:
        return ("item " if len(items) == 1 else "items ") + ", ".join(str(item) for item in items)

    relative_grounds = sorted(checked & set(I601_RELATIVE_GROUNDS))
    relative_name = ["p5Line1aFamilyName", "p5Line1bGivenName"]
    vawa = form.checked("p5VAWACB")
    if relative_grounds and not vawa and not form.filled(relative_name):
        form.add(
            f"Part 5 names no qualifying relative for Part 4 {items_text(relative_grounds)}",
            relative_name + ["p5VAWACB"],
            fix="Name the U.S. citizen or permanent resident relative (or K petitioner) the waiver rests "
                   "on in Part 5 items 1.a-8, or check the VAWA self-petitioner box.",
        )
    hardship_grounds = sorted(checked & set(I601_HARDSHIP_GROUNDS))
    if hardship_grounds:
        form.missing(f"Part 5 item 9 has no extreme hardship statement for Part 4 {items_text(hardship_grounds)}",
                     ["p5Line9ApplicantStatement"])
    # "In all cases, you must show that the approval of your application is warranted as a matter of
    # discretion ... In Part 6., Item Number 9., include a statement" (What Evidence Must You Submit).
    form.missing("The discretion statement (Part 6 item 9) is blank", ["p6Line9ApplicantStatement"])
    # A relative named in Part 5 or 6 needs the address, relationship, status and date of birth the
    # instructions ask for (the A-Number, phone and email are "if any").
    for label, name, address, other in (
        ("Qualifying relative (Part 5 items 1.a-8)", relative_name,
         ["p5Line2StreetNumberName", "p5Line2CityOrTown", "p5Line2State", "p5Line2ZipCode", "p5Line2Country"],
         ["p5Line5Relationship", "p5Line6ImmigrationStatus", "p5Line8DateofBirth"]),
        ("Other relative (Part 6 items 1.a-8)", ["p6Line1aFamilyName", "Pt6Line1b_GivenName"],
         ["p6Line2StreetNumberName", "p6Line2CityOrTown", "p6Line2State", "p6Line2ZipCode", "p6Line2Country"],
         ["p6Line5Relationship", "p6Line6ImmigrationStatus", "p6Line8DateofBirth"]),
    ):
        if not form.filled(name + address + other):
            continue
        missing = [box for box in name + other if not form.value(box)]
        missing += form.address_missing(*address)
        if missing:
            form.add(f"{label} is incomplete", missing)
    form.missing("Signature fields are still blank", ["Pt7Line6a_SignatureofApplicant", "p7Line6DateofSignature"],
                 severity="warning")


# I-601A (01/20/25). Part 3 item 1.a-1.e and Part 4 items 2.a-2.d and 5.a-5.d are separate boxes of
# which exactly one is checked; every yes/no question is one global group (Y or N). From Part 1 item
# 31 on, each yes/no box is named one below its item (Pt1Checkbox30_Checkbox is item 31,
# Pt1Checkbox31_Checkbox item 32 ... Pt1Checkbox44_Checkbox item 45; schemas/i601a.py).
I601A_BASIS = [f"Pt3Line4_Option{n}" for n in range(1, 6)]
I601A_RELATIVE = [f"Pt4Line2{letter}_Checkbox" for letter in "abcd"]
I601A_OTHER_RELATIVE = [f"Pt4Line5{letter}_Checkbox" for letter in "abcd"]
I601A_HISTORY = [f"Pt1Checkbox{item}_Checkbox" for item in
                 ("31", "32", "33", "34", "35", "36", "37", "38a", "38b", "38c", "38d", "38e", "39a", "39b", "40", "41", "42",
                  "43", "44")]  # Part 1 items 32-45
I601A_PART9_TEXT = [f"Pt9Line{n}d_AdditionalInfo" for n in range(3, 8)]
I601A_RACE = [f"Pt2Checkbox2_{n}" for n in range(1, 6)]
I601A_MINIMUM_AGE = 17  # Who May File, item 2; Processing Information: rejected under 17


def audit_i601a(form: Form) -> None:
    """I-601A (01/20/25): what the instructions reject it for (no full name, U.S. physical address
    or date of birth, under 17, no approved petition or DV case, unsigned), what makes the applicant
    ineligible on the face of the form (removal proceedings not administratively closed, a final
    order without an approved I-212, a final reinstatement decision, unexpired voluntary
    departure), the qualifying relative, and the Part 5 statement."""

    form.blank_output()
    # Processing Information: USCIS rejects an I-601A without the full name, a U.S. physical
    # address or the date of birth, or from an applicant under 17.
    form.missing("Applicant's full name or date of birth (Part 1 items 4.a-4.b and 11) is missing",
                 ["Pt1Line4a_FamilyName", "Pt1Line4b_GivenName", "Pt1Line11_DateOfBirth"])
    age = age_from_dob(form.value("Pt1Line11_DateOfBirth"))
    if age is not None and age < I601A_MINIMUM_AGE:
        form.add("The applicant is under 17 (Part 1 item 11); USCIS rejects an I-601A filed before 17",
                 ["Pt1Line11_DateOfBirth"], age=age)
    form.missing("Applicant's sex, place of birth or citizenship (Part 1 items 10 and 12-14) is missing",
                 ["Pt1Line10_Sex", "Pt1Line12_CityOrTownOfBirth", "Pt1Line13_CountryOfBirth",
                  "Pt1Line14_CountryOfCitizenship"])
    form.missing("U.S. mailing address (Part 1 items 7.b and 7.d-7.f) is incomplete",
                 ["Pt1Line7b_StreetNumberName", "Pt1Line7d_CityOrTown", "Pt1Line7e_State", "Pt1Line7f_ZipCode"])
    same_address = form.value("Pt1Line8_Checkbox")
    if not same_address:
        form.add("Part 1 item 8 (is the physical address the same as the mailing address) is not answered",
                 ["Pt1Line8_Checkbox"])
    elif same_address == "N":
        form.missing("U.S. physical address (Part 1 items 9.a-9.e) is missing",
                     ["Pt1Line9a_StreetNumberName", "Pt1Line9c_CityOrTown", "Pt1Line9d_State", "Pt1Line9e_ZipCode"])
    form.missing("Last entry into the United States (Part 1 items 17, 18.a and 19) is incomplete",
                 ["Pt1Line17_DateOfEntry", "Pt1Line18a_PlaceOfEntry", "Pt1Line19_ImmigrationStatus"])

    # Immigration proceedings, Part 1 items 27-31 ("Who is NOT Eligible", items 3-6).
    form.missing("Immigration history questions (Part 1 items 26, 27, 29.a, 30.a and 31) are not answered",
                 ["Pt1Checkbox25_Checkbox", "Pt1Checkbox27", "Pt1Checkbox29a_Checkbox", "Pt1Checkbox30a_Checkbox",
                  "Pt1Checkbox30_Checkbox"])
    form.conditional(
        [
            ("Pt1Checkbox27", "Y", "Part 1 item 28.a or 28.b (are the removal proceedings administratively closed) is not "
             "selected", ["Pt1Checkbox28"]),
            ("Pt1Checkbox30a_Checkbox", "Y", "Part 1 item 30.b (a final reinstatement decision) is not answered",
             ["Pt1Checkbox30b_Checkbox"]),
        ],
    )
    if form.value("Pt1Checkbox28") == "B":
        form.add("Part 1 item 28.b: removal proceedings that are not administratively closed (or are back on EOIR's "
                 "calendar) make the applicant ineligible", ["Pt1Checkbox28"])
    final_order = form.value("Pt1Checkbox29a_Checkbox")
    i212_receipt = form.value("Pt1Line29b_ReceiptNumber")
    if final_order == "Y" and not i212_receipt:
        form.add(
            "A final order (Part 1 item 29.a) without an approved I-212: its receipt number "
                     "(item 29.b) is missing",
            ["Pt1Line29b_ReceiptNumber"],
            severity="warning",
            fix="Give the approved I-212's receipt number in item 29.b or attach its approval notice; "
                   "without an approved I-212 a final order makes the applicant ineligible.",
        )
    elif final_order == "N" and i212_receipt:
        form.add("Follow-up answers are given although the question before them is not answered Yes",
                 ["Pt1Line29b_ReceiptNumber"], question_box="Pt1Checkbox29a_Checkbox", answer=final_order)
    if form.value("Pt1Checkbox30b_Checkbox") == "Y":
        form.add("Part 1 item 30.b: a final decision reinstating a prior order makes the applicant ineligible",
                 ["Pt1Checkbox30b_Checkbox"])
    if form.value("Pt1Checkbox30_Checkbox") == "Y":
        # The instructions list it among the ineligible; 8 CFR 212.7(e)(4) (eCFR, checked 2026-10-30) doesn't.
        form.add(
            "Part 1 item 31: an unexpired grant of voluntary departure, which the instructions "
                     "list as making the applicant ineligible",
            ["Pt1Checkbox30_Checkbox"],
            severity="warning",
            fix="The current regulation, 8 CFR 212.7(e)(4), has no voluntary departure bar: whether to "
                   "file is the attorney's decision (an attorney_decision open item).",
        )

    # Criminal, security and human rights history (items 32-45): each "Yes" is explained in Part 9,
    # as is a "Yes" to item 26 (the other previous entries).
    form.missing("Criminal, security and human rights questions (Part 1 items 32-45) are not answered", I601A_HISTORY)
    explained = [box for box in ["Pt1Checkbox25_Checkbox", *I601A_HISTORY] if form.value(box) == "Y"]
    if explained and not form.filled(I601A_PART9_TEXT):
        form.add("The Part 9 explanation of a 'Yes' to Part 1 item 26 or items 32-45 is missing",
                 [*explained, *I601A_PART9_TEXT])

    form.missing("Biographic information (Part 2 items 1 and 3-6) is incomplete",
                 ["Pt2Checkbox1", "Pt2Line3_HeightFeet", "Pt2Line3_HeightInches", "Pt2Line4_HeightInches1",
                  "Pt2Line4_HeightInches2", "Pt2Line4_HeightInches3", "Pt2Checkbox5", "Pt2Checkbox6"])
    if not any(form.checked(box) for box in I601A_RACE):
        form.add("Race (Part 2 item 2) is not selected", I601A_RACE)

    # Part 3: an approved I-130, I-140 or I-360 with its DOS case, or a DV selection (Who May File,
    # item 3; rejected without either).
    basis = form.one_of("Part 3 item 1 (the basis for the immigrant visa, 1.a-1.e)", I601A_BASIS)
    if basis == "Pt3Line4_Option1":
        form.missing("The DV case number (Part 3 item 2.a) is missing", ["Pt3Line6a_DV_KCCCaseNumber"])
    elif basis:
        form.missing("The approved petition's receipt number or the NVC case number (Part 3 items 3.a-3.b) is missing",
                     ["Pt3Line3a_USCISReceiptNumber", "Pt3Line3b_CSC_NVCCaseNumber"])
        petitioner = ["Pt3Line2a_FamilyName[1]", "Pt3Line2b_GivenName[1]", "Pt3Line3_CompanyOrOrgName"]
        if not form.filled([petitioner[0], petitioner[2]]):
            form.add("The petitioner's name or company (Part 3 items 3.c-3.f) is missing", petitioner)

    # Part 4: extreme hardship must be to a U.S. citizen or LPR spouse or parent.
    form.missing("Qualifying relative's name (Part 4 items 1.a-1.b) is missing",
                 ["Pt4Line1a_FamilyName", "Pt4Line1b_GivenName"])
    form.one_of("Part 4 item 2 (U.S. citizen or LPR spouse or parent)", I601A_RELATIVE)
    more = form.value("Pt4Line3_Checkbox")
    if not more:
        form.add("Part 4 item 3 (more than one qualifying relative) is not answered", ["Pt4Line3_Checkbox"])
    form.conditional(
        [
            ("Pt4Line3_Checkbox", "Y", "The other qualifying relative's name (Part 4 items 4.a-4.b) is missing",
             ["Pt4Line4a_FamilyName", "Pt4Line4b_GivenName"]),
        ],
    )
    if more == "Y":
        form.one_of("Part 4 item 5 (the other relative is a U.S. citizen or LPR spouse or parent)",
                    I601A_OTHER_RELATIVE)
    form.missing("Statement from applicant (Part 5: extreme hardship and discretion) is missing",
                 ["Pt5Line1_ApplicantStatement"])

    # Part 6: who read the application, the interpreter and preparer it names, and the phone.
    reads = form.value("Pt6Checkbox1")
    if not reads:
        form.add("Part 6 item 1.a or 1.b (reads English, or an interpreter read it) is not selected", ["Pt6Checkbox1"])
    elif reads == "B":
        form.missing("The interpreter or language (Part 6 item 1.b, Part 7) is missing",
                     ["Pt6Line1b_NameofLanguage", "Pt7Line1a_InterpreterFamilyName", "Pt7Line1b_InterpreterGivenName",
                      "Pt7Line6_NameOfLanguage"])
    if form.value("Pt6Checkbox2") == "C":
        form.missing("The preparer (Part 6 item 2, Part 8 items 1.a-1.b and 7) is missing",
                     ["Pt6Line2_Name", "Pt8Line1a_PreparerFamilyName", "Pt8Line1b_PreparerGivenName",
                      "Pt8Line7_Checkbox"])
    form.missing("Applicant's daytime telephone number (Part 6 item 3) is missing", ["Pt6Line3_DaytimeTelephoneNumber"])
    form.missing("Signature fields are still blank", ["Pt6Line6a_SignatureofApplicant", "Pt6Line6b_DateofSignature"],
                 severity="warning")


def audit_i612(form: Form) -> None:
    """I-612 (04/01/24): identity, why 212(e) applies, the ground, and the relative the hardship
    ground rests on."""
    form.blank_output()
    form.missing(
        "Applicant identity or exchange program details are missing",
        ["Pt1Line2a_FamilyName", "Pt1Line2b_FirstName", "P1_L8_DateOfBirth", "P1_L10_CountryOfBirth",
                "P1_L11_CountryOfCitizenshipNationality", "Part1_Line8_MaritalStatus", "P4_L1_AddInfo",
                "P4_L2_Checkboxes", "P4_L4_DateOfBirth"],
    )
    reasons = ["Part2_Checkboxes[1]", "Part2_Checkboxes[0]", "Part2_Checkboxes[2]", "Part2_Checkboxes[3]"]
    if not form.filled(reasons):
        form.add("Part 2 does not say why the foreign residence requirement applies", reasons)
    if form.value("Part2_Checkboxes[0]") == "B":
        form.missing("The agency or country that gave the grant (Part 2 item 2.b) is missing",
                     ["Part2_Line9b_PlaceOfEntry"])
    ground = form.value("Part3_Line1_Checkboxes")
    if not ground:
        form.add("Waiver ground (Part 3 item 1 or 2) is not selected", ["Part3_Line1_Checkboxes"])
    if ground == "Departure" and not form.filled(["P4_L27a_FamilyName", "P4_L31a_FamilyName"]):
        form.add("The hardship ground names no U.S. citizen or permanent resident spouse or child (Part 4 items 8-22)",
                 ["P4_L27a_FamilyName", "P4_L27b_FirstName", "P4_L31a_FamilyName", "P4_L31b_GivenName"])
    if form.value("Part1_Line8_MaritalStatus") == "M":
        form.missing("A married applicant does not say whether the spouse is included (Part 4 item 7)",
                     ["P3_L4a_Checkboxes"])
    if form.value("Part4_Line9_Checkboxes") == "B":
        form.missing("Naturalization details of the U.S. citizen relative (Part 4 items 10-12) are incomplete",
                     ["P4_L29a_NatCertNumber", "P4_L29b_DateOfNat", "P1_L12_CityTown", "P1_L12_State"])
    form.missing("Signature fields are still blank", ["P5_Line6a_SignatureofApplicant", "Part8_Line3b_DateofSignature"],
                 severity="warning")


# I-907 (04/01/24). The forms designated for premium processing (instructions, page 5): the I-129 and
# I-140 are petitions, requested by the petitioner or its attorney (Part 1 item 8.A or 8.B); the I-539
# and I-765 are applications (8.C or 8.D).
I907_PETITIONS = ("I-129", "I-140")
I907_APPLICATIONS = ("I-539", "I-765")
I907_REQUESTORS = {"A": "the petitioner", "B": "the petitioner's attorney", "C": "the applicant",
                   "D": "the applicant's attorney"}
# The I-140 classifications on page 5; E21 is designated twice, NIW (45 days) and non-NIW (15 days).
I907_I140_CLASSES = re.compile(r"\b(E1[123]|E21|E3[12]|EW3)\b")
I907_RECEIPT = re.compile(r"^[A-Z]{3}\d{10}$")
I907_RELATED_PETITIONER = ["Part2_Line4_PetitionerApplicantFamilyName", "Part2_Line4_PetitionerApplicantGivenName"]
I907_RELATED_BENEFICIARY = ["Line_FamilyName", "Line_GivenName"]


def audit_i907(form: Form) -> None:
    """I-907 (04/01/24): who requests it and for which form, the related case's details USCIS matches it
    by (all of Part 2 to upgrade a pending case), the names a request without a company must give, the
    requestor's statement and contact, and the signature."""
    form.blank_output()
    rows = [("Requestor's mailing address (Part 1 item 5)", "Part1_Line5_MailingAddress_")]
    form.missing("Part 1 item 6 (is the mailing address the physical address) is not answered", ["Part1Line6_Checkbox"])
    if form.value("Part1Line6_Checkbox") == "N":
        rows.append(("Physical address (Part 1 item 7), needed with 'No' to item 6", "Part1_Line7_PhysicalAddress_"))
    requestor = form.value("Part1_Line8_CheckBox").upper()
    if not requestor:
        form.add("Part 1 item 8 (who is requesting premium processing) is not selected", ["Part1_Line8_CheckBox"])
    # Part 2 items 1 and 3 go with every request; item 2 only once the related case has a receipt
    # number (instructions, page 3: filed together, "you will not know the receipt number").
    raw_form = form.value("P2_Line1_FormNumberof").upper()
    match = re.search(r"\b([GIN])[-\s]?(\d{2,4}[A-Z]?)\b", raw_form)
    case_form = f"{match.group(1)}-{match.group(2)}" if match else ""
    form.missing("The related case's form number or classification (Part 2 items 1 and 3) is missing",
                 ["P2_Line1_FormNumberof", "P2_Line2_ClassorEligRequested"])
    if raw_form and case_form not in (*I907_PETITIONS, *I907_APPLICATIONS):
        form.add(
            "Part 2 item 1 names a form premium processing isn't designated for (the I-129, I-140, "
                     "I-539 and I-765 are)",
            ["P2_Line1_FormNumberof"],
            value=raw_form,
        )
    petition, application = case_form in I907_PETITIONS, case_form in I907_APPLICATIONS
    if (petition and requestor in ("C", "D")) or (application and requestor in ("A", "B")):
        right = "8.A (the petitioner) or 8.B (its attorney)" if petition else "8.C (the applicant) or 8.D (their attorney)"
        form.add(
            f"Part 1 item 8 says {I907_REQUESTORS[requestor]} requests it, but the {case_form} is "
                     f"{'a petition' if petition else 'an application'}",
            ["Part1_Line8_CheckBox", "P2_Line1_FormNumberof"],
            fix=f"Check {right}.",
        )
    classification = form.value("P2_Line2_ClassorEligRequested").upper()
    if case_form == "I-140" and classification:
        codes = I907_I140_CLASSES.findall(classification)
        if not codes:
            form.add(
                "Part 2 item 3 gives no I-140 classification code (E11, E12, E13, E21 NIW or "
                         "non-NIW, E31, E32, EW3)",
                ["P2_Line2_ClassorEligRequested"],
                severity="warning",
                value=classification,
            )
        elif "E21" in codes and "NIW" not in classification:
            form.add(
                "Part 2 item 3 says E21 without NIW or non-NIW, which premium processing "
                         "designates separately (45 or 15 days)",
                ["P2_Line2_ClassorEligRequested"],
                severity="warning",
                value=classification,
            )
    receipt = re.sub(r"[\s-]", "", field_value(form.values, "P2_Line2_ReceiptNumberof")).upper()
    if receipt and not I907_RECEIPT.match(receipt):
        form.add("Receipt number of the related case (Part 2 item 2) isn't 3 letters and 10 digits",
                 ["P2_Line2_ReceiptNumberof"], value=receipt)
    # The people named in the related case: items 4-5 for a petition, item 4 for an application
    # (instructions, page 3). uscis.gov/i-907 (filing tips, checked 2026-10-30): for an I-129, I-140 or
    # I-765 with Part 1 item 4 (company) blank, Part 1 item 3 and those items must be filled, and "Entering
    # 'N/A' or 'none' is not an acceptable response"; USCIS rejects the form and returns the fee.
    company = form.value("Part1_Line4_CompanyorOrganizationName")
    related = I907_RELATED_PETITIONER + (I907_RELATED_BENEFICIARY if petition else [])
    items = "Part 2 items 4-5" if petition else "Part 2 item 4"
    if not company and (petition or case_form == "I-765"):
        bad = [box for box in ["Pt1Line3_FamilyName", "Pt1Line3_GivenName", *related]
               if form.value(box).lower() in NOT_APPLICABLE_WORDS | {""}]
        if bad:
            form.add(
                f"Without a company (Part 1 item 4), Part 1 item 3 and {items} need names, not "
                         "blanks, N/A or none",
                bad,
                fix="Give the requestor's name and the names in the related case; USCIS rejects the "
                       "I-907 and returns the fee otherwise.",
            )
    elif petition or application:
        form.missing(f"The names in the related case ({items}) are missing", related)
    # The beneficiary of a petition may not file the I-907 (instructions, page 5; G-1055). A
    # self-petitioner is the petitioner, so Part 1 item 3 names the same person as item 4.
    if petition and requestor == "A" and not company:
        names = [" ".join(field_value(form.values, box).split()).casefold() for box in
                 ["Pt1Line3_FamilyName", "Pt1Line3_GivenName", *I907_RELATED_PETITIONER, *I907_RELATED_BENEFICIARY]]
        requestor_name, petitioner_name, beneficiary_name = names[:2], names[2:4], names[4:]
        if all(requestor_name) and all(petitioner_name) and requestor_name != petitioner_name:
            beneficiary = requestor_name == beneficiary_name
            form.add(
                "The beneficiary of the petition is requesting premium processing, which only the "
                         "petitioner or its attorney may" if beneficiary else
                         "Part 1 item 8.A says the petitioner requests it, but Part 1 item 3 names someone "
                         "other than the petitioner (Part 2 item 4)",
                ["Pt1Line3_FamilyName", "Pt1Line3_GivenName", *I907_RELATED_PETITIONER],
            )
    # To upgrade a pending case, all of Part 2 (instructions, page 3).
    if receipt and (petition or application):
        rows.append(("To upgrade a pending case, the address in the related case (Part 2 item 8)",
                     "Part1_Line7_OtherInformationAboutCompanyOrg_"))
        if company:
            form.missing(
                "To upgrade a pending case, the company's point of contact (Part 2 item 6) is missing",
                ["Part1_Line8_NameOfCompanyPOC_FamilyName", "Part1_Line8_NameOfCompanyPOC_GivenName",
                        "Part1_Line8_NameOfCompanyPOC_TitleofPOC"],
            )
    for label, prefix in rows:
        missing = form.address_missing(f"{prefix}StreetNumberName", f"{prefix}CityTown", f"{prefix}State",
                                      f"{prefix}ZipCode", f"{prefix}Country")
        if missing:
            form.add(f"{label} is incomplete", missing)
    # An attorney who requests it files a G-28 unless one is already in the case (instructions, page 1).
    if requestor in ("B", "D") and not form.value("FormG28Attach"):
        form.add("Part 1 item 8 says an attorney requests it, but the G-28 box on page 1 isn't checked",
                 ["FormG28Attach", "Part1_Line8_CheckBox"], severity="warning",
                 fix="File a G-28 with the I-907, and check the box, unless one is already filed in the case.")
    statement = form.value("P3_Line1_Checkbox")
    if not statement:
        form.add("Part 3 item 1 (reads English, 1.A, or an interpreter read it, 1.B) is not selected",
                 ["P3_Line1_Checkbox"])
    elif statement == "N":
        form.missing(
            "With Part 3 item 1.B, the language or the interpreter (Part 4) is missing",
            ["P3_Line1_B_Language", "P4_Line1_InterpreterFamilyName", "P4_Line1_InterpreterGivenName",
                    "P4_Line6_Language"],
        )
    if form.value("P3_Line2_Checkbox") == "A":
        form.missing("With Part 3 item 2, the preparer's name or Part 5 is missing",
                     ["P3_Line2_NameofRepresentative", "P5_Line1_PreparerFamilyName", "P5_Line1_PreparerGivenName"])
    form.missing("Requestor's daytime telephone number (Part 3 item 3) is missing", ["P3_Line4_DaytimeTelePhoneNumber"])
    if form.filled(["P5_Line1_PreparerFamilyName", "P5_Line1_PreparerGivenName"]):
        lawyer = form.one_of("Part 5 item 7 (7.A not an attorney, 7.B an attorney)",
                             ["P5_Line7a_Checkbox", "P5_Line7b_Checkbox"])
        if lawyer == "P5_Line7b_Checkbox":
            form.one_of("Part 5 item 7.B (extends or does not extend beyond this request)",
                        ["P5_Line7b_extends", "P5_Line7b_notextends"])
    # Without a handwritten signature USCIS returns the request and the fee (instructions, page 2).
    form.missing("Signature fields are still blank", ["Pt5Line3_SignatureOfPetitioner", "P3_DateofSignature"],
                 severity="warning")


def audit_i864a(form: Form) -> None:
    """I-864A (08/24/26): the member, the relationship, one employment status, the income, the
    first intending immigrant, the opening names, and the asset total."""
    form.blank_output()
    form.missing(
        "Household member, relationship or income is missing",
        ["P1_Line1a_FamilyName", "P1_Line1b_GivenName", "P1_Line5_DateOfBirth", "P2_Line1-3_Checkbox",
                "P3_Line2_CurrentIncome", "P4_Line1_CB", "P5_Line1a_FamilyName", "P5_Line1b_GivenName",
                "P5_SponsorName", "Part9_Iamfluent[0]"],
    )
    if form.value("P2_Line1-3_Checkbox") == "C":
        form.missing("How the household member is related to the sponsor (Part 2 item 3) is missing",
                     ["P2_Line3_A_Relationship"])
    statuses = ["P3_Line1_Employment", "P3_Line4_Employment", "P3_Line5_Employment", "P3_Line6_Employment"]
    if not form.filled(statuses):
        form.add(
            "Part 3 does not say whether the household member is employed, self-employed, retired "
            "or unemployed",
            statuses,
        )
    parts = [parse_amount(form.value(name)) for name in ("P4_Line3_Assets", "P4_Line4_Assets", "P4_Line5_Assets")]
    total = parse_amount(form.value("P4_Line6_TotalAssets"))
    if total is not None and any(part is not None for part in parts) and abs(sum(p or 0 for p in parts) - total) > 0.5:
        form.add("Total assets (Part 4 item 6) is not the sum of items 3-5",
                 ["P4_Line6_TotalAssets", "P4_Line3_Assets", "P4_Line4_Assets", "P4_Line5_Assets"])
    form.missing("Signature fields are still blank",
                 ["Pt2Line6_ApplicantSignature[0]", "Pt2Line6_ApplicantSignature[1]"], severity="warning")


def audit_i693(form: Form) -> None:
    """I-693 (01/20/25), the applicant's side: Part 1 is complete, and nothing is typed into the
    civil surgeon's parts or the applicant's signature (signed in the civil surgeon's presence)."""
    form.blank_output()
    form.missing(
        "Applicant's information (Part 1) is incomplete",
        ["Pt1Line1a_FamilyName", "Pt1Line1b_GivenName", "Pt1Line2_StreetNumberName[0]",
                "P1Line2_CityOrTown", "P1Line2_Country", "Pt1Line3_Gender", "Pt1Line3_DateOfBirth",
                "Pt1Line3_CityTownVillageofBirth", "Pt1Line3_CountryofBirth"],
    )
    schema = get_question_schema("i693_applicant_part") or {}
    surgeon = list(dict(schema.get("required_questions", {})).get("civil_surgeon_parts", {}).get("required_fields", []))
    surgeon += ["Pt2Line6_ApplicantSignature", "Pt2Line6_DateofSignature"]
    typed = sorted({
        key for key, value in form.values.items()
        if field_base_and_index(key)[0] in surgeon and str(value).strip() not in UNCHECKED
    })
    if typed:
        form.add(
            "Boxes for the civil surgeon or the applicant's signature hold values typed by the firm",
            typed[:20],
            fix="Clear them: the civil surgeon completes Parts 5-10, and the applicant signs and dates "
            "Part 2 in the civil surgeon's presence.",
        )


def audit_g1145(form: Form) -> None:
    """G-1145: the name of the applicant or petitioner, and an email or a mobile number to notify."""
    form.blank_output()
    form.missing("Applicant or petitioner name is missing", ["LastName", "FirstName"])
    if not form.filled(["Email", "MobilePhoneNumber"]):
        form.add("E-notification contact is missing: give an email or a mobile number", ["Email", "MobilePhoneNumber"])
    mobile = form.value("MobilePhoneNumber")
    if mobile and not mobile.isdigit():
        form.add("Mobile number has characters other than digits; the form asks for digits only", ["MobilePhoneNumber"],
                 value=mobile)


# The payment forms: what the card or account holder writes by hand (forms_workflow.PAYMENT_BY_HAND).
# Never typed by the tools; a plan or a fill that holds one is refused before anything is written.
PAYMENT_NAME = {"g-1450": ["GivenName", "FamilyName"], "g-1650": ["GivenName[0]", "FamilyName[0]"]}


def audit_payment_form(form: Form) -> None:
    """G-1450 and G-1650: the applicant's name and a whole-dollar amount are prepared; card and bank
    details never are (the payer writes them and signs), so any value in those boxes is an error."""
    entry = form.manifest_entry or {}
    form.blank_output()
    form.missing("Applicant's name or the payment amount is missing",
                 PAYMENT_NAME[form.kind] + ["AuthorizedPaymentAmt"])
    amount = form.value("AuthorizedPaymentAmt")
    fee = entry.get("pays_amount")
    if amount and isinstance(fee, (int, float)) and amount.replace(",", "") != str(int(fee)):
        form.add(
            "Payment amount is not the fee this payment form pays",
            ["AuthorizedPaymentAmt"],
            value=amount,
            fee=f"{entry.get('pays_for', '')} {entry.get('pays_what', '')}: ${int(fee):,}".strip(),
            fix="USCIS takes the exact fee: make the amount the fee from the fees tool, or rerun setup with "
            "--payments for the current fees.",
        )
    if amount and not re.fullmatch(r"\d{1,3}(,\d{3})*|\d+", amount):
        form.add("Payment amount is not in whole dollars (no $, no cents)", ["AuthorizedPaymentAmt"], value=amount)
    typed = [name for name in PAYMENT_BY_HAND[form.kind] if form.checked(name)]
    if typed:
        form.add("Card or bank details are typed into the payment form; the payer writes them by hand", typed,
                 fix="Clear these boxes (the plan and the PDF). The payer fills them in and signs.")
    form.missing("Signature fields are still blank", ["SignatureOfApplicant"], severity="warning")


N400_TRIP_ROWS = [
    (f"P8_Line1_DateLeft{n}", f"P8_Line1_DateReturn{n}", "P9_Line1_Countries1" if n == 1 else f"P8_Line1_Countries{n}")
    for n in range(1, 7)
]
# Part 1 item 1 basis -> (years of permanent residence required, months of physical presence required).
N400_RESIDENCE = {"A": (5, 30), "B": (3, 18), "C": (3, 18)}


def audit_n400(form: Form) -> None:
    """N-400 (01/20/25): each trip row is complete and ends after it starts, and flags for the
    attorney what the trips and the green card date say about continuous residence and physical
    presence (warnings: the statute's exceptions are the attorney's call)."""
    form.blank_output()
    form.missing("Eligibility basis (Part 1 item 1) is not selected", ["Part1_Eligibility"])
    today = form.today or datetime.now(UTC)
    basis = form.value("Part1_Eligibility")
    days_out = 0
    for number, (left, back, countries) in enumerate(N400_TRIP_ROWS, start=1):
        row = [left, back, countries]
        if not form.filled(row):
            continue
        form.missing(f"Trip {number} (Part 8) is incomplete", row)
        start, end = parse_us_date(form.value(left)), parse_us_date(form.value(back))
        if not (start and end):
            continue
        if end < start:
            form.add(f"Trip {number} (Part 8) returns before it leaves", [left, back])
            continue
        length = (end - start).days
        days_out += max(length - 1, 0)  # the days of departure and return count as days in the United States
        if length >= 365:
            form.add(
                f"Trip {number} (Part 8) lasted a year or more: it breaks continuous residence "
                "unless an approved N-470 preserved it",
                [left, back],
                severity="warning",
                days=length,
                open_item_type="attorney_decision",
            )
        elif length > 180:
            form.add(
                f"Trip {number} (Part 8) lasted more than six months: continuous residence is "
                "presumed broken unless the applicant shows otherwise",
                [left, back],
                severity="warning",
                days=length,
                open_item_type="attorney_decision",
            )
    if basis in N400_RESIDENCE:
        years, months = N400_RESIDENCE[basis]
        lpr = parse_us_date(form.value("P2_Line9_DateBecamePermanentResident"))
        if lpr is not None:
            eligible = lpr.replace(year=lpr.year + years) - timedelta(days=90)
            if today < eligible:
                form.add(
                    f"Filed before the applicant has {years} years of permanent residence less 90 days "
                    f"(earliest filing date {eligible:%m/%d/%Y})",
                    ["P2_Line9_DateBecamePermanentResident"],
                    severity="warning",
                    open_item_type="attorney_decision",
                )
        allowed_out = years * 365 - months * 30.4
        if days_out > allowed_out:
            form.add(
                f"The trips listed add up to about {days_out} days outside the United States, more than "
                f"the {years}-year period allows for {months} months of physical presence",
                [row[0] for row in N400_TRIP_ROWS],
                severity="warning",
                open_item_type="attorney_decision",
            )


I751_WAIVERS = ["Pt3Line1c", "Pt3Line1d", "Pt3Line1e", "Pt3Line1f", "Pt3Line1g"]
I751_SPOUSE_PART = ["P8_Checkbox1", "P5_Line3_DaytimePhoneNumber[1]", "Pt8_Name"]


def audit_i751(form: Form) -> None:
    """I-751 (04/01/24): exactly one route, joint (1.a/1.b) or waiver (1.c-1.g); a joint petition
    has the spouse's part and signature, a waiver has neither; a waiver for a marriage that ended
    gives the date it ended."""
    form.blank_output()
    joint = form.value("Pt3Line1")
    waivers = [box for box in I751_WAIVERS if form.checked(box)]
    if joint and waivers:
        form.add("Part 3 selects both a joint petition and a waiver; choose one route", ["Pt3Line1", *waivers])
    elif not joint and not waivers:
        form.add("Part 3 basis for the petition is not selected", ["Pt3Line1", *I751_WAIVERS])
    spouse_signature = form.plan_status("spouse_signature")
    if joint:
        form.missing("A joint petition's spouse part (Part 8) is incomplete", I751_SPOUSE_PART)
        if spouse_signature == STATUS_NOT_APPLICABLE:
            form.add("A joint petition needs the spouse's signature, but the plan marks it not applicable",
                     question_key="spouse_signature")
    if waivers:
        if form.filled(I751_SPOUSE_PART) or (spouse_signature and spouse_signature != STATUS_NOT_APPLICABLE):
            form.add("A waiver petition has the spouse's part or signature, which only a joint petition takes",
                     I751_SPOUSE_PART)
        if {"Pt3Line1c", "Pt3Line1d"} & set(waivers):
            form.missing("The date the marriage ended (Part 1 item 13) is missing for a death or divorce waiver",
                         ["P1_Line13_DateMarriageEnded"])


I765_FOLLOW_UPS = {
    ("c", "3", "C"): ("(c)(3)(C) STEM OPT", ["Line27a_Degree", "Line27b_Everify", "Line27c_EverifyIDNumber"]),
    ("c", "26", ""): ("(c)(26) H-4 spouse", ["Line28_ReceiptNumber"]),
    ("c", "8", ""): ("(c)(8) pending asylum", ["PtLine29_YesNo"]),
    ("c", "35", ""): ("(c)(35) compelling circumstances", ["Line30a_ReceiptNumber", "PtLine30b_YesNo"]),
    ("c", "36", ""): ("(c)(36) compelling circumstances", ["Line30a_ReceiptNumber", "PtLine30b_YesNo"]),
}


def audit_i765(form: Form) -> None:
    """I-765 (08/21/25): the eligibility category is written as the form takes it, and only its own
    follow-up items (28-31) are answered."""
    form.blank_output()
    category = tuple(form.value(box) for box in ("section_1", "section_2", "section_3"))
    if not category[0] or not category[1]:
        form.add("Eligibility category (Part 2 item 27) is not answered", ["section_1", "section_2", "section_3"])
        return
    if category[0] not in {"a", "c"} or not category[1].isdigit() or "(" in "".join(category):
        form.add(
            "Eligibility category is not written as the form takes it (letter a or c, then the number, "
            "no parentheses)",
            ["section_1", "section_2", "section_3"],
            value="/".join(category),
        )
    own = I765_FOLLOW_UPS.get((category[0].lower(), category[1], category[2]))
    own_boxes = own[1] if own else []
    if own:
        form.missing(f"{own[0]} follow-up items are incomplete", own_boxes)
    others = sorted({box for _label, boxes in I765_FOLLOW_UPS.values() for box in boxes} - set(own_boxes))
    stray = [box for box in others if form.value(box)]
    if stray:
        form.add("Items 28-31 are answered for a category other than the one in item 27", stray)


def audit_i360(form: Form) -> None:
    """I-360 (01/20/25), the VAWA self-petition the schema covers: a VAWA classification (I, J or
    K), the self-petitioner's identity, and the abuser's name."""
    form.blank_output()
    classification = form.value("Pt2Line1")
    if classification and classification not in {"I", "J", "K"}:
        form.add("Part 2 item 1 selects a classification other than a VAWA self-petition (I, J or K)", ["Pt2Line1"],
                 value=classification)
    form.missing(
        "Classification, self-petitioner or abuser identity is missing",
        ["Pt2Line1", "Pt3Line1_FamilyName", "Pt3Line1_GivenName", "Pt3Line3_DateOfBirth",
                "Pt3Line4_CountryOfBirth", "Pt10Line1_FamilyName", "Pt10Line1_GivenName"],
    )


AUDITORS = {
    "g-28": audit_g28,
    "i-130": audit_i130,
    "i-130a": audit_i130a,
    "i-485": audit_i485,
    "i-131": audit_i131,
    "i-864": audit_i864,
    "i-765": audit_i765,
    "i-751": audit_i751,
    "n-400": audit_n400,
    "i-360": audit_i360,
    "i-129f": audit_i129f,
    "i-140": audit_i140,
    "i-601": audit_i601,
    "i-612": audit_i612,
    "i-907": audit_i907,
    "i-601a": audit_i601a,
    "i-864a": audit_i864a,
    "i-693": audit_i693,
    "g-1145": audit_g1145,
    "g-1450": audit_payment_form,
    "g-1650": audit_payment_form,
}


# --------------------------------------------------------------------------- text overflow
#
# Filing copies are rendered by Ghostscript from the AcroForm appearances that `fill`
# generates with pypdf. At a fixed font size those appearances neither wrap nor shrink
# text: a line wider than its box, or more lines than the box holds, is simply cut off,
# and the rendered filing copy loses the rest.
#
# The model below was calibrated against real filing copies (render, then compare with a
# render whose box and clip were grown, so any difference is ink the box cut off):
# - the clip is the widget's own box (pypdf's narrower inner clip never took effect; see
#   xfa_tools.close_appearance_clips);
# - text starts 2 pt in from the left edge, is centred in the box for /Q 1, and ends 2 pt in
#   from the right edge for /Q 2, so a centred 10-character date fills a 60 pt box exactly;
# - a line is cut off when its advance runs past an edge of the box (at 10 pt Courier New
#   Bold, 36 characters fit a 222 pt box, 38 a 234 pt one and 85 the 515.9 pt I-485 Part 14);
# - a multi-line box puts the first baseline one font-bbox top below its top edge and steps
#   down by the font-bbox height (19.3 pt for Courier New Bold at 10 pt); a line whose
#   baseline falls below the bottom edge is cut off. So a 30 pt box holds one line, 54 pt
#   three, 90 pt five, 126 pt six, 162 pt eight and 180 pt nine. On the last line that fits,
#   descenders (g, j, p, q, y) can lose their tails.
# The widths come from the standard font metrics, so a value right at the edge may still be
# judged either way.

FIELD_FLAG_MULTILINE = 1 << 12
FIELD_FLAG_COMB = 1 << 24
AUTO_SIZE_MIN = 4.0  # pypdf shrinks auto-sized text no further than this
AUTO_SIZE_MULTILINE = 12.0  # and starts auto-sized multi-line text here
EDGE_EPSILON = 0.01  # pt; rounding in the appearance stream, not an ink allowance
ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT = 0, 1, 2
DA_FONT_RE = re.compile(r"/(?P<font>[^\s/\[\]()<>]+)\s+(?P<size>[-+]?\d*\.?\d+)\s+Tf")

# Advance widths in 1/1000 em for printable ASCII (32-126), from the Adobe core-14
# AFM files. Courier is 600 for every character.
HELVETICA_WIDTHS = (
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
)
HELVETICA_BOLD_WIDTHS = (
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
    975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
    333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
    611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584,
)
# Font bounding box (bottom, top) in 1/1000 em, for line height when the PDF has none.
CORE_FONT_BBOX = {
    "Courier": (-250.0, 805.0),
    "Helvetica": (-225.0, 931.0),
    "Helvetica-Bold": (-228.0, 962.0),
}


@dataclass(frozen=True)
class FontMetrics:
    family: str  # Courier, Helvetica or Helvetica-Bold
    bbox_bottom: float
    bbox_top: float

    def width(self, text: str, size: float) -> float:
        if self.family == "Courier":
            units = 600 * len(text)
        else:
            table = HELVETICA_BOLD_WIDTHS if self.family == "Helvetica-Bold" else HELVETICA_WIDTHS
            units = sum(table[ord(char) - 32] if 32 <= ord(char) <= 126 else 556 for char in text)
        return units * size / 1000

    @property
    def leading(self) -> float:
        return (self.bbox_top - self.bbox_bottom) / 1000


def font_metrics(font_name: str, base_font: str = "", bbox: tuple[float, float] | None = None) -> FontMetrics:
    """Courier metrics for Courier-like fonts, Helvetica (bold when named so) otherwise."""
    lowered = f"{base_font} {font_name}".lower()
    if "cour" in lowered:
        family = "Courier"
    elif "bold" in lowered or font_name.lower() in {"hebo", "helvb"}:
        family = "Helvetica-Bold"
    else:
        family = "Helvetica"
    bottom, top = bbox or CORE_FONT_BBOX[family]
    return FontMetrics(family, float(bottom), float(top))


@dataclass(frozen=True)
class TextWidget:
    name: str  # the field name as plans use it: Name, or Name[n] when it repeats
    key: tuple[str, int]
    page: int
    value: str
    width: float
    height: float
    font: FontMetrics
    font_size: float  # 0 means auto-size
    multiline: bool
    margin: float = 0.0
    alignment: int = ALIGN_LEFT  # the widget's /Q: 0 left, 1 centred, 2 right


def wrapped_line_count(text: str, font: FontMetrics, size: float, width: float) -> int:
    """Lines needed when words wrap at `width` (how pypdf lays out auto-sized multi-line text)."""
    count = 0
    for paragraph in text.splitlines() or [""]:
        line_width = 0.0
        count += 1
        for word in paragraph.split(" "):
            word_width = font.width(word, size)
            space = font.width(" ", size) if line_width else 0.0
            if line_width and line_width + space + word_width > width:
                count += 1
                line_width = word_width
            else:
                line_width += space + word_width
    return count


def lines_that_fit(widget: TextWidget, size: float) -> int:
    """Lines of a multi-line box whose baseline stays inside the box (see the model above)."""
    font = widget.font
    first_baseline = widget.height - widget.margin - font.bbox_top * size / 1000
    step = font.leading * size
    bottom = widget.margin
    if step <= 0:
        return 1
    if first_baseline < bottom - EDGE_EPSILON:
        return 1  # even one line is cut; reported as one so the advice stays usable
    return int((first_baseline - bottom + EDGE_EPSILON) // step) + 1


def text_overflow(widget: TextWidget) -> dict[str, object] | None:
    """How a value overflows its box on the rendered filing copy, or None if it fits."""
    margin = widget.margin
    inset = 2 * max(margin, 1.0)  # pypdf's text inset from the left (and, right-aligned, the right) edge
    box = widget.width  # the clip is the box itself
    if box <= inset or not widget.value.strip():
        return None
    font = widget.font
    lines = widget.value.splitlines() or [widget.value]
    alignment = widget.alignment

    def start_of(line_width: float) -> float:
        if alignment == ALIGN_CENTER:
            return (box - line_width) / 2
        if alignment == ALIGN_RIGHT:
            return box - inset - line_width
        return inset

    def line_fits(line: str, size: float) -> bool:
        line_width = font.width(line, size)
        start = start_of(line_width)
        return start >= -EDGE_EPSILON and start + line_width <= box + EDGE_EPSILON

    size = widget.font_size
    auto_wrapped = False  # pypdf wraps auto-sized multi-line text itself
    if size <= 0:
        # pypdf scales auto-sized text to the box less 2 pt a side (4 pt with a border).
        scale_width = box - 4 * max(margin, 1.0)
        if not widget.multiline:
            if font.width(" ".join(lines), AUTO_SIZE_MIN) <= scale_width + EDGE_EPSILON:
                return None
            size = AUTO_SIZE_MIN
            lines = [" ".join(lines)]
        else:
            field_height = widget.height - 2 * margin
            size = AUTO_SIZE_MULTILINE
            while size >= AUTO_SIZE_MIN:
                needed = wrapped_line_count(widget.value, font, size, scale_width)
                if size + (needed - 1) * font.leading * size <= field_height:
                    return None
                size = round(size - 0.2, 1)
            size = AUTO_SIZE_MIN
            auto_wrapped = True

    if auto_wrapped:
        line_count = wrapped_line_count(widget.value, font, size, box - 4 * max(margin, 1.0))
        too_wide: list[str] = []
    else:
        line_count = len(lines)
        too_wide = [line for line in lines if not line_fits(line, size)]
    fit = lines_that_fit(widget, size) if widget.multiline else 1
    if not too_wide and line_count <= fit:
        return None

    room = box if alignment == ALIGN_CENTER else box - inset  # width one line may use
    longest = max(lines, key=len)
    average = font.width(longest, size) / max(len(longest), 1)
    chars_per_line = max(1, int((room + EDGE_EPSILON) // average)) if average else 0
    rewrapped = sum(max(1, -(-len(line) // chars_per_line)) for line in lines) if chars_per_line else len(lines)
    return {
        "font_size": size,
        "box_width_pt": round(room, 1),
        "text_width_pt": round(max(font.width(line, size) for line in lines), 1),
        "lines": line_count,
        "lines_that_fit": fit,
        "lines_too_wide": len(too_wide),
        "chars_per_line": chars_per_line,
        "fits_if_rewrapped": widget.multiline and not auto_wrapped and rewrapped <= fit,
    }


def text_widgets(pdf_path: Path) -> list[TextWidget]:
    """Filled text widgets of a live AcroForm (the layer the filing copy is rendered from)."""
    reader = PdfReader(str(pdf_path))
    root_acroform = reader.trailer["/Root"].get("/AcroForm")
    if not root_acroform:
        return []
    acroform = root_acroform.get_object()
    default_da = str(acroform.get("/DA") or "")
    fonts: dict[str, tuple[str, tuple[float, float] | None]] = {}
    resources = acroform.get("/DR")
    font_dict = resources.get_object().get("/Font") if resources is not None else None
    for resource_name, font_ref in (font_dict.get_object() if font_dict is not None else {}).items():
        font = font_ref.get_object()
        descriptor = font.get("/FontDescriptor")
        bbox = None
        if descriptor is not None and descriptor.get_object().get("/FontBBox") is not None:
            raw = [float(item) for item in descriptor.get_object()["/FontBBox"]]
            bbox = (raw[1], raw[3])
        fonts[str(resource_name).lstrip("/")] = (str(font.get("/BaseFont") or "").lstrip("/"), bbox)

    default_alignment = int(acroform.get("/Q", 0) or 0)
    found: list[tuple[str, int, int, str, float, float, FontMetrics, float, bool, float, int]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        for annot_ref in page.get("/Annots") or []:
            annot = annot_ref.get_object()
            if annot.get("/Subtype") != "/Widget":
                continue
            holder = annot
            if "/T" not in annot and annot.get("/Parent") is not None:
                holder = annot["/Parent"].get_object()
            if (annot.get("/FT") or holder.get("/FT")) != "/Tx":
                continue
            flags = int(annot.get("/Ff", holder.get("/Ff", 0)) or 0)
            value = holder.get("/V")
            if flags & FIELD_FLAG_COMB or value is None or not str(value).strip():
                continue
            da = str(annot.get("/DA") or holder.get("/DA") or default_da)
            match = DA_FONT_RE.search(da)
            font_name = match.group("font") if match else "Helv"
            base_font, bbox = fonts.get(font_name, ("", None))
            rect = [float(item) for item in annot.get("/Rect", [0, 0, 0, 0])]
            width, height = abs(rect[2] - rect[0]), abs(rect[3] - rect[1])
            characteristics = annot.get("/MK")
            characteristics = characteristics.get_object() if characteristics is not None else {}
            if int(characteristics.get("/R", 0) or 0) % 180 == 90:
                width, height = height, width
            border = annot.get("/BS")
            border = border.get_object() if border is not None else {}
            border_width = float(border.get("/W", 1)) if characteristics.get("/BC") else 0.0
            margin = border_width * (2 if str(border.get("/S", "")) in {"/B", "/I"} else 1)
            name = leaf_field_name(widget_full_name(annot))
            if not name:
                continue
            base, index = field_base_and_index(name)
            found.append(
                (
                    base,
                    index,
                    page_number,
                    str(value),
                    width,
                    height,
                    font_metrics(font_name, base_font, bbox),
                    float(match.group("size")) if match else 0.0,
                    bool(flags & FIELD_FLAG_MULTILINE),
                    margin,
                    int(annot.get("/Q", holder.get("/Q", default_alignment)) or 0),
                )
            )

    widest_index: dict[str, int] = defaultdict(int)
    for field_names in (reader.get_fields() or {}):
        base, index = qualified_base_and_index(field_names)
        widest_index[base] = max(widest_index[base], index)
    return [
        TextWidget(
            name=occurrence_key(base, index, widest_index[base] + 1),
            key=(base, index),
            page=page,
            value=value,
            width=width,
            height=height,
            font=font,
            font_size=size,
            multiline=multiline,
            margin=margin,
            alignment=alignment,
        )
        for base, index, page, value, width, height, font, size, multiline, margin, alignment in found
    ]


def overflow_report(pdf_path: Path | None) -> dict[tuple[str, int], dict[str, object]]:
    """(base, index) -> overflow details, for every filled text box whose text is cut off."""
    if pdf_path is None:
        return {}
    report: dict[tuple[str, int], dict[str, object]] = {}
    for widget in text_widgets(pdf_path):
        info = text_overflow(widget)
        if info is not None:
            report[widget.key] = {
                **info,
                "field": widget.name,
                "page": widget.page,
                "value": widget.value,
                "multiline": widget.multiline,
            }
    return report


def visible_value_in_overflowing_field(
    value: str,
    question: dict[str, object],
    overflow: dict[tuple[str, int], dict[str, object]],
) -> bool:
    wanted = normalize_visible_text(value)
    for field_name, field_text in dict(question.get("field_values", {})).items():
        key = field_base_and_index(canonical_field_name(str(field_name)))
        if key in overflow and wanted and wanted in normalize_visible_text(str(field_text)):
            return True
    return False


def overflow_findings(
    *,
    kind: str,
    pdf_path: Path,
    overflow: dict[tuple[str, int], dict[str, object]],
    manifest_entry: dict[str, object] | None,
) -> list[dict[str, object]]:
    question_for: dict[tuple[str, int], str] = {}
    for question in list((manifest_entry or {}).get("questions", [])):
        for field_name in dict(question.get("field_values", {})):
            key = field_base_and_index(canonical_field_name(str(field_name)))
            question_for.setdefault(key, str(question.get("key") or ""))

    findings: list[dict[str, object]] = []
    for key, info in overflow.items():
        chars = info["chars_per_line"]
        if info["multiline"]:
            title = "Text is cut off in a multi-line box on the filing copy"
            keep = info["lines_that_fit"]
            if info["fits_if_rewrapped"]:
                fix = (
                    f"Break the text into lines of about {chars} characters; the box does not "
                    "wrap long lines, and once broken the text fits."
                )
            else:
                fix = (
                    "Continue on an additional-information page: keep "
                    + (f"one line of up to {chars} characters" if keep == 1 else f"about {keep} lines of up to {chars} characters")
                    + " in this box, and carry the rest into the next Additional Information entry "
                    "(or an attached sheet) with the same page, part and item number."
                )
        else:
            title = "Text is cut off in a single-line box on the filing copy"
            fix = (
                f"Shorten or abbreviate the answer to about {chars} characters, or give the full "
                "answer in the form's Additional Information part with its page, part and item number."
            )
        value = str(info["value"])
        found: dict[str, object] = finding(kind, pdf_path, title, fields=[info["field"]], page=info["page"],
                                           value=value if len(value) <= 200 else value[:197] + "...",
                                           font_size=info["font_size"], box_width_pt=info["box_width_pt"],
                                           text_width_pt=info["text_width_pt"], fix=fix)
        if info["multiline"]:
            found["lines"] = info["lines"]
            found["lines_that_fit"] = info["lines_that_fit"]
        if key in question_for:
            found["question_key"] = question_for[key]
        findings.append(found)
    return findings


# --------------------------------------------------------------------------- box rules


def box_rule_findings(
    *, kind: str, pdf_path: Path, widget_pdf: Path | None, values: dict[str, str]
) -> list[dict[str, object]]:
    """Every stored answer against its own box, on every form.

    - No answer may be longer than its box's maxlen. Adobe cuts such an answer off at the
      limit, and a comb box (one character per cell: A-Numbers, ZIP Codes, receipt numbers)
      has no room for the rest at all, so the filing copy and the form USCIS reads disagree.
    - Each answer must be in the format its box takes (formats.py): a real mm/dd/yyyy date in
      every date box, 7 to 9 digits in an A-Number box, 9 in an SSN box, 3 letters and 10 digits
      in a receipt number box, 11 characters in an I-94 box, a ZIP Code, a state code.
    """
    if widget_pdf is None:
        return []
    reader = PdfReader(str(widget_pdf))
    acro = acro_fields_by_base(reader)
    global_names = global_bound_names(reader)  # one answer shown in many boxes: report it once
    box_formats = formats.box_formats(widget_pdf)
    too_long: list[dict[str, object]] = []
    misformatted: dict[str, list[dict[str, str]]] = defaultdict(list)
    seen: set[tuple[str, int]] = set()
    for name, raw in sorted(values.items()):
        value = str(raw or "").strip()
        base, index = field_base_and_index(name)
        specs = acro.get(base)
        key = (base, 0 if base in global_names else index)
        if not value or not specs or key in seen or specs[0].field_type == "/Btn":
            continue
        seen.add(key)
        spec = specs[index] if index < len(specs) else specs[0]
        if spec.max_len and len(value) > spec.max_len:
            too_long.append({"field": name, "value": value, "length": len(value), "maxlen": spec.max_len})
        box_format = box_formats.get(base)
        us_row = None
        if box_format == formats.ZIP_OR_POSTAL:  # a ZIP Code on a U.S. row, a postal code abroad
            country = field_value(values, formats.country_box(base)).strip()
            us_row = is_us_country(country) if country else None
        problem = formats.check(box_format, value, max_len=spec.max_len, us_row=us_row) if box_format else None
        if problem:
            misformatted[box_format].append({"field": name, "value": value, "problem": problem})
    findings: list[dict[str, object]] = []
    if too_long:
        findings.append(
            finding(
                kind,
                pdf_path,
                "An answer is longer than its box allows",
                fields=[item["field"] for item in too_long],
                values=too_long[:20],
                fix="Shorten each answer to the box's limit (a comb box holds one character per cell), "
                "or give the full answer in the form's Additional Information part with its page, "
                "part and item number.",
            )
        )
    for box_format, items in misformatted.items():
        label, takes = formats.DESCRIPTIONS[box_format]
        findings.append(finding(kind, pdf_path, f"{label} box holds an answer in the wrong format",
                                fields=[item["field"] for item in items], values=items[:20],
                                fix=f"{'An' if label[:1] in 'AEIOU' else 'A'} {label} box takes {takes}."))
    return findings


# --------------------------------------------------------------------------- known form defects


def button_states(pdf_path: Path) -> dict[str, set[str]]:
    """Checkbox on-states grouped by field base name."""
    states: dict[str, set[str]] = defaultdict(set)
    for full_name, spec in (PdfReader(str(pdf_path)).get_fields() or {}).items():
        if str(spec.get("/FT") or "") != "/Btn":
            continue
        base, _ = qualified_base_and_index(full_name)
        for state in spec.get("/_States_") or []:
            text = str(state).lstrip("/")
            if text.strip() and text != "Off":
                states[base].add(text)
    return states


def known_defect_findings(
    *,
    kind: str,
    pdf_path: Path,
    widget_pdf: Path | None,
    values: dict[str, str],
) -> list[dict[str, object]]:
    """Warn about known defects of the form edition that the preparer has to work around."""
    if widget_pdf is None:
        return []
    findings: list[dict[str, object]] = []
    for defect in linked_checkbox_defects(button_states(widget_pdf)):
        current = field_value(values, defect["base"]).strip()
        findings.append(finding(kind, pdf_path, f"Known {defect['form']} defect: linked checkboxes need hand-marking",
                                severity="warning", fields=[defect["base"]], problem=defect["problem"],
                                currently_checked=defect["states"].get(current, "none of them"),
                                action=defect["action"], open_item_type="attorney_action"))
    return findings


def adobe_view_findings(
    *,
    kind: str,
    pdf_path: Path,
    xfa_pdf: Path | None,
    manifest_entry: dict[str, object] | None,
) -> list[dict[str, object]]:
    """Planned answers that Adobe shows blank or different when it opens the XFA source.

    Adobe reads only the data node the form's template binds a box to. A source filled before
    fill followed the template keeps I-765 values directly under form1 instead of in their page's
    data group, and leaves boxes the template does not bind (other names, place of birth, Part 14
    page/part/item numbers) with no data Adobe reads. The filing copy is not affected.
    """
    if xfa_pdf is None or not manifest_entry:
        return []
    expected = {
        canonical_field_name(str(name)): str(value)
        for name, value in dict(manifest_entry.get("expected_fields", {})).items()
        if str(value).strip()
    }
    if not expected:
        return []
    shown = adobe_view(xfa_pdf, list(expected))
    unbound = sorted(name for name, value in shown.items() if value is None)
    different = [
        {"field": name, "expected": expected[name], "adobe_shows": value}
        for name, value in shown.items()
        if value is not None and not values_equivalent(expected[name], value)
    ]
    if not unbound and not different:
        return []
    found: dict[str, object] = finding(
        kind,
        pdf_path,
        "Adobe shows planned answers blank or different when it opens the XFA source",
        source_file=str(xfa_pdf),
        fields=unbound + [item["field"] for item in different],
        fix="Fill the source again from the official blank with the current xfa_tools.py fill, which "
        "writes each value where the form's template binds it and binds unbound boxes, then render "
        "the filing copy again. The filing copy itself shows these answers.",
    )
    if unbound:
        found["unbound_in_template"] = unbound
    if different:
        found["mismatches"] = different[:20]
    return [found]


def pdf_with_form_fields(pdf_path: Path, source_pdf: Path) -> Path | None:
    """The PDF whose live AcroForm the filing copy shows: the copy itself, or its source."""
    for candidate in (pdf_path, source_pdf):
        if candidate.exists() and PdfReader(str(candidate)).get_fields():
            return candidate
    return None


def parse_check_arg(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise ValueError(f"Invalid --check value: {raw}")
    kind, path_text = raw.split("=", 1)
    kind = kind.strip().lower()
    if kind not in AUDITORS:
        raise ValueError(f"Unsupported form kind: {kind}")
    return kind, Path(path_text.strip())


UNRESOLVED_STATUSES = {
    STATUS_MISSING,
    STATUS_PENDING_CLIENT,
    STATUS_PENDING_SIGNATURE,
    STATUS_MANUAL_REVIEW,
    STATUS_PARTIALLY_FILLED,
}
# Form-specific findings that report an answer as absent. Only these can be a deliberate gap;
# a wrong value, a layer mismatch, an overflow or a mapping mistake never is.
ABSENCE_TITLE_RE = re.compile(
    r"\b(missing|incomplete|blank|not answered|not selected|not completed|not described)\b", re.IGNORECASE
)
NOT_ABSENCE_TITLE_RE = re.compile(r"does not reflect|do not match|does not match|cut off|unexpected|question plan", re.IGNORECASE)


def _plain_field_name(name: str) -> str:
    base, index = field_base_and_index(str(name))
    return base if index == 0 else f"{base}[{index}]"


def tie_open_items(findings: list[dict[str, object]], manifest_entry: dict[str, object] | None) -> None:
    """Tie each error that is exactly a deliberate gap to the open item its question names.

    A plan question left missing, pending, for review or partly filled may carry
    "open_item": "<ledger id>". Its own "is missing" / "is still pending" error (and the
    required-section status error it raises) gets that id, and so does a form-specific
    absence error (a "Missing ..." or "... is incomplete" group) whose every field belongs to
    such questions; of a partly filled question, only the boxes it leaves blank count.
    Nothing else is tied: an error about a filled question, a value, a layer,
    an overflow or the plan's own structure is a mistake to fix, not a gap.
    """
    if not manifest_entry:
        return
    questions = [item for item in list(manifest_entry.get("questions") or []) if isinstance(item, dict)]
    by_key = {str(item.get("key")): item for item in questions}
    exact: dict[str, list[str]] = defaultdict(list)
    by_base: dict[str, list[str]] = defaultdict(list)
    for item in questions:
        open_item = str(item.get("open_item") or "").strip()
        if not open_item or str(item.get("status")) not in UNRESOLVED_STATUSES:
            continue
        values = dict(item.get("field_values") or {})
        if str(item.get("status")) == STATUS_PARTIALLY_FILLED:
            values = {name: value for name, value in values.items() if not str(value).strip()}
        for name in values:
            exact[_plain_field_name(name)].append(open_item)
            by_base[field_base_and_index(str(name))[0]].append(open_item)

    for finding in findings:
        if finding.get("severity") != "error" or finding.get("open_item"):
            continue
        key = finding.get("question_key")
        if key:
            item = by_key.get(str(key))
            if (
                item is not None
                and str(item.get("status")) in UNRESOLVED_STATUSES
                and str(item.get("open_item") or "").strip()
                and finding.get("title") in (unresolved_question_title(item), INVALID_STATUS_TITLE)
            ):
                finding["open_item"] = str(item["open_item"]).strip()
            continue
        title = str(finding.get("title") or "")
        fields = [str(name) for name in list(finding.get("fields") or []) if str(name).strip()]
        if not fields or not ABSENCE_TITLE_RE.search(title) or NOT_ABSENCE_TITLE_RE.search(title):
            continue
        ids: list[str] = []
        for name in fields:
            plain = _plain_field_name(name)
            owners = exact.get(plain) or (by_base.get(plain) if "[" not in plain else None)
            if not owners:
                break
            ids.extend(owner for owner in owners if owner not in ids)
        else:
            finding["open_item"] = ids[0]
            if len(ids) > 1:
                finding["open_items"] = ids


def redact_payment_details(kind: str, values: dict[str, str], findings: list[dict[str, object]]) -> list[dict[str, object]]:
    """A payment form's findings with every card or bank detail found on it replaced, so the audit
    JSON never holds one: the findings name the boxes, which is all the fix needs."""
    by_hand = payment_by_hand_bases(kind)
    secrets = sorted(
        {
            str(value).strip()
            for name, value in values.items()
            # A checkbox's one- or two-letter state (V for Visa) is no secret and too short to replace.
            if field_base_and_index(name)[0] in by_hand and len(str(value or "").strip()) >= 3
        },
        key=len,
        reverse=True,
    )
    if not secrets:
        return findings

    def scrub(item: object) -> object:
        if isinstance(item, str):
            for secret in secrets:
                item = item.replace(secret, "(card or bank detail, not shown)")
            return item
        if isinstance(item, dict):
            return {key: value if key in {"file", "source_file"} else scrub(value) for key, value in item.items()}
        if isinstance(item, list):
            return [scrub(value) for value in item]
        return item

    return [scrub(finding) for finding in findings]  # type: ignore[misc]


def run_audit(
    checks: list[tuple[str, Path]],
    intent_manifest_path: Path | None,
    *,
    profile: dict[str, object] | None = None,
    matter: Path | None = None,
) -> dict[str, object]:
    """Audit each (kind, filing copy) and return the payload written as the audit JSON.

    `profile` is the attorney profile and `matter` the matter folder (for its settings); both are
    optional, and the checks that need them are skipped without them.
    """
    results: list[dict[str, object]] = []
    findings: list[dict[str, object]] = []
    intent_manifest = load_intent_manifest(intent_manifest_path)
    protected = matter_is_protected(matter)

    for kind, pdf_path in checks:
        manifest_entry = intent_manifest.get(str(pdf_path))
        source_pdf_path = pdf_path
        xfa, acro = xfa_values(pdf_path), acro_values(pdf_path)
        if not xfa and manifest_entry and manifest_entry.get("source_pdf"):
            source_pdf_path = Path(str(manifest_entry["source_pdf"]))
            found = source_pdf_path.exists()
            xfa, acro = (xfa_values(source_pdf_path), acro_values(source_pdf_path)) if found else ({}, {})
        values = merged(xfa, acro)
        widget_pdf = pdf_with_form_fields(pdf_path, source_pdf_path)
        overflow = overflow_report(widget_pdf)
        xfa_pdf = next(
            (candidate for candidate in (pdf_path, source_pdf_path) if candidate.exists() and xfa_values(candidate)),
            None,
        )
        form = Form(kind, pdf_path, values, xfa=xfa, acro=acro, manifest_entry=manifest_entry,
                    intent_manifest=intent_manifest)
        AUDITORS[kind](form)
        from consistency import check_consistency
        check_consistency(form)
        box_findings = box_rule_findings(kind=kind, pdf_path=pdf_path, widget_pdf=widget_pdf, values=values)
        too_long = {
            field_base_and_index(str(name))
            for finding in box_findings
            if finding["title"] == "An answer is longer than its box allows"
            for name in list(finding["fields"])
        }
        overflow_left = {key: info for key, info in overflow.items() if key not in too_long}
        form.findings += box_findings
        here = {"kind": kind, "pdf_path": pdf_path}
        form.findings += overflow_findings(**here, overflow=overflow_left, manifest_entry=manifest_entry)
        form.findings += known_defect_findings(**here, widget_pdf=widget_pdf, values=values)
        form.findings += adobe_view_findings(**here, xfa_pdf=xfa_pdf, manifest_entry=manifest_entry)
        attorney_box_findings(form)
        form.findings += plan_findings(**here, manifest_entry=manifest_entry, overflow=overflow, profile=profile,
                                       widget_pdf=widget_pdf)
        form.findings += intent_findings(**here, actual_values=values, manifest_entry=manifest_entry)
        form.findings += final_output_findings(**here, manifest_entry=manifest_entry)
        form.findings += edition_findings(**here, manifest_entry=manifest_entry)
        form.findings += safe_address_findings(**here, values=values, manifest_entry=manifest_entry, profile=profile,
                                               protected=protected)
        form_findings = form.findings
        form_findings = collapse_overlapping_findings(form_findings)
        form_findings = redact_payment_details(kind, values, form_findings)
        tie_open_items(form_findings, manifest_entry)
        findings.extend(form_findings)
        result: dict[str, object] = {
            "form": kind,
            "file": str(pdf_path),
            "finding_count": len(form_findings),
        }
        if source_pdf_path != pdf_path:
            result["source_file"] = str(source_pdf_path)
        results.append(result)

    errors = [finding for finding in findings if finding["severity"] == "error"]
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "protected_matter": protected,
        "result_count": len(results),
        "error_count": len(errors),
        "warning_count": sum(1 for finding in findings if finding["severity"] == "warning"),
        "tied_error_count": sum(1 for finding in errors if finding.get("open_item")),
        "results": results,
        "findings": findings,
    }


def finding_brief(finding: dict[str, object], *, field_limit: int = 3) -> str:
    """'Title [Field1, Field2, +3]' for a summary line."""
    title = str(finding.get("title") or "untitled")
    fields = [str(name) for name in list(finding.get("fields") or [])]
    if not fields and finding.get("question_key"):
        fields = [f"question {finding['question_key']}"]
        values = [repr(str(value)) for value in list(finding.get("values") or [])]
        if values:
            fields[0] += ": " + ", ".join(values[:2]) + (f", +{len(values) - 2}" if len(values) > 2 else "")
    if not fields:
        return title
    shown = ", ".join(fields[:field_limit]) + (f", +{len(fields) - field_limit}" if len(fields) > field_limit else "")
    return f"{title} [{shown}]"


def summarize_by_file(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    """Per audited file: kind, error/warning counts, tied count, open-item ids and untied errors."""
    summary: dict[str, dict[str, object]] = {}
    for result in list(payload.get("results") or []):
        summary[str(result.get("file"))] = {
            "form": result.get("form"),
            "errors": 0,
            "warnings": 0,
            "tied": 0,
            "open_items": [],
            "untied": [],
            "coverage": result.get("coverage", "audit"),
        }
    for finding in list(payload.get("findings") or []):
        item = summary.setdefault(
            str(finding.get("file")),
            {"form": finding.get("form"), "errors": 0, "warnings": 0, "tied": 0, "open_items": [], "untied": []},
        )
        if finding.get("severity") == "warning":
            item["warnings"] += 1
        elif finding.get("severity") == "error":
            item["errors"] += 1
            if finding.get("open_item"):
                item["tied"] += 1
                for open_item in [finding["open_item"], *list(finding.get("open_items") or [])]:
                    if open_item not in item["open_items"]:
                        item["open_items"].append(open_item)
            else:
                item["untied"].append(finding)
    return summary


def summary_lines(payload: dict[str, object], output_json: Path, *, top: int = 3) -> list[str]:
    errors = int(payload.get("error_count") or 0)
    tied = int(payload.get("tied_error_count") or 0)
    lines = [
        f"audit: {payload.get('result_count', 0)} form(s), {errors} error(s) ({tied} tied to open items), "
        f"{payload.get('warning_count', 0)} warning(s) -> {output_json}"
    ]
    for path, item in summarize_by_file(payload).items():
        lines.append(
            f"  {item['form']} {Path(path).name}: {item['errors']} error(s) ({item['tied']} tied), "
            f"{item['warnings']} warning(s)"
        )
        untied = list(item["untied"])
        for finding in untied[:top]:
            lines.append(f"    untied: {finding_brief(finding)}")
        if len(untied) > top:
            lines.append(f"    +{len(untied) - top} more untied error(s) in the JSON")
    return lines


def main() -> int:
    args = parse_args()
    checks = [parse_check_arg(raw) for raw in args.check]
    payload = run_audit(
        checks,
        args.intent_manifest,
        profile=load_profile(args.profile),
        matter=args.matter.expanduser().resolve() if args.matter else None,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if args.full:
        print(json.dumps(payload, indent=2))
    else:
        print("\n".join(summary_lines(payload, args.output_json)))
    return 1 if payload["error_count"] else 0


if __name__ == "__main__":
    sys.exit(main())

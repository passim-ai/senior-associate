#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Shared logical-section schemas for supported USCIS form profiles.

Each schema lists the logical questions a question plan must cover for that form
profile, the XFA fields each question must declare, and which of them must be
non-empty when the question is marked filled. The audit enforces these.

A schema can also carry, per question, a `label`, `field_notes` (what each box is,
where its name misleads) and `choices` (checkbox or radio answers mapped to the
box's on-state), so a preparer can fill the form without reverse-engineering it.
Schemas built against a stored field list name it in `field_list`, and the tests
check every field and on-state against it.

The schemas live one file per form in `schemas/`, each defining
`SCHEMAS = {name: schema}`; they are loaded here.

    list                 print schema names with their form kind and description
    skeleton SCHEMA [--out PLAN.json [--force]]
                         print a starter question plan for SCHEMA (all statuses "missing"),
                         or write it to PLAN.json (an existing plan is kept unless --force).
                         `forms_workflow.py build MATTER --new NAME=SCHEMA` does this for
                         a matter and also fetches the blank.
    fields BLANK OUT     save a blank form's field names, types and on-states as a
                         field list for schema tests (schemas/fields/<FORM>.json)
    migrate PLAN [--dry-run] [--profile PROFILE.json] [--across-editions]
                         bring a plan written from an older version of its schema onto the
                         current skeleton: every answer is copied by question key and box name,
                         each status is kept, and the report lists the new questions to answer
                         (the old plan is kept beside it as PLAN.premigrate). A plan written for
                         another edition of the form is refused: a box of the same name on another
                         edition may ask something else. --across-editions migrates it anyway and
                         sets every answered question to manual_review, to be checked against the
                         new edition's instructions one by one.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from forms_workflow import (
    file_sha256,
    leaf_field_name,
    normalize_visible_text,
    STATUS_MANUAL_REVIEW,
    STATUS_MISSING,
    STATUS_FILLED,
    STATUS_NOT_APPLICABLE,
    STATUS_PARTIALLY_FILLED,
    STATUS_PENDING_CLIENT,
    STATUS_PENDING_SIGNATURE,
    WRITTEN_STATUSES,
)


SCHEMA_G28_CLIENT = "g28_represented_client"
SCHEMA_I130_FAMILY_PETITION = "i130_family_petition"
SCHEMA_I131_ADVANCE_PAROLE = "i131_advance_parole_pending_i485"
SCHEMA_I485_EMPLOYMENT_PRINCIPAL = "i485_employment_principal"
SCHEMA_I485_EMPLOYMENT_DERIVATIVE_CHILD = "i485_employment_derivative_child"

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
FIELD_LIST_DIR = SCHEMA_DIR / "fields"


def load_schema_modules() -> dict[str, dict[str, Any]]:
    """Schemas from schemas/*.py, one module per form, each defining SCHEMAS."""
    if str(SCHEMA_DIR) not in sys.path:
        sys.path.insert(0, str(SCHEMA_DIR))  # the schema files import _common
    loaded: dict[str, dict[str, Any]] = {}
    for path in sorted(SCHEMA_DIR.glob("[!_]*.py")):
        spec = importlib.util.spec_from_file_location(f"question_schemas_{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded.update(module.SCHEMAS)
    from answer_integrity import sensitive_question
    for schema in loaded.values():
        for question in schema.get("required_questions", {}).values():
            if sensitive_question(question, str(schema.get("kind") or "")) and STATUS_FILLED in question.get("allowed_statuses", [STATUS_FILLED]):
                question["requires_client_confirmation"] = True
                allowed = question.setdefault("allowed_statuses", [STATUS_FILLED])
                if STATUS_PENDING_CLIENT not in allowed:
                    allowed.append(STATUS_PENDING_CLIENT)
    return loaded


QUESTION_SCHEMAS = load_schema_modules()


def get_question_schema(name: str) -> dict[str, Any] | None:
    return QUESTION_SCHEMAS.get(name)


def load_field_list(name: str) -> dict[str, Any]:
    """A stored field list (schemas/fields/<name>), as written by the `fields` command."""
    return json.loads((FIELD_LIST_DIR / name).read_text(encoding="utf-8"))


def field_widgets(reader: Any) -> dict[str, list[str]]:
    """Where each box sits: {field base: ["page x0 y0 x1 y1", ...]}, one entry per widget, in points
    rounded to 0.1, in page order. A new edition's blank is compared with this box by box
    (editions.compare_boxes): a box that moved may ask something else."""
    from forms_workflow import widget_full_name

    widgets: dict[str, list[str]] = {}
    for page_number, page in enumerate(reader.pages, start=1):
        for annot_ref in page.get("/Annots") or []:
            annot = annot_ref.get_object()
            if annot.get("/Subtype") != "/Widget" or "/Rect" not in annot:
                continue
            base = leaf_field_name(widget_full_name(annot)).split("[")[0]
            if not base:
                continue
            x0, y0, x1, y1 = (float(value) for value in annot["/Rect"])
            box = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
            widgets.setdefault(base, []).append(f"{page_number} " + " ".join(f"{value:.1f}" for value in box))
    return dict(sorted(widgets.items()))


def save_field_list(blank_pdf: Path, out_path: Path) -> dict[str, Any]:
    """Field names, types, on-states and max lengths of a blank form, without tooltips or values,
    and where each box sits (field_widgets)."""
    from pypdf import PdfReader

    reader = PdfReader(str(blank_pdf))
    fields: dict[str, dict[str, Any]] = {}
    for name, field in (reader.get_fields() or {}).items():
        if not field.get("/FT"):
            continue  # layout containers such as form1, Page1 or #area, not fields
        # Escape-aware: "P9_Line7\.b\." is one field named "P9_Line7.b.", not three.
        base = leaf_field_name(name).split("[")[0]
        entry = fields.setdefault(base, {"type": str(field["/FT"]), "states": []})
        for state in field.get("/_States_", []) or []:
            if isinstance(state, (list, tuple)):  # a choice list's (export value, display text)
                state = state[0]
            state = str(state).lstrip("/")
            if state != "Off" and state not in entry["states"]:
                entry["states"].append(state)
        if field.get("/MaxLen") is not None:
            entry["maxlen"] = int(field["/MaxLen"])
    payload = {
        "pdf": blank_pdf.name,
        "pdf_sha256": file_sha256(blank_pdf),
        "fields": dict(sorted(fields.items())),
        "widgets": field_widgets(reader),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    return payload


def load_profile(path: Path | None) -> dict[str, Any]:
    """The attorney profile (matter contract, "Attorney profile"), or {} when there is none."""
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def profile_not_applicable(spec: dict[str, Any], profile: dict[str, Any] | None) -> str:
    """Why the attorney profile makes this question not applicable ("" when it doesn't).

    A schema question says which profile answers settle it in `not_applicable_when_profile`, as
    the G-28's attorney online account question does with has_uscis_online_account "no".
    """
    rules = dict(spec.get("not_applicable_when_profile") or {})
    if not profile or not rules:
        return ""
    for key, value in rules.items():
        if str(profile.get(key, "")).strip().casefold() != str(value).casefold():
            return ""
    if "has_uscis_online_account" in rules:
        return "The attorney profile says the attorney has no USCIS online account."
    return "The attorney profile settles this question: " + ", ".join(f"{k} is {v}" for k, v in rules.items()) + "."


def skeleton_plan(name: str, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    schema = get_question_schema(name)
    if schema is None:
        raise SystemExit(f"Unknown schema {name!r}. Known: {sorted(QUESTION_SCHEMAS)}")
    questions = []
    for key, spec in schema["required_questions"].items():
        question = {
            "key": key,
            "label": spec.get("label") or key.replace("_", " ").capitalize(),
            "status": STATUS_MISSING,
            "allowed_statuses": list(spec.get("allowed_statuses", [STATUS_FILLED])),
            "field_values": {field: "" for field in spec.get("required_fields", [])},
            "required_nonempty_fields_when_filled": list(
                spec.get("required_nonempty_fields_when_filled", [])
            ),
            "visible_values": [],
            "fact_ids": [],
            "notes": "",
        }
        if STATUS_PENDING_SIGNATURE in question["allowed_statuses"]:
            # A form not yet signed is normal in a draft: report it as a warning, not an error.
            question["unresolved_severity"] = "warning"
        if spec.get("field_notes"):
            question["field_notes"] = dict(spec["field_notes"])
        if spec.get("choices"):
            question["choices"] = {field: dict(options) for field, options in spec["choices"].items()}
        settled = profile_not_applicable(spec, profile)
        if settled:
            question["status"] = STATUS_NOT_APPLICABLE
            question["notes"] = settled
        questions.append(question)
    plan = {
        "kind": schema["kind"],
        "subject": "",
        "question_schema": name,
        "fact_table_path": "",
        "sources": [],
        "questions": questions,
    }
    if schema.get("edition"):
        plan["schema_edition"] = schema["edition"]
    if schema.get("notes"):
        plan["schema_notes"] = schema["notes"]
    return plan


# Keys a preparer writes on a question; migrate carries them over. The schema's own keys (label,
# allowed_statuses, required_nonempty_fields_when_filled, field_notes, choices) come from the
# current skeleton instead.
PREPARER_KEYS = ("status", "visible_values", "fact_ids", "notes", "open_item", "required", "unresolved_severity")


def _box(name: str) -> str:
    return str(name).replace("\\", "")


class EditionMismatch(ValueError):
    """migrate was asked to move a plan onto a schema built for another edition of the form."""


# Statuses that are an answer: carried onto another edition, each has to be checked again.
DECIDED_STATUSES = {STATUS_FILLED, STATUS_PARTIALLY_FILLED, STATUS_NOT_APPLICABLE}
# Statuses of a question still being worked on. Every schema allows them while a plan is in
# progress (the audit reports the question as open), so migrate doesn't call them a problem.
OPEN_STATUSES = {STATUS_MISSING, STATUS_PENDING_CLIENT, STATUS_MANUAL_REVIEW, STATUS_PARTIALLY_FILLED}


def migrate_plan(
    plan: dict[str, Any], profile: dict[str, Any] | None = None, *, across_editions: bool = False
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Move a plan written from an older version of its schema onto the current skeleton.

    Every question of the skeleton takes the old question with its key (status, answers, facts,
    notes, open item), and each of its boxes takes the old answer for that box name, wherever
    the old plan kept it. A box answered under an old question that the schema has since split
    or renamed moves to the question that now owns it; the new question is `filled` when it then
    answers every box the schema requires, `partially_filled` when it answers some. An answer that
    was written on the form stays written: a box never moves into a question whose status leaves
    it off the form, and a written answer that finds no other place stays with the question that
    held it (after the schema's questions, when that question has no place in the schema). So
    the filled form is unchanged.

    A new question the attorney profile settles (the G-28's attorney online account when the
    attorney has none) starts not_applicable, as in a skeleton.

    A plan written for another edition of the form (its schema_edition is not the schema's) is
    refused with EditionMismatch: the same box name on another edition can ask something else, so
    moving answers by box name is not safe. With across_editions it is migrated, and every
    question that carries an answer (filled, partly filled or not applicable) becomes
    manual_review, its old status kept in `status_before_migrate`, so the audit holds the form
    until each one is checked against the new edition and marked again.

    Returns (new plan, report). The report lists the questions that are new (left `missing`),
    moved boxes, questions kept outside the schema, statuses the schema doesn't allow (a final
    status only; an open one such as missing is just a question still to answer), and, across
    editions, the editions and the questions to check.
    """
    name = str(plan.get("question_schema") or "").strip()
    schema = get_question_schema(name)
    if schema is None:
        raise ValueError(
            f"The plan names no known schema ({name!r}). Set its question_schema to one of: "
            f"{', '.join(sorted(QUESTION_SCHEMAS))}"
        )
    from_edition = str(plan.get("schema_edition") or "").strip()
    to_edition = str(schema.get("edition") or "").strip()
    crossing = bool(from_edition and to_edition and from_edition != to_edition)
    if crossing and not across_editions:
        raise EditionMismatch(
            f"The plan was written for the {from_edition} edition of the {str(schema['kind']).upper()}, and the "
            f"schema is for the {to_edition} edition. A box with the same name on another edition can ask something "
            "else, so migrate won't move the answers by box name. Prepare the plan again from the current skeleton, "
            "or pass --across-editions to migrate it anyway: every answered question then becomes manual_review, "
            f"to be checked against the {to_edition} instructions one by one."
        )
    old_questions = [dict(item) for item in plan.get("questions", []) if isinstance(item, dict)]
    old_by_key = {str(item.get("key")): item for item in old_questions if item.get("key")}

    def written(status: object) -> bool:
        return str(status or "") in WRITTEN_STATUSES

    def answers(item: dict[str, Any]) -> dict[str, str]:
        return {_box(box): str(value) for box, value in dict(item.get("field_values") or {}).items() if str(value).strip()}

    report: dict[str, Any] = {
        "schema": name,
        "edition": schema.get("edition", ""),
        "from_edition": from_edition if crossing else "",
        "to_review": [],
        "new": [],
        "moved": [],
        "kept_outside_schema": [],
        "status_not_allowed": [],
    }
    taken: set[tuple[int, str]] = set()  # (old question, box) answers already carried somewhere
    carried: set[str] = set()  # keys of the questions that took something from the old plan
    questions: list[dict[str, Any]] = []
    for skeleton in skeleton_plan(name, profile=profile)["questions"]:
        key = skeleton["key"]
        old = old_by_key.get(key)
        question = dict(skeleton)
        values = dict(question["field_values"])
        contributors: list[dict[str, Any]] = []
        if old is not None:
            for field in PREPARER_KEYS:
                if field in old:
                    question[field] = old[field]
            own = answers(old)
            for box in values:
                if _box(box) in own:
                    values[box] = own[_box(box)]
                    taken.add((id(old), _box(box)))
        for box in values:
            if str(values[box]).strip():
                continue
            for source in old_questions:
                value = answers(source).get(_box(box))
                if value is None or source is old or (id(source), _box(box)) in taken:
                    continue
                # A written answer never moves into a question that leaves it off the form.
                if old is not None and written(source.get("status")) != written(question["status"]):
                    continue
                values[box] = value
                taken.add((id(source), _box(box)))
                if all(source is not item for item in contributors):
                    contributors.append(source)
                report["moved"].append({"box": box, "from": source.get("key"), "to": key})
                break
        question["field_values"] = values
        if old is None and contributors:
            statuses = {str(item.get("status")) for item in contributors}
            if all(written(item_status) for item_status in statuses):
                required = list(dict(schema["required_questions"][key]).get("required_nonempty_fields_when_filled", []))
                complete = all(str(values.get(box, "")).strip() for box in required)
                question["status"] = STATUS_FILLED if complete else STATUS_PARTIALLY_FILLED
            elif len(statuses) == 1:
                question["status"] = statuses.pop()
            else:
                question["status"] = STATUS_MANUAL_REVIEW
            question["visible_values"] = []  # rehome_visible_values brings the ones its boxes now show
            question["fact_ids"] = sorted({str(fact) for item in contributors for fact in item.get("fact_ids") or []})
            question["notes"] = "Moved here by migrate from " + ", ".join(str(item.get("key")) for item in contributors) + "."
        elif old is None and question["status"] == STATUS_MISSING:
            report["new"].append(key)
        if old is not None or contributors:
            carried.add(key)
        allowed = list(question.get("allowed_statuses") or [])
        status = str(question["status"])
        if old is not None and status not in allowed and status not in OPEN_STATUSES:
            report["status_not_allowed"].append({"key": key, "status": status, "allowed": allowed})
        questions.append(question)

    # What the old plan wrote on the form and nothing above carries as written stays with the
    # question that held it: as extra boxes on its schema question, which kept its status, or in
    # the old question itself, kept after the schema's questions.
    by_key = {str(question["key"]): question for question in questions}
    orphans: list[str] = []
    written_now = {
        _box(box)
        for question in questions
        if written(question["status"])
        for box, value in question["field_values"].items()
        if str(value).strip()
    }
    for item in old_questions:
        key = str(item.get("key") or "")
        left = {
            box: value
            for box, value in dict(item.get("field_values") or {}).items()
            if str(value).strip() and (id(item), _box(box)) not in taken
            and not (written(item.get("status")) and _box(box) in written_now)
        }
        if key in by_key:
            if written(item.get("status")):
                by_key[key]["field_values"].update(left)
                written_now.update(_box(box) for box in left)
            continue
        if left or not item.get("field_values"):
            questions.append({**item, "field_values": left})
            report["kept_outside_schema"].append(key)
            carried.add(key)
        else:
            orphans.extend(list(item.get("visible_values") or []))  # every box moved; its values follow

    rehome_visible_values(questions, orphans)
    if crossing:
        for question in questions:
            if str(question.get("key")) not in carried or str(question.get("status")) not in DECIDED_STATUSES:
                continue
            question["status_before_migrate"] = question["status"]
            question["status"] = STATUS_MANUAL_REVIEW
            question["notes"] = (
                f"Carried from the plan for the {from_edition} edition: check this answer and its boxes against the "
                f"{to_edition} edition's instructions, then set the status again. " + str(question.get("notes") or "")
            ).strip()
            report["to_review"].append(str(question.get("key")))
    migrated = {**plan, "questions": questions}
    if crossing:
        migrated["migrated_from_edition"] = from_edition
    if schema.get("edition"):
        migrated["schema_edition"] = schema["edition"]
    if schema.get("notes"):
        migrated["schema_notes"] = schema["notes"]
    return migrated, report


def rehome_visible_values(questions: list[dict[str, Any]], orphans: list[str] | None = None) -> None:
    """Each visible value goes with the box that now holds its text.

    A visible value is text that must show on the filing copy in its question's own boxes, so
    when migrate moves a box to another question, the value moves with it. A value whose text is
    in none of the plan's boxes stays where it was."""

    def box_text(question: dict[str, Any]) -> str:
        return " ".join(normalize_visible_text(str(value)) for value in dict(question.get("field_values") or {}).values())

    texts = [box_text(question) for question in questions]
    moves: list[tuple[int, int, str]] = []
    for here, question in enumerate(questions):
        for value in list(question.get("visible_values") or []):
            wanted = normalize_visible_text(str(value))
            if not wanted or wanted in texts[here]:
                continue
            there = next((index for index, text in enumerate(texts) if wanted in text), None)
            if there is not None:
                moves.append((here, there, value))
    for value in orphans or []:  # from an old question whose boxes all moved elsewhere
        wanted = normalize_visible_text(str(value))
        there = next((index for index, text in enumerate(texts) if wanted and wanted in text), None)
        if there is not None:
            moves.append((-1, there, value))
    for here, there, value in moves:
        if here >= 0:
            questions[here]["visible_values"] = [item for item in questions[here]["visible_values"] if item != value]
        target = questions[there].setdefault("visible_values", [])
        if value not in target:
            target.append(value)


def migrate_report_lines(report: dict[str, Any]) -> list[str]:
    lines = [f"migrated onto {report['schema']} ({report['edition'] or 'no edition'} schema)"]
    if report.get("from_edition"):
        lines.insert(
            0,
            f"EDITION CHANGE {report['from_edition']} -> {report['edition']}: the answers were moved by box name onto "
            f"another edition. {len(report['to_review'])} answered question(s) are now manual_review; check each "
            f"against the {report['edition']} instructions and set its status again.",
        )
    if report["new"]:
        lines.append(f"new questions, left missing for you to answer ({len(report['new'])}): {', '.join(report['new'])}")
    if report["moved"]:
        moves = sorted({f"{item['from']} -> {item['to']}" for item in report["moved"]})
        lines.append(f"boxes moved to the question that now owns them ({len(report['moved'])}): {'; '.join(moves)}")
    if report["kept_outside_schema"]:
        lines.append(
            "kept after the schema's questions (no place in the current schema; still filled as before): "
            + ", ".join(report["kept_outside_schema"])
        )
    for item in report["status_not_allowed"]:
        lines.append(f"status {item['status']!r} of {item['key']} is no longer allowed; use one of: {', '.join(item['allowed'])}")
    if len(lines) == 1:
        lines.append("nothing to change: the plan already matches its schema")
    return lines


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "migrate":
        path = Path(argv[1])
        rest = argv[2:]
        dry_run = "--dry-run" in rest
        profile_path = Path(rest[rest.index("--profile") + 1]) if "--profile" in rest[:-1] else None
        plan = json.loads(path.read_text(encoding="utf-8"))
        try:
            migrated, report = migrate_plan(
                plan, profile=load_profile(profile_path), across_editions="--across-editions" in rest
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if not dry_run:
            backup = path.with_name(path.name + ".premigrate")
            if not backup.exists():
                backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            path.write_text(json.dumps(migrated, indent=2) + "\n", encoding="utf-8")
        print("\n".join(migrate_report_lines(report) + ([] if dry_run else [f"wrote {path}"])))
        return 0
    if len(argv) >= 1 and argv[0] == "list":
        for name, schema in QUESTION_SCHEMAS.items():
            edition = f"\t{schema['edition']} edition" if schema.get("edition") else ""
            description = f"\t{schema['description']}" if schema.get("description") else ""
            print(f"{name}\t{schema['kind']}\t{len(schema['required_questions'])} questions{edition}{description}")
        return 0
    if len(argv) >= 2 and argv[0] == "skeleton":
        rest = argv[2:]
        force = "--force" in rest
        rest = [item for item in rest if item != "--force"]
        if not rest:
            print(json.dumps(skeleton_plan(argv[1]), indent=2))
            return 0
        if len(rest) == 2 and rest[0] == "--out":
            out = Path(rest[1])
            if out.exists() and not force:
                print(f"kept existing plan {out} (pass --force to replace it with a blank skeleton)", file=sys.stderr)
                return 1
            plan = skeleton_plan(argv[1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
            print(f"skeleton {argv[1]} ({len(plan['questions'])} questions) -> {out}")
            return 0
    if len(argv) == 3 and argv[0] == "fields":
        payload = save_field_list(Path(argv[1]), Path(argv[2]))
        print(f"{len(payload['fields'])} fields -> {argv[2]}")
        return 0
    print(
        "usage: form_question_schema.py list | skeleton SCHEMA [--out PLAN.json [--force]] | "
        "fields BLANK.pdf OUT.json | migrate PLAN.json [--dry-run] [--profile PROFILE.json] [--across-editions]",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

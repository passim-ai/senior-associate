"""The official USCIS blank a schema was built against, for tests that fill a real form.

    official_blank("i-485") -> Path | None

Looks for the blank whose sha256 matches the schema's field list (schemas/fields/<FORM>.json), in
order: the folder in $SA_FORMS_BLANKS, this folder's .blank-cache/, and the plugin's
evals/golden/blanks/ (present only in a development checkout). When none has it and
$SA_FORMS_OFFLINE is not set, it downloads the current blank from uscis.gov into .blank-cache/
(gitignored). It returns None, so the test can skip, when the blank can't be had offline or
uscis.gov now serves another edition (the edition check, editions.py, covers that case).
"""
from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import sys

FORMS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FORMS_DIR))

from forms_workflow import file_sha256  # noqa: E402

CACHE = Path(__file__).resolve().parent / ".blank-cache"
PLUGIN_ROOT = FORMS_DIR.parents[1]
_reasons: dict[str, str] = {}


def expected(form: str) -> tuple[str, str]:
    """(file name, sha256) of the blank the form's schemas were built against."""
    import download_uscis_forms as downloader
    from form_question_schema import QUESTION_SCHEMAS, load_field_list

    kind = form.strip().lower()
    for schema in QUESTION_SCHEMAS.values():
        if schema.get("kind") == kind and schema.get("field_list"):
            return downloader.spec_for(kind).pdf_name, load_field_list(schema["field_list"])["pdf_sha256"]
    raise KeyError(f"no schema with a field list for {form}")


def official_blank(form: str) -> Path | None:
    name, sha = expected(form)
    places = [Path(os.environ["SA_FORMS_BLANKS"])] if os.environ.get("SA_FORMS_BLANKS") else []
    places += [CACHE, PLUGIN_ROOT / "evals" / "golden" / "blanks"]
    for folder in places:
        candidate = folder / name
        if candidate.is_file() and file_sha256(candidate) == sha:
            return candidate
    if os.environ.get("SA_FORMS_OFFLINE"):
        _reasons[form] = f"{name} is not cached and SA_FORMS_OFFLINE is set"
        return None
    import download_uscis_forms as downloader

    CACHE.mkdir(exist_ok=True)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            downloader.download_form(downloader.spec_for(form), CACHE, include_instructions=False, overwrite=True)
    except Exception as exc:  # noqa: BLE001 - offline, or uscis.gov refused: the test skips
        _reasons[form] = f"could not download {name}: {exc}"
        return None
    candidate = CACHE / name
    if candidate.is_file() and file_sha256(candidate) == sha:
        return candidate
    _reasons[form] = f"uscis.gov now serves another {name} than the one the schema was built against"
    return None


def why_missing(form: str) -> str:
    return _reasons.get(form, f"no official {form.upper()} blank")


SAMPLE_BY_FORMAT = {
    "date": "01/02/2000",
    "zip": "62701",
    "zip_or_postal": "62701",
    "state": "IL",
    "a_number": "012345678",
    "ssn": "123456789",
    "receipt": "IOE0123456789",
    "i94": "12345678901",
    "online_account": "123456789012",
    "number": "12",
    "amount": "45.67",
}


def fictional_plan(schema_name: str, blank: Path, *, statuses: dict[str, str] | None = None) -> dict:
    """A skeleton of the schema with every question that can be filled filled with fictional values that
    fit their boxes (format and maxlen read from the official blank), and the rest pending signature or
    not applicable. `statuses` overrides a question's status (its boxes are then left blank)."""
    import formats
    from form_question_schema import skeleton_plan
    from pypdf import PdfReader
    import xfa_tools

    box_formats = formats.box_formats(blank)
    acro = xfa_tools.acro_fields_by_base(PdfReader(str(blank)))
    plan = skeleton_plan(schema_name)
    for question in plan["questions"]:
        allowed = question["allowed_statuses"]
        wanted = (statuses or {}).get(question["key"])
        if wanted or "filled" not in allowed or "pending_signature" in allowed:
            question["status"] = wanted or ("pending_signature" if "pending_signature" in allowed else "not_applicable")
            question["field_values"] = {name: "" for name in question["field_values"]}
            continue
        question["status"] = "filled"
        for name in question["field_values"]:
            base, _, index = name.partition("[")
            choices = question.get("choices", {}).get(name)
            specs = acro.get(base, [])
            spec = specs[int(index.rstrip("]"))] if index and specs else (specs[0] if specs else None)
            if choices:
                value = next(iter(choices.values()))
            elif spec is not None and spec.field_type == "/Ch":
                value = next((option for option in spec.on_states if option.strip()), "")
            elif box_formats.get(base) in SAMPLE_BY_FORMAT:
                value = SAMPLE_BY_FORMAT[box_formats[base]]
            else:
                value = "Sample"
            if spec is not None and spec.max_len:
                value = value[: spec.max_len]
            question["field_values"][name] = value
    return plan


def complete_plan(schema_name: str, statuses: dict[str, str] | None = None,
                  answers: dict[str, str] | None = None) -> dict:
    """A skeleton of the schema with every question filled (pending signature where it allows that)
    and each box it must fill answered: from `answers`, else a fictional placeholder. `statuses`
    sets a question's status instead. Offline: nothing is read from a blank."""
    from form_question_schema import skeleton_plan

    plan = skeleton_plan(schema_name)
    for item in plan["questions"]:
        allowed = item["allowed_statuses"]
        status = next(status for status in ("pending_signature", "filled", *allowed) if status in allowed)
        item["status"] = (statuses or {}).get(item["key"], status)
        for name in item["required_nonempty_fields_when_filled"]:
            item["field_values"][name] = (answers or {}).get(name, "Zztest")
    return plan


def check_schema_covers_the_form(test, schema_name: str, unanswered: set[str] = frozenset()) -> None:
    """Every box of the form belongs to exactly one question, but the `unanswered` ones (pre-printed),
    and every checkbox lists a choice for each of its on-states (a unittest.TestCase is passed as `test`)."""
    from form_question_schema import get_question_schema, load_field_list

    schema = get_question_schema(schema_name)
    fields = load_field_list(schema["field_list"])["fields"]
    owners: dict[str, list[str]] = {}
    by_base: dict[str, set[str]] = {}  # on-states the schema's choices give each checkbox name
    for key, spec in schema["required_questions"].items():
        for field in spec["required_fields"]:
            owners.setdefault(field, []).append(key)
            entry = fields[field.split("[")[0]]
            if entry["type"] == "/Btn":
                given = set(spec.get("choices", {}).get(field, {}).values())
                test.assertTrue(given, f"{key}: {field} has no choices")
                test.assertLessEqual(given, set(entry["states"]), f"{key}: {field}")
                by_base.setdefault(field.split("[")[0], set()).update(given)
    # Separate boxes of one name ([0], [1]...) each carry some of the name's on-states; together, all of them.
    for base, given in by_base.items():
        test.assertEqual(sorted(given), sorted(fields[base]["states"]), base)
    test.assertEqual({field: keys for field, keys in owners.items() if len(keys) > 1}, {})
    # Barcodes and push buttons (a ZIP Code lookup) are not answers.
    on_form = {name for name, entry in fields.items()
               if not name.startswith("PDF417") and "BBox" not in entry.get("states", [])}
    test.assertEqual(on_form - {field.split("[")[0] for field in owners}, set(unanswered))


def fill_and_check(test, kind: str, blank: Path, plan: dict) -> dict[str, str]:
    """Fill the official blank from the plan, verify both layers, run the box rules; return the
    stored values for the form's own audit."""
    import contextlib
    import io
    import tempfile

    import audit_prepared_forms as audit
    import forms_workflow
    import xfa_tools

    mapping = forms_workflow.flatten_filled_field_values(forms_workflow.plan_questions(plan))
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "filled.pdf"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = xfa_tools.write_filled_pdf(blank, out, mapping)
        test.assertEqual(xfa_tools.verify_output(out, result.fields, check_visible=True), {"xfa": {}, "visible": {}})
        values = audit.merged_values(out)
        test.assertEqual(audit.box_rule_findings(kind=kind, pdf_path=out, widget_pdf=out, values=values), [])
        dump = xfa_tools.field_dump(blank)
    test.assertEqual(
        {k: v for k, v in forms_workflow.mapping_field_check(mapping, dump).items() if v}, {}, "field check"
    )
    return values

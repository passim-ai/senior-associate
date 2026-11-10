#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Build a matter's USCIS forms from their question plans in one step.

    forms_workflow.py build MATTER [--slug SLUG] [--force] [--full]
    forms_workflow.py build MATTER --new "I-130=i130_family_petition" [--new ...] [--blank FORM ...]
    forms_workflow.py build MATTER --check-only [--audit-out PATH]
    forms_workflow.py build MATTER --allow-new-edition I-485=<open item id>
    forms_workflow.py build MATTER --refresh-blank I-485

Plans live in MATTER/output/working/vault/forms/<slug>/plans/<Name>.plan.json, one per
filing copy, named as the copy is: "I-130.plan.json" becomes output/deliverables/Forms/I-130.pdf
and "G-28 - Petitioner.plan.json" becomes "G-28 - Petitioner.pdf". The plan's `kind` names
the blank (output/working/forms/blank/I-130.pdf). A relative `fact_table_path` is read
from the vault folder, and an empty one means "form facts.json" there.

A build:
  1. downloads any missing blank and its instructions (forms-metadata.json records the edition);
  2. writes each plan's mapping (vault/forms/<slug>/mappings/) and the intent manifest;
  3. fills each form from its blank and verifies both layers;
  4. renders the filing copy into output/deliverables/Forms/;
  5. audits every form into vault/forms/<slug>/prepared forms audit.json, tying each error
     that is a deliberate gap to the open item its question names ("open_item");
  6. prints a summary of 25 lines or fewer. build log.json in the vault holds every note,
     verify mismatch and plan check; the audit JSON holds every finding.

Only forms whose answers (the plan's fill mapping) or blank changed since the last build are
refilled and re-rendered; build state.json in the vault keeps the hashes. --force rebuilds
all. The audit always covers every form, because some checks compare forms with each other.

A source edited outside build (in Acrobat, say) is never silently refilled: when an edit is in
neither the plan nor what build last wrote, the form is left as it is and the conflict reported.
Put the change in the plan (then build), or pass --force to discard the edit.

Every build checks each blank against the edition its schema was built for (editions.py) and fills
no other: the summary says what to do (--refresh-blank for an older blank; for a newer one, the
attorney's decision in the build log's suggested open item, then --allow-new-edition). The forms
README has the details.

Exit code 0 when every form verified and every audit error is tied to an item that is open in
output/deliverables/open-items.json; 1 when something still needs work; 2 on bad input.
"""
from __future__ import annotations

import argparse
from collections import Counter
import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import audit_prepared_forms as audit  # noqa: E402
import download_uscis_forms as downloader  # noqa: E402
import editions  # noqa: E402
from form_question_schema import QUESTION_SCHEMAS, load_profile, skeleton_plan  # noqa: E402
import forms_workflow as fw  # noqa: E402
import xfa_tools  # noqa: E402
from scripts.matter_state import sign_of_life  # noqa: E402


PLAN_SUFFIX = ".plan.json"
STATE_VERSION = 1
SUMMARY_LINES = 25
DETAIL_PER_FORM = 3
TOOLS_FINGERPRINT_FILES = ("xfa_tools.py",)  # what fills and renders; the mapping hash covers the rest


class BuildError(Exception):
    """Bad input: no plans, an unknown schema, an ambiguous vault folder."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return fw.file_sha256(path) if path.exists() else ""


def tools_fingerprint() -> str:
    here = Path(__file__).resolve().parent
    return sha256_bytes(b"".join((here / name).read_bytes() for name in TOOLS_FINGERPRINT_FILES))[:16]


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- layout


@dataclass
class Layout:
    matter: Path
    slug: str
    # The attorney profile. build reads only has_uscis_online_account (to settle the online
    # account questions) and, in a protected matter, mailing_address (the safe address check).
    profile_path: Path | None = None

    @property
    def profile(self) -> dict[str, Any]:
        path = self.profile_path or self.matter.parent / ".senior-associate" / "attorney-profile.json"
        return load_profile(path)

    @property
    def vault(self) -> Path:
        return self.matter / "output" / "working" / "vault" / "forms" / self.slug

    @property
    def plans(self) -> Path:
        return self.vault / "plans"

    @property
    def mappings(self) -> Path:
        return self.vault / "mappings"

    @property
    def manifest(self) -> Path:
        return self.vault / "form intent manifest.json"

    @property
    def audit(self) -> Path:
        return self.vault / "prepared forms audit.json"

    @property
    def state(self) -> Path:
        return self.vault / "build state.json"

    @property
    def log(self) -> Path:
        return self.vault / "build log.json"

    @property
    def facts(self) -> Path:
        return self.vault / "form facts.json"

    @property
    def blank_dir(self) -> Path:
        return self.matter / "output" / "working" / "forms" / "blank"

    @property
    def source_dir(self) -> Path:
        return self.matter / "output" / "working" / "forms" / "source"

    @property
    def forms_dir(self) -> Path:
        return self.matter / "output" / "deliverables" / "Forms"

    @property
    def ledger(self) -> Path:
        return self.matter / "output" / "deliverables" / "open-items.json"

    @property
    def review_audit(self) -> Path:
        return self.matter / "output" / "working" / "vault" / "review" / self.slug / "forms audit check.json"

    def rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.matter))
        except ValueError:
            return str(path)


def blank_name(kind: str) -> str:
    """The blank's file name for a form kind: i-130a -> I-130A.pdf (download_uscis_forms naming)."""
    try:
        return downloader.spec_for(kind).pdf_name
    except SystemExit:
        return f"{kind.upper()}.pdf"


def find_slug(matter: Path, requested: str | None, *, creating: bool) -> str:
    if requested:
        return requested
    root = matter / "output" / "working" / "vault" / "forms"
    candidates = sorted(path.parent.name for path in root.glob("*/plans") if path.is_dir()) if root.exists() else []
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        if creating:
            return "main"
        raise BuildError(
            f"No question plans in {root}/<slug>/plans/. Start them with "
            "--new 'I-130=i130_family_petition' (one --new per form)."
        )
    raise BuildError(f"Several plan folders under {root} ({', '.join(candidates)}); pass --slug.")


# --------------------------------------------------------------------------- forms


@dataclass
class FormJob:
    name: str
    plan_path: Path
    plan: dict[str, Any] | None = None
    kind: str = ""
    questions: list[dict[str, Any]] = field(default_factory=list)
    mapping: dict[str, str] = field(default_factory=dict)
    plan_sha: str = ""
    mapping_sha: str = ""
    blank_sha: str = ""
    error: str = ""  # this form could not be planned, filled or rendered
    reason: str = ""  # why it is rebuilt this time; "" when unchanged
    stale: str = ""  # check-only: why the filing copy may not match the plan
    plan_summary: dict[str, Any] = field(default_factory=dict)
    entry: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)  # every fill note, full text
    warnings: list[str] = field(default_factory=list)  # fill warnings worth a summary line
    verify: dict[str, Any] | None = None  # verify_output mismatches; None when not run
    render_note: str = ""
    seconds: float = 0.0
    edition: dict[str, Any] = field(default_factory=dict)  # editions.check_blank for its blank
    conflict: list[dict[str, str]] = field(default_factory=list)  # edits made outside build
    suggested_items: list[dict[str, Any]] = field(default_factory=list)  # open items to add
    unprintable: dict[str, str] = field(default_factory=dict)  # box -> letters the form's font can't print

    def blank(self, layout: Layout) -> Path:
        return layout.blank_dir / blank_name(self.kind)

    def source(self, layout: Layout) -> Path:
        return layout.source_dir / f"{self.name} source.pdf"

    def filing(self, layout: Layout) -> Path:
        return layout.forms_dir / f"{self.name}.pdf"

    def mapping_path(self, layout: Layout) -> Path:
        return layout.mappings / f"{self.name}.mapping.json"

    @property
    def verify_failures(self) -> int:
        if not self.verify:
            return 0
        return sum(len(self.verify.get(layer) or {}) for layer in ("xfa", "visible"))


def load_jobs(layout: Layout) -> list[FormJob]:
    jobs: list[FormJob] = []
    for path in sorted(layout.plans.glob(f"*{PLAN_SUFFIX}")):
        job = FormJob(name=path.name[: -len(PLAN_SUFFIX)], plan_path=path)
        raw = path.read_bytes()
        job.plan_sha = sha256_bytes(raw)
        try:
            plan = json.loads(raw)
            job.kind = str(plan["kind"]).strip().lower()
            job.questions = fw.plan_questions(plan)
        except (ValueError, KeyError, TypeError) as exc:
            job.error = f"plan not usable: {exc}"
            jobs.append(job)
            continue
        if not str(plan.get("fact_table_path") or "").strip() and layout.facts.exists():
            plan = {**plan, "fact_table_path": str(layout.facts)}
        job.plan = plan
        job.mapping = fw.flatten_filled_field_values(job.questions)
        job.mapping_sha = sha256_bytes(json.dumps(job.mapping, sort_keys=True).encode("utf-8"))
        jobs.append(job)
    return jobs


def ensure_blanks(layout: Layout, kinds: set[str]) -> tuple[dict[str, str], list[str]]:
    """Download each missing blank (with instructions); return ({kind: error}, [fetched names])."""
    errors: dict[str, str] = {}
    fetched: list[str] = []
    metadata_path = layout.blank_dir / "forms-metadata.json"
    metadata: dict[str, Any] = {}
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except ValueError:
            metadata = {}
    for kind in sorted(kind for kind in kinds if kind):
        try:
            spec = downloader.spec_for(kind)
        except SystemExit as exc:
            errors[kind] = str(exc)
            continue
        if (layout.blank_dir / spec.pdf_name).exists():
            continue
        layout.blank_dir.mkdir(parents=True, exist_ok=True)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                entry = downloader.download_form(spec, layout.blank_dir, include_instructions=True, overwrite=False)
        except Exception as exc:  # noqa: BLE001 - report it with the form, keep going
            errors[kind] = f"blank download failed: {exc}"
            continue
        metadata[spec.form_id] = entry
        fetched.append(spec.pdf_name)
    if fetched:
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return errors, fetched


def rebuild_reason(job: FormJob, previous: dict[str, Any] | None, layout: Layout, *, force: bool, tools: str) -> str:
    if force:
        return "forced"
    if not previous:
        return "new"
    if previous.get("tools") != tools:
        return "tools updated"
    if previous.get("blank_sha256") != job.blank_sha:
        return "blank changed"
    if previous.get("mapping_sha256") != job.mapping_sha:
        return "answers changed"
    for key, path in (("source_sha256", job.source(layout)), ("filing_sha256", job.filing(layout))):
        if not path.exists():
            return "output missing"
        if sha256_file(path) != previous.get(key):
            return "output changed outside build"
    if previous.get("verify") != "ok":
        return "last verify failed"
    return ""


def _same_value(planned: object, stored: object) -> bool:
    a, b = str(planned or "").strip(), str(stored or "").strip()
    if a == b:
        return True
    try:  # Adobe rewrites a number it calculates or formats ("52000" -> "52000.00")
        return float(a.replace(",", "")) == float(b.replace(",", ""))
    except ValueError:
        return False


def outside_edits(job: FormJob, layout: Layout, previous: dict[str, Any] | None) -> list[dict[str, str]]:
    """Values in the source that someone changed after build wrote it, and that the plan doesn't
    hold now either: the edits a refill from the plan would throw away.

    Compares the source's stored values with the answers build last wrote (kept in build state)
    and with the plan's current answers; a box that matches either is not an edit to keep.
    """
    source = job.source(layout)
    written = (previous or {}).get("mapping")
    if not source.exists() or not isinstance(written, dict):
        return []
    try:
        last = xfa_tools.resolve_mapping(source, dict(written))
        now_planned = xfa_tools.resolve_mapping(source, dict(job.mapping))
        stored = xfa_tools.stored_values(source)
        blank = job.blank(layout)
        blank_values = xfa_tools.stored_values(blank) if blank.exists() else {}
    except Exception:  # noqa: BLE001 - a source that can't be read is refilled as before
        return []
    edits: list[dict[str, str]] = []
    planned_bases: set[str] = set()
    by_hand = fw.payment_by_hand_bases(job.kind)

    def shown(key: str, value: object) -> str:
        # A card or bank detail is never copied into the build log, not even to report it.
        return "(card or bank detail, not shown)" if fw.field_base(key) in by_hand and str(value).strip() else str(value)

    for key in sorted(set(last) | set(now_planned)):
        planned_bases.add(fw.field_base(key))
        got = audit.field_value(stored, key)
        if _same_value(last.get(key, ""), got) or _same_value(now_planned.get(key, ""), got):
            continue
        edits.append({"field": key, "plan": str(now_planned.get(key, "")), "source": shown(key, got)})
    for key, value in sorted(stored.items()):
        base = fw.field_base(key)
        if not str(value).strip() or base in planned_bases or base.startswith("PDF417BarCode"):
            continue
        if _same_value(audit.field_value(blank_values, key), value):
            continue  # a default of the official blank
        edits.append({"field": key, "plan": "", "source": shown(key, value)})
    return edits


def fill_and_render(job: FormJob, layout: Layout) -> None:
    """Fill the source from the blank, verify both layers, render the filing copy."""
    started = time.monotonic()
    source, filing = job.source(layout), job.filing(layout)
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        try:
            result = xfa_tools.write_filled_pdf(job.blank(layout), source, dict(job.mapping))
        except ValueError as exc:
            job.error = f"fill stopped: {exc}"
            return
        job.notes = xfa_tools.fill_messages(result, full=True)
        job.warnings = [line for line in xfa_tools.fill_messages(result) if line.startswith("warning:")]
        job.verify = xfa_tools.verify_output(source, result.fields, check_visible=True)
        try:
            xfa_tools.render_filing_copy(source, filing)
        except SystemExit as exc:  # Ghostscript is missing
            job.error = str(exc)
        except subprocess.CalledProcessError as exc:
            job.error = f"render failed: Ghostscript exited {exc.returncode}"
    job.render_note = captured.getvalue().strip()
    job.seconds = round(time.monotonic() - started, 1)


def manual_result(job: FormJob, layout: Layout) -> dict[str, Any]:
    """Audit result for a form the bundled audit has no rules for."""
    return {
        "form": job.kind,
        "file": str(job.filing(layout)),
        "source_file": str(job.source(layout)),
        "coverage": "manual",
        "finding_count": 0,
        "manual_check": (
            "The bundled audit has no rules for this form. build filled it from its question plan and "
            "verified that the stored and visible values match the plan. Reviewer: check it line by line."
        ),
        "open_questions": [
            {
                "key": item["key"],
                "label": item["label"],
                "status": item["status"],
                "open_item": item.get("open_item", ""),
            }
            for item in fw.unresolved_questions(job.questions)
        ],
    }


def ledger_open_ids(layout: Layout) -> set[str] | None:
    """Open item ids in the matter's ledger; None when there is no ledger yet."""
    if not layout.ledger.exists():
        return None
    try:
        payload = json.loads(layout.ledger.read_text(encoding="utf-8"))
    except ValueError:
        return set()
    items = payload.get("items") if isinstance(payload, dict) else None
    return {
        str(item.get("id"))
        for item in (items if isinstance(items, list) else [])
        if isinstance(item, dict) and item.get("id") and item.get("status", "open") == "open"
    }


def run_audit_for(jobs: list[FormJob], layout: Layout, manifest_path: Path) -> dict[str, Any]:
    checks = [
        (job.kind, job.filing(layout))
        for job in jobs
        if not job.error and job.kind in audit.AUDITORS and job.filing(layout).exists()
    ]
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        payload = audit.run_audit(
            checks,
            manifest_path if manifest_path.exists() else None,
            profile=layout.profile,
            matter=layout.matter,
        )
    for job in jobs:
        if not job.error and job.kind not in audit.AUDITORS and job.filing(layout).exists():
            payload["results"].append(manual_result(job, layout))
    payload["result_count"] = len(payload["results"])
    return payload


# --------------------------------------------------------------------------- build


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def edition_gate(job: FormJob, blank: Path, allowed: dict[str, str]) -> bool:
    """Check the blank's edition; False (and job.error set) when it must not be filled.

    A blank the tools weren't built for is filled only when the attorney decided so
    (--allow-new-edition), and then only in the boxes that are the same on it as on the blank the
    tools know (editions.compare_boxes: name, kind of box, choices, length limit, page and place).
    Every other answer is withheld from the form; the edition check records which and why, and
    the audit holds the form until the plan records a box-by-box check of what was filled."""
    schema = str((job.plan or {}).get("question_schema") or "") or None
    job.edition = editions.check_blank(job.kind, blank, schema)
    if job.edition["status"] in editions.FILLABLE:
        return True
    if job.kind in allowed and not editions.is_older(job.edition):
        withheld = editions.compare_boxes(job.kind, blank, sorted(job.mapping), schema)
        job.edition.update(
            open_item=allowed[job.kind],
            withheld=withheld,
            filled_boxes=sorted(box for box in job.mapping if box not in withheld),
        )
        job.mapping = {box: value for box, value in job.mapping.items() if box not in withheld}
        job.mapping_sha = sha256_bytes(json.dumps(job.mapping, sort_keys=True).encode("utf-8"))
        return True
    item = editions.suggested_open_item(job.edition)
    text = f"not filled: {editions.problem_text(job.edition)} To fix it, {editions.fix_text(job.edition)}"
    if item is None:
        job.error = text
        return False
    job.suggested_items.append(item)
    job.error = (
        f"{text} ({item['id']}, in the build log). If the attorney decides to prepare it on this blank, rerun with "
        f"--allow-new-edition {job.kind.upper()}={item['id']}: it fills only the boxes that are the same on this blank, "
        "and the audit holds the form until the box-by-box check is recorded in the plan's new_edition_review."
    )
    return False


def unprintable_open_item(job: FormJob) -> dict[str, Any]:
    """The attorney's decision when a name or place holds a letter the form's own font can't print, in the
    open-items format. The id is per form, so the audit's finding and the ledger name the same item."""
    form = editions.form_label(job.kind)
    letters = sorted({part.split(" ")[0] for text in job.unprintable.values() for part in text.split(", ")})
    count = len(job.unprintable)
    return {
        "id": f"forms-letters-{re.sub(r'[^a-z0-9]+', '-', job.name.lower()).strip('-')}",
        "type": "attorney_decision",
        "title": f"The {form} can't print {', '.join(letters)}"[:79],
        "question": (
            f"The {form}'s own font can't print {', '.join(letters)}, so {count} box{'es were' if count != 1 else ' was'} "
            "left blank rather than respelled. How should the value go on the form?"
        ),
        "recommendation": (
            "Write it by hand on the printed form exactly as the passport's biographic page shows it; or tell Claude "
            "the spelling to type (the passport's machine-readable line, or a prior USCIS notice)."
        ),
        "detail": (
            f"Boxes left blank on {job.name}: {fw.capped(sorted(job.unprintable), 6)}. Every other answer is on the "
            "form. Nothing was transliterated."
        ),
        "needed_for": form,
        "blocks_filing": True,
        "status": "open",
        "stage": "forms_preparer",
    }


def letters_gate(job: FormJob, blank: Path) -> None:
    """Leave blank the boxes whose text holds a letter the form's own font can't print, and say so, instead of
    stopping the whole form at the first one. The answers stay in the plan."""
    try:
        job.unprintable = xfa_tools.unprintable_boxes(blank, dict(job.mapping))
    except Exception:  # a blank this check can't read: fill's own check still refuses an unprintable letter
        job.unprintable = {}
    if not job.unprintable:
        return
    job.mapping = {box: value for box, value in job.mapping.items() if box not in job.unprintable}
    job.mapping_sha = sha256_bytes(json.dumps(job.mapping, sort_keys=True).encode("utf-8"))
    item = unprintable_open_item(job)
    job.suggested_items.append(item)
    job.warnings.append(
        f"warning: {len(job.unprintable)} box(es) left blank because the form's font can't print a letter in them "
        f"({fw.capped(sorted(job.unprintable), 3)}); nothing is transliterated. Add the open item {item['id']} "
        "(in the build log) so the attorney decides how the value goes on the form."
    )


def parse_allowed_editions(values: list[str]) -> dict[str, str]:
    allowed: dict[str, str] = {}
    for value in values:
        if "=" not in value or not value.split("=", 1)[1].strip():
            raise BuildError(
                f"--allow-new-edition takes FORM=OPEN_ITEM_ID, as in 'I-485=forms-edition-i-485'; got {value!r}"
            )
        form, item = (part.strip() for part in value.split("=", 1))
        allowed[form.lower()] = item
    return allowed


def build(layout: Layout, *, force: bool = False, allow_new_edition: dict[str, str] | None = None) -> dict[str, Any]:
    started = time.monotonic()
    jobs = load_jobs(layout)
    if not jobs:
        raise BuildError(
            f"No question plans in {layout.plans} (files named <Name>{PLAN_SUFFIX}). Start them with "
            "--new 'I-130=i130_family_petition'."
        )
    blank_errors, fetched = ensure_blanks(layout, {job.kind for job in jobs if not job.error})
    state = load_json(layout.state, {})
    previous_forms = dict(state.get("forms") or {}) if state.get("version") == STATE_VERSION else {}
    previous_log = dict(load_json(layout.log, {}).get("forms") or {})
    tools = tools_fingerprint()

    entries: dict[str, dict[str, Any]] = {}
    new_state: dict[str, Any] = {}
    for job in jobs:
        sign_of_life(layout.matter, every=30)  # a long build keeps its run's lease fresh
        if job.error:
            continue
        blank = job.blank(layout)
        if job.kind in blank_errors or not blank.exists():
            job.error = blank_errors.get(job.kind) or f"blank not found: {layout.rel(blank)}"
            continue
        job.blank_sha = sha256_file(blank)
        if not edition_gate(job, blank, allow_new_edition or {}):
            continue
        letters_gate(job, blank)
        try:
            job.plan_summary, job.entry = fw.apply_plan(
                job.plan,
                mapping_out=job.mapping_path(layout),
                filing_copy=job.filing(layout),
                source_pdf=job.source(layout),
                blank_pdf=blank,
                fact_table_base=layout.vault,
                withheld=set(job.edition.get("withheld") or {}) | set(job.unprintable),
            )
        except (ValueError, KeyError) as exc:
            job.error = f"plan not usable: {exc}"
            continue
        if job.entry is not None and job.unprintable:
            job.entry["unprintable_boxes"] = dict(job.unprintable)
            job.entry["unprintable_open_item"] = job.suggested_items[-1]["id"]
        if job.entry is not None and job.edition.get("status") not in editions.FILLABLE:
            job.entry["edition_check"] = job.edition
        previous = previous_forms.get(job.name)
        job.reason = rebuild_reason(job, previous, layout, force=force, tools=tools)
        source = job.source(layout)
        if (
            not force
            and previous
            and source.exists()
            and sha256_file(source) != previous.get("source_sha256")
        ):
            edits = outside_edits(job, layout, previous)
            by_hand = fw.payment_by_hand_bases(job.kind)
            typed = [item["field"] for item in edits if fw.field_base(item["field"]) in by_hand]
            if typed:
                # Card or bank details typed into a payment form: never kept. Refill it from the plan,
                # which removes them from the source and the filing copy, and say so.
                job.reason = "card or bank details removed"
                job.warnings.append(
                    f"warning: removed card or bank details typed into the {job.kind.upper()} outside build "
                    f"({', '.join(typed)}); the payer writes them by hand on the printed form"
                )
                edits = []
            if edits:
                shown = "; ".join(
                    f"{item['field']}: plan {item['plan']!r}, source {item['source']!r}" for item in edits[:3]
                )
                job.conflict = edits
                job.error = (
                    f"edited outside build: {len(edits)} value(s) in {layout.rel(source)} differ from the plan "
                    f"({shown}{'; ...' if len(edits) > 3 else ''}). Put the change in the plan and build again, "
                    "or rebuild with --force to discard the edit."
                )
                new_state[job.name] = previous  # keep the record, so the conflict stays until resolved
                continue
        if job.reason:
            kept = list(job.warnings)
            fill_and_render(job, layout)
            job.warnings = kept + [line for line in job.warnings if line not in kept]
        else:
            old = previous_log.get(job.name, {})
            job.notes = list(old.get("fill_notes") or [])
            job.warnings = list((previous or {}).get("fill_warnings") or [])
            job.verify = old.get("verify") if old.get("verify") is not None else {"xfa": {}, "visible": {}}
        if job.error:
            continue
        entries[str(job.filing(layout))] = job.entry
        new_state[job.name] = {
            "kind": job.kind,
            "plan": layout.rel(job.plan_path),
            "plan_sha256": job.plan_sha,
            "mapping_sha256": job.mapping_sha,
            "blank": layout.rel(blank),
            "blank_sha256": job.blank_sha,
            "tools": tools,
            "source": layout.rel(job.source(layout)),
            "source_sha256": sha256_file(job.source(layout)),
            "filing_copy": layout.rel(job.filing(layout)),
            "filing_sha256": sha256_file(job.filing(layout)),
            "verify": "ok" if not job.verify_failures else "failed",
            "fill_warnings": job.warnings,
            "built_at": (previous or {}).get("built_at") if not job.reason else now(),
            # What build wrote, so an edit made outside build can be told from the plan.
            "mapping": job.mapping if job.reason else (previous or {}).get("mapping", job.mapping),
        }

    # Forms whose plan is gone: remove what build made for them, so only current forms remain.
    removed: list[str] = []
    planned = {job.name for job in jobs}
    for name, old in previous_forms.items():
        if name in planned:
            continue
        for key in ("filing_copy", "source"):
            path = layout.matter / str(old.get(key) or "")
            if old.get(key) and path.is_file():
                path.unlink()
                removed.append(layout.rel(path))
        (layout.mappings / f"{name}.mapping.json").unlink(missing_ok=True)

    # The manifest covers every planned form, and only those.
    layout.vault.mkdir(parents=True, exist_ok=True)
    fw.dump_json(layout.manifest, {"files": entries})

    payload = run_audit_for(jobs, layout, layout.manifest)
    fw.dump_json(layout.audit, payload)

    fw.dump_json(layout.state, {"version": STATE_VERSION, "built_at": now(), "forms": new_state})
    report = make_report(layout, jobs, payload, mode="build")
    report.update(
        {
            "fetched_blanks": fetched,
            "blank_errors": blank_errors,
            "removed": removed,
            "seconds": round(time.monotonic() - started, 1),
            "audit_path": str(layout.audit),
        }
    )
    write_log(layout.log, layout, jobs, report)
    return report


def check(layout: Layout, *, audit_out: Path | None = None) -> dict[str, Any]:
    """Re-verify and re-audit without changing any form (the reviewer's pass)."""
    started = time.monotonic()
    jobs = load_jobs(layout)
    if not jobs:
        raise BuildError(f"No question plans in {layout.plans}.")
    state = load_json(layout.state, {})
    previous_forms = dict(state.get("forms") or {}) if state.get("version") == STATE_VERSION else {}
    manifest = load_json(layout.manifest, {})

    for job in jobs:
        if job.error:
            continue
        blank, source, filing = job.blank(layout), job.source(layout), job.filing(layout)
        job.blank_sha = sha256_file(blank)
        previous = previous_forms.get(job.name)
        if not source.exists() or not filing.exists():
            job.error = f"not built: {layout.rel(filing if not filing.exists() else source)} is missing"
            continue
        if blank.exists():
            job.edition = editions.check_blank(job.kind, blank, str((job.plan or {}).get("question_schema") or "") or None)
        entry = dict(dict(manifest.get("files") or {}).get(str(filing)) or {})
        job.unprintable = {str(box): str(letters) for box, letters in dict(entry.get("unprintable_boxes") or {}).items()}
        if job.unprintable:
            job.mapping = {box: value for box, value in job.mapping.items() if box not in job.unprintable}
            job.mapping_sha = sha256_bytes(json.dumps(job.mapping, sort_keys=True).encode("utf-8"))
        built_on = dict(entry.get("edition_check") or {})
        # A form the attorney decided to prepare on this blank (--allow-new-edition): build filled
        # only its unchanged boxes, so the withheld ones are not expected on it.
        allowed = bool(built_on.get("open_item")) and built_on.get("sha256") == job.edition.get("sha256")
        if allowed:
            withheld = set(entry.get("withheld_boxes") or [])
            job.mapping = {box: value for box, value in job.mapping.items() if box not in withheld}
            job.mapping_sha = sha256_bytes(json.dumps(job.mapping, sort_keys=True).encode("utf-8"))
            job.edition = {**job.edition, **{k: built_on[k] for k in ("open_item", "withheld", "filled_boxes") if k in built_on}}
        if job.edition and job.edition["status"] not in editions.FILLABLE and not allowed:
            job.stale = editions.problem_text(job.edition)
        elif str(filing) not in dict(manifest.get("files") or {}):
            job.stale = "not in the intent manifest"
        elif previous is None:
            job.stale = "no build record (built by hand?)"
        elif previous.get("mapping_sha256") != job.mapping_sha:
            job.stale = "plan answers changed since the last build"
        elif previous.get("blank_sha256") != job.blank_sha:
            job.stale = "blank changed since the last build"
        elif sha256_file(filing) != previous.get("filing_sha256") or sha256_file(source) != previous.get("source_sha256"):
            job.stale = "filing copy or source changed outside build"
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            try:
                expected = xfa_tools.resolve_mapping(source, dict(job.mapping))
                job.verify = xfa_tools.verify_output(source, expected, check_visible=True)
            except ValueError as exc:
                job.error = f"verify could not run: {exc}"

    out = audit_out or layout.review_audit
    payload = run_audit_for(jobs, layout, layout.manifest)
    out.parent.mkdir(parents=True, exist_ok=True)
    fw.dump_json(out, payload)
    report = make_report(layout, jobs, payload, mode="check")
    report.update({"seconds": round(time.monotonic() - started, 1), "audit_path": str(out)})
    write_log(out.with_name("forms check log.json"), layout, jobs, report)
    report["log_path"] = str(out.with_name("forms check log.json"))
    return report


# --------------------------------------------------------------------------- report


def make_report(layout: Layout, jobs: list[FormJob], payload: dict[str, Any], *, mode: str) -> dict[str, Any]:
    by_file = audit.summarize_by_file(payload)
    ledger = ledger_open_ids(layout)
    tied_ids: list[str] = []
    for finding in payload.get("findings") or []:
        open_item = str(finding.get("open_item") or "")
        if finding.get("severity") == "error" and open_item and open_item not in tied_ids:
            tied_ids.append(open_item)
    not_in_ledger = [item for item in tied_ids if ledger is None or item not in ledger]
    errors_not_in_ledger = sum(
        1
        for finding in payload.get("findings") or []
        if finding.get("severity") == "error" and str(finding.get("open_item") or "") in not_in_ledger
    )
    forms = []
    for job in jobs:
        audited = by_file.get(str(job.filing(layout)))
        forms.append(
            {
                "name": job.name,
                "kind": job.kind,
                "schema": (job.plan or {}).get("question_schema") or "",
                "status_counts": dict(Counter(item["status"] for item in job.questions)),
                "reason": job.reason,
                "stale": job.stale,
                "error": job.error,
                "verify": None if job.verify is None else ("ok" if not job.verify_failures else "failed"),
                "verify_failures": job.verify_failures,
                "verify_lines": xfa_tools.verify_lines(job.verify or {}, limit=2) if job.verify_failures else [],
                "field_check": dict(job.plan_summary.get("field_check") or {}),
                "warnings": job.warnings,
                "edition": {
                    **{key: job.edition.get(key, "") for key in ("status", "file_edition", "schema_edition", "open_item")},
                    "filled": len(job.edition.get("filled_boxes") or []),
                    "withheld": sorted(job.edition.get("withheld") or {}),
                }
                if job.edition
                else {},
                "audit": None
                if audited is None
                else {
                    "coverage": audited.get("coverage", "audit"),
                    "errors": audited["errors"],
                    "tied": audited["tied"],
                    "warnings": audited["warnings"],
                    "open_items": audited["open_items"],
                    "untied": [audit.finding_brief(item) for item in audited["untied"]],
                },
            }
        )
    errors = int(payload.get("error_count") or 0)
    tied = int(payload.get("tied_error_count") or 0)
    return {
        "mode": mode,
        "matter": str(layout.matter),
        "slug": layout.slug,
        "forms": forms,
        "suggested_open_items": [item for job in jobs for item in job.suggested_items],
        "audit": {"errors": errors, "tied": tied, "warnings": int(payload.get("warning_count") or 0)},
        "tied_ids": tied_ids,
        "ledger_found": ledger is not None,
        "not_in_ledger": not_in_ledger,
        "errors_not_in_ledger": errors_not_in_ledger,
    }


def write_log(path: Path, layout: Layout, jobs: list[FormJob], report: dict[str, Any]) -> None:
    detail = {
        job.name: {
            "plan": str(job.plan_path),
            "reason": job.reason,
            "stale": job.stale,
            "error": job.error,
            "plan_summary": job.plan_summary,
            "fill_notes": job.notes,
            "verify": job.verify,
            "edited_outside_build": job.conflict,
            "render_output": job.render_note,
            "seconds": job.seconds,
        }
        for job in jobs
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    fw.dump_json(path, {"written_at": now(), "summary": report, "forms": detail})


def needs_work(report: dict[str, Any]) -> list[str]:
    forms = report["forms"]
    problems = []
    failed = [form for form in forms if form["error"]]
    if failed:
        problems.append(f"{len(failed)} form(s) not built")
    verify = sum(1 for form in forms if form["verify"] == "failed")
    if verify:
        problems.append(f"{verify} verify failure(s)")
    stale = sum(1 for form in forms if form["stale"])
    if stale:
        problems.append(f"{stale} stale form(s)")
    untied = report["audit"]["errors"] - report["audit"]["tied"]
    if untied:
        problems.append(f"{untied} untied audit error(s)")
    if report["not_in_ledger"]:
        problems.append(
            f"{report.get('errors_not_in_ledger', 0)} error(s) tied to {len(report['not_in_ledger'])} id(s) "
            "not open in the ledger"
        )
    checks = sum(1 for form in forms if form["field_check"])
    if checks:
        problems.append(f"field-check problems on {checks} form(s)")
    return problems


def detail_lines(form: dict[str, Any]) -> list[tuple[int, str]]:
    """(priority, text) lines that explain what needs work on one form; lower priority first."""
    lines: list[tuple[int, str]] = []
    if form["error"]:
        lines.append((0, f"! {form['error']}"[:220]))
    if form["stale"]:
        lines.append((1, f"! stale: {form['stale']}"))
    if form["verify_failures"]:
        lines.append((1, f"! verify: {form['verify_failures']} value(s) differ from the plan"))
        lines.extend((2, f"  {line.strip()}") for line in form["verify_lines"][:1])
    for line in fw.field_check_lines(form["field_check"], limit=3):
        lines.append((2, f"! {line}"))
    edition = form.get("edition") or {}
    if edition.get("open_item"):
        withheld = edition.get("withheld") or []
        lines.append((1, (
            f"! {edition.get('file_edition') or 'unknown'} edition (attorney's decision {edition['open_item']}): filled "
            f"{edition.get('filled', 0)} box(es) that are the same on it; withheld {len(withheld)} that changed"
            + (f" ({fw.capped(withheld, 3)})" if withheld else "")
            + "; record the box-by-box check in the plan's new_edition_review"
        )[:240]))
    for text in (form["audit"] or {}).get("untied", []):
        lines.append((3, f"! untied: {text}"))
    for text in form["warnings"]:
        lines.append((4, f"! fill {text}"[:240]))
    return lines


def summary_lines(report: dict[str, Any]) -> list[str]:
    layout = Layout(Path(report["matter"]), report["slug"])
    forms = report["forms"]
    width = min(max([len(form["name"]) for form in forms] + [4]), 24)
    if report["mode"] == "build":
        rebuilt = [form for form in forms if form["reason"] and not form["error"]]
        reasons = Counter(form["reason"] for form in rebuilt)
        head = f"Forms build, {report['matter']} (vault/forms/{report['slug']}): {len(forms)} form(s); rebuilt {len(rebuilt)}"
        if rebuilt:
            head += " (" + ", ".join(f"{count} {reason}" for reason, count in reasons.items()) + ")"
            if len(rebuilt) < len(forms):
                head += ": " + fw.capped([form["name"] for form in rebuilt], 4)
        head += f"; unchanged {sum(1 for form in forms if not form['reason'] and not form['error'])}"
        head += f"; {report.get('seconds', 0)} s"
    else:
        head = f"Forms check (no form changed), {report['matter']} (vault/forms/{report['slug']}): {len(forms)} form(s); {report.get('seconds', 0)} s"
    lines = [head]
    if report.get("fetched_blanks"):
        lines.append(f"Downloaded blanks: {fw.capped(report['fetched_blanks'], 6)}")

    rows: list[str] = []
    details: list[list[tuple[int, str]]] = []
    for form in forms:
        if form["error"] and form["verify"] is None:
            verify = "not built"
        elif form["verify"] == "ok":
            verify = "verify OK"
        elif form["verify"] == "failed":
            verify = f"verify FAILED ({form['verify_failures']})"
        else:
            verify = "not verified"
        audited = form["audit"]
        if audited is None:
            audit_text = "not audited"
        elif audited["coverage"] == "manual":
            audit_text = "no audit rules: reviewer checks by hand"
        else:
            audit_text = f"audit {audited['errors']} err ({audited['tied']} tied), {audited['warnings']} warn"
        rows.append(f"{form['name'][:width]:<{width}}  {fw.status_line(form['status_counts'])} | {verify} | {audit_text}")
        details.append(detail_lines(form)[:DETAIL_PER_FORM])

    footer: list[str] = []
    audit_totals = report["audit"]
    tied_text = (
        f"Open items: {audit_totals['tied']} of {audit_totals['errors']} audit error(s) tied to "
        f"{len(report['tied_ids'])} id(s)"
    )
    if report["not_in_ledger"]:
        where = "output/deliverables/open-items.json" if report["ledger_found"] else "the ledger (no open-items.json yet)"
        tied_text += f"; not open in {where}: {fw.capped(report['not_in_ledger'], 5)}"
    footer.append(tied_text)
    if report.get("suggested_open_items"):
        footer.append(
            "Open items to add (in the build log, under summary.suggested_open_items): "
            + fw.capped([item["id"] for item in report["suggested_open_items"]], 4)
        )
    problems = needs_work(report)
    footer.append(
        "Status: NEEDS WORK: " + "; ".join(problems)
        if problems
        else "Status: clean: every form verified, every audit error is tied to an open item in the ledger"
    )
    if report["mode"] == "build":
        rebuilt_names = [f"{form['name']}.pdf" for form in forms if form["reason"] and not form["error"]]
        unchanged = sum(1 for form in forms if not form["reason"] and not form["error"])
        forms_line = f"  {layout.rel(layout.forms_dir)}/: "
        forms_line += f"rebuilt {fw.capped(rebuilt_names, 3)}" if rebuilt_names else "nothing rebuilt"
        forms_line += f"; {unchanged} unchanged" if unchanged else ""
        footer.append("Wrote, under the matter folder:")
        footer.append(forms_line)
        if report.get("removed"):
            footer.append(f"  removed (plan gone): {fw.capped(report['removed'], 3)}")
        footer.append(f"  {layout.rel(layout.manifest)}")
        footer.append(f"  {layout.rel(layout.audit)}")
        footer.append(f"  {layout.rel(layout.log)} (every note, mismatch and plan check)")
    else:
        footer.append(f"Wrote: {layout.rel(Path(report['audit_path']))}")
        footer.append(f"       {layout.rel(Path(report['log_path']))}")

    budget = max(SUMMARY_LINES - len(lines) - len(rows) - len(footer), 0)
    flat = sorted(
        ((priority, index, order) for index, items in enumerate(details) for order, (priority, _) in enumerate(items)),
    )
    total = len(flat)
    shown = budget if total <= budget else max(budget - 1, 0)  # one line says how many are hidden
    keep = {(index, order) for _, index, order in flat[:shown]}
    for index, row in enumerate(rows):
        lines.append(row)
        for order, (_, text) in enumerate(details[index]):
            if (index, order) in keep:
                lines.append(f"    {text}")
    hidden = total - len(keep)
    if hidden > 0:
        lines.append(f"    (+{hidden} more line(s) in the build log and audit JSON)")
    return lines + footer


def print_report(report: dict[str, Any], *, full: bool) -> None:
    if full:
        print(json.dumps(report, indent=2))
    else:
        print("\n".join(summary_lines(report)))


# --------------------------------------------------------------------------- setup


PAYMENT_SCHEMAS = {"G-1450": "g1450_credit_card_payment", "G-1650": "g1650_ach_payment"}
G1145_SCHEMA = "g1145_e_notification"


def filing_method(matter: Path) -> str:
    """The matter's filing method (paper or online) from its settings; paper when unset."""
    plugin_root = str(Path(__file__).resolve().parents[2])
    if plugin_root not in sys.path:
        sys.path.insert(0, plugin_root)
    from scripts.matter_state import read_meta

    return str(read_meta(matter).get("filing_method") or "paper")


# A USCIS form number as fees.py writes it (I-130, I-130A, I-129F, N-400): never a path.
FORM_NUMBER_RE = re.compile(r"^[A-Z]{1,2}-\d{1,4}[A-Z]{0,3}$")
# What a fee is called in a plan name: letters, digits, spaces and the punctuation fee names use.
FEE_WORDS_RE = re.compile(r"[^A-Za-z0-9 .,()-]+")


@dataclass
class PaymentSpec:
    """One payment form for one fee: its plan name, schema, and the fee it pays."""

    name: str
    schema: str
    pays_for: str  # the form whose fee it pays ("I-765")
    what: str  # which fee ("filing fee", "Pub. L. 119-21 fee")
    amount: int  # whole dollars
    order: int  # its place in the fees tool's list, from 1: the order the payment forms go on top


def payment_plan_specs(fees_json: Path, payment_form: str) -> list[PaymentSpec]:
    """One payment form for each fee the fees tool says needs one, each with its own plan name.

    fees_json is the output of scripts/packet/fees.py --json (or --output): its
    `payment_forms_needed` lists one {"form", "what", "amount"} per separate payment of a paper
    filing: a form's filing fee, and each fee that must be paid apart from it (the I-765's
    Pub. L. 119-21 fee, say). A form can appear more than once (two applicants' I-485s). Each
    plan is named for the form and the fee ("G-1450 - I-765 Pub. L. 119-21 fee"), with "(1 of 2)"
    and so on when the same form and fee repeat, so no fee shares a payment form with another."""
    try:
        payload = json.loads(fees_json.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BuildError(f"--payments: can't read {fees_json}: {exc}") from exc
    if payment_form not in PAYMENT_SCHEMAS:
        raise BuildError(f"--payment-form is G-1450 (card) or G-1650 (bank account); got {payment_form!r}")
    fees: list[tuple[str, str, int]] = []
    for item in payload.get("payment_forms_needed") or []:
        form = str((item or {}).get("form") or "").strip().upper()
        what = " ".join(FEE_WORDS_RE.sub(" ", str((item or {}).get("what") or "fee")).split()) or "fee"
        amount = (item or {}).get("amount")
        if not FORM_NUMBER_RE.match(form):
            raise BuildError(f"--payments: {form or 'an entry'!r} in payment_forms_needed is not a form number such as I-130")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount <= 0 or amount != int(amount):
            raise BuildError(
                f"--payments: the {form} {what} amount must be a whole number of dollars above zero; got {amount!r}"
            )
        fees.append((form, what, int(amount)))
    totals = Counter((form, what.casefold()) for form, what, _ in fees)
    seen: Counter[tuple[str, str]] = Counter()
    specs = []
    for order, (form, what, amount) in enumerate(fees, start=1):
        key = (form, what.casefold())
        seen[key] += 1
        suffix = f" ({seen[key]} of {totals[key]})" if totals[key] > 1 else ""
        specs.append(
            PaymentSpec(f"{payment_form} - {form} {what}{suffix}", PAYMENT_SCHEMAS[payment_form], form, what, amount, order)
        )
    return specs


def payment_plan(spec: PaymentSpec, profile: dict[str, Any]) -> dict[str, Any]:
    """A payment form's skeleton with the fee it pays already in (the form, which fee, the amount):
    the only answers the tools give a payment form besides the names the preparer adds from the
    record. The payer's own questions (card or bank details, signature) start pending_signature."""
    plan = skeleton_plan(spec.schema, profile=profile)
    plan.update(pays_for=spec.pays_for, pays_what=spec.what, pays_amount=spec.amount, fee_order=spec.order)
    text = f"{spec.amount:,}"
    for question in plan["questions"]:
        if question["allowed_statuses"] == [fw.STATUS_PENDING_SIGNATURE]:
            # The card or bank details and the signature: only the payer writes them, by hand.
            question["status"] = fw.STATUS_PENDING_SIGNATURE
        if question["key"] == "payment_amount":
            question.update(
                status="filled",
                field_values={"AuthorizedPaymentAmt": text},
                visible_values=[text],
                notes=f"The {spec.pays_for} {spec.what}, from the fee schedule (fees.py).",
            )
    return plan


def planned_amount(plan: dict[str, Any]) -> str:
    """The amount a payment plan authorizes, as its plan holds it ("" when none)."""
    for question in plan.get("questions") or []:
        if isinstance(question, dict) and question.get("key") == "payment_amount":
            return str(dict(question.get("field_values") or {}).get("AuthorizedPaymentAmt") or "").strip()
    return ""


def refresh_blank(layout: Layout, form: str) -> str:
    """Move a matter's blank (and its instructions) aside into blank/superseded/, so the setup that
    follows downloads uscis.gov's current one. Returns a summary line."""
    kind = form.strip().lower()
    try:
        spec = downloader.spec_for(kind)
    except SystemExit as exc:
        raise BuildError(str(exc)) from exc
    blank = layout.blank_dir / spec.pdf_name
    if not blank.exists():
        return f"  refresh {spec.pdf_name}: no blank yet; downloading the current one"
    check = editions.check_blank(kind, blank)
    tag = check.get("file_edition", "").replace("/", "-") or sha256_file(blank)[:8]
    aside = layout.blank_dir / "superseded"
    aside.mkdir(parents=True, exist_ok=True)
    for path in (blank, layout.blank_dir / spec.instructions_name):
        if path.exists():
            path.replace(aside / f"{path.stem} ({tag}){path.suffix}")
    return f"  refresh {spec.pdf_name}: the {check.get('file_edition') or 'old'} blank moved to blank/superseded/"


def setup(
    layout: Layout,
    new: list[str],
    blanks: list[str],
    *,
    payments: Path | None = None,
    payment_form: str = "G-1450",
    refresh: list[str] | None = None,
) -> list[str]:
    """Write skeleton plans for new forms and fetch their blanks; return summary lines.

    A first setup of a paper filing also adds a G-1145 plan (e-notification when USCIS accepts the
    package); --payments adds one payment form plan per fee from the fees tool's output;
    --refresh-blank moves a blank aside and downloads the current one (an older edition than the
    tools know, say)."""
    lines = [f"Forms setup, {layout.matter} (vault/forms/{layout.slug}):"]
    kinds: set[str] = set()
    for form in refresh or []:
        lines.append(refresh_blank(layout, form))
        kinds.add(form.strip().lower())
    first_setup = not any(layout.plans.glob(f"*{PLAN_SUFFIX}")) if layout.plans.exists() else True
    new = list(new)
    if (
        new
        and first_setup
        and filing_method(layout.matter) == "paper"
        and not any(spec.split("=", 1)[-1].strip() == G1145_SCHEMA for spec in new)
    ):
        new.append(f"G-1145={G1145_SCHEMA}")
        lines.append("  paper filing: added a G-1145 plan, for USCIS's e-mail or text when it accepts the package")
    for spec in payment_plan_specs(payments, payment_form) if payments else []:
        kinds.add(QUESTION_SCHEMAS[spec.schema]["kind"])
        path = layout.plans / f"{spec.name}{PLAN_SUFFIX}"
        if path.exists():
            kept = planned_amount(load_json(path, {}))
            if kept.replace(",", "") != str(spec.amount):
                lines.append(
                    f"  ! plan kept (already exists), but it authorizes ${kept or '?'} and the {spec.pays_for} "
                    f"{spec.what} is now ${spec.amount:,}: update its amount: {layout.rel(path)}"
                )
            else:
                lines.append(f"  plan kept (already exists): {layout.rel(path)}")
            continue
        plan = payment_plan(spec, layout.profile)
        plan["fact_table_path"] = "form facts.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        lines.append(f"  plan: {layout.rel(path)} (pays the {spec.pays_for} {spec.what}, ${spec.amount:,})")
    for spec in new:
        if "=" not in spec:
            raise BuildError(f"--new takes NAME=SCHEMA, as in 'I-130=i130_family_petition'; got {spec!r}")
        name, schema = (part.strip() for part in spec.split("=", 1))
        if schema not in QUESTION_SCHEMAS:
            raise BuildError(f"Unknown schema {schema!r}. Known: {', '.join(sorted(QUESTION_SCHEMAS))}")
        kinds.add(QUESTION_SCHEMAS[schema]["kind"])
        path = layout.plans / f"{name}{PLAN_SUFFIX}"
        if path.exists():
            lines.append(f"  plan kept (already exists): {layout.rel(path)}")
            continue
        plan = skeleton_plan(schema, profile=layout.profile)
        plan["fact_table_path"] = "form facts.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        lines.append(f"  plan: {layout.rel(path)} ({schema}, {len(plan['questions'])} questions)")
        if not QUESTION_SCHEMAS[schema].get("field_list"):
            boxes = sum(len(question["field_values"]) for question in plan["questions"])
            lines.append(
                f"    partial schema: {boxes} boxes, high-signal questions only, no choices. Add a question for "
                "each other item you answer; find its boxes with dump-fields --acro --prefix <part>."
            )
    kinds.update(form.strip().lower() for form in blanks if form.strip())
    errors, fetched = ensure_blanks(layout, kinds)
    metadata = load_json(layout.blank_dir / "forms-metadata.json", {})
    for kind in sorted(kinds):
        if kind in errors:
            lines.append(f"  blank {kind}: {errors[kind]}")
            continue
        blank = layout.blank_dir / blank_name(kind)
        fw.load_field_dump(blank)  # saves output/working/forms/fields/<FORM>.json
        check = editions.check_blank(kind, blank)
        edition = check.get("file_edition") or (metadata.get(kind) or {}).get("edition_date") or "edition: see the PDF footer"
        how = "downloaded" if blank.name in fetched else "present"
        lines.append(f"  blank: {layout.rel(blank)} ({how}; {edition})")
        if check["status"] not in editions.FILLABLE:
            lines.append(f"    ! {editions.problem_text(check)} build will not fill it. To fix it, {editions.fix_text(check)}.")
    lines.append(
        "Next: fill each plan from the fact table (field_values; use `choices` for checkboxes; "
        "tie each deliberate gap to an open item with \"open_item\"), then run build without --new."
    )
    return lines


# --------------------------------------------------------------------------- CLI


def add_build_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("matter", type=Path, help="The matter folder (the one that holds output/).")
    parser.add_argument("--slug", help="Vault folder under output/working/vault/forms/ (default: the only one).")
    parser.add_argument(
        "--new",
        action="extend",
        nargs="+",
        default=[],
        metavar="NAME=SCHEMA",
        help="Set up: write a skeleton plan for this form and fetch its blank, e.g. 'G-28 - Petitioner=g28_represented_client'.",
    )
    parser.add_argument(
        "--blank", action="extend", nargs="+", default=[], metavar="FORM", help="Set up: fetch this blank (e.g. i-912)."
    )
    parser.add_argument(
        "--payments",
        type=Path,
        metavar="FEES.json",
        help="Set up: one payment form plan per fee in this output of scripts/packet/fees.py --json (its "
        "payment_forms_needed), with the amount and the form it pays for filled in. A relative path is inside "
        "the matter folder.",
    )
    parser.add_argument(
        "--payment-form",
        default="G-1450",
        help="With --payments: G-1450 (credit card, the default) or G-1650 (U.S. bank account).",
    )
    parser.add_argument(
        "--refresh-blank",
        action="extend",
        nargs="+",
        default=[],
        metavar="FORM",
        help="Set up: move this form's blank aside (blank/superseded/) and download uscis.gov's current one.",
    )
    parser.add_argument("--force", action="store_true", help="Refill and re-render every form.")
    parser.add_argument(
        "--allow-new-edition",
        action="extend",
        nargs="+",
        default=[],
        metavar="FORM=OPEN_ITEM",
        help="Fill this form on a blank the tools were not built for (the attorney decided so in this open item): "
        "only the boxes that are the same on that blank are filled, and the audit holds the form until the plan "
        "records a box-by-box check (new_edition_review).",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Change no form: re-verify, flag stale forms, rerun the audit into --audit-out.",
    )
    parser.add_argument(
        "--audit-out", type=Path, help="Audit JSON for --check-only (default vault/review/<slug>/forms audit check.json)."
    )
    parser.add_argument(
        "--profile",
        type=Path,
        help="The attorney profile (default: .senior-associate/attorney-profile.json in the matter's parent folder).",
    )
    parser.add_argument("--full", action="store_true", help="Print the whole report as JSON instead of the summary.")


def in_matter(matter: Path, path: Path | None) -> Path | None:
    """A path given on the command line: a relative one is inside the matter folder, wherever the
    command runs from (fees.py --output writes its file the same way)."""
    if path is None:
        return None
    path = path.expanduser()
    return (path if path.is_absolute() else matter / path).resolve()


def run(args: argparse.Namespace) -> int:
    matter = args.matter.expanduser().resolve()
    if not matter.is_dir():
        print(f"error: matter folder not found: {matter}", file=sys.stderr)
        return 2
    try:
        layout = Layout(
            matter,
            find_slug(matter, args.slug, creating=bool(args.new or args.blank or args.payments or args.refresh_blank)),
            profile_path=args.profile.expanduser().resolve() if getattr(args, "profile", None) else None,
        )
        if args.new or args.blank or args.payments or args.refresh_blank:
            print(
                "\n".join(
                    setup(
                        layout,
                        list(args.new),
                        list(args.blank),
                        payments=in_matter(matter, args.payments),
                        payment_form=args.payment_form.upper(),
                        refresh=list(args.refresh_blank),
                    )
                )
            )
            return 0
        if args.check_only:
            report = check(layout, audit_out=in_matter(matter, args.audit_out))
        else:
            report = build(layout, force=args.force, allow_new_edition=parse_allowed_editions(args.allow_new_edition))
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print_report(report, full=args.full)
    return 1 if needs_work(report) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_build_arguments(parser)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())

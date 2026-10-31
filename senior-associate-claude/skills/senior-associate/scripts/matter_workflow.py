#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import sys
from functools import partial
from typing import Any, Callable, Iterator

from scripts.matter_state import item_blocks_filing, now_iso, relative_to_matter, sha256_file, write_json_atomic
from scripts.privacy_cleanup import is_render_clutter
from scripts.privacy_lint import (
    SENSITIVE_TEXT_PATTERNS,
    lint_stage_completion,
    party_name_failures,
    protected_term_failures,
    scan_text,
    workspace_path_failures,
)


SCHEMA_VERSION = 8
STATE_RELATIVE_PATH = Path("output/working/workflow/matter_status.json")
# Matters started before the working-folder rename keep their state here.
LEGACY_STATE_ROOT = Path("output/shareable/workflow")
CASE_THEORY_MAP_NAME = "case_theory_evidence_map.json"
VALID_STAGE_STATUSES = {
    "pending",
    "in_progress",
    "passed",
    "failed",
    "blocked",
    "skipped",
}
VALID_BLOCKER_OWNERS = {"client", "attorney", "system", "agency", "third_party"}
# A path holding one of these (anywhere: "tmp/" covers every tmp folder) is scratch, which no pass may rely on.
EPHEMERAL_PATH_MARKERS = (
    "tmp/",
    "output/playwright/",
    "output/forms/.source_xfa/",
    "output/forms/editable_xfa/",
    "output/working/forms/.source_xfa/",
    "output/working/forms/editable_xfa/",
)
RESOLVED_FINDING_STATUSES = {
    "resolved",
    "closed",
    "fixed",
    "not_applicable",
    "no_finding",
    "accepted_risk",
    "waived",
}
MATERIAL_REVIEW_SEVERITIES = {"blocker", "major", "manual_review"}
CURABLE_ADJUDICATION_OUTCOMES = {"rfe_likely", "noid_likely", "attorney_hold"}
REVIEW_SEVERITIES = {"blocker", "major", "minor", "manual_review"}
ADJUDICATION_OUTCOMES = {"deny_likely", "noid_likely", "rfe_likely", "attorney_hold", "approvable"}
# A final-review merits risk the orchestrator must route somewhere, even when no cure exists (deny_likely goes to the attorney).
OWNED_ADJUDICATION_OUTCOMES = CURABLE_ADJUDICATION_OUTCOMES | {"deny_likely"}
_LINT_PATTERNS = dict(SENSITIVE_TEXT_PATTERNS)
# What a stage summary is kept with in place of each identifier, in this order: the privacy lint's patterns (the A-number
# one ignoring case here too), between a user's home path and any long number.
SUMMARY_REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"/Users/[^\s,;]+"), "[redacted-path]"),
    (re.compile(_LINT_PATTERNS["a_number"].pattern, re.IGNORECASE), "[redacted-a-number]"),
    (_LINT_PATTERNS["uscis_receipt"], "[redacted-receipt]"),
    (_LINT_PATTERNS["i94_number"], "[redacted-i94]"),
    (_LINT_PATTERNS["passport_number"], "[redacted-passport]"),
    (_LINT_PATTERNS["ssn"], "[redacted-ssn]"),
    (_LINT_PATTERNS["long_identifier"], "[redacted-passport-or-receipt]"),
    (_LINT_PATTERNS["email"], "[redacted-email]"),
    (_LINT_PATTERNS["phone"], "[redacted-phone]"),
    (_LINT_PATTERNS["dob_labeled"], "[redacted-dob]"),
    (_LINT_PATTERNS["date_numeric"], "[redacted-date]"),
    (_LINT_PATTERNS["date_long"], "[redacted-date]"),
    (_LINT_PATTERNS["street_address"], "[redacted-address]"),
    (re.compile(r"\b\d{7,}\b"), "[redacted-number]"),
)


@dataclass(frozen=True)
class StageDefinition:
    category: str
    # The step's name as the attorney reads it on the timeline (the app's step labels).
    label: str
    description: str


# Every stage, in the full packet's order.
STAGE_DEFINITIONS: dict[str, StageDefinition] = {
    "docs_review": StageDefinition("evidence", "Document review",
                                   "Inventory client/source documents and compare them against required and suggested evidence."),
    "forms_preparer": StageDefinition("forms", "Forms",
                                      "Prepare the USCIS forms from current official materials and source documents."),
    "forms_reviewer": StageDefinition("forms", "Forms review", "Run the skeptical forms review gate."),
    "cover_letter_writer_draft": StageDefinition("cover_letter", "Cover letter",
                                                 "Draft the cover letter from the closest model and matter facts."),
    "cover_letter_researcher": StageDefinition("cover_letter", "Research", "Build the authority pack for the draft."),
    "cover_letter_writer_integrate": StageDefinition("cover_letter", "Letter revision",
                                                     "Integrate the support pack into the draft."),
    "cover_letter_reviewer": StageDefinition("cover_letter", "Letter review",
                                             "Run the final skeptical cover-letter review gate."),
    "packet_assembly": StageDefinition("packet", "Packet", "Assemble the packet PDF and manifest."),
    "final_review": StageDefinition("review", "Final review",
                                    "Pre-filing QA and a strict officer's merits read of the assembled packet, in one pass."),
    "attorney_handoff": StageDefinition("handoff", "Your memo", "Write the attorney memo, the client request list, and the "
                                        "open-items ledger for the packet as it stands."),
}


def stage_phrase(stage_id: str) -> str:
    """The step as the middle of a plain sentence: "The forms review sent the forms back to be redone." """
    definition = STAGE_DEFINITIONS.get(stage_id)
    if definition is None:
        return stage_id
    # "Your memo" already says whose it is.
    return definition.label.lower() if stage_id == "attorney_handoff" else f"the {definition.label.lower()}"


def reroute_line(reset: list[str], detected_in_stage_id: str | None) -> str:
    """The one timeline line a reroute writes, in plain words."""
    redone = stage_phrase(reset[0])
    if detected_in_stage_id and detected_in_stage_id != reset[0]:
        finder = stage_phrase(detected_in_stage_id)
        return f"{finder[:1].upper()}{finder[1:]} sent {redone} back to be redone."
    return f"Redoing {redone}" + (" and the steps after it." if len(reset) > 1 else ".")


WORKFLOW_TEMPLATES: dict[str, list[str]] = {
    "full_packet": list(STAGE_DEFINITIONS),
    "forms_only": ["forms_preparer", "forms_reviewer"],
    "docs_review_only": ["docs_review"],
    "cover_letter_only": ["cover_letter_writer_draft", "cover_letter_researcher", "cover_letter_writer_integrate",
                          "cover_letter_reviewer"],
    "packet_build": ["packet_assembly", "final_review"],
    "final_review_only": ["final_review"],
}

# What each stage needs before it can start (schema 8). The forms review and the cover letter both start once the
# forms exist, so they run side by side; the packet waits for both reviews. A workflow that leaves stages out
# inherits their dependencies (a stage depends on its nearest required ancestors), so "packet_build" makes the
# final review wait on the packet and nothing else.
STAGE_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "docs_review": (),
    "forms_preparer": ("docs_review",),
    "forms_reviewer": ("forms_preparer",),
    "cover_letter_writer_draft": ("forms_preparer",),
    "cover_letter_researcher": ("cover_letter_writer_draft",),
    "cover_letter_writer_integrate": ("cover_letter_researcher",),
    "cover_letter_reviewer": ("cover_letter_writer_integrate",),
    "packet_assembly": ("forms_reviewer", "cover_letter_reviewer"),
    "final_review": ("packet_assembly",),
    "attorney_handoff": ("final_review",),
}

# The work each review checks. A review may be skipped only when that work was itself skipped (or the attorney
# approved it); the handoff reviews the whole matter, so it follows the final review.
REVIEWED_STAGE: dict[str, tuple[str, ...]] = {
    "forms_reviewer": ("forms_preparer",),
    "cover_letter_reviewer": ("cover_letter_writer_integrate", "cover_letter_writer_draft"),
    "final_review": ("packet_assembly",),
    "attorney_handoff": ("final_review",),
}

# A review that sends work back to the same stage more than this many times in one run stops sending it back:
# what is left becomes an open item, so an unattended run can't loop.
REROUTE_LIMIT = 2

ROLLBACK_TARGETS: dict[str, str] = {
    "forms_defect": "forms_preparer",
    "cover_letter_defect": "cover_letter_writer_draft",
    "packet_assembly_defect": "packet_assembly",
    "final_review_defect": "final_review",
}


SAFE_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")


# Older layouts kept the state here; the current one is STATE_RELATIVE_PATH.
LEGACY_STATE_PATHS = (LEGACY_STATE_ROOT / "matter_status.json", Path("output/workflow/matter_status.json"))


def state_progress(path: Path) -> int:
    """How far a workflow record got: the number of stages that started. -1 when it can't be read or a newer
    runtime wrote it. An older schema counts, so loading it refuses it in words rather than starting over beside it."""
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("schema_version") not in range(1, SCHEMA_VERSION + 1):
            return -1
        stages = state.get("stages") or {}
        return sum(
            1
            for record in stages.values()
            if isinstance(record, dict) and str(record.get("status") or "pending") != "pending"
        )
    except Exception:
        return -1


def default_state_path(matter_path: Path) -> Path:
    """The matter's workflow record. The current layout wins, unless it never got past the start and an older
    layout's record holds the work (a matter resumed by a newer app that wrote an empty record beside it)."""
    current = matter_path / STATE_RELATIVE_PATH
    legacy = [matter_path / relative for relative in LEGACY_STATE_PATHS if (matter_path / relative).is_file()]
    if not legacy:
        return current
    best = max(legacy, key=state_progress)
    if not current.exists():
        # Before this layout existed, the older record is the record, if this runtime can read it.
        return best if state_progress(best) >= 0 else current
    if state_progress(current) > 0:
        return current
    return best if state_progress(best) > 0 else current


def validate_workflow_slug(workflow_slug: str) -> str:
    slug = workflow_slug.strip()
    if not SAFE_SLUG_RE.fullmatch(slug):
        raise ValueError(
            "workflow_slug must start with a letter or number and contain only letters, numbers, dots, hyphens, or underscores."
        )
    if slug in {".", ".."}:
        raise ValueError("workflow_slug cannot be '.' or '..'.")
    return slug


def workflow_state_path(matter_path: Path, workflow_slug: str | None = None) -> Path:
    if workflow_slug is None or not workflow_slug.strip():
        return default_state_path(matter_path)
    slug = validate_workflow_slug(workflow_slug)
    current = matter_path / "output" / "working" / "workflow" / slug / "matter_status.json"
    legacy = matter_path / LEGACY_STATE_ROOT / slug / "matter_status.json"
    if not current.exists() and legacy.exists():
        return legacy
    return current


def case_theory_map_path_for_state_path(state_path: Path) -> Path:
    return state_path.parent / CASE_THEORY_MAP_NAME


def stage_template(stage_id: str) -> dict[str, Any]:
    stage_def = STAGE_DEFINITIONS[stage_id]
    return {
        "stage_id": stage_id,
        "display_name": stage_id.replace("_", " ").title(),
        "category": stage_def.category,
        "description": stage_def.description,
        "status": "pending",
        "started_at": None,
        "completed_at": None,
        "summary": None,
        "summary_redacted": False,
        "artifacts": [],
        "artifact_records": [],
        "evidence_files": [],
        "evidence_records": [],
        "open_blocker_ids": [],
        "history": [],
        # The last time this stage passed: its artifacts and a hash snapshot of the matter, kept through
        # reroutes so a re-review can check its earlier findings and only what changed (changed-since).
        "last_pass": None,
        # Every attempt's start, end and length, kept through reroutes, so time estimates come from real runs.
        "timing": {"attempts": [], "total_seconds": 0},
    }


def validate_stage_ids(stage_ids: list[str]) -> list[str]:
    if not stage_ids:
        raise ValueError("At least one required stage is required.")
    seen: set[str] = set()
    validated: list[str] = []
    for stage_id in stage_ids:
        if stage_id not in STAGE_DEFINITIONS:
            raise ValueError(f"Unknown stage: {stage_id}")
        if stage_id in seen:
            raise ValueError(f"Duplicate stage: {stage_id}")
        seen.add(stage_id)
        validated.append(stage_id)
    return validated


def workflow_stage_ids(workflow_key: str, custom_stage_ids: list[str] | None = None) -> tuple[str, list[str]]:
    if custom_stage_ids:
        return "custom", validate_stage_ids(custom_stage_ids)
    if workflow_key not in WORKFLOW_TEMPLATES:
        raise ValueError(f"Unknown workflow template: {workflow_key}")
    return workflow_key, list(WORKFLOW_TEMPLATES[workflow_key])


def normalized_text(value: str) -> str:
    """An intake value as stored: trimmed, with runs of spaces and line breaks as one space."""
    return " ".join(str(value or "").split())


def intake_key(value: Any) -> str:
    """An intake value as compared: case, spacing, and line breaks don't make a different case."""
    return " ".join(str(value or "").split()).casefold()


def compare_state_to_intake(
    state: dict[str, Any],
    *,
    matter_type: str | None = None,
    filing_posture: str | None = None,
    deliverable: str | None = None,
    workflow_key: str | None = None,
    custom_stage_ids: list[str] | None = None,
) -> list[str]:
    """Where the record says otherwise than this intake, one line each. An option left out isn't compared, and the
    workflow is compared only when a key or a stage list is given."""
    asked = {"matter_type": matter_type, "filing_posture": filing_posture, "deliverable": deliverable}
    stage_ids = None
    if workflow_key or custom_stage_ids:
        asked["workflow_key"], stage_ids = workflow_stage_ids(workflow_key or "full_packet", custom_stage_ids)
    recorded = state["matter"]
    # The folder isn't compared: a matter moved or renamed in Finder is the same matter, and ensure records
    # where it is now (record_matter_folder).
    mismatches = [
        f"{key}: recorded {recorded.get(key)!r}, asked for {normalized_text(value)!r}"
        for key, value in asked.items()
        if value is not None and intake_key(recorded.get(key)) != intake_key(value)
    ]
    actual_stage_ids = list(state.get("required_stage_ids", []))
    if stage_ids is not None and actual_stage_ids != stage_ids:
        mismatches.append(f"required_stage_ids: recorded {actual_stage_ids!r}, asked for {stage_ids!r}")
    return mismatches


def record_matter_folder(state: dict[str, Any], matter_path: Path) -> bool:
    """Point the record at the folder it is in now, after a move or a rename. True when it changed."""
    current = str(matter_path.resolve())
    matter = state.setdefault("matter", {})
    previous = matter.get("matter_folder")
    if previous == current:
        return False
    matter["matter_folder"] = current
    append_history(state, "matter_folder_moved", previous_folder=previous, matter_folder=current)
    return True


def resolve_path_for_matter(matter_path: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return matter_path / path


def normalize_summary(summary: str) -> tuple[str, bool]:
    cleaned = " ".join(summary.strip().split())
    sanitized = cleaned
    for pattern, replacement in SUMMARY_REDACTION_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized, sanitized != cleaned


def _ends(*suffixes: str) -> Callable[[str], bool]:
    return lambda path: path.endswith(suffixes)


def _within(folder: str) -> Callable[[str], bool]:
    return lambda path: folder in path


# What an artifact is: the reason of the first rule its path (lower case, forward slashes) meets.
ARTIFACT_REASONS: tuple[tuple[Callable[[str], bool], str], ...] = (
    (_ends("form facts.json"), "forms_fact_table"),
    (_ends("form intent manifest.json"), "forms_intent_manifest"),
    (_ends("prepared forms audit.json"), "forms_audit"),
    (_ends(CASE_THEORY_MAP_NAME), "case_theory_evidence_map"),
    (_ends("attorney memo.md"), "attorney_memo"),
    (_ends("client request.md"), "client_request"),
    (_ends("open-items.json"), "open_items"),
    (_ends("docs review memo.md"), "docs_review_memo"),
    (_ends("document inventory.json"), "document_inventory"),
    (_ends("docs review checklist.json"), "docs_review_checklist"),
    (_ends("forms review memo.md"), "forms_review_memo"),
    (_ends("forms review findings.json"), "forms_review_findings"),
    (lambda path: path.endswith("audit.json") and "cover letter" in path, "cover_letter_audit"),
    (lambda path: path.endswith((".docx", ".pdf")) and "cover letter" in path, "cover_letter_output"),
    (_ends("authority pack.md"), "authority_pack"),
    (_ends("support matrix.json"), "support_matrix"),
    (_ends("cover letter review memo.md"), "cover_letter_review_memo"),
    (_ends("cover letter review findings.json"), "cover_letter_review_findings"),
    # Only the delivered packet counts: a draft render, an exhibit split, or a file that merely has "packet" in its
    # name somewhere else doesn't.
    (lambda path: path.startswith("output/deliverables/filing packet") and path.endswith(".pdf"), "packet_pdf"),
    (_ends("letter check.json"), "letter_check"),
    (_ends("packet manifest.json"), "packet_manifest"),
    (_ends("final review memo.md"), "final_review_memo"),
    (_ends("final review findings.json"), "final_review_findings"),
    (_ends("packet review memo.md"), "packet_review_memo"),
    (_ends("packet review findings.json"), "packet_review_findings"),
    (_ends("adjudicator memo.md"), "adjudicator_memo"),
    (_ends("reroute matrix.json"), "reroute_matrix"),
    (_within(".source_xfa/"), "source_xfa"),
    (_within("editable_xfa/"), "editable_xfa"),
    (_within("output/working/workflow/"), "workflow_output"),
    (_within("output/working/vault/docs-review/"), "docs_review_artifact"),
    (_within("output/working/vault/cover-letter/"), "cover_letter_artifact"),
    (_within("output/working/vault/research/"), "research_artifact"),
    (_within("output/working/vault/packet/"), "packet_artifact"),
    (_within("output/working/vault/review/"), "review_artifact"),
    (_within("output/working/vault/final-review/"), "final_review_artifact"),
    (_within("output/working/vault/adjudicator/"), "adjudicator_artifact"),
    (_within("output/working/vault/"), "vault_artifact"),
    (_within("output/deliverables/"), "deliverable"),
)


def classify_artifact_path(path_value: str) -> dict[str, str]:
    lower_value = path_value.replace("\\", "/").casefold()
    ephemeral = any(marker in lower_value for marker in EPHEMERAL_PATH_MARKERS)
    reason = next((reason for test, reason in ARTIFACT_REASONS if test(lower_value)),
                  "ephemeral_helper_output" if ephemeral else "general_output")
    return {"path": path_value, "retention": "ephemeral" if ephemeral else "durable", "reason": reason}


def classify_paths(paths: list[str], *, matter_path: Path) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for raw_path in paths:
        relative_path = relative_to_matter(matter_path, resolve_path_for_matter(matter_path, raw_path))
        records.append(classify_artifact_path(relative_path))
    return records


def append_history(target: dict[str, Any], event: str, **details: Any) -> None:
    entry = {
        "timestamp": now_iso(precise=True),
        "event": event,
    }
    if details:
        entry["details"] = details
    target.setdefault("history", []).append(entry)


def matter_metadata(
    *,
    matter_path: Path,
    matter_type: str,
    filing_posture: str,
    deliverable: str,
    workflow_key: str,
) -> dict[str, Any]:
    return {
        "matter_folder": str(matter_path.resolve()),
        "matter_type": normalized_text(matter_type),
        "filing_posture": normalized_text(filing_posture),
        "deliverable": normalized_text(deliverable),
        "workflow_key": workflow_key,
    }


# The words in an intake (its case type and deliverable) that say what is being filed, by the term they set.
INTAKE_WORDS: dict[str, tuple[str, ...]] = {
    "vawa": ("vawa", "self-petition", "self petition"),
    "i360": ("i-360", "i360", "vawa", "self-petition", "self petition"),
    "family": ("i-130", "i130", "immediate relative", "spouse", "family"),
    "spouse": ("spouse", "marriage", "husband", "wife", "i-130a", "i130a"),
    "sponsor": ("family", "spouse"),
    "adjustment": ("i-485", "i485", "adjustment", "adjust status"),
    "affidavit": ("i-864", "i864", "affidavit of support"),
    "work_permit": ("i-765", "i765", "employment authorization"),
    "travel": ("i-131", "i131", "advance parole", "travel document"),
    "conditions": ("i-751", "i751", "remove conditions"),
    "waiver": ("i-751", "i751", "waiver", "remove conditions"),
    "naturalization": ("n-400", "n400", "naturalization"),
    "packet": ("packet",),
}


def intake_terms(matter_type: str, deliverable: str) -> set[str]:
    text = f"{matter_type} {deliverable}".casefold()
    terms = {term for term, words in INTAKE_WORDS.items() if any(word in text for word in words)}
    if "i360" in terms:
        # An I-360 self-petition takes the place of an I-130, so words like "spouse" in its description don't add one.
        terms -= {"family", "sponsor"}
    return terms


def expected_forms_from_intake(matter_type: str, deliverable: str) -> list[str]:
    terms = intake_terms(matter_type, deliverable)
    forms: list[str] = []
    if "i360" in terms:
        forms += ["G-28", "I-360"]
    if "family" in terms:
        # The I-130A goes with every spouse petition; an "immediate relative" intake may be a spouse, parent or child.
        forms += ["G-28", "I-130", "I-130A" if "spouse" in terms else "I-130A if the beneficiary is a spouse"]
    if "adjustment" in terms:
        forms += ["G-28", "I-485"]
        if "family" in terms:
            forms.append("I-864")
        # VAWA self-petitioners need no I-864; they request the exemption in I-485 Part 3 (I-485 instructions).
        if "vawa" in terms:
            forms.append("I-765 if the client wants a work permit while the I-485 is pending")
    forms += [form for term, form in (("affidavit", "I-864"), ("work_permit", "I-765"), ("travel", "I-131"),
                                      ("conditions", "I-751"), ("naturalization", "N-400")) if term in terms]
    if not forms and "packet" in terms:
        forms.append("G-28")
    return list(dict.fromkeys(forms))


# The evidence a filing needs, in the order the docs review lists it: (the intake terms that call for it, any one of
# them, or none for every filing; category; purpose).
EVIDENCE_CATEGORIES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    ((), "identity_and_status", "Identity, nationality, admission, current status, and government identity numbers."),
    (("vawa",), "abuser_status_and_relationship",
     "The abuser's U.S. citizenship or LPR status, and the qualifying relationship: spouse or former spouse, child, or "
     "parent of a U.S. citizen son or daughter 21 or older."),
    (("vawa",), "shared_residence", "That the self-petitioner lived with the abuser, now or in the past."),
    (("vawa",), "battery_or_extreme_cruelty",
     "Battery or extreme cruelty by the abuser during the relationship, shown by any credible evidence."),
    (("vawa",), "good_moral_character",
     "The self-petitioner's affidavit, with police clearances from each place lived six months or more in the three "
     "years before filing (age 14 and over)."),
    (("vawa",), "good_faith_marriage", "For a self-petitioning spouse, that the marriage was entered in good faith."),
    (("vawa",), "derivative_children", "Birth records for any unmarried children under 21 included on the self-petition."),
    (("family",), "petitioner_status", "U.S. citizen or LPR petitioner status, as required by the petition theory."),
    (("family",), "qualifying_relationship", "Marriage, parent-child, or other qualifying family relationship evidence."),
    (("family",), "bona_fide_relationship",
     "Evidence that supports the bona fides of the claimed relationship when required or helpful."),
    (("adjustment",), "adjustment_eligibility",
     "Inspection/admission or parole, immigrant basis, visa availability if applicable, and no unresolved bars."),
    (("adjustment",), "inadmissibility_and_discretion",
     "Record evidence for inadmissibility, public charge, criminal, immigration-violation, and discretionary issues."),
    (("affidavit", "sponsor"), "financial_sponsorship",
     "Sponsor household size, tax years, current income, assets if needed, and sponsor domicile."),
    (("waiver",), "waiver_or_joint_filing_record",
     "Conditional residence posture, good-faith marriage evidence, divorce or abuse/extreme-hardship proof if applicable."),
    ((), "filing_logistics", "Signatures, fees, photos, sealed medicals, translations, filing address, and physical assembly notes."),
)


def required_evidence_categories(matter_type: str, deliverable: str) -> list[dict[str, str]]:
    terms = intake_terms(matter_type, deliverable)
    return [{"category": category, "purpose": purpose} for needs, category, purpose in EVIDENCE_CATEGORIES
            if not needs or terms.intersection(needs)]


def build_case_theory_evidence_map(
    *,
    matter_path: Path,
    matter_type: str,
    filing_posture: str,
    deliverable: str,
    workflow_key: str,
    required_stage_ids: list[str],
) -> dict[str, Any]:
    expected_forms = expected_forms_from_intake(matter_type, deliverable)
    return {
        "schema_version": 1,
        "generated_at": now_iso(precise=True),
        **matter_metadata(matter_path=matter_path, matter_type=matter_type, filing_posture=filing_posture,
                          deliverable=deliverable, workflow_key=workflow_key),
        "source": "senior_associate_intake",
        "privacy_note": "This map is generated from explicit intake only. It should not contain copied client facts.",
        "benefit_request": normalized_text(matter_type),
        "legal_mechanism": "",
        "burden_of_proof": "preponderance_of_the_evidence_unless_a_specific_standard_applies",
        "expected_forms": expected_forms,
        "required_stage_ids": list(required_stage_ids),
        "eligibility_elements": [],
        "required_evidence_categories": required_evidence_categories(matter_type, deliverable),
        "known_missing_documents": [],
        "likely_weak_points": [],
        "attorney_questions": [],
        "specialist_notes": {
            "docs_review": "Inventory client/source documents and refine required versus suggested evidence before downstream drafting or assembly.",
            "forms_preparer": "Refine expected forms and required evidence before filling PDFs.",
            "cover_letter": "Use this map to keep the requested relief, evidence theory, and exhibit list aligned.",
            "final_review": "Use this map as intake framing and a checklist, not as proof of eligibility; verify against current official USCIS sources and the final packet.",
        },
    }


def ensure_case_theory_evidence_map(
    *,
    matter_path: Path,
    state: dict[str, Any],
    state_path: Path,
) -> Path:
    path = case_theory_map_path_for_state_path(state_path)
    matter = state["matter"]
    if not path.exists():
        payload = build_case_theory_evidence_map(
            matter_path=matter_path,
            matter_type=str(matter.get("matter_type") or ""),
            filing_posture=str(matter.get("filing_posture") or ""),
            deliverable=str(matter.get("deliverable") or ""),
            workflow_key=str(matter.get("workflow_key") or ""),
            required_stage_ids=required_stage_ids(state),
        )
        write_json_atomic(path, payload)
    state["case_theory_evidence_map"] = {
        "path": relative_to_matter(matter_path, path),
        "status": "draft",
        "generated_from": "explicit_intake",
    }
    return path


def initialize_state(
    *,
    matter_path: Path,
    matter_type: str,
    filing_posture: str,
    deliverable: str,
    workflow_key: str,
    custom_stage_ids: list[str] | None = None,
) -> dict[str, Any]:
    resolved_workflow_key, required_stage_ids = workflow_stage_ids(workflow_key, custom_stage_ids)
    now = now_iso(precise=True)
    state = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now,
        "updated_at": now,
        "overall_status": "in_progress",
        "current_stage": None,
        "next_stage": required_stage_ids[0],
        "matter": matter_metadata(
            matter_path=matter_path,
            matter_type=matter_type,
            filing_posture=filing_posture,
            deliverable=deliverable,
            workflow_key=resolved_workflow_key,
        ),
        "required_stage_ids": required_stage_ids,
        "stages": {stage_id: stage_template(stage_id) for stage_id in required_stage_ids},
        "blockers": [],
        "history": [],
    }
    # The case type lives in the intake block ("matter") and nowhere else in this file: a protected matter's
    # record shouldn't name it twice.
    append_history(
        state,
        "matter_initialized",
        workflow_key=resolved_workflow_key,
        required_stage_ids=required_stage_ids,
    )
    refresh_derived_fields(state)
    return state


def save_state(state_path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = now_iso(precise=True)
    write_json_atomic(state_path, state)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def damaged_record_message(state_path: Path, why: str) -> str:
    """The plain error for a workflow record that exists but can't be read: it is never treated as a matter that
    hasn't started, and never written over."""
    return (
        f"This matter's workflow record can't be read ({state_path}): {why}. Nothing was changed. In a run, stop "
        "here and report it; don't write a new record over it. When the attorney asked you to repair the matter: if "
        "the damage is only a cut-off end or a stray character and the whole record is still there, fix the file so "
        "it parses and run status again; otherwise move it aside (rename it matter_status.damaged.json, beside it) "
        "and start the record again with ensure and the matter's intake. The client's documents and the finished "
        "files stay; the steps run again."
    )


def load_state(state_path: Path) -> dict[str, Any]:
    """The workflow record. One from another schema is refused: every record in use is schema 8."""
    if not state_path.exists():
        raise FileNotFoundError(f"Workflow state file not found: {state_path}")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        raise ValueError(damaged_record_message(state_path, "it isn't text")) from None
    except json.JSONDecodeError as exc:
        raise ValueError(damaged_record_message(state_path, f"it isn't valid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno})")) from None
    if not isinstance(state, dict) or not isinstance(state.get("stages"), dict) or not isinstance(state.get("required_stage_ids"), list):
        raise ValueError(damaged_record_message(state_path, "it doesn't hold a workflow record (no stages)"))
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported schema_version {state.get('schema_version')} in workflow state {state_path}; expected {SCHEMA_VERSION}."
        )
    return state


def required_stage_ids(state: dict[str, Any]) -> list[str]:
    return list(state["required_stage_ids"])


def stage_record(state: dict[str, Any], stage_id: str) -> dict[str, Any]:
    stages = state["stages"]
    if stage_id not in stages:
        raise ValueError(f"Stage {stage_id} is not required for this matter.")
    return stages[stage_id]


def open_blockers(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [blocker for blocker in state["blockers"] if blocker["status"] == "open"]


def open_blockers_for_stage(state: dict[str, Any], stage_id: str) -> list[dict[str, Any]]:
    return [blocker for blocker in open_blockers(state) if blocker["stage_id"] == stage_id]


DONE_STATUSES = {"passed", "skipped"}


def stage_dependencies(state: dict[str, Any]) -> dict[str, list[str]]:
    """Each required stage's dependencies among the required stages (STAGE_DEPENDENCIES, with left-out stages
    replaced by their own dependencies)."""
    required = required_stage_ids(state)
    present = set(required)

    def project(stage_id: str, seen: frozenset[str]) -> list[str]:
        result: list[str] = []
        for dependency in STAGE_DEPENDENCIES.get(stage_id, ()):
            if dependency in present:
                result.append(dependency)
            elif dependency not in seen:
                result.extend(project(dependency, seen | {dependency}))
        return result

    return {stage_id: _unique(project(stage_id, frozenset({stage_id}))) for stage_id in required}


def dependents_of(state: dict[str, Any], stage_id: str) -> list[str]:
    """The stage and every stage that depends on it, directly or through others, in workflow order."""
    dependencies = stage_dependencies(state)
    found = {stage_id}
    changed = True
    while changed:
        changed = False
        for candidate, needs in dependencies.items():
            if candidate not in found and found.intersection(needs):
                found.add(candidate)
                changed = True
    return [candidate for candidate in required_stage_ids(state) if candidate in found]


def unmet_dependencies(state: dict[str, Any], stage_id: str) -> list[tuple[str, str]]:
    """(dependency, its status) for each dependency of stage_id that hasn't passed or been skipped."""
    return [
        (dependency, stage_record(state, dependency)["status"])
        for dependency in stage_dependencies(state).get(stage_id, [])
        if stage_record(state, dependency)["status"] not in DONE_STATUSES
    ]


def running_stage_ids(state: dict[str, Any]) -> list[str]:
    return [stage_id for stage_id in required_stage_ids(state) if stage_record(state, stage_id)["status"] == "in_progress"]


def ready_stage_ids(state: dict[str, Any]) -> list[str]:
    """Stages that can start now: not started (or failed), with every dependency passed or skipped. Nothing is
    ready while a blocker is open."""
    if open_blockers(state):
        return []
    return [
        stage_id
        for stage_id in required_stage_ids(state)
        if stage_record(state, stage_id)["status"] in {"pending", "failed", "blocked"}
        and not unmet_dependencies(state, stage_id)
    ]


def compute_overall_status(state: dict[str, Any]) -> str:
    if open_blockers(state):
        return "blocked"
    stage_statuses = [stage_record(state, stage_id)["status"] for stage_id in required_stage_ids(state)]
    if any(status == "blocked" for status in stage_statuses):
        return "blocked"
    if all(status in DONE_STATUSES for status in stage_statuses):
        # A packet nobody gave its final review isn't finished, however the other steps ended.
        if "final_review" in state["stages"] and stage_record(state, "final_review")["status"] != "passed":
            return "incomplete"
        return "passed"
    # A stage that failed beside one still running isn't the matter's last word yet.
    if any(status == "in_progress" for status in stage_statuses):
        return "in_progress"
    if any(status == "failed" for status in stage_statuses):
        return "failed"
    return "in_progress"


def compute_current_stage(state: dict[str, Any]) -> str | None:
    for status in ("in_progress", "blocked", "failed"):
        for stage_id in required_stage_ids(state):
            if stage_record(state, stage_id)["status"] == status:
                return stage_id
    return compute_next_stage(state)


def compute_next_stage(state: dict[str, Any]) -> str | None:
    """The first stage to run: one left in progress (resume it), else the first ready one."""
    if open_blockers(state):
        return None
    running = running_stage_ids(state)
    if running:
        return running[0]
    ready = ready_stage_ids(state)
    return ready[0] if ready else None


def refresh_derived_fields(state: dict[str, Any]) -> None:
    state["overall_status"] = compute_overall_status(state)
    state["current_stage"] = compute_current_stage(state)
    state["next_stage"] = compute_next_stage(state)
    state["running"] = running_stage_ids(state)
    state["ready"] = ready_stage_ids(state)
    state["stage_dependencies"] = stage_dependencies(state)


def blocker_id(state: dict[str, Any]) -> str:
    return f"BLK-{len(state['blockers']) + 1:03d}"


# ---------------------------------------------------------------------------
# Timing: every attempt at a stage, and per-run totals
# ---------------------------------------------------------------------------

TELEMETRY_RUN_LIMIT = 50


def _seconds_between(start: str | None, end: str | None) -> float | None:
    try:
        return round((datetime.fromisoformat(str(end)) - datetime.fromisoformat(str(start))).total_seconds(), 1)
    except (TypeError, ValueError):
        return None


def stage_timing(stage: dict[str, Any]) -> dict[str, Any]:
    timing = stage.get("timing")
    if not isinstance(timing, dict) or not isinstance(timing.get("attempts"), list):
        timing = stage["timing"] = {"attempts": [], "total_seconds": 0}
    return timing


def begin_attempt(stage: dict[str, Any], *, now: str, run_id: str | None) -> None:
    timing = stage_timing(stage)
    for attempt in timing["attempts"]:
        if not attempt.get("ended_at") and not attempt.get("outcome"):
            attempt["outcome"] = "restarted"
    timing["attempts"].append({"started_at": now, "ended_at": None, "seconds": None, "outcome": None, "run_id": run_id or ""})


def end_attempt(state: dict[str, Any], stage_id: str, *, now: str, outcome: str, run_id: str | None) -> float | None:
    """Close the open attempt and add its length to the stage and to its run's totals. None when the stage
    never started (a pending stage skipped or blocked)."""
    stage = stage_record(state, stage_id)
    timing = stage_timing(stage)
    attempt = next((a for a in reversed(timing["attempts"]) if not a.get("ended_at") and not a.get("outcome")), None)
    if attempt is None:
        return None
    seconds = _seconds_between(attempt.get("started_at"), now)
    attempt.update({"ended_at": now, "seconds": seconds, "outcome": outcome})
    timing["total_seconds"] = round(sum(float(a.get("seconds") or 0) for a in timing["attempts"]), 1)
    stage["duration_seconds"] = seconds
    runs = state.setdefault("telemetry", {}).setdefault("runs", [])
    key = run_id or attempt.get("run_id") or "interactive"
    run = next((r for r in runs if r.get("run_id") == key), None)
    if run is None:
        run = {"run_id": key, "first_started_at": attempt.get("started_at"), "last_ended_at": now, "stage_seconds": 0, "stages": {}}
        runs.append(run)
        del runs[:-TELEMETRY_RUN_LIMIT]
    run["first_started_at"] = min(str(run.get("first_started_at") or now), str(attempt.get("started_at") or now))
    run["last_ended_at"] = now
    run["stage_seconds"] = round(float(run.get("stage_seconds") or 0) + float(seconds or 0), 1)
    run["stages"][stage_id] = round(float(run["stages"].get(stage_id) or 0) + float(seconds or 0), 1)
    run["wall_seconds"] = _seconds_between(run["first_started_at"], now)
    return seconds


def start_stage(state: dict[str, Any], stage_id: str, *, run_id: str | None = None) -> None:
    stage = stage_record(state, stage_id)
    if open_blockers(state):
        raise ValueError("Cannot start a stage while there are open blockers.")
    unmet = unmet_dependencies(state, stage_id)
    if unmet:
        dependency, status = unmet[0]
        raise ValueError(
            f"Cannot start {stage_id} before {dependency} is passed or skipped; current status is {status}."
        )
    if stage["status"] in DONE_STATUSES:
        raise ValueError(f"Cannot start {stage_id}; it is already {stage['status']}.")
    now = now_iso(precise=True)
    # started_at is when the current attempt began; earlier attempts stay in timing.
    stage["started_at"] = now
    stage["completed_at"] = None
    stage["status"] = "in_progress"
    begin_attempt(stage, now=now, run_id=run_id)
    append_history(stage, "stage_started")
    append_history(state, "stage_started", stage_id=stage_id)
    refresh_derived_fields(state)


def close_stage_blockers(
    state: dict[str, Any],
    stage_id: str,
    *,
    resolution_note: str,
) -> None:
    for blocker in open_blockers_for_stage(state, stage_id):
        blocker["status"] = "resolved"
        blocker["resolved_at"] = now_iso(precise=True)
        blocker["resolution_note"] = resolution_note
        stage = stage_record(state, stage_id)
        if blocker["id"] in stage["open_blocker_ids"]:
            stage["open_blocker_ids"].remove(blocker["id"])


def existing_paths_for_reason(records: list[dict[str, str]], reason: str, *, matter_path: Path) -> list[Path]:
    """The artifacts of one kind a stage recorded, that exist."""
    paths = [resolve_path_for_matter(matter_path, record["path"]) for record in records if record.get("reason") == reason]
    return [path for path in paths if path.exists()]


def json_artifacts(failures: list[str], paths: list[Path], label: str) -> Iterator[tuple[Path, Any]]:
    """Each artifact's JSON, with its path. One that can't be read is a failure, and is skipped."""
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            failures.append(f"Could not read {label} JSON artifact at {path}: {exc}")
            continue
        yield path, payload


def open_items_by_id(matter_path: Path) -> dict[str, dict[str, Any]]:
    """The open items in the matter's ledger, by id, for gaps a stage may leave on purpose."""
    try:
        payload = json.loads((matter_path / "output" / "deliverables" / "open-items.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return {}
    return {
        str(item.get("id")): item
        for item in items
        if isinstance(item, dict) and item.get("id") and item.get("status", "open") == "open"
    }


def form_number_pattern(form: str) -> re.Pattern[str] | None:
    """A pattern for a form number as people write it ("I-485", "i485"), not matching a longer one ("I-130A")."""
    match = re.fullmatch(r"\s*([A-Za-z]{1,2})-?(\d+)([A-Za-z]?)\s*", form or "")
    if not match:
        return None
    prefix, number, suffix = match.groups()
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(prefix)}-?{number}{re.escape(suffix)}(?![A-Za-z0-9])", re.IGNORECASE)


OPEN_ITEM_FORM_FIELDS = ("title", "question", "detail", "needed_for", "recommendation")


def open_item_concerns_form(item: dict[str, Any], form: str) -> bool:
    """True when the item is about this form: its words name it, or its "forms" list does. An audit error on the
    I-485 can't be explained away by an unrelated item about the I-130."""
    pattern = form_number_pattern(form)
    if pattern is None:
        return True  # nothing to compare against; the tie stands as the audit wrote it
    listed = item.get("forms")
    if isinstance(listed, list) and any(pattern.search(str(value)) for value in listed):
        return True
    return any(pattern.search(str(item.get(field) or "")) for field in OPEN_ITEM_FORM_FIELDS)


def packet_status_line(matter_path: Path) -> str | None:
    """'draft, N item(s) block filing' or 'ready to file', from the ledger; None before there is one."""
    try:
        payload = json.loads((matter_path / "output" / "deliverables" / "open-items.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict) or payload.get("packet_status") not in PACKET_STATUSES:
        return None
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    blocking = sum(1 for item in items if item_blocks_filing(item))
    if payload["packet_status"] == "ready_to_file" and not blocking:
        return "ready to file"
    return f"draft, {blocking} item(s) block filing"


def validate_clean_forms_audit(failures: list[str], audit_paths: list[Path], *, matter_path: Path) -> None:
    # A draft packet may leave a field blank when the record lacks the fact, as long as the gap is on the
    # attorney's open items ledger: the audit error then carries "open_item": "<id>", and that item has to be
    # about the same form. Any other error blocks.
    ledger = open_items_by_id(matter_path)
    for path, payload in json_artifacts(failures, audit_paths, "forms audit"):
        findings = payload.get("findings") if isinstance(payload, dict) else None
        if isinstance(findings, list):
            unexplained: list[dict[str, Any]] = []
            mismatched: list[str] = []
            for finding in findings:
                if not isinstance(finding, dict) or finding.get("severity") != "error":
                    continue
                item_id = str(finding.get("open_item") or "")
                item = ledger.get(item_id)
                if item is None:
                    unexplained.append(finding)
                elif finding.get("form") and not open_item_concerns_form(item, str(finding["form"])):
                    mismatched.append(f"{item_id} for the {str(finding['form']).upper()}")
            if unexplained:
                titles = "; ".join(str(f.get("title") or "untitled") for f in unexplained[:5])
                failures.append(
                    f"Forms audit has {len(unexplained)} error(s) not tied to an open item ({titles}): {path}"
                )
            if mismatched:
                failures.append(
                    "Forms audit ties errors to open items that don't mention that form ("
                    + "; ".join(mismatched[:5])
                    + "). Tie each error to an item about the same form, naming the form in its title, detail, "
                    f"or needed_for: {path}"
                )
        elif not isinstance(payload, dict):
            failures.append(f"Forms audit JSON must be an object: {path}")
        elif int(payload.get("error_count") or 0) > 0:
            failures.append(f"Forms audit has unresolved errors: {path}")


def validate_clean_cover_letter_audit(failures: list[str], audit_paths: list[Path]) -> None:
    for path, payload in json_artifacts(failures, audit_paths, "cover-letter audit"):
        if not isinstance(payload, dict):
            failures.append(f"Cover-letter audit JSON must be an object: {path}")
        elif int(payload.get("finding_count") or 0) > 0 or int(payload.get("error_count") or 0) > 0:
            failures.append(f"Cover-letter style/render audit has unresolved findings: {path}")


# The letter's source, beside its letter check in vault/cover-letter/<slug>/.
LETTER_SOURCE_NAME = "cover letter.md"


def validate_letter_check(failures: list[str], check_paths: list[Path]) -> None:
    """The mechanical letter check the writer runs before review: zero errors."""
    for path, payload in json_artifacts(failures, check_paths, "letter check"):
        if not isinstance(payload, dict):
            failures.append(f"Letter check JSON must be an object: {path}")
            continue
        errors = payload.get("errors")
        count = len(errors) if isinstance(errors, list) else 0
        try:
            count = max(count, int(payload.get("error_count") or 0))
        except (TypeError, ValueError):
            failures.append(f"Letter check error_count must be a number: {path}")
        if errors is None and "error_count" not in payload:
            failures.append(f"Letter check JSON needs an 'errors' list or an 'error_count': {path}")
        elif count:
            failures.append(f"Letter check has {count} error(s); fix the letter and run the check again: {path}")
        source = path.parent / LETTER_SOURCE_NAME
        if source.is_file() and source.stat().st_mtime > path.stat().st_mtime + 1:
            failures.append(
                f"The letter changed after its letter check ran ({LETTER_SOURCE_NAME} is newer); run the check again: {path}"
            )


def validate_packet_manifest(failures: list[str], manifest_paths: list[Path], *, matter_path: Path) -> None:
    for path, payload in json_artifacts(failures, manifest_paths, "packet manifest"):
        if not isinstance(payload, dict):
            failures.append(f"Packet manifest JSON must be an object: {path}")
            continue
        exhibits = payload.get("exhibits")
        if not isinstance(exhibits, list) or not exhibits:
            failures.append(f"Packet manifest has no exhibit list: {path}")
        packet_pdf = str(payload.get("packet_pdf") or "").strip()
        if packet_pdf and not resolve_path_for_matter(matter_path, packet_pdf).exists():
            failures.append(f"Packet manifest references a missing packet PDF: {packet_pdf}")
        page_count = payload.get("total_packet_pages", payload.get("total_pages"))
        if page_count is not None:
            try:
                if int(page_count) <= 0:
                    failures.append(f"Packet manifest reports a non-positive page count: {path}")
            except (TypeError, ValueError):
                failures.append(f"Packet manifest reports a non-numeric page count: {path}")


def list_payload_items(
    payload: Any,
    *,
    keys: tuple[str, ...],
    label: str,
    path: Path,
    failures: list[str],
) -> list[Any] | None:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        failures.append(f"{label} JSON must be an object or list: {path}")
        return None
    for key in keys:
        if key in payload:
            items = payload[key]
            if not isinstance(items, list):
                failures.append(f"{label} JSON field {key!r} must be a list: {path}")
                return None
            return items
    failures.append(f"{label} JSON must contain one of these top-level lists: {', '.join(keys)}.")
    return None


def item_is_resolved(item: dict[str, Any]) -> bool:
    if item.get("resolved") is True:
        return True
    status = str(
        item.get("status")
        or item.get("resolution")
        or item.get("finding_status")
        or item.get("issue_status")
        or ""
    ).strip().casefold()
    return status in RESOLVED_FINDING_STATUSES


def item_owner_or_target(item: dict[str, Any]) -> str:
    return str(
        item.get("owner")
        or item.get("reroute_target")
        or item.get("target")
        or item.get("responsible_role")
        or item.get("assignee")
        or item.get("recommended_owner")
        or ""
    ).strip()


# Reviewers don't all use the contract's four words. Normalize first, so "critical" or "high" can't skip the
# owner check that "blocker" gets. A word not listed here counts as material: it has to name an owner too.
SEVERITY_SYNONYMS = {
    "blocker": "blocker", "critical": "blocker", "high": "blocker", "severe": "blocker", "fatal": "blocker",
    "major": "major", "medium": "major", "moderate": "major", "significant": "major", "important": "major",
    "minor": "minor", "low": "minor", "trivial": "minor", "cosmetic": "minor",
    "manual_review": "manual_review", "manual": "manual_review", "attorney_review": "manual_review",
    "needs_review": "manual_review", "check_by_hand": "manual_review",
    "info": "info", "informational": "info", "note": "info", "none": "info",
}


def normalize_severity(value: Any) -> str:
    """The contract's severity for a reviewer's word; "" when there is none, "unknown" when it isn't recognized."""
    key = "_".join(str(value or "").strip().casefold().replace("-", " ").split())
    if not key:
        return ""
    return SEVERITY_SYNONYMS.get(key, "unknown")


def finding_outcome(item: dict[str, Any]) -> str:
    return str(item.get("likely_outcome") or item.get("outcome") or "").strip().casefold()


def finding_is_material(item: dict[str, Any], *, final_review: bool = False) -> bool:
    """A finding that matters to filing: a material severity, or a merits outcome that isn't approvable."""
    outcome = finding_outcome(item)
    if outcome == "approvable":
        return False
    severity = normalize_severity(item.get("severity"))
    outcomes = OWNED_ADJUDICATION_OUTCOMES if final_review else CURABLE_ADJUDICATION_OUTCOMES
    return severity in MATERIAL_REVIEW_SEVERITIES or severity == "unknown" or outcome in outcomes


def open_material_findings(payload: Any, *, final_review: bool = False) -> list[dict[str, Any]]:
    """The open, material findings in a review's findings JSON (an object with a list, or a bare list)."""
    if isinstance(payload, dict):
        items = next((payload[key] for key in ("findings", "issues", "reroutes") if isinstance(payload.get(key), list)), [])
    else:
        items = payload if isinstance(payload, list) else []
    return [
        item
        for item in items
        if isinstance(item, dict) and not item_is_resolved(item) and finding_is_material(item, final_review=final_review)
    ]


def validate_findings_sidecar(failures: list[str], findings_paths: list[Path], *, label: str) -> None:
    for path, payload in json_artifacts(failures, findings_paths, label):
        items = list_payload_items(
            payload,
            keys=("findings", "issues", "reroutes"),
            label=label,
            path=path,
            failures=failures,
        )
        if items is None:
            continue
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                failures.append(f"{label} item {index} must be an object: {path}")
                continue
            if not item_is_resolved(item) and finding_is_material(item) and not item_owner_or_target(item):
                failures.append(
                    f"{label} item {item.get('id') or index} has an unresolved material finding without an owner "
                    f"or reroute target: {path}"
                )


def validate_json_lists(failures: list[str], paths: list[Path], *, label: str, keys: tuple[str, ...]) -> None:
    """Each artifact is a list, or an object holding one of these lists."""
    for path, payload in json_artifacts(failures, paths, label):
        list_payload_items(payload, keys=keys, label=label, path=path, failures=failures)


def validate_docs_review_checklist(failures: list[str], checklist_paths: list[Path]) -> None:
    for path, payload in json_artifacts(failures, checklist_paths, "docs review checklist"):
        if not isinstance(payload, dict):
            failures.append(f"Docs review checklist JSON must be an object: {path}")
            continue
        for key in ("missing_required", "suggested_documents"):
            if key not in payload:
                failures.append(f"Docs review checklist JSON must contain {key!r}: {path}")
                continue
            if not isinstance(payload[key], list):
                failures.append(f"Docs review checklist JSON field {key!r} must be a list: {path}")
        if "existing_documents" in payload and not isinstance(payload["existing_documents"], list):
            failures.append(f"Docs review checklist JSON field 'existing_documents' must be a list: {path}")
        if "official_sources_checked" in payload and not isinstance(payload["official_sources_checked"], list):
            failures.append(f"Docs review checklist JSON field 'official_sources_checked' must be a list: {path}")


OPEN_ITEM_TYPES = {"client_document", "client_question", "attorney_decision", "attorney_action", "risk"}
OPEN_ITEM_STATUSES = {"open", "resolved"}
OPEN_ITEM_WHO = {"attorney", "client", "system"}
PACKET_STATUSES = {"draft", "ready_to_file"}
# The open-items format in the matter contract. A list that declares it is held to the plain-language rules
# below, because the app shows its text to the attorney. An older list without it still loads; those rules
# only warn about it, so a matter built before them can finish.
OPEN_ITEMS_SCHEMA_VERSION = 2
# The length the contract asks for; the runtime refuses text more than twice as long.
OPEN_ITEM_TEXT_TARGETS = {"title": 80, "question": 140, "recommendation": 120, "detail": 300}

_URL_OR_EMAIL = re.compile(r"https?://\S+|\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PATH_PATTERNS = (
    re.compile(r"(?<![\w.:/])~?/[A-Za-z][\w.-]+/"),  # /Users/..., ~/Matters/...
    re.compile(r"\b(?:output|vault|deliverables)/"),  # the matter's own folders
    re.compile(r"\b[\w.-]+/[\w.-]+\.(?:json|md|pdf|docx|txt|py)\b", re.IGNORECASE),  # Forms/I-130.pdf
    re.compile(r"\$\{|<plugin root>"),
)
_SNAKE_CASE = re.compile(r"(?<![\w@.-])[a-z][a-z0-9]*(?:_[a-z0-9]+)+(?![\w@-])")  # forms_preparer
_REVIEW_CODE = re.compile(r"\b(?:ADJ|FR)\d+\b|\bfinding [A-Z]{1,4}\d+\b")
_DATED_NOTE = re.compile(r"\([^()]{0,60}\b\d{4}-\d{2}-\d{2}\b[^()]{0,60}\)\s*:")  # "Cover letter (draft 2026-10-28):"
_FORM_NUMBER = re.compile(r"[A-Za-z]{1,2}-\d+[A-Za-z]?")  # an id like "i-94" would collide with the form name


def open_item_reference_ids(items: list[Any]) -> list[str]:
    """Item ids that read as ids (hyphens or underscores), which should never surface in text the attorney reads."""
    ids = {str(item.get("id") or "").strip() for item in items if isinstance(item, dict)}
    return sorted(
        item_id
        for item_id in ids
        if len(item_id) >= 4 and ("-" in item_id or "_" in item_id) and not _FORM_NUMBER.fullmatch(item_id)
    )


def open_item_text_problems(field: str, text: str, *, reference_ids: list[str]) -> list[str]:
    """What keeps one field from reading as plain English on the attorney's screen."""
    problems: list[str] = []
    target = OPEN_ITEM_TEXT_TARGETS[field]
    if len(text) > 2 * target:
        hint = "; put the history in notes" if field == "detail" else ""
        problems.append(f"{field} runs {len(text)} characters (aim for {target}; the limit is {2 * target}{hint})")
    prose = _URL_OR_EMAIL.sub(" ", text)
    if any(pattern.search(prose) for pattern in _PATH_PATTERNS):
        problems.append(f"{field} names a file path; describe the document in words")
    found_id = next(
        (item_id for item_id in reference_ids if re.search(rf"(?<![\w-]){re.escape(item_id)}(?![\w-])", prose)), None
    )
    if found_id:
        problems.append(f"{field} mentions the item id {found_id!r}; name that item by its title")
    snake = next((match.group(0) for match in _SNAKE_CASE.finditer(prose) if match.group(0) != found_id), None)
    if snake:
        problems.append(f"{field} uses the internal name {snake!r}; use plain words")
    code = _REVIEW_CODE.search(prose)
    if code:
        problems.append(f"{field} cites the review code {code.group(0)!r}; say what the review found instead")
    if field == "detail" and _DATED_NOTE.search(prose):
        problems.append("detail reads like a dated log; rewrite it as one current statement and put the history in notes")
    return problems


def open_item_rule_problems(item: dict[str, Any], *, changing: bool) -> list[str]:
    """The rules every open item keeps, whatever the list's age. An item being added or changed (``changing``) keeps
    them once resolved too: it needs its resolution, and blocks_filing stays true or false."""
    status = item.get("status", "open")
    problems: list[str] = []
    if item.get("type") not in OPEN_ITEM_TYPES:
        problems.append(f"type must be one of {sorted(OPEN_ITEM_TYPES)}")
    if not str(item.get("title") or "").strip():
        problems.append("needs a title")
    if status not in OPEN_ITEM_STATUSES:
        problems.append("status must be 'open' or 'resolved'")
    if changing and status == "resolved" and not str(item.get("resolution") or "").strip():
        problems.append("is resolved with no resolution; add a one-line resolution")
    if (changing or status == "open") and not isinstance(item.get("blocks_filing"), bool):
        problems.append("blocks_filing must be true or false")
    return problems


def open_item_format_problems(item: dict[str, Any], *, reference_ids: list[str], protected: bool = False) -> list[str]:
    """The contract's rules for the fields the app shows, and in a protected matter the client-facing items' words.
    Resolved items are history and only need to be valid JSON."""
    problems: list[str] = []
    item_type = item.get("type")
    who = item.get("who")
    if who is not None and who not in OPEN_ITEM_WHO:
        problems.append(f"who must be one of {sorted(OPEN_ITEM_WHO)}")
    notes = item.get("notes")
    if notes is not None and not (isinstance(notes, list) and all(isinstance(note, str) for note in notes)):
        problems.append("notes must be a list of strings")
    texts: dict[str, str] = {}
    for field in OPEN_ITEM_TEXT_TARGETS:
        value = item.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            problems.append(f"{field} must be a string")
        elif value.strip():
            texts[field] = value.strip()
    if item.get("status", "open") != "open":
        return problems
    question = texts.get("question")
    if item_type == "attorney_decision":
        if not question:
            problems.append("is a decision with no question; add question, the decision as one short question for the attorney")
        elif not question.rstrip("\"'”) ").endswith("?"):
            problems.append("question should end with a question mark")
    elif question:
        problems.append("question belongs only on decisions; a client's question goes in the title")
    for field, text in texts.items():
        problems.extend(open_item_text_problems(field, text, reference_ids=reference_ids))
    if protected:
        problems += client_facing_protected_problems(item)
    return problems


def report_open_item_warnings(warnings: list[str], path: Path) -> None:
    """An older list passes, but the agent reconciling it hears what to bring up to date."""
    if not warnings:
        return
    shown = warnings[:10]
    lines = [
        f"Note: {path.name} predates the current open-items format, so these are warnings, not refusals. "
        f"Bring its open items up to the matter contract's rules and add \"schema_version\": {OPEN_ITEMS_SCHEMA_VERSION}.",
        *(f"- {warning}" for warning in shown),
    ]
    if len(warnings) > len(shown):
        lines.append(f"- and {len(warnings) - len(shown)} more item(s).")
    print("\n".join(lines), file=sys.stderr)


CLIENT_FACING_TYPES = {"client_document", "client_question"}


def client_facing_protected_problems(item: dict[str, Any]) -> list[str]:
    """In a protected matter, an open item the client request is built from must not name the case or what happened."""
    if item.get("status", "open") != "open":
        return []
    if item.get("type") not in CLIENT_FACING_TYPES and item.get("who") != "client":
        return []
    texts = {field: item.get(field) for field in OPEN_ITEM_TEXT_TARGETS if isinstance(item.get(field), str)}
    if protected_term_failures(protected=True, **texts):
        return [
            "names the case or what happened to the client, and the client request is built from it; use neutral "
            "words such as \"documents about your relationship and your safety\""
        ]
    return []


# ---------------------------------------------------------------------------
# Changing one open item (run_matter_workflow.py open-items), under the matter's lock
# ---------------------------------------------------------------------------

OPEN_ITEM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
OPEN_ITEM_NOTE_LIMIT = 300


class OpenItemRefused(ValueError):
    """An open-item change the matter contract doesn't allow; the message says what to fix."""


def _empty_open_items(now: str) -> dict[str, Any]:
    return {"schema_version": OPEN_ITEMS_SCHEMA_VERSION, "updated_at": now, "packet_status": "draft", "items": []}


def _clean_note(text: Any) -> str:
    note = " ".join(str(text or "").split())
    if not note:
        raise OpenItemRefused("A note needs text: one line, starting with the step's plain name.")
    if len(note) > OPEN_ITEM_NOTE_LIMIT:
        raise OpenItemRefused(f"A note is one line of at most {OPEN_ITEM_NOTE_LIMIT} characters; this one runs {len(note)}.")
    return note


def upsert_open_item(ledger: dict[str, Any] | None, change: Any, *, protected: bool, now: str) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Add one item to the open items list, or change the item with the same id. Pure: returns (new list, the item,
    whether it was added). The fields given replace the item's own; ``notes`` given are added to its notes. The
    item is held to the matter contract's rules whatever the list's age, and a blocking open item turns
    ``packet_status`` back to ``draft``. Raises OpenItemRefused with what to fix."""
    if not isinstance(change, dict):
        raise OpenItemRefused("The item must be a JSON object with at least an id.")
    item_id = str(change.get("id") or "").strip()
    if not OPEN_ITEM_ID.fullmatch(item_id):
        raise OpenItemRefused("The item needs a stable, readable id (letters, digits and hyphens), such as doc-i94.")
    new = json.loads(json.dumps(ledger)) if ledger is not None else _empty_open_items(now)
    items = new.setdefault("items", [])
    if not isinstance(items, list):
        raise OpenItemRefused("The open items list has no items list; rewrite it to the matter contract first.")
    existing = next((it for it in items if isinstance(it, dict) and str(it.get("id") or "").strip() == item_id), None)
    added_notes = change.get("notes", [])
    if isinstance(added_notes, str):
        added_notes = [added_notes]
    if not isinstance(added_notes, list):
        raise OpenItemRefused("notes must be a list of one-line strings.")
    fields = {key: value for key, value in change.items() if key not in {"notes", "attorney_actions_seen", "resolved_by"}}
    if existing is None:
        missing = [key for key in ("type", "title", "blocks_filing") if key not in fields]
        if missing:
            raise OpenItemRefused(f"A new item needs {', '.join(missing)} (and a question when it's a decision).")
        item: dict[str, Any] = {"status": "open"}
        items.append(item)
    else:
        item = existing
        if item.get("resolved_by") == "attorney" and fields.get("status") == "open" and item.get("status") != "open":
            raise OpenItemRefused(
                "The attorney marked this item done in the app, so it stays resolved. Add a note to it, or a new item "
                "if something new is needed."
            )
    item.update(fields)
    if added_notes:
        notes = item.get("notes") if isinstance(item.get("notes"), list) else []
        for note in added_notes:
            note = _clean_note(note)
            if note not in notes:
                notes.append(note)
        item["notes"] = notes
    if item.get("status", "open") == "open":
        item.pop("resolution", None)
    problems = open_item_rule_problems(item, changing=True)
    problems += open_item_format_problems(item, reference_ids=open_item_reference_ids(items), protected=protected)
    if problems:
        raise OpenItemRefused(f"Open item {item_id}: {'; '.join(problems)}.")
    if item_blocks_filing(item):
        new["packet_status"] = "draft"
    new.setdefault("packet_status", "draft")
    new["updated_at"] = now
    return new, item, existing is None


def note_open_item(ledger: dict[str, Any] | None, item_id: str, text: str, *, now: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Add one line to an item's history (``notes``, which the app never shows). Pure; raises OpenItemRefused."""
    note = _clean_note(text)
    new = json.loads(json.dumps(ledger)) if ledger is not None else None
    items = (new or {}).get("items") if isinstance(new, dict) else None
    item = next((it for it in items or [] if isinstance(it, dict) and str(it.get("id") or "").strip() == item_id.strip()), None)
    if item is None:
        raise OpenItemRefused(f"There's no open item {item_id!r} to add a note to; add it with open-items upsert.")
    notes = item.get("notes") if isinstance(item.get("notes"), list) else []
    if note not in notes:
        notes.append(note)
    item["notes"] = notes
    new["updated_at"] = now
    return new, item


def set_open_items_packet_status(ledger: dict[str, Any] | None, packet_status: str, *, protected: bool,
                                 now: str) -> dict[str, Any]:
    """Set the list's ``packet_status`` (the handoff's reconcile) and mark it current (``schema_version`` 2). Pure;
    refuses ``ready_to_file`` while an open item blocks filing, and a list whose open items break the contract."""
    if packet_status not in PACKET_STATUSES:
        raise OpenItemRefused(f"packet_status must be one of {sorted(PACKET_STATUSES)}.")
    new = json.loads(json.dumps(ledger)) if ledger is not None else _empty_open_items(now)
    items = new.get("items")
    if not isinstance(items, list):
        raise OpenItemRefused("The open items list has no items list; rewrite it to the matter contract first.")
    blocking = [str(it.get("title") or it.get("id")) for it in items if item_blocks_filing(it)]
    if packet_status == "ready_to_file" and blocking:
        raise OpenItemRefused(f"{len(blocking)} open item(s) still block filing ({'; '.join(blocking[:3])}), so it stays a draft.")
    reference_ids = open_item_reference_ids(items)
    problems = []
    for item in items:
        if isinstance(item, dict):
            found = open_item_format_problems(item, reference_ids=reference_ids, protected=protected)
            if found:
                problems.append(f"Open item {item.get('id') or '?'}: {'; '.join(found)}.")
    if problems:
        raise OpenItemRefused("Bring these open items up to the contract's rules first (open-items upsert):\n" + "\n".join(problems[:10]))
    new["packet_status"] = packet_status
    new["schema_version"] = OPEN_ITEMS_SCHEMA_VERSION
    new["updated_at"] = now
    return new


def validate_open_items(
    failures: list[str],
    open_items_paths: list[Path],
    warnings: list[str] | None = None,
    *,
    protected: bool = False,
) -> None:
    """Refuse a malformed list. Hold a current-format list to the plain-language rules; only warn about an older one.

    Warnings go to `warnings` when given, otherwise to stderr, where the agent completing the stage sees them.
    """
    for path, payload in json_artifacts(failures, open_items_paths, "open items"):
        if not isinstance(payload, dict):
            failures.append(f"Open items JSON must be an object: {path}")
            continue
        packet_status = payload.get("packet_status")
        if packet_status not in PACKET_STATUSES:
            failures.append(f"Open items JSON needs packet_status of 'draft' or 'ready_to_file': {path}")
        schema_version = payload.get("schema_version")
        current = isinstance(schema_version, int) and not isinstance(schema_version, bool) and schema_version >= OPEN_ITEMS_SCHEMA_VERSION
        if schema_version is not None and not current:
            failures.append(f"Open items JSON schema_version must be {OPEN_ITEMS_SCHEMA_VERSION}: {path}")
        items = payload.get("items")
        if not isinstance(items, list):
            failures.append(f"Open items JSON must contain an 'items' list (empty when nothing is open): {path}")
            continue
        reference_ids = open_item_reference_ids(items)
        format_problems: list[str] = []
        seen_ids: set[str] = set()
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                failures.append(f"Open item {index} must be an object: {path}")
                continue
            failures.extend(f"Open item {index} {problem}: {path}" for problem in open_item_rule_problems(item, changing=False))
            item_id = str(item.get("id") or "").strip()
            problems = open_item_format_problems(item, reference_ids=reference_ids, protected=protected)
            if not item_id:
                problems.insert(0, "needs a stable id")
            elif item_id in seen_ids:
                problems.insert(0, "repeats an id another item already uses")
            seen_ids.add(item_id)
            if problems:
                format_problems.append(f"Open item {item_id or index}: {'; '.join(problems)}.")
        blocking_open = sum(1 for item in items if item_blocks_filing(item))
        if packet_status == "ready_to_file" and blocking_open:
            failures.append(f"Open items JSON says ready_to_file but {blocking_open} open item(s) block filing: {path}")
        if current:
            failures.extend(format_problems)
        elif warnings is not None:
            warnings.extend(format_problems)
        else:
            report_open_item_warnings(format_problems, path)


def validate_final_review_findings(failures: list[str], findings_paths: list[Path]) -> None:
    """Each finding: an id, a title, a severity, an outcome when it's a merits risk, and an owner when it matters."""
    for path, payload in json_artifacts(failures, findings_paths, "final review findings"):
        if not isinstance(payload, dict) or not isinstance(payload.get("findings"), list):
            failures.append(f"Final review findings JSON must be an object with a 'findings' list (empty when clean): {path}")
            continue
        overall = str(payload.get("overall_outcome") or "").strip().casefold()
        if overall and overall not in ADJUDICATION_OUTCOMES:
            failures.append(f"Final review overall_outcome must be one of {sorted(ADJUDICATION_OUTCOMES)}: {path}")
        for index, item in enumerate(payload["findings"], start=1):
            if not isinstance(item, dict):
                failures.append(f"Final review finding {index} must be an object: {path}")
                continue
            label = f"Final review finding {item.get('id') or index}"
            if not str(item.get("id") or "").strip():
                failures.append(f"Final review finding {index} needs an id (keep ids stable across re-reviews).")
            if not str(item.get("title") or "").strip():
                failures.append(f"{label} needs a title.")
            # "critical" or "high" reads as blocker, so it can't skip the owner check below.
            severity = normalize_severity(item.get("severity"))
            if severity not in REVIEW_SEVERITIES:
                failures.append(f"{label} severity must be one of {sorted(REVIEW_SEVERITIES)}.")
            outcome = str(item.get("outcome") or "").strip().casefold()
            if outcome and outcome not in ADJUDICATION_OUTCOMES:
                failures.append(f"{label} outcome must be one of {sorted(ADJUDICATION_OUTCOMES)}.")
            if finding_is_material(item, final_review=True) and not item_is_resolved(item) and not item_owner_or_target(item):
                failures.append(f"{label} is open and material but has no owner.")


FILING_COPIES_DIR = "output/deliverables/Forms"


def filing_copies(matter_path: Path) -> list[Path]:
    folder = matter_path / FILING_COPIES_DIR
    if not folder.is_dir():
        return []
    return sorted(path for path in folder.iterdir() if path.is_file() and path.suffix.casefold() == ".pdf")


def validate_final_review_memo(failures: list[str], memo_paths: list[Path]) -> None:
    failures.extend(f"Final review memo is empty: {path}" for path in memo_paths
                    if not path.read_text(encoding="utf-8", errors="replace").strip())


# What each stage's pass records, as (reason, label), in the order its refusal names them: in each group, every
# missing artifact first, then what's wrong with the ones there (artifact_checks).
PASS_ARTIFACTS: dict[str, list[list[tuple[str, str]]]] = {
    "docs_review": [[("docs_review_memo", "docs review memo"), ("document_inventory", "document inventory JSON"),
                     ("docs_review_checklist", "docs review checklist JSON")]],
    "forms_preparer": [[("forms_fact_table", "forms fact table"), ("forms_intent_manifest", "forms intent manifest"),
                        ("forms_audit", "prepared-forms audit")]],
    "forms_reviewer": [[("forms_review_memo", "forms review memo"), ("forms_review_findings", "forms review findings JSON")]],
    "cover_letter_writer_draft": [[("cover_letter_output", "cover-letter DOCX/PDF")]],
    "cover_letter_researcher": [[("authority_pack", "authority pack"), ("support_matrix", "support matrix")]],
    # The writer can fix what the render audit finds; the reviewer may not, so it gates the writer too. The mechanical
    # letter check (authorities in the support matrix, the exhibit plan against the audit, a source for every fact
    # sentence) gates the hand-off to the letter review.
    "cover_letter_writer_integrate": [[("cover_letter_output", "cover-letter DOCX/PDF"),
                                       ("cover_letter_audit", "cover-letter render audit")], [("letter_check", "letter check")]],
    # The letter reviewed is the letter checked: a reviewer's own fix gets the check again.
    "cover_letter_reviewer": [[("cover_letter_review_memo", "cover-letter review memo"),
                               ("cover_letter_review_findings", "cover-letter review findings JSON")],
                              [("cover_letter_audit", "cover-letter style/render audit")], [("letter_check", "letter check")]],
    "packet_assembly": [[("packet_pdf", "assembled packet PDF"), ("packet_manifest", "packet manifest")]],
    "final_review": [[("final_review_memo", "final review memo")], [("final_review_findings", "final review findings JSON")]],
    "attorney_handoff": [[("attorney_memo", "attorney memo"), ("client_request", "client request list"),
                          ("open_items", "open items JSON")]],
}


def artifact_checks(matter_path: Path, protected: bool) -> dict[str, Callable[[list[str], list[Path]], None]]:
    """What is checked in each kind of artifact a pass records, by its reason."""
    return {
        "document_inventory": partial(validate_json_lists, label="document inventory",
                                      keys=("documents", "existing_documents", "items")),
        "docs_review_checklist": validate_docs_review_checklist,
        "forms_audit": partial(validate_clean_forms_audit, matter_path=matter_path),
        "forms_review_findings": partial(validate_findings_sidecar, label="forms review findings"),
        "support_matrix": partial(validate_json_lists, label="support matrix",
                                  keys=("propositions", "items", "authorities", "support")),
        "cover_letter_audit": validate_clean_cover_letter_audit,
        "letter_check": validate_letter_check,
        "cover_letter_review_findings": partial(validate_findings_sidecar, label="cover-letter review findings"),
        "packet_manifest": partial(validate_packet_manifest, matter_path=matter_path),
        "final_review_memo": validate_final_review_memo,
        "final_review_findings": validate_final_review_findings,
        "open_items": partial(validate_open_items, protected=protected),
    }


def stage_pass_validation_failures(
    *,
    matter_path: Path,
    stage_id: str,
    artifact_records: list[dict[str, str]],
    evidence_records: list[dict[str, str]],
    protected: bool = False,
) -> list[str]:
    records = [*artifact_records, *evidence_records]
    checks = artifact_checks(matter_path, protected)
    failures: list[str] = []
    for group in PASS_ARTIFACTS.get(stage_id, []):
        found: dict[str, list[Path]] = {}
        for reason, label in group:
            found[reason] = existing_paths_for_reason(records, reason, matter_path=matter_path)
            if not found[reason]:
                failures.append(f"Missing required {label} artifact ({reason}).")
        for reason, paths in found.items():
            if reason in checks:
                checks[reason](failures, paths)

    if stage_id == "attorney_handoff":
        deliverables = matter_path / "output" / "deliverables"
        # The attorney gets the memo and the client request as PDFs too, rendered from the final Markdown.
        for name in ("Attorney Memo", "Client Request"):
            md, pdf = deliverables / f"{name}.md", deliverables / f"{name}.pdf"
            if md.is_file() and (not pdf.is_file() or pdf.stat().st_mtime < md.stat().st_mtime):
                failures.append(f"{name}.pdf is missing or older than {name}.md: render it again with "
                                "scripts/packet/render_document.py (references/handoff.md, \"PDF copies\").")
        if deliverables.is_dir() and any(deliverables.glob("Filing Packet*.pdf")) and not any(deliverables.glob("Filing Checklist.*")):
            print(
                "Note: a packet exists but there's no Filing Checklist.md or .pdf in the deliverables; the handoff "
                "writes it once a packet exists (references/handoff.md).",
                file=sys.stderr,
            )
    elif stage_id == "forms_preparer" and not filing_copies(matter_path):
        failures.append(
            f"No filing copy in {FILING_COPIES_DIR}/. Render each prepared form's filing copy there "
            "(forms_workflow.py build does it) before passing."
        )
    return failures


# The artifact whose bytes show a stage did its work this time. A pass whose main artifact is byte-identical to the
# last pass needs a reason (--unchanged-reason): a stage sent back to fix something that re-passes on the same file
# didn't fix it. The forms are judged by their filing copies and fact table together.
MAIN_ARTIFACT_REASONS: dict[str, tuple[str, ...]] = {
    "docs_review": ("docs_review_memo", "document_inventory", "docs_review_checklist"),
    "forms_preparer": ("forms_fact_table",),
    "forms_reviewer": ("forms_review_findings",),
    "cover_letter_writer_draft": ("cover_letter_output",),
    "cover_letter_researcher": ("support_matrix", "authority_pack"),
    "cover_letter_writer_integrate": ("cover_letter_output",),
    "cover_letter_reviewer": ("cover_letter_review_findings",),
    "packet_assembly": ("packet_pdf",),
    "final_review": ("final_review_findings",),
    "attorney_handoff": ("attorney_memo", "open_items"),
}
REVIEW_FINDINGS_REASONS = {
    "forms_reviewer": "forms_review_findings",
    "cover_letter_reviewer": "cover_letter_review_findings",
    "final_review": "final_review_findings",
}


def main_artifact_hashes(
    stage_id: str,
    records: list[dict[str, str]],
    *,
    matter_path: Path,
) -> dict[str, str]:
    reasons = MAIN_ARTIFACT_REASONS.get(stage_id, ())
    paths = [record["path"] for record in records if record.get("reason") in reasons]
    if stage_id == "forms_preparer":
        paths += [relative_to_matter(matter_path, path) for path in filing_copies(matter_path)]
    hashes: dict[str, str] = {}
    for relative in sorted(set(paths)):
        path = resolve_path_for_matter(matter_path, relative)
        if path.is_file():
            hashes[relative] = sha256_file(path)
    return hashes


def unchanged_since_last_pass(
    stage: dict[str, Any],
    records: list[dict[str, str]],
    *,
    matter_path: Path,
) -> list[str]:
    """The main artifacts that are byte-identical to the stage's last pass; empty when anything changed or there
    was no earlier pass to compare with."""
    last_pass = stage.get("last_pass") or {}
    snapshot_rel = last_pass.get("snapshot") if isinstance(last_pass, dict) else None
    if not snapshot_rel:
        return []
    try:
        before = json.loads(resolve_path_for_matter(matter_path, snapshot_rel).read_text(encoding="utf-8")).get("files") or {}
    except Exception:
        return []
    now = main_artifact_hashes(stage["stage_id"], records, matter_path=matter_path)
    if not now or any(before.get(path) != digest for path, digest in now.items()):
        return []
    return sorted(now)


def skip_refusal(state: dict[str, Any], stage_id: str) -> str | None:
    """Why a review (or the handoff) can't be skipped, or None when it can: the work it checks was itself skipped."""
    reviewed = [candidate for candidate in REVIEWED_STAGE.get(stage_id, ()) if candidate in state["stages"]]
    if stage_id not in REVIEWED_STAGE:
        return None
    if reviewed and all(stage_record(state, candidate)["status"] == "skipped" for candidate in reviewed):
        return None
    what = " and ".join(reviewed) if reviewed else "work this workflow doesn't include"
    return (
        f"Cannot skip {stage_id}: it checks {what}, which wasn't skipped. A review, or the handoff, is skipped only "
        "when the work it checks was skipped, or when the attorney says so: pass --attorney-approved \"<what the "
        "attorney said>\". A refusal to pass is information about the work; fix it or mark the stage blocked."
    )


def review_finding_counts(
    stage_id: str,
    records: list[dict[str, str]],
    *,
    matter_path: Path,
) -> dict[str, Any] | None:
    """For a review: how many material findings are still open, and whose they are."""
    reason = REVIEW_FINDINGS_REASONS.get(stage_id)
    if reason is None:
        return None
    open_findings: list[dict[str, Any]] = []
    for _path, payload in json_artifacts([], existing_paths_for_reason(records, reason, matter_path=matter_path), reason):
        open_findings.extend(open_material_findings(payload, final_review=stage_id == "final_review"))
    by_owner: dict[str, int] = {}
    for finding in open_findings:
        owner = item_owner_or_target(finding) or "unassigned"
        by_owner[owner] = by_owner.get(owner, 0) + 1
    return {
        "count": len(open_findings),
        "by_owner": by_owner,
        "ids": [str(finding.get("id")) for finding in open_findings if finding.get("id")][:50],
    }


def stage_was_worked_on(stage: dict[str, Any]) -> bool:
    """The stage was started at some point (its history says so), even if a redo has since reset it."""
    return any(isinstance(h, dict) and h.get("event") == "stage_started" for h in stage.get("history") or [])


def completion_refusal(stage_id: str, status: str, stage: dict[str, Any]) -> str | None:
    """Why a completion of a stage that isn't in progress is refused, or None when it may be recorded (a stage
    nobody has started can be skipped, failed or blocked outright, never passed)."""
    current = str(stage.get("status") or "pending")
    doing = f"pass {stage_id}" if status == "passed" else f"mark {stage_id} {status}"
    if current == "pending" and stage_was_worked_on(stage):
        return (
            f"Cannot {doing}: it isn't in progress (it is pending). A redo reset it after it started, so this result "
            f"is for work that was set aside, and nothing was recorded. The stage runs again from start-stage {stage_id}."
        )
    if current == "pending":
        if status != "passed":
            return None
        return (
            f"Cannot pass {stage_id}: it isn't in progress (it is pending). Run start-stage {stage_id}, "
            "do the stage's work, then complete it; a pass records work done in this attempt."
        )
    if current == "blocked":
        return (
            f"Cannot {doing}: it isn't in progress (it is blocked). Resolve its blocker (resolve-blocker), then "
            f"start-stage {stage_id} again."
        )
    return f"Cannot {doing}: it isn't in progress (it is {current}). Run start-stage {stage_id} again first."


def refuse(heading: str, failures: list[str]) -> ValueError:
    """The error for a refused completion: the heading, then each failure on its own line."""
    return ValueError(heading + "\n" + "\n".join(f"- {failure}" for failure in failures))


def complete_stage(
    state: dict[str, Any],
    *,
    matter_path: Path,
    stage_id: str,
    status: str,
    summary: str,
    artifacts: list[str] | None = None,
    evidence_files: list[str] | None = None,
    blocker_summary: str | None = None,
    blocker_owner: str | None = None,
    attorney_approved: str | None = None,
    unchanged_reason: str | None = None,
    protected: bool = False,
    run_id: str | None = None,
) -> str | None:
    if status not in VALID_STAGE_STATUSES - {"pending", "in_progress"}:
        raise ValueError(f"Unsupported completion status: {status}")
    stage = stage_record(state, stage_id)
    if not summary.strip():
        raise ValueError("A non-empty summary is required.")
    attorney_approved = (attorney_approved or "").strip() or None
    unchanged_reason = (unchanged_reason or "").strip() or None
    if stage["status"] in DONE_STATUSES:
        # Relabeling finished work would leave the stages after it standing on something that changed under them.
        raise ValueError(
            f"Cannot mark {stage_id} {status}: it is already {stage['status']}. To redo it, reroute from it "
            f"(reroute --from-stage {stage_id}), which resets the stages that depend on it too."
        )
    if stage["status"] != "in_progress":
        # A result is recorded only on the attempt it belongs to. A stage nobody has started may be skipped, failed or
        # blocked outright; one that was started and then reset by a redo (a reroute, side by side with this agent's
        # work) is waiting for its new attempt, and this result is for work that was set aside.
        refusal = completion_refusal(stage_id, status, stage)
        if refusal:
            raise ValueError(refusal)
    if status in {"passed", "skipped"}:
        unmet = unmet_dependencies(state, stage_id)
        if unmet:
            dependency, dependency_status = unmet[0]
            verb = "pass" if status == "passed" else "skip"
            raise ValueError(
                f"Cannot {verb} {stage_id} before {dependency} is passed or skipped; current status is {dependency_status}."
            )
    if status == "skipped" and not attorney_approved:
        refusal = skip_refusal(state, stage_id)
        if refusal:
            raise ValueError(refusal)
    if status == "blocked":
        if not blocker_summary or not blocker_summary.strip():
            raise ValueError("A blocker summary is required when marking a stage blocked.")
        if blocker_owner not in VALID_BLOCKER_OWNERS:
            raise ValueError(
                f"Invalid blocker owner {blocker_owner!r}; expected one of {sorted(VALID_BLOCKER_OWNERS)}."
            )
    if status != "passed":
        # A blocked or failed stage shows on the dashboard too; lint_stage_completion covers a passed one.
        shown = {"stage_summary": summary, "blocker_summary": blocker_summary if status == "blocked" else None}
        screen_failures = protected_term_failures(protected=protected, **shown) + party_name_failures(matter_path, **shown)
        if status == "blocked":
            # The blocker is stored as written (a summary is redacted), so identifiers in it are refused outright.
            kinds = sorted({finding["kind"] for finding in scan_text(blocker_summary or "", source="blocker_summary")})
            if kinds:
                screen_failures.append(
                    f"Blocker summary contains sensitive-looking data ({', '.join(kinds)}); the dashboard shows it, so "
                    "say what is needed in general words, such as \"Waiting on documents from the client.\""
                )
        if screen_failures:
            raise refuse(f"Cannot record {stage_id} as {status}; privacy lint failed.", screen_failures)

    normalized_stage_summary, summary_redacted = normalize_summary(summary)
    artifact_records = classify_paths(artifacts or [], matter_path=matter_path)
    evidence_records = classify_paths(evidence_files or [], matter_path=matter_path)
    records = [*artifact_records, *evidence_records]
    unchanged: list[str] = []
    if status == "passed":
        privacy_lint_failures = lint_stage_completion(
            matter_path=matter_path,
            summary=normalized_stage_summary,
            artifact_records=artifact_records,
            evidence_records=evidence_records,
            protected=protected,
        )
        if privacy_lint_failures:
            raise refuse(f"Cannot pass {stage_id}; privacy lint failed.", privacy_lint_failures)
        validation_failures = stage_pass_validation_failures(
            matter_path=matter_path,
            stage_id=stage_id,
            artifact_records=artifact_records,
            evidence_records=evidence_records,
            protected=protected,
        )
        validation_failures += workspace_path_failures(matter_path, records)
        if validation_failures:
            raise refuse(f"Cannot pass {stage_id}; required stage contract is incomplete.", validation_failures)
        unchanged = unchanged_since_last_pass(stage, records, matter_path=matter_path)
        if unchanged and not unchanged_reason:
            raise ValueError(
                f"Cannot pass {stage_id}: {', '.join(unchanged)} is byte-for-byte the file it passed with last time, "
                "so this attempt changed nothing. Do the work this pass is for (the reroute or the attorney's request "
                "says what), or, when nothing needed to change, say why: --unchanged-reason \"<why>\"."
            )

    now = now_iso(precise=True)
    if stage["started_at"] is None:
        stage["started_at"] = now
    stage["completed_at"] = now
    stage["status"] = status
    stage["summary"] = normalized_stage_summary
    stage["summary_redacted"] = summary_redacted
    stage["artifact_records"] = artifact_records
    stage["evidence_records"] = evidence_records
    stage["artifacts"] = [record["path"] for record in stage["artifact_records"]]
    stage["evidence_files"] = [record["path"] for record in stage["evidence_records"]]
    stage["attorney_approved"] = attorney_approved
    stage["unchanged_reason"] = unchanged_reason if unchanged else None
    if status == "passed":
        counts = review_finding_counts(stage_id, records, matter_path=matter_path)
        if counts is not None:
            stage["open_material_findings"] = counts
    end_attempt(state, stage_id, now=now, outcome=status, run_id=run_id)

    blocker_value: str | None = None
    if status == "blocked":
        blocker_value = blocker_id(state)
        blocker = {
            "id": blocker_value,
            "stage_id": stage_id,
            "owner": blocker_owner,
            "summary": blocker_summary.strip(),
            "status": "open",
            "created_at": now,
            "resolved_at": None,
            "resolution_note": None,
        }
        state["blockers"].append(blocker)
        stage["open_blocker_ids"].append(blocker_value)
    else:
        close_stage_blockers(
            state,
            stage_id,
            resolution_note=f"Stage marked {status}.",
        )

    append_history(
        stage,
        "stage_completed",
        status=status,
        summary=stage["summary"],
        artifacts=stage["artifacts"],
        evidence_files=stage["evidence_files"],
        blocker_id=blocker_value,
        attorney_approved=attorney_approved,
        unchanged_reason=stage["unchanged_reason"],
    )
    append_history(
        state,
        "stage_completed",
        stage_id=stage_id,
        status=status,
        blocker_id=blocker_value,
    )
    refresh_derived_fields(state)
    return blocker_value


def resolve_blocker(
    state: dict[str, Any],
    *,
    blocker_id_value: str,
    resolution_note: str,
    reset_stage_to: str = "pending",
    run_id: str | None = None,
) -> None:
    if reset_stage_to not in {"pending", "in_progress"}:
        raise ValueError("reset_stage_to must be 'pending' or 'in_progress'.")
    blocker = next((item for item in state["blockers"] if item["id"] == blocker_id_value), None)
    if blocker is None:
        raise ValueError(f"Unknown blocker: {blocker_id_value}")
    if blocker["status"] != "open":
        raise ValueError(f"Blocker {blocker_id_value} is already {blocker['status']}.")
    blocker["status"] = "resolved"
    blocker["resolved_at"] = now_iso(precise=True)
    blocker["resolution_note"] = resolution_note.strip()
    stage = stage_record(state, blocker["stage_id"])
    if blocker_id_value in stage["open_blocker_ids"]:
        stage["open_blocker_ids"].remove(blocker_id_value)
    if not open_blockers_for_stage(state, blocker["stage_id"]):
        stage["status"] = reset_stage_to
        stage["completed_at"] = None
        stage["summary"] = None
        if reset_stage_to == "in_progress":
            # Picking the stage straight back up is a new attempt, timed like one start-stage begins.
            now = now_iso(precise=True)
            stage["started_at"] = now
            begin_attempt(stage, now=now, run_id=run_id)
        append_history(
            stage,
            "blocker_resolved",
            blocker_id=blocker_id_value,
            reset_stage_to=reset_stage_to,
        )
    append_history(
        state,
        "blocker_resolved",
        blocker_id=blocker_id_value,
        stage_id=blocker["stage_id"],
        reset_stage_to=reset_stage_to,
    )
    refresh_derived_fields(state)


# What an attempt at a stage records, which a redo clears back to a new stage's values. Its history, last pass and
# timing stay for the re-review.
ATTEMPT_FIELDS = ("status", "started_at", "completed_at", "summary", "summary_redacted", "artifacts", "artifact_records",
                  "evidence_files", "evidence_records")


def reset_stage_for_reroute(stage: dict[str, Any], *, reason: str) -> None:
    append_history(stage, "stage_reset_for_reroute", reason=reason, prior_status=stage["status"])
    fresh = stage_template(stage["stage_id"])
    stage.update({key: fresh[key] for key in ATTEMPT_FIELDS})
    # What the last pass recorded about itself goes with it.
    for key in ("open_material_findings", "attorney_approved", "unchanged_reason", "duration_seconds"):
        stage.pop(key, None)


REDO_RESOLUTION_NOTE = "Set aside by a redo."


def count_reroute(
    state: dict[str, Any],
    *,
    from_stage_id: str,
    detected_in_stage_id: str | None,
    run_id: str | None,
    attorney_approved: str | None,
) -> None:
    """Hold a review to REROUTE_LIMIT send-backs of the same work in one run. A redo the attorney asked for (no
    detecting review, or --attorney-approved) isn't counted. A new run starts the count again."""
    if not detected_in_stage_id or detected_in_stage_id not in REVIEW_STAGE_IDS or attorney_approved:
        return
    record = state.get("reroute_counts")
    run_key = run_id or "interactive"
    if not isinstance(record, dict) or record.get("run_id") != run_key:
        record = state["reroute_counts"] = {"run_id": run_key, "counts": {}}
    key = f"{from_stage_id}<-{detected_in_stage_id}"
    sent_back = int(record["counts"].get(key) or 0)
    if sent_back >= REROUTE_LIMIT:
        raise ValueError(
            f"Not rerouted: {detected_in_stage_id} has already sent {from_stage_id} back {sent_back} times in this run. "
            "Record what is still wrong as open items (with the review's recommendation), let the review pass with "
            "those findings owned, and carry on, so an unattended run can't loop. If the attorney asked for another "
            "redo, pass --attorney-approved \"<what they said>\"."
        )
    record["counts"][key] = sent_back + 1


def reroute_from_stage(
    state: dict[str, Any],
    *,
    from_stage_id: str,
    reason: str,
    detected_in_stage_id: str | None = None,
    run_id: str | None = None,
    attorney_approved: str | None = None,
) -> list[str]:
    """Reset a stage and every stage that depends on it (not the stages beside it), and set aside their open
    blockers. Returns the reset stages in workflow order."""
    if from_stage_id not in required_stage_ids(state):
        raise ValueError(f"Cannot reroute from {from_stage_id}; it is not required for this matter.")
    if detected_in_stage_id and detected_in_stage_id not in required_stage_ids(state):
        raise ValueError(
            f"Cannot record detected-in stage {detected_in_stage_id}; it is not required for this matter."
        )
    count_reroute(
        state,
        from_stage_id=from_stage_id,
        detected_in_stage_id=detected_in_stage_id,
        run_id=run_id,
        attorney_approved=(attorney_approved or "").strip() or None,
    )
    reset = dependents_of(state, from_stage_id)
    set_aside: list[str] = []
    for stage_id in reset:
        set_aside += [blocker["id"] for blocker in open_blockers_for_stage(state, stage_id)]
        # A redo replaces the work the blocker was about, so the blocker goes with it; otherwise the matter
        # would wait on a blocker for work nobody is doing any more.
        close_stage_blockers(state, stage_id, resolution_note=REDO_RESOLUTION_NOTE)
        reset_stage_for_reroute(stage_record(state, stage_id), reason=reason)
    append_history(
        state,
        "matter_rerouted",
        from_stage_id=from_stage_id,
        detected_in_stage_id=detected_in_stage_id,
        reason=reason,
        reset=reset,
        blockers_set_aside=set_aside,
        attorney_approved=(attorney_approved or "").strip() or None,
    )
    refresh_derived_fields(state)
    return reset


def reroute_from_category(
    state: dict[str, Any],
    *,
    category: str,
    reason: str,
    detected_in_stage_id: str | None = None,
    run_id: str | None = None,
    attorney_approved: str | None = None,
) -> tuple[str, list[str]]:
    if category not in ROLLBACK_TARGETS:
        raise ValueError(f"Unknown reroute category: {category}")
    target_stage_id = ROLLBACK_TARGETS[category]
    if target_stage_id not in required_stage_ids(state):
        raise ValueError(
            f"Reroute category {category} maps to {target_stage_id}, which is not required for this matter."
        )
    reset = reroute_from_stage(
        state,
        from_stage_id=target_stage_id,
        reason=reason,
        detected_in_stage_id=detected_in_stage_id,
        run_id=run_id,
        attorney_approved=attorney_approved,
    )
    return target_stage_id, reset


def is_re_review(stage: dict[str, Any]) -> bool:
    """A review stage that passed before and is due again after a reroute."""
    return (
        stage.get("stage_id") in REVIEW_STAGE_IDS
        and bool(stage.get("last_pass"))
        and stage.get("status") in {"pending", "in_progress", "failed"}
    )


def status_lines(
    state: dict[str, Any],
    *,
    matter_path: Path | None = None,
    meta: dict[str, Any] | None = None,
) -> list[str]:
    matter = state["matter"]
    folder = Path(matter_path) if matter_path else Path(matter["matter_folder"])
    packet = packet_status_line(folder)
    overall = state["overall_status"]
    if overall == "passed" and packet and packet != "ready to file":
        # Every stage passing still leaves a draft when documents are missing; don't let "passed" read as "file it".
        overall = "passed (workflow complete; the packet is a draft)"
    elif overall == "incomplete":
        overall = "incomplete (every stage is done, but the final review didn't pass, so the packet isn't ready to file)"
    lines = [
        f"Matter folder: {folder}",
        f"Matter: {matter['matter_type']} · {matter['filing_posture']} · workflow {matter['workflow_key']}",
        f"Deliverable: {matter['deliverable']}",
    ]
    if meta is not None:
        lines.append(
            f"Settings: {'protected (8 U.S.C. 1367)' if meta.get('protected') else 'not protected'} · "
            f"filing {meta.get('filing_method') or 'paper'} · client language {meta.get('client_language') or 'English'}"
        )
    lines += [
        f"Overall status: {overall}",
        f"Packet: {packet or '-'}",
        f"Running: {', '.join(state.get('running') or []) or '-'}",
        f"Ready to start: {', '.join(state.get('ready') or []) or '-'}",
        f"Next stage: {state['next_stage'] or '-'}",
        f"Case theory/evidence map: {state.get('case_theory_evidence_map', {}).get('path', '-')}",
        "Stages:",
    ]
    for stage_id in required_stage_ids(state):
        stage = stage_record(state, stage_id)
        line = f"  - {stage_id}: {stage['status']}"
        if is_re_review(stage):
            line += " (re-review: brief it with changed-since and its previous findings)"
        counts = stage.get("open_material_findings")
        if stage["status"] == "passed" and isinstance(counts, dict) and counts.get("count"):
            line += f" ({counts['count']} material finding(s) open)"
        waiting_on = [dependency for dependency, _status in unmet_dependencies(state, stage_id)]
        if stage["status"] == "pending" and waiting_on:
            line += f" (after {', '.join(waiting_on)})"
        if stage["summary"]:
            line += f" · {stage['summary']}"
        lines.append(line)
    open_items = open_blockers(state)
    if open_items:
        lines.append("Open blockers:")
        for blocker in open_items:
            lines.append(
                f"  - {blocker['id']} [{blocker['stage_id']}/{blocker['owner']}] {blocker['summary']}"
            )
    return lines


# ---------------------------------------------------------------------------
# Change tracking: what a re-review has to look at
# ---------------------------------------------------------------------------

REVIEW_STAGE_IDS = ("forms_reviewer", "cover_letter_reviewer", "final_review")
SNAPSHOT_DIR_NAME = "snapshots"
# Hashed at every pass: the client's documents, everything delivered, and the stage vaults.
SNAPSHOT_OUTPUT_ROOTS = ("output/deliverables", "output/working/vault")
SNAPSHOT_PRUNE_DIRS = {"__pycache__", "node_modules", ".git", ".venv", "tmp"}
# Reserved only at the top of the matter folder: a client's own "tmp" folder further down holds documents (the app lists them).
SNAPSHOT_TOP_ONLY_DIRS = {"tmp"}
SNAPSHOT_OUTPUT_PRUNE_DIRS = SNAPSHOT_PRUNE_DIRS | {"converted", "renders", "scratch"}
SNAPSHOT_SKIP_SUFFIXES = (".pyc", ".tmp")
CHANGED_SINCE_LIST_LIMIT = 60


def snapshot_scope(matter_path: Path) -> list[Path]:
    """The files a review can depend on: client documents (anything outside output/), deliverables, and the vault."""
    matter_path = matter_path.resolve()
    found: list[Path] = []

    def walk(root: Path, prune: set[str], *, skip_top_output: bool) -> None:
        for dirpath, dirnames, filenames in os.walk(root):
            at_top = Path(dirpath) == root
            dirnames[:] = sorted(
                name
                for name in dirnames
                if not name.startswith(".")
                and (name not in prune or (skip_top_output and not at_top and name in SNAPSHOT_TOP_ONLY_DIRS))
                and not (skip_top_output and at_top and name == "output")
            )
            for name in sorted(filenames):
                if name.startswith((".", "~$")) or name.endswith(SNAPSHOT_SKIP_SUFFIXES):
                    continue
                path = Path(dirpath) / name
                # Page renders and OCR text that closeout deletes aren't work a review depends on.
                if is_render_clutter(path.relative_to(matter_path).as_posix()):
                    continue
                found.append(path)

    walk(matter_path, SNAPSHOT_PRUNE_DIRS, skip_top_output=True)
    for relative_root in SNAPSHOT_OUTPUT_ROOTS:
        base = matter_path / relative_root
        if base.is_dir():
            walk(base, SNAPSHOT_OUTPUT_PRUNE_DIRS, skip_top_output=False)
    return found


def take_snapshot(matter_path: Path, extra_paths: list[str] | None = None) -> dict[str, str]:
    files: dict[str, str] = {}
    candidates = list(snapshot_scope(matter_path))
    candidates += [resolve_path_for_matter(matter_path, raw) for raw in extra_paths or []]
    for path in candidates:
        relative = relative_to_matter(matter_path, path)
        if relative in files or not path.is_file():
            continue
        try:
            files[relative] = sha256_file(path)
        except OSError:
            continue
    return files


def snapshot_path_for(state_path: Path, stage_id: str) -> Path:
    return state_path.parent / SNAPSHOT_DIR_NAME / f"{stage_id}.json"


def write_stage_snapshot(*, matter_path: Path, state_path: Path, stage_id: str, files: dict[str, str]) -> dict[str, Any]:
    """Write the snapshot file for a stage's pass from take_snapshot's hashes (taken outside the matter lock: hashing
    reads every client document). Returns what set_last_pass stores on the stage."""
    path = snapshot_path_for(state_path, stage_id)
    write_json_atomic(
        path,
        {"schema_version": 1, "stage_id": stage_id, "recorded_at": now_iso(precise=True), "files": files},
    )
    return {"snapshot": relative_to_matter(matter_path, path), "file_count": len(files)}


def set_last_pass(stage: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    stage["last_pass"] = {
        "completed_at": stage.get("completed_at"),
        "artifacts": list(stage.get("artifacts", [])),
        "snapshot": snapshot["snapshot"],
        "file_count": snapshot["file_count"],
    }
    return stage["last_pass"]


def owning_stage(relative_path: str) -> str | None:
    """The stage that produces a file, or None for client documents, the ledger, and anything shared."""
    lower = relative_path.replace("\\", "/").casefold()
    name = lower.rsplit("/", 1)[-1]
    if not lower.startswith("output/"):
        return None
    if lower.startswith("output/working/vault/docs-review/"):
        return "docs_review"
    if lower.startswith(("output/working/vault/forms/", "output/deliverables/forms/")):
        return "forms_preparer"
    if lower.startswith("output/working/vault/review/"):
        if name.startswith("forms review"):
            return "forms_reviewer"
        if name.startswith("packet review"):
            return "final_review"
        return None
    if lower.startswith("output/working/vault/research/"):
        return "cover_letter_researcher"
    if lower.startswith("output/working/vault/cover-letter/"):
        return "cover_letter_reviewer" if "review" in name else "cover_letter_writer_draft"
    if lower.startswith(("output/working/vault/final-review/", "output/working/vault/adjudicator/")):
        return "final_review"
    if lower.startswith("output/working/vault/packet/"):
        return "packet_assembly"
    if lower.startswith("output/deliverables/"):
        if name.startswith("cover letter"):
            return "cover_letter_writer_draft"
        if "packet" in name and name.endswith(".pdf"):
            return "packet_assembly"
        if name.startswith(("attorney memo", "client request", "filing checklist")):
            return "attorney_handoff"
    return None


def is_findings_path(path: str) -> bool:
    lower = path.casefold()
    return lower.endswith("findings.json") or lower.endswith("reroute matrix.json")


def changed_since(
    state: dict[str, Any],
    *,
    matter_path: Path,
    state_path: Path,
    stage_id: str,
    fresh: bool = False,
) -> dict[str, Any]:
    """What changed since stage_id last passed, limited to its own and earlier stages' files and the client's documents.

    With fresh (the attorney asked for a full, fresh review), the previous findings are reference only and the
    review covers everything again; nothing is listed as changed or unchanged.
    """
    stage = stage_record(state, stage_id)
    last_pass = stage.get("last_pass") or None
    previous = list(last_pass.get("artifacts", [])) if last_pass else []
    result: dict[str, Any] = {
        "stage_id": stage_id,
        "status": stage["status"],
        "review": "fresh" if fresh else "first",
        "last_passed_at": last_pass.get("completed_at") if last_pass else None,
        "previous_findings": [path for path in previous if is_findings_path(path)],
        "previous_memos": [path for path in previous if path.casefold().endswith("memo.md")],
        "previous_artifacts": previous,
        "added": [],
        "changed": [],
        "removed": [],
        "unchanged_count": 0,
        "later_stage_changes": 0,
    }
    if not last_pass or fresh:
        return result
    snapshot_rel = last_pass.get("snapshot")
    snapshot_file = resolve_path_for_matter(matter_path, snapshot_rel) if snapshot_rel else None
    if snapshot_file is None or not snapshot_file.is_file():
        result["review"] = "re_review_without_snapshot"
        return result
    try:
        before = json.loads(snapshot_file.read_text(encoding="utf-8")).get("files") or {}
    except Exception:
        result["review"] = "re_review_without_snapshot"
        return result
    result["review"] = "re_review"
    now = take_snapshot(matter_path, previous)
    order = required_stage_ids(state)
    position = order.index(stage_id)

    def in_scope(path: str) -> bool:
        owner = owning_stage(path)
        return owner is None or owner not in order or order.index(owner) <= position

    def sort_key(path: str) -> tuple[bool, str]:
        return (path.startswith("output/"), path.casefold())

    for path in sorted(set(before) | set(now), key=sort_key):
        if path in before and path in now and before[path] == now[path]:
            result["unchanged_count"] += 1
            continue
        if not in_scope(path):
            result["later_stage_changes"] += 1
            continue
        kind = "added" if path not in before else "removed" if path not in now else "changed"
        result[kind].append(path)
    return result


def changed_since_lines(report: dict[str, Any]) -> list[str]:
    stage_id = report["stage_id"]
    if report["review"] == "first":
        return [f"{stage_id}: first review (it has not passed before). Review in full."]
    if report["review"] == "fresh":
        lines = [
            f"{stage_id}: fresh review. The attorney asked for a full review, so review everything again, in full, "
            "as if for the first time: every client document and every earlier stage's work, not only what changed."
        ]
        references = report["previous_findings"] + report["previous_memos"]
        if references:
            lines.append("Previous findings, for reference only (don't limit the review to them; keep their ids for "
                         "findings that still stand):")
            lines += [f"  {path}" for path in references]
        return lines
    lines: list[str] = []
    if report["review"] == "re_review_without_snapshot":
        lines.append(
            f"{stage_id}: re-review, but its last pass ({report['last_passed_at'] or 'date unknown'}) predates change "
            "tracking. Check the previous findings, then review in full."
        )
    elif stage_id in REVIEW_STAGE_IDS:
        lines.append(f"{stage_id}: re-review. Last passed {report['last_passed_at'] or '-'}.")
    else:
        lines.append(f"{stage_id}: changes since it last passed ({report['last_passed_at'] or '-'}).")
    for path in report["previous_findings"]:
        lines.append(f"Previous findings: {path}")
    for path in report["previous_memos"]:
        lines.append(f"Previous memo: {path}")
    if not report["previous_findings"] and not report["previous_memos"] and report["previous_artifacts"]:
        lines.append(f"Previous artifacts: {'; '.join(report['previous_artifacts'])}")
    if report["review"] != "re_review":
        return lines
    entries = (
        [("A", path) for path in report["added"]]
        + [("M", path) for path in report["changed"]]
        + [("D", path) for path in report["removed"]]
    )
    if entries:
        lines.append(
            f"Changed since then ({len(report['added'])} added, {len(report['changed'])} changed, "
            f"{len(report['removed'])} removed). Review these, and what they touch:"
        )
        for marker, path in entries[:CHANGED_SINCE_LIST_LIMIT]:
            lines.append(f"  {marker} {path}")
        if len(entries) > CHANGED_SINCE_LIST_LIMIT:
            lines.append(f"  ... {len(entries) - CHANGED_SINCE_LIST_LIMIT} more (--json lists all)")
    else:
        lines.append("Changed since then: nothing in this stage's scope. Confirm the previous findings still hold.")
    lines.append(f"Unchanged: {report['unchanged_count']} file(s). Don't re-read them.")
    if report["later_stage_changes"]:
        lines.append(f"Later stages changed {report['later_stage_changes']} file(s); not in this review's scope.")
    return lines


def state_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    snapshot = deepcopy(state)
    refresh_derived_fields(snapshot)
    return snapshot

#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
from datetime import UTC, datetime
from typing import Any

from scripts.matter_access import ensure_policy, log_access_event
from scripts.matter_state import now_iso, relative_to_matter
from scripts.privacy_terms import find_terms, matter_privacy_terms


SENSITIVE_TEXT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("a_number", re.compile(r"\b(?:[Aa][#-]?\s*|Alien(?:\s+Registration)?\s*(?:No\.?|Number|#)?\s*)\d{8,9}\b")),
    ("uscis_receipt", re.compile(r"\b(?:EAC|WAC|LIN|SRC|MSC|IOE|NBC|YSC)\d{10}\b", re.IGNORECASE)),
    ("i94_number", re.compile(r"\bI-?94(?:\s*(?:No\.?|Number|#))?[:\s#-]*[A-Z0-9]{11}\b", re.IGNORECASE)),
    (
        "passport_number",
        re.compile(r"\bPassport(?:\s*(?:No\.?|Number|#))?[:\s#-]*[A-Z0-9]{6,12}\b", re.IGNORECASE),
    ),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("email", re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")),
    ("phone", re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?){2}\d{4}\b")),
    (
        "dob_labeled",
        re.compile(
            r"\b(?:DOB|Date of Birth|Birth Date)\s*[:#-]?\s*"
            r"(?:\d{1,2}/\d{1,2}/\d{2,4}|"
            r"(?:January|February|March|April|May|June|July|August|September|October|November|December) "
            r"\d{1,2}, \d{4})\b",
            re.IGNORECASE,
        ),
    ),
    ("date_numeric", re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")),
    (
        "date_long",
        re.compile(
            r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December) "
            r"\d{1,2}, \d{4}\b",
            re.IGNORECASE,
        ),
    ),
    (
        "street_address",
        re.compile(
            r"\b\d{1,6}\s+[A-Za-z0-9][A-Za-z0-9 .'-]{1,60}\s+"
            r"(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Drive|Dr\.?|Lane|Ln\.?|Court|Ct\.?|"
            r"Boulevard|Blvd\.?|Place|Pl\.?|Circle|Cir\.?|Way|Terrace|Ter\.?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "tax_record_indicator",
        re.compile(r"\b(?:Form\s+)?(?:1040|W-2|1099|IRS transcript|tax return|tax transcript)\b", re.IGNORECASE),
    ),
    (
        "medical_record_indicator",
        re.compile(r"\b(?:I-693|sealed medical|medical exam|vaccination record)\b", re.IGNORECASE),
    ),
    (
        "immigration_status_fact",
        re.compile(
            r"\b(?:unlawful presence|overstay|entered without inspection|EWI|removal proceedings|"
            r"asylum|withholding of removal|TPS|DACA|parolee|deferred inspection)\b",
            re.IGNORECASE,
        ),
    ),
    ("long_identifier", re.compile(r"\b[A-Z]{1,3}\d{7,12}\b")),
)

# Words that name a case 8 U.S.C. 1367 protects (VAWA, T and U) or what happened to the client. The statute bars
# disclosing anything about these applicants, and the dashboard shows stage summaries and blockers on screen, so a
# summary never carries these in any matter, whatever the stage's status. They are checked in summaries, blockers and
# client-facing open items only: the vault's memos and the forms rightly use them.
PROTECTED_CASE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "protected_case_term",
        re.compile(
            r"\b(?:VAWA|I-?360|I-?914|I-?918|[TU][- ]visas?|[TU][- ]nonimmigrant|traffick\w*|qualifying\s+crim\w*|"
            r"battery|battered|extreme\s+cruelty|abus(?:e|ed|es|er|ers|ive)|domestic\s+violence)\b",
            re.IGNORECASE,
        ),
    ),
)
# In a matter marked protected (matter-meta.json), more words would tell a reader what kind of case it is.
PROTECTED_MATTER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "protected_matter_term",
        re.compile(
            r"\b(?:victim\w*|self[- ]?petition\w*|(?:8\s+U\.?S\.?C\.?\s*(?:§\s*)?|section\s+)1367|cruel\w*|"
            r"violen\w*|assault\w*|stalk\w*|(?:protection|protective|restraining)\s+orders?)\b",
            re.IGNORECASE,
        ),
    ),
)

TEXT_SUFFIXES = {".csv", ".json", ".md", ".txt", ".yaml", ".yml"}
APPROVED_SENSITIVE_PREFIXES = (
    "output/vault/",
    "output/workflow/",
    # Older layouts kept the forms' fact tables, intent manifests and audits in output/forms/, and the packet and
    # its manifest in output/pdf/ or output/packet/. They are work product, not scratch.
    "output/forms/",
    "output/pdf/",
    "output/packet/",
    # Text extracted from the client's documents (extract_documents.py), kept for later steps.
    "output/working/extracts/",
    "output/working/vault/",
    "output/working/workflow/",
    # Blank USCIS forms, their edition metadata, and the editable filled sources the forms tools keep.
    "output/working/forms/",
    "output/deliverables/",
    # Matters started before the working-folder rename.
    "output/shareable/vault/",
    "output/shareable/workflow/",
    "output/security/",
    "output/privacy/",
    # Set aside by the app: an earlier case's work after the attorney changed what is being filed, and client
    # documents the attorney removed from the matter (kept so they can be put back).
    "output/earlier/",
    "output/removed documents/",
)
QUARANTINE_RELATIVE_ROOT = Path("output/security/quarantine")
# The only places closeout moves a file from: tool scratch inside output/. Anything outside output/ is the client's
# own document (evidence), and the rest of output/ is work product, so neither is ever moved, whatever its name.
SCRATCH_PREFIXES = (
    "output/tmp/",
    "output/working/tmp/",
    "output/working/pdf/",
    "output/working/doc/",
    "output/working/images/",
    "output/working/vault/scratch/",
    "output/doc/",
    "output/images/",
    "output/playwright/",
)


def utc_now_token() -> str:
    return datetime.now(UTC).strftime("%Y%m%d%H%M%S")


def looks_textual(path: Path) -> bool:
    return path.suffix.casefold() in TEXT_SUFFIXES


def scan_text(
    text: str,
    *,
    source: str,
    patterns: tuple[tuple[str, re.Pattern[str]], ...] = SENSITIVE_TEXT_PATTERNS,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for kind, pattern in patterns:
        for match in pattern.finditer(text):
            findings.append(
                {
                    "source": source,
                    "kind": kind,
                    "span": [match.start(), match.end()],
                    "sample": match.group(0)[:8] + "[redacted]",
                }
            )
    return findings


def scan_file(
    path: Path,
    *,
    matter_path: Path,
    max_bytes: int = 500_000,
    patterns: tuple[tuple[str, re.Pattern[str]], ...] = SENSITIVE_TEXT_PATTERNS,
) -> list[dict[str, Any]]:
    if not path.exists() or path.is_dir() or not looks_textual(path):
        return []
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return [
            {
                "source": relative_to_matter(matter_path, path),
                "kind": "read_error",
                "sample": str(exc),
            }
        ]
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
    text = raw.decode("utf-8", errors="ignore")
    return scan_text(text, source=relative_to_matter(matter_path, path), patterns=patterns)


def is_approved_sensitive_location(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    return any(normalized.startswith(prefix) for prefix in APPROVED_SENSITIVE_PREFIXES)


def is_quarantine_location(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    return normalized.startswith(str(QUARANTINE_RELATIVE_ROOT).replace("\\", "/") + "/")


def is_scratch_location(relative_path: str) -> bool:
    """Tool scratch inside output/: the only files closeout may move to quarantine."""
    lower_value = relative_path.replace("\\", "/").casefold()
    if is_quarantine_location(lower_value):
        return False
    return any(lower_value.startswith(prefix) for prefix in SCRATCH_PREFIXES)


def protected_patterns(protected: bool) -> tuple[tuple[str, re.Pattern[str]], ...]:
    return PROTECTED_CASE_PATTERNS + (PROTECTED_MATTER_PATTERNS if protected else ())


def protected_term_failures(*, protected: bool = False, **texts: str | None) -> list[str]:
    """One failure per text (a stage summary, a blocker summary) that names a protected case type. A matter marked
    protected also refuses the words that would tell a reader what kind of case it is."""
    failures: list[str] = []
    for label, text in texts.items():
        if text and scan_text(text, source=label, patterns=protected_patterns(protected)):
            name = label.replace("_", " ").capitalize()
            failures.append(
                f"{name} names a protected case type or what happened to the client (VAWA, I-360, T or U, abuse, "
                "battery, extreme cruelty, trafficking); the dashboard shows it, so keep it generic, such as "
                "\"Prepared the forms; gaps recorded as open items.\""
            )
    return failures


def party_name_failures(matter_path: Path, *, terms: dict[str, Any] | None = None, **texts: str | None) -> list[str]:
    """One failure per text that names a party or carries one of their identifiers, per the forms fact table.
    The failure says what kind of term it found, never the term."""
    terms = terms if terms is not None else matter_privacy_terms(matter_path)
    failures: list[str] = []
    for label, text in texts.items():
        kinds = find_terms(text or "", terms)
        if kinds:
            name = label.replace("_", " ").capitalize()
            what = " and ".join("a person's name" if kind == "name" else "an identifying number" for kind in kinds)
            failures.append(
                f"{name} contains {what} from this matter's fact table; the dashboard shows it, so say what was "
                "done without naming anyone, such as \"Reviewed the client's documents.\""
            )
    return failures


WORKSPACE_MARKER = "stage-workspaces/"


def workspace_path_failures(matter_path: Path, records: list[dict[str, str]], *, limit: int = 5) -> list[str]:
    """JSON artifacts must point at the client's documents where they are, not at a stage workspace's copy, which
    closeout deletes. Names each field that does."""
    failures: list[str] = []
    for record in records:
        relative_path = str(record.get("path") or "")
        if not relative_path.casefold().endswith(".json"):
            continue
        path = matter_path / relative_path
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # the stage's own validators report a missing or malformed file
        found: list[str] = []

        def walk(value: Any, where: str) -> None:
            if len(found) >= limit:
                return
            if isinstance(value, str):
                if WORKSPACE_MARKER in value.replace("\\", "/"):
                    found.append(where or "(top level)")
            elif isinstance(value, dict):
                for key, item in value.items():
                    walk(item, f"{where}.{key}" if where else str(key))
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    walk(item, f"{where}[{index}]")

        walk(payload, "")
        if found:
            failures.append(
                f"{relative_path} points into a stage workspace ({', '.join(found)}). Workspaces are temporary copies "
                "that closeout deletes: use the path relative to the matter folder (the workspace's stage manifest.json "
                "maps each copy to its original)."
            )
    return failures


def lint_stage_completion(
    *,
    matter_path: Path,
    summary: str,
    artifact_records: list[dict[str, str]],
    evidence_records: list[dict[str, str]],
    protected: bool = False,
) -> list[str]:
    failures: list[str] = []

    summary_findings = scan_text(summary, source="stage_summary")
    if summary_findings:
        kinds = ", ".join(sorted({finding["kind"] for finding in summary_findings}))
        failures.append(f"Stage summary still contains sensitive-looking data after redaction: {kinds}.")
    failures.extend(protected_term_failures(protected=protected, stage_summary=summary))
    failures.extend(party_name_failures(matter_path, stage_summary=summary))

    for record in [*artifact_records, *evidence_records]:
        relative_path = record.get("path", "")
        if record.get("retention") == "ephemeral":
            failures.append(f"Passed stage cannot rely on ephemeral artifact: {relative_path}")
        if relative_path.startswith("/"):
            failures.append(f"Passed stage artifact must stay matter-local, not absolute external path: {relative_path}")

        absolute_path = matter_path / relative_path
        if is_approved_sensitive_location(relative_path):
            continue
        file_findings = scan_file(absolute_path, matter_path=matter_path)
        if file_findings:
            kinds = ", ".join(sorted({finding["kind"] for finding in file_findings}))
            failures.append(f"Sensitive-looking text found outside approved protected output: {relative_path} ({kinds}).")

    return failures


def lint_matter(
    matter_path: Path,
    *,
    include_output: bool = False,
    generated_outputs_only: bool = False,
    max_files: int = 1000,
    protected: bool = False,
) -> dict[str, Any]:
    """Scan matter files outside the approved folders. In a protected matter, the words that name the case count as
    findings too."""
    matter_path = matter_path.expanduser().resolve()
    patterns = SENSITIVE_TEXT_PATTERNS + (protected_patterns(True) if protected else ())
    findings: list[dict[str, Any]] = []
    scanned = 0
    for path in sorted(matter_path.rglob("*")):
        if path.is_dir():
            continue
        relative_path = relative_to_matter(matter_path, path)
        if not include_output and relative_path.startswith("output/"):
            continue
        if is_approved_sensitive_location(relative_path):
            continue
        if is_quarantine_location(relative_path):
            continue
        if generated_outputs_only and not is_scratch_location(relative_path):
            continue
        scanned += 1
        findings.extend(scan_file(path, matter_path=matter_path, patterns=patterns))
        if scanned >= max_files:
            break
    return {
        "matter_path": str(matter_path),
        "include_output": include_output,
        "generated_outputs_only": generated_outputs_only,
        "scanned_files": scanned,
        "finding_count": len(findings),
        "findings": findings,
    }


def quarantine_matter(matter_path: Path, *, apply: bool = False, max_files: int = 1000, protected: bool = False) -> dict[str, Any]:
    """Move tool scratch that carries identifiers into output/security/quarantine. Only scratch locations inside
    output/ are ever candidates (is_scratch_location): the client's documents and the work product stay where they
    are, whatever their names say."""
    matter_path = matter_path.expanduser().resolve()
    report = lint_matter(
        matter_path,
        include_output=True,
        generated_outputs_only=True,
        max_files=max_files,
        protected=protected,
    )
    findings_by_source: dict[str, list[dict[str, Any]]] = {}
    for finding in report["findings"]:
        source = finding["source"]
        findings_by_source.setdefault(source, []).append(finding)

    token = utc_now_token()
    quarantine_root = matter_path / QUARANTINE_RELATIVE_ROOT / token
    candidates: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []

    for source in sorted(findings_by_source):
        if source.startswith("/"):
            continue
        if not is_scratch_location(source):
            continue
        source_path = matter_path / source
        if not source_path.exists() or source_path.is_dir():
            continue
        candidate = {
            "source": source,
            "finding_kinds": sorted({item["kind"] for item in findings_by_source[source]}),
            "finding_count": len(findings_by_source[source]),
        }
        candidates.append(candidate)
        if not apply:
            continue
        destination = quarantine_root / source
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.move(str(source_path), str(destination))
        os.chmod(destination, 0o600)
        quarantined.append({**candidate, "quarantine_path": relative_to_matter(matter_path, destination)})

    manifest_path: Path | None = None
    if apply and quarantined:
        manifest = {
            "schema_version": 1,
            "generated_at": now_iso(precise=True),
            "matter_path": str(matter_path),
            "apply": apply,
            "quarantine_root": relative_to_matter(matter_path, quarantine_root),
            "quarantined_count": len(quarantined),
            "quarantined": quarantined,
        }
        manifest_path = quarantine_root / "quarantine manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        os.chmod(manifest_path, 0o600)
        ensure_policy(matter_path)
        log_access_event(
            matter_path,
            event_type="sensitive_output_quarantined",
            role="system",
            actor="system",
            data_planes=["audit_metadata"],
            artifacts=[str(manifest_path)],
            notes=f"quarantined_count={len(quarantined)}",
        )

    return {
        "matter_path": str(matter_path),
        "apply": apply,
        "candidate_count": len(candidates),
        "quarantined_count": len(quarantined),
        "quarantine_root": relative_to_matter(matter_path, quarantine_root),
        "manifest_path": relative_to_matter(matter_path, manifest_path) if manifest_path else None,
        "candidates": candidates,
        "quarantined": quarantined,
    }

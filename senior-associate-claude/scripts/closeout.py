#!/usr/bin/env python3
"""Closeout, and the dashboard of what it would do: the end of a work session in a matter folder.

run_matter_workflow.py's ``closeout`` and ``security-dashboard`` commands call these.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.matter_access import WORKFLOW_RECORD_DIRS, log_access_event
from scripts.matter_protection import is_protected_matter
from scripts.matter_state import now_iso, relative_to_matter, write_json_atomic
from scripts.privacy_cleanup import MATTER_TARGETS, delete_path, delete_vault_clutter, summarize_path, vault_clutter
from scripts.privacy_lint import lint_matter, quarantine_matter


def recent_access_events(matter_path: Path, *, limit: int = 10) -> list[dict[str, Any]]:
    access_log = matter_path / "output/privacy/access_log.jsonl"
    if not access_log.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in access_log.read_text(encoding="utf-8").splitlines()[-limit:]:
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"raw": line})
    return events


def workflow_summaries(matter_path: Path) -> list[dict[str, Any]]:
    state_paths: list[Path] = []
    for relative_root in WORKFLOW_RECORD_DIRS:  # the current layout first, then older ones
        workflow_root = matter_path / relative_root
        if workflow_root.exists():
            state_paths.extend(sorted(workflow_root.rglob("matter_status.json")))
    summaries: list[dict[str, Any]] = []
    for state_path in state_paths:
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception as exc:
            summaries.append(
                {
                    "state_path": relative_to_matter(matter_path, state_path),
                    "error": str(exc),
                }
            )
            continue
        summaries.append(
            {
                "state_path": relative_to_matter(matter_path, state_path),
                "overall_status": payload.get("overall_status"),
                "current_stage": payload.get("current_stage"),
                "next_stage": payload.get("next_stage"),
                "open_blockers": [
                    blocker for blocker in payload.get("blockers", []) if blocker.get("status") == "open"
                ],
            }
        )
    return summaries


def cleanup_report(matter_path: Path) -> list[dict[str, Any]]:
    return [summarize_path(target_type, matter_path, matter_path / relative_path) for target_type, relative_path in MATTER_TARGETS]


def quarantine_report(matter_path: Path) -> dict[str, Any]:
    root = matter_path / "output/security/quarantine"
    records: list[dict[str, Any]] = []
    if root.exists():
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            file_count = sum(1 for item in child.rglob("*") if item.is_file())
            manifest = child / "quarantine manifest.json"
            records.append(
                {
                    "path": relative_to_matter(matter_path, child),
                    "file_count": file_count,
                    "manifest_exists": manifest.exists(),
                }
            )
    return {
        "root": relative_to_matter(matter_path, root),
        "quarantine_run_count": len(records),
        "runs": records,
    }


def build_security_dashboard(
    matter_path: Path,
    *,
    include_findings: bool = False,
    recent_event_limit: int = 10,
) -> dict[str, Any]:
    matter_path = matter_path.expanduser().resolve()
    lint_report = lint_matter(matter_path, include_output=True, generated_outputs_only=True,
                              protected=is_protected_matter(matter_path))
    finding_counts: dict[str, int] = {}
    for finding in lint_report["findings"]:
        kind = finding.get("kind", "unknown")
        finding_counts[kind] = finding_counts.get(kind, 0) + 1
    lint_payload = {
        "finding_count": lint_report["finding_count"],
        "scanned_files": lint_report["scanned_files"],
        "finding_counts": finding_counts,
    }
    if include_findings:
        lint_payload["findings"] = lint_report["findings"]
    return {
        "generated_at": now_iso(precise=True),
        "matter_path": str(matter_path),
        "workflows": workflow_summaries(matter_path),
        "recent_access_events": recent_access_events(matter_path, limit=recent_event_limit),
        "cleanup_targets": cleanup_report(matter_path),
        "privacy_lint": lint_payload,
        "quarantine": quarantine_report(matter_path),
    }


def dashboard_summary_lines(payload: dict[str, Any]) -> list[str]:
    """A few lines for the dashboard; --json carries every target, event, and finding."""
    lines = [f"Matter: {payload.get('matter_path')}"]
    for workflow in payload.get("workflows", []):
        if workflow.get("error"):
            lines.append(f"Workflow {workflow['state_path']}: unreadable ({workflow['error']})")
            continue
        blockers = len(workflow.get("open_blockers") or [])
        lines.append(
            f"Workflow: {workflow.get('overall_status')}, next stage {workflow.get('next_stage') or '-'}, "
            f"{blockers} open blocker(s) [{workflow['state_path']}]"
        )
    lint = payload.get("privacy_lint") or {}
    kinds = ", ".join(f"{kind} {count}" for kind, count in sorted((lint.get("finding_counts") or {}).items()))
    lines.append(
        f"Privacy lint: {lint.get('finding_count', 0)} finding(s) in {lint.get('scanned_files', 0)} scanned file(s)"
        + (f" ({kinds})" if kinds else "")
    )
    targets = [target for target in payload.get("cleanup_targets", []) if target.get("exists")]
    if targets:
        listed = ", ".join(f"{target['type']} ({target['file_count']} files)" for target in targets)
        lines.append(f"Scratch closeout would delete: {listed}")
    else:
        lines.append("Scratch closeout would delete: nothing")
    quarantine = payload.get("quarantine") or {}
    runs = quarantine.get("runs") or []
    lines.append(f"Quarantine: {len(runs)} run(s), {sum(run.get('file_count', 0) for run in runs)} file(s)")
    events = payload.get("recent_access_events") or []
    if events:
        last = events[-1]
        lines.append(f"Recent access events: {len(events)} (last: {last.get('event_type', '?')} at {last.get('timestamp', '?')})")
    lines.append("Full detail: --json (add --include-findings for each lint finding).")
    return lines


def closeout_summary_lines(report: dict[str, Any]) -> list[str]:
    """A few lines for a closeout; the full report is the closeout report file (or --json)."""
    quarantine = report.get("quarantine") or {}
    if report.get("dry_run"):
        targets = [target for target in report.get("cleanup_targets_before", []) if target.get("exists")]
        renders = report.get("vault_renders") or {}
        if renders.get("file_count"):
            targets.append(renders)
        listed = ", ".join(f"{t['type']} ({t['file_count']} files)" for t in targets) or "nothing"
        return [
            f"Dry run. Would delete: {listed}.",
            f"Would quarantine {quarantine.get('candidate_count', 0)} file(s).",
        ]
    deleted = list(report.get("deleted_targets") or [])
    renders = report.get("vault_renders") or {}
    if renders.get("file_count"):
        deleted.append(renders)
    listed = ", ".join(f"{t['type']} ({t['file_count']} files)" for t in deleted) or "nothing to delete"
    lines = [
        f"Closeout done. Deleted: {listed}.",
        f"Quarantined {quarantine.get('quarantined_count', 0)} stray sensitive file(s)"
        + (f" to {quarantine.get('quarantine_root')}." if quarantine.get("quarantined_count") else "."),
    ]
    if report.get("closeout_report_path"):
        lines.append(f"Report: {report['closeout_report_path']}")
    return lines


def closeout_matter(matter_path: Path, *, dry_run: bool = False) -> dict[str, Any]:
    """Clean a matter's working files at the end of a session. In order: move tool scratch inside output/ that
    carries identifiers into quarantine (never the client's documents or the work product); delete the scratch
    folders and stage workspaces (MATTER_TARGETS); delete the page renders, OCR text and scratch that stages leave
    in the vault. Memos, findings, plans, the forms and the packet stay. In a protected matter (8 U.S.C. 1367) the
    quarantine also catches scratch that names the case, and the report lists counts, not file names."""
    matter_path = matter_path.expanduser().resolve()
    protected = is_protected_matter(matter_path)
    cleanup_before = cleanup_report(matter_path)
    quarantine = quarantine_matter(matter_path, apply=not dry_run, protected=protected)

    deleted_targets: list[dict[str, Any]] = []
    if not dry_run:
        for target_type, relative_path in MATTER_TARGETS:
            target = matter_path / relative_path
            summary = summarize_path(target_type, matter_path, target)
            if summary["exists"]:
                delete_path(target)
                summary["deleted"] = True
                summary["exists_after"] = target.exists()
                deleted_targets.append(summary)
        vault_renders = delete_vault_clutter(matter_path)
    else:
        clutter = vault_clutter(matter_path)
        vault_renders = {"type": "vault_renders", "file_count": len(clutter),
                         "total_bytes": sum(path.stat().st_size for path in clutter)}

    if protected:
        # The closeout report outlives the session; in a protected matter it doesn't list the scratch it moved.
        for key in ("candidates", "quarantined"):
            quarantine[key] = [{k: v for k, v in item.items() if k not in {"source", "quarantine_path"}}
                               for item in quarantine.get(key, [])]

    report = {
        "schema_version": 1,
        "generated_at": now_iso(precise=True),
        "matter_path": str(matter_path),
        "dry_run": dry_run,
        "protected_matter": protected,
        "quarantine": quarantine,
        "cleanup_targets_before": cleanup_before,
        "deleted_targets": deleted_targets,
        "vault_renders": vault_renders,
    }

    closeout_report_path = matter_path / "output/security/closeout report.json"
    if not dry_run:
        write_json_atomic(closeout_report_path, report)
        log_access_event(
            matter_path,
            event_type="secure_matter_closeout",
            role="senior_associate",
            actor="system",
            data_planes=["audit_metadata"],
            artifacts=[str(closeout_report_path)],
            notes=f"quarantined={quarantine['quarantined_count']}; deleted_targets={len(deleted_targets)}",
        )
        report["closeout_report_path"] = str(closeout_report_path)
    return report

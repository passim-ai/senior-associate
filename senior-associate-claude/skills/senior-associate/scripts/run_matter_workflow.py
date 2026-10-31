#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from contextlib import contextmanager
import json
import sys
from pathlib import Path
from typing import Any, Callable, Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.matter_access import assert_role_access, ensure_policy, log_access_event, require_matter_folder
from scripts.matter_protection import is_protected_matter, protection
from scripts.matter_state import (
    LEASE_HOLDERS,
    LEASE_KINDS,
    OPEN_ITEMS_FILE,
    RUN_ENDED,
    RUN_LOST,
    RUN_NO_LEASE,
    RUN_TAKEN,
    LockTimeout,
    acquire_lease,
    add_event,
    apply_attorney_actions,
    attorney_actions,
    heartbeat_lease,
    lease_is_fresh,
    matter_lock,
    merge_attorney_actions,
    new_run_id,
    now_iso,
    parse_time,
    read_lease,
    read_meta,
    read_open_items,
    release_lease,
    renew_run_lease,
    update_meta,
    write_json_atomic,
)
from scripts.closeout import build_security_dashboard, closeout_matter, closeout_summary_lines, dashboard_summary_lines
from matter_workflow import (
    REVIEW_STAGE_IDS,
    ROLLBACK_TARGETS,
    STAGE_DEFINITIONS,
    OpenItemRefused,
    note_open_item,
    reroute_line,
    set_open_items_packet_status,
    upsert_open_item,
    WORKFLOW_TEMPLATES,
    changed_since,
    changed_since_lines,
    compare_state_to_intake,
    complete_stage,
    ensure_case_theory_evidence_map,
    initialize_state,
    is_re_review,
    load_state,
    packet_status_line,
    record_matter_folder,
    refresh_derived_fields,
    reroute_from_category,
    reroute_from_stage,
    resolve_blocker,
    save_state,
    set_last_pass,
    stage_record,
    take_snapshot,
    start_stage,
    state_snapshot,
    status_lines,
    workflow_state_path,
    write_stage_snapshot,
)

# Exit code for "someone else holds a fresh lease on this matter" (lease acquire).
EXIT_LEASE_HELD = 3

# Commands that change the matter's record. They renew the run's lease even when it has gone quiet: a command that
# changes the work is proof the run is alive. Read-only commands renew only a fresh lease, so looking at a matter
# never revives a run that has gone.
MUTATING_COMMANDS = {"start-stage", "complete-stage", "resolve-blocker", "reroute", "closeout", "apply-attorney-actions", "set-protected",
                     "open-items"}
# Commands that change the matter, for --run-id: given the run's id, each renews only that run's lease, and refuses
# (exit 3, nothing changed) once another run holds the matter or this run's lease has ended, so a run that lost the
# matter while it worked (it went quiet, and someone else started) stops instead of working over the other run.
CHANGING_COMMANDS = MUTATING_COMMANDS | {"init", "ensure"}
NOT_YOURS = {
    RUN_TAKEN: "Another run holds this matter now; stop. Nothing was changed.",
    RUN_LOST: "Another run took this matter over while this run was quiet; stop. Nothing was changed.",
    RUN_ENDED: "This run's lease on the matter has ended (it was released, or the attorney stopped it in the app); stop. "
               "Nothing was changed.",
}


def add_command(subparsers: Any, name: str, help: str, *, json: str | None = "", full: bool = False,
                slug: bool = True) -> argparse.ArgumentParser:
    """A command's parser with what most share: the matter folder, the --workflow-slug track, and --json (with its
    help; None for none), or with ``full`` the short --json result and the whole --full state."""
    parser = subparsers.add_parser(name, help=help)
    parser.add_argument("matter_path", type=Path)
    if slug:
        parser.add_argument(
            "--workflow-slug",
            help="Optional matter-local workflow namespace, stored at output/working/workflow/<slug>/matter_status.json.",
        )
    if full:
        parser.add_argument("--json", action="store_true", help="Print a short JSON result.")
        parser.add_argument("--full", action="store_true", help="Print the whole workflow state as JSON.")
    elif json is not None:
        parser.add_argument("--json", action="store_true", help=json or None)
    return parser


def add_intake_arguments(parser: argparse.ArgumentParser, *, required: bool = True) -> None:
    parser.add_argument("--matter-type", required=required)
    parser.add_argument("--filing-posture", required=required)
    parser.add_argument("--deliverable", required=required)
    parser.add_argument(
        "--workflow-key",
        default=None if not required else "full_packet",
        choices=sorted(WORKFLOW_TEMPLATES),
        help="Workflow template to initialize or validate.",
    )
    parser.add_argument(
        "--stage-id",
        dest="stage_ids",
        action="append",
        default=[],
        help="Optional custom stage list. If provided, workflow_key is ignored and the workflow becomes custom.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Persist and manage Immigration Packet Builder workflow state inside a matter folder."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = add_command(subparsers, "init", "Initialize matter workflow state.", json="Print the initialized state as JSON.")
    add_intake_arguments(init_parser)
    init_parser.add_argument("--force", action="store_true", help="Replace an existing workflow record (the attorney started over).")

    ensure_parser = add_command(
        subparsers, "ensure", "Initialize workflow state if missing, or resume it when it matches this intake (or with --resume).",
        json="Print the current state as JSON.",
    )
    add_intake_arguments(ensure_parser, required=False)
    ensure_parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume the recorded workflow with its recorded intake; intake options, if given, must match it.",
    )

    add_command(subparsers, "status", "Print workflow status.")
    dashboard_parser = add_command(subparsers, "security-dashboard", "Print matter security/workflow posture.",
                                   json="Print the full dashboard as JSON (default: a short summary).")
    dashboard_parser.add_argument("--include-findings", action="store_true")
    closeout_parser = add_command(
        subparsers, "closeout",
        "Quarantine tool scratch with identifiers, delete scratch, stage workspaces and vault renders, and write the closeout report.",
        json="Print the full closeout report as JSON (default: a short summary).",
    )
    closeout_parser.add_argument("--dry-run", action="store_true")
    add_command(subparsers, "next-stage", "Print the first line of next-stages.", json=None)
    add_command(subparsers, "next-stages", "Print every stage to run now, one per line: any left in progress, then every "
                "ready stage. Start them together.", json=None)

    start_parser = add_command(subparsers, "start-stage", "Mark a stage in progress.", full=True)
    start_parser.add_argument("stage_id")

    complete_parser = add_command(subparsers, "complete-stage", "Mark a stage complete, blocked, failed, or skipped.", full=True)
    complete_parser.add_argument("stage_id")
    complete_parser.add_argument(
        "--status",
        required=True,
        choices=("passed", "failed", "blocked", "skipped"),
    )
    complete_parser.add_argument("--summary", required=True)
    complete_parser.add_argument("--artifact", dest="artifacts", action="append", default=[])
    complete_parser.add_argument("--evidence-file", dest="evidence_files", action="append", default=[])
    complete_parser.add_argument("--blocker-summary")
    complete_parser.add_argument(
        "--blocker-owner",
        choices=("client", "attorney", "system", "agency", "third_party"),
    )
    complete_parser.add_argument(
        "--attorney-approved",
        help="The attorney's go-ahead, in a line, for skipping a review or the handoff whose work wasn't skipped.",
    )
    complete_parser.add_argument(
        "--unchanged-reason",
        help="Why a pass whose main artifact is identical to the last pass is still right (nothing needed to change).",
    )

    resolve_parser = add_command(subparsers, "resolve-blocker", "Resolve an open blocker.", full=True)
    resolve_parser.add_argument("blocker_id")
    resolve_parser.add_argument("--resolution-note", required=True)
    resolve_parser.add_argument(
        "--reset-stage-to",
        default="pending",
        choices=("pending", "in_progress"),
        help="How to reset the blocked stage after resolution.",
    )

    reroute_parser = add_command(
        subparsers, "reroute", "Reset a stage and the stages that depend on it after a later review finds a defect it owns.",
        full=True,
    )
    reroute_group = reroute_parser.add_mutually_exclusive_group(required=True)
    reroute_group.add_argument("--from-stage")
    reroute_group.add_argument(
        "--category",
        choices=tuple(sorted(ROLLBACK_TARGETS)),
        help="Convenience reroute class such as forms_defect or cover_letter_defect.",
    )
    reroute_parser.add_argument("--reason", required=True)
    reroute_parser.add_argument("--detected-in-stage")
    reroute_parser.add_argument(
        "--attorney-approved",
        help="The attorney asked for this redo; it doesn't count toward a review's limit of two send-backs per run.",
    )

    changed_parser = add_command(
        subparsers, "changed-since",
        "What changed since a stage last passed, and where its previous findings are: the brief for a re-review.",
        json="Print the full report as JSON.",
    )
    changed_parser.add_argument("stage_id")
    changed_parser.add_argument(
        "--fresh",
        action="store_true",
        help="The attorney asked for a full, fresh review: list the previous findings as reference and review everything.",
    )

    lease_parser = subparsers.add_parser(
        "lease",
        help="Who is working on the matter now: acquire (exit 3 when someone else holds it), heartbeat, release, show.",
    )
    lease_parser.add_argument("action", choices=("acquire", "heartbeat", "release", "show"))
    lease_parser.add_argument("matter_path", type=Path)
    lease_parser.add_argument("--run-id", help="The run id from the app's brief; acquire makes a new one when it's missing.")
    lease_parser.add_argument("--kind", default="build", choices=sorted(LEASE_KINDS))
    lease_parser.add_argument("--holder", default="orchestrator", choices=sorted(LEASE_HOLDERS))
    lease_parser.add_argument("--description", default="")
    lease_parser.add_argument("--stage", help="heartbeat: the stage(s) running now.")
    lease_parser.add_argument("--outcome", default="done", choices=("done", "stopped", "failed"))
    lease_parser.add_argument("--json", action="store_true")

    add_command(subparsers, "apply-attorney-actions",
                "Write the attorney's Mark done, Reopen and Accept this risk into the open items list.", slug=False)

    items_parser = subparsers.add_parser(
        "open-items",
        help="Add or change one open item, or add a note to one, under the matter's lock and the contract's rules.",
    )
    items_actions = items_parser.add_subparsers(dest="items_action", required=True)
    upsert_parser = add_command(items_actions, "upsert",
                                "Add an item, or change the item with its id (fields given replace its own; notes are added).",
                                slug=False)
    item_source = upsert_parser.add_mutually_exclusive_group(required=True)
    item_source.add_argument("--item-json", help="The item as JSON, with at least its id.")
    item_source.add_argument("--item-file", type=Path, help="A file holding the item as JSON (for long text).")
    note_parser = add_command(items_actions, "note", "Add one line to an item's history (notes, never shown in the app).",
                              slug=False)
    note_parser.add_argument("item_id")
    note_parser.add_argument("text")
    status_parser = add_command(items_actions, "packet-status",
                                "Set the list's packet_status at the handoff (ready_to_file only with nothing blocking).",
                                slug=False)
    status_parser.add_argument("packet_status", choices=("draft", "ready_to_file"))

    protected_parser = add_command(
        subparsers, "set-protected",
        "Mark the matter protected under 8 U.S.C. 1367 (VAWA, T or U), or lift it (the attorney only).", slug=False,
    )
    protected_group = protected_parser.add_mutually_exclusive_group(required=True)
    protected_group.add_argument("--on", action="store_true")
    protected_group.add_argument("--off", action="store_true")
    protected_parser.add_argument("--reason", required=True, choices=("docs_review", "attorney"))

    # Every command but lease (which has its own) takes the run's id; open-items takes it after its action.
    for name, sub in subparsers.choices.items():
        if name == "open-items":
            for nested in items_actions.choices.values():
                add_run_argument(nested)
        elif name != "lease":
            add_run_argument(sub)

    return parser


def add_run_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--run-id",
        help="Your run's id (from lease acquire, or the app's brief). A command that changes the matter then renews "
             "only your run's lease, and exits 3 without changing anything once another run holds the matter.",
    )


# ---------------------------------------------------------------------------
# Reading and changing the record, under the matter's lock
# ---------------------------------------------------------------------------

def read_state(args: argparse.Namespace) -> dict:
    """Load the record under the lock, for a command that only reads it."""
    with matter_lock(args.matter_path):
        return load_state(args.state_path)


# Recording a pass's snapshot waits longer for the lock than other commands: the pass is already saved by then, and
# giving up would only lose the re-review's comparison point.
SNAPSHOT_LOCK_TIMEOUT = 60.0


@contextmanager
def changing_state(args: argparse.Namespace, timeout: float | None = None) -> Iterator[dict]:
    """Read, change and write the record as one step, so two stages finishing side by side (or the app writing
    beside a run) never lose each other's changes. The record is saved only when the block completes."""
    with matter_lock(args.matter_path, **({"timeout": timeout} if timeout else {})):
        state = load_state(args.state_path)
        record_matter_folder(state, args.matter_path)
        yield state
        save_state(args.state_path, state)


def given_run_id(args: argparse.Namespace) -> str:
    return (getattr(args, "run_id", None) or "").strip()


def current_run_id(matter_path: Path, args: argparse.Namespace | None = None) -> str | None:
    """The run a change belongs to: the one the command names (--run-id), else whoever holds a fresh lease."""
    if args is not None and given_run_id(args):
        return given_run_id(args)
    lease = read_lease(matter_path)
    return str(lease["run_id"]) if lease_is_fresh(lease) else None


def renew_lease(matter_path: Path, *, mutating: bool, stage: str | None = None, run_id: str = "") -> None:
    """Renew the lease as a sign the run is alive. With the run's id, only that run's own lease; without, whichever
    unreleased lease exists (as before --run-id): a changing command renews it even when quiet, a read-only one only
    while fresh."""
    lease = read_lease(matter_path)
    if run_id:
        if lease and lease.get("run_id") == run_id and not lease.get("released_at") and (mutating or lease_is_fresh(lease)):
            heartbeat_lease(matter_path, run_id=run_id, stage=stage)
        return
    if lease and not lease.get("released_at") and (mutating or lease_is_fresh(lease)):
        heartbeat_lease(matter_path, stage=stage)


def guard_run(args: argparse.Namespace, matter_path: Path) -> int | None:
    """Before a command runs: renew the lease, and with --run-id on a command that changes the matter, refuse when
    the run no longer holds it. Returns the exit code when the command must not run."""
    run_id = given_run_id(args)
    changing = args.command in CHANGING_COMMANDS
    if not run_id or not changing:
        renew_lease(matter_path, mutating=args.command in MUTATING_COMMANDS, run_id=run_id)
        return None
    what, _lease = renew_run_lease(matter_path, run_id)
    if what in NOT_YOURS:
        print(NOT_YOURS[what], file=sys.stderr)
        return EXIT_LEASE_HELD
    return None


def stage_label(stage_id: str) -> str:
    definition = STAGE_DEFINITIONS.get(stage_id)
    return definition.label if definition else stage_id


def timeline(matter_path: Path, kind: str, text: str, **extra: object) -> None:
    """One line on the matter's timeline. The text is the step's plain name: no case type, names, or paths."""
    try:
        add_event(matter_path, kind, text, actor="claude", **extra)
    except (OSError, LockTimeout):
        pass  # the timeline is a courtesy; the record above is what counts


BLOCKED_ON = {
    "client": "the client",
    "attorney": "you",
    "system": "a setup problem on this Mac",
    "agency": "USCIS or another agency",
    "third_party": "someone outside the firm",
}


def completion_event(stage_id: str, status: str, *, blocker_owner: str | None, attorney_approved: str | None) -> tuple[str, str]:
    label = stage_label(stage_id)
    if status == "passed":
        if stage_id == "attorney_handoff":
            return "stage_passed", "Your memo, the client request and the open items are up to date."
        if stage_id in REVIEW_STAGE_IDS:
            return "stage_passed", f"{label} passed."
        return "stage_passed", f"{label} is done."
    if status == "blocked":
        return "stage_blocked", f"{label} is waiting on {BLOCKED_ON.get(blocker_owner or '', 'something')}."
    if status == "skipped":
        return "stage_skipped", f"{label} was skipped" + (", as you approved." if attorney_approved else ".")
    return "stage_failed", f"{label} didn't finish."


def print_state(state: dict, *, as_json: bool, matter_path: Path) -> None:
    snapshot = state_snapshot(state)
    meta = read_meta(matter_path)
    shield = protection(matter_path, snapshot["matter"].get("matter_type"), meta=meta)
    meta["protected"], meta["protected_reason"] = bool(shield["protected"]), str(shield["reason"])
    if as_json:
        lease = read_lease(matter_path)
        snapshot["packet"] = packet_status_line(matter_path)
        snapshot["meta"] = meta
        snapshot["lease"] = {**lease, "fresh": lease_is_fresh(lease)} if lease else None
        print(json.dumps(snapshot, indent=2))
        return
    print("\n".join(status_lines(snapshot, matter_path=matter_path, meta=meta)))


def print_result(state: dict, args: argparse.Namespace, lines: list[str], result: dict, matter_path: Path) -> None:
    """Mutating commands print a few lines; --json a short result; --full the whole state."""
    if getattr(args, "full", False):
        print_state(state, as_json=True, matter_path=matter_path)
    elif getattr(args, "json", False):
        print(json.dumps(result, indent=2))
    else:
        print("\n".join(lines))


def next_stage_line(state: dict, matter_path: Path) -> str:
    snapshot = state_snapshot(state)
    if snapshot["overall_status"] == "blocked":
        return "Next stage: none while a blocker is open."
    running = snapshot.get("running") or []
    ready = snapshot.get("ready") or []
    if running or ready:
        parts = []
        if running:
            parts.append(f"in progress: {', '.join(running)}")
        if ready:
            notes = [
                f"{stage_id} (re-review)" if is_re_review(stage_record(snapshot, stage_id)) else stage_id
                for stage_id in ready
            ]
            parts.append(("ready, start together: " if len(ready) > 1 else "ready: ") + ", ".join(notes))
        return f"Next stage: {snapshot['next_stage']}. Now {'; '.join(parts)}."
    packet = packet_status_line(matter_path)
    return f"Next stage: none; every stage is done. Packet: {packet or '-'}."


def result_payload(state: dict, matter_path: Path, **extra: object) -> dict:
    snapshot = state_snapshot(state)
    return {
        **extra,
        "overall_status": snapshot["overall_status"],
        "next_stage": snapshot["next_stage"],
        "running": snapshot.get("running") or [],
        "ready": snapshot.get("ready") or [],
        "packet": packet_status_line(matter_path),
    }


def ensure_workflow_access(matter_path: Path) -> None:
    ensure_policy(matter_path)
    assert_role_access(matter_path, role="senior_associate", data_planes=["audit_metadata"])


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def new_record(args: argparse.Namespace) -> dict:
    """Start the matter's workflow record from this intake, and its case theory map."""
    state = initialize_state(
        matter_path=args.matter_path,
        matter_type=args.matter_type,
        filing_posture=args.filing_posture,
        deliverable=args.deliverable,
        workflow_key=args.workflow_key or "full_packet",
        custom_stage_ids=args.stage_ids or None,
    )
    ensure_case_theory_evidence_map(matter_path=args.matter_path, state=state, state_path=args.state_path)
    save_state(args.state_path, state)
    return state


def command_init(args: argparse.Namespace) -> int:
    with matter_lock(args.matter_path):
        if args.state_path.exists() and not args.force:
            raise ValueError(
                f"This matter already has a workflow record ({args.state_path}). Run ensure --resume to continue it."
            )
        state = new_record(args)
    print_state(state, as_json=args.json, matter_path=args.matter_path)
    return 0


INTAKE_OPTIONS = ("matter_type", "filing_posture", "deliverable")


def command_ensure(args: argparse.Namespace) -> int:
    """Sets ``args.ensured`` to what it did, for the access log: "created", "moved" (the folder), or nothing ("")."""
    matter_path, state_path = args.matter_path, args.state_path
    given = {key: getattr(args, key) for key in INTAKE_OPTIONS if getattr(args, key) is not None}
    missing = [f"--{key.replace('_', '-')}" for key in INTAKE_OPTIONS if key not in given]
    with matter_lock(matter_path):
        if not state_path.exists():
            if args.resume:
                raise ValueError(
                    "There is no workflow record to resume in this matter yet. Run ensure with --matter-type, "
                    "--filing-posture and --deliverable to start one."
                )
            if missing:
                raise ValueError(f"ensure needs {', '.join(missing)} to start a workflow record (or --resume for an existing one).")
            state = new_record(args)
            args.ensured = "created"
        else:
            if missing and not args.resume:
                raise ValueError(f"ensure needs {', '.join(missing)}, or --resume to continue with the recorded intake.")
            state = load_state(state_path)
            # With --resume the recorded intake stands, and whatever is given alongside it must agree with it.
            mismatches = compare_state_to_intake(
                state,
                **given,
                workflow_key=args.workflow_key if args.resume else args.workflow_key or "full_packet",
                custom_stage_ids=args.stage_ids or None,
            )
            if mismatches:
                mismatch_block = "\n".join(f"- {item}" for item in mismatches)
                raise ValueError(
                    "This matter's workflow record was set up for a different filing than this request:\n"
                    f"{mismatch_block}\n"
                    "Don't start over: the record holds the work done so far. If the request is the same matter, "
                    "run ensure --resume to continue with the recorded intake. If the case or posture really "
                    "changed, stop and tell the attorney; they change it on the matter page (Change what is being "
                    "filed), which sets the earlier work aside."
                )
            args.ensured = "moved" if record_matter_folder(state, matter_path) else ""
            ensure_case_theory_evidence_map(matter_path=matter_path, state=state, state_path=state_path)
            refresh_derived_fields(state)
            save_state(state_path, state)
    print_state(state, as_json=args.json, matter_path=matter_path)
    return 0


def command_status(args: argparse.Namespace) -> int:
    print_state(read_state(args), as_json=args.json, matter_path=args.matter_path)
    return 0


def command_security_dashboard(args: argparse.Namespace) -> int:
    payload = build_security_dashboard(args.matter_path, include_findings=args.include_findings)
    print(json.dumps(payload, indent=2) if args.json else "\n".join(dashboard_summary_lines(payload)))
    return 0


def command_closeout(args: argparse.Namespace) -> int:
    payload = closeout_matter(args.matter_path, dry_run=args.dry_run)
    print(json.dumps(payload, indent=2) if args.json else "\n".join(closeout_summary_lines(payload)))
    return 0


def command_next_stages(args: argparse.Namespace) -> int:
    """next-stages, and next-stage, its first line."""
    state = read_state(args)
    refresh_derived_fields(state)
    first_only = args.command == "next-stage"
    # Nothing starts while a blocker is open (start-stage refuses), so nothing is offered either.
    stages = [] if state["overall_status"] == "blocked" else list(state.get("running") or []) + list(state.get("ready") or [])
    if first_only:
        print(stages[0] if stages else "")
    elif stages:
        print("\n".join(stages))
    return 0


def command_start_stage(args: argparse.Namespace) -> int:
    matter_path = args.matter_path
    stage_id = args.stage_id
    with changing_state(args) as state:
        start_stage(state, stage_id, run_id=current_run_id(matter_path, args))
    renew_lease(matter_path, mutating=True, stage=",".join(state.get("running") or []), run_id=given_run_id(args))
    timeline(matter_path, "stage_started", f"{stage_label(stage_id)} started.", stage=stage_id)
    stage = stage_record(state, stage_id)
    line = f"{stage_id}: in progress."
    if is_re_review(stage):
        line += f" Re-review: changed-since \"{matter_path}\" {stage_id} lists its previous findings and what changed."
    print_result(
        state,
        args,
        [line],
        result_payload(state, matter_path, stage_id=stage_id, status="in_progress", re_review=is_re_review(stage)),
        matter_path,
    )
    return 0


def command_complete_stage(args: argparse.Namespace) -> int:
    matter_path = args.matter_path
    stage_id = args.stage_id
    # The attorney's Mark done / Reopen / Accept this risk go into the open items first, so the handoff's checks
    # (and the next stage) see the list the attorney sees.
    applied = merge_attorney_actions(matter_path)
    run_id = current_run_id(matter_path, args)
    with changing_state(args) as state:
        blocker = complete_stage(
            state,
            matter_path=matter_path,
            stage_id=stage_id,
            status=args.status,
            summary=args.summary,
            artifacts=args.artifacts,
            evidence_files=args.evidence_files,
            blocker_summary=args.blocker_summary,
            blocker_owner=args.blocker_owner,
            attorney_approved=args.attorney_approved,
            unchanged_reason=args.unchanged_reason,
            protected=is_protected_matter(matter_path, state["matter"].get("matter_type")),
            run_id=run_id,
        )
        completed_at = stage_record(state, stage_id)["completed_at"]
        extra_paths = list(stage_record(state, stage_id)["artifacts"]) + list(stage_record(state, stage_id)["evidence_files"])
    snapshot_files = None
    snapshot_note = None
    if args.status == "passed":
        # The hashes a later re-review compares against (changed-since). Hashing reads every client document, so it
        # happens outside the lock; the snapshot is written and the record updated under it, and only while the
        # stage is still the pass just recorded.
        files = take_snapshot(matter_path, extra_paths)
        try:
            with changing_state(args, timeout=SNAPSHOT_LOCK_TIMEOUT) as state:
                stage = stage_record(state, stage_id)
                if stage["status"] == "passed" and stage["completed_at"] == completed_at:
                    set_last_pass(stage, write_stage_snapshot(matter_path=matter_path, state_path=args.state_path,
                                                              stage_id=stage_id, files=files))
                    snapshot_files = len(files)
        except LockTimeout:
            # The pass itself is saved; only the re-review's comparison point is missing (it then reviews in full).
            snapshot_note = "The pass is recorded, but the record was too busy to save its snapshot; a later re-review of it reviews in full."
    renew_lease(matter_path, mutating=True, stage=",".join(state.get("running") or []), run_id=given_run_id(args))
    kind, text = completion_event(stage_id, args.status, blocker_owner=args.blocker_owner, attorney_approved=args.attorney_approved)
    timeline(matter_path, kind, text, stage=stage_id)
    if blocker:
        line = f"{stage_id}: blocked ({blocker}, owner {args.blocker_owner}). Nothing runs until resolve-blocker clears it."
    else:
        line = f"{stage_id}: {args.status}."
        if snapshot_files is not None:
            line += f" Snapshot of {snapshot_files} file(s) recorded for later re-reviews."
        elif snapshot_note:
            line += f" {snapshot_note}"
        counts = stage_record(state, stage_id).get("open_material_findings")
        if args.status == "passed" and isinstance(counts, dict) and counts.get("count"):
            line += f" {counts['count']} material finding(s) still open."
    lines = [line, next_stage_line(state, matter_path)]
    if applied:
        lines.insert(0, f"Applied {applied} attorney action(s) to the open items first.")
    print_result(
        state,
        args,
        lines,
        result_payload(
            state,
            matter_path,
            stage_id=stage_id,
            status=args.status,
            blocker_id=blocker,
            snapshot_file_count=snapshot_files,
            attorney_actions_applied=applied,
            open_material_findings=stage_record(state, stage_id).get("open_material_findings"),
        ),
        matter_path,
    )
    return 0


def command_resolve_blocker(args: argparse.Namespace) -> int:
    matter_path = args.matter_path
    with changing_state(args) as state:
        resolve_blocker(
            state,
            blocker_id_value=args.blocker_id,
            resolution_note=args.resolution_note,
            reset_stage_to=args.reset_stage_to,
            run_id=current_run_id(matter_path, args),
        )
    print_result(
        state,
        args,
        [f"{args.blocker_id}: resolved.", next_stage_line(state, matter_path)],
        result_payload(state, matter_path, blocker_id=args.blocker_id, status="resolved"),
        matter_path,
    )
    return 0


def command_reroute(args: argparse.Namespace) -> int:
    matter_path = args.matter_path
    run_id = current_run_id(matter_path, args)
    with changing_state(args) as state:
        # Whether the reroute sends back work that was done or under way: a reroute repeated over stages it already
        # reset changes nothing, and the timeline says each one once.
        before = {stage_id: str(stage_record(state, stage_id).get("status") or "pending") for stage_id in state["required_stage_ids"]}
        if args.from_stage:
            reset = reroute_from_stage(
                state,
                from_stage_id=args.from_stage,
                reason=args.reason,
                detected_in_stage_id=args.detected_in_stage,
                run_id=run_id,
                attorney_approved=args.attorney_approved,
            )
        else:
            _target, reset = reroute_from_category(
                state,
                category=args.category,
                reason=args.reason,
                detected_in_stage_id=args.detected_in_stage,
                run_id=run_id,
                attorney_approved=args.attorney_approved,
            )
    target = args.from_stage or args.category
    if any(before.get(stage_id, "pending") != "pending" for stage_id in reset):
        timeline(matter_path, "rerouted", reroute_line(reset, args.detected_in_stage), stage=reset[0])
    re_reviews = [stage_id for stage_id in reset if stage_id in REVIEW_STAGE_IDS and is_re_review(stage_record(state, stage_id))]
    lines = [f"Rerouted from {reset[0]}. Reset to pending: {', '.join(reset)}."]
    untouched = [stage_id for stage_id in state["required_stage_ids"] if stage_id not in reset and stage_record(state, stage_id)["status"] == "passed"]
    if untouched:
        lines.append(f"Still passed (they don't depend on it): {', '.join(untouched)}.")
    if re_reviews:
        lines.append(
            f"Re-reviews: {', '.join(re_reviews)}. Brief each as a re-review: "
            f"changed-since \"{matter_path}\" <stage> names its previous findings and what changed."
        )
    lines.append(next_stage_line(state, matter_path))
    print_result(state, args, lines, result_payload(state, matter_path, rerouted_from=reset[0], reset=reset, re_reviews=re_reviews), matter_path)
    return 0


def command_changed_since(args: argparse.Namespace) -> int:
    report = changed_since(read_state(args), matter_path=args.matter_path, state_path=args.state_path, stage_id=args.stage_id,
                           fresh=args.fresh)
    print(json.dumps(report, indent=2) if args.json else "\n".join(changed_since_lines(report)))
    return 0


def lease_line(lease: dict[str, Any] | None) -> str:
    if not lease:
        return "No one is working on this matter."
    state = "released" if lease.get("released_at") else ("active" if lease_is_fresh(lease) else "gone quiet")
    return (
        f"Lease {state}: run {lease.get('run_id')} ({lease.get('kind')}, held by {lease.get('holder')}), "
        f"started {lease.get('started_at')}, last sign of life {lease.get('heartbeat_at')}"
        + (f", stage {lease['stage']}" if lease.get("stage") else "")
        + (f", released {lease['released_at']} ({lease.get('outcome')})" if lease.get("released_at") else "")
        + "."
    )


_FINISHED_TEXT = {"done": "Claude finished.", "stopped": "Claude stopped.", "failed": "Claude ran into a problem and stopped."}
# A lease's kind as the app names the run on its timeline (the server's run kinds), for a run started in the chat.
RUN_KIND_OF_LEASE = {"build": "build", "update": "update", "review": "review_docs", "redo": "redo", "officer": "stress_test"}


def _lease_minutes(lease: dict) -> str:
    started = parse_time(lease.get("started_at"))
    if started is None:
        return ""
    minutes = max(1, round((datetime.now(timezone.utc) - started).total_seconds() / 60))
    return f" It took {minutes} minute{'s' if minutes != 1 else ''}."


def command_lease(args: argparse.Namespace) -> int:
    matter_path = args.matter_path
    if args.action == "acquire":
        run_id = (args.run_id or "").strip() or new_run_id()
        acquired, lease = acquire_lease(matter_path, run_id, args.kind, args.holder, args.description)
        if not acquired:
            what = (lease or {}).get("description") or (lease or {}).get("kind") or "a run"
            message = (
                f"Claude is already working on this matter ({what}, since {(lease or {}).get('started_at')}). "
                "Stop here and report that; don't change anything."
            )
            if args.json:
                print(json.dumps({"acquired": False, "lease": lease, "message": message}, indent=2))
            else:
                print(message, file=sys.stderr)
            return EXIT_LEASE_HELD
        if args.json:
            print(json.dumps({"acquired": True, "lease": lease}, indent=2))
        else:
            print(f"Lease acquired: run {lease['run_id']} ({lease['kind']}, {lease['holder']}). "
                  f"Release it with: lease release \"{matter_path}\" --run-id {lease['run_id']}")
        return 0
    if args.action == "heartbeat":
        run_id = (args.run_id or "").strip()
        if run_id:
            # The orchestrator's renewal between stages: its own lease only, and it learns here when another run
            # has the matter now, before it starts anything more.
            what, lease = renew_run_lease(matter_path, run_id, stage=args.stage)
            if what in NOT_YOURS:
                if args.json:
                    print(json.dumps({"renewed": False, "lease": lease, "message": NOT_YOURS[what]}, indent=2))
                else:
                    print(NOT_YOURS[what], file=sys.stderr)
                return EXIT_LEASE_HELD
            if what == RUN_NO_LEASE:
                lease = None
        else:
            lease = heartbeat_lease(matter_path, stage=args.stage)
        if args.json:
            print(json.dumps({"renewed": lease is not None, "lease": lease}, indent=2))
        else:
            print("Lease renewed." if lease else "No unreleased lease to renew" + (" for that run." if args.run_id else "."))
        return 0 if lease else 1
    if args.action == "release":
        lease = read_lease(matter_path)
        run_id = (args.run_id or "").strip()
        if not run_id and lease and not lease.get("released_at") and lease.get("holder") == args.holder:
            run_id = str(lease["run_id"])
        released = bool(run_id) and release_lease(matter_path, run_id, outcome=args.outcome)
        # The app writes "finished" for runs it started; a run started in the chat gets it here, with what the app's
        # own record carries (the kind of run and when it started), so the app knows later what the run took in.
        if released and lease and (lease.get("origin") or lease.get("holder")) != "app":
            minutes = _lease_minutes(lease)
            kind = str(lease.get("kind") or "other")
            add_event(matter_path, "run_finished", _FINISHED_TEXT.get(args.outcome, "Claude stopped.") + minutes,
                      actor="claude", run_id=run_id, outcome=args.outcome, run_kind=RUN_KIND_OF_LEASE.get(kind, kind),
                      lease_kind=kind, started_at=str(lease.get("started_at") or ""))
        if args.json:
            print(json.dumps({"released": released, "lease": read_lease(matter_path)}, indent=2))
        elif released:
            print(f"Lease released ({args.outcome}).")
        elif lease and run_id and lease.get("run_id") == run_id and lease.get("released_at"):
            print(f"Nothing to release: this run's lease was already released ({lease.get('outcome') or 'no outcome'}).")
        else:
            print("Nothing released: the current lease belongs to another run.")
        return 0 if released else 1
    lease = read_lease(matter_path)
    if args.json:
        print(json.dumps({**lease, "fresh": lease_is_fresh(lease)} if lease else None, indent=2))
    else:
        print(lease_line(lease))
    return 0


def command_apply_attorney_actions(args: argparse.Namespace) -> int:
    applied = merge_attorney_actions(args.matter_path)
    if args.json:
        print(json.dumps({"applied": applied}, indent=2))
    else:
        print(f"Applied {applied} attorney action(s) to the open items." if applied else "No attorney actions to apply.")
    return 0


def command_open_items(args: argparse.Namespace) -> int:
    """One locked read-modify-write of open-items.json: the attorney's actions from the app are applied first, so a
    stage changing one item never drops what the attorney marked, and nothing else in the list is touched."""
    matter_path = args.matter_path
    path = matter_path / OPEN_ITEMS_FILE
    if args.items_action == "upsert":
        raw = args.item_json if args.item_json is not None else args.item_file.read_text(encoding="utf-8")
        try:
            change = json.loads(raw)
        except ValueError as exc:
            raise ValueError(f"The item isn't valid JSON ({exc.msg} at character {exc.pos}).") from None
    protected = is_protected_matter(matter_path)
    with matter_lock(matter_path):
        current = read_open_items(matter_path)
        if path.exists() and not current.ok:
            raise ValueError(
                "The open items list can't be read, so nothing was changed. Rewrite it to the matter contract's rules "
                "from the review findings and the memo, then run this again."
            )
        ledger = current.data if current.ok else None
        if ledger is not None:
            ledger, _applied = apply_attorney_actions(ledger, attorney_actions(matter_path))
        now = now_iso(precise=True)
        try:
            if args.items_action == "upsert":
                ledger, item, added = upsert_open_item(ledger, change, protected=protected, now=now)
                line = f"{'Added' if added else 'Updated'} open item {item['id']}."
            elif args.items_action == "note":
                ledger, item = note_open_item(ledger, args.item_id, args.text, now=now)
                added, line = False, f"Added a note to open item {item['id']}."
            else:
                ledger = set_open_items_packet_status(ledger, args.packet_status, protected=protected, now=now)
                item, added, line = None, False, "Set the open items list's status."
        except OpenItemRefused as exc:
            raise ValueError(str(exc)) from None
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(path, ledger)
    if args.json:
        print(json.dumps({"item": item, "added": added, "packet_status": ledger.get("packet_status")}, indent=2))
    else:
        print(f"{line} The list's packet_status is {ledger.get('packet_status')}.")
    return 0


def command_set_protected(args: argparse.Namespace) -> int:
    matter_path = args.matter_path
    meta = read_meta(matter_path)
    if args.off:
        if args.reason != "attorney":
            raise ValueError(
                "Only the attorney lifts a matter's protection (set-protected --off --reason attorney). The document "
                "review can mark a matter protected, never unmark it."
            )
        meta = update_meta(matter_path, protected=False)
        line = "This matter is no longer marked protected."
    elif meta.get("protected"):
        line = f"This matter is already marked protected ({meta.get('protected_reason') or 'attorney'}); nothing changed."
    else:
        actor = "claude" if args.reason == "docs_review" else "attorney"
        meta = update_meta(matter_path, protected=True, protected_reason=args.reason, actor=actor)
        line = (
            "Marked protected under 8 U.S.C. 1367. Every later step follows the contract's \"VAWA and other protected "
            "cases\" section: safe mailing address, neutral client request, summaries that never name the case."
        )
    print(json.dumps(meta, indent=2) if args.json else line)
    return 0


COMMAND_HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "init": command_init,
    "ensure": command_ensure,
    "status": command_status,
    "security-dashboard": command_security_dashboard,
    "closeout": command_closeout,
    "next-stage": command_next_stages,
    "next-stages": command_next_stages,
    "start-stage": command_start_stage,
    "complete-stage": command_complete_stage,
    "resolve-blocker": command_resolve_blocker,
    "reroute": command_reroute,
    "changed-since": command_changed_since,
    "apply-attorney-actions": command_apply_attorney_actions,
    "set-protected": command_set_protected,
    "open-items": command_open_items,
}

# Every command but these checks the senior associate's access to the matter before it runs.
UNCHECKED_COMMANDS = {"apply-attorney-actions", "set-protected"}


def protection_note(args: argparse.Namespace) -> str:
    meta = read_meta(args.matter_path)
    return f"protected={meta.get('protected')}; reason={meta.get('protected_reason') or args.reason}"


# What a command that ran writes to the matter's access log: (event, artifacts, notes), from its arguments and the
# workflow record it used. A command not here writes nothing of its own (closeout's report logs itself).
ACCESS_LOG: dict[str, Callable[[argparse.Namespace, list[str]], tuple[str, list[str], str] | None]] = {
    "init": lambda args, record: ("workflow_state_initialized", record, "Matter workflow state initialized."),
    "ensure": lambda args, record: {
        "created": ("workflow_state_initialized", record, "Matter workflow state initialized through ensure."),
        "moved": ("workflow_matter_moved", record, "The matter folder moved; the workflow record now points at its current place."),
    }.get(args.ensured),
    "status": lambda args, record: ("workflow_state_viewed", record, "Workflow state viewed."),
    "security-dashboard": lambda args, record: ("workflow_security_dashboard_viewed", [], "Security dashboard viewed."),
    "next-stage": lambda args, record: ("workflow_next_stage_viewed", record, "Next actionable workflow stage viewed."),
    "next-stages": lambda args, record: ("workflow_next_stage_viewed", record, "Stages to run now viewed."),
    "start-stage": lambda args, record: ("workflow_stage_started", record, f"Workflow stage {args.stage_id} started."),
    "complete-stage": lambda args, record: ("workflow_stage_completed", record + args.artifacts + args.evidence_files,
                                            f"Workflow stage {args.stage_id} completed with status {args.status}."),
    "resolve-blocker": lambda args, record: ("workflow_blocker_resolved", record, f"Workflow blocker {args.blocker_id} resolved."),
    "reroute": lambda args, record: ("workflow_rerouted", record, f"Workflow rerouted from {args.from_stage or args.category}."),
    "changed-since": lambda args, record: ("workflow_changes_viewed", record, f"Changes since {args.stage_id} last passed viewed."),
    "set-protected": lambda args, record: ("matter_protection_changed", [], protection_note(args)),
}


def main() -> int:
    args = build_parser().parse_args()
    try:
        # A new matter's folder starts empty (the app creates it, then runs ensure); every other
        # command needs a folder that already holds a workflow record or the client's documents.
        args.matter_path = require_matter_folder(args.matter_path, allow_empty=args.command in {"init", "ensure", "lease"})
        if args.command == "lease":
            return command_lease(args)
        # Every runtime command is a sign the run is alive (CONTRACTS §3); with --run-id, a change is refused once
        # the run no longer holds the matter.
        refused = guard_run(args, args.matter_path)
        if refused is not None:
            return refused
        args.state_path = workflow_state_path(args.matter_path, getattr(args, "workflow_slug", None)).resolve()
        if args.command not in UNCHECKED_COMMANDS:
            ensure_workflow_access(args.matter_path)
        exit_code = COMMAND_HANDLERS[args.command](args)
        entry = ACCESS_LOG[args.command](args, [str(args.state_path)]) if args.command in ACCESS_LOG else None
        if entry:
            event_type, artifacts, notes = entry
            log_access_event(args.matter_path, event_type=event_type, role="senior_associate", actor="system",
                             data_planes=["audit_metadata"], artifacts=artifacts, notes=notes)
        return exit_code
    except LockTimeout:
        print("The matter's record is busy (another step is writing it). Run the command again in a moment.", file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.matter_access import (
    AccessDeniedError,
    NotAMatterFolder,
    ensure_policy,
    load_policy,
    log_access_event,
    require_matter_folder,
)
from scripts.matter_protection import is_protected_matter
from scripts.matter_state import parse_time, read_lease, sign_of_life


ACTION_RULES: dict[str, dict[str, dict[str, str]]] = {
    "official_source": {
        "standard": {"no_client_data": "allow", "client_data": "confirm"},
        "high_sensitivity": {"no_client_data": "allow", "client_data": "confirm"},
        "restricted": {"no_client_data": "allow", "client_data": "block"},
    },
    "mcp_research": {
        "standard": {"no_client_data": "allow", "client_data": "confirm"},
        "high_sensitivity": {"no_client_data": "confirm", "client_data": "confirm"},
        "restricted": {"no_client_data": "block", "client_data": "block"},
    },
    "browser_remote": {
        "standard": {"no_client_data": "allow", "client_data": "confirm"},
        "high_sensitivity": {"no_client_data": "confirm", "client_data": "confirm"},
        "restricted": {"no_client_data": "block", "client_data": "block"},
    },
}


# Who runs unattended: the app's background build and the orchestrator it starts. Nobody is there to confirm
# that a client's facts may leave the machine, so such a run never sends them, confirmed or not.
UNATTENDED_HOLDERS = frozenset({"app", "orchestrator"})
# The matter chat talks with the attorney, who can say yes in the conversation.
INTERACTIVE_ACTORS = frozenset({"matter_chat", "attorney"})
# A run's lease goes stale after 30 quiet minutes, but a long step can go that long without a runtime command. For
# this check an unreleased run lease counts for six hours, so a quiet step can't send client facts out.
UNATTENDED_WINDOW_SECONDS = 6 * 60 * 60


class NetworkBoundaryError(PermissionError):
    pass


def lease_is_unattended(lease: dict[str, Any] | None, now: datetime | None = None) -> bool:
    """True while a lease says a background run holds the matter: held by the app or an orchestrator (however it
    started: from the app, the chat box, or by hand), not released, and with a sign of life in the last six hours.
    The app's research gate reads the same rule from the matters list."""
    if not lease or lease.get("released_at") or str(lease.get("holder") or "") not in UNATTENDED_HOLDERS:
        return False
    beat = parse_time(lease.get("heartbeat_at")) or parse_time(lease.get("started_at"))
    current = now or datetime.now(tz=timezone.utc)
    return beat is not None and (current - beat).total_seconds() < UNATTENDED_WINDOW_SECONDS


def unattended_run(matter_root: Path, actor: str) -> bool:
    """True while the app's background run (or its orchestrator) holds the matter, unless the caller is the
    attorney's own conversation."""
    # A caller-supplied role is not evidence that the attorney is present.
    return lease_is_unattended(read_lease(matter_root))


def evaluate_network_action(
    *,
    privacy_mode: str,
    action: str,
    sends_client_data: bool,
    confirmed: bool = False,
) -> dict[str, Any]:
    if action not in ACTION_RULES:
        allowed = ", ".join(sorted(ACTION_RULES))
        raise ValueError(f"Unknown network action {action!r}. Expected one of: {allowed}.")
    mode_rules = ACTION_RULES[action].get(privacy_mode)
    if mode_rules is None:
        raise ValueError(f"Unsupported privacy mode {privacy_mode!r}.")
    data_key = "client_data" if sends_client_data else "no_client_data"
    rule = mode_rules[data_key]
    allowed = rule == "allow" or (rule == "confirm" and confirmed)
    return {
        "privacy_mode": privacy_mode,
        "action": action,
        "sends_client_data": sends_client_data,
        "rule": rule,
        "confirmed": confirmed,
        "allowed": allowed,
    }


def check_network_action(
    matter_root: Path,
    *,
    action: str,
    role: str,
    actor: str = "system",
    sends_client_data: bool = False,
    confirmed: bool = False,
    notes: str = "",
) -> dict[str, Any]:
    """Decide, and log, whether a stage may make a network call. Every check is logged, allowed or not, so the
    access log shows what was asked and what the gate said."""
    matter_root = require_matter_folder(matter_root)
    ensure_policy(matter_root)
    sign_of_life(matter_root)  # a check is a sign the run is alive
    policy = load_policy(matter_root)
    unattended = unattended_run(matter_root, actor)
    try:
        decision = evaluate_network_action(
            privacy_mode=policy.get("privacy_mode", "standard"),
            action=action,
            sends_client_data=sends_client_data,
            confirmed=confirmed,
        )
    except ValueError as exc:
        decision = {"action": action, "sends_client_data": sends_client_data, "confirmed": confirmed,
                    "allowed": False, "rule": "invalid", "error": str(exc)}
    decision["unattended"] = unattended
    decision["protected_matter"] = is_protected_matter(matter_root)
    reason = ""
    if decision.get("rule") == "invalid":
        reason = str(decision.get("error"))
    elif sends_client_data and unattended and decision["allowed"]:
        # Nobody can have confirmed this: the attorney isn't watching an app run.
        decision["allowed"] = False
        decision["rule"] = "unattended"
        reason = (
            "This is an unattended run, so nothing that carries the client's facts leaves the machine, confirmed or "
            "not. Phrase the research as a legal question without the client's details, or add an attorney_decision "
            "open item saying what you would send and why."
        )
    elif not decision["allowed"]:
        if decision["rule"] == "confirm":
            reason = (
                f"{action} with the client's facts needs the attorney's go-ahead in this conversation. Ask, and run "
                "the gate again with --confirmed only after they say yes."
            )
        else:
            reason = f"{action} is blocked in this matter's {decision['privacy_mode']} privacy mode."
    log_access_event(
        matter_root,
        event_type="network_boundary_check",
        role=role,
        actor=actor,
        data_planes=["audit_metadata"],
        artifacts=[],
        notes=json.dumps({**decision, "notes": notes}, sort_keys=True),
    )
    if not decision["allowed"]:
        raise NetworkBoundaryError(reason)
    return decision


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check and log matter network-boundary decisions.")
    parser.add_argument("matter_root", type=Path)
    parser.add_argument("--action", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--actor", default="system")
    parser.add_argument("--sends-client-data", action="store_true")
    parser.add_argument("--confirmed", action="store_true")
    parser.add_argument("--notes", default="")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        decision = check_network_action(
            args.matter_root,
            action=args.action,
            role=args.role,
            actor=args.actor,
            sends_client_data=args.sends_client_data,
            confirmed=args.confirmed,
            notes=args.notes,
        )
    except (NetworkBoundaryError, NotAMatterFolder, FileNotFoundError, AccessDeniedError) as exc:
        error = str(exc)
        if isinstance(exc, AccessDeniedError):
            error += " Pass your stage id as --role (the matter chat passes attorney)."
        print(json.dumps({"allowed": False, "error": error}, indent=2) if args.json else error, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(decision, indent=2))
    else:
        print("allowed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

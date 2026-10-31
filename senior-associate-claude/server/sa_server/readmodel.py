"""The matter card and the matters list: everything the app draws, read from the matter folder.

The server is the one source of truth for where a matter stands (CONTRACTS §4): the card carries its status, its
counts and its words, so the app never re-derives them. The list op reads only what a row needs; the full card,
with documents hashed and notes normalized, is built only for the matter the attorney has open.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.matter_state import (EVENTS_FILE, LEASE_FILE, apply_attorney_actions, attorney_actions, is_app_written,
                                  lease_is_fresh, question_key, read_answers, read_jsonl, read_lease, read_meta,
                                  read_open_items)
from scripts.network_gate import lease_is_unattended

from .catalog import (DEFAULT_STAGE_MINUTES, DEFAULT_WORKFLOW, FINDINGS_FILE_STAGES, PHASE_LABELS, STAGE_LABELS,
                      STAGE_MINUTES, SUPERSEDED_BY_FINAL_REVIEW, WORKFLOW_TEMPLATES, catalog, posture_entry, type_entry)
from .common import as_text, as_word
from .common import iso as _iso, mtime_iso as _mtime_iso, parse_time as _parse_time, plugin_version
from .common import read_json as _read_json, read_text as _read_text
from .context import Context
from .doctor import doctor
from .folders import (CHAT_CHANGES_FILE, DELIVERABLES_DIR, FILED_FILE, DamagedRecord, documents_for, is_matter_name,
                      load_track, outputs_for, read_instructions, seen_cutoff, walk_files, walk_output)
from .logs import log, matter_tag
from .plaintext import (QUESTION_LIMIT, _id_pattern, cut_text, plain_detail, plain_question, plain_recommendation,
                        plain_title, split_stage_prefix, strip_machinery)
from .profile import load_profile
from .samples import guide_for as sample_guide, is_sample

OPEN_ITEM_ORDER = {"attorney_decision": 0, "client_document": 1, "client_question": 2, "attorney_action": 3, "risk": 4}
WHO_BY_TYPE = {"client_document": "client", "client_question": "client", "attorney_decision": "attorney", "attorney_action": "attorney", "risk": "attorney"}
# Waiting on an agency or a third party is the attorney's to chase, not the client's.
WHO_BY_OWNER = {"client": "client", "attorney": "attorney", "system": "system", "agency": "attorney", "third_party": "attorney"}
WHO_VALUES = {"attorney", "client", "system"}

# Files the app writes for itself under output/: never a sign that Claude is working.
SERVER_WRITTEN_NAMES = frozenset({"hash-cache.json"})

DAMAGED_NEED_ID = "open-items-damaged"


def open_items_path(matter: Path) -> Path:
    return matter / DELIVERABLES_DIR / "open-items.json"


# ---------------------------------------------------------------------------
# Open items, with the attorney's Mark done / Reopen / Accept this risk applied on top
# ---------------------------------------------------------------------------

def ledger_for(matter: Path) -> tuple[str, dict[str, Any] | None]:
    """The open items as the screen shows them: ("missing", None) before the first run writes the list,
    ("damaged", None) when the file exists but can't be read, else ("ok", the list with the attorney's actions)."""
    result = read_open_items(matter)
    if not result.ok:
        return result.state, None
    merged, _applied = apply_attorney_actions(result.data, attorney_actions(matter))
    return "ok", open_items_view(merged, fallback_time=_mtime_iso(open_items_path(matter)))


def open_items_view(data: dict[str, Any], fallback_time: str = "") -> dict[str, Any]:
    raw_items = [r for r in data.get("items") or [] if isinstance(r, dict)]
    ids_re = _id_pattern({as_text(r.get("id")) for r in raw_items if r.get("id")})
    items: list[dict[str, Any]] = []
    for i, raw in enumerate(raw_items):
        title = as_text(raw.get("title")).strip()
        if not title:
            continue
        typ = as_word(raw.get("type")) or "risk"
        who = as_word(raw.get("who"))
        detail_raw = as_text(raw.get("detail"))
        raw_id = as_text(raw.get("id")).strip()
        entry: dict[str, Any] = {
            "id": raw_id or f"item-{i + 1}",
            "type": typ,
            "title": plain_title(title, ids_re),
            "detail": plain_detail(detail_raw, ids_re),
            # Anything but a plain false holds up filing, as the runtime reads it: "no" or a missing value is the safe way.
            "blocks_filing": raw.get("blocks_filing") is not False,
            "status": "resolved" if as_word(raw.get("status")) == "resolved" else "open",
            "resolution": plain_detail(as_text(raw.get("resolution")), ids_re),
            "who": who if who in WHO_VALUES else WHO_BY_TYPE.get(typ, "attorney"),
            "stage": STAGE_LABELS.get(as_text(raw.get("stage")), ""),
        }
        if typ == "attorney_decision":
            entry["question"] = plain_question(as_text(raw.get("question")), title, ids_re)
        recommendation = plain_recommendation(as_text(raw.get("recommendation")), detail_raw if typ == "attorney_decision" else "", ids_re)
        if recommendation:
            entry["recommendation"] = recommendation
        # The key the attorney's saved answer is kept under: the item's id, or a hash of its words without one.
        entry["key"] = question_key(raw_id or None, entry.get("question") or entry["title"])
        items.append(entry)
    open_items = [it for it in items if it["status"] == "open"]
    open_items.sort(key=lambda it: (not it["blocks_filing"], OPEN_ITEM_ORDER.get(it["type"], 9)))
    counts: dict[str, int] = {}
    blocking_by_who = {"attorney": 0, "client": 0, "system": 0}
    for it in open_items:
        counts[it["type"]] = counts.get(it["type"], 0) + 1
        if it["blocks_filing"]:
            blocking_by_who[it["who"]] = blocking_by_who.get(it["who"], 0) + 1
    resolved = [it for it in items if it["status"] == "resolved"]
    return {
        "packet_status": "ready_to_file" if data.get("packet_status") == "ready_to_file" else "draft",
        "updated_at": as_text(data.get("updated_at")) or fallback_time,
        "open": open_items[:100],
        "resolved": [{k: it[k] for k in ("id", "type", "title", "resolution", "blocks_filing")} for it in resolved[:100]],
        "resolved_count": len(resolved),
        "counts": counts,
        "blocking": sum(1 for it in open_items if it["blocks_filing"]),
        "blocking_by_who": blocking_by_who,
    }


def chat_changes_since_build(matter: Path, track: dict[str, Any] | None) -> list[dict[str, str]]:
    """What the attorney changed in chat that no finished run has taken in yet, oldest first; empty before any step
    passed. A change stays until a run that started after it finishes: a step that merely passes later, in a run
    that began before the change, never re-checked it."""
    finished = seen_cutoff(matter, track)
    if finished is None:
        return []
    data = _read_json(matter / CHAT_CHANGES_FILE)
    entries = data.get("changes") if isinstance(data, dict) else None
    out = []
    for e in entries if isinstance(entries, list) else []:
        at = _parse_time(e.get("at")) if isinstance(e, dict) and isinstance(e.get("what"), str) else None
        if at and at > finished:
            out.append({"at": str(e["at"]), "what": " ".join(e["what"].split())[:200]})
    return out[-20:]


# ---------------------------------------------------------------------------
# Reviewer findings and the notes the attorney reads (CONTRACTS §5)
# ---------------------------------------------------------------------------

RESOLVED_STATUSES = {"resolved", "closed", "fixed", "cured", "accepted"}
SEVERITY_WORDS = {
    "blocker": "important", "critical": "important", "high": "important",
    "major": "worth fixing",
    "minor": "minor", "low": "minor",
    "manual_review": "check by hand",
}
OUTCOME_WORDS = {"deny_likely": "denial likely", "noid_likely": "NOID likely", "rfe_likely": "RFE likely", "attorney_hold": "your call"}
OWNER_WORDS = {"attorney": "you", "client": "the client"}


def _normalize_finding(item: dict[str, Any], source: Path, matter: Path, index: int) -> dict[str, Any]:
    status = as_word(item.get("status"))
    summary = next((as_text(item.get(k)) for k in ("summary", "title", "finding", "issue", "description", "reason") if as_text(item.get(k)).strip()), "")
    detail = next((as_text(item.get(k)) for k in ("detail", "details", "description", "rationale", "explanation", "evidence")
                   if as_text(item.get(k)).strip() and as_text(item.get(k)) != summary), "")
    stage_id = as_text(item.get("stage") or item.get("stage_id")) or FINDINGS_FILE_STAGES.get(source.name, "")
    outcome = as_word(item.get("outcome") or item.get("likely_outcome"))
    raw_id = as_text(item.get("id") or item.get("finding_id")).strip()
    return {
        "id": raw_id,
        # An adjudicator matrix (older matters) has only an outcome; it stands in for the severity there.
        "severity": as_word(item.get("severity")) or outcome or as_word(item.get("category")) or "note",
        "outcome": outcome,
        "summary": summary[:400],
        "detail": detail[:800],
        "owner": as_word(item.get("owner")),
        "resolved": item.get("resolved") is True or status in RESOLVED_STATUSES,
        "stage_id": stage_id,
        "stage": STAGE_LABELS.get(stage_id, stage_id),
        "source": source.relative_to(matter).as_posix(),
        "index": index,
    }


def findings_for(matter: Path, output_files: list[Path] | None = None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    files = output_files if output_files is not None else walk_output(matter)
    candidates = [p for p in files if p.name.endswith("findings.json") or p.name == "reroute matrix.json"]
    if any(p.name == "final review findings.json" for p in candidates):
        # The final review re-checked what the old packet review and adjudicator found; show its findings, not theirs.
        candidates = [p for p in candidates if p.name not in SUPERSEDED_BY_FINAL_REVIEW]
    for path in sorted(candidates, key=_mtime_iso, reverse=True)[:40]:
        data = _read_json(path)
        if not isinstance(data, dict):
            continue
        for key in ("findings", "issues", "reroutes"):
            items = data.get(key)
            if isinstance(items, list):
                findings.extend(_normalize_finding(item, path, matter, i) for i, item in enumerate(items) if isinstance(item, dict))
    return findings[:200]


def finding_key(f: dict[str, Any]) -> str:
    """A finding's stable id: f-<stage>-<its id> when the reviewer gave one, else a hash of what it says."""
    if f.get("id"):
        return f"f-{f.get('stage_id') or 'review'}-{f['id']}"
    return question_key(None, f"{f.get('stage_id')}|{f.get('summary')}")


def is_open_note(f: dict[str, Any]) -> bool:
    """Resolved findings and findings the officer called approvable are not open notes."""
    return not f["resolved"] and not f.get("outcome", "").startswith("approvable")


def review_note(f: dict[str, Any]) -> dict[str, Any]:
    """A finding in the words the attorney reads: no raw severity, outcome or owner code ever reaches the screen."""
    title = plain_title(f["summary"]) or "A reviewer flagged something."
    detail = plain_detail(f.get("detail") or "")
    return {
        "id": finding_key(f),
        "title": title,
        "detail": "" if detail == title else detail,
        "severity_word": SEVERITY_WORDS.get(f["severity"], "note"),
        "outcome_word": OUTCOME_WORDS.get(f.get("outcome") or "", ""),
        "owner_word": OWNER_WORDS.get(f.get("owner") or "", "Claude"),
        "stage_label": f.get("stage") if f.get("stage") in STAGE_LABELS.values() else STAGE_LABELS.get(f.get("stage_id") or "", ""),
    }


def review_notes(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [review_note(f) for f in findings if is_open_note(f)]


# ---------------------------------------------------------------------------
# What's waiting on someone
# ---------------------------------------------------------------------------

# A setup problem on the attorney's Mac, recognized by what it names: the fix to show and the request that has Claude
# do it (the setup skill installs the tool, and Homebrew first if it's missing).
SYSTEM_FIXES = [
    (re.compile(r"ghostscript|\bgs\b", re.I), "Claude can install Ghostscript for you. Then build again.", "Install Ghostscript for Immigration Packet Builder."),
    (re.compile(r"libreoffice|soffice", re.I), "Claude can install LibreOffice for you.", "Install LibreOffice for Immigration Packet Builder."),
    (re.compile(r"poppler|pdftotext", re.I), "Claude can install Poppler for you.", "Install Poppler for Immigration Packet Builder."),
    (re.compile(r"\buv\b"), "Claude can install uv for you.", "Install uv for Immigration Packet Builder."),
]
# A fix written for Terminal, as older runs wrote them, gives way to the request.
TERMINAL_FIX = re.compile(r"\bTerminal\b|\bbrew\b|\bcommand below\b", re.I)


def _fix_for(text: str, given_fix: Any = None, given_command: Any = None) -> dict[str, str]:
    out: dict[str, str] = {}
    for pattern, fix, ask in SYSTEM_FIXES:
        if pattern.search(text):
            out = {"fix": fix, "ask": ask}
            break
    if isinstance(given_command, str) and given_command.strip() and "ask" not in out:
        out["ask"] = f"Do this setup step for Immigration Packet Builder on this Mac: {given_command.strip()}"
    if isinstance(given_fix, str) and given_fix.strip() and not ("ask" in out and TERMINAL_FIX.search(given_fix)):
        out["fix"] = strip_machinery(given_fix)
    if "fix" not in out:
        out["fix"] = "Claude couldn't fix this by itself. Ask Claude about it on the matter page, then check again."
    return out


def damaged_need(matter_name: str) -> dict[str, Any]:
    return {
        "kind": "setup", "id": DAMAGED_NEED_ID, "key": DAMAGED_NEED_ID, "who": "system", "stage": "",
        "text": "Claude's list of open items can't be read.", "detail": "", "blocks_filing": True,
        "fix": "Claude can rewrite it from the review notes and the memo.",
        "ask": f"Rewrite the open items list for {matter_name} from the review findings and the memo.",
    }


def needs_you(track: dict[str, Any] | None, findings: list[dict[str, Any]], ledger: dict[str, Any] | None = None,
              ledger_state: str = "", matter_name: str = "") -> list[dict[str, Any]]:
    """What's waiting on someone before the work can go on: the attorney's questions, setup problems on this Mac,
    and steps stopped on the client. The open items list is the source once the workflow has written it; before
    that (older matters), the reviewers' findings that need the attorney stand in. Every entry has a ``key``."""
    items: list[dict[str, Any]] = []
    if ledger_state == "damaged":
        items.append(damaged_need(matter_name))
    for b in (track or {}).get("blockers", []):
        who = WHO_BY_OWNER.get(as_word(b.get("owner")), "attorney")
        text, prefix_stage = split_stage_prefix(strip_machinery(as_text(b.get("summary"))))
        text = text or "Claude stopped here and needs help to go on."
        entry: dict[str, Any] = {
            "kind": "blocker",
            "id": as_text(b.get("id")),
            "key": question_key(as_text(b.get("id")) or None, text),
            "who": who,
            "stage": STAGE_LABELS.get(as_text(b.get("stage")), "") or prefix_stage,
            "text": text,
        }
        if who == "attorney":
            entry["question"] = text
        elif who == "system":
            entry.update(_fix_for(text))
        items.append(entry)
    if ledger is not None:
        for it in ledger["open"]:
            if it["who"] == "system":
                text = it["title"]
                items.append({"kind": "setup", "id": it["id"], "key": it["key"], "who": "system", "stage": it["stage"], "text": text,
                              "detail": it["detail"], "blocks_filing": it["blocks_filing"],
                              **_fix_for(f"{it['title']} {it['detail']}", it["detail"] or None)})
            elif it["type"] == "attorney_decision" and it["who"] == "attorney":
                entry = {"kind": "decision", "id": it["id"], "key": it["key"], "who": "attorney", "stage": it["stage"],
                         "text": it.get("question") or it["title"], "question": it.get("question") or it["title"],
                         "detail": it["detail"], "blocks_filing": it["blocks_filing"]}
                if it.get("recommendation"):
                    entry["recommendation"] = it["recommendation"]
                items.append(entry)
    elif ledger_state != "damaged":
        for f in findings:
            if not is_open_note(f):
                continue
            sev, outcome, owner = f["severity"], f.get("outcome") or "", f.get("owner") or ""
            if (
                sev in {"blocker", "attorney_hold", "manual_review", "noid_likely"}
                or outcome in {"attorney_hold", "noid_likely", "deny_likely"}
                or owner == "attorney"
            ):
                who = "client" if owner == "client" else "attorney"
                text = cut_text(strip_machinery(f["summary"]), QUESTION_LIMIT) or "A reviewer flagged something for you."
                entry = {"kind": outcome if outcome in {"attorney_hold", "noid_likely", "deny_likely"} else sev,
                         "id": finding_key(f), "key": finding_key(f), "who": who, "stage": f.get("stage") or "", "text": text}
                if who == "attorney":
                    entry["question"] = text
                items.append(entry)
    order = {"system": 0, "attorney": 1, "client": 2}
    items.sort(key=lambda it: order.get(it["who"], 1))
    return items[:20]


# ---------------------------------------------------------------------------
# Where the matter stands (CONTRACTS §4)
# ---------------------------------------------------------------------------

def _reviewed_only(stages: list[dict[str, Any]]) -> bool:
    """The document review is done and nothing after it has started."""
    review = [s for s in stages if s["id"] == "docs_review"]
    return bool(review) and review[0]["status"] == "passed" and all(
        s["status"] == "pending" for s in stages if s["id"] != "docs_review"
    )


def _passed(stages: list[dict[str, Any]], stage_id: str) -> bool:
    return any(s["id"] == stage_id and s["status"] == "passed" for s in stages)


def final_review_passed(stages: list[dict[str, Any]]) -> bool:
    """The final review passed: run, not skipped. A matter the runtime hasn't migrated still has the two reviews it
    replaced; there both must have passed."""
    ids = {s["id"] for s in stages}
    if "final_review" in ids:
        return _passed(stages, "final_review")
    return {"packet_review", "uscis_adjudicator"} <= ids and _passed(stages, "packet_review") and _passed(stages, "uscis_adjudicator")


QUIET_MINUTES = 20  # a step "in progress" with nothing changing for this long has stopped (Claude was closed, say)


def phase_for(track: dict[str, Any] | None, doc_count: int, needs: list[dict[str, Any]], ledger: dict[str, Any] | None = None,
              filed: bool = False, last_change_at: str = "", now: datetime | None = None, *, lease: dict[str, Any] | None = None,
              lease_file: bool = False, ledger_state: str | None = None) -> str:
    """Where the matter stands, in one word; the first rule that matches wins.

    1. filed. 2. building: a fresh run lease, or, for a matter an older plugin ran (no lease file at all), a step in
    progress with something under output/ changed in the last 20 minutes. 3. a damaged open items list: draft. 4. the
    document review done and nothing after it started: reviewed. 5. a setup problem or a question for the attorney:
    needs_you (once every step is done, only a question needed before filing); a step stopped on the client:
    waiting_client. 6. every step done: complete only when the final review
    passed (not skipped), the memo step passed, the list is readable and ready to file, and nothing needed before
    filing is open after the attorney's own actions; else waiting_client when everything needed is the client's, else
    draft. 7. nothing started: new or ready. 8. otherwise paused.
    """
    if ledger_state is None:
        ledger_state = "ok" if ledger is not None else "missing"
    if filed:
        return "filed"
    stages = (track or {}).get("stages", [])
    now = now or datetime.now(tz=timezone.utc)
    if lease_is_fresh(lease, now):
        return "building"
    if not lease_file and any(s["status"] == "in_progress" for s in stages):
        changed = _parse_time(last_change_at)
        if changed is not None and (now - changed).total_seconds() <= QUIET_MINUTES * 60:
            return "building"
    if ledger_state == "damaged":
        return "draft"
    if _reviewed_only(stages):
        return "reviewed"
    done = [s for s in stages if s["status"] in {"passed", "skipped"}]
    all_done = bool(stages) and len(done) == len(stages)
    # Once every step is done, a question that isn't needed before filing doesn't hold the packet: it waits beside a
    # packet that is ready to file (or a draft). Before then any open question stops the work, so it needs the attorney.
    holding = [n for n in needs if not (all_done and n.get("kind") == "decision" and not n.get("blocks_filing"))]
    if any(n.get("who") != "client" for n in holding):
        return "needs_you"
    if holding:
        return "waiting_client"
    if all_done:
        blocking = [it for it in (ledger or {}).get("open", []) if it["blocks_filing"]]
        if (
            ledger_state == "ok" and ledger is not None and ledger["packet_status"] == "ready_to_file" and not blocking
            and final_review_passed(stages) and _passed(stages, "attorney_handoff")
        ):
            return "complete"
        if blocking and all(it["who"] == "client" and it["type"] != "risk" for it in blocking):
            return "waiting_client"
        return "draft"
    if not any(s["status"] != "pending" for s in stages):
        return "new" if doc_count == 0 else "ready"
    return "paused"


def minutes_left(stages: list[dict[str, Any]], now: datetime | None = None) -> int | None:
    """About how many minutes the remaining steps take; a running step counts only what's left of it."""
    if not stages:
        return None
    now = now or datetime.now(tz=timezone.utc)
    total = 0.0
    for s in stages:
        if s["status"] in {"passed", "skipped"}:
            continue
        minutes = float(STAGE_MINUTES.get(s["id"], DEFAULT_STAGE_MINUTES))
        started = _parse_time(s.get("started_at")) if s["status"] == "in_progress" else None
        if started:
            minutes = max(1.0, minutes - (now - started).total_seconds() / 60)
        total += minutes
    return int(math.ceil(total))


def _claude_wrote(path: Path) -> bool:
    return not is_app_written(path) and path.name not in SERVER_WRITTEN_NAMES


def last_change(matter: Path, track: dict[str, Any] | None, output_files: list[Path]) -> str:
    """When Claude last changed anything about the work: the workflow record, a file it writes under output/, or a
    file in a step's workspace. What the app or the attorney writes (answers, actions, the lease) doesn't count, and
    neither do the logs under output/privacy/ (the access log gets a line from every runtime command, even one that
    only reads the matter, such as status or changed-since)."""
    times: list[float] = []
    stamp = _parse_time((track or {}).get("updated_at"))
    if stamp:
        times.append(stamp.timestamp())
    workspaces = matter / "output" / "security" / "stage-workspaces"
    candidates = list(output_files)  # walk_output leaves out output/privacy/ and output/security/
    if workspaces.is_dir():
        candidates += walk_files(workspaces, prune={"tmp"})
    for p in candidates:
        if not _claude_wrote(p):
            continue
        try:
            times.append(p.stat().st_mtime)
        except OSError:
            continue
    return _iso(max(times)) if times else ""


def lease_view(lease: dict[str, Any] | None, now: datetime) -> dict[str, Any] | None:
    """The run lease as the app reads it. ``origin`` is who took it first (the app, the chat, an orchestrator), so the
    app can tell its own start waiting in the chat box from a run it didn't start."""
    if not lease:
        return None
    return {k: as_text(lease.get(k)) for k in ("run_id", "kind", "holder", "origin", "started_at", "heartbeat_at", "stage")} | {
        "fresh": lease_is_fresh(lease, now)}


def lease_row(lease: dict[str, Any] | None, now: datetime) -> dict[str, Any] | None:
    """What a list row carries of the lease: enough for the app to say Waiting for you for its own start that waits
    in the chat box, and never Stopped while another run works on the matter."""
    view = lease_view(lease, now)
    return {k: view[k] for k in ("run_id", "holder", "origin", "started_at", "fresh")} if view else None


def status_for(phase: str, stages: list[dict[str, Any]], lease: dict[str, Any] | None, ledger_state: str,
               now: datetime) -> dict[str, Any]:
    done = sum(1 for s in stages if s["status"] in {"passed", "skipped"})
    return {
        "phase": phase,
        "label": PHASE_LABELS[phase],
        "running": [{"id": s["id"], "label": s["label"]} for s in stages if s["status"] == "in_progress"],
        "step_index": min(done + 1, len(stages)) if stages else 0,
        "step_total": len(stages),
        "lease": lease_view(lease, now),
        "open_items_state": ledger_state,
    }


def counts_for(ledger: dict[str, Any] | None, ledger_state: str, needs: list[dict[str, Any]],
               answers: dict[str, Any]) -> dict[str, Any]:
    """The numbers the app says ("3 things are needed before filing: 1 from the client, 1 for you and 1 risk to
    weigh"; "3 of 12 answered"), counted once here so they always add up."""
    blocking = {"client": 0, "you": 0, "risks": 0}
    for it in (ledger or {}).get("open", []):
        if not it["blocks_filing"]:
            continue
        if it["who"] == "system":
            blocking["you"] += 1
        elif it["type"] == "risk":
            blocking["risks"] += 1
        elif it["who"] == "client":
            blocking["client"] += 1
        else:
            blocking["you"] += 1
    if ledger_state == "damaged":
        blocking["you"] += 1  # rewriting the unreadable list
    questions = [n for n in needs if n.get("who") == "attorney" and n.get("question")]
    return {
        "needed_before_filing": blocking["client"] + blocking["you"] + blocking["risks"],
        "blocking": blocking,
        "decisions_open": len(questions),
        "decisions_answered": sum(1 for n in questions if n.get("key") in answers),
        "open_total": len((ledger or {}).get("open", [])),
        "resolved_total": (ledger or {}).get("resolved_count", 0),
    }


def client_request_texts(outputs: dict[str, Any]) -> dict[str, str]:
    texts: dict[str, str] = {}
    if outputs.get("client_request"):
        texts["English"] = _read_text(Path(outputs["client_request"]["path"]), 20000)
    for copy in outputs.get("client_request_translations") or []:
        texts[copy["language"]] = _read_text(Path(copy["path"]), 20000)
    return texts


def timeline_for(matter: Path, limit: int = 200) -> list[dict[str, str]]:
    """The matter's timeline, newest first. Lines written in the same second keep their order, newest first too
    (the times are to the second, so the file's order breaks the tie)."""
    events = [(i, e) for i, e in enumerate(read_jsonl(matter / EVENTS_FILE)) if e.get("at") and e.get("kind") and e.get("text")]
    floor = datetime.min.replace(tzinfo=timezone.utc)
    events.sort(key=lambda pair: (_parse_time(pair[1].get("at")) or floor, pair[0]), reverse=True)
    return [{k: as_text(e.get(k)) for k in ("at", "kind", "text", "actor")} for _i, e in events[:limit]]


def filed_record(matter: Path) -> dict[str, Any] | None:
    path = matter / FILED_FILE
    if not path.is_file():
        return None
    data = _read_json(path)
    filed_at = data.get("filed_at") if isinstance(data, dict) else None
    return {"filed_at": as_text(filed_at) or _mtime_iso(path)}


def stages_of(track: dict[str, Any] | None) -> list[dict[str, Any]]:
    return (track or {}).get("stages") or [
        {"id": s, "label": STAGE_LABELS.get(s, s), "status": "pending", "started_at": "", "completed_at": ""}
        for s in WORKFLOW_TEMPLATES[DEFAULT_WORKFLOW]
    ]


def intake_of(track: dict[str, Any] | None) -> dict[str, str]:
    intake = (track or {}).get("intake") or {}
    matter_type = as_text(intake.get("matter_type"))
    posture = as_text(intake.get("filing_posture"))
    t_entry = type_entry(matter_type)
    p_entry = posture_entry(posture)
    return {
        "matter_type": matter_type,
        "matter_type_label": t_entry["label"] if t_entry else matter_type,
        "filing_posture": posture,
        "filing_posture_label": p_entry["label"] if p_entry else posture,
        "deliverable": as_text(intake.get("deliverable")),
    }


FORM_NUMBER_RE = re.compile(r"\b(?:I|N|G|AR|DS)-\d+[A-Z]?\b", re.I)


def _case_type_words(matter_type: str) -> str:
    """The case type as the runtime reads it: a catalog id or label stands for its entry's case type."""
    t_entry = type_entry(matter_type or "")
    return t_entry["matter_type"] if t_entry else (matter_type or "")


def protected_case_type(matter_type: str) -> bool:
    """A case type that can only be a protected case, by the runtime's own rule (``scripts/matter_protection.py``),
    so a case described in words ("I-485 based on U status") counts the same in the app and the workflow."""
    from scripts.matter_protection import protected_case_type as runtime_check

    return bool(runtime_check(_case_type_words(matter_type)))


def protection_of(matter: Path, intake: dict[str, str], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Whether the matter is protected (8 U.S.C. 1367), and why, by the runtime's one rule: its setting, or a case
    type that can only be protected (``scripts/matter_protection.protection``). The card's settings, the list's case
    line, the timeline and every brief take it from here, so a matter from before the setting is protected in all."""
    from scripts.matter_protection import protection

    return protection(matter, matter_type=_case_type_words(intake.get("matter_type") or ""), meta=meta)


def effective_meta(matter: Path, meta: dict[str, Any], intake: dict[str, str]) -> dict[str, Any]:
    """The matter's settings as the app shows them: ``protected`` is the effective value, ``protected_reason`` why
    (``case_type`` when only the case type makes it so)."""
    shield = protection_of(matter, intake, meta)
    return {**meta, "protected": bool(shield["protected"]), "protected_reason": str(shield["reason"])}


def case_line(intake: dict[str, str], protected: bool) -> str:
    """The case as a list row shows it. A list is read at a glance, so a protected case shows only its form numbers."""
    if not protected:
        return intake["matter_type_label"]
    t_entry = type_entry(intake["matter_type"])
    if t_entry:
        return t_entry["short"] if t_entry.get("protected") else " ".join(FORM_NUMBER_RE.findall(t_entry["short"])) or t_entry["short"]
    forms: list[str] = []
    for f in FORM_NUMBER_RE.findall(intake["matter_type"]):
        if f.upper() not in forms:
            forms.append(f.upper())
    return " ".join(forms)


# ---------------------------------------------------------------------------
# One matter, read once
# ---------------------------------------------------------------------------

class MatterRead:
    """What both the card and the list row need, read from the folder once."""

    def __init__(self, ctx: Context, matter: Path, *, light: bool = False) -> None:
        self.ctx = ctx
        self.matter = matter
        self.now = ctx.now()
        self.track = load_track(matter)
        self.stages = stages_of(self.track)
        self.lease = read_lease(matter)
        self.lease_file = (matter / LEASE_FILE).exists()
        self.ledger_state, self.ledger = ledger_for(matter)
        self.filed = filed_record(matter)
        self.output_files = walk_output(matter)
        # Findings matter for the list only when there's no open items list to read the questions from.
        self.findings = findings_for(matter, self.output_files) if (not light or self.ledger_state == "missing") else []
        self.needs = needs_you(self.track, self.findings, self.ledger, self.ledger_state, matter.name)
        self.intake = intake_of(self.track)
        # The settings with protection as the one rule has it: the flag, or a case type that can only be protected.
        self.meta = effective_meta(matter, read_meta(matter), self.intake)
        # The card lists and hashes documents itself; a list row only counts them.
        self.doc_files = walk_files(matter) if light else []
        self.changed_at = ""
        legacy = not self.lease_file and any(s["status"] == "in_progress" for s in self.stages)
        if legacy or not light:
            self.changed_at = last_change(matter, self.track, self.output_files)

    def phase(self, doc_count: int) -> str:
        return phase_for(self.track, doc_count, self.needs, self.ledger, filed=bool(self.filed),
                         last_change_at=self.changed_at, now=self.now, lease=self.lease, lease_file=self.lease_file,
                         ledger_state=self.ledger_state)


def matter_card(ctx: Context, matter: Path) -> dict[str, Any]:
    r = MatterRead(ctx, matter)
    track, stages = r.track, r.stages
    docs = documents_for(matter, track)
    outputs = outputs_for(matter, r.output_files)
    chat = chat_changes_since_build(matter, track)
    phase = r.phase(docs["count"])
    label = PHASE_LABELS[phase]
    if phase == "complete" and not outputs["packet"]:
        label = "Complete"
    status = status_for(phase, stages, r.lease, r.ledger_state, r.now) | {"label": label}
    done = sum(1 for s in stages if s["status"] in {"passed", "skipped"})
    current = (
        next((s for s in stages if s["status"] in {"blocked", "failed"}), None)
        or next((s for s in stages if s["status"] == "in_progress"), None)
        or next((s for s in stages if s["status"] == "pending"), None)
    )
    answers = read_answers(matter)
    card = {
        "name": matter.name,
        "path": str(matter),
        "phase": phase,
        "phase_label": label,
        "status": status,
        "counts": counts_for(r.ledger, r.ledger_state, r.needs, answers),
        "needs_intake": not r.intake["matter_type"],
        "intake": r.intake,
        # The case as every screen names it: in a protected matter its form numbers only, as the list shows it.
        "case_line": case_line(r.intake, bool(r.meta["protected"])),
        "meta": r.meta,
        "created_at": as_text((track or {}).get("created_at")),
        "updated_at": as_text((track or {}).get("updated_at")) or docs["last_added"],
        "documents": docs,
        "progress": {
            "stages": stages,
            "done": done,
            "total": len(stages),
            "current": current,
            "current_index": stages.index(current) + 1 if current else None,
            "current_label": current["label"] if current else None,
            "minutes_left": minutes_left(stages, r.now),
            "updated_at": r.changed_at,
        },
        "needs_you": r.needs,
        "review_notes": review_notes(r.findings),
        "outputs": outputs,
        "open_items": r.ledger,
        "answers": answers,
        "memo_text": _read_text(Path(outputs["memo"]["path"])) if outputs["memo"] else "",
        "client_request_text": _read_text(Path(outputs["client_request"]["path"]), 20000) if outputs["client_request"] else "",
        # Every language the client request is written in, English first: {"English": text, "Spanish": text}.
        "client_request_texts": client_request_texts(outputs),
        "attorney_instructions": read_instructions(matter),
        "chat_changes": chat,
        "timeline": timeline_for(matter),
        # The sample matter's guide (what to try, what a good review catches); None for every real matter.
        "sample": sample_guide(ctx, matter),
    }
    if r.filed:
        card["filed_at"] = r.filed["filed_at"]
    return card


# ---------------------------------------------------------------------------
# The matters list
# ---------------------------------------------------------------------------

def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def next_line(phase: str, needs: list[dict[str, Any]], ledger: dict[str, Any] | None, counts: dict[str, Any]) -> str:
    """The one thing to do next, as a list row says it after the case: "Answer 2 questions"."""
    questions = sum(1 for n in needs if n.get("who") == "attorney")
    setup = sum(1 for n in needs if n.get("who") == "system")
    client = counts["blocking"]["client"] or sum(1 for n in needs if n.get("who") == "client")
    if phase == "new":
        return "Add the client's documents"
    if phase == "ready":
        return "Build the packet"
    if phase == "reviewed":
        return "Build the packet"
    if phase == "building":
        return ""
    if phase == "paused":
        return "Continue building"
    if phase == "needs_you":
        if setup and not questions:
            return "Fix a setup problem" if setup == 1 else f"Fix {setup} setup problems"
        return f"Answer {_plural(questions, 'question', 'questions')}"
    if phase == "waiting_client":
        return f"Waiting on {_plural(client, 'item', 'items')} from the client" if client else "Waiting on the client"
    if phase == "draft":
        n = counts["needed_before_filing"]
        return f"{n} needed before filing" if n else "Read the draft packet"
    if phase == "complete":
        return "Open the packet"
    return ""


def running_line(phase: str, status: dict[str, Any]) -> str:
    if phase != "building" or not status["step_total"]:
        return ""
    names = [s["label"] for s in status["running"]]
    where = f"step {status['step_index']} of {status['step_total']}"
    if not names:
        return where
    return f"{where}: {names[0] if len(names) == 1 else ', '.join(names[:-1]) + ' and ' + names[-1]}"


def list_row(ctx: Context, matter: Path) -> dict[str, Any]:
    """One row of the matters list: only what the row shows, read without hashing documents or building a card."""
    r = MatterRead(ctx, matter, light=True)
    phase = r.phase(len(r.doc_files))
    status = status_for(phase, r.stages, r.lease, r.ledger_state, r.now)
    counts = counts_for(r.ledger, r.ledger_state, r.needs, {})
    row = {
        "path": str(matter),
        "name": matter.name,
        "case_line": case_line(r.intake, bool(r.meta["protected"])),
        "phase": phase,
        "label": PHASE_LABELS[phase],
        "next_line": next_line(phase, r.needs, r.ledger, counts),
        "running_line": running_line(phase, status),
        "updated_at": as_text((r.track or {}).get("updated_at")) or _newest_time(r.doc_files),
        "archived": bool(r.meta.get("archived_at")),
        "sample": is_sample(matter),
        "counts": counts,
        # A background run holds the matter, as the runtime's network gate counts one (whatever the phase says):
        # the app's research gate checks such a matter's private terms too.
        "unattended_run": lease_is_unattended(r.lease, r.now),
        "lease": lease_row(r.lease, r.now),
    }
    if r.filed:
        row["filed_at"] = r.filed["filed_at"]
    return row


def _newest_time(files: list[Path]) -> str:
    times = []
    for p in files:
        try:
            st = p.stat()
        except OSError:
            continue
        times.append(max(st.st_mtime, st.st_ctime))
    return _iso(max(times)) if times else ""


REPAIR_LINE = "Immigration Packet Builder can't read this matter. Ask Claude to repair it."
DAMAGED_RECORD_LINE = "Claude's record of this matter's steps can't be read. Ask Claude to repair it."
OUTSIDE_LINE = "This matter's folder is a link to a folder outside your Matters folder. Move the folder itself into your Matters folder."


def problem_row(matter: Path, line: str, ask: str = "") -> dict[str, Any]:
    """A row for a matter the app can't show: what's wrong, and the request that has Claude fix it."""
    row = {
        "path": str(matter), "name": matter.name, "case_line": "", "phase": "problem", "label": "Can't open",
        "next_line": line, "running_line": "", "updated_at": "", "archived": False, "problem": True, "lease": None,
    }
    if ask:
        row["ask"] = ask
    return row


def matter_folders(ctx: Context) -> list[Path]:
    root = ctx.matters_root
    if not root.is_dir():
        return []
    return [child for child in sorted(root.iterdir(), key=lambda p: p.name.lower()) if child.is_dir() and is_matter_name(child.name)]


def matters_list(ctx: Context, include_archived: bool = True) -> list[dict[str, Any]]:
    """Every matter as a list row. One matter the app can't read gets a row that says so; it never takes the list
    down with it."""
    rows: list[dict[str, Any]] = []
    for child in matter_folders(ctx):
        if child.is_symlink():
            rows.append(problem_row(child, OUTSIDE_LINE))
            continue
        try:
            row = list_row(ctx, child)
        except DamagedRecord as exc:
            # Its record of the steps is there but won't parse: never shown as a matter nothing has run on.
            log(f"list row: the workflow record of matter {matter_tag(child)} can't be read")
            row = problem_row(child, DAMAGED_RECORD_LINE, exc.ask)
        except Exception as exc:
            log(f"list row failed for matter {matter_tag(child)}: {type(exc).__name__}")
            row = problem_row(child, REPAIR_LINE, f"Repair the Immigration Packet Builder matter {child.name}: its files can't be read.")
        if include_archived or not row["archived"]:
            rows.append(row)
    return rows


def app_payload(ctx: Context, selected: Path | None, status: str = "opened", matters: list[dict[str, Any]] | None = None,
                want_setup: bool = False) -> dict[str, Any]:
    rows = matters if matters is not None else matters_list(ctx)
    payload = {
        "status": status,
        "version": plugin_version(ctx),
        "matters_root": str(ctx.matters_root),
        "profile": load_profile(ctx),
        "catalog": catalog(),
        "matters": [row for row in rows if not row.get("archived")],
        "archived_count": sum(1 for row in rows if row.get("archived")),
        "selected": str(selected) if selected else "",
        "matter": card_or_problem(ctx, selected) if selected else None,
    }
    setup = doctor(ctx)
    if want_setup or not setup["ok"]:
        payload["setup"] = setup
    return payload


def card_or_problem(ctx: Context, matter: Path) -> dict[str, Any]:
    """The open matter's card. A matter whose files can't be read says so in a sentence instead of failing."""
    from .common import UserError

    try:
        return matter_card(ctx, matter)
    except DamagedRecord:
        log(f"card: the workflow record of matter {matter_tag(matter)} can't be read")
        raise
    except Exception as exc:
        log(f"card failed for matter {matter_tag(matter)}: {type(exc).__name__}")
        raise UserError(f"Immigration Packet Builder can't read {matter.name}. Ask Claude to repair it: \"Repair the Senior "
                        f"Associate matter {matter.name}: its files can't be read.\"") from exc

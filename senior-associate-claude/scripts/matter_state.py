#!/usr/bin/env python3
"""Shared matter state: the small files the app, the workflow runtime and the matter chat all touch.

Standard library only, so the app's helper server, the runtime and the privacy scripts can all import it
(``from scripts.matter_state import ...`` with the plugin root on ``sys.path``).

Every file here lives in ``output/working/workflow/`` inside the matter folder:

    .lock                    held (fcntl) around every read-modify-write below, and around open-items.json
    run-lease.json           who is working on the matter right now, and when they last showed signs of life
    attorney-actions.jsonl   Mark done / Reopen / Accept this risk, appended; applied on top of open-items.json
    attorney-answers.json    answers the attorney typed and saved, kept until a run works them in
    matter-meta.json         the attorney's settings for the matter: protected, archived, language, filing method
    events.jsonl             the matter's timeline, appended by the app and the runtime

Writes are atomic (temp file in the same folder, then ``os.replace``), so a reader never sees half a file.

It also holds the small helpers every runtime script shares: the time stamp, the atomic JSON write, a file's
sha256, and a path as the matter's records write it.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Iterator
import uuid

WORKFLOW_DIR = Path("output") / "working" / "workflow"
LOCK_FILE = WORKFLOW_DIR / ".lock"
LEASE_FILE = WORKFLOW_DIR / "run-lease.json"
ACTIONS_FILE = WORKFLOW_DIR / "attorney-actions.jsonl"
ANSWERS_FILE = WORKFLOW_DIR / "attorney-answers.json"
META_FILE = WORKFLOW_DIR / "matter-meta.json"
EVENTS_FILE = WORKFLOW_DIR / "events.jsonl"
OPEN_ITEMS_FILE = Path("output") / "deliverables" / "open-items.json"

# Files the app or the attorney writes. Their changes are not signs that Claude is working.
APP_WRITTEN_NAMES = frozenset({
    ".lock",
    "run-lease.json",
    "attorney-actions.jsonl",
    "attorney-answers.json",
    "attorney-instructions.md",
    "matter-meta.json",
    "events.jsonl",
    "chat-changes.json",
    "filed.json",
    "removed.json",
    "hash-cache.json",
    "fingerprint-cache.json",
    "filing-approval.json",
})

# A lease nobody has renewed for this long belongs to a run that is gone.
LEASE_FRESH_SECONDS = 30 * 60
# A run the app started is renewed by the app every 15 seconds while its agent lives. When the app stops (Claude
# quit, the start was left unsent in the chat box), the run is gone well before 30 minutes; this long without the
# app's renewal means so.
APP_HEARTBEAT_STALE_SECONDS = 3 * 60
# A renewal stamped further ahead than this (a clock set wrong, a file written by hand) is no sign of life: it would
# otherwise hold the matter until that time came.
LEASE_FUTURE_SECONDS = 5 * 60
LOCK_TIMEOUT_SECONDS = 10.0

LEASE_KINDS = frozenset({"build", "review", "update", "redo", "officer", "chat", "other"})
LEASE_HOLDERS = frozenset({"app", "chat", "orchestrator"})
ATTORNEY_ACTIONS = frozenset({"resolve", "reopen", "accept_risk"})
FILING_METHODS = frozenset({"paper", "online"})
PROTECTED_REASONS = frozenset({"catalog", "attorney", "docs_review"})

META_DEFAULTS: dict[str, Any] = {
    "protected": False,
    "protected_reason": "",
    "archived_at": "",
    "client_language": "English",
    "filing_method": "paper",
    "client_name": "",
    "forum": "USCIS",
    "circuit": "",
    "jurisdiction_basis": "",
}


class LockTimeout(RuntimeError):
    """Another process held the matter lock for longer than the timeout."""


@dataclass(frozen=True)
class ReadResult:
    """A JSON file read: ``state`` is ``missing``, ``ok`` or ``damaged`` (exists but won't parse, or wrong shape)."""

    state: str
    data: Any = None

    @property
    def ok(self) -> bool:
        return self.state == "ok"


# ---------------------------------------------------------------------------
# Time, locking, files
# ---------------------------------------------------------------------------

def now_iso(now: datetime | None = None, *, precise: bool = False) -> str:
    """Now (or ``now``) in UTC, to the second. ``precise`` keeps the microseconds: the workflow record times its
    steps from these stamps."""
    stamp = (now or datetime.now(tz=timezone.utc)).astimezone(timezone.utc)
    return stamp.isoformat() if precise else stamp.isoformat(timespec="seconds")


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@contextmanager
def matter_lock(matter: Path, timeout: float = LOCK_TIMEOUT_SECONDS) -> Iterator[None]:
    """Hold the matter's lock. Every read-modify-write of a shared matter file happens inside one.

    The lock is advisory (fcntl.flock), per matter, and released when the block ends or the process dies.
    Raises LockTimeout after ``timeout`` seconds.
    """
    path = Path(matter) / LOCK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                    raise
                if time.monotonic() >= deadline:
                    raise LockTimeout(f"the matter is busy: {path}") from exc
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def write_json_atomic(path: Path, data: Any) -> None:
    """Write JSON so a reader sees the old file or the new one, never part of one: the new file is on disk before it
    replaces the old (a crash or a full disk mid-write can't leave a record cut short), and only its owner can read
    it, as matter files hold client facts."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def read_json(path: Path) -> ReadResult:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ReadResult("missing")
    except OSError:
        return ReadResult("damaged")
    if not text.strip():
        return ReadResult("damaged")
    try:
        return ReadResult("ok", json.loads(text))
    except ValueError:
        return ReadResult("damaged")


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Append one JSON line. Callers hold the matter lock."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Every well-formed object line; a damaged line is skipped, not fatal."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def sha256_file(path: Path) -> str:
    with open(path, "rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def relative_to_matter(matter: Path, path: Path) -> str:
    """A path as the matter's records write it: relative to the matter folder, or absolute when it's outside."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path(matter).resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def is_app_written(path: Path) -> bool:
    """True for files the app or the attorney writes, whose changes say nothing about Claude working."""
    name = Path(path).name
    return name in APP_WRITTEN_NAMES or (name.startswith(".") and name.endswith(".tmp"))


# ---------------------------------------------------------------------------
# Run lease
# ---------------------------------------------------------------------------

def read_lease(matter: Path) -> dict[str, Any] | None:
    result = read_json(Path(matter) / LEASE_FILE)
    if not result.ok or not isinstance(result.data, dict) or not result.data.get("run_id"):
        return None
    return result.data


def _beat_within(beat: datetime | None, current: datetime, seconds: float) -> bool:
    """A renewal at ``beat`` is recent: less than ``seconds`` ago, and not more than five minutes ahead."""
    if beat is None:
        return False
    age = (current - beat).total_seconds()
    return -LEASE_FUTURE_SECONDS <= age < seconds


def lease_is_fresh(lease: dict[str, Any] | None, now: datetime | None = None) -> bool:
    """True while the run that holds the lease is alive: not released, renewed within 30 minutes (and not stamped
    more than five minutes ahead), and, for a run the app started, renewed by the app within 3 minutes."""
    if not lease or lease.get("released_at"):
        return False
    current = now or datetime.now(tz=timezone.utc)
    beat = parse_time(lease.get("heartbeat_at")) or parse_time(lease.get("started_at"))
    if not _beat_within(beat, current, LEASE_FRESH_SECONDS):
        return False
    if lease.get("origin") == "app":
        app_beat = parse_time(lease.get("app_heartbeat_at")) or parse_time(lease.get("started_at"))
        if not _beat_within(app_beat, current, APP_HEARTBEAT_STALE_SECONDS):
            return False
    return True


def acquire_lease(matter: Path, run_id: str, kind: str, holder: str, description: str = "",
                  now: datetime | None = None) -> tuple[bool, dict[str, Any] | None]:
    """Take the matter for a run. Returns (True, lease) or (False, the fresh lease someone else holds).

    Taking a lease the same run already holds renews it (the orchestrator does this with the run id the app gave
    it). ``origin`` records who took it first and never changes, so a run the app started stays tied to the app's
    renewals. A stale or released lease is replaced, and the timeline notes that the earlier run stopped without
    finishing.
    """
    if kind not in LEASE_KINDS:
        kind = "other"
    if holder not in LEASE_HOLDERS:
        raise ValueError(f"unknown lease holder: {holder}")
    matter = Path(matter)
    stamp = now_iso(now)
    with matter_lock(matter):
        current = read_lease(matter)
        if current and lease_is_fresh(current, now) and current.get("run_id") != run_id:
            return False, current
        if current and current.get("run_id") != run_id and not current.get("released_at"):
            _event_locked(matter, "run_abandoned", "An earlier run stopped without finishing.", actor="app", now=now,
                          run_id=current.get("run_id", ""))
        # The same run renewing its own live lease keeps its history. Taking up a run id whose lease was released or
        # went stale (a start left in the chat box and sent later) is a new taking: its origin is the new holder, so
        # the app's three-minute rule can't make a live orchestrator's lease look stale.
        same = bool(current and current.get("run_id") == run_id and not current.get("released_at")
                    and lease_is_fresh(current, now))
        lease = {
            "run_id": run_id,
            "kind": kind,
            "holder": holder,
            "origin": (current.get("origin") or current.get("holder")) if same else holder,
            "description": description,
            "started_at": current.get("started_at") if same else stamp,
            "heartbeat_at": stamp,
            "app_heartbeat_at": current.get("app_heartbeat_at", "") if same else "",
            "stage": current.get("stage", "") if same else "",
            "released_at": "",
            "outcome": "",
        }
        if holder == "app":
            lease["app_heartbeat_at"] = stamp
        write_json_atomic(matter / LEASE_FILE, lease)
        return True, lease


def heartbeat_lease(matter: Path, run_id: str | None = None, stage: str | None = None,
                    now: datetime | None = None, by_app: bool = False) -> dict[str, Any] | None:
    """Renew the current lease. With ``run_id``, only that run's lease; without, whichever unreleased lease
    exists (any runtime command is a sign the run is alive). ``by_app`` is the app's own renewal for a run it
    started (it needs ``run_id``). Returns the lease, or None if there was none."""
    if by_app and not run_id:
        raise ValueError("the app renews only its own run: pass run_id")
    matter = Path(matter)
    if not (matter / LEASE_FILE).exists():
        return None
    with matter_lock(matter):
        lease = read_lease(matter)
        if not lease or lease.get("released_at"):
            return None
        if run_id and lease.get("run_id") != run_id:
            return None
        lease["heartbeat_at"] = now_iso(now)
        if by_app:
            lease["app_heartbeat_at"] = lease["heartbeat_at"]
        if stage is not None:
            lease["stage"] = stage
        write_json_atomic(matter / LEASE_FILE, lease)
        return lease


# What a run learns when it renews its own lease (renew_run_lease).
RUN_RENEWED = "renewed"   # its lease, renewed
RUN_NO_LEASE = "none"     # no lease at all (an older matter, a run that never took one): nothing to renew
RUN_TAKEN = "taken"       # another run holds the matter now
RUN_LOST = "lost"         # another run took the matter after this one went quiet; that run has since ended or gone quiet
RUN_ENDED = "ended"       # this run's lease was released (by the run, the app's Stop, or the attorney in the app)


def renew_run_lease(matter: Path, run_id: str, stage: str | None = None,
                    now: datetime | None = None) -> tuple[str, dict[str, Any] | None]:
    """A run's own renewal, before one of its commands changes the matter: only that run's lease is renewed, and a
    run that no longer holds the matter learns so before it changes anything (it must stop). Returns (what, lease),
    ``what`` one of RUN_RENEWED, RUN_NO_LEASE, RUN_TAKEN, RUN_LOST, RUN_ENDED."""
    matter = Path(matter)
    if not (matter / LEASE_FILE).exists():
        return RUN_NO_LEASE, None
    with matter_lock(matter):
        lease = read_lease(matter)
        if not lease:
            return RUN_NO_LEASE, None
        if lease.get("run_id") != run_id:
            return (RUN_TAKEN if lease_is_fresh(lease, now) else RUN_LOST), lease
        if lease.get("released_at"):
            return RUN_ENDED, lease
        lease["heartbeat_at"] = now_iso(now)
        if stage is not None:
            lease["stage"] = stage
        write_json_atomic(matter / LEASE_FILE, lease)
        return RUN_RENEWED, lease


_last_sign_of_life: dict[str, float] = {}


def sign_of_life(matter: Path, now: datetime | None = None, timeout: float = 2.0, every: float = 0.0) -> bool:
    """A long tool's renewal while it works (the forms build, the packet assembly), so a step that runs for a long
    time doesn't let its run's lease go stale. Only a fresh lease is renewed: a tool run by hand never revives a run
    that has gone. A busy matter skips the renewal rather than hold the tool up, and nothing here fails the tool.
    With ``every``, a tool that calls it in a loop renews at most once in that many seconds. Returns True when it
    renewed."""
    matter = Path(matter)
    if every:
        tick = time.monotonic()
        if tick - _last_sign_of_life.get(str(matter), -every) < every:
            return False
        _last_sign_of_life[str(matter)] = tick
    try:
        if not (matter / LEASE_FILE).exists():
            return False
        with matter_lock(matter, timeout=timeout):
            lease = read_lease(matter)
            if not lease_is_fresh(lease, now):
                return False
            lease["heartbeat_at"] = now_iso(now)
            write_json_atomic(matter / LEASE_FILE, lease)
            return True
    except (LockTimeout, OSError):
        return False


def release_lease(matter: Path, run_id: str, outcome: str = "done", now: datetime | None = None) -> bool:
    """End a run's lease. Returns False when the lease belongs to another run, or that run already ended it: an
    ended lease keeps the outcome it ended with (the orchestrator's own word on how the run went), and nothing
    changes."""
    matter = Path(matter)
    with matter_lock(matter):
        lease = read_lease(matter)
        if not lease or lease.get("run_id") != run_id or lease.get("released_at"):
            return False
        lease["released_at"] = now_iso(now)
        lease["outcome"] = outcome
        write_json_atomic(matter / LEASE_FILE, lease)
        return True


def withdraw_start(matter: Path, run_id: str, now: datetime | None = None) -> str:
    """The app gives up a start it never saw begin (a request it left in the chat box). Returns what happened:

    - ``released``: the app still held the lease, so nothing was sent; it ends, outcome ``stopped``.
    - ``taken_up``: a run took the lease up under this run id (the request was sent after all, and the orchestrator
      renewed it). That run keeps the matter on its own renewals, as one started from the chat would: its origin
      becomes its holder, so the app's three-minute rule no longer applies to it.
    - ``gone``: the lease is another run's, or already ended. Nothing changes.
    """
    matter = Path(matter)
    with matter_lock(matter):
        lease = read_lease(matter)
        if not lease or lease.get("run_id") != run_id or lease.get("released_at"):
            return "gone"
        holder = str(lease.get("holder") or "app")
        if holder == "app":
            lease["released_at"] = now_iso(now)
            lease["outcome"] = "stopped"
            write_json_atomic(matter / LEASE_FILE, lease)
            return "released"
        lease["origin"] = holder
        write_json_atomic(matter / LEASE_FILE, lease)
        return "taken_up"


def new_run_id() -> str:
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Open items and the attorney's actions on them
# ---------------------------------------------------------------------------

def read_open_items(matter: Path) -> ReadResult:
    """The open-items list as written, or ``damaged`` when it won't parse or has no ``items`` list."""
    result = read_json(Path(matter) / OPEN_ITEMS_FILE)
    if result.state != "ok":
        return result
    data = result.data
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return ReadResult("damaged")
    return result


def record_attorney_action(matter: Path, action: str, item_id: str, note: str = "", by: str = "app",
                           now: datetime | None = None) -> dict[str, Any]:
    """Append Mark done (``resolve``), ``reopen`` or Accept this risk (``accept_risk``) for one open item.

    The app never edits open-items.json itself; the action is applied on top of whatever the list says, by the
    app when it shows the list and by the runtime when it next writes the list, so an agent rewriting the list
    from an older copy can't lose it.
    """
    if action not in ATTORNEY_ACTIONS:
        raise ValueError(f"unknown attorney action: {action}")
    if not item_id:
        raise ValueError("an attorney action needs an item id")
    record = {"id": uuid.uuid4().hex[:12], "at": now_iso(now), "action": action, "item_id": item_id,
              "note": note, "by": by}
    matter = Path(matter)
    with matter_lock(matter):
        append_jsonl(matter / ACTIONS_FILE, record)
        _event_locked(matter, f"item_{action}", _ACTION_EVENT_TEXT[action], actor="attorney", now=now, item_id=item_id)
    return record


_ACTION_EVENT_TEXT = {
    "resolve": "You marked an item done.",
    "reopen": "You reopened an item.",
    "accept_risk": "You accepted a risk.",
}


def attorney_actions(matter: Path) -> list[dict[str, Any]]:
    return [r for r in read_jsonl(Path(matter) / ACTIONS_FILE)
            if r.get("action") in ATTORNEY_ACTIONS and r.get("item_id") and r.get("id")]


def item_blocks_filing(item: Any) -> bool:
    """An open item holds up filing unless it says plainly that it doesn't (``blocks_filing: false``): a value that
    isn't a boolean ("no", 0, missing) is read the safe way, as the app reads it. A resolved item holds up nothing."""
    return isinstance(item, dict) and item.get("status", "open") == "open" and item.get("blocks_filing") is not False


def apply_attorney_actions(ledger: dict[str, Any], actions: list[dict[str, Any]]) -> tuple[dict[str, Any], int]:
    """Apply the attorney's actions to an open-items list. Pure: returns (new list, number applied).

    Each item remembers the action ids already applied to it (``attorney_actions_seen``), so applying again is a
    no-op, Claude can later change an item it has seen the action on, and a list rewritten from an older copy
    gets the action back. A reopened blocking item turns ``packet_status`` back to ``draft``. Resolving the last
    blocking item never promotes the list to ``ready_to_file``: the packet itself still has to be rebuilt and
    re-checked, which only an update does.
    """
    new = json.loads(json.dumps(ledger))
    items = [it for it in new.get("items", []) if isinstance(it, dict)]
    by_id = {str(it.get("id")): it for it in items if it.get("id")}
    applied = 0
    for act in actions:
        item = by_id.get(str(act.get("item_id")))
        if item is None:
            continue
        seen = item.get("attorney_actions_seen")
        if not isinstance(seen, list):
            seen = []
        if act["id"] in seen:
            continue
        kind = act["action"]
        note = str(act.get("note") or "").strip()
        if kind == "reopen":
            item["status"] = "open"
            item.pop("resolution", None)
            item.setdefault("notes", [])
            if isinstance(item["notes"], list):
                item["notes"].append("Reopened by the attorney." + (f" {note}" if note else ""))
        else:
            item["status"] = "resolved"
            default = "Risk accepted by the attorney." if kind == "accept_risk" else "Marked done by the attorney."
            item["resolution"] = note or default
            item["resolved_by"] = "attorney"
        seen.append(act["id"])
        item["attorney_actions_seen"] = seen
        applied += 1
    if any(item_blocks_filing(it) for it in items):
        new["packet_status"] = "draft"
    return new, applied


def merge_attorney_actions(matter: Path, now: datetime | None = None) -> int:
    """Write pending attorney actions into open-items.json, under the lock. Returns how many were applied.
    A missing or damaged list is left alone (returns 0)."""
    matter = Path(matter)
    with matter_lock(matter):
        result = read_open_items(matter)
        if not result.ok:
            return 0
        merged, applied = apply_attorney_actions(result.data, attorney_actions(matter))
        if applied:
            merged["updated_at"] = now_iso(now)
            write_json_atomic(matter / OPEN_ITEMS_FILE, merged)
        return applied


# ---------------------------------------------------------------------------
# Saved answers
# ---------------------------------------------------------------------------

def question_key(item_id: str | None, question: str) -> str:
    """A stable key for a question: its open item's id, or a hash of its words when it has no id."""
    if item_id:
        return str(item_id)
    words = re.sub(r"\s+", " ", str(question or "")).strip().casefold()
    return "q-" + hashlib.sha1(words.encode("utf-8")).hexdigest()[:12]


def read_answers(matter: Path) -> dict[str, dict[str, Any]]:
    result = read_json(Path(matter) / ANSWERS_FILE)
    if not result.ok or not isinstance(result.data, dict) or not isinstance(result.data.get("answers"), dict):
        return {}
    return {str(k): v for k, v in result.data["answers"].items() if isinstance(v, dict)}


def save_answer(matter: Path, key: str, question: str, answer: str, now: datetime | None = None) -> dict[str, Any]:
    """Keep an answer until a run works it in. An empty answer clears it."""
    matter = Path(matter)
    with matter_lock(matter):
        answers = read_answers(matter)
        if answer.strip():
            answers[key] = {"question": question, "answer": answer.strip(), "saved_at": now_iso(now)}
        else:
            answers.pop(key, None)
        write_json_atomic(matter / ANSWERS_FILE, {"answers": answers})
        return answers


def clear_answers(matter: Path, keys: list[str]) -> dict[str, dict[str, Any]]:
    matter = Path(matter)
    with matter_lock(matter):
        answers = read_answers(matter)
        for key in keys:
            answers.pop(key, None)
        write_json_atomic(matter / ANSWERS_FILE, {"answers": answers})
        return answers


# ---------------------------------------------------------------------------
# The attorney's settings for the matter
# ---------------------------------------------------------------------------

def read_meta(matter: Path) -> dict[str, Any]:
    result = read_json(Path(matter) / META_FILE)
    meta = dict(META_DEFAULTS)
    if result.ok and isinstance(result.data, dict):
        for key in META_DEFAULTS:
            if key in result.data:
                meta[key] = result.data[key]
    meta["protected"] = bool(meta.get("protected"))
    if meta.get("filing_method") not in FILING_METHODS:
        meta["filing_method"] = "paper"
    if not isinstance(meta.get("client_language"), str) or not meta["client_language"].strip():
        meta["client_language"] = "English"
    return meta


def update_meta(matter: Path, now: datetime | None = None, *, actor: str = "attorney", **changes: Any) -> dict[str, Any]:
    """Change some of the matter's settings. Unknown keys are refused; ``protected_reason`` must be one of
    catalog, attorney or docs_review when ``protected`` is set. ``actor`` is who made the change (``attorney``,
    ``claude`` or ``app``), for the timeline."""
    unknown = set(changes) - set(META_DEFAULTS)
    if unknown:
        raise ValueError(f"unknown matter settings: {sorted(unknown)}")
    if "filing_method" in changes and changes["filing_method"] not in FILING_METHODS:
        raise ValueError("filing_method is paper or online")
    if changes.get("protected") and changes.get("protected_reason", "attorney") not in PROTECTED_REASONS:
        raise ValueError("protected_reason is catalog, attorney or docs_review")
    matter = Path(matter)
    with matter_lock(matter):
        meta = read_meta(matter)
        before = dict(meta)
        meta.update(changes)
        if meta.get("protected") and not meta.get("protected_reason"):
            meta["protected_reason"] = "attorney"
        if not meta.get("protected"):
            meta["protected_reason"] = ""
        meta["updated_at"] = now_iso(now)
        write_json_atomic(matter / META_FILE, meta)
        for key, text in _META_EVENT_TEXT.items():
            if key in changes and before.get(key) != meta.get(key):
                _event_locked(matter, f"meta_{key}", text(meta, actor), actor=actor, now=now)
        return meta


def _protected_text(meta: dict[str, Any], actor: str) -> str:
    if not meta["protected"]:
        return "No longer marked as protected."
    if actor == "claude":
        return "The document review marked this matter protected."
    if meta.get("protected_reason") == "catalog":
        return "Protected, because of what is being filed."
    return "Marked as a protected matter."


_META_EVENT_TEXT = {
    "protected": _protected_text,
    "archived_at": lambda m, _a: "Archived." if m["archived_at"] else "Taken out of the archive.",
    "client_language": lambda m, _a: f"Client request language: {m['client_language']}.",
    "filing_method": lambda m, _a: "Filing online." if m["filing_method"] == "online" else "Filing on paper.",
}


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

def _event_locked(matter: Path, kind: str, text: str, actor: str = "app", now: datetime | None = None,
                  **extra: Any) -> dict[str, Any]:
    record = {"at": now_iso(now), "kind": kind, "text": text, "actor": actor}
    record.update({k: v for k, v in extra.items() if v not in (None, "")})
    append_jsonl(Path(matter) / EVENTS_FILE, record)
    return record


def add_event(matter: Path, kind: str, text: str, actor: str = "app", now: datetime | None = None,
              **extra: Any) -> dict[str, Any]:
    """Add one line to the matter's timeline. ``text`` is plain English the attorney reads; ``actor`` is
    ``app``, ``claude`` or ``attorney``. Never put a client's name, a number, or a case type in ``text`` beyond
    what the matter page already shows."""
    with matter_lock(Path(matter)):
        return _event_locked(matter, kind, text, actor=actor, now=now, **extra)


def read_events(matter: Path, limit: int = 200) -> list[dict[str, Any]]:
    """The newest ``limit`` events, newest first."""
    events = [e for e in read_jsonl(Path(matter) / EVENTS_FILE) if e.get("at") and e.get("kind")]
    # Newest first; events in the same second keep the order they were written in, newest first too.
    order = sorted(range(len(events)),
                   key=lambda i: (parse_time(events[i].get("at")) or datetime.min.replace(tzinfo=timezone.utc), i),
                   reverse=True)
    return [events[i] for i in order][:limit]

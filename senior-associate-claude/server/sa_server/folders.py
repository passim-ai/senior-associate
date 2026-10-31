"""Matter folders: finding a matter, the client's documents in it, Claude's workflow record, and the finished files."""
from __future__ import annotations

import hashlib
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .catalog import STAGE_LABELS
from .common import UserError, as_text, as_word, iso, mtime_iso, parse_time, read_json, show_path, write_json_atomic
from .context import Context

STATE_DIRS = ("output/working/workflow", "output/shareable/workflow", "output/workflow")
DELIVERABLES_DIR = Path("output") / "deliverables"
FILED_FILE = DELIVERABLES_DIR / "filed.json"
# Work set aside when the attorney changes what is being filed: the old packet, memo and open items, kept, not deleted.
EARLIER_DIR = Path("output") / "earlier"
# The attorney's standing instructions for the matter, typed on its page in the app. Every run's brief names the file
# and every step reads it. It sits with the workflow state, where client facts may be kept.
INSTRUCTIONS_FILE = Path("output") / "working" / "workflow" / "attorney-instructions.md"
INSTRUCTIONS_LIMIT = 8000
# Changes the attorney made to the matter's work by talking with Claude in chat, recorded by scripts/chat_changes.py.
# The app lists those made since Claude last finished a step, and the next update re-checks the packet with them.
CHAT_CHANGES_FILE = Path("output") / "working" / "workflow" / "chat-changes.json"
# Client files the attorney removed from the matter, kept so they can be put back.
REMOVED_DIR = Path("output") / "removed documents"
REMOVED_INDEX = REMOVED_DIR / "removed.json"
# Neither is Claude's work in progress: the files the app reads from output/ never include them.
SET_ASIDE = {EARLIER_DIR.name, REMOVED_DIR.name}
# Folders in the Matters folder that aren't matters (compared without regard to case).
SKIP_DIRS = {"output", "tmp", "__pycache__", "node_modules", "scripts", "docs", "tests", "Exemplar", "Exemplars"}
# Files that are never a client's document: Finder's and Windows' bookkeeping. "Icon\r" is a folder's custom icon.
SKIP_FILES = {".DS_Store", "Thumbs.db", "desktop.ini", "Icon\r"}
# The top-level names in a matter folder that are Claude's, never the client's. Compared without regard to case,
# because macOS folders don't tell "Output" from "output"; and only at the top, as the runtime reads them: a client's
# "Bank/tmp" folder is the client's.
RESERVED_TOP = {"output", "tmp"}
# Program folders, skipped at any depth.
PROGRAM_DIRS = {"__pycache__", "node_modules", ".git", ".venv"}
# The server's own cache of the client's documents' hashes, so a refresh doesn't read every file again.
HASH_CACHE = Path("output") / "working" / "workflow" / "hash-cache.json"


def is_reserved_top(name: str) -> bool:
    return name.casefold() in RESERVED_TOP


def is_matter_name(name: str) -> bool:
    """A folder in the Matters folder that can be a matter: not hidden, not one of the folders kept beside them."""
    return bool(name) and not name.startswith(".") and name.casefold() not in {d.casefold() for d in SKIP_DIRS}


def resolve_matter(ctx: Context, matter_path: str) -> Path:
    """A matter folder: one folder directly inside the Matters folder. Never the Matters folder itself, a folder
    inside a matter, or a link that leads out of the Matters folder."""
    raw = (matter_path or "").strip()
    if not raw:
        raise UserError("Choose a matter first.")
    root = ctx.matters_root
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    if candidate.parent != root or not is_matter_name(candidate.name):
        raise UserError(f"That folder isn't a matter in your Matters folder ({show_path(root)}). Move it there, or choose a matter from the list.")
    if not candidate.is_dir():
        raise UserError(f"{candidate.name} isn't in your Matters folder anymore. It may have been moved or renamed in Finder.")
    return candidate


def walk_files(root: Path, *, prune: set[str] | None = None) -> list[Path]:
    """Every regular file under root, never descending into hidden or program folders. With the default ``prune``
    (a matter folder), the top-level output/ and tmp/ are Claude's and skipped too, whatever their case."""
    found: list[Path] = []
    top_only = RESERVED_TOP if prune is None else set()
    anywhere = {d.casefold() for d in (PROGRAM_DIRS if prune is None else prune)}
    for dirpath, dirnames, filenames in os.walk(root):
        at_top = Path(dirpath) == root
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d.casefold() not in anywhere
                       and not (at_top and d.casefold() in top_only)]
        for name in filenames:
            if name in SKIP_FILES or name.startswith((".", "~$")):
                continue
            found.append(Path(dirpath) / name)
    return found


def walk_output(matter: Path) -> list[Path]:
    """Every file under the matter's output folder, skipping scratch."""
    out = matter / "output"
    if not out.is_dir():
        return []
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(out):
        # security/ holds stage-workspace copies and quarantine; privacy/ holds the policy and access log.
        at_top = Path(dirpath) == out
        dirnames[:] = [d for d in dirnames if d != "tmp" and not d.startswith(".") and not (at_top and d in {"security", "privacy", *SET_ASIDE})]
        for name in filenames:
            if not name.startswith((".", "~$")):
                found.append(Path(dirpath) / name)
    return found


def state_files(matter: Path) -> list[Path]:
    found: list[Path] = []
    for rel in STATE_DIRS:
        base = matter / rel
        if not base.is_dir():
            continue
        direct = base / "matter_status.json"
        if direct.is_file():
            found.append(direct)
        for child in sorted(base.iterdir()):
            if child.is_dir() and (child / "matter_status.json").is_file():
                found.append(child / "matter_status.json")
    return found


def track_of(state_path: Path) -> dict[str, Any] | None:
    """The workflow record as the app reads it, or None when it can't be read (it won't parse, or holds no stages,
    which the runtime refuses too)."""
    state = read_json(state_path)
    if not isinstance(state, dict) or not isinstance(state.get("stages"), dict):
        return None
    meta = state.get("matter") or {}
    stages_raw = state.get("stages") or {}
    order = state.get("required_stage_ids") or (list(stages_raw.keys()) if isinstance(stages_raw, dict) else [])
    stages = []
    snapshots: list[tuple[str, str]] = []
    for sid in order if isinstance(order, list) else []:
        sid = as_text(sid)
        if not sid:
            continue
        rec = stages_raw.get(sid, {}) if isinstance(stages_raw, dict) else {}
        rec = rec if isinstance(rec, dict) else {}
        status = as_word(rec.get("status")) or "pending"
        stages.append({
            "id": sid,
            "label": STAGE_LABELS.get(sid) or as_text(rec.get("display_name")) or sid,
            "status": status,
            "started_at": as_text(rec.get("started_at")),
            "completed_at": as_text(rec.get("completed_at")),
        })
        last_pass = rec.get("last_pass") if isinstance(rec.get("last_pass"), dict) else {}
        if status == "passed" and last_pass.get("snapshot"):
            snapshots.append((as_text(last_pass.get("completed_at") or rec.get("completed_at")), as_text(last_pass["snapshot"])))
    blockers = [
        {"id": as_text(b.get("id")), "stage": as_text(b.get("stage_id")), "owner": as_word(b.get("owner")), "summary": as_text(b.get("summary"))}
        for b in (state.get("blockers") if isinstance(state.get("blockers"), list) else [])
        if isinstance(b, dict) and as_word(b.get("status") or "open") == "open"
    ]
    meta = meta if isinstance(meta, dict) else {}
    history = state.get("history") if isinstance(state.get("history"), list) else []
    return {
        "workflow_key": as_text(meta.get("workflow_key") or state.get("workflow_key")),
        "intake": {
            "matter_type": as_text(meta.get("matter_type")),
            "filing_posture": as_text(meta.get("filing_posture")),
            "deliverable": as_text(meta.get("deliverable")),
            "workflow_key": as_text(meta.get("workflow_key") or state.get("workflow_key")),
        },
        "stages": stages,
        "blockers": blockers,
        "snapshots": sorted(snapshots, reverse=True),
        # When the steps were last sent back (a redo or an update that reroutes): the start of the current pass.
        "rerouted_at": max((as_text(h.get("timestamp")) for h in history
                            if isinstance(h, dict) and h.get("event") == "matter_rerouted"), default=""),
        "created_at": as_text(state.get("created_at")),
        "updated_at": as_text(state.get("updated_at")),
    }


class DamagedRecord(UserError):
    """The matter's workflow record is there but can't be read. It is never taken for a matter nothing has run on:
    the runtime refuses to work on it too, so the app says so, with the request that has Claude repair it."""

    def __init__(self, matter: Path) -> None:
        self.ask = f"Repair the Immigration Packet Builder matter {matter.name}: its record of the steps can't be read."
        super().__init__(f"Claude's record of the steps for {matter.name} can't be read, so Immigration Packet Builder can't show "
                         f"it. Ask Claude to repair it: \"{self.ask}\"")


def load_track(matter: Path) -> dict[str, Any] | None:
    """The matter's workflow record, chosen as the runtime chooses it (``matter_workflow.default_state_path``: the
    current layout, unless an older layout's record holds the work and the current one never started), so the app and
    the workflow read the same one. Otherwise the first readable record of any layout. None when there is no record;
    DamagedRecord when the record the runtime would use (or every record there is) can't be read."""
    try:
        from matter_workflow import default_state_path  # type: ignore
    except Exception:  # pragma: no cover - the runtime ships beside the server
        default_state_path = None
    if default_state_path is not None:
        try:
            chosen = default_state_path(matter)
        except Exception:
            chosen = None
        if chosen is not None and chosen.is_file():
            track = track_of(chosen)
            if track:
                return track
            raise DamagedRecord(matter)
    found = state_files(matter)
    tracks = [t for t in (track_of(p) for p in found) if t]
    if found and not tracks:
        raise DamagedRecord(matter)
    return tracks[0] if tracks else None


def file_time(st: os.stat_result) -> float:
    # A copied file keeps its original modified date; the change time says when it arrived in the matter.
    return max(st.st_mtime, st.st_ctime)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


class HashCache:
    """The client's documents' hashes, by path, kept while the file's size and modified time stay the same, so a
    refresh reads a file again only when it changed. Written only when something new was hashed or a file left."""

    def __init__(self, matter: Path) -> None:
        self.matter = matter
        data = read_json(matter / HASH_CACHE)
        files = data.get("files") if isinstance(data, dict) and data.get("version") == 1 else None
        self.entries: dict[str, dict[str, Any]] = {k: v for k, v in (files if isinstance(files, dict) else {}).items() if isinstance(v, dict)}
        self.dirty = False

    def sha(self, rel: str) -> str:
        path = self.matter / rel
        try:
            st = path.stat()
        except OSError:
            return ""
        known = self.entries.get(rel)
        if known and known.get("size") == st.st_size and known.get("mtime_ns") == st.st_mtime_ns and known.get("sha256"):
            return str(known["sha256"])
        digest = sha256(path)
        if digest:
            self.entries[rel] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "sha256": digest}
            self.dirty = True
        return digest

    def save(self, present: set[str]) -> None:
        stale = set(self.entries) - present
        for rel in stale:
            del self.entries[rel]
        if self.dirty or stale:
            try:
                write_json_atomic(self.matter / HASH_CACHE, {"version": 1, "files": self.entries})
            except OSError:
                pass  # a cache that can't be written only means hashing again next time
            self.dirty = False


# Hashing a new file costs a read of it; past this many at once, the rest count as new without the check for a
# renamed copy (a folder dropped in all at once).
MAX_HASHED_ARRIVALS = 200
# The runs that take in every new document when they start: one of these that finished saw them all.
WORK_RUN_KINDS = {"build", "continue", "update", "review_docs", "review_again", "redo"}
WORK_LEASE_KINDS = {"build", "update", "review", "redo"}


def last_work_run_start(matter: Path) -> datetime | None:
    """When the last run that finished its work started: from the server's own record of the app's runs on the
    timeline, and from the lease file for a run started from the chat. None when neither has one (older matters)."""
    from scripts.matter_state import read_jsonl, read_lease, EVENTS_FILE

    starts: list[datetime] = []
    for e in read_jsonl(matter / EVENTS_FILE):
        if e.get("kind") == "run_finished" and e.get("outcome") == "done" and e.get("run_kind") in WORK_RUN_KINDS:
            when = parse_time(e.get("started_at"))
            if when:
                starts.append(when)
    lease = read_lease(matter)
    if lease and lease.get("released_at") and lease.get("outcome") == "done" and lease.get("kind") in WORK_LEASE_KINDS:
        when = parse_time(lease.get("started_at"))
        if when:
            starts.append(when)
    return max(starts) if starts else None


def last_step_finished(track: dict[str, Any] | None) -> datetime | None:
    passed = [parse_time(s.get("completed_at")) for s in (track or {}).get("stages", []) if s["status"] == "passed"]
    return max((d for d in passed if d), default=None)


def seen_cutoff(matter: Path, track: dict[str, Any] | None) -> datetime | None:
    """What Claude has taken in: anything before the start of the last run that finished its work. A matter the app
    never ran has no record of runs; there, anything before the last step finished. None before any step passed."""
    finished = last_step_finished(track)
    if finished is None:
        return None
    return last_work_run_start(matter) or finished


def comparison_snapshot(matter: Path, track: dict[str, Any] | None) -> tuple[dict[str, str], datetime | None] | None:
    """The files Claude had when the current pass began: the snapshot taken by the oldest step to pass since the
    steps were last sent back (the document review's, for a build that ran straight through). The newest snapshot
    would count a document added halfway through a build as seen, though no step read it."""
    floor = datetime.min.replace(tzinfo=timezone.utc)
    snapshots = sorted(((parse_time(when), rel) for when, rel in (track or {}).get("snapshots", [])), key=lambda pair: pair[0] or floor)
    rerouted = parse_time((track or {}).get("rerouted_at"))
    current = [pair for pair in snapshots if rerouted is None or (pair[0] and pair[0] >= rerouted)] or snapshots
    for when, rel in current:
        data = read_json((matter / rel) if not Path(rel).is_absolute() else Path(rel))
        if isinstance(data, dict) and isinstance(data.get("files"), dict):
            return {str(k): str(v) for k, v in data["files"].items()}, parse_time(data.get("recorded_at")) or when
    return None


def arrivals(matter: Path, files: list[tuple[float, str, str]], track: dict[str, Any] | None,
             cache: HashCache | None = None) -> tuple[list[str], list[str]]:
    """The client's files Claude hasn't taken in yet: (new ones, ones replaced at a path Claude knows), newest first,
    by name; both empty before any step passed.

    A file is new when the comparison snapshot has neither its path nor its contents (a renamed copy is not new), and
    changed when the snapshot has its path with other contents. Either way it counts as taken in when it arrived
    before the last run that finished its work started. Older matters have no snapshots; there a file is new when it
    changed after the last step finished.
    """
    cutoff = seen_cutoff(matter, track)
    if cutoff is None:
        return [], []
    client = [f for f in files if not f[2].endswith((".tmp", ".pyc"))]
    if not client:
        return [], []
    run_start = last_work_run_start(matter)

    def taken_in(when: float) -> bool:
        return run_start is not None and when <= run_start.timestamp()

    found = comparison_snapshot(matter, track)
    if found is None:
        new = [f for f in client if f[0] > cutoff.timestamp() + 1]
        if len(new) == len(client) and len(client) > 1:
            return [], []  # every file is newer: the folder was copied or restored, not sent new documents
        return [name for _t, name, _rel in new], []
    cache = cache or HashCache(matter)
    snapshot, recorded = found
    known = {k: v for k, v in snapshot.items() if not k.startswith("output/")}
    unknown = [f for f in client if f[2] not in known]
    if len(unknown) == len(client) and len(client) > 1:
        return [], []  # nothing matches: the folder was copied or restored, not sent new documents
    hashes = set(snapshot.values())
    new: list[str] = []
    for i, (when, name, rel) in enumerate(unknown):
        if taken_in(when):
            continue
        if i < MAX_HASHED_ARRIVALS and cache.sha(rel) in hashes:
            continue  # a renamed copy of a file Claude has
        new.append(name)
    changed: list[str] = []
    since = recorded.timestamp() if recorded else None
    for when, name, rel in client:
        if rel not in known or taken_in(when):
            continue
        # A file untouched since the snapshot was taken still has the contents it had then: no need to read it.
        if since is not None and when < since:
            continue
        digest = cache.sha(rel)
        if digest and digest != known[rel]:
            changed.append(name)
    return new, changed


def added_since_build(matter: Path, files: list[tuple[float, str, str]], track: dict[str, Any] | None) -> list[str]:
    return arrivals(matter, files, track)[0]


def removed_index(matter: Path) -> list[dict[str, str]]:
    data = read_json(matter / REMOVED_INDEX)
    entries = data.get("removed") if isinstance(data, dict) else None
    return [e for e in entries if isinstance(e, dict) and isinstance(e.get("kept"), str) and isinstance(e.get("original"), str)] \
        if isinstance(entries, list) else []


def removed_documents(matter: Path) -> list[dict[str, str]]:
    """Client files the attorney removed and can put back, newest first."""
    out = []
    for e in reversed(removed_index(matter)):
        if (matter / e["kept"]).is_file():
            out.append({"name": Path(e["original"]).name, "path": e["original"], "kept": e["kept"], "removed_at": as_text(e.get("removed_at"))})
    return out


def removed_since_build(matter: Path, track: dict[str, Any] | None) -> list[str]:
    """Documents the attorney removed after Claude last took the matter in: still in the packet until an update."""
    cutoff = seen_cutoff(matter, track)
    if cutoff is None:
        return []
    return [r["path"] for r in removed_documents(matter) if (parse_time(r["removed_at"]) or cutoff) > cutoff]


def documents_for(matter: Path, track: dict[str, Any] | None = None) -> dict[str, Any]:
    files: list[tuple[float, str, str]] = []
    for p in walk_files(matter):
        try:
            files.append((file_time(p.stat()), p.name, p.relative_to(matter).as_posix()))
        except (OSError, ValueError):
            continue
    files.sort(reverse=True)
    last = iso(files[0][0]) if files else ""
    listed = [{"name": n, "path": rel, "modified": iso(m)} for m, n, rel in files[:300]]
    per_folder = Counter(rel.rsplit("/", 1)[0] if "/" in rel else "" for _m, _n, rel in files)
    folders = [{"path": k, "count": per_folder[k]} for k in sorted(per_folder, key=lambda k: (k != "", k.lower()))]
    cache = HashCache(matter)
    added, changed = arrivals(matter, files, track, cache)
    cache.save({rel for _m, _n, rel in files})
    return {
        "count": len(files),
        "listed": len(listed),
        "recent": [n for _, n, _ in files[:5]],
        "files": listed,
        "folders": folders,
        "added_since_build": added,
        "changed_since_build": changed,
        "removed": removed_documents(matter),
        "removed_since_build": removed_since_build(matter, track),
        "last_added": last,
        "folder": str(matter),
    }


def newest(paths: list[Path]) -> Path | None:
    paths = [p for p in paths if p.is_file()]
    return max(paths, key=lambda p: p.stat().st_mtime) if paths else None


def describe(p: Path | None) -> dict[str, Any] | None:
    return {"name": p.name, "path": str(p), "modified": mtime_iso(p)} if p else None


def describe_with_pdf(md: Path) -> dict[str, Any] | None:
    """A Markdown deliverable (the memo, a client request), and in `pdf` the PDF rendered from it, unless that is
    missing or older than the Markdown (out of date)."""
    if not md.is_file():
        return None
    out = describe(md)
    pdf = md.with_suffix(".pdf")
    try:
        if pdf.is_file() and pdf.stat().st_mtime >= md.stat().st_mtime:
            out["pdf"] = str(pdf)
    except OSError:
        pass
    return out


UPLOAD_SUFFIX = " upload files"
# A split filing's second packet, for the forms USCIS takes only on paper: "Filing Packet (paper part).pdf".
PAPER_PART_RE = re.compile(r"\(paper part\)", re.IGNORECASE)
TRANSLATED_REQUEST_RE = re.compile(r"^Client Request \((?P<language>[^()/]{1,40})\)\.md$")


def outputs_for(matter: Path, output_files: list[Path] | None = None) -> dict[str, Any]:
    """The attorney-facing files. The deliverables folder wins; older matters kept them elsewhere under output/. The
    client's own documents are never Claude's work, however they're named (a client's earlier "packet" PDF)."""
    deliverables = matter / DELIVERABLES_DIR
    if deliverables.is_dir():
        # The packet and the letter sit at the top of the folder; Forms/ and the upload files are folders of their own.
        candidates = [p for p in deliverables.iterdir() if p.is_file() and not p.name.startswith((".", "~$"))]
    else:
        candidates = list(output_files if output_files is not None else walk_output(matter))
    pdfs, docs = [], []
    for p in candidates:
        n = p.name.lower()
        if n.endswith(".pdf") and "packet" in n:
            pdfs.append(p)
        elif n.endswith(".docx") and "cover letter" in n and "bad-ai-pass" not in n:
            docs.append(p)
    forms_dir = deliverables / "Forms"
    forms = sorted((p for p in forms_dir.glob("*.pdf") if not p.name.startswith(".")), key=lambda p: p.name.lower()) if forms_dir.is_dir() else []
    memo = deliverables / "Attorney Memo.md"
    request = deliverables / "Client Request.md"
    main = [p for p in pdfs if not PAPER_PART_RE.search(p.name)]
    paper_parts = [p for p in pdfs if PAPER_PART_RE.search(p.name)]
    packet = newest(main) or newest(paper_parts)
    return {
        "packet": describe(packet),
        # A split filing: the paper packet beside the online one (CONTRACTS §11).
        "paper_packet": describe(newest(paper_parts)) if main else None,
        "cover_letter": describe(newest(docs)),
        "memo": describe_with_pdf(memo),
        "client_request": describe_with_pdf(request),
        # The client request in the client's language, when it isn't English (CONTRACTS §6).
        "client_request_translations": [
            {"language": m.group("language"), **(describe_with_pdf(p) or {})}
            for p in sorted(candidates, key=lambda p: p.name.lower()) if (m := TRANSLATED_REQUEST_RE.match(p.name))
        ],
        "filing_checklist": describe(_first_file(deliverables / "Filing Checklist.pdf", deliverables / "Filing Checklist.md")),
        "upload_files": _upload_files(deliverables, packet),
        "forms": [describe(p) for p in forms],
        "folder": str(deliverables) if deliverables.is_dir() else "",
        # Work set aside when what is being filed changed, for "Show the earlier work in Finder".
        "earlier": str(matter / EARLIER_DIR) if (matter / EARLIER_DIR).is_dir() else "",
    }


def _first_file(*paths: Path) -> Path | None:
    return next((p for p in paths if p.is_file()), None)


def _upload_files(deliverables: Path, packet: Path | None) -> dict[str, Any] | None:
    """For online filing: the packet split into PDFs by evidence category, in "<packet name> upload files"."""
    if not deliverables.is_dir():
        return None
    folders = [p for p in deliverables.iterdir() if p.is_dir() and p.name.endswith(UPLOAD_SUFFIX)]
    if not folders:
        return None
    wanted = deliverables / f"{packet.stem}{UPLOAD_SUFFIX}" if packet else None
    folder = wanted if wanted in folders else max(folders, key=lambda p: p.stat().st_mtime)
    files = sorted((p for p in folder.glob("*.pdf") if not p.name.startswith(".")), key=lambda p: p.name.lower())
    return {"name": folder.name, "path": str(folder), "count": len(files), "files": [describe(p) for p in files]}


def client_file(matter: Path, rel: str) -> Path:
    """One of the client's documents in the matter, by its path inside the matter folder; never Claude's own files."""
    raw = (rel or "").strip()
    target = (matter / raw).resolve() if raw else matter
    parts = target.relative_to(matter).parts if matter in target.parents else ()
    if not parts or is_reserved_top(parts[0]) or any(part.startswith(".") or part.casefold() in PROGRAM_DIRS for part in parts):
        raise UserError("That file isn't one of this matter's documents. Open the matter folder to see what's there.")
    if not target.is_file():
        raise UserError(f"{Path(raw).name} isn't in the matter folder anymore. It may have been moved or renamed in Finder.")
    return target


def free_path(dest: Path) -> Path:
    n = 2
    free = dest
    while free.exists():
        free = dest.with_name(f"{dest.stem} ({n}){dest.suffix}")
        n += 1
    return free


def safe_folder_name(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", name).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        raise UserError("Give the matter a name.")
    return cleaned[:80]


def exemplars_list(ctx: Context) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if ctx.exemplars_dir.is_dir():
        for f in sorted(ctx.exemplars_dir.iterdir(), key=lambda p: p.name.lower()):
            if f.is_file() and f.suffix.lower() in {".docx", ".pdf"} and not f.name.startswith((".", "~$")):
                out.append({"name": f.stem, "path": str(f)})
    return out


def read_instructions(matter: Path) -> str:
    from .common import read_text

    return read_text(matter / INSTRUCTIONS_FILE, INSTRUCTIONS_LIMIT).strip()

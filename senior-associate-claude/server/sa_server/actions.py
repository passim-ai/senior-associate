"""Everything that changes a matter: create it, add and take out documents, record what the attorney did, and
change what is being filed. Each returns the matter as it now stands."""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Iterator

from scripts.matter_state import (EVENTS_FILE, FILING_METHODS, META_FILE, WORKFLOW_DIR, acquire_lease, add_event,
                                  clear_answers, heartbeat_lease, lease_is_fresh, matter_lock, new_run_id, read_answers,
                                  read_events, read_lease, read_meta, read_open_items, record_attorney_action,
                                  release_lease, save_answer, update_meta, withdraw_start)

from .catalog import DEFAULT_DELIVERABLE, DEFAULT_WORKFLOW, FILING_POSTURES, posture_entry, type_entry
from .common import UserError, now_iso, parse_time
from .common import write_json_atomic as _write_json_atomic
from .context import Context
from .folders import (EARLIER_DIR, resolve_matter, track_of, FILED_FILE, INSTRUCTIONS_FILE, INSTRUCTIONS_LIMIT, REMOVED_DIR, REMOVED_INDEX,
                      client_file, free_path, load_track, outputs_for, read_instructions, removed_index,
                      safe_folder_name, state_files, is_reserved_top)
from .adding import AddResult, add_files, add_folder, pick_files, pick_folder
from .logs import log
from .profile import save_profile
from .prompts import prompt_for
from .readmodel import MatterRead, app_payload, lease_view, ledger_for, matter_folders, matter_tag, matters_list, stages_of
from . import samples

def run_ensure(ctx: Context, matter: Path, matter_type: str, filing_posture: str) -> str:
    cmd = [
        sys.executable, str(ctx.runtime_cli), "ensure", str(matter),
        "--matter-type", matter_type, "--filing-posture", filing_posture,
        "--deliverable", DEFAULT_DELIVERABLE, "--workflow-key", DEFAULT_WORKFLOW, "--json",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(ctx.plugin_root))
    if r.returncode != 0:
        return (r.stderr or r.stdout).strip()[-600:]
    return ""


def open_path(path: Path) -> None:
    if platform.system() == "Darwin":
        subprocess.Popen(["open", str(path)])
    elif platform.system() == "Windows":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(path)])




def _setup_warning(warning: str) -> str:
    first = next((line.strip() for line in reversed(warning.splitlines()) if line.strip()), "")[:200]
    return ("The matter folder was created, but Claude couldn't finish setting it up. You can still add documents. "
            f"If Build doesn't start, paste this into Ask Claude about this matter, on the matter page: {first}")



def _filing_method(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if value not in FILING_METHODS:
        raise UserError("Choose paper or online for how this will be filed.")
    return str(value)


def _apply_intake_settings(matter: Path, entry: dict[str, Any] | None, protected: bool | None, filing_method: str | None,
                           ctx: Context) -> None:
    """The settings chosen with what is being filed: protected by the case type itself (catalog) or by the attorney's
    choice, and the filing method. A case type that isn't protected never clears a protection already set."""
    changes: dict[str, Any] = {}
    if entry and entry.get("protected"):
        if not read_meta(matter).get("protected"):
            changes.update(protected=True, protected_reason="catalog")
    elif protected:
        changes.update(protected=True, protected_reason="attorney")
    if filing_method:
        changes["filing_method"] = filing_method
    if changes:
        update_meta(matter, now=ctx.now(), **changes)


def do_create(ctx: Context, name: str, matter_type: str, filing_posture: str = "new filing packet", *,
              protected: bool | None = None, filing_method: str | None = None) -> dict[str, Any]:
    """Make a matter folder with its workflow record and settings. A creation that fails partway (the setup step
    timing out, say) takes its folder back out, so no half-made matter is left in the list."""
    t = type_entry(matter_type)
    if not t:
        described = re.sub(r"\s+", " ", (matter_type or "")).strip()
        if len(described) < 3:
            raise UserError("Say what is being filed, for example \"I-485 based on asylee status\".")
        t = {"matter_type": described[:160]}
    p = posture_entry(filing_posture) or FILING_POSTURES[0]
    method = _filing_method(filing_method)
    base = safe_folder_name(name)
    ctx.matters_root.mkdir(parents=True, exist_ok=True)
    folder = ctx.matters_root / base
    n = 2
    while True:
        try:
            folder.mkdir()
            break
        except FileExistsError:
            folder = ctx.matters_root / f"{base} ({n})"
            n += 1
    try:
        warning = run_ensure(ctx, folder, t["matter_type"], p["value"])
        add_event(folder, "created", "Matter created.", actor="attorney", now=ctx.now())
        _apply_intake_settings(folder, t if t.get("id") else None, protected, method, ctx)
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    log(f"created matter {matter_tag(folder)}")
    payload = app_payload(ctx, folder, status="created")
    if warning:
        payload["warning"] = _setup_warning(warning)
    return payload


def _create_sample(ctx: Context) -> tuple[Path, str]:
    """Copy the sample's fictional documents in as a new matter marked as the sample: (the matter, any setup warning)."""
    m = samples.manifest(ctx)
    docs = samples.documents(ctx)
    if not m or not docs:
        raise UserError("The sample matter's files are missing from this install. Ask Claude to update Senior Associate.")
    payload = do_create(ctx, str(m["name"]), str(m["matter_type"]), str(m.get("filing_posture") or ""),
                        filing_method=m.get("filing_method"))
    matter = Path(payload["selected"])
    try:
        add_files(matter, docs)
        samples.mark_matter(matter)
        add_event(matter, "sample", "Sample matter added: fictional documents to try Senior Associate with.", now=ctx.now())
    except BaseException:
        shutil.rmtree(matter, ignore_errors=True)
        raise
    samples.record_offered(ctx, "added", matter)
    log(f"added the sample matter {matter_tag(matter)}")
    return matter, str(payload.get("warning") or "")


def ensure_sample(ctx: Context) -> Path | None:
    """The first time the app opens on an empty Matters folder, add the sample matter. A folder that already has
    matters is only recorded, so the sample never appears for an attorney who started without it. Never raises: the
    app opens either way."""
    if samples.was_offered(ctx):
        return None
    try:
        if matter_folders(ctx):
            samples.record_offered(ctx, "skipped: the Matters folder already had matters")
            return None
        return _create_sample(ctx)[0]
    except Exception as exc:  # noqa: BLE001 - a sample that can't be added must not keep the app from opening
        log(f"sample matter not added: {type(exc).__name__}")
        return None


def do_add_sample(ctx: Context) -> dict[str, Any]:
    """Help's Open the sample matter: open the sample (taken out of the archive when it was archived), or add it again
    when its folder is gone."""
    rows = [row for row in matters_list(ctx) if row.get("sample")]
    row = next((r for r in rows if not r.get("archived")), None) or next(iter(rows), None)
    if row:
        if row.get("archived"):
            return do_archive(ctx, row["path"], archived=False)
        return app_payload(ctx, Path(row["path"]), status="opened")
    matter, warning = _create_sample(ctx)
    payload = app_payload(ctx, matter, status="sample_added")
    if warning:
        payload["warning"] = _setup_warning(warning)
    return payload


def do_set_intake(ctx: Context, matter_path: str, matter_type: str, filing_posture: str = "new filing packet", *,
                  protected: bool | None = None, filing_method: str | None = None) -> dict[str, Any]:
    """Record what is being filed for a matter folder made outside the app (its card says needs_intake)."""
    matter = resolve_matter(ctx, matter_path)
    t = type_entry(matter_type)
    described = t["matter_type"] if t else re.sub(r"\s+", " ", (matter_type or "")).strip()[:160]
    if len(described) < 3:
        raise UserError("Say what is being filed, for example \"I-485 based on asylee status\".")
    p = posture_entry(filing_posture) or FILING_POSTURES[0]
    method = _filing_method(filing_method)
    warning = run_ensure(ctx, matter, described, p["value"])
    _apply_intake_settings(matter, t, protected, method, ctx)
    payload = app_payload(ctx, matter, status="intake_saved")
    if warning:
        payload["warning"] = _setup_warning(warning).replace("The matter folder was created, but ", "")
    return payload


def _added_payload(ctx: Context, matter: Path, result: AddResult | None) -> dict[str, Any]:
    if result is None:
        payload = app_payload(ctx, matter, status="cancelled")
        payload.update({"added": [], "cancelled": True})
        return payload
    if result.added:
        n = len(result.added)
        # A count, never names: a file name can say what a protected case is.
        add_event(matter, "documents_added", f"Added {n} file{'s' if n != 1 else ''}.", actor="attorney", now=ctx.now())
    payload = app_payload(ctx, matter, status="added")
    payload.update({
        "added": result.added,
        "already_in_matter": len(result.already),
        "not_added": result.not_added,
        "renamed": result.renamed,
        "skipped": result.skipped,
        "message": result.message(),
        "cancelled": False,
    })
    return payload


def do_add_documents(ctx: Context, matter_path: str) -> dict[str, Any]:
    """Copy files the attorney picks into the matter. Allowed while Claude works (that run won't see them)."""
    matter = resolve_matter(ctx, matter_path)
    picked = pick_files()
    return _added_payload(ctx, matter, None if picked is None else add_files(matter, picked))


def do_add_folder(ctx: Context, matter_path: str) -> dict[str, Any]:
    matter = resolve_matter(ctx, matter_path)
    folder = pick_folder()
    if folder is None:
        return _added_payload(ctx, matter, None)
    payload = _added_payload(ctx, matter, add_folder(ctx, matter, folder))
    payload["source_folder"] = str(folder)
    return payload


def do_open_folder(ctx: Context, matter_path: str) -> dict[str, Any]:
    matter = resolve_matter(ctx, matter_path)
    open_path(matter)
    return {"opened": str(matter)}


OUTPUT_NAMES = {"packet": "packet", "cover_letter": "cover letter", "memo": "memo", "client_request": "client request",
                "filing_checklist": "filing checklist", "paper_packet": "paper part of the filing"}


def do_open_output(ctx: Context, matter_path: str, which: str = "packet", name: str = "") -> dict[str, Any]:
    matter = resolve_matter(ctx, matter_path)
    outputs = outputs_for(matter)
    if which == "form":
        # One filled form from the matter's Forms folder, by its file name.
        form = next((f for f in outputs.get("forms") or [] if f.get("name") == name), None)
        if not form:
            raise UserError(f"{name or 'That form'} isn't in {matter.name}'s files anymore. Open the files folder to see what's there.")
        open_path(Path(form["path"]))
        return {"opened": form["path"]}
    if which == "earlier":
        folder = matter / EARLIER_DIR
        if not folder.is_dir():
            raise UserError(f"{matter.name} has no earlier work set aside.")
        open_path(folder)
        return {"opened": str(folder)}
    if which == "client_request" and name:
        # The client request in another language, by its language.
        copy = next((c for c in outputs["client_request_translations"] if c["language"].casefold() == name.strip().casefold()), None)
        if not copy:
            raise UserError(f"There's no client request in {name} for {matter.name} yet. Claude writes it at the end of the next run.")
        target = copy.get("pdf") or copy["path"]
        open_path(Path(target))
        return {"opened": target}
    if which == "upload_files":
        if not outputs["upload_files"]:
            raise UserError(f"There are no upload files for {matter.name} yet. Claude makes them when the packet is built for online filing.")
        open_path(Path(outputs["upload_files"]["path"]))
        return {"opened": outputs["upload_files"]["path"]}
    if which == "deliverables":
        if not outputs["folder"]:
            raise UserError(f"There are no finished files for {matter.name} yet. They appear after a document review or a build.")
        open_path(Path(outputs["folder"]))
        return {"opened": outputs["folder"]}
    if which not in OUTPUT_NAMES:
        raise UserError("That action isn't available in this version. Restart Claude and try again.")
    out = outputs.get(which)
    if not out:
        if which == "packet":
            raise UserError("There's no packet yet. Build it first.")
        if which == "paper_packet":
            raise UserError(f"{matter.name} has no paper part: every form in it goes online.")
        when = ("during a build" if which == "cover_letter" else "at the end of a build" if which == "filing_checklist"
                else "at the end of a document review or a build")
        raise UserError(f"There's no {OUTPUT_NAMES[which]} for {matter.name} yet. Claude writes it {when}.")
    # The memo and the client request open as their PDF while it's up to date.
    target = out.get("pdf") or out["path"]
    open_path(Path(target))
    return {"opened": target}


WORKING = "Claude is working on this matter. Try again when it finishes."
# What stays with the matter when what is being filed changes (the rest of the workflow folder is set aside).
STAY_WITH_THE_MATTER = (META_FILE.name, EVENTS_FILE.name)


@contextmanager
def nobody_working(ctx: Context, matter: Path) -> Iterator[None]:
    """Hold the matter's lock for a change that can't happen under a running build (CONTRACTS §3): refused while
    anyone holds a fresh run lease. Nothing inside may take the lock again or start the runtime."""
    with matter_lock(matter):
        if lease_is_fresh(read_lease(matter), ctx.now()):
            raise UserError(WORKING)
        yield


def _open_item(matter: Path, item_id: str) -> dict[str, Any]:
    """One item of the open items list as the attorney sees it (their own actions applied)."""
    item_id = (item_id or "").strip()
    if not item_id:
        raise UserError("Choose an item first.")
    state, ledger = ledger_for(matter)
    if state == "missing":
        raise UserError(f"{matter.name} has no list of open items yet. It's written at the end of a document review or a build.")
    if ledger is None:
        raise UserError(f"{matter.name}'s list of open items can't be read. Ask Claude to rewrite it, then try again.")
    item = next(({**it, "status": "open"} for it in ledger["open"] if it["id"] == item_id), None) \
        or next(({**it, "status": "resolved"} for it in ledger["resolved"] if it["id"] == item_id), None)
    if item is None:
        raise UserError("That item isn't on the list anymore. Claude may have rewritten the list since.")
    return item


NO_ITEM_ID = ("This item can't be {what} here: Claude's list didn't give it an id. Ask Claude about this matter to "
              "do it for you, or to rewrite the list.")
ACTION_WORDS = {"resolve": "marked done", "reopen": "reopened", "accept_risk": "accepted"}


def _matched_by_id(matter: Path, item_id: str) -> bool:
    """The item is in Claude's list under this id, so the attorney's action on it applies when the list is read."""
    result = read_open_items(matter)
    return result.ok and any(isinstance(it, dict) and it.get("id") and str(it["id"]) == item_id
                             for it in result.data.get("items") or [])


def _attorney_action(ctx: Context, matter_path: str, action: str, item_id: str, note: str, status: str) -> dict[str, Any]:
    """Mark done, Reopen and Accept this risk go to the attorney's actions file, never into the open items list
    itself: the app and the next run apply them on top of whatever the list says (CONTRACTS §2). Allowed while
    Claude works; the run picks them up."""
    matter = resolve_matter(ctx, matter_path)
    item = _open_item(matter, item_id)
    if not _matched_by_id(matter, item["id"]):
        # An item Claude listed without an id is shown under a stand-in, which the actions file can't match when
        # the list is read again: refused here, so the timeline never says something happened that won't apply.
        raise UserError(NO_ITEM_ID.format(what=ACTION_WORDS[action]))
    wanted = "open" if action == "reopen" else "resolved"
    if item["status"] != wanted:
        said = re.sub(r"\s+", " ", note or "").strip()[:240]
        record_attorney_action(matter, action, item["id"], note=said)
        log(f"attorney action {action} in matter {matter_tag(matter)}")
    return app_payload(ctx, matter, status=status)


def do_resolve_item(ctx: Context, matter_path: str, item_id: str, note: str = "") -> dict[str, Any]:
    """Mark one open item done, and return the matter as it now stands."""
    return _attorney_action(ctx, matter_path, "resolve", item_id, note, "item_resolved")


def do_accept_risk(ctx: Context, matter_path: str, item_id: str, note: str = "") -> dict[str, Any]:
    return _attorney_action(ctx, matter_path, "accept_risk", item_id, note, "risk_accepted")


def do_reopen_item(ctx: Context, matter_path: str, item_id: str) -> dict[str, Any]:
    """Put an item the attorney marked done (or Claude resolved) back on the list."""
    return _attorney_action(ctx, matter_path, "reopen", item_id, "", "item_reopened")


# Files that run something when opened, rather than show a document: a client's file could be one (a download kept
# its name, but a copy loses macOS's "downloaded from the internet" warning). They're shown in Finder instead.
RUNS_WHEN_OPENED = {
    ".command", ".tool", ".sh", ".zsh", ".bash", ".csh", ".app", ".scpt", ".scptd", ".applescript", ".workflow",
    ".terminal", ".pkg", ".mpkg", ".dmg", ".jar", ".py", ".rb", ".pl", ".exe", ".bat", ".cmd", ".webloc", ".inetloc",
    ".fileloc", ".url", ".shortcut", ".action", ".prefpane", ".saver",
}


def reveal_path(path: Path) -> None:
    if platform.system() == "Darwin":
        subprocess.Popen(["open", "-R", str(path)])
    else:
        open_path(path.parent)


def do_open_document(ctx: Context, matter_path: str, rel: str) -> dict[str, Any]:
    matter = resolve_matter(ctx, matter_path)
    target = client_file(matter, rel)
    if target.suffix.lower() in RUNS_WHEN_OPENED:
        reveal_path(target)
        return {"opened": str(target), "revealed": True,
                "message": f"{target.name} could run a program, so it's shown in Finder instead of opened."}
    open_path(target)
    return {"opened": str(target)}


def do_remove_document(ctx: Context, matter_path: str, rel: str) -> dict[str, Any]:
    """Take a document out of the matter. It is kept in the output folder's removed documents, so it can be put back."""
    matter = resolve_matter(ctx, matter_path)
    target = client_file(matter, rel)
    original = target.relative_to(matter).as_posix()
    with nobody_working(ctx, matter):
        kept = free_path(matter / REMOVED_DIR / original)
        kept.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(kept))
        index = removed_index(matter)
        index.append({"original": original, "kept": kept.relative_to(matter).as_posix(), "removed_at": now_iso(ctx)})
        # Every removal stays in the index for as long as its file is kept: an entry dropped from it could never be put back.
        _write_json_atomic(matter / REMOVED_INDEX, {"removed": index})
    # Never by name: a file name often carries the client's name (and in a protected matter can say what the case is).
    # The Documents screen names it, under Removed.
    add_event(matter, "document_removed", "You took out a document.", actor="attorney", now=ctx.now())
    log(f"removed a document from matter {matter_tag(matter)}")
    payload = app_payload(ctx, matter, status="removed")
    payload["removed"] = {"name": target.name, "path": original, "kept": kept.relative_to(matter).as_posix()}
    return payload


def _restore_target(matter: Path, original: str) -> Path:
    """Where a removed document goes back: its old place, which must be one of the client's places in the matter.
    The removed documents' index is a file on disk, so what it says is checked, never trusted."""
    raw = Path(original or "")
    target = (matter / raw).resolve()
    parts = target.relative_to(matter).parts if matter in target.parents else ()
    if raw.is_absolute() or not parts or is_reserved_top(parts[0]) or any(part.startswith(".") for part in parts):
        raise UserError("That document can't go back where it was. Open the matter folder to see what's there.")
    return target


def do_restore_document(ctx: Context, matter_path: str, kept_rel: str) -> dict[str, Any]:
    """Put a removed document back where it was (beside it, numbered, if that name is taken again)."""
    matter = resolve_matter(ctx, matter_path)
    with nobody_working(ctx, matter):
        index = removed_index(matter)
        entry = next((e for e in index if e["kept"] == (kept_rel or "").strip()), None)
        kept = (matter / entry["kept"]).resolve() if entry else None
        if not entry or not kept or not kept.is_file() or (matter / REMOVED_DIR).resolve() not in kept.parents:
            raise UserError("That document isn't in the removed documents anymore. Open the matter folder to see what's there.")
        dest = free_path(_restore_target(matter, entry["original"]))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(kept), str(dest))
        _write_json_atomic(matter / REMOVED_INDEX, {"removed": [e for e in index if e is not entry]})
    add_event(matter, "document_restored", "You put back a document.", actor="attorney", now=ctx.now())
    log(f"put a document back in matter {matter_tag(matter)}")
    payload = app_payload(ctx, matter, status="restored")
    payload["restored"] = {"name": dest.name, "path": dest.relative_to(matter).as_posix()}
    return payload


def do_change_intake(ctx: Context, matter_path: str, matter_type: str, filing_posture: str = "new filing packet", *,
                     protected: bool | None = None, filing_method: str | None = None) -> dict[str, Any]:
    """Change what is being filed. The steps start over for the new case; the client's documents stay. Work already done
    for the old case (the packet, memo, open items and Claude's working files) is set aside in output/earlier, not deleted."""
    matter = resolve_matter(ctx, matter_path)
    t = type_entry(matter_type)
    described = t["matter_type"] if t else re.sub(r"\s+", " ", (matter_type or "")).strip()[:160]
    if len(described) < 3:
        raise UserError("Say what is being filed, for example \"I-485 based on asylee status\".")
    p = posture_entry(filing_posture) or FILING_POSTURES[0]
    method = _filing_method(filing_method)
    tracks = [tr for tr in (track_of(sp) for sp in state_files(matter)) if tr]
    old = (tracks[0] if tracks else {}).get("intake") or {}
    same_case = (" ".join((old.get("matter_type") or "").split()).casefold() == described.casefold()
                 and " ".join((old.get("filing_posture") or "").split()).casefold() == p["value"].casefold())
    if same_case:
        # Only the settings may have changed: then nothing is set aside or started over. New matter and Change what is
        # being filed can mark a matter protected; only the matter's own setting (set_meta) takes protection away.
        meta = read_meta(matter)
        if not ((protected and not meta.get("protected")) or (method and method != meta["filing_method"])):
            raise UserError("That's already what is being filed, so nothing was changed.")
        _refuse_if_working(ctx, matter)
        _apply_intake_settings(matter, None, protected, method, ctx)
        return app_payload(ctx, matter, status="intake_changed") | {"set_aside": ""}
    out = matter / "output"
    movable = [out / "deliverables", out / "working", out / "shareable", out / "workflow"]
    started = any(s["status"] != "pending" for tr in tracks for s in tr.get("stages", []))
    has_work = started or (out / "deliverables").exists()
    set_aside = ""
    with nobody_working(ctx, matter):
        # The attorney's instructions, the matter's settings and its timeline are about the matter, not the old case's
        # work: they stay. Answers, actions on old items and chat changes belong to the old case's work and go with it.
        instructions = read_instructions(matter)
        kept = {name: (matter / WORKFLOW_DIR / name).read_bytes() for name in STAY_WITH_THE_MATTER
                if (matter / WORKFLOW_DIR / name).is_file()}
        if has_work:
            # Named by the time only: a folder name shows in Finder, and in a protected case the old case must not.
            dest = free_path(matter / EARLIER_DIR / f"Set aside {ctx.now().astimezone().strftime('%Y-%m-%d %H.%M')}")
            dest.mkdir(parents=True)
            for src in movable:
                if src.exists():
                    shutil.move(str(src), str(dest / src.name))
            set_aside = dest.relative_to(matter).as_posix()
        else:
            # Nothing has run: the old record is only what creating the matter wrote, so it is replaced outright.
            for state_file in state_files(matter):
                shutil.rmtree(state_file.parent)
        (matter / WORKFLOW_DIR).mkdir(parents=True, exist_ok=True)
        for name, data in kept.items():
            (matter / WORKFLOW_DIR / name).write_bytes(data)
    warning = run_ensure(ctx, matter, described, p["value"])
    _write_instructions(matter, instructions)
    _apply_intake_settings(matter, t, protected, method, ctx)
    add_event(matter, "intake_changed", "You changed what is being filed." + (" The earlier work is kept." if set_aside else ""),
              actor="attorney", now=ctx.now())
    log("changed what is being filed in matter " + matter_tag(matter) + (" (earlier work set aside)" if set_aside else ""))
    payload = app_payload(ctx, matter, status="intake_changed")
    payload["set_aside"] = set_aside
    if warning:
        payload["warning"] = _setup_warning(warning).replace("The matter folder was created, but ", "")
    return payload


def do_mark_filed(ctx: Context, matter_path: str) -> dict[str, Any]:
    matter = resolve_matter(ctx, matter_path)
    with nobody_working(ctx, matter):
        _write_json_atomic(matter / FILED_FILE, {"filed_at": now_iso(ctx)})
    add_event(matter, "filed", "You marked it as filed.", actor="attorney", now=ctx.now())
    return app_payload(ctx, matter, status="filed")


def do_unmark_filed(ctx: Context, matter_path: str) -> dict[str, Any]:
    matter = resolve_matter(ctx, matter_path)
    with nobody_working(ctx, matter):
        try:
            (matter / FILED_FILE).unlink()
        except FileNotFoundError:
            pass
    add_event(matter, "unfiled", "You took back Mark as filed.", actor="attorney", now=ctx.now())
    return app_payload(ctx, matter, status="unfiled")



def _write_instructions(matter: Path, text: str) -> None:
    path = matter / INSTRUCTIONS_FILE
    if not text:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def do_set_instructions(ctx: Context, matter_path: str, text: str) -> dict[str, Any]:
    """Save the attorney's standing instructions for a matter; empty text clears them."""
    matter = resolve_matter(ctx, matter_path)
    clean = (text or "").replace("\r\n", "\n").strip()
    if len(clean) > INSTRUCTIONS_LIMIT:
        raise UserError(f"Instructions can be up to {INSTRUCTIONS_LIMIT:,} characters. Shorten them and save again.")
    _write_instructions(matter, clean)
    add_event(matter, "instructions_saved", "You saved instructions for Claude." if clean else "You cleared the instructions for Claude.",
              actor="attorney", now=ctx.now())
    log(f"{'saved' if clean else 'cleared'} the attorney instructions in matter {matter_tag(matter)}")
    return app_payload(ctx, matter, status="instructions_saved")



def do_save_profile(ctx: Context, profile: dict[str, Any]) -> dict[str, Any]:
    save_profile(ctx, profile)
    return app_payload(ctx, None, status="profile_saved")



# ---------------------------------------------------------------------------
# Runs the app starts: the lease, the brief, and what the timeline says (CONTRACTS §3, §7)
# ---------------------------------------------------------------------------

# Each kind of run the app starts: the lease kind it holds, and what it is doing, as the timeline says it.
RUN_KINDS: dict[str, tuple[str, str]] = {
    "build": ("build", "building the packet"),
    "continue": ("build", "building the packet"),
    "update": ("update", "updating the packet"),
    "review_docs": ("review", "reviewing the documents"),
    "review_again": ("review", "reviewing the documents again"),
    "redo": ("redo", "redoing {stage} and the steps after it"),
    "stress_test": ("officer", "reading the packet as a USCIS officer would"),
    "closeout": ("other", "cleaning up working files"),
}
OUTCOMES = {"done", "stopped", "failed"}
ALREADY_WORKING = "Claude is already working on this matter. This page updates as it goes."


def _doing(kind: str, stage_label: str = "") -> str:
    return RUN_KINDS[kind][1].format(stage=stage_label or "a step")


def _duration_words(minutes: float) -> str:
    if minutes < 1:
        return "under a minute"
    m = int(round(minutes))
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60} min" if m % 60 else f"{m // 60} h"


def do_start_run(ctx: Context, matter_path: str, kind: str, stage_id: str = "", note: str = "") -> dict[str, Any]:
    """Take the matter for a run the app is about to start, and hand back its brief. Refused while anyone else holds
    a fresh lease, so two presses (or the app and a run from the chat) never start two runs on one matter."""
    matter = resolve_matter(ctx, matter_path)
    if kind not in RUN_KINDS:
        raise UserError("That action isn't available in this version. Restart Claude and try again.")
    # A record that can't be read stops here, before the matter is taken: the run couldn't work on it either.
    track = load_track(matter)
    stage_label = ""
    if kind == "redo":
        stage = next((s for s in stages_of(track) if s["id"] == stage_id), None)
        if stage is None:
            raise UserError("Choose the step to redo, then try again.")
        stage_label = stage["label"]
    run_id = new_run_id()
    lease_kind, _ = RUN_KINDS[kind]
    doing = _doing(kind, stage_label)
    ok, lease = acquire_lease(matter, run_id, lease_kind, "app", description=doing[:1].upper() + doing[1:], now=ctx.now())
    if not ok:
        raise UserError(ALREADY_WORKING)
    add_event(matter, "run_started", f"Claude started {doing}.", actor="app", run_id=run_id, run_kind=kind, now=ctx.now())
    log(f"run started ({kind}) in matter {matter_tag(matter)}")
    try:
        brief = prompt_for(ctx, matter, kind, stage_id=stage_id, note=note, run_id=run_id)
    except Exception:
        release_lease(matter, run_id, "failed", now=ctx.now())
        raise
    payload = app_payload(ctx, matter, status="run_started")
    payload.update({"run_id": run_id, "prompt": brief, "lease": lease_view(lease, ctx.now())})
    return payload


def do_heartbeat_run(ctx: Context, matter_path: str, run_id: str) -> dict[str, Any]:
    """The app's agent is still alive: renew its lease. Light, for the 15-second tick: no card."""
    matter = resolve_matter(ctx, matter_path)
    if not (run_id or "").strip():
        raise UserError("That action isn't available in this version. Restart Claude and try again.")
    lease = heartbeat_lease(matter, run_id.strip(), now=ctx.now(), by_app=True)
    return {"status": "heartbeat", "ok": lease is not None, "lease": lease_view(lease or read_lease(matter), ctx.now())}


def do_release_run(ctx: Context, matter_path: str, run_id: str, outcome: str = "done") -> dict[str, Any]:
    """The app's agent ended: release its lease, say so on the timeline, and drop saved answers whose question is
    settled or gone (the run worked them in). A run whose orchestrator already released its own lease ended the way
    it said: that outcome stands, here and on the timeline, whatever the app saw of its agent."""
    matter = resolve_matter(ctx, matter_path)
    run_id = (run_id or "").strip()
    outcome = outcome if outcome in OUTCOMES else "stopped"
    lease = read_lease(matter)
    mine = lease if lease and run_id and lease.get("run_id") == run_id else None
    started = next((e for e in read_events(matter, 1000) if e.get("kind") == "run_started" and e.get("run_id") == run_id), None)
    kind = str((started or {}).get("run_kind") or "")
    started_at = parse_time((mine or {}).get("started_at") if mine else (started or {}).get("at"))
    if mine and mine.get("released_at"):
        if str(mine.get("outcome") or "") in OUTCOMES:
            outcome = str(mine["outcome"])
        if (mine.get("origin") or mine.get("holder")) != "app":
            # A run started (or taken up) from the chat wrote its own finish when it released the lease.
            clear_settled_answers(ctx, matter)
            return app_payload(ctx, matter, status="run_released")
    elif run_id:
        release_lease(matter, run_id, outcome, now=ctx.now())
    minutes = (ctx.now() - started_at).total_seconds() / 60 if started_at else 0.0
    doing = RUN_KINDS[kind][1].format(stage="a step") if kind in RUN_KINDS else "working on this matter"
    took = _duration_words(minutes)
    text = {
        "done": f"Claude finished {doing} in {took}.",
        "stopped": f"Claude stopped {doing} after {took}.",
        "failed": f"Claude ran into a problem {doing}, after {took}.",
    }[outcome]
    add_event(matter, "run_finished", text, actor="app", run_id=run_id, run_kind=kind, outcome=outcome,
              started_at=started_at.isoformat(timespec="seconds") if started_at else "", minutes=int(round(minutes)), now=ctx.now())
    clear_settled_answers(ctx, matter)
    log(f"run finished ({kind or 'unknown'}, {outcome}) in matter {matter_tag(matter)}")
    return app_payload(ctx, matter, status="run_released")


# What the timeline says about a start the app took back, by why it never began.
START_NOT_SENT = "The start waiting in the chat box wasn't sent, so it was taken back."
START_DIDNT_BEGIN = "Claude didn't start after all, so nothing was done."


def do_cancel_start(ctx: Context, matter_path: str, run_id: str, why: str = "") -> dict[str, Any]:
    """The app gives up a start it never saw begin: a request it left in the chat box, unsent after the wait or
    taken back with Cancel, or (``why: "not_started"``) a start that never got going (the agent didn't start, the
    request couldn't go into the chat box). The lease goes only while the app still holds it. When the request was
    sent after all and a run took the lease up, that run keeps the matter (on its own renewals) and nothing is
    written: its orchestrator writes its finish. ``start`` says which: ``cancelled``, ``taken_up`` or ``gone``."""
    matter = resolve_matter(ctx, matter_path)
    run_id = (run_id or "").strip()
    if not run_id:
        raise UserError("That action isn't available in this version. Restart Claude and try again.")
    what = withdraw_start(matter, run_id, now=ctx.now())
    if what == "released":
        started = next((e for e in read_events(matter, 1000) if e.get("kind") == "run_started" and e.get("run_id") == run_id), None)
        kind = str((started or {}).get("run_kind") or "")
        add_event(matter, "run_finished", START_DIDNT_BEGIN if why == "not_started" else START_NOT_SENT, actor="app",
                  run_id=run_id, run_kind=kind, outcome="stopped", started_at=str((started or {}).get("at") or ""),
                  minutes=0, now=ctx.now())
        log(f"run start withdrawn ({kind or 'unknown'}) in matter {matter_tag(matter)}")
    payload = app_payload(ctx, matter, status="start_cancelled")
    payload["start"] = {"released": "cancelled", "taken_up": "taken_up"}.get(what, "gone")
    return payload


NOT_THAT_RUN = "Claude has just started on this matter again, so nothing was changed. This page shows it."


def do_abandon_run(ctx: Context, matter_path: str, run_id: str) -> dict[str, Any]:
    """The attorney says Claude isn't working on this matter anymore, though its lease looks alive: a run started
    outside this app session (from the chat, another window) that ended without letting go, say. Its lease is
    released with outcome ``stopped`` and the timeline says so; were the run still going, its next change is refused
    (its lease has ended) and it stops. Only the run the page showed: one that took the matter since is left alone."""
    matter = resolve_matter(ctx, matter_path)
    run_id = (run_id or "").strip()
    if not run_id:
        raise UserError("That action isn't available in this version. Restart Claude and try again.")
    lease = read_lease(matter)
    if lease and lease.get("run_id") != run_id and lease_is_fresh(lease, ctx.now()):
        raise UserError(NOT_THAT_RUN)
    if release_lease(matter, run_id, "stopped", now=ctx.now()):
        add_event(matter, "run_let_go", "You said Claude wasn't working on this anymore, so the matter was let go.",
                  actor="attorney", run_id=run_id, outcome="stopped", now=ctx.now())
        log(f"a run's lease was let go by the attorney in matter {matter_tag(matter)}")
    return app_payload(ctx, matter, status="run_let_go")


def clear_settled_answers(ctx: Context, matter: Path) -> list[str]:
    """Drop saved answers whose question is no longer open: its item was resolved or is gone. Nothing is dropped
    while the open items list can't be read, since then nothing can be told apart."""
    answers = read_answers(matter)
    if not answers:
        return []
    r = MatterRead(ctx, matter, light=True)
    if r.ledger_state != "ok":
        return []
    still_open = {n["key"] for n in r.needs} | {it["key"] for it in (r.ledger or {}).get("open", [])}
    settled = [key for key in answers if key not in still_open]
    if settled:
        clear_answers(matter, settled)
    return settled


# ---------------------------------------------------------------------------
# Answers and the matter's settings (CONTRACTS §5, §6)
# ---------------------------------------------------------------------------

ANSWER_LIMIT = 4000


def do_save_answer(ctx: Context, matter_path: str, key: str, question: str, answer: str) -> dict[str, Any]:
    """Keep the attorney's answer to one question until a run works it in; an empty answer clears it. Allowed while
    Claude works: the next run picks it up."""
    matter = resolve_matter(ctx, matter_path)
    key = (key or "").strip()
    if not key:
        raise UserError("That question can't take an answer here. Restart Claude and try again.")
    answer = (answer or "").replace("\r\n", "\n").strip()
    if len(answer) > ANSWER_LIMIT:
        raise UserError(f"An answer can be up to {ANSWER_LIMIT:,} characters. Shorten it and save again.")
    save_answer(matter, key[:200], " ".join((question or "").split())[:500], answer, now=ctx.now())
    add_event(matter, "answer_saved", "You saved an answer." if answer else "You cleared an answer.", actor="attorney", now=ctx.now())
    return app_payload(ctx, matter, status="answer_saved")


LANGUAGE_LIMIT = 40


def do_set_meta(ctx: Context, matter_path: str, changes: dict[str, Any]) -> dict[str, Any]:
    """The attorney's settings for the matter: protected (8 U.S.C. 1367), the filing method, the client request's
    language. Allowed while Claude works; each run reads them when it starts."""
    matter = resolve_matter(ctx, matter_path)
    clean: dict[str, Any] = {}
    if "protected" in changes and changes["protected"] is not None:
        clean["protected"] = bool(changes["protected"])
        clean["protected_reason"] = "attorney" if clean["protected"] else ""
    if changes.get("filing_method") not in (None, ""):
        if changes["filing_method"] not in FILING_METHODS:
            raise UserError("Choose paper or online for how this will be filed.")
        clean["filing_method"] = changes["filing_method"]
    if changes.get("client_language") not in (None, ""):
        language = " ".join(str(changes["client_language"]).split())
        if not language or len(language) > LANGUAGE_LIMIT or not re.fullmatch(r"[^\W\d_][\w '()-]*", language):
            raise UserError("Name the language in a word or two, for example Spanish.")
        clean["client_language"] = language
    if not clean:
        return app_payload(ctx, matter, status="meta_saved")
    update_meta(matter, now=ctx.now(), **clean)
    return app_payload(ctx, matter, status="meta_saved")


def _refuse_if_working(ctx: Context, matter: Path) -> None:
    if lease_is_fresh(read_lease(matter), ctx.now()):
        raise UserError(WORKING)


def do_archive(ctx: Context, matter_path: str, archived: bool = True) -> dict[str, Any]:
    """Hide a matter from the main list (it shows under Archived), or bring it back. Not while Claude works on it."""
    matter = resolve_matter(ctx, matter_path)
    _refuse_if_working(ctx, matter)
    update_meta(matter, now=ctx.now(), archived_at=now_iso(ctx) if archived else "")
    return app_payload(ctx, matter, status="archived" if archived else "unarchived")

"""Adding the client's documents: the Mac's file and folder pickers, and copying what was chosen into the matter.

Copies only, never moves: the attorney's originals stay where they were. What can't be a document is left out and
said by name (a Pages file to export as a PDF, a Finder alias), a file already in the matter isn't copied twice
(so adding a folder again, or again after a failure partway, adds only what's missing), and a client folder named
like Claude's own output folder is renamed on arrival instead of disappearing into it.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .common import UserError
from .context import Context
from .folders import PROGRAM_DIRS, SKIP_FILES, HashCache, is_reserved_top, walk_files
from .logs import log

AUTOMATION_DENIED = ("Allow Claude to open the file picker: System Settings › Privacy & Security › Automation › Claude › "
                     "turn on System Events, then try again.")
PICKER_ONLY_ON_MAC = ("Choosing files from a picker works only on a Mac. Copy the client's files into the matter folder "
                      "instead (Open the matter folder).")
# The pickers wait this long for the attorney; the subprocess waits a little longer, so the script's own timeout
# (error -1712) is what ends a picker left open, and it ends with a sentence. Both end well before the app gives up on
# the whole request (10 minutes, hooks/server.ts), so the app hears that sentence rather than a timeout of its own.
PICKER_SECONDS = 540
PICKER_GRACE_SECONDS = 15
PICKER_TIMED_OUT = f"The {{what}} picker was open for {PICKER_SECONDS // 60} minutes and closed. Open it again when you're ready."
# A dialog that System Events shows stays open when the script stops waiting for it; System Events quitting closes
# it (it starts again by itself the next time anything asks for it).
DISMISS_PICKER = 'tell application "System Events" to quit'

# Mac documents that are folders on disk, or zipped bundles: Claude can't read them, but a PDF of them it can.
EXPORT_SUFFIXES = {".pages", ".numbers", ".key", ".rtfd"}
# Bundles that are programs or libraries, never a client's document.
BUNDLE_SUFFIXES = {".app", ".bundle", ".framework", ".plugin", ".kext", ".photoslibrary", ".musiclibrary", ".fcpbundle"}
# What a Finder alias file starts with (bookmark data).
ALIAS_MAGIC = b"book\x00\x00\x00\x00mark\x00\x00\x00\x00"
# A source folder's top-level output/ that holds an earlier run's work (of this or another workflow), not documents.
GENERATED_MARKERS = {"working", "vault", "deliverables", "shareable", "workflow", "security", "privacy"}

WHY_EXPORT = "Export it as a PDF and add that."
WHY_ALIAS = "It's a Finder alias, not the document. Add the original file."
WHY_PROGRAM = "It's an app or a program file, not a document."
WHY_UNREADABLE = "Immigration Packet Builder couldn't read it. Check that it isn't locked or still downloading, then add it again."


def _picker_failed(stderr: str, what: str) -> UserError:
    log(f"{what} picker failed: error {_apple_error(stderr) or 'unknown'}")
    if "-1743" in stderr or "not authorized" in stderr.lower() or "not allowed to send" in stderr.lower():
        return UserError(AUTOMATION_DENIED)
    if "-1712" in stderr:
        return UserError(PICKER_TIMED_OUT.format(what=what))
    return UserError(f"The {what} picker didn't open. Try again; if it still doesn't appear, look behind the Claude window.")


def _apple_error(stderr: str) -> str:
    import re

    m = re.search(r"\((-\d+)\)", stderr or "")
    return m.group(1) if m else ""


def _picker_script(choose: str) -> str:
    """The picker, asked of System Events after activating it so it opens in front of Claude. Left open past
    PICKER_SECONDS it is closed (System Events quits), and the script ends with the timeout's error."""
    return (
        "try\n"
        f"with timeout of {PICKER_SECONDS} seconds\n"
        'tell application "System Events"\n'
        "activate\n"
        f"{choose}\n"
        "end tell\n"
        "end timeout\n"
        "on error errText number errNumber\n"
        f"if errNumber is -1712 then {DISMISS_PICKER}\n"
        "error errText number errNumber\n"
        "end try\n"
    )


def dismiss_picker() -> None:
    """Close a picker left open (the script stopped waiting, or was stopped). Never fails the request."""
    try:
        subprocess.run(["osascript", "-e", DISMISS_PICKER], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


def _run_picker(script: str, what: str) -> subprocess.CompletedProcess[str] | None:
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True,
                           timeout=PICKER_SECONDS + PICKER_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        dismiss_picker()
        raise UserError(PICKER_TIMED_OUT.format(what=what)) from None
    if r.returncode != 0:
        if "-128" in r.stderr or "cancel" in r.stderr.lower():
            return None
        raise _picker_failed(r.stderr, what)
    return r


def pick_files() -> list[Path] | None:
    """Open the system file picker. Returns None when the user cancels."""
    hook = os.environ.get("SENIOR_ASSOCIATE_PICKER_FILES")
    if hook:
        return [Path(p) for p in hook.split(os.pathsep) if p]
    if platform.system() != "Darwin":
        raise UserError(PICKER_ONLY_ON_MAC)
    script = _picker_script(
        'set fs to choose file with prompt "Choose the client\'s documents (Claude adds copies; your originals stay put)" with multiple selections allowed'
    ) + (
        'set out to ""\n'
        "repeat with f in fs\n"
        "set out to out & POSIX path of f & linefeed\n"
        "end repeat\n"
        "return out"
    )
    r = _run_picker(script, "file")
    if r is None:
        return None
    return [Path(line.strip()) for line in r.stdout.splitlines() if line.strip()]


def pick_folder() -> Path | None:
    """Open the system folder picker. Returns None when the user cancels."""
    hook = os.environ.get("SENIOR_ASSOCIATE_PICKER_FOLDER")
    if hook:
        return Path(hook)
    if platform.system() != "Darwin":
        raise UserError(PICKER_ONLY_ON_MAC)
    script = _picker_script(
        'set f to choose folder with prompt "Choose the folder that holds this client\'s documents (Claude adds a copy)"'
    ) + "return POSIX path of f"
    r = _run_picker(script, "folder")
    if r is None:
        return None
    chosen = r.stdout.strip()
    return Path(chosen) if chosen else None


@dataclass
class AddResult:
    """What adding did: the files copied (paths in the matter), how many were already there, what was left out and
    why, the subfolders skipped as an earlier run's work, and client folders renamed on arrival."""

    added: list[str] = field(default_factory=list)
    already: list[str] = field(default_factory=list)
    not_added: list[dict[str, str]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    renamed: list[dict[str, str]] = field(default_factory=list)

    def message(self) -> str:
        """One plain sentence or three for the page: what was added, what was already there, what wasn't added."""
        parts = []
        n = len(self.added)
        parts.append("No files added." if n == 0 else f"Added {n} file{'s' if n != 1 else ''}.")
        if self.already:
            k = len(self.already)
            parts.append(f"{k} {'was' if k == 1 else 'were'} already in the matter.")
        for entry in self.not_added[:5]:
            parts.append(f"Not added: {entry['name']}. {entry['why']}")
        if len(self.not_added) > 5:
            parts.append(f"{len(self.not_added) - 5} more weren't added.")
        for entry in self.renamed:
            parts.append(f"The client's {entry['from']} folder is now {entry['to']}, so it isn't mixed with Claude's work.")
        return " ".join(parts)


def _is_alias(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(len(ALIAS_MAGIC)) == ALIAS_MAGIC
    except OSError:
        return False


def _why_not(path: Path) -> str:
    """Why a chosen file or package can't be added as a document, or "" when it can."""
    suffix = path.suffix.lower()
    if suffix in EXPORT_SUFFIXES:
        return WHY_EXPORT
    if suffix in BUNDLE_SUFFIXES:
        return WHY_PROGRAM
    if path.is_file() and _is_alias(path):
        return WHY_ALIAS
    return ""


class _Matter:
    """The matter's client documents by size and hash, so a byte-identical file is found without reading them all."""

    def __init__(self, matter: Path) -> None:
        self.matter = matter
        self.cache = HashCache(matter)
        self.by_size: dict[int, list[str]] = {}
        for p in walk_files(matter):
            try:
                self.by_size.setdefault(p.stat().st_size, []).append(p.relative_to(matter).as_posix())
            except OSError:
                continue

    def has_copy_of(self, src: Path) -> bool:
        try:
            size = src.stat().st_size
        except OSError:
            return False
        same_size = self.by_size.get(size)
        if not same_size:
            return False
        from .folders import sha256

        digest = sha256(src)
        return bool(digest) and any(self.cache.sha(rel) == digest for rel in same_size)

    def added(self, dest: Path) -> None:
        try:
            self.by_size.setdefault(dest.stat().st_size, []).append(dest.relative_to(self.matter).as_posix())
        except OSError:
            pass

    def save(self) -> None:
        self.cache.save({rel for rels in self.by_size.values() for rel in rels})


def _free_dest(dest: Path) -> Path:
    n = 2
    free = dest
    while free.exists():
        free = dest.with_name(f"{dest.stem} ({n}){dest.suffix}")
        n += 1
    return free


def _copy_one(src: Path, dest: Path, into: _Matter, result: AddResult, shown_name: str) -> None:
    why = _why_not(src)
    if why:
        result.not_added.append({"name": shown_name, "why": why})
        return
    if into.has_copy_of(src):
        result.already.append(shown_name)
        return
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest = _free_dest(dest)
        shutil.copy2(src, dest)
    except OSError as exc:
        log(f"a file couldn't be added: {type(exc).__name__} errno {getattr(exc, 'errno', '')}")
        result.not_added.append({"name": shown_name, "why": WHY_UNREADABLE})
        return
    into.added(dest)
    result.added.append(dest.relative_to(into.matter).as_posix())


def add_files(matter: Path, sources: list[Path]) -> AddResult:
    """Copy chosen files into the matter folder's top level."""
    result = AddResult()
    into = _Matter(matter)
    for src in sources:
        name = src.name
        if name in SKIP_FILES or name.startswith("."):
            continue
        if not src.exists():
            result.not_added.append({"name": name, "why": "It isn't there anymore. It may have been moved."})
            continue
        if src.is_dir():
            why = _why_not(src) or "It's a folder. Use Add a folder… for a whole folder."
            result.not_added.append({"name": name, "why": why})
            continue
        _copy_one(src, matter / name, into, result, name)
    into.save()
    return result


def folder_problem(ctx: Context, matter: Path, folder: Path) -> str | None:
    """Why this folder can't be added to the matter, or None when it can."""
    m, f = matter.resolve(), folder.resolve()
    root = ctx.matters_root.resolve()
    if f == m or m in f.parents:
        return "That folder is this matter itself. Choose the client's own document folder."
    if f in m.parents or f == root or f in root.parents:
        return (f"That folder ({f.name}) contains your matters folder, so it holds other clients' files too. "
                "Choose just this client's folder.")
    if root in f.parents:
        return f"That folder is inside another matter ({f.relative_to(root).parts[0]}). Choose the client's own folder."
    if f == Path.home().resolve() or f == Path(f.anchor) or f == ctx.plugin_root or ctx.plugin_root in f.parents:
        return "That looks like a home or system folder, not a client's folder. Choose the folder that holds just this client's documents."
    return None


def _looks_generated(folder: Path) -> bool:
    """A top-level output/ holding an earlier run's work (Immigration Packet Builder's or another workflow's)."""
    try:
        return any(child.is_dir() and child.name.casefold() in GENERATED_MARKERS for child in folder.iterdir())
    except OSError:
        return False


def _client_name(matter: Path, name: str) -> str:
    """A free name for a client folder called like one of Claude's: "Output" becomes "Output (client)"."""
    candidate = f"{name} (client)"
    n = 2
    while (matter / candidate).exists() and not (matter / candidate).is_dir():
        candidate = f"{name} (client {n})"
        n += 1
    return candidate


def folder_files(ctx: Context, folder: Path) -> tuple[list[tuple[Path, str]], list[str], list[dict[str, str]]]:
    """The files Add folder would copy, each with its path in the matter-to-be; the top-level subfolders it skips
    as an earlier run's work; and what it leaves out by name (packages to export, programs). Stops as soon as the
    folder is clearly too big to be one client's documents, before reading the rest of it."""
    files: list[tuple[Path, str]] = []
    skipped: set[str] = set()
    left_out: list[dict[str, str]] = []
    total = 0
    for dirpath, dirnames, filenames in os.walk(folder):
        here = Path(dirpath)
        at_top = here == folder
        keep = []
        for d in sorted(dirnames):
            if d.startswith(".") or d.casefold() in PROGRAM_DIRS:
                continue
            path = here / d
            why = _why_not(path)
            if why:
                left_out.append({"name": d, "why": why})
                continue
            if at_top and d.casefold() == "output" and _looks_generated(path):
                skipped.add(d)
                continue
            keep.append(d)
        dirnames[:] = keep
        for name in sorted(filenames):
            if name in SKIP_FILES or name.startswith((".", "~$")):
                continue
            src = here / name
            if not src.is_file():
                continue
            files.append((src, src.relative_to(folder).as_posix()))
            try:
                total += src.stat().st_size
            except OSError:
                pass
            if len(files) > ctx.max_folder_files or total > ctx.max_folder_bytes:
                raise UserError(
                    f"{folder.name} has more than {ctx.max_folder_files:,} files or {ctx.max_folder_bytes // 1024**3} GB, far more "
                    "than one client's documents. Choose the client's own folder, or add files one at a time."
                )
    return files, sorted(skipped), left_out


def add_folder(ctx: Context, matter: Path, folder: Path) -> AddResult:
    """Copy the folder's files into the matter, keeping its subfolders. Everything is checked before the first file
    is copied, so a refused folder leaves the matter untouched."""
    if not folder.is_dir():
        raise UserError("That isn't a folder. Choose a folder of the client's documents.")
    problem = folder_problem(ctx, matter, folder)
    if problem:
        raise UserError(problem)
    files, skipped, left_out = folder_files(ctx, folder)
    result = AddResult(skipped=skipped, not_added=left_out)
    into = _Matter(matter)
    renamed: dict[str, str] = {}
    for src, rel in files:
        parts = rel.split("/")
        if len(parts) > 1 and is_reserved_top(parts[0]):
            # The client's own folder named like Claude's output or scratch folder: renamed, never merged into it.
            if parts[0] not in renamed:
                renamed[parts[0]] = _client_name(matter, parts[0])
                result.renamed.append({"from": parts[0], "to": renamed[parts[0]]})
            parts[0] = renamed[parts[0]]
        _copy_one(src, matter.joinpath(*parts), into, result, src.name)
    into.save()
    return result

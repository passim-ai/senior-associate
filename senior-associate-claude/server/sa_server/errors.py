"""Errors the attorney reads: one plain sentence or two for whatever went wrong, never a raw error."""
from __future__ import annotations

import errno
import subprocess
from pathlib import Path

from scripts.matter_state import LockTimeout

from .common import MATTERS_FOLDER_HOWTO, UserError, show_path
from .context import Context

GENERIC_ERROR = "That didn't work, and Immigration Packet Builder couldn't tell why. Try again; if it keeps happening, restart Claude."
BUSY = "This matter is busy: Claude is saving something in it right now. Try again in a moment."


def _inside_matters(root: Path, path: Path) -> bool:
    try:
        p = path.expanduser().resolve()
    except (OSError, RuntimeError):
        return False
    return p == root or root in p.parents or p in root.parents


def friendly_error(exc: BaseException, ctx: Context) -> str:
    """One plain sentence or two for whatever went wrong: what happened and what to do. Never a raw error."""
    if isinstance(exc, UserError):
        return str(exc)
    if isinstance(exc, LockTimeout):
        # Another step (or Claude in the chat) is writing the matter's records this moment.
        return BUSY
    if isinstance(exc, subprocess.TimeoutExpired):
        return "That took too long and was stopped. Try again."
    if isinstance(exc, PermissionError):
        target = Path(exc.filename) if exc.filename else None
        if target is None or _inside_matters(ctx.matters_root, target):
            return f"Immigration Packet Builder can't save in {show_path(ctx.matters_root)}. {MATTERS_FOLDER_HOWTO}"
        return (f"macOS didn't let Immigration Packet Builder open {target.name}. Check that it isn't locked or in a protected "
                "folder, or copy it to your Desktop first, then try again.")
    if isinstance(exc, OSError):
        name = Path(exc.filename).name if getattr(exc, "filename", None) else ""
        if exc.errno == errno.ENOSPC:
            return "Your Mac is out of disk space. Free some space, then try again."
        if exc.errno == errno.ENOENT:
            return (f"Immigration Packet Builder couldn't find {name or 'a file it needed'}. It may have been moved or renamed in "
                    "Finder. Try again.")
        if exc.errno == errno.EROFS:
            return "That folder can't be changed (it's on a read-only disk). Choose a folder on your Mac instead."
        if exc.errno in (errno.ENAMETOOLONG,):
            return "A file name is too long for macOS. Shorten it in Finder, then try again."
        return f"Immigration Packet Builder couldn't read or save {name or 'a file'} ({(exc.strerror or 'a file problem').lower()}). Try again."
    return GENERIC_ERROR

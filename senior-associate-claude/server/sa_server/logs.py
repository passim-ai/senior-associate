"""The server's own log: stderr for the host, plus a file so activity can be checked from outside the host.

Nothing in it identifies a client. A matter appears only as a short tag (a hash of its folder's path), never its name
or a path; an error appears as its type and number, never its message (which can carry a path); and as a last guard,
anything shaped like a path is taken out before a line is written. So the log needs no purge when a matter is cleaned
up or deleted. It rotates at 1 MB, keeping three old files.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
from datetime import datetime
from pathlib import Path

MAX_BYTES = 1024 * 1024
KEEP = 3


def _log_file() -> Path:
    # Tests point this at a temporary folder, so a test run never writes to the attorney's real log.
    override = os.environ.get("SENIOR_ASSOCIATE_LOG_FILE", "").strip()
    return Path(override).expanduser() if override else Path.home() / "Library" / "Logs" / "SeniorAssociate" / "server.log"


LOG_FILE = _log_file()

# A path: absolute, home-relative, or quoted with a slash in it; and a URL's query string, which can carry a name.
_PATH_RE = re.compile(r"""(?:'[^']*/[^']*'|"[^"]*/[^"]*"|~/\S+|(?<![\w:])/(?:Users|private|var|Volumes|tmp|home|opt)/\S+|\?\S+)""")


def scrub(text: str) -> str:
    return _PATH_RE.sub("<path>", text)


def matter_tag(matter: Path) -> str:
    """A short, stable tag for a matter in the log: never its name or its path."""
    return hashlib.sha256(str(matter).encode("utf-8")).hexdigest()[:8]


def describe_error(exc: BaseException) -> str:
    """An error as the log keeps it: its type, and its number for a system error. Never its message."""
    number = getattr(exc, "errno", None)
    return f"{type(exc).__name__}" + (f" errno {number}" if isinstance(number, int) else "")


def _rotate(path: Path) -> None:
    try:
        if path.stat().st_size < MAX_BYTES:
            return
    except OSError:
        return
    for i in range(KEEP, 0, -1):
        older = path.with_name(f"{path.name}.{i}")
        newer = path.with_name(f"{path.name}.{i - 1}") if i > 1 else path
        try:
            if newer.exists():
                os.replace(newer, older)
        except OSError:
            return


def log(msg: str) -> None:
    msg = scrub(msg)
    line = f"[senior-associate] {msg}"
    print(line, file=sys.stderr, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _rotate(LOG_FILE)
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now().isoformat(timespec='seconds')} pid={os.getpid()} {msg}\n")
    except OSError:
        pass

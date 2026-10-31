"""Small helpers every module uses: the error the attorney reads, times, and reading files that may be missing."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .context import Context


class UserError(ValueError):
    """A problem the attorney can act on, already worded as a plain sentence for the screen."""


def show_path(path: Path) -> str:
    """A path as the attorney would recognize it: the home folder as ~."""
    try:
        rel = path.resolve().relative_to(Path.home().resolve()).as_posix()
    except ValueError:
        return str(path)
    return "~" if rel == "." else f"~/{rel}"


def read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def read_text(path: Path, limit: int = 40000) -> str:
    try:
        return path.read_text(encoding="utf-8")[:limit]
    except (OSError, UnicodeDecodeError):
        return ""


def plugin_version(ctx: Context) -> str:
    data = read_json(ctx.plugin_json)
    return str(data.get("version") or "") if isinstance(data, dict) else ""


def now_iso(ctx: Context | None = None) -> str:
    current = ctx.now() if ctx else datetime.now(tz=timezone.utc)
    return current.astimezone(timezone.utc).isoformat(timespec="seconds")


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def mtime_iso(path: Path) -> str:
    try:
        return iso(path.stat().st_mtime)
    except OSError:
        return ""


def write_json_atomic(path: Path, data: Any) -> None:
    from scripts.matter_state import write_json_atomic as _write

    _write(path, data)


# Claude changes plugin options for the attorney (the setup skill), so every message about another Matters folder
# carries the request that has Claude do it. The app shows it as a button.
MATTERS_FOLDER_ASK = "Change my Senior Associate Matters folder."
MATTERS_FOLDER_HOWTO = "Claude can set up a different Matters folder for you."


def as_text(value: Any) -> str:
    """An agent-written field as text, whatever shape it came in: a list becomes "a, b"; None becomes ""."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return ", ".join(as_text(v) for v in value if v not in (None, ""))
    if isinstance(value, dict):
        return ""
    return str(value)


def as_word(value: Any) -> str:
    """An agent-written code ("high", "attorney") as one lowercase word; a list counts as its first entry."""
    if isinstance(value, (list, tuple)):
        value = next((v for v in value if isinstance(v, str) and v.strip()), "")
    return as_text(value).strip().lower()

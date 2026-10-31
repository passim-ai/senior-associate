#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Turns automatic updates for Immigration Packet Builder's marketplace on or off, or reports them.

Claude reads a marketplace's autoUpdate only from its entry in the user's settings.json, so that's the one place this
writes. Everything else in the file is left as it was.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

MARKETPLACE = "document-automation"
REPO = "passim-ai/senior-associate"


def settings_path() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(base).expanduser() / "settings.json"


class SettingsProblem(Exception):
    """settings.json can't be read or changed safely; the message says so in plain words."""


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SettingsProblem(f"Claude's settings file couldn't be read ({exc.strerror or exc}). Nothing was changed.") from exc
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise SettingsProblem(
            f"Claude's settings file ({path}) has a mistake in it at line {getattr(exc, 'lineno', '?')}, so it wasn't "
            "changed. Fix or remove that line, or ask Claude to repair the file, then try again."
        ) from exc
    if not isinstance(data, dict):
        raise SettingsProblem(f"Claude's settings file ({path}) isn't in the form Claude expects, so it wasn't changed.")
    return data


def save(path: Path, data: dict) -> None:
    """Write the whole file to a temporary file beside it, then swap it in: a crash leaves the old file or the new one,
    never half of one. Keeps the file's permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings.", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv: list[str]) -> int:
    want = argv[1] if len(argv) > 1 else "status"
    if want not in {"on", "off", "status"}:
        print("Usage: auto_update.py on|off|status", file=sys.stderr)
        return 2
    path = settings_path()
    try:
        data = load(path)
    except SettingsProblem as exc:
        print(str(exc), file=sys.stderr)
        return 1
    known = data.get("extraKnownMarketplaces")
    entry = known.get(MARKETPLACE) if isinstance(known, dict) else None
    if want == "status":
        on = isinstance(entry, dict) and entry.get("autoUpdate") is True
        print(f"Automatic updates are {'on' if on else 'off'}.")
        return 0
    if not isinstance(known, dict):
        known = data["extraKnownMarketplaces"] = {}
    if not isinstance(entry, dict):
        entry = known[MARKETPLACE] = {"source": {"source": "github", "repo": REPO}}
    entry["autoUpdate"] = want == "on"
    try:
        save(path, data)
    except OSError as exc:
        print(f"Claude's settings file couldn't be saved ({exc.strerror or exc}). Nothing was changed.", file=sys.stderr)
        return 1
    print(f"Automatic updates are {want}. They take effect the next time Claude starts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

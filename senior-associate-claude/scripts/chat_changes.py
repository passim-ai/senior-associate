#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The changes an attorney made to a matter's work by talking with Claude in chat.

    uv run --script chat_changes.py record MATTER --what "Cover letter: leads with the joint lease" [--file REL ...]
    uv run --script chat_changes.py list MATTER

The app shows the changes made since Claude last finished a step, and the next Update the packet re-checks the
packet with them. The log sits with the workflow state, where client facts may be kept.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.matter_access import NotAMatterFolder, require_matter_folder
from scripts.matter_state import LockTimeout, matter_lock, write_json_atomic

LOG = Path("output") / "working" / "workflow" / "chat-changes.json"
WHAT_LIMIT = 200


def read_log(matter: Path) -> list[dict[str, object]]:
    try:
        data = json.loads((matter / LOG).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    changes = data.get("changes") if isinstance(data, dict) else None
    return [c for c in changes or [] if isinstance(c, dict) and isinstance(c.get("what"), str)]


def record(matter: Path, what: str, files: list[str]) -> dict[str, object]:
    what = " ".join(what.split())
    if not what:
        raise ValueError("Say what changed, in a few plain words.")
    entry: dict[str, object] = {
        "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "what": what[:WHAT_LIMIT],
        "files": [str(Path(f)) for f in files if f.strip()],
    }
    # Under the matter's lock, so two changes recorded at once (or the app reading as one is written) never lose
    # one; the write is atomic, so a reader sees the old list or the new one.
    with matter_lock(matter):
        changes = read_log(matter) + [entry]
        write_json_atomic(matter / LOG, {"changes": changes})
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description="Record or list the changes made to a matter in chat.")
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record", help="Record one change.")
    rec.add_argument("matter", type=Path)
    rec.add_argument("--what", required=True, help="What changed, as the attorney will read it on screen. No file paths.")
    rec.add_argument("--file", action="append", default=[], help="A changed file, relative to the matter folder. Repeatable.")
    ls = sub.add_parser("list", help="List every recorded change.")
    ls.add_argument("matter", type=Path)
    args = parser.parse_args()
    try:
        matter = require_matter_folder(args.matter)
        if args.command == "record":
            entry = record(matter, args.what, args.file)
            print(f"Recorded at {entry['at']}: {entry['what']}")
        else:
            for c in read_log(matter):
                print(f"{c.get('at', '')}  {c['what']}")
    except (NotAMatterFolder, ValueError, LockTimeout) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

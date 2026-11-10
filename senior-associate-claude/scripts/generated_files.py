"""Keep what a person changed in a generated file.

A rebuild never overwrites a deliverable somebody edited (a letter revised in Word, a packet marked up in Preview):
the edited copy is moved into "Your edited copies" beside it first, and the rebuild goes on. A file with no receipt
was written before receipts existed, or was renamed since; it is taken as generated, as it always was.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime
from pathlib import Path

# Beside the generated files, in the folder the attorney opens: never read as a deliverable, never part of an approval.
KEPT_DIR = "Your edited copies"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _written(receipt: Path) -> dict[str, str]:
    try:
        previous = json.loads(receipt.read_text())
    except (OSError, ValueError):
        return {}
    return previous if isinstance(previous, dict) else {}


def edited(paths: list[Path], receipt: Path) -> list[Path]:
    """The files changed since they were generated. One the receipt doesn't name isn't counted."""
    previous = _written(receipt)
    return [path for path in paths if path.is_file() and path.name in previous and previous[path.name] != file_hash(path)]


def set_aside(path: Path, *, now: datetime | None = None) -> Path:
    """Move a file into "Your edited copies" beside it, under a name that says when. Returns where it went."""
    stamp = (now or datetime.now()).strftime("%Y-%m-%d %H%M")
    folder = path.parent / KEPT_DIR
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{path.stem} ({stamp}){path.suffix}"
    n = 2
    while target.exists():
        target = folder / f"{path.stem} ({stamp}, {n}){path.suffix}"
        n += 1
    path.replace(target)
    return target


def preserve_edits(paths: list[Path], receipt: Path, *, now: datetime | None = None) -> list[Path]:
    """Before generated files are rewritten: set each edited one aside. Returns where they went."""
    return [set_aside(path, now=now) for path in edited(paths, receipt)]


def kept_notice(kept: list[Path]) -> str:
    """What a tool says after setting edited copies aside: the step adds one open item so the attorney hears of it."""
    if not kept:
        return ""
    names = ", ".join(f"{KEPT_DIR}/{path.name}" for path in kept)
    return (f"Kept the attorney's edited {'copy' if len(kept) == 1 else 'copies'} ({names}) and wrote a new one from "
            "the source. Add one attorney_action open item naming the kept file, so the attorney can say which edits "
            "to carry over; never fold them in by guessing.")


def record_generated(paths: list[Path], receipt: Path) -> None:
    from scripts.matter_state import write_json_atomic
    write_json_atomic(receipt, {p.name: file_hash(p) for p in paths})

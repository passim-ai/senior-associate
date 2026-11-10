"""Keep what a person changed in a generated file.

A rebuild never overwrites a deliverable somebody edited (a letter revised in Word, a packet marked up in Preview):
the edited copy is moved into "Your edited copies" beside it first, and the rebuild goes on. A file the receipt
doesn't name (written before receipts were kept, or the receipt is gone or damaged) may hold edits nobody can see
from here, so it is kept the same way, under a name that says it is an earlier copy.
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
    """The files the receipt shows were changed since they were generated."""
    previous = _written(receipt)
    return [path for path in paths if path.is_file() and path.name in previous and previous[path.name] != file_hash(path)]


def unvouched(paths: list[Path], receipt: Path) -> list[Path]:
    """The files already there that the receipt doesn't name: nobody can say whether a person changed them."""
    previous = _written(receipt)
    return [path for path in paths if path.is_file() and path.name not in previous]


# In a kept file's name when the receipt couldn't say whether it was edited.
EARLIER = "earlier copy, "


def set_aside(path: Path, *, now: datetime | None = None, earlier: bool = False) -> Path:
    """Move a file into "Your edited copies" beside it, under a name that says when. Returns where it went."""
    stamp = (EARLIER if earlier else "") + (now or datetime.now()).strftime("%Y-%m-%d %H%M")
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
    """Before generated files are rewritten: set aside each one a person changed, and each one already there that
    the receipt can't vouch for. Returns where they went."""
    changed, unknown = edited(paths, receipt), unvouched(paths, receipt)
    return [set_aside(path, now=now) for path in changed] + [set_aside(path, now=now, earlier=True) for path in unknown]


def kept_notice(kept: list[Path]) -> str:
    """What a tool says after setting copies aside: the step adds one open item so the attorney hears of it."""
    if not kept:
        return ""
    changed = [path for path in kept if f"({EARLIER}" not in path.name]
    unknown = [path for path in kept if f"({EARLIER}" in path.name]
    names = lambda paths: ", ".join(f"{KEPT_DIR}/{path.name}" for path in paths)  # noqa: E731
    said = []
    if changed:
        said.append(f"Kept the attorney's edited {'copy' if len(changed) == 1 else 'copies'} ({names(changed)}) and "
                    "wrote a new one from the source. Add one attorney_action open item naming the kept file, so the "
                    "attorney can say which edits to carry over; never fold them in by guessing.")
    if unknown:
        said.append(f"Kept the {'copy' if len(unknown) == 1 else 'copies'} made before this version kept track of "
                    f"edits ({names(unknown)}) and wrote a new one from the source. Add one attorney_action open "
                    "item, not needed before filing, naming the kept file and asking whether the attorney had "
                    "changed it; if they had, they say which edits to carry over.")
    return " ".join(said)


def record_generated(paths: list[Path], receipt: Path) -> None:
    from scripts.matter_state import write_json_atomic
    write_json_atomic(receipt, {p.name: file_hash(p) for p in paths})

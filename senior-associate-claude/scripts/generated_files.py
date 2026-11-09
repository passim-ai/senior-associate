"""Preserve human edits to generated files. No overwrite override is offered."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_generated(paths: list[Path], receipt: Path) -> None:
    try:
        previous = json.loads(receipt.read_text())
    except (OSError, ValueError):
        previous = {}
    if not isinstance(previous, dict):
        previous = {}
    for path in paths:
        if path.exists() and previous.get(path.name) != file_hash(path):
            raise ValueError(f"{path.name} was edited outside the renderer or has no generation receipt. "
                             "Preserve it and reconcile the edits with the source, then render to a new output name.")


def record_generated(paths: list[Path], receipt: Path) -> None:
    from scripts.matter_state import write_json_atomic
    write_json_atomic(receipt, {p.name: file_hash(p) for p in paths})

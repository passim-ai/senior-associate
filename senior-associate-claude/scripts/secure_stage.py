#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
from datetime import UTC, datetime
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.matter_access import (
    AccessDeniedError,
    NotAMatterFolder,
    assert_role_access,
    ensure_policy,
    log_access_event,
    require_matter_folder,
)
from scripts.matter_protection import is_protected_matter
from scripts.matter_state import now_iso, sha256_file, sign_of_life


# Folders whose names start with "." are skipped too (should_skip).
IGNORED_DIRS = {"__pycache__", "node_modules"}
IGNORED_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
# Inside output/, nothing goes into a workspace by default: the stages read earlier stages' work at its matter
# path, and copying it is what let plans point at temporary copies. Never these, even when asked by name: what the
# attorney took out of the matter, earlier work set aside after a change of case, and other workspaces.
NEVER_INCLUDE_PREFIXES = (
    "output/removed documents/",
    "output/earlier/",
    "output/security/",
    "output/privacy/",
)
# A workspace this large means something other than one client's documents is in the folder. Refuse rather than
# copy part of it: a stage that silently misses documents reviews the wrong record.
MAX_WORKSPACE_FILES = 1500


class SecureStageError(RuntimeError):
    pass


def safe_slug(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned[:80] or "stage"


def should_skip(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    if path.name.startswith((".", "~$")) or path.name in IGNORED_NAMES:
        return True
    parts = set(relative.parts)
    return bool(parts & IGNORED_DIRS) or any(part.startswith(".") for part in relative.parts[:-1])


def is_client_document(relative_path: Path) -> bool:
    """The client's documents are everything outside output/ (the matter contract's layout)."""
    return bool(relative_path.parts) and relative_path.parts[0] != "output"


def never_included(relative_path: Path) -> bool:
    lower_value = relative_path.as_posix().casefold() + ("/" if relative_path.parts else "")
    return any(lower_value.startswith(prefix) for prefix in NEVER_INCLUDE_PREFIXES)


def collect_stage_files(
    matter_root: Path,
    *,
    stage_id: str,
    includes: list[str] | None = None,
    max_files: int | None = None,
) -> tuple[list[Path], list[str]]:
    """Every client document, plus any working file the orchestrator names with --include. Nothing is capped:
    when the total passes the limit, the workspace is refused with the count and the reason."""
    matter_root = matter_root.resolve()
    selected: dict[Path, None] = {}
    excluded: list[str] = []

    for path in sorted(matter_root.rglob("*")):
        if not path.is_file() or should_skip(path, matter_root):
            continue
        relative = path.relative_to(matter_root)
        if is_client_document(relative):
            selected[path] = None
        else:
            excluded.append(relative.as_posix())

    for raw in includes or []:
        path = (matter_root / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
        try:
            relative = path.relative_to(matter_root)
        except ValueError:
            raise SecureStageError(f"--include {raw} is outside the matter folder; a workspace holds only this matter's files.")
        if never_included(relative):
            raise SecureStageError(
                f"--include {raw} is in a folder no stage reads (removed documents, set-aside earlier work, "
                "or security and privacy records)."
            )
        if not path.exists():
            raise SecureStageError(f"--include {raw} doesn't exist in the matter folder.")
        children = sorted(path.rglob("*")) if path.is_dir() else [path]
        for child in children:
            if child.is_file() and not should_skip(child, matter_root) and not never_included(child.relative_to(matter_root)):
                selected[child] = None
                relative_child = child.relative_to(matter_root).as_posix()
                if relative_child in excluded:
                    excluded.remove(relative_child)

    limit = max_files or MAX_WORKSPACE_FILES
    if len(selected) > limit:
        client_count = sum(1 for path in selected if is_client_document(path.relative_to(matter_root)))
        raise SecureStageError(
            f"This workspace would hold {len(selected)} files ({client_count} of them outside output/), more than the "
            f"{limit} a stage workspace allows, so it wasn't created; a partial copy would hide documents from the stage. "
            "Check that the matter folder holds only this client's documents (a folder of other clients' files, or a "
            "whole archive, may have been added), or pass --max-files to allow more."
        )
    return list(selected), excluded


def workspace_root(matter_root: Path, stage_id: str) -> Path:
    # A random suffix keeps two workspaces made in the same second (a quick retry, stages side by side) apart.
    token = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return (
        matter_root / "output" / "security" / "stage-workspaces"
        / f"{safe_slug(stage_id)}-{token}-{secrets.token_hex(3)}"
    )


def link_or_copy_file(source: Path, destination: Path, *, copy_files: bool) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if copy_files:
        shutil.copy2(source, destination)
    else:
        os.symlink(source, destination)


def create_stage_workspace(
    matter_root: Path,
    *,
    stage_id: str,
    role: str,
    includes: list[str] | None = None,
    privacy_mode: str = "standard",
    copy_files: bool = True,
    max_files: int | None = None,
) -> dict[str, Any]:
    try:
        matter_root = require_matter_folder(matter_root)
    except NotAMatterFolder as exc:
        raise SecureStageError(str(exc)) from exc
    sign_of_life(matter_root)  # making a workspace is a sign the run is alive

    ensure_policy(matter_root, privacy_mode=privacy_mode)
    # Check the role before anything is written, so a refusal leaves no half-made workspace behind.
    try:
        assert_role_access(matter_root, role=role, data_planes=["agent_context"])
    except AccessDeniedError as exc:
        raise SecureStageError(f"{exc} Use the stage id as the role, e.g. --role {stage_id}.") from exc
    files, excluded = collect_stage_files(
        matter_root,
        stage_id=stage_id,
        includes=includes,
        max_files=max_files,
    )
    root = workspace_root(matter_root, stage_id)
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    linked_files: list[dict[str, Any]] = []

    for source in files:
        relative = source.resolve().relative_to(matter_root)
        destination = root / "files" / relative
        link_or_copy_file(source, destination, copy_files=copy_files)
        digest = sha256_file(source)
        linked_files.append(
            {
                # The original, so a tool that read the copy records the document itself: its absolute path, its
                # path relative to the matter folder (what plans, manifests and findings record), and its hash.
                "original_path": str(source.resolve()),
                "relative_path": relative.as_posix(),
                "workspace_path": str(destination),
                "original_sha256": digest,
                "mode": "copy" if copy_files else "symlink",
                "size_bytes": source.stat().st_size,
            }
        )

    manifest = {
        "schema_version": 2,
        "generated_at": now_iso(precise=True),
        "matter_root": str(matter_root),
        "stage_id": stage_id,
        "role": role,
        "privacy_mode": privacy_mode,
        "protected_matter": is_protected_matter(matter_root),
        "copy_files": copy_files,
        "workspace_root": str(root),
        "files_root": str(root / "files"),
        "file_count": len(linked_files),
        "files": linked_files,
        "excluded_count": len(excluded),
        "excluded": excluded[:200],
        "notes": [
            "files/ holds a copy of every client document, at the same path it has in the matter folder.",
            "Read earlier stages' work at its matter path; it isn't copied here.",
            "Never write a workspace path into a plan, manifest, or findings file: use the path relative to the matter "
            "folder (relative_path above). Closeout deletes this workspace.",
        ],
    }
    manifest_path = root / "stage manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    os.chmod(manifest_path, 0o600)

    log_access_event(
        matter_root,
        event_type="stage_workspace_created",
        role=role,
        actor="system",
        data_planes=["audit_metadata", "agent_context"],
        artifacts=[str(manifest_path)],
        notes=f"stage_id={stage_id}; file_count={len(linked_files)}; copy_files={copy_files}",
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create stage-scoped Immigration Packet Builder workspaces.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("matter_root", type=Path)
    create_parser.add_argument("--stage-id", required=True)
    create_parser.add_argument("--role", required=True)
    create_parser.add_argument("--privacy-mode", default="standard")
    create_parser.add_argument("--include", action="append", default=[])
    create_parser.add_argument(
        "--symlink-files",
        action="store_true",
        help="Use symlinks instead of copying files into the stage workspace. Not recommended for live matters.",
    )
    create_parser.add_argument("--allow-unprotected", action="store_true", help="Accepted for older briefs; does nothing.")
    create_parser.add_argument(
        "--max-files",
        type=int,
        help=f"Allow a workspace larger than {MAX_WORKSPACE_FILES} files. Nothing is ever cut: past the limit, create refuses.",
    )
    create_parser.add_argument("--json", action="store_true", help="Print a short JSON result: the workspace, its manifest, and the file count.")
    create_parser.add_argument("--full", action="store_true", help="Print the whole manifest, every file included, as JSON.")
    return parser


def short_result(payload: dict[str, Any]) -> dict[str, Any]:
    """What a caller needs; the full file list stays in the workspace's stage manifest.json."""
    root = Path(payload["workspace_root"])
    return {
        "stage_id": payload["stage_id"],
        "role": payload["role"],
        "workspace_root": str(root),
        "files_dir": str(root / "files"),
        "manifest": str(root / "stage manifest.json"),
        "file_count": payload["file_count"],
        "excluded_count": payload["excluded_count"],
    }


def main() -> int:
    args = build_parser().parse_args()
    try:
        payload = create_stage_workspace(
            args.matter_root,
            stage_id=args.stage_id,
            role=args.role,
            includes=args.include,
            privacy_mode=args.privacy_mode,
            copy_files=not args.symlink_files,
            max_files=args.max_files,
        )
    except SecureStageError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.full:
        print(json.dumps(payload, indent=2))
    elif args.json:
        print(json.dumps(short_result(payload), indent=2))
    else:
        print(payload["workspace_root"])
        print(payload["file_count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

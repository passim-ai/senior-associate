#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
from typing import Any


MATTER_TARGETS = (
    ("pdf_tmp", Path("output/pdf/tmp")),
    ("doc_tmp", Path("output/doc/tmp")),
    ("image_tmp", Path("output/images/tmp")),
    ("source_xfa", Path("output/forms/.source_xfa")),
    ("editable_xfa", Path("output/forms/editable_xfa")),
    ("working_pdf_tmp", Path("output/working/pdf/tmp")),
    ("working_doc_tmp", Path("output/working/doc/tmp")),
    ("working_image_tmp", Path("output/working/images/tmp")),
    ("working_source_xfa", Path("output/working/forms/.source_xfa")),
    ("working_editable_xfa", Path("output/working/forms/editable_xfa")),
    ("stage_workspaces", Path("output/security/stage-workspaces")),
    ("tool_tmp", Path("output/security/tool-tmp")),
    # Where a stage writes scratch that holds client facts (helper JSON, page text it pulled to compare): kept with
    # the matter rather than in /tmp, and deleted here.
    ("vault_scratch", Path("output/working/vault/scratch")),
    ("working_tmp", Path("output/working/tmp")),
    ("output_tmp", Path("output/tmp")),
    ("playwright_output", Path("output/playwright")),
)

VAULT_PREFIXES = ("output/working/vault/", "output/vault/")
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".ppm", ".pgm", ".pbm", ".tif", ".tiff", ".bmp", ".gif", ".webp"})
# Folders a stage fills with page renders, OCR text, or copies to compare: "render-check", "renders/docs",
# "exemplar-renders", "source-ocr", "visual-check", "scratch".
CLUTTER_DIR = re.compile(
    r"^(?:scratch|tmp|temp|converted|previews?|thumbnails?|page[-_ ]?images?|"
    r"render\w*(?:[-_ ].*)?|.*[-_ ]renders?|(?:\w+[-_ ])?ocr(?:[-_ ].*)?|(?:render|visual|page|layout|pdf)[-_ ]checks?)$",
    re.IGNORECASE,
)


def is_render_clutter(relative_path: str) -> bool:
    """A file a stage left in the vault while checking its work: a page image anywhere in the vault, or anything in
    a render, OCR, or scratch folder. Closeout deletes these; the stage's memos, findings and plans stay."""
    normalized = relative_path.replace("\\", "/")
    lower_value = normalized.casefold()
    prefix = next((p for p in VAULT_PREFIXES if lower_value.startswith(p)), None)
    if prefix is None:
        return False
    parts = normalized[len(prefix):].split("/")
    if Path(parts[-1]).suffix.casefold() in IMAGE_SUFFIXES:
        return True
    return any(CLUTTER_DIR.match(part) for part in parts[1:-1])


def vault_clutter(matter_path: Path) -> list[Path]:
    """Every render, OCR text and scratch file in the matter's vault (both layouts)."""
    found: list[Path] = []
    for prefix in VAULT_PREFIXES:
        root = matter_path / prefix
        if not root.is_dir():
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                path = Path(dirpath) / name
                if is_render_clutter(path.relative_to(matter_path).as_posix()):
                    found.append(path)
    return sorted(found)


def delete_vault_clutter(matter_path: Path) -> dict[str, Any]:
    """Delete the vault's render clutter, then the folders it leaves empty. Returns a count, not file names."""
    files = vault_clutter(matter_path)
    total_bytes = 0
    folders: set[Path] = set()
    for path in files:
        try:
            total_bytes += path.stat().st_size
            path.unlink()
        except OSError:
            continue
        folders.add(path.parent)
    for folder in sorted(folders, key=lambda p: len(p.parts), reverse=True):
        current = folder
        while current != matter_path and any(str(current).startswith(str(matter_path / p)) for p in VAULT_PREFIXES):
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent
    return {"type": "vault_renders", "file_count": len(files), "total_bytes": total_bytes}


def summarize_path(target_type: str, root: Path, path: Path) -> dict[str, Any]:
    file_count = 0
    total_bytes = 0
    if path.is_dir():
        for child in path.rglob("*"):
            if child.is_file():
                file_count += 1
                total_bytes += child.stat().st_size
    elif path.is_file():
        file_count = 1
        total_bytes = path.stat().st_size
    return {
        "type": target_type,
        "root": str(root.resolve()),
        "path": str(path.resolve()),
        "relative_path": str(path.resolve().relative_to(root.resolve())),
        "exists": path.exists(),
        "file_count": file_count,
        "total_bytes": total_bytes,
    }


def delete_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()

"""Keep clean filing sources separate from visibly marked review copies.

Every packet Claude assembles is kept twice: the review copy in the deliverables folder, with a DRAFT band above
each page, and the clean source it was stamped from, in the working folder. Approving a version copies the clean
sources out. A review copy the attorney renames, marks up or removes never blocks that: the clean source is what
is filed, and it alone has to be intact.
"""
from __future__ import annotations
import io
import os
from datetime import datetime
from pathlib import Path
import shutil
import tempfile

from scripts.matter_state import read_json, write_json_atomic, sha256_file

RELEASE_MANIFEST = Path("output/working/filing-source/release.json")
APPROVED_DIR = Path("output/deliverables/Approved for filing")
DELIVERABLES = "output/deliverables/"
FILING_SOURCE = "output/working/filing-source/"

# The only reasons a version can't be approved, as the attorney reads them.
NOT_ASSEMBLED = "There's no assembled packet to approve yet. Build the packet first."
SOURCE_CHANGED = ("The clean copy of the packet is missing or was changed. Press Update the packet so Claude "
                  "assembles it again.")
RECORD_DAMAGED = ("The record of the assembled packet can't be read. Press Update the packet so Claude assembles "
                  "it again.")


def stamp_review_copy(source: Path, destination: Path) -> None:
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen.canvas import Canvas
    writer = PdfWriter(clone_from=str(source))
    for page in writer.pages:
        page.transfer_rotation_to_content()
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        # Add a band outside the original content; never overlay an answer or barcode.
        page.mediabox.upper_right = (width, height + 20)
        page.cropbox.upper_right = (width, height + 20)
        layer = io.BytesIO()
        canvas = Canvas(layer, pagesize=(width, height + 20))
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawCentredString(width / 2, height + 6, "DRAFT — ATTORNEY REVIEW REQUIRED")
        canvas.save()
        page.merge_page(PdfReader(layer).pages[0])
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".review-", suffix=".pdf", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            writer.write(stream)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _recorded(matter: Path) -> dict[str, dict]:
    """The release record's entries, by review copy; {} when there is none. Raises when it can't be read."""
    if not (matter / RELEASE_MANIFEST).exists():
        return {}
    record = read_json(matter / RELEASE_MANIFEST)
    entries = record.data.get("entries") if record.ok and isinstance(record.data, dict) else None
    if not isinstance(entries, dict):
        raise ValueError(RECORD_DAMAGED)
    for relative, entry in entries.items():
        if (not isinstance(relative, str) or not isinstance(entry, dict) or not isinstance(entry.get("source"), str)
                or not relative.startswith(DELIVERABLES) or not entry["source"].startswith(FILING_SOURCE)):
            raise ValueError(RECORD_DAMAGED)
    return entries


def _review_copies(matter: Path, taken: set[str]) -> dict[str, str]:
    """PDFs in the deliverables folder that no entry names, by their contents: where a renamed review copy is found."""
    found: dict[str, str] = {}
    root = matter / DELIVERABLES
    if not root.is_dir():
        return found
    for path in sorted(root.rglob("*.pdf")):
        relative = path.relative_to(matter).as_posix()
        if relative in taken or relative.startswith(APPROVED_DIR.as_posix() + "/") or path.name.startswith(".") or path.is_symlink():
            continue
        try:
            found.setdefault(sha256_file(path), relative)
        except OSError:
            continue
    return found


def release_sources(matter: Path) -> dict[str, dict]:
    """The packets that can be approved now: each review copy in the deliverables folder, with its clean source.

    A review copy renamed since it was assembled (the handoff drops "(DRAFT)" from its name once nothing blocks
    filing) is found by its contents. One that is gone (an earlier packet, replaced) is left out. Raises when there
    is nothing to approve, or when a clean source is missing, changed or outside the matter."""
    entries = _recorded(matter)
    current: dict[str, dict] = {}
    elsewhere: dict[str, str] | None = None
    root = matter.resolve()
    for relative, entry in entries.items():
        if not (matter / relative).is_file():
            if elsewhere is None:
                elsewhere = _review_copies(matter, set(entries))
            moved = elsewhere.get(str(entry.get("draft_sha256") or ""))
            if moved is None:
                continue
            relative = moved
        source = matter / entry["source"]
        try:
            source.resolve().relative_to(root)
            intact = not source.is_symlink() and sha256_file(source) == entry.get("clean_sha256")
        except (OSError, ValueError):
            intact = False
        if not intact:
            raise ValueError(SOURCE_CHANGED)
        current[relative] = entry
    if not current:
        raise ValueError(NOT_ASSEMBLED)
    return current


def keep_review_copy(matter: Path, packet: Path) -> None:
    """Called only on the newly assembled file, after all compression and splitting."""
    relative = packet.resolve().relative_to(matter.resolve()).as_posix()
    clean = matter / FILING_SOURCE / Path(relative).relative_to(DELIVERABLES)
    try:
        entries = _recorded(matter)
    except ValueError:
        entries = {}  # a record that can't be read is written again from what is assembled now
    old = entries.get(relative)
    if clean.exists() and (not old or sha256_file(clean) != old.get("clean_sha256")):
        # Not the source this record wrote: kept under another name, never overwritten.
        stamp = datetime.now().strftime("%Y-%m-%d %H%M%S")
        clean.replace(clean.with_name(f"{clean.stem} (set aside {stamp}){clean.suffix}"))
    clean.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(packet, clean)
    stamp_review_copy(clean, packet)
    entries[relative] = {"source": clean.relative_to(matter).as_posix(), "clean_sha256": sha256_file(clean),
                         "draft_sha256": sha256_file(packet)}
    # A packet that is gone (assembled under another name before, then removed) leaves the record.
    entries = {name: entry for name, entry in entries.items() if (matter / name).is_file()}
    write_json_atomic(matter / RELEASE_MANIFEST, {"schema_version": 1, "entries": entries})


def export_approved(matter: Path, version: str) -> Path:
    """Copy the clean sources into Approved for filing, by version. A copy already there is left as it is: the
    attorney may have signed or completed it."""
    entries = release_sources(matter)
    destination = matter / APPROVED_DIR / version[:16]

    def approved_path(relative: str) -> Path:
        parts = Path(relative).relative_to(DELIVERABLES).parts
        return destination.joinpath(*(part.replace(" (DRAFT)", "") for part in parts))

    for relative, entry in entries.items():
        target = approved_path(relative)
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(matter / entry["source"], target)
        # An online filing's upload files go with the map that says where each belongs in the USCIS account.
        upload_map = (matter / relative).parent / "Upload map.md"
        if upload_map.is_file() and not (target.parent / upload_map.name).exists():
            shutil.copy2(upload_map, target.parent / upload_map.name)
    return destination


def prune_upload_entries(matter: Path, folder: Path, current: list[Path]) -> None:
    """Retire obsolete split exports from the current manifest; preserve their clean bytes on disk."""
    record = read_json(matter / RELEASE_MANIFEST)
    if not record.ok or not isinstance(record.data, dict):
        return
    prefix = folder.relative_to(matter).as_posix() + "/"
    keep = {path.relative_to(matter).as_posix() for path in current}
    entries = {name: entry for name, entry in record.data.get("entries", {}).items()
               if not name.startswith(prefix) or name in keep}
    write_json_atomic(matter / RELEASE_MANIFEST, {"schema_version": 1, "entries": entries})

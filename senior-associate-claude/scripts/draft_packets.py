"""Keep clean filing sources separate from visibly marked review copies."""
from __future__ import annotations
import io
import os
from pathlib import Path
import shutil
import tempfile

from scripts.matter_state import read_json, write_json_atomic, sha256_file

RELEASE_MANIFEST = Path("output/working/filing-source/release.json")
APPROVED_DIR = Path("output/deliverables/Approved for filing")


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


def keep_review_copy(matter: Path, packet: Path) -> None:
    """Called only on the newly assembled file, after all compression and splitting."""
    relative = packet.resolve().relative_to(matter.resolve()).as_posix()
    clean = matter / "output/working/filing-source" / Path(relative).relative_to("output/deliverables")
    record = read_json(matter / RELEASE_MANIFEST)
    entries = record.data.get("entries", {}) if record.ok and isinstance(record.data, dict) else {}
    old = entries.get(relative)
    if clean.exists() and (not old or sha256_file(clean) != old.get("clean_sha256")):
        raise ValueError("A clean filing source was edited outside assembly. Preserve and reconcile it before rebuilding.")
    clean.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(packet, clean)
    stamp_review_copy(clean, packet)
    entries[relative] = {"source": clean.relative_to(matter).as_posix(), "clean_sha256": sha256_file(clean),
                         "draft_sha256": sha256_file(packet)}
    write_json_atomic(matter / RELEASE_MANIFEST, {"schema_version": 1, "entries": entries})


def release_sources(matter: Path) -> dict[str, dict]:
    record = read_json(matter / RELEASE_MANIFEST)
    entries = record.data.get("entries") if record.ok and isinstance(record.data, dict) else None
    if not isinstance(entries, dict) or not entries:
        raise ValueError("Reassemble the packet to create marked review copies and clean filing sources.")
    for relative, entry in entries.items():
        if not isinstance(relative, str) or not isinstance(entry, dict) or not isinstance(entry.get("source"), str):
            raise ValueError("The packet release record is damaged.")
        for key, target in (("draft_sha256", relative), ("clean_sha256", entry.get("source", ""))):
            path = matter / target
            try:
                path.resolve().relative_to(matter.resolve())
                if path.is_symlink() or sha256_file(path) != entry.get(key):
                    raise ValueError("A review packet or filing source changed after assembly. Rebuild and review it.")
            except (OSError, ValueError) as exc:
                raise ValueError("A review packet or filing source is missing, changed, or outside this matter.") from exc
        if not relative.startswith("output/deliverables/") or not entry["source"].startswith("output/working/filing-source/"):
            raise ValueError("Invalid packet release destination.")
    return entries


def export_approved(matter: Path, version: str) -> Path:
    entries = release_sources(matter)
    destination = matter / APPROVED_DIR / version[:16]
    # Versioned exports preserve older releases. Never overwrite a changed export.
    for relative, entry in entries.items():
        name = Path(relative).relative_to("output/deliverables")
        name = name.with_name(name.name.replace(" (DRAFT)", ""))
        target = destination / name
        if target.exists() and sha256_file(target) != entry["clean_sha256"]:
            raise ValueError("An approved export was edited. Preserve it before exporting this version again.")
    for relative, entry in entries.items():
        name = Path(relative).relative_to("output/deliverables")
        name = name.with_name(name.name.replace(" (DRAFT)", ""))
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(matter / entry["source"], target)
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

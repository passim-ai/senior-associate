#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pypdf[crypto]>=5.0",
#   "reportlab>=4.0",
#   "pillow>=10.0",
#   "pillow-heif>=0.16; sys_platform == 'darwin' or (sys_platform == 'linux' and (platform_machine == 'x86_64' or platform_machine == 'aarch64')) or (sys_platform == 'win32' and platform_machine == 'AMD64')",
# ]
# ///
"""Assemble a USCIS filing packet PDF from an ordered plan.

    uv run --script assemble_packet.py PLAN.json [--output PACKET.pdf] [--manifest MANIFEST.json]
        [--no-stamps] [--max-mb N] [--split-max-mb [N]] [--split-dir DIR] [--table]

Item kinds: pdf, image, docx, separator, placeholder, index (see README.md). Writes the
merged packet with one bookmark per item (exhibits nested under their section), an
exhibit stamp and packet page number on each page, and a manifest JSON recording where
every item landed and which source file (matter-relative path and sha256) it came from.
Source files are only read. Stdout is a short summary (paths, page count, exhibits,
placeholder labels, warnings); the page map is in the manifest, and --table also prints it.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

sys.dont_write_bytecode = True  # never leave __pycache__ inside the plugin folder
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.matter_state import sign_of_life  # noqa: E402
import filing_channels  # noqa: E402
from _packet_common import (  # noqa: E402
    ToolError,
    find_soffice,
    page_ranges,
    register_serif_fonts,
    run_cli,
    soffice_convert_to_pdf,
    unsupported_chars,
)


logging.getLogger("pypdf").setLevel(logging.ERROR)

KINDS = ("pdf", "image", "docx", "separator", "placeholder", "index")
COMMON_KEYS = {"kind", "label", "description", "section", "bookmark", "role"}
# What an item is in the filing. Forms, payment forms and the cover letter are never stamped or
# resampled: a filing copy is often flattened (no form fields left to recognize it by), and a
# USCIS form's own footer and barcode sit in the margin a stamp would use.
ROLES = ("cover_letter", "form", "payment", "exhibit", "other")
UNTOUCHED_ROLES = ("cover_letter", "form", "payment")
FORM_NUMBER_RE = re.compile(r"^(?:form\s+)?[GIN]-\d{2,4}[A-Z]?\b", re.IGNORECASE)
KIND_KEYS = {
    "pdf": {"path", "paths", "pages"},
    "docx": {"path", "pages"},
    "image": {"path", "paths", "orientation", "captions"},
    "separator": set(),
    "placeholder": {"note"},
    "index": {"title"},
}
TOP_KEYS = {"output", "manifest", "title", "base_dir", "items", "notes", "filing_method", "stamps"}
LETTER_PT = (612.0, 792.0)
IMAGE_MARGIN_PT = 36.0
MAX_IMAGE_DPI = 300
# Below this printed size (inches, on both sides) a photo is too small to read; warn.
SMALL_IMAGE_IN = 2.0
# USCIS online filing: "Files must not be larger than 12MB." (uscis.gov/online-filing-options,
# updated 10/07/2026, checked 2026-10-29).
ONLINE_UPLOAD_MAX_MB = 12
# --max-mb tries these image resolutions in turn (the first is the normal build).
COMPRESSION_STEPS = (300, 150, 100)
PAYMENT_FORM_RE = re.compile(r"\bG-?\s?(1450|1650|1651)\b", re.IGNORECASE)
PREPARED_PAYMENT_RE = re.compile(r"\bG-?\s?(1450|1650)\b", re.IGNORECASE)  # the ones the forms step prepares
ENOTICE_FORM_RE = re.compile(r"\bG-?\s?1145\b", re.IGNORECASE)
COVER_LETTER_RE = re.compile(r"\bcover\s+letter\b", re.IGNORECASE)
WORKSPACES_DIR = ("security", "stage-workspaces")
# The forms step's record of every filing copy it prepared, one per forms folder of the matter.
FORMS_MANIFEST_GLOB = "output/working/vault/forms/*/form intent manifest.json"
PAYMENT_KINDS = ("g-1450", "g-1650")  # a payment form the forms step prepares, one per fee
ENOTICE_KIND = "g-1145"
FEE_KEYS = ("pays_for", "pays_what", "pays_amount", "fee_order")
# The top of a paper packet, in order: each payment form (in the fees tool's order), the G-1145, the cover letter.
FRONT_RANK = {"payment": 0, "g-1145": 1, "cover_letter": 2}


@dataclass
class Item:
    index: int  # 1-based position in the plan
    kind: str
    label: str | None
    description: str | None
    section: str | None
    bookmark: str | None
    note: str | None
    raw: dict
    sources: list[dict] = field(default_factory=list)  # {"path", "pages", "source_page_count", "sha256", ...}
    # filled while loading / building
    readers: list = field(default_factory=list)  # (PdfReader, [page indices]) per source
    orientation: str = "auto"
    captions: list[str] | None = None
    has_form_fields: bool = False
    role: str = "other"
    # What the forms step's manifest says this filing copy is ("g-1450", "g-1145", "i-130"), and for a
    # payment form the fee it pays (pays_for, pays_what, pays_amount, fee_order); None when it isn't listed.
    prepared_kind: str | None = None
    fee: dict = field(default_factory=dict)
    image_downsampled: list[bool] = field(default_factory=list)  # per image file, in the last build
    file_pages: list[int] = field(default_factory=list)  # pages placed per source, in order
    start: int = 0  # 0-based first packet page
    count: int = 0
    bookmark_title: str = ""
    bookmark_level: int = 0
    stamped: bool = False

    @property
    def where(self) -> str:
        tag = f"item {self.index} ({self.kind}"
        if self.label:
            tag += f", {self.label}"
        return tag + ")"


# ---------------------------------------------------------------------------
# Matter folder and stage workspaces
# ---------------------------------------------------------------------------
def find_matter_root(*paths: Path) -> Path | None:
    """The matter folder: the parent of the nearest enclosing `output/` folder of any path given."""
    for path in paths:
        for parent in [path, *path.parents]:
            if parent.name == "output" and parent.parent != parent:
                return parent.parent
    return None


def _workspace_of(path: Path) -> Path | None:
    """The stage workspace folder (output/security/stage-workspaces/<name>) holding path, if any."""
    parts = path.parts
    for i in range(1, len(parts) - 1):
        if (parts[i - 1], parts[i]) == WORKSPACES_DIR:
            return Path(*parts[: i + 2])
    return None


def _sha256(path: Path) -> str:
    with path.open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def map_workspace_copy(path: Path, where: str, warnings: list[str]) -> Path:
    """Return the matter's original for a stage-workspace copy (or path itself when it isn't a copy).

    A stage workspace holds temporary copies that are deleted when working files are cleaned
    up, so the packet reads, and the manifest records, the original. The workspace's
    `stage manifest.json` (scripts/secure_stage.py) maps each copy to its original and its hash;
    without it, the copy's place under `files/` is its place in the matter folder.
    """
    ws = _workspace_of(path)
    if ws is None:
        return path
    # The copy's place under files/ is the original's place in the matter folder
    # (<matter>/output/security/stage-workspaces/<ws>/files/...), also when the matter folder moved since.
    files = ws / "files"
    original = (ws.parents[3] / path.relative_to(files)).resolve() if path.is_relative_to(files) else None
    expected_hash = None
    try:
        entries = json.loads((ws / "stage manifest.json").read_text(encoding="utf-8")).get("files") or []
    except (OSError, ValueError, AttributeError):
        entries = []
    for entry in entries:
        rel = entry.get("relative_path") if isinstance(entry, dict) else None
        if rel and (files / rel).resolve() == path:
            if entry.get("original_path") and Path(entry["original_path"]).is_file():
                original = Path(entry["original_path"]).resolve()
            expected_hash = entry.get("original_sha256")
            break
    if original is None or not original.is_file():
        raise ToolError(
            f"{where}: {path.name} is a temporary copy of a client document, and its original "
            f"{'(' + str(original) + ') ' if original else ''}is no longer in the matter folder. "
            "Point the plan at the document in the matter folder itself."
        )
    if expected_hash and _sha256(original) != expected_hash:
        warnings.append(
            f"{where}: {original.name} changed after the working copy was made; the packet uses the current original."
        )
    return original


def _relative(path: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            pass
    return str(path)


# ---------------------------------------------------------------------------
# Plan loading and validation
# ---------------------------------------------------------------------------
def load_plan(plan_path: Path) -> tuple[dict, list[Item], Path, list[str]]:
    if not plan_path.is_file():
        raise ToolError(f"Plan file not found: {plan_path}")
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ToolError(f"Plan {plan_path} is not valid JSON (line {exc.lineno}, column {exc.colno}: {exc.msg}).") from None
    if isinstance(plan, list):
        plan = {"items": plan}
    if not isinstance(plan, dict) or not isinstance(plan.get("items"), list) or not plan["items"]:
        raise ToolError('The plan must be a JSON object with a non-empty "items" list.')
    warnings: list[str] = []
    for key in plan:
        if key not in TOP_KEYS:
            warnings.append(f"Unknown top-level plan key {key!r} was ignored (known: {', '.join(sorted(TOP_KEYS))}).")
    base = plan_path.parent
    if plan.get("base_dir"):
        base = _resolve(str(plan["base_dir"]), plan_path.parent)
        if not base.is_dir():
            raise ToolError(f'"base_dir" {base} is not a folder.')
    if _workspace_of(base) is not None:
        raise ToolError(
            "The plan points at a temporary copy of the matter's files, which is deleted when working files are "
            'cleaned up. Set "base_dir" to the matter folder itself and give each path relative to it.'
        )
    notes = plan.get("notes", [])
    if isinstance(notes, str):
        notes = [notes]
    if not isinstance(notes, list) or not all(isinstance(n, str) for n in notes):
        raise ToolError('"notes" must be a list of one-line strings (fees, photos and other physical filing items).')
    plan["notes"] = [" ".join(n.split()) for n in notes if n.strip()]
    method = str(plan.get("filing_method") or "paper").strip().lower()
    if method not in ("paper", "online"):
        raise ToolError(f'"filing_method" must be "paper" or "online" (got {plan.get("filing_method")!r}).')
    plan["filing_method"] = method
    if not isinstance(plan.get("stamps", True), bool):
        raise ToolError('"stamps" must be true or false.')

    errors: list[str] = []
    items: list[Item] = []
    for n, raw in enumerate(plan["items"], start=1):
        if not isinstance(raw, dict):
            errors.append(f"item {n}: must be a JSON object, got {type(raw).__name__}.")
            continue
        kind = str(raw.get("kind", "")).strip().lower()
        if kind not in KINDS:
            errors.append(f'item {n}: "kind" must be one of {", ".join(KINDS)} (got {raw.get("kind")!r}).')
            continue
        allowed = COMMON_KEYS | KIND_KEYS[kind]
        for key in raw:
            if key not in allowed:
                hint = ' (did you mean "pages"?)' if key in ("page", "page_range", "range") else ""
                warnings.append(f"item {n} ({kind}): unknown key {key!r} was ignored{hint}.")

        def text(key: str) -> str | None:
            value = raw.get(key)
            if value is None:
                return None
            value = " ".join(str(value).split())
            return value or None

        item = Item(
            index=n, kind=kind, label=text("label"), description=text("description"),
            section=text("section"), bookmark=text("bookmark"), note=text("note"), raw=raw,
        )
        if kind in ("pdf", "image", "docx"):
            paths = raw.get("paths") if kind != "docx" else None
            if raw.get("path") and paths:
                errors.append(f'{item.where}: give either "path" or "paths", not both.')
                continue
            if paths is not None and (not isinstance(paths, list) or not paths):
                errors.append(f'{item.where}: "paths" must be a non-empty list of file paths.')
                continue
            path_list = [raw["path"]] if raw.get("path") else (paths or [])
            if not path_list:
                errors.append(f'{item.where}: needs "path" (the source file).')
                continue
            if kind == "pdf" and len(path_list) > 1 and raw.get("pages") not in (None, "", "all"):
                errors.append(f'{item.where}: "pages" only works with a single "path"; split the files into separate items.')
                continue
            for p in path_list:
                resolved = _resolve(str(p), base)
                if not resolved.is_file():
                    near = _near_miss(resolved)
                    errors.append(
                        f"{item.where}: file not found: {resolved}"
                        + (f" (a similar file exists: {near.name!r}; copy the exact name)" if near else "")
                    )
                    continue
                try:
                    original = map_workspace_copy(resolved, item.where, warnings)
                except ToolError as exc:
                    errors.append(str(exc))
                    continue
                source = {"path": str(original)}
                if original != resolved:
                    source["_from_copy"] = True
                item.sources.append(source)
            if kind == "image":
                orient = str(raw.get("orientation", "auto")).lower()
                if orient not in ("auto", "portrait", "landscape"):
                    errors.append(f'{item.where}: "orientation" must be auto, portrait or landscape.')
                item.orientation = orient
                captions = raw.get("captions")
                if captions is not None:
                    if (not isinstance(captions, list) or len(captions) != len(path_list)
                            or not all(isinstance(c, str) and c.strip() for c in captions)):
                        errors.append(f'{item.where}: "captions" must list one short caption per image path.')
                    else:
                        item.captions = [" ".join(c.split()) for c in captions]
        elif kind == "separator":
            if not item.label:
                errors.append(f'{item.where}: a separator needs a "label" such as "Exhibit A".')
        elif kind == "placeholder":
            if not (item.label or item.description):
                errors.append(f'{item.where}: a placeholder needs a "label" and/or "description" of the missing document.')
        elif kind == "index" and item.label:
            errors.append(f"{item.where}: the index isn't an exhibit; remove its \"label\".")
        if raw.get("role") is not None:
            role = str(raw["role"]).strip().lower().replace(" ", "_")
            if role not in ROLES:
                errors.append(f'{item.where}: "role" must be one of {", ".join(ROLES)} (got {raw["role"]!r}).')
            else:
                item.role = role
                item.raw = dict(raw, _role_given=True)
        items.append(item)
    errors += _settle_exhibit_sections(items)
    if errors:
        raise ToolError("The plan has problems:\n  - " + "\n  - ".join(errors))
    return plan, items, base, warnings


def _settle_exhibit_sections(items: list[Item]) -> list[str]:
    """Give an exhibit's items one section and check that they sit together.

    An item without a "section" takes the section of the first item with the same label,
    so a document listed after its separator stays under the separator's section. An
    exhibit whose items are split by other items, or that names two sections, is an error.
    """
    errors: list[str] = []
    first_section: dict[str, str] = {}
    for it in items:
        key = _norm_label(it.label)
        if key and it.section and key not in first_section:
            first_section[key] = it.section
    for it in items:
        key = _norm_label(it.label)
        if key and not it.section and key in first_section:
            it.section = first_section[key]
    seen: dict[str, Item] = {}
    prev_key: str | None = None
    for it in items:
        key = _norm_label(it.label)
        if key is None:
            prev_key = None
            continue
        if key in seen and key != prev_key:
            errors.append(
                f"{it.label!r} is used at item {seen[key].index} and again at item {it.index}, with other items "
                "between them. Keep each exhibit's items together, or give the later one its own label."
            )
        elif key in seen and it.section != seen[key].section:
            errors.append(
                f"{it.label!r} is in section {seen[key].section!r} at item {seen[key].index} and {it.section!r} at "
                f"item {it.index}. An exhibit belongs to one section."
            )
        seen.setdefault(key, it)
        prev_key = key
    return errors


def _resolve(p: str, base: Path) -> Path:
    path = Path(os.path.expandvars(os.path.expanduser(p)))
    return (path if path.is_absolute() else base / path).resolve()


def _near_miss(path: Path) -> Path | None:
    """Find a file whose name differs only by spacing/case (e.g. 'Marriage certificate .pdf')."""
    parent = path.parent
    if not parent.is_dir():
        return None
    want = re.sub(r"\s+", "", path.name).lower()
    for candidate in parent.iterdir():
        if re.sub(r"\s+", "", candidate.name).lower() == want:
            return candidate
    return None


# ---------------------------------------------------------------------------
# Page ranges
# ---------------------------------------------------------------------------
def parse_pages(spec, total: int, where: str) -> list[int]:
    """'1-3,5,7-' -> zero-based indices. None/'all' means every page."""
    if spec is None or (isinstance(spec, str) and spec.strip().lower() in ("", "all")):
        return list(range(total))
    if isinstance(spec, int):
        spec = str(spec)
    if isinstance(spec, list):
        spec = ",".join(str(x) for x in spec)
    out: list[int] = []
    for part in str(spec).replace(" ", "").split(","):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)(?:-(\d*))?", part)
        if not m:
            raise ToolError(f'{where}: cannot read page range {part!r}. Use 1-based pages like "1-3,5" or "4-" (4 to the end).')
        a = int(m.group(1))
        b = a if m.group(2) is None else (int(m.group(2)) if m.group(2) else total)
        if a < 1 or b > total or a > b:
            raise ToolError(
                f"{where}: page range {part!r} does not fit the file, which has {total} page"
                f"{'s' if total != 1 else ''} (valid pages are 1-{total})."
            )
        out.extend(range(a - 1, b))
    if not out:
        raise ToolError(f'{where}: "pages" selects no pages.')
    return out


def compact_pages(indices: list[int]) -> str:
    """[0,1,2,4] -> '1-3,5' (1-based)."""
    return page_ranges([i + 1 for i in indices])


# ---------------------------------------------------------------------------
# Opening sources
# ---------------------------------------------------------------------------
_MAGIC = [
    (b"\xff\xd8\xff", 'a JPEG image; use kind "image"'),
    (b"\x89PNG", 'a PNG image; use kind "image"'),
    (b"PK\x03\x04", 'a Word/zip file; use kind "docx" for .docx files'),
    (b"\xd0\xcf\x11\xe0", 'an old Word .doc file; use kind "docx" (LibreOffice converts .doc too)'),
    (b"II*\x00", 'a TIFF image; use kind "image"'),
    (b"MM\x00*", 'a TIFF image; use kind "image"'),
]


def open_pdf(path: Path, where: str):
    from pypdf import PdfReader
    from pypdf.errors import FileNotDecryptedError, PdfReadError

    with path.open("rb") as fh:
        head = fh.read(1024)
    if b"%PDF" not in head:
        for magic, what in _MAGIC:
            if head.startswith(magic):
                raise ToolError(f"{where}: {path} is not a PDF; it looks like {what}.")
        if head[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftypmsf1"):
            raise ToolError(f'{where}: {path} is not a PDF; it looks like a HEIC photo; use kind "image".')
        raise ToolError(
            f"{where}: {path} is not a readable PDF (no PDF header). It may be damaged or mislabeled; "
            "open it in a PDF viewer, re-save or re-scan it, and point the plan at the new copy."
        )
    try:
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted:
            try:
                ok = reader.decrypt("")
            except Exception as exc:  # noqa: BLE001 - unsupported crypto, etc.
                raise ToolError(
                    f"{where}: {path} is encrypted and could not be opened ({exc}). Open it in a PDF viewer, "
                    "print or export it to a new unprotected PDF, and use that copy."
                ) from None
            if not ok:
                raise ToolError(
                    f"{where}: {path} is password-protected. Open it with its password, save an unprotected "
                    "copy (Print > Save as PDF works), and point the plan at that copy."
                )
        total = len(reader.pages)
        for page in reader.pages:
            _ = page.mediabox
    except ToolError:
        raise
    except FileNotDecryptedError:
        raise ToolError(
            f"{where}: {path} is password-protected. Save an unprotected copy and use that instead."
        ) from None
    except (PdfReadError, ValueError, KeyError, TypeError, AttributeError, IndexError, OSError, RecursionError) as exc:
        raise ToolError(
            f"{where}: {path} is damaged or not a valid PDF ({type(exc).__name__}: {exc}). Re-download, "
            "re-scan or re-save it (Print > Save as PDF), then point the plan at the new copy."
        ) from None
    if total == 0:
        raise ToolError(f"{where}: {path} has no pages.")
    return reader


def _has_form_fields(reader) -> bool:
    acro = reader.trailer["/Root"].get("/AcroForm")
    return acro is not None and bool(acro.get_object().get("/Fields"))


def _isolate_form_fields(reader, tag: str):
    """Give a fillable PDF's form fields unique names before merging.

    USCIS forms reuse the same internal field names, so two merged forms would
    otherwise show each other's answers. Also drops XFA, which would make some
    viewers show the first form's XFA layer for the whole packet.
    """
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, TextStringObject

    if not _has_form_fields(reader):
        return reader
    writer = PdfWriter(clone_from=reader)
    form = writer._root_object["/AcroForm"].get_object()
    if "/XFA" in form:
        del form["/XFA"]
    for ref in form.get("/Fields", []):
        fld = ref.get_object()
        if "/T" in fld:
            fld[NameObject("/T")] = TextStringObject(f"{tag}{fld['/T']}")
    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    return PdfReader(buf, strict=False)


def open_image_frames(path: Path, tmp: Path, where: str) -> list:
    from PIL import Image, ImageOps, ImageSequence

    suffix = path.suffix.lower()
    src = path
    if suffix in (".heic", ".heif"):
        try:
            import pillow_heif  # type: ignore

            pillow_heif.register_heif_opener()
        except ImportError:
            if sys.platform == "darwin" and shutil.which("sips"):
                src = tmp / f"heic-{hashlib.sha1(str(path).encode()).hexdigest()[:12]}.jpg"
                proc = subprocess.run(
                    ["sips", "-s", "format", "jpeg", str(path), "--out", str(src)],
                    capture_output=True, text=True,
                )
                if proc.returncode != 0 or not src.is_file():
                    raise ToolError(f"{where}: could not convert HEIC photo {path} with sips. Export it as JPG and use that.")
            else:
                raise ToolError(
                    f"{where}: {path} is a HEIC photo and HEIC support (pillow-heif) is unavailable here. "
                    'Re-run with: uv run --with pillow-heif --script ... , or export the photo as JPG.'
                )
    try:
        img = Image.open(src)
        frames = []
        seq = ImageSequence.Iterator(img) if getattr(img, "format", "") == "TIFF" else [img]
        for frame in seq:
            frame.load()
            frames.append(ImageOps.exif_transpose(frame.copy()))
        photo = (getattr(img, "format", "") or "").upper() in ("JPEG", "MPO", "HEIF", "HEIC", "AVIF", "WEBP")
        return [(f, photo) for f in frames]
    except Image.DecompressionBombError:
        raise ToolError(f"{where}: {path} is too large to place safely. Shrink it below about 150 megapixels.") from None
    except (OSError, SyntaxError, ValueError) as exc:
        raise ToolError(
            f"{where}: cannot read image {path} ({exc}). It may be damaged or not really an image; "
            "re-export it as JPG or PNG."
        ) from None


# ---------------------------------------------------------------------------
# Generated pages
# ---------------------------------------------------------------------------
def _fit_font(text: str, font: str, size: float, max_width: float, min_size: float) -> float:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    while size > min_size and stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def _centered_paragraph(c, text: str, font: str, size: float, top_y: float, width: float, color=None) -> float:
    """Draw wrapped centered text with its top at top_y; return the y of its bottom."""
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph

    style = ParagraphStyle("c", fontName=font, fontSize=size, leading=size * 1.25, alignment=TA_CENTER)
    if color is not None:
        style.textColor = color
    para = Paragraph(xml_escape(text), style)
    _, h = para.wrap(width, 10_000)
    para.drawOn(c, (LETTER_PT[0] - width) / 2, top_y - h)
    return top_y - h


def _canvas(out: Path, title: str):
    """A Letter-size reportlab canvas for one generated item, and the fonts to draw it with."""
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(out), pagesize=LETTER_PT)
    c.setTitle(title)
    return c, register_serif_fonts()


def make_separator(out: Path, label: str, description: str | None) -> None:
    c, fonts = _canvas(out, label)
    w, h = LETTER_PT
    text = label.upper()
    size = _fit_font(text, fonts.bold, 40, w - 144, 20)
    y = h * 0.57
    c.setFont(fonts.bold, size)
    c.drawCentredString(w / 2, y, text)
    c.setLineWidth(1)
    c.line(w / 2 - 90, y - 20, w / 2 + 90, y - 20)
    if description:
        _centered_paragraph(c, description, fonts.regular, 16, y - 40, 5.5 * 72)
    c.showPage()
    c.save()


def make_placeholder(out: Path, label: str | None, description: str | None, note: str | None) -> None:
    from reportlab.lib import colors

    c, fonts = _canvas(out, f"TO BE SUPPLIED - {label or description}")
    w, h = LETTER_PT
    c.setStrokeColor(colors.Color(0.35, 0.35, 0.35))
    c.setLineWidth(2)
    c.setDash(9, 5)
    c.rect(54, 54, w - 108, h - 108)
    c.setDash()
    y = h * 0.62
    c.setFillColor(colors.black)
    c.setFont(fonts.bold, 38)
    c.drawCentredString(w / 2, y, "TO BE SUPPLIED")
    y -= 42
    if label:
        text = label.upper()
        c.setFont(fonts.bold, _fit_font(text, fonts.bold, 24, w - 160, 14))
        c.drawCentredString(w / 2, y, text)
        y -= 22
    if description:
        y = _centered_paragraph(c, description, fonts.regular, 16, y - 6, 5.5 * 72)
        y -= 14
    if note:
        _centered_paragraph(c, f"Note: {note}", fonts.italic, 12.5, y - 10, 5.25 * 72, colors.Color(0.2, 0.2, 0.2))
    c.setFont(fonts.italic, 9.5)
    c.setFillColor(colors.Color(0.35, 0.35, 0.35))
    c.drawCentredString(w / 2, 72, "Placeholder in a draft packet. Replace with the actual document before filing.")
    c.showPage()
    c.save()


def make_index(out: Path, title: str, entries: list[dict]) -> int:
    """Draw the exhibit index with packet page numbers; return its page count.

    entries: {"section": str|None, "label", "description", "pages": "12-15" or "to be supplied, p. 40"}.
    The layout does not depend on the page numbers, so a draft with placeholder numbers
    has the same page count as the final index.
    """
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph

    c, fonts = _canvas(out, title)
    w, h = LETTER_PT
    left, right, top, bottom = 72.0, w - 72.0, h - 72.0, 72.0
    label_w, pages_w = 1.1 * 72, 1.15 * 72
    desc_w = right - left - label_w - pages_w - 12
    style = ParagraphStyle("d", fontName=fonts.regular, fontSize=11, leading=13.5)
    pages = 1
    y = top
    c.setFont(fonts.bold, 15)
    c.drawCentredString(w / 2, y - 15, title)
    y -= 40
    c.setFont(fonts.bold, 10)
    c.drawRightString(right, y, "Packet pages")
    y -= 16
    current: object = object()
    for e in entries:
        para = Paragraph(xml_escape(e["description"] or ""), style)
        _, ph = para.wrap(desc_w, 10_000)
        need = max(ph, 13.5) + 6 + (22 if e["section"] != current and e["section"] else 0)
        if y - need < bottom:
            c.showPage()
            pages += 1
            y = top
        if e["section"] != current:
            current = e["section"]
            if e["section"]:
                c.setFont(fonts.bold, 11.5)
                c.drawString(left, y - 12, e["section"])
                y -= 22
        c.setFont(fonts.regular, 11)
        c.drawString(left, y - 11, e["label"] or "")
        para.drawOn(c, left + label_w, y - ph + 2.5)
        c.drawRightString(right, y - 11, e["pages"])
        y -= max(ph, 13.5) + 6
    c.showPage()
    c.save()
    return pages


def make_image_pages(out: Path, paths: list[Path], orientation: str, tmp: Path, where: str,
                     dpi: int, warnings: list[str], downsampled: list[bool] | None = None) -> list[int]:
    """Draw each image (each frame of a multi-page TIFF) on its own page; return pages per file.

    downsampled, when given, gets one flag per file: whether any of its frames was resampled."""
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(out), pagesize=LETTER_PT)
    per_file: list[int] = []
    n = 0
    for path in paths:
        frames = open_image_frames(path, tmp, where)
        any_down = False
        for img, photo in frames:
            printed, down = _draw_image_page(c, img, photo, orientation, tmp, f"{out.stem}-{n}", dpi)
            any_down = any_down or down
            if max(printed) < SMALL_IMAGE_IN:
                warnings.append(
                    f"{where}: {path.name} is only {img.size[0]} x {img.size[1]} pixels, so it prints at "
                    f"{printed[0]:.1f} x {printed[1]:.1f} in. Use a larger copy of the photo if there is one."
                )
            n += 1
        per_file.append(len(frames))
        if downsampled is not None:
            downsampled.append(any_down)
    c.save()
    return per_file


def _draw_image_page(c, img, photo: bool, orientation: str, tmp: Path, tag: str,
                     dpi: int) -> tuple[tuple[float, float], bool]:
    """Draw one image centered on its own page; return its printed size in inches and whether it was resampled."""
    from PIL import Image

    wpx, hpx = img.size
    landscape = orientation == "landscape" or (orientation == "auto" and wpx > hpx)
    pw, ph = (LETTER_PT[1], LETTER_PT[0]) if landscape else LETTER_PT
    c.setPageSize((pw, ph))
    box_w, box_h = pw - 2 * IMAGE_MARGIN_PT, ph - 2 * IMAGE_MARGIN_PT
    # Fit the page, but never enlarge an image past one point per pixel: a small image
    # blown up to the page prints blurred.
    scale = min(box_w / wpx, box_h / hpx, 1.0)
    dw, dh = wpx * scale, hpx * scale
    # Downsample very high-resolution photos; never upsample.
    max_px = (max(1, round(dw / 72 * dpi)), max(1, round(dh / 72 * dpi)))
    down = wpx > max_px[0] * 1.05
    if down:
        img = img.resize(max_px, Image.LANCZOS)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, "white")
        bg.paste(rgba, mask=rgba.split()[-1])
        img = bg
    elif img.mode == "1":
        img = img.convert("L")
    elif img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if photo:
        staged = tmp / f"img-{tag}.jpg"
        img.save(staged, "JPEG", quality=90 if dpi >= 300 else 80, optimize=True)
    else:
        staged = tmp / f"img-{tag}.png"
        img.save(staged, "PNG", optimize=True)
    c.drawImage(str(staged), (pw - dw) / 2, (ph - dh) / 2, dw, dh)
    c.showPage()
    return (dw / 72, dh / 72), down


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def _norm_label(label: str | None) -> str | None:
    return " ".join(label.upper().split()) if label else None


def _source_name(item: Item) -> str:
    if not item.sources:
        return item.kind
    names = [Path(s["path"]).name for s in item.sources]
    text = names[0] if len(names) == 1 else f"{names[0]} (+{len(names) - 1} more)"
    if len(item.sources) == 1:
        pages, total = item.sources[0].get("pages"), item.sources[0].get("source_page_count")
        whole = "1" if total == 1 else f"1-{total}"
        if pages and total and pages != whole:
            text += f", {'pp.' if ('-' in pages or ',' in pages) else 'p.'} {pages}"
    return text


def load_items(items: list[Item], tmp: Path, warnings: list[str], *, tick=None) -> None:
    """Open every source, resolve page ranges, convert DOCX. Raises with all problems at once.
    `tick` is called once per item (the run's sign of life)."""
    errors: list[str] = []
    soffice = None
    for item in items:
        if tick:
            tick()
        try:
            for source in item.sources:
                source["sha256"] = _sha256(Path(source["path"]))
            if item.kind == "docx":
                soffice = soffice or find_soffice()
                if not soffice:
                    raise ToolError(
                        f"{item.where}: converting {item.sources[0]['path']} needs LibreOffice, which is not installed. "
                        "Install LibreOffice (https://www.libreoffice.org) or set SOFFICE_PATH, or export the document "
                        'to PDF from Word and list it as kind "pdf".'
                    )
                src = Path(item.sources[0]["path"])
                pdf = tmp / f"docx-{item.index}.pdf"
                soffice_convert_to_pdf(src, pdf, soffice)
                reader = open_pdf(pdf, item.where)
                idx = parse_pages(item.raw.get("pages"), len(reader.pages), item.where)
                item.sources[0].update(pages=compact_pages(idx), source_page_count=len(reader.pages))
                item.readers.append((reader, idx))
                item.file_pages = [len(idx)]
            elif item.kind == "pdf":
                for n, source in enumerate(item.sources):
                    reader = open_pdf(Path(source["path"]), item.where)
                    item.has_form_fields = item.has_form_fields or _has_form_fields(reader)
                    reader = _isolate_form_fields(reader, f"p{item.index:03d}{n}_")
                    idx = parse_pages(item.raw.get("pages") if len(item.sources) == 1 else None, len(reader.pages), item.where)
                    source.update(pages=compact_pages(idx), source_page_count=len(reader.pages))
                    item.readers.append((reader, idx))
                    item.file_pages.append(len(idx))
                    odd = [i + 1 for i in idx if not _is_letter(reader.pages[i])]
                    if odd:
                        size = _page_size_name(reader.pages[odd[0] - 1])
                        warnings.append(
                            f"{item.where}: {len(odd)} page(s) of {Path(source['path']).name} are not Letter size "
                            f"(e.g. page {odd[0]} is {size}); they were kept at their original size."
                        )
            elif item.kind == "image":
                for source in item.sources:
                    # Decode now to catch damaged files early; pages are drawn later, one file at a time.
                    frames = open_image_frames(Path(source["path"]), tmp, item.where)
                    source.update(pages=None, source_page_count=len(frames))
                    item.file_pages.append(len(frames))
                    del frames
            elif item.kind in ("separator", "placeholder"):
                item.file_pages = [1]
        except ToolError as exc:
            errors.append(str(exc))
    if errors:
        raise ToolError("Some sources could not be used:\n  - " + "\n  - ".join(errors))


def _is_letter(page) -> bool:
    w, h = sorted((float(page.mediabox.width), float(page.mediabox.height)))
    return abs(w - 612) < 3 and abs(h - 792) < 3


def _page_size_name(page) -> str:
    w, h = sorted((float(page.mediabox.width), float(page.mediabox.height)))
    for name, (a, b) in {"A4": (595, 842), "Legal": (612, 1008), "A5": (420, 595), "Tabloid": (792, 1224)}.items():
        if abs(w - a) < 4 and abs(h - b) < 4:
            return name
    return f"{w / 72:.2f} x {h / 72:.2f} in"


def assign_roles(items: list[Item], matter_root: Path | None) -> None:
    """Decide what each item is, unless the plan said so with "role".

    A filing copy the forms step's manifest lists is what it says (a payment form, or a form).
    Otherwise a form is recognized by where it lives (output/deliverables/Forms/), by a file name or
    description that starts with a form number inside output/deliverables/, by its exhibit
    section ("Forms"), or by fillable fields; a payment form by its form number (G-1450,
    G-1650, G-1651); the cover letter by its name.
    """
    forms_dir = (matter_root / "output" / "deliverables" / "Forms").resolve() if matter_root else None
    deliverables = (matter_root / "output" / "deliverables").resolve() if matter_root else None
    for item in items:
        if item.raw.get("_role_given"):
            continue
        if item.kind in ("separator", "placeholder", "index"):
            item.role = "exhibit" if item.label else "other"
            continue
        if item.prepared_kind:
            item.role = "payment" if item.prepared_kind in PAYMENT_KINDS else "form"
            continue
        paths = [Path(s["path"]) for s in item.sources]
        names = [p.name for p in paths]
        text = _item_text(item)
        in_forms_dir = forms_dir is not None and any(_is_within(p, forms_dir) for p in paths)
        numbered = (deliverables is not None and any(_is_within(p, deliverables) for p in paths)
                    and any(FORM_NUMBER_RE.match(n) for n in names))
        if PAYMENT_FORM_RE.search(text):
            item.role = "payment"
        elif _is_cover_letter(item):
            item.role = "cover_letter"
        elif (in_forms_dir or numbered or item.has_form_fields
              or (item.section and re.match(r"\s*forms?\b", item.section, re.IGNORECASE))
              or ENOTICE_FORM_RE.search(text)):
            item.role = "form"
        else:
            item.role = "exhibit" if item.label else "other"


def _item_text(item: Item) -> str:
    """What an item says it is: its description, bookmark, and its files' names."""
    return " ".join(filter(None, [item.description, item.bookmark, *(Path(s["path"]).name for s in item.sources)]))


def _is_cover_letter(item: Item) -> bool:
    if item.raw.get("_role_given"):
        return item.role == "cover_letter"
    if item.kind not in ("pdf", "image", "docx") or item.prepared_kind:
        return False
    text = _item_text(item)
    return bool(COVER_LETTER_RE.search(text)) and not PAYMENT_FORM_RE.search(text)


def _is_within(path: Path, folder: Path) -> bool:
    return path.resolve().is_relative_to(folder)


# ---------------------------------------------------------------------------
# Layout: exhibits and the index, before anything is written
# ---------------------------------------------------------------------------
def exhibit_groups(items: list[Item]) -> list[list[Item]]:
    """Consecutive items with the same label form one exhibit; unlabeled items stand alone."""
    groups: list[list[Item]] = []
    for item in items:
        key = _norm_label(item.label)
        if key is not None and groups and _norm_label(groups[-1][0].label) == key:
            groups[-1].append(item)
        else:
            groups.append([item])
    return groups


def _exhibit_description(group: list[Item]) -> str | None:
    return next((g.description for g in group if g.description), None)


def index_entries(items: list[Item]) -> list[dict]:
    entries = []
    for group in exhibit_groups(items):
        head = group[0]
        if head.label is None:
            continue
        content = [g for g in group if g.kind in ("pdf", "image", "docx")]
        missing = [g for g in group if g.kind == "placeholder"]
        if content:
            a, z = content[0].start + 1, content[-1].start + content[-1].count
            pages = str(a) if a == z else f"{a}-{z}"
        elif missing:
            pages = f"to be supplied, p. {missing[0].start + 1}"
        else:
            pages = f"enclosed, p. {head.start + 1}"
        entries.append({"section": head.section, "label": head.label, "description": _exhibit_description(group),
                        "pages": pages})
    return entries


def layout(items: list[Item], tmp: Path) -> None:
    """Give every item its packet position. The index's page count is measured with draft numbers."""
    for item in items:
        if item.kind == "index":
            draft = [dict(e, pages="0000-0000") for e in index_entries(items)]
            item.count = make_index(tmp / f"index-draft-{item.index}.pdf", _index_title(item), draft)
        else:
            item.count = sum(item.file_pages)
    pos = 0
    for item in items:
        item.start = pos
        pos += item.count


def _index_title(item: Item) -> str:
    return str(item.raw.get("title") or item.description or "Index of Exhibits")


# ---------------------------------------------------------------------------
# Compression (--max-mb)
# ---------------------------------------------------------------------------
def find_ghostscript() -> str | None:
    for name in ("gs", "gswin64c", "gswin32c"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in ("/opt/homebrew/bin/gs", "/usr/local/bin/gs", "/usr/bin/gs"):
        if Path(candidate).is_file():
            return candidate
    return None


def _compress_pdf(src: Path, dest: Path, dpi: int, gs: str) -> bool:
    """Re-save a scanned PDF with its images downsampled to dpi. True when the copy is smaller."""
    cmd = [
        gs, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.6",
        "-dDetectDuplicateImages=true", "-dDownsampleColorImages=true", "-dDownsampleGrayImages=true",
        "-dDownsampleMonoImages=true", "-dColorImageDownsampleType=/Bicubic",
        "-dGrayImageDownsampleType=/Bicubic", f"-dColorImageResolution={dpi}", f"-dGrayImageResolution={dpi}",
        f"-dMonoImageResolution={max(dpi * 2, 300)}", "-dColorImageDownsampleThreshold=1.1",
        "-dGrayImageDownsampleThreshold=1.1", f"-sOutputFile={dest}", str(src),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and dest.is_file() and 0 < dest.stat().st_size < src.stat().st_size


def compressed_readers(items: list[Item], tmp: Path, dpi: int, gs: str | None) -> tuple[dict[int, list], set]:
    """Readers for a smaller build: scanned exhibits re-saved at dpi by Ghostscript.

    Forms, payment forms and the cover letter are never resampled. Returns the readers by
    item index, and the (item index, source number) pairs actually replaced by a smaller copy.
    """
    out: dict[int, list] = {}
    done: set = set()
    if gs is None:
        return out, done
    for item in items:
        if item.kind not in ("pdf", "docx") or item.has_form_fields or item.role in UNTOUCHED_ROLES:
            continue
        readers = []
        for n, (reader, idx) in enumerate(item.readers):
            src = Path(item.sources[n]["path"]) if item.kind == "pdf" else tmp / f"docx-{item.index}.pdf"
            dest = tmp / f"small-{dpi}-{item.index}-{n}.pdf"
            small = None
            if _compress_pdf(src, dest, dpi, gs):
                try:
                    candidate = open_pdf(dest, item.where)
                    if len(candidate.pages) == len(reader.pages):
                        small = candidate
                except ToolError:
                    small = None
            if small is not None:
                done.add((item.index, n))
            readers.append((small or reader, idx))
        out[item.index] = readers
    return out, done


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def _stamp_text(item: Item, page_in_exhibit: int | None, exhibit_pages: int, packet_page: int, total: int) -> str:
    packet = f"packet p. {packet_page} of {total}"
    if item.label and page_in_exhibit is not None:
        label = re.sub(r"^\s*exhibit\s+", "Ex. ", item.label, flags=re.IGNORECASE)
        return f"{label}, p. {page_in_exhibit}/{exhibit_pages} ({packet})"
    return packet[0].upper() + packet[1:]


STAMP_BAND_PT = 20.0  # the strip the page's content is moved up out of, for the stamp


def make_room_for_stamp(page, band: float = STAMP_BAND_PT) -> tuple[float, float, float, float]:
    """Shrink the page's content proportionally into the page above a clear band at the bottom.

    The page keeps its size; its content (clipped to the original visible area) is scaled by
    (height - band) / height and centered, so nothing the document shows can sit under the
    stamp. Annotation rectangles move with the content. Returns the visible box (left, bottom,
    width, height) the stamp is drawn in.
    """
    from pypdf.generic import ArrayObject, DecodedStreamObject, FloatObject, NameObject

    if page.get("/Rotate", 0) % 360:
        page.transfer_rotation_to_content()
    box = page.cropbox
    left, bottom, w, h = float(box.left), float(box.bottom), float(box.width), float(box.height)
    s = (h - band) / h
    e = left * (1 - s) + (w - w * s) / 2
    f = bottom * (1 - s) + band
    contents = page.get_contents()
    data = contents.get_data() if contents is not None else b""
    head = (f"q {s:.6f} 0 0 {s:.6f} {e:.4f} {f:.4f} cm {left:.4f} {bottom:.4f} {w:.4f} {h:.4f} re W n\n").encode()
    stream = DecodedStreamObject()
    stream.set_data(head + data + b"\nQ\n")
    page.replace_contents(stream)
    for ref in page.get("/Annots") or []:
        annot = ref.get_object()
        rect = annot.get("/Rect")
        if rect and len(rect) == 4:
            x1, y1, x2, y2 = (float(v) for v in rect)
            annot[NameObject("/Rect")] = ArrayObject(
                [FloatObject(x1 * s + e), FloatObject(y1 * s + f), FloatObject(x2 * s + e), FloatObject(y2 * s + f)])
    return left, bottom, w, h


def apply_stamps(writer, items: list[Item]) -> int:
    """Stamp exhibit and packet page numbers in a clear band at the foot of each page.

    The page's content is first shrunk a little to clear the band (make_room_for_stamp), so a
    stamp can never cover anything the document shows. Forms, payment forms and the cover
    letter are left exactly as they are. The exhibit page count ("p. 3/7") counts every page of
    the exhibit's documents, including any left unstamped. Returns the number of pages stamped.
    """
    from pypdf import PdfReader, Transformation
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    fonts = register_serif_fonts()
    total = len(writer.pages)
    jobs: list[tuple[int, str]] = []
    for group in exhibit_groups(items):
        content = [g for g in group if g.kind in ("pdf", "image", "docx")]
        content_ids = {id(g) for g in content}
        exhibit_pages = sum(g.count for g in content)
        k = 0
        for g in group:
            skip = g.has_form_fields or g.role in UNTOUCHED_ROLES
            for p in range(g.start, g.start + g.count):
                in_exhibit = None
                if id(g) in content_ids:
                    k += 1
                    in_exhibit = k
                if not skip:
                    jobs.append((p, _stamp_text(g, in_exhibit, exhibit_pages, p + 1, total)))
            g.stamped = not skip and g.count > 0
    if not jobs:
        return 0
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    boxes = []
    for p, text in jobs:
        left, bottom, w, h = make_room_for_stamp(writer.pages[p])
        boxes.append((p, left, bottom))
        c.setPageSize((w, h))
        size = 7.5
        tw = stringWidth(text, fonts.regular, size)
        c.setFont(fonts.regular, size)
        c.drawString(w - 18 - tw, (STAMP_BAND_PT - size) / 2 + 1, text)  # no fill: nothing underneath to hide
        c.showPage()
    c.save()
    buf.seek(0)
    overlay = PdfReader(buf)
    for (p, left, bottom), stamp in zip(boxes, overlay.pages):
        writer.pages[p].merge_transformed_page(stamp, Transformation().translate(left, bottom))
    return len(jobs)


def build_packet(plan: dict, items: list[Item], out_pdf: Path, tmp: Path, warnings: list[str], *,
                 dpi: int = MAX_IMAGE_DPI, readers: dict[int, list] | None = None, stamps: bool = True, tick=None):
    from pypdf import PdfReader, PdfWriter

    readers = readers or {}
    writer = PdfWriter()
    has_forms = False
    need_appearances = False
    for item in items:
        if tick:
            tick()
        before = len(writer.pages)
        if item.kind in ("pdf", "docx"):
            for reader, idx in readers.get(item.index, item.readers):
                acro = reader.trailer["/Root"].get("/AcroForm")
                if acro is not None and acro.get_object().get("/Fields"):
                    has_forms = True
                    need_appearances = need_appearances or bool(acro.get_object().get("/NeedAppearances", False))
                writer.append(reader, pages=list(idx), import_outline=False)
        else:
            gen = tmp / f"gen-{item.index}.pdf"
            if item.kind in ("separator", "placeholder"):
                bad = unsupported_chars(" ".join(filter(None, (item.label, item.description, item.note))), register_serif_fonts())
                if bad:
                    _warn_once(warnings,
                        f"{item.where}: the built-in fallback font cannot draw {' '.join(sorted(bad))}; install Times New Roman "
                        "or Liberation Serif, or spell those characters without accents."
                    )
            if item.kind == "separator":
                make_separator(gen, item.label or "", item.description)
            elif item.kind == "placeholder":
                make_placeholder(gen, item.label, item.description, item.note)
            elif item.kind == "index":
                make_index(gen, _index_title(item), index_entries(items))
            else:
                image_warnings: list[str] = []
                item.image_downsampled = []
                item.file_pages = make_image_pages(gen, [Path(s["path"]) for s in item.sources], item.orientation,
                                                   tmp, item.where, dpi, image_warnings, item.image_downsampled)
                for w in image_warnings:
                    _warn_once(warnings, w)
            writer.append(PdfReader(str(gen)), import_outline=False)
        if len(writer.pages) - before != item.count:
            raise ToolError(f"{item.where}: expected {item.count} page(s) but placed {len(writer.pages) - before}.")

    if has_forms:
        from pypdf.generic import BooleanObject, NameObject

        form = writer._root_object.get("/AcroForm")
        if form is not None:
            form = form.get_object()
            if "/XFA" in form:
                del form["/XFA"]
            if need_appearances:
                form[NameObject("/NeedAppearances")] = BooleanObject(True)

    for item in items:
        item.stamped = False
    if stamps:
        apply_stamps(writer, items)
    exhibits = add_bookmarks(writer, items, warnings)
    title = plan.get("title") or out_pdf.stem
    writer.add_metadata({"/Title": str(title), "/Creator": "assemble_packet.py"})
    writer.page_mode = "/UseOutlines"
    try:
        writer.compress_identical_objects()  # defaults drop duplicate and unreferenced objects
    except Exception:  # noqa: BLE001 - optimisation only
        pass
    _write_atomic(writer, out_pdf)
    return exhibits


def _warn_once(warnings: list[str], text: str) -> None:
    if text not in warnings:
        warnings.append(text)


def _write_atomic(writer, out_pdf: Path) -> None:
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".packet-", suffix=".pdf", dir=str(out_pdf.parent))
    os.close(fd)
    # mkstemp creates the file owner-only; give the packet the same permissions as the other deliverables.
    umask = os.umask(0)
    os.umask(umask)
    os.chmod(tmp_name, 0o666 & ~umask)
    try:
        with open(tmp_name, "wb") as fh:
            writer.write(fh)
        os.replace(tmp_name, out_pdf)
    except OSError as exc:
        Path(tmp_name).unlink(missing_ok=True)
        raise ToolError(f"Could not write {out_pdf} ({exc}). If it is open in a PDF viewer, close it and retry.") from None


def _photo_titles(item: Item) -> list[str]:
    n = len(item.sources)
    if item.captions:
        return list(item.captions)
    noun = "Photo" if all(Path(s["path"]).suffix.lower() in (".jpg", ".jpeg", ".heic", ".heif", ".webp", ".png")
                          for s in item.sources) else "Image"
    return [f"{noun} {k} of {n}" for k in range(1, n + 1)]


def _add_photo_bookmarks(writer, item: Item, parent, level: int) -> None:
    """One bookmark per image file of an image item with more than one file."""
    if item.kind != "image" or len(item.sources) < 2:
        return
    page = item.start
    for title, pages, source in zip(_photo_titles(item), item.file_pages, item.sources):
        writer.add_outline_item(title, page, parent=parent)
        source["packet_start"] = page + 1
        page += pages


def add_bookmarks(writer, items: list[Item], warnings: list[str]) -> list[dict]:
    exhibits: list[dict] = []
    seen_sections: set[str] = set()
    current_section: object = object()
    section_bm = None
    for group in exhibit_groups(items):
        item = group[0]
        if item.section != current_section:
            current_section = item.section
            section_bm = None
            if item.section:
                if item.section in seen_sections:
                    warnings.append(f"Section {item.section!r} appears in two separate places; it has two bookmarks.")
                seen_sections.add(item.section)
                section_bm = writer.add_outline_item(item.section, item.start)
        level = 1 if section_bm is not None else 0
        if item.label is None:
            title = item.bookmark or item.description or (_index_title(item) if item.kind == "index" else _source_name(item))
            if item.kind == "placeholder":
                title = f"TO BE SUPPLIED - {title}"
            bm = writer.add_outline_item(title, item.start, parent=section_bm)
            item.bookmark_title, item.bookmark_level = title, level
            _add_photo_bookmarks(writer, item, bm, level + 1)
            continue
        desc = _exhibit_description(group)
        head = item.bookmark or (f"{item.label} - {desc}" if desc else item.label)
        missing = any(g.kind == "placeholder" for g in group)
        if missing:
            head += " [TO BE SUPPLIED]"
        group_bm = writer.add_outline_item(head, item.start, parent=section_bm)
        content = [g for g in group if g.kind != "separator"]
        for g in group:
            g.bookmark_title, g.bookmark_level = head, level
        if len(content) == 1 and content[0].kind == "image" and len(content[0].sources) > 1:
            # One set of photos: each photo directly under the exhibit.
            _add_photo_bookmarks(writer, content[0], group_bm, level + 1)
        elif any(g.kind == "separator" for g in group) or len(content) > 1:
            for g in content:
                if g.kind == "placeholder":
                    title = f"TO BE SUPPLIED - {g.description or g.label}"
                else:
                    title = g.bookmark or (g.description if g.description and g.description != desc else _source_name(g))
                bm = writer.add_outline_item(title, g.start, parent=group_bm)
                g.bookmark_title, g.bookmark_level = title, level + 1
                _add_photo_bookmarks(writer, g, bm, level + 2)
        last = group[-1]
        exhibits.append({"label": item.label, "description": desc, "section": item.section, "packet_start": item.start + 1,
                         "packet_end": last.start + last.count, "items": [g.index for g in group],
                         "to_be_supplied": missing})
    return exhibits


# ---------------------------------------------------------------------------
# Upload files for an online filing (--split-max-mb)
# ---------------------------------------------------------------------------
_UPLOAD_NAME_RE = re.compile(r"^\d{2} .+\.pdf$")
# The upload folder's own record of the files the tool wrote there, so ownership survives another packet's run
# writing the manifest (a split filing's paper part) and the upload map is never written over a stranger's file.
UPLOADS_RECORD = ".upload files written.json"


def _pdf_bytes(reader, pages: list[int]) -> int:
    from pypdf import PdfWriter

    w = PdfWriter()
    for p in pages:
        w.add_page(reader.pages[p])
    buf = io.BytesIO()
    w.write(buf)
    return buf.tell()


def _safe_name(text: str, limit: int = 80) -> str:
    """A file-name-safe title of at most limit characters, cut at a clause or word, never mid-word
    ("Form G-28, Notice of Entry of Appearance as Attorney or Accredited Representative" -> "Form G-28")."""
    text = " ".join(re.sub(r'[\\/:*?"<>|]+', " ", text).split())
    if len(text) > limit:
        cut = text[:limit + 1]
        cut = cut[:cut.rfind(", ")] if ", " in cut else (cut.rsplit(" ", 1)[0] if " " in cut else cut[:limit])
        text = cut
    return text.strip(" .,;-") or "Part"


def check_split_dir(out_dir: Path, items: list[Item], matter_root: Path | None, manifest_path: Path) -> set[str]:
    """Refuse an upload folder the tool must not write into; return the upload files it wrote there before.

    The folder must be inside the matter's output/deliverables/ (when the packet is in a matter),
    hold none of the plan's sources, and hold no upload-named file this tool didn't write (those
    are listed in the previous manifest's upload_files).
    """
    if matter_root is not None and not _is_within(out_dir, (matter_root / "output" / "deliverables").resolve()):
        raise ToolError(f"The upload files go in a folder inside the matter's output/deliverables/, not {out_dir}. "
                        "Leave --split-dir out to use the default.")
    inside = [Path(s["path"]).name for it in items for s in it.sources if _is_within(Path(s["path"]), out_dir)]
    if inside:
        raise ToolError(f"{out_dir} holds documents the packet is built from ({', '.join(sorted(set(inside))[:3])}). "
                        "Write the upload files to their own folder.")
    owned: set[str] = set()
    try:
        previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        previous = {}
    if isinstance(previous, dict) and previous.get("upload_dir") and Path(previous["upload_dir"]).resolve() == out_dir:
        owned = {str(f.get("file")) for f in previous.get("upload_files") or [] if isinstance(f, dict) and f.get("file")}
        if isinstance(previous.get("upload_map"), dict) and previous["upload_map"].get("file"):
            owned.add(Path(previous["upload_map"]["file"]).name)
    try:
        record = json.loads((out_dir / UPLOADS_RECORD).read_text(encoding="utf-8"))
        owned |= {str(n) for n in record.get("files") or [] if isinstance(n, str)}
    except (OSError, ValueError, AttributeError):
        pass
    if out_dir.is_dir():
        strangers = sorted(x.name for x in out_dir.iterdir()
                           if x.is_file() and (_UPLOAD_NAME_RE.match(x.name) or x.name == UPLOAD_MAP_NAME)
                           and x.name not in owned)
        if strangers:
            raise ToolError(f"{out_dir} already has files this tool didn't write ({', '.join(strangers[:3])}). "
                            "Move them, or write the upload files to another folder.")
    return owned


def record_uploads(out_dir: Path, names: list[str]) -> None:
    """Write the upload folder's record of what this run put there."""
    (out_dir / UPLOADS_RECORD).write_text(json.dumps({"files": sorted(names)}, indent=1) + "\n", encoding="utf-8")


def _exhibit_span(labels: list[str]) -> str:
    """"Exhibit D", "Exhibits D-G" or "Exhibits D, F": the exhibits a file holds, for its name."""
    marks = [m.group(1) for x in labels if (m := re.match(r"^\s*exhibit\s+(\S+)\s*$", str(x or ""), re.IGNORECASE))]
    if not marks or len(marks) != len(labels):
        return ""
    if len(marks) == 1:
        return f"Exhibit {marks[0]}"
    if len(marks) == 2:
        return f"Exhibits {marks[0]}, {marks[1]}"
    return f"Exhibits {marks[0]}-{marks[-1]}"


_FORM_WORDS_RE = re.compile(r"\b([GIN])-?\s?(\d{2,4}[A-Z]?)\b(\s+supplement\s+[A-Z]\b)?", re.IGNORECASE)


def _item_words(item: Item) -> list[str]:
    return [x for x in [item.label, item.description, *(Path(s["path"]).stem for s in item.sources)] if x]


def form_number(item: Item) -> str | None:
    """The USCIS form an item is ("I-485", "G-28", "I-485 Supplement J"), from the forms step's manifest or its
    words; None if none."""
    if item.prepared_kind:
        return item.prepared_kind.upper()
    for text in _item_words(item):
        m = _FORM_WORDS_RE.search(text)
        if m:
            number = f"{m.group(1).upper()}-{m.group(2).upper()}"
            return number + (f" Supplement {m.group(3).split()[-1].upper()}" if m.group(3) else "")
    return None


def g28_for_form(item: Item) -> str | None:
    """The form a G-28 file names as the one it covers ("G-28 - I-130"), if it names one."""
    for text in _item_words(item):
        found = [f"{m.group(1).upper()}-{m.group(2).upper()}" for m in _FORM_WORDS_RE.finditer(text)]
        others = [f for f in found if f != "G-28"]
        if others:
            return others[0]
    return None


def split_for_upload(packet: Path, items: list[Item], out_dir: Path, max_mb: float, warnings: list[str],
                     owned: set[str] | None = None) -> list[dict]:
    """Write the packet as upload files: one per evidence category (section), each under max_mb.

    The cover letter and each form get a file of their own, whatever their section, because the
    online account takes each form as its own PDF. A category too large for one file is split
    between exhibits, and an exhibit too large between pages. An evidence file's name carries the
    exhibits it holds ("05 Bona Fide Marriage (Exhibits D-G).pdf").
    """
    from pypdf import PdfReader, PdfWriter

    cap = int(max_mb * 1_048_576)
    reader = PdfReader(str(packet))
    categories: list[tuple[str, list[list[Item]], Item]] = []
    for group in exhibit_groups(items):
        head = group[0]
        own_file = head.role in UNTOUCHED_ROLES
        name = (head.description or head.label or _source_name(head)) if own_file else (
            head.section or head.description or head.label or (_index_title(head) if head.kind == "index" else _source_name(head)))
        if not own_file and head.section and categories and categories[-1][0] == head.section \
                and categories[-1][2].role not in UNTOUCHED_ROLES:
            categories[-1][1].append(group)
        else:
            categories.append((name, [group], head))

    out_dir.mkdir(parents=True, exist_ok=True)
    for name in owned or ():  # only the files the previous run wrote, so only one set is ever current
        old = out_dir / name
        if old.is_file() and _UPLOAD_NAME_RE.match(name):
            old.unlink()

    files: list[dict] = []
    for name, groups, head in categories:
        units = []  # (pages, exhibit labels)
        for group in groups:
            pages = [p for g in group for p in range(g.start, g.start + g.count)]
            if _pdf_bytes(reader, pages) <= cap:
                units.append((pages, [group[0].label] if group[0].label else []))
                continue
            chunk: list[int] = []
            for p in pages:  # an exhibit larger than the cap: split between pages
                if chunk and _pdf_bytes(reader, chunk + [p]) > cap:
                    units.append((chunk, [group[0].label] if group[0].label else []))
                    chunk = []
                chunk.append(p)
            if chunk:
                units.append((chunk, [group[0].label] if group[0].label else []))
        parts: list[tuple[list[int], list[str]]] = []
        for pages, labels in units:
            if parts and _pdf_bytes(reader, parts[-1][0] + pages) <= cap:
                parts[-1] = (parts[-1][0] + pages, parts[-1][1] + [x for x in labels if x not in parts[-1][1]])
            else:
                parts.append((list(pages), list(labels)))
        for k, (pages, labels) in enumerate(parts, start=1):
            suffix = f" (part {k} of {len(parts)})" if len(parts) > 1 else ""
            span = _exhibit_span(labels) if head.role not in UNTOUCHED_ROLES else ""
            covers = g28_for_form(head) if head.role == "form" and form_number(head) == "G-28" else None
            # A G-28's name says which form it is for, so a filing's G-28s don't share one.
            title = f"Form G-28 for the {covers}" if covers else _safe_name(name)
            if span and span.lower() not in title.lower():
                title = f"{title} ({span})"
            fname = f"{len(files) + 1:02d} {title}{suffix}.pdf"
            w = PdfWriter()
            for p in pages:
                w.add_page(reader.pages[p])
            path = out_dir / fname
            with open(path, "wb") as fh:
                w.write(fh)
            size = path.stat().st_size
            if size > cap:
                warnings.append(
                    f"Upload file {fname} is {size / 1_048_576:.1f} MB, over the {max_mb:g} MB limit, because a single page "
                    "is that large. Re-scan that page at a lower resolution."
                )
            files.append({"file": fname, "category": name, "pages": compact_pages(pages),
                          "page_count": len(pages), "size_bytes": size, "exhibits": labels,
                          "role": head.role if head.role in UNTOUCHED_ROLES else ("index" if head.kind == "index" else "evidence"),
                          "form": form_number(head) if head.role == "form" else None, "covers": covers})
    return files


UPLOAD_MAP_NAME = "Upload map.md"


def load_channels(path: Path) -> dict:
    """The filing channels from fees.json (its "channels") or from filing_channels.py --json."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ToolError(f"--channels: {path} can't be read as JSON ({exc}).") from None
    channels = data.get("channels") if isinstance(data, dict) and "channels" in data else data
    if not isinstance(channels, dict) or not isinstance(channels.get("forms"), list) \
            or not isinstance(channels.get("submissions"), list):
        raise ToolError(f"--channels: {path} has no filing channels. Give the fees tool's fees.json.")
    return channels


def upload_map(files: list[dict], channels: dict | None, warnings: list[str]) -> dict:
    """What each upload file is in the USCIS online account, checked against the filing's channels.

    Returns {"submissions": [{lead, channel, forms, evidence_forms, g28_for, files: [...]}], "paper": [...],
    "unplaced": [...], "checks": [...]}; each file is {file, role, form, upload_as}. Problems are warnings."""
    entries = {e["form"]: e for e in (channels or {}).get("forms", [])}
    subs = [dict(s, files=[]) for s in (channels or {}).get("submissions", [])]
    lead_of = {}
    for s in subs:
        for f in s["forms"] + s["evidence_forms"]:
            lead_of[f] = s["lead"]
    first = subs[0] if subs else None
    unplaced: list[dict] = []
    general: list[dict] = []
    g28_files = 0

    def place(row: dict, lead: str | None) -> None:
        target = next((s for s in subs if s["lead"] == lead), None) if lead else None
        (target["files"] if target else general).append(row)

    for f in files:
        role, form = f.get("role", "evidence"), f.get("form")
        row = {"file": f["file"], "role": role, "form": form, "exhibits": f.get("exhibits") or [], "upload_as": ""}
        if role == "cover_letter":
            row["upload_as"] = "the cover letter: upload it first among the evidence"
            place(row, first["lead"] if first else None)
        elif role == "payment":
            row["upload_as"] = "not uploaded: an online filing is paid in the account"
            unplaced.append(row)
            warnings.append(f"Upload file {f['file']} is a payment form; an online filing is paid in the account, so "
                            "leave it out of the upload.")
        elif role == "form" and form == "G-28":
            g28_files += 1
            covers = f.get("covers")
            row["upload_as"] = (f"the G-28 for the {covers}" if covers else
                                "a G-28: the account asks for one with each form")
            place(row, lead_of.get(covers or "") or (first["lead"] if first else None))
        elif role == "form":
            e = entries.get(form or "")
            sign = "print it, have it signed in ink, and upload the scan of the signed form"
            if not channels or e is None:
                row["upload_as"] = f"the {form or 'form'} PDF ({sign})"
                place(row, first["lead"] if first else None)
                if channels and form:
                    warnings.append(f"Upload file {f['file']} is the {form}, which the filing channels don't list; "
                                    "price and plan it with the fees tool, or leave it out.")
            elif e["channel"] == "pdf_upload":
                row["upload_as"] = f"the {form} form PDF ({sign})"
                place(row, form)
            elif e["channel"] == "with" and form in filing_channels.EITHER_WAY:
                row["upload_as"] = (f"the {form}, with the {e['with']}: USCIS lists it both among the forms its upload "
                                    "takes and as supporting evidence, so add it the way the account offers")
                place(row, e["with"])
            elif e["channel"] == "with" and form in filing_channels.CONFIRM_ON_LIST:
                # The I-130A supplements the I-130, which may itself ride in the I-485's upload.
                of = filing_channels.EVIDENCE_OF.get(form, e["with"])
                where = "" if of == e["with"] else f", which files with the {e['with']}"
                row["upload_as"] = (f"evidence for the {of}{where}: the {form} (confirm it is on the account's "
                                    "acceptable-evidence list)")
                place(row, e["with"])
            elif e["channel"] == "with":
                row["upload_as"] = (f"a companion form: add the {form} when the account asks which forms to file with the "
                                    f"{e['with']}, and upload this ({sign})")
                place(row, e["with"])
            elif e["channel"] == "guided":
                row["upload_as"] = (f"for reference only: the {form} is typed into the account's step-by-step form, "
                                    "not uploaded")
                place(row, form)
            else:
                why = e.get("why") or e.get("needs") or ""
                row["upload_as"] = f"not uploaded: the {form} goes {'on paper' if e['channel'] == 'paper' else 'nowhere'}"
                unplaced.append(row)
                warnings.append(f"Upload file {f['file']} is the {form}, which "
                                + (f"goes on paper ({why}); it belongs in the paper packet, not the upload files."
                                   if e["channel"] == "paper" else
                                   f"isn't filed in this filing ({why}); leave it out." if e["channel"] == "not_filed" else
                                   f"has no settled channel yet ({why})."))
        elif role == "index":
            row["upload_as"] = "evidence: the exhibit index"
            place(row, first["lead"] if first else None)
        else:
            row["upload_as"] = "evidence"
            place(row, first["lead"] if len(subs) == 1 else None)
    checks: list[str] = []
    if channels:
        held = {f.get("form") for f in files if f.get("role") == "form"}
        for s in subs:
            # The I-693 is an exhibit (the civil surgeon's scan), not a prepared form, so it isn't looked for here.
            for form in s["forms"] + [x for x in s["evidence_forms"] if x != "I-693"]:
                if form not in held and s["channel"] == "pdf_upload":
                    warnings.append(f"No upload file holds the {form} for the {s['lead']} PDF upload.")
        needed = sum(len(s["g28_for"]) for s in subs if s["channel"] == "pdf_upload")
        if needed and g28_files < needed:
            names = ", ".join(f for s in subs if s["channel"] == "pdf_upload" for f in s["g28_for"])
            warnings.append(f"The upload files hold {g28_files} G-28{'s' if g28_files != 1 else ''} for {needed} forms "
                            f"({names}); an attorney's online submission needs a properly executed G-28 for each party "
                            "and form (uscis.gov/online-filing-options, updated 10/07/2026).")
        if len(subs) > 1 and general:
            checks.append("This filing has more than one online submission: upload each evidence file with the "
                          "submission whose forms it supports, as the cover letter's exhibit list does.")
    return {"submissions": subs, "general": general, "unplaced": unplaced,
            "paper": (channels or {}).get("paper"), "checks": checks}


def check_against_channels(plan: dict, items: list[Item], channels: dict, warnings: list[str]) -> None:
    """A split filing is two packets: warn when a form sits in the packet for the other way of filing."""
    method_of = {e["form"]: e["method"] for e in channels.get("forms", [])}
    if plan["filing_method"] == "online" and not channels.get("submissions"):
        warnings.append("The plan says online, but the filing channels have no online submission: this filing goes "
                        "on paper.")
    for it in items:
        if it.role != "form":
            continue
        form = form_number(it)
        if not form or form == "G-28" or form not in method_of:
            continue
        method = method_of[form]
        if plan["filing_method"] == "paper" and method == "online":
            warnings.append(f"{it.where}: the {form} goes online in this filing, so it belongs in the online upload, "
                            "not the paper packet.")
        elif plan["filing_method"] == "online" and method == "paper":
            warnings.append(f"{it.where}: the {form} goes on paper in this filing, so it belongs in the paper packet, "
                            "not the online upload.")


def write_upload_map(out_dir: Path, umap: dict, channels: dict | None, max_mb: float) -> Path:
    """The upload map as a short page in the upload folder, for the attorney at the USCIS account."""
    lines = ["# Upload map", ""]
    if channels:
        lines += [f"Online filing as planned on {channels.get('on', '')}, from USCIS's list of forms you can file "
                  f"online (updated {channels['checked']['page_updated']}, checked {channels['checked']['checked']}).", ""]
    for n, s in enumerate(umap["submissions"], start=1):
        rest = [f for f in s["forms"] if f != s["lead"]]
        how = "PDF upload" if s["channel"] == "pdf_upload" else "the account's step-by-step form"
        lines.append(f"## Submission {n}: {s['lead']}{' with ' + ', '.join(rest) if rest else ''} ({how})")
        lines.append("")
        if s["channel"] == "pdf_upload":
            lines.append(f"In your representative account: File a Form Online, choose the {s['lead']}, then \"Upload a "
                         "Filled-Out PDF Form\"" + (f", and add the {', '.join(rest)} when it asks which forms to file "
                                                     "with it." if rest else "."))
        else:
            lines.append(f"In your representative account: File a Form Online, choose the {s['lead']}, and fill it out "
                         "online; it is signed electronically, and the client needs their own USCIS online account "
                         "for that.")
        if s.get("fee_waiver"):
            lines.append("Upload the fee waiver request (I-912) and all its evidence when the account asks.")
        lines.append("")
        lines += [f"- `{r['file']}`: {r['upload_as']}" for r in s["files"]]
        lines.append("")
    if umap["general"]:
        lines += ["## Evidence for the submissions", ""]
        lines += [f"- `{r['file']}`: {r['upload_as']}" for r in umap["general"]]
        lines.append("")
    if umap["unplaced"]:
        lines += ["## Not uploaded", ""]
        lines += [f"- `{r['file']}`: {r['upload_as']}" for r in umap["unplaced"]]
        lines.append("")
    if umap["paper"] and umap["paper"].get("forms"):
        lines += ["## On paper", "",
                  f"These go in a separate paper package, mailed: {', '.join(umap['paper']['forms'])}.", ""]
    lines += ["## Before you submit", "",
              "- Each form is printed, signed in ink by each signer, and scanned; upload the scan of the signed form in "
              "place of the unsigned file. An attorney's PDF upload can't be signed electronically, and a signature "
              "copied from another page isn't valid.",
              "- The name, date of birth and A-Number on each form match the client's details in the online account.",
              f"- Every file is a PDF of {max_mb:g} MB or less, not password-protected.",
              "- A PDF upload gets no receipt number when you submit it: USCIS can take up to 30 days to accept it, "
              "and sends a rejection by mail with the reason."]
    lines += [f"- {c}" for c in umap["checks"]]
    path = out_dir / UPLOAD_MAP_NAME
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# The order of a filing: payment forms, the G-1145, the cover letter
# ---------------------------------------------------------------------------
def _from_matter(key: str, matter_root: Path) -> str | None:
    """A filing copy's path in the forms step's manifest, relative to the matter folder, also when the matter
    was in another folder when the forms were built (the manifest records absolute paths)."""
    path = Path(key)
    if not path.is_absolute():
        return path.as_posix()
    if _is_within(path, matter_root):
        return path.resolve().relative_to(matter_root.resolve()).as_posix()
    parts = path.parts
    for i in range(len(parts) - 2, -1, -1):
        if parts[i] == "output" and parts[i + 1] == "deliverables":
            return "/".join(parts[i:])
    return None


def read_prepared_forms(matter_root: Path | None, warnings: list[str]) -> tuple[dict[str, dict], list[str]]:
    """The forms step's record of each filing copy (form intent manifest.json): {matter-relative path:
    {kind, pays_for, pays_what, pays_amount, fee_order}}, and the manifests read (matter-relative)."""
    if matter_root is None:
        return {}, []
    entries: dict[str, dict] = {}
    read: list[str] = []
    for path in sorted(matter_root.glob(FORMS_MANIFEST_GLOB)):
        where = _relative(path, matter_root)
        try:
            files = json.loads(path.read_text(encoding="utf-8")).get("files")
        except (OSError, ValueError, AttributeError):
            files = None
        if not isinstance(files, dict):
            warnings.append(f"The forms step's manifest {where} can't be read, so the payment forms' order wasn't "
                            "checked against it. Run the forms build again.")
            continue
        read.append(where)
        for key, entry in files.items():
            rel = _from_matter(str(key), matter_root) if isinstance(entry, dict) else None
            if rel:
                kind = str(entry.get("kind") or "").strip().lower()
                entries[rel] = {"kind": kind, **{k: entry[k] for k in FEE_KEYS if entry.get(k) not in (None, "")}}
    return entries, read


def tag_prepared_forms(items: list[Item], prepared: dict[str, dict], matter_root: Path | None) -> None:
    """Mark each item that is a filing copy the forms step prepared, with the fee a payment form pays."""
    for item in items:
        for source in item.sources:
            entry = prepared.get(_relative(Path(source["path"]), matter_root))
            if entry and entry["kind"]:
                item.prepared_kind = entry["kind"]
                if entry["kind"] in PAYMENT_KINDS:
                    item.fee = {k: entry[k] for k in FEE_KEYS if k in entry}
                break


def _front_kind(item: Item) -> str | None:
    """Where an item goes at the top of a paper packet ("payment", "g-1145", "cover_letter"), or None."""
    if item.prepared_kind in PAYMENT_KINDS:
        return "payment"
    if item.prepared_kind == ENOTICE_KIND:
        return "g-1145"
    return "cover_letter" if _is_cover_letter(item) else None


def _fee_number(order: object) -> int:
    """A fee_order as a sort key: its number, or 0 when it isn't one."""
    return order if isinstance(order, int) and not isinstance(order, bool) and order > 0 else 0


def _fee_place(item: Item) -> int | None:
    """A payment form's place in the fees tool's list (1, 2, ...), or None when the manifest gives none."""
    return _fee_number(item.fee.get("fee_order")) or None


def place_front_matter(plan: dict, items: list[Item], prepared: dict[str, dict]) -> tuple[list[Item], bool]:
    """On paper, put the top of the packet in USCIS's order, from the forms step's manifest rather than file
    names: each payment form in the fees tool's order (its fee_order), then the G-1145, then the cover letter.
    Every other item keeps the plan's order, and an item carrying an exhibit label stays where the plan put it
    (the order check says so). Without the forms step's manifest nothing moves. Returns (items, moved)."""
    if plan["filing_method"] != "paper" or not prepared:
        return items, False
    front = [(n, it) for n, it in enumerate(items) if _front_kind(it) and not it.label]

    def rank(pair: tuple[int, Item]) -> tuple[int, int, int]:
        n, it = pair
        place = _fee_place(it) if _front_kind(it) == "payment" else None
        return FRONT_RANK[_front_kind(it)], place if place is not None else 1_000_000, n

    on_top = [it for _, it in sorted(front, key=rank)]
    placed_ids = {id(it) for it in on_top}
    placed = on_top + [it for it in items if id(it) not in placed_ids]
    return placed, [id(it) for it in placed] != [id(it) for it in items]


def check_filing_order(plan: dict, items: list[Item], prepared: dict[str, dict], matter_root: Path | None,
                       warnings: list[str]) -> list[dict]:
    """Check the top of the packet against the forms step's manifest (or, without one, file names), and return
    the front matter as placed: [{index, what, file, pays_for, pays_what, pays_amount, fee_order}]."""

    def named(item: Item, form_re: re.Pattern) -> bool:
        """A form the forms step didn't prepare, known only by its number in the item's words."""
        return item.prepared_kind is None and bool(form_re.search(" ".join(filter(None, [item.label, _item_text(item)]))))

    if plan["filing_method"] == "online":
        for it in items:
            if it.prepared_kind in PAYMENT_KINDS or named(it, PAYMENT_FORM_RE):
                warnings.append(
                    f"{it.where}: an online filing is paid in the USCIS online account, so the payment form "
                    "doesn't belong in the packet."
                )
            elif it.prepared_kind == ENOTICE_KIND or named(it, ENOTICE_FORM_RE):
                warnings.append(
                    f"{it.where}: an online filing's notices come through the USCIS online account, so the G-1145 "
                    "doesn't belong in the packet."
                )
        return []

    if not prepared:
        # No record from the forms step (an older matter, or a plan outside one): check by the form number.
        first_other = next((n for n, it in enumerate(items) if not named(it, PAYMENT_FORM_RE)), len(items))
        for it in [it for n, it in enumerate(items) if named(it, PAYMENT_FORM_RE) and n > first_other]:
            warnings.append(
                f"{it.where}: a payment form goes on top of a paper packet, before the cover letter "
                "(USCIS: place the payment form on top of the package)."
            )
        return []

    front: list[dict] = []
    seen_rank = -1
    places: dict[int, list[Item]] = {}
    for it in items:
        what = _front_kind(it)
        if what is None:
            seen_rank = max(seen_rank, len(FRONT_RANK))
            continue
        entry = {"index": it.index, "what": what,
                 "file": _relative(Path(it.sources[0]["path"]), matter_root) if it.sources else None, **it.fee}
        if FRONT_RANK[what] < seen_rank:
            name = {"payment": "a payment form", "g-1145": "the G-1145", "cover_letter": "the cover letter"}[what]
            why = f" It carries the exhibit label {it.label!r}, so it was left where the plan put it." if it.label else ""
            warnings.append(
                f"{it.where}: {name} goes at the top of a paper packet: each payment form in fee order, then the "
                f"G-1145, then the cover letter.{why}"
            )
        else:
            front.append(entry)
        seen_rank = max(seen_rank, FRONT_RANK[what])
        if what == "payment":
            if _fee_place(it) is None:
                warnings.append(
                    f"{it.where}: the forms step's manifest gives no place in the fee order for this payment form; "
                    "run the forms build again with --payments to record it."
                )
            else:
                places.setdefault(_fee_place(it), []).append(it)
    for place, same in sorted(places.items()):
        if len(same) > 1:
            warnings.append(
                f"{', '.join(it.where for it in same)}: these payment forms all have place {place} in the fee order, "
                "so they are out of step with the fees tool's list. Run the forms build again with --payments."
            )
    for it in items:
        if named(it, PREPARED_PAYMENT_RE):
            warnings.append(
                f"{it.where}: this looks like a payment form, but it isn't one the forms step prepared for this "
                "matter's fees (an earlier build's copy?). Leave it out, or run the forms build again."
            )
    in_packet = {_relative(Path(s["path"]), matter_root) for it in items for s in it.sources}
    for rel, entry in sorted(prepared.items(), key=lambda kv: (_fee_number(kv[1].get("fee_order")), kv[0])):
        if rel in in_packet or matter_root is None or not (matter_root / rel).is_file():
            continue
        if entry["kind"] in PAYMENT_KINDS:
            fee = " ".join(str(entry.get(k) or "") for k in ("pays_for", "pays_what")).strip() or "a fee"
            warnings.append(
                f"The payment form for the {fee} ({Path(rel).name}) isn't in the packet. Each fee is paid with its "
                "own payment form, on top of a paper packet."
            )
        elif entry["kind"] == ENOTICE_KIND:
            warnings.append(
                f"The forms step prepared a G-1145 ({Path(rel).name}) that isn't in the packet. Put it right after "
                "the payment forms, or remove its plan if the attorney doesn't want e-notification."
            )
    return front


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Assemble a filing packet PDF from a plan JSON (see README.md).")
    ap.add_argument("plan", type=Path, help="Plan JSON file")
    ap.add_argument("--output", type=Path, help='Packet PDF path (overrides the plan\'s "output")')
    ap.add_argument("--manifest", type=Path, help="Manifest JSON path (default: <output>.manifest.json)")
    ap.add_argument("--no-stamps", action="store_true",
                    help="Leave pages unmarked (no exhibit stamps or packet page numbers)")
    ap.add_argument("--max-mb", type=float,
                    help="Shrink the packet below this size if it is larger: photos and scans are resampled "
                         "(150, then 100 dpi; scans need Ghostscript). Forms are never changed.")
    ap.add_argument("--split-max-mb", type=float, nargs="?", const=float(ONLINE_UPLOAD_MAX_MB),
                    help=f"Also write upload files for an online filing, one per evidence category, each under "
                         f"this size (default {ONLINE_UPLOAD_MAX_MB}, USCIS's per-file limit)")
    ap.add_argument("--split-dir", type=Path, help='Folder for the upload files (default: "<output stem> upload files")')
    ap.add_argument("--channels", type=Path,
                    help="The fees tool's fees.json: warns when a form is in the wrong packet of a split filing, and "
                         "with --split-max-mb the upload map says where each upload file goes in the online account")
    ap.add_argument("--table", action="store_true",
                    help="Also print the page map, one line per item (it is always in the manifest)")
    args = ap.parse_args(argv)
    for name in ("max_mb", "split_max_mb"):
        value = getattr(args, name)
        if value is not None and value <= 0:
            raise ToolError(f"--{name.replace('_', '-')} must be a positive number of megabytes.")

    plan_path = args.plan.expanduser().resolve()
    plan, items, base, warnings = load_plan(plan_path)

    def chosen(arg: Path | None, key: str) -> Path | None:
        """The command line's path, else the plan's (relative to its base), else None."""
        if arg:
            return arg.expanduser().resolve()
        return _resolve(str(plan[key]), base) if plan.get(key) else None

    out_pdf = chosen(args.output, "output")
    if out_pdf is None:
        raise ToolError('Say where to write the packet: add "output" to the plan or pass --output PACKET.pdf.')
    if out_pdf.suffix.lower() != ".pdf":
        raise ToolError(f"The packet output must end in .pdf (got {out_pdf.name}).")
    manifest_path = chosen(args.manifest, "manifest") or out_pdf.with_name(out_pdf.stem + ".manifest.json")
    source_paths = {Path(s["path"]) for it in items for s in it.sources}
    for target in (out_pdf, manifest_path):
        if target in source_paths:
            raise ToolError(f"{target} is also a source in the plan. Write the packet/manifest to a different path; sources are never overwritten.")
    stamps = plan.get("stamps", True) and not args.no_stamps
    matter_root = find_matter_root(plan_path, out_pdf, base)

    # A long assembly renews its run's lease as it works, at most once a half minute (a lease is fresh 30 minutes).
    def tick() -> None:
        if matter_root is not None:
            sign_of_life(matter_root, every=30)

    tick()

    prepared, forms_manifests = read_prepared_forms(matter_root, warnings)
    tag_prepared_forms(items, prepared, matter_root)
    items, moved = place_front_matter(plan, items, prepared)
    front = check_filing_order(plan, items, prepared, matter_root, warnings)
    split_dir: Path | None = None
    owned_uploads: set[str] = set()
    channels = load_channels(args.channels.expanduser().resolve()) if args.channels else None
    if args.split_max_mb:
        split_dir = (args.split_dir.expanduser().resolve() if args.split_dir
                     else out_pdf.with_name(f"{out_pdf.stem} upload files"))
        owned_uploads = check_split_dir(split_dir, items, matter_root, manifest_path)

    compression = None
    upload_files: list[dict] = []
    umap: dict | None = None
    with tempfile.TemporaryDirectory(prefix="sa-packet-") as tmp_name:
        tmp = Path(tmp_name)
        load_items(items, tmp, warnings, tick=tick)
        assign_roles(items, matter_root)
        if channels is not None:
            check_against_channels(plan, items, channels, warnings)
        layout(items, tmp)
        exhibits = build_packet(plan, items, out_pdf, tmp, warnings, stamps=stamps, tick=tick)
        if args.max_mb and out_pdf.stat().st_size > args.max_mb * 1_048_576:
            gs = find_ghostscript()
            original_size = out_pdf.stat().st_size
            replaced: set = set()
            for dpi in COMPRESSION_STEPS[1:]:
                readers, replaced = compressed_readers(items, tmp, dpi, gs)
                exhibits = build_packet(plan, items, out_pdf, tmp, [], dpi=dpi, readers=readers, stamps=stamps,
                                        tick=tick)
                for it in items:
                    for n, source in enumerate(it.sources):
                        source["_resampled"] = ((it.index, n) in replaced
                                                or (it.kind == "image" and n < len(it.image_downsampled)
                                                    and it.image_downsampled[n]))
                compression = {"dpi": dpi, "ghostscript": bool(gs), "from_bytes": original_size,
                               "resampled_items": sorted({it.index for it in items
                                                          if any(s.get("_resampled") for s in it.sources)})}
                if out_pdf.stat().st_size <= args.max_mb * 1_048_576:
                    break
            if out_pdf.stat().st_size > args.max_mb * 1_048_576:
                warnings.append(
                    f"The packet is still {out_pdf.stat().st_size / 1_048_576:.1f} MB after resampling to "
                    f"{compression['dpi']} dpi, over the {args.max_mb:g} MB asked for."
                    + ("" if gs else " Ghostscript isn't installed, so scanned PDFs weren't resampled.")
                )
        if split_dir is not None:
            upload_files = split_for_upload(out_pdf, items, split_dir, args.split_max_mb, warnings, owned_uploads)
            umap = upload_map(upload_files, channels, warnings)
            umap["file"] = str(write_upload_map(split_dir, umap, channels, args.split_max_mb))
            record_uploads(split_dir, [f["file"] for f in upload_files] + [UPLOAD_MAP_NAME])

    from pypdf import PdfReader

    total = len(PdfReader(str(out_pdf)).pages)
    expected = sum(it.count for it in items)
    if total != expected:
        warnings.append(f"Page count check: packet has {total} pages but items add up to {expected}.")
    size = out_pdf.stat().st_size
    if plan["filing_method"] == "online" and not upload_files and size > ONLINE_UPLOAD_MAX_MB * 1_048_576:
        warnings.append(
            f"The packet is {size / 1_048_576:.1f} MB, and each file uploaded to a USCIS online filing must be "
            f"{ONLINE_UPLOAD_MAX_MB} MB or less. Run again with --split-max-mb to write the upload files."
        )

    def source_entry(s: dict) -> dict:
        entry = {"path": _relative(Path(s["path"]), matter_root)}
        entry.update({k: v for k, v in s.items() if k != "path" and not k.startswith("_")})
        if s.get("_from_copy"):
            entry["mapped_from_working_copy"] = True
        if s.get("_resampled"):
            entry["resampled"] = True
        return entry

    manifest = {
        "packet": str(out_pdf),
        "plan": str(plan_path),
        "matter_root": str(matter_root) if matter_root else None,
        "created": _dt.datetime.now().replace(microsecond=0).isoformat(),
        "filing_method": plan["filing_method"],
        "total_pages": total,
        "file_size_bytes": size,
        "stamps": stamps,
        "notes": plan["notes"],
        "items": [
            {"index": it.index, "kind": it.kind, "label": it.label, "description": it.description, "section": it.section,
             "sources": [source_entry(s) for s in it.sources], "note": it.note, "page_count": it.count,
             "packet_start": it.start + 1, "packet_end": it.start + it.count, "bookmark": it.bookmark_title,
             "bookmark_level": it.bookmark_level, "role": it.role, "stamped": it.stamped}
            for it in items
        ],
        "exhibits": exhibits,
        # The top of a paper packet as placed, from the forms step's manifests ("checked_with"); "moved" when the
        # plan listed it in another order.
        "filing_order": {"checked_with": forms_manifests, "front": front, "moved": moved},
        "placeholders": [{"index": it.index, "label": it.label, "description": it.description, "note": it.note,
                          "packet_page": it.start + 1} for it in items if it.kind == "placeholder"],
        "compression": compression,
        "upload_files": upload_files,
        "upload_dir": str(split_dir) if split_dir else None,
        "upload_map": umap,
        "warnings": warnings,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print_summary(manifest, manifest_path, items, show_table=args.table)
    return 0


MAX_PRINTED_WARNINGS = 10


def front_matter_line(filing_order: dict) -> str:
    """The top of a paper packet in one line: "the payment forms in fee order (I-130 filing fee; I-765
    Pub. L. 119-21 fee), then the G-1145, then the cover letter"; empty when there's nothing to say."""
    front = filing_order.get("front") or []
    pays = [f for f in front if f["what"] == "payment"]
    parts = []
    if pays:
        fees = "; ".join(" ".join(str(f.get(k) or "") for k in ("pays_for", "pays_what")).strip()
                         or Path(f.get("file") or "").stem for f in pays)
        parts.append(f"the payment form{'s in fee order' if len(pays) > 1 else ''} ({fees})")
    if any(f["what"] == "g-1145" for f in front):
        parts.append("the G-1145")
    if any(f["what"] == "cover_letter" for f in front):
        parts.append("the cover letter")
    if not parts:
        return ""
    line = "on top, " + ", then ".join(parts)
    return line + ("; placed by the tool, not in the plan's order" if filing_order.get("moved") else "")


def print_summary(manifest: dict, manifest_path: Path, items: list[Item], show_table: bool = False) -> None:
    """Print a short summary; the full page map stays in the manifest (or --table)."""
    total = manifest["total_pages"]
    size_mb = manifest["file_size_bytes"] / 1_048_576
    print(f"Packet:   {manifest['packet']} ({total} page{'s' if total != 1 else ''}, {size_mb:.1f} MB)")
    print(f"Manifest: {manifest_path}")
    if show_table:
        for it in items:
            a, b = it.start + 1, it.start + it.count
            pages = f"p. {a}" if a == b else f"pp. {a}-{b}"
            what = it.label or it.description or _source_name(it)
            if it.label and it.description:
                what += f" - {it.description}"
            print(f"  {pages:<12} {it.kind:<11} {what}")
    exhibits, placeholders = manifest["exhibits"], manifest["placeholders"]
    missing = sum(1 for e in exhibits if e["to_be_supplied"])
    print(f"Items:    {len(items)}; exhibits: {len(exhibits)}" + (f" ({missing} to be supplied)" if missing else ""))
    if placeholders:
        names = ", ".join(f"{ph['label'] or 'item %d' % ph['index']} (p. {ph['packet_page']})" for ph in placeholders)
        print(f"DRAFT: {len(placeholders)} placeholder{'s' if len(placeholders) != 1 else ''}: {names}")
    order = front_matter_line(manifest["filing_order"])
    if order:
        print(f"Order:    {order}")
    if manifest["compression"]:
        c = manifest["compression"]
        print(f"Resized:  {c['from_bytes'] / 1_048_576:.1f} MB -> {size_mb:.1f} MB (images at {c['dpi']} dpi)")
    if manifest["upload_files"]:
        largest = max(f["size_bytes"] for f in manifest["upload_files"]) / 1_048_576
        print(f"Uploads:  {len(manifest['upload_files'])} files in {manifest['upload_dir']} (largest {largest:.1f} MB)")
        if manifest.get("upload_map"):
            subs = manifest["upload_map"]["submissions"]
            leads = ", ".join(s["lead"] for s in subs) or "no submission from the filing channels"
            print(f"Map:      {manifest['upload_map']['file']} ({leads})")
    warnings = manifest["warnings"]
    for w in warnings[:MAX_PRINTED_WARNINGS]:
        print(f"WARNING: {w}")
    if len(warnings) > MAX_PRINTED_WARNINGS:
        print(f"WARNING: {len(warnings) - MAX_PRINTED_WARNINGS} more in the manifest's warnings[].")
    if not show_table:
        print("Page map: the manifest's items[] and exhibits[] (or rerun with --table).")


if __name__ == "__main__":
    run_cli(main)

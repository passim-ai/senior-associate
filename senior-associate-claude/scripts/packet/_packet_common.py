"""Shared helpers for the packet tools in this folder.

Every tool here imports it; it is not run directly. It holds a user-fixable error
type, a CLI wrapper that turns errors into short instructions, reading a UTF-8
source and naming its outputs, page ranges, LibreOffice discovery and headless
conversion, and serif fonts and page numbers for reportlab.
"""
from __future__ import annotations

import atexit
import glob
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path


class ToolError(Exception):
    """A problem the caller can fix. The message says what is wrong and how to fix it."""


def run_cli(main) -> None:
    """Run main() and exit with a clear message instead of a raw traceback."""
    try:
        code = main()
    except ToolError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        sys.exit(130)
    except Exception:  # noqa: BLE001 - last-resort guard for a CLI
        traceback.print_exc()
        print(
            "ERROR: unexpected internal failure (traceback above). Check that every input "
            "file opens normally in a viewer; if it does, report the traceback.",
            file=sys.stderr,
        )
        sys.exit(1)
    sys.exit(code or 0)


def read_utf8(path: Path) -> str:
    """A text source's contents; one that isn't UTF-8 is a ToolError, not a traceback."""
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise ToolError(f"{path} is not UTF-8 text. Save it as UTF-8 and try again.") from None


def output_base(src: Path, out_dir: Path | None, name: str | None) -> tuple[Path, str]:
    """The outputs' folder (made if missing; default: the source's) and base name (default: the source's stem)."""
    folder = out_dir.expanduser().resolve() if out_dir else src.parent
    folder.mkdir(parents=True, exist_ok=True)
    name = name or src.stem
    if any(c in name for c in "/\\"):
        raise ToolError("--name must be a plain file name without folders; use --out-dir for the folder.")
    return folder, name


def page_ranges(pages: list[int], sep: str = ",") -> str:
    """[1, 2, 3, 5] -> "1-3,5": each run of consecutive pages, in the order given."""
    spans: list[list[int]] = []
    for page in pages:
        if spans and page == spans[-1][1] + 1:
            spans[-1][1] = page
        else:
            spans.append([page, page])
    return sep.join(str(a) if a == b else f"{a}-{b}" for a, b in spans)


# ---------------------------------------------------------------------------
# LibreOffice
# ---------------------------------------------------------------------------

_SOFFICE_FIXED = [
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    str(Path.home() / "Applications/LibreOffice.app/Contents/MacOS/soffice"),
    "/opt/homebrew/bin/soffice",
    "/usr/local/bin/soffice",
    "/usr/bin/soffice",
    "/usr/bin/libreoffice",
    "/usr/lib/libreoffice/program/soffice",
    "/snap/bin/libreoffice",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
]


def find_soffice() -> str | None:
    """Return a LibreOffice `soffice` executable, or None if LibreOffice is not installed.

    Order: $SOFFICE_PATH, `soffice`/`libreoffice` on PATH, then the standard install
    locations on macOS, Linux and Windows.
    """
    override = os.environ.get("SOFFICE_PATH") or os.environ.get("LIBREOFFICE_PATH")
    if override:
        if Path(override).is_file():
            return override
        raise ToolError(
            f"SOFFICE_PATH is set to {override!r}, but no file exists there. "
            "Point it at the soffice executable or unset it."
        )
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    candidates = list(_SOFFICE_FIXED) + sorted(glob.glob("/opt/libreoffice*/program/soffice"))
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    return None


_LO_PROFILE: Path | None = None


def _lo_profile() -> Path:
    """One throwaway LibreOffice profile per process (a cold profile costs several seconds)."""
    global _LO_PROFILE
    if _LO_PROFILE is None:
        _LO_PROFILE = Path(tempfile.mkdtemp(prefix="sa-lo-profile-"))
        atexit.register(shutil.rmtree, _LO_PROFILE, True)
    return _LO_PROFILE


def soffice_convert_to_pdf(src: Path, dest_pdf: Path, soffice: str, timeout: int = 240) -> None:
    """Convert a .docx/.doc/.odt/.rtf file to PDF at dest_pdf with headless LibreOffice.

    Uses a throwaway LibreOffice profile so the conversion works even when the
    LibreOffice app is already open, and copies the input to a plain file name so
    unusual characters in the original name cannot trip the converter. The source
    file is never modified.
    """
    work = Path(tempfile.mkdtemp(prefix="sa-lo-"))
    try:
        staged = work / f"input{src.suffix.lower()}"
        shutil.copyfile(src, staged)
        outdir = work / "out"
        outdir.mkdir()
        cmd = [soffice, f"-env:UserInstallation={_lo_profile().as_uri()}", "--headless", "--norestore",
               "--nolockcheck", "--nodefault", "--convert-to", "pdf", "--outdir", str(outdir), str(staged)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise ToolError(
                f"LibreOffice took longer than {timeout}s converting {src}. Close any LibreOffice "
                "dialogs that may be open and try again, or export the file to PDF by hand."
            ) from None
        except OSError as exc:
            raise ToolError(f"Could not start LibreOffice at {soffice}: {exc}") from None
        produced = outdir / "input.pdf"
        if not produced.is_file() or produced.stat().st_size == 0:
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
            raise ToolError(
                f"LibreOffice could not convert {src} to PDF"
                + (f" ({' / '.join(detail)})" if detail else "")
                + ". Open the file in Word or LibreOffice to confirm it is not damaged, "
                "or export it to PDF by hand and use the PDF instead."
            )
        dest_pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(produced), str(dest_pdf))
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------------
# Fonts for reportlab
# ---------------------------------------------------------------------------

_WIN_FONTS = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
_SERIF_SETS = [
    # (regular, bold, italic, bold italic, description)
    *[(*[f"{d}/Times New Roman{s}.ttf" for s in ("", " Bold", " Italic", " Bold Italic")], "Times New Roman")
      for d in ("/System/Library/Fonts/Supplemental", "/Library/Fonts")],
    (*[str(_WIN_FONTS / f"times{s}.ttf") for s in ("", "bd", "i", "bi")], "Times New Roman"),
    (*[f"/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman{s}.ttf" for s in ("", "_Bold", "_Italic", "_Bold_Italic")],
     "Times New Roman"),
    *[(*[f"{d}/LiberationSerif-{s}.ttf" for s in ("Regular", "Bold", "Italic", "BoldItalic")],
       "Liberation Serif (metric-compatible with Times New Roman)")
      for d in ("/usr/share/fonts/truetype/liberation", "/usr/share/fonts/truetype/liberation2",
                "/usr/share/fonts/liberation-serif", "/usr/share/fonts/liberation")],
]


@dataclass(frozen=True)
class SerifFonts:
    regular: str
    bold: str
    italic: str
    bold_italic: str
    unicode: bool  # False means reportlab's built-in Times (Latin-1/cp1252 characters only)
    description: str


_REGISTERED: SerifFonts | None = None


def register_serif_fonts() -> SerifFonts:
    """Register a Times-style family with reportlab and return its font names.

    Prefers an installed Times New Roman (or metric-compatible Liberation Serif) so
    any character renders; falls back to reportlab's built-in Times, which covers
    Western European characters only.
    """
    global _REGISTERED
    if _REGISTERED is not None:
        return _REGISTERED
    from reportlab.lib.fonts import addMapping
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for regular, bold, italic, bold_italic, desc in _SERIF_SETS:
        files = (regular, bold, italic, bold_italic)
        if not all(Path(f).is_file() for f in files):
            continue
        try:
            names = ("SASerif", "SASerif-Bold", "SASerif-Italic", "SASerif-BoldItalic")
            for name, path, (bold_, italic_) in zip(names, files, ((0, 0), (1, 0), (0, 1), (1, 1))):
                pdfmetrics.registerFont(TTFont(name, path))
                addMapping("SASerif", bold_, italic_, name)
            _REGISTERED = SerifFonts(*names, unicode=True, description=f"{desc} ({regular})")
            return _REGISTERED
        except Exception:  # noqa: BLE001 - a broken font file just means "try the next one"
            continue
    _REGISTERED = SerifFonts("Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic", unicode=False,
                             description="reportlab built-in Times (no Times New Roman or Liberation Serif found)")
    return _REGISTERED


def unsupported_chars(text: str, fonts: SerifFonts) -> set[str]:
    """Characters the fallback built-in Times cannot draw (empty when a TTF font is in use)."""
    if fonts.unicode:
        return set()
    bad = set()
    for ch in text:
        try:
            ch.encode("cp1252")
        except UnicodeEncodeError:
            bad.add(ch)
    return bad


def numbered_canvas(font: str, size: float, show):
    """A reportlab canvas class that writes "Page N of M" centered at the foot of each page for which
    show(page, total) is true. The total is known only once every page is drawn, so pages are held until then."""
    from reportlab.pdfgen import canvas

    class NumberedCanvas(canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved: list[dict] = []

        def showPage(self):  # noqa: N802 - reportlab API
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved)
            for state in self._saved:
                self.__dict__.update(state)
                if show(self._pageNumber, total):
                    self.setFont(font, size)
                    self.drawCentredString(self._pagesize[0] / 2, 36, f"Page {self._pageNumber} of {total}")
                super().showPage()
            super().save()

    return NumberedCanvas

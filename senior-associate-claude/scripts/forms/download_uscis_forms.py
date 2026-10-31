#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Download the current official USCIS form PDFs from live uscis.gov form pages.

The PDF link is resolved from the form's own page (https://www.uscis.gov/<form>)
on every run, so the file saved is whatever edition USCIS is publishing today.
The edition date shown on the page is recorded in the metadata JSON, and so is the edition
printed in the PDF's own footer (`file_edition`), which is what a kept file actually is.
Running it again merges into an existing metadata JSON rather than replacing it.

Instructions are optional for a form that publishes none (the G-1145 carries its own).

Some companion forms have no page of their own and are linked from their parent
form's page instead (the I-130A is on the I-130 page). Known companions resolve
from the parent page directly. For any other form whose own page returns 404, the
parent page is tried next (i-130a -> i-130), and the metadata records which page
the PDF and the edition date came from.

uscis.gov, and some network sandboxes in front of it, sometimes end a transfer early.
A dropped connection, a body shorter than its Content-Length, a PDF without its
closing %%EOF marker, or a 5xx response is retried twice before the form is
reported as failed. A 404 is not retried, because it means the page doesn't exist.

    uv run --script download_uscis_forms.py --output-dir DIR [--include-instructions]
        [--overwrite] [--metadata-json FILE] g-28 i-130 ...
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
USCIS_BASE = "https://www.uscis.gov"
# Seconds to wait before the second and third attempts at a fetch.
RETRY_DELAYS = (2, 5)
FORM_ID_RE = re.compile(r"^[a-z]{1,3}-\d{1,4}[a-z]{0,4}$")
PARENT_ID_RE = re.compile(r"^(?P<parent>[a-z]{1,3}-\d{1,4})[a-z]+$")
EDITION_RE = re.compile(
    r"Edition Date\s*</div>.*?<p>(?P<para>.*?)</p>",
    flags=re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")
DATE_RE = re.compile(r"\b\d{2}/\d{2}/\d{2,4}\b")


@dataclass(frozen=True)
class FormSpec:
    form_id: str
    display_name: str
    page_url: str
    pdf_name: str
    instructions_name: str
    pdf_suffix: str
    instructions_suffix: str
    # Set for a companion form that is published on its parent form's page.
    parent_id: str | None = None
    # False for a form whose page publishes no separate instructions.
    has_instructions: bool = True


def generic_spec(form_id: str, *, parent_id: str | None = None, has_instructions: bool = True) -> FormSpec:
    """Build a spec for any USCIS form that follows the standard uscis.gov layout."""
    display = form_id.upper()
    return FormSpec(
        form_id=form_id,
        display_name=display,
        page_url=f"{USCIS_BASE}/{parent_id or form_id}",
        pdf_name=f"{display}.pdf",
        instructions_name=f"{display} Instructions.pdf",
        pdf_suffix=f"/sites/default/files/document/forms/{form_id}.pdf",
        instructions_suffix=f"/sites/default/files/document/forms/{form_id}instr.pdf",
        parent_id=parent_id,
        has_instructions=has_instructions,
    )


# Companion forms with no uscis.gov page of their own (www.uscis.gov/<id> is a 404).
# Each PDF is linked from the parent form's page and shares the parent's instructions.
# Checked live on 2026-10-28. The I-864A has its own page, so it is not listed.
COMPANION_FORMS: dict[str, str] = {
    "i-130a": "i-130",  # Supplemental Information for Spouse Beneficiary
    "i-539a": "i-539",  # Supplemental Information for Application to Extend/Change Status
}

# Forms the audit and question schemas know about. Any other form id that follows
# the standard uscis.gov URL pattern (e.g. i-765, i-864a, n-400) is also accepted.
FORM_SPECS: dict[str, FormSpec] = {
    form_id: generic_spec(form_id) for form_id in ("g-28", "i-130", "i-131", "i-485", "i-864")
}
FORM_SPECS.update(
    {form_id: generic_spec(form_id, parent_id=parent) for form_id, parent in COMPANION_FORMS.items()}
)
# Forms whose page links no instructions PDF (the form carries its own). Checked live on
# 2026-10-29: the G-1145 page links only the form; the G-1450 and G-1650 pages link instructions.
NO_INSTRUCTIONS = ("g-1145",)
FORM_SPECS.update({form_id: generic_spec(form_id, has_instructions=False) for form_id in NO_INSTRUCTIONS})


def spec_for(form_id: str) -> FormSpec:
    normalized = form_id.strip().lower()
    if normalized in FORM_SPECS:
        return FORM_SPECS[normalized]
    if not FORM_ID_RE.fullmatch(normalized):
        raise SystemExit(f"Not a USCIS form id: {form_id!r} (expected something like i-765 or g-28)")
    return generic_spec(normalized)


def parent_form_id(form_id: str) -> str | None:
    """The form a lettered companion belongs to: i-130a -> i-130, i-485supj -> i-485."""
    match = PARENT_ID_RE.fullmatch(form_id)
    return match.group("parent") if match else None


class TruncatedDownload(OSError):
    """The server sent less than the whole file."""


# Failures worth another attempt. HTTPError is a URLError too; fetch_bytes handles it first.
TRANSIENT_ERRORS = (IncompleteRead, TruncatedDownload, ConnectionError, TimeoutError, URLError)


def fetch_once(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        payload = response.read()
        expected = response.headers.get("Content-Length", "")
    if expected.isdigit() and len(payload) < int(expected):
        raise TruncatedDownload(f"{url} sent {len(payload)} of {expected} bytes")
    return payload


def fetch_bytes(url: str, *, complete: Callable[[bytes], bool] | None = None) -> bytes:
    """Fetch url, retrying a transfer that drops, ends early, or fails with a 5xx.

    complete, when given, decides whether a payload is whole; one that isn't is
    retried like a dropped connection.
    """
    for attempt in range(len(RETRY_DELAYS) + 1):
        last_attempt = attempt == len(RETRY_DELAYS)
        try:
            payload = fetch_once(url)
            if complete is not None and not complete(payload):
                raise TruncatedDownload(f"{url} ended before the end of the file ({len(payload)} bytes)")
            return payload
        except HTTPError as exc:
            if exc.code < 500 or last_attempt:
                raise
        except TRANSIENT_ERRORS:
            if last_attempt:
                raise
        time.sleep(RETRY_DELAYS[attempt])
    raise AssertionError("unreachable")


def pdf_complete(payload: bytes) -> bool:
    """False for a PDF cut off before its closing %%EOF marker. Anything that isn't a
    PDF passes here, so download_file can report it as a bot-check page instead."""
    return not payload.startswith(b"%PDF") or b"%%EOF" in payload[-4096:]


def fetch_text(url: str) -> str:
    return fetch_bytes(url).decode("utf-8", "ignore")


def extract_pdf_link(page_html: str, page_url: str, preferred_suffix: str) -> str | None:
    hrefs = re.findall(r'href=(["\'])([^"\']+?\.pdf)\1', page_html, flags=re.IGNORECASE)
    normalized_hrefs = [urljoin(page_url, html.unescape(href)) for _, href in hrefs]

    for href in normalized_hrefs:
        if href.lower().endswith(preferred_suffix.lower()):
            return href

    for href in normalized_hrefs:
        if preferred_suffix.rsplit("/", 1)[-1].lower() in href.lower():
            return href

    return None


def extract_edition(page_html: str) -> tuple[str, str]:
    """Return (edition_date, edition_note) from the page's Edition Date panel, if present."""
    match = EDITION_RE.search(page_html)
    if match is None:
        return "", ""
    note = html.unescape(TAG_RE.sub("", match.group("para")))
    note = re.sub(r"\s+", " ", note).strip()
    date_match = DATE_RE.search(note)
    return (date_match.group(0) if date_match else ""), note


def fetch_form_page(spec: FormSpec) -> tuple[str, str, str | None]:
    """Return (page_url, page_html, parent_id) for the page that links the form's PDF.

    A known companion form goes straight to its parent's page. Any other form whose
    own page returns 404 falls back to the page of the form it is lettered after.
    """
    try:
        return spec.page_url, fetch_text(spec.page_url), spec.parent_id
    except HTTPError as exc:
        parent_id = None if spec.parent_id else parent_form_id(spec.form_id)
        if exc.code != 404 or parent_id is None:
            raise
    parent_url = f"{USCIS_BASE}/{parent_id}"
    try:
        page_html = fetch_text(parent_url)
    except HTTPError as exc:
        raise RuntimeError(
            f"{spec.page_url} returned HTTP 404, and the parent form page {parent_url} "
            f"returned HTTP {exc.code}"
        ) from exc
    return parent_url, page_html, parent_id


def download_form(
    spec: FormSpec, output_dir: Path, *, include_instructions: bool, overwrite: bool
) -> dict[str, str]:
    """Download one form (and optionally its instructions); return its metadata entry."""
    page_url, page_html, parent_id = fetch_form_page(spec)
    pdf_url = extract_pdf_link(page_html, page_url, spec.pdf_suffix)
    if not pdf_url:
        where = page_url if page_url == spec.page_url else f"{spec.page_url} or {page_url}"
        raise RuntimeError(f"Could not resolve the {spec.display_name} PDF link from {where}")
    edition_date, edition_note = extract_edition(page_html)

    pdf_path = output_dir / spec.pdf_name
    entry = {
        "page_url": page_url,
        "pdf_url": pdf_url,
        "pdf_path": str(pdf_path),
        "pdf_status": download_file(pdf_url, pdf_path, overwrite),
        "edition_date": edition_date,
        "edition_note": edition_note,
    }
    # The page lists today's edition; a kept file may be an older one. Its footer says which.
    file_edition = pdf_footer_edition(pdf_path)
    entry["file_edition"] = file_edition
    if file_edition and edition_date and file_edition != edition_date:
        entry["file_edition_note"] = (
            f"{spec.pdf_name} is the {file_edition} edition; the page now lists {edition_date}. "
            "Pass --overwrite to fetch the current one."
        )
    if parent_id:
        parent_display = parent_id.upper()
        entry["parent_form"] = parent_id
        entry["edition_source"] = (
            f"Edition Date panel of the {parent_display} page, which also lists "
            f"{spec.display_name}. Confirm the edition printed in the {spec.display_name} "
            "PDF footer."
        )
        if page_url != spec.page_url:
            entry["requested_page_url"] = spec.page_url
            entry["page_note"] = (
                f"{spec.page_url} returned HTTP 404; the PDF was found on the "
                f"{parent_display} page."
            )
    print(pdf_path)

    if include_instructions and not spec.has_instructions:
        entry["instructions_status"] = "none published (the form carries its own instructions)"
    elif include_instructions:
        instructions_url = extract_pdf_link(page_html, page_url, spec.instructions_suffix)
        instructions_path = output_dir / spec.instructions_name
        if not instructions_url and parent_id:
            # Companion forms share the parent's instructions (one combined PDF).
            parent_spec = spec_for(parent_id)
            instructions_url = extract_pdf_link(page_html, page_url, parent_spec.instructions_suffix)
            instructions_path = output_dir / parent_spec.instructions_name
            entry["instructions_shared_with"] = parent_id
        if not instructions_url:
            raise RuntimeError(f"Could not resolve the instructions PDF link from {page_url}")
        entry["instructions_url"] = instructions_url
        entry["instructions_path"] = str(instructions_path)
        entry["instructions_status"] = download_file(instructions_url, instructions_path, overwrite)
        print(instructions_path)
    return entry


def pdf_footer_edition(pdf_path: Path) -> str:
    """The edition printed in a form's footer ("09/18/26"), or "" when it can't be read."""
    try:
        from editions import footer_edition
    except ImportError:  # run on its own, outside scripts/forms
        return ""
    found = footer_edition(pdf_path)
    return found[1] if found else ""


def download_file(url: str, destination: Path, overwrite: bool) -> str:
    if destination.exists() and not overwrite:
        return "kept existing file (pass --overwrite to replace)"
    payload = fetch_bytes(url, complete=pdf_complete)
    if not payload.startswith(b"%PDF"):
        raise RuntimeError(
            f"{url} did not return a PDF (got {payload[:40]!r}); uscis.gov may be "
            "serving a bot-check page. Retry later or download it in a browser."
        )
    destination.write_bytes(payload)
    return "downloaded"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download the current official USCIS PDF forms from live USCIS form pages."
    )
    parser.add_argument("forms", nargs="+", help="Form ids such as g-28 i-130 i-485 i-765")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--include-instructions", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--metadata-json", type=Path, help="Optional JSON log of resolved URLs.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    metadata: dict[str, dict[str, str]] = {}
    if args.metadata_json and args.metadata_json.exists():
        try:  # merge: a later run for one form keeps the other forms' entries
            metadata = json.loads(args.metadata_json.read_text(encoding="utf-8"))
        except ValueError:
            metadata = {}
    failures = 0

    for form_id in args.forms:
        spec = spec_for(form_id)
        try:
            entry = download_form(
                spec,
                args.output_dir,
                include_instructions=args.include_instructions,
                overwrite=args.overwrite,
            )
        except Exception as exc:  # report every form, then fail at the end
            failures += 1
            entry = {"page_url": spec.page_url, "error": str(exc)}
            print(f"ERROR {spec.display_name}: {exc}", file=sys.stderr)

        metadata[spec.form_id] = entry

    if args.metadata_json:
        args.metadata_json.parent.mkdir(parents=True, exist_ok=True)
        args.metadata_json.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

# Packet tools: assemble the packet, price the filing, decide how it goes

These tools handle the fragile parts of the packet: merging, bookmarks, stamps, the exhibit index, upload files, fees and filing channels. They need only `uv`: each resolves its own Python dependencies and works from any directory. `<plugin root>` is the plugin's install folder (`${CLAUDE_PLUGIN_ROOT}`). The rules they apply (how each form goes, how fees are paid, the packet's order) are in the senior-associate skill's `references/filing.md`.

| Tool | Input | Output |
|---|---|---|
| `render_letter.py`, `letter_check.py` | The cover letter | Its `.docx`, `.pdf` and audit, and `letter check.json`: documented in `LETTER.md` beside this file |
| `assemble_packet.py` | Plan JSON (ordered items) | Packet `.pdf` with bookmarks, stamps and an index + manifest JSON (+ upload files) |
| `fees.py` | The forms, filing method and categories | Each form's fee and how to pay it, the total, notes, and each form's channel |
| `filing_channels.py` | The forms, filing method and the facts a channel depends on | How each form goes to USCIS (PDF upload, the online form, or paper), the online submissions, the paper part, e-filing mandates |
| `filing_locations.py` | The lead form and the basis it's filed on | Whether a paper filing goes to the "Attn: 1367" lockbox or the form's own address page |
| `render_document.py` | Plain Markdown with tables (the attorney memo, the client request, a checklist, a certificate) | `.pdf` and `.docx` |
| `translations.py` | The matter's document extracts index | The documents and pages that need a certified translation |

The packet assembler prints a short summary to stdout and keeps the detail in its manifest. Read the summary first and open the file only for the part you need.

Exit codes, for every tool: `0` means success. `2` means an input problem, with a one-line `ERROR: ...` on stderr that says how to fix it. `1` means an unexpected failure, with a traceback (and, from `filing_locations.py`, a form and basis the tools haven't checked). No tool changes its source files.

## 1. assemble_packet.py

```bash
uv run --script "<plugin root>/scripts/packet/assemble_packet.py" "<matter>/output/working/vault/packet/main/packet plan.json"
# optional: --output PACKET.pdf  --manifest MANIFEST.json  (override the plan)
#           --no-stamps          (leave pages unmarked)
#           --max-mb N           (shrink the packet below N MB if it is larger)
#           --split-max-mb [N]   (online filing: also write upload files of N MB or less; 12 when N is left out)
#           --split-dir DIR      (where the upload files go; default "<output stem> upload files")
#           --channels FEES.json (the fees tool's channels: the upload map, and a form in the wrong packet of a split filing)
#           --table              (also print the page map, one line per item)
```

Relative paths in the plan are resolved against the plan file's folder, or against `base_dir` if the plan sets it. In a matter, set `base_dir` to the matter folder and give every path relative to it. Items are placed in the order given, except on a paper filing in a matter: there the payment forms go first, in the fee order the forms step recorded in `form intent manifest.json`, then the G-1145, then the cover letter. The manifest's `filing_order` records the order used.

**Never point a plan at a stage workspace.** The workspace (`output/security/stage-workspaces/...`) holds temporary copies that are deleted when working files are cleaned up. A plan whose `base_dir` is inside one is refused. A single path that points at a workspace copy is read from, and recorded as, the matter's original: the workspace's `stage manifest.json` maps each copy to its original (and, when it records the original's sha256, a changed original is a warning); without that file, the copy's place under `files/` names the original. A copy whose original is gone is an error.

Top-level plan keys: `output`, `manifest`, `title`, `base_dir`, `items`, plus:

- `notes`: a list of one-line strings, copied into the manifest. Put the physical filing items here (the fee payment, passport photos, the sealed I-693 envelope, wet signatures), not as pages.
- `filing_method`: `paper` (the default) or `online`. On paper, a payment form (G-1450, G-1650, G-1651) that isn't on top of the packet is a warning. Online, a payment form in the packet is a warning, because the fee is paid in the online account, and a packet over 12 MB without `--split-max-mb` is a warning.
- `stamps`: `true` (the default) or `false`, as `--no-stamps`.

| `kind` | Keys (plus the common `label`, `description`, `section`, `bookmark`, `role`) | Pages |
|---|---|---|
| `pdf` | `path` (or `paths` list); `pages` such as `"1-3,5"`, `"4-"` or `"all"` (default `all`, one `path` only) | as selected |
| `image` | `path` or `paths` (jpg, png, heic, tiff, webp, gif, bmp); `orientation` auto/portrait/landscape; `captions`, one per path | one per image (each frame of a multi-page TIFF) |
| `docx` | `path`, `pages` (needs LibreOffice; .doc/.odt/.rtf also work) | as converted |
| `separator` | `label` (required, for example `"Exhibit A"`, printed in capitals), `description` (one line) | 1 |
| `placeholder` | `label` and/or `description`, `note` | 1, marked TO BE SUPPLIED |
| `index` | `title` (default "Index of Exhibits"); no `label` | as long as the list: each exhibit's section, label, description and its packet pages |

**Roles.** Each item is a `cover_letter`, `form`, `payment`, `exhibit` or `other`. The tool works it out (a payment form by its number, G-1450, G-1650 or G-1651; the cover letter by its name; a form by living in `output/deliverables/Forms/`, by a form-number file name in `output/deliverables/`, by a "Forms" section, by the G-1145, or by fillable fields), and `"role"` in the plan overrides it. Forms, payment forms and the cover letter are never stamped and never resampled: a filing copy is often flattened, so its fields can't identify it, and a USCIS form's own footer and barcode sit where a stamp would go.

An item without a `section` takes the section of the first item with the same label, so a document listed after its separator stays with it. An exhibit's items must sit together and in one section: a label used again after other items, or in two sections, is an error.

```json
{
  "base_dir": "/path/to/the matter folder",
  "output": "output/deliverables/Filing Packet (DRAFT).pdf",
  "title": "I-130 Petition - Jane Example for John Example",
  "filing_method": "paper",
  "notes": ["Payment: one Form G-1450 per fee, on top (in the packet as page 1).", "Two passport photos of John Example."],
  "items": [
    {"kind": "pdf", "path": "output/deliverables/Forms/G-1450 - I-130 filing fee.pdf", "description": "Form G-1450, payment of the I-130 filing fee"},
    {"kind": "pdf", "path": "output/deliverables/Forms/G-1145.pdf", "description": "Form G-1145, e-notification"},
    {"kind": "pdf", "path": "output/deliverables/Cover Letter.pdf", "description": "Cover Letter"},
    {"kind": "pdf", "path": "output/deliverables/Forms/I-130.pdf", "label": "Exhibit A", "description": "Form I-130, Petition for Alien Relative", "section": "Forms"},
    {"kind": "index"},
    {"kind": "separator", "label": "Exhibit C", "description": "U.S. passport of Jane Example", "section": "Petitioner's Citizenship"},
    {"kind": "pdf", "path": "client docs/IDs combined.pdf", "pages": "3-4", "label": "Exhibit C"},
    {"kind": "separator", "label": "Exhibit D", "description": "Residential lease naming both spouses", "section": "Evidence of Bona Fide Marriage"},
    {"kind": "placeholder", "label": "Exhibit D", "description": "Residential lease naming both spouses", "note": "Client to send the signed lease."},
    {"kind": "separator", "label": "Exhibit E", "description": "Photographs of the couple", "section": "Evidence of Bona Fide Marriage"},
    {"kind": "image", "paths": ["photos/IMG_0423.HEIC", "photos/IMG_0511.jpg"], "captions": ["Wedding, June 2024", "Anniversary dinner, June 2025"], "label": "Exhibit E"}
  ]
}
```

**Stamps.** By default every page except the forms, payment forms and cover letter gets a small stamp at its foot: exhibit pages read "Ex. F, p. 3/7 (packet p. 45 of 114)", counting every page of the exhibit's documents (not its separator, and including any unstamped form pages), and other pages read "Packet p. 2 of 114". The stamp never covers the document: the page keeps its size, its content is shrunk about 3% (clipped to what it showed before) to clear a 20-point band at the bottom, and the stamp is printed in that band with no background. A rotated page is turned upright first, so its stamp reads the right way.

**Index.** An `index` item draws the exhibit list with the packet pages of each exhibit's documents ("to be supplied, p. 40" for a placeholder, "enclosed, p. 52" for an exhibit with only a separator, such as the sealed I-693). Put it after the forms, before the first exhibit.

**Bookmarks.** Consecutive items with the same `section` share one section bookmark. Consecutive items with the same `label` form one exhibit bookmark, titled `Exhibit C - <description>`, nested under the section. When an exhibit has a separator or more than one document, each document also gets a child bookmark. Each photo of an image item with several files gets its own bookmark, titled by its caption or "Photo 2 of 5"; when the photos are the exhibit's only document, they sit directly under the exhibit. The PDF opens with the bookmark panel showing.

**Images.** Each image is fitted to a Letter page with 0.5" margins but never enlarged past one point per pixel, so a small image prints at its own size instead of blurred across the page; one under 2" on both sides is a warning that names the file. Photos are downsampled to 300 dpi.

**Size.** `--max-mb N` rebuilds a packet that is larger than N MB with photos and scanned exhibits resampled at 150 dpi, then 100 dpi, until it fits. Scanned PDFs are resampled with Ghostscript (`gs`); forms, payment forms and the cover letter are never changed. The manifest's `compression` gives the dpi and `resampled_items`, and a source is marked `resampled` only when it really was (a Ghostscript copy that failed or came out larger is not used and not marked). A packet that still doesn't fit is a warning. USCIS online filing takes files of 12 MB or less ("Files must not be larger than 12MB", uscis.gov/online-filing-options, checked 2026-10-30).

**Upload files (online filing).** `--split-max-mb [N]` also writes the packet as upload files in `<output stem> upload files/`: one file for the cover letter and for each form, whatever its section (the online account takes each form as its own PDF), and one per evidence category (each `section`), named `01 Cover Letter.pdf`, `03 Form I-485.pdf`, `07 Evidence of Bona Fide Marriage (Exhibits D-G) (part 1 of 2).pdf`, and so on: an evidence file's name carries its exhibits, so the letter's exhibit list finds it. Beside them it writes `Upload map.md`, and the manifest's `upload_map` holds the same: each online submission from `--channels` (its lead form, its companion forms, and each file with where it goes: the form PDF, a companion form, evidence, a G-28, or not uploaded), the paper part, and what to check before submitting. Given `--channels` (the fees tool's `fees.json`), it warns about a form the upload doesn't hold (the I-864, I-864A and I-130A included), fewer G-28s than the forms that need one, and a form that goes on paper; a G-28 whose name names its form (`G-28 - I-130`) is placed with that form's submission. The folder keeps a hidden record of what the tool wrote (`.upload files written.json`), so another packet's run can't orphan the upload files, and an `Upload map.md` the tool didn't write stops it like any other stranger's file. `--channels` also works on a paper packet: in a split filing, a form that goes online is a warning there. A category too large for one file is split between exhibits, and an exhibit too large between pages, so every file is N MB or less (a single page larger than N is a warning). Re-running replaces the upload files the previous run wrote (the ones the previous manifest lists) and nothing else. In a matter, `--split-dir` must be inside `output/deliverables/`; a folder holding any of the plan's sources, or an upload-named file (`NN name.pdf`) this tool didn't write, is refused before anything is written.

**Manifest.** The default path is `<output stem>.manifest.json`. It contains:

- `matter_root` (the matter folder, found as the parent of the nearest `output/` folder, or null), `filing_method`, `stamps`, `notes`, `total_pages` and `file_size_bytes`.
- `items[]`, one per item: `index`, `kind`, `label`, `description`, `section`, `sources[]`, `page_count`, `packet_start`, `packet_end`, `bookmark`, `role`, `stamped`. Each source has `path` (relative to the matter folder when it is inside it), `sha256` of the original file, `pages` used and `source_page_count`; `packet_start` for each photo of a multi-photo item; `mapped_from_working_copy` when the plan named a workspace copy; and `resampled` when `--max-mb` resampled it.
- `exhibits[]`: `label`, `description`, `section`, `packet_start`, `packet_end`, `items`, `to_be_supplied`.
- `placeholders[]`: `label`, `description`, `note`, `packet_page`.
- `compression` (or null), `upload_files[]` (`file`, `category`, `pages`, `page_count`, `size_bytes`, `exhibits`) and `upload_dir`.
- `warnings[]`.

**Stdout** is a short summary: the packet path (pages, size), the manifest path, the item and exhibit counts, a `DRAFT` line listing each placeholder's label and page, a `Resized` line after `--max-mb`, an `Uploads` line after `--split-max-mb`, and up to ten warnings (the rest are in the manifest). The page map is not printed; it is the manifest's `items[]` and `exhibits[]`, and `--table` prints it as well.

```text
Packet:   .../Filing Packet (DRAFT).pdf (114 pages, 2.8 MB)
Manifest: .../packet manifest.json
Items:    52; exhibits: 24 (5 to be supplied)
DRAFT: 5 placeholders: Exhibit 7 (p. 77), Exhibit 12 (p. 87), Exhibit 16 (p. 96), Exhibit 19 (p. 104), Exhibit 20 (p. 106)
Page map: the manifest's items[] and exhibits[] (or rerun with --table).
```

To check one exhibit, look it up in the manifest's `exhibits[]` (its pages and item indexes) rather than reading the whole file.

## 2. fees.py

```bash
uv run --script "<plugin root>/scripts/packet/fees.py" "<matter>" --forms I-130,I-130A,I-485,I-864,I-765,I-131 [--filing-method paper|online] [--category vawa | --category I-485=under14_with_parent] [the channel facts of filing_channels.py] [--output fees.json] [--json]
```

Each form is priced and paid the way `filing_channels.py` (section 6) says it goes: an online form at its online fee, paid in the account; a paper form at its paper fee, with its own payment form. An online matter with a form USCIS takes only on paper is a split filing: `split` is true, each line carries its `filing_method`, `payment_forms_needed` lists only the paper part's fees, and `channels` holds the whole channel decision (its `decisions` are the attorney's to make). The printout adds `Filing:` lines (the online submissions, the paper part) and the channels' `PROBLEM:` and `DECISION:` lines.

The fee table is Form G-1055, edition 10/26/26 (checked 2026-10-29 at https://www.uscis.gov/g-1055); a newer edition on that page means the table needs refreshing before a total is relied on. The filing method defaults to the matter's setting. A relative `--output` path is inside the matter folder, wherever the command runs from. A bare `--category` applies to every listed form that has it; `FORM=CATEGORY` to one form; `--list-categories` prints them all. An I-765 filed with a fee-paying I-485 takes the reduced fee for a pending I-485 ($260), and an I-131 filed with an I-485 is advance parole, unless a category says otherwise; an I-131 alone needs a category.

The result has one line per form (`fee`, any `additional_fees` such as a Pub. L. 119-21 fee or the I-140 Asylum Program Fee, `total`, `payments`, `payment`, `online_available`), the `total`, `payment_forms_needed` on paper (one G-1450 or G-1650 per payment), `problems` (a fact a channel still needs, or a fee the table lacks for the way a form goes), `notes`, `sources`, `split` and `channels`. A Pub. L. 119-21 fee "must be paid by separate payment concurrent with any filing fee" (G-1055), so it is its own payment: a (c)(8) renewal is two payments, $520 and $275. The I-131 follows G-1055's general fee exemptions (no fee for a VAWA self-petitioner, T, U, SIJ, an Afghan or Iraqi special immigrant, or a current or former service member; and for a refugee's reentry permit, refugee travel document or advance parole): give the group as a category (`--category vawa`), or it follows the I-485's category. Advance parole adds a note about the $1,050 Immigration Parole Fee CBP may collect on return, and its exception for a lawful adjustment applicant returning from temporary travel. The payment rules it applies are in `references/filing.md` of the senior-associate skill. An online filing is paid in the online account, which takes the payer to Pay.gov (card or bank account; G-1055 and uscis.gov/forms/filing-fees, updated 02/12/2026), so its output has no payment-form or card wording (uscis.gov doesn't say how the account collects a separate Pub. L. 119-21 fee, so the note says to follow the account's payment steps). The tool never asks for, stores or prints card or bank details.

## 3. render_document.py

```bash
uv run --script "<plugin root>/scripts/packet/render_document.py" "<matter>/output/deliverables/Filing Checklist.md" [--out-dir DIR] [--name NAME] [--formats pdf,docx]
```

Renders a plain Markdown page: `#`/`##`/`###` headings, paragraphs, `-` bullets, `1.` numbered lists, `- [ ]` and `- [x]` checklist items (an empty box for an open step, a box with a check mark for a done one), `| a | b |` tables (a `| --- |` line under the first row makes it a bold header row, repeated on each PDF page; `\|` is a literal bar), `**bold**`, `*italic*`, `---` rules, and lines of underscores to fill in by hand. HTML comments are dropped. Pages are numbered when there is more than one. A PDF is refused (exit 2, nothing written) when the text has characters the installed font can't draw, or right-to-left script; keep the Markdown alone then. Use it for the filing checklist and the translation certificate (`skills/docs-review/references/translation-certificate.md`); cover letters go through `render_letter.py`.

## 4. translations.py

```bash
uv run --script "<plugin root>/scripts/packet/translations.py" "<matter>" [--json]
```

Reads `output/working/extracts/index.json`, which `scripts/extract_documents.py` writes, and lists each client document that needs a certified English translation under 8 C.F.R. 103.2(b)(3) (its language, and "all" or the page numbers), with a suggested open-item id (the file name plus a short hash of its path, so same-named files in different folders get different items), and each document with no text layer (an image or a scan), which someone has to look at.

## 5. filing_locations.py

```bash
uv run --script "<plugin root>/scripts/packet/filing_locations.py" --form I-485 --basis vawa [--json]
```

Says whether a paper filing goes to the "Attn: 1367" lockbox (exit 0), the lead form's own address page (exit 0), or isn't known to the tools (exit 1: read the form's address page by hand and record what it says), and names the page to re-read on the day. Where a paper filing goes is the lead form's address page's call, by form and basis, not the matter's protection. The rule, read on 2026-10-29:

- **The "Attn: 1367" lockbox** for the state where the client lives (Dallas, Phoenix or Chicago, listed at https://www.uscis.gov/Certain-VAWA-T-U-Filing-Locations): the I-360 page sends a VAWA self-petition there; the I-485 page a VAWA, T, U, Cuban Adjustment Act abused spouse or child, or HRIFA battered spouse or child adjustment; the I-765 page its VAWA, T and U categories ((c)(9) with such an I-485, (c)(14), (a)(16) filed apart from the I-914, (a)(19), (a)(20), (c)(25), (c)(31), (c)(40)); the I-131 page items 5.A (with or based on such an I-485), 5.F and 5.G; and the VAWA, T and U filing page itself lists the I-102, I-192, I-212, I-290B, I-539, I-601 and I-824 filed in connection with VAWA, T or U status (all updated 10/07/2026, the day these locations took effect). The client's state of residence decides the lockbox, not the safe mailing address. USCIS accepts packages sent to a prior 1367 location only if postmarked by November 9, 2026.
- **The I-751** page (https://www.uscis.gov/i-751-direct-filing-addresses, updated 09/24/2024) sends every I-751, an abuse waiver included, to the Elgin or Phoenix "Attn: I-751" lockbox for the client's state.

Forms filed with the lead form go where it goes. Check the page on every run; a changed page means the table needs refreshing.

## 6. filing_channels.py

```bash
uv run --script "<plugin root>/scripts/packet/filing_channels.py" "<matter>" --forms I-130,I-130A,I-485,I-864,I-765,I-131 \
  [--filing-method paper|online] [--category ...] [--basis I-485=family|employment|vawa|other] [--eligibility I-765=c9] \
  [--fee-waiver FORM] [--pending-i485 online|paper] [--mandate FORM[:CATEGORY,...]=YYYY-MM-DD[=URL]] [--on YYYY-MM-DD] [--json]
```

How each form reaches USCIS, from USCIS's list of forms you can file online (https://www.uscis.gov/file-online/forms-available-to-file-online, updated 10/07/2026, checked 2026-10-30) and the online filing options page. Each form's `channel` is `pdf_upload` (the completed PDF uploaded in the attorney's account), `guided` (the account's step-by-step form; the client signs in their own account), `with` (inside another form's upload: an attorney's I-485 upload carries its concurrent I-130 or I-140, the I-765 and an advance parole I-131 as companion forms, and the I-864 and I-693, which USCIS lists both as forms that upload takes and as supporting evidence; the I-864A rides with the I-864 and the I-130A with its I-130, if the account's evidence list has them), `paper`, or `not_filed` (a G-1145 or payment form in an online filing, an I-864 with no I-485). `None` with a `needs` line means a fact is missing; it is also a `PROBLEM:`.

The matter's filing method is the attorney's preference. Online: online wherever USCIS takes the form and its category, and paper for the rest, with a `decisions` line for each form that goes on paper (a fee-exempt (c)(9) I-765, which USCIS says to mail; an N-400 with a reduced fee or fee waiver; a reentry permit or refugee travel document; an I-360 other than a VAWA self-petition; an I-485 not resting on an I-130, I-140 or VAWA I-360; a fee waiver with a form other than an I-90, I-131, I-751 or I-765; an I-140 filed with an I-907 for premium processing, which go by mail together with any I-485 filed with them; any form not on USCIS's list, such as the I-129F, I-612 and I-601). A VAWA I-360 and I-485 filed together go on paper, since the account doesn't take an I-360 with an I-485. Paper: by mail, except a form under an e-filing mandate whose day has passed, which goes online with a `decisions` line.

The result has `forms` (each with `channel`, `with`, `method`, `options`, `why`, `needs`, `mandate`), `submissions` (each online submission: `lead`, `channel`, `count` (how many filings of the lead form), `forms`, `evidence_forms`, `g28_for`, one G-28 per party and form, so a form listed twice in `--forms` counts twice, `fee_waiver`; an I-765 with a fee waiver is its own upload beside the I-485's, since the I-912 can't ride in it), `paper` (the paper part's forms), `split`, `problems`, `decisions`, `notes` (wet-ink signatures scanned for a PDF upload, no receipt number until USCIS accepts it, the I-693 envelope opened online) and `sources`.

**E-filing mandates.** Since Aug. 11, 2026, USCIS may require a form online once it has been available online for more than 180 days, after 60 days' notice on uscis.gov (8 C.F.R. 103.2(a)(1)(ii), DHS interim final rule, 91 FR 51924). `MANDATES` lists the forms USCIS has named and the first day it refuses paper; none as of 2026-10-30 (the alerts, Forms Updates, and the filing locations and online filing options updates name none). A mandate in force moves a paper form online (with its I-485 when it is a concurrent petition); one still to come is a note with the days left; one that leaves a form on paper anyway (a category that can't go online, or a companion of a paper I-485) is a `PROBLEM:`, a blocker until the notice's scope is checked. A mandate limited to categories (`--mandate I-765:c8,c11=2027-01-15`, fee categories or I-765 eligibility codes) covers only forms in them. When the list's check is more than 30 days old, a paper filing gets a note naming the pages to check; pass a notice found there as `--mandate FORM=YYYY-MM-DD=URL`. A paper filing of a mandated form needs an approved Form I-936 waiver first ($25), which DHS expects represented filers generally not to get.

## Gotchas

- **Use exact file names.** Matter files often have odd spacing, such as `Marriage certificate .pdf`. A wrong name fails, and the error names any similar file.
- **Problems are reported all together.** Every source is checked before anything is written, and all problems are listed at once: missing files, page ranges outside the file ("the file has 3 pages"), damaged PDFs, and images saved with a `.pdf` extension.
- **Password-protected PDFs.** A PDF that opens without a password but carries edit restrictions works. A PDF that needs a password to open fails. Ask for an unprotected copy.
- **Page sizes.** PDF pages keep their own size: A4 and Legal pages are never stretched, and a warning is recorded. Images are scaled to fit Letter with 0.5" margins and never enlarged past one point per pixel. Landscape images get a landscape page. Phone rotation (EXIF) is honored. Photos are downsampled to 300 dpi.
- **HEIC photos** use `pillow-heif`, which is installed automatically on macOS, Linux x86-64/arm64 and Windows x64. On other platforms, macOS falls back to `sips`. Otherwise, run with `uv run --with pillow-heif --script ...` or export the photo as JPG.
- **Fillable forms keep their values.** Each form's fields are renamed with a per-item prefix, so two USCIS forms with identical internal field names do not overwrite each other. XFA is dropped. The forms are not flattened.
- **LibreOffice** runs headless with a private profile, so it works even while the LibreOffice app is open; a `docx` item needs it.
- **Outputs.** The packet and manifest are written atomically and replaced on re-run. An output path that is also a source is refused.

## Tests

```bash
uv run --script "<plugin root>/scripts/packet/tests/test_packet_tools.py"
uv run --script "<plugin root>/scripts/packet/tests/test_filing_channels.py"
```

The tests generate their own fixtures in a temp folder. The LibreOffice, Ghostscript and `uv` CLI tests are skipped when those tools are absent.

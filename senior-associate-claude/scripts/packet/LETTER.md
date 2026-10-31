# The cover letter: render it, check it

You write the letter's words and decide the exhibit order. These two tools handle the fragile parts: `render_letter.py` turns the letter's Markdown into the `.docx` and `.pdf` and audits it mechanically, and `letter_check.py` checks its authorities, exhibits and facts against the research and the record. Each needs only `uv`, resolves its own Python dependencies, and works from any directory. `<plugin root>` is the plugin's install folder (`${CLAUDE_PLUGIN_ROOT}`). The packet, fees and filing tools are in `README.md` beside this file.

Both print a short summary to stdout and keep the detail in a file (the letter's summary JSON, `letter check.json`): read the summary first, and open the file only for the part you need. Exit `0` means success; `2` an input problem, with a one-line `ERROR: ...` on stderr that says how to fix it; `1` an unexpected failure, with a traceback. Neither changes its source files.

## 1. render_letter.py

```bash
uv run --script "<plugin root>/scripts/packet/render_letter.py" "<matter>/output/working/vault/cover-letter/<slug>/cover letter.md" \
  --profile "<path>/attorney.json" \
  --out-dir "<matter>/output/deliverables" --name "Cover Letter" \
  --summary-json "<matter>/output/working/vault/cover-letter/<slug>/cover letter audit.json"
```

- `--out-dir` defaults to the letter's folder. `--name` defaults to the `.md` file name. The outputs are `<name>.docx` and `<name>.pdf`.
- `--summary-json PATH` sets where the summary/audit goes. The default is `<out-dir>/<name>.render.json`.
- Stdout is short: the PDF (page count, renderer), the `.docx`, the summary path, one audit line (`clean` or `NOT READY`, finding and error counts, exhibit count), and the first five findings, errors first, one line each. The rest are in the summary's `findings`. `--json` prints the whole summary instead.

```text
Letter:  .../Cover Letter.pdf (7 pages, libreoffice)
Docx:    .../Cover Letter.docx
Summary: .../cover letter audit.json
Audit:   clean: 0 findings (0 errors), 24 exhibits, 0 notes
```
- `--renderer auto|libreoffice|reportlab`. With `auto` (the default), LibreOffice converts the `.docx` if it is installed: `soffice` on PATH, `/Applications/LibreOffice.app/...`, or `$SOFFICE_PATH`. Without LibreOffice, reportlab draws the same source directly. The summary's `renderer` field says which one was used. Re-rendering overwrites the previous outputs.

### Letter Markdown

| Write | Renders as |
|---|---|
| Front matter between `---` lines (keys below) | Date, delivery line, USCIS address, bold RE block, salutation |
| Paragraph (blank line between paragraphs; line wraps are joined) | 12 pt Times New Roman, justified, 0.5" first-line indent (never tabs) |
| `# I. Introduction` | Major heading, bold and underlined, rendered verbatim, so type the numeral yourself |
| `## Joint Residence` | Italic proof subhead, auto-numbered `i.`, `ii.`, ... The numbering restarts after each `#`. Any numeral you type is dropped. |
| `### Heading` | Bold, unnumbered |
| `*Matter of Laureano*`, `**bold**`, `***both***`, `<u>underline</u>` | Inline emphasis. Italic inside italic flips back to roman. Use `\*` for a literal asterisk. |
| `> quoted text` (consecutive lines) | Block quote indented 0.75" on both sides. Put the citation in the next paragraph. |
| `- item` / `1. item` | Bulleted / numbered list with hanging indent |
| A fenced ```` ```exhibits ```` block | Exhibit index. `# Section` lines become bold-underlined headers. Each `- description` gets the next label (`Exhibit A`, `B`, ... `Z`, `AA`, `BB`), and the labels run continuously across sections and across blocks. Indented lines continue the item above. **Do not type labels**: they are assigned automatically, and a hand-typed label that disagrees is reported as an error. |
| `<!-- pagebreak -->` | Page break |
| `<!-- signature -->` | Puts the signature block here instead of at the end, for example before an index that follows the signature |
| `<!-- any other comment -->` | Dropped |

Front-matter keys:

- `date` is required. If it is missing, today's date is used and a warning is recorded.
- `delivery` (italic) and `to` (list) give the delivery line and the USCIS address.
- `re` is a list. The first line follows `RE:`, and the whole block is bold.
- `salutation` defaults to "Dear Sir or Madam:" and `closing` defaults to "Respectfully submitted,".
- `signer_title` is optional, for example "Counsel for Petitioner". `cc` is an optional list.
- `exhibit_labels` is `letters` (the default) or `numbers`.
- `exhibit_start` sets the first label, for example `D` or `4`.
- `exhibit_prefix` defaults to `Exhibit` and can be set to `Tab`.
- `page_numbers` defaults to true and puts "Page N of M" on page 2 onward.
- `smart_quotes` defaults to true.
- `matter_type` sets the length budget: a key from the matter contract's "Matter types" table (`i130_i485`, `n400`, ...), or `rfe_response` / `noid_response` / `other` for no budget. `I-130/I-485` is read as `i130_i485`.
- `length_budget` overrides the budget, in words. Set it only when the attorney wants the longer letter.
- `filing_method` is `paper` (the default) or `online`. An online letter has no delivery line and no mailing address.
- `protected: true` marks a protected matter (8 U.S.C. 1367): on paper and online alike, the audit warns when the body never cites 1367 or never asks USCIS to use the safe mailing address. Being protected doesn't decide where the letter goes.
- `filing_location` names where a paper filing goes: `1367 lockbox` (the "Attn: 1367" lockbox for the client's state) or `form page` (the lead form's own address page). `lead_form` (the form whose address page decides: the I-360 for a VAWA self-petition and what's filed with it, the I-485 for an adjustment, the I-751) and `filing_basis` (`vawa`, `t`, `u`, `cuban_adjustment_abused`, `hrifa_battered`, `abuse_waiver` or `other`) say why. The audit checks the location against `filing_locations.py`'s rule (`README.md`, section 5) and the `to` block against the location: an I-751 abuse waiver named `1367 lockbox`, or a `to` block naming the 1367 lockbox for a form-page filing, is an error. A protected paper letter must give all three. Online, `filing_location` is `online` or left out.

Quote any value that contains `: ` inside a list item, for example `- "Petitioner: Jane Example"`.

Typography that happens automatically: curly quotes (a quote inside a quote opens correctly, and the apostrophe in '96 stays an apostrophe), and non-breaking spaces after `§`/`¶`, `Mr.`/`Ms.`/`Mrs.`/`Dr.` and `Exhibit`. In the PDF, citations such as `201(b)(2)(A)(i)` stay on one line. Tables and footnotes are not supported. Cite inline instead.

Complete example:

````markdown
---
date: October 28, 2026
delivery: Via FedEx Priority Overnight
to:
  - U.S. Citizenship and Immigration Services
  - Attn: I-130
  - 2501 S. State Hwy. 121 Business, Suite 400
  - Lewisville, TX 75067
re:
  - Form I-130, Petition for Alien Relative
  - "Petitioner: Jane Example (U.S. Citizen)"
  - "Beneficiary: John Example"
  - "Receipt No.: Not yet assigned"
signer_title: Counsel for Petitioner
matter_type: i130_standalone
---

# I. Introduction

Undersigned counsel represents Petitioner Jane Example ("Ms. Example"), who files the enclosed Form I-130 for her husband, John Example, under INA § 201(b)(2)(A)(i). The completed forms are enclosed. Ms. Example's U.S. passport establishes her citizenship. *See* Exhibit C.

# II. The Marriage Is Bona Fide

The question is whether the parties intended to establish a life together. *Matter of Laureano*, 19 I&N Dec. 1, 3 (BIA 1983). As the Board explained:

> Evidence to establish intent could take many forms, including ... shared residence, and experiences.

## Joint Residence

The couple has lived at 455 Sample Street since August 2024. *See* Exhibit D.

## Commingled Finances

They share a checking account. *See* Exhibit E.

# III. Index of Exhibits

```exhibits
# Forms
- Form G-28, Notice of Entry of Appearance as Attorney
- Form I-130, Petition for Alien Relative
# Petitioner's U.S. Citizenship
- U.S. passport biographic page of Jane Example
# Evidence of Bona Fide Marriage
- Residential lease naming both spouses (August 2024 – July 2026)
- Joint checking account statements, Example Federal Credit Union
```

# IV. Conclusion

We respectfully request that USCIS approve the petition.
````

### Attorney profile JSON

```json
{"attorney_name": "A. Counsel, Esq.", "firm_name": "Example Law PLLC",
 "mailing_address": "1200 Example Avenue, Suite 400, Austin, TX 78701",
 "phone": "(512) 555-0142", "email": "acounsel@examplelaw.test",
 "bar_number": "24000000", "licensing_authority": "State Bar of Texas"}
```

Every key is optional, and a missing key's line is simply left out. `mailing_address` may be a string (split into street and city lines automatically) or a list of lines. Missing `attorney_name` is an audit error, because the letter would have no signature.

### Summary / audit JSON

```json
{"ok": true, "renderer": "libreoffice", "renderer_detail": "...", "docx": "...", "pdf": "...", "page_count": 3,
 "exhibit_labels": "letters",
 "exhibits": [{"label": "A", "display": "Exhibit A", "section": "Forms", "description": "Form G-28, ...", "cited_in_body": true}],
 "finding_count": 0, "error_count": 0,
 "findings": [{"severity": "error", "title": "Exhibit cited but not listed", "detail": "..."}],
 "notes": ["..."]}
```

`findings` lists defects in the letter. **The letter is not ready while `finding_count > 0`.** Fix the `.md` and render again. The checks are:

- **Errors:** missing front matter, USCIS address block, RE block, signature, or body text; unresolved Markdown (an unmatched `*`, a stray HTML tag, or an unknown fenced block); tables or footnotes; unfilled placeholders (`[INSERT ...]`, `TBD`, `TODO`, `XXX`, `{{...}}`, `???`); an exhibit cited in the body (`Exhibit D`, `Exhibits F–H`, `Exs. 3 and 5`) that is not in the list; a hand-typed exhibit label that is duplicated or does not match its slot; an empty exhibit list; characters the fallback PDF font cannot draw.
- **Warnings:** a listed exhibit never cited in the body (checked only when the body cites at least one exhibit; exhibits under a section whose name starts with "Forms" are enclosed, not argued, and need no citation); an empty section or empty exhibit section; `#` headings numbered out of order; an unknown front-matter key (usually a typo); a missing or unreadable date; a date more than 7 days from the day the letter is rendered; an argument longer than its `matter_type` budget (the detail gives the word count); mailing details in an online filing (a protected one included), or a `filing_location` other than `online`; a protected matter that never cites 8 U.S.C. 1367 or never asks for the safe mailing address; on paper, a protected letter with no `filing_location` or no `lead_form` and `filing_basis`, and a 1367-lockbox filing whose `to` block isn't the 1367 lockbox; headings deeper than `###`. (A `filing_location` that contradicts the lead form and basis, and a `to` block naming the 1367 lockbox for a form-page filing, are errors.)

Exhibit citations are read only in the label shapes the renderer assigns: one letter or a repeated letter (`C`, `AA`) or a number. A label must end its word, so "Exhibit C, I-94 record", "Exhibit A, I&N Dec.", "Exhibits A and B, DHS records" and "Exhibit 4 and 8 C.F.R." cite only C, A, A–B and 4. A range ("A–C", "A to C", "3 through 5") needs a label at both ends, so "Exhibit A to I-485" cites A alone.

`notes` never block: renderer fallback, profile fields left out, and similar. Use `exhibits` (label, description, section) to build the packet plan; read them from the file, since stdout shows only the count.

The summary also carries `matter_type`, `filing_method`, `protected`, `filing_location` (`named`, `expected`, `lead_form`, `filing_basis`, `page`), `word_count`, `length_budget`, `letter_date`, `render_date`, and `computed_phrases`: every age or duration in the body ("29 years old", "eighteen-month marriage", "for three years") with its sentence. Each one goes stale, so recompute it from the documents as of the letter's date; the letter check (`letter_check.py`) requires a fact-table row for each.

## 2. letter_check.py

Run it after the integration pass, before the letter goes to the reviewer:

```bash
uv run --script "<plugin root>/scripts/packet/letter_check.py" "<matter>" --slug main
```

It reads, under `output/working/vault/`: `cover-letter/<slug>/cover letter.md`, `cover letter audit.json`, `exhibit plan.json` and `letter facts.json`, `research/<slug>/support matrix.json` (`--research-slug` when the research folder has another slug), and `research/chat/research notes.md` when it exists (`--letter`, `--audit`, `--plan`, `--matrix`, `--facts`, `--notes` override any path). It writes `cover-letter/<slug>/letter check.json` (`--output` to move it) and prints one line: `clean` or `NOT READY` with the error count. **The letter is ready for review only when `error_count` is 0.**

- **Authorities.** Every case (`19 I&N Dec. 1`, `596 F.3d 1115`), INA section, `8 U.S.C.` section, `C.F.R.` section, Policy Manual chapter (`6 USCIS-PM B.6`), policy memo (`PM-602-0199`) and Federal Register cite in the letter must appear in a support-matrix row's `authority`, `citation` or `pinpoint`, or in a verified entry of the matter chat's research notes. From each notes entry (a `## R<n>.` heading) the check reads only its `- Authority:` line (the full cite) and its `- Verified:` line, which must start with the date (`2026-10-29`, `10/29/2026` or `Oct. 29, 2026`) and must not record negative treatment (overruled, vacated, reversed, superseded, abrogated, negative); an entry without that, or an authority named only on its `- Adverse:` line, doesn't cover a cite. Each authority in `letter check.json` says `in_matrix` and `chat_note` (the entry id, or null). Matching is at the level of the case's first page, the section, or the chapter, so `INA § 245(a)` in the letter is covered by an `INA § 245(c)(2)` row; the pinpoint is the reviewer's to check. Short forms ("19 I&N Dec. at 3") aren't checked.
- **Exhibits.** The render audit has zero findings; the exhibit plan has the same number of exhibits, the same labels in order and the same sections as the audit (a different description is a warning); each exhibit has `sources` that exist in the matter folder, or `placeholder: true` or `physical: true` with its `open_item`.
- **Facts.** A sentence that states a date, a year, an amount, a count ("14 months of statements") or an identifier is sourced when it, or the sentence right after it, cites an exhibit, or when a fact-table entry's `text` appears in it. Years inside citations ("(BIA 1983)", "(ed. 04/01/24)") don't count. Every age or duration the render audit lists in `computed_phrases` must be in the fact table, recomputed as of the letter's date.

The fact table, `letter facts.json`, is the writer's list of the facts the letter states that its exhibits don't show on their face, each with the document that proves it:

```json
{"facts": [
  {"text": "lived together for two years", "source": "Lease 2024.pdf; Lease 2025.pdf", "as_of": "2026-10-28"},
  {"text": "opened a joint account in March 2023", "source": "Joint account statements.pdf p. 1"}
]}
```

`text` is copied from the letter (any part of the sentence), `source` names the document and page. An entry no longer in the letter is a warning.

## Gotchas

- **Use exact file names.** Matter files often have odd spacing, such as `Marriage certificate .pdf`. A wrong name fails, and the error names any similar file.
- **LibreOffice** runs headless with a private profile, so it works even while the LibreOffice app is open. The first conversion in a run takes several seconds. The editable `.docx` and the LibreOffice PDF come from the same source.
- **reportlab fallback.** Without LibreOffice, line and page breaks can differ slightly from Word. Check `page_count`. reportlab uses Times New Roman or Liberation Serif when installed. Otherwise it falls back to built-in Times, which cannot draw some accented characters (for example Vietnamese), and the audit flags them.

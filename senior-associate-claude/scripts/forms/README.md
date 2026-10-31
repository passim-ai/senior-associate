# USCIS forms tools

What the forms stages need to prepare and check USCIS PDF forms. Every tool runs with uv and needs no venv. `<plugin root>` is the plugin's install folder (`${CLAUDE_PLUGIN_ROOT}`). The separate tools `build` runs for you, the audit's checks in detail, the field-mapping notes, every known form defect and the tests are in `REFERENCE.md` beside this file: open it only when a tool fails and its message doesn't say why, or for a form with no schema.

- Python packages come from each script's inline metadata (`pypdf`, `cryptography`; USCIS PDFs are AES-encrypted). **Ghostscript** (`gs`) is required to render filing copies. The audit reads rendered text with `pdftotext` (poppler) if present, else Ghostscript; with neither, it falls back to pypdf, which can't read the fonts in rendered filing copies and reports false "not visible" errors.
- Use absolute paths and quote them. The tools write only the output paths you give them, plus each blank's field list, saved with the matter in `output/working/forms/fields/<FORM>.json` so a rerun or a reviewer can rebuild the forms later.
- No tool writes attorney, client or firm details on its own: you put every value into the question plan. `build` reads two profile keys only to check the plans: `has_uscis_online_account` and, in a protected matter, `mailing_address`.
- Every tool prints a short summary and keeps the detail in a file (the build log, the audit JSON, the field list). Pass `--full` only when you need the long form: an agent re-reads every line a tool prints for the rest of its stage.

## forms_workflow.py build (the whole pipeline)

From the question plans, `build` downloads missing blanks, writes the mappings and the intent manifest, fills with verify, renders the filing copies, audits every form and prints a summary of 25 lines or fewer.

```bash
B="<plugin root>/scripts/forms/forms_workflow.py"
uv run --script "$B" build "/abs/matter" --new "G-28 - Petitioner=g28_represented_client" \
  --new "I-130=i130_family_petition" --new "I-485=i485_family_based"    # set up: skeleton plans + blanks
uv run --script "$B" build "/abs/matter"                # plans -> filing copies + audit
uv run --script "$B" build "/abs/matter" --check-only   # reviewer: re-verify and re-audit; changes no form
```

Where everything lives (`<slug>` is the vault folder, found automatically when there is one; otherwise pass `--slug`):

| What | Where |
| --- | --- |
| Question plans, one per filing copy | `output/working/vault/forms/<slug>/plans/<Name>.plan.json` |
| Fact table (a plan's default `fact_table_path`) | `output/working/vault/forms/<slug>/form facts.json` |
| Blanks, instructions, `forms-metadata.json` (editions) | `output/working/forms/blank/` |
| Field lists | `output/working/forms/fields/<FORM>.json` |
| Mappings | `output/working/vault/forms/<slug>/mappings/<Name>.mapping.json` |
| Editable XFA sources | `output/working/forms/source/<Name> source.pdf` |
| Filing copies | `output/deliverables/Forms/<Name>.pdf` |
| Manifest, audit | `form intent manifest.json`, `prepared forms audit.json` in the vault folder |
| Build record and full detail | `build state.json`, `build log.json` in the vault folder |

- **Names.** The plan's file name is the filing copy's name: `I-130.plan.json` becomes `I-130.pdf`, `G-28 - Petitioner.plan.json` becomes `G-28 - Petitioner.pdf`. The plan's `kind` names the blank (`i-130a` → `blank/I-130A.pdf`), so two G-28 plans share one blank. A relative `fact_table_path` is read from the vault folder.
- **Setup.** `--new NAME=SCHEMA` writes the schema's skeleton as a new plan (an existing plan is never overwritten) and fetches the blank with its instructions and edition; `--blank FORM` fetches a blank that has no schema. Either one stops after setup. The first setup of a paper filing (the matter's `filing_method`, paper by default) also writes a `G-1145` plan, one per package; remove it if the attorney doesn't want the e-notification.
- **Payment forms.** `--payments FEES.json [--payment-form G-1450|G-1650]` (a relative path is inside the matter folder, where `fees.py --output` writes it) writes one payment form plan per fee listed in `payment_forms_needed` of the fees tool's output: a form's filing fee and each fee paid apart from it get their own plan, named for the form and the fee (`G-1450 - I-765 filing fee`, `G-1450 - I-765 Pub. L. 119-21 fee`), with "(1 of 2)" and so on when a form and fee repeat (two applicants' I-485s). Each plan carries `pays_for` (the form), `pays_what` (the fee), `pays_amount` and `fee_order` (its place in the fees list); the amount is filled in, and the audit checks it against `pays_amount`. Add the applicant's name (and the payer's, when the record says who pays). The card or bank details are never typed: those questions allow only `pending_signature`, and a plan that holds a value in one of those boxes, in a box that isn't its question's own, or a long number anywhere is refused before anything is written. Details typed into a payment form outside `build` are removed by the next build.
- **Only what changed is rebuilt.** A form is refilled and re-rendered when its answers (the plan's fill mapping) or its blank changed since the last build, when an output is missing or was changed outside `build`, when its last verify failed, or after an update of `xfa_tools.py`. `--force` rebuilds everything. The manifest and the audit always cover every form, because some checks compare forms (the I-130A attorney box against the G-28). The summary's first line says which forms were rebuilt and why.
- **Edits outside `build` are never thrown away silently.** When a source was changed after `build` wrote it (opened and edited in Acrobat, say), `build` compares its stored values with the answers it last wrote and with the plan's current ones. A value that matches neither is an edit the plan doesn't hold: `build` leaves that form as it is and reports "edited outside build" with the boxes. Put the change in the plan and build again, or pass `--force` to discard it. A source saved again with no change of value is simply refilled, and an edit that doesn't reach the PDF (a note, `fact_ids`, an `open_item`, the status of a question left unanswered) refills nothing.
- **Open items.** A question left `missing`, `pending_client_input`, `pending_signature`, `manual_review` or `partially_filled` may carry `"open_item": "<ledger id>"`. The audit ties that question's own error to the id, and also a form-specific absence error ("Missing ...", "... is incomplete") whose every field belongs to such questions (for a `partially_filled` question, only the boxes it leaves blank). It never ties an error about a filled question, a value, a layer, an overflow or the plan's structure. `build` then checks each tied id against the open items in `output/deliverables/open-items.json`, because the runtime accepts only those.
- **Forms the audit has no rules for** (a form with no schema) are still filled, verified and rendered; the audit JSON lists them with `"coverage": "manual"` and their unresolved questions, for a line-by-line review. The manifest holds only the forms that have a plan.
- A plan file that is removed takes its filing copy, source and mapping with it on the next build.
- **The summary**, per form: questions by status, verify OK or failed, audit errors (how many tied) and warnings; then, within the line budget, what needs work: a form that could not be built, a verify mismatch, a field-check problem (a name the form doesn't have, a checkbox value that is not an on-state), the untied errors with their fields, and fill warnings (a value longer than its box, a known form defect). Then the open-item check, a status line and the paths written.
- **Exit code** 0 when every form verified and every audit error is tied to an open item in the ledger; 1 when something needs work (the status line says what); 2 for bad input. The code is in `build_forms.py`, which takes the same arguments.
- **`--check-only`** changes no form and no preparer file. It re-verifies each source against the current plan, marks a form `stale` when its plan or blank changed since the last build, and reruns the audit into `--audit-out` (default `output/working/vault/review/<slug>/forms audit check.json`, with `forms check log.json` beside it).
- **Editions.** Every build checks each blank against the edition its schema was built for (`editions.py`): the very file (by sha256, recorded in `schemas/fields/<FORM>.json`), or a file whose footer prints the same edition and whose boxes are the same (name, kind, choices, length limit, page and place). Any other blank is **not filled**, and the summary says what to do:
  - an **older** edition than the tools know needs no decision: `--refresh-blank I-485` moves it to `blank/superseded/` and downloads uscis.gov's current blank; a plan written for the old edition is then moved with `form_question_schema.py migrate --across-editions`.
  - a **newer** edition, or a blank whose boxes don't match (try `--refresh-blank` first), is the attorney's decision: the build log holds an `attorney_decision` open item (`forms-edition-<form>`, under `summary.suggested_open_items`) to add to the list. If the attorney decides to prepare the form on that blank, `--allow-new-edition I-485=forms-edition-i-485` fills **only the boxes that are the same on it** and withholds every answer whose box changed (the manifest's `edition_check.withheld` says why for each). The audit then reports an error that no open item can explain until the plan records a box-by-box check of every box filled: `"new_edition_review": {"edition": "<the blank's edition>", "boxes": {"<box>": "<what it is on this edition>"}}`; with it, the error is tied to the attorney's decision. A withheld answer stays an error until its question is set to `manual_review` with an open item (to complete it by hand on the new edition) or its answer is taken off the plan.

## forms_workflow.py editions (is every blank current?)

```bash
uv run --script "<plugin root>/scripts/forms/forms_workflow.py" editions "/abs/matter" [--live] [--json]
```

One line per blank in `output/working/forms/blank/`: the edition printed in its footer, whether it is the edition the form tools were built for, and with `--live` what the form's uscis.gov page lists today (its Edition Date panel, with the note on which editions are still accepted). Exit 0 when every blank is current, 1 when one is not, a page could not be read, or a page was read but its edition date could not be found (never a pass).

## Question plans and schemas

- A plan has the keys `kind`, `subject`, `question_schema`, `fact_table_path`, `sources` and `questions`. Each question has `key`, `label`, `status`, `field_values`, `visible_values` (text that must show on the filing copy), `fact_ids`, `notes`, and optionally `required`, `unresolved_severity` (`error` by default; `warning` for pending signatures) and `open_item` (the ledger id that explains a deliberate gap).
- The statuses are `filled`, `partially_filled`, `not_applicable`, `pending_client_input`, `pending_signature`, `missing` and `manual_review`. Only `filled` and `partially_filled` values go into the mapping. The audit reports a `partially_filled` question's blank required boxes as still open, or, when it fills all of those, the other boxes it leaves blank (a form rule can need more, such as a prior address's move-in date). One that leaves no box blank is `filled`.
- The fact table is JSON shaped `{"matter": ..., "facts": [{"id", "subject", "key", "value", "sources", "source_kind", "notes"}]}`. Use `source_kind: "prior_prepared_form"` for facts taken from an old partial form; the audit warns when an answer rests only on such facts.
- Each question of a schema carries the form's `label`, `field_notes` where a box name misleads or a format matters, and `choices`, which give the on-state for each checkbox answer. Use the `choices` rather than guessing an on-state, and read the `field_notes` before reaching for `dump-fields`.
- `build` checks each mapping against the form's field list and lists under `field_check` any mapped name the form does not have, any `[n]` past the last box, any checkbox value that is not one of the box's on-states, and any drop-down value that is not one of its choices (a state drop-down takes `IL`, not `Illinois`).

```bash
S="<plugin root>/scripts/forms/form_question_schema.py"
uv run --script "$S" list                                          # every schema: its form, edition, and when to use it
uv run --script "$S" migrate "/abs/.../plans/I-130.plan.json" [--dry-run] [--across-editions]
```

A plan for a form the tools have a schema for must name one in `question_schema`. A plan written from an older version of its schema fails the audit with "Question plan predates its schema": don't rewrite it by hand. `migrate` copies every answer onto the current skeleton by question key and box name, keeps each status, fact, note and open item, leaves the form it fills unchanged, and prints the new questions to answer (left `missing`). The old plan is kept beside it as `<plan>.premigrate`. A plan written for another edition of the form is refused: `--across-editions` migrates it anyway, prints "EDITION CHANGE <old> -> <new>" first, and sets every question that carries an answer to `manual_review` (its old status kept in `status_before_migrate`), so the audit holds the form until each answer is checked against the new edition's instructions and its status set again.

## A closer look at one form

A filled form is a hybrid PDF with two layers that must agree: the **XFA dataset**, which Adobe Acrobat and Reader show, and the **AcroForm widgets**, which Preview, browsers, printers, Ghostscript and `pdftotext` show. The **editable XFA source** (`output/working/forms/source/`) is the filled file; the **filing copy** is its static render, with no AcroForm and no XFA: that is what you review, assemble and file. Its PDF417 barcode is the blank's, unchanged, so never describe it to the attorney as a data barcode.

```bash
T="<plugin root>/scripts/forms/xfa_tools.py"
uv run --script "$T" extract-values "/abs/G-28 source.pdf" Pt3Line5a_FamilyName [--visible | --both]
uv run --script "$T" extract-values "/abs/G-28 source.pdf" --prefix Pt3 --both   # a whole part, both layers
uv run --script "$T" dump-fields "/abs/G-28.pdf" --acro [--prefix Pt3]          # a form with no schema: what each box means
```

- `extract-values` prints `name<TAB>value`, one line per name (at most 80; `--json` for JSON); `--prefix P` adds every box whose name starts with `P`. It reads `Name` and `Name[0]` as the same node. For a `global` checkbox group, `Name` returns the group's value and `Name[n]` box n's state. `--both` compares the stored and visible layers name by name and marks each name whose values differ (`DIFFERS`). That is real, but may be harmless: some blanks carry a default in one layer only (the I-864's calculated totals hold `0.00000000` in the XFA layer of the official blank), which the same command on the blank confirms.
- `dump-fields --acro` prints each box's name, type, on-states or options, `maxlen`, page and **tooltip**, which names the real question. Use it only for a form with no schema (`form_question_schema.py list` shows which have one) or when a tool fails; `REFERENCE.md` has `fill` and the rest.
- **Render a page only for what the text check can't show:** which row of a repeated table a value landed in, clipped text, or a checkbox. At most two pages per form, at 70 dpi, into the matter's vault, and view each image once: an agent keeps every image it views for the rest of its run.

```bash
pdftoppm -r 70 -png -f 2 -l 2 "/abs/G-28 filing copy.pdf" "/abs/matter/output/working/vault/forms/<slug>/renders/g28-p"
```

## What the audit doesn't check

The audit (`audit_prepared_forms.py`, which `build` runs and `--check-only` reruns) checks each plan against its schema, the stored values against the plan, that each planned value shows on the filing copy inside its own boxes, every box's length and format, text cut off in a box, the layers, the safe mailing address in a protected matter, and each form's own rules (`REFERENCE.md` lists them). It does not check whether answers are true or match the documents; eligibility, fees or the filing address; whether uscis.gov still accepts the edition (`editions --live` does); fields outside its lists; or which box in a repeated row a value landed in, beyond its field name. Untied errors are stop conditions; warnings are open client-input or signature items, or known form defects, that must still be reported.

## Known form defects

Some USCIS editions have mistakes in the PDF itself that no mapping can work around (on the I-864, I-864A, I-765, I-129F, I-601A, I-601, I-360, I-130 and I-751). `fill` and the audit recognize each by field name and on-states and print a warning saying what to do: do that, and add the `attorney_action` item it names (usually a box the signer marks by hand). `REFERENCE.md`, "Known form defects", has each one.

## Pitfalls

- **Long answers.** A filled box neither wraps nor shrinks text on the filing copy, so text that doesn't fit is cut off; the audit names the box. Shorten a single-line answer, break the lines of a multi-line box, or continue in the form's Additional Information part, with page, part and item.
- **Non-Roman script doesn't render.** The filing copy prints "?" for each character, and the visible-value check skips values with fewer than 3 Latin letters or digits. Leave such boxes (the I-130's Part 4 items 57-58, names in native script) blank, add an open item, and have them handwritten.
- Keep the I-864 Part 3 item 5 A-Number (`P2_Line5_AlienNumber[0]`) out of `visible_values`: the text check reads that box out of order.
- Some box names contain a literal dot (`Pt8Line42.a_YesNo` on the I-485, `P9_Line7.b.` on the N-400). Use them exactly as the schema or `dump-fields --acro` gives them.

## Attorney profile

`build` finds the profile at `.senior-associate/attorney-profile.json` in the matter's parent folder (or `--profile PATH`); the keys are in the matter contract. The tools never copy its values: copy them into the plan's attorney or preparer question, and cite the profile as a fact source. The G-28 schema's `field_notes` name the profile key behind each box. `has_uscis_online_account: "no"` settles every attorney online account question: the G-28's Part 1 item 1 starts `not_applicable` in a new skeleton (and in `migrate`), and the attorney box on the other forms leaves its account number blank. A missing key leaves its fields blank, with the question `missing` (or `manual_review`), never an invented value or one from another matter. If `attorney_name` doesn't split cleanly into family and given names, ask.

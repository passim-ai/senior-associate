---
name: docs-review
description: Reviews a client's documents for a USCIS filing. It inventories what each document actually is, builds the evidence checklist for the case type from current official USCIS instructions, and reports what is present, what required items are missing, and what additional evidence would most strengthen the case. Use when an attorney asks what documents a matter has or still needs, wants a missing-documents or client intake checklist, asks for bona fide marriage evidence suggestions, or when the Immigration Packet Builder workflow reaches its docs_review stage.
---

# Document review

This review is the evidence map the rest of the packet is built on. The forms are filled from the documents it identifies, the cover letter's exhibit list grows out of its checklist, and its gaps become the client's request list. So the job is to be accurate about what each document really shows, and precise about what's missing and why it matters.

## Inputs

- The case type and filing posture (from the attorney or the orchestrator's brief). If either is missing in a direct request, ask; the checklist depends on both.
- The matter folder, or the stage workspace the orchestrator created (read its `files/` folder and `stage manifest.json`).
- `output/working/workflow/case_theory_evidence_map.json` if it exists: an intake-derived starting list of elements and evidence categories, to refine rather than trust.
- The matter's settings, from `status` or the brief: the filing method (`paper` or `online`), whether it's protected, and the client request's language.
- The document extracts: run `uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/extract_documents.py" "<matter>"` first. It writes the text of each document and `output/working/extracts/index.json` (its language and the pages not in English), and only re-reads documents that changed.

Layout, artifact names, the matter types, and the open items format are in `${CLAUDE_PLUGIN_ROOT}/skills/senior-associate/references/matter-contract.md`.

## How to work

**Inventory what's really there.** Open every client document: filenames are often wrong or vague, and a file called "passport" may be a visa page. Read the extract first when there is one, then the PDF or image itself for the pages that matter, and look directly at scanned or handwritten files, which have no extract. For each document, record what it is, whose it is, its date or the period it covers, its page count, its language, and whether it's complete, signed, legible, and unexpired where those matter. Note duplicates. Keep anything the firm generated (old drafts, prior packets, notes) separate from the client's evidence.

**Build the checklist from current official sources.** For each form in the filing, read the current USCIS form page and instructions. These are public pages, so checking them sends no client data, but run the network gate first so the check is logged (`uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/network_gate.py" "<matter>" --action official_source --role docs_review --json`). Record each URL with the date you checked it. Start from the seeds: `references/evidence-checklists.md` (the rules for every matter) and `references/checklists/<key>.md` for the case type, with its key from the contract's "Matter types". Where the official instructions differ, follow them and note the difference. For case types the seeds don't cover, build the list from the instructions and the governing regulation.

Classify each item:

- `required`: the filing or an eligibility element is unsupported without it
- `required_if_applicable`: triggered by the facts (a prior marriage, an arrest, a name change, a non-English document); say which fact triggers it
- `suggested`: strengthens bona fides, credibility, or discretion, or heads off a likely RFE
- `optional`, `not_applicable`

**Compare.** Mark each item `satisfied`, `partial`, `missing`, `unclear`, or `not_applicable`, and name the documents that satisfy it. A document that's unsigned, expired, untranslated, illegible, or covers only part of the required period is `partial`, with the reason. So is a translation short of 8 C.F.R. 103.2(b)(3) (the seeds' "Translations"): a summary, an excerpt, or a translation of some pages only. A cover letter, an old packet, or a previously prepared form isn't proof of anything. The underlying document has to be there.

**Judge strength where it's a matter of degree.** Bona fide marriage, good moral character, hardship, and continuous residence aren't checkbox items. Say how strong the current evidence is, and recommend the few additions that would add the most. Dated, objective, third-party records spread over time beat volume (see the prioritization at the end of the checklist seeds).

**Flag what the attorney needs to see.** Anything in the documents that could matter legally goes into the memo and onto the open items, even when no one asked: an arrest record, a prior removal, a status gap, inconsistent names or dates across documents, an entry without inspection.

**Translations.** Run `uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/packet/translations.py" "<matter>"`. It lists every document, and the pages, that the extracts show in another language, and every document without a text layer, which you look at yourself. For each document that needs one and has no complete certified translation in the folder, add one open item: a `client_document` ("Certified English translation of Ana's birth certificate") when the client arranges it, or an `attorney_action` when the firm translates, with `blocks_filing: true` when the document is an exhibit or proves an element. Copy `references/translation-certificate.md` for that document into your working folder, fill in the language, the document and its page count, render it with `${CLAUDE_PLUGIN_ROOT}/scripts/packet/render_document.py`, and say in the item's detail that the translator signs it. Use the item id `translations.py` suggests, so later steps update the same item. Name the language as `translations.py` gives it (`language_name`). When it marks `script_only` (Arabic, Cyrillic or Devanagari script, which write many languages), only the script is known: say "a language written in Cyrillic script" (or the script it gives) in the item, never one language, unless the document itself names its language, and leave the certificate's language line blank for the translator, who names the language they certify.

**Protected matters.** When the record shows battery or extreme cruelty, trafficking, or a qualifying crime and `status` doesn't already say protected, mark it, so the app, the forms and the handoff treat it that way from now on, and then follow `protected-matters.md` (beside the contract), which says which matters are protected:

```bash
uv run --script "${CLAUDE_PLUGIN_ROOT}/skills/senior-associate/scripts/run_matter_workflow.py" set-protected "<matter>" --on --reason docs_review --run-id <run id>
```

Say in the memo what in the record led you to mark it. Never turn protection off yourself; if you think it was set in error, add an `attorney_decision` item. For a VAWA case, `references/checklists/i360_vawa.md` has the elements, the good moral character clearances for each place lived in the last three years, the derivative children, and the care that records showing where the client lives now need.

## Outputs

Write these to `output/working/vault/docs-review/<slug>/`:

**`docs review memo.md`** for the attorney: the case type and posture; the sources checked; what's present (grouped by evidence category); what required items are missing and why each matters; partial and unclear items; the strength assessment and the highest-value additions; and the legally significant facts you noticed.

**`document inventory.json`:**
```json
{"documents": [{"path": "Marriage certificate .pdf", "type": "marriage certificate", "party": "petitioner and beneficiary",
  "date": "2022-06-18", "pages": 1, "language": "English", "condition": "complete", "categories": ["civil status", "relationship"], "notes": ""}],
 "parties": [{"name": "Jane Q. Example", "role": "petitioner", "other_names": ["Jane Sample"]},
             {"name": "John Example", "role": "beneficiary"}]}
```

`parties` lists every person the documents name in the case: the client, the spouse or fiancé(e), children, parents, the petitioner or the abuser, prior spouses, and witnesses or affiants. Give each one's given and family names as the documents spell them (`name`), any other names and spellings (`other_names`: maiden names, aliases, transliterations), and their `role` in a word or two. List people only, never an agency, court or employer. The privacy check reads this list to catch these names in step summaries before the forms exist, so include everyone even when a name seems minor.

**`docs review checklist.json`:**
```json
{"matter_type": "...", "filing_posture": "...", "review_date": "2026-10-28",
 "official_sources_checked": [{"url": "https://www.uscis.gov/i-130", "checked": "2026-10-28"}],
 "items": [{"id": "marriage-cert", "item": "Marriage certificate", "classification": "required", "status": "satisfied",
            "satisfied_by": ["Marriage certificate .pdf"], "note": "", "source": "I-130 instructions"}],
 "missing_required": ["I-94 arrival record"],
 "suggested_documents": ["Joint lease or mortgage"],
 "ambiguities": ["Two different spellings of the beneficiary's surname"]}
```
`missing_required` and `suggested_documents` must be present even when empty.

**Open items:** add each one with `uv run --script "${CLAUDE_PLUGIN_ROOT}/skills/senior-associate/scripts/run_matter_workflow.py" open-items upsert "<matter>" --item-json '<the item as JSON>' --run-id <run id>`, never by editing `output/deliverables/open-items.json` (the contract's "Open items"; if it refuses an item, fix it and run it again). Add a `client_document` item for each missing or partial required document (`blocks_filing: true`), and for each high-value suggested addition (`blocks_filing: false`). Passport photos, signatures, and the fee payment are physical filing items, non-blocking `attorney_action` items; the I-693's item, when an I-485 is in scope, blocks filing (both as the contract's "Open items" says). Use `client_question` for facts only the client can supply, `attorney_decision` for legal judgment calls (each with a `question` and your `recommendation`), and `risk` for adverse facts. The attorney reads these on screen and the client request is built from them: a title that names the document or asks the question, and a `detail` of a sentence or two on why it matters and how to get it.

Then complete the stage:
```bash
uv run --script "${CLAUDE_PLUGIN_ROOT}/skills/senior-associate/scripts/run_matter_workflow.py" complete-stage "<matter>" docs_review --run-id <run id> \
  --status passed --summary "Reviewed client documents against the evidence checklist." \
  --artifact "output/working/vault/docs-review/<slug>/docs review memo.md" \
  --artifact "output/working/vault/docs-review/<slug>/document inventory.json" \
  --artifact "output/working/vault/docs-review/<slug>/docs review checklist.json"
```

On an online filing, write the checklist for upload: every document is a scan (the I-693 included, with the original kept), and nothing goes in for payment. Missing documents don't block this stage; they're its findings. Use `--status blocked` only when there's nothing reviewable at all.

When the attorney asks for a quick review in conversation rather than a workflow stage, answer in chat in the same order (present, missing, suggested, issues), naming documents in words rather than by path, and offer to save the files.

## Reconcile the case and any notice

Before downstream work, read `output/working/workflow/case_theory_evidence_map.json`. Correct the requested benefit, expected forms, eligibility elements and evidence categories for this exact matter; set `reconciled_at` only after that comparison. Never let a shared word such as waiver substitute an I-751 theory for an I-601A, I-601, I-612 or NIW. Check the matter's forum, circuit and jurisdiction basis. Missing information becomes a blocking question.

For an RFE or NOID, follow `../senior-associate/references/notice-responses.md` and prepare the notice response plan.

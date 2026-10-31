---
name: coverletter
description: Writes, researches, and reviews the cover letter for a USCIS filing, from the client's documents, the prepared forms, and verified legal authority. The letter states the relief, the legal basis, and the exhibit that proves each element. Use when an attorney asks to draft, revise, strengthen, or check a cover letter, waiver letter, RFE or NOID response letter, or interview supplement, or when the Senior Associate workflow reaches one of its cover letter stages.
---

# Cover letter

The cover letter is the packet's argument. It tells the officer exactly what's being requested and under what law, walks through each element with the exhibit that proves it, and answers the obvious doubt before the officer raises it. A good letter makes approval the easy path. A bad one, with a misstated fact, an exhibit that isn't there, or a citation that doesn't say what the letter claims, gives the officer a reason to look harder.

The work has three roles, and in the workflow each runs as its own agent: the **writer** drafts and later integrates research, the **researcher** finds and verifies authority, and the **reviewer** checks the result independently. The brief says which role you're playing.

In every role, add or change an open item with `uv run --script "${CLAUDE_PLUGIN_ROOT}/skills/senior-associate/scripts/run_matter_workflow.py" open-items upsert "<matter>" --item-json '<the item as JSON>' --run-id <run id>`, and add a history line with `... open-items note "<matter>" <id> "<line>" --run-id <run id>`, never by editing `open-items.json` (the matter contract's "Open items"). When your work touches an item that's already listed (the letter cites it as a placeholder exhibit, research changes what it needs), add a note to it, and change its `detail` only if what's needed changed. Never put a path, a finding id, or a role name in an item's text.

Shared references:
- `references/letter-craft.md`: structure, proof blocks, the exhibit list, tone, and citation form (writer and reviewer)
- `references/research.md`: the research method and the authority pack and support matrix formats (researcher)
- `references/authorities/<key>.md`: the vetted standard authorities for the case type, keyed as in the matter contract's "Matter types"
- `${CLAUDE_PLUGIN_ROOT}/scripts/packet/LETTER.md`: the letter's Markdown dialect, `render_letter.py` and `letter_check.py`
- `${CLAUDE_PLUGIN_ROOT}/skills/senior-associate/references/matter-contract.md`: layout, matter types, open items, findings, and the attorney profile

## Writer

**Before drafting,** pin down the exact request (benefit, form, posture) and the legal mechanism, and gather what the letter rests on:

- the docs review (what each document is and what's missing)
- the filled forms (the letter's facts must match them exactly)
- the case theory map
- the attorney profile (for the letterhead and signature)

If the brief names a folder of the firm's model letters, follow the closest model letter's structure, headings, and tone, because that's the firm's house style. Otherwise use the default format in `letter-craft.md`. Either way, the letter's length follows the budget in `letter-craft.md`.

**Draft** in the Markdown dialect from `LETTER.md`, saved as `output/working/vault/cover-letter/<slug>/cover letter.md`. The integration pass and any revision start from this file. Put `matter_type` (the case type's key, such as `i130_i485`) and `filing_method` (`paper` or `online`, from the brief or the matter's settings) in the front matter. Date the letter for the day it will be signed. Render it:

```bash
uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/packet/render_letter.py" "<matter>/output/working/vault/cover-letter/<slug>/cover letter.md" \
  --profile "<attorney profile path>" --out-dir "<matter>/output/deliverables" --name "Cover Letter" \
  --summary-json "<matter>/output/working/vault/cover-letter/<slug>/cover letter audit.json"
```

The command prints the output paths, one audit line (`clean`, or `NOT READY` with the finding and error counts) and the first few findings. The full audit, the exhibit list and the notes are in `cover letter audit.json`; open it only for the findings or exhibits you need. The letter isn't done until the audit line reads `clean` (`finding_count` is zero), so fix the source and render again. Let the renderer number the exhibits (don't type labels), and cite every evidence exhibit at least once in the body, where it proves something. A range such as "*See* Exhibits A–C" counts, and an exhibit that's listed but never cited is a finding. Exhibits under a section named "Forms" are enclosed, not argued, so don't write filler such as "*See* Exhibits 1–2" just to cite them. The audit also warns when the letter runs past its matter type's word budget, when the date is more than a week from today, and, for an online filing, when the letter carries mailing details. Look at the rendered PDF before you hand it on.

- Every fact comes from a document, not a filename and not a summary. Write dates, names, and numbers exactly as the documents and forms have them. Keep `letter facts.json` next to the letter source: each fact the letter states that its cited exhibit doesn't show on its face, and every age or duration ("29 years old", "married for three years", which the audit lists in `computed_phrases`), with the document that proves it, computed as of the letter's date. The letter check reads it.
- Build the exhibit list from the evidence, grouped by what each exhibit proves. Record it in `exhibit plan.json` next to the letter source, with the label, description, source paths, and section, plus `placeholder: true` and the open item id for evidence still to come. After each render, make the plan's labels, sections and descriptions match the `exhibits` in `cover letter audit.json`, which are in the same order. Packet assembly builds from this plan, so the letter and the packet can't drift apart. Describe each exhibit by what it is ("Form I-130, Petition for Alien Relative"), not by the fee that goes with it: on paper the payment forms sit on top of the packet, outside the exhibit list, and online the fee is paid in the account.
- When a strong argument needs evidence the record lacks, write the argument around the evidence that exists. Add the missing piece to the exhibit plan as a placeholder, and add a `client_document` open item.
- Cite standard propositions straight from the case type's authorities file, and list in `propositions.json`, next to the letter source, only the propositions that still need research (id, the proposition in one sentence, where it appears). Draft each sentence so it reads well with or without a citation.
- Address the adverse fact an officer will notice in this record (a short courtship, a gap in joint records, a prior overstay) with the evidence that answers it. If how to handle it is a strategy call, write the stronger version, and add an `attorney_decision` item: a `question` naming the choice, your `recommendation`, and the alternative in a sentence of `detail`.
- Don't pre-empt an issue the record doesn't raise. If you think the officer might ask about something the documents don't show (a gap you're only guessing at, a ground the facts don't suggest), write the leaner letter and add an `attorney_decision` item asking whether to address it, recommending the leaner letter unless you have a reason in the record.

For an **online filing**, the letter is uploaded with the forms: address it as `letter-craft.md` says, leave out mailing logistics (payment forms, the sealed envelope, assembly order), and mention the I-693 as uploaded, if it's in scope.

In a **protected matter** (`status` or the brief says so), follow `protected-matters.md` (beside the matter contract), "The cover letter" and "Where a paper filing goes": on paper, run `uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/packet/filing_locations.py" --form <lead form> --basis <basis>` and check the page it names today.

**Integration pass:** read the authority pack and support matrix. Cite what the researcher verified, where it strengthens the argument. Rewrite or drop propositions the research didn't support, including any file entry the currency check flagged. Never add an authority that isn't in the support matrix. Re-render, update `cover letter audit.json` and `letter facts.json`, and then run the letter check:

```bash
uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/packet/letter_check.py" "<matter>" --slug <slug> [--research-slug <research slug>]
```

It writes `output/working/vault/cover-letter/<slug>/letter check.json`: every authority the letter cites is in the support matrix (or verified in the chat research notes), the exhibit plan matches the audit's exhibits, and every dated or numeric fact cites an exhibit or appears in `letter facts.json`. The letter goes to the reviewer only when its `error_count` is 0, so fix the letter, the plan or the fact table and run it again. Don't loosen a fact to dodge the check; give it its source.

## Researcher

Make every legal sentence in the letter defensible, spending research only where this client differs from the usual case: start from the case type's authorities file and the matter's chat research notes, check that they're still current, and research only the entries in `propositions.json` that they don't cover. `references/research.md` is the whole method: the currency check, the network gate, the call budget, keeping results small, what to do without the connector, and the output formats. Write `authority pack.md` and `support matrix.json` to `output/working/vault/research/<slug>/`. Don't edit the letter.

## Reviewer

Read the letter as a skeptical senior attorney who didn't write it.

- **Facts:** every fact matches the documents and the filled forms, including names, dates, A-numbers, and receipt numbers.
- **Request and law:** the relief and mechanism are right for the forms filed, and every citation appears in the support matrix (or in a verified entry of the chat research notes) and says what the sentence claims. Spot-check the most important ones at the source. Any case whose matrix row says `treatment not checked` gets a finding owned by `attorney` unless its "Check that ... is still good law" item is open.
- **Exhibits:** each exhibit the body cites is in the list, and each list item is in `exhibit plan.json`. Placeholders are clearly marked and tied to open items.
- **Advocacy:** each element is argued with its proof, the obvious doubt is answered, and nothing is overstated (no "clearly eligible" or "no issues" unless the record shows it).
- **Form:** `cover letter audit.json` shows zero findings, `letter check.json` shows zero errors and is newer than the letter source, and the rendered PDF looks like a professional law-firm letter. A letter longer than its budget, or one that argues an issue the record doesn't raise, is a finding for the writer unless the attorney asked for it.

Write `cover letter review memo.md` and `cover letter review findings.json` to `output/working/vault/cover-letter/<slug>/`, using the findings format from the matter contract. The owner is `cover_letter_writer_integrate` for text, `forms_preparer` for a form/letter mismatch that's the form's fault, and `client` or `attorney` as usual. Don't fix the letter yourself.

**On a re-review** (the brief says this is a re-review after fixes), read your previous memo and findings, then see what changed since your last pass:

```bash
uv run --script "${CLAUDE_PLUGIN_ROOT}/skills/senior-associate/scripts/run_matter_workflow.py" changed-since "<matter>" cover_letter_reviewer
```

Check only that each earlier finding was fixed, and review whatever changed. Don't re-review unchanged parts of the letter, because a second full pass repeats work the first one already did. Update the memo and findings: close what was fixed, keep what's still open with its owner, and add anything new in the changed material.

**When the brief asks for a fresh, full review** (the attorney redid this step), review the whole letter as on a first review, whatever changed. `changed-since "<matter>" cover_letter_reviewer --fresh` lists your previous findings for reference only: carry over or close each one in your new findings.

## Completing the stages

Each stage passes its artifacts from the matter contract's "Stages, owners, and required artifacts":

```bash
uv run --script "${CLAUDE_PLUGIN_ROOT}/skills/senior-associate/scripts/run_matter_workflow.py" complete-stage "<matter>" <stage> --run-id <run id> \
  --status passed --summary "<one line, no client identifiers>" --artifact "<path>" [--artifact "<path>" ...]
```

The reviewer stage passes only when the audit shows zero findings, the letter check shows zero errors, and every open `blocker`, `major` or `manual_review` finding has an owner. When the attorney asks for letter work directly, outside the workflow, play all three roles in order, and keep the reviewer's pass honest.

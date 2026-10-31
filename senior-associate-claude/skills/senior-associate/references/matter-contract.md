# Matter contract

Every skill in this plugin reads and writes the same matter folder layout. That's what lets one stage hand work to the next, the workflow runtime check that a stage really produced what it claims, and the attorney's dashboard show progress.

`<plugin root>` below is the plugin's install folder (`${CLAUDE_PLUGIN_ROOT}`; an Immigration Packet Builder brief states it). `<run id>` in a command is the run id in your brief; asked outside the workflow, with no run id, leave `--run-id` out.

Two references beside this file hold rules only some matters need: `protected-matters.md` when the matter is protected (see "VAWA and other protected cases" below), and `filing.md` for how each form goes to USCIS, the fees and payment, and the packet's order.

## Folder layout

```
<matter folder>/                     the client's documents, anywhere outside output/
  output/
    deliverables/                    what the attorney receives
      Filing Packet.pdf              or "Filing Packet (DRAFT).pdf" while anything blocks filing
      Cover Letter.docx              and Cover Letter.pdf
      Forms/                         one filing copy per prepared form, e.g. "I-130.pdf", "G-28 - Petitioner.pdf"
      Attorney Memo.md               and Attorney Memo.pdf, rendered from it
      Client Request.md              and Client Request.pdf, rendered from it
      open-items.json
    working/                         everything the stages produce along the way
      workflow/matter_status.json    stage state; the runtime owns this file
      workflow/attorney-instructions.md   the attorney's standing instructions; the app or the matter chat writes it, stages only read it
      workflow/chat-changes.json    changes the attorney made in chat; chat_changes.py writes it, stages only read it
      workflow/run-lease.json        who is working on the matter now (the run lease); the runtime and the app write it
      workflow/attorney-actions.jsonl   the attorney's Mark done, Reopen and Accept this risk; apply-attorney-actions merges them
      workflow/matter-meta.json      the matter's settings (protected, filing method, client language, archived); read them from `status`
      workflow/events.jsonl          the matter's timeline
      workflow/snapshots/            file hashes taken when each stage passed, for changed-since
      workflow/case_theory_evidence_map.json
      extracts/                      the text of each client document and index.json (extract_documents.py)
      forms/                         downloaded blank forms, instructions, editable form files
      vault/<area>/<slug>/           stage artifacts: memos, findings JSON, fact tables, research
      vault/research/chat/research notes.md   authorities verified while the attorney talked the matter through
      vault/scratch/                 a stage's scratch that holds client facts; closeout deletes it
      pdf/tmp/  doc/tmp/  images/tmp/   scratch; closeout deletes these
    privacy/  security/              policy, access log, stage workspaces, quarantine, closeout report
```

Client documents are evidence. Read them where they are and never rename, move, or edit them. When a document needs a converted copy (OCR text, a HEIC photo turned into a PDF, one page split out), write the copy under `output/working/` and keep pointing at the original as the source.

**Paths are matter paths.** Every path a stage writes into a plan, a manifest, findings, or any other JSON is relative to the matter folder (`From client/Passport.pdf`, `output/deliverables/Forms/I-130.pdf`), never a stage workspace's copy: closeout deletes workspaces, and the runtime and the packet assembler refuse JSON that points into one. The workspace's `stage manifest.json` maps each copy to its original.

Keep exactly one current version of each deliverable. When a stage replaces the packet, the letter, or a form, overwrite or remove the old file so the attorney never has to wonder which one is current. Use a short, stable `<slug>` for vault folders, such as `main` or the principal's surname.

## Attorney profile

The attorney's own details (for the G-28, preparer blocks, the letterhead, and the signature block) live in `.senior-associate/attorney-profile.json` inside the matters folder (`${user_config.matters_root}`, normally the matter folder's parent). The app writes it from its "Your details" screen, and the brief names its path. Keys, any of which may be missing: `attorney_name`, `firm_name`, `mailing_address`, `phone`, `email`, `bar_number`, `licensing_authority`, `uscis_online_account_number`, `has_uscis_online_account`, `subject_to_discipline_order`, `discipline_order_details`.

- `has_uscis_online_account` is `yes` or `no`. With `no`, every question about the attorney's USCIS online account is not applicable: leave it blank and raise no open item for it.
- `subject_to_discipline_order` (`no` or `yes`) answers the G-28's Part 2 item 1.c, whether an order restricts the attorney's practice of law; with `yes`, `discipline_order_details` goes in the G-28's Part 6. When the key is missing, leave item 1.c blank and add the usual `attorney_action` item; never assume "am not".
- Use only what the profile says. If a detail a form or the letter needs is missing, leave it blank and add an `attorney_action` item asking the attorney to add it in "Your details". Never fill counsel fields from anything else in the folder; a prior filing may carry another attorney's details.

## Attorney instructions

`output/working/workflow/attorney-instructions.md`, when it exists, is what the attorney typed into the app's "Additional attorney instructions" box for this matter, in their own words. They hold for every run and every stage until the attorney changes them. When a brief names the file, read it before you start and follow it in your stage's work: what to lead with, what to leave out, how the letter argues, which optional forms to include.

Instructions direct the work; they don't remove a stage or replace the record. If one would contradict the client's documents or misstate the law, don't do that part. Add an `attorney_decision` open item that says what you did instead and why, and carry on. A fact the attorney states there that the documents don't contradict ("the couple met in Lisbon in May 2025") is the attorney's word: use it, and name the instructions as its source.

## Changes made in chat

The attorney can talk a matter through with Claude (the matter-chat skill) and have it change the work directly: the letter, a form, the open items, the memo. Each change is recorded in `output/working/workflow/chat-changes.json`, as `{"changes": [{"at": "<UTC time>", "what": "Cover letter: leads with the joint lease", "files": ["<path relative to the matter>"]}]}`, and the app lists the ones made since a step last passed. A change made in chat is the attorney's decision. When a brief lists them, keep each one, re-run the reviews after the earliest step whose work it touched (as re-reviews, with changed-since), and don't undo it. If one contradicts the documents or the law, add an `attorney_decision` item instead of reverting it.

## Stages, owners, and required artifacts

The runtime refuses to mark a stage `passed` until every artifact listed here exists and is well formed; its message says what to fix. Pass each one to `complete-stage` with `--artifact`.

| Stage id | Skill (agent) | Required artifacts |
| --- | --- | --- |
| `docs_review` | docs-review | `docs review memo.md`, `document inventory.json`, `docs review checklist.json` in `vault/docs-review/<slug>/` |
| `forms_preparer` | forms-preparer | `form facts.json`, `form intent manifest.json`, `prepared forms audit.json` (every error either fixed or tied to an open item about the same form) in `vault/forms/<slug>/`; at least one filing copy in `deliverables/Forms/` |
| `forms_reviewer` | forms-reviewer | `forms review memo.md`, `forms review findings.json` in `vault/review/<slug>/` |
| `cover_letter_writer_draft` | coverletter (cover-letter-writer) | `Cover Letter.docx` or `.pdf` in `deliverables/` |
| `cover_letter_researcher` | coverletter (cover-letter-researcher) | `authority pack.md`, `support matrix.json` in `vault/research/<slug>/` |
| `cover_letter_writer_integrate` | coverletter (cover-letter-writer) | the updated `Cover Letter.docx` or `.pdf`, `cover letter audit.json` (zero findings), and `letter check.json` (`error_count` 0, written by `scripts/packet/letter_check.py` after the letter's last change) in `vault/cover-letter/<slug>/` |
| `cover_letter_reviewer` | coverletter (cover-letter-reviewer) | `cover letter review memo.md`, `cover letter review findings.json`, `cover letter audit.json` (zero findings), and `letter check.json` (zero errors, run after the letter's last change) in `vault/cover-letter/<slug>/` |
| `packet_assembly` | packet-assembly | `Filing Packet.pdf` or `Filing Packet (DRAFT).pdf` in `deliverables/`, `packet manifest.json` in `vault/packet/<slug>/` |
| `final_review` | final-review | `final review memo.md`, `final review findings.json` in `vault/final-review/<slug>/` |
| `attorney_handoff` | senior-associate | `Attorney Memo.md` and `.pdf`, `Client Request.md` and `.pdf`, `open-items.json` in `deliverables/`; once a packet exists, `Filing Checklist.md` and `Filing Checklist.pdf` there too |

All vault paths are under `output/working/`.

## Matter types

The case type maps to one key, which names the case type's authorities file (`skills/coverletter/references/authorities/<key>.md`), its evidence checklist (`skills/docs-review/references/checklists/<key>.md`), its officer theories (`skills/final-review/references/theories/<key>.md`), and the letter's `matter_type` front matter.

| Workflow `matter_type` | Key |
| --- | --- |
| I-130/I-485 immediate relative packet | `i130_i485` |
| I-130 stand-alone petition | `i130_standalone` |
| I-751 joint petition to remove conditions | `i751_joint` |
| I-751 waiver petition | `i751_waiver` |
| N-400 naturalization packet | `n400` |
| I-765 employment authorization packet | `i765` |
| I-131 travel document packet | `i131` |
| I-129F fiancé(e) petition packet | `i129f` |
| I-612 waiver packet | `i612` |
| I-601A provisional unlawful presence waiver packet | `i601a` |
| I-601 waiver of inadmissibility packet | `i601` |
| I-140 national interest waiver petition packet | `i140_niw` (with `i140_i485` A7–A9 when an I-485 goes with it) |
| I-140/I-485 employment-based packet | `i140_i485` |
| I-485 adjustment of an asylee or refugee (INA 209) | `i485_asylee_refugee` |
| I-360 VAWA self-petition packet | `i360_vawa` |
| I-360/I-485 VAWA self-petition and adjustment packet | `i360_vawa` |

A case type with no key here has no seeded files: build from the current instructions and the governing law, and say so.

## Findings JSON (review stages)

Forms review, cover letter review, and the final review write findings in this shape. The final review adds an `outcome` to each merits risk, plus `decision` and `overall_outcome` at the top level (see the final-review skill).

```json
{
  "reviewed_at": "2026-10-28",
  "findings": [
    {
      "id": "F1",
      "severity": "major",
      "title": "I-485 last-arrival date differs from the I-94",
      "detail": "Form says 2023-03-14; the I-94 in Passport.pdf p.3 shows 2023-03-12.",
      "source": "Passport.pdf p.3; USCIS I-485 instructions (checked 2026-10-28)",
      "fix": "Correct Part 1 item 23 to 2023-03-12.",
      "owner": "forms_preparer",
      "status": "open"
    }
  ]
}
```

- `severity`: `blocker` (can't responsibly file), `major` (fix before filing), `minor` (real but not outcome-changing), `manual_review` (needs attorney judgment or facts the record lacks).
- `outcome` (final review, for merits risks): `deny_likely`, `noid_likely`, `rfe_likely`, `attorney_hold`, `approvable`.
- `id`: stable across re-reviews, so a re-review can mark each earlier finding fixed or still open. The final review requires one.
- `owner` is the stage id that fixes it, or `attorney` or `client`. The runtime refuses to pass a review whose open `blocker`, `major`, or `manual_review` findings lack an owner, reading `critical` and `high` as `blocker` and any word it doesn't know as material. For the final review, the same goes for findings with any outcome except `approvable`. A passed review records how many material findings it left open, and whose.
- `status`: `open` or `resolved`. When a reroute fixes something, the reviewer that re-checks it marks it `resolved` and adds a one-line `resolution`.

## Open items

`output/deliverables/open-items.json` is the single list of everything that still stands between this packet and filing, plus the risks the attorney should weigh. Every stage that finds a gap adds to it, and the handoff reconciles it. The app shows it as written: each decision as a question with an answer box and your recommendation, the rest on its "What's left" screen. So `title`, `question`, `recommendation`, and `detail` are text the attorney reads, and `notes` is where the history goes.

```json
{
  "schema_version": 2,
  "updated_at": "2026-10-28T15:04:00Z",
  "packet_status": "draft",
  "items": [
    {
      "id": "doc-i94",
      "type": "client_document",
      "title": "Luis's I-94 arrival record",
      "detail": "Proves he was admitted, which adjustment requires, and gives the I-94 number the I-485 asks for. He can print it free at i94.cbp.dhs.gov.",
      "needed_for": "I-485 Part 1 items 12 and 15; INA 245(a)",
      "blocks_filing": true,
      "status": "open",
      "stage": "docs_review",
      "notes": ["Forms: left the I-94 number blank on the I-130 and I-485.", "Cover letter: cited as Exhibit 12, to be supplied."]
    },
    {
      "id": "decide-prior-overstay",
      "type": "attorney_decision",
      "title": "Answer Yes to I-485 Part 8 item 22, given the 2019 overstay?",
      "question": "Should I-485 Part 8 item 22 be answered Yes, with an explanation of Luis's 2019 overstay?",
      "recommendation": "Yes. The immediate-relative exception covers the overstay, and No would misstate the record.",
      "detail": "His passport shows a 2019 visitor stay past its end date. The answer also decides whether the cover letter addresses it.",
      "blocks_filing": true,
      "status": "open",
      "stage": "forms_preparer"
    }
  ]
}
```

- **Change the list only with the runtime's command**, never by editing the file: `run_matter_workflow.py open-items upsert "<matter>" --item-json '<item>' --run-id <run id>` (or `--item-file <path>` for long text) adds an item or changes the one with its id (the fields given replace its own; `notes` given are added), `... open-items note "<matter>" <id> "<line>" --run-id <run id>` adds a history line, and `... open-items packet-status "<matter>" draft|ready_to_file --run-id <run id>` sets the status at the handoff. Each is one change under the matter's lock, after the attorney's actions from the app are applied, so stages running side by side never lose each other's items. Each refuses an item that breaks these rules, with what to fix, and an open blocking item turns `packet_status` back to `draft`. When an item is already listed, tie to it and add a note rather than a duplicate.
- `id`: stable and readable, so later stages update the same item instead of adding a duplicate. The attorney never sees it, so never write it into another item's text, the memo, or the report.
- `type`: `client_document` (a document to ask the client for), `client_question` (a fact only the client can supply, such as a missing address), `attorney_decision` (a question only the attorney can answer), `attorney_action` (something the attorney does: sign, pay the fee, add a detail to "Your details"), `risk` (an adjudication risk to weigh, not a task).
- `title`: the item's name everywhere the attorney sees it, under 80 characters, naming people by first name. A document names the document ("Luis's I-94 arrival record"); a client question is the question; an action is an instruction ("Enter Jane's SSN on the I-130 and I-864"); a risk is a statement ("An officer may find Luis misrepresented his purpose at entry"). A decision's title is its question, shortened if it has to be.
- `question` (decisions only, required while open): the decision as one short question to the attorney, under 140 characters, ending in "?". Make it answerable: yes or no, or a choice among named options.
- `recommendation` (decisions, whenever you have a view): your answer in under 120 characters, starting with the answer ("Yes.", "No.", "Option C:") and then the main reason. The app offers it as the attorney's answer in one click, so it has to stand on its own.
- `detail`: why it matters and how it gets resolved, in one to three sentences, under 300 characters, in plain English. No item ids, review codes (FR2), step names (forms_preparer), file paths, or dated notes.
- `notes` (optional): the item's history, a list of one-line entries, each starting with the step's plain name ("Forms review: left Part 9 item 12 blank until this is answered."). When a later step learns something, add a note, and rewrite `detail` only if what's needed has changed, as one current statement. The app never shows notes.
- `who` (optional): `attorney`, `client`, or `system`, when the type doesn't make it obvious. A setup problem on the attorney's machine, such as missing Ghostscript, is `system`, with the fix in its detail.
- `blocks_filing`: true when the packet shouldn't be filed until this is done, decisions included. The memo's "Needed before filing" lists exactly these items, so set it to match what the memo says.
- **Physical filing items** are things that can't be scanned into the matter: passport photos, wet signatures, the card or bank details on the payment forms, and on a paper filing the sealed I-693 envelope. Each is an `attorney_action` item, even when the client is the one who gets it, because they're gathered at signing. Photos, signatures and payment details have `blocks_filing: false`, since they're gathered whether or not the packet is complete; so `ready_to_file` means ready to sign, gather those items, and mail or upload. The client request asks the client for the items they supply.
- **The I-693 blocks filing.** An I-485 filed without it "may be rejected" (I-485 instructions, ed. 09/18/26, item 9, checked 2026-10-29). Whenever an I-485 is in scope, its I-693 item (the partial I-693 some applicants file instead is the same item) has `blocks_filing: true` until the attorney confirms the sealed envelope is in hand (paper) or the scan is ready to upload, with the original kept (online), and is resolved then; when an exception means no I-693 at all, resolve it with that reason. Who needs which I-693 is in the docs-review skill's `evidence-checklists.md`, "The medical exam".
- `status`: `open` or `resolved`. When an item is resolved, keep it and add `"resolution"` with a one-line note, so the memo can say what changed.
- `packet_status`: `ready_to_file` only when no open item blocks filing; otherwise `draft`. The runtime enforces this.
- `schema_version: 2` marks a list written to these rules; the command creates every new list with it. The runtime checks the list when `attorney_handoff` passes. It refuses an open decision without a question, and a title, question, recommendation, or detail that names a file path, an item id, a step name, or a review code, or that runs more than twice its length. A list without `schema_version` passes with warnings until the handoff brings its open items up to these rules.

## Running the bundled scripts

Every bundled script declares its own Python version and packages, so run it with uv from any directory:

```bash
uv run --script "<plugin root>/skills/senior-associate/scripts/run_matter_workflow.py" status "/path/to/matter folder"
```

Nothing in the workflow runs without `uv`. If it's missing, stop and say so: it's a setup problem (a `system` item, "Install uv"), which the setup skill fixes from the app. Never ask the attorney to run a command.

Tool references:
- Forms: `<plugin root>/scripts/forms/README.md`
- The cover letter (`render_letter.py`, `letter_check.py`): `<plugin root>/scripts/packet/LETTER.md`
- The packet, fees, filing channels and locations, rendered documents and translations: `<plugin root>/scripts/packet/README.md`
- Workflow runtime: `runtime.md` beside this file

## Handling client data

These matters hold sensitive personal data, and some of it is privileged work product. The privacy scripts exist so that what leaves the machine, and what lingers on it, is deliberate.

- **Stage workspaces.** In the workflow, each stage gets a workspace holding a copy of every client document (anything outside `output/`; any of them could be evidence) in its `files/` folder, at the same path it has in the matter folder, with `stage manifest.json` listing each copy's original path and sha256. Nothing from `output/` is copied (read earlier stages' work at its matter path), and never the documents the attorney removed (`output/removed documents/`) or the earlier work set aside after a change of case (`output/earlier/`). Read from `files/`; write to the matter paths above, and record matter paths ("Folder layout").
- **Network gate.** Before anything goes to a remote service (case-law research, a web form, a remote site), check the gate:
  `uv run --script "<plugin root>/scripts/network_gate.py" "<matter>" --action <official_source|mcp_research|browser_remote> --role <stage> [--sends-client-data] --json`
  Anything without client facts goes through: official USCIS pages, and legal research phrased as propositions and anonymized fact patterns, never raw documents or identifiers. Sending client facts needs the attorney's go-ahead in the conversation, and an unattended run (the app's background run) never sends them: the gate refuses `--sends-client-data` while the app's run holds the matter, confirmed or not. So in a stage, add an `attorney_decision` item saying what you'd send and why, and work without it. A stage that queries the BIA Edge connector runs the gate with `--action mcp_research --role <stage>` before its first query, even for bare citations. The gate logs every check in `output/privacy/access_log.jsonl`, which is how the attorney sees that research ran inside the rules. The document review, forms, forms review and packet assembly agents have no research connector or web search at all (they can still read uscis.gov pages).
- **Privacy lint.** The runtime won't pass a stage whose summary or artifacts leave identifiers outside `output/working/vault/`, `output/working/workflow/`, `output/working/forms/`, `output/working/extracts/`, or `output/deliverables/`, or that relies on scratch files. Stage and blocker summaries show on the attorney's screen, so they're scanned for identifiers, the names and numbers of the people in the case (from the forms fact table and the document review's `parties` list), and sensitive terms (asylum, TPS, overstay, entry without inspection, removal, medical, tax return, and the like, and the protected-case terms in `protected-matters.md`). Keep each to a generic line such as "Prepared the forms; gaps recorded as open items."; the artifacts carry the detail. Every JSON or text file a stage writes with client facts (plans, mappings, propositions, scripts) goes in that stage's vault folder, and scratch it won't need again in `output/working/vault/scratch/`, never in `/tmp` or `$TMPDIR`: closeout cleans only the matter folder, so client data left there stays behind.
- **Closeout.** At the end of a run, `run_matter_workflow.py closeout "<matter>"` quarantines scratch that carries identifiers and deletes the scratch folders, the stage workspaces, and the page renders and OCR text stages leave in the vault. It never moves a client document or the work product (`runtime.md`, "Closeout").

## VAWA and other protected cases

When `status` or your brief says the matter is protected (8 U.S.C. 1367: VAWA, T or U), read `protected-matters.md` beside this file. It says which matters are protected, and holds the safe mailing address for every form, where a paper filing goes, the cover letter's request, a client request that's safe if someone else reads it, and the words that may never show on screen.

## Translations

A document in another language needs a full English translation that the translator certifies as complete and accurate, with the translator's certification of competence (8 C.F.R. 103.2(b)(3); the rule's words are in the docs-review skill's `evidence-checklists.md`). The document review lists what needs one and opens an item for each. In the packet, the original, its full translation and the signed certificate sit together under the same exhibit, and the letter quotes a foreign-language document only from its certified translation. The client request's own language is a different matter (`handoff.md`).

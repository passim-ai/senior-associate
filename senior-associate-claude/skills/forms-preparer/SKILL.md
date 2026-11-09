---
name: forms-preparer
description: Prepares the USCIS forms for an immigration matter from the current official editions and the client's documents. It builds a fact table with a source for every answer, fills the forms with the bundled tools, renders filing copies, and audits them, leaving any answer the record doesn't support blank and listing it as an open item. Use when an attorney asks to prepare, fill, or update USCIS forms (G-28, I-130, I-130A, I-485, I-864, I-765, I-131, I-751, N-400, and others), or when the Immigration Packet Builder workflow reaches its forms_preparer stage.
---

# Forms preparer

The client signs these forms under penalty of perjury, and USCIS reads them before anything else in the packet. Every answer has to come from a document, the attorney profile, or an explicit instruction from the attorney, and every blank has to be a deliberate blank the attorney knows about. A complete-looking form with one invented date is worse than an honest draft with three blanks on the open items list.

## Inputs

- The case type and posture, the stage workspace (`files/` holds the client's documents), and the attorney profile path, all from the brief.
- The docs review in `output/working/vault/docs-review/<slug>/`: what each document is, and what's missing.
- The tools: `${CLAUDE_PLUGIN_ROOT}/scripts/forms/README.md`. Its `REFERENCE.md` is only for when a tool fails and its message doesn't say why.
- Layout, artifact names, and the open items format: `${CLAUDE_PLUGIN_ROOT}/skills/senior-associate/references/matter-contract.md`; how each form goes to USCIS and how its fee is paid: `filing.md` beside it.

## Which forms

Work out the form set from the case type, the posture, and the current USCIS instructions; `references/forms-playbook.md` lists common form sets and the fact areas that most often go wrong. An immediate-relative spouse adjustment, for example, usually means a G-28 for each represented party plus the I-130, I-130A, I-485, and I-864. When a common companion form is a judgment call (an I-765 or I-131 alongside an I-485), add an `attorney_decision` item rather than deciding silently, with a `question` ("Include an I-765 work permit application with the I-485?") and your `recommendation`.

Then run the fees tool, which says how each form goes to USCIS and what it costs (`filing.md` has the rules):

```bash
uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/packet/fees.py" "<matter>" --forms I-130,I-485 --output "output/working/vault/forms/<slug>/fees.json"
```

Give `--category` whenever a fee depends on the case's basis: without one, every form is priced at its general fee, so a VAWA, T, U, refugee or SIJ I-485 would show $1,440 instead of $0 (`--category vawa`), and an I-131 filed without an I-485 is refused until you name what it requests (`--category I-131=reentry_permit`); a (c)(8) I-765 is `--category I-765=c8_initial` or `c8_renewal` (`--list-categories` lists them all). Make each `DECISION:` line an `attorney_decision` item and each `PROBLEM:` line a fact to find or an open item. Online, a representative's upload needs a G-28 for each party and form, so plan one G-28 per form (`G-28 - I-130`, `G-28 - I-485`, each listing its own form); on paper, one per represented party is the usual set. A paper filing also gets a G-1145 (`build` adds it on the first setup of a paper matter; for the paper part of a split filing, add it with `--new "G-1145=g1145_e_notification"` when the attorney wants e-notification) and one payment form per fee: `build "<matter>" --payments "output/working/vault/forms/<slug>/fees.json"` (`--payment-form G-1650` when the payer uses a bank account) makes them for the fees of forms that go on paper. Fill in only the names; the card or bank details stay blank for the payer.

## How to work

The stage is one tool, `build`, plus the plans you write:

```bash
B="${CLAUDE_PLUGIN_ROOT}/scripts/forms/forms_workflow.py"
uv run --script "$B" build "<matter>" --new "I-130=i130_family_petition" --new "G-28 - Petitioner=g28_represented_client" ...
uv run --script "$B" build "<matter>"
```

Keep to that path. Every extra command, and every line it prints, stays in your context and is re-read on every later step, so an unneeded field dump, helper script, extract, or render costs more than the forms themselves. Every bundled schema covers its whole form: it names every box, gives each checkbox's on-state in `choices`, and says in `field_notes` where a box's name misleads. `build` fills, verifies, renders, and audits. Don't run `dump-fields`, `extract-values`, or your own scripts for a form that has a schema; use them only for a form with no schema (`form_question_schema.py list` shows which have one) or when a tool fails and its message doesn't say why. Keep every file with client facts, scripts included, in `output/working/vault/forms/<slug>/`, never in `/tmp` or `$TMPDIR`: closeout cleans only the matter folder.

1. **Get the blanks and the plan skeletons.** Run `build --new "<Name>=<schema>"` once, one `--new` per filing copy, named as the copy will be (`I-130`, `G-28 - Petitioner`, `G-28 - Beneficiary`). `form_question_schema.py list` says which schema fits each form and posture (the I-485 has four). It writes skeleton plans to the vault's `plans/` and downloads each blank with its instructions; its summary gives the edition printed on each blank. For a form with no schema, `--blank <form>` fetches the blank, and you write its plan yourself. Read each form's instructions; they decide what goes where.

   A plan that already exists from an earlier run is kept. If the audit says it "predates its schema", run `uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/forms/form_question_schema.py" migrate "<plan>"` and answer the new questions it lists; never rebuild a plan from a fresh skeleton by hand. A plan written for another edition of the form needs `--across-editions`, only after downloading the current blank (the README, "Question plans and schemas").
2. **Build the fact table** (`form facts.json` in the vault folder). Record one fact per entry, with its source document and page, kept separate by party (petitioner, beneficiary, sponsor, attorney). Primary records outrank everything else. A fact found only on an old prepared form is marked `prior_prepared_form` and needs corroboration. Attorney and preparer details come only from the attorney profile.
3. **Write each plan from its skeleton**, editing the JSON directly. Give every question a `status` (one of the question's own `allowed_statuses`), its answers in `field_values` (dates `mm/dd/yyyy`; A-Numbers as digits only; read the `field_notes`; take each checkbox value from `choices` and each drop-down value from the form's two-letter codes), its `fact_ids`, and in `visible_values` the text that must show in that question's boxes on the filing copy. Keep each answer within its box; anything longer goes in the form's Additional Information part, with page, part, and item. The audit checks every box's length and format.

   When the record answers some of a question's boxes but not a required one (a current address with no move-in date, "Married" with the number of marriages unknown, a spouse with no country of birth), mark it `partially_filled`: put the known answers in their boxes and leave only the unknown boxes blank. Don't hold back the known answers, and don't move them to the Additional Information part because one box is unknown. An officer reads blank boxes as unanswered questions. Use `pending_client_input` with nothing written only when a partial answer would mislead, such as a yes/no group where one answer is still the client's to give.
4. **Run `build`** and read its summary, nothing else: per form, questions by status, verify, and audit errors (how many tied to open items) and warnings, then what needs work and a status line.

   If a form shows "not filled" because of its blank's edition, do what the summary says (the README's "Editions": an older blank is refreshed with `--refresh-blank`; a newer one waits on the attorney's decision, and goes ahead only with `--allow-new-edition` and a `new_edition_review` of every box it fills). Add every item under the build log's `summary.suggested_open_items` (the `forms-edition-<form>` decision among them) as it is, with `open-items upsert` as in step 6, and go on with the other forms. If a form shows "edited outside build", someone changed its source in Acrobat: put the change in the plan if the record supports it, then build; never pass `--force` to get past it without the attorney's say.
5. **Fix what it flags** in the plans and run `build` again; it refills only forms whose answers changed. A verify failure or field-check problem means a wrong box name or checkbox value: recheck `field_notes` and `choices`. An untied error is a mistake to fix, or a deliberate gap to tie (step 6). Text cut off in a box: shorten it, break its lines, or continue on the Additional Information page. A known form defect: do what the warning says and add the `attorney_action` item it names. For one finding's detail, search `build log.json` or `prepared forms audit.json` rather than reading them whole. Render a page only as the README's "A closer look at one form" says (at most two pages per form, into the vault's `renders/`).
6. **Tie the deliberate gaps.** For each question left `missing`, `pending_client_input`, `partially_filled`, or `manual_review`, add an open item (`client_document` or `client_question` for facts only the client has, `attorney_action` for missing profile details, `attorney_decision` for answers that need legal judgment) with `uv run --script "${CLAUDE_PLUGIN_ROOT}/skills/senior-associate/scripts/run_matter_workflow.py" open-items upsert "<matter>" --item-json '<the item as JSON>' --run-id <run id>`, never by editing `open-items.json` (the contract's "Open items"), put its id in the question's `"open_item"`, and run `build`. Name every form whose gap the item explains, with part and item, in its `needed_for` ("I-485 Part 1 item 12; I-130 Part 4 item 21"): the runtime ties an audit error only to an item that names the same form in its title, detail or `needed_for`. For a `partially_filled` question, the item names the blank boxes and the fact each one needs. The audit ties that question's errors to the item, and the summary names any id that isn't open on the list. Don't edit the audit JSON; the next build rewrites it. Never tie a wrong value, a layer mismatch, an overflow, or a mapping mistake. You're done when the status line reads clean.

   Write each item to the contract's open-item rules, because the attorney reads it on screen. When an earlier stage already listed the fact, tie to that item and add a line with `... open-items note "<matter>" <id> "Forms: left I-130 Part 2 item 3 blank until this arrives." --run-id <run id>` rather than appending to its detail.

A form the audit has no rules for still goes through `build`; the audit JSON lists it as `"coverage": "manual"` for the reviewer to check line by line.

## Protected matters

When `status` or the brief says the matter is protected, every client mailing-address box on every form gets the safe mailing address, as `protected-matters.md` (beside the contract) says, with where each form puts it and the open items to add. Record it once in each of the client's plans as `"safe_mailing_address": {"in_care_of", "street", "unit", "number", "city", "state", "zip", "country", "source": "profile" or "attorney"}`; the audit checks every mailing-address box against it. A VAWA self-petition is a G-28 and the I-360; with adjustment, add the I-485 (no I-864: the client claims the exemption in I-485 Part 3) and usually an I-765, as an `attorney_decision`.

## Attorney details

Counsel and preparer answers come from the attorney profile only. When the profile says `has_uscis_online_account` is `no`, the G-28's attorney online account question starts `not_applicable` and needs no open item, and the attorney boxes on the other forms leave the account number blank.

## Yes/no eligibility questions

Never infer a "No" from a silent record. Criminal, security, immigration-violation, and other inadmissibility answers need a documented client response, reviewed with counsel. Leave unsupported answers blank with `pending_client` status and a blocking `client_question` open item naming the exact questions. A conflict between the client's answer and the documents is a blocking `attorney_decision`.

For each answered sensitive question, link `fact_ids` to a fact with `source_kind: "client_confirmation"`, a nonempty `source` identifying the interview note or signed questionnaire, and `confirmed_at` in ISO date format. Preserve the response in that source; do not invent confirmation metadata. The forms audit rejects an answered sensitive question without this provenance. The attorney must review these answers with the client before signing; the agent cannot mark that conversation complete.

Do not default other answers either. Dates, addresses, employment, marital history, entries, and status all come from documents or stay blank. Some yes/no items are facts, not eligibility questions, and the schemas' notes say which. On the N-400, for example, the tax questions, Selective Service, U.S. military service, and titles of nobility come from the record, and the oath-related items expect "Yes". An unexpected answer there is an `attorney_decision`, never a default.

## Finish

Complete the stage with all three vault artifacts:

```bash
uv run --script "${CLAUDE_PLUGIN_ROOT}/skills/senior-associate/scripts/run_matter_workflow.py" complete-stage "<matter>" forms_preparer --run-id <run id> \
  --status passed --summary "Prepared the forms from current editions; gaps recorded as open items." \
  --artifact "output/working/vault/forms/<slug>/form facts.json" \
  --artifact "output/working/vault/forms/<slug>/form intent manifest.json" \
  --artifact "output/working/vault/forms/<slug>/prepared forms audit.json"
```

If `gs` (Ghostscript) is missing, `build` can't render filing copies and says so. Stop, and tell the orchestrator that Ghostscript needs installing; the app offers the attorney a button that has Claude install it. Don't hand over unrendered forms.

For each sensitive answer, the cited client-confirmation fact must list the exact plan question key in `question_keys`, plus `source_kind: client_confirmation`, a source reference, `confirmed_at` (ISO date), and the actual response in `value`. A confirmation of one question cannot support a different question.

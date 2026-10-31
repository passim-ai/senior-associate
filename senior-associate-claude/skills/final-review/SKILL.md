---
name: final-review
description: The last review of an assembled USCIS filing packet, done in one pass. It runs the pre-filing QA check (current forms, facts against the client's documents, completeness, letter and exhibit alignment, filing logistics) and reads the case as a strict USCIS officer would, naming the strongest RFE, NOID, or denial theory with its cure and owner. Use when an attorney asks to check a packet before filing, wants an officer's review or a stress test, asks how USCIS would see a packet or where its weakest point is, or when the Immigration Packet Builder workflow reaches its final_review stage. When it re-reviews after fixes, it checks only the earlier findings and what changed; when the attorney asks for a fresh or full review, it reviews everything.
---

# Final review

You're the last two readers before the packet goes to USCIS, in a single pass. One is the careful QA reviewer who catches what a rejection notice would catch. The other is the strict officer who decides the case. Read the packet once, with two questions open the whole time: *is anything wrong or missing?* and *on this record, what would I RFE, NOID, or deny?*

Ground every finding in the packet, the client's documents, or a current official source, and keep proven defects separate from judgment calls. One strong theory is worth more than ten weak ones: the officer writes the RFE about the element that's actually under-proven, and the attorney needs to know which element that is.

## First: full review or re-review?

Read the brief first. When it says the attorney asked for a fresh or full review (Redo of this step, or Re-check as a USCIS officer would), review everything, whatever changed:

```bash
RW="${CLAUDE_PLUGIN_ROOT}/skills/senior-associate/scripts/run_matter_workflow.py"
uv run --script "$RW" changed-since "<matter>" final_review --fresh
```

It lists your previous findings for reference only. Do the whole review below, as on a first review, and settle your own strongest theory before you look at them; then carry over or close each one in your findings.

Otherwise:

```bash
uv run --script "$RW" changed-since "<matter>" final_review
```

- **First review.** It says the stage hasn't passed before. Do the whole review below.
- **Re-review** (only when the brief doesn't ask for a fresh or full review). It names your previous findings and lists what was added, changed, or removed since your last pass.
  1. Read your previous findings. Check each one against the fix: mark it `resolved` with a one-line `resolution`, or keep it `open` and say what's still wrong.
  2. Review only the listed files, plus what they directly touch. For example, a changed form answer means rechecking the letter passage and the exhibit that rely on it.
  3. Don't re-read unchanged evidence. Don't re-verify sources you recorded last time either, unless a change makes them relevant or the check is more than 30 days old. Carry untouched findings forward as they stand.

  If it says the last pass predates change tracking, check the previous findings and then review in full.

## Inputs

- The packet PDF and its manifest (`output/deliverables/`, `output/working/vault/packet/<slug>/packet manifest.json`), the filled forms in `output/deliverables/Forms/`, the cover letter, and `open-items.json`.
- The client's documents, from the stage workspace's `files/` folder when the brief gives you one.
- The earlier review memos in `output/working/vault/` (docs review, forms review, letter review), the letter's `letter check.json`, and the research's `support matrix.json`. **Read them only after you've settled your own strongest theory** (steps 1 to 4 below), so their conclusions don't anchor yours. Then check that what they flagged got fixed, and say in the memo where you see it differently. Don't re-litigate a point they settled unless you found something they didn't.
- The matter's settings, from `status` or the brief: the filing method, and whether it's protected.
- For dynamic USCIS PDFs, the stored field values are the truth, not what a viewer happens to render (`${CLAUDE_PLUGIN_ROOT}/scripts/forms/README.md`, "A closer look at one form").
- Before any case-law query through the BIA Edge connector, even a bare citation, run the network gate (`uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/network_gate.py" "<matter>" --action mcp_research --role final_review --json`), and send legal propositions, never client identifiers.

The folder layout, the matter types, the findings format, and the open-item rules are in `${CLAUDE_PLUGIN_ROOT}/skills/senior-associate/references/matter-contract.md`; how each form goes and how its fee is paid in `filing.md` beside it.

## The review

1. **Frame the decision.** State the benefit requested, the posture, and the legal mechanism (for example INA 201(b)(2)(A)(i) and 245(a) for an immediate-relative adjustment). List each element USCIS must find, any bars or inadmissibility grounds the facts raise, the primary evidence normally expected, and whether discretion applies. If the mechanism itself is unclear, that's your first finding.
2. **Check currency.** Each form edition must be acceptable today, per its USCIS form page. Check every blank live before filing:

   ```bash
   uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/forms/forms_workflow.py" editions "<matter>" --live
   ```

   It prints one line per blank: the edition in its footer, whether the form tools were built for it, and what the form's uscis.gov page lists today, with its note on prior editions. Exit 0 means every blank is the edition uscis.gov lists. Exit 1 means at least one line needs you, and each such line is a finding with an owner, never a pass. A blank that isn't the edition uscis.gov lists today is `forms_preparer`'s to fix; say whether the page's note still accepts the blank's edition, and until when. A newer edition than the form tools know is the attorney's decision: the forms-edition open item must record it, and a form prepared on that edition must have had every filled box checked in the forms review. A page that couldn't be read (offline, unreachable, or no edition date found) is a `manual_review` finding: check that form's uscis.gov page by hand, record what it showed and the date, and never count it as checked. Record what the command printed and the date.

   The fee and the payment method must be current, and the packet must follow `filing.md`: rerun `${CLAUDE_PLUGIN_ROOT}/scripts/packet/fees.py` for the packet's forms and compare its fee-schedule edition with uscis.gov/g-1055. On paper, the filing address must be current for this case's controlling facts (case type, state, category, courier or USPS), and the payment forms sit on top in the fees tool's order, then the G-1145 if there is one, then the cover letter (the packet manifest's `filing_order` records what the tool put on top). Online, each form must be one USCIS takes online for this category (uscis.gov/file-online/forms-available-to-file-online), and the packet manifest's `upload_map` has no warning left. Check each form's channel in the fees tool's `channels` against the packet it is in (a split filing has two), that every `PROBLEM:` fact was settled from the record, and that every `DECISION:` line is an `attorney_decision` item. A paper filing of a form USCIS no longer takes on paper is a blocker; when the fees tool says its list of mandates is over 30 days old, look at the uscis.gov pages it names and rerun it with any notice you find (the packet tools README, `filing_channels.py`). Record each URL and the date you checked it. If a controlling fact isn't in the record, make it a `manual_review` finding.
3. **Check facts against the record.** Compare each of these with the strongest source document: names, dates of birth, A-numbers, passport details, addresses and address history, marital history, last entry and status, employment, and the yes/no inadmissibility answers. Watch for answers copied across forms without support, and for required fields left blank with no open item.
4. **Test each element against the evidence.** Does a preponderance of the packet's evidence prove it? Look for missing primary evidence where it would normally exist, secondary evidence offered without explaining the gap, contradictions between documents or between the forms and the documents, gaps in time, derogatory facts that need rebuttal, and weaknesses that bear on discretion. Settle the strongest theory here, before reading the earlier memos. Then re-verify the two or three authorities that theory, or the letter's answer to it, rests on, at the primary source itself (the statute on uscode.house.gov, the regulation on ecfr.gov, the Policy Manual chapter, the precedent decision's PDF at justice.gov/eoir), not through the support matrix or the authorities file. Record what you read and the date.
5. **Check completeness, the letter, and the exhibits.** Sort supporting items into required, required if applicable, and strongly recommended under the current instructions, and don't call a recommended item mandatory. The relief requested must match the forms filed. Every exhibit the letter cites must be in the packet, in order, behind its separator, and nothing important may be in the packet but missing from the index; the packet's index pages must match the manifest. Each placeholder must be clearly marked and have an open item. The letter check (`letter check.json`) must show zero errors and be newer than the letter. A case the support matrix marks `treatment not checked` needs its "still good law" item open, or it's a finding for the attorney.
6. **Check logistics.** Look at signatures and dates, photos, the I-693 if an I-485 is in scope, certified translations (8 C.F.R. 103.2(b)(3)), and the assembly order. Photos, wet signatures, and the payment details aren't packet defects as long as each has its non-blocking `attorney_action` item; the I-693's item must block filing until it's resolved (the contract's "Open items"). Flag any of these that's missing from the open items. An online letter must carry no mailing details.
7. **Check confidentiality, in a protected matter** (`status` or the brief says so): every rule in `protected-matters.md` (beside the contract), as `references/checklists.md` lists them. A client mailing address other than the safe address is a `blocker` owned by `forms_preparer`.

Work from current authority in this order: the statute and regulations, the current form instructions, the USCIS Policy Manual (its general adjudication chapters and the benefit's volume), other current USCIS guidance, then binding or persuasive case law when a point turns on it. When the packet and a source conflict, cite both.

`references/checklists.md` has the high-risk form fields and the residual problems, and `references/theories/<key>.md` the officer theories for the case type that most often lead to an RFE, NOID, or denial (keyed as in the matter contract's "Matter types"). Read both to make sure nothing routine was skipped; they don't replace reading the packet.

## Findings

Give each finding these fields:

- `id`: keep it the same across re-reviews, for example `FR1`
- `title`
- `detail`: what the packet shows
- `source`: the record and the authority you checked, with dates
- `fix`
- `owner`
- `status`: `open` or `resolved`
- `severity`, one of:
  - `blocker`: likely rejection, a misfiling, a materially false filing, or no legal basis for approval
  - `major`: fix before filing
  - `minor`: real but not outcome-changing
  - `manual_review`: needs attorney judgment, or facts the record lacks

When the finding is a merits risk, add an `outcome` and write `detail` as the officer's theory, in the officer's voice:

- `deny_likely`: no legal basis on this posture; more evidence won't fix it
- `noid_likely`: a serious adverse fact or contradiction that needs rebuttal
- `rfe_likely`: approvable, but key evidence or explanation is missing
- `attorney_hold`: a strategy or posture question that needs legal judgment

The `owner` is whoever cures it:

| Cause | Owner |
| --- | --- |
| A wrong or unsupported form answer | `forms_preparer` |
| An element argued weakly or not at all | `cover_letter_writer_integrate` |
| Evidence that exists but isn't in the packet | `packet_assembly` |
| Evidence that doesn't exist yet | `client`, plus a `client_document` open item |
| A strategy, posture, or disclosure choice | `attorney`, plus an `attorney_decision` open item |

The runtime won't pass the stage while any open finding lacks an owner if it's a `blocker`, `major`, or `manual_review`, or has an outcome other than `approvable`.

If you conclude there's no legal basis for approval on this posture, say so in the memo's first line. Make it a `blocker` with `deny_likely` or `attorney_hold` and owner `attorney`. Don't invent a cure; the orchestrator stops the run and asks the attorney.

## Outputs

Write both files to `output/working/vault/final-review/<slug>/`. On a re-review, rewrite both in full, updated.

`final review findings.json`:

```json
{
  "reviewed_at": "2026-10-28",
  "re_review": false,
  "decision": "I-130, spouse of a U.S. citizen, INA 201(b)(2)(A)(i); concurrent I-485 under INA 245(a); discretionary",
  "overall_outcome": "rfe_likely",
  "strongest_theory": "FR2",
  "findings": [
    {
      "id": "FR2",
      "severity": "major",
      "outcome": "rfe_likely",
      "title": "Joint records begin two months before filing",
      "detail": "The petitioner hasn't shown the marriage was entered in good faith: every joint record postdates ...",
      "source": "Joint Bank Statements Aug-Oct 2026.pdf; 6 USCIS-PM B.6(C)(1) (checked 2026-10-28)",
      "fix": "Ask the client for earlier joint records or third-party affidavits.",
      "owner": "client",
      "status": "open"
    }
  ]
}
```

`overall_outcome` is the record as it stands: `approvable` when no material issue remains, otherwise the most serious outcome.

`final review memo.md`:

1. The decision framing, in one line.
2. The strongest theory and its cure.
3. The findings, most serious first.
4. What you couldn't verify, such as unreadable scans or sources you couldn't reach.
5. A two- or three-sentence overall assessment.

On a re-review, open the memo with what was fixed and what's still open.

Add open items for anything the attorney or client must act on: `client_document` for curable evidence gaps, `attorney_decision` for holds, and `risk` for exposure the attorney should weigh even when nothing can be done about it. A decision gets a `question` and your `recommendation`, and the officer's theory goes into the item in plain words, without its finding id (FR2) or outcome code. Add or change each one with `uv run --script "${CLAUDE_PLUGIN_ROOT}/skills/senior-associate/scripts/run_matter_workflow.py" open-items upsert "<matter>" --item-json '<the item as JSON>' --run-id <run id>`, never by editing `open-items.json` (the contract's "Open items"); when an item is already listed, add a line with `... open-items note "<matter>" <id> "<line>" --run-id <run id>` rather than lengthening its detail. Then complete the stage:

```bash
uv run --script "$RW" complete-stage "<matter>" final_review --run-id <run id> \
  --status passed --summary "Final review complete." \
  --artifact "output/working/vault/final-review/<slug>/final review memo.md" \
  --artifact "output/working/vault/final-review/<slug>/final review findings.json"
```

The stage passes with open findings as long as each material one has an owner. The orchestrator decides what to reroute.

## Direct requests

You might be asked outside the workflow: "check this packet before filing", "read it like an officer", or the app's officer's review. Do the same review. The app's officer's review (Re-check as a USCIS officer would) is the attorney asking for a fresh, full read: run `changed-since ... --fresh` and review everything. Otherwise, if `changed-since` shows an earlier pass, do it as a re-review. For an officer's review, lead with the framing and the strongest theory. Save the memo and findings as above, but don't run `complete-stage`. If `open-items.json` and `Attorney Memo.md` exist, update them as `${CLAUDE_PLUGIN_ROOT}/skills/senior-associate/references/handoff.md` describes, the memo's case assessment included. In chat, give the bottom line in plain words, with no finding ids or paths: whether the packet is ready to file, plus the strongest theory and its cure.

If there's no matter folder to save into, give the findings in chat in the same order, and offer to save them.

# Workflow runtime

`scripts/run_matter_workflow.py` keeps the matter's stage state in `output/working/workflow/matter_status.json`. It's the durable record of what has run, so a later run (or a different person) picks up exactly where the last one stopped, and it's what the attorney's dashboard reads. Run it with uv:

```bash
RW="<plugin root>/skills/senior-associate/scripts/run_matter_workflow.py"
uv run --script "$RW" <command> "/path/to/matter folder" [options]
```

`<plugin root>` is the plugin's install folder (`${CLAUDE_PLUGIN_ROOT}`).

Always pass the matter folder's absolute path. Every command, and the network gate and stage-workspace tools, refuses a path that doesn't exist or isn't a matter folder (no workflow record and no client documents), rather than creating one; `init`, `ensure` and `lease` accept the app's new, empty matter folder.

Every command that changes the record reads, changes and writes it under the matter's lock (`output/working/workflow/.lock`), so stages finishing side by side, and the app writing beside a run, never lose each other's changes. A command that finds the record busy for more than ten seconds says so; run it again.

## Commands

| Command | What it does |
| --- | --- |
| `lease acquire [--run-id ID] [--kind K] [--holder H] [--description D]` | Takes the matter for a run. The same run id renews it (an app run's lease becomes the orchestrator's). Exit code 3, with one line, when someone else holds a fresh lease: stop and report that Claude is already working on the matter. Without `--run-id`, makes a new id and prints it. |
| `lease heartbeat [--run-id ID] [--stage S]`, `lease release --run-id ID [--outcome done\|stopped\|failed]`, `lease show [--json]` | Renew, end, or show the lease. Every other command renews it too: a command that changes the record renews an unreleased lease even when it has gone quiet; a read-only one renews only a fresh one, so looking at a matter never revives a run that has gone. `start-stage` and `complete-stage` record the running stages on it. `lease heartbeat --run-id` exits 3, like a changing command, when the run no longer holds the matter: the orchestrator runs it before each round of stages. |
| `--run-id ID` on any other command | The run the command belongs to: pass it on every command that changes the matter (`init`, `ensure`, `start-stage`, `complete-stage`, `resolve-blocker`, `reroute`, `closeout`, `apply-attorney-actions`, `set-protected`, and `open-items upsert\|note\|packet-status`, after the action). Then the command renews only that run's lease, and changes nothing and exits 3 when another run holds the matter now ("Another run holds this matter now; stop."), took it over while this run was quiet, or this run's lease has ended (released, or stopped by the attorney in the app): stop the run and report it. Without it, a command renews whatever unreleased lease there is, as above. On a read-only command it renews only that run's own fresh lease. |
| `ensure --matter-type T --filing-posture P --deliverable D [--workflow-key K]` | Creates the state if missing; resumes it when it matches this intake. Case, spacing, and line breaks don't make a different case. A moved or renamed matter folder is the same matter: the record is pointed at where it is now. Refuses a different case or posture, saying how to continue (`--resume`) or that the attorney changes the case on the matter page; it never suggests starting over. Also creates `case_theory_evidence_map.json` and the matter's privacy policy. Run it first, every time. |
| `ensure --resume` | Continues the recorded workflow with its recorded intake. Any intake option given alongside must agree with the record. Refuses when there's no record yet. |
| `status [--json]` | Stage map, the stages running and ready, open blockers, the next stage, the matter's settings (protected, filing method, client language), and the packet's state from the ledger (`draft, N item(s) block filing` or `ready to file`). `--json` adds `running`, `ready`, `stage_dependencies`, `meta`, `lease` and `packet`. Every stage passing doesn't make the packet fileable. A review stage that passed before a reroute shows as a re-review. |
| `next-stages` | Every stage to run now, one per line: any left in progress (start them again), then every ready stage. Start them together. Empty when everything is done, and while a blocker is open; `status` tells which. |
| `next-stage` | The first line of `next-stages`. |
| `start-stage <stage>` | Marks a stage in progress once every stage it depends on has passed or been skipped. Several stages may be in progress at once. Starts a new timed attempt. |
| `complete-stage <stage> --status passed\|failed\|blocked\|skipped --summary "..." --artifact <path> ... [--evidence-file <path>] [--blocker-owner client\|attorney\|system\|agency\|third_party --blocker-summary "..."] [--attorney-approved "..."] [--unchanged-reason "..."]` | Records the outcome. Applies the attorney's actions to the open items first. Any outcome needs the stage in progress; only a stage nobody has started may be skipped, failed or blocked outright. A stage a redo reset after it started is refused, whatever the status ("A redo reset it after it started"): the result is for work that was set aside, and the stage runs again from `start-stage`. See "When a pass is refused" for what a pass needs. Paths are relative to the matter folder. A pass also hashes the client's documents, the deliverables, and the vault for `changed-since`, and a passed review records how many material findings it left open, and whose. |
| `apply-attorney-actions` | Writes what the attorney marked done, reopened, or accepted in the app (`attorney-actions.jsonl`) into `open-items.json`, under the lock. Safe to run again. Run it before reading the open items. |
| `open-items upsert --item-json '<item>'` (or `--item-file <path>`), `open-items note <id> "<line>"`, `open-items packet-status draft\|ready_to_file` | The only way to change `open-items.json` (the matter contract's "Open items"). A new item needs `type`, `title` and `blocks_filing`; `upsert` creates the list when there's none. `packet-status` never sets `ready_to_file` while an open item blocks filing, and marks a list without `schema_version` current once its items keep the rules. An item the attorney marked done in the app can't be reopened. |
| `set-protected --on\|--off --reason docs_review\|attorney` | Marks the matter protected under 8 U.S.C. 1367 (VAWA, T or U), in `matter-meta.json` (`protected-matters.md` says when). Only `--off --reason attorney` lifts it. Every later step reads the flag from `status`. |
| `resolve-blocker <id> --resolution-note "..." [--reset-stage-to pending\|in_progress]` | Clears a blocker after the attorney or client supplies what was missing. |
| `reroute --from-stage <stage> --reason "..." [--detected-in-stage <stage>] [--attorney-approved "..."]` | Resets a stage and every stage that depends on it (not the stages beside it), for when a later review finds a defect upstream. The open blockers on the reset stages are resolved ("Set aside by a redo."). Names the reviews that become re-reviews. A review sends the same stage back at most twice in one run (counted by `--detected-in-stage` and the lease's run id); the third is refused, unless the attorney asked for it. `--category forms_defect\|cover_letter_defect\|packet_assembly_defect\|final_review_defect` is a shortcut. |
| `changed-since <stage> [--fresh] [--json]` | For a re-review: the stage's previous findings and memo, and the files added, changed, or removed since it last passed. It lists client documents and the files its own and earlier stages produce; later stages' changes are only counted. A stage that never passed gets "first review". `--fresh` is for a full review the attorney asked for: it lists the previous findings as reference only and says to review everything again. |
| `security-dashboard [--json]` | A short summary of workflow state, privacy lint, cleanup targets, quarantine, and recent access events. `--json` gives the full detail. |
| `closeout [--json] [--dry-run]` | Cleans the working files: see "Closeout" below. Writes the closeout report and prints a short summary (`--json` prints the report). |
| `init ... --force` | Replaces the state outright. Only when the attorney has changed the matter type or posture and wants to start over. |

`--workflow-slug <slug>` on any command keeps a second track (for example a separate principal in a family folder) in `output/working/workflow/<slug>/`.

`start-stage`, `complete-stage`, `resolve-blocker`, and `reroute` print a line or two: what changed and what runs next. `--json` prints a short JSON result, and `--full` prints the whole state.

## Workflow keys and dependencies

| Key | Stages |
| --- | --- |
| `full_packet` (default) | docs_review, forms_preparer, forms_reviewer, cover_letter_writer_draft, cover_letter_researcher, cover_letter_writer_integrate, cover_letter_reviewer, packet_assembly, final_review, attorney_handoff |
| `docs_review_only` | docs_review |
| `forms_only` | forms_preparer, forms_reviewer |
| `cover_letter_only` | the four cover letter stages |
| `packet_build` | packet_assembly, final_review |
| `final_review_only` | final_review |

`--stage-id <id>` (repeatable) defines a custom list instead.

Each stage starts when the stages it depends on have passed or been skipped:

```
docs_review
forms_preparer                 <- docs_review
forms_reviewer                 <- forms_preparer
cover_letter_writer_draft      <- forms_preparer
cover_letter_researcher        <- cover_letter_writer_draft
cover_letter_writer_integrate  <- cover_letter_researcher
cover_letter_reviewer          <- cover_letter_writer_integrate
packet_assembly                <- forms_reviewer, cover_letter_reviewer
final_review                   <- packet_assembly
attorney_handoff               <- final_review
```

So the forms review runs beside the whole cover letter track, and the packet waits for both reviews. A workflow that leaves stages out gives each stage its nearest included ancestors (in `packet_build`, the final review waits on the packet). Nothing starts while a blocker is open.

The overall status is `passed` only when every stage passed or was skipped and, when the workflow has a final review, the final review passed; with a skipped final review it's `incomplete`.

Workflow records are schema 8, which keeps the case type only in the record's intake block (`matter`). The runtime refuses a record of any other schema, saying so, rather than starting over beside it.

## Timing

Each stage keeps every attempt's start, end, length and outcome (`timing.attempts`, `timing.total_seconds`, and `duration_seconds` for the last), and `telemetry.runs` totals the stage time per run id, so time estimates can come from real runs. The handoff's time is right only when `start-stage attorney_handoff` comes before the memo is written.

## Timeline

`start-stage`, `complete-stage` and `reroute` add a line to the matter's timeline (`events.jsonl`), in the step's plain name: "Forms review started.", "Forms review passed.", "Forms is done.", "Packet is waiting on the client.", "Letter review sent Letter revision back to be redone." No case type, names, or file paths.

## Extracts

`<plugin root>/scripts/extract_documents.py "<matter>" [--json]` writes the text of each client document to `output/working/extracts/<sha256>.txt` (pages separated by form feeds) and an `index.json`:

```json
{"version": 1, "files": {"From client/Acta.pdf": {"sha256": "...", "pages": 2, "chars": 1830, "method": "text",
  "language": "es", "language_name": "Spanish", "non_english_pages": [1, 2], "needs_translation": true,
  "pages_without_text": []}}}
```

The document review runs it first; a re-run extracts only new or changed files and drops the ones that left the matter. `method` is `none` for an image or a scan (its pages are listed in `pages_without_text`: someone has to look at them). `language` is a heuristic per page: `en`, `es`, `pt`, `fr`, `ht`, `vi` by their common words; `zh`, `ja`, `ko` by script; `arabic-script`, `cyrillic` and `devanagari` for those scripts, which write many languages, so only the script is known (`script_only: true`, `language_name` "a language written in Cyrillic script"); otherwise `unknown`. A page needs translation when it's mostly in a language other than English; a bilingual page that is at least half English doesn't. The extracts are client data, kept in `output/working/`.

## When a pass is refused

The refusal message names what's missing. A pass needs:

- the stage in progress (`start-stage` first) and every stage it depends on passed or skipped;
- the stage's artifacts, existing and well formed (every artifact of a kind is checked, not only the first); `forms_preparer` also needs at least one filing copy in `output/deliverables/Forms/`, and `cover_letter_writer_integrate` a clean `letter check.json`;
- a forms audit whose errors are each tied to an open item about the same form (the item's title, detail, question, or `needed_for` names it);
- review findings with an owner for every open material one: `blocker`, `major`, `manual_review`, and any severity word the runtime doesn't recognize (`critical` and `high` count as `blocker`);
- JSON artifacts that point at files by their path in the matter folder, never into a stage workspace (the refusal names the field);
- a summary with no identifiers, no party's name or number from the fact table, and no words naming a protected case (VAWA, I-360, T or U, abuse, battery, extreme cruelty, trafficking; in a matter marked protected, also words like victim, self-petition, or 1367);
- main artifacts that changed since the stage last passed, or `--unchanged-reason "<why>"`.

A blocked, failed, or skipped stage's summary, and a blocker's summary, are held to the same screen rules (the dashboard shows them), and a blocker's summary may carry no identifier at all.

`skipped` is refused for a review (forms review, letter review, final review) and for the handoff, unless the work it checks was itself skipped, or the attorney approved it (`--attorney-approved "<what the attorney said>"`). A refusal is information about the work, not a formatting hurdle; don't relabel the stage `skipped` to get past it.

`blocked` is for a stage that genuinely can't produce its artifacts (for example, no documents at all to review). Missing evidence isn't a block: record it in the open items ledger and pass the stage with what the record supports.

## Closeout

`closeout` cleans what a run leaves behind, and never touches the client's documents or the work product:

1. It moves tool scratch that carries identifiers into `output/security/quarantine/`. Only scratch locations inside `output/` are ever moved (`output/tmp/`, `output/working/tmp/`, `output/working/pdf/`, `doc/` and `images/`, the vault's `scratch/`). A file outside `output/` is the client's document, whatever its name, and the work product (vault, workflow, forms, deliverables, extracts) stays where it is.
2. It deletes the scratch folders (`pdf/tmp`, `doc/tmp`, `images/tmp`, the forms tools' `.source_xfa` and `editable_xfa`, `output/working/vault/scratch/`, `output/working/tmp/`, `output/tmp/`, `output/playwright/`) and every stage workspace.
3. It deletes what stages leave in the vault while checking their work: every image (page renders) and everything in a render, OCR, or scratch folder (`render-check/`, `renders/`, `ocr/`, `source-ocr/`, `visual-check/`, and the like). Memos, findings, plans, the fact table, and research stay.

In a protected matter, the quarantine also catches scratch that names the case, and the closeout report lists counts, not file names.

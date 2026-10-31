---
name: packet-assembly
description: Assembles the USCIS filing packet into one ordered, bookmarked PDF (payment forms on top of a paper filing, the cover letter, the forms, an exhibit index, then each exhibit behind its separator page, with clearly marked placeholders for evidence still to come), and for an online filing the upload files, and writes a manifest mapping every page to its source. Use when an attorney asks to assemble, build, or rebuild a filing packet, or when the Immigration Packet Builder workflow reaches its packet_assembly stage.
---

# Packet assembly

The packet is what USCIS actually receives, so it has to match the cover letter exactly. Every exhibit the letter lists sits behind its own separator, in order, and nothing that isn't listed slips in. When evidence is still missing, the draft packet shows a clear "to be supplied" page in its place, so the attorney sees the gap where it belongs and no one mistakes the draft for the filing copy.

## Inputs

- `exhibit plan.json` in `output/working/vault/cover-letter/<slug>/`: the controlling order, written with the letter.
- The cover letter PDF and the filing copies of the forms in `output/deliverables/`, including the payment forms the forms step prefilled (G-1450 or G-1650, one per fee: payer, amount and form only) and the G-1145.
- The client's documents, as named in the plan's sources.
- The filing method (`paper` or `online`) from `status` or the brief, and the fees from `fees.py` (below).
- The open items list, which decides whether this is a draft. When you note something on an existing item (the page its placeholder landed on, say), add a line to its notes with `uv run --script "${CLAUDE_PLUGIN_ROOT}/skills/senior-associate/scripts/run_matter_workflow.py" open-items note "<matter>" <id> "<line>" --run-id <run id>`, never to its `detail` and never by editing the file (the matter contract's "Open items"). A new item goes in with `... open-items upsert "<matter>" --item-json '<the item as JSON>' --run-id <run id>`.
- The tools: `assemble_packet.py` and `fees.py`, documented in `${CLAUDE_PLUGIN_ROOT}/scripts/packet/README.md`. The rules they apply (how each form goes, the fees and payment forms, the packet's order): `${CLAUDE_PLUGIN_ROOT}/skills/senior-associate/references/filing.md`, beside the matter contract.

## How to work

1. **Check the plan against reality.** Every source path exists, page ranges are inside the document, and every placeholder has an open item. Where the plan and the documents disagree (a file missing, two plausible matches, a combined PDF with no page range), don't guess. Use the clearly correct document if there is one and note it, or send it back to the writer as a finding. If a source simply isn't there, make it a placeholder and add the open item.
2. **Price the filing and settle how it goes.** Run `uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/packet/fees.py" "<matter>" --forms <every form in the filing> --output "<matter>/output/working/vault/packet/<slug>/fees.json"` (add `--category` where a fee depends on the category, such as `vawa` or `I-485=under14_with_parent`, and the channel facts the README's `filing_channels.py` section lists, such as `--basis I-485=family` or `--eligibility I-765=c9`). Its fees and payment forms go in the plan's `notes`, the memo's filing logistics and the filing checklist. Its `Filing:` lines say which forms go online, in which submission, and which on paper. When it says the filing is split, build two packets from two plans, each with its own manifest: the online one (`packet plan.json`, `"filing_method": "online"`, its forms and evidence; `packet manifest.json`) and the paper one (`packet plan (paper part).json`, `"filing_method": "paper"`, its forms with their payment forms; `packet manifest (paper part).json`), named `Filing Packet.pdf` and `Filing Packet (paper part).pdf` (each with ` (DRAFT)` while an open item blocks filing). When the filing isn't split, remove any `Filing Packet (paper part)` PDF an earlier build left, so the app never shows a paper part that no longer exists. A `PROBLEM:` line is a fact still missing: send it back as a finding rather than guess.
3. **Order the packet** the way USCIS expects for this filing:
   - **On paper:** the payment forms on top, one G-1450 or G-1650 for each fee, as the forms step prepared them in `output/deliverables/Forms/` (`G-1450 - I-130 filing fee`, `G-1450 - I-765 Pub. L. 119-21 fee`); then the G-1145 if the forms step prepared one; then the cover letter; then the forms in the order the current instructions or filing tips give (usually the G-28 first, then the primary form, then supporting forms); then an `index` item; then the exhibits in the letter's order. List every payment form and the G-1145 without an exhibit label. The tool reads from the forms step's manifest (`form intent manifest.json`) which filing copies are payment forms, the fee each one pays and its place in the fees tool's list, and puts each payment form on top in that order, then the G-1145, then the cover letter, whatever order the plan gives them; its summary's `Order:` line says what it put on top. A payment form or G-1145 the forms step prepared that the plan leaves out, or a payment form it didn't prepare (an earlier build's copy), is a warning: fix the plan.
   - **Online:** no payment forms (the fee is paid in the online account) and no G-1145 (notices come through the account); the cover letter, the forms, the index, then the exhibits.
   The physical items the attorney adds (passport photos, wet signatures, the card or bank details on the payment form, and on paper the sealed I-693 envelope) go in the plan's `notes`, one line each, not as pages.
4. **Write the plan** to `output/working/vault/packet/<slug>/packet plan.json`, with `"base_dir"` set to the matter folder itself and every path relative to it, and with `"filing_method"`. Never point the plan at a stage workspace (`output/security/stage-workspaces/...`), even when your brief gave you one to read from: those are temporary copies that cleanup deletes, and the tool refuses a plan based inside one. Use the workspace copy to read; write the matter path in the plan. The manifest then records each source by its path in the matter folder and its sha256. Put a `separator` item (`"label": "Exhibit A"` and a one-line description) before each exhibit, `pdf`, `image`, or `docx` items for its sources (photos with `captions`, which become their bookmarks), and a `placeholder` item (label, description, and a note naming the open item) for anything still to be supplied. Give an exhibit's items the same `label`; an item without a `section` takes its exhibit's section.
   - **The I-693.** On paper, the civil surgeon's sealed envelope is enclosed unopened: the exhibit marked `physical: true` gets its separator page only, saying the envelope is enclosed, and no placeholder. Online, the scan is the exhibit's source.
5. **Name the output** `output/deliverables/Filing Packet.pdf` when no open item blocks filing, and `Filing Packet (DRAFT).pdf` otherwise. Remove the other name if it exists, so only one packet is ever current. Run:

```bash
uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/packet/assemble_packet.py" "<matter>/output/working/vault/packet/<slug>/packet plan.json" \
  --output "<matter>/output/deliverables/Filing Packet (DRAFT).pdf" \
  --manifest "<matter>/output/working/vault/packet/<slug>/packet manifest.json"
```

   Give every run `--channels "<matter>/output/working/vault/packet/<slug>/fees.json"`: the tool warns when a form is in the wrong packet of a split filing. For an online filing, also add `--split-max-mb 12` (USCIS's per-file limit): the tool writes the upload files next to the packet (each form its own PDF, the evidence by category with its exhibits in the file name) and `Upload map.md` beside them, saying for each file which submission it belongs to and where it goes in the account; the manifest's `upload_map` holds the same. Its warnings (a form missing from the upload, fewer G-28s than forms, a paper form in the upload) are findings to fix before handoff. For a paper packet the attorney will email or print, add `--max-mb <size>` only when they ask for a smaller file. Pages carry exhibit stamps and packet page numbers by default (in a clear strip at the foot, never over the document); leave them on unless the attorney asked otherwise. The forms, the payment forms and the cover letter are left unmarked and never resampled; give a form that isn't in `output/deliverables/Forms/` `"role": "form"` in the plan so the tool knows it.

   The tool checks every source before writing anything, and lists all the problems at once. On success it prints a short summary: the packet and manifest paths, the page count, the exhibit count, each placeholder's label and page, the top of a paper packet (`Order:`), and any warnings (a payment form missing or out of place, a photo too small to read). The page map stays in the manifest (`items[]`, `exhibits[]`); look up only the exhibit or page you're checking rather than reading the whole file or rerunning with `--table`. If it warns that Ghostscript is missing, add a `system` open item asking the attorney to install it, and carry on.
6. **Look at it.** Check the first pages, the index, each transition from separator to exhibit, every placeholder, any page range taken from a larger PDF, the stamps on a rotated page if there is one, and the last page, using the manifest's page numbers to find them.

## Finish

Pass the packet and its manifest to the runtime (and, for an online filing, say in the summary that the upload files were written):

```bash
uv run --script "${CLAUDE_PLUGIN_ROOT}/skills/senior-associate/scripts/run_matter_workflow.py" complete-stage "<matter>" packet_assembly --run-id <run id> \
  --status passed --summary "Assembled the packet from the exhibit plan." \
  --artifact "output/deliverables/Filing Packet (DRAFT).pdf" \
  --artifact "output/working/vault/packet/<slug>/packet manifest.json"
```

(Use the packet's actual file name.) Report the page count, the number of exhibits, the placeholders, and the fee total from `fees.json`, so the reviewer and the memo can use them.

# Attorney handoff

The handoff is what the attorney actually reads. A busy immigration attorney should be able to open the memo, know within a minute whether the packet can be filed and what stands in the way, send the client request to the client unedited, and trust that nothing was guessed.

Refresh all three files at the end of every run, even one that stops early, so they always describe the packet as it stands: `open-items.json`, `Attorney Memo.md` and `Client Request.md`, with a PDF of the memo and of the client request beside them (see "PDF copies" below). Once a packet exists, also write the filing checklist (`Filing Checklist.md` and `.pdf`), and when the client's language isn't English, the translated client request. The `attorney_handoff` stage checks the final version.

**First, the matter's settings,** from `status`: protected or not, the filing method, and the client request's language. When it says protected, everything below marked for protected matters applies, with `protected-matters.md`. The filing method decides the logistics (`filing.md`), and the language decides whether there's a translated client request.

All three are about the case, not the process. The attorney sees the open items on the matter page and reads the memo beside them, so they have to agree, and neither should show the machinery: no item ids, review codes (FR2, ADJ1), step ids (forms_preparer), file paths, "the writer", "this run", "reroute", "ledger", "vault", or tallies of internal audit errors. Name things by their plain names: the forms review, the officer's review, the cover letter, the working notes.

## open-items.json

The rules are in `matter-contract.md` under "Open items". Before writing the memo, reconcile the list, one item at a time, with `run_matter_workflow.py open-items upsert` and `open-items note`, never by rewriting the file:

- merge items the stages added: resolve a duplicate with a `resolution` naming the item it repeats, and mark items resolved where later work or the attorney's answers closed them;
- bring every open item up to the rules, because stages tend to append. Rewrite a detail that has grown into a log as one current statement and move the history to notes. Give every decision a `question`, and a `recommendation` wherever you have a view. Make `blocks_filing` match what the memo will say;
- set `packet_status` with `... open-items packet-status "<matter>" draft` (or `ready_to_file`, which it refuses while an open item blocks filing). It also marks an older list current (`"schema_version": 2`) once every item keeps the rules, and names the ones that don't.

## Attorney Memo.md

Write for a lawyer: direct, specific, no filler. Use the client's real names and the real facts; this file stays with the firm. Cite the record by document name ("Marriage certificate.pdf") and the sources checked (URL and date) so the attorney can verify anything quickly.

```markdown
# Attorney memo: <Petitioner> for <Beneficiary>, <case type>
<Filing posture> · <date> · **Draft packet — 6 things are needed before filing** (or **Ready to file**; after a document review alone, **Documents reviewed — 6 things are needed before filing**)

## Bottom line
Open with the verdict: ready to file, or not and the one or two things most in the way. Then two to four sentences: the strongest part of the case, the main risk and its cure, and what happens next.

## Needed before filing
**Your decisions (2)**
1. **<The item's question>** <Why it matters, in a sentence or two.> *Recommendation:* <one line>. <Other options, only if there's a real alternative.>

**From the client (3; all are in the client request)**
- **<Item title>.** <Why, in a clause.>

**For you to do (1)**
- **<Item title>.** <Where or how, in a clause.>

## Not needed before filing
One line each: decisions and questions that can wait, optional evidence that would strengthen the case, and risks to counsel the client on.

## Case assessment
Each eligibility element, the evidence that proves it (by exhibit), and how strong that proof is. Then the officer's strongest objection from the final review, how the packet answers it now, and what would answer it fully.

## What's in the packet
- Forms: each form, for whom, and any field left blank and why (each blank is tied to an item above)
- Cover letter: the relief requested and the theory in one line
- Exhibits: numbers and short names, with placeholders marked "to be supplied"

## Judgment calls made
Assumptions and choices made along the way that the attorney should know about: answers given under the standing "No" rule, which of two conflicting documents was followed and why, evidence left out and why.

## Filing logistics
On paper: where to file (from the current USCIS page, with URL and date checked); each fee and its payment form, from `fees.py`, with the G-1055 edition used; the physical items to gather before mailing (wet signatures, passport photos, the sealed medical exam envelope, the card or bank details on the payment forms); and the order of assembly. Online: how each form goes (the fees tool's `channels`, and any form that goes on paper and why), the upload files and `Upload map.md`, the fees to pay in the online account, the wet signatures to scan, and the I-693 scan with the original kept. A split filing has both lists, one per packet. `filing.md` has the rules behind each; point to the filing checklist for the step-by-step list.

## Sources checked
Official pages and authorities relied on, with URLs and dates. Call the case-law service BIA Edge.

## How this was checked
One or two sentences: which reviews were done independently of the work they checked, what they sent back and that it was fixed, and that the reviewers' full notes are kept with the working notes.
```

"Needed before filing" lists the open items with `blocks_filing: true`, one line each, named by their titles so the memo and the matter page read the same. Each group's count is the number of its items, and the counts add up to the number in the status line. Client questions count under "From the client"; a setup problem counts under "For you to do". Leave out an empty group. The photos, signatures and payment details aren't needed before filing (the contract's "Physical filing items"); they go under "Filing logistics". The I-693 item, while it's open and blocks filing, is listed under "Needed before filing", in "For you to do", and counted in the status line like any other blocking item; "Filing logistics" still says how the envelope is enclosed or the scan uploaded.

Keep the memo as long as the matter needs and no longer. A clean, complete packet might need a page; a difficult one might need five.

In a protected matter, put this note directly under the title line, before the bottom line:

```markdown
> **Confidential (8 U.S.C. 1367).** Send the client request only through a channel the client has said is safe. Every client mailing address on the forms is the safe address: <the address, or "our office">.
```

If the record doesn't say which channel is safe, say so in the note and list the item to confirm one under "For you to do".

## Client Request.md

This goes to the client, so write it for them: plain English, warm, short. No legal analysis, no risk assessment, no internal notes, nothing about the attorney's strategy. Tell them what to send, why it's needed in one plain sentence, and how to get it if that isn't obvious.

The attorney's Copy button turns it into plain text for an email. So use only headings, bold, numbered lists, bullets (one level of sub-bullets at most), and bare URLs, which all survive that.

```markdown
# Documents and information we still need

Hi <first names>, thank you for everything you've sent so far. Your application is well underway. To finish it, please send us the items below. You don't need to wait until you have everything: send each one when it's ready.

## Needed before we can file
1. **<Document>.** <Why, in one plain sentence.> <How to get it, if that isn't obvious.>

## Questions
**For both of you**
1. ...

**For <first name>**
2. ...

## Questions we'll go over together
Some questions are easier to talk through than to write down. Please think about these, and we'll go over them with you; you don't need to write the answers.
- ...

## To bring when you sign
1. **Passport-style photos:** <n> of <name>, taken within 30 days before we file. We'll tell you when to get them. A pharmacy photo counter is fine.

## Optional, but it makes your application stronger
1. ...

## How to send things
Reply to this email with photos or scans; a clear phone photo of each page is fine. Keep the originals unless we ask for them.

If anything is hard to find, let us know and we'll help you figure out an alternative.

<Attorney name>
<Firm name>
<Phone> · <Email>
```

- Sign it with the attorney's name, firm, phone, and email from "Your details". If those are empty, end with "Thank you," alone.
- Don't count or number the lists in the introduction; if you refer to one, use its heading.
- Put a question under "we'll go over together" when its answer could change a sworn answer or admissibility: why the client came and what they told the officer at entry, work without authorization, how they've supported themselves, earlier status filings, arrests, and past misrepresentation. The attorney needs to hear those answers before anything is written down.
- An affidavit has to be sworn, not just signed: say so in those words, and that we'll send a template with the exact wording.
- Say when a timed item should be obtained, such as photos within 30 days of filing, or booking the medical exam early because appointments fill up.
- The optional list holds documents only; a question goes under "Questions".

In a protected matter, write the request so it's safe if someone else reads it, as `protected-matters.md` says ("The client request and client-facing items").

Only client-facing items belong here. Ask for every open `client_document` item, and every factual question the client (not the attorney) can answer. If an item matters only under one answer to a pending attorney decision, keep it off the open items until the attorney answers, and mention it in the memo instead. Under "To bring when you sign", list the physical filing items the client supplies, such as photos and the sealed medical exam, with how to get them. If nothing is needed from the client, write a one-line file saying so.

## Client Request in the client's language

When `client_language` in the matter's settings is anything but English, write `output/deliverables/Client Request (<Language>).md` (for example `Client Request (Spanish).md`) next to the English one, every time you refresh the English one. `Client Request.md` stays in English and is the one the memo refers to.

- The first line is in English, for the attorney: "<Language> translation of the client request; check it before sending." Then a blank line, then the translation.
- Translate the whole English request, section by section, with the same items in the same order. Add nothing and leave nothing out. Keep people's names, dates, numbers, form numbers and URLs exactly as in English. Translate a document's name so the client understands it, with the English name in parentheses the first time ("acta de matrimonio (marriage certificate)"), so the client and the firm mean the same document.
- Plain words a client reads easily, in the polite form the language uses with a client. Same formatting limits as the English one (headings, bold, numbered lists, bullets, bare URLs), because the Copy button turns it into plain text.
- In a protected matter, the translation is just as neutral as the English.
- If you can't translate into the language reliably, don't write the file; add an `attorney_action` item asking the attorney to have the client request translated, and say so in the memo.

## PDF copies

The attorney gets the memo and the client request both ways: the Markdown, which the app shows and copies from, and a PDF to print, file or send. The Markdown is the source. Every time you write or change `Attorney Memo.md`, `Client Request.md` or a translated client request, render it again to a PDF of the same name beside it:

```bash
uv run --script "<plugin root>/scripts/packet/render_document.py" "<matter>/output/deliverables/Attorney Memo.md" --formats pdf
uv run --script "<plugin root>/scripts/packet/render_document.py" "<matter>/output/deliverables/Client Request.md" --formats pdf
```

Never edit a PDF. One older than its Markdown is out of date: the app opens the Markdown instead, and `attorney_handoff` won't pass with an English one missing or out of date. If the renderer refuses the English memo or request over a character the font can't draw, write it another way (a name romanized as on the passport) and render again. If it refuses a translation because the font can't draw its script, keep the translation's Markdown alone.

## Filing Checklist.md

Once a packet exists, write `output/deliverables/Filing Checklist.md`, the attorney's printable list for the day the packet is signed and sent, and render it to `Filing Checklist.pdf`:

```bash
uv run --script "<plugin root>/scripts/packet/render_document.py" "<matter>/output/deliverables/Filing Checklist.md" --formats pdf
```

Use checkboxes (`- [ ]`) for every step, in the order they're done, and plain names (no ids, paths, or step names):

```markdown
# Filing checklist: <Petitioner> for <Beneficiary>, <forms>

<Paper filing | Online filing> · <date> · packet of <n> pages

## Fees and payment
- [ ] Form G-1450 (card) or G-1650 (bank account) for the I-130: $675. The payer fills in the card or bank details and signs.
- [ ] ... one line per fee, from fees.py (a Pub. L. 119-21 fee is its own line, with its own payment form). Total: $<total>.

## Signatures
- [ ] <Name> signs <form>, <part and item>, by hand, and dates it the day of signing.

## To gather
- [ ] <n> passport-style photos of <name>, taken within 30 days.
- [ ] The civil surgeon's sealed I-693 envelope, unopened.

## Assemble and send
- [ ] Payment forms on top, then <the G-1145 if used,> the cover letter, the forms, and the exhibits, in the packet's order.
- [ ] Mail to: <the address from the current USCIS page, with the date checked>.

## Keep
- [ ] A complete copy of everything sent, and the tracking number.
- [ ] The receipt notice when it arrives.
```

- Fees: from `fees.py` for the packet's forms (the same figures as the memo), with the G-1055 edition.
- Signatures: who signs which form and where, from each form's signature part; the attorney's G-28 and preparer blocks too.
- To gather: the physical filing items from the open items.
- Online: replace "Fees and payment" with "Pay in the online account: $<total>" (no payment forms); replace "Assemble and send" with the upload steps from the packet manifest's `upload_map`, one block per submission (sign in to your representative account, File a Form Online, the lead form, "Upload a Filled-Out PDF Form", the companion forms it asks for, then each file as `Upload map.md` says), pay, submit, and watch the account for USCIS's acceptance (`filing.md`, "The packet").
- A split filing: both checklists, the online one first, then the paper one for the forms the fees tool sends on paper (its own payment forms and address), each with its reason.
- A protected matter: on paper, the mailing step is the address the letter's `filing_location` names, from the lead form's current address page. Never write the client's current location.
- If a figure or an address couldn't be checked, say so on its line instead of guessing.

# Protected matters (8 U.S.C. 1367)

Read this when `status`, or your brief, says the matter is protected. Under 8 U.S.C. 1367, USCIS may not disclose information about these clients, outside narrow exceptions, or rely on information that comes only from the abuser. The firm's share of that protection is making sure the case never reaches the abuser through the mail, a shared phone or inbox, or a page someone else picks up.

## Which matters are protected

Every stage takes the answer from `status` (or the brief), never from its own reading of the case type. A matter is protected when:

- **its settings mark it.** The app marks every VAWA case type it offers (the I-360 self-petition, alone or with the I-485, and a VAWA-based I-485 or I-765), the I-751 battery or extreme cruelty waiver, and every T or U matter (the I-914, the I-918, an I-485 based on T or U status). The attorney can mark any matter. The document review marks it when the record shows battery or extreme cruelty, trafficking, or a qualifying crime: `run_matter_workflow.py set-protected "<matter>" --on --reason docs_review --run-id <run id>`;
- **or its recorded case type can only be a protected case:** one that names VAWA, a self-petition, a battered spouse or child, extreme cruelty, abuse, trafficking, the I-914 or I-918, or a T or U visa. An I-360 or an I-751 waiver alone isn't one (the I-360 also serves special immigrant juveniles and religious workers, and an I-751 waiver may rest on divorce or hardship), so the document review marks those when the record shows abuse.

Only the attorney lifts it (`set-protected --off --reason attorney`). If you think it was set in error, add an `attorney_decision` item.

## The safe mailing address

Every client mailing-address box on every form uses the safe mailing address: the attorney's office address from the profile's `mailing_address`, in care of the firm (or the attorney, when there's no firm name), unless the attorney gave another address for this client. That covers the I-360, the I-485 mailing address, the I-765, the G-28's client address, and any form added later. A client mailing address other than the safe address is a `blocker` owned by `forms_preparer`, because USCIS mail sent there could reach the abuser.

- If the profile has no `mailing_address`, leave those boxes blank and tie them to one `attorney_action` item, blocking filing, asking the attorney to add their address in "Your details".
- Physical addresses still come from the record; the safe address never replaces one. If the client's physical address is shared with the abuser, add an `attorney_decision` item.
- The abuser's address goes only where a form asks for it (the I-360's Part 10 item 10, the last address the two shared). It never goes in a mailing-address box, the letter, an exhibit description, or the client request.
- A later change of address follows the VAWA, T, and U instructions at uscis.gov/addresschange, which the I-485 instructions point to.

What the current instructions say (checked 2026-10-28):

| Form, edition | Where the safe address goes | What else the form expects |
| --- | --- | --- |
| I-360, 01/20/25 | Part 1 item 7, "Alternate and/or Safe Mailing Address" (a VAWA self-petitioner skips to item 7), and Part 3 item 2, the mailing address | The form requires Part 3 whenever item 7 is used; give the safe address in both. Without item 7, USCIS may use the preparer's address (instructions, p. 5). Part 10 item 12 asks for the (c)(31) work permit on approval. |
| I-485, 09/18/26 | Part 1 item 18, the mailing address ("Safe or Alternate Address, if applicable") | Answer No to whether the physical address is also the mailing address; the physical address stays in item 18 (instructions, p. 5, item 7). |
| I-765, 08/21/25 | Items 5.a-5.f, where the card is mailed | Item 6 is No, with the physical address in items 7.a-7.e, unless the client lives at the safe address. The note to items 5.a-5.f names the attorney's address as a safe address. |
| G-28, 09/17/18 | Part 3 items 13.a-13.h, the client's mailing address (no in-care-of line) | The instructions allow the attorney's business address here only when it is the safe address on the form filed with the G-28, which it is by default. Part 4 items 1.a and 1.b send original notices and secure documents to the attorney; recommend them, as an `attorney_decision` for the client to confirm. |
| I-131, 01/20/25 | Item 3, "Current Mailing Address (Safe Address, if applicable)" | The physical address goes in item 4. |

## Where a paper filing goes

The lead form's address page decides, by form and basis, not the matter's protection. `<plugin root>/scripts/packet/filing_locations.py --form <lead form> --basis <basis>` says whether it's the "Attn: 1367" lockbox for the state where the client lives or the form's own address page, and names the page to re-read today; its section of the packet tools README holds the rule and the dates. Forms filed with the lead form go with it. Online, there is no lockbox.

## The cover letter

Put `protected: true` in the front matter. On paper and online alike, near the top, say the filing is protected by 8 U.S.C. § 1367 and ask USCIS to send every notice and document to the safe mailing address on the forms ("Please direct all correspondence to the safe mailing address on the enclosed forms, in care of counsel."). On paper, also give `lead_form`, `filing_basis` and `filing_location` (`1367 lockbox` or `form page`) from `filing_locations.py`, address the letter there, and record the date you checked the page; online, address it to "U.S. Citizenship and Immigration Services" alone. The abuser's address and the client's current location stay out of the letter and the exhibit descriptions; the forms carry what USCIS needs. The render audit checks the front matter, the address block and the request.

## The client request and client-facing items

The client request has to be safe for someone else to read, in English and in any translation. Use neutral words: "documents about your relationship and your safety", not "evidence of abuse"; "a local police record check from each place you've lived for six months or more in the last three years", not "good moral character evidence". Leave out the abuser's name, the case type, the form numbers that would name it, and VAWA. Keep the usual title and greeting, which are already neutral.

Write every client-facing open item the same way, since the request is built from them and the app shows them on screen: an open `client_document` or `client_question` item (or any item `"who": "client"`) may not name the case or what happened to the client in its title, question, recommendation, or detail. The runtime refuses it at the handoff.

## The memo

The memo opens with a confidentiality note (its wording is in `handoff.md`): the matter is protected by 8 U.S.C. 1367, and the client request goes only through a channel the client has said is safe. If the record doesn't say which channel that is, add an `attorney_action` item to confirm one before anything is sent. The memo itself stays with the firm and uses the real names and facts, and so does the filing checklist, which never gives the client's current location.

## What shows on screen

The dashboard shows stage summaries, blockers and the timeline, so the runtime refuses, in every matter, a summary or blocker that names a protected case type or what happened (VAWA, I-360, abuse, battery, extreme cruelty, domestic violence; T and U case names: I-914, I-918, T or U visa, trafficking, a qualifying crime), whatever the stage's status. In a matter marked protected it also refuses words that would tell a reader what kind of case it is (victim, self-petition, 1367, violence, assault, stalking, a protection order), and holds client-facing open items to the same words. The workflow record keeps the case type only in its intake block, and the timeline names steps, never the case.

The app names a protected matter's folder by the client's surname and the form numbers only ("Example I-360 I-485"), never with a word that says what the case is about (VAWA, waiver, abuse, T or U visa), because a folder name shows in Finder and on screen. Never rename the folder, and never put such a word in it or in the name of a file you create. Records that show where the client lives now get the care the VAWA evidence checklist describes (`skills/docs-review/references/checklists/i360_vawa.md`).

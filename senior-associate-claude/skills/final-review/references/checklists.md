# Final review checklists

These lists back up the checks in SKILL.md so nothing routine gets skipped. They don't replace reading the packet. Policy Manual guidance changes, so confirm any officer theory against current authority before you rely on it.

## High-risk form fields

- legal names, aliases, and consistent spelling across every form
- dates of birth, country of birth, and citizenship
- passport numbers and expiration dates
- A-numbers, I-94 numbers, receipt numbers, and Social Security numbers
- the current address and the full address history, with no gaps in the required period
- marital history for both spouses, including every prior marriage and how it ended
- the date, place, and manner of last entry, the class of admission, and current status
- employment history, with no gaps
- the criminal, immigration-violation, and other inadmissibility yes/no answers
- family sections: parents, spouse, children
- repeated-row sections on dynamic USCIS PDFs, where values are easily lost or misplaced
- the attorney, preparer, and interpreter blocks
- signatures and signature dates

## Residual problems

- a non-English document without a full certified English translation (8 C.F.R. 103.2(b)(3)); a summary, an excerpt or a partial translation doesn't meet it
- an unsigned declaration or affidavit
- an expired identity document, or a notice that a newer one has superseded
- duplicate or contradictory documents among the exhibits
- an enclosure the letter mentions (a payment form, photos, a sealed envelope) that isn't there, or a paper check
- on paper, a payment form that isn't on top of the packet, out of the fees tool's order, or missing for a fee, or one payment covering several fees; online, any payment form or G-1145 at all (the senior-associate skill's `references/filing.md`)
- a blank on an edition its uscis.gov page no longer lists or accepts, or a form whose page the live edition check couldn't read and no one checked by hand
- an I-485 without its I-693 (or the partial one the applicant's category allows)
- a "to be supplied" placeholder with no matching open item
- assembly problems that would confuse intake, such as a missing separator, a rotated page, or a blank page

## Mapping elements

For each element, write one line: the element, its legal source, the primary evidence expected, what the packet offers, and whether that proves it by a preponderance. Then cover:

- **threshold eligibility:** the status of the petitioner or applicant, the qualifying relationship, and any time requirements
- **admissibility:** the grounds the facts raise, and any exception or waiver in play
- **procedural prerequisites:** lawful admission or parole for 245(a), the filing posture, prior filings, and concurrent-filing rules
- **discretion,** where the benefit is discretionary

## Officer theories that most often drive an RFE, NOID, or denial

Read the theories for the case type in `theories/<key>.md`, with the key from the matter contract's "Matter types" table (the authorities files carry the citations). A packet with two benefits (an I-485 with an I-765 and I-131, say) gets every file that applies, and every packet with an I-485 also gets these:

**Adjustment of status (any I-485)**
- No evidence of inspection and admission or parole: the I-94 or other entry evidence is missing or contradicted.
- Intent at admission: conduct soon after a nonimmigrant entry that suggests a preconceived intent to stay (8 USCIS-PM J.3).
- Unauthorized employment or status violations where the immediate-relative exception (or 245(k)) doesn't apply.
- An I-864 short of the guideline: the wrong household size, income without the most recent year's transcript or return and W-2s, an I-864A household member without their own most recent return, or a missing joint sponsor.
- A missing I-693, or one opened on a paper filing.
- Criminal history without certified dispositions.
- Discretion: PM-602-0199 (May 21, 2026) treats adjustment as discretionary; a record with no affirmative equities invites the question.

## Filing destination

Take the address only from the current USCIS page for the form, and say which facts control it: the case type, the applicant's state, the category, and courier or USPS. If a controlling fact isn't clear from the record, make the finding `manual_review` and say what's missing.

## Protected matters

When `status` or the brief says protected, check each rule in the senior-associate skill's `references/protected-matters.md`: the safe mailing address in every client mailing-address box (its table names them), the physical addresses and the abuser's address, where a paper filing goes (re-read the page `filing_locations.py` names; a letter sent to the wrong lockbox, or an online letter that names one, is a finding), the letter's 1367 request, a client request that reads safely if someone else sees it, and the memo's confidentiality note.

# Letter craft

The default form of a USCIS cover letter in this plugin. When the firm supplies model letters, the closest model letter's choices win.

## Shape

1. **Letterhead, date, delivery line, and USCIS address.** On paper, use the filing address from the current USCIS page for this form and these filing assumptions, and record the URL and date checked. Online, the letter is uploaded: address it to "U.S. Citizenship and Immigration Services" alone, with no delivery line or street address (front matter `filing_method: online`).
2. **RE block:** the benefit and form numbers; petitioner, beneficiary, or applicant names, with A-numbers and receipt numbers where they exist; and, for a response, the notice type and date.
3. **Salutation:** "Dear Sir or Madam:" or "Dear Officer:".
4. **I. Introduction.** One paragraph: who files what, for whom, under which provision, and the request in one sentence ("We respectfully request that USCIS approve...").
5. **II. Argument** (titled "Legal Standard and Eligibility" or similar):
   - the governing standard: statute, regulation, burden of proof (preponderance unless a heightened standard applies), and the Policy Manual chapter;
   - a proof block for each element, under a lower-roman italic subhead (*i. The Petitioner Is a U.S. Citizen*). Give each block one or two tight paragraphs stating the fact, the evidence (Exhibit X), and why it proves the element;
   - a block that answers the likeliest doubt (*iv. The Marriage Was Entered in Good Faith Despite the Short Courtship*) with evidence, not adjectives.
6. **III. Conclusion.** The request again, and an offer to provide anything further.
7. **Signature block** from the attorney profile.
8. **Exhibit list ("Index of Exhibits").** Group items under section headers by what they prove (Forms; Petitioner's Status; Bona Fide Marriage: Joint Residence; ...), in the dialect's fenced `exhibits` block. The payment forms aren't exhibits: on paper they sit on top of the packet, and online the fee is paid in the account. Exhibits under a "Forms" section are enclosed, not argued, and need no citation in the body. The renderer letters or numbers them continuously across groups. Describe each item specifically ("Joint lease, 123 Main St., June 2022 to May 2023", not "Lease"). Put `<!-- signature -->` before the index when it follows the signature.

**Length.** Put `matter_type` in the front matter, and the audit warns, with the word count, when the argument (paragraphs, quotes and lists, not headings or the exhibit index) runs past its budget: `i765` 600 words, `i131` 700, `n400` and `i485_asylee_refugee` 900, `i130_standalone` and `i129f` 1,000, `i751_joint` 1,200, `i130_i485` 1,500, `i751_waiver` 2,500, `i612`, `i601a`, `i601`, `i140_i485` and `i360_vawa` 3,000, and `i140_niw` 6,000 (an NIW letter is the petition's argument, not a covering note). A response to an RFE or NOID (`rfe_response`, `noid_response`) has no budget: it takes as many words as the notice's grounds need, and no more. Over budget, cut first what the record doesn't need. An issue the record doesn't raise is a question for the attorney (an `attorney_decision` recommending the leaner letter), not a section. Set `length_budget` only when the attorney wants the longer letter.

**A national interest waiver** (`i140_niw`). The letter is the petition's argument, and USCIS says a petition organized around the issues "in the order USCIS follows when adjudicating ... should assist adjudicators" (EB-2 page, NIW filing tips, updated 01/15/2025, checked 2026-10-30). So the argument takes that order:
1. **EB-2 eligibility:** the advanced degree (or the bachelor's and five years of progressive experience after it), or exceptional ability; and that the occupation behind the endeavor is a profession.
2. **The proposed endeavor**, defined once, specifically: what the petitioner will do, how, and where. Reuse those words wherever the endeavor comes up, and keep them identical to I-140 Part 6 and the ETA-9089 Appendix A.
3. **Prong 1** (substantial merit and national importance), **prong 2** (well positioned) and **prong 3** (on balance, the waiver benefits the United States), each a section under *Matter of Dhanasar*, with every claim tied to an exhibit.

Argue national importance from the endeavor's own broader implications, never from the field's importance, a labor shortage, or the employer's benefit. Describe each expert letter by what the writer saw first-hand and where the record corroborates it, rather than quoting its praise. Don't cite *NYSDOT*. The authorities file is `i140_niw.md`.

**Protected matters** (front matter `protected: true`): the letter's request, its address and what stays out of it are in the senior-associate skill's `references/protected-matters.md`, "The cover letter".

## Writing

- Lead with the conclusion, then the proof. Officers skim, so a paragraph's first sentence should carry its point.
- Be concrete. "Joint bank statements for 14 consecutive months (Exhibit F)" persuades; "extensive evidence of commingled finances" doesn't.
- Don't overstate. Avoid "clearly", "undeniably", "no issues", and "straightforward case" unless the record shows it, because an officer reads overstatement as a tell.
- Use the clients' names as the documents spell them, consistently.
- Use English only. Quote a non-English document only from its certified translation.
- Never include facts the client hasn't documented, internal notes, or anything about strategy the attorney hasn't approved.

## Citations

- Statute: INA § 245(a), 8 U.S.C. § 1255(a). Regulation: 8 C.F.R. § 204.2(a)(1)(i)(B). Policy Manual: 7 USCIS-PM B.2(A) (cite the volume, part, and chapter, and note the date accessed for anything that changes often).
- Cases: italicize the full name, and give the reporter cite and a pinpoint. Use a short form after the first cite. *Matter of Laureano*, 19 I&N Dec. 1, 3 (BIA 1983).
- Cite the strongest single authority for routine points. String cites belong only where the point is contested.
- Every authority must appear in the support matrix as verified.

## Exhibits and the packet

The exhibit list is the packet's table of contents. Every item maps to a real document, or to a "to be supplied" placeholder tied to an open item, in `exhibit plan.json`:

```json
{"labels": "letters",
 "exhibits": [
   {"label": "A", "section": "Forms", "description": "Form G-28, Notice of Entry of Appearance", "sources": ["output/deliverables/Forms/G-28 - Petitioner.pdf"]},
   {"label": "F", "section": "Bona Fide Marriage: Joint Residence", "description": "Joint lease, June 2022 to May 2023", "sources": ["Lease 2022.pdf"], "pages": "1-4"},
   {"label": "G", "section": "Admission", "description": "Beneficiary's most recent I-94 arrival record", "placeholder": true, "open_item": "doc-i94"}
 ]}
```

Source paths are relative to the matter folder. `pages` is optional, 1-based, and inclusive.

**The I-693** goes in with the I-485 (the matter contract's "Open items" has why its item blocks filing):

- **On paper,** it's an exhibit but never a scan: the civil surgeon's envelope goes in unopened. List it as enclosed ("Form I-693, in the civil surgeon's sealed envelope"), and mark it `"physical": true` with no sources, plus `"open_item"` naming its `attorney_action` item. Don't mark it as a placeholder.
- **Online,** the client opens the envelope, the I-693 is uploaded, and the client keeps the original and the envelope until USCIS decides the case. List it with the scan as its source, or as a placeholder until the scan exists.

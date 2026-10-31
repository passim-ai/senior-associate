# Forms playbook

Common form sets and the places where prepared forms most often go wrong. Confirm every set against the current USCIS instructions; filing rules change.

## Common form sets

| Case | Usual forms | Often added (attorney's call) |
| --- | --- | --- |
| Immediate-relative spouse, concurrent adjustment | G-28 per represented party, I-130, I-130A, I-485, I-864 (plus I-864A or a joint sponsor's I-864 if needed), I-693 (see below) | I-765, I-131 |
| Immediate-relative parent or child, concurrent | G-28, I-130, I-485, I-864, I-693 | I-765, I-131 |
| I-130 alone (consular processing) | G-28, I-130 (and I-130A for a spouse) | none |
| I-751 joint | G-28, I-751 | none |
| I-751 waiver | G-28, I-751 | none |
| N-400 | G-28, N-400 | I-912 if requesting a fee waiver |
| I-765 alone | G-28, I-765 | none |
| I-131 alone | G-28, I-131 | none |
| I-129F | G-28, I-129F | none |
| I-601A provisional waiver | G-28, I-601A (`i601a_provisional_waiver`), filed alone: USCIS rejects it with an I-485, I-130, I-212, I-131 or I-765 | G-1145 |
| I-601 waiver | G-28, I-601 (`i601_inadmissibility_waiver`), with the I-485 when it is filed with one | I-212 for someone previously removed |
| I-140 national interest waiver (EB-2 NIW) | G-28, I-140 (`i140_worker_petition`, Part 2 box 1.h) | I-907 (`i907_premium_processing`) for premium processing, which sends the I-140 by mail; the I-485 with its I-693 (see below), I-765 and I-131 when a visa is available, with no Supplement J and, for a self-petition, no I-864; G-1145 on paper |
| VAWA self-petition | G-28, I-360 (`i360_vawa_self_petition`) | I-485 with its I-693 (see below), plus I-765 and I-131, when concurrent filing is allowed (a U.S. citizen abuser, or an LPR abuser with a visa number available); no I-864 (the I-485's Part 3 claims the exemption) |

When the attorney represents more than one party (for example the petitioner and the beneficiary), each one gets their own G-28.

## The I-140 for a national interest waiver

- **A self-petitioner** gives their own name in Part 1 items 1.a-1.c (no company name and no EIN), checks Self in Part 5 item 1, and gives their occupation and annual income in Part 5 items 11-12; Part 3 names the same person. Every petitioner answers Part 1 items 5 and 6, or USCIS rejects the petition, and a self-petitioner answers No to item 5 and Yes to item 6, which sets the $300 Asylum Program Fee (uscis.gov/i-140 filing tips, updated 07/24/2026, checked 2026-10-30). The audit checks all of this.
- **An employer filing an NIW** fills Part 1 as a company with its EIN, and Part 5 items 2-7. The beneficiary still signs the ETA-9089 Final Determination.
- **Part 6** is the proposed employment: the job title and SOC code of the occupation through which the endeavor is pursued (which decides whether the beneficiary is a member of the professions), and in item 3 the endeavor in the same words the letter and the ETA-9089 Appendix A use. The wage is the expected pay for that work from the record; when the record has none (a new company, say), it is a `client_question`, never a guess.
- **Part 4** item 1: a visa abroad (with the consulate) or adjustment in the United States; item 6: whether an I-485, I-765 or I-131 goes with it. Part 7's answers about whether each family member will adjust or apply abroad are not binding but should reflect their intent at filing (instructions, p. 7).
- **The I-907** (`i907_premium_processing`), when the attorney wants premium processing: one per petition, requested by the petitioner (Part 1 item 8.A) or the petitioner's attorney (8.B), never by a beneficiary as such. A self-petitioner gives their own name in Part 1 item 3, leaves item 4 (company) blank, and is both the petitioner and the beneficiary in Part 2 items 4-5: with no company, a blank or "N/A" there gets the I-907 rejected (uscis.gov/i-907, checked 2026-10-30). Item 3 is the classification, E21 NIW. Filed with the I-140, the receipt number (item 2) stays blank; to upgrade a pending I-140, fill all of Part 2, receipt number included. The requestor signs in ink; an attorney requestor needs a G-28 unless one is already in the case. The I-907 and the I-140 then go by mail together.
- **The ETA-9089 Appendix A and Final Determination** are Department of Labor forms the tools don't fill. Record an `attorney_action` to prepare them from the fact table, with the same job title, SOC code and endeavor as Part 6, and leave the signatures for the petitioner, the attorney and the beneficiary.

## The I-693 medical exam goes in with the I-485

The I-693 is part of the I-485 filing, not an optional extra: its open item blocks filing (the matter contract's "Open items"), and the document review's checklist says who needs the full exam, the vaccination record alone, or none. The applicant's side is Parts 1-4 (`i693_applicant_part`: information about the applicant, the applicant's statement and signature, and any interpreter and preparer); the civil surgeon completes Parts 5-8 and 10 and hands the form back in a sealed envelope, and USCIS returns an I-693 whose envelope was opened or altered (I-693 instructions).

## Fact areas that go wrong

- **Names:** legal name versus other names used; spelling that differs across documents (record each variant with its source, and add a `client_question` if they conflict).
- **Address and employment histories:** gaps in the required look-back period, overlapping dates, and "present" versus a date.
- **Last entry:** date, place, manner, class of admission, and I-94 number come from the I-94 or the passport stamp, never from memory or an old form.
- **Marital history:** every prior marriage for both spouses, with how and when it ended, and the document that proves it.
- **Family sections:** parents, children, and dependents, including children not immigrating.
- **The I-864:** household size, income year, which tax year's return or transcript, joint sponsor details.
- **Repeated rows:** the second and later rows of a history table, where values land in the wrong box or vanish. Look at the rendered page.
- **Counsel blocks:** the G-28 parts and every preparer block. These come from the attorney profile only.
- **Signatures and dates:** leave them for the signers. They're `pending_signature`, not missing.

## Known form defects

A few editions have mistakes in the PDF that you work around rather than fix. The tools print a warning with what to do (the forms README, "Known form defects"). The I-130A has no page of its own on uscis.gov: it's published on the I-130 page and shares the I-130 instructions, which the download handles; confirm the edition in its footer.

## Sources, strongest first

1. Government-issued records: passports, I-94s, visas, notices, civil documents
2. Signed client documents: intake questionnaires, declarations, retainers
3. Financial and employment records: tax returns and transcripts, W-2s, pay stubs, employer letters
4. The attorney's explicit instructions, recorded as facts with "attorney instruction" as the source
5. Previously prepared forms: corroboration only

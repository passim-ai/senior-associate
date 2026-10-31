# Evidence Checklist Seeds

Use these as starting points for a docs-review pass. They are not a substitute for current official USCIS form instructions, the current USCIS form page, or attorney judgment. This file holds the rules for every matter; each case type's own list is `checklists/<key>.md`, with the key from the matter contract's "Matter types" table (the final review's officer theories use the same keys). Read this file and your case type's. Each list names the instructions edition it was built from and the date it was checked; when the form page shows a newer edition, follow the new instructions and note the difference in the memo. Some instruction PDFs on uscis.gov (the I-140, I-612 and I-131 on 2026-10-29) carried a "Draft / Not for Production" or "Not for Reproduction" watermark although their editions matched the form page; note one in the memo.

## Classification Rules

- `required`: needed to prove an eligibility element, complete a required form filing package, or satisfy current USCIS instructions.
- `required_if_applicable`: required only if the fact pattern triggers it, such as prior marriages, arrests, translations, co-sponsors, name changes, or waiver grounds.
- `suggested`: useful to strengthen bona fides, credibility, discretion, or RFE prevention, but not a filing blocker by itself.
- `optional`: helpful only at the margins.
- `not_applicable`: does not apply to the explicit matter type and filing posture.

When official instructions are unavailable, label required items as `provisional_required` in the memo and report the source-check blocker.

## Universal Client Document Categories

Review every matter for these categories unless the filing posture makes them irrelevant:

- Identity: passports, birth certificates, national ID, driver's license, green card, EAD, Social Security card.
- Status and immigration history: I-94, visas, approval notices, receipt notices, prior USCIS decisions, removal records, parole documents.
- Civil status: marriage certificates, divorce decrees, death certificates, name-change orders, adoption or custody records.
- Translations: every foreign-language document needs "a full English language translation which the translator has certified as complete and accurate, and ... the translator's certification that he or she is competent to translate from the foreign language into English" (8 C.F.R. 103.2(b)(3), eCFR current as of 2026-10-28, checked 2026-10-29). A summary, an excerpt, a translation of only some pages, or a translation without both certifications is `partial`.
- Filing logistics: signatures, passport photos, the fee and how it's paid (the senior-associate skill's `references/filing.md`), the medical exam with every I-485 (below), mailing address facts.
- Adverse history: arrests, dispositions, probation records, immigration violations, prior fraud or misrepresentation records, prior removal or voluntary departure records.

## Common RFE triggers (any matter type)

- **Birth certificates.** The I-485 instructions (ed. 09/18/26) point to the State Department's Reciprocity Schedule "to determine how to obtain a birth certificate from your country of birth"; when one can't be had, secondary evidence (church or school records) and, failing that, two or more affidavits. The I-130 instructions (ed. 04/01/24) ask first for a statement from the civil authority that the record isn't available, then secondary evidence: a religious record of baptism within two months after birth, school or census records, or two or more written statements from people with personal knowledge. 8 C.F.R. 103.2(b)(2)(i): when a required document "does not exist or cannot be obtained, an applicant or petitioner must demonstrate this and submit secondary evidence". (All checked 2026-10-29.) Compare each foreign birth certificate with the schedule's entry for the country (which document it lists, and any notes on extracts or delayed registration), and mark one that doesn't match `partial` with the reason. The schedule itself couldn't be read on 2026-10-29, so check it live.
- **The I-864's tax evidence.** The sponsor gives "either an Internal Revenue Service (IRS) transcript or a photocopy ... of your Federal individual income tax return for the most recent tax year"; with a photocopy, "each and every Form W-2 and Form 1099" (I-864 instructions, ed. 08/24/26). Each I-864A household member gives the same for their own most recent return, plus proof of the relationship and of sharing the sponsor's residence, except a spouse, and a dependent on the sponsor's return (I-864A instructions, ed. 08/24/26). Checked 2026-10-29. An older year's return, or a return without the W-2s, is `partial`.
- **The five-year rule, INA 204(a)(2)(A).** A permanent resident who got status through an earlier marriage and petitions for a new spouse within five years of becoming a resident needs "clear and convincing evidence" that the earlier marriage wasn't entered to evade the immigration laws (8 U.S.C. 1154(a)(2)(A)), unless that marriage ended by death (8 C.F.R. 204.2(a)(1)(i)(A)). Checked 2026-10-29. Look for it whenever the petitioner is a permanent resident with an earlier marriage.
- **The Adam Walsh Act.** A U.S. citizen petitioner "convicted of a specified offense against a minor" can't have a family petition approved unless DHS, in its "sole and unreviewable discretion", determines that the citizen poses no risk to the beneficiary (INA 204(a)(1)(A)(viii)(I), 8 U.S.C. 1154(a)(1)(A)(viii)(I), checked 2026-10-29). 6 USCIS-PM C has no guidance of its own; it points to the retired Adjudicator's Field Manual. Any arrest or conviction of the petitioner involving a minor is a `risk` item and an `attorney_decision`; before relying on this for a permanent-resident petitioner, read the parallel provision for them in INA 204(a)(1)(B).
- **Criminal records.** Where charges were filed, USCIS asks for "an original or court-certified copy of the complete arrest record and/or disposition for each incident"; where someone was arrested or detained and no charges were filed, "an original official statement by the arresting agency or applicable court order confirming that no charges were filed" (I-751 instructions, ed. 04/01/24, checked 2026-10-29; the I-129F, I-485 and I-765 instructions ask for court-certified records too). A printout, a background check or the client's account is `partial`. The I-751 instructions (pp. 5-6) spell it out:
    - Arrested or detained, and no charges filed: an original official statement by the arresting agency, or a court order, confirming that no charges were filed.
    - Charges filed, with or without an arrest: an original or court-certified copy of the complete arrest record and/or disposition for each incident.
    - Convicted, or placed in an alternative sentencing or rehabilitative program: the original or court-certified sentencing record and evidence the sentence or program was completed; any order vacating, sealing or expunging the record; or, if no record is available, an original statement from the court that none exists.
    - Not needed: traffic fines and incidents that did not involve an actual arrest, where the only penalty was a fine under $500 and/or points on the license, unless the incident was alcohol or drug related.
- **The medical exam with an I-485.** Form I-693, completed by a civil surgeon: "you must submit it with your Form I-485. Otherwise, your Form I-485 may be rejected" (I-485 instructions, ed. 09/18/26, item 9, checked 2026-10-29). The exceptions (I-693 instructions, ed. 01/20/25, FAQs 2-5, checked 2026-10-29): a refugee adjusting one year after admission, and an asylee derivative filing within a year of becoming eligible, whose overseas exam found no Class A condition, submit only the vaccination record (Parts 1-5, 7 and 10); a K-1 to K-4 entrant who files within a year of the overseas exam (no Class A condition found, or one waived and its terms met) needs no new exam but must show the vaccination requirements are met, with Parts 1-5, 7 and 10 from a civil surgeon when the overseas vaccination record wasn't properly completed; and an Afghan national who entered under Operation Allies Welcome files no I-693 when the overseas exam is in the A-file, found no Class A condition, is no more than four years old, and nothing suggests one since. A principal asylee has no exception. A civil surgeon signature dated July 3, 2025 or later must be on the 01/20/25 edition of the I-693 (uscis.gov/i-693, updated 07/24/2026, checked 2026-10-29). On paper the sealed envelope goes in unopened; online the client opens it, the I-693 is uploaded, and the client keeps the original and the envelope until USCIS decides (uscis.gov/i-693, checked 2026-10-29). Its `attorney_action` item blocks filing as the matter contract's "Open items" says; when the record doesn't show whether an exception applies, say so in the item's detail.

## Bona Fide Evidence Prioritization

Prioritize evidence that is objective, dated, and spread over time:

1. Joint residence and shared financial obligations.
2. Joint taxes, insurance, benefits, children, and legally significant records.
3. Third-party institutional records such as schools, doctors, employers, banks, and government agencies.
4. Photos, travel, messages, cards, and affidavits.

Avoid asking for large volumes of low-value evidence when a smaller set of dated objective records would be stronger.

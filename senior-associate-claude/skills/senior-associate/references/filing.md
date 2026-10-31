# Filing method, fees and payment

How each form reaches USCIS, how its fee is paid, and the packet's order. The tools that apply these rules (`fees.py`, `filing_channels.py`) are in `<plugin root>/scripts/packet/README.md`.

## How each form goes

`filing_method` (from `status` or the brief) is the attorney's choice for the whole filing: `paper` (the default) means by mail, except a form USCIS no longer takes on paper; `online` means online wherever USCIS takes the form and its category, and on paper for the rest. Which way each form goes is the fees tool's call, under `channels` in `fees.json`.

- A `PROBLEM:` line names a missing fact: find it in the record, or make it an open item; never guess it. Each `DECISION:` line is an `attorney_decision` item.
- **A split filing.** When the matter is online and a form can go only on paper, that form goes on paper, with an `attorney_decision` item giving the fees tool's reason, and the filing is two packets: the online submission's upload files, and a paper packet with its own payment forms and filing address. A VAWA I-360 and I-485 filed together go on paper (the account doesn't take an I-360 with an I-485); filing the I-360 online first and the I-485 after it is the attorney's decision.
- **Paper going away.** Since Aug. 11, 2026, USCIS may require a form online once it has been available online for more than 180 days, after 60 days' notice on uscis.gov (8 C.F.R. 103.2(a)(1)(ii)). A form past its day goes online even in a paper matter (an `attorney_decision` item), and a paper filing before the day must arrive by then; paper after it needs an approved Form I-936 waiver, which DHS expects represented filers generally not to get. When the fees tool says its list of mandates is over 30 days old, check the pages it names before a paper filing.

## Fees and payment

`fees.py` prices the filing from Form G-1055; when uscis.gov/g-1055 shows a newer edition than the tool's, say so in the memo and verify the fees there. Packet assembly saves the result as `output/working/vault/packet/<slug>/fees.json`, which the memo and the filing checklist use.

- **Paper.** Since October 28, 2025, USCIS takes no checks, money orders or other paper payments unless the payer qualifies for an exemption (Policy Alert PA-2025-19; 1 USCIS-PM B.3, current as of Oct. 27, 2026). Each fee is paid with its own Form G-1450 (U.S. card) or G-1650 (U.S. bank account): one for each form's filing fee, and one more for each Pub. L. 119-21 fee, which "must be paid by separate payment concurrent with any filing fee" (G-1055, ed. 10/26/26), all on top of the packet in the order `fees.py` lists them. One payment for several forms can get the whole package rejected (Tips for Filing Forms by Mail, updated 07/10/2026). A payer who can't pay electronically files Form G-1651 with the package, one per payer. All checked 2026-10-29.
- **Online.** The fee is paid in the USCIS online account when the filing is submitted; there's no G-1450 or G-1650.
- **Split.** Each form is priced and paid the way it goes; `payment_forms_needed` in `fees.json` lists only the paper part's fees.
- **Separate fees** (a Pub. L. 119-21 fee, the I-140's Asylum Program Fee) can't be waived.
- **The payment details.** The forms step prefills only the payer's name, the amount and the form it pays for. The card or bank details stay blank, for one `attorney_action` item, "Fill in the payment details and sign the payment form" (`blocks_filing: false`, a physical filing item). Never write card or bank numbers anywhere in the matter folder, the open items, the memo or a chat.

## The packet

- **Paper:** the payment forms (one per fee), the G-1145 if the attorney wants e-notification, the cover letter, the forms, the exhibit index, then the exhibits. The letter carries the delivery line and the filing address from the current USCIS page. The sealed I-693 envelope is enclosed unopened.
- **Online:** no payment forms and no G-1145, and the letter has no delivery line or mailing address. A representative's PDF upload needs a properly executed G-28 for each party and form, and each form printed, signed in ink by each signer and scanned (no electronic signature), with the name, date of birth and A-Number matching the online account. Each upload file is 12 MB or less ("Files must not be larger than 12MB"), and `Upload map.md` says where each goes (uscis.gov/online-filing-options, updated 10/07/2026, checked 2026-10-30). The client opens the I-693 envelope, the I-693 is uploaded, and the client keeps the original and the envelope until USCIS decides the case (uscis.gov/i-693, checked 2026-10-29). A PDF upload gets no receipt number on submission; USCIS can take up to 30 days to accept it, and a rejection comes by mail. A protected matter filed online has no lockbox.

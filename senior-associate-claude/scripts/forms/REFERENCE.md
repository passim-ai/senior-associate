# USCIS forms tools: maintainer reference

The details behind `README.md`: the separate tools `build` runs for you, what the audit checks and how, the field-mapping notes, every known form defect, the attorney-profile mapping, and the tests. A stage agent needs this file only when a tool fails and its message doesn't say why, or for a form with no schema. `<plugin root>` is the plugin's install folder.

## download_uscis_forms.py

```bash
uv run --script "<plugin root>/scripts/forms/download_uscis_forms.py" \
  --output-dir "/abs/matter/forms" --include-instructions \
  --metadata-json "/abs/matter/forms/forms-metadata.json" g-28 i-130
```

- Takes any form id with the usual uscis.gov layout (`g-28`, `i-130`, `i-485`, `i-765`, `i-864a`,
  `n-400`, ...). It fetches `https://www.uscis.gov/<id>` live and downloads the PDF the page links to.
- Some companion forms have no page of their own. The I-130A is linked from the I-130 page, and
  `uscis.gov/i-130a` is a 404. Known companions (`i-130a`, `i-539a`) go straight to the parent's
  page. For any other form whose page returns 404, the tool tries the page of the form it is
  lettered after (`i-123a` → `i-123`). The I-864A has its own page and needs neither.
- Writes `G-28.pdf` and `G-28 Instructions.pdf`, and prints each path. The metadata JSON records
  the URLs and the page's **edition date** and edition note, and `file_edition`, the edition printed
  in the PDF's own footer. For a kept file the two can differ (the page has moved on); the entry then
  says so in `file_edition_note`. A second run merges into an existing metadata JSON.
- The G-1145 page publishes no separate instructions (the form carries its own), so
  `--include-instructions` records "none published" for it instead of failing.
- For a companion form, the edition date comes from the parent page's Edition Date panel, so the
  metadata adds `parent_form` and `edition_source`. Confirm the edition printed in the PDF footer.
  Companions share the parent's instructions: `--include-instructions` saves
  `I-130 Instructions.pdf` and records `instructions_shared_with`.
- An existing file is kept unless you pass `--overwrite` (the metadata says "kept existing file").
- A transfer that drops, comes back shorter than its Content-Length, or ends before the PDF's
  closing `%%EOF` is fetched again, as is a 5xx response: three attempts in all, a few seconds
  apart. A 404 isn't retried.
- It fails if uscis.gov returns HTML instead of a PDF (a bot check). Exit code 1 if any form failed.

## xfa_tools.py

Current USCIS forms are hybrid PDFs with two layers that must agree:

- the **XFA dataset**: Adobe Acrobat and Reader display this layer;
- the **AcroForm widgets**: Preview, browsers, printers, Ghostscript and `pdftotext` display this layer.

`fill` writes the XFA dataset, then syncs the matching widgets and builds their appearances.

```bash
T="<plugin root>/scripts/forms/xfa_tools.py"
uv run --script "$T" dump-fields "/abs/G-28.pdf" --acro [--prefix Pt3]   # what each field means
uv run --script "$T" dump-fields "/abs/G-28.pdf"                          # raw XFA dataset nodes
uv run --script "$T" fill "/abs/G-28.pdf" "/abs/G-28 source.pdf" "/abs/mapping.json" --verify [--report R.json]
uv run --script "$T" extract-values "/abs/G-28 source.pdf" Pt3Line5a_FamilyName [--visible | --both]
uv run --script "$T" extract-values "/abs/G-28 source.pdf" --prefix Pt3 --both   # a whole part, both layers
uv run --script "$T" render-filing-copy "/abs/G-28 source.pdf" "/abs/G-28 filing copy.pdf"
```

- `dump-fields --acro` prints, tab-separated: the logical name (with `[n]` when the name
  repeats), the type (`Tx` text, `Btn` checkbox, `Ch` list), the exact on-states or options,
  `maxlen`, `global`, the page, and the **tooltip**. The tooltip names the real question. Read it
  before you map a field. It prints at most 40 lines, and tooltips are cut to their last 100
  characters (the item's own words); narrow with `--prefix`, read the saved JSON, or pass `--full`.
- `dump-fields` also saves the whole field list as JSON (names, types, on-states, `maxlen`,
  `global`, pages, tooltips and XFA node names, but no stored values). For a blank in a matter's
  `output/working/forms/blank/` it goes to `output/working/forms/fields/<FORM>.json`, and the
  path is printed to stderr. Helper scripts that need field types should read that file rather
  than a dump in a scratch folder, which a later session will not have. Pass `--save PATH` to
  choose the location, or `--no-save` to only print.
- The mapping JSON maps field names to values. Use `"Name[n]": value` for the nth
  occurrence of a repeated field, or `"Name": [v0, v1, ...]`. `null` skips a field and `""` clears
  it. Dates are `mm/dd/yyyy`. A checkbox takes its on-state (see `dump-fields --acro`). A
  state takes the 2-letter export value.
- `Name` and `Name[0]` are the same XFA data node, and every `[n]` of a `global` field is the
  same node too. When two mapping keys bind one node, `fill` stops with an error naming both if
  their values differ, and otherwise writes the one value and prints a warning. An empty value
  never overwrites a non-empty one for the same node. The reason is that writing both keys in
  turn would let the later one replace the earlier: an I-485 mapping with
  `Pt6Line10_CityTownOfBirth[0]: "Austin"` and `Pt6Line10_CityTownOfBirth: ""` would store a
  blank current-marriage place.
- In a repeated field that is not `global`, the nth box shows the nth data node, as in Adobe. A
  box with no node of its own is cleared, never given another box's value. So writing only the
  current-marriage place (`Pt6Line10_*[0]`) leaves the prior-marriage place boxes blank, with no
  need to write `[1]` as `""`.
- `fill` writes a new file, normally from the official blank each time, because refilling an old
  partial carries stale answers. It prints notes to stderr, one capped line per kind: values that
  exceed the box's `maxlen` (Adobe truncates them), checkbox values rewritten to the form's exact
  padded state (`STE` becomes `" STE "`), fields that exist only in the XFA layer (Adobe shows
  them, a rendered copy does not), mapping keys that share a data node, and known defects of the
  form edition (see "Known form defects"). `--report PATH` writes every note and verify mismatch
  as JSON; `--full` prints them all.
- `fill` closes the clip of every text appearance it writes. pypdf leaves it open, and
  Ghostscript then draws an empty box near the bottom of most pages of the filing copy.
- `fill` writes each value into the XFA data node the form's template binds that box to, which
  is the only node Adobe shows. Most forms keep their data directly under `form1`. The I-765
  keeps each page's answers in a data group (`form1/Page3/Line19_DOB`), and the I-485 Part 9
  certifications table sits in `form1/Table1/RowN`. `dump-fields` records each box's node as
  `data`.
- Boxes the template leaves unbound (`<bind match="none"/>`; see "Known form defects") would
  show empty in Adobe whatever the data holds. When the mapping fills one, `fill` binds it
  normally in the filled source's own template and prints a note; the blank and the filing copy
  are unchanged. A box that can't be bound without taking another field's data stays unbound:
  `fill` warns, and `--verify` fails.
- A mapping key may contain a literal dot (`P9_Line7.b.`, or escaped `P9_Line7\.b\.`). It is one
  field, not a path.
- `fill --verify` reads both layers back and exits 1 on any mismatch, listing the first five.
  It also checks what Adobe will show, so a value stored where Adobe doesn't read it fails. Where
  keys share a node it checks the value that was kept.
- `fill` removes Adobe's usage-rights signature, which stops being valid once the file
  changes. Without that, Reader would warn that "extended features" are disabled.
- The filled file is the **editable XFA source**. Keep it. The **filing copy** is the static
  render: it has no AcroForm and no XFA, and it is what you review, assemble and mail. Each of
  its pages shows the PDF417 barcode drawn in the blank form, unchanged by `fill` (checked on the
  I-485, I-130, I-130A, I-864 and G-28: the rendered barcode area matches the blank's on every
  page), so the barcode does not carry the answers. Only Adobe, printing the XFA source itself,
  draws a barcode of the answers. Nothing here regenerates it, and nothing should be described
  to the attorney as a data barcode.

## form_question_schema.py

```bash
uv run --script "<plugin root>/scripts/forms/form_question_schema.py" list
uv run --script "<plugin root>/scripts/forms/form_question_schema.py" skeleton g28_represented_client \
  --out "/abs/matter/output/working/vault/forms/main/plans/G-28 - Petitioner.plan.json"
```

`build --new NAME=SCHEMA` does the same for a matter and fetches the blank. `skeleton` without
`--out` prints the plan; with `--out` it keeps an existing plan unless you pass `--force`. Plans,
`list` and `migrate` are in `README.md`, "Question plans and schemas".

These schemas say which logical questions a plan must cover, the fields each must declare,
and which must be non-empty once a question is `filled`. `list` prints every schema with its
form, edition and a line on when to use it. Pick by form and posture:

| Form | Schemas |
|---|---|
| G-28 (09/17/18) | `g28_represented_client` (one plan per represented person) |
| I-130 (04/01/24) / I-130A (04/01/24) | `i130_family_petition` (any relationship, citizen or LPR petitioner), `i130a_spouse_beneficiary` |
| I-131 (01/20/25) | `i131_advance_parole_pending_i485` (5.A, pending I-485), `i131_travel_document` (any document type) |
| I-360 (01/20/25) | `i360_vawa_self_petition` (VAWA self-petitioning spouse, child or parent) |
| I-485 (09/18/26) | `i485_family_based`, `i485_asylee_refugee`, `i485_employment_principal`, `i485_employment_derivative_child` |
| I-751 (04/01/24) | `i751_remove_conditions` (joint petition or waiver) |
| I-765 (08/21/25) | `i765_work_authorization` (any eligibility category) |
| I-864 (08/24/26) | `i864_household_sponsor` (any sponsor type) |
| N-400 (01/20/25) | `n400_naturalization` (any eligibility basis) |
| I-129F (01/20/25) | `i129f_fiance_petition` (K-1 fiance(e), or K-3 spouse) |
| I-140 (06/07/24) | `i140_worker_petition` (any EB category, employer or self-petitioner) |
| I-612 (04/01/24) | `i612_foreign_residence_waiver` (212(e) hardship or persecution waiver) |
| I-601A (01/20/25) | `i601a_provisional_waiver` (provisional unlawful presence waiver: approved I-130/I-140/I-360 or DV selection, extreme hardship to a USC or LPR spouse or parent) |
| I-601 (01/20/25) | `i601_inadmissibility_waiver` (any ground; Part 4 section A immigrant visa, adjustment, K or V; B T or SIJ; C TPS) |
| I-907 (04/01/24) | `i907_premium_processing` (premium processing of an I-140, an EB-2 NIW say, filed with it or to upgrade it once pending; also the I-129, I-539 and I-765; one per petition or application) |
| I-864A (08/24/26) | `i864a_household_member` (one per household member counted on the I-864) |
| I-693 (01/20/25) | `i693_applicant_part` (the applicant's Parts 1-4; the civil surgeon's parts are never filled) |
| G-1145 (09/26/14) | `g1145_e_notification` (one per paper package) |
| G-1450 (02/06/26) / G-1650 (06/03/25) | `g1450_credit_card_payment`, `g1650_ach_payment` (one per fee; card and bank details always blank) |

Every schema covers every question a preparer answers on its form, every row of the repeated
tables included, and names the `field_list` it was built against. For a form with no schema, cover every question yourself; the audit then warns that no schema
is declared (for a form that has one, that is an error). The schemas live in `form_question_schema.py` and, one file per form, in
`schemas/`. Each names the stored field list it was built against (`schemas/fields/`), and the
tests check every field and on-state against it. When USCIS publishes a new edition, rebuild
the list with `form_question_schema.py fields <blank.pdf> schemas/fields/<FORM>.json` and fix
whatever the tests then flag.

## audit_prepared_forms.py (the readiness gate)

```bash
uv run --script "<plugin root>/scripts/forms/audit_prepared_forms.py" \
  --output-json "/abs/forms-audit.json" --intent-manifest "/abs/forms-manifest.json" \
  --check "g-28=/abs/G-28 filing copy.pdf" --check "i-130=/abs/I-130 filing copy.pdf"
```

`build` runs the audit for you (`build --check-only` reruns it); run it by hand only for a closer look.
`KIND` is any form with a schema (`form_question_schema.py list`); any other kind is rejected. Every
form has its own rules besides the generic checks (the plan against its schema, stored against
planned values, visible values, box rules and overflow). Besides the ones listed below: the N-400's
trip rows, with warnings for a trip over six months or a year and for trips that leave too little
physical presence, and for filing before the green card is old enough (less 90 days); the I-751's
single route (joint 1.a/1.b or waiver 1.c-1.g) with the spouse's part and signature only on a joint
petition; the I-765's category written as the form takes it, with only that category's items 28-31;
the I-360's VAWA classification; and the I-907's requestor (a petition's petitioner or its attorney,
never its beneficiary; an application's applicant or theirs), a designated form and, for an I-140, a
classification code (E21 with NIW or non-NIW), the related case's names (with no company in Part 1
item 4, real names in Part 1 item 3 and Part 2 items 4-5, not N/A), a receipt number only to upgrade
a pending case, which then needs all of Part 2, and the requestor's statement and daytime phone. The `--check` path must be the
filing copy's path exactly as the manifest keys it, or the manifest entry is not found. The audit writes every finding to the
JSON and prints a summary: counts per form, how many errors are tied to open items, and the first
untied errors with their fields (`--full` prints the JSON too). It exits 1 if there is any
`error`. Treat untied errors as stop conditions. Warnings are open client-input or signature
items, or known form defects, that must still be reported.

**What it checks:**

- Per-form high-signal blanks, such as the attorney or preparer block, identity, addresses
  and relationship basis.
- Conditional sections on the I-485: A-number, spouse, prior spouse, children, minors'
  school, public charge and organizations. Passport and I-94
  details are required after an admission or parole (Part 1 item 11 A or B), and otherwise only
  once started. Mobile phone, email and the principal's A-Number are "if any". Part 4 item 8 is
  checked only once started. The receipt number and priority date aren't required when the plan
  marks `underlying_petition` not_applicable (a concurrent I-140). A marriage count of "None"
  is zero. Any one or more of the five race boxes may be checked.
- On the I-485, a state and ZIP Code are asked for only on a row whose country is the United
  States (the prior address, the spouse's address, the place of marriage), and a province or
  postal code never. The most recent address outside the United States is required when its plan
  question isn't `not_applicable` (with no plan, once started), whatever the five-year answer.
  Prior marriages are the marriage count less the current one: a divorced or widowed applicant
  married once lists that spouse, and a legally separated applicant still has a current spouse.
- I-485 Part 2 by the category selected in item 3. Exactly one category must be chosen, and
  only that category's follow-up answers are required: the I-140 relative question, receipt
  number and priority date for an employment-based filing, the grant or admission date for an
  asylee or refugee, the rank number for the Diversity Visa. A family-based filing is not asked
  for I-140 answers, and item 4 (INA 245(i)) is required only for the categories it covers.
- On the I-130A: the spouse beneficiary's name, each parent's name, date of birth and
  countries; the address and employment rows (a row is blank or complete, starts before it
  ends, has a unit number with its unit type, and has a state and ZIP code when it is in the
  United States; an "Unemployed" row needs no address); the preparer block; and the page 1
  attorney box, which must agree with the G-28 for the same person in the manifest (the "G-28
  attached" box, bar number, online account number, and the preparer's name when the preparer
  is the attorney).
- On every form, every stored answer against its own box (`formats.py`): no answer longer
  than the box's maxlen, comb boxes included (Adobe cuts it off at the limit), and each in the
  format its box takes: a real date written mm/dd/yyyy in every date box (or N/A, D/S,
  INDEFINITE or PRESENT), 7 to 9 digits with no "A" or dashes in an A-Number box, 9 digits in an SSN box,
  3 letters and 10 digits in a receipt number box, 11 characters in an I-94 box, a ZIP Code,
  12 digits in an online account box, and a state code in a state drop-down. Date and ZIP boxes
  are found from the form's XFA template, the number boxes from their names. A five-digit box
  (picture `text{99999}`) is a ZIP Code only when its name or the form's own description of it
  (the template's tool tip) says ZIP Code; any other five-digit box takes a whole number (the
  I-130's number of marriages). A ZIP Code column that the form says also takes an address
  abroad (the N-400's residence and employment tables) takes a ZIP Code on a row whose country
  is the United States and a postal code on any other row. These are never deliberate gaps, so
  they are never tied to an open item.
- On the I-864: Part 5 item 8 (the household size, box `Override`) is the sum of items 1-7, and
  Part 6 item 12 (total household income) is the sum of items 7-11 (errors). The household income
  is compared with the I-864P poverty guideline for that household size (`poverty_guidelines.py`,
  the table effective 03/01/2026, Alaska and Hawaii separately; 100% for an active-duty petitioning
  sponsor, 125% otherwise). Below it is a warning that suggests an `attorney_decision` (a joint
  sponsor, an I-864A, or assets). Replace the table when USCIS updates uscis.gov/i-864p; the
  audit warns once it is more than a year old.
- In a protected matter (the matter's settings say `protected`: VAWA, T or U, 8 U.S.C. 1367),
  every mailing-address box of the client on the G-28, I-485, I-765, I-131, I-360, I-751 and
  N-400 (`safe_address.py` lists them) must hold the safe mailing address. The audit compares them
  with the plan's `safe_mailing_address` record (`in_care_of`, `street`, `unit`, `number`, `city`,
  `state`, `zip`, `country`, `source`: `profile` or `attorney`), or, when a plan has none, with the
  profile's `mailing_address`. Where the form takes the physical address as the mailing address
  (I-485 item 18 "Yes", N-400 Part 4 item 2 "Yes"), the physical address is checked instead.
  Anything else is an error; boxes left empty for their open item are not.
- Text cut off on the filing copy (see "Overflow" below).
- Planned answers Adobe would show blank or different in the XFA source, as in a source filled
  by an older `fill` (I-765 values outside their page's data group, boxes the template doesn't
  bind). The fix is to refill and re-render.
- Known defects of a form edition, as warnings with what to do (see "Known form defects").
- Signature fields that are still blank (a warning).
- Stored XFA values that disagree with the visible layer.

**Overflow.** The filing copy is rendered from the appearances `fill` generates, and at a fixed
font size those neither wrap nor shrink text, so text that does not fit is cut off. The audit
estimates each filled box's text width from the font and size in its `/DA` (Courier or
Helvetica metrics; an auto-size box shrinks to 4 pt before it overflows) and compares it with
the box. The clip is the box itself. Text starts 2 pt in from the left edge; a centred box
(`/Q 1`) centres it, and an N-400 Part 7 date fills its 60 pt box exactly. A line is cut off
when it runs past an edge, or when its baseline falls below the bottom of the box. At 10 pt
Courier New Bold, a 30 pt box holds one line (the N-400 Part 4, 6 and 9 tables), 54 pt holds
three, 90 pt five (I-485 Part 14, about 85 characters a line), 162 pt eight and 180 pt nine,
and a 234 pt box takes 38 characters a line. These figures come from Ghostscript renders. Each cut-off box is an error naming the field, page and fix:
shorten a single-line answer or move it to Additional Information; break the lines of a
multi-line box that would then fit; otherwise continue on an additional-information page. A
visible value that is missing only because its box overflows is reported this way, not as a
value that does not show. The estimate is approximate, so a value right at the edge can go
either way.

With the manifest it also checks:

- that the plan covers every schema question with an allowed status and non-empty values;
- that each `visible_values` string shows on the filing copy inside its question's own boxes (word
  positions from `pdftotext -bbox`, boxes from the source's widgets), so words printed on the
  form itself ("Yes", "None", "United States") never count as the answer; without poppler it
  falls back to the whole page text;
- that stored values match the plan;
- that no unexpected non-empty fields are present (a default the manifest's official blank
  already holds is ignored);
- that the filing copy is static and its XFA source exists;
- whether any answer rests only on prior-form facts.

## Field-mapping knowledge for USCIS PDFs

- **Field names mislead; tooltips do not.** On the G-28 (09/17/18 edition) the mobile-phone
  box is `Line6_EMail` (maxlen 10) and the email box is `Line7_MobileTelephoneNumber`.
  `Line3_Date` is the attorney's signature date, and `Pt5Line2b_DateofSignature` is the
  law-student date. On the I-130 the petitioner's legal name is `Pt2Line4a/4b`, and
  `Pt2Line5a/5b` is "Other Names Used". `dump-fields --acro` settles every such question.
- **Repeated names:** the nth XFA node with a name binds to the nth widget with that name, in
  form order. Keep the `[n]` occurrence indexes, never collapse duplicates into one key, and
  check the tooltip and page of every `[n]` that you use. The same leaf name can serve
  different prompts within a section.
- **`global` fields** share one value everywhere they appear. Examples are the client name
  repeated on the Additional Information page and checkbox groups such as G-28
  `Line4_Checkbox` (A, P, R, B, BD). Set the base name once. A checkbox group takes the on-state
  of the chosen box, and the other boxes in the group clear.
- Blank forms carry defaults (e.g. "PRESENT" in some I-130 date-to boxes). The audit ignores a
  value the manifest's blank already holds.
- Never force a partial fact into an incompatible box. Leave unsupported fields blank.
- Keep petitioner, beneficiary, sponsor and attorney facts separate. Each answer needs a
  fact ID that points to a document or an explicit user instruction. Prior prepared forms
  rank below primary records.
- On the I-601A (01/20/25), `Pt1Checkbox25_Checkbox` is Part 1 item 26 and `Pt1Checkbox30_Checkbox`
  item 31; from item 32 on, each yes/no box is named one below its item (`Pt1Checkbox31` is item 32).
  `Pt2Line4_HeightInches1-3` are the weight digits, and `Pt3Line4_Option1-5` are Part 3 items
  1.a-1.e. The instructions' rejection list mentions a Part 3 item 5 (DOS acting before January 3,
  2013) that this edition doesn't have.
- On the I-601 (01/20/25), `p1Line1dCityOrTown` is Part 2 item 1.d, `Pt7Line6a_SignatureofApplicant`
  and `p7Line6DateofSignature` are Part 7 items 4.a-4.b, `p8Line7Signature`/`p8Line7DateofSignature`
  are Part 8 items 6.a-6.b, and `P8Language` is the interpreter's language. Its Part 4 note says to
  mention an attached letter in item 39; it means item 40.
- On the I-907 (04/01/24), Part 2 items 6-8 carry Part 1 names (`Part1_Line8_NameOfCompanyPOC_*`,
  `Part1_Line9_CompanyIRSTaxNumber`, `Part1_Line7_OtherInformationAboutCompanyOrg_*`),
  `P2_Line2_ClassorEligRequested` is Part 2 item 3, and `Line_FamilyName` is item 5 (the
  beneficiary). `P3_Line5_MobileTelePhoneNumber[1]` is Part 3 item 5, the fax number, and
  `P5_Line5_FaxNumber` is Part 5 item 5, printed as the preparer's mobile number. Part 1 item 8
  stores A-D in printed order (petitioner, its attorney, applicant, theirs); Part 3 item 1 stores
  `Y` for 1.A and `N` for 1.B.
- Adobe Acrobat is the right viewer for a human spot-check of the XFA source. Any viewer works
  for the filing copy. Adobe shows every answer in a source filled by the current `fill`, except
  the I-751's calculated name boxes.

## Known form defects

Some USCIS editions have mistakes in the PDF itself that no mapping can work around. `fill`
and the audit recognize the ones listed here by field name and on-states, and print a warning
with what to do. A corrected edition stops matching, and the warning goes away.

- **I-864 (08/24/26): Part 6 item 1 "Employed" and Part 8 items 1.a and 1.b are one checkbox
  group.** All three boxes are `P6_Line1_Checkbox` (on-states `" Y"`, `A` and `B`), a single
  global value, so checking 1.a or 1.b clears "Employed", and the reverse. Check "Employed" if
  it applies and leave Part 8 item 1.a/1.b unmarked in the PDF. The sponsor marks 1.a or 1.b by
  hand at signing. Add an `attorney_action` open item for that hand-marking, and don't tick 1.a
  or 1.b in Acrobat later, because that would clear "Employed" on the form.

- **I-765 (08/21/25): the page 5 unit checkboxes don't match their labels.** In
  `Pt5Line3b_Unit` (Part 4 item 3.b, the interpreter) and `Pt6Line3b_Unit` (Part 5 item 3.b, the
  preparer), `" FLR "` checks the box printed "Apt.", `" APT "` checks "Ste." and `" STE "` checks
  "Flr.". The schema's `choices` are keyed by the printed label, so use them, never the plain unit
  code. The stored value will name a different unit than the box shown. The Part 2 unit boxes
  are correct.
- **I-129F (01/20/25): most unit checkboxes don't match their labels, and two eye colors are
  swapped.** In Part 1 items 8, 9, 11, 14 and 18 and Part 2 items 12, 14, 17 and 21, `" FLR "`
  checks the box printed "Apt.", `" APT "` checks "Ste." and `" STE "` checks "Flr."; in Part 4
  item 5 the box printed "Gray" stores `GRN` and "Green" stores `GRY`. The schema's `choices` are
  keyed by the printed label. Part 3 item 3 ("select all that apply") is one checkbox group, so only
  one box can be checked: explain the others in Part 8. These were read from where each box sits
  next to its label (the same reading reproduces the I-765 defect above), not yet in Acrobat.
- **I-601A (01/20/25): the eye colors Gray and Green are swapped.** In Part 2 item 5
  (`Pt2Checkbox5`) the box printed "Gray" stores `GRN` and the box printed "Green" stores `GRY`
  (the tooltips follow the printed labels). The schema's `choices` are keyed by the printed label,
  so use them, never the plain color code. Read from where each box sits next to its label and
  confirmed on a rendered filing copy, not yet in Acrobat. The hair colors and every unit box are
  correct.
- **I-601A (01/20/25): Part 8 item 7.b has no box for "extends / does not extend beyond the
  preparation of this application".** The attorney marks it by hand at signing; add an
  `attorney_action` open item.
- **I-601 (01/20/25): two eye colors are swapped.** In Part 3 item 5 (`p3Line5EyeColor`) the box
  printed "Gray" stores `GRN` and the box printed "Green" stores `GRY` (the tooltips name them the
  same way). The schema's `choices` are keyed by the printed label. Read from each box's position and
  on-state and confirmed on a rendered filing copy, not yet in Acrobat. The unit, yes/no, sex,
  ethnicity, race and hair boxes match their labels.
- **I-360 (01/20/25): Part 15 items 1-2 (name, A-Number) are the global Part 1 item 1 and 4 boxes**
  (`Pt1Line1_*`, `Pt1Line4_AlienNumber`). A VAWA or SIJ self-petitioner skips Part 1, so filling Part
  15's header fills Part 1 too. Leave both blank unless the attorney decides otherwise
  (`attorney_decision`).
- **I-864A (08/24/26): the sponsor's statement (Part 5 items 5.a, 5.b and 6) is one checkbox
  group**, so item 6 (a preparer prepared it) can't be checked with 5.a or 5.b. Check 5.a or 5.b,
  name the preparer in item 6's box, and add an `attorney_action` for the sponsor to mark item 6
  by hand at signing.
- **I-864 (08/24/26): Acrobat calculates Part 6 item 12** (`P6_Line15_TotalHouseholdIncome`, the sum
  of items 7-11) **and Part 7 items 4, 9 and 10.** Enter the exact sum, digits only. `fill --verify`
  doesn't check the sum, and the filing copy shows the plan's value.
- **I-130 (04/01/24): Part 5 item 5 "Result" (`Pt5Line5_Result`) accepts only digits and "/" when
  typed in Acrobat.** `fill` writes any text and the filing copy shows it; change it in the plan
  and rebuild, not in Acrobat.
- **I-751 (04/01/24): `P7_Name` and `Pt8_Name` are calculated in Adobe.** Acrobat shows initials
  plus the family name ("M.L.Family"), built from the Part 1 and Part 4 names, whatever is
  stored. The filing copy shows what the plan wrote.
- **I-751 (04/01/24): the interpreter's email box (`P6_Line5_InterpretersEmailAddress`) holds 10
  characters.** Put the email in Part 11, citing Page 8, Part 9, Item 5.
- **Boxes the XFA layer doesn't bind (`<bind match="none"/>`).** Adobe would show these empty
  whatever the data holds. `fill` binds the ones it fills in the filled source, so Adobe shows
  them; this was checked in Acrobat on the I-765, I-485, I-751, N-400 and I-130A.
  - I-485: 33 boxes, including place of birth (`Pt1Line7_*`), other names, the I-94 name, other
    A-Numbers, parents' and spouse's countries, marriage places, and the Part 14 page, part and
    item boxes.
  - I-765: other names (`Line2*`, `Line3*`), `Line18a/18b_CityTownOfBirth`, and the Part 6 page,
    part and item boxes.
  - I-751: other names (`P1_Line2*`, `P1_Line3*`), every child's name (`Line1a/1b/1c_*3`,
    `Line13a/13b/13c_*`), and the Part 11 page, part and item boxes (`P8_Line3a`-`P8_Line7c`).
  - I-130A: Parent 1's city of birth (`Pt1Line12CityTownOfBirth`).

  These were also found, and `fill --verify` confirms they're bound, but they weren't opened in
  Acrobat:
  - G-28: `Line3_Date` (the attorney's signature date), `Line2c_DateExpires`, and every Part 6
    page, part and item box (`Pt9Line3a`-`Pt9Line6c`).
  - I-130: the beneficiary's sex boxes (`Pt4Line9_Male`, `Pt4Line9_Female`).
  - I-131: other names (`Part2_Line2_*`), Part 4 items 2.c and 3.c (`P4_Line2c_Disposition`,
    `P4_Line3c_Disposition`), Part 7 item 5 (`P7_Line5_ExpectedLengthTrip`), Part 8 item 2
    (`P8_Line2_ExpectedLengthTripinUS`), and Part 13 item 3's page, part and item.
  - I-360: Part 15 item 3's page, part and item (`Pt14Line3a/3b/3c`).
  - I-601A: the other qualifying relative's name (`Pt4Line4a_FamilyName`, `Pt4Line4b_GivenName`,
    `Pt4Line4c_MiddleName`, Part 4 items 4.a-4.c).
  - I-601: Part 1 items 11, 12, 15.a and 15.b (`p1Line11CityOrTownOfBirth`, `p1Line12ProvinceOfBirth`,
    `p1Line15aCaseNumber`, `p1Line15bCity`, `p1Line15bCountry`) and the five Part 3 item 2 race boxes
    (`p3Line2Race[0]`-`[4]`).
  - I-907: Part 2 item 7, the EIN (`Part1_Line9_CompanyIRSTaxNumber`), and the Part 6 page, part and
    item boxes (`Pt9Line3a`-`3c`, `Pt9Line4a`-`4c`).
  - I-864: the Part 4 family members' name and relationship boxes (`P3_Line3a`-`3c`,
    `P3_Line4_Relationship`, and the same on Lines 8-9, 13-14 and 18-19).
  - N-400: other names (`Line3_GivenName1/2`, `Line3_MiddleName1/2`), the new name
    (`Part2Line4a_GivenName/MiddleName`), the current spouse's name (`P10_Line4a_*`), the
    spouse's number of marriages (`P10_Line4g_Employer`), and Part 14 item 2's page, part and
    item (`P11_Line3A/B/C`).

  To spot one, look for a field in `dump-fields --acro` whose name isn't among the dump's
  `xfa_nodes`.

To spot a new linked-checkbox defect, look in `dump-fields --acro` for one checkbox name whose
boxes sit in different parts or questions of the form.

## Attorney profile: the G-28 mapping

G-28 attorney fields:

| Profile key | G-28 field(s) |
|---|---|
| attorney_name | `Pt1Line2a_FamilyName`, `Pt1Line2b_GivenName`, `Pt1Line2c_MiddleName` |
| firm_name | `Pt2Line1d_NameofFirmOrOrganization` |
| mailing_address | `Line3a_StreetNumber`, `Line3b_Unit` + `Line3b_AptSteFlrNumber`, `Line3c_CityOrTown`, `Line3d_State`, `Line3e_ZipCode`, `Line3h_Country` |
| phone | `Line4_DaytimeTelephoneNumber` |
| email | `Line7_MobileTelephoneNumber` (the email box) |
| bar_number | `Pt2Line1b_BarNumber` |
| licensing_authority | `Pt2Line1a_LicensingAuthority` (with `CheckBox1` = `Y`) |
| uscis_online_account_number | `Pt1Line1_USCISOnlineAcctNumber` |
| subject_to_discipline_order | Part 2 item 1.c: `no` → `Checkbox1dAmNot` = `Y`; `yes` → `Checkbox1dAm` = `N` (the boxes are named "1d" but sit at item 1.c, and those are their on-states) |
| discipline_order_details | Part 6 Additional Information, cited to Page 1, Part 2, Item 1.c; only with `yes` |

If `subject_to_discipline_order` is missing, leave both boxes blank and set the question to
`missing`; never assume "am not". For preparer blocks on other forms, see the
`preparer_block` fields in the schema, or run `dump-fields --acro --prefix Pt12` (I-485),
`--prefix Part12` (I-131) or `--prefix Pt8` (I-130).

## Tests

```bash
uv run --script "<plugin root>/scripts/forms/tests/test_forms_gate.py"     # the tools
uv run --script "<plugin root>/scripts/forms/tests/test_schema_g28.py"     # one form's schema, and so on
"<plugin root>/scripts/check.sh"                                         # every suite of the plugin
```

Each `tests/test_*.py` runs on its own. The tests use only fictional data. The `build` tests render with Ghostscript and are skipped
when `gs` is not installed. The real-blank tests (`tests/test_schema_real_blanks.py` and each new
form's schema test) fill the official blank each schema was built against: `tests/official_blanks.py`
finds it by sha256 in `$SA_FORMS_BLANKS`, `tests/.blank-cache/` (gitignored) or a development
checkout's `evals/golden/blanks/`, and otherwise downloads it from uscis.gov into the cache once.
With `SA_FORMS_OFFLINE=1`, or when uscis.gov now serves another edition, those tests skip and say
why.


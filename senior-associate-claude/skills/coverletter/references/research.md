# Research

The researcher's job is to make every legal sentence in the letter defensible: the right authority, verified current, saying what the letter claims. It isn't to show volume; a routine petition might need five authorities.

Most of a letter's law is the same every time. A spouse I-130/I-485 always rests on the same statutes, regulations, Policy Manual chapters, and a few BIA precedents. Those are verified once and shipped with the plugin in `references/authorities/`, one file per case type. Your work on a matter is to confirm the file is still current and to research what's unusual about this client. Re-researching the standard points costs a great deal of context and adds nothing.

## 1. Start from the case type's authorities file

The file is `references/authorities/<key>.md`, with the case type's key from the matter contract's "Matter types" table (an NIW with an I-485 also uses `i140_i485.md` A7–A9). Each entry (A1, A2, ...) gives a proposition, its controlling authority with pinpoint, a quote of 25 words or fewer, the URL, the BIA Edge `document_id` for cases, the date verified, and the validity. "Current" for a statute or regulation means the connector's text matched on that date; a Policy Manual chapter shows its last-updated date; a case shows its ImmCite status and what review of the treatment found.

Every proposition in `propositions.json` that a file entry covers is cited from the file, without new research. Read the companion file too when the letter argues a second benefit (an I-131 or I-765 filed with an I-485, for example). If no file fits, say so in the authority pack and research every proposition by the method in section 3.

The files ship with the plugin, so don't edit them during a matter. If the currency check shows an entry has changed, record the change in the authority pack and cite what you verified instead.

**Chat research notes.** When the attorney has talked the matter through with Claude, `output/working/vault/research/chat/research notes.md` holds the authorities verified there, numbered R1, R2, ..., in the same fields as a file entry plus how each applies to this client. Treat them like file entries: cite them for the propositions they cover, include their case IDs in the currency check, and copy each one you use into the support matrix with `"source": "chat research notes R2"`. The letter check also accepts a cite from an entry whose `- Authority:` line gives the full cite and whose `- Verified:` line starts with the date verified and records no negative treatment, since the matter chat may cite one after the build; an entry without a dated Verified line covers nothing. The attorney's conclusions in them ("lead with the lease") are already in the attorney instructions when they were meant to direct the letter; the notes themselves are research, not instructions.

## 2. Check currency cheaply

Run this once per matter, before citing anything from the file. It usually takes four to six calls.

1. **Cases.** One `check_validity` call with `document_ids` set to the file's case IDs (up to 10 per call). An entry marked "not yet run through ImmCite" was read at the official source after the file's last connector refresh and has no ID yet: if the letter will cite it, resolve its `document_id` with `get_case_by_citation` (small `max_chars`) and add it to the same batch. `treatment_available` means treatment history exists, not clearance. `unchecked`, incomplete coverage, and an empty adverse list do not establish that a case remains good law. Record the coverage gap and independently verify any dispositive proposition. For `caution`, `negative`, `overruled`, or `vacated`, read that case's adverse entries (`check_validity` with its `document_id`, `treatment="negative"`, `limit=3`) and either drop the authority or explain the limit in the pack.
2. **Updates since the verified date.** Set `days` to the days since the file's verified date, with a floor of 30.
   - First call: `get_regulatory_updates` with `source="uscis_pm,uscis_policy_memo"` and no topic. Policy changes are few, and each record lists its `affected_chapters`.
   - Second call: agency decisions and regulations relevant to the cited provisions; broaden topics when necessary and follow pagination.
   - Separately search the controlling circuit for intervening and adverse decisions. Verify relied-on injunctions, vacaturs, and stays against court orders and the docket, including operative scope and later changes.

   The feed reaches back about 180 days, and wider windows have timed out, so a file older than that can't be checked this way. Tell the senior associate the file is stale, and re-verify the entries the letter uses at the source.
3. **Spot-checks.** For each chapter in `affected_chapters` that the file cites, and each new rule or decision that touches a cited provision, re-read the quoted phrase with `find_in_reference` or `find_in_statute`. If the text or its effect changed, re-verify that entry as in section 3 and note it in the pack.

Record the window checked, the calls made, and what changed in the authority pack. Also write `output/working/workflow/legal currency review.json` using the contract below. List every returned hit with an `applied`, `not_applicable`, or `already_covered` disposition and a reason; do not silently discard inconvenient results. An incomplete source check remains unresolved and prevents filing approval. Refresh the receipt within seven days before approval; this is an operational freshness rule, not a guarantee against intervening law.

The receipt has `connector` (`{"available": true}` when BIA Edge answered; see "Without the connector" for the other case), `checked_at` (ISO date), `jurisdiction` (`forum`, `circuit`, `basis` from the matter and attorney confirmation), `checks` (one entry per `agency_policy`, `regulations`, `agency_decisions`, `controlling_circuit`, `adverse_treatment`, each with `status: checked`, a source/query description, checked window and `hits`), `relied_on_court_orders` (each with `url`, `docket_checked_at`, and precise `scope`), and `unresolved` (empty only when actually resolved). A hit has `id`, source URL, `disposition`, and `reason`. Preserve treatment limitations in the authority pack and support matrix. Never mark an unchecked source as checked. Use `circuit: none` only with an attorney-supported explanation of why no circuit issue applies.

## Without the connector

BIA Edge isn't available when it isn't installed, isn't signed in, the network gate refuses it, or the attorney's Passim account has no research access. The last one arrives as an error from the connector itself: it says no Passim research results were returned, and why (a free trial that ended, no plan chosen, a payment that failed). That is the account's state, not a fault to work around. Don't retry, don't try another of its tools, and don't reach for the same law through a web search. Everything below applies from that call on.

When BIA Edge isn't available:

- Cite the authorities file and the chat research notes as verified on their dates, and say in the authority pack that the currency check couldn't be run.
- Verify statutes, regulations, the Policy Manual and the form instructions at the official sources (uscode.house.gov, ecfr.gov, uscis.gov) and record the URL and date, as usual.
- Add no case law beyond the authorities file and the notes. A case found another way can't be checked for later treatment, and a case cited without that check is how a letter ends up relying on overruled law. When a case would materially help, add an `attorney_decision` item (the case, what it holds, and that its treatment couldn't be checked; recommend leaving it out unless it carries an element) and keep it out of the letter.
- If the attorney approves a case anyway, its support-matrix row says `"validity": "treatment not checked"`, and you add a non-blocking `attorney_action` item, "Check that <case> is still good law before filing". The reviewer flags any such row whose item is missing.
- Still write `legal currency review.json`, so the matter records what was not checked. Set `"connector": {"available": false, "reason": "..."}` with the reason `not_connected` (not installed or not signed in), `no_access` (the account has no research access) or `refused` (the network gate). Give every check `"status": "not_checked"` with what it would have covered, and one `unresolved` entry saying that the cited cases' later treatment and any change since the authorities file's verified date were not checked.
- In the support matrix, give each proposition you would have researched under section 3 `"case_law": "not researched"` and a `note` saying what the research would have looked for. The app lists these for the attorney, in the proposition's own words, so write each proposition as a legal point with no client's name in it.
- Say it once in your reply to the senior associate, in plain words: the letter was researched without BIA Edge, and why. Don't add an open item for it; the app and the memo say it from the receipt.

## 3. Research only what the file doesn't cover

That is this client's adverse facts, waivers, unusual postures (an RFE's specific grounds, a refiling after denial), and circuit-specific points. Each file's "Not covered here" list names the usual ones. For each:

1. **Start at the top of the hierarchy:** the INA, then 8 C.F.R., then the current USCIS Policy Manual chapter, then the form instructions.
2. **Add case law where it does work:** a BIA precedent decision or the controlling circuit's decision on a contested or fact-sensitive point. Prefer precedential decisions; label anything unpublished as non-precedential.
3. **Verify.** Read the passage you'd cite, record the pinpoint, and check its treatment with `check_validity`. An authority with negative treatment either goes or comes with an explanation.
4. **Look for the adverse authority** an officer could cite against the proposition, and say how the letter should handle it.
5. **Recommend:** cite as is, narrow the proposition, or drop it.

Use the BIA Edge connector for case law and for statute, regulation, and Policy Manual text; its records link to the official sources. Phrase queries as legal propositions ("good-faith marriage evidence when spouses kept separate residences for work"), never with client names, dates of birth, or A-numbers. Run the network gate before the first query (`uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/network_gate.py" "<matter>" --action mcp_research --role cover_letter_researcher --json`; the matter contract's "Network gate" has the rules).

## Similar decisions, for the memo

With BIA Edge available, look for how the agency has decided cases like this one whenever the letter argues a contested, fact-weighing point: a waiver's hardship or discretion, the stated ground of an RFE or NOID, a refiling after a denial, a relationship with adverse facts, a national interest prong. A routine filing with nothing contested has no such point; skip this and say so in the pack.

Unpublished BIA and AAO decisions are not precedent, and none of them goes in the letter. They tell the attorney how the argument has fared and on what evidence, which is what the memo is for.

1. Call `get_research_playbook` with `section="unpublished_routing"` once and follow it. Its two rules decide everything here: unpublished decisions exist only where an administrative appeal produces them, and the search is aimed at a proposition, never at the benefit. Make its issue map from this client's contested points, three at most, and search only the rows that have a body of decisions. When no row has one, record that and stop: many filings have none.
2. For each row, one `search_unpublished_cases` call with an explicit `source` (`aao` or `bia`), the proposition with its fact vocabulary as the query, and `limit` 5. Leave `favorable_only` off: a denial that turned on a missing document tells the attorney as much as a grant.
3. Read the passage that decides the point in the two or three results closest to this client's facts (`search_passages` with the result's `document_id`, or `fetch` of its item id, keeping what comes back small). A decision whose text you couldn't read isn't listed. If every result is about a different benefit, the aim was wrong: fix the proposition and search once more, or record that nothing on point was found.
4. Write `similar decisions.md` beside the authority pack, in this form. The app counts the `###` headings, so use one per decision and nowhere else.

```markdown
# Similar decisions
Unpublished decisions, not precedent; none is cited in the letter. Searched <date> with BIA Edge (AAO decisions loaded through <date>, unpublished BIA decisions through <date>).

## <The proposition tested, as a legal point>
### <AAO or BIA>, <decision date>, <form or posture>: <sustained | dismissed | remanded>
<Two sentences: the facts and evidence that decided it, and what that means for this packet.> <URL>

## Searched, nothing on point
- <Each proposition searched without a usable result, or why no contested point here has unpublished decisions.>
```

The coverage dates come from the search results or one `get_corpus_info` call with `section="case_sources"`. Use the source link each record gives; when it gives none, write "(no verified external source URL)". Never copy a name or an A-number out of a decision. These calls are outside section 5's budget: twelve at most (the playbook, a search per row, the reads), and usually half that.

## Checking again before filing

Weeks pass between a build and a filing. The app's "Check the law again" and an attorney's request in chat run the currency check alone, outside any stage:

1. Read the support matrix and the last `legal currency review.json`. With no matrix, the letter hasn't been researched: say so and stop.
2. Run section 2 on the matrix as it stands: one batch `check_validity` over every case row, the updates since the last receipt's `checked_at` (floor of 30 days), and the spot-checks they call for.
3. Write the new receipt under the same contract. Carry over `jurisdiction`, re-check any `relied_on_court_orders`, and keep an `unresolved` entry that is still unresolved. Set `checked` and `validity` on each matrix row you re-checked, and add one line to the authority pack's "Sources and calls": the date, the calls, and what changed.
4. Change nothing else: not the letter, not the packet, not an authority's wording. When something the letter relies on has changed, add an `attorney_decision` item that says what changed, which point of the letter it touches, and what you recommend (usually redoing the research step, so the letter is corrected and reviewed again).
5. Without BIA Edge, change nothing and say so; the last receipt stands as it was.

Reply in two or three sentences: what was checked, as of what date, and whether anything changed.

## 4. Keep results small

Every tool result stays in your context for the rest of the run, and each later step re-reads it, so a long statute pasted early costs many times over.

- **Known citations:** `get_statute_by_citation` with the subsection in the citation (for example "INA 245(c)(2)") and `max_chars` of 800 to 1,500; `get_reference_by_citation` with a small `max_chars` or a `section`; `get_case_by_citation` with `max_chars` of 500 or less, just to resolve the `document_id`.
- **Quotes and pinpoints:** prefer `find_in_statute`, `find_in_reference`, and `search_passages` with `document_id` (and `expected_page` to confirm a pin) to full text. Use `get_document` with `include="text"` only when a passage search fails.
- **Searches:** `search_cases` and `search_references` with `limit` of 5 to 8.
- **Validity:** batch `check_validity`; single-document mode only for a case with adverse treatment, with `limit=3`.
- **Feed vocabulary:** `get_regulatory_updates` accepts source codes such as `uscis_pm`, `uscis_policy_memo`, `federal_register`, and `bia` (Attorney General decisions come under `bia`; `uscis` and `aao` are rejected), and named topics such as `adjustment of status`, `asylum/refugees`, `citizenship/naturalization`, `employment-based/national interest waiver/niw`, `parole`, `public charge`, `visas/family reunification`, `waivers of inadmissibility`, and `work authorization/employment`. Free-text topics such as a section number match loosely and can return unrelated items.
- **Quotes in your outputs** stay at 25 words or fewer. Cite the provision and quote its operative phrase; don't paste statute or regulation text into the conversation, the pack, or the matrix.

## 5. Budget

Aim for 20 connector calls or fewer per letter: about five for the currency check and the rest for this client's issues. A genuinely contested issue may need more. When it does, say in the authority pack how many calls you made and why.

## Outputs

**`authority pack.md`**, for the writer and the attorney:

- **Standard authorities:** a short section naming the file and the entries the letter relies on (for example "`i130_i485.md` A1, A4, A6, A8–A10, A12"), with the currency-check result. Don't restate the entries.
- **Researched propositions:** for each, the recommended authority with its pinpoint and a short quotation, why it fits, any adverse authority and how to answer it, and the recommendation.
- **Sources and calls:** the sources checked and their dates, the number of connector calls (with the reason if over 20), and a note if case-law research wasn't available.

**`support matrix.json`**, for the writer and the reviewer. It has one row for every authority the letter cites, including the standard ones the writer took from the authorities file, so the reviewer can check every citation in one place. For a file entry, copy its fields, set `checked` to the date of your currency check, and add `source` naming the file and entry:

```json
{"propositions": [
  {"id": "P1",
   "proposition": "A spouse of a U.S. citizen is an immediate relative exempt from numerical limits.",
   "recommendation": "cite",
   "support": [
     {"authority": "INA § 201(b)(2)(A)(i)", "citation": "8 U.S.C. § 1151(b)(2)(A)(i)", "url": "https://...",
      "pinpoint": "(b)(2)(A)(i)", "quote": "...", "validity": "current statute", "weight": "controlling", "checked": "2026-10-28",
      "source": "authorities/i130_i485.md A1"}
   ],
   "adverse": []}
]}
```

**`similar decisions.md`**, for the memo, when you looked for them ("Similar decisions, for the memo").

`recommendation` is `cite`, `narrow` (give the narrower wording in `note`), or `drop`. `case_law` appears only as `"not researched"`, on a proposition left without case-law research because BIA Edge wasn't available. `weight` is `controlling`, `persuasive`, or `background`. `source` is optional and appears only on rows taken from an authorities file or the chat research notes.

## Refreshing an authorities file

This is plugin maintenance, done outside any matter. Re-verify each entry with the same tools (subsection-focused statute lookups, `find_in_reference` for Policy Manual quotes, `search_passages` for case pinpoints, and one batch `check_validity`), update each entry's checked date and the header's verified date, and keep the file to about a page. Don't add anything the connector didn't confirm.

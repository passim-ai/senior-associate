# The research behind a letter, and the way to BIA Edge — November 10, 2026

Released as 1.4.0. Made on `claude/packet-builder-passim-funnel-20261110`, based on 1.3.0 (`ee5fda2`). The app used BIA Edge, Passim's immigration law library, without ever showing what it did, and gave an attorney without it one line, "Connect BIA Edge in Claude's Connectors", with no link, no price and no word on what it is. This change shows the research on every matter, says plainly when a letter was researched without the library, and puts a way to a trial beside it.

Nothing in the app is locked behind a subscription, and the app reports nothing to Passim.

## What changed

| Before | Now |
|---|---|
| Setup said "Connect BIA Edge in Claude's Connectors so letters can cite case law." | Setup says what BIA Edge is and what it costs, with **Start a free trial** (Passim's sign-up page, in the browser) and **Open Claude's Connectors**. The matter page's ask box and its new Research card carry the same press. (`hooks/server.ts` `researchCheck`, `server/sa_server/actions.py` `LINKS`) |
| A build made 35 to 45 library calls and the attorney saw none of them. | The Overview has a **Research** card: when the law was checked, how many authorities and cases the letter cites, how many cases carry a limit, how many points were researched for this client, how many updates were reviewed. The memo's Sources checked opens with the same words. Both come from one tool that reads the researcher's own records and judges nothing. (`scripts/research_summary.py`) |
| A letter researched without the library looked the same as one researched with it. | The receipt records whether BIA Edge was available and why not. The card then says "Researched without BIA Edge", that nothing after the reference files' date was checked, and which points got no case-law research. The approval page lists it as a point to weigh. |
| The check of the law aged, and the only way to refresh it was to redo the research step and every step after it (about 20 to 60 minutes). | **Check the law again**, on the Research card, the Packet tab and More you can do: the currency check alone, as a run of its own. It changes the receipt, the matrix's dates and the memo's Sources checked, never the letter or the packet. (`recheck` in `prompts.py`, `actions.py`, `hooks/matter.ts`) |
| Unpublished BIA and AAO decisions were used only when a researcher happened to search them. | When a point is contested, the researcher follows the library's own routing rules, looks for unpublished decisions on similar facts, and the memo gets **How similar cases were decided**. They are never cited in the letter. (`skills/coverletter/references/research.md`, `skills/senior-associate/references/handoff.md`) |
| An account with no research access (a trial that ended, a failed payment) got Passim's notice as a tool error. The research instructions did not name the case. | The instructions name it: one call, no retry, no looking for the same case law another way, and the receipt says `no_access`. The app keeps Passim's notice, in Passim's words, and shows it on Setup and the matter page with a link to the account until research answers again. (`hooks/library.ts`) |

On the Passim site, `packet-builder` joins the sign-up sources it counts (`app/billing/signup_ref.py` in the `biaedge` repository, branch `claude/signup-ref-packet-builder-20261110`). Until that is live the tag is ignored, and the links work the same.

## Decisions worth knowing

- **The price is written in the app.** "$29 a month, with 14 days free for a new account (a card is required)" is in `hooks/words.ts` and the README, as passimai.com/pricing gave it on November 10, 2026. A price change needs a release. When Passim answers that an account has no access, the app shows Passim's own words instead, which carry that account's price.
- **The app opens four addresses and no others.** Passim's sign-up page, its plans page and its account page, and Claude's Connectors page. The app names the page; the address is fixed in the server. The sign-up and plans addresses end in `ref=packet-builder`. Nothing about the attorney, the Mac or a matter is in them.
- **The app keeps Passim's notice, not the attorney's research.** The tool hook reads a connector's answer only when it is an error, and keeps it only when it is Passim's no-access notice. It is stored on the Mac with its date and cleared by the next answer with results.
- **A clean check is never called a guarantee.** The card says so in small type whenever a case was checked.
- **The summary counts; it does not conclude.** A case counts as carrying a limit when its row in the support matrix says caution, negative, overruled, vacated or the like. The research notes explain it; the card points there.
- **Unpublished decisions stay out of the letter.** The memo section opens by saying they are not precedent. The researcher skips the search when nothing in the filing is contested, and records a search that found nothing.
- **Check the law again holds the matter like any run** and shows on the timeline. It is offered only when BIA Edge is in the session and answering.

## Verification

Everything used the plugin's fictional sample matter (*Sample - Barrientos-Eckhardt*, an I-601A). No client matter was opened.

**Suites.** `UV_PYTHON=3.12 bash scripts/check-plugins.sh` on the final code: all 31 Claude suites (28 Python suites, the 158 app tests, plugin and marketplace validation), the ChatGPT adapter's tests, the lifecycle test through both transports and the 13 browser scenarios.

**Types.** TypeScript 5.9 against the engine's own type file reports nothing in the files this change touches. It reports two strictness notes in `hooks/privacy.ts` that were there before, left as they were.

**In the desktop app's engine** (2.1.317, headless, auto mode, the candidate loaded with `--plugin-dir`, the Matters folder set through `pluginConfigs`), on copies of the matter built for the 1.3.0 release:

| Trial | What ran | Result |
|---|---|---|
| Redo from Research, with BIA Edge | Research, letter revision, letter review, packet, final review, memo | All six steps passed in 21 minutes, $9.61 at API prices, 6 agents, 6 reports handed back. The researcher made 43 library calls, among them the routing playbook once and three searches of unpublished decisions. It wrote five AAO decisions on similar facts; the memo has **How similar cases were decided** with all five and their links, and Sources checked opens with the summary word for word. Four calls were refused by the privacy check, all the known "Lopez-Meza" limit. |
| Check the law again | The new run, on that matter | 4 minutes, $2.03. One batch treatment check and six update queries. The receipt and the memo were rewritten; the letter and the packet were not touched. The timeline reads "Claude finished checking the law the letter cites again in 4 min." |
| Redo from Research, account with no access | The same redo, with a trial-only plugin answering every library call in the words Passim gives a Claude caller whose free trial has ended | The researcher made one library call, did not retry, and did not look for case law elsewhere. It re-verified the statutes, the regulation and the Policy Manual at their official sites, wrote the receipt with `no_access`, and said so in its report. Stopped once the research step passed. |
| The same, from scratch | The earlier research records removed first | One library call, 22 official-source fetches. Two points were marked as left without case-law research, and the card lists both. A case from outside the reference files was recorded as "treatment not checked" with a recommendation to drop the sentence unless the attorney keeps it. |

The trial plugin and the scripts are kept with the evidence, outside this repository.

## Not tested

- **The panel in the desktop app.** No screen was opened or pressed. The Research card, the Setup line, the links and the law line beside the approval are covered by the app tests, which draw each screen, one of them against what the real helper sends.
- **A press that opens the browser.** The helper's `open_link` is tested with the open itself stood in for. No browser was opened by the app.
- **Passim's real no-access notice, received from Passim.** The account used for the trials has access. The notice's text was copied from the site's code, and the trial plugin answered with it as a plugin refusal, which reaches the agent as an error but does not pass through the app's own hook the way a connector's error does. The hook is covered by the app tests alone.
- **A full build from an empty matter,** a build without the connector installed, case types other than the I-601A, and the default permission mode.
- **Whether the similar decisions are the right ones.** Nobody checked the five decisions against the facts beyond what the research agent did.
- **The ChatGPT adapter's panel.** It shares the server and the skills, so its builds record and summarize research the same way, but its panel does not show the Research card or the links.
- **The sign-up source count.** The site change is not deployed, so no visit has been counted.

## Known limits

- The summary's counts depend on what the researcher wrote. A matrix row that names a case in an unusual way may not be counted as a case.
- A redo of the research step without the library keeps the earlier research and its dates; the card then says "as last verified" with the earlier date and lists no point as unresearched.
- The Research card says a letter was researched without BIA Edge until the research step is redone; connecting the library later changes the offer on the card, not the heading.

# Immigration Packet Builder

> Free under the [PolyForm Shield License 1.0.0](LICENSE). A drafting aid, not legal advice: an attorney reviews everything before it is relied on, sent or filed.

Immigration Packet Builder turns a client's documents into a USCIS filing packet. It works inside the Claude desktop app: you name the client and the case and add their documents. Claude then reviews them, prepares the forms, writes and researches the cover letter, assembles the packet, and checks it the way a USCIS officer would.

- **If the documents are all there,** you get a packet ready to sign and file.
- **If something's missing,** you get a **draft packet** built as far as the documents allow, with placeholders where evidence is still to come. You also get a memo that says exactly what's needed before filing, and a plain-English client request you can send.

Nothing is guessed, filed or sent. If the documents don't support an answer, Claude leaves it blank and adds it to the list of open items.

## Install

Follow the steps on the [repository's front page](../README.md#install): you paste one message into the Claude app's Code tab, and Claude does the installing. It runs `plugin marketplace add passim-ai/senior-associate` and `plugin install senior-associate@document-automation` with the copy of its command-line tool inside the desktop app, because `/plugin` isn't available in the Code tab. That page also covers permission prompts, connecting BIA Edge for case-law research, setup changes, updates and troubleshooting.

## Using it

Type `/matters` in the Code tab. Immigration Packet Builder opens beside your chat, on your list of matters with each group folded, so no client's name is on screen until you press **Show**. To show it to someone else, type `/matters demo`: only the fictional sample matter appears, until you press **Leave the demo**.

1. **Getting set up.** The first time, a checklist marks each tool ✓ or ✗. For a ✗, press **Ask Claude to do it**: Claude installs it in the chat. Then press **Check again**. You can come back to it any time from **Help › Check my setup**.
2. **Try the sample matter (optional).** Your list starts with *Sample - Barrientos-Eckhardt*, a fictional I-601A with 14 scanned documents and gaps planted on purpose. Open it from the welcome and press **Review documents first**: in 5–10 minutes Claude lists what's missing, and the matter page then shows what a good review catches, to compare. Archive it when you're done; **Help › Open the sample matter** brings it back.
3. **Your details.** Add your name, firm, address, bar number and licensing authority once. They go on the G-28, the preparer sections of the forms, and the letter's signature.
4. **New matter.** Type the client's name, choose what is being filed (I-130/I-485, I-751, N-400, an I-601A or I-601 waiver, an EB-2 national interest waiver, an I-360 VAWA self-petition with or without the I-485, and others, or describe it), say whether it's a new filing or a response, and whether you'll file on paper or online. Mark the client protected under 8 U.S.C. 1367 (VAWA, T or U) when that applies; the VAWA case types are marked for you.
5. **Add documents.** Use **Add files…** or **Add a folder…**. Immigration Packet Builder copies the files into the matter; your originals stay where they were.
6. **Review documents first** (about 5–10 minutes). It shows what's there, what's missing, and a client request ready to copy into an email.
7. **Build packet** (about 1–1½ hours). It runs in the background. Keep Claude open, and your Mac awake, until it finishes. You can use Claude for other things meanwhile, and you get a notification when the build is done.
8. **Read the result.** The matter page shows where things stand and what's left. Your files are listed there under **Files for this matter**, and they're in the matter's folder in Finder:
   - the packet, or the draft packet while anything is needed before filing, with exhibit stamps, packet page numbers and an exhibit index (for online filing, the upload files too, each form its own PDF and each under USCIS's size limit, with an upload map saying where each goes in your USCIS account; when a form can go only on paper, a separate paper packet for it);
   - the cover letter, in Word and PDF, and the filled forms, with a card or bank-account payment form for each fee on a paper filing;
   - the filing checklist: fees and payment forms, who signs what, photos, the medical exam, where to send it, and what to keep. **Print the filing checklist** opens it;
   - your memo: the bottom line, what's needed before filing, the case assessment, the officer's strongest objection, the judgment calls Claude made, and filing logistics;
   - the client request, also in the client's language when you choose one on the Client request screen. **Copy the client request** puts it on your clipboard as plain text.
9. **Ask Claude about the matter.** Under the main card, type a question into **Ask Claude about this matter**, or press one of the suggested questions. Claude answers in the chat from the matter's documents and work, looks up the law in BIA Edge, and makes the changes you ask for ("Lead the letter with the joint lease"), keeping the packet in step. What's left and the Packet screen's review notes have **Ask Claude about this** beside each item. A change made in chat shows on the matter page until **Update the packet** checks it again, and the research Claude did in chat carries into the next build.
10. **Answer and update.** When Claude needs your decision, the matter shows **Needs your answer**. Each question has its own answer box, and **Use the recommendation** fills in Claude's suggestion when it has one. When the client sends more documents, add them. Either way, press **Update the packet**, and Claude works in the new information and checks the packet again.
11. **Go back, redo, change.** Under the main card, **More you can do** lists everything else you can do with the matter right now, each with a line on what it does:
   - **Add documents…** at any point. Before a build, **Review the documents again** looks at everything once more and rewrites what's missing. After one, **Update the packet** works them in.
   - **Tell Claude what to change**: a correction in your own words. Claude redoes only what it affects.
   - **Redo a step…**: on the Packet screen, **Redo from here** redoes that step and every step after it.
   - **Change what is being filed**: another case type or posture. The steps start over; your documents stay, and earlier work is kept.
   - Undo is there too: **Stop** while Claude works, **Reopen** an item you marked done (What's left › Resolved), **Remove** a document and **Put back**, and **Undo** after Mark as filed.

   **Help › How do I…** answers these in one line each.
12. **Keep track.** Each matter has a **Timeline** of what happened: documents added, runs started and finished, items you settled, filing. **Archive** puts a finished matter away (Archived, at the end of the list); sort the list by updated, name, case type or status. In the side panel, **n** starts a new matter, **f** finds one, **1–9** open one, and **b** presses a matter's main button.

You can also ask in the chat: "Build the packet for the Garcia matter", "What documents are we still missing for Lopez?", "Ask Immigration Packet Builder about Nguyen N-400: does the 2021 trip break continuous residence?", or "Read the Nguyen packet the way a USCIS officer would."

### What each status means

| Status | What it means | What to do |
| --- | --- | --- |
| Needs documents | The matter has no documents yet. | Add files… or Add a folder… |
| Ready to build | The documents are in. | Review documents first, or Build packet |
| Documents reviewed | Claude reviewed the documents; nothing else has started. | Copy the client request, or Build packet. When the client sends more, add it and Review the documents again. |
| Claude is working | A review or build is running. | Keep Claude open. Watch Claude work if you're curious. |
| Waiting for you | The start is in your chat box. | Press Return to send it, or Cancel |
| Paused | Claude stopped partway, or you stopped it, or Claude was closed mid-run. Everything finished so far is saved. | Continue building |
| Stopped | The build stopped on its own. | Try again |
| Needs your answer | Claude needs a decision from you. | Answer, then Update the packet |
| Waiting on the client | Every open question is the client's. | Copy the client request; add files when they arrive |
| Draft packet | Built, but some things are needed before filing. | See what's left |
| Ready to file | Passed the final review, including the officer's review. Nothing needed before filing is open. The packet is marked DRAFT until you approve it. | Read the memo and the packet; Approve for filing; Mark as filed |
| Filed | You marked it filed. | Nothing (Undo if that was a mistake) |
| Can't open | Immigration Packet Builder can't read the matter's folder. | Press it to have Claude repair it |

## Privacy

Client documents stay in the matter folder on your Mac. Claude reads them to do the work, so their contents go to Claude through your Claude account, as anything you share with Claude does. Immigration Packet Builder doesn't encrypt the folder; turn on FileVault.

- **Each step works from a copy of the client's documents,** never documents you removed or earlier work set aside, and the copies are deleted when the run ends.
- **Cleaning up never moves or deletes a client's document.** It deletes Claude's scratch files, the step copies, and the page images and OCR text the reviews make. Memos, forms, research, the packet and the text Claude read from each document stay. The **Clean up working files** button does the same at any time.
- **Research gets legal questions, not documents.** A build running in the background never sends a client's details anywhere: the network check refuses it, the document review, forms and packet steps can't reach research tools at all, and the app blocks any research request that carries a client's name or identifying number. In the matter chat, Claude includes the client's facts in research only when you ask it to. Every check is logged in the matter.
- **On screen,** step summaries, stops and the timeline never carry a client's name or identifying number.
- **The app's log** (in your Mac's Library › Logs) records no client names, folder paths or error text.

**Protected matters (8 U.S.C. 1367).** VAWA self-petitions, I-751 battery or extreme cruelty waivers, VAWA-based I-485s and I-765s, and T and U matters are protected, and so is any matter you mark protected (or the document review marks, when the record shows it). Every client mailing address on the forms is a safe address, your office address from **Your details** unless you give another, and the forms check confirms it. The client request is worded so it's safe if someone else reads it, in every language, and the memo reminds you to send it only through a channel the client says is safe. The folder is named by form numbers only ("Ramos I-360"), nothing on screen names the case, and the client's file names never go into Claude's instructions.

---

<details>
<summary><strong>What's inside</strong> (for developers)</summary>

| Part | What it does |
| --- | --- |
| `skills/senior-associate` | The orchestrator: runs the steps, keeps the open items, writes the attorney handoff |
| `skills/docs-review` | What's present, what's missing, what would strengthen the case |
| `skills/forms-preparer`, `skills/forms-reviewer` | Fill the current USCIS forms from the record, then check them independently |
| `skills/coverletter` | Write, research, and review the cover letter |
| `skills/packet-assembly` | Build the packet PDF |
| `skills/final-review` | One pass before filing: a check of the whole packet and the officer's review, with the strongest RFE, NOID, or denial theory and its cure. After fixes, it re-checks only its earlier notes and what changed |
| `skills/matter-chat` | Talks a matter through in chat: answers from the documents and the work, researches with BIA Edge, makes the changes the attorney asks for and records them, and keeps its research for the next build |
| `skills/setup` | Sets up the attorney's Mac from the chat: installs the tools (Homebrew first if needed), signs in to GitHub, changes the Matters or model letters folder, stages updates for verification, and updates the plugin. The app's **Ask Claude to do it** buttons send it the request |
| `agents/` | One agent per step, so each review is independent of the work it checks |
| `scripts/forms/` | Download, fill, verify, render, and audit USCIS PDFs |
| `scripts/packet/` | Render the cover letter and assemble the packet with bookmarks and placeholders |
| `skills/senior-associate/scripts/` | The workflow runtime. It records each step, refuses a step that didn't produce its files, and tells a re-review what changed since it last passed |
| `scripts/*.py` | Data handling: the shared matter state (`matter_state.py`: lock, run lease, your actions on open items, saved answers, settings, timeline), per-step workspaces, reading each document once (`extract_documents.py`), the network check before client facts leave the machine, the privacy check, and cleanup |
| `scripts/packet/fees.py` | The fee calculator, from USCIS Form G-1055 |
| `hooks/` | The `/matters` app: `register.tsx`, one file per screen in `hooks/screens/`, and the one status function in `status.ts` |
| `server/` | The app's local helper (`cli.py`, standard library only), which the `/matters` app calls, and its modules in `server/sa_server/` |

The contract every skill follows is `skills/senior-associate/references/matter-contract.md` (with `protected-matters.md` and `filing.md` beside it). The screens, in the order an attorney meets them, are described in `docs/EXPERIENCE.md`.

</details>

<details>
<summary><strong>Development</strong></summary>

- Every suite at once: `scripts/check.sh` (`--quick` skips the app tests and plugin validation). CI runs the quick set on every push.
- App tests: `claude plugin test .`; they draw every screen against payloads the real server produces (`bash tests/make-golden.sh` refreshes them after a server change)
- Plugin checks: `claude plugin validate .` (and `claude plugin validate ..` for the marketplace)
- Forms tools tests: `uv run --script scripts/forms/tests/test_forms_gate.py`
- Packet tools tests: see `scripts/packet/README.md`
- Workflow runtime tests: `uv run --script skills/senior-associate/scripts/tests/test_workflow_runtime.py`
- `scripts/dev-sync.sh <dev mod folder>` mirrors the app into a hot-reloading mods folder while you work on it.
- To release: bump `version` in `.claude-plugin/plugin.json`, add a `CHANGELOG.md` entry, and push. Users get the new version only when the version string changes.

</details>

Every packet Claude assembles is marked DRAFT above each page until you approve it. On the Packet tab, **Approve for filing** lists whatever is still open (items needed before filing, review notes, form-check errors); you can approve as it is, with a line on why, and the approval records that exact version, what was open and your reason. The approved copies, without the marking, go in the matter's folder under Approved for filing. A change to the packet or the client's documents needs approving again. See [data handling](docs/DATA-HANDLING.md) and [verification](docs/VERIFICATION.md).

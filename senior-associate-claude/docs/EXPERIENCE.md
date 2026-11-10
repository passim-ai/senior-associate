# Immigration Packet Builder: the experience, screen by screen

The person: an immigration attorney who has never used Claude. They installed the plugin because it promised one thing: client documents in, a filing packet out, and an honest list of whatever is still missing. They don't know what a slash command, a side panel, or a session is. Every screen has to answer three questions without them asking: where am I, what should I do now, and what will happen when I do it.

The frame is the Claude desktop app's Code tab. The app draws with Claude's own elements, so it inherits Claude's font, cursor, focus ring, keyboard and screen-reader behaviour, and its colours: every text, card, line and button follows the app's light or dark theme, so the panel reads in either. Passim shows in its wordmark at the top left and in its orange, kept to bars, the tab underline and the step track. Cards are the app's raised surface inside its faint border, with thin rules between sections. Headings are Claude's font, semibold. Buttons are Claude's own, drawn natively, the whole button the press: the main one is the app's main button (dark in a light theme, light in a dark one), its companion outlined, and links plain text. A button shows only its words, so its words say what it does ("Open", "View ›", "Mark done"). A text field has its label above it and takes the width it is given. Nothing is drawn as a terminal.

Every screen has the same header: Passim's wordmark, a thin rule, "Immigration Packet Builder", and at the right **Matters**, **Your details**, **Setup** and **Help** (and **Open as side panel** in the conversation). In the side panel the header stacks: the lockup, then the four places in a row. Under it, where you are ("Matters › Garcia I-130 I-485"), the screen's title, and on a matter its tabs.

## Principles

1. **One next step, obvious.** Every screen answers "what do I do now?" in its first lines.
2. **Plain English.** No step ids, file paths, item ids, review codes, or words like workflow, ledger, vault, artifact, deliverables, schema, runtime.
3. **Set expectations.** Say how long things take, that Claude must stay open, and where results appear.
4. **Never strand the attorney.** Every state has a way forward: after new documents arrive, after a stop, after a restart. Never claim work is happening when it isn't.
5. **Every step can be taken back or done again.** Adding a document, Mark done, Mark as filed, a case type chosen by mistake, a step Claude got wrong: each has its undo or its redo, on the screen where the attorney would look for it, with one line on what it will do.
6. **Errors say what happened and what to do,** in one sentence, with a button where one helps. Never show a raw error.
7. **Messages appear where the eye is,** and go away when they no longer apply.
8. **One name per thing** (the glossary below).

## Words

| Say | Never say on screen |
| --- | --- |
| **packet**; **draft packet** while anything is needed before filing | package, binder, output |
| **your files** ("Files for this matter") | deliverables, outputs |
| **steps** ("step 4 of 10: Cover letter") | stages, workflow, stage track |
| **open items**; the tab is **Questions** ("Questions & missing evidence") | ledger, open-items.json |
| **needed before filing** / **not needed before filing** | blocking, non-blocking |
| **your decisions**, a **question for you** | attorney_decision |
| **for you to do** | attorney_action, actions |
| **from the client**, the **client request** | client_document |
| **reviewer notes** (important, worth fixing, minor, check by hand) | findings, review codes, raw severities |
| **officer's review**, part of the **final review** | adjudicator, stress test, officer's read |
| **update the packet** | continue the workflow, reroute, resume |
| **redo** a step ("Redo from here"), **review the documents again** | reroute, rerun a stage |
| **Tell Claude what to change** | instructions, feedback loop |
| **approve for filing**; the **approved copies**; what is **open** before approving | sign-off gate, release, export, blockers, digest |
| **clean up working files** | close out, closeout report, scratch, quarantine |
| **working notes** | vault, stage memos, artifacts |
| **model letters** | exemplars |
| **Your details** | attorney profile |
| **BIA Edge** | Passim (the header's brand mark may stay) |

## Status names

The server is the source of truth for each matter's status (its `status`, from the run lease and the steps). The app adds only what it alone knows: a start waiting in the chat box, and a run of this session's that stopped. The status chip, the next step's heading, the matters list, the line under the Matters title and the notification all read the same status, the same way. The chip's colour follows it: the accent's light shade where the attorney is needed, navy's while the work goes on, amber's where it waits, green once it can be filed, red when it stopped, and plain otherwise.

| Status | When |
| --- | --- |
| Needs documents | No client documents yet |
| Ready to build | Documents in, nothing started |
| Documents reviewed | The document review finished and nothing else has started |
| Claude is working | A step is running right now |
| Waiting for you | A start went into the chat box and waits for the attorney's Enter |
| Stopped | A run of this session's stopped on its own, or before it changed anything (red) |
| Paused | Steps started and nobody is working on them: no run holds the matter (a run that isn't renewed for 30 minutes lets go of it), and a stop the attorney chose |
| Needs your answer | An open question only the attorney can answer |
| Waiting on the client | Every open question is the client's |
| Draft packet | Built, with things needed before filing. A list of open items Claude can't read is said on the card ("Needs fixing first"), with Ask Claude to do it |
| Ready to file | Passed the final review; nothing needed before filing is open. The packet stays marked DRAFT until the attorney approves that version; approving doesn't change the status |
| Filed | The attorney marked it filed |
| Can't open | The server can't read the matter, or it is a link to a folder outside the Matters folder (red); pressing it asks Claude to repair it |

No screen decides a status from when a file last changed. Claude is working means a run holds the matter right now (Claude in the app's own agent, in the chat, or one started by hand); a step still marked running with no run holding it is Paused everywhere.

## Install and first launch

The attorney never opens Terminal. The repository's front page has one message to paste into the Code tab, and Claude does the rest: Apple's command line tools and Homebrew if they're missing (Homebrew's macOS installer package, so macOS asks for the password in its own window), then `uv`, Ghostscript and poppler; `~/Matters`; and the plugin itself, installed with the copy of Claude's command-line tool that ships inside the desktop app, because `/plugin` isn't available in the Code tab. Automatic updates are left off; new versions are staged and checked before activation. It ends with: quit Claude with ⌘Q, reopen it, open the Code tab in the Matters folder, and type `/matters`.

After that, every setup task (a missing tool, another Matters folder, model letters, an update) is a request to Claude. The plugin's `setup` skill holds the steps, and the app's **Ask Claude to do it** buttons send the request to the chat as the attorney's own words (with the chat box as the fallback when the chat won't take it).

## Getting set up

Shown automatically the first time, and whenever a required check fails before a build. Also reachable from Help ("Check my setup").

- Title **Getting set up**; sub "Once, about 5 minutes."
- One row per check, from the server's `doctor`:
  - ✗ **Ghostscript** prints the filled USCIS forms. "Claude can install Ghostscript for you." **Ask Claude to do it**.
  - ○ **LibreOffice** (optional) makes the letter's PDF match Word exactly.
  - ○ **poppler** (optional) reads the forms back for checking.
  - ✗ **Matters folder** must exist and be writable.
  - ✗ **Your details** go on the G-28 and the letter. **Add your details**.
  - ○ **Model letters folder** (optional).
  - ○ **Case-law research**: connect BIA Edge in Claude's Connectors so letters can cite case law.
- There's no Homebrew row: Claude installs Homebrew first when a tool needs it.
- Under the rows: "Ask Claude to do it sends the request to Claude in the chat. Claude does the installing and asks before each step; choose Allow. When it's done, press Check again."
- Foot: **Check again** ("After Claude installs what's marked ✗") · "Continue anyway".

## Welcome

The first screen once setup is done:

- Title **Matters**, "Client documents in. Filing-ready packet out.", and at its right **New matter** ("Name the client and the case"); while Your details are empty, **Add your details** ("2 minutes, once") comes first and New matter beside it.
- A rule, then the eyebrow **YOUR FIRST MATTER** and the headline *A clear path from documents to review.*, with a line that nothing is filed or sent.
- Three numbered steps (01, 02, 03 in the accent) between rules, three across when the panel is wide and one under another when it is narrow: **Add the documents**, **Review what's needed** (a document review takes about 5–10 minutes), **Build and review** (a full build about 1–1½ hours, in the background).
- While Your details are empty, a line on what they go on.
- **See how it works**, "A fictional I-601A case to try first", with **Open the sample matter**, when the sample is on the list.
- Foot: where the documents stay ("Documents stay in your Matters folder on this Mac…") and "Type /matters any time to come back." Open as side panel is in the header.

## The sample matter

The first time the app opens on an empty Matters folder, the server adds *Sample - Barrientos-Eckhardt*: the fictional I-601A in `samples/barrientos-eckhardt-i601a/` (14 scanned documents marked SPECIMEN, with gaps planted on purpose), the case type and paper filing set. It is added once: a Matters folder that already has matters never gets it, and once archived or deleted it doesn't come back by itself (the Matters folder's `.senior-associate/sample.json` records that it was offered).

- It doesn't take the welcome's place: the sample alone on the list still shows the welcome, whose **See how it works** offers **Open the sample matter** ("A fictional I-601A case to try first"), and it never opens by itself.
- Its Overview has a card under the next step, **This is a sample matter**: what it is, then "Press Review documents first…". Once the document review has passed, the card lists **What a good review catches** (the eight planted gaps) and says to compare them with Questions. Then a line on what a full build costs and that it can be archived.
- **Help › How do I… › Try Immigration Packet Builder on a fictional case**, **Open the sample matter**: opens it, takes it out of the archive, or adds it again when its folder is gone.

## Your details

Name, firm, mailing address, phone, email, bar number, licensing authority, discipline status, and USCIS online account number, with **I don't have a USCIS online account** beside it (then nothing asks about one). One field each, labeled, with an example. Every build uses them for the G-28, each form's preparer section, and the letter's letterhead and signature. In a VAWA matter, the mailing address is also the client's safe mailing address on every form, unless the attorney gives another.

- Enter (or the **save** beside a field) saves and stays: a green line at the top, "✓ Saved. Every build from now on uses your details.", and "✓ Saved" under that field until its text changes or the screen does. **Save** returns to wherever the attorney came from, with "✓ Your details are saved." there. The discipline choice saves on its own. Saves are confirmed on the page, never only in a toast: the side panel can hold toasts until it closes.
- The path line reads "Saved on this Mac, in your Matters folder."
- **Back** with changes typed but not saved asks on the page: "You changed Firm and Phone and haven't saved them." **Save and go back** · **Discard** · Keep editing.

## Matters

What `/matters` shows once a matter exists.

- Title **Matters**, with **New matter** at its right. The line under it: "2 need your answer · 1 stopped · 1 in progress · 3 ready to file". Need your answer counts only matters with a question for the attorney; a stop and a start waiting in the chat box are said as such.
- Groups, each with its heading: **Needs you**, **Claude is working**, **In preparation**, **Ready to file**, **Filed** (collapsed), and **Archived (n)** (collapsed) at the foot.
- **Sort:** Updated (the default), Name, Case type, Status, as chips; the order holds within each group, for the session.
- A row is a card: the client's name with the status chip beside it, then one line: "I-751 waiver · Answer 2 questions · updated Oct 27", and **Open** at its right (below, in the side panel), which 1–9 also press. A live run shows "step 4 of 10: Forms review and Cover letter".
- The list refreshes by itself every 15 seconds and whenever `/matters` is typed again, so a build that finishes elsewhere shows at once.
- **Pick up where you left off** appears only with more than three matters, with **Open <matter>**. Past six, a search field filters as they type.
- **New matter** is at the title's right; **Your details** is in the header, and while they're empty the list says "Add your details so the G-28 and the letter carry your name and bar number".
- Keys, in the side panel: n New matter, f find, 1–9 open the matter in that place.

## New matter

Matters › New matter; the title and a line; then a card per question:

- **Who is the client?** Placeholder "e.g. Maria Garcia". The preview shows what the matter will be called ("Garcia I-130 I-485"), capitalized as it will be created; the small words of a family name stay as typed ("Maria de la Cruz").
- **What is being filed?** The six most common case types, one line each, then "More case types (6) ›" and **Something else** to describe it in words. A VAWA case is named by its form numbers only ("Ramos I-360"): that is what the app calls it, on the list and on its page. Its folder in Finder gets a neutral name ("Matter 3F9A21C0B7"), and the page says so before the matter is made ("Here it will be called “Ramos I-360”. Its folder in Finder gets a neutral name instead, because this client is protected."); Matter details names the folder to look for. Requests to Claude and its agents name the folder, never the client.
- **New filing or a response?** New filing to start with; for an RFE or NOID: "Add the RFE notice along with the client's documents."
- **How it is filed**: On paper, by mail (the default) or Online, in a USCIS account (online wherever USCIS takes the form; a form it takes only on paper goes in a paper packet of its own, and a paper matter's form that USCIS no longer takes on paper goes online); and "This client is protected under 8 U.S.C. 1367 (VAWA, T or U)", which keeps their name and documents out of anything Claude looks up. A VAWA, T or U case is protected by its type, and says so.
- Each choice is marked ● and its name says it is selected.
- Enter without a case type puts "Choose one below, then press Create matter." under the question, with an amber border.
- A duplicate name says "You already have Garcia I-130 I-485. This one will be named “Garcia I-130 I-485 (2)”." with **Open the existing matter**. The toast names the matter actually created.

## Matter

The screen for one case. At the top: "Matters › Garcia I-130 I-485", the client's name as the title, the case line under it (as the list shows it: a protected matter by its form numbers only, here and on Change what is being filed), and the status chip at the right. Then the matter's **tabs**: **Overview**, **Documents**, **Questions** (with how many are open: "Questions · 3"), **Packet**, **Memo & request**, **Timeline**. The tab open is in full over an accent underline, the others dim; the tabs wrap onto a second line in the side panel. The header marks where you are the same way. The tabs replace the summary rows that used to lead to those screens.

The **Overview**, from the top:

1. **The next step**: a card with the accent bar down its left edge, the eyebrow **NEXT STEP**, a heading saying where the matter stands in words ("Ready to build", "Your judgment is needed", "Claude is working", "Add the client's documents", "Draft packet ready", "Ready to file"…), what it means in a line or two, then the main action(s), each with a line under it on what it does: the main one the app's main button (b presses it, in the side panel, and the focus starts there), its companion outlined. Then links (Open draft packet, Watch Claude work, Stop…) and, in small type, what to keep in mind ("Keep Claude open until it finishes…", "macOS may ask…"). Between a press that starts Claude and the agent starting, the start buttons wait, and a second press says Claude is starting. While Claude works it holds the step track; when a run finished, **What Claude did** sits right under it.
2. The sample matter's guide, on the sample.
3. **The numbers**, between rules: **Documents** (how many), **Steps complete** ("3 of 10") and **Needed before filing** (how many); each number opens its tab (Documents, Packet, Questions).
4. **Needs attention** beside **Ask Claude about this matter**, two columns when the panel is wide, one under the other when it is narrow. Needs attention lists up to four open items and questions, needed before filing first, each with its kind ("Your decision · Needed before filing") and **View ›**, which opens Questions at it; then "All 9 on Questions ›".
5. Folded, each under a rule with ▸, opening to ▾ in place: **Attorney instructions** ("Saved; Claude follows them" or "None yet"), **More you can do** ("9 actions") and **Matter details** (the case, Documents "4 files · last added just now", Packet "Draft built · 2 needed before filing", Open items, Attorney memo, Client request, Timeline, and Open the matter folder in Finder, Show files in Finder, Show the earlier work in Finder).

### Ask Claude about this matter

A column on every Overview: "A question, some research, or a change you want made. Claude reads this matter's documents and work, looks up the law in BIA Edge, and makes the changes you ask for. It answers in the chat." While Claude works: "Ask anything while Claude works. Changes you ask for wait until it finishes, or go into your instructions for the steps it hasn't reached." Without BIA Edge connected: "Connect BIA Edge in Claude's Connectors so Claude can cite case law."

- One box, two lines, with **Ask** (placeholder "e.g. Does the 2019 arrest affect eligibility?" before a build, "e.g. How strong is our bona fide marriage evidence?" after). The question goes to the chat as the attorney's own words, "Ask Immigration Packet Builder about Garcia I-130 I-485: …", which the plugin's matter-chat skill answers. The page says "✓ Claude is answering in the chat." and the box comes back empty. When the chat won't take it, the question waits in the chat box: "Your question is in the chat box. Press Enter to send it to Claude." Pressed with nothing typed: "Type your question first, then press Ask." Asked while an error shows, the question carries the error as the app got it.
- **Or ask:** up to three questions from where the matter stands, each a press that sends it: what to file (before the case type is chosen); the officer's strongest objection ("How do we answer this: "Joint records begin two months before filing.""); a decision waiting ("Help me decide: Include an I-765…?"); before a build, "Does the client qualify, on the documents we have?", "What could stand in for the documents still missing?" and "What would an officer question first in this case?"; after one, "What would an officer question first in this packet?" and "What's the weakest point in the cover letter, and how do we shore it up?".
- Claude can change the work in chat: the letter, a form, the open items, the memo, the client request, and the standing instructions (a standing instruction appears in the box below). It records each change, and research it verified carries into the next build. After a build, a change made in chat is a change since the build, on the main card like new files: "Since the packet was built, you made a change in chat (Cover letter: leads with the joint lease). Update the packet to have the reviews check it.", with **Update the packet: re-checks what you changed in chat**. With more than one, the ask card lists them under "Changed in chat since Claude last checked the packet:".
- What goes into research is the attorney's call: Claude words queries as legal propositions unless the attorney asks it to include the client's facts, and asks for no further confirmation. Claude's own agents, at work on a matter, never send its client's names or identifiers to BIA Edge or a web search: such a call is refused, and the agent rephrases it as a legal question. The same goes for a command that reaches the network, and a matter run's agents use no other tool that could send words off the Mac (another connector, a publishing or messaging tool). Their own work, the plugin's scripts and every local command included, is never refused, and an agent that isn't working on a matter is never touched beyond the check on research. A precedent that shares the client's surname ("Matter of Garcia") is a citation and goes through. When the app can't check a request against the client's details, the request waits ("Try again in a moment") rather than going out unchecked.

### Attorney instructions

Folded on every Overview except Filed, and the box keeps its label "Additional attorney instructions": "Anything Claude should follow on this matter: what to lead with, what to leave out, how to argue it. Claude reads these before every step, in the build and every update after it." One box, four lines, with **save**. Saved, they live in the matter folder (output › working › workflow › attorney-instructions.md), every run's brief names the file, and each step reads it, so they hold for the build and every run after it until the attorney changes them. The save says when they take effect: before a build, "Claude follows them in every step of the build"; while Claude works, "The steps Claude hasn't reached yet follow them"; after a build, "Claude follows them from its next run. To redo the packet with them now, use Tell Claude what to change." Saving an empty box clears them. Text typed but not saved goes with the next run anyway: pressing Build packet, or any button that starts Claude, saves it first. Changing what is being filed keeps them. An instruction Claude can't follow without contradicting the documents or the law becomes a question on Questions instead. **Save instructions** under the box does what Enter does.

### More you can do

Every other thing that makes sense for the matter right now, folded under its heading with how many there are, so nothing depends on finding a hidden link. Each is its name as a press, then one dim line on what it does. What the next step already offers isn't repeated.

| Entry | When | Its line |
| --- | --- | --- |
| **Add documents…** | always, except Filed | before a build: "Then Review the documents again shows what's still missing"; after one: "Then Update the packet works them in"; while Claude works: "Claude won't see them in this run" |
| **Review the documents again** | only the document review has run | "About 5–10 minutes. Claude re-reads every document, new ones included… It doesn't build." |
| **Update the packet** | a step after the review has finished, and it isn't on the card | "Works in what changed since the build: documents added or taken out, items marked done or reopened, and your answers." |
| **Tell Claude what to change** | the same | "Claude redoes only the steps it affects, checks the packet again, and updates the memo." |
| **Redo a step…** | the same | opens the Packet tab, where each step has Redo from here |
| **Re-check as a USCIS officer would** | a packet exists | "About 15 minutes. A fresh, full officer's review…, not only of what changed; it updates Questions and the memo" |
| **Approve for filing as it is** | a packet is assembled and this version isn't approved (Ready to file has it on the card) | "Clean copies without the DRAFT marking. The Packet tab lists what is still open; your reason for filing with it open is kept with the approval." |
| **Show the approved copies** | this version is approved (Ready to file has it on the card) | "The clean copies of the version you approved, without the DRAFT marking." |
| **Mark as filed** | a packet exists (Ready to file has it on the card) | "Undo puts it back." |
| **Clean up working files** | every step done, Filed included | "Your documents and the finished files stay." It asks on the card first: "Delete Claude's working copies of the client's documents? …" **Yes, clean up** · **Keep them**. |
| **Change what is being filed** | always, except while Claude works | "A different case type, filing posture, or how it is filed. The steps start over for a new case…" |
| **Archive** / **Unarchive** | always, except while Claude works | "Takes it off the main list, into Archived at its foot. Nothing is deleted." |

While Claude works, only Add documents… shows; the card has Watch and Stop.

| Status | The next step's heading | It says | Main action | Second |
| --- | --- | --- | --- | --- |
| Needs documents | Add the client's documents | Add the client's documents to get started. | Add files… | Add a folder… |
| Ready to build | Ready to build | What Claude will do, and that missing documents become a list rather than a stop. | Build packet: "About 1–1½ hours · runs in the background" | Review documents first: "About 5–10 minutes · see what's missing first" |
| Documents reviewed | Documents reviewed | "Claude reviewed the 23 documents. 4 things are missing; they're on the client request. Send it now and build when they arrive, or build now and Claude leaves placeholders." With questions: "2 questions wait for you on Questions (0 answered). Your answers go with the build…" Then "When the client sends more: Add documents…, under More you can do, then Review the documents again." | Build packet | Copy the client request: "ready to paste into an email" |
| Documents reviewed, new files since | Documents changed since the review | "2 new files arrived since Claude reviewed the documents. Review the documents again to see what's still missing and refresh the client request. Or build the packet now: the build starts by reviewing them." | Review the documents again: "About 5–10 minutes · see what's still missing" | Build packet: "reviews them first" |
| Claude is working | Claude is working | See "While Claude works" below. | Watch Claude work | |
| Paused | Paused | "Claude stopped working on this yesterday, at step 4 of 10 (Cover letter). Everything finished so far is saved." Stopped during the document review, it offers Finish the document review. A step the server still calls running, with nothing changed for 20 minutes and no run of this session's, is Paused too, with "If Claude is still working on it in the chat, leave it." | Continue building: "picks up at Cover letter" | |
| Needs your answer | Your judgment is needed | See "Needs your answer" below. | Review questions: "2 questions · 0 answered" | Update the packet: "with your answers" |
| Waiting on the client | Waiting on the client | "Waiting on the client for 3 items." | Add files…: "what the client sent" | Copy the client request |
| Draft packet | Draft packet ready | "The draft packet is built. 6 things are needed before filing: 3 from the client, 2 for you and 1 risk to weigh." The parts always add up to the total. | Copy the client request (when the client owes anything), else Review questions | Review questions: "6 needed before filing" |
| Ready to file | Ready to file | "The packet passed its final review, including the officer's review, and nothing needed before filing is open. Every page is marked DRAFT until you approve it: read it through, then approve it to get clean copies to file." A question for you that the packet can be filed without waits on Questions, marked "Not needed before filing", and Update the packet works an answer in. Files added since the build are offered with Update the packet, and Mark as filed and Print the filing checklist stay: the attorney may file without them. | Open packet | **Approve for filing** ("Then clean copies, without the DRAFT marking", or "2 points to look at first"), which opens the Packet tab at the approval; Read the memo; Update the packet (with such a question); Mark as filed |
| Ready to file, approved | Ready to file | "You approved this version for filing on November 9, 2026. The clean copies, without the DRAFT marking, are ready to print or upload. Follow the memo's Filing logistics: signatures, photos, fees and mailing." | Show the approved copies | Read the memo; Mark as filed |
| Filed | Filed | "Filed Oct 30." | | Undo |

With new files, files taken out or changes in chat since the build, the heading is "Changes to work in". A draft also offers **Open draft packet** and **Re-check as a USCIS officer would**. In Draft packet, Waiting on the client and Ready to file, a question not needed before filing waits on Questions with its answer box, and Needs attention's **View** finds it. Ready to file and Draft packet offer **Print the filing checklist** once Claude has written it (fees and payment forms, signatures, photos, where to mail or how to file online).

**Your details gate.** On Build packet in Ready to build or Documents reviewed with Your details empty (it goes once they're filled in, however they were saved): "⚠ Your details aren't filled in, so the G-28 and the letter's signature will be left blank." **Add your details first (2 minutes)** · **Build anyway**.

**New documents.** A file the client sent, and a file Claude had read that was since replaced with a new version, are offered the same way. After a document review only: see Documents reviewed above ("Passport.pdf changed since Claude reviewed the documents." works the same way, with Review the documents again). In Waiting on the client, Draft packet, or Ready to file, when client files arrived after the last build: "3 new files arrived since the packet was built. Update the packet to work them in and re-check it."; when one was replaced: "Passport.pdf changed since the packet was built. Update the packet to work in the new version." ("2 files changed…" for more); both, or with files taken out or changes in chat: "Since the packet was built, 2 new files arrived and Passport.pdf changed. Update the packet to bring it up to date and re-check it." Main action **Update the packet: works in the 3 new files** (or "the new version of Passport.pdf"). The Documents screen marks each file new or changed and has the same press; Claude's brief for the update names what changed. In a protected matter no file name is said, only how many. With none new, Add documents… is under More you can do. After adding, a green line on the page names the press that works them in ("Added 2 files. Press Review the documents again to see what's still missing, or Build packet to start the build with them." before a build; "Press Update the packet to work them in." after one); the server's own summary of what was and wasn't added comes first. A Build after new files reviews them first.

### Starting a build

Build starts the app's own background agent on the matter: the Immigration Packet Builder orchestrator the plugin ships. Nothing is typed into the conversation.

When the attorney's permission settings don't let the app start Claude itself (Auto mode, for example), the request goes into the chat box: "Build the packet for Garcia I-130 I-485 with Immigration Packet Builder, in the background.", a blank line, then the brief. The note says "Claude needs your OK to start. Press Enter to send the request in your chat box." A **Waiting for you** card shows meanwhile (with Cancel), and the page switches to Claude is working by itself once the agent appears: the app knows it by the run id in its brief, whatever the chat calls it. The request holds the matter for 10 minutes; not sent by then, it lets go, takes the request out of the chat box, and the page says "The start in your chat box wasn't sent. Press Build packet to try again." When the box can't be cleared, it says so: "…It's still in your chat box: delete it there rather than send it." A request sent after all, whose run Claude has taken up, is never let go of: the matter shows Claude is working until that run finishes. If even that fails: "Claude couldn't start the build from here. In the chat box below, type: Build the packet for Garcia I-130 I-485, then press Enter."

### While Claude works

- Heading **Claude is working**. Bold: "Building the packet · step 4 of 10: Cover letter", the step track (one segment per step: done in the app's text colour, the accent running, faint for what's to come) and "Then: Research, Letter revision". Then "Started 2:14 PM · running 22 min · about 50 min left".
- Dim: "Keep Claude open until it finishes. You can use Claude for other things meanwhile; you'll get a notification when it's done."
- The sentence fits the run: a document review, a build or update, or an officer's review.
- **Watch Claude work** opens the agent's transcript. **Stop** asks first, on the card: "Stop Claude now? Everything finished so far is kept. Continue building picks up where it stopped." **Yes, stop** · **Keep working**. A stop the attorney chose shows as Paused, not Stopped, with a green line that everything Claude finished is saved; Continue building (or Finish the document review, for a review) carries the same answers and instructions. A stop before Claude changed anything stays Stopped, with Try again, which carries them too.
- Claude working outside this page (started from the chat, or changing the matter in the chat) says so, with when it last made progress. Nothing else can start meanwhile: a start is refused in plain words. (A matter an older plugin was building keeps no run lease; then **Not working? Continue building** is offered.) When the attorney knows that run has stopped (the chat was closed mid-run, say), **Claude isn't working on this anymore** asks on the page first ("Let go of this matter? Do this only if Claude isn't working on it in the chat or another window…", **Yes, let it go** · **Keep waiting**), then frees the matter; the timeline says so, and a run that was still going stops at its next step.
- Mark done, Reopen and Accept this risk still work, and say "Claude takes this into account when it finishes." Answers and instructions can be saved too.
- When the agent is waiting for a permission answer: "Claude is waiting for your OK in the chat. The build continues once you answer."
- After 20 minutes with no change: "Nothing has changed for 20 minutes. Claude may be waiting for your OK in the chat, or it stopped." **Watch Claude work** · **Stop and try again**.
- The page refreshes itself every fifteen seconds, silently.

### When it finishes

A notification (a toast if notifications aren't available) names the matter, and the next `/matters` opens that matter: "Garcia I-130 I-485 is ready to file." / "Garcia I-130 I-485: draft packet ready. 4 items are needed before filing." / "Garcia I-130 I-485: Claude needs your answer on 2 questions." / "Garcia I-130 I-485: the build stopped at Forms review. Open it to try again."

The agent's short report appears as **What Claude did**, "finished 3:29 PM, took 1 h 15 min", right under the next step, drawn like the memo.

### When it stops

"The build stopped at step 3 of 10 (Forms review): Claude hit a temporary problem, such as a busy service or a dropped connection. Everything finished before that is saved." Other reasons: "It was stopped", "Claude declined to continue", "It ran into an error". Main action **Try again: picks up at Forms review**; links **See what Claude was doing** and **Not now: show where the matter stands**, which sets the stop aside so the card shows the matter's own state and every way forward (a redo from an earlier step, say). Chip **Stopped**, in red. The raw report of a failed run is never shown.

### Needs your answer

- Heading **Your judgment is needed**. First line: "Answer what you can on Questions, then press Update the packet. Anything you leave blank stays on the list for later."
- Main action **Review questions** ("2 questions · 0 answered"), which opens the Questions tab, where the answer boxes are (below); beside it **Update the packet: with your answers**.
- Setup problems show their fix on the Overview, with **Ask Claude to do it** and **Done — check again**, which says what it found ("Everything Claude needs is on this Mac now. Press Update the packet…", or what's still missing). With only setup problems, the heading is "Something on this Mac needs setting up", the lead line says so instead of asking for answers, and Update the packet is the main action.
- What the client owes, from Claude's questions, is on Questions under **Waiting on the client**: bullets, no boxes, and "Client sent it? Add files…".

## Redo, Review the documents again, Tell Claude what to change

One screen for doing work again, reached from Redo from here on Packet, Review the documents again, or Tell Claude what to change. It says what will happen before anything does:

- **Redo Forms**: "Claude redoes Forms and every step after it: Forms review, Cover letter, … Document review stays as it is. About 1 h 14 min, in the background. The current files stay in the folder until Claude replaces them."
- **Redo** a review step (Forms review, Letter review, Final review) adds: "Forms review is done fresh and in full: Claude checks everything again, not only what changed since the last review, and reads the earlier findings only as a reference."
- **Review the documents again** (only the review has run): "Claude re-reads every document in the matter, including any you've added since, and rewrites what's missing, the memo and the client request. It stops before the forms." After a build, Document review's Redo from here is a redo of every step.
- **Tell Claude what to change**: "Claude works in what you write below: it redoes the steps your change affects, checks the packet again, and updates Questions, the memo and the client request."
- "It also works in the 2 new files and your 3 answers." when there are any.
- A box: "Anything Claude should know? (optional)" for a redo, "What should Claude change?" for a change, which needs words (or new files or answers) before it starts.
- **Redo from Forms** / **Review the documents again** / **Update the packet**, with the time; **Cancel**: "Nothing changes", back to where the attorney came from. Starting it opens the matter page, Claude at work.

## Change what is being filed

From More you can do. "Now: I-130 / I-485 immediate relative · New filing", then what happens: before anything has run, "this only changes what Claude will build"; after, "The steps start over for the new case, and your documents stay. The current packet, memo and open items are kept in the matter folder (output › earlier), not deleted." The matter keeps its name. The case list, posture and How it is filed as on New matter, starting on the current choices. **Change and start over** (or **Save**) "As N-400 naturalization" · **Cancel**. Changing only how it is filed, or protection, saves at once and starts nothing over. A last card, **Where the case is decided**, holds who decides it (USCIS, to start with), the federal circuit as named choices (First to Eleventh, D.C., Federal, None applies) and why that circuit applies; each saves as it is chosen, with "✓ Saved. Claude uses it from its next step on." With nothing changed, the press says so and does nothing. Afterwards the matter page has **Show the earlier work in Finder**, and the earlier case's report and answers are gone from it. A folder made outside the app chooses its posture on its first card too.

## Questions

The tab **Questions & missing evidence**, with a chip "2 needed before filing", the count ("3 open items, 2 needed before filing"), and "Save your decisions here, then update the packet to apply them." (before a build: "they go with the build").

**Attorney decisions · 3 of 12 answered**: every question only the attorney can answer, Claude's and the open items' alike, each once, numbered 01, 02… in the accent, those needed before filing first (marked so, the rest "Not needed before filing"). Each shows its question, a dim line of detail, and when Claude has a recommendation, a **Suggested approach** box (on the surface, a rule at its left: "Recommended: Yes. No extra fee with a pending I-485…") with **Use the recommendation**, which saves "Go with your recommendation: …". Then its own answer box, labelled "Your answer to question 1" and keyed by its question, so two questions never share a box, with **Save answer** under it. A save (or Enter) keeps the answer in the matter, so quitting Claude doesn't lose it, and shows "✓ Saved" beside the button and "✓ Answer saved. Claude gets it when you press Update the packet." at the top (**Build packet** after a document review). Typed answers go with Update even unsaved; save is how the attorney sees that one landed. While Claude works, the questions show without boxes: "You can answer it here once Claude has finished." Questions Claude asked only in its report get one box each (or one box for them all when they can't be told apart). Each decision has **Ask Claude about this**.

Then the other open items, grouped by who acts: **From the client**, **For you to do**, **Risks to weigh**, then **Waiting on the client** for what Claude asked of the client outside the list. Each item has its title, one or two lines on why it matters, and "Needed before filing" when it is. Each item has a way to act on it:

- from the client, a document: **Received — Add files…**, which then shows the Overview, where the press that works them in is
- from the client, a question: **The client answered — tell Claude**, which opens Tell Claude what to change with the question already written
- for you to do: **Mark done**
- risks: **Accept this risk**, which resolves it
- items about Your details link there.
- an item Claude listed without an id can't be marked here: the press says so, and to ask Claude to do it.
- every item: **Ask Claude about this**, which puts the matter, the item and a first question in the chat box for the attorney to change or send ("Ask Immigration Packet Builder about Garcia I-130 I-485, about "Include an I-765…?": Help me decide. What are the options, and the risk of each?"), with "Your question is in the chat box below. Change it if you like, then press Enter." Nothing is sent.

Each press is named for its item ("Mark done: Sign the G-28", "Save answer: Include an I-765…?"), so a screen reader tells them apart. A list Claude wrote that can't be read says so ("Claude's list of open items can't be read"), here and on the Overview, with **Ask Claude to do it** to rewrite it, never as no list yet. Then **Copy the client request** (plain text: no Markdown symbols, numbering and bullets kept), **Copy it in Spanish** for each other language it was written in, **Show the client request**, and **Resolved (3) ›**, which lists what's settled, each with how it was resolved and **Reopen** ("Back on the list. Claude takes it up again on the next update."). Mark done confirms on the page and says where Reopen is. At the foot, under a rule, **Ready to use your answers?** "Saved answers are worked in the next time you update the packet." with **Update the packet with saved answers** (before a build, **Build packet**: "Your saved answers go with the build").

## Memo & request

One tab for the two documents Claude writes for the attorney, read right here, never in another app. At its top, a switch of two: **Attorney memo** · **Client request** (the one shown is the app's main button). Each document is drawn on a card, by the app's own reader: headings semibold, bulleted and numbered lists, bold and italic, tables as aligned rows, notes with an accent rule, links as their words with the address after them. It never uses the host's Markdown, which takes none of the panel's sizes or colours.

**Attorney memo**: eyebrow ATTORNEY WORK PRODUCT, then the memo. Its status line reads "**Draft packet — 6 things are needed before filing**" or "**Ready to file**". Then the bottom line (verdict first), what's needed before filing (from the client, your decisions, for you to do, with counts that add up), what's not needed before filing, the case assessment and the officer's strongest objection, the judgment calls made, filing logistics, sources checked, and how this was checked. Beside the switch: **Copy memo** (plain text) and **Open the memo file**, which opens the memo's PDF (the Markdown when the PDF is missing or older). Below it: **Copy the client request**.

**Client request**: eyebrow FOR THE CLIENT, then the request; main action **Copy the client request** ("Plain text, ready to paste into an email"), and **Copy it in Spanish** for each other language it was written in; "Claude rewrites it after every document review and update." Then **Also write it in**: English only, Spanish, Portuguese, French, Haitian Creole, Vietnamese, Chinese, Other… (a box for any other language). Claude writes it in that language too from the next document review or update, and always in English for the attorney. Show the client request, on Questions, opens it here.

## Documents

- **Source documents**, then "4 files in the matter folder" ("450 files · showing the 300 most recent" when the list is capped).
- Grouped by folder, each heading with its count and a rule, each file a row between rules, newest first. The first 8 files per folder, then "Show all 64". A file new or replaced since Claude last looked carries a chip, "new" or "changed".
- At the top: Add files…, Add a folder…. Foot: "Open the matter folder in Finder to see every file."
- When files arrived since Claude last looked, the press that works them in is here too: "2 new files since Claude reviewed the documents." **Review the documents again** (or **Update the packet** after a build) · **Add more files…**.
- A file's name opens it. **Remove** (named "Remove Passport.pdf") asks on its row ("Take Passport.pdf out of the matter? It's kept, and Put back returns it.") and moves it to the matter's output/removed documents, where Claude doesn't read it. **Removed · 2** lists them, each with **Put back**. Neither Remove nor Put back is offered while Claude works.
- Adding a folder toasts "Copied 230 files into the matter. Your originals stay where they were." plus anything skipped.
- Before the first file picker: "macOS may ask whether Claude can control System Events. Choose OK; that's what lets the file picker open in front." A cancelled picker toasts "No files added."

## Packet

First, once a packet is assembled, **Approve for filing**: the attorney's sign-off on this exact version. Every packet Claude assembles is marked DRAFT above each page; approving a version puts clean copies, without the marking, in the matter's folder under Approved for filing. The attorney can always approve an assembled packet: what is still open is listed first, in plain words, and approving with any of it open takes a line of reason, kept with the approval.

- Nothing open: "Every page of the packet is marked DRAFT until you approve it. Read it through, then approve: clean copies without the marking go in the matter's folder. Nothing is filed or sent." **Approve this version for filing**.
- Something open: "…You can approve it as it is; 3 points are open first, and your reason for filing with them open is kept with the approval.", then each point ("• 2 open items on Questions are marked needed before filing.", "• The officer's review expects a request for evidence as it stands.", "• Review note: Joint records begin two months before filing", "• Forms check, I-485: …", "• The check that the law the letter cites is still current is more than a week old (last done 2026-10-30).", "• The packet or the client's documents changed after the final review…"), a box **Why you're filing with these open**, and the button. Pressed without a reason: "Say in a line why you're filing with these points open, then press Approve."
- Approved: "Ana Ruiz approved this version for filing on November 9, 2026. The clean copies… If the packet or the client's documents change, the new version needs approving again.", what was open when they approved and the reason given, and **Show the approved copies**.
- Only two things make approval impossible, each said with its way forward: nothing is assembled yet ("There's no assembled packet to approve yet. Build the packet first."), or the packet's clean copy is missing or changed ("…Press Update the packet so Claude assembles it again.").
- An approval holds until the packet or the client's documents change. The app's own records (an answer saved, the matter archived or cleaned up, the memo rewritten) and a check that ages afterwards never take it back. While Claude works: "approve once it has finished."

Then **Files for this matter**, once there are any (below). Then **Steps**: "3 of 10 steps done", the step track, and every step with its marker (✓ when done, its number otherwise, coloured by its state), its state (done, in progress, skipped, not started) and one line on what it does ("Fills the current USCIS forms from the documents, leaving blank anything the record doesn't support."). Every step that has run has **Redo from here ›** (**Review again ›** for the document review when nothing else has run), except while Claude works. Then the reviewer notes in plain words only (important, worth fixing, minor, check by hand, note; to fix: you, the client or Claude) and, for a risk the officer's review found, the likely outcome ("RFE likely"); no review code ever shows, and a note the officer found approvable isn't an open note. Past 40, "…and 5 more. The memo lists every one."; each with **Ask Claude about this** ("Is this right, and how should we fix it?"), as on Questions. **Files for this matter**: the packet, the letter, each form (each opens on its own), **Print the filing checklist** once it exists, **Show the files to upload in Finder** for a matter filed online (with `Upload map.md` among them, saying where each file goes in the USCIS account), **Open the paper part** when a split filing has one, and **Show files in Finder**. Matter details, on the Overview, reads "Draft built · 6 needed before filing" when an open-items list exists. Clean up working files is on the Overview (More you can do), once every step is done.

## Help

**Help** in the header of every screen; the page's line says the version ("Immigration Packet Builder 1.3.0").

- How it works, in four steps.
- **How do I…**: ask about a case, research a point, or have one thing changed; add documents after a review or a build; have Claude look at the documents again; fix something in the draft; redo one part; change the case type or posture; take out a document; undo Mark done; stop Claude; undo Mark as filed. Each is the question in bold and the presses, in one line.
- What each status means, Filed included.
- **Keyboard**, in the side panel once it has been clicked: b the matter's main button, n New matter, f find a matter, 1–9 open a matter, Tab and Enter.
- If something goes wrong: Try again; Update the packet; **Check my setup** (opens Getting set up); where your files are.
- "Questions or a problem: github.com/passim-ai/senior-associate/issues"

## Status messages

A note appears at the top of the page, under the title (and a matter's tabs), on a card with a bar at its left edge (green when it confirms, amber when it warns, the accent while something waits), with a "⚠" or "⏳" prefix and **Dismiss**. It clears on every navigation and after any successful action. Errors are friendly sentences, whether the server phrased them or the app's fallback did; anything of a program's (an error's name, a file path, a code) is never shown. While a Finder picker is open the note says so with **Close the picker**, which closes it and gives the page back at once. When the quiet refresh fails twice in a row, the note says why ("…isn't in your Matters folder anymore", with **Go back to Matters**) instead of the page going silent.

- "Immigration Packet Builder can't save in <folder>. Choose another matters folder."
- "Allow Claude to open the file picker: System Settings › Privacy & Security › Automation › Claude › turn on System Events, then try again."
- "<name> isn't in your Matters folder anymore. It may have been moved or renamed in Finder."
- "There's no packet yet. Build it first."

## Timeline

The matter's **Timeline** tab: what happened on the matter, newest first, grouped by day (Today, Yesterday, the date), each line a time and plain words ("You: Answer saved.", "Claude: Forms review passed."). A document is never named there ("You took out a document."): a file name often carries the client's name. The Documents screen names it, under Removed. Nothing is recorded before the first run of this version.

## Inline /matters and the side panel

Both placements (the row under `/matters`, and the side panel from **Open as side panel** or `/matters pane`) draw the same screen from the same state. When the side panel is already open, the inline row shows only "Immigration Packet Builder is open beside the chat." with **Show it**. The first two inline uses add "Tip: Open as side panel keeps this beside your chat while Claude works." Outside the desktop app: "Immigration Packet Builder opens in the Claude desktop app."

## Rules that hold everywhere

- One main action per screen, the app's main button, with at most one secondary beside it, outlined; a line under each says what it does. Links are plain text, quieter presses dim. A matter's row has **Open**.
- The way back is at the top left of every screen ("Matters › …"), and the header reaches Matters, Your details, Setup and Help from anywhere.
- Plain words, per the glossary. Agents' replies and the files they write follow it too.
- Nothing greys out except the main buttons while a Mac picker is open (a second press would open a second picker) or a start is on its way (a second press would start a second Claude).
- A press that can't be undone with one more press (Stop, Remove) asks on the spot, in a line with **Yes** and a way out; nothing else asks.
- What the attorney changed is never overwritten or refused. A cover letter revised in Word, or a packet marked up in Preview, is moved into **Your edited copies** in the matter's files before Claude writes a new one, and Claude raises one item so the attorney can say which edits to carry over. A matter built by an earlier version rebuilds as it always did.
- A name with a letter a USCIS form's own font can't print (Nguyễn, Łukasz) leaves that one box blank and becomes a question for the attorney ("The I-130 can't print ễ … How should the value go on the form?"); the rest of the form is filled, and nothing is respelled.
- What the attorney did is confirmed on the page in green (added, removed, put back, marked done, reopened, stopped, saved), never only in a toast.
- The app never submits a prompt the attorney didn't ask for. A question typed into Ask Claude about this matter, a suggested question pressed, and Ask Claude to do it go to the chat as the attorney's own words; Ask Claude about this only fills the chat box. Work runs as the app's own background agent; when that can't start, the request waits in the chat box for the attorney to send.
- Contrast holds in light and dark because the panel draws in the app's own theme colours, never a fixed colour behind words: on the app's light and dark backgrounds the text reads 18.7:1 and 17.1:1, the dim text 7.5:1 and 11.0:1, and the state colours (amber, green, red, blue) 5.4:1 or more (hooks/theme.ts measures each). Passim's orange (3.7:1 and 5.0:1) draws only bars, underlines and the track, never text.
- Everything can be reached with the keyboard and read by a screen reader: every box has its label, every press says in words what it does, and a choice shows ● when chosen and ○ when not.
- **Ask Claude about this matter** sends the attorney's question to the chat as their own words; **Ask Claude about this**, beside an item or a review note, fills the chat box and sends nothing.

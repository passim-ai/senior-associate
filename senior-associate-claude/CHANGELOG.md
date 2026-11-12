# What's new in Immigration Packet Builder

Your version appears at the foot of every Immigration Packet Builder screen ("Help · Immigration Packet Builder 1.5.0"). After an update, quit Claude with ⌘Q and reopen it.

## 1.5.0 (November 2026)

**Clients' names stay off the screen until you ask.** Your list of matters now opens with each group folded: what stands where and how many, and no names. **Show** opens a group; **Hide names** folds them all again. No matter opens by itself anymore, and **Pick up where you left off** says the matter by its case, not the client.

**Notifications never name a matter.** "A packet is ready to file." in place of the client's name. Type `/matters` and the list says what finished, with **Open it**.

**`/matters` opens beside your chat.** The side panel opens straight away, and nothing about a client is left in the conversation. Where the panel can't open, the app is drawn in the conversation as before; `/matters here` asks for that.

**A demo you can show.** `/matters demo` shows only the fictional sample matter, from a folder of its own, until you press **Leave the demo**. Your own matters are never listed there.

## 1.4.1 (November 2026)

**Use Auto for builds.** In Claude's usual permission setting, a full build stops to ask your permission several hundred times: 479 on the sample matter, seconds apart. The matter page now tells you to switch the permission setting under the prompt box to **Auto** before you build, and reminds you whenever a build is waiting for your OK. In Auto, Claude checks each step itself. In Auto the page puts the build request in your chat box; press Return to send it. Help has the same under "Stop Claude asking permission for every step".

## 1.4.0 (November 2026)

**See what the letter's law rests on.** Each matter's Overview has a **Research** card. It says when the law in the cover letter was last checked, how many authorities and cases support the letter, whether any case carries a limit, and how many points were researched for this client. The memo's Sources checked opens with the same summary. If a letter was researched without BIA Edge, the card says so and lists the points that got no case-law research, and the Packet tab lists it among the points to weigh before you approve.

**Check the law again before you file.** Weeks can pass between a build and a filing. **Check the law again**, on the Research card, the Packet tab and under More you can do, checks every cited case for later treatment and looks for changes in the law since the last check. It takes about five minutes with BIA Edge and changes nothing in the letter or the packet. If something the letter relies on has changed, it's added to Questions.

**How similar cases were decided.** When the letter argues a contested point, such as a waiver's hardship or the stated ground of an RFE, Claude looks for unpublished BIA and AAO decisions on similar facts and summarizes up to five in the memo, with links. They are not precedent and are never cited in the letter.

**BIA Edge.** Setup now says what BIA Edge is (Passim's immigration law library for Claude) and what it costs: $29 a month, with 14 days free for a new account (a card is required). **Start a free trial** opens Passim's sign-up page in your browser. If your Passim account has no research access, because a trial ended or a payment failed, the build goes on without case-law research and says so, and the app shows Passim's notice on Setup and the matter's page with a link to your account. Nothing in Immigration Packet Builder requires BIA Edge, and the app sends Passim nothing about you or your matters.

## 1.3.0 (November 2026)

**Every packet is a draft until you approve it.** Each page of a packet Claude assembles is marked "DRAFT — ATTORNEY REVIEW REQUIRED" in a band above the page. A finished matter says **Ready to file** and offers **Approve for filing**. The Packet tab lists whatever is still open (items needed before filing, review notes, form-check errors), and you can approve as it is, with a line on why. The approval records your name, the time, that exact version, what was open and your reason. The clean copies go in the matter's folder under **Approved for filing**. If the packet, the letter, the forms or the client's documents change afterwards, you approve again.

**Your edits are kept.** If you edit the cover letter in Word or mark up the packet and then rebuild, Claude moves your version to **Your edited copies** beside it and lists it as an open item, instead of writing over it. The first time you rebuild a matter made before 1.3.0, the letter and packet that were there are kept the same way, as earlier copies, in case you had edited them.

**Forms.**
- A question about arrests, removal, fraud, the security grounds and the like is answered only from the client's own dated answer. Without one, the box is left blank and listed as an open item. Claude no longer answers "No" because the documents are silent.
- A name with a letter the form can't print (Nguyễn, Łukasz) leaves that one box blank and raises a decision for you. Nothing is respelled.
- New checks catch contradictions before the packet is assembled: two answers to one question, dates out of order, a malformed Social Security number, and one person's name written two ways on different forms.

**RFE and NOID responses.** Claude plans the response against the notice itself. Each ground is matched to an answer and its evidence, and the deadline is quoted from the notice for you to verify.

**Research.** The cover letter's research now records what it covered, when, and which federal circuit governs. Choose the circuit under **Where the case is decided** on the matter's first screen. A research check more than a week old is listed when you approve.

**Protected matters.** The folder keeps a neutral name in Finder, and the app shows the name you gave the matter.

**Privacy.** The check that keeps client details out of research now also covers commands that reach the internet and Claude's built-in browser. During a build, Claude's agents can't upload a file or use another connector, such as email or a shared drive.

**Your Mac stays awake during a build,** for up to six hours. Closing the lid still interrupts it.

**Updates.** New installs leave automatic updates off. To update, choose **Help** and press **Ask Claude to do it** next to "To get the newest version". If you installed before 1.3.0, automatic updates stay on until you ask Claude to turn them off.

## 1.2.0 (October 2026)

**Senior Associate is now Immigration Packet Builder.** Only the name changed. You still open it with `/matters`; the install name (`senior-associate`) and the GitHub address stay the same, so it keeps updating as before.

## 1.1.0 (October 2026)

**A redesigned app.** Every screen has the same header, with Passim's wordmark and Matters, Your details, Setup and Help, and a way back at the top left. It follows Claude's light or dark theme, and every button is Claude's own, clickable all over.

**A matter is now tabs:** Overview, Documents, Questions, Packet, Memo & request, Timeline.
- **Overview** leads with the next step and its main action, then the numbers (documents, steps done, what's needed before filing), what needs your attention beside the box for asking Claude, and folded sections for your instructions, more you can do, and the matter's details.
- **Questions** holds Claude's questions, each with a suggested approach and a box for your answer, then **Update the packet with saved answers**.
- **Memo & request** shows the attorney memo and the client request right in the app, with Copy beside each.

## 1.0.0 (October 2026)

The first public release, free under the PolyForm Shield License 1.0.0.

**What it does.** You name the client and the case and add their documents. Claude reviews the documents, prepares the USCIS forms, drafts and researches the cover letter, assembles the packet, and reads it the way a USCIS officer would. You get the packet (or a draft with placeholders for what's still missing), the cover letter in Word and PDF, the filled forms, a memo, a client request ready to email, a filing checklist, and a list of open items. Nothing is guessed, filed or sent.

**Case types.** I-130/I-485 and the I-130 alone; I-751, joint or with a waiver (including battery or extreme cruelty); N-400; I-765; I-131; I-129F; the I-612, I-601A and I-601 waivers; the EB-2 national interest waiver and other I-140/I-485 employment cases; VAWA self-petitions, alone or with the I-485; the T and U visas and adjustment based on them. You can also describe a case that isn't on the list.

**The app.** Type `/matters` in the Claude desktop app's Code tab, beside the chat or in it.
- **A sample matter** to try first: a fictional I-601A with gaps planted for a document review to catch, and a guide comparing what Claude found with what it should.
- **Review documents first** (5–10 minutes) or **Build packet** (about an hour, in the background, with a notification when it's done).
- **Answer Claude's questions** on the matter page, then **Update the packet**. **Ask Claude about this matter** in the chat, with case-law research when BIA Edge is connected. **Redo a step**, **Change what is being filed**, take a document out and put it back, mark a matter filed, archive it, and see its timeline. Nothing you do is lost.

**Forms and filing.** Current editions only, each answer traced to a document, and an audit of every filled form before it goes in the packet. Paper or online filing, with each form sent the way USCIS takes it; the fees from the current fee schedule, with a payment form for each; the filing address from USCIS's current page; and, online, the upload files with a map of where each goes.

**Research and review.** The cover letter cites verified authorities, checked for later treatment through the BIA Edge connector. A final review reads the finished packet the way a strict officer would and names the strongest objection, with its cure.

**Privacy.** Matter folders stay on your Mac, and Claude works on them under your own Claude account. A build sends research only legal questions, never your client's facts. Protected matters (8 U.S.C. 1367) keep the case out of folder names and client requests, and use the safe mailing address throughout.

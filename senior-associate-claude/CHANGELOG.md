# What's new in Immigration Packet Builder

Your version appears at the foot of every Immigration Packet Builder screen ("Help · Immigration Packet Builder 1.3.0"). After an update, quit Claude with ⌘Q and reopen it.

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

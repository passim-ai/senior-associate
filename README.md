# Immigration Packet Builder

Immigration Packet Builder turns a client's documents into a USCIS filing packet. It works inside the Claude desktop app: you name the client and the case and add their documents. Claude then reviews them, prepares the forms, writes and researches the cover letter, assembles the packet, and checks it the way a USCIS officer would.

It was called Senior Associate until version 1.2.0. The plugin's install name (`senior-associate`) and this repository's address haven't changed, so installs made under the old name keep updating.

This project contains both clients: [`senior-associate-claude`](senior-associate-claude/) and [`senior-associate-chatgpt`](senior-associate-chatgpt/). The ChatGPT adapter builds against the Claude folder's shared Python engine, so fixes are packaged together rather than maintained in two engine copies. Its interface and host integration remain separate. See [building and testing both plugins](docs/both-plugins-2026-11-09.md). The install instructions below are for Claude.

For each matter you get:

- **The packet**: one PDF, ready to sign and file. While anything is still needed before filing, you get a **draft packet** instead, with placeholders for the missing pieces.
- **The cover letter** (Word and PDF) and **the filled USCIS forms**.
- **A memo for you**: the bottom line, what's needed before filing, and the strongest objection an officer could raise.
- **A client request**: a plain-English list of what to ask the client for, ready to paste into an email.
- **A filing checklist** to print: the fees and a payment form for each (USCIS no longer takes checks), who signs what, photos, the medical exam, and where to send it.

Nothing is guessed, filed or sent. If the documents don't support an answer, Claude leaves it blank and adds it to the list of open items.

## Before you start

You need:

- **A Mac.**
- **The Claude desktop app** ([claude.com/download](https://claude.com/download)), signed in on a paid Claude plan. You'll use its **Code** tab.
- **About 15–20 minutes**, mostly waiting while things download.

You won't need Terminal. Claude does the installing.

## Install

1. **Open the Claude app and click Code.** When it asks for a folder, choose any folder, such as Documents.
2. **Copy the message below** (the copy button is at its top right), **paste it into the chat, and press Return.**

   ```
   Please install the Immigration Packet Builder plugin on this Mac. Do every step yourself and don't ask me to use Terminal. Tell me whenever I need to click or type something, and wait for me.

   1. If `xcode-select -p` fails, run `xcode-select --install` and wait while I finish the window that opens.
   2. If Homebrew isn't installed: on Apple Silicon, download Homebrew.pkg from the latest release at github.com/Homebrew/brew/releases and open it for me; on an Intel Mac, open Homebrew's official install command in a Terminal window for me, because it asks for my Mac password there. Then add Homebrew's `brew shellenv` line to ~/.zprofile.
   3. Install the tools: brew install uv ghostscript poppler
   4. Create the folder ~/Matters.
   5. Install the plugin with the copy of Claude's command-line tool inside the Claude app (the newest "$HOME/Library/Application Support/Claude/claude-code/*/*/claude.app/Contents/MacOS/claude"): run `plugin marketplace add passim-ai/senior-associate`, then `plugin install senior-associate@document-automation --config matters_root="$HOME/Matters"`.
   6. Leave automatic updates off with the plugin's own script, never by editing ~/.claude/settings.json: run `uv run --script "$HOME/.claude/plugins/marketplaces/document-automation/senior-associate-claude/skills/setup/scripts/auto_update.py" off`.
   7. Tell me to quit Claude with ⌘Q, open it again, and type /matters.
   ```

3. **Follow along in the chat.** Claude asks before each command it runs: choose **Allow**. Along the way, Claude may ask you to:
   - click **Install** in a macOS window for Apple's command line tools;
   - click through the Homebrew installer and enter your Mac password when macOS asks;

   Claude skips anything that's already on your Mac. If something goes wrong partway, paste the same message again and Claude picks up from there.
4. **Quit Claude with ⌘Q and open it again** when Claude says it's done. Closing the window isn't enough: Claude finds Immigration Packet Builder only when it starts.
5. **Open the Code tab in your Matters folder.** Under the prompt box, click the folder control. Press ⇧⌘G, type `~/Matters`, press Return, then click **Open**. Choose this folder whenever you work with Immigration Packet Builder.

## First steps

1. **In the Code tab, type `/matters` and press Return.** Immigration Packet Builder opens. Choose **Open as side panel** to keep it beside your chat while Claude works.
2. **Getting set up** appears the first time. It checks each tool and marks it ✓ or ✗. For a ✗, press **Ask Claude to do it**: Claude installs it in the chat. Then press **Check again**. Rows marked ○ are optional.
3. **Try the sample matter, if you like.** Your list starts with *Sample - Barrientos-Eckhardt*, a fictional I-601A with gaps planted on purpose. Press **Open the sample matter**, then **Review documents first**: in about 5–10 minutes Claude lists what's missing, and the page then shows what a good review catches, so you can compare. It uses your Claude plan like any matter. Archive it when you're done.
4. **Add your details** (2 minutes, once): your name, firm, address, bar number and licensing authority. They go on the G-28 and on the letter's signature.
5. **Start the first matter.**
   - Type the client's name, choose what is being filed and whether it's a new filing or a response, and press **Create matter**.
   - Add the client's documents with **Add files…** or **Add a folder…**. Immigration Packet Builder copies them into the matter; your originals stay where they were.
   - The first time, macOS may ask whether Claude can control System Events. Choose **OK**; that's what lets the file picker open in front.
6. **Press Review documents first.** In about 5–10 minutes you see what's there, what's missing, and a client request you can copy into an email. When you're ready, press **Build packet**.

Type `/matters` any time to come back. **Help**, at the foot of every screen, explains each status and what to do if something goes wrong.

## What to expect

- **How long it takes.** A document review takes about 5–10 minutes. A full build takes about 1–1½ hours. Each button shows its estimate.
- **Builds run in the background.** Keep Claude open, and your Mac awake, until the build finishes. Meanwhile you can use Claude for other things. The matter page shows which step Claude is on and about how long is left, and you get a notification when it's done.
- **Nothing is filed or sent.** You get a draft to read. You decide what to file and what to send the client.
- **When Claude needs your answer,** the matter says **Needs your answer** and lists short questions. Claude's recommendation appears under a question when it has one. Answer what you can, then press **Update the packet**. Anything you leave blank stays on the list for later.
- **When the client sends more documents,** add them to the matter and press **Update the packet**. Claude works them in and checks the packet again.
- **Where your files are.** The packet, letter, forms, memo and client request are on the matter page, and in the matter's folder in Finder.
- **Usage.** A full build is a lot of work for Claude, and it counts toward your Claude plan's usage limits. A build can stop partway, for example at a usage limit or after a dropped connection. Everything finished before that point is saved. Open the matter and press **Try again** to pick up where it stopped.

## Permission prompts

Claude asks before it runs some commands, and the build waits until you answer. While it waits, the matter page says **Claude is waiting for your OK in the chat**. Answer in the chat.

To stop the same question from coming back on later builds, choose **Yes, and don't ask again**. Claude remembers that answer for your Matters folder, which is one more reason to always choose that folder in the Code tab.

In **Auto** mode (chosen under the prompt box), Claude can't start a build from the matter page by itself. The page puts the request in your chat box instead. Press Return to send it. The page then switches to **Claude is working** on its own.

## Case-law research (BIA Edge)

Immigration Packet Builder finds case law for the cover letter through the **BIA Edge** connector in your Claude account. To connect it once:

1. In the Claude app, click **Customize** in the sidebar and open **Connectors**. You can also go to [claude.ai/customize/connectors](https://claude.ai/customize/connectors).
2. Add BIA Edge. On Team and Enterprise plans, an admin adds connectors.

Code tab sessions signed in with the same Claude account can then use it. A build sends BIA Edge legal questions, never client documents, names or identifying details. When you talk a matter through with Claude, it includes your client's facts in a research question only when you ask it to; that's your call.

Without BIA Edge, the cover letter still cites the statute, the regulations, the USCIS Policy Manual and the precedents in Immigration Packet Builder's own reference files. Claude adds other case law only with your approval, as an item to check before filing.

## Ask Claude to change things

Anything else about the setup is a request to Claude in the Code tab. For example:

- **"Use my firm's model letters with Immigration Packet Builder."** Claude asks where your cover letters (.docx) are and sets them up. The letter then follows the closest one; without model letters, it uses a standard letter format.
- **"Change my Immigration Packet Builder Matters folder."** Use a new or empty folder, not your existing client-files folder: every folder inside it would show up as a matter.
- **"Install LibreOffice for Immigration Packet Builder."** Optional: it makes the cover letter's PDF match the Word version exactly.
- **"Update Immigration Packet Builder to the newest version."**

Immigration Packet Builder's own screens have an **Ask Claude to do it** button wherever Claude can fix something, so you rarely need to type these.

## Updates

New installations leave automatic updates off. Updates are downloaded into a separate candidate folder, checked, and tried with a synthetic matter before activation. Existing installations keep their settings until you change them. Finish active builds before switching versions. Your version appears at the foot of every Immigration Packet Builder screen, for example "Help · Immigration Packet Builder 1.0.0", and what changed in each version is in the [CHANGELOG](senior-associate-claude/CHANGELOG.md).

To update right away, choose **Help** in Immigration Packet Builder and press **Ask Claude to do it** next to "To get the newest version". Then quit Claude with ⌘Q and reopen it.

## Troubleshooting

- **`/matters` doesn't appear.** Quit Claude with ⌘Q and reopen it. If it's still missing, paste the install message again: Claude checks each step and finishes whatever isn't done.
- **A tool still shows ✗ after Claude installed it.** Press **Check again**. If it still shows ✗, quit Claude with ⌘Q, reopen it, type `/matters`, and choose **Help › Check my setup**.
- **The file picker doesn't open.** Open System Settings › Privacy & Security › Automation › Claude, turn on System Events, and try again.
- **A build stopped.** Open the matter and press **Try again**. It picks up where it stopped.
- **Anything else:** ask Claude in the Code tab, or [open an issue](https://github.com/passim-ai/senior-associate/issues).

The full guide, including what each status means and how your clients' documents are protected, is in [senior-associate-claude/README.md](senior-associate-claude/README.md).

## License

Immigration Packet Builder is free under the [PolyForm Shield License 1.0.0](LICENSE). You may use, change and share it for any purpose, including in a commercial law practice, except to build a product that competes with it. Copyright 2026 Passim AI.

It is a drafting aid, not legal advice. Nothing is filed or sent for you, and your attorneys review and approve all of its work before it is relied on, sent or filed. As the license says, it comes as is, without any warranty.

## Reliability and data handling

See [data handling and limits](senior-associate-claude/docs/DATA-HANDLING.md), [verification procedure](senior-associate-claude/docs/VERIFICATION.md), [the local evaluation](docs/implementation-2026-11-09.md), and [the fixes made to it](docs/fixes-2026-11-09.md). A completed review packet is a draft. Attorney approval binds the filing export to the reviewed version; substantive changes require review and approval again.

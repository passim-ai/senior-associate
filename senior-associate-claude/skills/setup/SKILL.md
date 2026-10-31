---
name: setup
description: Sets up Senior Associate on the attorney's Mac from inside the Claude app, so the attorney never opens Terminal. It installs the tools Senior Associate uses (Homebrew, uv, Ghostscript, Poppler, LibreOffice), changes the Matters folder or the model letters folder, turns automatic updates on, and updates Senior Associate. Use when the attorney asks to set up, fix or update Senior Associate, install one of its tools, change either folder, or turn on automatic updates, or when the Senior Associate app asks Claude to.
---

# Setting up Senior Associate

The attorney works only in the Claude app and may never have used Terminal. Do every step yourself with your own tools. Never ask them to open Terminal, paste a command, or type a password in the chat. When a step needs them (a macOS window asking for their Mac password, a code to enter on github.com, quitting Claude), tell them exactly what they'll see and what to click, then wait for them to say it's done.

Start with one line on what you're about to do, and that Claude asks before each command it runs: they should choose **Allow**. End with two or three plain sentences: what you installed or changed, and the one thing left for them to do, if any. Don't show commands or file paths unless they ask.

`<plugin root>` below is `${CLAUDE_PLUGIN_ROOT}`.

## The tools

| Tool | Needed? | What it does |
| --- | --- | --- |
| uv | required | runs Senior Associate's tools |
| Ghostscript (`gs`) | required | prints the filled USCIS forms |
| Poppler (`pdftotext`) | optional | reads the text in PDFs more quickly |
| LibreOffice (`soffice`) | optional | makes the cover letter's PDF match Word exactly (a large download, about 350 MB: install it only when asked) |

Look for each in `PATH` and in `/opt/homebrew/bin`, `/usr/local/bin` and `~/.local/bin`. Install only what's missing or what the attorney asked for, in this order:

1. **Apple's command line tools** (Homebrew needs them). If `xcode-select -p` fails, run `xcode-select --install`. Tell the attorney: "A macOS window asks to install the command line developer tools. Click **Install**, then **Agree**. It takes 5–15 minutes; tell me when it says the software was installed." Confirm with `xcode-select -p`.
2. **Homebrew**, when neither `/opt/homebrew/bin/brew` nor `/usr/local/bin/brew` exists.
   - On Apple Silicon (`uname -m` prints `arm64`), use Homebrew's installer package. Read the newest release from `https://api.github.com/repos/Homebrew/brew/releases/latest`, download its `.pkg` asset to `~/Downloads` with `curl -fL`, and `open` it. Tell the attorney: "The Homebrew installer opened. Click **Continue**, **Continue**, **Agree** and **Install**, enter your Mac password when macOS asks, then click **Close**. Tell me when it's done."
   - On an Intel Mac there's no installer package. Open the official installer in a Terminal window for them, because it asks for the Mac password there: `osascript -e 'tell application "Terminal" to do script "/bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""'`. Tell them: "A window opened that asks for your Mac password. Type it (nothing shows as you type) and press Return, then press Return again when it asks. When it says Installation successful, close the window and tell me."
   - Then make it findable: if `~/.zprofile` doesn't already mention `brew shellenv`, add `eval "$(/opt/homebrew/bin/brew shellenv)"` (`/usr/local/bin/brew` on Intel).
3. **The tools themselves**, with Homebrew's full path, for example `/opt/homebrew/bin/brew install uv ghostscript poppler`. LibreOffice is `brew install --cask libreoffice`. Allow up to 10 minutes for each install.
4. **Check** each one by running it (`gs --version`, `uv --version`, `pdftotext -v`) with its full path.

Never run `sudo`: it can't ask for a password here. Homebrew installs without it once Homebrew itself is installed.

## Claude's plugin settings

The desktop app carries Claude's command-line tool. Run it with `sh "<plugin root>/skills/setup/scripts/claude-cli.sh" <arguments>` (called `claude-cli` below).

The two folders are the plugin's settings. Right now the Matters folder is `${user_config.matters_root}` and the model letters folder is `${user_config.exemplars_dir}` (empty, or shown as the placeholder itself, when none is set). Installing with `--config` sets the settings it names, so **always pass both**, the one being changed and the other one as it is now, or installing to change one folder resets the other:

- **Install, or install again:** `claude-cli plugin marketplace add passim-ai/senior-associate`, then `claude-cli plugin install senior-associate@document-automation --config matters_root="<Matters folder>" --config exemplars_dir="<model letters folder, or the current one>"`, then turn automatic updates on (below). Leave out `exemplars_dir` only when there has never been one.
- **The Matters folder.** If the attorney didn't say which folder, suggest `~/Matters` and ask once. Use a new or empty folder. Refuse their home folder, Documents, Desktop, Downloads, or an existing client-files folder: every folder inside it would show up as a matter. Create it (`mkdir -p`), then run `claude-cli plugin install senior-associate@document-automation --config matters_root="<absolute path>" --config exemplars_dir="${user_config.exemplars_dir}"` (leave out the second when it's empty). Matters already in the old folder stay there; offer to move them only if the attorney asks.
- **Model letters.** Ask where their cover letters (.docx) are if they didn't say, and check that the folder holds at least one .docx. Then run `claude-cli plugin install senior-associate@document-automation --config exemplars_dir="<absolute path>" --config matters_root="${user_config.matters_root}"`.
- **Automatic updates:** `uv run --script "<plugin root>/skills/setup/scripts/auto_update.py" on` (or `off`, or `status`). It's the only thing that changes Claude's `settings.json` for Senior Associate: never edit that file by hand, because a mistake in it can stop Claude from starting. If `auto_update.py` says the file has a mistake in it, tell the attorney in a line and offer to look at it with them; don't rewrite it.
- **Update now:** `claude-cli plugin marketplace update document-automation`, then `claude-cli plugin update senior-associate@document-automation`.

The installed version is in `<plugin root>/.claude-plugin/plugin.json`.

## When you're done

- After installing Senior Associate, updating it, or changing a folder, Claude has to restart to pick it up. Tell the attorney: "Quit Claude with ⌘Q (closing the window isn't enough), open it again, and type /matters."
- After installing only a tool, no restart is needed: tell them to press **Check again** in Senior Associate.

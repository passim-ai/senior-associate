# Release 1.3.0: what was tested, and what was not

Recorded November 10, 2026, as `senior-associate-claude/docs/VERIFICATION.md` asks. Everything here used fictional documents. No client matter was opened, and the installed plugin on the test Mac was left as it was.

## Result

A full build of the plugin's sample matter passed all 10 steps on the release candidate, in the desktop app's own engine. The approval steps then worked on that build's output. The build also showed one more defect in the tool gate, which was fixed, reviewed, fixed again more narrowly, and probed in the engine before release.

The panel itself was not used in the desktop app. That is the main thing still untested.

## What ran

| Item | Value |
|---|---|
| Engine | The Claude desktop app's bundled engine, 2.1.317, run headless (`claude -p`) with the candidate loaded by `--plugin-dir` and the installed copy switched off for that process |
| Permission mode | auto |
| Session model | claude-opus-5-5 (the account's default; each agent's own model setting applied) |
| Matter | The sample the plugin ships: *Sample - Barrientos-Eckhardt*, a fictional I-601A with 14 specimen documents and planted gaps |
| Matters folder | A new, separate folder, set through `pluginConfigs` so the candidate never read the Mac's real one |
| Attorney profile | Made up |
| Research | The BIA Edge connector and web fetch, as an attorney's build would have them |
| How it was started | As the app starts a build from the chat box: `start_run` for the lease and the brief, the lease renewed every 45 seconds, then the brief given to the `senior-associate:senior-associate` agent |
| Mac | macOS 27.2, uv 0.13.5, Python 3.12.12, Ghostscript 10.06.0, Poppler 26.10.0, LibreOffice 26.2.0.3, Node 26.12.1 |

Commits: the build ran on `1858375`. The approval steps ran on `04521a3`. The last gate probe and the last full test run used `93d5931`. Between `1858375` and `93d5931` the changes are the tool gate's reading of shell commands, the rule for retiring packets, and the test workflow's runner. The released commit adds only this record.

## The build

| Measure | Result |
|---|---|
| Steps | 10 of 10 passed |
| Time | 68 minutes |
| Agents | 17 started, each of the plugin's nine types at least once |
| Reports handed back | 17 of 17 delivered |
| Shell commands | 398 |
| Research calls | 12 web fetches, 35 BIA Edge calls |
| Permission refusals in auto mode | 0 |
| Tokens | 111.9 million, of which 106.0 million were cache reads |
| Cost the engine reported | $32.98 at API prices |
| Delivered | A 73-page packet, the cover letter in Word and PDF, four forms (I-601A, G-28, G-1145, G-1450), the memo, the client request, the filing checklist, 28 open items (12 needed before filing) |

The packet's review copy carries the DRAFT line on all 73 pages, each 20 points taller than the clean page. The clean copy carries it on none. Both have 21 bookmarks.

The document review raised 7 of the sample's 8 planted gaps. It did not raise the missing proof of the wife's U.S. citizenship, in the open items or in the memo. The memo ran to 2,250 words.

### What the gate refused

Three calls out of about 445 that it screens.

| Call | Refused because | Right? |
|---|---|---|
| A BIA Edge search for "Lopez-Meza moral turpitude…" | "Lopez" is the surname of the client's mother | By the rule, yes; in effect, no. *Matter of Lopez-Meza* is a precedent. The agent searched again in other words and went on. See "Known limits". |
| A shell command writing a Python file of source addresses with `cat` | The check reads an address anywhere in a command as reaching the network, and the file named the client | No. Fixed in `93d5931`: text a command only writes down is left out. |
| A shell command writing the review memo with `cat` | The memo said the packet goes "by mail", and `mail` is a program that connects | No. Fixed in `93d5931`, the same way. |

In both false refusals the agent wrote the file another way and the step passed.

## Approval, on the build's output

Run through the app's local helper, which is what the Packet tab calls.

| Step | Result |
|---|---|
| The approval section for the finished draft | Can be approved; 13 open points listed in plain words (12 items needed before filing, the officer's review expecting rejection at intake, nine review notes of which six are shown, three form-check errors, an incomplete research check) |
| Approve with no reason | Refused: "Explain your decision to file with these points open, then approve." |
| Approve from a page drawn for another version | Refused: "The matter changed since this page was drawn." |
| Approve with a reason | Approved. The record keeps the attorney, the time, the version, the 13 points and the reason, and covers 22 files. |
| The approved copy | 73 pages, no DRAFT line, original page height, 21 bookmarks, named `Filing Packet.pdf` |
| A new client document arrives | The approval no longer applies, and the page says the review did not cover this version |
| The document is taken out again | Approved again, same version |
| An answer is saved and the memo is rewritten | Still approved |
| The cover letter is edited, then rendered again | The edited letter is kept in `Your edited copies`, the tool says so, and a new letter is written |
| The packet is marked up, then assembled again | Said on the approval page; on assembly the marked-up packet is kept in `Your edited copies` |
| The handoff drops "(DRAFT)" from the packet's name and it is then marked up | Still found, said as changed, and approved with a reason; a second approved copy is written beside the first |

## Probes of the tool gate in the engine

Each started one of the plugin's agents on the sample matter while a run held it.

| Probe | Commit | Result |
|---|---|---|
| 1 | `c241852` | Failed. The agent's report was refused three times: `SubagentHandback` was on no list of allowed tools. This would have stopped every build. |
| 2 | `1858375` | The agent loaded its skill, ran a compound local command, fetched a public page (200), and handed back its report. A second agent's legal search and a fetch of a USCIS page went through; its search naming the client was refused. |
| 3 | `04521a3` | Passed, on a first version of the fix that was then replaced (see "Independent review"). |
| 4 | `93d5931` | A memo naming the client and saying "by mail" was written with `cat`; a Python file of source addresses naming the client was written with `cat` and run; `[ -f page ] \|\| curl …` fetched (200); a search naming the client's wife was refused; a search for *Matter of Cervantes-Gonzalez* went through; the report was handed back. |

In probe 2 the agent itself declined two commands it was asked to run, one sending the client's name to a website and one uploading a client document, so the gate's refusal of those was not seen in the engine. The app tests cover both.

## Test suites

- `UV_PYTHON=3.12 bash scripts/check-plugins.sh` on `93d5931`: all 30 Claude suites (27 Python suites, the app tests, plugin and marketplace validation), 6 transport tests, 29 ChatGPT adapter tests, the lifecycle test through both real transports, 13 browser scenarios.
- The app tests (148) pass under engine 2.1.317.
- The build's own 398 shell commands were replayed through the final rule: the 3 false network readings are gone and no other command reads differently.
- GitHub Actions ran this workflow for the first time on this branch. Every earlier run, back to 1.0.0, was cancelled within seconds because the `macos-14` runner image was being retired; it now runs on `macos-15`.

## Independent review

GPT-6 Astra (high) reviewed `c241852`, then `1858375`, then `04521a3`. The first two rounds found ten defects, all fixed; `docs/fixes-2026-11-09.md` lists them.

The third round was on the first fix for the false refusals above, which read a command's network reach from the programs it ran. Astra found nine ways that reading missed a real request (inside a process substitution or an unquoted here-document, launched from inline Python, behind `env -i`, after a comment with an apostrophe, inside `bash -c`) and one pattern that could take minutes on a long address. That design was dropped. `93d5931` goes back to the broad reading the first two rounds covered and leaves out one thing only: the body of a here-document that a command writes down with `cat`, `tee` or a plain filter. That narrower change was not reviewed by Astra again.

## Not tested

- **The panel in the desktop app.** No screen was opened or pressed with this candidate. The Overview, the Packet tab's approval section, the circuit choice and the protected-matter names are covered by the app tests alone, which draw each screen against what the real helper sends.
- **A build started by the app's own button.** The trial started the build the way the chat box does.
- **The default permission mode.** The build ran in auto mode. Nobody has counted the prompts a build raises in default mode.
- **Case types other than the I-601A,** online and split filings, protected matters, RFE and NOID responses, and a name the form's font cannot print, in a real build. The Python and app tests cover them.
- **A matter built by 1.2.0 and rebuilt by 1.3.0.** The tests cover the kept copies; no such rebuild was run.
- **The ChatGPT adapter in ChatGPT.** Its tests and browser scenarios pass; it was not loaded in the ChatGPT app.
- **Legal accuracy.** Nobody checked the letter's law or the forms' answers beyond what the build's own reviewers did.

## Known limits seen in the trial

- A precedent cited by a short name that is also a party's surname is refused ("Lopez-Meza" when a party is named López). Writing "Matter of Lopez-Meza" passes.
- A shell command that names an address, or a word such as `mail` or `ssh`, outside a file it is writing is still read as reaching the network, and is refused if it also names the client. Inline Python that builds a record with source addresses and the client's name is the likely case; the agent then writes the file with the Write tool instead.
- Text written down inside a shell function or group that is later piped to a shell is not read. The gate is a safeguard against a slip, not against a command built to get round it.
- First names and titles read from the documents become terms too ("Rev", from "Rev. Julián Arreola"), so a search containing one as a whole word is refused.
- A build of the sample cost about three times the 35 to 43 million tokens measured for builds under versions 0.2.4 to 0.9. The earlier figures may not have counted cache reads the same way, so the two are not a like-for-like comparison.

## Reproducing the trial

1. Check out the candidate in its own folder, and make an empty Matters folder.
2. `uv run --script <candidate>/senior-associate-claude/server/cli.py '{"op":"add_sample","matters_root":"<folder>"}'`, then `save_profile`.
3. `start_run` with `"kind":"build"`: keep its `run_id`, renew it with `heartbeat_run` every 45 seconds, and give its `prompt` to the agent.
4. Run the desktop app's bundled `claude -p --plugin-dir <candidate>/senior-associate-claude --permission-mode auto --output-format stream-json --verbose`, with `--settings` turning the installed copy off (`enabledPlugins`) and setting `pluginConfigs."senior-associate@inline".options.matters_root` to the folder. Without that setting the candidate reads `~/Matters`.
5. `release_run` when it ends, then `state` and `approve_filing` for the approval steps.

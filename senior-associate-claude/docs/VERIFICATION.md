# Verification and release procedure

Run `scripts/check.sh` from the plugin folder. It runs Python suites, Claude host app tests, and plugin/marketplace validation. `--quick` skips the host checks. Every dependency-bearing PEP 723 script has a committed adjacent `.py.lock` with versions, registry URLs, and package hashes. `uv run --locked --script path.py ...` refuses changed dependency metadata; the test runner uses it for locked suites. Refresh a lock deliberately with `uv lock --script path.py`, then rerun affected suites. Runtime scripts automatically use their adjacent lock. OS utilities (Ghostscript, Poppler, LibreOffice) remain system dependencies; record their versions with evaluation results.

The setup staging tool creates a new candidate directory, records its exact commit, and checks it without changing the installed plugin. A successful command-line check is not desktop acceptance. Complete or pause active matters, run the desktop check below, then activate the same checked candidate. Keep the previous version and matter backup. Rollback means reselecting that version and reviewing any matter files written by the newer version; never delete evidence to make a rollback appear clean.

On macOS app-started runs hold an idle-sleep assertion only while their existing lease remains fresh, with a six-hour maximum. The watcher does not renew or restart work. Closing the lid, forced sleep, power loss, or an expired lease can still interrupt work. Resume using the saved stage/lease controls and recheck affected output; do not infer successful completion from an elapsed timer.

## Desktop acceptance with synthetic documents

1. Load the candidate in an isolated Claude desktop session with a temporary Matters folder; do not use a client matter.
2. Start a fictional build and observe actual `tool.call` / `tool.check` events. Test both hook events with a nested research call containing a short name, a common name, an encoded name, an identifying number inside a citation, and an opaque connector. Confirm refusals happen before the underlying tool executes. Check ordinary legal research and the shipped local tools still work.
3. Finish a synthetic packet. Check draft markings visually on every page size/orientation and preserve originals. Leave a critical review finding and a filing blocker: the blocker must prevent approval. Resolve procedural gaps, acknowledge the merits risk with a reason, and approve through the Packet screen.
4. Open the approved export, verify its content and absence of draft markings, change a source or form, and confirm the prior approval is stale.
5. Edit a generated Word/PDF deliverable, rebuild, and confirm the edit survives. Exercise an unsupported Unicode name and confirm an actionable stop; compare the rendered supported name to the source.
6. Stop/resume a build and inspect sleep assertion release. Stage an update without activating it; verify installed version and client folders are unchanged.

Publish the exact candidate commit, host/tool versions, commands, fixture scope, passed/failed counts, and untested paths with each release. Synthetic regression results do not measure real-case legal accuracy, model cost, or end-to-end reliability. Keep those evaluations separate and report failed runs too.

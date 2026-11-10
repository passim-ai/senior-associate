# Candidate verification — 2026-11-09

The 0.2.1 source candidate is now maintained alongside the Claude plugin in Passim Packet Builder. It imports the current shared engine at build time. Run the repository's `scripts/check-plugins.sh` for both clients. The combined tests cover the actual Claude CLI and ChatGPT stdio transport, browser UI, version-bound approval, clean PDF export, source mutation, privacy refusals, and packaged file hashes. Stage content in the lifecycle/browser fixtures is deterministic fictional data, not a model-authored legal packet.

This candidate has not replaced either installed plugin. The browser protocol host is a test fixture, not ChatGPT. Native desktop loading, hook trust/execution, actual widget-to-chat handoff, file pickers, and a full model-driven packet build in each desktop app remain separate acceptance requirements. Do not rely on the older installed package's behavior as proof of this candidate. Historical verification below applies only to its named versions.

The shared data-handling document is packaged as `SHARED-DATA-HANDLING.md`. Claude-specific host guarantees and installation instructions do not apply to ChatGPT; the adapter's exact-input checker and the limits in `CHATGPT-RUNTIME.md` govern here.

---

# Desktop adapter verification — 2026-10-31

Current UI release: **0.2.0**. See [UI redesign](UI-REDESIGN.md) for the visual changes and 11 passing browser checks. The underlying fictional-matter workflow below was exercised on 0.1.2 and is retained as historical evidence.

Version 0.1.2, built on Senior Associate Claude 0.9.1 with the scoped intake fixes below. Branch: `codex/chatgpt-matters`.

## Installed and exercised

Installed with the desktop-bundled CLI. Active registration is `senior-associate-chatgpt@personal`, installed in `~/.codex/plugins/cache/personal/senior-associate-chatgpt/0.1.2`. The separate `senior-associate-chatgpt-local` registration is disabled to avoid duplicate tools. The existing Personal BIA Edge entry and installed Claude plugin are preserved. No real client matter was used.

The actual installed MCP stdio server (no mocked transport) created the bundled fictional sample, reserved a document-review run, and returned the exact run brief. The orchestrator adopted that lease; an independent specialist reviewed all 14 scanned source files / 17 pages, retrieved six official sources through the research gate, produced substantive review artifacts, and passed the runtime's docs_review validator. The original files retained identical SHA-256 hashes.

The handoff includes an attorney memo and client request in Markdown/PDF. Their rendered pages were visually inspected. A clearly labeled fictional answer to the marriage-date question was saved through MCP, survived a new request and installed-package replacement, and was included in the resumed brief. The scoped resume resolved that item and refreshed the handoff. Current state is **Documents reviewed**, 19 open items / 11 blocking; no stage running, leases released. Forms and packet stages were not run or marked passed. This is not a filing-ready packet.

Detailed receipts and the sample outputs are retained under `artifacts/acceptance-2026-10-31/` (ignored local test evidence). `final-status.json` and `final-app-view.json` show the installed-server result, not a screenshot of ChatGPT.

## Fixes and automated checks

- I-601A now supplies G-28 and I-601A defaults, and provisional-waiver evidence categories. Words such as spouse/family no longer create a new I-130 or financial-sponsorship requirement for that matter type. Generic waiver language no longer assigns I-751 conditional-residence evidence.
- ChatGPT's view reads its own package version instead of reporting the shared Claude engine's version.
- The package includes the documented default hook file and a compatibility manifest. This is packaging compatibility only; hook discovery remains unresolved below.
- 216 shared workflow/server regression tests passed after the intake fix (214 existing plus 2 new). Pre-existing unclosed-pipe ResourceWarnings remain.
- 25 adapter/package/MCP tests passed against the updated build, including shared-source hash checks, lease exclusion, concurrent starts, saved answers, path confinement and exact-input research checks.
- For UI release 0.2.0: 6 JavaScript transport tests, 25 adapter/package tests, and 11 browser scenarios passed; desktop, narrow-panel, and dark-theme renders were inspected. The browser host fixture is not ChatGPT.

## Remaining host acceptance blockers

The user reported that the plugin was not visible after CLI-source installation. It has since been added to the existing Personal catalog and installed from there; the user confirmed that it is still not visible after refreshing Personal. A full app restart/new local chat remains unverified. Computer use refuses control of the ChatGPT application's own native interface. The permitted MCP Apps panel inventory is empty. The current chat has not exposed the newly installed tools. No alternate UI-control mechanism was used to bypass that boundary.

The desktop's read-only `plugin/read` and `hooks/list` probes discover the skills/MCP server but return no plugin hooks, including after testing the documented portable/default/compatibility locations. No hook was trusted programmatically and no trust bypass was used. Hook execution is therefore **not verified and must not be relied on**. The explicit exact-input checker was used for every fictional-matter research request. Hosted web requests are outside local hook coverage regardless.

Still unverified: native sidebar/panel visibility, real chat handoff from a widget button, native file pickers/document opening through that widget, and privacy-hook discovery/trust/execution. Consequently the native end-to-end acceptance test remains incomplete despite the installed-server workflow passing.

## Next host check

Refresh Plugins Directory → Personal; if still absent, restart the desktop app and check in a new local chat. Ask “Open Matters.” If the app becomes visible, expand it in the chat panel for the remaining button/picker checks. Investigate hook discovery before relying on that supplemental safeguard. Do not select a real Matters folder as part of this test.

Official packaging/trust references: https://developers.openai.com/plugins/build/plugins and https://learn.chatgpt.com/docs/hooks (checked October 31, 2026).

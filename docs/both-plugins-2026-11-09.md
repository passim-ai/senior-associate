# Both plugin candidates — November 9, 2026

The project now contains the complete ChatGPT adapter source alongside the Claude plugin. The fixes are shared at build time. Automated verification passes for both candidates; native desktop/model-driven acceptance remains incomplete.

## Source and packaging

- Claude engine: this repository's `senior-associate-claude/`, including reliability commit `4a017d8`.
- Imported adapter: all tracked `senior-associate-chatgpt/` files from a separate local checkout (`chatgpt-matters`), commit `9d966b26e0a6ab7a739827c6d9cd3b161670f662`. The original checkout and installed packages were not changed.
- ChatGPT candidate version: **0.2.1**. `build.py` copies the sibling engine and adapts only prompt Markdown. The source folder is not the installable package; the complete build path is recorded in `senior-associate-chatgpt/dist/latest.txt`.
- Each build has its own output directory. `shared-source.json` records hashes for 214 shared source files, including 82 Python files, plus hashes for the packaged contents. Tests compare every shared Python file against the current Claude source and verify every packaged hash.
- Fonts, original adapter documentation, manifests, MCP server, privacy hook, frontend, tests, and the package lock are in this project. Dependency caches and build/test outputs are ignored.

## Ported behavior

The shared package includes version-bound filing approval, dated sensitive-answer confirmation, Unicode/font validation, preservation of edited deliverables, draft markings and clean exports, form consistency checks, legal-currency and jurisdiction requirements, corrected case routing, RFE/NOID response checks, and the existing adversarial regressions.

The ChatGPT-specific changes add the Packet approval/risk controls, approved-copy opening, jurisdiction editing, and “Completed with findings” labels. The adapter owns its compact model-facing summary because that helper no longer exists in the current shared readmodel. The privacy hook screens opaque research connector names, unknown outbound tools, shell networking, short/common names, full names and identifying values inside citation arguments. It reloads the current facts on each request and fails closed when party records are unavailable. Run preparation now starts the shared bounded sleep watcher for the exact lease and reports startup failures.

ChatGPT's explicit research checker remains required. The supplemental hook is not network isolation, and its presence in the package is not evidence that a host discovers, trusts or executes it. Claude-specific host permissions do not transfer automatically to ChatGPT.

## Verification results

| Boundary | Result |
|---|---|
| Claude engine and host harness | All 30 suites passed across the full run and the scoped PDF rerun; includes 137 Claude app tests and plugin/marketplace validation. |
| PDF conversion rerun | 61 tests passed with local LibreOffice access. The sandboxed run had 2 LibreOffice process aborts; all other suites passed. |
| ChatGPT adapter/package/MCP | 29 tests passed against the built package, including actual stdio initialization/resource retrieval, hash parity, privacy, lease behavior, and exact-run sleep watcher wiring. |
| JavaScript transport | 6 tests passed. |
| Browser | 13 scenarios passed in Chrome against the actual bundled UI and Python backend through an MCP Apps protocol fixture. Includes approval reasons, clean-copy action, source-change invalidation, saved jurisdiction, intake/import, questions, handoff cancellation, safe document rendering, dark theme and narrow panels. |
| Both real transports | Claude CLI and ChatGPT stdio each passed create → saved profile/jurisdiction/answer → draft PDF → risk refusal → explicit approval → clean PDF export → changed-source rejection → filed/unfiled and archive/unarchive. Exported text and bookmarks were checked. |
| Shared matter | Each client refused a start while the other held the lease. Wrong-run cancellation preserved ownership; exact-run cancellation released only that reservation. Tested through the real CLI and stdio entry points. |
| Visual review | Inspected the rendered ChatGPT Packet screen, including the separate attorney-filing-review section. Previous shared PDF layout review remains documented in `implementation-2026-11-09.md`. |

The lifecycle and browser tests seed explicitly fictional stage outputs; they do **not** represent a model completing the legal work, establish real-case accuracy, or measure cost. An initial adapter import failure exposed the removed `card_summary` helper and was fixed. Initial lifecycle/browser approval fixtures used an obsolete open-items path; correcting those fixtures produced the passing results above.

Local logs: `/tmp/packet-builder-claude-20261109.log`, `/tmp/packet-builder-pdf-20261109.log`, `/tmp/packet-builder-chatgpt-adapter-20261109.log`, `/tmp/packet-builder-chatgpt-browser-20261109.log`, `/tmp/packet-builder-both-e2e-20261109.log`, and `/tmp/packet-builder-cross-client-20261109.log`. Browser screenshots are ignored local artifacts under `senior-associate-chatgpt/artifacts/`.

## Reproduction

From the repository root, run:

```sh
UV_PYTHON=3.12 bash scripts/check-plugins.sh
```

This installs the locked frontend dependencies, builds a new candidate and runs both plugins' tests. Chrome, uv, Node, and the shared document utilities must be available. `--quick` skips the Claude-specific host checks; it does not skip the ChatGPT browser/transport tests. Use `PLAYWRIGHT_CHANNEL=chromium` after installing Playwright Chromium when Chrome is unavailable. CI now includes packaging, adapter/transport, and browser tests; remote CI has not run because these changes have not been pushed.

## Native desktop acceptance still required

The live desktop check found Claude actively running unrelated work. Its installed plugin and running sessions were preserved. Computer use explicitly refused access to the ChatGPT application's own native interface; the MCP Apps inventory for this chat had no open panel. No alternative mechanism was used to bypass that restriction.

Neither candidate has been installed or released. Native candidate loading, ChatGPT hook discovery/trust/execution, actual widget-to-chat handoff and native pickers, and a full model-driven synthetic packet build in each desktop app remain unverified. Those checks require an isolated host session with a temporary Matters folder and the exact tested candidate. A passing test fixture or existing installed MCP tool is not proof of this candidate's native behavior.

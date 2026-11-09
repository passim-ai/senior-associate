# Packet builder reliability implementation — November 9, 2026

Implemented locally on `codex/packet-builder-reliability-20261109`, based on `01136a8`. This changes the Claude plugin in this project folder. No installed plugin, client matter, release, or external publication was changed.

## Result

| Group | Implemented behavior |
|---|---|
| Readiness and answers | Completed builds remain drafts until explicit attorney approval. Approval records attorney, time, exact source/output/review fingerprint, and reasons for accepting remaining merits risks. Missing/damaged review records, stale review receipts, open filing blockers, or deterministic form-audit errors prevent approval. Sensitive answers require dated, question-specific client confirmation; silence no longer supplies “No.” |
| Privacy and document integrity | Both host hook paths screen research, refuse unknown outbound tools, bind Python calls to the actual plugin root, and screen current facts without a stale cache. Short/common names and identifiers inside citations are covered. Protected matters use neutral new-folder names and notifications. Unicode comparisons retain characters; unsupported glyphs stop filling. Edited generated letters/packets are preserved. Review packets have a separate draft band, retain bookmarks, and export clean versioned filing copies after approval. |
| Legal and case-type correctness | Corrected the identified A-V-O-, Dorcas, and Simantov references with their scope limits and primary sources. Research records source coverage, update-hit disposition, jurisdiction, unresolved treatment questions, and court-order docket checks. Waiver routing uses the requested form rather than generic “waiver” or “spouse” wording. Matter-level forum, circuit, and jurisdiction basis are editable. Unsupported T/U coverage is labeled. |
| Validation and responses | Added relationship exclusivity, birth/marriage/arrival chronology, identifier checks, and same-subject cross-form name comparison. RFE/NOID work has a notice-bound response plan with every ground mapped to an answer/evidence, exact notice hash, quoted deadline, attorney verification, delivery instructions, and missing-request checks. |
| Operations | Added 37 adjacent dependency lockfiles, locked test execution, staged update download/check receipts, new-install auto-update defaults, and a bounded macOS idle-sleep watcher tied to an existing app run. Added data-handling and release-verification documentation. |

## Verification

- **All 30 suites passed** with `UV_CACHE_DIR=/tmp/packet-builder-uv-cache UV_PYTHON=3.12 bash scripts/check.sh` from the plugin folder. This includes 27 Python suites, 137 host app tests, and plugin/marketplace validation. See [verification summary](verification-2026-11-09.txt).
- The final bookmark-preservation adjustment passed the affected **61-test PDF suite** and **20-test adversarial suite** again.
- Adversarial tests cover missing/damaged reviews, stale approvals, explicit risk acknowledgment, unwaivable form-audit errors, changed sources, release tampering, draft/clean export, edited Word files, Unicode fidelity/font refusal, short/common names, form contradictions, waiver routing, legal-currency gaps, notice chronology/mapping, bounded sleep release, and failed staged updates.
- Actual Claude host test hooks exercise both `tool.call` and `tool.check` before the simulated destination executes; the UI test verifies the reviewed digest and attorney risk reason reach the server action.
- Poppler-rendered synthetic portrait, landscape, and rotated pages were visually inspected. The draft marking is outside source content and barcodes; bookmarks remain. Clean filing sources keep the original page dimensions and content. Temporary visual fixtures: `/tmp/packet-builder-visual-20261109/`.
- Earlier runs found and fixed PDF-library compatibility errors and incomplete UI input handling. Older schema fixtures with impossible parent birth dates/all-zero SSNs were corrected. One sandbox run passed 29 suites and aborted in LibreOffice; the complete run with the required LibreOffice access passed all 30. `git diff --check` passed.

Environment: Claude CLI 2.1.304; Python 3.12 for locked verification; uv 0.13.5; Ghostscript 10.06.0; Poppler 26.10.0; LibreOffice 26.2.0.3. Locks select pypdf 7.0.0, ReportLab 5.1.0, python-docx 1.2.0, Pillow 13.0.0, and cryptography 50.0.2 where required.

## Remaining release acceptance

A **full model-driven build in the actual Claude desktop app has not been run with this candidate**. The open desktop app was running unrelated work; its installed plugins/settings were preserved. The passing host test harness does not establish complete desktop event coverage, live model legal accuracy, typical cost, or reliable behavior on a client case. Follow [the desktop acceptance procedure](../senior-associate-claude/docs/VERIFICATION.md) before releasing or representing those properties as verified.

The privacy gate is a workflow safeguard, not network isolation. Filing approval is a local attorney action, not an authentication boundary against a process that can rewrite the matter folder. Court and agency sources must still be refreshed for each matter. See [data handling and limits](../senior-associate-claude/docs/DATA-HANDLING.md).

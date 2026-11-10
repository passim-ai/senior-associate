# Matters interface 0.2.0 — October 31, 2026

The workspace now uses Passim’s wordmark, navy and orange palette, warm paper surfaces, Newsreader headings, and Public Sans controls. Fonts and SVGs are bundled locally; no asset CDN, remote font request, or new network permission is required. The OFL font licenses are included in the installable package.

## Attorney workflow

- First use explains the document → decisions → draft review sequence and offers a fictional sample.
- The matter overview gives one recommended next action based on the current state. Setup issues and unanswered attorney decisions receive priority. Source counts, stage progress, and items needed before filing link to their respective sections.
- New matter creation asks only relevant questions; the custom-filing description appears only when needed. Draft fields survive navigation and refreshes within the open panel.
- Attorney decisions are separated from client evidence requests. Suggested wording can be adopted and edited before saving. Saving is explicitly distinguished from applying an answer during a packet update.
- Work product comes before preparation history. Redo and mark-as-filed actions have contextual confirmations. Neither action sends a filing.
- Memos and client requests use a readable document view with safe Markdown formatting and copy actions. HTML is inert; only HTTP(S) links without embedded credentials are accepted, and opening a link is delegated to the host.
- Setup uses descriptions of attorney tasks, with tool names in advanced details. Instructions and matter preferences remain available through disclosures.

## Detail and accessibility pass

Desktop, 420-pixel panels, and 320-pixel panels were checked. Narrow panels expose all six matter sections. Light and dark themes preserve the Passim identity. Controls have visible keyboard focus, labeled inputs, announcements for actions and failures, and keyboard-accessible confirmations with focus containment and return. Refresh preserves active editing. Reduced motion is honored. There is one main landmark.

## Verification boundary

The actual bundled component was exercised against the local protocol test host and real packaged MCP server, using disposable fictional records and mocked native pickers. All 11 browser scenarios pass: creation/import/review/cancel; persistent answers; rejected handoff recovery; profile privacy; refresh; conditional intake and draft preservation; search; safe formatted documents and host links; confirmation keyboard behavior; narrow/dark/reduced-motion layouts; and visual review capture. Six transport tests and 25 adapter/package checks pass. Shared Claude source and installed Claude files were not changed by this redesign.

Screenshots are retained under `artifacts/ui-redesign-2026-10-31/`, with additional narrow light/dark captures under `artifacts/`. They show fictional UI fixtures, not a verified legal packet or the native ChatGPT host.

Native ChatGPT panel visibility, actual host button handoff and pickers, and privacy-hook discovery remain unverified as described in VERIFICATION.md. This UI release does not claim to resolve those host limitations.

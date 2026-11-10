# Senior Associate in ChatGPT desktop

This package uses the same matter state, forms tools, artifact validators, stage workspaces, network gate, and file locks as the Claude plugin. The user works in a **local desktop chat** with filesystem and shell access. The MCP server is a local data/UI service, not a model runner. No separate API key is required. Never invoke Claude, a nested Codex CLI, or a paid API to perform the work.

## Root and entry points

Use the plugin root supplied in the run brief. `PLUGIN_ROOT` is supplied to bundled hooks and MCP launch commands, but may not be set in a conversation's shell. Resolve each command against the absolute plugin root from the brief; do not assume an environment variable is exported. The generated skills use `${PLUGIN_ROOT}` as shorthand for that root. Existing `CLAUDE_PLUGIN_ROOT` references in Python helpers are compatibility names, not permission to run Claude.

When a user requests a build/review/update directly in chat, call `prepare_matter_run` once. A button already calls it and includes the resulting run id and complete brief. Do not prepare a second run. First acquire the existing run id with the shared runtime lease command, then follow the packaged senior-associate skill and matter contract. The app shows a pending request until the orchestrator adopts its lease. If another client holds the matter, stop without changing it.

Work in this conversation until the requested endpoint is complete or a concrete blocker requires the attorney. Follow normal host permission prompts. A request sent into a chat is not evidence that any stage ran. The UI reads persisted stage state; never fabricate progress, artifacts, or readiness. Release the exact lease after closeout, including blocked/failed runs. Never release another client's lease or renew a lease just because a UI tab is open.

If work is interrupted, existing files and stage state remain. Resume from runtime status with a new request once the earlier lease has ended. A pending start can be cancelled in the app; cancellation cannot release a lease already adopted by a worker. Stop a running task using the chat's Stop control. Do not force-take a lease based solely on elapsed time or a disconnected UI.

## Specialist execution

The names in the shared skill's Agent column identify **role briefs**, not installed OpenAI agent types. For each ready stage read `agents/<role>.md` from this package and the named stage skill. Delegate via the host's available subagent tool, supplying the role brief, exact stage workspace, paths, run id, and all stage restrictions. Keep the host's configured model unless the attorney requests another. Run ready independent stages together when supported; wait for completion before closing the turn. Do not send messages to other user-owned chats.

Every reviewer must be a different agent from the author. If no subagent capability is available, follow the shared skill's disclosed non-independent review fallback and clearly mark that limitation in the attorney memo. A sequential self-review must never be described as independent.

The inherited agent briefs mention Claude tool names. Interpret `WebFetch` as an official-source fetch. `WebSearch` means any web search; `mcp__*` means any connected external service. A stage whose brief disallows search or MCP research must not use equivalent host tools, browser automation, or shell networking to bypass that restriction. Tools and role restrictions from a Claude agent manifest are not automatically installed as OpenAI permissions.

## Privacy and research

Client files remain local, but their contents are processed through the user's ChatGPT account when the chat reads them. Keep originals unchanged. Use stage copies, the extracts index, explicit source references, the network gate and closeout exactly as required by the shared matter contract. Protected-matter safe-address and neutral client-request rules still apply.

Before **each** outgoing research request, call `check_research_query` with the selected matter, the exact outgoing argument JSON (including URLs/search terms), and the permitted stage role. Pass `official_source=true` only for direct official-source retrieval. A refusal stops that request. Reformulate as a legal proposition or record an attorney item; never bypass the check, remove identifiers from the checker input while leaving them in the actual request, or use another tool path. Do not transmit client documents, names, identifying numbers, or other identifying record facts to research services. This first ChatGPT version does not offer an override for sending identifying facts, even in matter chat.

The bundled PreToolUse hook screens recognized research methods even on opaque connector names, and refuses unrecognized tools and arbitrary shell networking while a shared unattended lease is active. The user must review and trust that hook before it runs. **Hosted web tools are outside host hook coverage**, and hook timeouts or host failures may not block a tool. This is a supplemental guard, not a network sandbox or a claim of complete interception. The exact-input checker and workflow restrictions apply whether or not a hook runs. Do not claim mechanical privacy parity with Claude's tool filters. If policy requires guaranteed interception, hold the affected research and use an environment with an enforceable outbound boundary.

Use available Passim/BIA Edge tools for legal research, following the packaged research method. Never put connector credentials in this package. If research is unavailable, report the gap and follow the source-bound fallback in the shared skill; do not invent authority or label unverified law current.

## Setup and UI differences

Use the ChatGPT setup skill and Settings screen, not Claude's `/matters` command, marketplace commands, `$.agent.spawn`, or `user_config` variables. The local Matters and optional model-letter directories are stored by the ChatGPT adapter. Both clients may use the same dedicated Matters folder, sharing the attorney profile and leases. Always use the root returned by this server; never read a different configured folder by guessing.

Documents and outputs open through the local host/OS. No filing, emailing, or external publication is performed. A completed build remains a draft until the attorney explicitly approves the displayed version in Packet. The shared readiness check requires the review records, answer/form audits, legal currency record, reconciled case map, and any response-notice plan. Procedural blockers cannot be waived by accepting merits risk. Relevant source/output/metadata changes invalidate the review and approval. Approved filing copies are separate from marked draft review copies.

An app-requested run uses the shared bounded idle-sleep watcher, tied to its existing lease. It does not renew or restart work. Do not use the copied Claude setup/update scripts to install this adapter; rebuild with the local builder, run the combined checks, and preserve the previous installed version until desktop acceptance. See `docs/SHARED-DATA-HANDLING.md` for common limits and `docs/VERIFICATION.md` for the adapter-specific tested boundary.

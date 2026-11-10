# Senior Associate / Matters for ChatGPT desktop

A desktop-first ChatGPT MCP App built on Senior Associate's existing matter engine. The installed Claude plugin is preserved; shared-engine fixes in this branch are regression-tested for both clients. This package adds a Matters sidebar and chat panel, local intake and document import, attorney profile and instructions, saved answers, packet progress, reviewer notes, memo/client request, and a timeline. Buttons hand work to the local ChatGPT conversation; they do not launch a hidden model process or require an API key.

## Interface

Version 0.2.1 retains the Passim visual identity, guided intake, a prioritized next step, grouped questions, and a formatted document reader. It supports desktop and narrow panels, light/dark themes, keyboard navigation, and reduced motion. See [the interface changes and verification](docs/UI-REDESIGN.md).

## Build

From this directory:

```sh
cd web
npm ci --ignore-scripts
npm run build
cd ..
python3 build.py
```

The builder prints the complete installable plugin directory and writes its path to `dist/latest.txt`. Each build goes into a new directory; earlier builds are preserved. The build root includes `.agents/plugins/marketplace.json` for local discovery. `shared-source.json` records the source engine version and hashes. The builder copies shared scripts byte-for-byte and adapts only generated skill/role Markdown. It never edits the Claude source, installed plugin, client matters, or credentials.

The checked-in adapter folder is source, **not the installable package**. Install the built directory, which includes the shared engine, skills, and bundled UI. Node is needed only for authoring; uv runs the packaged Python server. `chatgpt/server.py.lock` pins its Python dependencies.

## Install locally

Register the printed package's **parent directory** as a local marketplace:

```sh
codex plugin marketplace add /absolute/path/to/dist/build-TIMESTAMP
```

Then open the desktop Plugins Directory, choose **Senior Associate for ChatGPT**, and install **Senior Associate / Matters**. For a local source that is not visible in the desktop directory, add the built package as a local entry in the existing `~/.agents/plugins/marketplace.json` Personal catalog, preserving every existing entry, and install `senior-associate-chatgpt@personal`. Enable only one copy to avoid duplicate skills and servers. Restart the app if the new local source is not visible. Refresh the Plugins Directory and test in a new local chat. Installation and a real host run are separate from the automated checks below; CLI discovery alone does not verify UI visibility. Keep it enabled only for local desktop work. The package uses portable `plugin.json` and `mcp.json` manifests and a local stdio server. Installation does not modify the Claude marketplace.

Open **Matters**, or ask **Open Matters** in chat. Settings defaults to `~/Matters`; use the same dedicated folder as Claude if you want shared matters. Local settings live in plugin data (or `~/.config/senior-associate-chatgpt/settings.json` outside a managed plugin installation). Environment variables `SENIOR_ASSOCIATE_MATTERS_ROOT`, `SENIOR_ASSOCIATE_EXEMPLARS_DIR`, and `SENIOR_ASSOCIATE_CHATGPT_DATA` override those paths for managed installations and tests.

Run the setup skill, fill **Your details**, and try the fictional sample. The local privacy hook requires the host's review/trust step; do not bypass it. Public directory distribution is separate from this local build and may require OpenAI's approval for local MCP servers and a different treatment of lifecycle hooks.

## How work runs

A requested build/review takes the shared matter lease and returns a brief to the local chat. The orchestrator adopts that exact lease and follows the shared stages and gates. Another ChatGPT or Claude run cannot start over it. The UI refreshes state without keeping a dead worker's lease alive. Cancelling a pending start never releases a worker that already adopted it. Actual interruption uses the chat's Stop control; completed artifacts remain available to resume.

The first ChatGPT version uses the host's normal conversation and available subagent tools. It does not replicate Claude's private agent API, execute a background API job, or assume a particular model. See [the execution contract](docs/CHATGPT-RUNTIME.md).

## Privacy boundaries

The interface communicates only through the MCP Apps bridge. It contains no localhost token or direct HTTP side channel. Tool results expose the selected matter summary to the model and place the full workspace view in `_meta` for the UI. All displayed file contents are rendered as text.

Client files stay in the local Matters folder; content read by ChatGPT is processed through that account. Existing matter protection, source-copy, lease, artifact, and review rules remain in the shared workflow. Every research request must pass the explicit exact-input privacy check. The optional trusted hook additionally checks supported local research calls. Hosted web calls and host hook failures are not a complete enforcement boundary; this package does not claim mechanical privacy parity with Claude's tool restrictions. Sending identifying client facts to research has no override in this version.

No client documents are automatically sent to research services, and the plugin never files or emails a packet. The shared engine keeps completed work in draft until explicit attorney approval of the exact version. The Packet screen shows blockers and merits risks, accepts a reason for filing with risks, and opens separate clean filing copies. Changes to relevant inputs invalidate approval. Matter details capture the forum, circuit, and jurisdiction basis.

## Verification

Run adapter tests with the freshly built package:

```sh
uv run --locked --script tests/test_adapter.py
cd web
npm test
npx playwright test
```

The backend tests use disposable fictional matters. Browser tests exercise the actual bundled MCP App through a protocol host fixture. Test receipts should distinguish that from an actual ChatGPT installation or a model-completed legal packet.

See [verification and remaining host checks](docs/VERIFICATION.md) for this build's tested boundary.

From the repository root, `bash scripts/check-plugins.sh` runs the shared engine, Claude host harness, ChatGPT adapter, real CLI/stdio lifecycle, and browser suites. Each build is staged in a new directory; installed copies are not overwritten. See [current verification boundary](docs/VERIFICATION.md).

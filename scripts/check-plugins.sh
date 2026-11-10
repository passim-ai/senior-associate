#!/bin/bash
# Both source plugins. --quick skips only the Claude-specific CLI host checks.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1
(cd "$ROOT/senior-associate-claude" && bash scripts/check.sh "${1:-}")
(cd "$ROOT/senior-associate-chatgpt/web" && npm ci --ignore-scripts && npm run build && npm test)
python3 "$ROOT/senior-associate-chatgpt/build.py"
uv run --locked --script "$ROOT/senior-associate-chatgpt/tests/test_adapter.py"
uv run --locked --script "$ROOT/tests/test_plugins_e2e.py"
(cd "$ROOT/senior-associate-chatgpt/web" && npx --no-install playwright test)

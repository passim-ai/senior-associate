#!/bin/bash
# Runs every test suite in the plugin, one after another, and stops at the end with a summary.
#
#   scripts/check.sh            all suites
#   scripts/check.sh --quick    skip the app tests and plugin validation (no Claude CLI needed)
#
# Python suites are every scripts/**/tests/test_*.py and skills/**/tests/test_*.py, run with uv. The app tests and
# plugin validation use the Claude CLI: the one on PATH, else the newest copy inside the Claude desktop app.
# Suites run one at a time because LibreOffice conversions can't run in parallel.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1

QUICK=0
[ "${1:-}" = "--quick" ] && QUICK=1

failed=()
passed=0

run() {
  local name="$1"; shift
  local log
  log="$(mktemp -t sa-check)"
  local start=$SECONDS
  if "$@" >"$log" 2>&1; then
    passed=$((passed + 1))
    printf '  ok    %-60s %4ss\n' "$name" "$((SECONDS - start))"
  else
    failed+=("$name")
    printf '  FAIL  %-60s %4ss\n' "$name" "$((SECONDS - start))"
    tail -n 40 "$log" | sed 's/^/        /'
  fi
  rm -f "$log"
}

UV="$(command -v uv || true)"
for candidate in /opt/homebrew/bin/uv /usr/local/bin/uv "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
  [ -z "$UV" ] && [ -x "$candidate" ] && UV="$candidate"
done
if [ -z "$UV" ]; then
  echo "uv isn't installed; the Python suites need it." >&2
  exit 2
fi

echo "Python suites"
while IFS= read -r suite; do
  if [ -f "$suite.lock" ]; then
    run "$suite" "$UV" run --locked --quiet --script "$suite"
  else
    run "$suite" "$UV" run --quiet --script "$suite"
  fi
done < <(find scripts skills -path '*/tests/test_*.py' -type f | sort)

if [ "$QUICK" -eq 0 ]; then
  CLAUDE="$(command -v claude || true)"
  if [ -z "$CLAUDE" ]; then
    CLAUDE="$(ls -t "$HOME/Library/Application Support/Claude/claude-code/"*/*/claude.app/Contents/MacOS/claude 2>/dev/null | head -1)"
  fi
  echo "App"
  if [ -n "$CLAUDE" ]; then
    run "claude plugin test ." "$CLAUDE" plugin test .
    run "claude plugin validate ." "$CLAUDE" plugin validate .
    run "claude plugin validate .. (marketplace)" "$CLAUDE" plugin validate ..
  else
    echo "  FAIL  the Claude CLI is required for full verification; use --quick only for offline checks"
    failed+=("Claude CLI unavailable")
  fi
fi

echo
if [ "${#failed[@]}" -eq 0 ]; then
  echo "All $passed suites passed."
  exit 0
fi
echo "${#failed[@]} failed, $passed passed:"
printf '  %s\n' "${failed[@]}"
exit 1

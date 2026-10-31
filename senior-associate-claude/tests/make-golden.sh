#!/bin/bash
# The golden payloads the app's tests read: the real server (server/tools/golden_payloads.py) run against its
# fictional matters, written into tests/golden.ts (a test can't read files, so they are a module). Run it again after
# a server change, from the plugin folder: bash tests/make-golden.sh
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT
uv run --script "$SRC/server/tools/golden_payloads.py" --out "$OUT" >/dev/null
python3 - "$OUT" "$SRC/tests/golden.ts" <<'PY'
import json, sys
from pathlib import Path
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
payloads = {p.stem.removeprefix('payload-'): json.loads(p.read_text()) for p in sorted(src.glob('payload-*.json'))}
# One payload per line, so a server change shows in a diff as the payloads it changed.
body = ",\n".join(f"  {json.dumps(name)}: {json.dumps(data, ensure_ascii=False, sort_keys=True)}" for name, data in payloads.items())
dst.write_text(
    "// Written by tests/make-golden.sh from server/tools/golden_payloads.py: what the real server answers for its\n"
    "// fictional matters, one in each state the app draws. Don't edit by hand; run the script again.\n"
    "/* eslint-disable */\n"
    f"export const GOLDEN: Record<string, any> = {{\n{body},\n}}\n"
)
print(f"wrote {dst} ({len(payloads)} payloads)")
PY

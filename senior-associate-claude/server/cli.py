#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The /matters command path: one JSON request in, one JSON answer out.

    uv run --script cli.py '{"op": "state", "matters_root": "~/Matters"}'

Standard library only, so it runs offline and never resolves a package on the app's 15-second refresh.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from sa_server.transports.cli import main  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('usage: cli.py \'{"op": "state"}\'', file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])

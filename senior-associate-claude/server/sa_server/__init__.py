"""The Senior Associate app server, in small modules.

    catalog      case types, postures, step names, status names
    plaintext    the clean-up that turns older open items into plain sentences
    folders      matter folders, the client's documents, finished files
    readmodel    the matter card and the matters list the app draws
    prompts      the briefs for the runs the app starts, built when a start needs them
    actions      everything that changes a matter, each under the matter's lock
    doctor       the setup check
    transports   the command line /matters runs

Everything here is standard library.
"""
from __future__ import annotations

import sys
from pathlib import Path

# The shared matter state lives in the plugin's scripts/ folder: ``from scripts.matter_state import ...``.
_PLUGIN_ROOT = str(Path(__file__).resolve().parents[2])
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

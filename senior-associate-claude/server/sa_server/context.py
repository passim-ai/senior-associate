"""Where the server works: the attorney's Matters folder and model letters, passed to every function that needs them.

One Context per request, built from the environment and the plugin's settings in the request. Nothing reads a module
global for these, so a test (or a second request with other folders) can't leak into the next one.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PLUGIN_ROOT = Path(__file__).resolve().parents[2]

# A client's documents are dozens or hundreds of files. Far more means the wrong folder was picked
# (a whole practice folder, a home folder), and copying it would bury the matter and stall the app.
MAX_FOLDER_FILES = 1500
MAX_FOLDER_BYTES = 3 * 1024**3


def _env_path(env: Mapping[str, str], name: str, default: Path) -> Path:
    raw = env.get(name, "").strip()
    # An option the attorney never set can arrive as its unexpanded placeholder.
    if "${" in raw:
        raw = ""
    return (Path(raw).expanduser() if raw else default).resolve()


@dataclass(frozen=True)
class Context:
    matters_root: Path
    exemplars_dir: Path
    plugin_root: Path = PLUGIN_ROOT
    max_folder_files: int = MAX_FOLDER_FILES
    max_folder_bytes: int = MAX_FOLDER_BYTES
    # A fixed clock, for golden payloads and tests; None is the real time.
    fixed_now: datetime | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Context":
        env = os.environ if env is None else env
        root = _env_path(env, "SENIOR_ASSOCIATE_MATTERS_ROOT", Path.home() / "Matters")
        fixed = env.get("SENIOR_ASSOCIATE_FIXED_NOW", "").strip()
        return cls(
            matters_root=root,
            exemplars_dir=_env_path(env, "SENIOR_ASSOCIATE_EXEMPLARS_DIR", root / "Exemplar"),
            fixed_now=_parse_fixed(fixed),
        )

    def with_request(self, request: Mapping[str, Any]) -> "Context":
        """The app passes the attorney's folders with every request. An unset option comes through empty or as its
        placeholder; then the defaults stand (~/Matters), so /matters works even if the option was skipped."""
        ctx = self
        root = str(request.get("matters_root") or "").strip()
        if root and "${" not in root:
            matters_root = Path(root).expanduser().resolve()
            ctx = replace(ctx, matters_root=matters_root, exemplars_dir=(matters_root / "Exemplar").resolve())
        letters = str(request.get("exemplars_dir") or "").strip()
        if letters and "${" not in letters:
            ctx = replace(ctx, exemplars_dir=Path(letters).expanduser().resolve())
        return ctx

    def now(self) -> datetime:
        return self.fixed_now or datetime.now(tz=timezone.utc)

    @property
    def runtime_dir(self) -> Path:
        return self.plugin_root / "skills" / "senior-associate" / "scripts"

    @property
    def runtime_cli(self) -> Path:
        return self.runtime_dir / "run_matter_workflow.py"

    @property
    def plugin_json(self) -> Path:
        return self.plugin_root / ".claude-plugin" / "plugin.json"

    @property
    def profile_path(self) -> Path:
        return self.matters_root / ".senior-associate" / "attorney-profile.json"


def _parse_fixed(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

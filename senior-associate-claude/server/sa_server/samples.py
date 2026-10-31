"""The sample matter: fictional documents shipped with the plugin (samples/<id>/), copied in as a matter the first time
the app opens on an empty Matters folder, and again whenever the attorney asks from Help.

A matter is the sample when its workflow folder holds sample.json naming the sample. The Matters folder's own
.senior-associate/sample.json records that the sample was offered, so it never comes back by itself once the attorney
has archived or deleted it."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.matter_state import WORKFLOW_DIR

from .common import now_iso, read_json, write_json_atomic
from .context import Context

SAMPLE_ID = "barrientos-eckhardt-i601a"
MATTER_FILE = "sample.json"  # in the matter's workflow folder: this matter is the sample


def sample_dir(ctx: Context, sample_id: str = SAMPLE_ID) -> Path:
    return ctx.plugin_root / "samples" / sample_id


def manifest(ctx: Context, sample_id: str = SAMPLE_ID) -> dict[str, Any] | None:
    data = read_json(sample_dir(ctx, sample_id) / "sample.json")
    return data if isinstance(data, dict) and data.get("id") == sample_id else None


def documents(ctx: Context, sample_id: str = SAMPLE_ID) -> list[Path]:
    m = manifest(ctx, sample_id) or {}
    folder = sample_dir(ctx, sample_id) / str(m.get("documents") or "Client documents")
    if not folder.is_dir():
        return []
    return sorted((p for p in folder.iterdir() if p.is_file() and not p.name.startswith(".")), key=lambda p: p.name.lower())


def offered_marker(ctx: Context) -> Path:
    return ctx.matters_root / ".senior-associate" / MATTER_FILE


def was_offered(ctx: Context) -> bool:
    return offered_marker(ctx).exists()


def record_offered(ctx: Context, how: str, matter: Path | None = None) -> None:
    record = {"offered_at": now_iso(ctx), "how": how, "sample": SAMPLE_ID}
    if matter is not None:
        record["matter"] = matter.name
    write_json_atomic(offered_marker(ctx), record)


def mark_matter(matter: Path, sample_id: str = SAMPLE_ID) -> None:
    write_json_atomic(matter / WORKFLOW_DIR / MATTER_FILE, {"sample": sample_id})


def sample_id_of(matter: Path) -> str:
    data = read_json(matter / WORKFLOW_DIR / MATTER_FILE)
    return str(data.get("sample") or "") if isinstance(data, dict) else ""


def is_sample(matter: Path) -> bool:
    return bool(sample_id_of(matter))


def guide_for(ctx: Context, matter: Path) -> dict[str, Any] | None:
    """What the sample's page tells the attorney to try, and what a good document review catches."""
    sid = sample_id_of(matter)
    if not sid:
        return None
    guide = (manifest(ctx, sid) or {}).get("guide")
    return {"id": sid, **guide} if isinstance(guide, dict) else {"id": sid}


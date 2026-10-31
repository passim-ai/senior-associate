#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import uuid
from typing import Any

from scripts.matter_state import now_iso, write_json_atomic


# Where a matter's workflow record can live: the current layout, then older ones.
WORKFLOW_RECORD_DIRS = (Path("output/working/workflow"), Path("output/shareable/workflow"), Path("output/workflow"))
POLICY_RELATIVE_PATH = Path("output/privacy/matter_policy.json")
ACCESS_LOG_RELATIVE_PATH = Path("output/privacy/access_log.jsonl")
DEFAULT_ROLES = [
    "senior_associate",
    "docs_review",
    "forms_preparer",
    "forms_reviewer",
    "cover_letter_writer",
    "cover_letter_writer_draft",
    "cover_letter_writer_integrate",
    "cover_letter_researcher",
    "cover_letter_reviewer",
    "packet_assembly",
    "final_review",
    "attorney_handoff",
    "attorney",
    "support",
    "system",
]
DEFAULT_DATA_PLANES = {
    "raw_documents": [
        "attorney",
        "attorney_handoff",
        "docs_review",
        "forms_preparer",
        "forms_reviewer",
        "cover_letter_writer",
        "cover_letter_researcher",
        "cover_letter_reviewer",
        "packet_assembly",
        "final_review",
        "senior_associate",
        "system",
    ],
    "structured_facts": [
        "attorney",
        "docs_review",
        "forms_preparer",
        "forms_reviewer",
        "cover_letter_writer",
        "cover_letter_researcher",
        "cover_letter_reviewer",
        "final_review",
        "senior_associate",
        "system",
    ],
    "agent_context": ["docs_review", "forms_preparer", "forms_reviewer", "cover_letter_writer", "cover_letter_writer_draft", "cover_letter_writer_integrate", "attorney_handoff", "cover_letter_researcher", "cover_letter_reviewer", "packet_assembly", "final_review", "senior_associate", "system"],
    "audit_metadata": DEFAULT_ROLES,
}
# A matter's privacy mode: what the network gate allows in it (network_gate.ACTION_RULES).
PRIVACY_MODES = ("high_sensitivity", "restricted", "standard")


class AccessDeniedError(PermissionError):
    """Raised when a role attempts to cross a matter privacy boundary."""


def policy_path(matter_root: Path) -> Path:
    return matter_root.resolve() / POLICY_RELATIVE_PATH


def access_log_path(matter_root: Path) -> Path:
    return matter_root.resolve() / ACCESS_LOG_RELATIVE_PATH


def normalize_privacy_mode(value: str) -> str:
    normalized = value.strip().casefold()
    if normalized not in PRIVACY_MODES:
        raise ValueError(f"Unsupported privacy mode {value!r}. Expected one of: {', '.join(PRIVACY_MODES)}.")
    return normalized


def build_default_policy(matter_root: Path, *, privacy_mode: str = "standard") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "matter_id": f"matter-{uuid.uuid4()}",
        "matter_root": str(matter_root.resolve()),
        "privacy_mode": normalize_privacy_mode(privacy_mode),
        "roles": list(DEFAULT_ROLES),
        "data_plane_access": DEFAULT_DATA_PLANES,
        "created_at": now_iso(precise=True),
        "updated_at": now_iso(precise=True),
    }


def merge_policy_defaults(policy: dict[str, Any]) -> bool:
    changed = False

    roles = policy.setdefault("roles", [])
    if isinstance(roles, list):
        for role in DEFAULT_ROLES:
            if role not in roles:
                roles.append(role)
                changed = True

    data_plane_access = policy.setdefault("data_plane_access", {})
    if isinstance(data_plane_access, dict):
        for plane, default_roles in DEFAULT_DATA_PLANES.items():
            allowed_roles = data_plane_access.setdefault(plane, [])
            if not isinstance(allowed_roles, list):
                continue
            for role in default_roles:
                if role not in allowed_roles:
                    allowed_roles.append(role)
                    changed = True

    if changed:
        policy["updated_at"] = now_iso(precise=True)
    return changed


class NotAMatterFolder(ValueError):
    pass


def has_workflow_record(root: Path) -> bool:
    return any(any((root / folder).glob("**/matter_status.json")) for folder in WORKFLOW_RECORD_DIRS)


def has_client_documents(root: Path) -> bool:
    for path in root.iterdir():
        if path.name.startswith(".") or path.name == "output":
            continue
        if path.is_file() or (path.is_dir() and any(child.is_file() for child in path.rglob("*"))):
            return True
    return False


def require_matter_folder(matter_root: Path, *, allow_empty: bool = False) -> Path:
    """The matter folder a script was given, or an error if the path isn't one.

    Without this, an agent that passes a stage id ("docs_review") where the folder belongs
    gets a fresh output/ skeleton created under whatever folder it happens to be working in.
    A matter folder has to exist already; unless allow_empty (the app creates a new matter's
    folder empty and records the workflow next), it also holds a workflow record or the
    client's documents.
    """
    root = matter_root.expanduser().resolve()
    if not root.is_dir():
        raise NotAMatterFolder(
            f"Matter folder not found: {root}. Pass the matter folder's absolute path (not a stage id)."
        )
    if not allow_empty and not has_workflow_record(root) and not has_client_documents(root):
        raise NotAMatterFolder(
            f"{root} doesn't look like a matter folder: it has no workflow record and no client documents. "
            "Pass the matter folder's absolute path (not a stage id)."
        )
    return root


def ensure_policy(matter_root: Path, *, privacy_mode: str = "standard") -> Path:
    if not matter_root.expanduser().is_dir():  # never create a matter folder as a side effect
        raise NotAMatterFolder(f"Matter folder not found: {matter_root}. Pass the matter folder's absolute path.")
    path = policy_path(matter_root)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if merge_policy_defaults(payload):
            write_json_atomic(path, payload)
        return path
    write_json_atomic(path, build_default_policy(matter_root, privacy_mode=privacy_mode))
    return path


def load_policy(matter_root: Path) -> dict[str, Any]:
    path = policy_path(matter_root)
    if not path.exists():
        raise FileNotFoundError(f"Matter policy not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def denied_data_planes(policy: dict[str, Any], *, role: str, data_planes: list[str]) -> list[str]:
    if role not in policy.get("roles", []):
        return list(data_planes)

    permissions = policy.get("data_plane_access", {})
    denied: list[str] = []
    for data_plane in data_planes:
        allowed_roles = permissions.get(data_plane, [])
        if role not in allowed_roles:
            denied.append(data_plane)
    return denied


def assert_role_access(
    matter_root: Path,
    *,
    role: str,
    data_planes: list[str],
) -> dict[str, Any]:
    policy = load_policy(matter_root)
    denied = denied_data_planes(policy, role=role, data_planes=data_planes)
    if denied:
        raise AccessDeniedError(
            f"Role {role!r} is not allowed to access data planes {denied!r} for this matter."
        )
    return policy


def log_access_event(
    matter_root: Path,
    *,
    event_type: str,
    role: str,
    actor: str = "system",
    data_planes: list[str] | None = None,
    artifacts: list[str] | None = None,
    notes: str | None = None,
) -> Path:
    requested_planes = list(data_planes or [])
    policy = assert_role_access(matter_root, role=role, data_planes=requested_planes)

    path = access_log_path(matter_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": now_iso(precise=True),
        "matter_id": policy.get("matter_id", ""),
        "event_type": event_type,
        "actor": actor,
        "role": role,
        "data_planes": requested_planes,
        "privacy_mode": policy.get("privacy_mode", ""),
        "artifacts": list(artifacts or []),
        "notes": notes or "",
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")
    return path

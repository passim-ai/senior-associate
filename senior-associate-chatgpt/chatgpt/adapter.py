"""OpenAI host adapter around the shared Senior Associate matter engine.

The browser has no localhost bridge, token, filesystem path override, or arbitrary
command endpoint. App actions go through MCP and the shared matter locks. Models
receive compact summaries; the view payload is carried in tool-result _meta.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
sys.path.insert(0, str(ROOT))

from sa_server import actions, readmodel
from sa_server.common import UserError
from sa_server.context import Context
from sa_server.folders import load_track, resolve_matter
from sa_server.prompts import REPORT_NOTE, prompt_for
from sa_server.transports.cli import run_cli
from scripts.matter_state import acquire_lease, add_event, new_run_id, release_lease

APP_URI = 'ui://senior-associate-chatgpt/matters-v1.html'
APP_ID = 'senior-associate-chatgpt'


def data_dir() -> Path:
    return Path(os.environ.get('SENIOR_ASSOCIATE_CHATGPT_DATA') or os.environ.get('PLUGIN_DATA')
                or Path.home() / '.config/senior-associate-chatgpt').expanduser().resolve()


def settings() -> dict[str, str]:
    path = data_dir() / 'settings.json'
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError()
        return {k: v for k, v in value.items() if k in {'matters_root', 'exemplars_dir'} and isinstance(v, str)}
    except (OSError, ValueError):
        raise UserError('Senior Associate settings could not be read. Ask ChatGPT to repair its settings file.') from None


@dataclass(frozen=True)
class ChatGPTContext(Context):
    @property
    def plugin_json(self) -> Path:
        return self.plugin_root / 'plugin.json'

    @property
    def ui_html(self) -> Path:
        return self.plugin_root / 'web/dist/index.html'

    def with_request(self, request):
        # A widget request must never redirect the server to another folder.
        if 'matters_root' in request or 'exemplars_dir' in request:
            raise UserError('Change the Matters folder through Settings, not a matter action.')
        return self


def context() -> ChatGPTContext:
    saved = settings()
    root = Path(os.environ.get('SENIOR_ASSOCIATE_MATTERS_ROOT') or saved.get('matters_root') or Path.home() / 'Matters').expanduser().resolve()
    letters = Path(os.environ.get('SENIOR_ASSOCIATE_EXEMPLARS_DIR') or saved.get('exemplars_dir') or root / 'Exemplar').expanduser().resolve()
    return ChatGPTContext(matters_root=root, exemplars_dir=letters, plugin_root=ROOT)


def configure(matters_root: str, exemplars_dir: str = '') -> dict:
    root = Path(matters_root).expanduser()
    if not root.is_absolute():
        raise UserError('Choose an absolute path for the Matters folder.')
    root = root.resolve()
    home = Path.home().resolve()
    if root in {Path('/'), home, home / 'Documents', home / 'Desktop', home / 'Downloads', home / 'Library'}:
        raise UserError('Choose a dedicated Matters folder, not a home or general documents folder.')
    if root.exists() and not root.is_dir():
        raise UserError('The Matters path must be a folder.')
    if os.environ.get('SENIOR_ASSOCIATE_MATTERS_ROOT') or os.environ.get('SENIOR_ASSOCIATE_EXEMPLARS_DIR'):
        raise UserError('This installation sets its folders in the server environment. Change that configuration instead.')
    letters = Path(exemplars_dir).expanduser().resolve() if exemplars_dir.strip() else root / 'Exemplar'
    if exemplars_dir and not letters.is_dir():
        raise UserError('The model letters folder does not exist.')
    values = {'matters_root': str(root), 'exemplars_dir': str(letters)}
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    from sa_server.common import write_json_atomic
    write_json_atomic(folder / 'settings.json', values)
    return {'status': 'configured', **values}


def host_brief(ctx: Context, text: str) -> str:
    text = text.replace(REPORT_NOTE, '').replace('senior-associate:', 'senior-associate-chatgpt:')
    return (f'Use the installed Senior Associate / Matters ChatGPT plugin. Plugin root: {ctx.plugin_root}\n'
            f'Read {ctx.plugin_root / "docs/CHATGPT-RUNTIME.md"} before any work. '
            'Work in this local chat using its tools and available subagents. '
            'Do not invoke Claude, start another CLI session, use an API key, or claim a background job was launched.\n\n'
            + text)


def prepare_run(ctx: Context, matter_path: str, kind: str, stage_id: str = '', note: str = '') -> dict:
    # Same lease protocol as Claude: a second client or double-click cannot start another writer.
    matter = resolve_matter(ctx, matter_path)
    if kind not in actions.RUN_KINDS:
        raise UserError('Choose a supported packet action.')
    load_track(matter)  # unreadable records must stop before taking a lease
    lease_kind, _ = actions.RUN_KINDS[kind]
    run_id = new_run_id()
    ok, _ = acquire_lease(matter, run_id, lease_kind, 'app', description='Waiting for the ChatGPT request', now=ctx.now())
    if not ok:
        raise UserError('Another run holds this matter. Follow it in its chat before starting more work.')
    try:
        brief = host_brief(ctx, prompt_for(ctx, matter, kind, stage_id=stage_id, note=note, run_id=run_id))
    except Exception:
        release_lease(matter, run_id, 'failed', now=ctx.now())
        raise
    add_event(matter, 'run_started', 'Packet work requested in ChatGPT.', actor='app', run_id=run_id, run_kind=kind, now=ctx.now())
    payload = view(ctx, str(matter))
    from scripts.keep_awake import start
    try:
        start(matter, run_id)
    except OSError:
        payload['warning'] = 'Keep this Mac awake during the build; sleep prevention could not start.'
    return {'status': 'run_prepared', 'run_id': run_id, 'prompt': brief,
            'matter_path': str(matter), 'view': payload}


# Only explicit app capabilities. No raw shell, privacy-term dump, arbitrary file
# read/write, lease heartbeat, or completion operation is exposed to the widget.
APP_ACTIONS = frozenset({
    'create', 'add_sample', 'add_documents', 'add_folder', 'open_folder', 'open_output', 'open_document',
    'save_answer', 'resolve_item', 'reopen_item', 'save_profile', 'set_instructions', 'set_meta',
    'approve_filing', 'mark_filed', 'unmark_filed', 'archive', 'unarchive', 'cancel_start',
})


def action(ctx: Context, request: dict[str, Any]) -> dict:
    if not isinstance(request, dict) or request.get('op') not in APP_ACTIONS:
        raise UserError('That action is not available in this app.')
    # Validate even when run_cli gets an action that does not otherwise use the context.
    ctx.with_request(request)
    return run_cli(request, ctx)


def view(ctx: Context, matter_path: str = '', include_archived: bool = False) -> dict:
    selected = resolve_matter(ctx, matter_path) if matter_path else None
    rows = readmodel.matters_list(ctx, include_archived=True)
    payload = readmodel.app_payload(ctx, selected, status='view', matters=rows, want_setup=True)
    payload['matters'] = [m for m in rows if include_archived or not m.get('archived')]
    payload['version'] = json.loads((ctx.plugin_root / 'plugin.json').read_text())['version']
    payload['chatgpt'] = {'execution': 'local-chat', 'settings_path': str(data_dir() / 'settings.json'),
                        'plugin_root': str(ctx.plugin_root), 'exemplars_dir': str(ctx.exemplars_dir)}
    return payload


def summary(payload: dict) -> dict:
    card = payload.get('matter')
    return {'status': payload.get('status', 'ok'), 'app': APP_ID,
            'matter': card_summary(card) if card and not card.get('problem') else None}


def card_summary(card: dict[str, Any]) -> dict[str, Any]:
    """One matter as the model-facing tools answer about it: where it stands and what's next, without the other
    matters, the attorney's details, the documents' names, or any brief."""
    status, counts = card["status"], card["counts"]
    protected = bool((card.get("meta") or {}).get("protected"))
    files = {k: v["name"] for k in ("packet", "paper_packet", "cover_letter", "memo", "client_request", "filing_checklist")
             if isinstance(v := card["outputs"].get(k), dict)}
    return {
        "name": card["name"],
        "path": card["path"],
        "case": readmodel.case_line(card["intake"], protected),
        "phase": card["phase"],
        "label": card["phase_label"],
        "next": readmodel.next_line(card["phase"], card["needs_you"], card["open_items"], counts),
        "step": f"step {status['step_index']} of {status['step_total']}" if status["step_total"] else "",
        "running": [s["label"] for s in status["running"]],
        "documents": card["documents"]["count"],
        "new_documents": len(card["documents"]["added_since_build"]) + len(card["documents"].get("changed_since_build", [])),
        "needed_before_filing": counts["needed_before_filing"],
        "questions_open": counts["decisions_open"],
        "files": files,
    }

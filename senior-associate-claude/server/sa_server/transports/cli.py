"""One action as a plain command, for the Claude Code pane: JSON in, JSON out. Standard library only, so /matters
works offline and never waits on a package resolve."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from .. import actions
from ..common import UserError
from ..context import Context
from ..doctor import doctor
from ..errors import friendly_error
from ..folders import resolve_matter
from ..logs import describe_error, log
from ..readmodel import app_payload, matters_list

UNAVAILABLE = "That action isn't available in this version. Restart Claude and try again."


class Request:
    """One request's fields, each read as text: ``q("kind")``, or ``q("which", "packet")`` with a default."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw

    def __call__(self, key: str, default: str = "") -> str:
        return str(self.raw.get(key) or default)

    def intake_settings(self) -> dict[str, Any]:
        """The settings New matter and Change what is being filed send with the case: protected, filing method."""
        out: dict[str, Any] = {}
        if self.raw.get("protected") is not None:
            out["protected"] = bool(self.raw["protected"])
        if self.raw.get("filing_method"):
            out["filing_method"] = str(self.raw["filing_method"])
        return out


def _state(ctx: Context, q: Request) -> dict[str, Any]:
    # The app's first open on a new Matters folder asks for the sample matter (it is added only once).
    if q.raw.get("ensure_sample"):
        actions.ensure_sample(ctx)
    selected = resolve_matter(ctx, q("matter_path")) if q("matter_path") else None
    matters = matters_list(ctx)
    shown = [m for m in matters if not m.get("archived") and not m.get("problem")]
    # The one matter opens by itself, unless it is the sample: a new attorney sees the welcome first.
    if (selected is None and len(shown) == 1 and len(matters) == 1 and not shown[0].get("sample")
            and q.raw.get("auto_select", True)):
        selected = Path(shown[0]["path"])
    return app_payload(ctx, selected, status="status", matters=matters, want_setup=bool(q.raw.get("setup") or q.raw.get("doctor")))


def _list(ctx: Context, q: Request) -> dict[str, Any]:
    """The matters list alone, light enough for the list screen's own refresh. Archived matters only when asked."""
    rows = matters_list(ctx)
    live = [m for m in rows if not m.get("archived")]
    return {"status": "list", "matters": rows if q.raw.get("include_archived") else live, "archived_count": len(rows) - len(live)}


def _save_profile(ctx: Context, q: Request) -> dict[str, Any]:
    profile = q.raw.get("profile")
    if not isinstance(profile, dict):
        raise UserError("Your details couldn't be saved. Try again.")
    return actions.do_save_profile(ctx, profile)


def _privacy_terms(ctx: Context, path: str) -> dict[str, Any]:
    # For the app's tool gate only: the parties' names and the client's identifiers. Never logged.
    from ..privacy import terms_payload

    return terms_payload(resolve_matter(ctx, path))


# Every op the app sends, by name: (the request's context, the matter it names, the request).
OPS: dict[str, Callable[[Context, str, Request], dict[str, Any]]] = {
    "state": lambda ctx, path, q: _state(ctx, q),
    "list": lambda ctx, path, q: _list(ctx, q),
    "doctor": lambda ctx, path, q: doctor(ctx),
    "create": lambda ctx, path, q: actions.do_create(ctx, q("name"), q("matter_type"), q("filing_posture"), **q.intake_settings()),
    "add_sample": lambda ctx, path, q: actions.do_add_sample(ctx),
    "set_intake": lambda ctx, path, q: actions.do_set_intake(ctx, path, q("matter_type"), q("filing_posture"), **q.intake_settings()),
    "change_intake": lambda ctx, path, q: actions.do_change_intake(ctx, path, q("matter_type"), q("filing_posture"), **q.intake_settings()),
    "add_documents": lambda ctx, path, q: actions.do_add_documents(ctx, path),
    "add_folder": lambda ctx, path, q: actions.do_add_folder(ctx, path),
    "open_folder": lambda ctx, path, q: actions.do_open_folder(ctx, path),
    "open_output": lambda ctx, path, q: actions.do_open_output(ctx, path, q("which", "packet"), q("name")),
    "open_document": lambda ctx, path, q: actions.do_open_document(ctx, path, q("path")),
    "remove_document": lambda ctx, path, q: actions.do_remove_document(ctx, path, q("path")),
    "restore_document": lambda ctx, path, q: actions.do_restore_document(ctx, path, q("kept")),
    "resolve_item": lambda ctx, path, q: actions.do_resolve_item(ctx, path, q("id"), q("note")),
    "reopen_item": lambda ctx, path, q: actions.do_reopen_item(ctx, path, q("id")),
    "accept_risk": lambda ctx, path, q: actions.do_accept_risk(ctx, path, q("id"), q("note")),
    "mark_filed": lambda ctx, path, q: actions.do_mark_filed(ctx, path),
    "unmark_filed": lambda ctx, path, q: actions.do_unmark_filed(ctx, path),
    "archive": lambda ctx, path, q: actions.do_archive(ctx, path, archived=True),
    "unarchive": lambda ctx, path, q: actions.do_archive(ctx, path, archived=False),
    "set_instructions": lambda ctx, path, q: actions.do_set_instructions(ctx, path, q("text")),
    "set_meta": lambda ctx, path, q: actions.do_set_meta(ctx, path, {k: q.raw[k] for k in ("protected", "client_language", "filing_method") if k in q.raw}),
    "save_answer": lambda ctx, path, q: actions.do_save_answer(ctx, path, q("key"), q("question"), q("answer")),
    "save_profile": lambda ctx, path, q: _save_profile(ctx, q),
    "start_run": lambda ctx, path, q: actions.do_start_run(ctx, path, q("kind"), q("stage_id") or q("stage"), q("note")),
    "heartbeat_run": lambda ctx, path, q: actions.do_heartbeat_run(ctx, path, q("run_id")),
    "release_run": lambda ctx, path, q: actions.do_release_run(ctx, path, q("run_id"), q("outcome", "done")),
    "cancel_start": lambda ctx, path, q: actions.do_cancel_start(ctx, path, q("run_id"), q("why")),
    "abandon_run": lambda ctx, path, q: actions.do_abandon_run(ctx, path, q("run_id")),
    "privacy_terms": lambda ctx, path, q: _privacy_terms(ctx, path),
}


def run_cli(request: dict[str, Any], ctx: Context | None = None) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise UserError(UNAVAILABLE)
    q = Request(request)
    handler = OPS.get(q("op", "state"))
    if handler is None:
        raise UserError(UNAVAILABLE)
    # Older ops name the matter matter_path; the ops added with the run lease name it matter (CONTRACTS §13).
    return handler((ctx or Context.from_env()).with_request(request), q("matter_path") or q("matter"), q)


def request_op(raw: str) -> str:
    """The op a request asked for, for the log; never the rest of the request, which names matters."""
    try:
        op = json.loads(raw).get("op")
    except (ValueError, AttributeError):
        return "unreadable request"
    return op if isinstance(op, str) and op.isidentifier() else "unknown op"


def main(raw: str) -> None:
    """Run one request and print its JSON answer: the result, or {"error": "<a plain sentence>"} with exit code 1."""
    ctx = Context.from_env()
    try:
        try:
            request = json.loads(raw)
        except json.JSONDecodeError:
            raise UserError(UNAVAILABLE) from None
        if isinstance(request, dict):
            ctx = ctx.with_request(request)
        result = run_cli(request, ctx)
    except Exception as exc:
        if not isinstance(exc, UserError):
            log(f"cli failed ({request_op(raw)}): {describe_error(exc)}")
        print(json.dumps({"error": friendly_error(exc, ctx)}))
        sys.exit(1)
    print(json.dumps(result))

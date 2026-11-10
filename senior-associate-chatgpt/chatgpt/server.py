#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=1.30,<2"]
# ///
"""ChatGPT desktop stdio MCP entry point. No HTTP side channel is opened."""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
from typing import Any
from mcp.types import CallToolResult, TextContent, ToolAnnotations

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapter import APP_ID, APP_URI, APP_ACTIONS, UserError, action, configure, context, host_brief, prepare_run, summary, view
from sa_server.errors import friendly_error
from sa_server.folders import resolve_matter
from sa_server.readmodel import card_or_problem
from sa_server.transports.cli import run_cli


def build_server():
    from mcp.server.fastmcp import FastMCP

    server = FastMCP('Senior Associate / Matters', instructions=(
        'Open Matters for its local desktop workspace. Use matter_status for a selected matter. '
        'Builds execute through the packaged senior-associate skill in the local conversation, not in the MCP server. '
        'Call prepare_matter_run only when the user asks for that work, then read the returned brief and carry it out. '
        'Read docs/CHATGPT-RUNTIME.md before client work. No filing or sending is performed by this plugin.'
    ))
    app_only = {'ui': {'visibility': ['app']}}
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
    template = context().ui_html
    if not template.is_file():
        raise RuntimeError('Build and install the complete Senior Associate package before starting its MCP server.')
    # Content-addressed URI prevents stale host caches after a rebuilt bundle.
    uri = APP_URI.replace('-v1.html', '-' + hashlib.sha256(template.read_bytes()).hexdigest()[:16] + '.html')

    def result(payload: dict, *, private: bool = True):
        public = summary(payload) if private else payload
        return CallToolResult(content=[TextContent(type='text', text=json.dumps(public))],
                              structuredContent=public, **({'_meta': {'view': payload}} if private else {}))

    def failed(exc: Exception):
        # Shared error formatting suppresses tracebacks and filesystem implementation detail.
        try:
            message = friendly_error(exc, context())
        except Exception:
            message = 'Senior Associate could not complete the request. Check its setup.'
        message = message.replace('Restart Claude', 'Restart ChatGPT').replace('Ask Claude', 'Ask ChatGPT')
        return CallToolResult(isError=True, content=[TextContent(type='text', text=message)])

    @server.tool(name='open_matters', title='Matters', annotations=read,
                 description='Open Senior Associate / Matters, or open one selected matter, inside ChatGPT.',
                 meta={'ui': {'resourceUri': uri}, 'openai/ui': {'entrypoints': [{'type': 'global'}, {'type': 'thread'}]}})
    def open_matters(matter_path: str = '') -> CallToolResult:
        try:
            return result(view(context(), matter_path))
        except Exception as exc:
            return failed(exc)

    @server.resource(uri, name='Matters', mime_type='text/html;profile=mcp-app',
                     meta={'ui': {'prefersBorder': False, 'permissions': {'clipboardWrite': {}}, 'csp': {'connectDomains': [], 'resourceDomains': []}}})
    def matters_html() -> str:
        return template.read_text()

    @server.tool(name='matters_view', title='Refresh Matters', annotations=read, meta=app_only,
                 description='Read the matter workspace for the app. Does not create or start anything.')
    def matters_view(matter_path: str = '', include_archived: bool = False) -> CallToolResult:
        try:
            return result(view(context(), matter_path, include_archived))
        except Exception as exc:
            return failed(exc)

    @server.tool(name='matters_action', title='Update Matters', annotations=write, meta=app_only,
                 description='Perform a user-selected matter action through the app; never runs shell commands.')
    def matters_action(request: dict[str, Any]) -> CallToolResult:
        try:
            return result(action(context(), request))
        except Exception as exc:
            return failed(exc)

    @server.tool(name='configure_matters', title='Set Matters folders', annotations=write, meta=app_only,
                 description='Save the dedicated local Matters folder and optional model-letter folder. Does not move files.')
    def configure_matters(matters_root: str, exemplars_dir: str = '') -> CallToolResult:
        try:
            configure(matters_root, exemplars_dir)
            return result(view(context()))
        except Exception as exc:
            return failed(exc)

    @server.tool(name='matter_status', title='Matter status', annotations=read,
                 description='Read a selected matter summary and its local folder path. Does not start a run.')
    def matter_status(matter_path: str) -> CallToolResult:
        try:
            ctx = context()
            card = card_or_problem(ctx, resolve_matter(ctx, matter_path))
            return result({'status': 'status', 'matter': card})
        except Exception as exc:
            return failed(exc)

    @server.tool(name='prepare_matter_run', title='Prepare packet work', annotations=write,
                 description='Reserve a selected matter for requested work and return its execution brief. '
                 'Does not itself launch an agent. kind: build, continue, update, review_docs, review_again, redo, stress_test, closeout. '
                 'Follow the brief in this local conversation; release the exact lease on completion or cancellation.')
    def prepare_matter_run(matter_path: str, kind: str, stage_id: str = '', note: str = '') -> CallToolResult:
        try:
            prepared = prepare_run(context(), matter_path, kind, stage_id, note)
            private_view = prepared.pop('view')
            return CallToolResult(content=[TextContent(type='text', text=prepared['prompt'])],
                                  structuredContent=prepared, **{'_meta': {'view': private_view}})
        except Exception as exc:
            return failed(exc)

    @server.tool(name='cancel_matter_start', title='Cancel a pending start', annotations=write,
                 description='Release only a pending app start. Never releases a run already adopted by a worker.')
    def cancel_matter_start(matter_path: str, run_id: str) -> CallToolResult:
        try:
            return result(action(context(), {'op': 'cancel_start', 'matter': matter_path, 'run_id': run_id}))
        except Exception as exc:
            return failed(exc)

    @server.tool(name='check_research_query', title='Check research privacy', annotations=write,
                 description='Check the exact proposed outgoing research input against this matter and log the network gate. '
                 'Use before every research call, including hosted web calls. A refusal must stop that query.')
    def check_research_query(matter_path: str, query: str, role: str = 'cover_letter_researcher', official_source: bool = False) -> CallToolResult:
        try:
            from privacy_hook import check_query
            check_query(context(), matter_path, query, role, official_source)
            return result({'status': 'allowed'}, private=False)
        except Exception as exc:
            return failed(exc)

    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--describe', action='store_true', help='Print tool names and annotations without opening any UI')
    args = parser.parse_args()
    server = build_server()
    if args.describe:
        async def describe():
            print(json.dumps([t.model_dump(by_alias=True, exclude_none=True) for t in await server.list_tools()], indent=2))
        asyncio.run(describe())
    else:
        server.run(transport='stdio')

if __name__ == '__main__':
    main()

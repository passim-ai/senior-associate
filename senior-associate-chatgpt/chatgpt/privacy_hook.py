#!/usr/bin/env python3
"""Supplemental privacy guard for supported local tool calls.

Hosted web requests are not intercepted by the host. The workflow must also call
check_research_query with the exact outgoing input before each research request.
This guard never authorizes a permission escalation or records client terms.
"""
from __future__ import annotations
import json
from pathlib import Path
import re
import shlex
import sys
import unicodedata
from urllib.parse import unquote_plus, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapter import ROOT, UserError, context
from sa_server.folders import resolve_matter
from scripts.matter_state import read_lease
from scripts.network_gate import check_network_action, lease_is_unattended
from scripts.privacy_terms import find_terms, matter_privacy_terms

BLOCKED = 'Senior Associate blocked research containing client details. Use a legal proposition without identifying facts.'
UNCHECKED = 'Senior Associate could not check research privacy. Resolve its settings or matter record before retrying.'


def plain(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text) if not unicodedata.combining(c))


def contains_private(query: str, terms: dict) -> bool:
    normalized = {k: [plain(str(v)) for v in values] for k, values in terms.items() if k in {'names', 'identifiers', 'full_names'}}
    for text in (query, unquote_plus(query)):
        text = plain(text)
        if find_terms(text, normalized):
            return True
        if any(re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', text, re.I) for name in normalized.get('full_names', [])):
            return True
        # Protect identifying values even before extraction reaches the fact table.
        if re.search(r'\bA\s*[-#.]?\s*(?:\d[ .-]*){7,9}\b|'
                     r'\b(?:EAC|WAC|LIN|SRC|MSC|IOE|NBC|YSC)[ -]*(?:\d[ -]*){10}\b|'
                     r'\b\d{3}[- ]\d{2}[- ]\d{4}\b|\b\d{9,16}\b|'
                     r'\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b|'
                     r'\b(?:\d{3}[-. ]|\(\d{3}\)\s*)\d{3}[-. ]\d{4}\b|'
                     r'\b(?:date of birth|dob|born)\b.{0,20}\d|'
                     r"\b\d{1,6}\s+[\w .'-]{1,60}\s+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd)\b", text, re.I):
            return True
    return False


def check_query(ctx, matter_path: str, query: str, role: str = 'cover_letter_researcher', official_source: bool = False):
    if not isinstance(query, str) or not query.strip() or len(query) > 100000:
        raise UserError('Supply the exact proposed research input, up to 100,000 characters.')
    research_roles = {'cover_letter_researcher', 'final_review', 'attorney', 'cover_letter_reviewer'}
    official_roles = research_roles | {'docs_review', 'forms_preparer', 'forms_reviewer', 'packet_assembly', 'senior_associate', 'cover_letter_writer'}
    if role not in (official_roles if official_source else research_roles):
        raise UserError('This stage cannot send research queries.')
    if official_source:
        urls = re.findall(r'https?://[^\s\"<>]+', query)
        if not urls or any(urlsplit(url).scheme != 'https' or not (urlsplit(url).hostname or '').endswith('.gov') for url in urls):
            raise UserError('Official-source checks require the exact HTTPS government URL; use the research check for other requests.')
    matter = resolve_matter(ctx, matter_path)
    terms = checked_terms(matter, require_sources=not official_source)
    if contains_private(query, terms):
        raise UserError(BLOCKED)
    # v1 deliberately never grants consent to send identifying client facts.
    check_network_action(matter, action='official_source' if official_source else 'mcp_research',
                         role=role, actor='system', sends_client_data=False)


def checked_terms(matter: Path, *, require_sources: bool = True) -> dict:
    from scripts.privacy_terms import FACT_TABLE_GLOBS, INVENTORY_GLOBS, name_tokens
    # The shared extractor tolerates damaged files; this outbound boundary must not.
    for pattern in (*FACT_TABLE_GLOBS, *INVENTORY_GLOBS):
        for path in matter.glob(pattern):
            try:
                data = json.loads(path.read_text())
                if not isinstance(data, (dict, list)):
                    raise ValueError()
            except (OSError, ValueError):
                raise UserError(UNCHECKED) from None
    terms = matter_privacy_terms(matter)
    if require_sources and (not terms['sources'] or not (terms['names'] or terms['full_names'])):
        raise UserError('Review the documents and record the parties before external case-law research.')
    terms['names'] = list(set(terms['names']) | set(name_tokens(matter.name)))
    return terms


LOCAL_TOOLS = {'Read', 'Write', 'Edit', 'MultiEdit', 'Glob', 'Grep', 'LS', 'TodoWrite', 'Task', 'Agent', 'AskUserQuestion'}
RESEARCH_METHODS = re.compile(r'__(?:search_cases|search_statutes|search_references|search_passages|search_country_conditions|search_unpublished_cases|search_district_court_decisions|get_case_by_citation|get_statute_by_citation|get_reference_by_citation|get_document|get_citations|check_validity|get_regulatory_updates|get_corpus_info|get_research_playbook|get_visa_bulletin|lookup_uscis_form|find_in_statute|find_in_reference|lookup_criminal_code|get_provision_case_law|fetch)$')
OWN_METHODS = re.compile(r'^mcp__senior_associate_matters__(?:open_matters|matter_status|prepare_matter_run|cancel_matter_start|check_research_query)$')
UNKNOWN = 'This tool is not approved during a matter run. Use supported local document tools or read-only legal research.'


def research_tool(name: str) -> bool:
    return name in {'WebSearch', 'WebFetch'} or bool(RESEARCH_METHODS.search(name)) or bool(re.search(r'web(?:__|\.)|search_service', name, re.I))


def local_command(value: dict) -> bool:
    raw = str(value.get('command', value.get('cmd', ''))).strip()
    if not raw or re.search(r'[;|&><`\n]|\$\(|https?:', raw, re.I):
        return False
    raw = raw.replace('${PLUGIN_ROOT}', str(ROOT))
    if re.search(r'[$\\]|\bfind\b.*-(?:exec|execdir|ok|okdir)', raw):
        return False
    try:
        tokens = shlex.split(raw)
    except ValueError:
        return False
    if not tokens:
        return False
    if tokens[0] in {'pwd','ls','cat','head','tail','wc','rg','find','mkdir','cp','gs','pdftotext','pdftoppm','pdfinfo'}:
        return True
    script = ''
    if Path(tokens[0]).name in {'python','python3'} and len(tokens)>1:
        script = tokens[1]
    if Path(tokens[0]).name == 'uv' and tokens[1:2] == ['run'] and '--script' in tokens:
        at = tokens.index('--script')
        if all(t in {'--offline','--locked'} for t in tokens[2:at]) and len(tokens)>at+1:
            script = tokens[at+1]
    try:
        relative = Path(script).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return False
    return bool(re.fullmatch(r'(?:scripts|skills/[a-z-]+/scripts)/[a-zA-Z0-9_/-]+\.py', relative)) and Path(script).is_file()


def decision(event: dict) -> dict:
    if event.get('hook_event_name') == 'SessionStart':
        return {'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': (
            'Senior Associate local research privacy hook is loaded. For Senior Associate matters, read the packaged '
            'docs/CHATGPT-RUNTIME.md. Before every outgoing research request call check_research_query with its exact '
            'input. Hosted web tools are not intercepted by this hook. Never send client documents or identifiers '
            'to research services. Runs execute in the local chat, and their exact leases must be released when done.'
        )}}
    name = str(event.get('tool_name', ''))
    if event.get('hook_event_name') != 'PreToolUse' or name in LOCAL_TOOLS or OWN_METHODS.fullmatch(name):
        return {}
    try:
        ctx = context()
        if not ctx.matters_root.exists():
            return {}
        for matter in ctx.matters_root.iterdir():
            if not matter.is_dir() or matter.name.startswith('.') or matter.is_symlink():
                continue
            if lease_is_unattended(read_lease(matter)):
                if name in {'Bash', 'exec_command', 'functions.exec_command'}:
                    return {} if local_command(event.get('tool_input', {})) else denied(UNKNOWN)
                if not research_tool(name):
                    return denied(UNKNOWN)
                query = json.dumps(event.get('tool_input', {}), ensure_ascii=False)
                if contains_private(query, checked_terms(matter)):
                    return denied(BLOCKED)
    except Exception:
        return denied(UNCHECKED)
    return {}


def denied(reason: str) -> dict:
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                   'permissionDecisionReason': reason}}


def main():
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise ValueError()
        output = decision(event)
    except Exception:
        output = denied(UNCHECKED)
    print(json.dumps(output))

if __name__ == '__main__':
    main()

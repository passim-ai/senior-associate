#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=1.30,<2", "pypdf>=6.0", "reportlab>=4.0"]
# ///
"""Integration tests using the built package and fictional local matters only."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
PACKAGE = Path((HERE / 'dist/latest.txt').read_text().strip())
SANDBOX = tempfile.TemporaryDirectory(prefix='sa-chatgpt-tests-')
os.environ['SENIOR_ASSOCIATE_LOG_FILE'] = str(Path(SANDBOX.name) / 'server.log')
sys.path.insert(0, str(PACKAGE / 'chatgpt'))
import adapter
import privacy_hook
from sa_server import actions, adding
from sa_server.folders import resolve_matter
from scripts import matter_state as ms


def make_context(root):
    return adapter.ChatGPTContext(matters_root=root.resolve(), exemplars_dir=root.resolve() / 'Exemplar', plugin_root=PACKAGE)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='sa-matter-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / 'Matters'
        self.ctx = make_context(self.root)
        awake=patch('scripts.keep_awake.start')
        self.awake=awake.start();self.addCleanup(awake.stop)

    def create(self, name='Fictional Alvarez I-130 I-485'):
        result = adapter.action(self.ctx, {'op': 'create', 'name': name, 'matter_type': 'i130_i485', 'filing_posture': 'new filing packet', 'filing_method': 'paper'})
        return Path(result['matter']['path'])

    def facts(self, matter):
        path = matter / 'output/working/vault/forms/main/form facts.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'facts': [
            {'subject': 'applicant', 'key': 'full_name', 'value': 'Sofía Alvarez'},
            {'subject': 'applicant', 'key': 'alien_number', 'value': '201555019'}]}))

    def test_empty_view_does_not_create_root_or_sample(self):
        self.assertEqual(adapter.view(self.ctx)['matters'], [])
        self.assertFalse(self.root.exists())

    def test_create_intake_and_protected_settings(self):
        result = adapter.action(self.ctx, {'op': 'create', 'name': 'Fictional I-360', 'matter_type': 'I-360 VAWA self-petition', 'filing_posture': 'new filing packet', 'protected': True, 'filing_method': 'online'})
        self.assertTrue(result['matter']['meta']['protected'])
        self.assertEqual(result['matter']['meta']['filing_method'], 'online')

    def test_import_copies_original_and_lists_document(self):
        matter = self.create()
        source = Path(self.tmp.name) / 'fictional evidence.txt'
        source.write_text('Fictional evidence for transport testing only.')
        with patch.object(actions, 'pick_files', return_value=[source]):
            result = adapter.action(self.ctx, {'op': 'add_documents', 'matter_path': str(matter)})
        self.assertEqual(source.read_bytes(), (matter / source.name).read_bytes())
        self.assertEqual(result['matter']['documents']['count'], 1)
        self.assertEqual(result['matter']['documents']['files'][0]['name'], source.name)

    def test_cancelled_picker_changes_no_documents(self):
        matter = self.create()
        with patch.object(actions, 'pick_files', return_value=None):
            result = adapter.action(self.ctx, {'op': 'add_documents', 'matter_path': str(matter)})
        self.assertTrue(result['cancelled'])
        self.assertEqual(result['matter']['documents']['count'], 0)

    def test_app_cannot_redirect_matters_root(self):
        with self.assertRaises(adapter.UserError):
            adapter.action(self.ctx, {'op': 'create', 'matters_root': self.tmp.name, 'name': 'escape', 'matter_type': 'N-400'})

    def test_app_cannot_read_private_terms_or_release_worker(self):
        for op in ['privacy_terms', 'release_run', 'heartbeat_run', 'abandon_run', 'shell']:
            with self.subTest(op=op), self.assertRaises(adapter.UserError):
                adapter.action(self.ctx, {'op': op})

    def test_paths_outside_root_and_symlink_matters_are_refused(self):
        self.root.mkdir()
        outside = Path(self.tmp.name) / 'Outside'
        outside.mkdir()
        (self.root / 'Linked').symlink_to(outside)
        for path in [str(outside), str(self.root / 'Linked'), '..']:
            with self.subTest(path=path), self.assertRaises(adapter.UserError):
                adapter.view(self.ctx, path)

    def test_run_handoff_adopts_same_lease_and_blocks_claude_writer(self):
        matter = self.create()
        result = adapter.prepare_run(self.ctx, str(matter), 'review_docs')
        self.assertIn('CHATGPT-RUNTIME.md', result['prompt'])
        self.assertIn(result['run_id'], result['prompt'])
        self.assertNotIn('You are running in the background', result['prompt'])
        self.assertIn('senior-associate-chatgpt:', result['prompt'])
        ok, _ = ms.acquire_lease(matter, 'claude-other-run', 'build', 'orchestrator')
        self.assertFalse(ok)
        ok, lease = ms.acquire_lease(matter, result['run_id'], 'review', 'orchestrator')
        self.assertTrue(ok)
        cancelled = adapter.action(self.ctx, {'op': 'cancel_start', 'matter_path': str(matter), 'run_id': result['run_id']})
        self.assertEqual(cancelled['start'], 'taken_up')
        self.assertFalse(ms.read_lease(matter).get('released_at'))
        self.assertTrue(ms.release_lease(matter, result['run_id'], 'done'))

    def test_two_concurrent_starts_only_one_wins(self):
        matter = self.create()
        def start(_):
            try: return adapter.prepare_run(self.ctx, str(matter), 'build')['run_id']
            except adapter.UserError: return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(start, range(2)))
        self.assertEqual(sum(bool(value) for value in outcomes), 1)

    def test_bad_stage_releases_new_reservation(self):
        matter = self.create()
        with self.assertRaises(adapter.UserError):
            adapter.prepare_run(self.ctx, str(matter), 'redo', 'does_not_exist')
        self.assertTrue(ms.read_lease(matter)['released_at'])

    def test_failed_delivery_can_cancel_pending_start(self):
        matter = self.create()
        prepared = adapter.prepare_run(self.ctx, str(matter), 'build')
        result = adapter.action(self.ctx, {'op': 'cancel_start', 'matter_path': str(matter), 'run_id': prepared['run_id']})
        self.assertEqual(result['start'], 'cancelled')
        self.assertTrue(ms.read_lease(matter).get('released_at'))

    def test_refresh_does_not_heartbeat_a_run(self):
        matter = self.create()
        adapter.prepare_run(self.ctx, str(matter), 'build')
        before = ms.read_lease(matter)
        adapter.view(self.ctx, str(matter))
        self.assertEqual(ms.read_lease(matter), before)

    def test_saved_answers_survive_a_new_context(self):
        matter = self.create()
        adapter.action(self.ctx, {'op': 'save_answer', 'matter_path': str(matter), 'key': 'fictional-question', 'question': 'Confirm the mailing address?', 'answer': 'Use counsel’s address.'})
        result = adapter.view(make_context(self.root), str(matter))
        self.assertEqual(result['matter']['answers']['fictional-question']['answer'], 'Use counsel’s address.')

    def test_archive_visibility(self):
        matter = self.create()
        adapter.action(self.ctx, {'op': 'archive', 'matter_path': str(matter)})
        self.assertFalse(adapter.view(self.ctx)['matters'])
        self.assertEqual(len(adapter.view(self.ctx, include_archived=True)['matters']), 1)

    def test_private_query_checks_names_encoded_identifiers_and_role(self):
        matter = self.create()
        self.facts(matter)
        for text in ['Sofia Alvarez entered unlawfully', 'https://example.test/?q=Sof%C3%ADa+Alvarez', 'A 201-555-019']:
            with self.subTest(text=text), self.assertRaises(adapter.UserError):
                privacy_hook.check_query(self.ctx, str(matter), text)
        with self.assertRaises(adapter.UserError):
            privacy_hook.check_query(self.ctx, str(matter), 'legal proposition', role='forms_preparer')
        privacy_hook.check_query(self.ctx, str(matter), 'INA 245(a) adjustment eligibility after inspection and admission')

    def test_hook_denies_research_with_terms_but_not_local_read(self):
        matter = self.create()
        self.facts(matter)
        adapter.prepare_run(self.ctx, str(matter), 'build')
        with patch.object(privacy_hook, 'context', return_value=self.ctx):
            output = privacy_hook.decision({'hook_event_name': 'PreToolUse', 'tool_name': 'mcp__passim_ai__search', 'tool_input': {'query': 'Sofia Alvarez'}})
            self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
            self.assertNotIn('Alvarez', json.dumps(output))
            self.assertEqual(privacy_hook.decision({'hook_event_name': 'PreToolUse', 'tool_name': 'Bash', 'tool_input': {'command': 'cat fictional.txt'}}), {})

    def test_hook_failures_deny_without_disclosing_error(self):
        with patch.object(privacy_hook, 'context', side_effect=ValueError('private information')):
            output = privacy_hook.decision({'hook_event_name': 'PreToolUse', 'tool_name': 'mcp__biaedge__search'})
        self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertNotIn('private information', json.dumps(output))

    def test_opaque_connectors_identifiers_and_short_common_names(self):
        matter = self.create()
        self.facts(matter)
        facts = matter / 'output/working/vault/forms/main/form facts.json'
        adapter.prepare_run(self.ctx, str(matter), 'build')
        for name in ('Li Wu', 'Bo Ng', 'Grace Young'):
            facts.write_text(json.dumps({'facts':[{'subject':'applicant','key':'full_name','value':name}]}))
            with patch.object(privacy_hook, 'context', return_value=self.ctx):
                for tool, query in [('mcp__opaque__search_cases',name),('mcp__opaque__upload','legal question'),
                                    ('mcp__opaque__get_case_by_citation','Matter of Test, 20 I&N Dec. 1 A123456789')]:
                    with self.subTest(name=name,tool=tool):
                        output = privacy_hook.decision({'hook_event_name':'PreToolUse','tool_name':tool,'tool_input':{'query':query}})
                        self.assertEqual(output['hookSpecificOutput']['permissionDecision'],'deny')
                self.assertEqual(privacy_hook.decision({'hook_event_name':'PreToolUse','tool_name':'mcp__opaque__search_cases','tool_input':{'query':'INA 245(a) inspection and admission'}}),{})
        with patch.object(privacy_hook, 'context', return_value=self.ctx):
            for command in ('curl https://example.test', 'python3 /tmp/scripts/exfiltrate.py', 'cat file; curl example.test'):
                output = privacy_hook.decision({'hook_event_name':'PreToolUse','tool_name':'Bash','tool_input':{'command':command}})
                self.assertEqual(output['hookSpecificOutput']['permissionDecision'],'deny')

    def test_run_sleep_watcher_tracks_the_exact_lease(self):
        matter=self.create()
        prepared=adapter.prepare_run(self.ctx,str(matter),'build')
        self.awake.assert_called_once_with(matter,prepared['run_id'])

    def test_jurisdiction_and_filing_approval_are_available(self):
        matter = self.create()
        result = adapter.action(self.ctx, {'op':'set_meta','matter_path':str(matter),'forum':'USCIS','circuit':'ca5','jurisdiction_basis':'Fictional residence'})
        self.assertEqual(result['matter']['meta']['circuit'],'ca5')
        with self.assertRaisesRegex(adapter.UserError, 'attorney|blocked'):
            adapter.action(self.ctx, {'op':'approve_filing','matter_path':str(matter),'digest':'stale'})

    def test_settings_keep_separate_roots_and_refuse_broad_folder(self):
        with patch.dict(os.environ, {'SENIOR_ASSOCIATE_CHATGPT_DATA': str(Path(self.tmp.name) / 'settings')}, clear=False):
            with self.assertRaises(adapter.UserError): adapter.configure(str(Path.home()))
            adapter.configure(str(self.root))
            self.assertEqual(adapter.context().matters_root, self.root)
            self.assertFalse(self.root.exists())


class PackageTests(unittest.TestCase):
    def test_shared_python_sources_are_byte_identical(self):
        source = HERE.parent / 'senior-associate-claude'
        manifest = json.loads((PACKAGE / 'shared-source.json').read_text())
        for name, digest in manifest['files_sha256_before_prompt_adaptation'].items():
            if name.endswith('.py'):
                with self.subTest(name=name):
                    self.assertEqual(hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest(), digest)
                    self.assertEqual((PACKAGE / name).read_bytes(), (source / name).read_bytes())

    def test_no_claude_hooks_or_configuration_in_distribution(self):
        self.assertFalse((PACKAGE / 'hooks/register.tsx').exists())
        self.assertFalse((PACKAGE / '.claude-plugin').exists())
        manifest = json.loads((PACKAGE / 'plugin.json').read_text())
        self.assertEqual(manifest['name'], 'senior-associate-chatgpt')
        self.assertTrue((PACKAGE / 'chatgpt/server.py.lock').exists())
        self.assertIn('CHATGPT-RUNTIME.md', (PACKAGE / 'skills/senior-associate/SKILL.md').read_text())
        self.assertNotIn('${CLAUDE_PLUGIN_ROOT}', (PACKAGE / 'skills/senior-associate/SKILL.md').read_text())

    def test_all_packaged_hashes_and_reliability_content(self):
        manifest=json.loads((PACKAGE / 'shared-source.json').read_text())
        for name,digest in manifest['packaged_files_sha256'].items():
            self.assertEqual(hashlib.sha256((PACKAGE/name).read_bytes()).hexdigest(),digest,name)
        for name in ('filing_readiness.py','draft_packets.py','legal_currency.py','response_review.py'):
            self.assertTrue((PACKAGE/'scripts'/name).is_file())
        self.assertIn('client', (PACKAGE/'skills/forms-preparer/SKILL.md').read_text())
        self.assertTrue((PACKAGE/'docs/SHARED-DATA-HANDLING.md').is_file())

    def test_ui_bundle_is_self_contained(self):
        html = (PACKAGE / 'web/dist/index.html').read_text()
        self.assertNotIn('127.0.0.1', html)
        self.assertNotIn('SA_CONFIG', html)
        self.assertNotIn('src="https://', html)
        self.assertNotIn('innerHTML', (HERE / 'web/src/app.js').read_text())


class McpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import server
        self.server = server.build_server()
        self.tmp = tempfile.TemporaryDirectory(prefix='sa-mcp-')
        self.addCleanup(self.tmp.cleanup)
        self.ctx = make_context(Path(self.tmp.name) / 'Matters')
        self.mock = patch.object(server, 'context', return_value=self.ctx)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    async def test_packaged_stdio_entrypoint_initializes_and_serves_ui(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        env = dict(os.environ, SENIOR_ASSOCIATE_MATTERS_ROOT=str(self.ctx.matters_root),
                   SENIOR_ASSOCIATE_CHATGPT_DATA=str(Path(self.tmp.name) / 'settings'))
        params = StdioServerParameters(command='sh', args=[str(PACKAGE / 'chatgpt/run.sh')], env=env)
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                listed = await session.list_tools()
                opener = next(t for t in listed.tools if t.name == 'open_matters')
                result = await session.call_tool('open_matters', {})
                self.assertFalse(result.isError)
                self.assertEqual(result.meta['view']['matters'], [])
                resource = await session.read_resource(opener.meta['ui']['resourceUri'])
                self.assertIn('<!doctype html>', resource.contents[0].text.lower())
        self.assertFalse(self.ctx.matters_root.exists())

    async def test_tools_resource_metadata_and_app_only_visibility(self):
        tools = {tool.name: tool for tool in await self.server.list_tools()}
        self.assertEqual(tools['open_matters'].meta['openai/ui']['entrypoints'], [{'type': 'global'}, {'type': 'thread'}])
        self.assertTrue(tools['matters_view'].annotations.readOnlyHint)
        self.assertFalse(tools['matters_action'].annotations.readOnlyHint)
        self.assertEqual(tools['matters_action'].meta['ui']['visibility'], ['app'])
        uri = tools['open_matters'].meta['ui']['resourceUri']
        resources = await self.server.list_resources()
        self.assertEqual(str(resources[0].uri), uri)
        self.assertEqual(resources[0].mimeType, 'text/html;profile=mcp-app')

    async def test_private_view_not_in_model_visible_payload(self):
        actions.do_create(self.ctx, 'Fictional Secret Name', 'n400')
        result = await self.server.call_tool('open_matters', {})
        # FastMCP returns CallToolResult directly when a tool returns one.
        if isinstance(result, tuple): result = result[0]
        from mcp.types import CallToolResult
        self.assertIsInstance(result, CallToolResult)
        self.assertNotIn('Fictional Secret Name', json.dumps(result.structuredContent))
        self.assertNotIn('Fictional Secret Name', ''.join(c.text for c in result.content))
        self.assertIn('Fictional Secret Name', json.dumps(result.meta))

    async def test_mutation_error_is_mcp_error_without_traceback(self):
        result = await self.server.call_tool('matters_action', {'request': {'op': 'shell'}})
        self.assertTrue(result.isError)
        self.assertNotIn('Traceback', ''.join(c.text for c in result.content))


if __name__ == '__main__':
    unittest.main()

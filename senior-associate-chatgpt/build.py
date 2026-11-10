#!/usr/bin/env python3
"""Assemble a self-contained desktop plugin without editing the Claude distribution.

Run npm ci && npm run build in web/ first. Every build creates a new directory.
Shared Python files are copied byte-for-byte; only generated prompt Markdown is
adapted to the host. No client folders, credentials, hooks, or Claude settings
are copied. A source manifest records the reused engine for review.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil
import time

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'senior-associate-claude'
EXCLUDE = shutil.ignore_patterns('node_modules', '__pycache__', '*.pyc', '.DS_Store', '.pytest_cache', 'tests', 'test_*')


def adapt_markdown(text: str) -> str:
    return text.replace('${CLAUDE_PLUGIN_ROOT}', '${PLUGIN_ROOT}').replace('senior-associate:', 'senior-associate-chatgpt:')


def build() -> Path:
    if not (HERE / 'web/dist/index.html').is_file():
        raise SystemExit('Build the web component first: cd web && npm ci && npm run build')
    output = HERE / 'dist' / f'build-{time.time_ns()}' / 'senior-associate-chatgpt'
    output.mkdir(parents=True)
    copied = {}
    for name in ('scripts', 'skills', 'agents', 'samples'):
        shutil.copytree(SOURCE / name, output / name, ignore=EXCLUDE)
    shutil.copytree(SOURCE / 'server/sa_server', output / 'server/sa_server', ignore=EXCLUDE)
    for path in output.rglob('*'):
        if path.is_file():
            copied[str(path.relative_to(output))] = hashlib.sha256(path.read_bytes()).hexdigest()
    for path in (output / 'skills').rglob('*.md'):
        path.write_text(adapt_markdown(path.read_text()))
    for path in (output / 'agents').glob('*.md'):
        text = adapt_markdown(path.read_text())
        if text.startswith('---\n'):
            text = text.split('---', 2)[2].lstrip()
        path.write_text(text)
    for name in ('plugin.json', 'mcp.json'):
        shutil.copy2(HERE / name, output / name)
    # Compatibility manifest for desktop runtimes that discover hooks through this path.
    portable = json.loads((output / 'plugin.json').read_text())
    compatibility = {'name': portable['name'], 'version': portable['version'],
                     **portable['extensions']['com.openai'], 'hooks': './hooks/hooks.json'}
    (output / '.codex-plugin').mkdir()
    (output / '.codex-plugin/plugin.json').write_text(json.dumps(compatibility, indent=2) + '\n')
    shutil.copy2(SOURCE / 'LICENSE', output / 'LICENSE')
    shutil.copytree(HERE / 'chatgpt', output / 'chatgpt', ignore=EXCLUDE)
    (output / 'hooks').mkdir()
    shutil.copy2(HERE / 'chatgpt/hooks.json', output / 'hooks/hooks.json')
    shutil.copytree(HERE / 'web/dist', output / 'web/dist')
    (output / 'web/licenses').mkdir()
    for license_path in (HERE / 'web/src/assets').glob('*OFL.txt'):
        shutil.copy2(license_path, output / 'web/licenses' / license_path.name)
    shutil.copytree(HERE / 'docs', output / 'docs')
    for name in ('DATA-HANDLING.md', 'VERIFICATION.md'):
        shutil.copy2(SOURCE / 'docs' / name, output / 'docs' / ('SHARED-' + name))
    shutil.copy2(HERE / 'README.md', output / 'README.md')
    for name in ('senior-associate', 'matter-chat'):
        path = output / f'skills/{name}/SKILL.md'
        text = path.read_text()
        frontmatter_end = text.index('---', 3) + 3
        note = '\n\n## ChatGPT desktop execution\n\nBefore working, read `${PLUGIN_ROOT}/docs/CHATGPT-RUNTIME.md`. Its host adapter rules replace Claude-specific launch, agent, and setup instructions; all evidence, lease, artifact, review, and privacy gates remain required.\n'
        path.write_text(text[:frontmatter_end] + note + text[frontmatter_end:])
    shutil.copy2(HERE / 'docs/SETUP-SKILL.md', output / 'skills/setup/SKILL.md')
    manifest = json.loads((SOURCE / '.claude-plugin/plugin.json').read_text())
    (output / 'shared-source.json').write_text(json.dumps({'version': manifest['version'], 'files_sha256_before_prompt_adaptation': copied,
        'packaged_files_sha256': {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(output.rglob('*')) if p.is_file()}}, indent=2) + '\n')
    marketplace = {
        'name': 'senior-associate-chatgpt-local', 'interface': {'displayName': 'Senior Associate for ChatGPT'},
        'plugins': [{'name': 'senior-associate-chatgpt', 'source': {'source': 'local', 'path': './senior-associate-chatgpt'},
                     'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_INSTALL'},
                     'category': 'Productivity'}]
    }
    catalog = output.parent / '.agents/plugins/marketplace.json'
    catalog.parent.mkdir(parents=True)
    catalog.write_text(json.dumps(marketplace, indent=2) + '\n')
    (HERE / 'dist/latest.txt').write_text(str(output) + '\n')
    print(output)
    return output

if __name__ == '__main__':
    build()

#!/usr/bin/env python3
"""Download and verify a candidate in a new directory. Never replace an installed plugin."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
from datetime import datetime, timezone

REPO = 'https://github.com/passim-ai/senior-associate.git'


def stage(parent: Path, ref: str) -> Path:
    if not ref or ref.startswith('-'):
        raise ValueError('Use a branch, tag, or commit, not an option.')
    parent.mkdir(parents=True, exist_ok=True)
    candidate = Path(tempfile.mkdtemp(prefix='packet-builder-candidate-', dir=parent))
    receipt = {'repository': REPO, 'requested_ref': ref, 'started_at': datetime.now(timezone.utc).isoformat(), 'status': 'failed'}
    try:
        subprocess.run(['git', 'clone', '--no-checkout', REPO, str(candidate)], check=True)
        subprocess.run(['git', '-C', str(candidate), 'checkout', '--detach', ref], check=True)
        receipt['commit'] = subprocess.check_output(['git','-C',str(candidate),'rev-parse','HEAD'], text=True).strip()
        with (candidate/'candidate-checks.log').open('w') as log:
            result = subprocess.run(['bash','scripts/check.sh'], cwd=candidate/'senior-associate-claude', stdout=log, stderr=subprocess.STDOUT)
        receipt['status'] = 'passed' if result.returncode == 0 else 'failed'
        receipt['check_exit_code'] = result.returncode
    finally:
        (candidate/'candidate-verification.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return candidate


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--ref',default='origin/main')
    args=parser.parse_args()
    candidate=stage(args.directory.expanduser(),args.ref)
    print(candidate)
    result=json.loads((candidate/'candidate-verification.json').read_text())
    raise SystemExit(0 if result['status']=='passed' else 1)

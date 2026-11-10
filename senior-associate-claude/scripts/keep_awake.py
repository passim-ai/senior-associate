"""Bounded macOS idle-sleep assertion for one existing run; never starts or renews work."""
from __future__ import annotations
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.matter_state import read_lease, lease_is_fresh

MAX_SECONDS = 6 * 60 * 60


def watch(matter: Path, run_id: str) -> None:
    if sys.platform != 'darwin' or not Path('/usr/bin/caffeinate').exists():
        return
    child = None
    end = time.monotonic() + MAX_SECONDS
    try:
        while time.monotonic() < end:
            lease = read_lease(matter)
            if not lease or lease.get('run_id') != run_id or not lease_is_fresh(lease):
                break
            if child is None:
                child = subprocess.Popen(['/usr/bin/caffeinate', '-i', '-t', str(MAX_SECONDS)],
                                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(15)
    finally:
        if child is not None:
            child.terminate()
            child.wait(timeout=5)


def start(matter: Path, run_id: str) -> None:
    if sys.platform == 'darwin':
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), str(matter), run_id],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)


if __name__ == '__main__':
    watch(Path(sys.argv[1]), sys.argv[2])

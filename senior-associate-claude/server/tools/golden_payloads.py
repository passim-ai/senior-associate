#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Golden payloads for the app's tests: the real server (server/cli.py) run against fictional matters, one in each
state the app draws, with the answers written to <out>/payload-<name>.json.

    uv run --script server/tools/golden_payloads.py [--out tests/fixtures]

Every matter, name and file here is made up. The clock is fixed (SENIOR_ASSOCIATE_FIXED_NOW) and what the file
system decides (a file's modified time, the temporary folder's path, a run's random id) is replaced with a fixed
value, so running it twice writes the same files.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parents[1]
CLI = PLUGIN_ROOT / "server" / "cli.py"

NOW = "2026-10-28T15:00:00+00:00"
SHOWN_ROOT = "/Users/example/Matters"
FILE_TIME = "2026-10-20T12:00:00+00:00"
FULL = ["docs_review", "forms_preparer", "forms_reviewer", "cover_letter_writer_draft", "cover_letter_researcher",
        "cover_letter_writer_integrate", "cover_letter_reviewer", "packet_assembly", "final_review", "attorney_handoff"]
# Values the file system or a random id decides, replaced so the output is the same every time.
FILE_TIME_KEYS = {"modified", "last_added", "generated"}
RUN_ID_RE = re.compile(r"\b[0-9a-f]{32}\b")
ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})")


def write(path: Path, content: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if isinstance(content, str) else json.dumps(content, indent=2), encoding="utf-8")


def state(matter: Path, statuses: dict[str, str], *, matter_type: str = "I-130/I-485 immediate relative packet",
          blockers: list[dict[str, Any]] | None = None) -> None:
    stages = {}
    for i, sid in enumerate(FULL):
        status = statuses.get(sid, "pending")
        stamp = f"2026-10-28T1{min(i, 4)}:0{i % 10}:00+00:00"
        stages[sid] = {"status": status, "started_at": stamp if status != "pending" else None,
                       "completed_at": stamp if status in {"passed", "skipped"} else None}
    write(matter / "output/working/workflow/matter_status.json", {
        "matter": {"matter_type": matter_type, "filing_posture": "new filing packet", "deliverable": "packet",
                   "workflow_key": "full_packet"},
        "required_stage_ids": FULL, "stages": stages, "blockers": blockers or [],
        "created_at": "2026-10-27T09:00:00+00:00", "updated_at": "2026-10-28T14:00:00+00:00"})


def ledger(matter: Path, items: list[dict[str, Any]], packet_status: str = "draft") -> None:
    write(matter / "output/deliverables/open-items.json",
          {"schema_version": 2, "updated_at": "2026-10-28T14:00:00+00:00", "packet_status": packet_status, "items": items})


DECISION = {"id": "decide-i765", "type": "attorney_decision", "title": "File an I-765 with the I-485?",
            "question": "Include an I-765 work permit application with the I-485?",
            "recommendation": "Yes, if the client wants to work while the I-485 is pending.",
            "detail": "There is no work authorization now. The I-765 has its own fee.", "blocks_filing": True, "status": "open",
            "stage": "docs_review"}
I94 = {"id": "doc-i94", "type": "client_document", "title": "The I-94 arrival record", "detail": "Proves the admission.",
       "blocks_filing": True, "status": "open", "who": "client", "stage": "docs_review"}
SIGN = {"id": "action-sign", "type": "attorney_action", "title": "Sign the G-28", "detail": "", "blocks_filing": True,
        "status": "resolved", "resolution": "Signed at the office."}
RISK = {"id": "risk-gap", "type": "risk", "title": "Joint records start two months before filing",
        "detail": "An officer may ask for more.", "blocks_filing": False, "status": "open"}
FINDINGS = {"findings": [
    {"id": "1", "summary": "Joint lease is missing a page", "severity": "high", "owner": "client", "outcome": "rfe_likely"},
    {"id": "2", "summary": "Date format on the I-130", "severity": "low", "owner": "attorney_handoff"},
    {"id": "3", "summary": "Merits are sound", "severity": "note", "outcome": "approvable"},
]}


def build_matters(root: Path) -> dict[str, str]:
    """The fictional matters, by the name of the payload each one gives."""
    m: dict[str, str] = {}

    def matter(name: str, *docs: str) -> Path:
        path = root / name
        for doc in docs:
            write(path / doc, f"%PDF fictional {doc}")
        return path

    matter("Avery New I-130").mkdir(parents=True)
    m["new"] = "Avery New I-130"

    matter("Blake Ready I-751", "Marriage certificate.pdf", "Lease.pdf")
    m["ready"] = "Blake Ready I-751"

    reviewed = matter("Casey Reviewed I-130 I-485", "Passport.pdf", "Birth certificate.pdf")
    state(reviewed, {"docs_review": "passed"})
    ledger(reviewed, [DECISION, I94])
    write(reviewed / "output/working/workflow/attorney-answers.json",
          {"answers": {"decide-i765": {"question": DECISION["question"], "answer": "Yes.", "saved_at": "2026-10-28T14:30:00+00:00"}}})
    m["reviewed"] = reviewed.name

    building = matter("Drew Building I-130 I-485", "Passport.pdf")
    state(building, {"docs_review": "passed", "forms_preparer": "passed", "forms_reviewer": "in_progress",
                     "cover_letter_writer_draft": "in_progress"})
    write(building / "output/working/workflow/run-lease.json", {
        "run_id": "0" * 32, "kind": "build", "holder": "orchestrator", "description": "Building the packet",
        "started_at": "2026-10-28T14:10:00+00:00", "heartbeat_at": "2026-10-28T14:58:00+00:00", "stage": "forms_reviewer",
        "released_at": "", "outcome": ""})
    m["building"] = building.name

    paused = matter("Emery Paused I-130", "Passport.pdf")
    state(paused, {"docs_review": "passed", "forms_preparer": "in_progress"})
    write(paused / "output/working/workflow/run-lease.json", {
        "run_id": "1" * 32, "kind": "build", "holder": "app", "description": "Building the packet",
        "started_at": "2026-10-28T11:00:00+00:00", "heartbeat_at": "2026-10-28T11:20:00+00:00", "stage": "forms_preparer",
        "released_at": "", "outcome": ""})
    m["paused"] = paused.name

    needs = matter("Finley Needs N-400", "Green card.pdf")
    state(needs, {sid: "passed" for sid in FULL}, matter_type="N-400 naturalization packet")
    ledger(needs, [DECISION, SIGN, RISK])
    write(needs / "output/working/vault/review/final review findings.json", FINDINGS)
    write(needs / "output/deliverables/Finley Needs N-400 Packet.pdf", "%PDF packet")
    m["needs_you"] = needs.name

    waiting = matter("Gray Waiting I-130 I-485", "Passport.pdf")
    state(waiting, {sid: "passed" for sid in FULL})
    ledger(waiting, [I94, SIGN])
    write(waiting / "output/deliverables/Gray Waiting I-130 I-485 Packet.pdf", "%PDF packet")
    m["waiting_client"] = waiting.name

    draft = matter("Harper Draft I-751", "Lease.pdf")
    state(draft, {sid: "passed" for sid in FULL}, matter_type="I-751 joint petition to remove conditions")
    ledger(draft, [I94, dict(RISK, blocks_filing=True)])
    write(draft / "output/deliverables/Harper Draft I-751 Packet.pdf", "%PDF packet")
    write(draft / "output/deliverables/Attorney Memo.md", "# Memo\n\nDraft packet.")
    write(draft / "output/deliverables/Client Request.md", "Please send the I-94.")
    write(draft / "output/deliverables/Client Request (Spanish).md", "Por favor envíe el I-94.")
    m["draft"] = draft.name

    complete = matter("Indigo Ready I-130", "Passport.pdf")
    state(complete, {sid: "passed" for sid in FULL})
    ledger(complete, [SIGN], packet_status="ready_to_file")
    for name in ("Indigo Ready I-130 Packet.pdf", "Filing Checklist.pdf", "Attorney Memo.md"):
        write(complete / "output/deliverables" / name, "%PDF")
    write(complete / "output/deliverables/Forms/I-130.pdf", "%PDF form")
    sys.path.insert(0, str(HERE))
    from filing_fixture import approve_fixture
    approve_fixture(complete, [{"id": sid, "status": "passed"} for sid in FULL], {"packet_status": "ready_to_file", "open": []})
    m["complete"] = complete.name

    filed = matter("Jordan Filed I-765", "EAD.pdf")
    state(filed, {sid: "passed" for sid in FULL}, matter_type="I-765 employment authorization packet")
    ledger(filed, [], packet_status="ready_to_file")
    write(filed / "output/deliverables/filed.json", {"filed_at": "2026-10-27T16:00:00+00:00"})
    m["filed"] = filed.name

    damaged = matter("Kai Damaged I-130", "Passport.pdf")
    state(damaged, {sid: "passed" for sid in FULL})
    write(damaged / "output/deliverables/open-items.json", '{"packet_status": "ready_to_file", "items": [,]}')
    m["damaged"] = damaged.name

    protected = matter("Lane I-360 I-485", "Passport.pdf")
    state(protected, {"docs_review": "passed"}, matter_type="I-360/I-485 VAWA self-petition and adjustment packet")
    write(protected / "output/working/workflow/matter-meta.json", {"protected": True, "protected_reason": "catalog"})
    m["protected"] = protected.name

    archived = matter("Morgan Archived I-131", "Passport.pdf")
    write(archived / "output/working/workflow/matter-meta.json", {"archived_at": "2026-10-01T00:00:00+00:00"})
    m["archived"] = archived.name
    return m


def normalize(value: Any, root: str, key: str = "") -> Any:
    if isinstance(value, dict):
        return {k: normalize(v, root, k) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v, root, key) for v in value]
    if isinstance(value, str):
        if key in FILE_TIME_KEYS and value:
            return FILE_TIME
        # Every time the fixtures set is at or before NOW; a later one came from the file system's clock.
        if ISO_RE.fullmatch(value) and value > NOW:
            return FILE_TIME
        value = value.replace(root, SHOWN_ROOT)
        return RUN_ID_RE.sub("<run-id>", value)
    return value


def run(request: dict[str, Any], root: Path) -> dict[str, Any]:
    env = {**os.environ, "SENIOR_ASSOCIATE_FIXED_NOW": NOW, "SENIOR_ASSOCIATE_MATTERS_ROOT": str(root),
           "SENIOR_ASSOCIATE_EXEMPLARS_DIR": str(root / "Exemplar"), "HOME": str(root.parent)}
    env.setdefault("SENIOR_ASSOCIATE_LOG_FILE", str(root.parent / "server.log"))
    result = subprocess.run([sys.executable, str(CLI), json.dumps({"matters_root": str(root), **request})],
                            capture_output=True, text=True, timeout=120, env=env, cwd=str(root.parent))
    return json.loads(result.stdout.strip().splitlines()[-1])


def generate(out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with TemporaryDirectory() as tmp:
        root = (Path(tmp).resolve() / "Matters")
        root.mkdir()
        matters = build_matters(root)
        # The doctor's answer depends on this Mac's tools; the payloads shouldn't.
        payloads: dict[str, dict[str, Any]] = {
            "list": run({"op": "list"}, root),
            "list-with-archived": run({"op": "list", "include_archived": True}, root),
            "state-home": run({"op": "state", "auto_select": False}, root),
        }
        for phase, name in matters.items():
            payloads[f"matter-{phase}"] = run({"op": "state", "matter_path": name, "auto_select": False}, root)
        payloads["start-run"] = run({"op": "start_run", "matter": matters["ready"], "kind": "build"}, root)
        payloads["error-moved"] = run({"op": "state", "matter_path": "Nobody Here I-130"}, root)
        for name, payload in payloads.items():
            payload.pop("setup", None)
            path = out / f"payload-{name}.json"
            path.write_text(json.dumps(normalize(payload, str(root)), indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
            written.append(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", default=str(PLUGIN_ROOT / "tests" / "fixtures"), help="folder for payload-*.json")
    args = parser.parse_args()
    for path in generate(Path(args.out)):
        print(path)


if __name__ == "__main__":
    main()

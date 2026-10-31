#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Offline tests for the workflow runtime: the final review, change tracking for re-reviews, short command output,
and protected (VAWA) matters. Every matter here is synthetic.

    uv run --script skills/senior-associate/scripts/tests/test_workflow_runtime.py
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
import unittest.mock

SCRIPTS = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = SCRIPTS.parents[2]
RW = SCRIPTS / "run_matter_workflow.py"
SECURE_STAGE = PLUGIN_ROOT / "scripts" / "secure_stage.py"
sys.path.insert(0, str(PLUGIN_ROOT))
sys.path.insert(0, str(SCRIPTS))

import matter_workflow as mw  # noqa: E402

INTAKE = ["--matter-type", "I-130/I-485 immediate relative packet", "--filing-posture", "new filing packet", "--deliverable", "packet"]
V = "output/working/vault"


def run(*args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([sys.executable, *args], capture_output=True, text=True, timeout=120)
    if ok and result.returncode != 0:
        raise AssertionError(f"{args[1:3]} failed ({result.returncode}): {result.stderr or result.stdout}")
    return result


def rw(*args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
    return run(str(RW), *args, ok=ok)


def write(path: Path, content: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2) if not isinstance(content, str) else content, encoding="utf-8")
    return path


# The artifacts each stage needs to pass, written fresh by `produce`.
STAGE_ARTIFACTS: dict[str, dict[str, object]] = {
    "docs_review": {
        f"{V}/docs-review/main/docs review memo.md": "# Docs review\n",
        f"{V}/docs-review/main/document inventory.json": {"documents": [{"name": "Passport.pdf"}]},
        f"{V}/docs-review/main/docs review checklist.json": {"missing_required": [], "suggested_documents": []},
        "output/deliverables/open-items.json": {"packet_status": "draft", "items": []},
    },
    "forms_preparer": {
        f"{V}/forms/main/form facts.json": {"facts": []},
        f"{V}/forms/main/form intent manifest.json": {"forms": ["I-130"]},
        f"{V}/forms/main/prepared forms audit.json": {"findings": []},
        "output/deliverables/Forms/I-130.pdf": "%PDF-1.4 I-130 v1",
    },
    "forms_reviewer": {
        f"{V}/review/main/forms review memo.md": "# Forms review\n",
        f"{V}/review/main/forms review findings.json": {
            "findings": [{"id": "F1", "severity": "major", "title": "Last-arrival date", "owner": "forms_preparer", "status": "open"}]
        },
    },
    "cover_letter_writer_draft": {"output/deliverables/Cover Letter.docx": "letter v1"},
    "cover_letter_researcher": {
        f"{V}/research/main/authority pack.md": "# Authorities\n",
        f"{V}/research/main/support matrix.json": {"propositions": []},
    },
    "cover_letter_writer_integrate": {
        "output/deliverables/Cover Letter.docx": "letter v1",
        f"{V}/cover-letter/main/cover letter audit.json": {"finding_count": 0},
        f"{V}/cover-letter/main/letter check.json": {"errors": []},
    },
    "cover_letter_reviewer": {
        f"{V}/cover-letter/main/cover letter review memo.md": "# Letter review\n",
        f"{V}/cover-letter/main/cover letter review findings.json": {"findings": []},
        f"{V}/cover-letter/main/cover letter audit.json": {"finding_count": 0},
        f"{V}/cover-letter/main/letter check.json": {"errors": []},
    },
    "packet_assembly": {
        "output/deliverables/Filing Packet (DRAFT).pdf": "%PDF-1.4 packet v1",
        f"{V}/packet/main/packet manifest.json": {"exhibits": [{"number": 1}], "total_pages": 10},
    },
    "final_review": {
        f"{V}/final-review/main/final review memo.md": "# Final review\nRFE likely on bona fides.\n",
        f"{V}/final-review/main/final review findings.json": {
            "reviewed_at": "2026-10-28",
            "decision": "I-130 spouse; I-485 under INA 245(a)",
            "overall_outcome": "rfe_likely",
            "findings": [
                {"id": "FR1", "severity": "major", "outcome": "rfe_likely", "title": "Thin joint records", "owner": "client", "status": "open"},
                {"id": "FR2", "severity": "minor", "title": "Separator 4 is rotated", "status": "open"},
            ],
        },
    },
    "attorney_handoff": {
        "output/deliverables/Attorney Memo.md": "# Attorney memo\n",
        "output/deliverables/Attorney Memo.pdf": "%PDF-1.4 memo",
        "output/deliverables/Client Request.md": "# Documents we still need\n",
        "output/deliverables/Client Request.pdf": "%PDF-1.4 request",
        "output/deliverables/open-items.json": {"packet_status": "draft", "items": []},
    },
}


def new_matter(root: Path, name: str = "Sample Matter") -> Path:
    matter = root / name
    write(matter / "Passport.pdf", "%PDF-1.4 passport")
    write(matter / "Marriage Certificate.pdf", "%PDF-1.4 marriage")
    return matter


def produce(matter: Path, stage_id: str) -> list[str]:
    for relative, content in STAGE_ARTIFACTS[stage_id].items():
        write(matter / relative, content)
    return list(STAGE_ARTIFACTS[stage_id])


def complete_args(matter: Path, stage_id: str, artifacts: list[str], *extra: str, summary: str = "Stage complete.") -> list[str]:
    args = ["complete-stage", str(matter), stage_id, "--status", "passed", "--summary", summary, *extra]
    for artifact in artifacts:
        args += ["--artifact", artifact]
    return args


def pass_stage(matter: Path, stage_id: str) -> str:
    rw("start-stage", str(matter), stage_id)
    return rw(*complete_args(matter, stage_id, produce(matter, stage_id))).stdout


def state_of(matter: Path) -> dict:
    return json.loads((matter / mw.STATE_RELATIVE_PATH).read_text(encoding="utf-8"))


class FinalReviewContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.matter = new_matter(Path(self.enterContext(TemporaryDirectory())))
        rw("ensure", str(self.matter), *INTAKE, "--workflow-key", "packet_build")
        pass_stage(self.matter, "packet_assembly")
        rw("start-stage", str(self.matter), "final_review")
        produce(self.matter, "final_review")
        self.findings = self.matter / f"{V}/final-review/main/final review findings.json"
        self.memo = f"{V}/final-review/main/final review memo.md"

    def complete(self, *artifacts: str) -> subprocess.CompletedProcess[str]:
        artifacts = artifacts or (self.memo, str(self.findings.relative_to(self.matter)))
        return rw(*complete_args(self.matter, "final_review", list(artifacts), summary="Final review complete."), ok=False)

    def refused(self, payload: object, expected: str) -> None:
        write(self.findings, payload)
        result = self.complete()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(expected, result.stderr)
        self.assertEqual(state_of(self.matter)["stages"]["final_review"]["status"], "in_progress")

    def test_valid_artifacts_pass_with_a_short_report(self) -> None:
        result = self.complete()
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.strip().splitlines()
        self.assertEqual(len(lines), 2, result.stdout)
        self.assertTrue(lines[0].startswith("final_review: passed. Snapshot of"), lines[0])
        self.assertEqual(lines[1], "Next stage: none; every stage is done. Packet: -.")
        stage = state_of(self.matter)["stages"]["final_review"]
        self.assertEqual(stage["status"], "passed")
        self.assertTrue((self.matter / stage["last_pass"]["snapshot"]).is_file())

    def test_material_finding_without_owner_is_refused(self) -> None:
        self.refused(
            {"findings": [{"id": "FR1", "severity": "minor", "outcome": "noid_likely", "title": "Intent at entry", "status": "open"}]},
            "FR1 is open and material but has no owner",
        )

    def test_missing_severity_and_bad_outcome_are_refused(self) -> None:
        self.refused(
            {"findings": [{"id": "FR1", "outcome": "likely_denied", "title": "x", "owner": "attorney"}]},
            "severity must be one of",
        )
        self.refused(
            {"findings": [{"id": "FR1", "severity": "major", "outcome": "likely_denied", "title": "x", "owner": "attorney"}]},
            "outcome must be one of",
        )

    def test_findings_need_ids_and_a_findings_list(self) -> None:
        self.refused({"findings": [{"severity": "minor", "title": "x"}]}, "needs an id")
        self.refused([{"id": "FR1", "severity": "minor", "title": "x"}], "must be an object with a 'findings' list")

    def test_missing_memo_is_refused(self) -> None:
        result = self.complete(str(self.findings.relative_to(self.matter)))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing required final review memo artifact", result.stderr)

class ChangedSinceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.matter = new_matter(self.root)
        rw("ensure", str(self.matter), *INTAKE, "--workflow-key", "full_packet")
        for stage_id in mw.WORKFLOW_TEMPLATES["full_packet"]:
            pass_stage(self.matter, stage_id)

    def test_first_review_before_any_pass(self) -> None:
        other = new_matter(self.root, "Other Matter")
        rw("ensure", str(other), *INTAKE)
        self.assertEqual(rw("changed-since", str(other), "forms_reviewer").stdout.strip(),
                         "forms_reviewer: first review (it has not passed before). Review in full.")

    def test_reroute_then_changed_since_lists_exactly_the_changes(self) -> None:
        out = rw("reroute", str(self.matter), "--from-stage", "forms_preparer", "--reason", "Final review found a forms defect.",
                 "--detected-in-stage", "final_review").stdout
        self.assertIn("Re-reviews: forms_reviewer, cover_letter_reviewer, final_review.", out)
        self.assertIn("Next stage: forms_preparer", out)
        self.assertIn("forms_reviewer: pending (re-review", rw("status", str(self.matter)).stdout)

        # The fix: one form changes, the client sends a new document, the draft packet is replaced.
        write(self.matter / "output/deliverables/Forms/I-130.pdf", "%PDF-1.4 I-130 v2")
        write(self.matter / "I-94.pdf", "%PDF-1.4 i94")
        (self.matter / "output/deliverables/Filing Packet (DRAFT).pdf").unlink()
        write(self.matter / "output/deliverables/Filing Packet.pdf", "%PDF-1.4 packet v2")
        write(self.matter / "output/deliverables/Cover Letter.docx", "letter v2")
        ledger = {"packet_status": "draft", "items": [{"id": "doc-i94", "type": "client_document", "title": "I-94", "status": "resolved"}]}
        write(self.matter / "output/deliverables/open-items.json", ledger)

        forms = json.loads(rw("changed-since", str(self.matter), "forms_reviewer", "--json").stdout)
        self.assertEqual(forms["review"], "re_review")
        self.assertEqual(forms["added"], ["I-94.pdf"])
        # The ledger is shared, so every re-review sees it change.
        self.assertEqual(forms["changed"], ["output/deliverables/Forms/I-130.pdf", "output/deliverables/open-items.json"])
        self.assertEqual(forms["removed"], [])
        # The letter, research, packet, and reviews written after forms_reviewer passed are counted, not listed.
        self.assertGreater(forms["later_stage_changes"], 0)
        self.assertEqual(forms["previous_findings"], [f"{V}/review/main/forms review findings.json"])

        final = json.loads(rw("changed-since", str(self.matter), "final_review", "--json").stdout)
        self.assertEqual(final["added"], ["I-94.pdf", "output/deliverables/Filing Packet.pdf"])
        self.assertEqual(
            final["changed"],
            ["output/deliverables/Cover Letter.docx", "output/deliverables/Forms/I-130.pdf", "output/deliverables/open-items.json"],
        )
        self.assertEqual(final["removed"], ["output/deliverables/Filing Packet (DRAFT).pdf"])
        self.assertEqual(final["previous_findings"], [f"{V}/final-review/main/final review findings.json"])
        self.assertEqual(final["previous_memos"], [f"{V}/final-review/main/final review memo.md"])

        # The letter reviewer sees the letter, the form, and the client's new document. What later stages wrote
        # (the packet and its manifest, the final review, the handoff) is only counted.
        letter = json.loads(rw("changed-since", str(self.matter), "cover_letter_reviewer", "--json").stdout)
        self.assertEqual(letter["added"], ["I-94.pdf"])
        self.assertEqual(
            letter["changed"],
            ["output/deliverables/Cover Letter.docx", "output/deliverables/Forms/I-130.pdf", "output/deliverables/open-items.json"],
        )
        self.assertEqual(letter["later_stage_changes"], 8)  # the handoff's memo and request count with their PDFs

        text = rw("changed-since", str(self.matter), "final_review").stdout
        self.assertIn("  M output/deliverables/Forms/I-130.pdf", text)
        self.assertIn("  D output/deliverables/Filing Packet (DRAFT).pdf", text)
        self.assertIn("Don't re-read them.", text)


class ShortOutputTests(unittest.TestCase):
    def test_stage_workspace_json_is_a_count_not_a_file_list(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = new_matter(Path(tmp))
            rw("ensure", str(matter), *INTAKE)
            result = run(str(SECURE_STAGE), "create", str(matter), "--stage-id", "final_review", "--role", "final_review",
                         "--allow-unprotected", "--json")
            payload = json.loads(result.stdout)
            self.assertNotIn("files", payload)
            self.assertGreaterEqual(payload["file_count"], 2)
            self.assertTrue(Path(payload["manifest"]).is_file())
            self.assertEqual(len(json.loads(Path(payload["manifest"]).read_text())["files"]), payload["file_count"])
            closeout = rw("closeout", str(matter)).stdout.strip().splitlines()
            self.assertLessEqual(len(closeout), 4, closeout)
            self.assertTrue(closeout[0].startswith("Closeout done. Deleted: stage_workspaces"), closeout)
            dashboard = rw("security-dashboard", str(matter)).stdout.strip().splitlines()
            self.assertLessEqual(len(dashboard), 12, dashboard)


VAWA = "I-360 VAWA self-petition packet"
VAWA_AOS = "I-360/I-485 VAWA self-petition and adjustment packet"


class ProtectedMatterTests(unittest.TestCase):
    def test_vawa_forms_need_no_i130_or_i864(self) -> None:
        self.assertEqual(mw.expected_forms_from_intake(VAWA, "packet"), ["G-28", "I-360"])
        forms = mw.expected_forms_from_intake(VAWA_AOS, "packet")
        self.assertEqual(forms[:3], ["G-28", "I-360", "I-485"])
        self.assertTrue(forms[3].startswith("I-765"), forms)
        self.assertEqual(len(forms), 4)
        # A description that says "spouse" still gets a self-petition, not an I-130 and I-864.
        self.assertEqual(mw.expected_forms_from_intake("VAWA self-petition for an abused spouse with adjustment", "packet")[:3],
                         ["G-28", "I-360", "I-485"])

    def test_a_summary_that_names_the_case_is_refused_whatever_the_status(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = new_matter(Path(tmp), "Ramos I-360")
            rw("ensure", str(matter), "--matter-type", VAWA, "--filing-posture", "new filing packet", "--deliverable", "packet")
            rw("start-stage", str(matter), "docs_review")
            artifacts = produce(matter, "docs_review")
            for summary in ("Reviewed the VAWA evidence.", "Abuse records are thin.", "Missing proof of extreme cruelty.",
                            "Checked the I-360 checklist.", "Battery evidence reviewed."):
                refused = rw(*complete_args(matter, "docs_review", artifacts, summary=summary), ok=False)
                self.assertNotEqual(refused.returncode, 0, summary)
                self.assertIn("protected case type", refused.stderr, summary)
            rw(*complete_args(matter, "docs_review", artifacts, summary="Reviewed client documents against the evidence checklist."))

            rw("start-stage", str(matter), "forms_preparer")
            refused = rw("complete-stage", str(matter), "forms_preparer", "--status", "blocked", "--summary", "Waiting on the client.",
                         "--blocker-owner", "client", "--blocker-summary", "Need the abuser's status papers.", ok=False)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("Blocker summary names a protected case type", refused.stderr)
            rw("complete-stage", str(matter), "forms_preparer", "--status", "blocked", "--summary", "Waiting on the client.",
               "--blocker-owner", "client", "--blocker-summary", "Waiting on documents from the client.")
            self.assertEqual(state_of(matter)["stages"]["forms_preparer"]["status"], "blocked")



class OpenItemRulesTests(unittest.TestCase):
    """Open items as the app shows them: a question per decision, short plain details, no ids or paths.
    A list without schema_version 2 was written before these rules, so it still passes, with warnings."""

    DECISION = {
        "id": "decide-i765", "type": "attorney_decision", "title": "File an I-765 with the I-485?",
        "question": "Include an I-765 work permit application with the I-485?",
        "recommendation": "Yes. He has no work permit, and this lets him work while the I-485 is pending.",
        "detail": "He has no U.S. work authorization. The I-765 carries its own fee, and the forms change if it's added.",
        "notes": ["Forms (forms_preparer, 2026-10-28): left the I-765 out pending this; see output/working/vault/forms/main."],
        "blocks_filing": False, "status": "open", "stage": "forms_preparer",
    }
    DOCUMENT = {
        "id": "doc-i94", "type": "client_document", "title": "Luis's I-94 arrival record",
        "detail": "Proves he was admitted, which adjustment requires. He can print it free from the CBP site.",
        "blocks_filing": True, "status": "open", "stage": "docs_review", "who": "client",
    }

    def setUp(self) -> None:
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.path = self.root / "open-items.json"

    def check(self, *items: dict, schema_version: object = 2) -> tuple[list[str], list[str]]:
        payload: dict = {"packet_status": "draft", "items": list(items)}
        if schema_version is not None:
            payload["schema_version"] = schema_version
        write(self.path, payload)
        failures: list[str] = []
        warnings: list[str] = []
        mw.validate_open_items(failures, [self.path], warnings)
        return failures, warnings

    def refused(self, item: dict, expected: str) -> None:
        failures, _ = self.check(self.DOCUMENT, item)
        self.assertTrue(any(expected in failure for failure in failures), failures)

    def test_a_current_list_in_plain_words_passes(self) -> None:
        lookalikes = dict(
            self.DOCUMENT, id="q-contact", type="client_question", title="Jane's email and phone?",
            detail="Jane and/or Luis: reply to jane_sample@example.test. See 91 FR 45324, the F-1 rules, and the I-94 at "
            "https://i94.cbp.dhs.gov/I94/#/home. Filed as an I-130/I-485 on 03/12/2024.",
        )
        no_view = {key: value for key, value in self.DECISION.items() if key != "recommendation"}
        no_view["id"] = "decide-discretion"
        resolved = {
            "id": "decide-old", "type": "attorney_decision", "title": "An earlier call",
            "detail": "Plain words. " * 60 + "(forms_preparer, ADJ1) see output/working/vault/x.md",
            "status": "resolved", "resolution": "Answered by the attorney.",
        }
        self.assertEqual(self.check(self.DECISION, self.DOCUMENT, lookalikes, no_view, resolved), ([], []))

    def test_a_decision_needs_a_question(self) -> None:
        no_question = {key: value for key, value in self.DECISION.items() if key != "question"}
        self.refused(no_question, "Open item decide-i765: is a decision with no question")
        self.refused(dict(self.DECISION, question="Include an I-765."), "question should end with a question mark")

    def test_a_detail_over_600_characters_is_refused(self) -> None:
        self.refused(dict(self.DOCUMENT, id="doc-long", detail="Plain words. " * 47), "detail runs 610 characters")
        self.assertEqual(self.check(dict(self.DOCUMENT, detail="Plain words. " * 46)), ([], []))

    def test_paths_ids_review_codes_and_dated_notes_are_refused(self) -> None:
        cases = {
            "Details: output/working/vault/research/main/authority pack.md": "detail names a file path",
            "Saved at /Users/someone/Matters for now.": "detail names a file path",
            "The copy in Forms/I-130.pdf is cut off.": "detail names a file path",
            "This waits on doc-i94 first.": "detail mentions the item id 'doc-i94'",
            "The forms_preparer left it blank.": "detail uses the internal name 'forms_preparer'",
            "The officer's strongest theory (ADJ1).": "detail cites the review code 'ADJ1'",
            "Cover letter (draft 2026-10-28): cited as Exhibit 12.": "detail reads like a dated log",
        }
        for detail, expected in cases.items():
            with self.subTest(detail):
                self.refused(dict(self.DECISION, detail=detail), expected)
        self.refused(dict(self.DECISION, question="Answer doc-i94 first?"), "question mentions the item id 'doc-i94'")

    def test_the_new_fields_are_checked(self) -> None:
        self.refused(dict(self.DECISION, who="paralegal"), "who must be one of")
        self.refused(dict(self.DECISION, notes="Forms review: done."), "notes must be a list of strings")
        self.refused(dict(self.DOCUMENT, id="doc-x", question="Send it?"), "question belongs only on decisions")
        self.refused(dict(self.DECISION, recommendation="Yes. " * 50), "recommendation runs 249 characters")
        self.refused(dict(self.DECISION, id="doc-i94"), "Open item doc-i94: repeats an id")
        self.refused({key: value for key, value in self.DECISION.items() if key != "id"}, "needs a stable id")

    def test_an_older_list_still_passes_and_only_warns(self) -> None:
        legacy = {
            "id": "decide-entry-intent", "type": "attorney_decision", "title": "Whether to address intent at entry",
            "detail": "Research (cover_letter_researcher, 2026-10-28; see output/working/vault/research/main/a.md): " + "x " * 400,
            "blocks_filing": False, "status": "open",
        }
        failures, warnings = self.check(self.DOCUMENT, legacy, schema_version=None)
        self.assertEqual(failures, [])
        self.assertEqual(len(warnings), 1, warnings)
        for expected in ("is a decision with no question", "detail runs", "file path", "dated log"):
            self.assertIn(expected, warnings[0])
        # The rules every list has always had still refuse.
        failures, _ = self.check(dict(legacy, type="task"), schema_version=None)
        self.assertTrue(any("type must be one of" in failure for failure in failures), failures)
        failures, _ = self.check(self.DOCUMENT, schema_version="2")
        self.assertTrue(any("schema_version must be 2" in failure for failure in failures), failures)

    def test_the_handoff_refuses_a_bad_current_list_and_warns_on_an_older_one(self) -> None:
        matter = new_matter(self.root)
        rw("ensure", str(matter), *INTAKE, "--stage-id", "attorney_handoff")
        rw("start-stage", str(matter), "attorney_handoff")
        artifacts = produce(matter, "attorney_handoff")
        ledger = matter / "output/deliverables/open-items.json"
        no_question = {key: value for key, value in self.DECISION.items() if key != "question"}
        args = complete_args(matter, "attorney_handoff", artifacts, summary="Handoff written.")

        write(ledger, {"schema_version": 2, "packet_status": "draft", "items": [no_question]})
        result = rw(*args, ok=False)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("decide-i765: is a decision with no question", result.stderr)
        self.assertEqual(state_of(matter)["stages"]["attorney_handoff"]["status"], "in_progress")

        write(ledger, {"packet_status": "draft", "items": [no_question]})
        result = rw(*args, ok=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("predates the current open-items format", result.stderr)
        self.assertIn("attorney_handoff: passed", result.stdout)


NETWORK_GATE = PLUGIN_ROOT / "scripts" / "network_gate.py"
EXTRACT = PLUGIN_ROOT / "scripts" / "extract_documents.py"
CHAT_CHANGES = PLUGIN_ROOT / "scripts" / "chat_changes.py"

from scripts import matter_state as ms  # noqa: E402


def run_through(matter: Path, last: str) -> None:
    """Pass every full_packet stage in order up to and including `last`."""
    for stage_id in mw.WORKFLOW_TEMPLATES["full_packet"]:
        pass_stage(matter, stage_id)
        if stage_id == last:
            return


class RuntimeCase(unittest.TestCase):
    def setUp(self) -> None:
        self.matter = new_matter(Path(self.enterContext(TemporaryDirectory())))
        rw("ensure", str(self.matter), *INTAKE)

    def other_matter(self) -> Path:
        """A second matter, in a folder of its own."""
        return new_matter(Path(self.enterContext(TemporaryDirectory())))

    def stage(self, stage_id: str) -> dict:
        return state_of(self.matter)["stages"][stage_id]

    def events(self) -> list[dict]:
        return ms.read_jsonl(self.matter / ms.EVENTS_FILE)


class PassAndSkipRulesTests(RuntimeCase):
    """Finding 2: a pass needs a started stage and fresh work; a review is skipped only with its work, or the attorney."""

    def test_a_stage_that_never_started_cannot_pass(self) -> None:
        artifacts = produce(self.matter, "docs_review")
        result = rw(*complete_args(self.matter, "docs_review", artifacts), ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("it isn't in progress (it is pending)", result.stderr)
        self.assertEqual(self.stage("docs_review")["status"], "pending")

    def test_a_review_cannot_be_skipped_unless_its_work_was_or_the_attorney_approves(self) -> None:
        run_through(self.matter, "forms_preparer")
        refused = rw("complete-stage", str(self.matter), "forms_reviewer", "--status", "skipped", "--summary", "Not needed.", ok=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("Cannot skip forms_reviewer: it checks forms_preparer, which wasn't skipped", refused.stderr)
        for stage_id in ("final_review", "attorney_handoff"):
            refused = rw("complete-stage", str(self.matter), stage_id, "--status", "skipped", "--summary", "Not needed.", ok=False)
            self.assertIn(f"Cannot skip {stage_id}", refused.stderr)
        rw("complete-stage", str(self.matter), "forms_reviewer", "--status", "skipped", "--summary", "Skipped at the attorney's request.",
           "--attorney-approved", "The attorney reviewed the forms herself.")
        stage = self.stage("forms_reviewer")
        self.assertEqual(stage["status"], "skipped")
        self.assertEqual(stage["attorney_approved"], "The attorney reviewed the forms herself.")
        self.assertIn("was skipped, as you approved.", self.events()[-1]["text"])

    def test_a_review_of_skipped_work_may_be_skipped(self) -> None:
        matter = self.other_matter()
        rw("ensure", str(matter), *INTAKE, "--workflow-key", "forms_only")
        rw("complete-stage", str(matter), "forms_preparer", "--status", "skipped", "--summary", "Forms filed separately.")
        rw("complete-stage", str(matter), "forms_reviewer", "--status", "skipped", "--summary", "Nothing to review.")
        self.assertEqual(state_of(matter)["overall_status"], "passed")

    def test_a_pass_on_the_same_files_as_last_time_needs_a_reason(self) -> None:
        run_through(self.matter, "forms_reviewer")
        rw("reroute", str(self.matter), "--from-stage", "forms_reviewer", "--reason", "Check again.")
        rw("start-stage", str(self.matter), "forms_reviewer")
        artifacts = list(STAGE_ARTIFACTS["forms_reviewer"])  # untouched since the last pass
        refused = rw(*complete_args(self.matter, "forms_reviewer", artifacts), ok=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("is byte-for-byte the file it passed with last time", refused.stderr)
        self.assertIn("--unchanged-reason", refused.stderr)
        rw(*complete_args(self.matter, "forms_reviewer", artifacts, "--unchanged-reason", "Re-checked; nothing in scope changed."))
        self.assertEqual(self.stage("forms_reviewer")["unchanged_reason"], "Re-checked; nothing in scope changed.")

    def test_the_forms_need_a_filing_copy(self) -> None:
        run_through(self.matter, "docs_review")
        rw("start-stage", str(self.matter), "forms_preparer")
        artifacts = produce(self.matter, "forms_preparer")
        (self.matter / "output/deliverables/Forms/I-130.pdf").unlink()
        refused = rw(*complete_args(self.matter, "forms_preparer", artifacts[:3]), ok=False)
        self.assertIn("No filing copy in output/deliverables/Forms/", refused.stderr)

    def test_finished_work_is_redone_by_a_reroute_not_relabeled(self) -> None:
        run_through(self.matter, "forms_preparer")
        for status in ("skipped", "failed", "blocked"):
            extra = ["--blocker-owner", "client", "--blocker-summary", "Waiting on documents."] if status == "blocked" else []
            refused = rw("complete-stage", str(self.matter), "forms_preparer", "--status", status, "--summary", "Again.", *extra, ok=False)
            self.assertNotEqual(refused.returncode, 0, status)
            self.assertIn("it is already passed. To redo it, reroute from it", refused.stderr)
        # A stage can't be skipped ahead of the work it needs, either.
        refused = rw("complete-stage", str(self.matter), "cover_letter_researcher", "--status", "skipped", "--summary", "Not needed.", ok=False)
        self.assertIn("Cannot skip cover_letter_researcher before cover_letter_writer_draft", refused.stderr)

    def test_overall_passed_needs_the_final_review_passed(self) -> None:
        run_through(self.matter, "packet_assembly")
        rw("complete-stage", str(self.matter), "final_review", "--status", "skipped", "--summary", "Skipped.",
           "--attorney-approved", "File it without the final review.")
        pass_stage(self.matter, "attorney_handoff")
        state = state_of(self.matter)
        self.assertEqual(state["overall_status"], "incomplete")
        self.assertIn("incomplete (every stage is done, but the final review didn't pass", rw("status", str(self.matter)).stdout)


class DependencyTests(RuntimeCase):
    """Findings 45/46: steps start when what they need has passed, and run side by side."""

    def test_the_forms_review_and_the_letter_are_ready_together(self) -> None:
        run_through(self.matter, "forms_preparer")
        self.assertEqual(rw("next-stages", str(self.matter)).stdout.split(), ["forms_reviewer", "cover_letter_writer_draft"])
        rw("start-stage", str(self.matter), "forms_reviewer")
        rw("start-stage", str(self.matter), "cover_letter_writer_draft")
        state = json.loads(rw("status", str(self.matter), "--json").stdout)
        self.assertEqual(state["running"], ["forms_reviewer", "cover_letter_writer_draft"])
        self.assertEqual(state["stage_dependencies"]["packet_assembly"], ["forms_reviewer", "cover_letter_reviewer"])
        # The packet waits for both reviews.
        refused = rw("start-stage", str(self.matter), "packet_assembly", ok=False)
        self.assertIn("Cannot start packet_assembly before forms_reviewer", refused.stderr)

    def test_stages_completed_at_the_same_moment_are_both_recorded(self) -> None:
        run_through(self.matter, "forms_preparer")
        processes = []
        for stage_id in ("forms_reviewer", "cover_letter_writer_draft"):
            rw("start-stage", str(self.matter), stage_id)
        for stage_id in ("forms_reviewer", "cover_letter_writer_draft"):
            artifacts = produce(self.matter, stage_id)
            processes.append(subprocess.Popen([sys.executable, str(RW), *complete_args(self.matter, stage_id, artifacts)],
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        for process in processes:
            _out, err = process.communicate(timeout=120)
            self.assertEqual(process.returncode, 0, err)
        state = state_of(self.matter)
        self.assertEqual(state["stages"]["forms_reviewer"]["status"], "passed")
        self.assertEqual(state["stages"]["cover_letter_writer_draft"]["status"], "passed")
        self.assertEqual(state["ready"], ["cover_letter_researcher"])

    def test_a_reroute_resets_only_what_depends_on_the_redone_stage(self) -> None:
        run_through(self.matter, "cover_letter_reviewer")
        out = rw("reroute", str(self.matter), "--from-stage", "cover_letter_writer_integrate", "--reason", "Letter defect.",
                 "--detected-in-stage", "cover_letter_reviewer").stdout
        self.assertIn("Reset to pending: cover_letter_writer_integrate, cover_letter_reviewer, packet_assembly, final_review, "
                      "attorney_handoff.", out)
        self.assertIn("Still passed (they don't depend on it): docs_review, forms_preparer, forms_reviewer, "
                      "cover_letter_writer_draft, cover_letter_researcher.", out)
        state = state_of(self.matter)
        self.assertEqual(state["stages"]["forms_reviewer"]["status"], "passed")
        self.assertEqual(state["stages"]["cover_letter_researcher"]["status"], "passed")
        self.assertEqual(self.events()[-1]["text"], "The letter review sent the letter revision back to be redone.")
        # The same reroute sent again resets nothing new, and the timeline says it once.
        rw("reroute", str(self.matter), "--from-stage", "cover_letter_writer_integrate", "--reason", "Letter defect.",
           "--detected-in-stage", "cover_letter_reviewer")
        self.assertEqual([e["text"] for e in self.events()].count("The letter review sent the letter revision back to be redone."), 1)

    def test_a_review_sending_the_forms_back_reads_as_one_plain_line(self) -> None:
        run_through(self.matter, "forms_reviewer")
        rw("reroute", str(self.matter), "--from-stage", "forms_reviewer", "--reason", "The attorney asked to redo this step")
        rw("reroute", str(self.matter), "--from-stage", "forms_preparer", "--reason", "Forms defect.",
           "--detected-in-stage", "forms_reviewer")
        rerouted = [e["text"] for e in self.events() if e["kind"] == "rerouted"]
        self.assertEqual(rerouted, ["Redoing the forms review and the steps after it.", "The forms review sent the forms back to be redone."])

    def test_nothing_is_offered_while_a_blocker_is_open_and_a_failure_beside_running_work_isnt_final(self) -> None:
        run_through(self.matter, "forms_preparer")
        rw("start-stage", str(self.matter), "forms_reviewer")
        rw("start-stage", str(self.matter), "cover_letter_writer_draft")
        rw("complete-stage", str(self.matter), "forms_reviewer", "--status", "failed", "--summary", "The render tool crashed.")
        self.assertEqual(state_of(self.matter)["overall_status"], "in_progress")
        rw("start-stage", str(self.matter), "forms_reviewer")
        out = rw("complete-stage", str(self.matter), "forms_reviewer", "--status", "blocked", "--summary", "Waiting.",
                 "--blocker-owner", "attorney", "--blocker-summary", "A decision on the forms is needed.").stdout
        self.assertIn("Next stage: none while a blocker is open.", out)
        self.assertEqual(rw("next-stages", str(self.matter)).stdout, "")
        self.assertEqual(rw("next-stage", str(self.matter)).stdout.strip(), "")

    def test_a_blocker_resolved_straight_back_into_progress_is_timed(self) -> None:
        run_through(self.matter, "docs_review")
        rw("start-stage", str(self.matter), "forms_preparer")
        rw("complete-stage", str(self.matter), "forms_preparer", "--status", "blocked", "--summary", "Waiting.",
           "--blocker-owner", "system", "--blocker-summary", "Ghostscript is missing.")
        rw("resolve-blocker", str(self.matter), "BLK-001", "--resolution-note", "Installed.", "--reset-stage-to", "in_progress")
        rw(*complete_args(self.matter, "forms_preparer", produce(self.matter, "forms_preparer")))
        attempts = self.stage("forms_preparer")["timing"]["attempts"]
        self.assertEqual([a["outcome"] for a in attempts], ["blocked", "passed"])
        self.assertIsNotNone(attempts[-1]["seconds"])

    def test_a_reroute_sets_aside_the_blockers_on_the_stages_it_resets(self) -> None:
        run_through(self.matter, "packet_assembly")
        rw("start-stage", str(self.matter), "final_review")
        rw("complete-stage", str(self.matter), "final_review", "--status", "blocked", "--summary", "Waiting on a decision.",
           "--blocker-owner", "attorney", "--blocker-summary", "The attorney needs to choose a filing strategy.")
        self.assertEqual(rw("next-stage", str(self.matter)).stdout.strip(), "")
        rw("reroute", str(self.matter), "--from-stage", "packet_assembly", "--reason", "The attorney asked for a redo.")
        state = state_of(self.matter)
        self.assertEqual(state["blockers"][0]["status"], "resolved")
        self.assertEqual(state["blockers"][0]["resolution_note"], "Set aside by a redo.")
        self.assertEqual(state["next_stage"], "packet_assembly")

    def test_a_review_sends_the_same_work_back_at_most_twice_a_run(self) -> None:
        rw("lease", "acquire", str(self.matter), "--run-id", "run-one")
        run_through(self.matter, "final_review")
        def redo_packet(version: int) -> None:
            rw("start-stage", str(self.matter), "packet_assembly")
            write(self.matter / "output/deliverables/Filing Packet (DRAFT).pdf", f"%PDF-1.4 packet v{version}")
            rw(*complete_args(self.matter, "packet_assembly", produce_keep(self.matter, "packet_assembly")))

        for attempt in range(2):
            rw("reroute", str(self.matter), "--from-stage", "packet_assembly", "--reason", "Exhibit order.", "--detected-in-stage", "final_review")
            redo_packet(attempt + 2)
            rw("start-stage", str(self.matter), "final_review")
            write(self.matter / f"{V}/final-review/main/final review findings.json", {"findings": [], "pass": attempt})
            rw(*complete_args(self.matter, "final_review", produce_keep(self.matter, "final_review")))
        refused = rw("reroute", str(self.matter), "--from-stage", "packet_assembly", "--reason", "Exhibit order.",
                     "--detected-in-stage", "final_review", ok=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("has already sent packet_assembly back 2 times in this run", refused.stderr)
        # The attorney's own redo isn't counted, and a new run starts the count again.
        rw("reroute", str(self.matter), "--from-stage", "packet_assembly", "--reason", "Redo.", "--detected-in-stage", "final_review",
           "--attorney-approved", "Redo the packet.")
        rw("lease", "release", str(self.matter), "--run-id", "run-one")
        rw("lease", "acquire", str(self.matter), "--run-id", "run-two")
        redo_packet(9)
        rw("reroute", str(self.matter), "--from-stage", "packet_assembly", "--reason", "Exhibit order.", "--detected-in-stage", "final_review")

    def test_timing_is_recorded_per_attempt_and_per_run(self) -> None:
        rw("lease", "acquire", str(self.matter), "--run-id", "timed-run")
        pass_stage(self.matter, "docs_review")
        stage = self.stage("docs_review")
        attempts = stage["timing"]["attempts"]
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["outcome"], "passed")
        self.assertEqual(attempts[0]["run_id"], "timed-run")
        self.assertIsNotNone(stage["duration_seconds"])
        runs = state_of(self.matter)["telemetry"]["runs"]
        self.assertEqual(runs[0]["run_id"], "timed-run")
        self.assertIn("docs_review", runs[0]["stages"])
        texts = [event["text"] for event in self.events()]
        self.assertIn("Document review started.", texts)
        self.assertIn("Document review is done.", texts)


def produce_keep(matter: Path, stage_id: str) -> list[str]:
    """The stage's artifact paths, writing only the ones that don't exist yet (a caller changed the rest)."""
    for relative, content in STAGE_ARTIFACTS[stage_id].items():
        if not (matter / relative).exists():
            write(matter / relative, content)
    return list(STAGE_ARTIFACTS[stage_id])


class LeaseAndActionsTests(RuntimeCase):
    """Findings 12/40: the run lease, heartbeats, and the attorney's actions on the open items."""

    def test_a_second_run_is_refused_with_exit_code_3(self) -> None:
        rw("lease", "acquire", str(self.matter), "--run-id", "app-run", "--holder", "app", "--kind", "build")
        refused = rw("lease", "acquire", str(self.matter), "--run-id", "other-run", ok=False)
        self.assertEqual(refused.returncode, 3)
        self.assertIn("Claude is already working on this matter", refused.stderr)
        # The orchestrator started by the app takes the same run id over.
        rw("lease", "acquire", str(self.matter), "--run-id", "app-run", "--holder", "orchestrator")
        self.assertEqual(ms.read_lease(self.matter)["holder"], "orchestrator")
        rw("start-stage", str(self.matter), "docs_review")
        self.assertEqual(ms.read_lease(self.matter)["stage"], "docs_review")
        rw("lease", "release", str(self.matter), "--run-id", "app-run", "--outcome", "done")
        self.assertTrue(ms.read_lease(self.matter)["released_at"])
        rw("lease", "acquire", str(self.matter), "--run-id", "other-run")

    def test_looking_at_a_matter_never_revives_a_run_that_is_gone(self) -> None:
        old = datetime_ago(hours=2)
        ms.acquire_lease(self.matter, "gone-run", "build", "orchestrator", now=old)
        rw("status", str(self.matter))
        self.assertFalse(ms.lease_is_fresh(ms.read_lease(self.matter)))
        rw("start-stage", str(self.matter), "docs_review")
        self.assertTrue(ms.lease_is_fresh(ms.read_lease(self.matter)))

    def test_the_handoff_applies_the_attorneys_actions_before_it_checks_the_open_items(self) -> None:
        item = {"id": "doc-lease", "type": "client_document", "title": "The joint lease", "detail": "Shows they live together.",
                "blocks_filing": True, "status": "open"}
        old_copy = {"schema_version": 2, "packet_status": "draft", "items": [item]}
        matter = self.other_matter()
        rw("ensure", str(matter), *INTAKE, "--stage-id", "attorney_handoff")
        rw("start-stage", str(matter), "attorney_handoff")
        artifacts = produce(matter, "attorney_handoff")
        write(matter / "output/deliverables/open-items.json", old_copy)
        ms.record_attorney_action(matter, "resolve", "doc-lease")
        write(matter / "output/deliverables/open-items.json", old_copy)  # an agent writes back the copy it read earlier
        out = rw(*complete_args(matter, "attorney_handoff", artifacts)).stdout
        self.assertIn("Applied 1 attorney action(s) to the open items first.", out)
        self.assertEqual(json.loads((matter / "output/deliverables/open-items.json").read_text())["items"][0]["status"], "resolved")

    def test_a_run_that_lost_the_matter_while_quiet_stops_before_changing_anything(self) -> None:
        # A run started from the chat goes quiet in a long step; the attorney starts another from the app.
        rw("lease", "acquire", str(self.matter), "--run-id", "chat-run", "--holder", "orchestrator")
        rw("start-stage", str(self.matter), "docs_review", "--run-id", "chat-run")
        ms.acquire_lease(self.matter, "chat-run", "build", "orchestrator", now=datetime_ago(minutes=40))
        ok, _lease = ms.acquire_lease(self.matter, "app-run", "build", "app")
        self.assertTrue(ok)
        beat = ms.read_lease(self.matter)["heartbeat_at"]
        artifacts = produce(self.matter, "docs_review")
        refused = rw(*complete_args(self.matter, "docs_review", artifacts, "--run-id", "chat-run"), ok=False)
        self.assertEqual(refused.returncode, 3)
        self.assertIn("Another run holds this matter now; stop.", refused.stderr)
        self.assertEqual(self.stage("docs_review")["status"], "in_progress")
        lease = ms.read_lease(self.matter)
        self.assertEqual((lease["run_id"], lease["heartbeat_at"]), ("app-run", beat))  # the other run's lease, untouched
        for args in (["open-items", "note", str(self.matter), "x", "A note.", "--run-id", "chat-run"],
                     ["lease", "heartbeat", str(self.matter), "--run-id", "chat-run"]):
            self.assertEqual(rw(*args, ok=False).returncode, 3, args[0])
        # Reading takes no lease and is never refused; without a run id, a command behaves as before.
        rw("status", str(self.matter), "--run-id", "chat-run")
        self.assertEqual(ms.read_lease(self.matter)["run_id"], "app-run")
        # The other run ended, but this one lost the matter in between: still not its to change.
        ms.release_lease(self.matter, "app-run", "done")
        refused = rw("start-stage", str(self.matter), "forms_preparer", "--run-id", "chat-run", ok=False)
        self.assertEqual(refused.returncode, 3)
        self.assertIn("took this matter over", refused.stderr)

    def test_a_run_renews_only_its_own_lease_and_stops_once_its_lease_ended(self) -> None:
        rw("lease", "acquire", str(self.matter), "--run-id", "r1", "--holder", "orchestrator")
        ms.acquire_lease(self.matter, "r1", "build", "orchestrator", now=datetime_ago(minutes=40))
        self.assertFalse(ms.lease_is_fresh(ms.read_lease(self.matter)))
        rw("start-stage", str(self.matter), "docs_review", "--run-id", "r1")  # its own quiet lease: renewed
        lease = ms.read_lease(self.matter)
        self.assertTrue(ms.lease_is_fresh(lease))
        self.assertEqual(lease["stage"], "docs_review")
        self.assertEqual(rw("lease", "heartbeat", str(self.matter), "--run-id", "r1").returncode, 0)
        # The attorney stopped it in the app (or said Claude wasn't working on it): its next change is refused.
        ms.release_lease(self.matter, "r1", "stopped")
        refused = rw(*complete_args(self.matter, "docs_review", produce(self.matter, "docs_review"), "--run-id", "r1"), ok=False)
        self.assertEqual(refused.returncode, 3)
        self.assertIn("lease on the matter has ended", refused.stderr)
        self.assertEqual(self.stage("docs_review")["status"], "in_progress")

    def test_a_completion_of_a_step_a_redo_reset_is_refused_whatever_its_status(self) -> None:
        run_through(self.matter, "forms_preparer")
        rw("start-stage", str(self.matter), "forms_reviewer")
        # A redo resets the review while its agent is still at work on it.
        rw("reroute", str(self.matter), "--from-stage", "forms_preparer", "--reason", "The attorney asked to redo the forms.")
        self.assertEqual(self.stage("forms_reviewer")["status"], "pending")
        for status in ("passed", "blocked", "failed", "skipped"):
            extra = ["--blocker-owner", "client", "--blocker-summary", "Waiting on documents."] if status == "blocked" else []
            extra += ["--attorney-approved", "Skip it."] if status == "skipped" else []
            args = complete_args(self.matter, "forms_reviewer", list(STAGE_ARTIFACTS["forms_reviewer"]), *extra) if status == "passed" \
                else ["complete-stage", str(self.matter), "forms_reviewer", "--status", status, "--summary", "Late result.", *extra]
            refused = rw(*args, ok=False)
            self.assertNotEqual(refused.returncode, 0, status)
            self.assertIn("A redo reset it after it started", refused.stderr, status)
            self.assertEqual(self.stage("forms_reviewer")["status"], "pending", status)
        # A step nobody started may still be skipped outright (a review of skipped work, say).
        self.assertIsNone(mw.completion_refusal("forms_reviewer", "skipped", mw.stage_template("forms_reviewer")))

    def test_chat_changes_recorded_at_once_are_all_kept(self) -> None:
        processes = [
            subprocess.Popen([sys.executable, str(CHAT_CHANGES), "record", str(self.matter), "--what", f"Cover letter: change {n}"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for n in range(6)
        ]
        for process in processes:
            _out, err = process.communicate(timeout=60)
            self.assertEqual(process.returncode, 0, err)
        changes = json.loads((self.matter / "output/working/workflow/chat-changes.json").read_text())["changes"]
        self.assertEqual(len(changes), 6)


def datetime_ago(**delta: float):
    from datetime import datetime, timedelta, timezone
    return datetime.now(tz=timezone.utc) - timedelta(**delta)


class EnsureAndMoveTests(unittest.TestCase):
    """Finding 41: intake wording, a moved folder, --resume, and no advice to start over."""

    def setUp(self) -> None:
        self.root = Path(self.enterContext(TemporaryDirectory()))

    def test_intake_wording_and_case_dont_make_a_different_matter(self) -> None:
        matter = new_matter(self.root)
        rw("ensure", str(matter), *INTAKE)
        rw("ensure", str(matter), "--matter-type", "  i-130/I-485   Immediate Relative packet ", "--filing-posture",
           "New filing packet", "--deliverable", "Packet")
        refused = rw("ensure", str(matter), "--matter-type", "N-400 naturalization packet", "--filing-posture", "new filing packet",
                     "--deliverable", "packet", ok=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("set up for a different filing", refused.stderr)
        self.assertNotIn("--force", refused.stderr)
        self.assertIn("ensure --resume", refused.stderr)
        refused = rw("init", str(matter), *INTAKE, ok=False)
        self.assertNotIn("--force", refused.stderr)

    def test_a_moved_matter_resumes_and_reads_its_own_open_items(self) -> None:
        matter = new_matter(self.root, "Before Move")
        rw("ensure", str(matter), *INTAKE)
        pass_stage(matter, "docs_review")
        moved = self.root / "Elsewhere" / "After Move"
        moved.parent.mkdir()
        matter.rename(moved)
        write(moved / "output/deliverables/open-items.json", {"packet_status": "ready_to_file", "items": []})
        status = rw("status", str(moved)).stdout
        self.assertIn(f"Matter folder: {moved.resolve()}", status)
        self.assertIn("Packet: ready to file", status)
        rw("ensure", str(moved), "--resume")
        state = state_of(moved)
        self.assertEqual(state["matter"]["matter_folder"], str(moved.resolve()))
        self.assertEqual(state["history"][-1]["event"], "matter_folder_moved")
        self.assertEqual(state["stages"]["docs_review"]["status"], "passed")

    def test_resume_refuses_a_different_workflow(self) -> None:
        matter = new_matter(self.root)
        rw("ensure", str(matter), *INTAKE)
        refused = rw("ensure", str(matter), "--resume", "--workflow-key", "forms_only", ok=False)
        self.assertIn("workflow_key: recorded 'full_packet', asked for 'forms_only'", refused.stderr)
        rw("ensure", str(matter), "--resume", "--workflow-key", "full_packet")

    def test_resume_needs_a_record(self) -> None:
        matter = new_matter(self.root)
        refused = rw("ensure", str(matter), "--resume", ok=False)
        self.assertIn("no workflow record to resume", refused.stderr)

    def fresh_record(self, matter: Path) -> dict:
        return mw.initialize_state(matter_path=matter, matter_type=INTAKE[1], filing_posture=INTAKE[3], deliverable=INTAKE[5],
                                   workflow_key="full_packet")

    def test_an_older_layouts_record_with_the_work_wins_over_an_empty_newer_one(self) -> None:
        matter = new_matter(self.root)
        legacy = self.fresh_record(matter)
        for stage_id in mw.WORKFLOW_TEMPLATES["full_packet"][:3]:
            legacy["stages"][stage_id]["status"] = "passed"
        legacy_path = write(matter / mw.LEGACY_STATE_ROOT / "matter_status.json", legacy)
        rw("ensure", str(matter), *INTAKE)  # an app that only knew the new layout
        # ensure resumed the older record instead of starting an empty one beside it
        self.assertFalse((matter / mw.STATE_RELATIVE_PATH).exists())
        write(matter / mw.STATE_RELATIVE_PATH, self.fresh_record(matter))
        self.assertEqual(mw.default_state_path(matter), legacy_path)
        self.assertIn("forms_reviewer: passed", rw("status", str(matter)).stdout)

    def test_a_record_from_another_schema_is_refused_in_words(self) -> None:
        matter = new_matter(self.root)
        write(matter / mw.STATE_RELATIVE_PATH, dict(self.fresh_record(matter), schema_version=7))
        refused = rw("status", str(matter), ok=False)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("Unsupported schema_version 7 in workflow state", refused.stderr)
        self.assertNotIn("Traceback", refused.stderr)

    def test_the_case_type_lives_only_in_the_intake_block(self) -> None:
        matter = new_matter(self.root)
        rw("ensure", str(matter), "--matter-type", VAWA, "--filing-posture", "new filing packet", "--deliverable", "packet")
        state = state_of(matter)
        text = json.dumps({key: value for key, value in state.items() if key != "matter"})
        self.assertNotIn("VAWA", text)
        self.assertNotIn("I-360", text)


class ClosedoutTests(unittest.TestCase):
    """Finding 3 and 26: closeout never moves a client document, and cleans what stages leave in the vault."""

    CLIENT_FILES = {
        "Intake notes.md": "Client intake notes. DOB: 01/02/1990. Phone 555-0123.",
        "From client/Relationship notes.txt": "We met on March 3, 2021 at 12 Sample Street.",
        "Bank statement summary.csv": "date,amount\n03/01/2024,1200\n",
        "From client/extract of record.txt": "Passport No. X1234567",
    }

    def test_client_documents_named_like_scratch_stay_put(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = new_matter(Path(tmp))
            rw("ensure", str(matter), *INTAKE)
            for relative, text in self.CLIENT_FILES.items():
                write(matter / relative, text)
            # Older layouts' work product, which earlier closeouts quarantined.
            write(matter / "output/forms/Sample form facts.json", {"facts": [{"key": "dob", "value": "01/02/1990"}]})
            write(matter / "output/pdf/Sample Packet manifest.txt", "Passport No. X1234567")
            # Real scratch with identifiers, and vault clutter.
            write(matter / "output/working/pdf/page-3.txt", "Phone 555-0123, DOB: 01/02/1990")
            write(matter / f"{V}/review/main/render-check/p1.png", "png")
            write(matter / f"{V}/review/main/renders/docs/passport.txt", "Passport No. X1234567")
            write(matter / f"{V}/docs-review/main/ocr/page-1.txt", "text")
            write(matter / f"{V}/scratch/helper.json", {"dob": "01/02/1990"})
            write(matter / f"{V}/review/main/forms review findings.json", {"findings": []})
            out = rw("closeout", str(matter)).stdout
            for relative in self.CLIENT_FILES:
                self.assertTrue((matter / relative).is_file(), relative)
            self.assertTrue((matter / "output/forms/Sample form facts.json").is_file())
            self.assertTrue((matter / "output/pdf/Sample Packet manifest.txt").is_file())
            self.assertTrue((matter / f"{V}/review/main/forms review findings.json").is_file())
            self.assertFalse((matter / "output/working/pdf/page-3.txt").exists())
            for relative in ("review/main/render-check", "review/main/renders", "docs-review/main/ocr", "scratch"):
                self.assertFalse((matter / V / relative).exists(), relative)
            report = json.loads((matter / "output/security/closeout report.json").read_text())
            self.assertEqual(report["quarantine"]["quarantined_count"], 1)
            self.assertEqual(report["vault_renders"]["file_count"], 3)
            self.assertIn("vault_renders (3 files)", out)
            moved = [item["source"] for item in report["quarantine"]["quarantined"]]
            self.assertEqual(moved, ["output/working/pdf/page-3.txt"])

    def test_a_protected_matters_closeout_report_names_no_files(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = new_matter(Path(tmp))
            rw("ensure", str(matter), *INTAKE)
            rw("set-protected", str(matter), "--on", "--reason", "docs_review")
            write(matter / "output/working/doc/notes.txt", "Notes about the abuse and the safe address.")
            rw("closeout", str(matter))
            report = json.loads((matter / "output/security/closeout report.json").read_text())
            self.assertTrue(report["protected_matter"])
            self.assertEqual(report["quarantine"]["quarantined_count"], 1)
            self.assertNotIn("source", report["quarantine"]["quarantined"][0])


class WorkspaceTests(RuntimeCase):
    """Findings 5, 6, 7: a workspace holds every client document and nothing set aside; nothing is cut silently."""

    def create(self, *extra: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        return run(str(SECURE_STAGE), "create", str(self.matter), "--stage-id", "final_review", "--role", "final_review",
                   "--allow-unprotected", "--json", *extra, ok=ok)

    def test_every_client_document_and_nothing_set_aside(self) -> None:
        for n in range(320):  # more than the old final review cap of 350 files, with the output files
            write(self.matter / "From client" / f"page {n:03d}.pdf", f"%PDF {n}")
        write(self.matter / "output/removed documents/Old passport.pdf", "%PDF old")
        write(self.matter / "output/earlier/I-751/output/deliverables/x.pdf", "%PDF earlier")
        write(self.matter / f"{V}/review/main/render-check/p1.png", "png")
        write(self.matter / "output/deliverables/Cover Letter.docx", "letter")
        payload = json.loads(self.create().stdout)
        manifest = json.loads(Path(payload["manifest"]).read_text())
        copied = {entry["relative_path"] for entry in manifest["files"]}
        self.assertEqual(payload["file_count"], 322)
        self.assertIn("Passport.pdf", copied)
        self.assertFalse(any(path.startswith("output/") for path in copied), sorted(copied)[:5])
        self.assertEqual(payload["excluded_count"], manifest["excluded_count"])
        self.assertGreaterEqual(payload["excluded_count"], 4)
        entry = next(e for e in manifest["files"] if e["relative_path"] == "Passport.pdf")
        self.assertEqual(entry["original_sha256"], ms.sha256_file(self.matter / "Passport.pdf"))
        self.assertNotIn("sha256", entry)  # one name for each value: original_path, original_sha256
        self.assertEqual(entry["original_path"], str((self.matter / "Passport.pdf").resolve()))
        # Two workspaces made in the same second don't collide.
        second = json.loads(self.create().stdout)
        self.assertNotEqual(second["workspace_root"], payload["workspace_root"])

    def test_a_workspace_past_the_limit_is_refused_not_cut(self) -> None:
        for n in range(6):
            write(self.matter / f"doc {n}.pdf", "%PDF")
        refused = self.create("--max-files", "5", ok=False)
        self.assertEqual(refused.returncode, 2)
        self.assertIn("would hold 8 files", refused.stderr)
        self.assertFalse((self.matter / "output/security/stage-workspaces").exists())
        refused = self.create("--include", "output/removed documents", ok=False)
        self.assertNotEqual(refused.returncode, 0)

    def test_a_plan_pointing_at_a_workspace_copy_cannot_pass(self) -> None:
        run_through(self.matter, "final_review")
        rw("reroute", str(self.matter), "--from-stage", "packet_assembly", "--reason", "Rebuild.")
        rw("start-stage", str(self.matter), "packet_assembly")
        artifacts = produce(self.matter, "packet_assembly")
        write(self.matter / "output/deliverables/Filing Packet (DRAFT).pdf", "%PDF-1.4 packet v2")
        write(self.matter / f"{V}/packet/main/packet manifest.json", {
            "exhibits": [{"number": 1, "source": f"{self.matter}/output/security/stage-workspaces/packet-assembly-1/files/Passport.pdf"}],
            "total_pages": 10,
        })
        refused = rw(*complete_args(self.matter, "packet_assembly", artifacts), ok=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("points into a stage workspace (exhibits[0].source)", refused.stderr)


class PrivacyLintTests(RuntimeCase):
    """Finding 26 and 28: names from the fact table, and protected matters."""

    def setUp(self) -> None:
        super().setUp()
        write(self.matter / f"{V}/forms/main/form facts.json", {"facts": [
            {"subject": "beneficiary", "key": "legal.family_name", "value": "Okonkwo-Barros"},
            {"subject": "beneficiary", "key": "legal.given_name", "value": "Teodora"},
            {"subject": "attorney", "key": "attorney_name", "value": "Pat Counsel"},
            {"subject": "beneficiary", "key": "a_number", "value": "A-201-555-019"},
            {"subject": "petitioner", "key": "employer_name", "value": "Acme Widgets"},
        ]})

    def test_the_fact_table_gives_names_and_numbers(self) -> None:
        from scripts.privacy_terms import matter_privacy_terms
        terms = matter_privacy_terms(self.matter)
        self.assertEqual(terms["names"], ["Barros", "Okonkwo", "Teodora"])
        self.assertEqual(terms["identifiers"], ["A-201-555-019"])
        self.assertNotIn("Counsel", terms["names"])
        self.assertNotIn("Acme", terms["names"])

    def test_employers_and_contractions_are_not_names(self) -> None:
        from scripts.privacy_terms import find_terms, matter_privacy_terms
        write(self.matter / f"{V}/forms/main/form facts.json", {"facts": [
            {"subject": "beneficiary", "key": "employment.current_or_recent.name", "value": "Research Institute"},
            {"subject": "petitioner", "key": "legal.given_name", "value": "Don"},
        ]})
        terms = matter_privacy_terms(self.matter)
        self.assertEqual(terms["names"], ["Don"])
        self.assertEqual(find_terms("Research done; the findings don't block filing.", terms), [])
        self.assertEqual(find_terms("Don's passport is missing.", terms), ["name"])

    def test_a_summary_or_blocker_naming_a_party_is_refused(self) -> None:
        rw("start-stage", str(self.matter), "docs_review")
        artifacts = produce(self.matter, "docs_review")
        refused = rw(*complete_args(self.matter, "docs_review", artifacts, summary="Reviewed Teodora's documents."), ok=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("contains a person's name from this matter's fact table", refused.stderr)
        self.assertNotIn("Teodora", refused.stderr)
        refused = rw("complete-stage", str(self.matter), "docs_review", "--status", "blocked", "--summary", "Waiting.",
                     "--blocker-owner", "client", "--blocker-summary", "Need the A number 201555019 confirmed.", ok=False)
        self.assertIn("an identifying number", refused.stderr)
        rw(*complete_args(self.matter, "docs_review", artifacts, summary="Reviewed the client's documents."))

    def test_a_protected_matter_refuses_more_words_and_checks_client_items(self) -> None:
        self.assertEqual(json.loads(rw("status", str(self.matter), "--json").stdout)["meta"]["protected_reason"], "")
        rw("set-protected", str(self.matter), "--on", "--reason", "attorney")
        meta = json.loads(rw("status", str(self.matter), "--json").stdout)["meta"]
        self.assertEqual((meta["protected"], meta["protected_reason"]), (True, "attorney"))
        rw("start-stage", str(self.matter), "docs_review")
        artifacts = produce(self.matter, "docs_review")
        refused = rw(*complete_args(self.matter, "docs_review", artifacts, summary="Listed what the victim still needs."), ok=False)
        self.assertIn("names a protected case type", refused.stderr)
        rw(*complete_args(self.matter, "docs_review", artifacts, summary="Listed what is still needed."))
        # The same words pass in a matter that isn't protected; T and U names never do.
        failures = mw.protected_term_failures(stage_summary="Listed what the victim still needs.")
        self.assertEqual(failures, [])
        self.assertTrue(mw.protected_term_failures(stage_summary="Checked the U visa certification."))
        item = {"id": "doc-safety", "type": "client_document", "title": "Records of the abuse", "detail": "Police reports.",
                "blocks_filing": True, "status": "open"}
        path = write(self.matter / "x.json", {"schema_version": 2, "packet_status": "draft", "items": [item]})
        failures: list[str] = []
        mw.validate_open_items(failures, [path], [], protected=True)
        self.assertTrue(any("client request is built from it" in failure for failure in failures), failures)
        failures = []
        mw.validate_open_items(failures, [path], [], protected=False)
        self.assertEqual(failures, [])

    def test_the_docs_review_marks_a_matter_protected_but_never_unmarks_it(self) -> None:
        rw("set-protected", str(self.matter), "--on", "--reason", "docs_review")
        self.assertEqual(ms.read_meta(self.matter)["protected_reason"], "docs_review")
        refused = rw("set-protected", str(self.matter), "--off", "--reason", "docs_review", ok=False)
        self.assertIn("Only the attorney lifts", refused.stderr)
        rw("set-protected", str(self.matter), "--off", "--reason", "attorney")
        self.assertFalse(ms.read_meta(self.matter)["protected"])

    def test_an_older_vawa_matter_without_the_flag_still_counts_as_protected(self) -> None:
        from scripts.matter_protection import is_protected_matter
        matter = self.other_matter()
        rw("ensure", str(matter), "--matter-type", VAWA, "--filing-posture", "new filing packet", "--deliverable", "packet")
        self.assertTrue(is_protected_matter(matter))
        self.assertFalse(is_protected_matter(self.matter))
        meta = json.loads(rw("status", str(matter), "--json").stdout)["meta"]
        self.assertEqual((meta["protected"], meta["protected_reason"]), (True, "case_type"))


class NetworkGateTests(RuntimeCase):
    """Finding 29: the gate logs every check and keeps client facts in the building during an unattended run."""

    def gate(self, *extra: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        return run(str(NETWORK_GATE), str(self.matter), "--action", "mcp_research", "--role", "cover_letter_researcher", "--json",
                   *extra, ok=ok)

    def checks(self) -> list[dict]:
        log = self.matter / "output/privacy/access_log.jsonl"
        return [json.loads(line) for line in log.read_text().splitlines() if '"network_boundary_check"' in line]

    def test_unattended_runs_never_send_client_facts(self) -> None:
        self.gate()
        refused = self.gate("--sends-client-data", ok=False)
        self.assertNotEqual(refused.returncode, 0)
        self.gate("--sends-client-data", "--confirmed")  # an attended session the attorney confirmed
        rw("lease", "acquire", str(self.matter), "--run-id", "bg", "--holder", "app")
        refused = self.gate("--sends-client-data", "--confirmed", ok=False)
        self.assertIn("unattended run", refused.stderr)
        # The matter chat talks with the attorney, who can say yes.
        run(str(NETWORK_GATE), str(self.matter), "--action", "mcp_research", "--role", "attorney", "--actor", "matter_chat",
            "--sends-client-data", "--confirmed")
        bad = run(str(NETWORK_GATE), str(self.matter), "--action", "email", "--role", "final_review", ok=False)
        self.assertNotEqual(bad.returncode, 0)
        # A run whose lease has gone quiet for an hour is still unattended for this check.
        ms.acquire_lease(self.matter, "quiet", "build", "orchestrator", now=datetime_ago(hours=1))
        refused = self.gate("--sends-client-data", "--confirmed", ok=False)
        self.assertIn("unattended run", refused.stderr)
        decisions = [json.loads(check["notes"]) for check in self.checks()]
        self.assertEqual([d["allowed"] for d in decisions], [True, False, True, False, True, False, False])
        self.assertEqual(decisions[3]["rule"], "unattended")
        self.assertEqual(decisions[5]["rule"], "invalid")

    def test_an_unknown_role_is_refused_in_words(self) -> None:
        for extra in ((), ("--json",)):
            refused = run(str(NETWORK_GATE), str(self.matter), "--action", "official_source", "--role", "paralegal", *extra, ok=False)
            self.assertEqual(refused.returncode, 1)
            self.assertIn("Role 'paralegal' is not allowed", refused.stderr)
            self.assertIn("Pass your stage id as --role", refused.stderr)
            self.assertNotIn("Traceback", refused.stderr)


class ValidatorTests(unittest.TestCase):
    """The review's extras: every artifact of a kind is checked, severities are normalized, ties must fit."""

    def setUp(self) -> None:
        self.root = Path(self.enterContext(TemporaryDirectory()))

    def test_blocks_filing_must_be_a_boolean_and_anything_but_false_blocks(self) -> None:
        path = write(self.root / "open-items.json", {"schema_version": 2, "packet_status": "draft", "items": [
            {"id": "act-sign", "type": "attorney_action", "title": "Sign the G-28.", "blocks_filing": "no", "status": "open"}]})
        failures: list[str] = []
        mw.validate_open_items(failures, [path], [])
        self.assertTrue(any("blocks_filing must be true or false" in f for f in failures), failures)
        self.assertTrue(mw.item_blocks_filing({"blocks_filing": "no"}))
        self.assertTrue(mw.item_blocks_filing({}))
        self.assertFalse(mw.item_blocks_filing({"blocks_filing": False}))
        with self.assertRaises(mw.OpenItemRefused):
            mw.set_open_items_packet_status(json.loads(path.read_text()), "ready_to_file", protected=False, now="2026-10-29T00:00:00+00:00")

    def test_a_record_that_wont_parse_gets_a_plain_error_and_is_written_whole(self) -> None:
        state = write(self.root / "output/working/workflow/matter_status.json", '{"stages": {"docs_review": ')
        with self.assertRaises(ValueError) as caught:
            mw.load_state(state)
        self.assertIn("This matter's workflow record can't be read", str(caught.exception))
        self.assertIn("isn't valid JSON", str(caught.exception))
        self.assertNotIn("--force", str(caught.exception))
        for shape in ("[]", '{"stages": [1], "required_stage_ids": []}'):
            state.write_text(shape)
            with self.assertRaises(ValueError):
                mw.load_state(state)
        # Written to disk (fsync) before it replaces the old file, never in place.
        synced: list[int] = []
        real_fsync = os.fsync
        with unittest.mock.patch.object(ms.os, "fsync", lambda fd: (synced.append(fd), real_fsync(fd))):
            ms.write_json_atomic(state, {"stages": {}})
        self.assertEqual(len(synced), 1)
        self.assertEqual(json.loads(state.read_text()), {"stages": {}})
        self.assertEqual([p.name for p in state.parent.iterdir()], ["matter_status.json"])

    # A stage summary as the record keeps it: each kind of identifier redacted, spacing made plain.
    REDACTED_SUMMARIES = {
        "Saved at /Users/someone/Matters/X/file.pdf, then filed.": ("Saved at [redacted-path], then filed.", True),
        "A-123456789": ("[redacted-a-number]", True),
        "alien number 123456789": ("[redacted-a-number]", True),
        "ALIEN REGISTRATION NO. 12345678": ("[redacted-a-number]", True),
        "Receipt EAC1234567890.": ("Receipt [redacted-receipt].", True),
        "I-94 No. 12345678901": ("[redacted-i94]", True),
        "Passport No. X1234567": ("[redacted-passport]", True),
        "SSN 987-65-4321": ("SSN [redacted-ssn]", True),
        "Case AB1234567 open.": ("Case [redacted-passport-or-receipt] open.", True),
        "Mail jane_sample@example.test": ("Mail [redacted-email]", True),
        "Call (555) 123-4567.": ("Call ([redacted-phone].", True),
        "DOB: 01/02/1990": ("[redacted-dob]", True),
        "Filed 03/12/2024.": ("Filed [redacted-date].", True),
        "Met on March 3, 2021.": ("Met on [redacted-date].", True),
        "Lives at 12 Sample Street.": ("Lives at [redacted-address].", True),
        "Number 12345678901234.": ("Number [redacted-number].", True),
        "Plain   words,\n only.": ("Plain words, only.", False),
    }

    def test_a_summary_is_kept_with_its_identifiers_redacted(self) -> None:
        for summary, expected in self.REDACTED_SUMMARIES.items():
            with self.subTest(summary):
                self.assertEqual(mw.normalize_summary(summary), expected)

    def test_the_second_findings_file_is_checked_too(self) -> None:
        good = write(self.root / "a.json", {"findings": []})
        bad = write(self.root / "b.json", {"findings": [{"id": "F9", "severity": "critical", "title": "x", "status": "open"}]})
        failures: list[str] = []
        mw.validate_findings_sidecar(failures, [good, bad], label="forms review findings")
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("F9 has an unresolved material finding without an owner", failures[0])
        for severity in ("high", "Critical", "blocker", "weird"):
            failures = []
            write(bad, {"findings": [{"id": "F9", "severity": severity, "title": "x"}]})
            mw.validate_findings_sidecar(failures, [bad], label="x")
            self.assertTrue(failures, severity)
        failures = []
        write(bad, {"findings": [{"id": "F9", "severity": "low", "title": "x"}]})
        mw.validate_findings_sidecar(failures, [bad], label="x")
        self.assertEqual(failures, [])
        failures = []
        mw.validate_clean_cover_letter_audit(failures, [write(self.root / "c1.json", {"finding_count": 0}),
                                                        write(self.root / "c2.json", {"finding_count": 2})])
        self.assertEqual(len(failures), 1)

    def test_a_forms_audit_error_needs_an_open_item_about_that_form(self) -> None:
        matter = new_matter(self.root)
        write(matter / "output/deliverables/open-items.json", {"packet_status": "draft", "items": [
            {"id": "q-i94", "type": "client_question", "title": "Luis's I-94 number", "detail": "For the I-485.", "status": "open"},
            {"id": "q-sig", "type": "attorney_action", "title": "Sign the G-28", "status": "open"},
        ]})
        audit = write(matter / "audit.json", {"findings": [
            {"severity": "error", "form": "i-485", "title": "I-94 blank", "open_item": "q-i94"},
            {"severity": "error", "form": "i-130", "title": "Date blank", "open_item": "q-sig"},
            {"severity": "error", "form": "i-130a", "title": "x", "open_item": "q-i94"},
        ]})
        failures: list[str] = []
        mw.validate_clean_forms_audit(failures, [audit], matter_path=matter)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("q-sig for the I-130", failures[0])
        self.assertIn("q-i94 for the I-130A", failures[0])

    def test_a_letter_check_older_than_the_letter_is_refused(self) -> None:
        folder = self.root / "cover-letter" / "main"
        check = write(folder / "letter check.json", {"error_count": 0, "errors": []})
        letter = write(folder / "cover letter.md", "# Letter\n")
        os.utime(check, (letter.stat().st_mtime - 60, letter.stat().st_mtime - 60))
        failures: list[str] = []
        mw.validate_letter_check(failures, [check])
        self.assertTrue(any("changed after its letter check ran" in f for f in failures), failures)
        os.utime(check, None)
        failures = []
        mw.validate_letter_check(failures, [check])
        self.assertEqual(failures, [])
        write(check, {"error_count": 2, "errors": [{}, {}]})
        mw.validate_letter_check(failures, [check])
        self.assertIn("Letter check has 2 error(s)", failures[0])

    # What each artifact path is (retention, reason), as the pass contract reads it.
    ARTIFACT_KINDS = {
        f"{V}/forms/main/form facts.json": ("durable", "forms_fact_table"),
        f"{V}/forms/main/form intent manifest.json": ("durable", "forms_intent_manifest"),
        f"{V}/forms/main/prepared forms audit.json": ("durable", "forms_audit"),
        "output/working/workflow/case_theory_evidence_map.json": ("durable", "case_theory_evidence_map"),
        "output/deliverables/Attorney Memo.md": ("durable", "attorney_memo"),
        "output/deliverables/Client Request.md": ("durable", "client_request"),
        "output/deliverables/open-items.json": ("durable", "open_items"),
        "OUTPUT/DELIVERABLES/OPEN-ITEMS.JSON": ("durable", "open_items"),
        f"{V}/docs-review/main/docs review memo.md": ("durable", "docs_review_memo"),
        f"{V}/docs-review/main/document inventory.json": ("durable", "document_inventory"),
        f"{V}/docs-review/main/docs review checklist.json": ("durable", "docs_review_checklist"),
        f"{V}/review/main/forms review memo.md": ("durable", "forms_review_memo"),
        f"{V}/review/main/forms review findings.json": ("durable", "forms_review_findings"),
        "output\\working\\vault\\review\\main\\forms review findings.json": ("durable", "forms_review_findings"),
        f"{V}/cover-letter/main/cover letter audit.json": ("durable", "cover_letter_audit"),
        "Cover letter notes/x audit.json": ("durable", "cover_letter_audit"),
        f"{V}/cover-letter/main/render audit.json": ("durable", "cover_letter_artifact"),
        "output/deliverables/Cover Letter.docx": ("durable", "cover_letter_output"),
        "output/deliverables/Cover Letter (DRAFT).PDF": ("durable", "cover_letter_output"),
        f"{V}/research/main/authority pack.md": ("durable", "authority_pack"),
        f"{V}/research/main/support matrix.json": ("durable", "support_matrix"),
        f"{V}/cover-letter/main/cover letter review memo.md": ("durable", "cover_letter_review_memo"),
        f"{V}/cover-letter/main/cover letter review findings.json": ("durable", "cover_letter_review_findings"),
        # Only the delivered packet counts as the packet.
        "output/deliverables/Filing Packet (DRAFT).pdf": ("durable", "packet_pdf"),
        "output/deliverables/Filing Packet.pdf": ("durable", "packet_pdf"),
        "output/deliverables/filing packet/exhibit 1.pdf": ("durable", "packet_pdf"),
        "output/deliverables/Filing Packet with Cover Letter.pdf": ("durable", "cover_letter_output"),
        f"{V}/packet/main/packet preview.pdf": ("durable", "packet_artifact"),
        "output/deliverables/Filing Checklist.pdf": ("durable", "deliverable"),
        "Old packet.pdf": ("durable", "general_output"),
        f"{V}/cover-letter/main/letter check.json": ("durable", "letter_check"),
        f"{V}/packet/main/packet manifest.json": ("durable", "packet_manifest"),
        f"{V}/final-review/main/final review memo.md": ("durable", "final_review_memo"),
        f"{V}/final-review/main/final review findings.json": ("durable", "final_review_findings"),
        f"{V}/review/main/packet review memo.md": ("durable", "packet_review_memo"),
        f"{V}/review/main/packet review findings.json": ("durable", "packet_review_findings"),
        f"{V}/adjudicator/main/adjudicator memo.md": ("durable", "adjudicator_memo"),
        f"{V}/adjudicator/main/reroute matrix.json": ("durable", "reroute_matrix"),
        "output/working/forms/.source_xfa/i-130.xml": ("ephemeral", "source_xfa"),
        "output/forms/editable_xfa/i-485.pdf": ("ephemeral", "editable_xfa"),
        "output/working/workflow/snapshots/docs_review.json": ("durable", "workflow_output"),
        f"{V}/docs-review/main/notes.md": ("durable", "docs_review_artifact"),
        f"{V}/cover-letter/main/outline.md": ("durable", "cover_letter_artifact"),
        f"{V}/research/main/notes.md": ("durable", "research_artifact"),
        f"{V}/packet/main/order.md": ("durable", "packet_artifact"),
        f"{V}/review/main/notes.md": ("durable", "review_artifact"),
        f"{V}/final-review/main/notes.md": ("durable", "final_review_artifact"),
        f"{V}/adjudicator/main/notes.md": ("durable", "adjudicator_artifact"),
        f"{V}/scratch/helper.json": ("durable", "vault_artifact"),
        "output/deliverables/Forms/I-130.pdf": ("durable", "deliverable"),
        "output/working/tmp/x.json": ("ephemeral", "ephemeral_helper_output"),
        "tmp/x.json": ("ephemeral", "ephemeral_helper_output"),
        "/tmp/elsewhere.json": ("ephemeral", "ephemeral_helper_output"),
        "output/playwright/shot.png": ("ephemeral", "ephemeral_helper_output"),
        "output/pdf/tmp/page.png": ("ephemeral", "ephemeral_helper_output"),
        "From client/tmp/statement.pdf": ("ephemeral", "ephemeral_helper_output"),
        f"{V}/scratch/tmp/prepared forms audit.json": ("ephemeral", "forms_audit"),
        "Passport.pdf": ("durable", "general_output"),
    }

    def test_each_artifact_path_gets_its_kind(self) -> None:
        for path, (retention, reason) in self.ARTIFACT_KINDS.items():
            with self.subTest(path):
                self.assertEqual(mw.classify_artifact_path(path), {"path": path, "retention": retention, "reason": reason})
        self.assertEqual(mw.owning_stage("output/deliverables/Filing Checklist.pdf"), "attorney_handoff")

    def test_a_passed_review_records_its_open_material_findings(self) -> None:
        matter = new_matter(self.root)
        rw("ensure", str(matter), *INTAKE, "--workflow-key", "packet_build")
        pass_stage(matter, "packet_assembly")
        pass_stage(matter, "final_review")
        counts = state_of(matter)["stages"]["final_review"]["open_material_findings"]
        self.assertEqual(counts, {"count": 1, "by_owner": {"client": 1}, "ids": ["FR1"]})


class FreshAndRedoReviewTests(RuntimeCase):
    """Finding 39: a fresh review the attorney asked for, beside the usual re-review."""

    def test_fresh_lists_the_previous_findings_as_reference_only(self) -> None:
        run_through(self.matter, "forms_reviewer")
        rw("reroute", str(self.matter), "--from-stage", "forms_reviewer", "--reason", "The attorney asked for a fresh review.")
        text = rw("changed-since", str(self.matter), "forms_reviewer", "--fresh").stdout
        self.assertIn("fresh review", text)
        self.assertIn("review everything again, in full", text)
        self.assertIn(f"{V}/review/main/forms review findings.json", text)
        report = json.loads(rw("changed-since", str(self.matter), "forms_reviewer", "--fresh", "--json").stdout)
        self.assertEqual(report["review"], "fresh")
        self.assertEqual(report["changed"], [])
        self.assertEqual(json.loads(rw("changed-since", str(self.matter), "forms_reviewer", "--json").stdout)["review"], "re_review")


class FullRunTests(RuntimeCase):
    """One run through every stage, with the forms sent back once by the final review, and a clean handoff."""

    def test_a_whole_run_with_one_loop(self) -> None:
        rw("lease", "acquire", str(self.matter), "--run-id", "full-run")
        run_through(self.matter, "final_review")
        out = rw("reroute", str(self.matter), "--from-stage", "forms_preparer", "--reason", "Final review found a forms defect.",
                 "--detected-in-stage", "final_review").stdout
        self.assertIn("Re-reviews: forms_reviewer, cover_letter_reviewer, final_review.", out)
        self.assertEqual(rw("next-stages", str(self.matter)).stdout.split(), ["forms_preparer"])
        # The fix changes a form, so every pass after it has new work to record.
        rw("start-stage", str(self.matter), "forms_preparer")
        write(self.matter / "output/deliverables/Forms/I-130.pdf", "%PDF-1.4 I-130 v2")
        write(self.matter / f"{V}/forms/main/form facts.json", {"facts": [{"key": "x", "value": "fixed"}]})
        rw(*complete_args(self.matter, "forms_preparer", produce_keep(self.matter, "forms_preparer")))
        self.assertEqual(rw("next-stages", str(self.matter)).stdout.split(), ["forms_reviewer", "cover_letter_writer_draft"])
        for stage_id in ("forms_reviewer", "cover_letter_writer_draft"):
            rw("start-stage", str(self.matter), stage_id)
        write(self.matter / f"{V}/review/main/forms review findings.json",
              {"findings": [{"id": "F1", "severity": "major", "title": "Last-arrival date", "owner": "forms_preparer",
                             "status": "resolved", "resolution": "Fixed."}]})
        rw(*complete_args(self.matter, "forms_reviewer", produce_keep(self.matter, "forms_reviewer")))
        write(self.matter / "output/deliverables/Cover Letter.docx", "letter v2")
        rw(*complete_args(self.matter, "cover_letter_writer_draft", produce_keep(self.matter, "cover_letter_writer_draft")))
        for stage_id, path, content in (
            ("cover_letter_researcher", f"{V}/research/main/support matrix.json", {"propositions": [{"id": "P1"}]}),
            ("cover_letter_writer_integrate", "output/deliverables/Cover Letter.docx", "letter v3"),
            ("cover_letter_reviewer", f"{V}/cover-letter/main/cover letter review findings.json", {"findings": [], "reviewed_at": "again"}),
            ("packet_assembly", "output/deliverables/Filing Packet (DRAFT).pdf", "%PDF-1.4 packet v2"),
            ("final_review", f"{V}/final-review/main/final review findings.json", {"findings": [], "overall_outcome": "approvable"}),
        ):
            rw("start-stage", str(self.matter), stage_id)
            write(self.matter / path, content)
            rw(*complete_args(self.matter, stage_id, produce_keep(self.matter, stage_id)))
        rw("start-stage", str(self.matter), "attorney_handoff")
        write(self.matter / "output/deliverables/Attorney Memo.md", "# Attorney memo\nReady.\n")
        write(self.matter / "output/deliverables/Attorney Memo.pdf", "%PDF-1.4 memo, ready")
        write(self.matter / "output/deliverables/open-items.json", {"schema_version": 2, "packet_status": "ready_to_file", "items": []})
        rw(*complete_args(self.matter, "attorney_handoff", produce_keep(self.matter, "attorney_handoff")))
        rw("lease", "release", str(self.matter), "--run-id", "full-run")
        state = state_of(self.matter)
        self.assertEqual(state["overall_status"], "passed")
        self.assertEqual(rw("next-stage", str(self.matter)).stdout.strip(), "")
        self.assertIn("Packet: ready to file", rw("status", str(self.matter)).stdout)
        self.assertEqual(state["stages"]["final_review"]["open_material_findings"]["count"], 0)
        self.assertEqual(len(state["stages"]["forms_preparer"]["timing"]["attempts"]), 2)
        kinds = [event["kind"] for event in self.events()]
        self.assertIn("rerouted", kinds)
        self.assertEqual(kinds.count("stage_passed"), 10 + 8)


class ExtractTests(unittest.TestCase):
    """CONTRACTS §10: extracts once, again only for what changed, with the language of each page."""

    def test_extracts_index_and_language(self) -> None:
        from scripts.extract_documents import extract_matter
        with TemporaryDirectory() as tmp:
            matter = Path(tmp) / "Matter"
            write(matter / "Letter.txt", "This letter is written by the petitioner and the date of the marriage is in the record of the county.")
            write(matter / "From client/Acta.txt", "El acta de nacimiento fue registrada en el libro del registro civil por el padre y la madre del niño.")
            write(matter / "Photo.jpg", "jpeg")
            write(matter / "output/deliverables/Cover Letter.md", "not a client document")
            first = extract_matter(matter)
            files = first["files"]
            self.assertEqual(sorted(files), ["From client/Acta.txt", "Letter.txt", "Photo.jpg"])
            self.assertEqual(files["Letter.txt"]["language"], "en")
            self.assertFalse(files["Letter.txt"]["needs_translation"])
            self.assertEqual(files["From client/Acta.txt"]["language"], "es")
            self.assertEqual(files["From client/Acta.txt"]["non_english_pages"], [1])
            self.assertTrue(files["From client/Acta.txt"]["needs_translation"])
            self.assertEqual(files["Photo.jpg"]["method"], "none")
            digest = files["Letter.txt"]["sha256"]
            self.assertTrue((matter / "output/working/extracts" / f"{digest}.txt").is_file())
            index = json.loads((matter / "output/working/extracts/index.json").read_text())
            self.assertEqual(index["version"], 1)
            # Again: nothing new is extracted; a removed document's extract goes.
            (matter / "Photo.jpg").unlink()
            second = extract_matter(matter)
            self.assertEqual((second["extracted"], second["reused"]), (0, 2))
            self.assertEqual(sorted(second["files"]), ["From client/Acta.txt", "Letter.txt"])

    def test_a_script_many_languages_share_is_named_as_the_script(self) -> None:
        from scripts.extract_documents import extract_matter
        with TemporaryDirectory() as tmp:
            matter = Path(tmp) / "Matter"
            write(matter / "Svidetelstvo.txt", "Свидетельство о рождении выдано отделом записи актов гражданского состояния города.")
            entry = extract_matter(matter)["files"]["Svidetelstvo.txt"]
            self.assertEqual((entry["language"], entry["language_name"], entry["script_only"]),
                             ("cyrillic", "a language written in Cyrillic script", True))
            self.assertTrue(entry["needs_translation"])
            # An index an earlier extractor wrote, naming the script as one language, is put right on the next run.
            index_path = matter / "output/working/extracts/index.json"
            index = json.loads(index_path.read_text())
            index["files"]["Svidetelstvo.txt"].update(language="ru", language_name="Cyrillic script (Russian, Ukrainian, or another)")
            del index["files"]["Svidetelstvo.txt"]["script_only"]
            write(index_path, index)
            again = extract_matter(matter)
            self.assertEqual(again["reused"], 1)
            entry = again["files"]["Svidetelstvo.txt"]
            self.assertEqual((entry["language"], entry["language_name"], entry["script_only"]),
                             ("cyrillic", "a language written in Cyrillic script", True))


class SetupScriptTests(unittest.TestCase):
    """auto_update.py changes only its own entry, refuses a damaged settings file in words, and writes atomically."""

    SCRIPT = PLUGIN_ROOT / "skills" / "setup" / "scripts" / "auto_update.py"

    def run_script(self, config: Path, *args: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "CLAUDE_CONFIG_DIR": str(config)}
        return subprocess.run([sys.executable, str(self.SCRIPT), *args], capture_output=True, text=True, env=env, timeout=60)

    def test_on_keeps_other_settings_and_a_damaged_file_is_left_alone(self) -> None:
        with TemporaryDirectory() as tmp:
            config = Path(tmp)
            settings = config / "settings.json"
            write(settings, {"theme": "dark", "extraKnownMarketplaces": {"other": {"autoUpdate": False}}})
            os.chmod(settings, 0o640)
            result = self.run_script(config, "on")
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(settings.read_text())
            self.assertEqual(data["theme"], "dark")
            self.assertEqual(data["extraKnownMarketplaces"]["other"], {"autoUpdate": False})
            self.assertTrue(data["extraKnownMarketplaces"]["document-automation"]["autoUpdate"])
            self.assertEqual(settings.stat().st_mode & 0o777, 0o640)
            self.assertEqual([p.name for p in config.iterdir()], ["settings.json"])  # no temporary file left
            settings.write_text('{"theme": "dark",\n  oops}')
            result = self.run_script(config, "off")
            self.assertEqual(result.returncode, 1)
            self.assertIn("has a mistake in it at line 2", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(settings.read_text(), '{"theme": "dark",\n  oops}')


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None) -> unittest.TestSuite:
    """The app server's tests live beside these, in test_server.py; this file's one command runs both."""
    spec = importlib.util.spec_from_file_location("test_server", Path(__file__).with_name("test_server.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tests.addTests(loader.loadTestsFromModule(module))
    return tests


class OpenItemsCommandTests(RuntimeCase):
    """Side-by-side stages change open-items.json through one locked command that keeps the contract's rules."""

    def items(self) -> dict:
        return json.loads((self.matter / "output/deliverables/open-items.json").read_text())

    def upsert(self, item: dict, ok: bool = True) -> subprocess.CompletedProcess[str]:
        return rw("open-items", "upsert", str(self.matter), "--item-json", json.dumps(item), ok=ok)

    I94 = {"id": "doc-i94", "type": "client_document", "title": "Luis's I-94 arrival record", "blocks_filing": True,
           "detail": "Proves he was admitted. He can print it free from the CBP site.", "stage": "docs_review"}
    I765 = {"id": "decide-i765", "type": "attorney_decision", "title": "File an I-765 with the I-485?",
            "question": "Include an I-765 work permit application with the I-485?", "recommendation": "Yes, if he wants to work.",
            "blocks_filing": False}

    def test_items_are_added_changed_and_noted_without_touching_the_rest(self) -> None:
        self.assertIn("Added open item doc-i94.", self.upsert(self.I94).stdout)
        ledger = self.items()
        self.assertEqual((ledger["schema_version"], ledger["packet_status"]), (2, "draft"))
        self.upsert(self.I765)
        self.upsert({"id": "doc-i94", "notes": ["Forms: left the I-94 number blank on the I-485."]})
        rw("open-items", "note", str(self.matter), "doc-i94", "Cover letter: cited as an exhibit to be supplied.")
        self.upsert({"id": "decide-i765", "status": "resolved", "resolution": "The attorney chose to file it."})
        items = {it["id"]: it for it in self.items()["items"]}
        self.assertEqual(items["doc-i94"]["notes"], ["Forms: left the I-94 number blank on the I-485.",
                                                     "Cover letter: cited as an exhibit to be supplied."])
        self.assertEqual(items["doc-i94"]["detail"], self.I94["detail"])
        self.assertEqual((items["decide-i765"]["status"], items["decide-i765"]["question"]), ("resolved", self.I765["question"]))
        refused = rw("open-items", "note", str(self.matter), "doc-gone", "Forms: something.", ok=False)
        self.assertIn("no open item 'doc-gone'", refused.stderr)

    def test_a_blocking_item_keeps_the_packet_status_honest(self) -> None:
        write(self.matter / "output/deliverables/open-items.json", {"schema_version": 2, "packet_status": "ready_to_file", "items": []})
        self.upsert(self.I765)
        self.assertEqual(self.items()["packet_status"], "ready_to_file")  # not needed before filing
        self.upsert(self.I94)
        self.assertEqual(self.items()["packet_status"], "draft")
        refused = rw("open-items", "packet-status", str(self.matter), "ready_to_file", ok=False)
        self.assertIn("still block filing", refused.stderr)
        self.upsert({"id": "doc-i94", "status": "resolved", "resolution": "The client sent it."})
        rw("open-items", "packet-status", str(self.matter), "ready_to_file")
        self.assertEqual(self.items()["packet_status"], "ready_to_file")

    def test_the_handoff_marks_an_older_list_current_only_once_its_items_keep_the_rules(self) -> None:
        write(self.matter / "output/deliverables/open-items.json", {"packet_status": "draft", "items": [
            dict(self.I94, detail="Forms (2026-10-28): see output/deliverables/Forms/I-485.pdf.")]})
        refused = rw("open-items", "packet-status", str(self.matter), "draft", ok=False)
        self.assertIn("Open item doc-i94", refused.stderr)
        self.assertNotIn("schema_version", self.items())
        self.upsert({"id": "doc-i94", "detail": self.I94["detail"], "notes": ["Forms: left the I-94 number blank on the I-485."]})
        rw("open-items", "packet-status", str(self.matter), "draft")
        self.assertEqual(self.items()["schema_version"], 2)

    def test_an_item_that_breaks_the_contract_is_refused_and_nothing_changes(self) -> None:
        self.upsert(self.I94)
        before = self.items()
        cases = {
            "a decision without a question": dict(self.I765, id="decide-x", question=None),
            "a file path": dict(self.I94, id="doc-x", detail="See output/deliverables/Forms/I-485.pdf for the gap."),
            "another item's id": dict(self.I94, id="doc-y", detail="Needed with doc-i94 before filing."),
            "a step name": dict(self.I94, id="doc-z", detail="The forms_preparer left it blank."),
            "no blocks_filing": {k: v for k, v in self.I94.items() if k != "blocks_filing"} | {"id": "doc-w"},
            "an unreadable id": dict(self.I94, id="I 94 / record"),
        }
        for label, item in cases.items():
            with self.subTest(label):
                refused = self.upsert({k: v for k, v in item.items() if v is not None}, ok=False)
                self.assertNotEqual(refused.returncode, 0)
                self.assertTrue(refused.stderr.strip())
        self.assertEqual(self.items(), before)
        write(self.matter / "output/deliverables/open-items.json", '{"items": [')
        refused = self.upsert(self.I765, ok=False)
        self.assertIn("can't be read", refused.stderr)
        self.assertEqual((self.matter / "output/deliverables/open-items.json").read_text(), '{"items": [')

    def test_what_the_attorney_marked_in_the_app_is_kept(self) -> None:
        self.upsert(self.I94)
        ms.record_attorney_action(self.matter, "resolve", "doc-i94", "The client sent it.")
        self.upsert(self.I765)  # another stage changing another item
        item = next(it for it in self.items()["items"] if it["id"] == "doc-i94")
        self.assertEqual((item["status"], item["resolved_by"]), ("resolved", "attorney"))
        refused = self.upsert({"id": "doc-i94", "status": "open"}, ok=False)
        self.assertIn("The attorney marked this item done in the app", refused.stderr)
        rw("open-items", "note", str(self.matter), "doc-i94", "Forms: filled in the I-94 number.")

    def test_a_protected_matters_client_items_stay_neutral(self) -> None:
        rw("set-protected", str(self.matter), "--on", "--reason", "attorney")
        refused = self.upsert(dict(self.I94, id="doc-abuse", title="Police report of the abuse"), ok=False)
        self.assertIn("names the case", refused.stderr)
        self.upsert(dict(self.I94, id="doc-safety", title="Documents about your safety"))

    def test_the_forms_builds_suggested_edition_items_go_in_as_they_are(self) -> None:
        # The forms preparer adds the build log's summary.suggested_open_items with this command, unchanged.
        spec = importlib.util.spec_from_file_location("forms_editions", PLUGIN_ROOT / "scripts" / "forms" / "editions.py")
        editions = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(editions)
        checks = [
            {"kind": "i-485", "status": editions.NEW_EDITION, "file_edition": "01/20/27", "schema_edition": "09/18/26"},
            {"kind": "i-130", "status": editions.CHANGED_BOXES, "file_edition": "04/01/24", "schema_edition": "04/01/24"},
        ]
        for check in checks:
            with self.subTest(check["status"]):
                item = editions.suggested_open_item(check)
                self.assertIn("Added open item", self.upsert(item).stdout)
                stored = next(it for it in self.items()["items"] if it["id"] == item["id"])
                self.assertEqual({k: stored[k] for k in item}, item)
        self.assertEqual(self.items()["packet_status"], "draft")

    def test_stages_side_by_side_never_lose_each_others_items(self) -> None:
        processes = [
            subprocess.Popen([sys.executable, str(RW), "open-items", "upsert", str(self.matter), "--item-json",
                              json.dumps(dict(self.I94, id=f"doc-{n}", title=f"Document number {n}"))],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for n in range(6)
        ]
        for process in processes:
            _out, err = process.communicate(timeout=120)
            self.assertEqual(process.returncode, 0, err)
        self.assertEqual(sorted(it["id"] for it in self.items()["items"]), [f"doc-{n}" for n in range(6)])


class SkillTextTests(unittest.TestCase):
    """What the agents and skills tell each other: cross-references that land, and steps that keep the work whole."""

    def test_runs_pass_their_run_id_on_every_change_and_stop_on_exit_3(self) -> None:
        skill = (PLUGIN_ROOT / "skills/senior-associate/SKILL.md").read_text(encoding="utf-8")
        start = skill.split("## Start or resume", 1)[1].split("```", 2)[1]
        for line in start.splitlines():
            command = line.split('"$RW" ', 1)[1].split(" ", 1)[0] if '"$RW" ' in line else ""
            if command in {"ensure", "apply-attorney-actions"}:
                self.assertIn("--run-id", line, command)
        self.assertIn('lease heartbeat "<matter>" --run-id <id>', skill)
        self.assertIn("Another run holds this matter now; stop.", skill)
        self.assertIn("Pass `--run-id <id>` on every runtime command you run that changes the matter", skill)
        chat = (PLUGIN_ROOT / "skills/matter-chat/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("pass it as `--run-id <id>` on every runtime command that changes the matter", chat)
        runtime = (PLUGIN_ROOT / "skills/senior-associate/references/runtime.md").read_text(encoding="utf-8")
        self.assertIn("`--run-id ID` on any other command", runtime)

    TEXTS = sorted([*PLUGIN_ROOT.glob("agents/*.md"), *PLUGIN_ROOT.glob("skills/*/SKILL.md"), *PLUGIN_ROOT.glob("skills/*/references/*.md")])

    @staticmethod
    def section(name: str) -> tuple[Path, str] | None:
        import re
        for path in SkillTextTests.TEXTS:
            text = path.read_text(encoding="utf-8")
            match = re.search(rf"^(#+)\s+{re.escape(name)}\s*$", text, re.M)
            if match:
                rest = text[match.end():]
                end = re.search(rf"^#{{1,{len(match.group(1))}}}\s", rest, re.M)
                return path, rest[: end.start()] if end else rest
        return None

    def test_every_numbered_step_reference_lands_on_its_step(self) -> None:
        import re
        reference = re.compile(r'"([A-Z][^"\n]{2,60})"\s*(?:\(step (\d+)\)|step (\d+))')
        found = 0
        for path in self.TEXTS:
            for name, a, b in reference.findall(path.read_text(encoding="utf-8")):
                found += 1
                target = self.section(name)
                self.assertIsNotNone(target, f"{path.name}: no section named {name!r}")
                steps = re.findall(r"^(\d+)\. ", target[1], re.M)
                self.assertIn(a or b, steps, f"{path.name}: {name!r} has no step {a or b}")
        self.assertGreater(found, 0)
        # The orchestrator's report: the step it points to is the one about the report.
        agent = (PLUGIN_ROOT / "agents" / "senior-associate.md").read_text(encoding="utf-8")
        number = re.search(r'"Finish every run" \(step (\d+)\)', agent).group(1)
        step = re.search(rf"^{number}\. (.+)$", self.section("Finish every run")[1], re.M).group(1)
        self.assertTrue(step.startswith("End with a short report"), step)
        self.assertIn("at most two open items", step)

    def test_the_open_items_change_only_through_the_locked_command(self) -> None:
        import re
        editing = re.compile(r"(?<!never )(?<!not )\b(?:edit|add to|append to|write to|rewrite|open items? to)\s+`?(?:output/deliverables/)?open-items\.json", re.I)
        for relative in ("skills/docs-review/SKILL.md", "skills/coverletter/SKILL.md", "skills/final-review/SKILL.md",
                         "skills/packet-assembly/SKILL.md", "skills/matter-chat/SKILL.md", "skills/senior-associate/SKILL.md",
                         "skills/senior-associate/references/handoff.md", "skills/forms-preparer/SKILL.md",
                         "skills/forms-reviewer/SKILL.md"):
            with self.subTest(relative):
                text = (PLUGIN_ROOT / relative).read_text(encoding="utf-8")
                self.assertIsNone(editing.search(text), relative)
                self.assertRegex(text, r"open-items (?:upsert|note)")

    def test_every_review_reviews_everything_when_the_brief_asks_for_a_fresh_review(self) -> None:
        for relative, stage_id in (("skills/forms-reviewer/SKILL.md", "forms_reviewer"),
                                   ("skills/coverletter/SKILL.md", "cover_letter_reviewer"),
                                   ("skills/final-review/SKILL.md", "final_review")):
            with self.subTest(stage_id):
                text = (PLUGIN_ROOT / relative).read_text(encoding="utf-8")
                self.assertIn(f'changed-since "<matter>" {stage_id} --fresh', text)

    def test_the_final_review_checks_every_form_edition_live_and_never_passes_an_unread_page(self) -> None:
        review = (PLUGIN_ROOT / "skills" / "final-review" / "SKILL.md").read_text(encoding="utf-8")
        step = review.split("2. **Check currency.**", 1)[1].split("\n3. ", 1)[0]
        self.assertIn('scripts/forms/forms_workflow.py" editions "<matter>" --live', step)
        self.assertIn("Exit 1", step)
        self.assertIn("finding with an owner, never a pass", step)
        self.assertIn("`manual_review` finding: check that form's uscis.gov page by hand", step)

    def test_the_i693_rule_is_said_once_by_its_owner(self) -> None:
        import re
        exceptions = re.compile(r"The exceptions \(I-693 instructions, ed\. 01/20/25, FAQs 2-5, checked [0-9-]+\): .+? since\.")
        edition = "A civil surgeon signature dated July 3, 2025 or later must be on the 01/20/25 edition of the I-693"
        # The exceptions and the edition rule live in the evidence checklist's common rules, once.
        owner = (PLUGIN_ROOT / "skills/docs-review/references/evidence-checklists.md").read_text(encoding="utf-8")
        found = exceptions.findall(owner)
        self.assertEqual(len(found), 1)
        for needed in ("one year after admission", "asylee derivative filing within a year of becoming eligible",
                       "K-1 to K-4", "within a year of the overseas exam", "Operation Allies Welcome"):
            self.assertIn(needed, found[0])
        self.assertIn(edition, owner)
        self.assertIn("I-485 instructions, ed. 09/18/26, item 9", owner)
        # The blocking rule lives in the matter contract's open items, and points at the owner.
        contract = (PLUGIN_ROOT / "skills/senior-associate/references/matter-contract.md").read_text(encoding="utf-8")
        self.assertIn("I-485 instructions, ed. 09/18/26, item 9", contract)
        self.assertIn("evidence-checklists.md", contract)
        # Nobody else restates the exceptions.
        for path in [*self.TEXTS, *PLUGIN_ROOT.glob("skills/docs-review/references/checklists/*.md")]:
            if path.name == "evidence-checklists.md":
                continue
            text = path.read_text(encoding="utf-8")
            with self.subTest(path.name):
                self.assertEqual(exceptions.findall(text), [])
                self.assertNotIn("Operation Allies Welcome", text)
                self.assertNotIn("I-730 asylee", text)
                self.assertNotIn("Afghan parolees", text)

    def test_a_letter_changed_in_chat_gets_its_letter_check_again(self) -> None:
        chat = (PLUGIN_ROOT / "skills" / "matter-chat" / "SKILL.md").read_text(encoding="utf-8")
        letter = next(line for line in chat.splitlines() if line.startswith("- **Cover letter:**"))
        self.assertIn("letter_check.py", letter)
        self.assertIn("after every edit to the letter", letter)


if __name__ == "__main__":
    unittest.main()

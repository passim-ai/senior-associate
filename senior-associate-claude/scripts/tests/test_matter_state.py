#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Offline tests for the shared matter state (scripts/matter_state.py). Every matter here is synthetic.

    uv run --script scripts/tests/test_matter_state.py
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import multiprocessing
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts import matter_state as ms  # noqa: E402

T0 = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)


def ledger(*items: dict) -> dict:
    return {"schema_version": 2, "updated_at": "2026-10-29T11:00:00+00:00", "packet_status": "draft", "items": list(items)}


def _append_many(matter: str, start: int) -> None:
    for i in range(start, start + 25):
        ms.record_attorney_action(Path(matter), "resolve", f"item-{i}")


class LockAndFiles(unittest.TestCase):
    def test_read_json_states(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.json"
            self.assertEqual(ms.read_json(path).state, "missing")
            path.write_text("", encoding="utf-8")
            self.assertEqual(ms.read_json(path).state, "damaged")
            path.write_text('{"a": 1,}', encoding="utf-8")
            self.assertEqual(ms.read_json(path).state, "damaged")
            ms.write_json_atomic(path, {"a": 1})
            self.assertEqual(ms.read_json(path).data, {"a": 1})
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["x.json"])  # no temp files left
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)  # matter files hold client facts

    def test_paths_hashes_and_stamps(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp) / "Matter"
            (matter / "From client").mkdir(parents=True)
            document = matter / "From client" / "Passport.pdf"
            document.write_bytes(b"%PDF-1.4")
            self.assertEqual(ms.relative_to_matter(matter, document), "From client/Passport.pdf")
            self.assertEqual(ms.relative_to_matter(matter, Path(tmp)), Path(tmp).resolve().as_posix())
            self.assertEqual(ms.sha256_file(document), hashlib.sha256(b"%PDF-1.4").hexdigest())
        self.assertEqual(ms.now_iso(T0), "2026-10-29T12:00:00+00:00")
        self.assertEqual(ms.now_iso(T0.replace(microsecond=5), precise=True), "2026-10-29T12:00:00.000005+00:00")

    def test_open_items_shape(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            self.assertEqual(ms.read_open_items(matter).state, "missing")
            ms.write_json_atomic(matter / ms.OPEN_ITEMS_FILE, {"items": "nope"})
            self.assertEqual(ms.read_open_items(matter).state, "damaged")
            ms.write_json_atomic(matter / ms.OPEN_ITEMS_FILE, ledger())
            self.assertTrue(ms.read_open_items(matter).ok)

    def test_lock_times_out_while_held(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            with ms.matter_lock(matter):
                ctx = multiprocessing.get_context("spawn")
                with ctx.Pool(1) as pool:
                    held = pool.apply(_try_lock, (str(matter),))
            self.assertEqual(held, "timeout")
            with ms.matter_lock(matter, timeout=0.2):
                pass

    def test_concurrent_appends_keep_every_line(self) -> None:
        with TemporaryDirectory() as tmp:
            ctx = multiprocessing.get_context("spawn")
            procs = [ctx.Process(target=_append_many, args=(tmp, n * 100)) for n in range(4)]
            for p in procs:
                p.start()
            for p in procs:
                p.join(60)
            self.assertEqual(len(ms.attorney_actions(Path(tmp))), 100)

    def test_jsonl_skips_damaged_lines(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "e.jsonl"
            path.write_text('{"a":1}\nnot json\n[1]\n{"b":2}\n', encoding="utf-8")
            self.assertEqual(ms.read_jsonl(path), [{"a": 1}, {"b": 2}])

    def test_app_written(self) -> None:
        self.assertTrue(ms.is_app_written(Path("output/working/workflow/attorney-instructions.md")))
        self.assertTrue(ms.is_app_written(Path("output/deliverables/.open-items.json.123.ab.tmp")))
        self.assertFalse(ms.is_app_written(Path("output/deliverables/open-items.json")))


def _try_lock(matter: str) -> str:
    try:
        with ms.matter_lock(Path(matter), timeout=0.3):
            return "got"
    except ms.LockTimeout:
        return "timeout"


class Lease(unittest.TestCase):
    def test_acquire_refuses_a_fresh_lease_and_takes_a_stale_one(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            ok, lease = ms.acquire_lease(matter, "run-a", "build", "orchestrator", now=T0)
            self.assertTrue(ok)
            ok, held = ms.acquire_lease(matter, "run-b", "update", "chat", now=T0 + timedelta(minutes=5))
            self.assertFalse(ok)
            self.assertEqual(held["run_id"], "run-a")
            ms.heartbeat_lease(matter, stage="forms_preparer", now=T0 + timedelta(minutes=20))
            self.assertTrue(ms.lease_is_fresh(ms.read_lease(matter), now=T0 + timedelta(minutes=45)))
            later = T0 + timedelta(minutes=20 + 31)
            self.assertFalse(ms.lease_is_fresh(ms.read_lease(matter), now=later))
            ok, lease = ms.acquire_lease(matter, "run-b", "update", "chat", now=later)
            self.assertTrue(ok)
            kinds = [e["kind"] for e in ms.read_events(matter)]
            self.assertIn("run_abandoned", kinds)

    def test_same_run_renews_and_keeps_start(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            ms.acquire_lease(matter, "run-a", "build", "app", now=T0)
            ok, lease = ms.acquire_lease(matter, "run-a", "build", "orchestrator", now=T0 + timedelta(seconds=40))
            self.assertTrue(ok)
            self.assertEqual(lease["started_at"], ms.now_iso(T0))
            self.assertEqual(lease["origin"], "app")
            self.assertEqual(lease["holder"], "orchestrator")

    def test_heartbeat_with_other_run_id_changes_nothing(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            self.assertIsNone(ms.heartbeat_lease(matter))
            ms.acquire_lease(matter, "run-a", "build", "app", now=T0)
            self.assertIsNone(ms.heartbeat_lease(matter, run_id="run-z", now=T0 + timedelta(minutes=9)))
            self.assertEqual(ms.read_lease(matter)["heartbeat_at"], ms.now_iso(T0))

    def test_release(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            ms.acquire_lease(matter, "run-a", "build", "app", now=T0)
            self.assertFalse(ms.release_lease(matter, "run-z"))
            self.assertTrue(ms.release_lease(matter, "run-a", "stopped", now=T0 + timedelta(minutes=1)))
            lease = ms.read_lease(matter)
            self.assertFalse(ms.lease_is_fresh(lease, now=T0 + timedelta(minutes=2)))
            self.assertEqual(lease["outcome"], "stopped")
            self.assertIsNone(ms.heartbeat_lease(matter, now=T0 + timedelta(minutes=3)))
            ok, _ = ms.acquire_lease(matter, "run-b", "build", "app", now=T0 + timedelta(minutes=4))
            self.assertTrue(ok)
            self.assertNotIn("run_abandoned", [e["kind"] for e in ms.read_events(matter)])

    def test_a_released_lease_keeps_the_outcome_it_ended_with(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            ms.acquire_lease(matter, "run-a", "build", "app", now=T0)
            ms.acquire_lease(matter, "run-a", "build", "orchestrator", now=T0 + timedelta(minutes=1))
            self.assertTrue(ms.release_lease(matter, "run-a", "stopped", now=T0 + timedelta(minutes=5)))
            # The app's agent then answers, and the app releases the same run: the orchestrator's word stands.
            self.assertFalse(ms.release_lease(matter, "run-a", "done", now=T0 + timedelta(minutes=6)))
            lease = ms.read_lease(matter)
            self.assertEqual((lease["outcome"], lease["released_at"]), ("stopped", ms.now_iso(T0 + timedelta(minutes=5))))

    def test_withdrawing_a_start_nobody_sent_releases_it(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            ms.acquire_lease(matter, "run-a", "build", "app", now=T0)
            self.assertEqual(ms.withdraw_start(matter, "run-z", now=T0 + timedelta(minutes=10)), "gone")
            self.assertEqual(ms.withdraw_start(matter, "run-a", now=T0 + timedelta(minutes=10)), "released")
            self.assertEqual(ms.read_lease(matter)["outcome"], "stopped")
            self.assertEqual(ms.withdraw_start(matter, "run-a", now=T0 + timedelta(minutes=11)), "gone")

    def test_withdrawing_a_start_an_orchestrator_took_up_hands_it_over(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            ms.acquire_lease(matter, "run-a", "build", "app", now=T0)
            ms.heartbeat_lease(matter, "run-a", by_app=True, now=T0 + timedelta(minutes=4))
            # The attorney sent the request from the chat box; its orchestrator renewed the app's run.
            ms.acquire_lease(matter, "run-a", "build", "orchestrator", now=T0 + timedelta(minutes=5))
            self.assertEqual(ms.withdraw_start(matter, "run-a", now=T0 + timedelta(minutes=10)), "taken_up")
            lease = ms.read_lease(matter)
            self.assertFalse(lease["released_at"])
            self.assertEqual((lease["origin"], lease["holder"]), ("orchestrator", "orchestrator"))
            # With the app gone quiet, the run still holds the matter on its own renewals.
            ms.heartbeat_lease(matter, now=T0 + timedelta(minutes=20))
            self.assertTrue(ms.lease_is_fresh(ms.read_lease(matter), now=T0 + timedelta(minutes=30)))
            ok, _ = ms.acquire_lease(matter, "run-b", "build", "app", now=T0 + timedelta(minutes=30))
            self.assertFalse(ok)

    def test_app_started_run_lapses_soon_after_the_app_stops_renewing(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            ms.acquire_lease(matter, "run-a", "build", "app", now=T0)
            ok, lease = ms.acquire_lease(matter, "run-a", "build", "orchestrator", now=T0 + timedelta(minutes=1))
            self.assertTrue(ok)
            self.assertEqual((lease["origin"], lease["holder"]), ("app", "orchestrator"))
            ms.heartbeat_lease(matter, "run-a", by_app=True, now=T0 + timedelta(minutes=2))
            ms.heartbeat_lease(matter, now=T0 + timedelta(minutes=4))  # a runtime command; the app has gone quiet
            self.assertTrue(ms.lease_is_fresh(ms.read_lease(matter), now=T0 + timedelta(minutes=4, seconds=59)))
            self.assertFalse(ms.lease_is_fresh(ms.read_lease(matter), now=T0 + timedelta(minutes=5, seconds=1)))
            ok, _ = ms.acquire_lease(matter, "run-b", "update", "app", now=T0 + timedelta(minutes=6))
            self.assertTrue(ok)

    def test_an_orchestrator_taking_up_an_abandoned_app_start_holds_the_matter(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            ms.acquire_lease(matter, "run-a", "build", "app", now=T0)
            ms.release_lease(matter, "run-a", "stopped", now=T0 + timedelta(minutes=10))  # the app gave up on the chat box
            ok, lease = ms.acquire_lease(matter, "run-a", "build", "orchestrator", now=T0 + timedelta(minutes=12))
            self.assertTrue(ok)
            self.assertEqual(lease["origin"], "orchestrator")
            self.assertFalse(lease["released_at"])
            self.assertTrue(ms.lease_is_fresh(ms.read_lease(matter), now=T0 + timedelta(minutes=30)))
            ok, _ = ms.acquire_lease(matter, "run-b", "build", "app", now=T0 + timedelta(minutes=31))
            self.assertFalse(ok)

    def test_a_stale_app_lease_taken_up_by_its_orchestrator_starts_over(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            ms.acquire_lease(matter, "run-a", "build", "app", now=T0)
            ok, lease = ms.acquire_lease(matter, "run-a", "build", "orchestrator", now=T0 + timedelta(minutes=8))
            self.assertTrue(ok)
            self.assertEqual(lease["origin"], "orchestrator")

    def test_runs_started_elsewhere_keep_the_30_minute_rule(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            ms.acquire_lease(matter, "run-c", "build", "orchestrator", now=T0)
            self.assertTrue(ms.lease_is_fresh(ms.read_lease(matter), now=T0 + timedelta(minutes=20)))
            with self.assertRaises(ValueError):
                ms.heartbeat_lease(matter, by_app=True)

    def test_a_renewal_stamped_far_ahead_is_no_sign_of_life(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            ms.acquire_lease(matter, "run-c", "build", "orchestrator", now=T0 + timedelta(minutes=4))
            self.assertTrue(ms.lease_is_fresh(ms.read_lease(matter), now=T0))  # a clock a little ahead
            ms.acquire_lease(matter, "run-c", "build", "orchestrator", now=T0 + timedelta(minutes=6))
            self.assertFalse(ms.lease_is_fresh(ms.read_lease(matter), now=T0))
            # Taken by another run, as a stale one is.
            ok, _ = ms.acquire_lease(matter, "run-d", "build", "app", now=T0)
            self.assertTrue(ok)

    def test_a_run_renews_only_its_own_lease_and_learns_when_it_lost_the_matter(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            self.assertEqual(ms.renew_run_lease(matter, "run-a"), (ms.RUN_NO_LEASE, None))
            ms.acquire_lease(matter, "run-a", "build", "orchestrator", now=T0)
            what, lease = ms.renew_run_lease(matter, "run-a", stage="forms_preparer", now=T0 + timedelta(minutes=45))
            self.assertEqual((what, lease["stage"]), (ms.RUN_RENEWED, "forms_preparer"))  # its own, though quiet
            self.assertEqual(ms.read_lease(matter)["heartbeat_at"], ms.now_iso(T0 + timedelta(minutes=45)))
            later = T0 + timedelta(minutes=90)
            ms.acquire_lease(matter, "run-b", "build", "app", now=later)
            self.assertEqual(ms.renew_run_lease(matter, "run-a", now=later)[0], ms.RUN_TAKEN)
            self.assertEqual(ms.read_lease(matter)["heartbeat_at"], ms.now_iso(later))  # run-b's, untouched
            ms.release_lease(matter, "run-b", "done", now=later)
            self.assertEqual(ms.renew_run_lease(matter, "run-a", now=later)[0], ms.RUN_LOST)
            self.assertEqual(ms.renew_run_lease(matter, "run-b", now=later)[0], ms.RUN_ENDED)

    def test_a_long_tool_renews_only_a_fresh_lease(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            self.assertFalse(ms.sign_of_life(matter))
            ms.acquire_lease(matter, "run-a", "build", "orchestrator", now=T0)
            self.assertTrue(ms.sign_of_life(matter, now=T0 + timedelta(minutes=20)))
            self.assertEqual(ms.read_lease(matter)["heartbeat_at"], ms.now_iso(T0 + timedelta(minutes=20)))
            self.assertFalse(ms.sign_of_life(matter, now=T0 + timedelta(minutes=60)))  # gone quiet: never revived
            self.assertEqual(ms.read_lease(matter)["heartbeat_at"], ms.now_iso(T0 + timedelta(minutes=20)))
            # A tool calling it in a loop renews at most once in `every` seconds.
            ms._last_sign_of_life.clear()
            self.assertTrue(ms.sign_of_life(matter, now=T0 + timedelta(minutes=21), every=30))
            self.assertFalse(ms.sign_of_life(matter, now=T0 + timedelta(minutes=22), every=30))

    def test_unknown_holder_refused(self) -> None:
        with TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            ms.acquire_lease(Path(tmp), "r", "build", "someone")


class AttorneyActions(unittest.TestCase):
    ITEMS = (
        {"id": "doc-i94", "type": "client_document", "title": "I-94", "blocks_filing": True, "status": "open"},
        {"id": "risk-1", "type": "risk", "title": "A risk", "blocks_filing": False, "status": "open"},
    )

    def test_actions_survive_a_rewrite_from_an_older_copy(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            ms.write_json_atomic(matter / ms.OPEN_ITEMS_FILE, ledger(*self.ITEMS))
            stale = ms.read_open_items(matter).data  # an agent read the list
            ms.record_attorney_action(matter, "resolve", "doc-i94", now=T0)
            ms.record_attorney_action(matter, "accept_risk", "risk-1", now=T0)
            ms.write_json_atomic(matter / ms.OPEN_ITEMS_FILE, stale)  # ...and wrote its old copy back
            shown, applied = ms.apply_attorney_actions(ms.read_open_items(matter).data, ms.attorney_actions(matter))
            self.assertEqual(applied, 2)
            by_id = {it["id"]: it for it in shown["items"]}
            self.assertEqual(by_id["doc-i94"]["status"], "resolved")
            self.assertEqual(by_id["risk-1"]["resolution"], "Risk accepted by the attorney.")
            self.assertEqual(shown["packet_status"], "draft")  # never promoted; an update re-checks the packet

    def test_merge_is_idempotent_and_claude_can_change_a_seen_item(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            ms.write_json_atomic(matter / ms.OPEN_ITEMS_FILE, ledger(*self.ITEMS))
            ms.record_attorney_action(matter, "resolve", "doc-i94", now=T0)
            self.assertEqual(ms.merge_attorney_actions(matter), 1)
            self.assertEqual(ms.merge_attorney_actions(matter), 0)
            data = ms.read_open_items(matter).data
            data["items"][0]["status"] = "open"  # Claude reopens it after seeing the action, keeping the field
            ms.write_json_atomic(matter / ms.OPEN_ITEMS_FILE, data)
            self.assertEqual(ms.merge_attorney_actions(matter), 0)
            self.assertEqual(ms.read_open_items(matter).data["items"][0]["status"], "open")

    def test_reopen_after_resolve_turns_the_packet_back_to_draft(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            done = dict(self.ITEMS[0], status="resolved", resolution="Received.")
            data = ledger(done)
            data["packet_status"] = "ready_to_file"
            ms.write_json_atomic(matter / ms.OPEN_ITEMS_FILE, data)
            ms.record_attorney_action(matter, "reopen", "doc-i94", note="Wrong year.", now=T0)
            shown, _ = ms.apply_attorney_actions(ms.read_open_items(matter).data, ms.attorney_actions(matter))
            self.assertEqual(shown["items"][0]["status"], "open")
            self.assertNotIn("resolution", shown["items"][0])
            self.assertEqual(shown["packet_status"], "draft")

    def test_damaged_list_is_left_alone(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            path = matter / ms.OPEN_ITEMS_FILE
            path.parent.mkdir(parents=True)
            path.write_text('{"items": [', encoding="utf-8")
            ms.record_attorney_action(matter, "resolve", "doc-i94", now=T0)
            self.assertEqual(ms.merge_attorney_actions(matter), 0)
            self.assertEqual(path.read_text(encoding="utf-8"), '{"items": [')

    def test_bad_actions_refused(self) -> None:
        with TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                ms.record_attorney_action(Path(tmp), "delete", "x")
            with self.assertRaises(ValueError):
                ms.record_attorney_action(Path(tmp), "resolve", "")


class AnswersMetaEvents(unittest.TestCase):
    def test_question_key(self) -> None:
        self.assertEqual(ms.question_key("decide-x", "Q?"), "decide-x")
        a = ms.question_key("", "Include an  I-765?")
        self.assertEqual(a, ms.question_key(None, "include an i-765?"))
        self.assertNotEqual(a, ms.question_key("", "Include an I-131?"))

    def test_answers_round_trip(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            ms.save_answer(matter, "k1", "Q one?", "Yes", now=T0)
            ms.save_answer(matter, "k2", "Q two?", "No", now=T0)
            ms.save_answer(matter, "k1", "Q one?", "  ", now=T0)
            self.assertEqual(list(ms.read_answers(matter)), ["k2"])
            ms.clear_answers(matter, ["k2"])
            self.assertEqual(ms.read_answers(matter), {})

    def test_meta_defaults_validation_and_events(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            self.assertEqual(ms.read_meta(matter)["filing_method"], "paper")
            meta = ms.update_meta(matter, protected=True, protected_reason="docs_review", now=T0)
            self.assertEqual(meta["protected_reason"], "docs_review")
            meta = ms.update_meta(matter, protected=False, now=T0)
            self.assertEqual(meta["protected_reason"], "")
            with self.assertRaises(ValueError):
                ms.update_meta(matter, filing_method="fax")
            with self.assertRaises(ValueError):
                ms.update_meta(matter, colour="blue")
            ms.update_meta(matter, filing_method="online", now=T0)
            ms.update_meta(matter, filing_method="online", now=T0)  # no change, no event
            kinds = [e["kind"] for e in ms.read_events(matter)]
            self.assertEqual(kinds.count("meta_filing_method"), 1)
            self.assertEqual(kinds.count("meta_protected"), 2)

    def test_events_in_the_same_second_are_newest_first(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            for text in ("first", "second", "third"):
                ms.add_event(matter, "note", text, now=T0)
            self.assertEqual([e["text"] for e in ms.read_events(matter)], ["third", "second", "first"])

    def test_meta_event_names_who_changed_it(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            ms.update_meta(matter, protected=True, protected_reason="docs_review", actor="claude", now=T0)
            event = ms.read_events(matter)[0]
            self.assertEqual(event["actor"], "claude")
            self.assertEqual(event["text"], "The document review marked this matter protected.")

    def test_events_newest_first_and_limited(self) -> None:
        with TemporaryDirectory() as tmp:
            matter = Path(tmp)
            for i in range(5):
                ms.add_event(matter, "note", f"n{i}", now=T0 + timedelta(minutes=i))
            events = ms.read_events(matter, limit=3)
            self.assertEqual([e["text"] for e in events], ["n4", "n3", "n2"])
            raw = (matter / ms.EVENTS_FILE).read_text(encoding="utf-8").splitlines()
            self.assertEqual(json.loads(raw[0])["actor"], "app")


if __name__ == "__main__":
    unittest.main()

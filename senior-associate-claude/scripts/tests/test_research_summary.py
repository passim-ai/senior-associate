#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Offline tests for the research summary (scripts/research_summary.py): what the app and the memo say about the
research behind a letter, read from the researcher's own records. Every matter here is synthetic.

    uv run --script scripts/tests/test_research_summary.py
"""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts import filing_readiness as fr  # noqa: E402
from scripts import research_summary as rs  # noqa: E402

TODAY = date(2026, 11, 10)
RESEARCH = "output/working/vault/research/main"
RECEIPT = "output/working/workflow/legal currency review.json"


def write(path: Path, content: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    return path


def row(authority: str, citation: str, validity: str, *, source: str = "", checked: str = "2026-11-09", document_id: int | None = None) -> dict:
    made = {"authority": authority, "citation": citation, "url": "https://example.test/a", "pinpoint": "", "quote": "",
            "validity": validity, "weight": "controlling", "checked": checked}
    if source:
        made["source"] = source
    if document_id:
        made["document_id"] = document_id
    return made


STATUTE = row("INA § 212(a)(9)(B)(v)", "8 U.S.C. § 1182(a)(9)(B)(v)", "current statute", source="authorities/i601a.md A2")
CERVANTES = row("Matter of Cervantes-Gonzalez, 22 I&N Dec. 560 (BIA 1999)", "22 I&N Dec. 560",
                "ImmCite treatment_available; precedential citing decisions reviewed, none adverse", source="authorities/i601a.md A7", document_id=618)
OJO = row("Matter of O-J-O-, 21 I&N Dec. 381 (BIA 1996)", "21 I&N Dec. 381",
          "ImmCite caution: limited by Matter of Monreal-Aguinaga for cancellation hardship only", source="authorities/i601a.md A8", document_id=718)
MENDEZ = row("Matter of Mendez-Moralez, 21 I&N Dec. 296 (BIA 1996)", "21 I&N Dec. 296",
             "ImmCite treatment_available; all precedential citing decisions reviewed, no adverse treatment identified", document_id=726)
MANUAL = row("9 USCIS-PM B.5", "9 USCIS Policy Manual pt. B, ch. 5", "current; chapter updated 2025-02-26")


def matrix(*propositions: dict) -> dict:
    return {"slug": "main", "checked": "2026-11-09", "propositions": list(propositions)}


def proposition(pid: str, text: str, support: list[dict], adverse: list | None = None, **extra: object) -> dict:
    return {"id": pid, "proposition": text, "recommendation": "cite", "support": support, "adverse": adverse or [], **extra}


def receipt(checked_at: str = "2026-11-09", **over: object) -> dict:
    hits = [{"id": "PA-2026-16", "url": "https://example.test/pa", "disposition": "not_applicable", "reason": "L-1 fees."},
            {"id": "Matter of Example", "url": "https://example.test/m", "disposition": "applied", "reason": "Narrowed P2."}]
    checks = [{"category": c, "status": "checked", "source": "BIA Edge", "hits": hits if c == "agency_policy" else []}
              for c in ("agency_policy", "regulations", "agency_decisions", "controlling_circuit", "adverse_treatment")]
    return {"connector": {"available": True}, "checked_at": checked_at,
            "jurisdiction": {"forum": "USCIS", "circuit": "ca5", "basis": "residence"}, "checks": checks,
            "relied_on_court_orders": [], "unresolved": []} | over


class SummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.m = Path(self.tmp.name) / "Synthetic I-601A"
        self.m.mkdir()

    def checked_matter(self) -> None:
        write(self.m / RESEARCH / "support matrix.json", matrix(
            proposition("S1", "USCIS may waive the bar on extreme hardship to a qualifying relative.", [STATUTE]),
            proposition("S2", "Extreme hardship exceeds the usual consequences of removal.", [CERVANTES, OJO],
                        adverse=[{"authority": "Matter of Pilch, 21 I&N Dec. 627 (BIA 1996)", "citation": "21 I&N Dec. 627"}]),
            proposition("P1", "Rehabilitation and the age of an adverse factor weigh in discretion.", [MENDEZ, MANUAL],
                        adverse=[{"authority": "Matter of Pilch, 21 I&N Dec. 627 (BIA 1996)", "citation": "21 I&N Dec. 627"}, "INS v. Jong Ha Wang, 450 U.S. 139"]),
        ))
        write(self.m / RECEIPT, receipt())

    def test_no_research_yet_is_no_summary(self) -> None:
        self.assertIsNone(rs.research_summary(self.m, TODAY))
        write(self.m / RESEARCH / "support matrix.json", "{not json")
        self.assertIsNone(rs.research_summary(self.m, TODAY))
        write(self.m / RESEARCH / "support matrix.json", matrix())
        self.assertIsNone(rs.research_summary(self.m, TODAY))
        self.assertEqual(rs.memo_lines(None), ["Research: the cover letter hasn’t been researched yet."])

    def test_checked_with_the_library_counts_what_the_records_say(self) -> None:
        self.checked_matter()
        s = rs.research_summary(self.m, TODAY)
        self.assertEqual((s["state"], s["headline"], s["age_days"]), ("checked", "Checked November 9, 2026 with BIA Edge", 1))
        # Five authorities, three of them cases; the manual chapter and the statute are not cases.
        self.assertEqual((s["authorities"], s["cases"], s["researched"], s["adverse"]), (5, 3, 1, 2))
        self.assertEqual(s["limited"], ["Matter of O-J-O-, 21 I&N Dec. 381 (BIA 1996)"])
        self.assertEqual(s["lines"], [
            "The research supports the letter with 5 authorities, 3 of them cases.",
            "Later treatment was checked for all 3 cases: 1 carries a limit that the research notes explain, and nothing adverse was found for the other 2.",
            "1 point was researched for this client beyond the standard authorities, and 2 adverse authorities were identified and answered.",
            "2 recent decisions and policy updates were reviewed: 1 was taken into account in the research; 1 doesn’t apply to this letter.",
        ])
        # A clean check is never called a guarantee.
        self.assertIn("isn’t a guarantee", s["caveat"])
        self.assertEqual((s["updates"], s["applied"], s["not_researched"], s["similar"]), (2, 1, [], 0))

    def test_a_case_whose_treatment_could_not_be_checked_is_counted_apart(self) -> None:
        self.checked_matter()
        unchecked = row("Matter of Example, 30 I&N Dec. 1 (BIA 2026)", "30 I&N Dec. 1", "treatment not checked")
        write(self.m / RESEARCH / "support matrix.json", matrix(proposition("P1", "A point.", [CERVANTES, unchecked])))
        s = rs.research_summary(self.m, TODAY)
        self.assertEqual(s["unchecked"], ["Matter of Example, 30 I&N Dec. 1 (BIA 2026)"])
        self.assertIn("Later treatment was checked for 1 of the 2 cases, and nothing adverse was found. For the other one, the research records no completed check.", s["lines"])

    def test_only_a_row_that_says_nothing_adverse_was_found_counts_as_a_clean_check(self) -> None:
        self.checked_matter()
        history = row("Matter of History, 29 I&N Dec. 1 (BIA 2024)", "29 I&N Dec. 1", "ImmCite treatment_available; incomplete coverage", document_id=11)
        silent = row("Matter of Silent, 29 I&N Dec. 2 (BIA 2024)", "29 I&N Dec. 2", "", document_id=12)
        write(self.m / RESEARCH / "support matrix.json", matrix(proposition("P1", "A point.", [CERVANTES, OJO, history, silent])))
        s = rs.research_summary(self.m, TODAY)
        # Treatment history existing is not a finished review, and a row that says nothing says nothing.
        self.assertEqual(s["unchecked"], ["Matter of History, 29 I&N Dec. 1 (BIA 2024)", "Matter of Silent, 29 I&N Dec. 2 (BIA 2024)"])
        self.assertIn("Later treatment was checked for 2 of the 4 cases: 1 carries a limit that the research notes explain, and nothing "
                      "adverse was found for the other 1. For the other 2, the research records no completed check.", s["lines"])
        write(self.m / RESEARCH / "support matrix.json", matrix(proposition("P1", "A point.", [history])))
        self.assertIn("The research records no completed check of later treatment for the case.", rs.research_summary(self.m, TODAY)["lines"])
        for text, want in (("ImmCite caution; review incomplete", "limited"), ("ImmCite negative: overruled", "limited"), ("ImmCite unchecked", "unknown"),
                           ("treatment not checked", "unknown"), ("not checked for negative treatment", "unknown"), ("current", "unknown"),
                           ("no negative treatment found on review", "clean"), ("overruled in part by Matter of X", "limited"),
                           ("ImmCite treatment_available; 12 of 12 citing decisions reviewed, none adverse", "clean")):
            with self.subTest(text):
                self.assertEqual(rs.treatment_of(text), want)

    def test_a_review_that_left_decisions_over_is_not_a_completed_review(self) -> None:
        # The wording the shipped authorities use for a case with one citing decision still unread.
        jean = "ImmCite treatment_available; 31 of 32 precedential citing decisions reviewed, none adverse; one unreviewed (Rivas-Gomez v. Gonzales, 441 F.3d 1072 (9th Cir. 2006)). Checked 2026-10-30."
        self.assertEqual(rs.treatment_of(jean), "unknown")
        self.assertEqual(rs.treatment_of("ImmCite treatment_available; 31 of 32 published citing decisions reviewed, none adverse"), "unknown")
        self.assertEqual(rs.treatment_of("ImmCite treatment_available; 12 of 12 citing decisions reviewed, none adverse. Checked 2026-10-30."), "clean")
        self.assertEqual(rs.treatment_of("ImmCite treatment_available; all 4 published citing decisions reviewed, none adverse"), "clean")
        # Read since: the row says so, and the review is whole again.
        self.assertEqual(rs.treatment_of("ImmCite treatment_available; the 2 unreviewed citing decisions now read, none adverse"), "clean")
        # A flag is a flag, however much of the rest was read.
        self.assertEqual(rs.treatment_of("ImmCite caution: limited by Matter of X; 3 of 9 citing decisions reviewed"), "limited")
        self.checked_matter()
        write(self.m / RESEARCH / "support matrix.json", matrix(proposition("P1", "A point.", [CERVANTES, row("Matter of Jean, 23 I&N Dec. 373 (A.G. 2002)", "23 I&N Dec. 373", jean, document_id=9)])))
        s = rs.research_summary(self.m, TODAY)
        self.assertEqual(s["unchecked"], ["Matter of Jean, 23 I&N Dec. 373 (A.G. 2002)"])
        self.assertIn("Later treatment was checked for 1 of the 2 cases, and nothing adverse was found. For the other one, the research records no completed check.", s["lines"])

    def test_support_under_a_point_the_research_drops_is_not_counted(self) -> None:
        self.checked_matter()
        dropped = proposition("P9", "A point the research recommends dropping.", [MENDEZ, OJO]) | {"recommendation": "drop"}
        write(self.m / RESEARCH / "support matrix.json", matrix(proposition("S1", "A kept point.", [STATUTE, CERVANTES]), dropped))
        s = rs.research_summary(self.m, TODAY)
        self.assertEqual((s["authorities"], s["cases"], s["limited"], s["researched"]), (2, 1, [], 0))
        self.assertEqual(s["lines"][0], "The research supports the letter with 2 authorities, one of them a case.")

    def test_the_receipt_says_the_library_answered_though_no_check_was_finished(self) -> None:
        self.checked_matter()
        write(self.m / RECEIPT, receipt(checks=[{"category": c, "status": "not_checked"} for c in ("agency_policy", "adverse_treatment")]))
        s = rs.research_summary(self.m, TODAY)
        # The library was used: never "researched without BIA Edge", and never a finished check either.
        self.assertEqual((s["state"], s["treatment_checked"], s["caveat"]), ("checked", False, ""))
        self.assertTrue(s["headline"].endswith("the check of later treatment wasn’t finished"))
        # The receipt's own time of writing rides along, for the law check to know its own work by.
        self.assertRegex(s["receipt_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")
        (self.m / RECEIPT).unlink()
        self.assertEqual(rs.research_summary(self.m, TODAY)["receipt_at"], "")

    def test_the_library_answered_but_the_treatment_check_was_not_finished(self) -> None:
        self.checked_matter()
        partial = receipt()
        partial["checks"] = [c | ({"status": "not_checked"} if c["category"] == "adverse_treatment" else {}) for c in partial["checks"]]
        write(self.m / RECEIPT, partial)
        s = rs.research_summary(self.m, TODAY)
        # Not "researched without BIA Edge": the updates it reviewed stand, and the unfinished part is said.
        self.assertEqual((s["state"], s["treatment_checked"]), ("checked", False))
        self.assertEqual(s["headline"], "Checked November 9, 2026 with BIA Edge; the check of later treatment wasn’t finished")
        self.assertIn("The check of the cases’ later treatment wasn’t finished.", s["lines"])
        self.assertTrue(any(line.startswith("2 recent decisions and policy updates were reviewed") for line in s["lines"]))
        self.assertEqual(s["caveat"], "")
        # With the treatment check finished, the same matter says so.
        self.checked_matter()
        self.assertTrue(rs.research_summary(self.m, TODAY)["treatment_checked"])

    def test_reviewed_updates_are_said_by_what_was_done_with_them(self) -> None:
        self.checked_matter()
        def with_hits(*dispositions: str) -> dict:
            made = receipt()
            made["checks"][0]["hits"] = [{"id": f"h{i}", "url": "https://example.test/h", "disposition": d, "reason": "r"} for i, d in enumerate(dispositions)]
            return made
        cases = {
            ("not_applicable", "not_applicable"): "2 recent decisions and policy updates were reviewed; none applies to this letter.",
            # Already covered is not "doesn't apply": the authority governs the letter and needed no new work.
            ("already_covered", "not_applicable"): "2 recent decisions and policy updates were reviewed: 1 was already covered by the research; 1 doesn’t apply to this letter.",
            ("already_covered",): "1 recent decision or policy update was reviewed: 1 was already covered by the research.",
            ("applied", "applied", "already_covered"): "3 recent decisions and policy updates were reviewed: 2 were taken into account in the research; 1 was already covered by the research.",
            # A hit nobody decided is not one that doesn't apply.
            ("pending", "not_applicable"): "2 recent decisions and policy updates were reviewed: 1 has no decision recorded; 1 doesn’t apply to this letter.",
            ("", ""): "2 recent decisions and policy updates were reviewed: 2 have no decision recorded.",
        }
        for dispositions, line in cases.items():
            with self.subTest(dispositions):
                write(self.m / RECEIPT, with_hits(*dispositions))
                self.assertIn(line, rs.research_summary(self.m, TODAY)["lines"])

    def test_researched_without_the_library_says_what_was_not_checked(self) -> None:
        old = "2026-10-30"
        write(self.m / RESEARCH / "support matrix.json", matrix(
            proposition("S1", "USCIS may waive the bar on extreme hardship.", [STATUTE | {"checked": old}, CERVANTES | {"checked": old, "validity": "current as of the authorities file"}]),
            proposition("P1", "A single DWI without aggravating elements is not a crime involving moral turpitude.", [MANUAL | {"checked": "2026-11-09"}],
                        case_law="not researched", note="Would have looked for BIA and circuit decisions on simple DWI."),
        ))
        for reason, words in (("no_access", "the Passim account had no research access"), ("not_connected", "BIA Edge wasn’t connected"),
                              ("refused", "the privacy check held the research back")):
            with self.subTest(reason):
                write(self.m / RECEIPT, receipt(connector={"available": False, "reason": reason},
                                                 checks=[{"category": "adverse_treatment", "status": "not_checked"}],
                                                 unresolved=["Later treatment and changes since 2026-10-30 were not checked."]))
                s = rs.research_summary(self.m, TODAY)
                self.assertEqual((s["state"], s["reason"], s["headline"], s["checked_at"], s["age_days"]), ("without", reason, "Researched without BIA Edge", "", None))
                self.assertEqual(s["lines"][0], f"When the letter was researched, {words}.")
                self.assertEqual(s["lines"][1], "The research supports the letter with 3 authorities, one of them a case, as last verified October 30, 2026. "
                                                "Nothing after that was checked: not the cases’ later treatment, and not new decisions or policy.")
                self.assertEqual(s["lines"][2], "1 point specific to this client got no case-law research.")
                self.assertEqual(s["not_researched"], ["A single DWI without aggravating elements is not a crime involving moral turpitude."])
                self.assertEqual(s["caveat"], "")
        # A reason the tool doesn't know is not repeated to the attorney.
        write(self.m / RECEIPT, receipt(connector={"available": False, "reason": "<script>"}, checks=[]))
        s = rs.research_summary(self.m, TODAY)
        self.assertEqual((s["reason"], s["lines"][0]), ("", "BIA Edge wasn’t used when the letter was researched."))

    def test_a_receipt_from_an_earlier_version_is_read_by_what_it_checked(self) -> None:
        self.checked_matter()
        old = receipt()
        del old["connector"]
        write(self.m / RECEIPT, old)
        self.assertEqual(rs.research_summary(self.m, TODAY)["state"], "checked")
        # Later treatment never checked: researched without the library, whatever else the receipt says.
        write(self.m / RECEIPT, old | {"checks": [c for c in old["checks"] if c["category"] != "adverse_treatment"]})
        self.assertEqual(rs.research_summary(self.m, TODAY)["state"], "without")
        # No receipt at all: the check was never recorded, and the summary says only that.
        (self.m / RECEIPT).unlink()
        s = rs.research_summary(self.m, TODAY)
        self.assertEqual((s["state"], s["headline"]), ("unrecorded", "Researched; the check of the law wasn’t recorded"))
        self.assertIn("wasn’t recorded", s["lines"][0])

    def test_similar_decisions_are_counted_by_their_headings(self) -> None:
        self.checked_matter()
        write(self.m / RESEARCH / "similar decisions.md", "# Similar decisions\nUnpublished decisions, not precedent.\n\n"
              "## Extreme hardship to a spouse with a disabled child\n### AAO, 2025-03-04, I-601: sustained\nTwo sentences. https://example.test/1\n"
              "### AAO, 2024-08-19, I-601: dismissed\nTwo sentences. https://example.test/2\n\n## Searched, nothing on point\n- Simple DWI as a discretionary factor.\n")
        s = rs.research_summary(self.m, TODAY)
        self.assertEqual(s["similar"], 2)
        self.assertEqual(s["lines"][-1], "2 unpublished decisions on similar facts are summarized in the memo. They are not precedent, and the letter doesn’t cite them.")

    def test_the_newest_matrix_is_the_letters_and_the_memo_prints_the_same_words(self) -> None:
        self.checked_matter()
        s = rs.research_summary(self.m, TODAY)
        memo = rs.memo_lines(s)
        self.assertTrue(memo[0].startswith("**Research: checked November 9, 2026 with BIA Edge.** The research supports the letter with 5 authorities, 3 of them cases."))
        self.assertEqual(memo[-1], s["caveat"])
        out = subprocess.run([sys.executable, str(PLUGIN_ROOT / "scripts/research_summary.py"), str(self.m)], capture_output=True, text=True, check=True).stdout
        self.assertIn("**Research: checked", out)
        as_json = json.loads(subprocess.run([sys.executable, str(PLUGIN_ROOT / "scripts/research_summary.py"), str(self.m), "--json"],
                                            capture_output=True, text=True, check=True).stdout)
        self.assertEqual(as_json["state"], "checked")
        missing = subprocess.run([sys.executable, str(PLUGIN_ROOT / "scripts/research_summary.py"), str(self.m / "nope")], capture_output=True, text=True)
        self.assertEqual(missing.returncode, 1)

    def test_the_approval_page_says_the_letter_was_researched_without_the_library(self) -> None:
        self.checked_matter()
        write(self.m / RECEIPT, receipt(date.today().isoformat()))
        self.assertEqual(fr._currency_point(self.m), "")
        write(self.m / RECEIPT, receipt(connector={"available": False, "reason": "no_access"}, checks=[], unresolved=["Not checked."]))
        self.assertEqual(fr._currency_point(self.m), "The letter was researched without BIA Edge: the cases it cites weren't checked for later "
                                                     "treatment, and nothing was checked for changes in the law.")


if __name__ == "__main__":
    unittest.main()

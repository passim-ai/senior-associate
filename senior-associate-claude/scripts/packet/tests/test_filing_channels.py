#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest>=8",
# ]
# ///
"""Tests for filing_channels.py and the way fees.py prices a filing by its channels.

    uv run --script tests/test_filing_channels.py        (from scripts/packet, or use the full path)
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import pytest  # noqa: E402

import fees  # noqa: E402
import filing_channels as fc  # noqa: E402
from _packet_common import ToolError  # noqa: E402

FAMILY = ["G-28", "I-130", "I-130A", "I-485", "I-864", "I-765", "I-131", "I-693"]


def by_form(result: dict) -> dict[str, dict]:
    return {e["form"]: e for e in result["forms"]}


def channel(forms: list[str], *args, key: str = "channel", **kwargs):
    """The first form's channel (or another of its fields) when the filing is decided with these arguments."""
    return by_form(fc.decide(forms, *args, **kwargs))[forms[0]][key]


def test_a_family_adjustment_online_is_one_pdf_upload_of_the_i485():
    r = fc.decide(FAMILY, "online")
    assert r["split"] is False and r["paper"] is None and r["problems"] == []
    [sub] = r["submissions"]
    assert sub["lead"] == "I-485" and sub["channel"] == fc.PDF_UPLOAD
    assert sub["forms"] == ["I-485", "I-130", "I-765", "I-131"]
    assert sub["evidence_forms"] == ["I-864", "I-693", "I-130A"]
    assert sub["g28_for"] == ["I-485", "I-130", "I-765", "I-131"]  # one G-28 for each party and form
    forms = by_form(r)
    assert forms["I-130"]["channel"] == fc.WITH and forms["I-130"]["with"] == "I-485"
    assert forms["I-130A"]["with"] == "I-485" and "acceptable-evidence list" in forms["I-130A"]["why"]
    assert all(e["method"] == "online" for e in r["forms"])
    said = " ".join(r["notes"])
    assert "sign it in ink" in said and "can't be signed electronically" in said and "up to 30 days" in said
    assert "opens the civil surgeon's sealed envelope" in said


def test_the_same_filing_on_paper_is_all_paper_and_says_it_could_be_required_online():
    r = fc.decide(FAMILY, "paper", on=date(2026, 10, 30))
    assert r["submissions"] == [] and set(r["paper"]["forms"]) == set(FAMILY) - {"G-28"}
    assert all(e["method"] == "paper" for e in r["forms"])
    assert any("may require the I-130, I-485, I-765, I-131 online on 60 days' notice" in n for n in r["notes"])
    assert r["checked"]["mandates_stale"] is False
    later = fc.decide(FAMILY, "paper", on=date(2026, 12, 15))
    assert later["checked"]["mandates_stale"] is True
    assert any("more than 30 days old" in n and "--mandate" in n for n in later["notes"])


def test_vawa_self_petition_and_adjustment_filed_together_stay_on_paper():
    r = fc.decide(["G-28", "I-360", "I-485", "I-765", "I-131"], "online", ["vawa"])
    assert r["submissions"] == [] and all(by_form(r)[f]["method"] == "paper" for f in ("I-360", "I-485", "I-765"))
    assert any("doesn't take an I-360 with an I-485" in d for d in r["decisions"])
    assert any("upload the I-360 on its own first" in d for d in r["decisions"])
    # The I-360 on its own goes online by PDF upload.
    alone = fc.decide(["G-28", "I-360"], "online", ["vawa"])
    assert alone["submissions"][0]["lead"] == "I-360"


def test_a_fee_exempt_c9_work_permit_splits_the_filing():
    r = fc.decide(["G-28", "I-485", "I-765"], "online", ["vawa"])  # I-360 already filed
    assert r["split"] is True
    forms = by_form(r)
    assert forms["I-485"]["channel"] == fc.PDF_UPLOAD and forms["I-765"]["channel"] == fc.PAPER
    assert "fee-exempt (c)(9)" in forms["I-765"]["why"]
    assert any("Mail it once USCIS accepts the I-485" in d for d in r["decisions"])
    assert r["paper"] == {"forms": ["I-765"], "g28_for": ["I-765"]}


def test_forms_and_categories_uscis_takes_only_on_paper():
    cases = [
        (["N-400"], ["reduced"], [], "reduced fee"),
        (["N-400"], [], ["N-400"], "fee waiver"),
        (["I-129F"], [], [], "isn't on USCIS's list"),
        (["I-612"], [], [], "isn't on USCIS's list"),
        (["I-601A"], [], [], "isn't on USCIS's list"),
        (["I-601"], [], [], "isn't on USCIS's list"),
        (["I-131"], ["I-131=reentry_permit"], [], "reentry permit"),
        (["I-360"], [], [], "only for a VAWA self-petition"),
        (["I-485", "I-130"], [], ["I-485"], "fee waiver"),
        (["I-485"], ["refugee"], [], "refugee, asylee"),
    ]
    for forms, cats, waived, words in cases:
        r = fc.decide(forms, "online", cats, fee_waiver=waived)
        lead = by_form(r)[forms[0]]
        assert lead["channel"] == fc.PAPER, forms
        assert words in lead["why"], (forms, lead["why"])
        assert any(d.startswith(f"{forms[0]} goes on paper") for d in r["decisions"]), forms


def test_an_i140_with_premium_processing_goes_by_mail():
    # uscis.gov/i-140 (updated 07/24/2026): an I-140 filed with an I-907 must be mailed.
    alone = fc.decide(["G-28", "I-140"], "online", ["I-140=self_petitioner"])
    assert by_form(alone)["I-140"]["channel"] == fc.PDF_UPLOAD
    r = fc.decide(["G-28", "I-140", "I-907"], "online", ["I-140=self_petitioner"])
    forms = by_form(r)
    assert r["submissions"] == [] and forms["I-140"]["channel"] == forms["I-907"]["channel"] == fc.PAPER
    assert "only by mail" in forms["I-140"]["why"]
    assert any(d.startswith("To file online instead, leave the I-907 out") for d in r["decisions"])
    # With a concurrent I-485, the whole package goes by mail.
    concurrent = fc.decide(["G-28", "I-140", "I-485", "I-765", "I-907"], "online", ["I-140=self_petitioner"],
                           eligibility={"I-765": "c9"})
    assert concurrent["submissions"] == []
    assert all(by_form(concurrent)[f]["method"] == "paper" for f in ("I-140", "I-485", "I-765", "I-907"))
    assert any("its I-485 by PDF upload" in d for d in concurrent["decisions"])
    # A standalone I-907 for a pending I-140 may be uploaded (only for an IOE receipt).
    assert channel(["I-907"], "online") == fc.PDF_UPLOAD and "IOE" in channel(["I-907"], "online", key="why")

def test_an_i751_fee_waiver_goes_online_with_the_petition():
    r = fc.decide(["G-28", "I-751"], "online", fee_waiver=["I-751"])
    [sub] = r["submissions"]
    assert sub["lead"] == "I-751" and sub["fee_waiver"] is True
    assert any("fee waiver request goes with its form" in n for n in r["notes"])


def test_facts_the_channel_depends_on_are_asked_for_not_guessed():
    r = fc.decide(["I-485", "I-765", "I-864"], "online")
    forms = by_form(r)
    assert forms["I-485"]["channel"] is None and "--basis I-485" in forms["I-485"]["needs"]
    assert forms["I-765"]["channel"] is None and forms["I-864"]["channel"] is None
    assert any(p.startswith("I-485: say what the I-485 is based on") for p in r["problems"])
    settled = fc.decide(["I-485", "I-765", "I-864"], "online", basis="family")
    assert settled["problems"] == [] and settled["submissions"][0]["forms"] == ["I-485", "I-765"]
    # An I-765 on its own needs its eligibility category, unless its fee category says it.
    assert fc.decide(["I-765"], "online")["problems"]
    assert channel(["I-765"], "online", ["c8_initial"]) == fc.PDF_UPLOAD
    student = {"eligibility": {"I-765": "(c)(3)(B)"}}
    assert channel(["I-765"], "online", **student) == fc.GUIDED
    assert "the client needs their own USCIS online account" in channel(["I-765"], "online", key="why", **student)
    # Advance parole on its own depends on where the pending I-485 was filed.
    assert fc.decide(["I-131"], "online", ["I-131=advance_parole"])["problems"]
    assert channel(["I-131"], "online", ["I-131=advance_parole"], pending_i485="online") == fc.PDF_UPLOAD
    assert channel(["I-131"], "online", ["I-131=advance_parole"], pending_i485="paper") == fc.PAPER
    # On paper the same gaps don't matter: nothing is filed online.
    assert fc.decide(["I-485", "I-765", "I-864"], "paper")["problems"] == []


def test_a_mandate_in_force_moves_a_paper_form_online():
    mandate = fc.Mandate("I-130", "2026-10-01", notice="https://www.uscis.gov/example-notice")
    r = fc.decide(["G-28", "I-130", "I-130A", "G-1450", "G-1145"], "paper", mandates=[mandate], on=date(2026, 10, 30))
    forms = by_form(r)
    assert forms["I-130"]["channel"] == fc.PDF_UPLOAD and forms["I-130"]["mandate"]["in_force"] is True
    assert forms["I-130A"]["with"] == "I-130"
    assert forms["G-1450"]["channel"] == fc.NOT_FILED and forms["G-1145"]["channel"] == fc.NOT_FILED
    assert any("stopped taking the I-130 on paper on 2026-10-01" in d and "I-936" in d for d in r["decisions"])
    # Before the day, it stays on paper with a warning of the date.
    early = fc.decide(["I-130"], "paper", mandates=[mandate], on=date(2026, 9, 15))
    assert by_form(early)["I-130"]["channel"] == fc.PAPER
    assert any("stops taking the I-130 on paper on 2026-10-01" in n and "16 days" in n for n in early["notes"])
    # A mandate for a form whose category can't go online is a problem to check, not a silent paper filing.
    clash = fc.decide(["N-400"], "paper", ["reduced"], mandates=[fc.Mandate("N-400", "2026-10-01")],
                      on=date(2026, 10, 30))
    assert any("stopped taking the N-400 on paper" in p and "scope" in p for p in clash["problems"])


def test_a_concurrent_petition_under_mandate_takes_its_i485_online():
    r = fc.decide(["I-130", "I-485", "I-765", "I-864"], "paper", mandates=[fc.Mandate("I-130", "2026-10-01")],
                  on=date(2026, 10, 30))
    assert r["submissions"][0]["forms"] == ["I-485", "I-130", "I-765"]
    [said] = r["decisions"]  # one decision naming everything that moved, and the other way to file
    assert "so the I-485, I-765, I-864 go online with it" in said and "file the I-130 online on its own first" in said
    # A work permit under mandate takes its I-485 online too; the other way runs the other order.
    r = fc.decide(["I-130", "I-485", "I-765"], "paper", mandates=[fc.Mandate("I-765", "2026-10-01")],
                  on=date(2026, 10, 30))
    assert r["submissions"][0]["lead"] == "I-485" and "file the I-485 on paper first" in r["decisions"][0]


def test_a_mandated_form_left_on_paper_is_always_a_problem():
    # A fee-exempt (c)(9) can't go online, so a mandate on the I-765 is a blocker to check, never a quiet paper form.
    r = fc.decide(["I-485", "I-765"], "paper", ["vawa"], mandates=[fc.Mandate("I-765", "2026-10-01")],
                  on=date(2026, 10, 30))
    assert by_form(r)["I-765"]["channel"] == fc.PAPER
    assert any(p.startswith("USCIS stopped taking the I-765 on paper") and "I-936" in p for p in r["problems"])


def test_a_mandate_can_cover_only_some_categories():
    m = fc.parse_mandate("I-765:c8,(c)(11)=2026-10-01=https://www.uscis.gov/x")
    assert m.categories == ("c8", "(c)(11)")
    on = date(2026, 10, 30)
    assert channel(["I-765"], "paper", ["c8_initial"], mandates=[m], on=on) == fc.PDF_UPLOAD
    assert channel(["I-765"], "paper", eligibility={"I-765": "c11"}, mandates=[m], on=on, key="method") == "online"
    assert channel(["I-765"], "paper", eligibility={"I-765": "c9"}, mandates=[m], on=on) == fc.PAPER


def test_two_applicants_need_a_g28_each():
    r = fc.decide(["I-130", "I-485", "I-485", "I-765", "I-765"], "online")
    assert r["submissions"][0]["g28_for"] == ["I-485", "I-485", "I-130", "I-765", "I-765"]
    assert any(n.startswith("2 I-485s") for n in r["notes"])


def test_an_i765_with_a_fee_waiver_is_its_own_upload_beside_the_i485():
    r = fc.decide(["I-130", "I-485", "I-765"], "online", fee_waiver=["I-765"])
    leads = [s["lead"] for s in r["submissions"]]
    assert leads == ["I-485", "I-765"] and r["submissions"][1]["fee_waiver"] is True
    assert any("I-765 with a fee waiver" in d for d in r["decisions"])


def test_no_online_account_and_the_i864_without_an_i485():
    r = fc.decide(["I-130", "I-864"], "online", has_online_account="no")
    assert any("profile says you don't have one" in d for d in r["decisions"])
    assert by_form(r)["I-864"]["channel"] == fc.NOT_FILED
    assert any("National Visa Center" in d for d in r["decisions"])


def test_mandate_and_pair_parsing():
    m = fc.parse_mandate("i130=2027-01-15=https://www.uscis.gov/x")
    assert (m.form, m.paper_ends, m.notice) == ("I-130", "2027-01-15", "https://www.uscis.gov/x")
    with pytest.raises(ToolError, match="isn't a date"):
        fc.parse_mandate("I-130=next month")
    with pytest.raises(ToolError, match="FORM=YYYY-MM-DD"):
        fc.parse_mandate("I-130")
    assert fc.parse_pairs(["c9"], "I-765", "--eligibility") == {"I-765": "c9"}
    assert fc.normalize_eligibility("(c)(3)(A)") == "c3a"
    with pytest.raises(ToolError, match="paper or online"):
        fc.decide(["I-130"], "fax")


def test_fees_price_each_form_by_its_channel():
    # A split filing: the I-130 online, a reentry permit on paper with its own payment form.
    r = fees.calculate(["I-130", "I-131"], "online", ["I-131=reentry_permit"])
    lines = {line["form"]: line for line in r["lines"]}
    assert r["split"] is True
    assert (lines["I-130"]["filing_method"], lines["I-130"]["fee"]) == ("online", 625)
    assert (lines["I-131"]["filing_method"], lines["I-131"]["fee"]) == ("paper", 630)
    assert lines["I-130"]["payment"] == "pay in the USCIS online account" and "G-1450" in lines["I-131"]["payment"]
    assert r["payment_forms_needed"] == [{"form": "I-131", "what": "filing fee", "amount": 630}]
    assert any("split filing" in n for n in r["notes"])
    assert "https://www.uscis.gov/g-1450" in r["sources"] and fees.ONLINE_PAYMENT_SOURCE in r["sources"]
    # An online filing's left-out accessories cost nothing and raise nothing.
    online = fees.calculate(["I-130", "G-1651"], "online", [])
    assert online["problems"] == [] and online["total"] == 625


def test_fees_cli_writes_the_channels_and_reads_the_profile(tmp_path, capsys):
    matter = tmp_path / "Matters" / "Example I-130"
    (matter / "output" / "working" / "workflow").mkdir(parents=True)
    (matter / "output" / "working" / "workflow" / "matter-meta.json").write_text(
        json.dumps({"filing_method": "online"}), encoding="utf-8")
    profile = tmp_path / "Matters" / ".senior-associate" / "attorney-profile.json"
    profile.parent.mkdir(parents=True)
    profile.write_text(json.dumps({"has_uscis_online_account": "no", "attorney_name": "A. Lawyer"}), encoding="utf-8")
    out = "output/working/vault/packet/main/fees.json"
    assert fees.main([str(matter), "--forms", "I-485,I-765", "--basis", "I-485=family", "--output", out]) == 0
    printed = capsys.readouterr().out
    assert "Fees (online filing" in printed  # the matter's filing method
    assert "Filing: Online (PDF upload): I-485 with I-765" in printed and "DECISION:" in printed
    saved = json.loads((matter / out).read_text(encoding="utf-8"))
    assert saved["channels"]["submissions"][0]["lead"] == "I-485"
    assert any("profile says you don't have one" in d for d in saved["channels"]["decisions"])
    assert fees.main([str(matter), "--forms", "I-130", "--mandate", "I-130=2026-01-01", "--filing-method", "paper",
                      "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["lines"][0]["filing_method"] == "online"
    assert fc.main([str(matter), "--forms", "I-485,I-765", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["problems"]  # the I-485's basis is unknown


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", *sys.argv[1:]]))

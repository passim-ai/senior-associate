#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""How each form in a filing reaches USCIS, and whether USCIS still takes it on paper.

    uv run --script filing_channels.py "<matter>" --forms I-130,I-130A,I-485,I-864,I-765,I-131
        [--filing-method paper|online] [--category CATEGORY | --category FORM=CATEGORY ...]
        [--basis I-485=family|employment|vawa|other] [--eligibility I-765=c9]
        [--fee-waiver FORM ...] [--pending-i485 online|paper]
        [--mandate FORM[:CATEGORY,...]=YYYY-MM-DD[=URL] ...] [--on YYYY-MM-DD] [--json]

A form goes one of three ways: uploaded as a completed PDF in the USCIS online account
("pdf_upload"), typed into the account's step-by-step form ("guided"), or mailed ("paper").
Some forms ride inside another form's online submission ("with"): the I-130, I-765, I-131,
I-864 and I-693 inside an attorney's I-485 upload, the I-130A with its I-130. The matter's
filing method is the attorney's choice for the whole filing: "online" means online wherever
USCIS takes the form and its category, and paper for the rest (a split filing); "paper" means
by mail, except a form USCIS no longer takes on paper.

Since Aug. 11, 2026, USCIS may require a form to be filed online once it has been available
online for more than 180 days, after 60 days' notice on uscis.gov (8 C.F.R. 103.2(a)(1)(ii)).
MANDATES lists the forms it has named, with the day paper stops; there were none when it was
last checked. When that check is more than RECHECK_DAYS old, check the pages in
MANDATE_SOURCES and pass any notice found as --mandate FORM=DATE.

fees.py runs this for every pricing and writes the answer under "channels" in fees.json, so a
split filing is priced and paid per form. Run it on its own to see each form's reasons.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _packet_common import ToolError, run_cli  # noqa: E402
import fees  # noqa: E402

CHANNELS_PAGE = "https://www.uscis.gov/file-online/forms-available-to-file-online"
OPTIONS_PAGE = "https://www.uscis.gov/online-filing-options"
PAGE_UPDATED = "10/07/2026"
CHECKED = "2026-10-30"

PDF_UPLOAD, GUIDED, PAPER, WITH, NOT_FILED = "pdf_upload", "guided", "paper", "with", "not_filed"
CHANNEL_WORDS = {
    PDF_UPLOAD: "online, PDF upload",
    GUIDED: "online, the account's step-by-step form",
    PAPER: "on paper",
    WITH: "online, with",
    NOT_FILED: "not filed",
}
BOTH = frozenset({PDF_UPLOAD, GUIDED})
PDF = frozenset({PDF_UPLOAD})
STEPS = frozenset({GUIDED})
NONE: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Mandate:
    """A form USCIS no longer takes on paper, from its notice on uscis.gov."""

    form: str
    paper_ends: str  # the first day USCIS refuses the paper form, YYYY-MM-DD
    # The categories it covers when it isn't every filing of the form: fee categories (fees.py) or I-765
    # eligibility codes ("c8"); empty covers every category.
    categories: tuple[str, ...] = ()
    scope: str = ""  # what the notice covers, in its words, when the categories can't say it
    notice: str = ""  # the uscis.gov page that gave the date
    posted: str = ""  # when the notice was posted, YYYY-MM-DD


# Forms USCIS has made online-only under 8 C.F.R. 103.2(a)(1)(ii). None as of MANDATES_CHECKED: the
# interim final rule itself mandates no form, and neither the alerts (newest Oct. 26, 2026), Forms Updates
# (newest Oct. 28, 2026) nor the filing locations and online filing options updates (newest Oct. 7, 2026)
# names one.
MANDATES: tuple[Mandate, ...] = ()
MANDATES_CHECKED = "2026-10-30"
RECHECK_DAYS = 30
MANDATE_RULE = ("8 C.F.R. 103.2(a)(1)(ii)-(iii), as amended by the DHS interim final rule \"Mandatory Electronic "
                "Filing (e-Filing),\" 91 FR 51924 (Aug. 11, 2026)")
MANDATE_RULE_URL = ("https://www.federalregister.gov/documents/2026/08/11/2026-16313/"
                    "mandatory-electronic-filing-e-filing")
MANDATE_SOURCES = (
    "https://www.uscis.gov/newsroom/alerts",
    "https://www.uscis.gov/forms/forms-updates",
    "https://www.uscis.gov/forms/us-citizenship-and-immigration-services-filing-locations-and-online-filing-options-updates",
)
# The rule's waiver: Form I-936, $25 (8 C.F.R. 106.2(a)(64)), fee waivable for VAWA, T, U, TPS and other
# filings 8 C.F.R. 106.3(a)(3)(iii) lists. The preamble says DHS expects represented requestors "generally
# not" to be eligible.
WAIVER_NOTE = ("A paper filing of a form USCIS requires online needs an approved Form I-936 waiver first ($25, "
               "for undue hardship); DHS expects represented filers generally not to qualify (91 FR 51924), so "
               "plan to file it online.")

# Forms an attorney's PDF upload of an I-485 can carry ("You can now submit the following forms with Form
# I-485 when you file online using PDF upload": the G-28, I-130, I-131, I-140, Supplements A and J, I-693,
# I-765 and I-864). The I-130, I-140, I-765 and I-131 are benefit requests of their own; the I-864 and I-693
# support the I-485 (the options page's FAQ: "you can upload Form I-693 or Form I-864 as supporting
# evidence"), so the account may take them either way. The I-130A rides with its I-130 and the I-864A with
# its I-864; neither is named on the pages, so the account's acceptable-evidence list decides.
I485_COMPANIONS = ("I-130", "I-140", "I-765", "I-131")
EVIDENCE_OF = {"I-864": "I-485", "I-864A": "I-485", "I-693": "I-485", "I-130A": "I-130"}
CONFIRM_ON_LIST = {"I-864A", "I-130A"}
EITHER_WAY = {"I-864", "I-693"}
# Accessory forms that only a paper package has: online, the fee is paid in the account and notices come there.
PAPER_ACCESSORIES = {"G-1145", "G-1450", "G-1650", "G-1651"}
# Forms USCIS takes a fee waiver request (I-912) with online, by PDF upload only.
I912_ONLINE = {"I-90", "I-131", "I-751", "I-765"}
I485_BASES = ("family", "employment", "vawa", "other")
_I485_FEE_BASIS = {"vawa": "vawa", "refugee": "other", "t": "other", "u": "other", "sij": "other",
                   "military_six_and_six": "other", "afghan_iraqi_siv": "other"}
# I-765 eligibility categories USCIS takes online, and how.
I765_ONLINE = {"a12": BOTH, "c8": BOTH, "c9": PDF, "c11": BOTH, "c19": BOTH,
               "c3a": STEPS, "c3b": STEPS, "c3c": STEPS, "c33": STEPS}
I765_FROM_FEE = {"with_pending_i485": "c9", "c8_initial": "c8", "c8_renewal": "c8", "refugee": "a3", "asylee": "a5"}
# Fee categories that are a fee-exempt (c)(9) with an I-485 (or, without one, a category USCIS doesn't take online).
I765_FEE_EXEMPT = {"with_i485_before_2024_04_01", "vawa", "t", "u", "sij", "afghan_iraqi_siv"}
# Forms on USCIS's online lists that the fee table doesn't price, with what the page says about them.
OTHER_ONLINE: dict[str, tuple[frozenset[str], str]] = {
    "AR-11": (STEPS, ""), "G-325R": (STEPS, ""), "G-639": (STEPS, ""), "I-90": (BOTH, ""),
    "I-129": (BOTH, "only certain classifications"), "I-129CW": (PDF, ""), "I-129S": (PDF, ""),
    "I-539": (STEPS, "only certain categories"), "I-589": (STEPS, ""), "I-821": (STEPS, ""), "I-821D": (STEPS, ""),
    "N-336": (STEPS, ""), "N-565": (STEPS, ""), "N-600": (STEPS, ""), "N-600K": (STEPS, ""),
}
NOT_LISTED = "isn't on USCIS's list of forms you can file online"
# uscis.gov/i-140 (updated 07/24/2026): "If you are submitting Form I-140 together with Form I-907 to request
# premium processing, you must file by mail. However, if you have a pending Form I-140 (with a receipt number
# that begins with IOE), you may file a standalone Form I-907 via PDF upload in the online account or you may
# file standalone Form I-907 by mail."
I140_PAGE = "https://www.uscis.gov/i-140"
PREMIUM_BY_MAIL = "USCIS takes an I-140 filed together with an I-907 (premium processing) only by mail"


@dataclass
class _Context:
    forms: list[str]
    cats: dict[str, str]
    basis: str | None
    eligibility: dict[str, str]
    fee_waiver: set[str]
    pending_i485: str | None


def normalize_eligibility(text: str) -> str:
    """"(c)(9)", "c9", "C)(9" -> "c9"; "(c)(3)(A)" -> "c3a"."""
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def _i485_basis(ctx: _Context) -> str | None:
    if ctx.basis:
        return ctx.basis
    fee_basis = _I485_FEE_BASIS.get(ctx.cats.get("I-485", ""))
    if fee_basis:
        return fee_basis
    if "I-130" in ctx.forms:
        return "family"
    if "I-140" in ctx.forms:
        return "employment"
    return None


def _alone(form: str, ctx: _Context) -> tuple[frozenset[str] | None, str]:
    """What USCIS takes online for this form and its category: the online ways (empty: paper only; None: can't
    tell without more facts) and why."""
    cat = ctx.cats.get(form, "")
    if form in ctx.fee_waiver and form not in I912_ONLINE:
        return NONE, (f"USCIS takes a fee waiver request (I-912) online only with an I-90, I-131, I-751 or I-765, "
                      f"so a {form} with one goes on paper")
    if form == "I-485":
        basis = _i485_basis(ctx)
        if basis is None:
            return None, ("say what the I-485 is based on (--basis I-485=family, employment, vawa or other): USCIS "
                          "takes it online only when it rests on an I-130, an I-140 or a VAWA I-360")
        if basis == "other":
            return NONE, ("USCIS takes an I-485 online only when it rests on an I-130, an I-140 or a VAWA I-360; a "
                          "refugee, asylee, T, U, SIJ or other adjustment goes on paper")
        if basis == "vawa" and "I-360" in ctx.forms:
            return NONE, ("the online account doesn't take an I-360 with an I-485, so a VAWA I-485 goes online only "
                          "once its I-360 is filed; filed together, both go on paper")
        underlying = {"family": "I-130", "employment": "I-140"}.get(basis)
        if underlying == "I-140" and {"I-140", "I-907"} <= set(ctx.forms):
            return NONE, f"{PREMIUM_BY_MAIL}, and the I-485 filed with it goes in the same package"
        if underlying and underlying in ctx.forms:
            return PDF, f"an attorney can file the I-485 and its {underlying} together by PDF upload"
        return PDF, "an I-485 on an I-130, I-140 or VAWA I-360 already filed goes by PDF upload"
    if form == "I-130":
        return BOTH, ""
    if form == "I-140":
        if "I-907" in ctx.forms:
            return NONE, PREMIUM_BY_MAIL
        return PDF, ""
    if form == "I-907":
        if "I-140" in ctx.forms:
            return NONE, PREMIUM_BY_MAIL
        return PDF, ("a standalone I-907 for a pending I-140 goes by PDF upload only when the I-140's receipt number "
                     "starts with IOE; otherwise mail it")
    if form == "I-360":
        if cat == "vawa":
            return PDF, "a VAWA self-petition goes by PDF upload"
        return NONE, "USCIS takes an I-360 online only for a VAWA self-petition"
    if form == "I-751":
        return PDF, ""
    if form == "N-400":
        if cat == "reduced":
            return NONE, "USCIS doesn't take an N-400 with a reduced fee online"
        if form in ctx.fee_waiver:
            return NONE, "USCIS doesn't take an N-400 with a fee waiver request online"
        return BOTH, ""
    if form == "I-765":
        code = ctx.eligibility.get("I-765") or I765_FROM_FEE.get(cat)
        if cat in I765_FEE_EXEMPT and (code in (None, "c9")):
            if "I-485" in ctx.forms or code == "c9":
                return NONE, ("USCIS says to mail a fee-exempt (c)(9) I-765: its PDF upload charges the fee and "
                              "doesn't refund it")
            return NONE, "this I-765 category isn't one USCIS takes online"
        if code is None:
            return None, ("say which category the I-765 requests (--eligibility I-765=c9, for example): USCIS takes "
                          "only some online")
        options = I765_ONLINE.get(code, NONE)
        if not options:
            return NONE, ("USCIS takes an I-765 online only for (a)(12), (c)(3)(A)-(C), (c)(8), (c)(9), (c)(11), "
                          "(c)(19) and (c)(33)")
        if form in ctx.fee_waiver:
            options = options & PDF
            if not options:
                return NONE, "USCIS takes a fee waiver request with this I-765 category only on paper"
        return options, ""
    if form == "I-131":
        if cat == "tps_travel":
            return PDF, ""
        if cat.startswith("advance_parole"):
            if form in ctx.fee_waiver:
                return NONE, "USCIS takes a fee waiver request with an advance parole I-131 only on paper"
            if "I-485" in ctx.forms:
                return PDF, "it goes with its I-485"
            if ctx.pending_i485 == "online":
                return PDF, "the pending I-485 was filed online (its receipt number starts with IOE)"
            if ctx.pending_i485 == "paper":
                return NONE, ("USCIS takes advance parole online only when the pending I-485 was filed online (its "
                              "receipt number starts with IOE)")
            return None, ("say whether the pending I-485 was filed online, its receipt starting with IOE "
                          "(--pending-i485 online or paper)")
        return NONE, "USCIS doesn't take a reentry permit or refugee travel document online"
    if form in OTHER_ONLINE:
        return OTHER_ONLINE[form]
    return NONE, f"the {form} {NOT_LISTED}"


def _parse_date(text: str, what: str) -> date:
    try:
        return date.fromisoformat(str(text).strip())
    except ValueError:
        raise ToolError(f"{what}: {text!r} isn't a date like 2027-01-15.") from None


def parse_mandate(text: str) -> Mandate:
    """--mandate FORM[:CATEGORY,...]=YYYY-MM-DD[=URL]: the categories, when the notice names some, are fee
    categories (fees.py --list-categories) or I-765 eligibility codes (c8)."""
    parts = str(text or "").split("=", 2)
    if len(parts) < 2 or not parts[0].strip():
        raise ToolError(f"--mandate {text!r}: give FORM=YYYY-MM-DD (or FORM:CATEGORY=YYYY-MM-DD), with the notice's "
                        "URL after another '='.")
    head, _, cats = parts[0].partition(":")
    form = fees.normalize_form(head)
    ends = _parse_date(parts[1], f"--mandate {text!r}").isoformat()
    categories = tuple(c.strip().lower() for c in cats.split(",") if c.strip())
    return Mandate(form=form, paper_ends=ends, categories=categories,
                   notice=parts[2].strip() if len(parts) > 2 else "")


def _mandate_for(form: str, mandates: list[Mandate], on: date, covers: set[str] | None = None) -> dict | None:
    """The mandate that governs this form on that day: one already in force, else the soonest to come. A mandate
    limited to categories governs only a form in one of them (`covers`: its fee category and eligibility code)."""
    found = [m for m in mandates if m.form == form
             and (not m.categories or bool(covers and covers & {normalize_eligibility(c) for c in m.categories}))]
    if not found:
        return None
    m = min(found, key=lambda m: (on < date.fromisoformat(m.paper_ends), m.paper_ends))
    ends = date.fromisoformat(m.paper_ends)
    return {"form": m.form, "paper_ends": m.paper_ends, "categories": list(m.categories), "scope": m.scope,
            "notice": m.notice, "posted": m.posted, "in_force": on >= ends, "days_left": max(0, (ends - on).days)}


def decide(forms: list[str], preference: str, categories: list[str] | tuple[str, ...] = (), *,
           basis: str | None = None, eligibility: dict[str, str] | None = None,
           fee_waiver: list[str] | tuple[str, ...] = (), pending_i485: str | None = None,
           mandates: list[Mandate] | tuple[Mandate, ...] = (), on: date | None = None,
           has_online_account: str | None = None) -> dict:
    """Each form's channel, the online submissions, the paper part, and what the attorney must decide."""
    if preference not in ("paper", "online"):
        raise ToolError(f"The filing method must be paper or online (got {preference!r}).")
    wanted: list[str] = []
    counts: dict[str, int] = {}
    for f in forms:
        form = fees.normalize_form(f)
        if form:
            counts[form] = counts.get(form, 0) + 1
            if form not in wanted:
                wanted.append(form)
    if not wanted:
        raise ToolError("Name the forms, for example --forms I-130,I-130A,I-485,I-864.")
    if basis is not None and basis not in I485_BASES:
        raise ToolError(f"--basis I-485 is one of {', '.join(I485_BASES)} (got {basis!r}).")
    if pending_i485 not in (None, "online", "paper"):
        raise ToolError(f"--pending-i485 is online or paper (got {pending_i485!r}).")
    on = on or date.today()
    priced = [f for f in wanted if f in fees.FEES]
    cats = fees.resolve_categories(priced, list(categories)) if priced else {}
    ctx = _Context(forms=wanted, cats=cats, basis=basis,
                   eligibility={fees.normalize_form(k): normalize_eligibility(v) for k, v in (eligibility or {}).items()},
                   fee_waiver={fees.normalize_form(f) for f in fee_waiver}, pending_i485=pending_i485)
    all_mandates = list(MANDATES) + list(mandates)

    def covers(form: str) -> set[str]:
        """What a category-limited mandate is matched against: the form's fee category and eligibility code."""
        cat = ctx.cats.get(form, "")
        code = ctx.eligibility.get(form) or (I765_FROM_FEE.get(cat, "") if form == "I-765" else "")
        return {normalize_eligibility(x) for x in (cat, code) if x}
    online_pref = preference == "online"
    problems: list[str] = []
    decisions: list[str] = []
    notes: list[str] = []
    entries: dict[str, dict] = {}

    def entry(form: str, channel: str | None, why: str = "", *, with_form: str | None = None,
              options: frozenset[str] | None = None, needs: str = "") -> dict:
        method = {PDF_UPLOAD: "online", GUIDED: "online", WITH: "online", PAPER: "paper"}.get(channel or "")
        e = {"form": form, "channel": channel, "with": with_form, "method": method,
             "options": sorted(options) if options else [], "why": why, "needs": needs, "mandate": mandate_of[form]}
        entries[form] = e
        return e

    alone = {f: _alone(f, ctx) for f in wanted if f not in PAPER_ACCESSORIES and f != "G-28" and f not in EVIDENCE_OF}
    mandate_of = {f: _mandate_for(f, all_mandates, on, covers(f)) for f in wanted}

    def forced(form: str) -> bool:
        m = mandate_of.get(form)
        return bool(m and m["in_force"])

    def online_ok(form: str) -> bool:
        options, _ = alone[form]
        return bool(options) and (online_pref or forced(form))

    def best(options: frozenset[str]) -> str:
        return PDF_UPLOAD if PDF_UPLOAD in options else GUIDED

    def paper_entry(form: str) -> None:
        options, why = alone[form]
        if options is None and (online_pref or forced(form)):
            entry(form, None, needs=why)
            problems.append(f"{form}: {why}.")
            return
        if forced(form) and not options:
            m = mandate_of[form]
            problems.append(f"USCIS stopped taking the {form} on paper on {m['paper_ends']}"
                            f"{' (' + m['notice'] + ')' if m['notice'] else ''}, but {why}. Check the notice's scope "
                            "before filing.")
        if online_pref and options is not None and not options:
            decisions.append(f"{form} goes on paper: {why}.")
        entry(form, PAPER, why if options is not None and not options else "the matter is set to file on paper",
              options=options)

    # The I-485 and what rides with it.
    group = []
    member_forced: list[str] = []
    i485_online = False
    if "I-485" in wanted:
        basis_now = _i485_basis(ctx)
        group = [f for f in I485_COMPANIONS if f in wanted
                 and not (f == "I-130" and basis_now not in (None, "family"))
                 and not (f == "I-140" and basis_now not in (None, "employment"))
                 and not (f == "I-131" and not ctx.cats.get("I-131", "").startswith("advance_parole"))]
        if basis_now == "vawa" and "I-360" in wanted:
            group.append("I-360")  # filed together, they go in one paper package
        options, why = alone["I-485"]
        member_forced = [f for f in group if forced(f) and alone[f][0]]
        i485_online = bool(options) and (online_pref or forced("I-485") or bool(member_forced))
        if member_forced and not options:
            problems.append(f"USCIS no longer takes the {', '.join(member_forced)} on paper, but this I-485 can't go "
                            f"online ({why}). File the {member_forced[0]} online on its own, and the I-485 on paper "
                            "as its own rules allow.")
        if i485_online:
            entry("I-485", PDF_UPLOAD, why, options=options)
            if not online_pref and not forced("I-485") and member_forced:
                moved = ["I-485"] + [f for f in group if f not in member_forced] + [
                    f for f in ("I-864", "I-864A", "I-693", "I-130A") if f in wanted]
                petition = next((f for f in member_forced if f in ("I-130", "I-140")), None)
                other_way = (f"file the {petition} online on its own first, and the I-485 on paper once it is accepted"
                             if petition else
                             f"file the I-485 on paper first, and the {', '.join(member_forced)} online once USCIS "
                             "accepts it")
                decisions.append(
                    f"The matter is set to file on paper, but USCIS no longer takes the {', '.join(member_forced)} on "
                    f"paper, so the {', '.join(moved)} go online with it as one I-485 PDF upload. The other way: "
                    f"{other_way}. {WAIVER_NOTE}")
            for f in group:
                if f == "I-765":
                    opts, w = alone[f]
                    if opts is None:
                        entry(f, None, needs=w)
                        problems.append(f"I-765: {w}.")
                        continue
                    if f in ctx.fee_waiver and opts and PDF_UPLOAD in opts:
                        entry(f, PDF_UPLOAD, "its fee waiver request (I-912) can't go in the I-485's upload, so the "
                              "I-765 and its I-912 are their own PDF upload, once USCIS accepts the I-485",
                              options=opts)
                        decisions.append("I-765 with a fee waiver: upload it with its I-912 on its own, once USCIS "
                                         "accepts the I-485 (the I-912 isn't among the forms the I-485's upload takes).")
                        continue
                    if PDF_UPLOAD not in opts:
                        entry(f, PAPER, w, options=opts)
                        decisions.append(f"I-765 goes on paper even though the I-485 goes online: {w}. Mail it once "
                                         "USCIS accepts the I-485, with a copy of the I-485 receipt notice.")
                        continue
                if f == "I-131" and not alone[f][0]:
                    entry(f, PAPER, alone[f][1], options=alone[f][0])
                    decisions.append(f"I-131 goes on paper even though the I-485 goes online: {alone[f][1]}. Mail it "
                                     "once USCIS accepts the I-485, with a copy of the I-485 receipt notice.")
                    continue
                entry(f, WITH, "added to the I-485's PDF upload as a companion form", with_form="I-485",
                      options=PDF)
        else:
            paper_entry("I-485")
            settled = entries["I-485"]["channel"] is not None
            for f in group:
                if settled:
                    entry(f, PAPER, "it goes in the same package as its I-485", options=alone[f][0])
                else:
                    entry(f, None, needs="its I-485's channel isn't settled yet")
            if "I-360" in group and settled and online_pref:
                decisions.append("To file online instead, upload the I-360 on its own first, then the I-485 once the "
                                 "I-360 is filed.")
    # Every other benefit form, on its own.
    for f in alone:
        if f in entries:
            continue
        options, why = alone[f]
        if online_ok(f):
            channel = best(options)
            note = why
            if channel == GUIDED:
                note = (why + "; " if why else "") + ("the client needs their own USCIS online account, since USCIS "
                                                     "lets a representative file for a client without one only by "
                                                     "PDF upload")
            entry(f, channel, note, options=options)
        else:
            paper_entry(f)
    if online_pref and {"I-140", "I-907"} <= set(wanted):
        decisions.append(f"To file online instead, leave the I-907 out: file the I-140"
                         f"{' and its I-485' if 'I-485' in wanted else ''} by PDF upload, then request premium "
                         "processing with a standalone I-907 by PDF upload once the I-140 has a receipt number "
                         f"starting with IOE ({I140_PAGE}, updated 07/24/2026).")
    # Forms that ride with another form.
    for f, lead in EVIDENCE_OF.items():
        if f not in wanted:
            continue
        host = lead if lead in entries else None
        if host is None:
            entry(f, NOT_FILED, f"it is filed with an {lead}, and this filing has none")
            decisions.append(f"{f} is filed with an {lead}, and this filing has none: leave it out, or add the {lead} "
                             "(an I-864 without an I-485 usually goes to the National Visa Center).")
            continue
        h = entries[host]
        if h["method"] == "online":
            submission_lead = h["with"] or host
            how = "uploaded as evidence"
            if f in CONFIRM_ON_LIST:
                how += " (confirm it is on the account's acceptable-evidence list)"
            entry(f, WITH, f"{how} with the {host}", with_form=submission_lead, options=PDF)
        elif h["method"] == "paper":
            entry(f, PAPER, f"it goes in the same package as its {host}")
        else:
            entry(f, None, needs=f"its {host}'s channel isn't settled yet")
    # Payment forms, the G-1145 and the G-28s.
    paper_forms = [e["form"] for e in entries.values() if e["method"] == "paper"]
    for f in [f for f in wanted if f in PAPER_ACCESSORIES]:  # in the filing's order, not the set's
        if paper_forms:
            entry(f, PAPER, f"it goes in the paper package (with {', '.join(paper_forms)})")
        else:
            entry(f, NOT_FILED, "an online filing is paid in the account and gets its notices there")
    benefit = list(alone)  # every form that is a benefit request of its own
    g28_online = [f for f in benefit if entries.get(f, {}).get("method") == "online"]
    g28_paper = [f for f in benefit if entries.get(f, {}).get("method") == "paper"]
    if "G-28" in wanted:
        entry("G-28", WITH if g28_online else PAPER,
              "one for each party and form in an online submission" if g28_online else "in the paper package",
              with_form="each form" if g28_online else None)
        entries["G-28"]["method"] = "online" if g28_online else "paper"

    def each(forms: list[str]) -> list[str]:
        """A form listed once per filing of it (two applicants' I-485s need two G-28s)."""
        return [f for f in forms for _ in range(counts.get(f, 1))]

    # The online submissions and the paper part.
    submissions: list[dict] = []
    if i485_online:
        riders = [f for f in group if entries[f]["channel"] == WITH]
        submissions.append({
            "lead": "I-485", "channel": PDF_UPLOAD, "count": counts["I-485"],
            "forms": ["I-485"] + riders,
            "evidence_forms": [f for f, e in entries.items() if f in EVIDENCE_OF and e["with"] == "I-485"],
            "g28_for": each(["I-485"] + riders),
            "fee_waiver": False,
        })
        if counts["I-485"] > 1:
            notes.append(f"{counts['I-485']} I-485s: upload each applicant's I-485 with that applicant's own companion "
                         "forms and G-28s; a representative's PDF upload can file for several clients at once.")
    for f in benefit:
        e = entries.get(f) or {}
        if e.get("channel") in (PDF_UPLOAD, GUIDED) and f != "I-485":
            submissions.append({
                "lead": f, "channel": e["channel"], "count": counts.get(f, 1), "forms": [f],
                "evidence_forms": [g for g, x in entries.items() if g in EVIDENCE_OF and x["with"] == f],
                "g28_for": each([f]), "fee_waiver": f in ctx.fee_waiver,
            })
    paper_part = None
    paper_all = [e["form"] for e in entries.values() if e["method"] == "paper" and e["form"] != "G-28"]
    if paper_all:
        paper_part = {"forms": paper_all, "g28_for": each(g28_paper)}
    split = bool(submissions) and bool(paper_part and any(f in benefit for f in paper_part["forms"]))

    # What the attorney should know.
    if submissions:
        if has_online_account == "no":
            decisions.append("Filing online needs a USCIS online account for you as the representative, and your "
                             "profile says you don't have one: open one, or file on paper.")
        if any(s["channel"] == PDF_UPLOAD for s in submissions):
            notes.append("PDF upload: print each form, have each signer sign it in ink, and upload a scan of the "
                         "signed form; an attorney's PDF upload can't be signed electronically. Upload a G-28 for each "
                         "party and form, and keep the name, date of birth and A-Number on each form the same as in "
                         f"the online account ({OPTIONS_PAGE}, updated {PAGE_UPDATED}).")
            notes.append("A PDF upload gets no receipt number when it is submitted: USCIS can take up to 30 days to "
                         "accept it, and a rejection comes by mail with the reason.")
        if any(s["channel"] == GUIDED for s in submissions):
            notes.append("The account's step-by-step form is signed electronically in a USCIS online account, and "
                         "USCIS lets a representative file for a client who has no account only by PDF upload "
                         f"({OPTIONS_PAGE}): the client needs their own account for it.")
        if "I-693" in entries and entries["I-693"]["method"] == "online":
            notes.append("Online, the client opens the civil surgeon's sealed envelope, the I-693 is uploaded with the "
                         "I-485, and the client keeps the original and the envelope until USCIS decides the case.")
        if any(s["fee_waiver"] for s in submissions):
            notes.append("A fee waiver request goes with its form in the same PDF upload, with all its evidence; "
                         "without it, USCIS rejects the form.")
    stale = (on - date.fromisoformat(MANDATES_CHECKED)).days > RECHECK_DAYS
    could_be_required = [f for f in benefit if entries.get(f, {}).get("method") == "paper" and alone.get(f, (None,))[0]]
    for f in benefit:
        m = entries.get(f, {}).get("mandate")
        if not m:
            continue
        if m["in_force"] and entries[f]["method"] == "paper" and not any(f in p and "on paper" in p for p in problems):
            # A paper filing USCIS would refuse: never left as a quiet paper form.
            problems.append(f"USCIS stopped taking the {f} on paper on {m['paper_ends']}"
                            f"{' (' + m['notice'] + ')' if m['notice'] else ''}, but here it goes on paper "
                            f"({entries[f]['why'] or 'with its package'}). File it online, check the notice's scope, "
                            f"or get an approved I-936 waiver first. {WAIVER_NOTE}")
            continue
        where = f" ({m['notice']})" if m["notice"] else ""
        scope = f" The notice covers {m['scope']}; confirm this filing is within it." if m["scope"] else ""
        if m["in_force"] and entries[f]["method"] == "online" and not online_pref and f not in member_forced:
            decisions.append(f"The matter is set to file on paper, but USCIS stopped taking the {f} on paper on "
                             f"{m['paper_ends']}{where}, so it goes online.{scope} {WAIVER_NOTE}")
        elif not m["in_force"]:
            notes.append(f"USCIS stops taking the {f} on paper on {m['paper_ends']}{where} ({m['days_left']} days "
                         f"from {on.isoformat()}): a paper filing must arrive before then.{scope}")
    if could_be_required:
        notes.append(f"USCIS may require the {', '.join(could_be_required)} online on 60 days' notice ({MANDATE_RULE}); "
                     f"none had a notice when the list was checked on {MANDATES_CHECKED}.")
        if stale:
            notes.append(f"That check is more than {RECHECK_DAYS} days old: look for an e-filing notice for the "
                         f"{', '.join(could_be_required)} at {', '.join(MANDATE_SOURCES)} before filing on paper, and "
                         "pass any you find as --mandate FORM=YYYY-MM-DD.")
    return {
        "preference": preference,
        "on": on.isoformat(),
        "checked": {"page": CHANNELS_PAGE, "page_updated": PAGE_UPDATED, "checked": CHECKED,
                    "mandates_checked": MANDATES_CHECKED, "mandates_stale": stale},
        "forms": [entries[f] for f in wanted if f in entries],
        "submissions": submissions,
        "paper": paper_part,
        "split": split,
        "problems": problems,
        "decisions": decisions,
        "notes": notes,
        "sources": [CHANNELS_PAGE, OPTIONS_PAGE, MANDATE_RULE_URL, *MANDATE_SOURCES],
    }


def online_account_answer(matter: Path) -> str | None:
    """The attorney profile's has_uscis_online_account ("yes"/"no"), the only key read; None when unset."""
    path = matter.parent / ".senior-associate" / "attorney-profile.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("has_uscis_online_account")
    except (OSError, ValueError, AttributeError):
        return None
    value = str(value or "").strip().lower()
    return value if value in ("yes", "no") else None


def parse_pairs(values: list[str], default_form: str, what: str) -> dict[str, str]:
    """FORM=VALUE pairs, or a bare VALUE for default_form."""
    out: dict[str, str] = {}
    for raw in values:
        form, sep, value = raw.partition("=")
        if not sep:
            form, value = default_form, raw
        if not value.strip():
            raise ToolError(f"{what} {raw!r}: give FORM=VALUE.")
        out[fees.normalize_form(form)] = value.strip().lower()
    return out


def add_arguments(ap: argparse.ArgumentParser) -> None:
    """The filing and the facts its channels depend on; fees.py takes the same ones."""
    ap.add_argument("matter", type=Path, nargs="?", help="Matter folder (its filing method is the default)")
    ap.add_argument("--forms", help="Comma-separated forms, e.g. I-130,I-130A,I-485,I-864")
    ap.add_argument("--filing-method", choices=("paper", "online"), help="Default: the matter's setting, else paper")
    ap.add_argument("--category", action="append", default=[],
                    help="A fee category for every form that has it (vawa), or FORM=CATEGORY; repeat as needed "
                         "(fees.py --list-categories)")
    ap.add_argument("--basis", action="append", default=[],
                    help="What the I-485 rests on: I-485=family, employment, vawa or other (inferred from an I-130, "
                         "I-140 or a VAWA category when left out)")
    ap.add_argument("--eligibility", action="append", default=[],
                    help="The I-765's eligibility category, I-765=c9 or I-765=(c)(8) (inferred from its fee category "
                         "when it can be)")
    ap.add_argument("--fee-waiver", action="append", default=[], help="A form filed with a fee waiver request; repeat")
    ap.add_argument("--pending-i485", choices=("online", "paper"),
                    help="For an advance parole I-131 filed without its I-485: was that I-485 filed online (receipt "
                         "number starting with IOE)?")
    ap.add_argument("--mandate", action="append", default=[],
                    help="A USCIS e-filing notice not yet in the table: FORM=YYYY-MM-DD (the first day paper is "
                         "refused), optionally =URL after it; repeat")
    ap.add_argument("--on", help="The day the filing will reach USCIS, YYYY-MM-DD (default today)")
    ap.add_argument("--json", action="store_true", help="Print the result as JSON")


def channel_kwargs(args: argparse.Namespace, matter: Path | None) -> dict:
    basis = parse_pairs(args.basis, "I-485", "--basis")
    for form in basis:
        if form != "I-485":
            raise ToolError(f"--basis applies to the I-485 (got {form}).")
    return {
        "basis": basis.get("I-485"),
        "eligibility": parse_pairs(args.eligibility, "I-765", "--eligibility"),
        "fee_waiver": [fees.normalize_form(f) for f in args.fee_waiver],
        "pending_i485": args.pending_i485,
        "mandates": [parse_mandate(m) for m in args.mandate],
        "on": _parse_date(args.on, "--on") if args.on else None,
        "has_online_account": online_account_answer(matter) if matter else None,
    }


def describe(result: dict) -> list[str]:
    """The channels in a few lines, for fees.py and this tool's own output."""
    lines = []
    for s in result["submissions"]:
        rest = [f for f in s["forms"] if f != s["lead"]]
        what = s["lead"] + (f" with {', '.join(rest)}" if rest else "")
        if s["evidence_forms"]:
            what += f"; uploaded as evidence: {', '.join(s['evidence_forms'])}"
        lines.append(f"Online ({'PDF upload' if s['channel'] == PDF_UPLOAD else 'step-by-step form'}): {what}")
    if result["paper"]:
        lines.append(f"On paper: {', '.join(result['paper']['forms'])}")
    return lines


def print_text(result: dict) -> None:
    print(f"Filing channels (matter set to {result['preference']}; USCIS's online list updated "
          f"{result['checked']['page_updated']}, checked {result['checked']['checked']}):")
    for line in describe(result):
        print(f"  {line}")
    for e in result["forms"]:
        where = CHANNEL_WORDS.get(e["channel"] or "", "not settled")
        if e["channel"] == WITH and e["with"]:
            where += f" {e['with']}" if e["with"] != "each form" else " each form"
        reason = e["needs"] or e["why"]
        print(f"  {e['form']:<7} {where}" + (f": {reason}" if reason else ""))
    print_lines(result["problems"], result["decisions"], result["notes"])


def print_lines(problems: list[str], decisions: list[str], notes: list[str]) -> None:
    """The PROBLEM:, DECISION: and note lines this tool and fees.py end with."""
    for prefix, lines in (("PROBLEM: ", problems), ("DECISION: ", decisions), ("- ", notes)):
        for line in lines:
            print(prefix + line)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="How each form in a filing reaches USCIS (online or on paper).")
    add_arguments(ap)
    args = ap.parse_args(argv)
    if not args.forms:
        raise ToolError('Give --forms, for example: filing_channels.py "<matter>" --forms I-130,I-485')
    matter = args.matter.expanduser().resolve() if args.matter else None
    if matter is not None and not matter.is_dir():
        raise ToolError(f"Matter folder not found: {matter}")
    method = args.filing_method or (fees._filing_method_from_matter(matter) if matter else "paper")
    result = decide(args.forms.split(","), method, args.category, **channel_kwargs(args, matter))
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_text(result)
    return 0


if __name__ == "__main__":
    run_cli(main)

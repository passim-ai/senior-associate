#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""USCIS filing fees and how to pay them, for a matter's forms.

    uv run --script fees.py "<matter>" --forms I-130,I-130A,I-485,I-864
        [--filing-method paper|online] [--category CATEGORY | --category FORM=CATEGORY ...]
        [--basis I-485=...] [--eligibility I-765=...] [--fee-waiver FORM] [--pending-i485 online|paper]
        [--mandate FORM=YYYY-MM-DD[=URL]] [--on YYYY-MM-DD] [--output fees.json] [--json]

Prints one line per form (the fee, any separate statutory fee, and how it is paid), the
total, how each form goes to USCIS, and notes. The filing method defaults to the matter's
setting (matter-meta.json). Each form is priced the way filing_channels.py says it goes: an
online matter whose form USCIS takes only on paper is a split filing, the paper forms paid
with payment forms and the rest in the online account; the decision is under "channels" in
the JSON. A relative --output path is inside the matter folder, wherever the command runs from.
Categories pick a form's fee where it varies: a bare category ("vawa") applies to every
form that has it, FORM=CATEGORY to one form. An I-765 or I-131 filed with a fee-paying
I-485 takes its reduced or advance-parole fee automatically. Run --list-categories to see
them all.

The table is USCIS Form G-1055, Fee Schedule. Check the edition below against
https://www.uscis.gov/g-1055 before relying on a total; a newer edition means this table
needs refreshing. No card or bank details are ever asked for, stored or printed.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _packet_common import ToolError, run_cli  # noqa: E402

FEE_SCHEDULE = {
    "form": "G-1055",
    "edition": "10/26/26",
    "url": "https://www.uscis.gov/g-1055",
    "checked": "2026-10-29",
}
# Payment rules, checked 2026-10-29:
# - Policy Alert PA-2025-19 (Aug. 29, 2025): "starting on October 28, 2025, USCIS will no longer
#   accept checks, money orders or other forms of paper payments, unless an exemption is available."
#   1 USCIS-PM B.3 (current as of Oct. 27, 2026) lists the paper instruments USCIS does not accept.
# - Forms G-1450 (card; ed. 02/06/26) and G-1650 (U.S. bank account; ed. 06/03/25) say to place the
#   form "ON TOP" of the package. G-1651 (ed. 06/03/25) requests the paper-payment exemption, one per payer.
# - Tips for Filing Forms by Mail (updated 07/10/2026): pay each filing fee separately for each
#   benefit request; a single combined payment for several forms may get the whole package rejected.
# - Online filings are paid through Pay.gov in the USCIS online account (G-1651 page, G-1055).
#   G-1055 (ed. 10/26/26): online, "the system will guide you through the process of paying your
#   fees with a credit, debit, or pre-paid card. Bank account withdrawals are also available."
#   Filing Fees page (updated 02/12/2026): after you submit, the system directs you to pay.gov. Neither
#   says how the account collects a fee that must be paid separately (a Pub. L. 119-21 fee).
ONLINE_PAYMENT_SOURCE = "https://www.uscis.gov/forms/filing-fees"
PAYMENT_SOURCES = [
    "https://www.uscis.gov/policy-manual/volume-1-part-b-chapter-3",
    "https://www.uscis.gov/g-1450",
    "https://www.uscis.gov/g-1650",
    "https://www.uscis.gov/g-1651",
    "https://www.uscis.gov/forms/filing-guidance/tips-for-filing-forms-by-mail",
]
# Forms Available to File Online (updated 10/07/2026, checked 2026-10-29).
ONLINE_SOURCE = "https://www.uscis.gov/file-online/forms-available-to-file-online"
PAY_ONLINE = "pay in the USCIS online account"
PAY_ON_PAPER = "Form G-1450 (card) or G-1650 (bank account), on top of the packet"


@dataclass(frozen=True)
class Fee:
    label: str
    paper: int | None  # None: can't be filed this way
    online: int | None
    # Additional fees: (name, amount, paid separately). G-1055: Pub. L. 119-21 fees "must be paid by
    # separate payment concurrent with any filing fee"; it doesn't say that of the Asylum Program Fee.
    extra: tuple[tuple[str, int, bool], ...] = ()
    note: str = ""


@dataclass(frozen=True)
class FormFees:
    title: str
    categories: dict[str, Fee]
    default: str | None = "general"
    online_note: str = ""
    aliases: dict[str, str] = field(default_factory=dict)


def _same(label: str, amount: int, **kw) -> Fee:
    return Fee(label, amount, amount, **kw)


PL_119_21 = "Pub. L. 119-21 fee"
APF = "Asylum Program Fee"

FEES: dict[str, FormFees] = {
    "G-28": FormFees("Notice of Entry of Appearance", {"general": _same("General filing", 0)}),
    "G-1145": FormFees("e-Notification of Application/Petition Acceptance", {"general": _same("General filing", 0)}),
    "G-1450": FormFees("Authorization for Credit Card Transactions", {"general": _same("Payment form", 0)}),
    "G-1650": FormFees("Authorization for ACH Transactions", {"general": _same("Payment form", 0)}),
    "G-1651": FormFees("Paper payment exemption request", {"general": Fee("Payment form", 0, None)}),
    "I-130": FormFees("Petition for Alien Relative", {"general": Fee("General filing", 675, 625)}),
    "I-130A": FormFees("Supplemental Information for Spouse Beneficiary", {
        "general": _same("Filed with the spouse's I-130", 0, note="G-1055 lists no separate fee for it."),
    }),
    "I-485": FormFees("Application to Register Permanent Residence or Adjust Status", {
        "general": Fee("General filing (14 or older)", 1440, 1390),
        "under14_with_parent": Fee("Under 14, filed with a parent's I-485", 950, 900),
        "refugee": _same("Refugee, or paroled as a refugee", 0),
        "vawa": _same("VAWA self-petitioner (including derivatives)", 0),
        "t": _same("T nonimmigrant, INA 245(l)", 0),
        "u": _same("U nonimmigrant, INA 245(m)", 0),
        "sij": _same("Special Immigrant Juvenile", 0),
        "military_six_and_six": _same("INA 101(a)(27)(K) armed forces member", 0),
        "afghan_iraqi_siv": _same("Afghan or Iraqi special immigrant", 0),
    }),
    "I-864": FormFees("Affidavit of Support", {"general": _same("General filing", 0)}),
    "I-864A": FormFees("Contract Between Sponsor and Household Member", {"general": _same("General filing", 0)}),
    "I-693": FormFees("Report of Immigration Medical Examination", {
        "general": _same("General filing", 0, note="USCIS charges nothing; the civil surgeon's own fee is separate."),
    }),
    "I-765": FormFees("Application for Employment Authorization", {
        "general": Fee("General filing", 520, 470),
        "with_pending_i485": Fee("With an I-485 filed with a fee on or after April 1, 2024 and still pending", 260, 260),
        "with_i485_before_2024_04_01": _same("With an I-485 filed July 30, 2007 to March 31, 2024, fee paid, still pending", 0),
        "c8_initial": _same("Initial (c)(8), pending asylum application (not ABC)", 0, extra=((PL_119_21, 570, True),)),
        "c8_renewal": Fee("Renewal (c)(8), asylum applicant", 520, 470, extra=((PL_119_21, 275, True),)),
        "refugee": _same("Initial (a)(3) refugee", 0),
        "asylee": _same("Initial (a)(5) asylee", 0),
        "vawa": _same("(c)(9) VAWA self-petitioner adjusting, or (c)(31) approved VAWA self-petition", 0),
        "t": _same("(c)(9) T nonimmigrant adjusting, or T categories", 0),
        "u": _same("(c)(9) U nonimmigrant adjusting, or U categories", 0),
        "sij": _same("(c)(9) Special Immigrant Juvenile adjusting", 0),
        "afghan_iraqi_siv": _same("(c)(9) Afghan or Iraqi special immigrant adjusting", 0),
        "military": _same("Current or former U.S. armed forces member", 0),
    }, online_note="Online only for (a)(12), (c)(8), (c)(9), (c)(11), (c)(19)."),
    "I-131": FormFees("Application for Travel Documents", {
        "advance_parole": Fee("Advance parole, pending I-485", 630, 580),
        "advance_parole_i485_before_2024_04_01": _same(
            "Advance parole, I-485 filed July 30, 2007 to March 31, 2024, fee paid, still pending", 0),
        "reentry_permit": Fee("Reentry permit", 630, None),
        "refugee_travel_refugee": Fee("Refugee travel document, refugee or LPR through refugee status", 0, None),
        "refugee_travel_asylee_under16": Fee("Refugee travel document, asylee (or LPR through asylum), under 16", 135, None),
        "refugee_travel_asylee_16plus": Fee("Refugee travel document, asylee (or LPR through asylum), 16 or older", 165, None),
        "tps_travel": Fee("TPS travel authorization", 630, 580),
    }, default=None, online_note="Online only for advance parole and TPS travel."),
    "I-751": FormFees("Petition to Remove Conditions on Residence", {
        "general": Fee("General filing (joint, or a waiver other than abuse)", 750, 700),
        "abuse_waiver": _same("Waiver based on battery or extreme cruelty", 0),
    }, aliases={"vawa": "abuse_waiver"}),
    "N-400": FormFees("Application for Naturalization", {
        "general": Fee("General filing", 760, 710),
        "reduced": Fee("Reduced fee (household income at or below 400% of the poverty guidelines)", 380, None),
        "military": _same("INA 328 or 329 military service", 0),
    }),
    "I-129F": FormFees("Petition for Alien Fiancé(e)", {
        "general": Fee("General filing", 675, None),
        "k3": Fee("K-3, based on a filed I-130", 0, None),
    }),
    "I-140": FormFees("Immigrant Petition for Alien Workers", {
        "general": Fee("Regular petitioner", 715, 665, extra=((APF, 600, False),)),
        "small_employer": Fee("Small employer", 715, 665, extra=((APF, 300, False),)),
        "self_petitioner": Fee("Self-petitioner", 715, 665, extra=((APF, 300, False),)),
        "nonprofit": Fee("Nonprofit petitioner", 715, 665, extra=((APF, 0, False),)),
    }),
    "I-360": FormFees("Petition for Amerasian, Widow(er), or Special Immigrant", {
        "general": Fee("General filing", 515, None),
        "vawa": _same("VAWA self-petition", 0),
        "sij": Fee("Special Immigrant Juvenile", 0, None, extra=((PL_119_21, 250, True),)),
        "afghan_iraqi_siv": Fee("Afghan or Iraqi special immigrant", 0, None),
    }, online_note="Online only for VAWA self-petitions."),
    "I-612": FormFees("Application for Waiver of the Foreign Residence Requirement", {
        "general": Fee("General filing", 1100, None),
    }),
    "I-601": FormFees("Application for Waiver of Grounds of Inadmissibility", {
        "general": Fee("General filing", 1050, None),
        "sij": Fee("Special Immigrant Juvenile", 0, None),
        "t": Fee("T nonimmigrant status", 0, None),
        "u": Fee("U nonimmigrant status", 0, None),
        "vawa": Fee("VAWA self-petitioner (including derivatives)", 0, None),
        "caa_hrifa_abused": Fee("Abused spouse or child adjusting under the Cuban Adjustment Act or HRIFA", 0, None),
        "nacara": Fee("NACARA benefits", 0, None),
        "afghan_iraqi_siv": Fee("Afghan or Iraqi special immigrant (or derivative)", 0, None),
        "afghan_diplomat": Fee("With an I-485 under section 13 of Pub. L. 85-316, Afghan A or G holder on July 14, 2021", 0, None),
        "indochina_refugee": Fee("Indochinese refugee adjusting under Pub. L. 95-145", 0, None),
    }),
    # G-1055 p. 28: premium processing is "in addition to all other applicable filing fees" and "You must
    # submit the Premium Processing fee separately"; the table prices it only with an I-140.
    "I-907": FormFees("Request for Premium Processing Service", {
        "i140": _same("With an I-140 (EB-1, EB-2 including NIW, or EB-3)", 2965),
    }, default="i140"),
    "I-601A": FormFees("Application for Provisional Unlawful Presence Waiver", {
        "general": Fee("General filing", 795, None),
        "vawa": Fee("VAWA self-petitioner (including derivatives)", 0, None),
        "sij": Fee("Special Immigrant Juvenile", 0, None),
    }),
}
# Fee-exempt I-485 categories whose I-765 filed with it takes the same category.
EXEMPT_I485_AND_I765 = {"refugee", "vawa", "t", "u", "sij", "afghan_iraqi_siv"}
# G-1055 (ed. 10/26/26), Appendix B, "General Fee Exemptions": no I-131 fee for these people, for
# every reentry permit, travel document and parole document...
I131_EXEMPT_ALL = {
    "vawa": "a VAWA self-petitioner or derivative",
    "t": "T status or adjustment under INA 245(l)",
    "u": "U status or adjustment under INA 245(m)",
    "sij": "Special Immigrant Juvenile classification or adjustment under INA 245(h)",
    "military": "a current or former U.S. armed forces member",
    "afghan_iraqi_siv": "an Afghan or Iraqi special immigrant",
}
# ...and for a refugee (or LPR through refugee status), for these documents only.
I131_REFUGEE_DOCS = {"reentry_permit", "refugee_travel_refugee", "advance_parole"}
PAROLE_FEE_NOTE = (
    "Advance parole: when the traveler returns, CBP may collect the $1,050 Pub. L. 119-21 Immigration Parole Fee "
    "at the port of entry unless an exception applies; one exception is a lawful applicant for adjustment of status "
    "under INA 245 returning after temporary travel abroad (G-1055 ed. 10/26/26, Appendix B). It isn't paid with "
    "the I-131."
)


def normalize_form(name: str) -> str:
    s = name.strip().upper().replace(" ", "")
    if s.startswith("FORM"):
        s = s[4:]
    if "-" not in s and len(s) > 1 and s[0] in "GIN" and s[1].isdigit():
        s = s[0] + "-" + s[1:]
    return s


def _wanted(forms: list[str]) -> list[str]:
    wanted = [normalize_form(f) for f in forms if f.strip()]
    if not wanted:
        raise ToolError("Name the forms to price, for example --forms I-130,I-130A,I-485,I-864.")
    unknown = [f for f in wanted if f not in FEES]
    if unknown:
        raise ToolError(
            f"No fee entry for {', '.join(unknown)} in this table. Look it up on Form G-1055 "
            f"({FEE_SCHEDULE['url']}); the table covers {', '.join(sorted(FEES))}."
        )
    return wanted


def resolve_categories(forms: list[str], categories: list[str]) -> dict[str, str]:
    """Each form's fee category: the one named for it, a shared one it has, the one an I-485 implies, or its default."""
    wanted = _wanted(forms)
    _, pick = _picker(wanted, categories)
    return {form: pick(form) for form in wanted}


def calculate(forms: list[str], filing_method: str, categories: list[str], *, channels: dict | None = None) -> dict:
    """The fee lines, total and payment notes for one filing.

    Each form is priced and paid the way it goes to USCIS (filing_channels.py): the online fee in the
    online account, or the paper fee with its own payment form. Without `channels` they are decided
    from the forms, the filing method and the categories alone."""
    if filing_method not in ("paper", "online"):
        raise ToolError(f"--filing-method must be paper or online (got {filing_method!r}).")
    wanted = _wanted(forms)
    if channels is None:
        import filing_channels

        channels = filing_channels.decide(wanted, filing_method, categories)
    method_of = {e["form"]: e["method"] or filing_method for e in channels["forms"]}
    not_filed = {e["form"] for e in channels["forms"] if e["channel"] == "not_filed"}
    shared, pick = _picker(wanted, categories)

    def i131_exemption(cat: str) -> str | None:
        groups = list(shared)
        if "I-485" in wanted:
            groups.append(pick("I-485"))
        for g in groups:
            if g in I131_EXEMPT_ALL:
                return I131_EXEMPT_ALL[g]
            if g == "refugee" and cat in I131_REFUGEE_DOCS:
                return "a refugee, or a permanent resident through refugee status"
        return None

    def how_paid(amount: int, method: str) -> str:
        return "no fee" if amount == 0 else PAY_ONLINE if method == "online" else PAY_ON_PAPER

    lines: list[dict] = []
    notes: list[str] = []
    problems: list[str] = list(channels["problems"])
    for form in wanted:
        method = method_of.get(form, filing_method)
        table = FEES[form]
        cat = pick(form)
        fee = table.categories[cat]
        label = fee.label
        amount = fee.paper if method == "paper" else fee.online
        if amount is None and form in not_filed:
            amount = 0  # a paper-only accessory an online filing leaves out
        elif amount is None:
            problems.append(f"{form} ({fee.label}): the fee table has no {method} fee for it; check Form G-1055 "
                            f"({FEE_SCHEDULE['url']}).")
            amount = fee.paper if fee.paper is not None else (fee.online or 0)
        extras = [{"name": name, "amount": value, "separate_payment": separate} for name, value, separate in fee.extra]
        if form == "I-131":
            exempt = i131_exemption(cat)
            if exempt:
                amount, extras = 0, []
                label = f"{fee.label}; no fee for {exempt} (G-1055 general fee exemptions)"
        total = amount + sum(e["amount"] for e in extras)
        # One payment for the filing fee (with any additional fee G-1055 doesn't require to be paid
        # apart), and one more for each fee that must be paid separately.
        payments: list[dict] = []
        if not form.startswith("G-1"):
            joined = amount + sum(e["amount"] for e in extras if not e["separate_payment"])
            if joined:
                what = "filing fee" + "".join(f" and {e['name']}" for e in extras if not e["separate_payment"] and e["amount"])
                payments.append({"what": what, "amount": joined, "payment": how_paid(joined, method)})
            for e in extras:
                if e["separate_payment"] and e["amount"]:
                    payments.append({"what": e["name"], "amount": e["amount"], "payment": how_paid(e["amount"], method)})
        if form.startswith("G-1"):
            payment = "not a fee"
        elif total == 0:
            payment = "no fee"
        elif method == "online":
            payment = PAY_ONLINE + (f" ({len(payments)} payments: each Pub. L. 119-21 fee is separate)"
                                    if len(payments) > 1 else "")
        elif len(payments) > 1:
            payment = f"{len(payments)} separate payments, each with its own {PAY_ON_PAPER}"
        else:
            payment = PAY_ON_PAPER
        lines.append({
            "form": form, "title": table.title, "category": cat, "category_label": label,
            "filing_method": method, "fee": amount, "additional_fees": extras, "total": total, "payments": payments,
            "payment": payment, "online_available": fee.online is not None, "note": fee.note,
        })
        if table.online_note and method == "online":
            notes.append(f"{form}: {table.online_note}")
        if form == "I-131" and cat.startswith("advance_parole"):
            notes.append(PAROLE_FEE_NOTE)
    grand = sum(line["total"] for line in lines)
    paid = [line for line in lines if line["total"] > 0]
    paid_paper = [line for line in paid if line["filing_method"] == "paper"]
    paid_online = [line for line in paid if line["filing_method"] == "online"]

    def has_extra(rows: list[dict], separate: bool) -> bool:
        return any(e["separate_payment"] is separate and e["amount"] for line in rows for e in line["additional_fees"])

    if paid_paper:
        notes.append(
            "Pay each fee with its own payment form (G-1450 card or G-1650 U.S. bank account), placed on top "
            "of the packet; one combined payment for several forms can get the whole packet rejected. USCIS no "
            "longer takes checks or money orders unless the payer qualifies for the G-1651 exemption."
        )
        if has_extra(paid_paper, True):
            notes.append("A Pub. L. 119-21 fee \"must be paid by separate payment concurrent with any filing fee\" and "
                         "can't be waived (G-1055): it is its own payment line above, with its own payment form.")
        notes.append(
            "Leave the card or bank details on each payment form blank for the payer to fill in and sign; never "
            "put them in the matter folder."
        )
        if has_extra(paid_paper, False):
            notes.append("The I-140's Asylum Program Fee is included in its filing-fee payment here; G-1055 and the I-140 "
                         "page (checked 2026-10-29) don't say whether it may share that payment, so confirm on the "
                         "payment form's instructions before filing.")
    if paid_online:
        notes.append("Pay the fees in the USCIS online account when you submit: the account takes you to Pay.gov, where "
                     "you pay by credit, debit or prepaid card or from a bank account (G-1055; uscis.gov/forms/"
                     "filing-fees, updated 02/12/2026).")
        if has_extra(paid_online, True):
            notes.append("A Pub. L. 119-21 fee \"must be paid by separate payment concurrent with any filing fee\" and "
                         "can't be waived (G-1055): it is its own payment line above. uscis.gov doesn't say how the "
                         "online account collects it, so pay it as the account's payment steps direct and confirm it "
                         "was paid before the filing is final.")
        if has_extra(paid_online, False):
            notes.append("The I-140's Asylum Program Fee is shown with its filing fee here; G-1055 and the I-140 page "
                         "(checked 2026-10-29) don't say whether it is paid with it, so follow the online account's "
                         "payment steps.")
    if paid_paper and paid_online:
        notes.append("This is a split filing: the online forms' fees are paid in the account, and each paper form's fee "
                     "with its own payment form on top of the paper package.")
    notes.append("G-1055 lists no separate biometric services fee for these forms.")
    notes.append(f"Fees from Form G-1055, edition {FEE_SCHEDULE['edition']} (checked {FEE_SCHEDULE['checked']}). "
                 f"Confirm the edition at {FEE_SCHEDULE['url']} before filing.")
    return {
        "fee_schedule": FEE_SCHEDULE,
        "filing_method": filing_method,
        "split": bool(channels["split"]),
        "lines": lines,
        "total": grand,
        "payment_forms_needed": [{"form": line["form"], "what": p["what"], "amount": p["amount"]}
                                 for line in paid_paper for p in line["payments"]],
        "problems": problems,
        "notes": notes,
        "sources": [FEE_SCHEDULE["url"], *(PAYMENT_SOURCES if paid_paper or not paid_online else []),
                    *([ONLINE_PAYMENT_SOURCE] if paid_online else []), ONLINE_SOURCE],
        "channels": channels,
    }


def _picker(wanted: list[str], categories: list[str]):
    """(the shared categories, pick(form) -> that form's category), checking every category given."""
    per_form: dict[str, str] = {}
    shared: list[str] = []
    for raw in categories:
        if "=" in raw:
            form, cat = raw.split("=", 1)
            form = normalize_form(form)
            if form not in FEES:
                raise ToolError(f"--category {raw!r}: {form} isn't one of the forms in the table.")
            per_form[form] = cat.strip().lower()
        elif raw.strip():
            shared.append(raw.strip().lower())
    def applies(cat: str, form: str) -> bool:
        if cat in FEES[form].categories or cat in FEES[form].aliases:
            return True
        return form == "I-131" and (cat in I131_EXEMPT_ALL or cat == "refugee")  # its general fee exemptions

    for cat in shared:
        if not any(applies(cat, f) for f in wanted):
            raise ToolError(f"--category {cat!r} doesn't apply to any of {', '.join(wanted)}. See --list-categories.")

    def pick(form: str) -> str:
        table = FEES[form]
        if form in per_form:
            cat = table.aliases.get(per_form[form], per_form[form])
            if cat not in table.categories:
                raise ToolError(f"{form} has no category {per_form[form]!r}; it has {', '.join(table.categories)}.")
            return cat
        for cat in shared:
            cat = table.aliases.get(cat, cat)
            if cat in table.categories:
                return cat
        if form in ("I-765", "I-131") and "I-485" in wanted:
            i485 = pick("I-485")
            if form == "I-765":
                return i485 if i485 in EXEMPT_I485_AND_I765 else "with_pending_i485"
            return "advance_parole"
        if table.default is None:
            raise ToolError(f"{form}'s fee depends on what is requested; give --category {form}=<one of "
                            f"{', '.join(table.categories)}>.")
        return table.default

    return shared, pick


def _filing_method_from_matter(matter: Path) -> str:
    try:
        from scripts.matter_state import read_meta
    except ImportError:  # running outside the plugin tree
        return "paper"
    return read_meta(matter)["filing_method"]


def print_text(result: dict) -> None:
    import filing_channels

    kind = "split" if result["split"] else result["filing_method"]
    print(f"Fees ({kind} filing; G-1055 edition {result['fee_schedule']['edition']}):")
    for line in result["lines"]:
        extra = "".join(f" + ${e['amount']:,} {e['name']}" for e in line["additional_fees"])
        print(f"  {line['form']:<7} ${line['fee']:>6,}{extra}  {line['category_label']}; {line['payment']}")
    print(f"Total:  ${result['total']:,}")
    for line in filing_channels.describe(result["channels"]):
        print(f"Filing: {line}")
    filing_channels.print_lines(result["problems"], result["channels"]["decisions"],
                                result["notes"] + result["channels"]["notes"])


def main(argv: list[str] | None = None) -> int:
    import filing_channels

    ap = argparse.ArgumentParser(description="USCIS filing fees and payment method for a matter's forms (Form G-1055).")
    filing_channels.add_arguments(ap)
    ap.add_argument("--output", type=Path,
                    help="Also write the result as JSON here (a relative path is inside the matter folder)")
    ap.add_argument("--list-categories", action="store_true", help="Print every form's categories and exit")
    args = ap.parse_args(argv)

    if args.list_categories:
        for form, table in FEES.items():
            cats = ", ".join(f"{k} (${v.paper if v.paper is not None else v.online:,})" for k, v in table.categories.items())
            print(f"{form}: {cats}")
        return 0
    if args.matter is None or not args.forms:
        raise ToolError('Give the matter folder and --forms, for example: fees.py "<matter>" --forms I-130,I-485')
    matter = args.matter.expanduser().resolve()
    if not matter.is_dir():
        raise ToolError(f"Matter folder not found: {matter}")
    method = args.filing_method or _filing_method_from_matter(matter)
    forms = args.forms.split(",")
    channels = filing_channels.decide(_wanted(forms), method, args.category,
                                      **filing_channels.channel_kwargs(args, matter))
    result = calculate(forms, method, args.category, channels=channels)
    if args.output:
        out = args.output.expanduser()
        out = (out if out.is_absolute() else matter / out).resolve()  # never wherever the command ran
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_text(result)
    return 0


if __name__ == "__main__":
    run_cli(main)

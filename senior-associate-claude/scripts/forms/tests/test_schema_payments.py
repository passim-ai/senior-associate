#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Tests for the G-1145, G-1450 and G-1650 schemas and audits, on their official blanks. Values are fictional.

    uv run --script tests/test_schema_payments.py
"""
from __future__ import annotations

import contextlib
from functools import partial
import io
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit_prepared_forms as audit  # noqa: E402
import build_forms  # noqa: E402
import editions  # noqa: E402
import forms_workflow  # noqa: E402
from form_question_schema import get_question_schema, load_field_list, skeleton_plan  # noqa: E402
from official_blanks import PLUGIN_ROOT, official_blank, why_missing  # noqa: E402
import xfa_tools  # noqa: E402

FORMS = {
    "g1145_e_notification": ("g-1145", "09/26/14"),
    "g1450_credit_card_payment": ("g-1450", "02/06/26"),
    "g1650_ach_payment": ("g-1650", "06/03/25"),
}


def base(field: str) -> str:
    return field.split("[")[0]


class PaymentSchemaTests(unittest.TestCase):
    def test_every_box_belongs_to_exactly_one_question_and_every_checkbox_has_its_choices(self) -> None:
        for name, (kind, edition) in FORMS.items():
            schema = get_question_schema(name)
            fields = load_field_list(schema["field_list"])["fields"]
            owners: dict[str, list[str]] = {}
            for key, spec in schema["required_questions"].items():
                for field in spec["required_fields"]:
                    owners.setdefault(field, []).append(key)
                    if fields[base(field)]["type"] == "/Btn":
                        with self.subTest(schema=name, field=field):
                            self.assertEqual(
                                sorted(spec["choices"][field].values()), sorted(fields[base(field)]["states"])
                            )
            with self.subTest(schema=name):
                self.assertEqual((schema["kind"], schema["edition"]), (kind, edition))
                self.assertEqual({f: k for f, k in owners.items() if len(k) > 1}, {})
                self.assertEqual({n for n in fields if not n.startswith("PDF417")} - {base(f) for f in owners}, set())

    def test_card_and_bank_details_can_never_be_filled(self) -> None:
        for name, by_hand in (
            ("g1450_credit_card_payment", ("card_holder_billing_and_contact", "card_details", "card_holder_signature")),
            ("g1650_ach_payment", ("bank_account_details", "account_holder_signature")),
        ):
            questions = get_question_schema(name)["required_questions"]
            for key in by_hand:
                self.assertEqual(questions[key]["allowed_statuses"], ["pending_signature"], key)
            plan = skeleton_plan(name)
            details = next(q for q in plan["questions"] if q["key"] == by_hand[0])
            details["status"] = "filled"
            findings = audit.schema_findings(
                pdf_path=Path("/x.pdf"), kind=FORMS[name][0], questions=plan["questions"],
                manifest_entry={"question_schema": name},
            )
            self.assertIn(audit.INVALID_STATUS_TITLE, [f["title"] for f in findings])
            # Their open item reads as a warning, not a blocking error.
            self.assertEqual(details["unresolved_severity"], "warning")

    def test_payment_audit(self) -> None:
        check = partial(audit.audit_form, "g-1450")
        good = {"GivenName": "Alex", "FamilyName": "Sample", "AuthorizedPaymentAmt": "1,440"}
        self.assertEqual([f for f in check(Path("/x.pdf"), good) if f["severity"] == "error"], [])
        typed = check(Path("/x.pdf"), {**good, "CreditCardNumber_1": "4111", "AuthorizedPaymentAmt": "$675.00"})
        titles = [f["title"] for f in typed if f["severity"] == "error"]
        self.assertIn("Card or bank details are typed into the payment form; the payer writes them by hand", titles)
        self.assertIn("Payment amount is not in whole dollars (no $, no cents)", titles)
        entry = {"pays_for": "I-765", "pays_what": "Pub. L. 119-21 fee", "pays_amount": 275}
        self.assertEqual([f for f in check(Path("/x.pdf"), {**good, "AuthorizedPaymentAmt": "275"}, manifest_entry=entry)
                          if f["severity"] == "error"], [])
        wrong = check(Path("/x.pdf"), {**good, "AuthorizedPaymentAmt": "520"}, manifest_entry=entry)
        self.assertEqual([f["title"] for f in wrong if f["severity"] == "error"],
                         ["Payment amount is not the fee this payment form pays"])
        bank = audit.audit_form("g-1650", Path("/x.pdf"), {"GivenName[0]": "Alex", "FamilyName[0]": "Sample",
                                                          "AuthorizedPaymentAmt": "675", "RoutingNumber": "011000015"})
        self.assertEqual([f["fields"] for f in bank if f["severity"] == "error"], [["RoutingNumber"]])

    def test_g1145_audit(self) -> None:
        check = partial(audit.audit_form, "g-1145")
        self.assertEqual(check(Path("/x.pdf"), {"LastName": "Sample", "FirstName": "Alex", "Email": "a@example.com"}), [])
        none = check(Path("/x.pdf"), {"LastName": "Sample", "FirstName": "Alex"})
        self.assertEqual([f["title"] for f in none], ["E-notification contact is missing: give an email or a mobile number"])
        dashed = check(Path("/x.pdf"), {"LastName": "Sample", "FirstName": "Alex", "MobilePhoneNumber": "555-0100"})
        self.assertEqual(len(dashed), 1)


class PaymentRealBlankTests(unittest.TestCase):
    def test_fill_the_official_blanks(self) -> None:
        cases = {
            "g-1145": {"LastName": "Sample", "FirstName": "Alex", "Email": "alex@example.com", "MobilePhoneNumber": "5555550100"},
            "g-1450": {"GivenName": "Alex", "FamilyName": "Sample", "AuthorizedPaymentAmt": "675",
                       "CCHolderGivenName": "Jordan", "CCHolderFamilyName": "Sample"},
            "g-1650": {"GivenName[0]": "Alex", "FamilyName[0]": "Sample", "AuthorizedPaymentAmt": "675",
                       "GivenName[1]": "Jordan", "FamilyName[1]": "Sample"},
        }
        for kind, mapping in cases.items():
            blank = official_blank(kind)
            if blank is None:
                self.skipTest(why_missing(kind))
            with self.subTest(form=kind), TemporaryDirectory() as tmp:
                self.assertEqual(editions.check_blank(kind, blank)["status"], editions.MATCH)
                out = Path(tmp) / "filled.pdf"
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    result = xfa_tools.write_filled_pdf(blank, out, mapping)
                self.assertEqual(xfa_tools.verify_output(out, result.fields, check_visible=True), {"xfa": {}, "visible": {}})
                errors = [f for f in audit.audit_form(kind, out, audit.merged_values(out)) if f["severity"] == "error"]
                self.assertEqual(errors, [])
                box_findings = audit.box_rule_findings(kind=kind, pdf_path=out, widget_pdf=out, values=audit.merged_values(out))
                self.assertEqual(box_findings, [])


def fees_tool():
    """scripts/packet/fees.py, the fees tool the payment plans come from."""
    import importlib.util

    if "sa_packet_fees" in sys.modules:
        return sys.modules["sa_packet_fees"]
    spec = importlib.util.spec_from_file_location("sa_packet_fees", PLUGIN_ROOT / "scripts" / "packet" / "fees.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["sa_packet_fees"] = module  # its dataclasses look their module up
    spec.loader.exec_module(module)
    return module


CARD = "4111 1111 1111 1111"  # a published test card number, not a real one
ROUTING, ACCOUNT = "011000015", "123456789012"


def payment_plan(schema: str, edits: dict[str, tuple[str, dict[str, str]]] | None = None, *, notes: dict[str, str] | None = None) -> dict:
    """A G-1450 or G-1650 plan with the applicant, the amount and the holder filled in; `edits` sets a
    question's (status, field values) on top."""
    plan = skeleton_plan(schema)
    names = {"g1450_credit_card_payment": ("GivenName", "FamilyName", "CCHolderGivenName", "CCHolderFamilyName"),
             "g1650_ach_payment": ("GivenName[0]", "FamilyName[0]", "GivenName[1]", "FamilyName[1]")}[schema]
    answers = {
        "applicant_name": ("filled", {names[0]: "Alex", names[1]: "Sample"}),
        "payment_amount": ("filled", {"AuthorizedPaymentAmt": "675"}),
        "card_holder_name": ("filled", {names[2]: "Jordan", names[3]: "Sample"}),
        "account_holder_name": ("filled", {names[2]: "Jordan", names[3]: "Sample"}),
        **(edits or {}),
    }
    for question in plan["questions"]:
        if question["allowed_statuses"] == ["pending_signature"]:
            question["status"] = "pending_signature"
        if question["key"] in answers:
            question["status"], values = answers[question["key"]]
            question["field_values"] = {**question["field_values"], **values}
        if question["key"] in (notes or {}):
            question["notes"] = notes[question["key"]]
    return plan


class PaymentDetailsAreNeverWrittenTests(unittest.TestCase):
    """Card and bank numbers never reach a mapping, manifest, build record, log, audit or PDF."""

    def refused(self, plan: dict) -> str:
        with self.assertRaises(ValueError) as caught:
            forms_workflow.plan_questions(plan)
        message = str(caught.exception)
        for secret in ("4111", ROUTING, ACCOUNT):
            self.assertNotIn(secret, message)  # the boxes are named, the values never
        return message

    def test_a_plan_with_card_or_bank_details_is_refused_whatever_the_status(self) -> None:
        forms_workflow.plan_questions(payment_plan("g1450_credit_card_payment"))  # the clean plan is fine
        forms_workflow.plan_questions(payment_plan("g1650_ach_payment"))
        card = {f"CreditCardNumber_{n}": "4111" for n in (1, 2, 3)}
        for status in ("filled", "pending_signature", "missing"):
            message = self.refused(payment_plan("g1450_credit_card_payment", {"card_details": (status, card)}))
            self.assertIn("card_details has card or bank details in CreditCardNumber_1", message)
            self.assertIn("nothing was written", message)
        # A card number under a question whose boxes are the applicant's name.
        misplaced = self.refused(payment_plan("g1450_credit_card_payment", {"applicant_name": (
            "filled", {"GivenName": "Alex", "FamilyName": "Sample", "CreditCardNumber_1": "4111"})}))
        self.assertIn("applicant_name has card or bank details in CreditCardNumber_1", misplaced)
        # Any box that isn't the question's own, even one the tools may fill elsewhere.
        stray = self.refused(payment_plan("g1450_credit_card_payment", {"payment_amount": (
            "filled", {"AuthorizedPaymentAmt": "675", "CCHolderGivenName": "Jordan"})}))
        self.assertIn("payment_amount writes boxes that are not its own (CCHolderGivenName)", stray)
        bank = self.refused(payment_plan("g1650_ach_payment", {"bank_account_details": (
            "pending_signature", {"RoutingNumber": ROUTING, "AccountNumber": ACCOUNT})}))
        self.assertIn("RoutingNumber, AccountNumber", bank)
        noted = self.refused(payment_plan("g1450_credit_card_payment", notes={"card_holder_name": f"Card {CARD}"}))
        self.assertIn("card_holder_name holds a long number", noted)
        # A plan for a payment form that names no schema is held to the same rules.
        bare = payment_plan("g1650_ach_payment", {"applicant_name": ("filled", {"GivenName[0]": "Alex", "AccountNumber": ACCOUNT})})
        bare.pop("question_schema")
        self.refused(bare)
        # Other forms are untouched by these rules.
        self.assertEqual(forms_workflow.payment_plan_problems("i-130", [{"key": "x", "field_values": {"Pt4Line4a_FamilyName": CARD}}]), [])

    def test_the_fill_itself_refuses_card_or_bank_details(self) -> None:
        for kind, mapping in (("g-1450", {"GivenName": "Alex", "CreditCardNumber_1": "4111"}),
                              ("g-1650", {"GivenName[0]": "Alex", "RoutingNumber": ROUTING})):
            blank = official_blank(kind)
            if blank is None:
                self.skipTest(why_missing(kind))
            with self.subTest(form=kind), TemporaryDirectory() as tmp:
                out = Path(tmp) / "filled.pdf"
                with self.assertRaises(ValueError) as caught, contextlib.redirect_stdout(io.StringIO()):
                    xfa_tools.write_filled_pdf(blank, out, mapping)
                self.assertFalse(out.exists())
                self.assertNotIn(ROUTING, str(caught.exception))
                self.assertNotIn("4111", str(caught.exception))

    def test_audit_json_never_repeats_a_detail_typed_into_the_form(self) -> None:
        findings = [{"severity": "error", "form": "g-1450", "file": "/m/4111.pdf", "title": "x",
                     "values": [{"field": "ZipCode", "value": "62701"}, {"field": "CreditCardNumber_1", "value": "4111"}]}]
        values = {"CreditCardNumber_1": "4111", "ZipCode": "62701", "CreditCardTypeChBx": "V", "GivenName": "Alex"}
        scrubbed = audit.redact_payment_details("g-1450", values, findings)
        self.assertNotIn("4111", json.dumps(scrubbed[0]["values"]))
        self.assertNotIn("62701", json.dumps(scrubbed))
        self.assertEqual(scrubbed[0]["file"], "/m/4111.pdf")  # paths are left alone
        self.assertEqual(audit.redact_payment_details("i-130", values, findings), findings)


@unittest.skipUnless(shutil.which("gs") or shutil.which("gswin64c"), "build renders with Ghostscript")
class PaymentBuildTests(unittest.TestCase):
    """The build path on the official G-1450 blank: a plan with card details writes nothing."""

    def matter(self, root: Path) -> build_forms.Layout:
        blank = official_blank("g-1450")
        if blank is None:
            self.skipTest(why_missing("g-1450"))
        layout = build_forms.Layout(root.resolve() / "Sample Matter", "main")
        layout.blank_dir.mkdir(parents=True)
        shutil.copyfile(blank, layout.blank_dir / "G-1450.pdf")
        layout.plans.mkdir(parents=True)
        return layout

    def build(self, layout: build_forms.Layout) -> dict:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return build_forms.build(layout)

    def files_holding(self, layout: build_forms.Layout, secret: str) -> list[str]:
        """Every file under the matter, but the plans, that holds `secret`: a PDF in its stored values
        or its text, any other file in its text."""
        found = []
        for path in layout.matter.rglob("*"):
            if not path.is_file() or path.parent == layout.plans:
                continue
            if path.suffix == ".pdf":
                text = " ".join(audit.merged_values(path).values()) + audit.extract_pdf_text(path)
            else:
                text = path.read_text(encoding="utf-8", errors="replace")
            if secret in text:
                found.append(str(path.relative_to(layout.matter)))
        return found

    def test_card_details_in_a_plan_reach_no_file_and_typed_ones_are_removed(self) -> None:
        with TemporaryDirectory() as tmp:
            layout = self.matter(Path(tmp))
            plan_path = layout.plans / "G-1450 - I-130 filing fee.plan.json"
            card = {"CreditCardNumber_1": "4111", "CreditCardNumber_2": "1111", "CreditCardNumber_3": "1111",
                    "CreditCardNumber_4[0]": "8317", "CreditCardNumber_4[1]": "987"}
            plan_path.write_text(json.dumps(payment_plan("g1450_credit_card_payment", {"card_details": ("filled", card)})))
            report = self.build(layout)
            form = report["forms"][0]
            self.assertIn("nothing was written for this form", form["error"])
            self.assertFalse((layout.mappings / "G-1450 - I-130 filing fee.mapping.json").exists())
            self.assertFalse((layout.forms_dir / "G-1450 - I-130 filing fee.pdf").exists())
            self.assertEqual(json.loads(layout.manifest.read_text())["files"], {})
            self.assertEqual(self.files_holding(layout, "8317"), [])

            # Cleared, it builds; the payer's boxes stay blank on both layers.
            plan_path.write_text(json.dumps(payment_plan("g1450_credit_card_payment")))
            report = self.build(layout)
            self.assertEqual(report["forms"][0]["error"], "")
            source = layout.source_dir / "G-1450 - I-130 filing fee source.pdf"
            stored = audit.merged_values(source)
            self.assertEqual([n for n in forms_workflow.PAYMENT_BY_HAND["g-1450"] if audit.field_value(stored, n).strip()
                              not in {"", "0", "Off"}], [])

            # Someone types the card into the source in Acrobat: the next build takes it out again
            # and says so, without copying it anywhere.
            typed = Path(tmp) / "typed.pdf"
            with patch.object(xfa_tools, "payment_form_of", return_value=""), contextlib.redirect_stdout(io.StringIO()):
                xfa_tools.write_filled_pdf(source, typed, card)
            shutil.copyfile(typed, source)
            self.assertNotEqual(self.files_holding(layout, "8317"), [])
            report = self.build(layout)
            form = report["forms"][0]
            self.assertEqual((form["error"], form["reason"]), ("", "card or bank details removed"))
            self.assertTrue(any("removed card or bank details" in line for line in form["warnings"]))
            self.assertEqual(self.files_holding(layout, "8317"), [])

    def test_each_fee_gets_its_own_payment_form(self) -> None:
        # An I-765 renewal with its separate Pub. L. 119-21 fee, and two applicants' I-485s.
        fees = fees_tool().calculate(["I-765", "I-485", "I-485"], "paper", ["I-765=c8_renewal"])
        self.assertEqual([(f["form"], f["what"]) for f in fees["payment_forms_needed"]],
                         [("I-765", "filing fee"), ("I-765", "Pub. L. 119-21 fee"), ("I-485", "filing fee"),
                          ("I-485", "filing fee")])
        with TemporaryDirectory() as tmp:
            layout = self.matter(Path(tmp))
            fees_json = Path(tmp) / "fees.json"
            fees_json.write_text(json.dumps(fees))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                lines = build_forms.setup(layout, [], [], payments=fees_json)
            names = sorted(path.name[: -len(".plan.json")] for path in layout.plans.glob("*.plan.json"))
            self.assertEqual(names, ["G-1450 - I-485 filing fee (1 of 2)", "G-1450 - I-485 filing fee (2 of 2)",
                                     "G-1450 - I-765 Pub. L. 119-21 fee", "G-1450 - I-765 filing fee"])
            self.assertTrue(any("pays the I-765 Pub. L. 119-21 fee, $275" in line for line in lines))
            for path in layout.plans.glob("*.plan.json"):
                plan = json.loads(path.read_text())
                for question in plan["questions"]:
                    if question["key"] == "applicant_name":
                        question.update(status="filled", field_values={"GivenName": "Alex", "MiddleName": "", "FamilyName": "Sample"})
                    if question["key"] == "card_holder_name":
                        question.update(status="pending_client_input")
                path.write_text(json.dumps(plan))
            report = self.build(layout)
            self.assertEqual([form["error"] for form in report["forms"]], [""] * 4)
            manifest = json.loads(layout.manifest.read_text())["files"]
            paid = sorted((entry["fee_order"], entry["pays_for"], entry["pays_what"], entry["pays_amount"])
                          for entry in manifest.values())
            self.assertEqual(paid, [(1, "I-765", "filing fee", 520), (2, "I-765", "Pub. L. 119-21 fee", 275),
                                    (3, "I-485", "filing fee", 1440), (4, "I-485", "filing fee", 1440)])
            amounts = {path.stem[: -len(" source")]: audit.field_value(audit.merged_values(path), "AuthorizedPaymentAmt")
                       for path in layout.source_dir.glob("*.pdf")}
            self.assertEqual(amounts, {"G-1450 - I-485 filing fee (1 of 2)": "1,440", "G-1450 - I-485 filing fee (2 of 2)": "1,440",
                                       "G-1450 - I-765 Pub. L. 119-21 fee": "275", "G-1450 - I-765 filing fee": "520"})
            # A fees file that changed since: the kept plan says its amount is out of date.
            fees["payment_forms_needed"][0]["amount"] = 470
            fees_json.write_text(json.dumps(fees))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                again = build_forms.setup(layout, [], [], payments=fees_json)
        self.assertTrue(any("authorizes $520 and the I-765 filing fee is now $470" in line for line in again), again)

    def test_a_fees_file_entry_must_be_a_form_and_a_whole_amount(self) -> None:
        with TemporaryDirectory() as tmp:
            fees_json = Path(tmp) / "fees.json"
            for bad in ({"form": "../../escaped", "what": "filing fee", "amount": 100},
                        {"form": "I-765", "what": "filing fee", "amount": 260.99},
                        {"form": "I-765", "what": "filing fee", "amount": 0}):
                fees_json.write_text(json.dumps({"payment_forms_needed": [bad]}))
                with self.subTest(entry=bad), self.assertRaises(build_forms.BuildError):
                    build_forms.payment_plan_specs(fees_json, "G-1450")


class SignOfLifeTests(unittest.TestCase):
    """A build renews the run's fresh lease as it works, and never a stale or missing one."""

    def build_with_lease(self, root: Path, minutes_ago: int | None) -> dict | None:
        from datetime import datetime, timedelta, timezone

        sys.path.insert(0, str(PLUGIN_ROOT))
        from scripts import matter_state

        blank = official_blank("g-1145")
        if blank is None:
            self.skipTest(why_missing("g-1145"))
        layout = build_forms.Layout(root.resolve() / "Sample Matter", "main")
        layout.blank_dir.mkdir(parents=True)
        shutil.copyfile(blank, layout.blank_dir / "G-1145.pdf")
        layout.plans.mkdir(parents=True)
        plan = skeleton_plan("g1145_e_notification")
        (layout.plans / "G-1145.plan.json").write_text(json.dumps(plan))
        self.now = datetime.now(tz=timezone.utc)
        if minutes_ago is not None:
            self.assertTrue(matter_state.acquire_lease(layout.matter, "run-1", "build", "orchestrator",
                                                       now=self.now - timedelta(minutes=minutes_ago))[0])
        with patch.object(matter_state, "_last_sign_of_life", {}), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            build_forms.build(layout)
        return matter_state.read_lease(layout.matter)

    def test_a_fresh_lease_is_renewed_and_a_stale_or_missing_one_left_alone(self) -> None:
        from datetime import datetime, timedelta

        with TemporaryDirectory() as tmp:
            fresh = self.build_with_lease(Path(tmp) / "a", 10)
            self.assertGreater(datetime.fromisoformat(fresh["heartbeat_at"]), self.now - timedelta(minutes=1))
            stale = self.build_with_lease(Path(tmp) / "b", 40)
            self.assertLess(datetime.fromisoformat(stale["heartbeat_at"]), self.now - timedelta(minutes=39))
            self.assertIsNone(self.build_with_lease(Path(tmp) / "c", None))


class PaymentsPathTests(unittest.TestCase):
    def test_a_relative_fees_file_is_read_from_the_matter_folder(self) -> None:
        # fees.py --output writes a relative path inside the matter; build --payments reads it from there too,
        # wherever the command runs from.
        with TemporaryDirectory() as tmp:
            matter, elsewhere = Path(tmp) / "matter", Path(tmp) / "elsewhere"
            matter.mkdir()
            elsewhere.mkdir()
            seen: dict[str, object] = {}

            def fake_setup(layout, new, blank, *, payments=None, payment_form="G-1450", refresh=()):
                seen["payments"] = payments
                return []

            parser = forms_workflow.build_parser()
            args = parser.parse_args(["build", str(matter), "--payments", "output/working/vault/forms/main/fees.json"])
            with patch.object(build_forms, "setup", fake_setup), contextlib.chdir(elsewhere), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(build_forms.run(args), 0)
            self.assertEqual(seen["payments"], (matter / "output/working/vault/forms/main/fees.json").resolve())
            absolute = Path(tmp) / "fees.json"
            self.assertEqual(build_forms.in_matter(matter, absolute), absolute.resolve())


if __name__ == "__main__":
    unittest.main()

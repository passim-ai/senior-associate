"""Question schema for Form G-1650, Authorization for ACH Transactions (payment from a U.S. bank account).

Built against the 06/03/25 edition (uscis.gov/g-1650 and the PDF footer, checked 2026-10-29).
Field list: schemas/fields/G-1650.json, every box of the form.

Many box names and tooltips on this edition were copied from the G-1450 and mislead: the second
GivenName/MiddleName/FamilyName row is the bank account holder, not a card holder;
CB_CreditCardType is the Checking/Savings choice ('V' checks Checking, 'MC' Savings, by the boxes'
positions); RoutingNumber, AccountNumber and BankName are bank boxes whatever their tooltips say.

As with the G-1450, the tools prepare only the applicant's name, the amount, and the account
holder's name when the record says who pays. The account type, routing and account numbers, bank
name and business name are never typed into the PDF: the account holder writes them and signs.
Those questions allow only `pending_signature`, and the audit reports any of their boxes that holds
a value. Add one `attorney_action` open item (not blocking filing): "Fill in the payment details and
sign the payment form". One G-1650 per fee, on top of the packet (a fee paid apart from the
filing fee gets its own); `build --payments` records the form, the fee and the amount in the
plan's `pays_for`, `pays_what` and `pays_amount`.
"""
from __future__ import annotations

from _common import FILLED, PENDING_CLIENT, PENDING_SIGNATURE, q

BY_HAND = (
    "Never typed: the account holder fills this in by hand at signing. Leave the box blank; the question "
    "allows only pending_signature, and the audit reports a value here."
)

SCHEMAS = {
    "g1650_ach_payment": {
        "kind": "g-1650",
        "edition": "06/03/25",
        "field_list": "G-1650.json",
        "description": (
            "Form G-1650 bank account (ACH) authorization for one form's fee: the applicant's name, the amount "
            "and the account holder's name; bank details are left for the account holder to write and sign."
        ),
        "notes": [
            "One G-1650 per fee, placed on top in a paper filing: a form's filing fee and each fee paid apart from it "
            "get their own. `build --payments FEES.json --payment-form G-1650` writes these plans from the fees tool's "
            "output, with the form, the fee and the amount already in. The account must be at a U.S. bank.",
            "Add one attorney_action open item, not blocking: Fill in the payment details and sign the payment form.",
        ],
        "required_questions": {
            "applicant_name": q(
                "Applicant's/Petitioner's/Requester's Information (Full Legal Name)",
                ["GivenName[0]", "MiddleName[0]", "FamilyName[0]"],
                ["GivenName[0]", "FamilyName[0]"],
                notes={
                    "GivenName[0]": "The applicant, petitioner or requester on the form this pays for (the first row).",
                },
            ),
            "payment_amount": q(
                "Authorized Payment Amount (whole dollars)",
                ["AuthorizedPaymentAmt"],
                ["AuthorizedPaymentAmt"],
                notes={
                    "AuthorizedPaymentAmt": (
                        "The fee of the form this pays for, from the fee schedule (fees.py), in whole dollars with "
                        "no '$' or cents (the form prints the .00)."
                    ),
                },
            ),
            "account_holder_name": q(
                "Bank Account Holder Information: account holder's name as it appears on the account",
                ["GivenName[1]", "MiddleName[1]", "FamilyName[1]"],
                ["GivenName[1]", "FamilyName[1]"],
                allowed=[FILLED, PENDING_CLIENT],
                notes={
                    "GivenName[1]": (
                        "The second name row is the ACCOUNT HOLDER (its tooltip says card holder). Only when the record "
                        "or the attorney says who pays; otherwise pending_client_input."
                    ),
                },
            ),
            "bank_account_details": q(
                "Business or personal account, business name, checking or savings, routing and account numbers, "
                "bank name (written by the account holder)",
                ["CB_AccountType", "BusinessName", "CB_CreditCardType", "RoutingNumber", "AccountNumber", "BankName"],
                allowed=[PENDING_SIGNATURE],
                notes={
                    "CB_CreditCardType": "Checking or Savings, despite the name. " + BY_HAND,
                    "RoutingNumber": "The 9-digit routing number. " + BY_HAND,
                },
                choices={
                    "CB_AccountType": {"Business Account": "B", "Personal Account": "P"},
                    "CB_CreditCardType": {"Checking Account": "V", "Savings Account": "MC"},
                },
            ),
            "account_holder_signature": q(
                "Account Holder's Signature (in ink; it can't be signed electronically)",
                ["SignatureOfApplicant"],
                allowed=[PENDING_SIGNATURE],
                notes={"SignatureOfApplicant": "Protected box (maxlen 1). The account holder signs in ink."},
            ),
        },
    }
}

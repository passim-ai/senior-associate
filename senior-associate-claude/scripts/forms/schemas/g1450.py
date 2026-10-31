"""Question schema for Form G-1450, Authorization for Credit Card Transactions.

Built against the 02/06/26 edition (uscis.gov/g-1450 and the PDF footer, checked 2026-10-29: "We
will also accept prior editions"). Field list: schemas/fields/G-1450.json, every box of the form.

The tools prepare only what the firm knows: the applicant's name, the amount, and the card
holder's name when the record says who pays. The card number, expiry, CVV, card type and the
holder's billing address and contact details are never typed into the PDF: the card holder writes
them by hand and signs (the form can't be signed electronically). Those questions allow only
`pending_signature`, and the audit reports any of their boxes that holds a value. Add one
`attorney_action` open item (not blocking filing; a physical filing item): "Fill in the payment
details and sign the payment form".

The form has no box for the form it pays for: one G-1450 goes on top of each fee it pays, and a
form with a fee paid apart from its filing fee (the I-765's Pub. L. 119-21 fee) gets one for each
(`build --payments` names the plans 'G-1450 - I-130 filing fee' and so on, and records the form,
the fee and the amount in the plan's `pays_for`, `pays_what` and `pays_amount`). The amount is
that fee as the fee schedule gives it (the fees tool, scripts/packet/fees.py), in whole dollars. USCIS charges up to the amount authorized and treats
the fee as final; "You must submit all fees in the exact amounts" (form, page 1).
"""
from __future__ import annotations

from _common import FILLED, PENDING_CLIENT, PENDING_SIGNATURE, q

BY_HAND = (
    "Never typed: the card holder fills this in by hand at signing. Leave the box blank; the question "
    "allows only pending_signature, and the audit reports a value here."
)

SCHEMAS = {
    "g1450_credit_card_payment": {
        "kind": "g-1450",
        "edition": "02/06/26",
        "field_list": "G-1450.json",
        "description": (
            "Form G-1450 credit card authorization for one form's fee: the applicant's name, the amount and the "
            "card holder's name; card details are left for the card holder to write and sign."
        ),
        "notes": [
            "One G-1450 per fee, placed on top in a paper filing: a form's filing fee and each fee paid apart from it "
            "get their own. `build --payments FEES.json` writes these plans from the fees tool's output, with the form, "
            "the fee and the amount already in (pays_for, pays_what, pays_amount).",
            "Add one attorney_action open item, not blocking: Fill in the payment details and sign the payment form.",
        ],
        "required_questions": {
            "applicant_name": q(
                "Applicant's/Petitioner's/Requester's Information (Full Legal Name)",
                ["GivenName", "MiddleName", "FamilyName"],
                ["GivenName", "FamilyName"],
                notes={
                    "GivenName": "The applicant, petitioner or requester on the form this pays for.",
                    "MiddleName": "If any.",
                },
            ),
            "payment_amount": q(
                "Authorized Payment Amount (whole dollars)",
                ["AuthorizedPaymentAmt"],
                ["AuthorizedPaymentAmt"],
                notes={
                    "AuthorizedPaymentAmt": (
                        "The fee of the form this pays for, from the fee schedule (fees.py), in whole dollars with "
                        "no '$' or cents: 675, or 1,440 (maxlen 7; the form prints the .00)."
                    ),
                },
            ),
            "card_holder_name": q(
                "Credit Card Billing Information: card holder's name as it appears on the card",
                ["CCHolderGivenName", "CCHolderMiddleName", "CCHolderFamilyName"],
                ["CCHolderGivenName", "CCHolderFamilyName"],
                allowed=[FILLED, PENDING_CLIENT],
                notes={
                    "CCHolderGivenName": (
                        "The payer, exactly as the card shows it, only when the record or the attorney says who pays; "
                        "otherwise pending_client_input (the payer writes it)."
                    ),
                },
            ),
            "card_holder_billing_and_contact": q(
                "Card holder's billing address, daytime phone and email (written by the card holder)",
                ["Pt1Line2b_StreetNumberName", "CCHolderAptSteFlr_Unit", "CCHolderAptSteFlrNumber", "CityOrTown",
                 "State", "ZipCode", "DaytimeTelephoneNumber", "Email"],
                allowed=[PENDING_SIGNATURE],
                notes={"Pt1Line2b_StreetNumberName": BY_HAND},
                choices={"CCHolderAptSteFlr_Unit": {"Apt.": " APT ", "Ste.": " STE ", "Flr.": " FLR "}},
            ),
            "card_details": q(
                "Credit Card Information: number, type, expiration date and CVV (written by the card holder)",
                ["CreditCardNumber_1", "CreditCardNumber_2", "CreditCardNumber_3", "CreditCardNumber_4[0]",
                 "CreditCardNumber_4[1]", "CreditCardTypeChBx", "ExpirationDate"],
                allowed=[PENDING_SIGNATURE],
                notes={
                    "CreditCardNumber_1": BY_HAND,
                    "CreditCardNumber_4[1]": "The CVV code, despite the name. " + BY_HAND,
                },
                choices={"CreditCardTypeChBx": {"Visa": "V", "MasterCard": "MC", "American Express": "A", "Discover": "D"}},
            ),
            "card_holder_signature": q(
                "Credit Card Holder's Signature (in ink; it can't be signed electronically)",
                ["SignatureOfApplicant"],
                allowed=[PENDING_SIGNATURE],
                notes={"SignatureOfApplicant": "Protected box (maxlen 1). The card holder signs in ink."},
            ),
        },
    }
}

"""Question schema for Form G-1145, e-Notification of Application/Petition Acceptance.

Built against the 09/26/14 edition (uscis.gov/g-1145, checked 2026-10-29: "You can also use
previous editions"; the page publishes no separate instructions, the form carries its own).
Field list: schemas/fields/G-1145.json, every box of the form.

The form says: clip it to the first page of the application package; USCIS sends one e-mail
and/or text message for each form filed, within 24 hours of accepting it, only for filings at a
USCIS lockbox; overseas customers get only the e-mail. It carries no personal
information beyond the name and the contact given here.
"""
from __future__ import annotations

from _common import q

SCHEMAS = {
    "g1145_e_notification": {
        "kind": "g-1145",
        "edition": "09/26/14",
        "field_list": "G-1145.json",
        "description": (
            "Form G-1145 for an e-mail and/or text when USCIS accepts a paper filing at a lockbox; one per package, "
            "clipped to its first page."
        ),
        "notes": [
            "One G-1145 per package: clipped to the first page, it brings one message for each form in the "
            "package. The packet puts it after the payment forms and before the cover letter. build --new adds it "
            "to a paper filing's first setup.",
            "Whose e-mail and mobile number go here is the attorney's choice (often the firm's). In a protected "
            "matter (VAWA, T or U), use only the firm's contact or one the client said is safe: the message "
            "names the receipt.",
        ],
        "required_questions": {
            "applicant_name": q(
                "Applicant/Petitioner Full Last Name, First Name, Middle Name",
                ["LastName", "FirstName", "MiddleName"],
                ["LastName", "FirstName"],
                notes={
                    "LastName": "The applicant or petitioner on the form this is clipped to (maxlen 30).",
                    "FirstName": "maxlen 18.",
                    "MiddleName": "If any (maxlen 18).",
                },
            ),
            "notification_contact": q(
                "Email Address and Mobile Phone Number (Text Message): at least one",
                ["Email", "MobilePhoneNumber"],
                notes={
                    "Email": "The address that gets the e-mail. The audit asks for this or the mobile number.",
                    "MobilePhoneNumber": (
                        "Digits only, no spaces, dashes or parentheses (maxlen 15), as the form says: "
                        "(011) 555-0101 is 0115550101. A U.S. number only; overseas customers get only the e-mail."
                    ),
                },
            ),
        },
    }
}

#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""The formats USCIS boxes take, and one validator for each.

Every form's date boxes take mm/dd/yyyy, its A-Number boxes 7 to 9 digits with no "A" or dashes
(the "A-" is printed beside the box), and so on. A box's format comes from the form itself where
the form says it: the XFA template marks a date box as a date field (or gives it a date picture).
The number boxes share one picture (nine digits for an A-Number, an SSN and an employer's tax
number alike), so those are told apart by the box's name, which USCIS keeps consistent across
forms (`...AlienNumber`, `...SSN`, `...ReceiptNumber`).

A picture of five digits, text{99999}, says only that the box takes up to five digits: most such
boxes are ZIP Codes, but the I-130's "How many times have you been married?" boxes carry it too.
So a five-digit box is a ZIP Code only when its name or the form's own description of it (the
template's tool tip, which screen readers speak) says ZIP Code; any other is a number box. And a
box named for a ZIP Code with no five-digit picture, whose description says an address abroad
goes in it too (the N-400's residence and employment tables: a "ZIP Code/Postal Code" column),
takes a ZIP Code on a U.S. row and a postal code on a row abroad, so it is checked against its
row's country box.

    box_formats(pdf)            {field base: format} for a form's text boxes
    check(format, value)        a short reason the value doesn't fit, or None
    country_box(base)           the country box of a ZIP-or-postal-code box's row
    US_STATE_CODES              the two-letter codes the state drop-downs offer

The audit runs these on every stored value of every form (audit_prepared_forms.format_findings).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))

DATE = "date"
A_NUMBER = "a_number"
SSN = "ssn"
RECEIPT = "receipt"
I94 = "i94"
ZIP = "zip"
ZIP_OR_POSTAL = "zip_or_postal"  # a table column that takes a ZIP Code, or a postal code on a row abroad
ONLINE_ACCOUNT = "online_account"
STATE = "state"
NUMBER = "number"  # a numeric box whose picture has no decimals (num{zzz,zz9}), or a digits-only text box: whole numbers
AMOUNT = "amount"  # a numeric box that takes decimals (num{zzz,zzz.99}): a wage of 45.67, say

# Words the instructions allow in place of an answer. "N/A" is the general rule for an item that
# does not apply. Where a date box copies an I-94's admit-until date, the record itself may say
# "D/S" (duration of status) or "INDEFINITE" (an asylee's I-94), and a history row that runs to
# today says "PRESENT" (some blanks print it in the date-to box).
NOT_APPLICABLE_WORDS = {"N/A", "NA", "NONE"}
DATE_WORDS = {"N/A", "D/S", "INDEFINITE", "PRESENT"}

US_STATE_CODES = frozenset(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM "
    "NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY "
    "AS FM GU MH MP PW PR VI UM AA AE AP".split()
)

# What each format is called on screen, and what the box takes.
DESCRIPTIONS = {
    DATE: ("Date", "a real date written mm/dd/yyyy (or N/A, D/S, INDEFINITE or PRESENT where the record says so)"),
    A_NUMBER: ("A-Number", "7 to 9 digits, with no A, dashes or spaces"),
    SSN: ("Social Security number", "9 digits, with no dashes or spaces"),
    RECEIPT: ("Receipt number", "3 letters and 10 digits, with no dashes or spaces"),
    I94: ("I-94 number", "11 letters and digits"),
    ZIP: ("ZIP Code", "5 digits (or ZIP+4 as 12345-6789 where the box has room)"),
    ZIP_OR_POSTAL: (
        "ZIP Code or postal code",
        "a 5-digit ZIP Code on a U.S. row (ZIP+4 where the box has room), or the postal code of an address abroad "
        "in letters, digits, spaces and hyphens",
    ),
    ONLINE_ACCOUNT: ("USCIS online account number", "12 digits"),
    STATE: ("State", "a two-letter U.S. state or territory code"),
    NUMBER: ("Number", "digits only (a whole number), with no $, commas or spaces"),
    AMOUNT: ("Amount", "a number with a period before any cents (45.67 or 150000), with no $, commas or spaces"),
}

_NAME_FORMATS: list[tuple[str, re.Pattern[str]]] = [
    (A_NUMBER, re.compile(r"(AlienNumber|ANumber)$", re.IGNORECASE)),
    (SSN, re.compile(r"(SSN|SSNumber|SocialSecurityNumber)$", re.IGNORECASE)),
    (RECEIPT, re.compile(r"Receipt(Number)?$", re.IGNORECASE)),
    (I94, re.compile(r"(I94|I94Number|I94RecordNo|ArrivalDeparture)$", re.IGNORECASE)),
    (ZIP, re.compile(r"ZipCode\d*$", re.IGNORECASE)),
    (
        ONLINE_ACCOUNT,
        re.compile(r"(OnlineAcctNumber|OnlineActNumber|ELISActNumber|ELISAcctNumber|ElisAccountNumber|"
                   r"USCISAccountNumber|OnlineAccountNumber|AcctIdentifier)$", re.IGNORECASE),
    ),
]
_DATE_NAME_RE = re.compile(r"Date|DOB", re.IGNORECASE)
_ZIP_WORDS_RE = re.compile(r"zip", re.IGNORECASE)  # in a box's name (ZipCode) or description ("Enter ZIP Code")
# A description saying the box also takes an address abroad: "ZIP Code (if outside the United
# States, indicate Province and Country)", or a "ZIP Code/Postal Code" column.
_ABROAD_TOO_RE = re.compile(r"postal\s*code|province", re.IGNORECASE)
_DIGITS_PICTURE_RE = re.compile(r"text\{(9+)\}")
_DATE_PICTURE_RE = re.compile(r"date\{([^}]*)\}", re.IGNORECASE)
_DATE_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_NUM_PICTURE_RE = re.compile(r"num\{([^}]*)\}", re.IGNORECASE)


def _local(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def name_format(base: str) -> str | None:
    """The format a box's name gives it (A-Number, SSN, receipt, I-94, ZIP, online account)."""
    for kind, pattern in _NAME_FORMATS:
        if pattern.search(base):
            return kind
    return None


def country_box(base: str) -> str:
    """The country box of the row a ZIP-or-postal-code box sits in (P4_Line3_ZipCode2 ->
    P4_Line3_Country2): the forms name a table's columns alike, row by row."""
    return re.sub(r"ZipCode", "Country", base, count=1, flags=re.IGNORECASE)


def template_kinds(template: bytes | None) -> dict[str, str]:
    """Field name -> "date" for the template's date boxes, "zip" for its ZIP Code boxes,
    "zip_or_postal" for a ZIP Code column that also takes a postal code abroad, "number" or
    "amount" for its numeric boxes, and "" for every other field it describes.

    A date box is a dateTimeEdit, or a text box whose picture is a full date (a card's MM/YYYY
    expiry is not one). A numeric box (numericEdit) holds the number itself in the form's data,
    which Adobe then shows through the box's picture: num{zzz,zzz.99} takes decimals ("amount",
    so a wage of 45.67 is typed 45.67, never 4567), num{zzz,zz9} a whole number ("number"); no
    "$" or commas either way, the picture adds them. A text box with a five-digit picture is a
    ZIP Code when its name or description says so, else a whole number (the I-130's number of
    marriages). A box named for a ZIP Code with no such picture, whose description says an
    address abroad goes in it too, is "zip_or_postal". These come from the template; see the
    module note.
    """
    if not template:
        return {}
    try:
        root = ET.fromstring(template)
    except ET.ParseError:
        return {}
    kinds: dict[str, str] = {}
    for field in root.iter():
        if _local(field) != "field" or not field.get("name"):
            continue
        kinds.setdefault(field.get("name"), "")
        ui = next((child for child in field if _local(child) == "ui"), None)
        widget = _local(next(iter(ui))) if ui is not None and len(ui) else ""
        pictures = [
            (node.text or "").strip()
            for node in field.iter()
            if _local(node) == "picture" and (node.text or "").strip()
        ]
        picture = pictures[0] if pictures else ""
        description = " ".join(
            " ".join("".join(node.itertext()).split()) for node in field.iter() if _local(node) == "toolTip"
        )
        names_zip = bool(_ZIP_WORDS_RE.search(field.get("name")) or _ZIP_WORDS_RE.search(description))
        five_digits = any(len(match) == 5 for match in _DIGITS_PICTURE_RE.findall(picture))
        full_date = any("D" in alternative.upper() for alternative in _DATE_PICTURE_RE.findall(picture))
        if widget == "numericEdit":
            numeric = _NUM_PICTURE_RE.findall(picture)
            whole = bool(numeric) and all("." not in alternative for alternative in numeric)
            kinds[field.get("name")] = NUMBER if whole else AMOUNT
        elif widget == "dateTimeEdit" and (not picture or full_date):
            kinds[field.get("name")] = DATE
        elif widget == "textEdit" and full_date:
            kinds[field.get("name")] = DATE
        elif widget == "textEdit" and five_digits:
            kinds[field.get("name")] = ZIP if names_zip else NUMBER
        elif widget == "textEdit" and _ZIP_WORDS_RE.search(field.get("name")) and _ABROAD_TOO_RE.search(description):
            kinds[field.get("name")] = ZIP_OR_POSTAL
    return kinds


def box_formats(pdf_path: Path) -> dict[str, str]:
    """{field base: format} for the text boxes and drop-downs of a USCIS PDF.

    Text boxes get their format from the template (dates, ZIP Codes) and then from their names;
    a box the XFA template doesn't describe falls back to its name alone, a date being a box
    named for one. A box named for a ZIP Code that the template says also takes a postal code
    abroad keeps the template's "zip_or_postal".
    Drop-downs whose choices are state codes are "state".
    """
    from pypdf import PdfReader
    import xfa_tools  # local import: xfa_tools imports forms_workflow, which this module must not

    reader = PdfReader(str(pdf_path))
    template = xfa_tools.xfa_packet(reader, "template")
    by_template = template_kinds(template)
    formats: dict[str, str] = {}
    for base, specs in xfa_tools.acro_fields_by_base(reader).items():
        field_type = specs[0].field_type
        if field_type == "/Ch":
            options = {state.strip() for spec in specs for state in spec.on_states if state.strip()}
            if options and options <= US_STATE_CODES | {""}:
                formats[base] = STATE
            continue
        if field_type != "/Tx":
            continue
        named, templated = name_format(base), by_template.get(base)
        kind = templated if (named == ZIP and templated == ZIP_OR_POSTAL) else (named or templated)
        if base not in by_template and _DATE_NAME_RE.search(base):
            kind = kind or DATE  # a box the template doesn't describe: its name is all there is
        if kind:
            formats[base] = kind
    return formats


def check(kind: str, value: str, *, max_len: int | None = None, us_row: bool | None = None) -> str | None:
    """Why `value` doesn't fit a box of this format, or None when it does (a blank always fits).

    `us_row` matters only to a "zip_or_postal" box: True when its row's country is the United
    States (a ZIP Code is due), False or None otherwise (a postal code abroad, or a row whose
    country isn't given, takes either)."""
    text = str(value or "").strip()
    if not text:
        return None
    upper = text.upper()
    if kind == DATE:
        if upper in DATE_WORDS:
            return None
        match = _DATE_RE.match(text)
        if match is None:
            return "not written mm/dd/yyyy"
        month, day, year = (int(part) for part in match.groups())
        try:
            date(year, month, day)
        except ValueError:
            return "not a real calendar date"
        if not 1850 <= year <= 2150:
            return "the year is out of range"
        return None
    if upper in NOT_APPLICABLE_WORDS:
        return None
    if kind == A_NUMBER:
        if not text.isdigit():
            return "holds something other than digits (type the number only: no A, dashes or spaces)"
        return None if 7 <= len(text) <= 9 else f"has {len(text)} digits, not 7 to 9"
    if kind == SSN:
        if not text.isdigit():
            return "holds something other than digits (no dashes or spaces)"
        return None if len(text) == 9 else f"has {len(text)} digits, not 9"
    if kind == RECEIPT:
        return None if re.fullmatch(r"[A-Za-z]{3}\d{10}", text) else "is not 3 letters followed by 10 digits"
    if kind == I94:
        return None if re.fullmatch(r"[A-Za-z0-9]{11}", text) else f"is not 11 letters and digits (has {len(text)} characters)"
    if kind == ZIP_OR_POSTAL and us_row:
        kind = ZIP
    if kind == ZIP:
        if re.fullmatch(r"\d{5}", text):
            return None
        if re.fullmatch(r"\d{5}-?\d{4}", text) and (max_len is None or len(text) <= max_len):
            return None
        return "is not a 5-digit ZIP Code" + (" (its row's country is the United States)" if us_row else "")
    if kind == ZIP_OR_POSTAL:
        if re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9 -]*[A-Za-z0-9])?", text):
            return None
        return "is neither a ZIP Code nor a postal code (letters, digits, spaces and hyphens only)"
    if kind == ONLINE_ACCOUNT:
        return None if re.fullmatch(r"\d{12}", text) else "is not 12 digits"
    if kind == STATE:
        return None if upper in US_STATE_CODES else "is not a two-letter U.S. state code"
    if kind == NUMBER:
        return None if text.isdigit() else "is not a whole number written in digits only (no $, commas or spaces)"
    if kind == AMOUNT:
        # The form's data holds the number itself; Adobe rounds what it shows to the picture's cents
        # (a calculated total of a blank stores 0.00000000).
        if re.fullmatch(r"\d+(\.\d+)?", text):
            return None
        return "is not a number written with only digits and a period before any cents (no $, commas or spaces)"
    return None

"""Deterministic contradictions, using edition-specific field semantics where necessary."""
from datetime import datetime, timezone
import re
import unicodedata


def check_consistency(form) -> None:
    from audit_prepared_forms import parse_us_date
    today = form.today or datetime.now(timezone.utc)
    values = form.values
    bases = {name.split("[")[0] for name in values}
    # These paired widget names are separate boxes, not a radio group.
    for base in sorted(bases):
        for left, right in (("_Male", "_Female"), ("_Yes", "_No")):
            if base.endswith(left) and base[:-len(left)] + right in bases:
                form.one_of("Choose only one answer", [base, base[:-len(left)] + right], required=False)
    for name, value in values.items():
        if re.search(r"date.?of.?birth|_DOB$|OtherDOB", name, re.I):
            when = parse_us_date(str(value))
            if when and when > today:
                form.add("A date of birth is in the future", [name])
        if re.search(r"SSN|SocialSecurity", name, re.I):
            digits = re.sub(r"\D", "", str(value))
            if digits and (len(digits) != 9 or digits[:3] in {"000", "666"} or digits[0] == "9" or digits[3:5] == "00" or digits[5:] == "0000"):
                form.add("Social Security number has an invalid structure", [name])
        # A card-like number is an alert, not proof that an arbitrary foreign identifier is invalid.
        if re.search(r"Passport|TravelDoc|NationalID", name, re.I):
            digits = re.sub(r"[ -]", "", str(value))
            if digits.isdigit() and 13 <= len(digits) <= 19:
                doubled = [int(c) * (2 if i % 2 else 1) for i, c in enumerate(digits[::-1])]
                if sum(n - 9 if n > 9 else n for n in doubled) % 10 == 0:
                    form.add("Possible payment-card number in an identity field; verify the source", [name], severity="manual_review")

    def order(first: str, second: str, message: str, *, equal_ok: bool = True):
        a, b = parse_us_date(form.value(first)), parse_us_date(form.value(second))
        if a and b and (a > b if equal_ok else a >= b):
            form.add(message, [first, second])

    if form.kind == "i-130":
        form.one_of("Petition relationship", ["Pt1Line1_Spouse", "Pt1Line1_Parent", "Pt1Line1_Child", "Pt1Line1_Siblings"])
        form.one_of("Petitioner citizenship or residence", ["Pt2Line36_USCitizen", "Pt2Line36_LPR"], required=False)
        form.one_of("Petitioner marital status", [f"Pt2Line17_{s}" for s in ("Single", "Married", "Divorced", "Widowed", "Separated", "Annulled")], required=False)
        order("Pt2Line8_DateofBirth", "Pt2Line18_DateOfMarriage", "Petitioner marriage predates birth")
        order("Pt4Line9_DateOfBirth", "Pt4Line19_DateOfMarriage", "Beneficiary marriage predates birth")
        order("Pt4Line9_DateOfBirth", "Pt4Line21c_DateOfArrival", "Arrival predates birth")
        for parent in ("Pt2Line25_DateofBirth", "Pt2Line31_DateofBirth"):
            order(parent, "Pt2Line8_DateofBirth", "A parent's birth must precede the child's birth", equal_ok=False)
        order("Pt2Line23_DateMarriageEnded", "Pt2Line18_DateOfMarriage", "Prior marriage ends after the current marriage began")
        order("Pt4Line17_DateMarriageEnded[1]", "Pt4Line19_DateOfMarriage", "Prior marriage ends after the current marriage began")
        if form.checked("Pt2Line17_Single") and form.value("Pt2Line18_DateOfMarriage"):
            form.add("Never married conflicts with a current marriage date", ["Pt2Line17_Single", "Pt2Line18_DateOfMarriage"])
        if form.checked("Pt1Line1_Spouse"):
            a, b = form.value("Pt2Line18_DateOfMarriage"), form.value("Pt4Line19_DateOfMarriage")
            if a and b and parse_us_date(a) != parse_us_date(b):
                form.add("Spouse petition lists different current marriage dates", ["Pt2Line18_DateOfMarriage", "Pt4Line19_DateOfMarriage"])
    elif form.kind == "i-485":
        order("Pt1Line3_DOB", "Pt1Line10_DateofArrival", "Arrival predates birth")
        order("Pt1Line3_DOB", "Pt5Line8_DateofBirth[2]", "Current marriage predates applicant birth")
        for parent in ("Pt5Line3_DateofBirth", "Pt5Line8_DateofBirth[0]"):
            order(parent, "Pt1Line3_DOB", "A parent's birth must precede the child's birth", equal_ok=False)
    cross_form_identity(form)


def cross_form_identity(form) -> None:
    """Compare the same subject only. Ambiguous multi-person packets need reviewer judgment."""
    mapping = {
        "i-130": ("Pt4Line4a_FamilyName", "Pt4Line4b_GivenName"),
        "i-130a": ("Pt1Line3a_FamilyName", "Pt1Line3b_GivenName"),
        "i-485": ("Pt1Line1_FamilyName", "Pt1Line1_GivenName"),
    }
    if form.kind not in mapping or not form.manifest_entry:
        return
    subject = str(form.manifest_entry.get("subject") or "").strip().casefold()
    if not subject:
        return
    for entry in form.intent_manifest.values():
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        if kind not in mapping or kind == form.kind or str(entry.get("subject") or "").strip().casefold() != subject:
            continue
        other = entry.get("expected_fields") or {}
        for own, counterpart in zip(mapping[form.kind], mapping[kind]):
            a, b = form.value(own), str(other.get(counterpart) or "").strip()
            norm = lambda v: " ".join(unicodedata.normalize("NFC", v).casefold().split())
            if a and b and norm(a) != norm(b):
                form.add("The same person's name differs between forms", [own], other_form=kind, other_field=counterpart)

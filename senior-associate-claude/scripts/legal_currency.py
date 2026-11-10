"""Validate the researcher's coverage receipt; a receipt is evidence of checks, not a guarantee of current law."""
from datetime import date
from urllib.parse import urlparse


def currency_problems(record: object, *, today: date | None = None) -> list[str]:
    today = today or date.today()
    if not isinstance(record, dict):
        return ["The legal currency review is missing or damaged."]
    problems = []
    try:
        checked = date.fromisoformat(str(record.get("checked_at", ""))[:10])
        if not 0 <= (today - checked).days <= 7:
            problems.append("Refresh the legal currency review before filing; it is future-dated or older than seven days.")
    except ValueError:
        problems.append("The legal currency review needs a valid checked date.")
    jurisdiction = record.get("jurisdiction") or {}
    if not isinstance(jurisdiction, dict) or not all(jurisdiction.get(k) for k in ("forum", "circuit", "basis")):
        problems.append("Confirm the matter's forum, relevant circuit, and the basis for that jurisdiction.")
    required = {"agency_policy", "regulations", "agency_decisions", "controlling_circuit", "adverse_treatment"}
    categories = set(required)
    checks = record.get("checks")
    if not isinstance(checks, list):
        checks = []
    for check in checks:
        if not isinstance(check, dict):
            problems.append("A legal currency check is damaged.")
            continue
        if check.get("category") in categories and check.get("status") == "checked" and check.get("source") and isinstance(check.get("hits"), list):
            required.discard(check["category"])
            for hit in check["hits"]:
                if not isinstance(hit, dict) or hit.get("disposition") not in {"applied", "not_applicable", "already_covered"} or not hit.get("reason"):
                    problems.append("Every update-feed hit needs a disposition and explanation, including hits not used.")
    if required:
        problems.append("Legal source coverage is incomplete: " + ", ".join(sorted(required)) + ".")
    if record.get("unresolved") != []:
        problems.append("Resolve or obtain attorney review of the outstanding legal currency questions.")
    orders = record.get("relied_on_court_orders") or []
    if not isinstance(orders, list):
        return problems + ["The court-order currency record is damaged."]
    for order in orders:
        if not isinstance(order, dict) or not order.get("docket_checked_at") or not order.get("scope") or urlparse(str(order.get("url", ""))).scheme != "https":
            problems.append("A relied-on court order needs a dated docket check, source link, and operative scope.")
            continue
        try:
            checked_order = date.fromisoformat(str(order["docket_checked_at"])[:10])
            if not 0 <= (today - checked_order).days <= 7:
                problems.append("Refresh the relied-on court order's docket and operative scope before filing.")
        except ValueError:
            problems.append("The court-order docket check needs a valid date.")
    return list(dict.fromkeys(problems))

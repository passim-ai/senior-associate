"""Notice response completeness and deadline checks. Dates come from the notice, never a guessed interval."""
from datetime import date
from pathlib import Path
from scripts.matter_state import sha256_file


def response_problems(matter: Path, record: object, *, today: date | None = None) -> list[str]:
    today = today or date.today()
    if not isinstance(record, dict):
        return ["Prepare the RFE/NOID response plan from the complete notice."]
    problems = []
    notice = record.get("notice") or {}
    if not isinstance(notice, dict):
        return ["The response notice record is damaged."]
    try:
        source = (matter / str(notice.get("path", ""))).resolve()
        source.relative_to(matter.resolve())
        if not source.is_file() or sha256_file(source) != notice.get("sha256"):
            problems.append("The response plan must identify the exact, unchanged notice.")
    except (OSError, ValueError, AttributeError):
        problems.append("The response notice must be a readable file in this matter.")
    if not notice.get("all_pages_reviewed") or not notice.get("issued_at"):
        problems.append("Review every notice page and record its issue date.")
    try:
        issued = date.fromisoformat(str(notice.get("issued_at", "")))
        if issued > today:
            problems.append("The notice issue date is in the future; verify the source.")
    except ValueError:
        issued = None
        problems.append("Record a valid issue date from the notice.")
    deadline = record.get("deadline") or {}
    if not isinstance(deadline, dict):
        return problems + ["The response deadline record is damaged."]
    try:
        due = date.fromisoformat(str(deadline.get("date", "")))
        if issued and due < issued:
            problems.append("The response deadline predates the notice; verify the source.")
        if due < today:
            problems.append("The notice deadline has passed. Attorney review of the available procedure is required.")
    except ValueError:
        problems.append("Record the deadline from the notice; do not infer it from the posture.")
    if not all(deadline.get(k) for k in ("source_quote", "source_page", "verified_by", "verified_at")):
        problems.append("The attorney must verify the notice deadline against its quoted text and page.")
    try:
        verified = date.fromisoformat(str(deadline.get("verified_at", ""))[:10])
        if verified > today or (issued and verified < issued):
            problems.append("The deadline verification date does not match the notice chronology.")
    except ValueError:
        problems.append("Record the actual date the attorney verified the deadline.")
    if not record.get("delivery_method") or not record.get("delivery_destination"):
        problems.append("Verify the response delivery method and destination from the notice.")
    grounds = record.get("grounds")
    if not isinstance(grounds, list) or not grounds:
        problems.append("Map each notice request or adverse allegation to a response and supporting evidence.")
    else:
        for ground in grounds:
            if not isinstance(ground, dict) or not all(ground.get(k) for k in ("id", "notice_page", "request", "response", "evidence")) or ground.get("status") != "addressed":
                problems.append("Every notice ground must be addressed, with a page reference and evidence.")
    if record.get("unmapped_notice_requests") != []:
        problems.append("Resolve every unmapped notice request before filing approval.")
    return list(dict.fromkeys(problems))

"""Sensitive answers require an affirmative record of the client's response."""
import re
from datetime import date

SENSITIVE = re.compile(r"arrest|convict|criminal|crime|inadmissib|remov(?:al|ed)|deport|security|terror|persecut|fraud|misrepresent|immigration.violat|unlawful|smuggl|traffick", re.I)


def sensitive_question(spec: dict, form: str = "") -> bool:
    label = str(spec.get("label") or "")
    return bool(SENSITIVE.search(label) or (form.lower().replace("-", "") in {"i485", "n400"} and re.match(r"Part 9\b", label)))


def confirmed(question: dict, facts: dict) -> bool:
    for fact_id in question.get("fact_ids") or []:
        fact = facts.get(str(fact_id), {})
        if not isinstance(fact, dict) or question.get("key") not in (fact.get("question_keys") or []):
            continue
        if fact.get("source_kind") != "client_confirmation" or not str(fact.get("source") or "").strip():
            continue
        try:
            when = date.fromisoformat(str(fact.get("confirmed_at") or ""))
        except ValueError:
            continue
        if when <= date.today() and fact.get("value") is not None:
            return True
    return False

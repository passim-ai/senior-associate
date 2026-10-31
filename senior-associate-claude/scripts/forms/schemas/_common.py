"""What the schema files share: the question builder, the plan statuses, and the answers and notes
that read the same on every form that uses them. Form-specific wording stays in each form's file."""
from __future__ import annotations

from typing import Any

from forms_workflow import (  # noqa: F401 - re-exported for the schema files
    STATUS_FILLED as FILLED,
    STATUS_MANUAL_REVIEW as MANUAL_REVIEW,
    STATUS_NOT_APPLICABLE as NOT_APPLICABLE,
    STATUS_PENDING_CLIENT as PENDING_CLIENT,
    STATUS_PENDING_SIGNATURE as PENDING_SIGNATURE,
)

FILLED_OR_NA = [FILLED, NOT_APPLICABLE]
SIGNATURE_STATUSES = [PENDING_SIGNATURE, FILLED]
OPTIONAL_SIGNATURE = [NOT_APPLICABLE, PENDING_SIGNATURE, FILLED]

YES_NO = {"Yes": "Y", "No": "N"}
UNIT = {"Apt.": " APT ", "Ste.": " STE ", "Flr.": " FLR "}  # padded, as most unit groups store them
DATE = "mm/dd/yyyy."
FOREIGN_ONLY = "Foreign address only."


def q(
    label: str,
    fields: list[str],
    nonempty: list[str] | None = None,
    *,
    allowed: list[str] | None = None,
    notes: dict[str, str] | None = None,
    choices: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """One schema question: its label, every box it declares, the boxes that must be filled when it is
    `filled`, the statuses it allows (filled only, when none are given), and its notes and choices."""
    spec: dict[str, Any] = {"label": label, "required_fields": list(fields)}
    if nonempty:
        spec["required_nonempty_fields_when_filled"] = list(nonempty)
    if allowed:
        spec["allowed_statuses"] = list(allowed)
    if notes:
        spec["field_notes"] = dict(notes)
    if choices:
        spec["choices"] = {field: dict(options) for field, options in choices.items()}
    return spec

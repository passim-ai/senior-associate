"""What the app offers: the case types, filing postures, the steps' plain names and timings, and the status names."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = PLUGIN_ROOT / "skills" / "senior-associate" / "scripts"

DEFAULT_DELIVERABLE = "a filing-ready packet, or a draft packet with an attorney memo and client request list when documents are missing"
DEFAULT_WORKFLOW = "full_packet"


# The runtime's workflows, the one list of steps. matter_workflow imports the bundled scripts package, which lives at
# the plugin root.
for _entry in (str(RUNTIME_DIR), str(PLUGIN_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)
from matter_workflow import WORKFLOW_TEMPLATES as _RUNTIME_WORKFLOWS  # type: ignore  # noqa: E402

WORKFLOW_TEMPLATES = {k: list(v) for k, v in _RUNTIME_WORKFLOWS.items()}

# The steps' plain names: the step chips, "step 4 of 10: Cover letter", and every stage the attorney reads.
STAGE_LABELS = {
    "docs_review": "Document review",
    "forms_preparer": "Forms",
    "forms_reviewer": "Forms review",
    "cover_letter_writer_draft": "Cover letter",
    "cover_letter_researcher": "Research",
    "cover_letter_writer_integrate": "Letter revision",
    "cover_letter_reviewer": "Letter review",
    "packet_assembly": "Packet",
    "final_review": "Final review",
    "attorney_handoff": "Your memo",
    # Matters the runtime hasn't migrated yet still name the two reviews the final review replaced.
    "packet_review": "Packet review",
    "uscis_adjudicator": "Officer's review",
}

# About how long each step takes, in minutes, from timed builds. A full build comes to about an hour and a half.
STAGE_MINUTES = {
    "docs_review": 6,
    "forms_preparer": 15,
    "forms_reviewer": 10,
    "cover_letter_writer_draft": 10,
    "cover_letter_researcher": 10,
    "cover_letter_writer_integrate": 8,
    "cover_letter_reviewer": 8,
    "packet_assembly": 5,
    "final_review": 15,
    "attorney_handoff": 3,
    "packet_review": 8,
    "uscis_adjudicator": 10,
}
DEFAULT_STAGE_MINUTES = 8

# Which stage wrote a findings file, by its name. Older matters have the packet review and adjudicator files.
FINDINGS_FILE_STAGES = {
    "forms review findings.json": "forms_reviewer",
    "cover letter review findings.json": "cover_letter_reviewer",
    "final review findings.json": "final_review",
    "packet review findings.json": "packet_review",
    "reroute matrix.json": "uscis_adjudicator",
}
SUPERSEDED_BY_FINAL_REVIEW = {"packet review findings.json", "reroute matrix.json"}

# "short" names the matter folder ("Garcia I-130 I-485"); "hint" is the one line the app shows under the label.
# "protected" marks a case 8 U.S.C. 1367 keeps confidential: every VAWA case, the I-751 battery or extreme cruelty
# waiver, and T and U cases. Its short is only form numbers, because a folder name shows in Finder and on screen;
# creating one marks the matter protected (matter-meta.json, reason "catalog"), and every brief points the workflow
# to the matter contract's rules for it.
MATTER_TYPES = [
    {"id": "i130_i485", "label": "I-130 / I-485 immediate relative", "matter_type": "I-130/I-485 immediate relative packet", "short": "I-130 I-485", "hint": "Petition and adjustment filed together for a spouse, parent, or child of a U.S. citizen"},
    {"id": "i130_standalone", "label": "I-130 petition only", "matter_type": "I-130 stand-alone petition", "short": "I-130", "hint": "The relative petition alone, e.g. for consular processing"},
    {"id": "i751_joint", "label": "I-751 joint petition", "matter_type": "I-751 joint petition to remove conditions", "short": "I-751", "hint": "Removing conditions on residence, filed by both spouses"},
    {"id": "i751_waiver", "label": "I-751 waiver", "matter_type": "I-751 waiver petition", "short": "I-751 Waiver", "hint": "Removing conditions without the spouse, after a divorce or for extreme hardship"},
    {"id": "n400", "label": "N-400 naturalization", "matter_type": "N-400 naturalization packet", "short": "N-400", "hint": "Application for citizenship"},
    {"id": "i765", "label": "I-765 work permit", "matter_type": "I-765 employment authorization packet", "short": "I-765", "hint": "Employment authorization on its own"},
    {"id": "i131", "label": "I-131 travel document", "matter_type": "I-131 travel document packet", "short": "I-131", "hint": "Advance parole, reentry permit, or refugee travel document"},
    {"id": "i129f", "label": "I-129F fiancé(e) petition", "matter_type": "I-129F fiancé(e) petition packet", "short": "I-129F", "hint": "K-1 visa petition for a fiancé(e)"},
    {"id": "i612", "label": "I-612 waiver", "matter_type": "I-612 waiver packet", "short": "I-612", "hint": "Waiver of the J-1 two-year foreign residence requirement"},
    {"id": "i601a", "label": "I-601A provisional waiver", "matter_type": "I-601A provisional unlawful presence waiver packet", "short": "I-601A", "hint": "Waiver of the 3- or 10-year unlawful presence bar, filed in the U.S. before the immigrant visa interview abroad"},
    {"id": "i601", "label": "I-601 waiver of inadmissibility", "matter_type": "I-601 waiver of inadmissibility packet", "short": "I-601", "hint": "Waiver of unlawful presence, fraud or misrepresentation, criminal or other grounds, with an I-485 or after a consular refusal"},
    {"id": "i140_niw", "label": "I-140 national interest waiver (EB-2 NIW)", "matter_type": "I-140 national interest waiver petition packet", "short": "I-140 NIW", "hint": "EB-2 petition without a job offer or labor certification, usually a self-petition, argued under Matter of Dhanasar"},
    {"id": "i140_i485", "label": "I-140 / I-485 employment-based", "matter_type": "I-140/I-485 employment-based packet", "short": "I-140 I-485", "hint": "Immigrant worker petition and adjustment, filed together"},
    {"id": "i360_vawa", "label": "I-360 VAWA self-petition", "matter_type": "I-360 VAWA self-petition packet", "short": "I-360", "hint": "Self-petition for an abused spouse, child, or parent of a U.S. citizen or LPR; the folder name and client request won't name the case", "protected": True},
    {"id": "i360_i485_vawa", "label": "I-360 / I-485 VAWA self-petition and adjustment", "matter_type": "I-360/I-485 VAWA self-petition and adjustment packet", "short": "I-360 I-485", "hint": "Self-petition and adjustment filed together when a visa is available; the folder name and client request won't name the case", "protected": True},
    {"id": "i751_abuse_waiver", "label": "I-751 waiver: battery or extreme cruelty", "matter_type": "I-751 waiver petition based on battery or extreme cruelty", "short": "I-751", "hint": "Removing conditions without the spouse, for a client who was abused; the folder name and client request won't name the case", "protected": True},
    {"id": "i485_vawa", "label": "I-485 based on a VAWA self-petition", "matter_type": "I-485 adjustment based on an approved VAWA self-petition", "short": "I-485", "hint": "Adjustment for a VAWA self-petitioner whose I-360 is approved; the folder name and client request won't name the case", "protected": True},
    {"id": "i765_vawa", "label": "I-765 for a VAWA self-petitioner", "matter_type": "I-765 employment authorization for a VAWA self-petitioner", "short": "I-765", "hint": "Work permit on a pending or approved VAWA self-petition; the folder name and client request won't name the case", "protected": True},
    {"id": "i914_t", "label": "I-914 T visa", "matter_type": "I-914 T nonimmigrant status application packet", "short": "I-914", "hint": "Custom research required; no bundled I-914 form schema or case checklist. Status for a survivor of human trafficking; the folder name and client request won't name the case", "protected": True},
    {"id": "i918_u", "label": "I-918 U visa", "matter_type": "I-918 U nonimmigrant status petition packet", "short": "I-918", "hint": "Custom research required; no bundled I-918 form schema or case checklist. Status for a victim of a qualifying crime who helped law enforcement; the folder name and client request won't name the case", "protected": True},
    {"id": "i485_t_u", "label": "I-485 based on T or U status", "matter_type": "I-485 adjustment based on T or U nonimmigrant status", "short": "I-485", "hint": "Custom research required; no bundled T/U adjustment checklist. Adjustment for a T or U nonimmigrant; the folder name and client request won't name the case", "protected": True},
]

FILING_POSTURES = [
    {"value": "new filing packet", "label": "New filing"},
    {"value": "RFE response", "label": "Response to an RFE"},
    {"value": "NOID response", "label": "Response to a NOID"},
    {"value": "interview supplement", "label": "Interview supplement"},
    {"value": "refile after denial", "label": "Refile after a denial"},
]

# One name per state: the pill, the card title and the matters list all use these.
PHASE_LABELS = {
    "new": "Needs documents",
    "ready": "Ready to build",
    "reviewed": "Documents reviewed",
    "building": "Claude is working",
    "paused": "Paused",
    "needs_you": "Needs your answer",
    "waiting_client": "Waiting on the client",
    "draft": "Draft packet",
    "complete": "Approved for filing",
    "filed": "Filed",
}


def catalog() -> dict[str, Any]:
    return {
        "matter_types": MATTER_TYPES,
        "filing_postures": FILING_POSTURES,
    }


def type_entry(value: str) -> dict[str, Any] | None:
    v = (value or "").strip().lower()
    for t in MATTER_TYPES:
        if v in {t["id"].lower(), t["matter_type"].lower(), t["label"].lower()}:
            return t
    return None


def posture_entry(value: str) -> dict[str, Any] | None:
    v = (value or "").strip().lower()
    for p in FILING_POSTURES:
        if v in {p["value"].lower(), p["label"].lower()}:
            return p
    return None

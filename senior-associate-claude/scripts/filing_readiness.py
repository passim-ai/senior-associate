"""Filing approval is an attorney action on an exact, reviewed set of bytes.

This is a local workflow safeguard, not an authentication boundary against a process
that can rewrite the matter folder. Never let an agent grant its own approval.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from scripts.matter_state import read_json, sha256_file, write_json_atomic, now_iso

APPROVAL = Path("output/working/workflow/filing-approval.json")
REVIEW_RECEIPT = Path("output/working/workflow/final-review-receipt.json")
MATERIAL = {"error", "blocker", "critical", "high", "major", "manual_review"}
ADVERSE = {"deny_likely", "noid_likely", "rfe_likely", "reject_likely", "attorney_hold"}
RESOLVED = {"resolved", "closed", "fixed", "cured"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv"}
SKIP_PREFIXES = ("output/tmp/", "output/privacy/", "output/working/earlier/", "output/working/workspaces/",
                 "output/working/workflow/snapshots/", "output/working/removed documents/",
                 "output/deliverables/Approved for filing/")
SKIP_PATHS = {str(APPROVAL), str(REVIEW_RECEIPT), "output/deliverables/filed.json"} | {
    "output/working/workflow/" + name for name in (".lock", "run-lease.json", "hash-cache.json", "events.jsonl")}


def fingerprint(matter: Path, *, review_inputs: bool = False) -> dict[str, str]:
    """Hash sources and substantive work, never activity logs or generated approval copies.

The review receipt excludes handoff text and ledgers, which are prepared after review.
The attorney approval includes them. Symlinks fail closed rather than hashing outside.
"""
    files: dict[str, str] = {}
    for parent, dirs, names in os.walk(matter, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")
                         and not ((Path(parent) / d).relative_to(matter).as_posix() + "/").startswith(SKIP_PREFIXES))
        for d in dirs:
            if (Path(parent) / d).is_symlink():
                raise ValueError("A linked folder cannot be included in a filing approval.")
        for name in sorted(names):
            if name == ".DS_Store" or name.startswith((".", "~$")):
                continue
            path = Path(parent) / name
            rel = path.relative_to(matter).as_posix()
            if rel in SKIP_PATHS:
                continue
            if review_inputs and ((rel.startswith("output/working/workflow/") and name not in {"legal currency review.json", "case_theory_evidence_map.json", "notice response plan.json", "attorney-instructions.md", "attorney-answers.json", "matter-meta.json"}) or
                                  "attorney-handoff/" in rel or name in {
                                      "open-items.json", "Attorney Memo.md", "Attorney Memo.pdf", "Client Request.md",
                                      "Client Request.pdf", "Filing Checklist.md", "Filing Checklist.pdf"}):
                continue
            if path.is_symlink():
                raise ValueError("A linked file cannot be included in a filing approval.")
            files[rel] = sha256_file(path)
    return files


def digest(files: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def record_review(matter: Path) -> None:
    write_json_atomic(matter / REVIEW_RECEIPT, {"reviewed_at": now_iso(), "files": fingerprint(matter, review_inputs=True)})


def review_problems(matter: Path, risks: list[str] | None = None) -> list[str]:
    risks = risks if risks is not None else []
    problems: list[str] = []
    roots = [matter / "output/working/vault", matter / "output/vault"]
    paths = sorted({p for root in roots if root.exists() for p in root.rglob("*findings.json")})
    final = [p for p in paths if p.name == "final review findings.json"]
    if len(final) != 1:
        problems.append("A single current final review is required before filing approval.")
    for path in paths:
        result = read_json(path)
        data = result.data
        if not result.ok or not isinstance(data, dict) or not isinstance(data.get("findings"), list):
            problems.append(f"The review record {path.name} is missing or damaged.")
            continue
        if path in final:
            outcome = data.get("overall_outcome")
            if outcome not in ADVERSE | {"approvable"}:
                problems.append("The final review has no recognized overall assessment.")
            elif outcome != "approvable":
                risks.append("Final review assessment: " + outcome.replace("_", " "))
        for finding in data["findings"]:
            if not isinstance(finding, dict):
                problems.append("A review finding is damaged.")
                continue
            if str(finding.get("status") or "").lower() in RESOLVED or finding.get("resolved") is True:
                continue
            if str(finding.get("severity") or "").lower() in MATERIAL or str(finding.get("outcome") or "").lower() in ADVERSE:
                risks.append(str(finding.get("title") or finding.get("summary") or "An unresolved material review finding remains."))
    receipt = read_json(matter / REVIEW_RECEIPT)
    if not receipt.ok or not isinstance(receipt.data, dict) or receipt.data.get("files") != fingerprint(matter, review_inputs=True):
        problems.append("The packet or its sources changed, or the final review has no content receipt. Run final review again.")
    return list(dict.fromkeys(problems))



def form_audit_problems(matter: Path) -> list[str]:
    """A reviewer or merits acknowledgment cannot excuse a deterministic form error."""
    forms = list((matter / "output/deliverables/Forms").glob("*.pdf"))
    audits = list((matter / "output/working/vault/forms").glob("*/prepared forms audit.json"))
    if forms and not audits:
        return ["Run the prepared-forms audit before filing approval."]
    problems: list[str] = []
    checked: set[str] = set()
    for path in audits:
        data = read_json(path).data
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            problems.append("The prepared-forms audit is damaged or incomplete.")
            continue
        for result in data["results"]:
            if not isinstance(result, dict) or not isinstance(result.get("findings"), list):
                problems.append("A prepared form lacks a complete audit result.")
                continue
            checked.add(Path(str(result.get("file") or "")).name)
            for finding in result["findings"]:
                if not isinstance(finding, dict):
                    problems.append("A form audit finding is damaged.")
                elif str(finding.get("severity") or "").lower() in MATERIAL:
                    problems.append("Form audit: " + str(finding.get("title") or "An unresolved form error remains."))
    for form in forms:
        if form.name not in checked:
            problems.append("The prepared-forms audit does not cover " + form.name + ".")
    return list(dict.fromkeys(problems))


def readiness(matter: Path, stages: list[dict[str, Any]], ledger: dict[str, Any] | None) -> dict[str, Any]:
    problems: list[str] = []
    risks: list[str] = []
    ids = {s["id"]: s["status"] for s in stages}
    if not stages or any(s["status"] != "passed" for s in stages) or any(ids.get(k) != "passed" for k in ("final_review", "attorney_handoff")):
        return {"eligible": False, "approved": False, "digest": "", "risks": [], "attorney": "", "approved_at": "",
                "blockers": ["Complete all required stages, including final review and the attorney handoff."]}
    if ledger is None or ledger.get("packet_status") != "ready_to_file":
        problems.append("The open-items record does not mark the packet ready for attorney approval.")
    if any(it.get("blocks_filing") for it in (ledger or {}).get("open", [])):
        problems.append("Items needed before filing remain open.")
    try:
        problems.extend(review_problems(matter, risks))
        problems.extend(form_audit_problems(matter))
        from scripts.draft_packets import release_sources
        try:
            release_sources(matter)
        except ValueError as exc:
            problems.append(str(exc))
        from scripts.legal_currency import currency_problems
        currency = read_json(matter / "output/working/workflow/legal currency review.json")
        problems.extend(currency_problems(currency.data))
        theory = read_json(matter / "output/working/workflow/case_theory_evidence_map.json")
        if not theory.ok or not isinstance(theory.data, dict) or not theory.data.get("reconciled_at") or not theory.data.get("eligibility_elements"):
            problems.append("Reconcile the case theory and evidence map to this filing before final review.")
        posture = str((theory.data or {}).get("filing_posture", "")) if isinstance(theory.data, dict) else ""
        if any(word in posture.lower() for word in ("rfe", "noid", "response")):
            from scripts.response_review import response_problems
            response = read_json(matter / "output/working/workflow/notice response plan.json")
            problems.extend(response_problems(matter, response.data))
        files = fingerprint(matter)
        packet_files = [p for p in files if p.startswith("output/deliverables/") and p.lower().endswith(".pdf")]
        if not packet_files:
            problems.append("There is no PDF deliverable to approve.")
        version = digest(files)
    except (OSError, ValueError) as exc:
        problems.append(str(exc))
        version = ""
    record = read_json(matter / APPROVAL)
    approved = bool(not problems and version and record.ok and isinstance(record.data, dict)
                    and record.data.get("digest") == version and record.data.get("attorney")
                    and (not risks or record.data.get("risk_note")))
    return {"eligible": not problems, "approved": approved, "digest": version,
            "blockers": list(dict.fromkeys(problems)), "risks": list(dict.fromkeys(risks)),
            "attorney": record.data.get("attorney", "") if approved else "",
            "approved_at": record.data.get("approved_at", "") if approved else ""}


def approve(matter: Path, *, expected_digest: str, attorney: str, stages: list[dict[str, Any]], ledger: dict[str, Any] | None, risk_note: str = "") -> None:
    current = readiness(matter, stages, ledger)
    if not attorney.strip():
        raise ValueError("Save the reviewing attorney's name in Your details first.")
    if not current["eligible"]:
        raise ValueError("Filing approval is blocked: " + " ".join(current["blockers"]))
    if not expected_digest or current["digest"] != expected_digest:
        raise ValueError("The matter changed since you opened it. Refresh and review the changes before approving.")
    if current["risks"] and not risk_note.strip():
        raise ValueError("Explain your decision to file with the listed review risks before approving this version.")
    from scripts.draft_packets import export_approved
    export_approved(matter, current["digest"])
    write_json_atomic(matter / APPROVAL, {"schema_version": 1, "attorney": attorney.strip(),
                                        "approved_at": now_iso(), "digest": current["digest"],
                                        "files": fingerprint(matter), "risks": current["risks"], "risk_note": risk_note.strip()})

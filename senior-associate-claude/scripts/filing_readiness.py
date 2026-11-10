"""Filing approval: the attorney's sign-off on one exact version of the packet.

The attorney can always approve an assembled packet. What stands in the way is said beside the button, in plain
words (`risks`), and approving with any of it open takes a written reason, which is kept with the approval. Only
two things make approval impossible (`blockers`): there is no assembled packet, or its clean copy is missing or
changed. Once a version is approved it stays approved until the packet or the client's documents change; a check
that ages afterwards (the research is a week old) never takes an approval back.

This is a local workflow safeguard, not an authentication boundary against a process that can rewrite the matter
folder. Never let an agent grant its own approval.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from scripts.generated_files import KEPT_DIR
from scripts.matter_state import read_json, sha256_file, write_json_atomic, now_iso

APPROVAL = Path("output/working/workflow/filing-approval.json")
REVIEW_RECEIPT = Path("output/working/workflow/final-review-receipt.json")
HASHES = Path("output/working/workflow/fingerprint-cache.json")
CURRENCY = Path("output/working/workflow/legal currency review.json")
THEORY = Path("output/working/workflow/case_theory_evidence_map.json")
RESPONSE_PLAN = Path("output/working/workflow/notice response plan.json")
MATERIAL = {"error", "blocker", "critical", "high", "major", "manual_review"}
# The same severities as the app words them on a review note (readmodel.SEVERITY_WORDS).
MATERIAL_WORDS = {"important", "worth fixing", "check by hand"}
ADVERSE = {"deny_likely", "noid_likely", "rfe_likely", "reject_likely", "attorney_hold"}
RESOLVED = {"resolved", "closed", "fixed", "cured"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv"}
DELIVERABLES = "output/deliverables"
FILING_SOURCE = "output/working/filing-source"
# Under the deliverables folder but not part of what is filed.
NOT_FILED_DIRS = {f"{DELIVERABLES}/Approved for filing", f"{DELIVERABLES}/{KEPT_DIR}"}
# What the handoff writes for the attorney after the final review: the memo, the client request (in any language),
# the filing checklist and the list of open items. They describe the packet; they aren't the packet.
HANDOFF_PREFIXES = ("Attorney Memo", "Client Request", "Filing Checklist")
HANDOFF_NAMES = {"open-items.json", "filed.json"}

LINKED = ("This matter holds a link to a file or folder kept somewhere else. Put the file itself in the matter, "
          "then try again.")
UNREADABLE = "Immigration Packet Builder couldn't read every file in this matter. Try again in a moment."
# How many of one kind of point are listed before the rest are counted.
LISTED = 6

OUTCOME_SAYS = {
    "reject_likely": "The officer's review expects USCIS to reject the filing at intake as it stands.",
    "deny_likely": "The officer's review expects a denial as it stands.",
    "noid_likely": "The officer's review expects a notice of intent to deny as it stands.",
    "rfe_likely": "The officer's review expects a request for evidence as it stands.",
    "attorney_hold": "The officer's review says to hold this for your decision.",
}


class _Hashes:
    """Each covered file's hash, kept while its size, its modified time and its change time stay the same, so the
    matter page's quiet refresh reads a file again only when it changed. The change time is the one a program can't
    set back, so new contents under an old date are still read. `fresh` reads every file whatever the cache says:
    a review receipt and an approval are taken from the files themselves."""

    def __init__(self, matter: Path, *, fresh: bool = False) -> None:
        self.matter = matter
        self.fresh = fresh
        data = read_json(matter / HASHES).data
        files = data.get("files") if isinstance(data, dict) and data.get("version") == 1 else None
        self.entries: dict[str, dict[str, Any]] = {k: v for k, v in (files or {}).items() if isinstance(v, dict)}
        self.dirty = False

    def sha(self, rel: str) -> str:
        path = self.matter / rel
        st = path.stat()
        seen = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "ctime_ns": st.st_ctime_ns}
        known = self.entries.get(rel)
        if not self.fresh and known and known.get("sha256") and all(known.get(key) == value for key, value in seen.items()):
            return str(known["sha256"])
        value = sha256_file(path)
        self.entries[rel] = {**seen, "sha256": value}
        self.dirty = True
        return value

    def save(self, present: set[str]) -> None:
        stale = set(self.entries) - present
        for rel in stale:
            del self.entries[rel]
        if not (self.dirty or stale) or not (self.matter / HASHES).parent.is_dir():
            return
        try:
            write_json_atomic(self.matter / HASHES, {"version": 1, "files": self.entries})
        except OSError:
            pass  # a cache that can't be written only means hashing again next time


def _covered_dir(rel: str) -> bool:
    if rel != "output" and not rel.startswith("output/"):
        return True  # the client's documents, wherever the attorney keeps them in the matter
    if rel in NOT_FILED_DIRS:
        return False
    return (rel in {"output", "output/working", DELIVERABLES, FILING_SOURCE}
            or rel.startswith((DELIVERABLES + "/", FILING_SOURCE + "/")))


def _covered_file(rel: str, name: str) -> bool:
    if not rel.startswith("output/"):
        return True
    if rel.startswith(FILING_SOURCE + "/"):
        return name != "release.json"
    if not rel.startswith(DELIVERABLES + "/"):
        return False
    at_top = rel == f"{DELIVERABLES}/{name}"
    return not (at_top and (name in HANDOFF_NAMES or name.startswith(HANDOFF_PREFIXES)))


def fingerprint(matter: Path, *, fresh: bool = False) -> dict[str, str]:
    """What a review or an approval covers: the client's documents and the files that are filed (the packet, the
    letter, the forms, the upload files, and the packet's clean copies).

    Claude's working files, the app's own records, the memo and the client request aren't part of it, so saving an
    answer, archiving the matter or cleaning up never undoes a review or an approval. A linked file or folder is
    refused rather than followed out of the matter."""
    cache = _Hashes(matter, fresh=fresh)
    files: dict[str, str] = {}
    for parent, dirs, names in os.walk(matter, followlinks=False):
        here = Path(parent).relative_to(matter).as_posix()
        here = "" if here == "." else here + "/"
        keep: list[str] = []
        for d in sorted(dirs):
            if d in SKIP_DIRS or d.startswith(".") or not _covered_dir(here + d):
                continue
            if (Path(parent) / d).is_symlink():
                raise ValueError(LINKED)
            keep.append(d)
        dirs[:] = keep
        for name in sorted(names):
            if name.startswith((".", "~$")) or not _covered_file(here + name, name):
                continue
            if (Path(parent) / name).is_symlink():
                raise ValueError(LINKED)
            files[here + name] = cache.sha(here + name)
    cache.save(set(files))
    return files


def _version(files: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """The client's documents by where they are, and Claude's files by what they hold: renaming the packet (the
    handoff drops "(DRAFT)" once nothing blocks filing) isn't a change to it."""
    documents = {rel: sha for rel, sha in files.items() if not rel.startswith("output/")}
    made = sorted(sha for rel, sha in files.items() if rel.startswith("output/"))
    return documents, made


def digest(files: dict[str, str]) -> str:
    documents, made = _version(files)
    return hashlib.sha256(json.dumps([documents, made], sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def record_review(matter: Path) -> None:
    """The final review passed on what the matter holds now. A matter that can't be read through (a linked folder)
    gets no receipt, and approval says why; passing the review itself is never refused for it."""
    try:
        files = fingerprint(matter, fresh=True)
    except (OSError, ValueError):
        (matter / REVIEW_RECEIPT).unlink(missing_ok=True)
        return
    write_json_atomic(matter / REVIEW_RECEIPT, {"reviewed_at": now_iso(), "files": files, "digest": digest(files)})


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _capped(lines: list[str], rest: str) -> list[str]:
    lines = list(dict.fromkeys(lines))
    if len(lines) <= LISTED:
        return lines
    return lines[:LISTED] + [f"…and {len(lines) - LISTED} more {rest}."]


def _findings_files(matter: Path) -> list[Path]:
    roots = [matter / "output/working/vault", matter / "output/vault"]
    return sorted({p for root in roots if root.exists() for p in root.rglob("*findings.json")})


def _review_points(matter: Path, notes: list[dict[str, Any]] | None, files: dict[str, str], reviewed: bool) -> list[str]:
    """What the reviews left open. `notes` are the open review notes as the app words them (readmodel.review_notes);
    without them the findings files are read as they are."""
    points: list[str] = []
    final = [p for p in _findings_files(matter) if p.name == "final review findings.json"]
    if not final:
        if reviewed:
            points.append("The final review's record is missing, so its notes aren't counted here.")
        return points
    newest = max(final, key=lambda p: p.stat().st_mtime)
    data = read_json(newest).data
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        points.append("The final review's record can't be read, so its notes aren't counted here.")
    elif str(data.get("overall_outcome") or "") in OUTCOME_SAYS:
        points.append(OUTCOME_SAYS[str(data["overall_outcome"])])
    if notes is not None:
        listed = [f"Review note: {n.get('title')}" for n in notes
                  if n.get("title") and (n.get("severity_word") in MATERIAL_WORDS or n.get("outcome_word"))]
    else:
        listed = []
        for path in _findings_files(matter):
            found = read_json(path).data
            for finding in (found.get("findings") if isinstance(found, dict) and isinstance(found.get("findings"), list) else []):
                if not isinstance(finding, dict):
                    continue
                if str(finding.get("status") or "").lower() in RESOLVED or finding.get("resolved") is True:
                    continue
                if str(finding.get("severity") or "").lower() in MATERIAL or str(finding.get("outcome") or "").lower() in ADVERSE:
                    listed.append("Review note: " + str(finding.get("title") or finding.get("summary") or "a reviewer flagged something."))
    points.extend(_capped(listed, "review notes on the Packet tab"))
    receipt = read_json(matter / REVIEW_RECEIPT).data
    covered = receipt.get("files") if isinstance(receipt, dict) else None
    if not isinstance(covered, dict) or _version(covered) != _version(files):
        points.append("The packet or the client's documents changed after the final review, so the review didn't "
                      "cover this exact version. Re-check as a USCIS officer would runs it again.")
    return points


def _on_the_list(ledger: dict[str, Any] | None) -> set[str]:
    """The open items an approval already accounts for: those counted as needed before filing, and those the
    attorney has settled."""
    if not isinstance(ledger, dict):
        return set()
    counted = [item for item in ledger.get("open") or [] if isinstance(item, dict) and item.get("blocks_filing")]
    settled = [item for item in ledger.get("resolved") or [] if isinstance(item, dict)]
    return {str(item.get("id")) for item in counted + settled if item.get("id")}


def _forms_points(matter: Path, ledger: dict[str, Any] | None = None) -> list[str]:
    """What the automatic check of the filled forms still reports. An error tied to an open item is left to that
    item only when the item is really on the list (counted as needed before filing, or settled by the attorney);
    a reference to an item nobody added hides nothing."""
    listed = _on_the_list(ledger)
    forms = sorted((matter / DELIVERABLES / "Forms").glob("*.pdf"))
    audits = sorted((matter / "output/working/vault/forms").glob("*/prepared forms audit.json"))
    if not forms:
        return []
    if not audits:
        return ["The filled forms haven't had their automatic check."]
    points: list[str] = []
    errors: list[str] = []
    checked: set[str] = set()
    for path in audits:
        data = read_json(path).data
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            points.append("The record of the automatic forms check can't be read.")
            continue
        found = list(data.get("findings") or []) if isinstance(data.get("findings"), list) else []
        for result in results:
            if not isinstance(result, dict):
                continue
            checked.add(Path(str(result.get("file") or "")).name)
            # An older record kept each form's findings with its result.
            found.extend(result.get("findings") or [] if isinstance(result.get("findings"), list) else [])
        for finding in found:
            if not isinstance(finding, dict) or str(finding.get("severity") or "").lower() != "error":
                continue
            if finding.get("open_item") and str(finding["open_item"]) in listed:
                continue
            form = str(finding.get("form") or "").upper()
            title = str(finding.get("title") or "an error remains")
            errors.append(f"Forms check{', ' + form if form else ''}: {title}.".replace("..", "."))
    points.extend(_capped(errors, "from the automatic forms check"))
    unchecked = [form.name for form in forms if form.name not in checked]
    if unchecked:
        points.append(f"The automatic forms check didn't cover {', '.join(unchecked[:4])}{' and others' if len(unchecked) > 4 else ''}.")
    return points


def _currency_point(matter: Path) -> str:
    from scripts.legal_currency import currency_problems
    record = read_json(matter / CURRENCY).data
    if not isinstance(record, dict):
        return "The check that the law the letter cites is still current wasn't recorded."
    problems = currency_problems(record)
    if not problems:
        return ""
    checked = str(record.get("checked_at") or "")[:10]
    if any("seven days" in problem for problem in problems):
        return ("The check that the law the letter cites is still current is more than a week old"
                + (f" (last done {checked})." if checked else "."))
    return "The check that the law the letter cites is still current is incomplete; the memo's Sources checked says what was covered."


def _response_points(matter: Path, posture: str) -> list[str]:
    theory = read_json(matter / THEORY).data
    posture = posture or (str(theory.get("filing_posture") or "") if isinstance(theory, dict) else "")
    if not any(word in posture.lower() for word in ("rfe", "noid", "response")):
        return []
    from scripts.response_review import response_problems
    return _capped([f"Response to the notice: {text}" for text in response_problems(matter, read_json(matter / RESPONSE_PLAN).data)],
                   "points on the response to the notice")


def _result(*, blockers: list[str] | None = None, risks: list[str] | None = None, version: str = "",
            record: dict[str, Any] | None = None) -> dict[str, Any]:
    record = record or {}
    return {"eligible": not blockers and bool(version), "approved": bool(record), "digest": version,
            "blockers": list(blockers or []), "risks": list(dict.fromkeys(risks or [])),
            "attorney": str(record.get("attorney") or ""), "approved_at": str(record.get("approved_at") or ""),
            "risk_note": str(record.get("risk_note") or "")}


def readiness(matter: Path, stages: list[dict[str, Any]], ledger: dict[str, Any] | None, *,
              notes: list[dict[str, Any]] | None = None, posture: str = "", fresh: bool = False) -> dict[str, Any]:
    """Where the packet stands for the attorney's sign-off: whether it can be approved, whether this exact version
    is, and what to weigh first. `fresh` reads every file again instead of trusting the cache."""
    from scripts.draft_packets import release_sources
    try:
        entries = release_sources(matter)
        files = fingerprint(matter, fresh=fresh)
    except ValueError as exc:
        return _result(blockers=[str(exc)])
    except OSError:
        return _result(blockers=[UNREADABLE])
    version = digest(files)
    approval = read_json(matter / APPROVAL).data
    if isinstance(approval, dict) and approval.get("digest") == version and approval.get("attorney"):
        # What was open when the attorney approved is on the record, with the reason given.
        return _result(version=version, record=approval, risks=[str(r) for r in approval.get("risks") or []])

    risks: list[str] = []
    unfinished = [str(s.get("label") or s.get("id")) for s in stages if s.get("status") not in ("passed", "skipped")]
    if not stages:
        risks.append("Claude's record of this matter's steps is missing.")
    elif unfinished:
        risks.append(f"Not every step has finished: {', '.join(unfinished)} still to do.")
    if ledger is None:
        risks.append("Claude's list of open items is missing or can't be read.")
    else:
        needed = sum(1 for item in ledger.get("open") or [] if isinstance(item, dict) and item.get("blocks_filing"))
        if needed:
            risks.append(f"{_count(needed, 'open item on Questions is', 'open items on Questions are')} marked needed before filing.")
        elif not unfinished and ledger.get("packet_status") not in (None, "", "ready_to_file"):
            risks.append("Claude's memo still calls this a draft packet; it says why.")
    reviewed = any(s.get("id") == "final_review" and s.get("status") == "passed" for s in stages)
    risks.extend(_review_points(matter, notes, files, reviewed))
    risks.extend(_forms_points(matter, ledger))
    currency = _currency_point(matter)
    if currency:
        risks.append(currency)
    risks.extend(_response_points(matter, posture))
    marked = sorted(Path(rel).name for rel, entry in entries.items() if files.get(rel) and files[rel] != entry.get("draft_sha256"))
    if marked:
        risks.append(f"{', '.join(marked)} was changed after Claude assembled it (marked up or saved again, perhaps). "
                     "The clean copies come from the packet as assembled, without those changes.")
    gone = sorted(Path(rel).name for rel in entries if rel not in files)
    if gone:
        risks.append(f"{', '.join(gone)} isn't in the matter's folder as Claude assembled it (renamed and changed, or "
                     "removed). Its clean copy is still part of what you approve, as assembled.")
    return _result(version=version, risks=risks)


def approve(matter: Path, *, expected_digest: str, attorney: str, stages: list[dict[str, Any]], ledger: dict[str, Any] | None,
            risk_note: str = "", notes: list[dict[str, Any]] | None = None, posture: str = "") -> None:
    # The approval is taken from the files themselves, never from what was remembered about them.
    current = readiness(matter, stages, ledger, notes=notes, posture=posture, fresh=True)
    if not attorney.strip():
        raise ValueError("Add the attorney's name in Your details first: the approval is recorded under it.")
    if not current["eligible"]:
        raise ValueError(" ".join(current["blockers"]) or UNREADABLE)
    if not expected_digest or current["digest"] != expected_digest:
        raise ValueError("The matter changed since this page was drawn. Look at what changed, then approve again.")
    if current["approved"]:
        return
    if current["risks"] and not risk_note.strip():
        raise ValueError("Explain your decision to file with these points open, then approve. Your reason is kept with the approval.")
    from scripts.draft_packets import export_approved
    export_approved(matter, current["digest"])
    write_json_atomic(matter / APPROVAL, {"schema_version": 2, "attorney": attorney.strip(),
                                        "approved_at": now_iso(), "digest": current["digest"],
                                        "files": fingerprint(matter), "risks": current["risks"], "risk_note": risk_note.strip()})

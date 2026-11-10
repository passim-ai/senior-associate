"""Synthetic byte fixtures for server/UI tests, never a real packet or legal review."""
from datetime import date
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.matter_state import write_json_atomic as write, sha256_file
from scripts.filing_readiness import record_review, approve, readiness


def approve_fixture(matter, stages, ledger, *, approved=True):
    draft=matter/'output/deliverables/Filing Packet.pdf'
    if not draft.exists():
        draft.parent.mkdir(parents=True,exist_ok=True);draft.write_bytes(b'%PDF synthetic server fixture')
    clean=matter/'output/working/filing-source/Filing Packet.pdf'
    clean.parent.mkdir(parents=True,exist_ok=True);clean.write_bytes(draft.read_bytes())
    write(matter/'output/working/filing-source/release.json',{'entries':{'output/deliverables/Filing Packet.pdf':{'source':'output/working/filing-source/Filing Packet.pdf','draft_sha256':sha256_file(draft),'clean_sha256':sha256_file(clean)}}})
    write(matter/'output/working/vault/final-review/main/final review findings.json',{'overall_outcome':'approvable','findings':[]})
    write(matter/'output/working/workflow/legal currency review.json',{'checked_at':date.today().isoformat(),'jurisdiction':{'forum':'USCIS','circuit':'none','basis':'synthetic'},'checks':[{'category':c,'status':'checked','source':'synthetic','hits':[]} for c in ('agency_policy','regulations','agency_decisions','controlling_circuit','adverse_treatment')],'unresolved':[]})
    write(matter/'output/working/workflow/case_theory_evidence_map.json',{'reconciled_at':'synthetic','eligibility_elements':['synthetic']})
    write(matter/"output/working/vault/forms/main/prepared forms audit.json", {"results":[{"file":f.name,"findings":[]} for f in (matter/"output/deliverables/Forms").glob("*.pdf")]})
    record_review(matter)
    # A packet that passed its reviews is ready to file; approving that version is the attorney's own next step.
    if approved:
        approve(matter,expected_digest=readiness(matter,stages,ledger)['digest'],attorney='Synthetic Attorney',stages=stages,ledger=ledger)

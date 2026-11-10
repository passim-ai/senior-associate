"""Deterministic integration fixture, never a claim of completed legal review."""
from datetime import date
from pathlib import Path
import json


def reviewed_packet(matter: Path, plugin: Path):
    import sys
    sys.path.insert(0, str(plugin))
    from scripts.draft_packets import keep_review_copy
    from scripts.filing_readiness import record_review
    from reportlab.pdfgen.canvas import Canvas
    def write(name, value):
        path=matter/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value))
    # The stage outputs are fixtures. Real assembly, readmodel, approval, export,
    # transports, and stale-content checks run against them.
    path=matter/'output/working/workflow/matter_status.json'
    data=json.loads(path.read_text())
    for stage in data['stages'].values():
        stage['status']='passed'
    path.write_text(json.dumps(data))
    write('output/deliverables/open-items.json',{'schema_version':2,'packet_status':'ready_to_file','items':[]})
    write('output/working/vault/final-review/main/final review findings.json',
          {'overall_outcome':'attorney_hold','findings':[{'severity':'critical','title':'Synthetic merits risk','summary':'Synthetic merits risk'}]})
    write('output/working/workflow/legal currency review.json',
          {'checked_at':date.today().isoformat(),'jurisdiction':{'forum':'USCIS','circuit':'ca5','basis':'synthetic residence'},
           'checks':[{'category':c,'status':'checked','source':'https://example.test/fictional-only','hits':[]}
                     for c in ('agency_policy','regulations','agency_decisions','controlling_circuit','adverse_treatment')],'unresolved':[]})
    write('output/working/workflow/case_theory_evidence_map.json',{'eligibility_elements':['synthetic identity'],'reconciled_at':date.today().isoformat()})
    packet=matter/'output/deliverables/Filing Packet (DRAFT).pdf'
    packet.parent.mkdir(parents=True,exist_ok=True)
    canvas=Canvas(str(packet));canvas.drawString(60,700,'FICTIONAL TEST ONLY - no legal review performed')
    canvas.bookmarkPage('test');canvas.addOutlineEntry('Synthetic evidence','test');canvas.showPage();canvas.save()
    keep_review_copy(matter,packet)
    record_review(matter)
    return packet

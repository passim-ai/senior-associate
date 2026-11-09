#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "reportlab>=4.0"]
# ///
"""Synthetic adversarial acceptance tests; no client data or live legal research."""
import json
from datetime import date, timedelta
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts/forms'), str(ROOT/'skills/senior-associate/scripts')]
from scripts import filing_readiness as fr
from scripts.draft_packets import keep_review_copy, export_approved, release_sources
from scripts.generated_files import check_generated, record_generated
from scripts.legal_currency import currency_problems
from scripts.response_review import response_problems
from scripts.matter_state import write_json_atomic as write, sha256_file
from scripts.privacy_terms import matter_privacy_terms
from answer_integrity import confirmed
from consistency import check_consistency
from audit_prepared_forms import Form
from forms_workflow import visible_value_present
from matter_workflow import intake_terms, expected_forms_from_intake
from pypdf import PdfReader, PdfWriter
from xfa_tools import check_font_coverage


def packet(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    writer=PdfWriter();writer.add_blank_page(width=612,height=792);writer.add_outline_item("Synthetic exhibit",0);writer.write(path)


def currency():
    return {'checked_at':date.today().isoformat(),'jurisdiction':{'forum':'USCIS','circuit':'ca5','basis':'residence'},
            'checks':[{'category':c,'status':'checked','source':'https://example.test/official','hits':[]} for c in
                      ('agency_policy','regulations','agency_decisions','controlling_circuit','adverse_treatment')],
            'unresolved':[]}


class FilingTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.m=Path(self.temp.name)
        self.p=self.m/'output/deliverables/Filing Packet (DRAFT).pdf';packet(self.p);keep_review_copy(self.m,self.p)
        self.final=self.m/'output/working/vault/final-review/main/final review findings.json'
        write(self.final,{'overall_outcome':'approvable','findings':[]})
        write(self.m/'output/working/workflow/legal currency review.json',currency())
        write(self.m/'output/working/workflow/case_theory_evidence_map.json',{'eligibility_elements':['identity'],'reconciled_at':'today'})
        self.stages=[{'id':s,'status':'passed'} for s in ('docs_review','forms_preparer','final_review','attorney_handoff')]
        self.ledger={'packet_status':'ready_to_file','open':[]}
        fr.record_review(self.m)
    def ready(self):return fr.readiness(self.m,self.stages,self.ledger)
    def approve(self,**kw):fr.approve(self.m,expected_digest=self.ready()['digest'],attorney='Synthetic Attorney',stages=self.stages,ledger=self.ledger,**kw)
    def test_completed_build_needs_explicit_approval_and_changed_source_invalidates(self):
        self.assertTrue(self.ready()['eligible']);self.assertFalse(self.ready()['approved']);self.approve()
        self.assertTrue(self.ready()['approved'])
        (self.m/'new evidence.txt').write_text('new evidence')
        self.assertFalse(self.ready()['approved']);self.assertFalse(self.ready()['eligible'])
    def test_missing_damaged_and_adverse_reviews(self):
        self.final.unlink();self.assertFalse(self.ready()['eligible'])
        write(self.final,[]);self.assertFalse(self.ready()['eligible'])
        for outcome in ('deny_likely','rfe_likely','attorney_hold'):
            write(self.final,{'overall_outcome':outcome,'findings':[{'severity':'critical','summary':'merits risk'}]})
            fr.record_review(self.m)
            self.assertTrue(self.ready()['eligible']);self.assertTrue(self.ready()['risks'])
            with self.assertRaises(ValueError):self.approve()
            self.approve(risk_note='Reviewed the risks and elect to file this version.')
            self.assertTrue(self.ready()['approved'])
    def test_form_audit_error_is_not_a_merits_risk_override(self):
        form=self.m/'output/deliverables/Forms/I-485.pdf';packet(form)
        audit=self.m/'output/working/vault/forms/main/prepared forms audit.json'
        write(audit,{'results':[{'file':str(form),'findings':[{'severity':'error','title':'Sensitive answer needs confirmation'}]}]})
        fr.record_review(self.m)
        self.assertFalse(self.ready()['eligible'])
        with self.assertRaises(ValueError):self.approve(risk_note='Accept all risks')
    def test_source_folder_named_earlier_is_still_bound(self):
        source=self.m/'earlier/source.txt';source.parent.mkdir();source.write_text('first')
        fr.record_review(self.m);self.approve();source.write_text('changed')
        self.assertFalse(self.ready()['approved'])
    def test_open_items_and_skipped_stage_block(self):
        self.ledger['open']=[{'blocks_filing':True}];self.assertFalse(self.ready()['eligible'])
        self.ledger['open']=[];self.stages[0]['status']='skipped';self.assertFalse(self.ready()['eligible'])
    def test_stale_page_digest_refused(self):
        old=self.ready()['digest'];(self.m/'new evidence.txt').write_text('changed');fr.record_review(self.m)
        with self.assertRaises(ValueError):fr.approve(self.m,expected_digest=old,attorney='Attorney',stages=self.stages,ledger=self.ledger)
    def test_draft_band_and_approved_export(self):
        draft=PdfReader(self.p).pages[0];self.assertEqual(float(draft.mediabox.height),812)
        self.assertIn('DRAFT',draft.extract_text())
        self.assertEqual(PdfReader(self.p).outline[0].title,"Synthetic exhibit")
        self.approve();folder=export_approved(self.m,self.ready()['digest'])
        clean=folder/'Filing Packet.pdf';self.assertEqual(float(PdfReader(clean).pages[0].mediabox.height),792)
        clean.write_bytes(b'attorney edited')
        with self.assertRaises(ValueError):export_approved(self.m,self.ready()['digest'])
    def test_tampered_release_and_symlink_are_blocked(self):
        self.p.write_bytes(b'changed')
        with self.assertRaises(ValueError):release_sources(self.m)
        (self.m/'linked').symlink_to('/tmp',target_is_directory=True)
        self.assertFalse(self.ready()['eligible'])


class IntegrityTests(unittest.TestCase):
    def test_unicode_does_not_silently_transliterate(self):
        for actual,expected in [('Yldz','Yıldız'),('Nguyn','Nguyễn'),('Nguyen','Nguyễn')]:
            self.assertFalse(visible_value_present(actual,expected))
        self.assertTrue(visible_value_present('Nguyễn','Nguyễn'))
    def test_font_coverage_stops_an_unsupported_name_before_writing(self):
        from reportlab.pdfgen.canvas import Canvas
        with TemporaryDirectory() as d:
            p=Path(d)/'form.pdf'
            c=Canvas(str(p));c.acroForm.textfield(name='name',x=10,y=700,width=200,height=20,fontName='Helvetica');c.showPage();c.save()
            reader=PdfReader(p)
            check_font_coverage(reader,{'name':'José'})
            with self.assertRaisesRegex(ValueError,'cannot safely render'):
                check_font_coverage(reader,{'name':'Nguyễn'})
    def test_same_subject_cross_form_names(self):
        own={'Pt1Line1_FamilyName':'Nguyễn','Pt1Line1_GivenName':'An'}
        other={'kind':'i-130','subject':'beneficiary','expected_fields':{'Pt4Line4a_FamilyName':'Nguyen','Pt4Line4b_GivenName':'An'}}
        form=Form('i-485',Path('synthetic.pdf'),own,manifest_entry={'subject':'beneficiary'},intent_manifest={'other':other})
        check_consistency(form)
        self.assertTrue(any("name differs" in f['title'] for f in form.findings))
        other['subject']='petitioner';form.findings.clear();check_consistency(form)
        self.assertFalse(any("name differs" in f['title'] for f in form.findings))
    def test_confirmation_is_dated_and_question_specific(self):
        q={'key':'criminal_history','fact_ids':['client']}
        fact={'source_kind':'client_confirmation','source':'signed intake page 4','confirmed_at':date.today().isoformat(),'value':'No','question_keys':['criminal_history']}
        self.assertTrue(confirmed(q,{'client':fact}))
        for mutation in ({'source_kind':'prior_prepared_form'},{'question_keys':['other']},{'confirmed_at':(date.today()+timedelta(days=1)).isoformat()},{'source':''}):
            self.assertFalse(confirmed(q,{'client':fact|mutation}))
    def test_short_common_names_remain_screened(self):
        with TemporaryDirectory() as d:
            m=Path(d);write(m/'output/working/vault/forms/main/form facts.json',{'facts':[{'key':'full_name','value':n} for n in ('Li Wu','Bo Ng','Grace Young')]})
            terms=matter_privacy_terms(m)
            self.assertTrue({'Li','Wu','Bo','Ng','Grace','Young'}<=set(terms['names']))
    def test_generated_word_pdf_edits_survive(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'letter.docx';p.write_bytes(b'generated');receipt=Path(d)/'receipt.json';record_generated([p],receipt)
            check_generated([p],receipt);p.write_bytes(b'attorney edits')
            with self.assertRaises(ValueError):check_generated([p],receipt)
            self.assertEqual(p.read_bytes(),b'attorney edits')
    def test_relationship_and_chronology_contradictions(self):
        f=Form('i-130',Path('synthetic.pdf'),{'Pt1Line1_Spouse':'Y','Pt1Line1_Child':'Y','Pt2Line8_DateofBirth':'12/31/2999','Pt2Line18_DateOfMarriage':'01/01/2000'})
        check_consistency(f);titles=[x['title'] for x in f.findings]
        self.assertTrue(any('more than one' in x for x in titles));self.assertTrue(any('future' in x for x in titles));self.assertTrue(any('predates birth' in x for x in titles))
    def test_waiver_theories_do_not_become_i751(self):
        for text,term in [('I-601A provisional waiver for a spouse','i601a'),('I-601 waiver','i601'),('I-612 waiver','i612'),('I-140 national interest waiver','niw')]:
            terms=intake_terms(text,'packet');self.assertIn(term,terms);self.assertNotIn('waiver',terms)
            self.assertNotIn('I-751',expected_forms_from_intake(text,'packet'))
    def test_currency_cannot_hide_unchecked_sources_or_treatment(self):
        good=currency();self.assertEqual(currency_problems(good),[])
        for mutation in ({'checks':[]},{'unresolved':['appeal status']},{'checked_at':'2000-01-01'}):self.assertTrue(currency_problems(good|mutation))
    def test_notice_deadline_evidence_and_mapping(self):
        with TemporaryDirectory() as d:
            m=Path(d);n=m/'notice.txt';n.write_text('Fictional notice, all pages')
            record={'notice':{'path':'notice.txt','sha256':sha256_file(n),'issued_at':'2026-11-01','all_pages_reviewed':True},'deadline':{'date':(date.today()+timedelta(days=10)).isoformat(),'source_quote':'respond by the printed date','source_page':1,'verified_by':'Attorney','verified_at':date.today().isoformat()},'delivery_method':'mail','delivery_destination':'notice address','grounds':[{'id':'1','notice_page':1,'request':'evidence','response':'attached','evidence':['exhibit A'],'status':'addressed'}],'unmapped_notice_requests':[]}
            self.assertEqual(response_problems(m,record),[])
            for mutation in ({'grounds':[]},{'deadline':{}},{'notice':[]},{'unmapped_notice_requests':['2']}):self.assertTrue(response_problems(m,record|mutation))
            n.write_text('changed');self.assertTrue(response_problems(m,record))

class OperationsTests(unittest.TestCase):
    def test_sleep_assertion_ends_when_the_existing_lease_ends(self):
        from scripts import keep_awake
        from scripts.matter_state import now_iso
        lease={'run_id':'test','heartbeat_at':now_iso(),'released_at':''}
        with patch.object(keep_awake.sys,'platform','darwin'), patch.object(keep_awake,'read_lease',side_effect=[lease,None]), patch.object(keep_awake.subprocess,'Popen') as popen, patch.object(keep_awake.time,'sleep'):
            keep_awake.watch(Path('/synthetic'), 'test')
            popen.assert_called_once()
            self.assertEqual(popen.call_args.args[0][-1],str(keep_awake.MAX_SECONDS))
            popen.return_value.terminate.assert_called_once()
    def test_staged_update_preserves_installed_code_and_records_failure(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('stage_update',ROOT/'skills/setup/scripts/stage_update.py')
        updater=importlib.util.module_from_spec(spec);spec.loader.exec_module(updater)
        with TemporaryDirectory() as d:
            parent=Path(d);installed=parent/'installed.txt';installed.write_text('original')
            def run(argv, **kwargs):
                if argv[:2]==['git','clone']:
                    (Path(argv[-1])/'senior-associate-claude').mkdir()
                from subprocess import CompletedProcess
                return CompletedProcess(argv,1 if argv[0]=='bash' else 0)
            with patch.object(updater.subprocess,'run',side_effect=run),patch.object(updater.subprocess,'check_output',return_value='a'*40):
                candidate=updater.stage(parent,'origin/main')
            self.assertEqual(installed.read_text(),'original')
            record=json.loads((candidate/'candidate-verification.json').read_text())
            self.assertEqual(record['status'],'failed');self.assertEqual(record['commit'],'a'*40)

if __name__=='__main__':unittest.main()

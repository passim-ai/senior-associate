#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "reportlab>=4.0"]
# ///
"""Synthetic adversarial acceptance tests; no client data or live legal research."""
import json
import os
from datetime import date, timedelta
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts/forms'), str(ROOT/'skills/senior-associate/scripts')]
from scripts import filing_readiness as fr
from scripts.draft_packets import keep_review_copy, export_approved, release_sources, retire_superseded
from scripts.generated_files import KEPT_DIR, kept_notice, preserve_edits, record_generated
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


def packet(path, pages=1):
    path.parent.mkdir(parents=True, exist_ok=True)
    writer=PdfWriter()
    for _ in range(pages):writer.add_blank_page(width=612,height=792)
    writer.add_outline_item("Synthetic exhibit",0);writer.write(path)


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
        ready=self.ready();self.assertTrue(ready['eligible']);self.assertFalse(ready['approved']);self.assertEqual(ready['risks'],[])
        self.approve();self.assertTrue(self.ready()['approved'])
        (self.m/'new evidence.txt').write_text('new evidence')
        after=self.ready();self.assertFalse(after['approved']);self.assertTrue(after['eligible'])
        self.assertTrue(any('changed after the final review' in r for r in after['risks']))
    def test_the_apps_own_records_never_undo_a_review_or_an_approval(self):
        self.approve();version=self.ready()['digest']
        write(self.m/'output/working/workflow/attorney-answers.json',{'answers':{'q':{'answer':'Yes'}}})
        write(self.m/'output/working/workflow/matter-meta.json',{'archived_at':'2026-11-09T00:00:00Z'})
        write(self.m/'output/security/closeout report.json',{'cleaned':True})
        write(self.m/'output/deliverables/open-items.json',{'packet_status':'ready_to_file','items':[]})
        (self.m/'output/deliverables/Attorney Memo.md').write_text('# Memo, rewritten')
        (self.m/'output/deliverables/Client Request (Spanish).md').write_text('Solicitud')
        after=self.ready();self.assertEqual(after['digest'],version);self.assertTrue(after['approved']);self.assertEqual(after['risks'],[])
    def test_missing_damaged_and_adverse_reviews_are_said_and_take_a_reason(self):
        self.final.unlink();missing=self.ready()
        self.assertTrue(missing['eligible']);self.assertTrue(any("final review's record is missing" in r for r in missing['risks']))
        with self.assertRaises(ValueError):self.approve()
        write(self.final,[]);self.assertTrue(any("can't be read" in r for r in self.ready()['risks']))
        for outcome,word in (('deny_likely','denial'),('rfe_likely','request for evidence'),('reject_likely','reject'),('attorney_hold','hold')):
            write(self.final,{'overall_outcome':outcome,'findings':[{'severity':'critical','summary':'merits risk'}]})
            fr.record_review(self.m)
            ready=self.ready();self.assertTrue(ready['eligible'])
            self.assertTrue(any(word in r for r in ready['risks']),ready['risks']);self.assertIn('Review note: merits risk',ready['risks'])
            with self.assertRaisesRegex(ValueError,'Explain your decision'):self.approve()
            self.approve(risk_note='Reviewed the risks and elect to file this version.')
            approved=self.ready();self.assertTrue(approved['approved']);self.assertEqual(approved['risk_note'],'Reviewed the risks and elect to file this version.')
            (self.m/'output/working/workflow/filing-approval.json').unlink()
    def test_form_check_errors_are_read_from_the_real_audit_and_take_a_reason(self):
        form=self.m/'output/deliverables/Forms/I-485.pdf';packet(form)
        audit=self.m/'output/working/vault/forms/main/prepared forms audit.json'
        # The audit's own shape: one result per form, the findings beside them (audit_prepared_forms.audit_manifest).
        write(audit,{'results':[{'form':'i-485','file':str(form),'finding_count':2}],'findings':[
            {'severity':'error','form':'i-485','file':str(form),'title':'Date of birth is after the filing date'},
            {'severity':'error','form':'i-485','file':str(form),'title':'I-94 number is missing','open_item':'doc-i94'},
            {'severity':'warning','form':'i-485','file':str(form),'title':'A long answer'}]})
        fr.record_review(self.m)
        checks=lambda:[r for r in self.ready()['risks'] if r.startswith('Forms check')]
        # The audit names an open item nobody added: the reference hides nothing.
        self.assertEqual(checks(),['Forms check, I-485: Date of birth is after the filing date.','Forms check, I-485: I-94 number is missing.'])
        # On the list but not counted as needed before filing: the error is still said here.
        self.ledger['open']=[{'id':'doc-i94','blocks_filing':False}];self.assertEqual(len(checks()),2)
        # Counted as needed before filing, or settled by the attorney: said once, there.
        self.ledger['open']=[{'id':'doc-i94','blocks_filing':True}]
        self.assertEqual(checks(),['Forms check, I-485: Date of birth is after the filing date.'])
        self.assertIn('1 open item on Questions is marked needed before filing.',self.ready()['risks'])
        self.ledger['open']=[];self.ledger['resolved']=[{'id':'doc-i94','blocks_filing':True}]
        ready=self.ready();self.assertTrue(ready['eligible'])
        self.assertEqual(checks(),['Forms check, I-485: Date of birth is after the filing date.'])
        with self.assertRaises(ValueError):self.approve()
        self.approve(risk_note='The date is corrected by hand on the printed form.');self.assertTrue(self.ready()['approved'])
    def test_a_clean_audit_covers_its_forms_and_an_unchecked_form_is_said(self):
        form=self.m/'output/deliverables/Forms/I-485.pdf';packet(form);other=self.m/'output/deliverables/Forms/G-28.pdf';packet(other)
        write(self.m/'output/working/vault/forms/main/prepared forms audit.json',{'results':[{'form':'i-485','file':str(form),'finding_count':0}],'findings':[]})
        fr.record_review(self.m)
        self.assertEqual([r for r in self.ready()['risks'] if 'forms check' in r],["The automatic forms check didn't cover G-28.pdf."])
    def test_source_folder_named_earlier_is_still_bound(self):
        source=self.m/'earlier/source.txt';source.parent.mkdir();source.write_text('first')
        fr.record_review(self.m);self.approve();source.write_text('changed')
        self.assertFalse(self.ready()['approved'])
    def test_open_items_and_unfinished_steps_are_said_not_refused(self):
        self.ledger['open']=[{'blocks_filing':True},{'blocks_filing':False}];ready=self.ready()
        self.assertTrue(ready['eligible']);self.assertIn('1 open item on Questions is marked needed before filing.',ready['risks'])
        self.ledger['open']=[];self.stages[1]['status']='pending'
        self.assertTrue(any(r.startswith('Not every step has finished: forms_preparer') for r in self.ready()['risks']))
        self.stages[1]['status']='skipped';self.assertEqual(self.ready()['risks'],[])
    def test_a_week_old_research_check_is_said_and_never_takes_an_approval_back(self):
        self.approve()
        old=currency()|{'checked_at':(date.today()-timedelta(days=30)).isoformat()}
        write(self.m/'output/working/workflow/legal currency review.json',old)
        self.assertTrue(self.ready()['approved'])
        (self.m/'output/working/workflow/filing-approval.json').unlink()
        self.assertTrue(any('more than a week old' in r for r in self.ready()['risks']))
    def test_stale_page_digest_refused(self):
        old=self.ready()['digest'];(self.m/'new evidence.txt').write_text('changed');fr.record_review(self.m)
        with self.assertRaises(ValueError):fr.approve(self.m,expected_digest=old,attorney='Attorney',stages=self.stages,ledger=self.ledger)
    def test_draft_band_and_approved_export(self):
        draft=PdfReader(self.p).pages[0];self.assertEqual(float(draft.mediabox.height),812)
        self.assertIn('DRAFT',draft.extract_text())
        self.assertEqual(PdfReader(self.p).outline[0].title,"Synthetic exhibit")
        self.approve();folder=export_approved(self.m,self.ready()['digest'])
        clean=folder/'Filing Packet.pdf';self.assertEqual(float(PdfReader(clean).pages[0].mediabox.height),792)
        # A copy the attorney completed or signed is left as it is, and opening the copies again is never refused.
        clean.write_bytes(b'attorney signed');export_approved(self.m,self.ready()['digest'])
        self.assertEqual(clean.read_bytes(),b'attorney signed')
    def test_a_renamed_packet_is_the_same_version_and_a_replaced_one_leaves_the_record(self):
        self.approve();version=self.ready()['digest']
        final=self.p.with_name('Filing Packet.pdf');self.p.rename(final)   # the handoff drops "(DRAFT)" once nothing blocks filing
        self.assertEqual(list(release_sources(self.m)),['output/deliverables/Filing Packet.pdf'])
        renamed=self.ready();self.assertTrue(renamed['approved']);self.assertEqual(renamed['digest'],version)
        packet(self.p);keep_review_copy(self.m,self.p);final.unlink()     # assembled again under the draft name
        self.assertEqual(list(release_sources(self.m)),['output/deliverables/Filing Packet (DRAFT).pdf'])
    def test_a_marked_up_review_copy_is_said_and_a_changed_clean_copy_or_a_link_blocks(self):
        self.p.write_bytes(b'marked up in Preview')
        ready=self.ready();self.assertTrue(ready['eligible']);self.assertTrue(any('was changed after Claude assembled it' in r for r in ready['risks']))
        clean=self.m/'output/working/filing-source/Filing Packet (DRAFT).pdf';clean.write_bytes(b'changed')
        with self.assertRaises(ValueError):release_sources(self.m)
        blocked=self.ready();self.assertFalse(blocked['eligible']);self.assertIn('Update the packet',blocked['blockers'][0])
        with self.assertRaises(ValueError):self.approve(risk_note='any reason')
    def test_a_renamed_then_marked_up_review_copy_still_approves_its_clean_packet(self):
        final=self.p.with_name('Filing Packet.pdf');self.p.rename(final)   # the handoff's rename
        final.write_bytes(b'annotated in Preview after the rename')        # neither its name nor its contents match now
        self.assertEqual(list(release_sources(self.m)),['output/deliverables/Filing Packet.pdf'])
        ready=self.ready();self.assertTrue(ready['eligible'],ready['blockers'])
        self.assertTrue(any('Filing Packet.pdf was changed after Claude assembled it' in r for r in ready['risks']),ready['risks'])
        with self.assertRaisesRegex(ValueError,'Explain your decision'):self.approve()
        self.approve(risk_note='My notes on the review copy are not for filing.')
        clean=export_approved(self.m,self.ready()['digest'])/'Filing Packet.pdf'
        self.assertEqual(float(PdfReader(clean).pages[0].mediabox.height),792)
        # Removed altogether: there is nothing in the folder to approve, and the page says what to do.
        final.unlink()
        gone=self.ready();self.assertFalse(gone['eligible']);self.assertIn("isn't in the matter's folder anymore",gone['blockers'][0])
    def test_a_split_filing_keeps_both_parts_and_each_assembly_retires_only_what_it_replaces(self):
        deliverables=self.m/'output/deliverables'
        both=['output/deliverables/Filing Packet (DRAFT).pdf','output/deliverables/Filing Packet (paper part) (DRAFT).pdf']
        def assemble(name,uploads=(),whole=False):
            made=[deliverables/name]+[deliverables/'Upload files'/u for u in uploads]
            # Each file its own length, as real ones are: a packet is told from another by what it holds.
            for path in made:packet(path,pages=len(path.name));keep_review_copy(self.m,path,part_of=made[0])
            retire_superseded(self.m,made[0],made,whole_filing=whole)
        # The online packet with its upload files, then the paper part: two assemblies, in either order.
        assemble('Filing Packet (DRAFT).pdf',['I-130.pdf','Evidence 1.pdf']);assemble('Filing Packet (paper part) (DRAFT).pdf')
        self.assertEqual(sorted(release_sources(self.m)),both+['output/deliverables/Upload files/Evidence 1.pdf','output/deliverables/Upload files/I-130.pdf'])
        assemble('Filing Packet (DRAFT).pdf',['I-130.pdf'])   # assembled again with one upload file fewer
        self.assertEqual(sorted(release_sources(self.m)),both+['output/deliverables/Upload files/I-130.pdf'])
        # The online packet under its filing name: its draft-named entry goes, though nobody removed that file.
        assemble('Filing Packet.pdf',['I-130.pdf'])
        self.assertTrue((deliverables/'Filing Packet (DRAFT).pdf').exists())
        self.assertEqual(sorted(release_sources(self.m)),['output/deliverables/Filing Packet (paper part) (DRAFT).pdf','output/deliverables/Filing Packet.pdf','output/deliverables/Upload files/I-130.pdf'])
        # A part removed from the folder is left out of what is approved, and the approval says so.
        fr.record_review(self.m);(deliverables/'Filing Packet (paper part) (DRAFT).pdf').unlink()
        ready=self.ready();self.assertTrue(ready['eligible'])
        self.assertTrue(any("Filing Packet (paper part) (DRAFT).pdf was assembled earlier and isn't in the matter's folder now" in r for r in ready['risks']),ready['risks'])
        # The fees tool says the filing isn't split any more: this packet is all of it, and nothing is said of the old part.
        assemble('Filing Packet.pdf',whole=True)
        self.assertEqual(list(release_sources(self.m)),['output/deliverables/Filing Packet.pdf'])
        self.assertFalse(any('assembled earlier' in r for r in self.ready()['risks']))
    def test_new_contents_under_an_old_date_are_read_and_an_approval_reads_every_file(self):
        doc=self.m/'passport scan.txt';doc.write_text('AAAA');fr.record_review(self.m);self.approve()
        self.assertTrue(self.ready()['approved'])
        before=doc.stat();doc.write_text('BBBB');os.utime(doc,ns=(before.st_atime_ns,before.st_mtime_ns))   # same size, same date
        self.assertEqual(doc.stat().st_mtime_ns,before.st_mtime_ns)
        self.assertFalse(self.ready()['approved'])
        # Whatever the cache has been made to say, a review receipt and an approval are taken from the files.
        fr.record_review(self.m);page=self.ready()['digest']
        doc.write_text('CCCC');now=doc.stat()
        cache=self.m/'output/working/workflow/fingerprint-cache.json';kept=json.loads(cache.read_text())
        kept['files']['passport scan.txt'].update(size=now.st_size,mtime_ns=now.st_mtime_ns,ctime_ns=now.st_ctime_ns)
        cache.write_text(json.dumps(kept))
        self.assertEqual(self.ready()['digest'],page)   # the page trusts its cache, as the quiet refresh must
        self.assertNotEqual(fr.readiness(self.m,self.stages,self.ledger,fresh=True)['digest'],page)
        with self.assertRaisesRegex(ValueError,'changed since this page was drawn'):
            fr.approve(self.m,expected_digest=page,attorney='Synthetic Attorney',stages=self.stages,ledger=self.ledger)
    def test_a_note_the_app_calls_worth_fixing_takes_a_reason_like_any_material_note(self):
        notes=[{'title':'The I-864 leaves out a household member','severity_word':'worth fixing','outcome_word':''},
               {'title':'A typo in the cover letter','severity_word':'minor','outcome_word':''}]
        ready=fr.readiness(self.m,self.stages,self.ledger,notes=notes)
        self.assertEqual([r for r in ready['risks'] if r.startswith('Review note')],['Review note: The I-864 leaves out a household member'])
        with self.assertRaisesRegex(ValueError,'Explain your decision'):
            fr.approve(self.m,expected_digest=ready['digest'],attorney='Synthetic Attorney',stages=self.stages,ledger=self.ledger,notes=notes)
    def test_a_linked_folder_blocks_and_nothing_assembled_says_so(self):
        (self.m/'linked').symlink_to('/tmp',target_is_directory=True)
        self.assertFalse(self.ready()['eligible']);self.assertIn('link',self.ready()['blockers'][0])
        fr.record_review(self.m)   # passing the final review is never refused for it; there is just no receipt
        self.assertFalse((self.m/'output/working/workflow/final-review-receipt.json').exists())
        with TemporaryDirectory() as d:
            self.assertEqual(fr.readiness(Path(d),[],None)['blockers'],["There's no assembled packet to approve yet. Build the packet first."])


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
    def test_an_unprintable_letter_becomes_the_attorneys_decision_in_the_build_and_the_audit(self):
        from reportlab.pdfgen.canvas import Canvas
        import build_forms
        from audit_prepared_forms import unprintable_findings
        with TemporaryDirectory() as d:
            blank=Path(d)/'blank.pdf';c=Canvas(str(blank))
            for i,name in enumerate(('FamilyName','City')):
                c.acroForm.textfield(name=name,x=10,y=700-30*i,width=200,height=20,fontName='Helvetica')
            c.showPage();c.save()
            job=build_forms.FormJob(name='I-130',plan_path=Path(d)/'I-130.plan.json',kind='i-130',mapping={'FamilyName':'Nguyễn','City':'Houston'})
            before=job.mapping_sha;build_forms.letters_gate(job,blank)
            self.assertEqual(job.mapping,{'City':'Houston'});self.assertNotEqual(job.mapping_sha,before)
            item=job.suggested_items[0]
            self.assertEqual((item['id'],item['type'],item['blocks_filing']),('forms-letters-i-130','attorney_decision',True))
            self.assertIn('ễ',item['title']);self.assertTrue(any('left blank' in w for w in job.warnings))
            found=unprintable_findings(kind='i-130',pdf_path=blank,manifest_entry={'unprintable_boxes':job.unprintable,'unprintable_open_item':item['id']})
            self.assertEqual((found[0]['open_item'],found[0]['fields']),(item['id'],['FamilyName']))
            self.assertEqual(unprintable_findings(kind='i-130',pdf_path=blank,manifest_entry={}),[])
            plain=build_forms.FormJob(name='I-130',plan_path=Path(d)/'x',kind='i-130',mapping={'FamilyName':'Garcia','City':'San José'})
            build_forms.letters_gate(plain,blank);self.assertEqual((plain.unprintable,plain.suggested_items),({},[]))
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
    def test_generated_word_pdf_edits_survive_and_never_block_a_rebuild(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'letter.docx';p.write_bytes(b'generated');receipt=Path(d)/'receipt.json';record_generated([p],receipt)
            self.assertEqual(preserve_edits([p],receipt),[]);self.assertTrue(p.exists())
            p.write_bytes(b'attorney edits');kept=preserve_edits([p],receipt)
            self.assertEqual(len(kept),1);self.assertEqual(kept[0].parent.name,KEPT_DIR);self.assertEqual(kept[0].read_bytes(),b'attorney edits')
            self.assertFalse(p.exists());self.assertIn('attorney_action',kept_notice(kept))
            # A file from before receipts were kept (a letter edited in Word under an earlier version, say), or one
            # whose receipt is gone or damaged: nobody can say it wasn't edited, so it is kept too, and the rebuild
            # goes on. Its name says what it is, and the notice asks rather than asserts.
            old=Path(d)/'older letter.docx';old.write_bytes(b'edited in Word under an earlier version')
            kept=preserve_edits([old],receipt)
            self.assertEqual(len(kept),1);self.assertFalse(old.exists())
            self.assertEqual(kept[0].parent.name,KEPT_DIR);self.assertIn('(earlier copy, ',kept[0].name)
            self.assertEqual(kept[0].read_bytes(),b'edited in Word under an earlier version')
            self.assertIn('asking whether the attorney had changed it',kept_notice(kept));self.assertIn('not needed before filing',kept_notice(kept))
            p.write_bytes(b'generated again');receipt.write_text('{ damaged')
            self.assertEqual(len(preserve_edits([p],receipt)),1);self.assertFalse(p.exists())
            # A new matter has nothing there yet: nothing is kept, and nothing is said.
            self.assertEqual(preserve_edits([Path(d)/'new letter.docx'],Path(d)/'none.json'),[]);self.assertEqual(kept_notice([]),'')
    def test_a_social_security_number_is_not_a_sensitive_answer(self):
        from answer_integrity import sensitive_question
        self.assertFalse(sensitive_question({'label':"Part 2, Item 3: Petitioner's U.S. Social Security Number, if any"},'i-130'))
        self.assertFalse(sensitive_question({'label':'Part 2, Item 13: Social Security number (SSN), if known'},'i-765'))
        self.assertTrue(sensitive_question({'label':'Part 9: national security and related grounds'},'i-601'))
        self.assertTrue(sensitive_question({'label':'Part 1, Item 20: Ever arrested, detained, charged'},'i-751'))
    def test_an_unprintable_letter_blanks_its_own_box_not_the_form(self):
        from reportlab.pdfgen.canvas import Canvas
        from xfa_tools import unprintable_boxes
        with TemporaryDirectory() as d:
            p=Path(d)/'form.pdf'
            c=Canvas(str(p))
            for i,name in enumerate(('FamilyName','GivenName','City')):
                c.acroForm.textfield(name=name,x=10,y=700-30*i,width=200,height=20,fontName='Helvetica')
            c.showPage();c.save()
            found=unprintable_boxes(p,{'FamilyName':'Nguyễn','GivenName':'José','City':'Houston','NoSuchBox':'Łódź'})
            self.assertEqual(list(found),['FamilyName']);self.assertIn('U+1EC5',found['FamilyName'])
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

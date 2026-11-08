import json,sqlite3,tempfile,time,unittest,subprocess
from pathlib import Path
from datetime import datetime,timedelta
from unittest.mock import Mock
from timesheet.store import Store
from timesheet.simple_setup import BUCKETS,ensure_buckets,preset_ids,finish_setup
from timesheet.automation_store import Repository
from timesheet.automation_worker import Engine
from timesheet.decision_policy import settings,DEFAULTS
from timesheet import simple_store
from timesheet.day_record import snapshot,bounds,pdf


class SimplicityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db');self.repo=Repository(self.store)
        self.now=int(time.time());self.day=datetime.fromtimestamp(self.now).date();self.start=bounds(self.day)[0]
        # Use yesterday so the isolated fixture works even just after midnight.
        self.day-=timedelta(days=1);self.base=bounds(self.day)[0]+9*3600
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def setup(self,**kw):
        config=finish_setup(self.store,list(BUCKETS),connected=True,now=self.now,**kw)
        config['since']=bounds(self.day)[0];self.repo.configure(config);self.ids=config['category_tasks'];return config
    def activity(self,app='Editor',state='active',start=None,end=None):
        with self.store.db:return self.store.db.execute('INSERT INTO activity(start,end,app,title,state,closed) VALUES(?,?,?,?,?,1)',(start or self.base,end or self.base+600,app,'PRIVATE TITLE /secret/file',state)).lastrowid
    def result(self,task=None):
        tid=task or self.ids[0];others=[x for x in self.ids if x!=tid]
        return dict(task=tid,probability=.99,none_probability=.004,alternatives=[(tid,.99)]+[(x,.002) for x in sorted(others)],personal=.01,enough_evidence=.99,work_kind='development',work_kind_probability=.95,model='jev-simple-test',usage={'input_tokens':100,'output_tokens':10})
    def test_presets_need_no_names_rates_or_user_text(self):
        ids=ensure_buckets(self.store,list(BUCKETS));self.assertEqual(len(ids),4)
        self.assertTrue(all(r['effective_rate'] is None for r in self.store.tasks()))
        self.assertEqual(set(preset_ids(self.store)),set(BUCKETS))
    def test_setup_does_not_adopt_or_change_same_named_user_project(self):
        original=self.store.quick_project('My day','Daily activities','Private task',12345)
        ids=ensure_buckets(self.store,list(BUCKETS))
        self.assertNotIn(original,ids);self.assertEqual(self.store.tasks()[0]['effective_rate'],12345)
    def test_repeated_setup_reuses_owned_categories_without_duplicates(self):
        first=ensure_buckets(self.store,list(BUCKETS));second=ensure_buckets(self.store,['create'])
        self.assertEqual(second,[first[0]]);self.assertEqual(len(self.store.tasks()),4)
    def test_invalid_choice_or_boolean_cannot_enable_automation(self):
        for keys in ([],['unknown'],['create','create']):
            with self.assertRaises(ValueError):finish_setup(self.store,keys,connected=True)
        with self.assertRaises(ValueError):finish_setup(self.store,['create'],connected='yes')
        self.assertEqual(self.repo.config()['mode'],'off')
    def test_local_only_mode_and_policy_are_explicit(self):
        finish_setup(self.store,['create'],connected=False,titles=False,remember=False)
        self.assertEqual(self.repo.config()['mode'],'off');self.assertEqual(self.store.get('capture_titles'),'0')
        self.assertEqual(self.store.get('simple_remember'),'0')
    def test_generic_payload_excludes_unrelated_project_names_and_raw_titles(self):
        self.store.quick_project('PRIVATE CLIENT','SECRET PROJECT','Secret task',5000)
        self.setup();aid=self.activity();activity=self.store.rows('SELECT * FROM activity WHERE id=?',(aid,))[0]
        context,reason=self.repo.context(activity);payload=json.dumps(context['network'])
        for sensitive in ('PRIVATE CLIENT','SECRET PROJECT','Secret task','PRIVATE TITLE','/secret/file'):self.assertNotIn(sensitive,payload)
        self.assertTrue(context['has_context']);self.assertEqual(len(context['network']['tasks']),4)
    def test_archived_or_edited_category_stops_generic_inference(self):
        self.setup();aid=self.activity()
        with self.store.db:self.store.db.execute('UPDATE tasks SET archived=1 WHERE id=?',(self.ids[0],))
        request=Mock();engine=Engine(self.store,request=request,key=lambda:'synthetic')
        self.assertEqual(engine.step(self.now),'idle');request.assert_not_called()
    def test_malformed_category_policy_fails_closed(self):
        for value in ([True],[0],[-1],[1,1],['1'],[{}]):
            self.assertEqual(settings(json.dumps({**DEFAULTS,'category_tasks':value}))['mode'],'off')
    def test_automatic_generic_category_is_nonbillable_draft_without_focus(self):
        self.setup();self.activity();request=Mock(return_value=self.result())
        self.assertEqual(Engine(self.store,request=request,key=lambda:'synthetic').step(self.now),'applied')
        entry=self.store.entries(self.base,self.base+600)[0]
        self.assertEqual((entry['billable'],entry['status'],entry['origin']),(0,'draft','jev'))
        self.assertIsNone(request.call_args.kwargs['focus'])
        self.store.undo();self.assertEqual(self.store.entries(self.base,self.base+600),[])
    def test_ambiguous_browser_still_needs_a_choice(self):
        self.setup();self.activity('Browser');value=self.result();value.update(task=None,probability=.6,none_probability=.6,alternatives=[(i,.1) for i in sorted(self.ids)])
        self.assertEqual(Engine(self.store,request=lambda *a,**kw:value,key=lambda:'synthetic').step(self.now),'exception')
        self.assertEqual(len(simple_store.review_items(self.store,self.day)),1)
    def test_pending_work_does_not_ask_a_duplicate_manual_question(self):
        self.setup();self.activity();self.repo.discover(self.now)
        self.assertEqual(simple_store.review_items(self.store,self.day),[])
    def test_manual_click_assignment_is_nonbillable_reversible_and_strict(self):
        self.setup();self.activity();item=simple_store.review_items(self.store,self.day)[0]
        simple_store.assign_manual(self.store,item['blocks'],self.ids[0]);entry=self.store.entries(self.base,self.base+600)[0]
        self.assertEqual(entry['billable'],0);self.assertIsNotNone(entry['activity_id'])
        self.store.undo();self.assertEqual(self.store.entries(self.base,self.base+600),[])
        self.store.add_entry(self.ids[1],self.base+100,self.base+200)
        with self.assertRaises(ValueError):simple_store.assign_manual(self.store,item['blocks'],self.ids[0])
        self.assertEqual(len(self.store.entries(self.base,self.base+600)),1)
    def test_skipping_preserves_record_but_removes_repeated_question(self):
        self.setup();self.activity();item=simple_store.review_items(self.store,self.day)[0]
        simple_store.skip_item(self.store,item);self.assertEqual(simple_store.review_items(self.store,self.day),[])
        self.assertEqual(snapshot(self.store,self.day)['unclassified'],600)
    def test_change_category_preserves_source_and_undo_not_financial_approval(self):
        self.setup();aid=self.activity();Engine(self.store,request=lambda *a,**kw:self.result(),key=lambda:'synthetic').step(self.now)
        entry=self.store.entries(self.base,self.base+600)[0]
        simple_store.change_category(self.store,entry['id'],self.ids[1],entry['revision'],remember=True)
        changed=self.store.entries(self.base,self.base+600)[0]
        self.assertEqual((changed['task_id'],changed['activity_id'],changed['billable'],changed['status']),(self.ids[1],aid,0,'draft'))
        self.assertEqual(len(self.store.rows('SELECT * FROM ai_examples')),1)
        with self.assertRaises(ValueError):simple_store.change_category(self.store,entry['id'],self.ids[2],entry['revision'])
        self.store.undo();self.assertEqual(self.store.entries(self.base,self.base+600)[0]['task_id'],self.ids[0])
    def test_day_record_clips_periods_and_separates_sources_gaps_and_privacy(self):
        self.setup();aid=self.activity();Engine(self.store,request=lambda *a,**kw:self.result(),key=lambda:'synthetic').step(self.now)
        self.activity('SECRET APP','excluded',start=self.base+600,end=self.base+900)
        self.activity('','unknown',start=self.base+900,end=self.base+1200)
        self.store.add_entry(self.ids[1],self.base+1500,self.base+1800,'PRIVATE DESCRIPTION',False)
        record=snapshot(self.store,self.day);text=json.dumps(record)
        self.assertEqual((record['active'],record['ai'],record['human'],record['gaps'],record['private']),(600,600,300,300,300))
        for private in ('SECRET APP','PRIVATE TITLE','PRIVATE DESCRIPTION','/secret/file'):self.assertNotIn(private,text)
        self.assertEqual([r['source'] for r in record['entries']],['AI category','Manual entry'])
    def test_snapshot_does_not_commit_existing_writer_transaction(self):
        self.setup()
        try:
            with self.store.db:
                self.store.db.execute('BEGIN IMMEDIATE');self.store.set('transaction','pending');snapshot(self.store,self.day)
                raise ValueError('rollback')
        except ValueError:pass
        self.assertEqual(self.store.get('transaction','absent'),'absent')
    def test_pdf_contains_factual_evidence_and_never_private_titles(self):
        self.setup();self.activity();record=snapshot(self.store,self.day);content=pdf(record)
        self.assertTrue(content.startswith(b'%PDF'))
        path=Path(self.tmp.name)/'day.pdf';path.write_bytes(content)
        text=subprocess.check_output(['pdftotext',str(path),'-'],text=True)
        self.assertIn('app activity',text);self.assertIn('Capture gaps',text);self.assertIn('not independent verification',text)
        self.assertIn('Editor',text);self.assertNotIn('PRIVATE TITLE',text)
        self.assertEqual(self.store.rows('SELECT * FROM reports'),[])

    def test_existing_client_rule_takes_priority_over_generic_categories(self):
        real=self.store.quick_project('Client','Project','Specific work',10000)
        self.setup();self.activity();rid=self.store.add_rule('Editor','',real)
        with self.store.db:self.store.db.execute('UPDATE rules SET created=? WHERE id=?',(self.base-1,rid))
        request=Mock();self.assertEqual(Engine(self.store,request=request,key=lambda:'synthetic').step(self.now),'idle');request.assert_not_called()
    def test_app_function_policy_does_not_claim_work_intent(self):
        self.setup();self.activity();value=self.result();value.update(personal=.9,enough_evidence=.88,probability=.95,none_probability=.044,alternatives=[(self.ids[0],.95)]+[(i,.002) for i in sorted(self.ids[1:])])
        self.assertEqual(Engine(self.store,request=lambda *a,**kw:value,key=lambda:'synthetic').step(self.now),'applied')
        record=snapshot(self.store,self.day);self.assertEqual(record['entries'][0]['source'],'AI category')
        from timesheet.decision_policy import route
        self.assertEqual(route(value,'automatic',has_context=True)[0],'exception')
    def test_generic_routing_still_rejects_weak_or_conflicting_evidence(self):
        from timesheet.decision_policy import route
        self.setup();value=self.result()
        for kwargs in ({'has_context':False},{'has_context':True}):
            result=dict(value,enough_evidence=.7)
            self.assertEqual(route(result,'automatic',application_categories=True,**kwargs)[0],'exception')
    def test_pdf_remains_multipage_and_preserves_unicode_category_names(self):
        self.setup();self.activity();record=snapshot(self.store,self.day)
        record['entries']=[dict(task='Résumé <planning> & design',start=self.base+i*60,end=self.base+(i+1)*60,source='Chosen by you') for i in range(160)]
        path=Path(self.tmp.name)/'long.pdf';path.write_bytes(pdf(record))
        info=subprocess.check_output(['pdfinfo',str(path)],text=True)
        pages=int(next(x.split(':')[1].strip() for x in info.splitlines() if x.startswith('Pages:')))
        self.assertGreater(pages,2)
        text=subprocess.check_output(['pdftotext',str(path),'-'],text=True)
        self.assertIn('Résumé <planning> & design',text)

    def test_recorded_synthetic_live_cases_keep_specialists_automatic_and_general_apps_uncertain(self):
        from timesheet.evaluate import evaluate
        cases=json.loads((Path(__file__).parent/'fixtures/jev_simple_heldout_recorded.json').read_text())
        result=evaluate(cases)
        self.assertEqual(result['metrics']['automated'],5)
        self.assertEqual(result['metrics']['correct_choices'],8)
        self.assertEqual(result['metrics']['exception_cases'],3)
        self.assertIn('does not measure live',result['evidence'])

    def test_setup_can_restore_changed_defaults_without_overwriting_old_work(self):
        self.setup();old=self.ids[0]
        with self.store.db:self.store.db.execute('UPDATE tasks SET name=? WHERE id=?',('My edited task',old))
        finish_setup(self.store,list(BUCKETS),connected=False)
        self.assertEqual(len(preset_ids(self.store)),4)
        self.assertEqual(self.store.db.execute('SELECT name FROM tasks WHERE id=?',(old,)).fetchone()[0],'My edited task')
        self.assertNotIn(old,preset_ids(self.store).values())


if __name__=='__main__':unittest.main()



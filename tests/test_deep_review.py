"""Adversarial regressions from the November product/code review; synthetic only."""
import copy,json,tempfile,time,unittest
from pathlib import Path
from datetime import datetime,timedelta
from unittest.mock import Mock
from timesheet.store import Store
from timesheet.simple_setup import finish_setup,BUCKETS
from timesheet.automation_store import Repository
from timesheet.automation_worker import Engine
from timesheet.decision_memory import remember,relevant
from timesheet.decision_context import canonical
from timesheet.automation_status import worker_state,summary,summary_text,explain_entry
from timesheet import day_organiser
from timesheet.evaluate import evaluate,compare


class DeepReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db')
        self.repo=Repository(self.store);self.now=int(time.time());self.base=self.now-2000
        self.config=finish_setup(self.store,list(BUCKETS),connected=True,local_types=False,now=self.base-86400)
        self.ids=self.config['category_tasks'];self.task=self.ids[0]
        with self.store.db:self.aid=self.store.db.execute("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,'Editor','active',1)",(self.base,self.base+300)).lastrowid
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def result(self):
        return dict(task=self.task,probability=.96,none_probability=.01,alternatives=[(i,.96 if i==self.task else .03/(len(self.ids)-1)) for i in self.ids],
            personal=.1,enough_evidence=.99,work_kind='development',model='jev-review-test',usage={'input_tokens':100,'output_tokens':10})
    def test_unknown_usage_survives_midnight_resume_and_reconfiguration(self):
        with self.store.db:self.store.db.execute("INSERT INTO ai_usage(job_id,at,outcome) VALUES(0,?,'unknown')",(self.now-86400,))
        self.repo.resume();self.repo.configure(self.config)
        self.assertEqual(self.repo.usage(self.now)['unknown'],1)
        request=Mock(return_value=self.result());engine=Engine(self.store,request=request,key=lambda:'fake')
        self.assertEqual(engine.step(self.now),'paused');request.assert_not_called()
        self.assertIn('unknown usage',self.store.get('ai_pause_reason'))
        self.repo.acknowledge_unknown_usage();self.assertEqual(self.repo.usage(self.now)['unknown'],0)
        self.assertEqual(engine.step(self.now),'applied');self.assertEqual(request.call_count,1)
    def test_daily_totals_exclude_other_days_and_future_records(self):
        with self.store.db:
            for at in (self.now-86400,self.now,self.now+86400):
                self.store.db.execute("INSERT INTO ai_usage(job_id,at,input_tokens,output_tokens,outcome) VALUES(0,?,100,1,'success')",(at,))
        self.assertEqual(self.repo.usage(self.now),dict(requests=1,tokens=100,unknown=0))
        value=summary(self.store,self.now);self.assertEqual((value['requests'],value['input_tokens']),(1,100))
    def test_scoped_memory_not_crowded_out_and_unicode_lookup(self):
        scope=canonical({'clues':[],'focus':None})
        with self.store.db:
            self.store.db.execute("UPDATE activity SET app='STRASSE' WHERE id=?",(self.aid,))
            remember(self.store,self.aid,'Straße',self.task,scope,1)
            for i in range(1005):remember(self.store,10000+i,'Unrelated',self.ids[1],scope,i+2)
        self.assertEqual(relevant(self.store,'STRASSE',self.ids,[],None),[dict(application='Straße',task=self.task)])
        self.assertEqual(relevant(self.store,'STRASSE',self.ids,[],self.task),[])
    def test_updated_correction_is_first_and_archived_targets_are_filtered(self):
        scope=canonical({'clues':[],'focus':None})
        with self.store.db:
            for i in range(10):
                aid=self.store.db.execute("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,'Editor','active',1)",(self.base-i*86400,self.base-i*86400+100)).lastrowid
                remember(self.store,aid,'Editor',self.ids[1],scope,i)
                if i==0:oldest=aid
            remember(self.store,oldest,'Editor',self.task,scope,100)
        examples=relevant(self.store,'editor',self.ids,[],None)
        self.assertEqual(len(examples),8);self.assertEqual(examples[0]['task'],self.task)
        self.assertTrue(all(r['task']==self.task for r in relevant(self.store,'Editor',[self.task],[],None)))
    def test_old_example_schema_migrates_without_losing_unicode_or_choices(self):
        with self.store.db:
            self.store.db.execute("UPDATE activity SET app='Straße' WHERE id=?",(self.aid,))
            self.store.db.execute('DROP TABLE ai_examples')
            self.store.db.execute('CREATE TABLE ai_examples(id INTEGER PRIMARY KEY,activity_id INTEGER UNIQUE,application TEXT,task_id INTEGER,at INTEGER,scope TEXT)')
            self.store.db.execute('INSERT INTO ai_examples VALUES(1,?,?,?,1,?)',(self.aid,'Straße',self.task,canonical({'clues':[],'focus':None})))
        Repository(self.store)
        self.assertEqual(relevant(self.store,'STRASSE',self.ids,[],None)[0]['task'],self.task)
    def test_repository_initialisation_does_not_commit_a_callers_transaction(self):
        with self.assertRaisesRegex(ValueError,'rollback'):
            with self.store.db:
                self.store.db.execute('BEGIN IMMEDIATE');self.store.set('half-written','secret')
                Repository(self.store);raise ValueError('rollback')
        self.assertEqual(self.store.get('half-written','absent'),'absent')
    def test_forgetting_examples_invalidates_inflight_jobs_and_cache(self):
        self.repo.discover(self.now);job=self.repo.claim(self.now)
        with self.store.db:self.store.db.execute("INSERT INTO ai_cache VALUES('key','{}',?)",(self.now+100,))
        self.repo.forget_examples()
        self.assertEqual(self.repo.complete(job,self.result()),'stale')
        self.assertEqual(self.store.rows('SELECT * FROM ai_cache'),[]);self.assertEqual(self.store.entries(0,self.now),[])
    def test_heartbeat_failure_clock_jump_and_recovery(self):
        self.assertEqual(worker_state(self.store,self.now),'not running')
        for value in ('corrupt',str(self.now-31),str(self.now+100)):
            self.store.set('ai_worker_seen',value);self.assertEqual(worker_state(self.store,self.now),'not running')
        self.store.set('ai_worker_seen',self.now);self.assertEqual(worker_state(self.store,self.now),'ready')
        self.store.set('ai_pause_reason','attention');self.assertEqual(worker_state(self.store,self.now),'paused')
    def test_status_does_not_disclose_activity_or_keys_or_write(self):
        before=self.store.db.total_changes
        text=summary_text(self.store,self.now)
        self.assertNotIn('Editor',text);self.assertNotIn('Daily activities',text)
        self.assertEqual(self.store.db.total_changes,before);self.assertIn('not AI accuracy',text)
    def test_entry_explanation_tracks_saved_decision_and_retention(self):
        Engine(self.store,request=lambda *a,**k:self.result(),key=lambda:'fake').step(self.now)
        eid=self.store.entries(0,self.now)[0]['id'];text=explain_entry(self.store,eid)
        self.assertIn('jev-review-test',text);self.assertIn('Broad app-activity estimate',text)
        self.assertNotIn('fake',text)
        with self.store.db:self.store.db.execute("UPDATE ai_jobs SET network='{}'")
        self.assertIn('no longer available',explain_entry(self.store,eid))
    def test_malformed_day_pass_fails_closed_without_crashing_worker(self):
        batch=day_organiser.request(self.store,datetime.fromtimestamp(self.base).date(),self.now)
        for change in ({'expires':'bad'},{'cursor':True},{'end':None},{'scanned':1},{'id':[]},{'start':batch['end']}):
            self.store.set('ai_day_pass',json.dumps(batch|change))
            self.assertIsNone(day_organiser.active(self.store,self.now));day_organiser.save(self.store,batch)
        for raw in ('[]','{bad','['*2000+'0'+']'*2000):
            self.store.set('ai_day_pass',raw);self.assertIsNone(day_organiser.active(self.store,self.now))
    def test_export_does_not_silently_subtract_an_omitted_live_timer(self):
        from timesheet.day_record import snapshot,digest_text
        day=datetime.fromtimestamp(self.base).date()
        self.store.start_timer(self.task,self.base)
        exported=snapshot(self.store,day,now=self.base+300)
        visible=snapshot(self.store,day,now=self.base+300,include_running=True)
        self.assertEqual(exported['unclassified'],300);self.assertEqual(visible['unclassified'],0)
        self.assertIn('current timer',digest_text(visible));self.assertNotIn('current timer',digest_text(exported))
    def test_undo_preview_cannot_undo_a_newer_background_change(self):
        self.store.add_entry(self.task,self.base,self.base+100,billable=False)
        preview=self.store.undo_preview()
        self.store.add_entry(self.task,self.base+100,self.base+200,billable=False)
        with self.assertRaisesRegex(ValueError,'newer change'):self.store.undo(expected_change=preview['id'])
        self.assertEqual(len(self.store.entries(0,self.now)),2)
        latest=self.store.undo_preview();self.store.undo(expected_change=latest['id'])
        self.assertEqual(len(self.store.entries(0,self.now)),1)
    def test_rule_explanation_retains_identity_without_copied_title_content(self):
        rid=self.store.add_rule('Editor','',self.task)
        with self.store.db:self.store.db.execute('UPDATE rules SET created=? WHERE id=?',(self.base-1,rid))
        self.assertEqual(self.store.apply_rules(self.now),1)
        eid=self.store.entries(0,self.now)[0]['id'];self.assertIn(f'Rule #{rid}',explain_entry(self.store,eid))
        with self.store.db:self.store.db.execute('DELETE FROM rules WHERE id=?',(rid,))
        self.assertIn(f'Rule #{rid}',explain_entry(self.store,eid))
        self.assertNotIn('title',set(self.store.rows('SELECT * FROM rule_assignments')[0].keys()))


class EvaluationReviewTests(unittest.TestCase):
    def cases(self):
        return json.loads((Path(__file__).parent/'fixtures/jev_simple_heldout_recorded.json').read_text())
    def test_replay_has_stable_identity_slices_and_model_metadata(self):
        cases=self.cases();cases[0]['slice']='specialist'
        result=evaluate(cases);self.assertEqual(result['schema_version'],1)
        self.assertEqual(result['slices']['specialist']['cases'],1);self.assertTrue(result['models'])
        self.assertEqual(compare(cases,copy.deepcopy(cases))['coverage_change'],0)
    def test_comparison_catches_newly_automated_wrong_choice(self):
        cases=self.cases();candidate=copy.deepcopy(cases)
        # Make a previously correct automatic decision wrong without changing its
        # input/label: swap the distribution and selected task to another option.
        first=next(c for c in candidate if c['result']['task'] is not None)
        decision=first['result'];original=decision['task'];other=next(i for i,_ in first['tasks'] if i!=original)
        probabilities=dict(decision['alternatives']);probabilities[original],probabilities[other]=probabilities[other],probabilities[original]
        decision['task']=other;decision['alternatives']=sorted(probabilities.items(),key=lambda x:(-x[1],x[0]))
        report=compare(cases,candidate);self.assertTrue(report['newly_wrong_automated_cases'])
        self.assertGreater(report['wrong_minutes_change'],0)
    def test_comparison_rejects_changed_labels_inputs_and_duplicate_ids(self):
        cases=self.cases();candidate=copy.deepcopy(cases);candidate[0]['seconds']+=1
        with self.assertRaises(ValueError):compare(cases,candidate)
        cases[0]['case_id']=cases[1]['case_id']='same'
        with self.assertRaises(ValueError):evaluate(cases)

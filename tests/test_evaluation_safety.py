"""Private template preflight and stale-contract regressions; no provider traffic."""
import hashlib,json,tempfile,unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock,patch
from timesheet.store import Store
from timesheet.simple_setup import BUCKETS,finish_setup
from timesheet.automation_store import Repository
from timesheet import jev
from timesheet.evaluate import validate_cases,evaluate,main
from timesheet.evaluation_template import build,save_new
from timesheet.day_record import bounds
from timesheet.decision_memory import remember
from timesheet.decision_context import canonical

class EvaluationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db';self.store=Store(self.path)
        self.day=date(2026,11,9);self.start=bounds(self.day)[0]+3600;self.now=self.start+3600
        self.config=finish_setup(self.store,list(BUCKETS),connected=True,local_types=False,now=self.start-86400)
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def activity(self,app,start=None,state='active'):
        start=self.start if start is None else start
        with self.store.db:return self.store.db.execute('INSERT INTO activity(start,end,app,title,state,closed,capture_version) VALUES(?,?,?,?,?,1,2)',(start,start+100,app,'SECRET WINDOW TITLE',state)).lastrowid
    def test_template_is_read_only_unlabelled_and_does_not_export_private_context(self):
        self.activity('Editor');self.activity('Private browser',self.start+200,'excluded');self.activity('Locked secret',self.start+400,'locked')
        self.store.quick_project('SECRET CLIENT','SECRET PROJECT')
        before=hashlib.sha256(self.path.read_bytes()).hexdigest()
        with patch('timesheet.jev.get_key',side_effect=AssertionError('no key')),patch('timesheet.jev.decide',side_effect=AssertionError('no request')):cases=build(self.path,self.day)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),before)
        self.assertEqual([r['applications'] for r in cases],[['Editor']]);self.assertEqual(cases[0]['seconds'],100)
        self.assertEqual(cases[0]['label_status'],'unlabelled');self.assertNotIn('SECRET',json.dumps(cases));self.assertNotIn('Private browser',json.dumps(cases))
        validate_cases(cases,require_labels=False)
        with self.assertRaisesRegex(ValueError,'Confirm every'):validate_cases(cases)
        request=Mock()
        with self.assertRaisesRegex(ValueError,'Confirm every'):evaluate(cases,live=True,request=request,key='fake')
        request.assert_not_called()
    def test_template_excludes_same_day_training_apps_and_current_privacy_choices(self):
        aid=self.activity('Editor');self.activity('Firefox',self.start+200);self.activity('Media',self.start+400)
        self.store.set('excluded_apps','Firefox')
        with self.store.db:remember(self.store,aid,'Editor',self.config['category_tasks'][0],canonical({'clues':[],'focus':None}),self.now)
        self.assertEqual([r['applications'] for r in build(self.path,self.day)],[['Media']])
    def test_unlabelled_cli_fails_before_key_and_new_file_is_private_no_overwrite(self):
        self.activity('Editor');cases=build(self.path,self.day);output=Path(self.tmp.name)/'cases.json';save_new(output,cases)
        self.assertEqual(output.stat().st_mode&0o777,0o600)
        with self.assertRaises(FileExistsError):save_new(output,[])
        key=Mock()
        with patch('sys.argv',['evaluate',str(output),'--live','--allow-paid-requests']),patch('timesheet.jev.get_key',key):
            with self.assertRaisesRegex(ValueError,'Confirm every'):main()
        key.assert_not_called()
    def test_contract_revision_invalidates_inflight_without_changing_old_entries(self):
        self.activity('Editor');repo=Repository(self.store);repo.discover(self.now);job=repo.claim(self.now)
        self.assertTrue(repo.fresh(job));self.assertEqual(job['request_version'],jev.REQUEST_VERSION)
        with patch('timesheet.automation_store.REQUEST_VERSION',jev.REQUEST_VERSION+1):self.assertFalse(repo.fresh(job))
        old=dict(job,request_version=0);self.assertFalse(repo.fresh(old));self.assertEqual(self.store.entries(0,self.now),[])
    def test_missing_database_is_not_created_and_bad_labels_have_no_requests(self):
        missing=Path(self.tmp.name)/'missing'
        with self.assertRaises(Exception):build(missing,self.day)
        self.assertFalse(missing.exists())
        self.activity('Editor');cases=build(self.path,self.day);cases[0]['label_status']='confirmed';cases[0]['expected_task']=999999
        request=Mock()
        with self.assertRaises(ValueError):evaluate(cases,live=True,request=request,key='fake')
        request.assert_not_called()

if __name__=='__main__':unittest.main()

class RetryMetadataTests(unittest.TestCase):
    def test_invalid_retry_timing_is_repaired_without_unlock_or_implicit_request(self):
        from timesheet.automation_worker import Engine
        import time
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'db');now=int(time.time())
            try:
                finish_setup(store,list(BUCKETS),connected=True,local_types=False,now=now-86400)
                key=Mock();request=Mock();engine=Engine(store,key=key,request=request)
                for invalid in ('broken','-1',str(now+86401)):
                    store.set('ai_backoff_until',invalid);self.assertEqual(engine.step(now),'paused')
                    self.assertEqual(store.get('ai_backoff_until'),'0');self.assertIn('Review usage',store.get('ai_pause_reason'))
                key.assert_not_called();request.assert_not_called();self.assertEqual(store.rows('SELECT * FROM ai_usage'),[])
                engine.repo.resume();store.set('ai_last_prune','invalid');self.assertEqual(engine.step(now),'idle')
                self.assertEqual(store.get('ai_last_prune'),str(now))
            finally:store.close()

class ScopedMemoryTests(unittest.TestCase):
    def test_forget_one_unicode_app_preserves_other_examples_and_saved_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'db')
            try:
                ids=finish_setup(store,list(BUCKETS),connected=False,local_types=False)['category_tasks'];repo=Repository(store)
                with store.db:
                    for i,app in enumerate(('Straße','Other app')):
                        aid=store.db.execute("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,?,'active',1)",(200+i*200,300+i*200,app)).lastrowid
                        remember(store,aid,app,ids[0],canonical({'clues':[],'focus':None}),1000)
                    store.db.execute("INSERT INTO ai_cache VALUES('key','{}',2000)")
                store.add_entry(ids[0],200,300,billable=False);repo.forget_examples('STRASSE')
                self.assertEqual([r['application'] for r in store.rows('SELECT application FROM ai_examples')],['Other app'])
                self.assertEqual(store.rows('SELECT * FROM ai_cache'),[]);self.assertEqual(len(store.entries(0,1000)),1)
            finally:store.close()

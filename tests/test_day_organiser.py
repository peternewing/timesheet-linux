"""Offline whole-day decisions: privacy, priorities, caching and human precedence."""
import json
import tempfile
import unittest
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import Mock
from timesheet.store import Store
from timesheet.automation_store import Repository
from timesheet.automation_worker import Engine
from timesheet.decision_policy import DEFAULTS,owner_token
from timesheet.simple_setup import finish_setup,preset_ids
from timesheet import day_organiser,simple_store
from timesheet.day_record import bounds
from timesheet.daily_choices import choose


class DayOrganiserTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db')
        self.now=int(datetime.now().replace(hour=15,minute=0,second=0,microsecond=0).timestamp())
        self.day=datetime.fromtimestamp(self.now).date()-timedelta(days=1);self.base=bounds(self.day)[0]+36000
        self.repo=Repository(self.store)
        # Same owned presets as the real no-typing setup, with synthetic policy.
        from timesheet.simple_setup import ensure_buckets,BUCKETS
        ids=ensure_buckets(self.store,list(BUCKETS));self.task=ids[0]
        self.repo.configure({**DEFAULTS,'mode':'automatic','consent_version':1,'owner':owner_token(),'since':self.base-86400,'category_tasks':ids})
        self.add(self.base,'Editor');self.add(self.base+3600,'Editor');self.add(self.base+7200,'Browser')
        tasks=sorted(ids);other=[i for i in tasks if i!=self.task]
        def answer(apps,tasks,key,**kw):
            unclear=apps==['Browser'];task=None if unclear else self.task
            probabilities=[(i,.1 if unclear else .01 if i!=task else .96) for i in sorted(ids)]
            probabilities.sort(key=lambda x:(-x[1],x[0]))
            return dict(task=task,probability=.6 if unclear else .96,none_probability=.6 if unclear else .01,
                alternatives=probabilities,personal=.1,enough_evidence=.3 if unclear else .99,work_kind='other',model='jev-test-1',usage={'input_tokens':100,'output_tokens':10})
        self.call=Mock(side_effect=answer);self.engine=Engine(self.store,request=self.call,key=lambda:'fake')
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def add(self,start,app):
        with self.store.db:return self.store.db.execute("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,?,'active',1)",(start,start+300,app)).lastrowid
    def drain(self):
        for _ in range(30):
            self.engine.step(self.now)
            if not day_organiser.active(self.store,self.now):return
        self.fail('Day did not finish')
    def test_whole_day_reuses_decision_and_only_uncertain_app_needs_review(self):
        batch=day_organiser.request(self.store,self.day,self.now);self.drain()
        self.assertEqual(self.call.call_count,2)
        self.assertEqual(len(self.store.entries(self.base,self.base+8000)),2)
        self.assertTrue(all(not r['billable'] and r['status']=='draft' for r in self.store.entries(self.base,self.base+8000)))
        self.assertEqual([r['app'] for r in simple_store.review_items(self.store,self.day)],['Browser'])
        self.assertEqual(day_organiser.progress(self.store,batch),{'waiting':0,'organised':2,'uncertain':1})
    def test_second_click_does_not_resend_uncertain_decision(self):
        day_organiser.request(self.store,self.day,self.now);self.drain()
        day_organiser.request(self.store,self.day,self.now);self.drain();self.assertEqual(self.call.call_count,2)
    def test_no_new_consent_or_wider_processing_period(self):
        old=self.store.get('ai_policy');day_organiser.request(self.store,self.day,self.now);self.assertEqual(self.store.get('ai_policy'),old)
        self.repo.configure({**self.repo.config(),'mode':'off'})
        self.assertIsNone(day_organiser.active(self.store,self.now))
        with self.assertRaises(ValueError):day_organiser.request(self.store,self.day,self.now)
        self.engine.step(self.now);self.call.assert_not_called()
    def test_limits_pause_batch_without_force_assigning(self):
        self.repo.configure({**self.repo.config(),'daily_requests':1});day_organiser.request(self.store,self.day,self.now)
        for _ in range(4):self.engine.step(self.now)
        self.assertEqual(self.call.call_count,1);self.assertTrue(self.store.get('ai_pause_reason'))
        self.assertEqual(len(self.store.entries(self.base,self.base+8000)),2)
    def test_selected_day_has_priority_over_older_queue(self):
        old=self.add(self.base-86400,'Older');self.repo.discover(self.now)
        day_organiser.request(self.store,self.day,self.now);self.engine.step(self.now)
        self.assertEqual(self.call.call_args.args[0],['Editor'])
        self.assertEqual(self.store.db.execute('SELECT state FROM ai_jobs WHERE activity_id=?',(old,)).fetchone()[0],'pending')
    def test_superseded_pass_cannot_overwrite_new_request(self):
        first=day_organiser.request(self.store,self.day,self.now);second=day_organiser.request(self.store,self.day,self.now)
        first['state']='done';day_organiser.save(self.store,first)
        self.assertEqual(day_organiser.active(self.store,self.now)['id'],second['id'])
    def test_expiry_and_future_retry_do_not_busy_loop(self):
        batch=day_organiser.request(self.store,self.day,self.now);self.repo.discover(self.now,batch=batch)
        with self.store.db:self.store.db.execute("UPDATE ai_jobs SET due=?",(self.now+30,))
        self.assertFalse(day_organiser.ready_to_work(self.store,self.now))
        self.assertIsNone(day_organiser.active(self.store,self.now+601))
    def test_direct_assign_can_replace_pending_jobs_and_preserves_human_choice(self):
        day_organiser.request(self.store,self.day,self.now);self.repo.discover(self.now)
        item=simple_store.activity_item(self.store,self.day,'Editor',self.now);self.assertEqual(len(item['blocks']),2)
        choose(self.store,item,self.task,now=self.now);self.drain()
        self.assertEqual(self.call.call_count,1);self.assertEqual(self.call.call_args.args[0],['Browser'])
        self.assertTrue(all(r['origin']=='assigned' for r in self.store.entries(self.base,self.base+4000)))
    def test_assign_can_correct_auto_only_app_day(self):
        day_organiser.request(self.store,self.day,self.now);self.drain()
        item=simple_store.activity_item(self.store,self.day,'Editor',self.now)
        self.assertEqual(len(item['blocks']),0);self.assertEqual(len(item['auto_entries']),2)
        other=next(i for i in preset_ids(self.store).values() if i!=self.task);choose(self.store,item,other,now=self.now)
        self.assertTrue(all(r['task_id']==other for r in self.store.entries(self.base,self.base+4000)))
        self.store.undo();self.assertTrue(all(r['task_id']==self.task for r in self.store.entries(self.base,self.base+4000)))

    def test_large_day_scans_multiple_bounded_pages(self):
        for offset in range(205):self.add(self.base+offset*10,'Editor')
        # Avoid overlapping synthetic observations: discovery itself is being
        # checked here, not allocation of impossible simultaneous foreground apps.
        batch=day_organiser.request(self.store,self.day,self.now)
        self.repo.discover(self.now,batch=batch);self.assertFalse(batch['scanned'])
        cursor=batch['cursor'];self.repo.discover(self.now,batch=batch)
        self.assertFalse(batch['scanned']);self.assertGreater(batch['cursor'],cursor)
        self.repo.discover(self.now,batch=batch);self.assertTrue(batch['scanned'])
    def test_suggestion_policy_is_not_promoted_by_day_button(self):
        self.repo.configure({**self.repo.config(),'mode':'suggest'})
        day_organiser.request(self.store,self.day,self.now);self.drain()
        self.assertEqual(self.store.entries(self.base,self.base+8000),[])
        self.assertEqual(len(simple_store.review_items(self.store,self.day)),2)
    def test_authorised_period_is_never_extended_to_older_day(self):
        self.repo.configure({**self.repo.config(),'since':self.base+7200})
        batch=day_organiser.request(self.store,self.day,self.now)
        self.assertEqual(batch['start'],self.base+7200);self.drain()
        self.assertEqual(self.call.call_count,1);self.assertEqual(self.call.call_args.args[0],['Browser'])
    def test_revocation_at_request_write_lock_wins(self):
        original=self.store.db
        other=Store(self.store.path) if hasattr(self.store,'path') else Store(Path(self.tmp.name)/'db')
        revoked=False
        class Connection:
            def __enter__(proxy):return original.__enter__()
            def __exit__(proxy,*args):return original.__exit__(*args)
            def execute(proxy,sql,*args):
                nonlocal revoked
                if sql=='BEGIN IMMEDIATE' and not revoked:
                    revoked=True;policy=self.repo.config();policy['mode']='off';other.set('ai_policy',json.dumps(policy))
                return original.execute(sql,*args)
            def __getattr__(proxy,name):return getattr(original,name)
        self.store.db=Connection()
        try:
            with self.assertRaises(ValueError):day_organiser.request(self.store,self.day,self.now)
            self.assertIsNone(day_organiser.active(self.store,self.now));self.call.assert_not_called()
        finally:self.store.db=original;other.close()

    def test_cross_midnight_observation_is_clipped_to_requested_day(self):
        midnight=bounds(self.day)[0]
        self.repo.configure({**self.repo.config(),'since':midnight-3600})
        with self.store.db:
            aid=self.store.db.execute("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,'Night editor','active',1)",(midnight-300,midnight+300)).lastrowid
        batch=day_organiser.request(self.store,self.day,self.now);self.repo.discover(self.now,batch=batch)
        job=self.store.db.execute('SELECT * FROM ai_jobs WHERE activity_id=?',(aid,)).fetchone()
        self.assertEqual((job['start'],job['end']),(midnight,midnight+300))

    def test_processing_one_day_does_not_hide_remaining_midnight_fragment(self):
        midnight=bounds(self.day)[0]
        self.repo.configure({**self.repo.config(),'since':midnight-3600})
        with self.store.db:
            aid=self.store.db.execute("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,'Editor','active',1)",(midnight-300,midnight+300)).lastrowid
        day_organiser.request(self.store,self.day,self.now);self.drain()
        self.store.set('ai_discover_after','0');self.repo.discover(self.now)
        remaining=self.store.db.execute("SELECT * FROM ai_jobs WHERE activity_id=? AND state='pending'",(aid,)).fetchone()
        self.assertIsNotNone(remaining);self.assertEqual((remaining['start'],remaining['end']),(midnight-300,midnight))

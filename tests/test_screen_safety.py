import hashlib,json,tempfile,time,unittest,random
from pathlib import Path
from datetime import datetime,date
from unittest.mock import Mock,patch
from timesheet.store import Store
from timesheet.day_record import bounds
from timesheet import screen_time,screen_spaces
from timesheet.review_metrics import Session,summary
from timesheet.diagnostics import database_health
from timesheet.automation_store import Repository
from timesheet.automation_worker import Engine
from timesheet.simple_setup import finish_setup,BUCKETS,preset_ids
from timesheet.decision_context import canonical
from timesheet.decision_memory import remember,relevant


class ScreenSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db';self.store=Store(self.path)
        self.day=date(2026,11,9);self.base=bounds(self.day)[0]+9*3600;self.now=self.base+3600
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def test_schedule_is_future_only_automatic_and_preserves_prior_schedules(self):
        screen_spaces.use_schedule(self.store,'weekdays_9_17',self.base)
        rows=screen_spaces.periods(self.store,self.base-3600,self.base+12*3600)
        self.assertEqual(rows[0]['space'],'unspecified')
        self.assertEqual(sum(r['end']-r['start'] for r in rows if r['space']=='work'),8*3600)
        before=screen_spaces.periods(self.store,self.base,self.base+12*3600)
        screen_spaces.use_schedule(self.store,'weekdays_10_18',self.base+86400)
        self.assertEqual(before,screen_spaces.periods(self.store,self.base,self.base+12*3600))
        self.assertEqual(self.store.entries(0,self.now),[])
    def test_manual_override_undo_restores_schedule_and_unsorted_is_explicit(self):
        screen_spaces.use_schedule(self.store,'weekdays_9_17',self.base)
        self.assertEqual(screen_spaces.effective_now(self.store,self.base+100)['space'],'work')
        change=screen_spaces.switch(self.store,'personal',self.base+100)
        self.assertEqual(screen_spaces.effective_now(self.store,self.base+200)['space'],'personal')
        screen_spaces.undo_switch(self.store,change)
        self.assertEqual(screen_spaces.effective_now(self.store,self.base+200)['space'],'work')
        screen_spaces.switch(self.store,'unspecified',self.base+300)
        self.assertEqual(screen_spaces.effective_now(self.store,self.base+400)['space'],'unspecified')
    def test_schedule_weekend_and_corrupt_preset_fail_closed(self):
        screen_spaces.use_schedule(self.store,'weekdays_9_17',self.base)
        saturday=self.base+5*86400
        self.assertTrue(all(r['space']=='personal' for r in screen_spaces.periods(self.store,saturday,saturday+3600)))
        with self.store.db:self.store.db.execute("UPDATE screen_space_schedules SET preset='invalid'")
        self.assertIsNone(screen_spaces.schedule(self.store));self.assertEqual(screen_spaces.effective_now(self.store,self.base+1)['space'],'unspecified')
    def test_filtered_zero_is_not_misreported_as_missing_recording(self):
        screen_spaces.switch(self.store,'personal',self.base)
        with self.store.db:self.store.db.execute("INSERT INTO activity(start,end,app,state) VALUES(?,?,'Game','active')",(self.base,self.base+300))
        value=screen_time.summary(self.store,self.day,self.now,space='work')
        self.assertTrue(value['has_observations']);self.assertEqual(value['screen_seconds'],0)
    def test_review_measurement_excludes_inactive_long_and_backward_gaps(self):
        clock=[0.0];meter=Session(self.store,clock=lambda:clock[0],now=self.base)
        meter.observe(True);clock[0]=1;meter.observe(True)
        clock[0]=2;meter.observe(False);clock[0]=100;meter.observe(True)
        clock[0]=101;meter.observe(True);clock[0]=-10;meter.observe(True)
        meter.answer('answered');meter.answer('stale');meter.finish(now=self.now)
        value=summary(self.store,self.day);self.assertEqual(value['active_ms'],2000)
        self.assertEqual((value['answered'],value['stale']),(1,1));self.assertNotIn('application',str(value))
    def test_database_health_is_read_only_and_content_free(self):
        self.store.quick_project('SECRET CLIENT','SECRET PROJECT');before=hashlib.sha256(self.path.read_bytes()).hexdigest()
        value=database_health(self.path,self.now)
        self.assertTrue(value['integrity_ok']);self.assertNotIn('SECRET',json.dumps(value));self.assertNotIn(str(self.path),json.dumps(value))
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),before)
        absent=Path(self.tmp.name)/'absent';self.assertEqual(database_health(absent)['status'],'unavailable');self.assertFalse(absent.exists())
    def test_future_collector_heartbeat_never_appears_healthy(self):
        self.store.set('capture_enabled','1')
        with self.store.db:self.store.db.execute("UPDATE runtime SET collector_seen=?,capture_status='active' WHERE id=1",(self.now+1000,))
        value=database_health(self.path,self.now);self.assertEqual(value['status'],'needs attention');self.assertIsNone(value['collector_seen_age_seconds'])
    def test_private_or_changed_source_cannot_be_retrieved_as_correction_context(self):
        finish_setup(self.store,list(BUCKETS),connected=True,local_types=False,now=self.base-86400);ids=preset_ids(self.store);scope=canonical({'clues':[],'focus':None})
        with self.store.db:aid=self.store.db.execute("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,'Editor','active',1)",(self.base,self.base+100)).lastrowid;remember(self.store,aid,'Editor',ids['create'],scope,self.now)
        self.assertEqual(len(relevant(self.store,'Editor',list(ids.values()),[],None)),1)
        with self.store.db:self.store.db.execute("UPDATE activity SET state='personal' WHERE id=?",(aid,))
        self.assertEqual(relevant(self.store,'Editor',list(ids.values()),[],None),[])
        with self.store.db:self.store.db.execute("UPDATE activity SET state='active',app='Other app' WHERE id=?",(aid,))
        self.assertEqual(relevant(self.store,'Editor',list(ids.values()),[],None),[])
    def test_one_fragmented_daily_choice_does_not_become_eight_votes(self):
        finish_setup(self.store,list(BUCKETS),connected=True,local_types=False,now=self.base-86400);ids=preset_ids(self.store);scope=canonical({'clues':[],'focus':None})
        with self.store.db:
            for i in range(12):
                aid=self.store.db.execute("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,'Editor','active',1)",(self.base+i*10,self.base+i*10+5)).lastrowid
                remember(self.store,aid,'Editor',ids['create'],scope,self.now+i)
        self.assertEqual(len(relevant(self.store,'Editor',list(ids.values()),[],None)),1)
    def test_profile_redefinition_clears_old_examples_but_keeps_entries(self):
        finish_setup(self.store,list(BUCKETS),connected=True,local_types=False,now=self.base-86400);repo=Repository(self.store);ids=preset_ids(self.store)
        with self.store.db:
            aid=self.store.db.execute("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,'Editor','active',1)",(self.base,self.base+100)).lastrowid
            remember(self.store,aid,'Editor',ids['create'],canonical({'clues':[],'focus':None}),self.now)
        self.store.add_entry(ids['create'],self.base,self.base+100,billable=False)
        repo.save_profile(ids['create'],'New explicit definition')
        self.assertEqual(self.store.rows('SELECT * FROM ai_examples'),[]);self.assertEqual(len(self.store.entries(0,self.now)),1)
    def test_usage_gate_does_not_unlock_a_key_when_blocked(self):
        finish_setup(self.store,list(BUCKETS),connected=True,local_types=False,now=self.base-86400)
        with self.store.db:
            self.store.db.execute("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,'Editor','active',1)",(self.base,self.base+100))
            self.store.db.execute("INSERT INTO ai_usage(job_id,at,outcome) VALUES(0,?,'unknown')",(self.base-86400,))
        key=Mock();request=Mock();self.assertEqual(Engine(self.store,key=key,request=request).step(self.now),'paused')
        key.assert_not_called();request.assert_not_called()
    def test_interval_union_matches_a_small_discrete_reference(self):
        rng=random.Random(20261109)
        for _ in range(100):
            rows=[]
            for i in range(12):
                start=rng.randrange(0,28);end=rng.randrange(start+1,31);state=rng.choice(['active','away','locked','excluded'])
                rows.append(dict(start=start,end=end,state=state,app='A' if i%2 else 'B'))
            actual=screen_time.periods(rows,0,30)
            for second in range(30):
                source=[r for r in rows if r['start']<=second<r['end']];result=[r for r in actual if r['start']<=second<r['end']]
                self.assertLessEqual(len(result),1)
                if not source:self.assertEqual(result,[]);continue
                expected=max(source,key=lambda r:screen_time.PRIORITY[r['state']])['state']
                if expected=='active' and len({r['app'] for r in source})>1:expected='unknown'
                self.assertEqual(result[0]['state'],expected)

class SpaceRefinementTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db');self.base=1794214800
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def test_schedule_clock_survives_travel_and_uses_dst_rules(self):
        import os
        with patch.dict(os.environ,TZ='Europe/London'):
            time.tzset();screen_spaces.use_schedule(self.store,'weekdays_9_17',self.base)
            start=int(datetime(2027,3,29,7).timestamp());end=start+12*3600
            expected=screen_spaces.periods(self.store,start,end)
        try:
            with patch.dict(os.environ,TZ='America/New_York'):
                time.tzset();self.assertEqual(screen_spaces.periods(self.store,start,end),expected)
                work=[r for r in expected if r['space']=='work'];self.assertEqual(work[0]['start'],start+2*3600);self.assertEqual(work[0]['end']-work[0]['start'],8*3600)
        finally:time.tzset()
    def test_random_finite_corrections_preserve_current_and_guard_undo(self):
        screen_spaces.switch(self.store,'personal',self.base)
        rng=random.Random(112026);reference=['personal']*100
        for _ in range(100):
            start=rng.randrange(0,99);end=rng.randrange(start+1,101);space=rng.choice(list(screen_spaces.SPACES))
            before=screen_spaces.periods(self.store,self.base,self.base+120)
            version=screen_spaces.revision(self.store)
            change=screen_spaces.label_period(self.store,self.base+start,self.base+end,space,expected_revision=version,now=self.base+100)
            after=screen_spaces.periods(self.store,self.base,self.base+120)
            actual=[next(r['space'] for r in after if r['start']<=self.base+i<r['end']) for i in range(100)]
            candidate=reference[:];candidate[start:end]=[space]*(end-start);self.assertEqual(actual,candidate)
            self.assertEqual(screen_spaces.effective_now(self.store,self.base+110)['space'],'personal')
            with self.assertRaises(ValueError):screen_spaces.label_period(self.store,self.base,self.base+1,'work',expected_revision=version,now=self.base+100)
            screen_spaces.undo_switch(self.store,change);self.assertEqual(screen_spaces.periods(self.store,self.base,self.base+120),before)
        self.assertEqual(self.store.entries(0,self.base+200),[])
    def test_corrupt_clock_rules_never_fall_back_to_current_timezone(self):
        screen_spaces.use_schedule(self.store,'weekdays_9_17',self.base)
        with self.store.db:self.store.db.execute("UPDATE screen_space_schedules SET zone='invalid'")
        self.assertTrue(all(r['space']=='unspecified' for r in screen_spaces.periods(self.store,self.base,self.base+100)))

    def test_manual_switch_cannot_cross_a_schedule_started_after_clock_rollback(self):
        screen_spaces.use_schedule(self.store,'weekdays_9_17',self.base)
        before=screen_spaces.revision(self.store)
        with self.assertRaisesRegex(ValueError,'clock moved backwards'):screen_spaces.switch(self.store,'personal',self.base-10)
        self.assertEqual(screen_spaces.revision(self.store),before);self.assertEqual(screen_spaces.current(self.store)['id'],None)

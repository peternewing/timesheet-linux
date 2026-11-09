"""Screen time is observed personal/work computer use, not time-entry totals."""
import os,tempfile,time,unittest
from datetime import datetime,date,timedelta
from pathlib import Path
from unittest.mock import patch
from timesheet.store import Store
from timesheet.day_record import bounds
from timesheet import screen_time,screen_spaces
from timesheet.automation_store import Repository


class ScreenTimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db')
        self.day=date(2026,11,9);self.base=bounds(self.day)[0]+9*3600;self.now=self.base+3600
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def add(self,a,z,app='Editor',state='active'):
        with self.store.db:return self.store.db.execute('INSERT INTO activity(start,end,app,title,state,closed) VALUES(?,?,?,?,?,1)',(a,z,app,'PRIVATE TITLE /private/file',state)).lastrowid
    def result(self,**kw):return screen_time.summary(self.store,self.day,self.now,**kw)
    def test_all_use_works_without_tasks_or_ai_or_key(self):
        self.add(self.base,self.base+600,'Game');self.add(self.base+600,self.base+900,'Browser')
        with patch('timesheet.jev.get_key',side_effect=AssertionError('key access')):r=self.result()
        self.assertEqual(r['screen_seconds'],900);self.assertEqual(r['apps'],[('Game',600),('Browser',300)])
        self.assertEqual((r['switches'],r['sessions'],r['longest_session']),(1,1,900));self.assertEqual(self.store.tasks(),[])
    def test_privacy_is_separate_from_personal_space(self):
        screen_spaces.switch(self.store,'personal',self.base)
        self.add(self.base,self.base+300,'Game');self.add(self.base+300,self.base+400,'SECRET APP','excluded')
        self.add(self.base+400,self.base+500,'SECRET APP','personal')
        r=self.result(space='personal')
        self.assertEqual((r['screen_seconds'],r['private_seconds']),(500,200));self.assertEqual(r['spaces'],{'personal':500})
        self.assertEqual(r['apps'],[('Game',300)]);self.assertNotIn('SECRET',str(r));self.assertNotIn('PRIVATE TITLE',str(r))
    def test_away_lock_and_gap_are_not_screen_time(self):
        for i,state in enumerate(('active','away','locked','unknown')):self.add(self.base+i*100,self.base+(i+1)*100,'App',state)
        r=self.result();self.assertEqual((r['screen_seconds'],r['away_seconds'],r['gap_seconds']),(100,200,100))
    def test_duplicate_observations_union_without_double_counting(self):
        self.add(self.base,self.base+600);self.add(self.base+100,self.base+400,'EDITOR')
        r=self.result();self.assertEqual(r['screen_seconds'],600);self.assertEqual(r['apps'][0][1],600)
    def test_conflicting_foreground_apps_become_unknown(self):
        self.add(self.base,self.base+600);self.add(self.base+100,self.base+400,'Browser')
        r=self.result();self.assertEqual((r['screen_seconds'],r['gap_seconds'],r['conflict_seconds']),(300,300,300))
    def test_privacy_takes_precedence_in_overlapping_evidence(self):
        self.add(self.base,self.base+600,'SECRET APP');self.add(self.base,self.base+600,'','excluded')
        r=self.result();self.assertEqual(r['private_seconds'],600);self.assertEqual(r['apps'],[])
    def test_spaces_clip_observations_without_changing_time_entries(self):
        self.add(self.base,self.base+600,'Browser')
        screen_spaces.switch(self.store,'personal',self.base+100);screen_spaces.switch(self.store,'work',self.base+400)
        self.assertEqual(self.result()['spaces'],{'unspecified':100,'personal':300,'work':200})
        self.assertEqual(self.result(space='work')['screen_seconds'],200);self.assertEqual(self.store.entries(0,self.now),[])
    def test_manual_entries_do_not_invent_screen_time(self):
        task=self.store.quick_project('Client','Project');self.store.add_entry(task,self.base,self.base+600)
        self.assertEqual(self.result()['screen_seconds'],0);self.assertFalse(self.result()['has_observations'])
    def test_live_observation_stops_at_last_durable_sample(self):
        self.add(self.base,self.base+100)
        self.assertEqual(self.result()['screen_seconds'],100)
    def test_streak_breaks_at_gaps_and_away(self):
        self.add(self.base,self.base+200);self.add(self.base+300,self.base+400)
        r=self.result();self.assertEqual((r['sessions'],r['longest_session']),(2,200))
    def test_week_distinguishes_no_recording_from_zero_and_matches_today_elapsed(self):
        self.add(self.base,self.base+600)
        old=self.base-7*86400;self.add(old,old+300);self.add(old+7200,old+7800)
        r=screen_time.week(self.store,self.day,self.now)
        self.assertEqual((r['total'],r['recorded_days'],r['average']),(600,1,600))
        self.assertEqual(r['previous_total'],300);self.assertIsNone(r['change_fraction'])
    def test_dst_days_have_real_23_or_25_hour_windows(self):
        previous=os.environ.get('TZ');os.environ['TZ']='Europe/London';time.tzset()
        try:
            for day,n in ((date(2026,3,29),23),(date(2026,10,25),25)):
                a,z=bounds(day);self.assertEqual(z-a,n*3600)
                r=screen_time.summary(self.store,day,z);self.assertEqual(len(r['hourly']),n)
                labels=[h['label'] for h in r['hourly']];self.assertEqual(len(set(labels)),n)
        finally:
            if previous is None:os.environ.pop('TZ',None)
            else:os.environ['TZ']=previous
            time.tzset()
    def test_space_switch_is_local_intent_and_undoable(self):
        repo=Repository(self.store);policy=repo.config();first=screen_spaces.switch(self.store,'personal',self.base)
        second=screen_spaces.switch(self.store,'work',self.base+100)
        self.assertEqual(repo.config(),policy);self.assertEqual(screen_spaces.current(self.store)['space'],'work')
        with self.assertRaises(ValueError):screen_spaces.undo_switch(self.store,first)
        screen_spaces.undo_switch(self.store,second);self.assertEqual(screen_spaces.current(self.store)['space'],'personal')
    def test_same_instant_switch_and_clock_rollback_are_safe(self):
        screen_spaces.switch(self.store,'personal',self.base);change=screen_spaces.switch(self.store,'work',self.base)
        self.assertEqual(len(self.store.rows('SELECT * FROM screen_spaces')),1)
        with self.assertRaises(ValueError):screen_spaces.switch(self.store,'personal',self.base-1)
        screen_spaces.undo_switch(self.store,change);self.assertEqual(screen_spaces.current(self.store)['space'],'personal')
    def test_read_helpers_preserve_callers_transaction(self):
        with self.assertRaises(ValueError):
            with self.store.db:
                self.store.db.execute('BEGIN IMMEDIATE');self.store.set('rollback','pending');self.result();screen_time.week(self.store,self.day,self.now)
                raise ValueError()
        self.assertEqual(self.store.get('rollback','absent'),'absent')

class WeeklyEvidenceTests(unittest.TestCase):
    def test_capture_gaps_or_paused_observations_never_become_a_percentage_usage_reduction(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'db');day=date(2026,11,9);now=bounds(day)[1]
            try:
                with store.db:
                    for offset in range(14):
                        start=bounds(day-timedelta(days=offset))[0]
                        store.db.execute("INSERT INTO activity(start,end,app,state,capture_version) VALUES(?,?,'Editor','active',2)",(start,start+100))
                self.assertIsNotNone(screen_time.week(store,day,now)['change_fraction'])
                with store.db:store.db.execute("UPDATE activity SET app='',state='unknown' WHERE start=?",(bounds(day)[0],))
                self.assertIsNone(screen_time.week(store,day,now)['change_fraction'])
                with store.db:store.db.execute("UPDATE activity SET state='paused' WHERE start=?",(bounds(day)[0],))
                self.assertIsNone(screen_time.week(store,day,now)['change_fraction'])
                self.assertEqual(screen_time.summary(store,day,now)['screen_seconds'],0)
            finally:store.close()

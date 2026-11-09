import tempfile,time,unittest
from pathlib import Path
from datetime import datetime,timedelta
from unittest.mock import Mock
from timesheet.store import Store
from timesheet.automation_store import Repository
from timesheet.automation_worker import Engine
from timesheet.simple_setup import BUCKETS,finish_setup
from timesheet.simple_store import review_items
from timesheet.daily_choices import choose,choice,apply_saved
from timesheet.day_record import bounds,snapshot


class DailyChoicesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db');self.repo=Repository(self.store)
        self.now=int(time.time());self.day=datetime.fromtimestamp(self.now).date()-timedelta(days=2);self.base=bounds(self.day)[0]+9*3600
        self.config=finish_setup(self.store,list(BUCKETS),connected=True,local_types=False,now=self.now);self.config['since']=bounds(self.day)[0];self.repo.configure(self.config);self.ids=self.config['category_tasks']
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def activity(self,offset=0,app='Firefox',seconds=600,state='active',closed=1):
        with self.store.db:return self.store.db.execute('INSERT INTO activity(start,end,app,title,state,closed) VALUES(?,?,?,?,?,?)',(self.base+offset,self.base+offset+seconds,app,'Private title '+str(offset),state,closed)).lastrowid
    def test_one_day_groups_nonadjacent_casefolded_apps_and_excludes_private_states(self):
        self.activity();self.activity(7200,'fireFOX');self.activity(1200,'Editor');self.activity(3000,'Firefox',state='personal');self.activity(4000,'Firefox',state='excluded');self.activity(86400,'Firefox')
        items=review_items(self.store,self.day)
        self.assertEqual(len(items),2);self.assertEqual((items[0]['app_key'],items[0]['seconds'],len(items[0]['blocks'])),('firefox',1200,2))
    def test_one_choice_assigns_real_periods_once_and_one_undo_revokes_day_rule(self):
        self.activity();self.activity(7200);item=review_items(self.store,self.day)[0]
        self.assertEqual(choose(self.store,item,self.ids[0],remember=True),2)
        rows=self.store.entries(self.base,self.base+8000);self.assertEqual(sum(r['end']-r['start'] for r in rows),1200)
        self.assertTrue(all(r['billable']==0 and r['status']=='draft' for r in rows));self.assertEqual(len(self.store.rows('SELECT * FROM ai_examples')),2)
        self.assertEqual(review_items(self.store,self.day),[])
        self.store.undo();self.assertIsNone(choice(self.store,self.day,'FIREFOX'));self.assertEqual(apply_saved(self.store,self.now),0)
        self.assertEqual(len(review_items(self.store,self.day)),1)
    def test_later_activity_uses_saved_choice_without_network_and_not_on_other_day(self):
        self.activity();choose(self.store,review_items(self.store,self.day)[0],self.ids[1]);self.activity(7200);self.activity(86400)
        self.assertEqual(apply_saved(self.store,self.now),1);self.assertEqual(apply_saved(self.store,self.now),0)
        self.assertEqual(len(self.store.entries(self.base,self.base+8000)),2)
        self.assertEqual(len(review_items(self.store,self.day+timedelta(days=1))),1)
    def test_continuation_is_bounded_and_finishes_remaining_periods(self):
        self.activity();choose(self.store,review_items(self.store,self.day)[0],self.ids[0])
        for i in range(205):self.activity(7200+i*2,seconds=1)
        self.assertEqual(apply_saved(self.store,self.now),200);self.assertEqual(apply_saved(self.store,self.now),5);self.assertEqual(apply_saved(self.store,self.now),0)
    def test_skip_is_one_daily_decision_but_never_deletes_evidence(self):
        self.activity();choose(self.store,review_items(self.store,self.day)[0],None);self.activity(7200)
        self.assertEqual(review_items(self.store,self.day),[]);self.assertEqual(snapshot(self.store,self.day)['unclassified'],1200)
        request=Mock();self.assertEqual(Engine(self.store,request=request,key=lambda:'fake').step(self.now),'idle');request.assert_not_called()
        self.store.undo();self.assertEqual(len(review_items(self.store,self.day)),1)
    def test_daily_answer_replaces_ai_estimates_but_undo_restores_them(self):
        aid=self.activity()
        with self.store.db:self.store.db.execute("INSERT INTO entries(task_id,start,end,description,billable,origin,activity_id) VALUES(?,?,?,'AI estimate',0,'jev',?)",(self.ids[0],self.base,self.base+600,aid))
        self.activity(7200);item=review_items(self.store,self.day)[0]
        self.assertEqual(len(item['auto_entries']),1);self.assertEqual(item['seconds'],1200)
        choose(self.store,item,self.ids[1]);self.assertTrue(all(e['task_id']==self.ids[1] for e in self.store.entries(self.base,self.base+8000)))
        self.store.undo();rows=self.store.entries(self.base,self.base+8000);self.assertEqual(len(rows),1);self.assertEqual((rows[0]['origin'],rows[0]['task_id']),('jev',self.ids[0]))
    def test_new_manual_assignment_makes_frozen_group_atomic_and_stale(self):
        self.activity();self.activity(7200);item=review_items(self.store,self.day)[0]
        self.store.add_entry(self.ids[2],self.base+7200,self.base+7500,'Explicit work',False)
        with self.assertRaises(ValueError):choose(self.store,item,self.ids[0])
        self.assertIsNone(choice(self.store,self.day,'Firefox'));self.assertEqual(len(self.store.entries(self.base,self.base+8000)),1)
    def test_existing_explicit_assignments_are_preserved(self):
        self.activity();self.activity(7200);eid=self.store.add_entry(self.ids[2],self.base,self.base+300,'Keep this',False)
        choose(self.store,review_items(self.store,self.day)[0],self.ids[0])
        self.assertEqual(self.store.db.execute('SELECT description,task_id FROM entries WHERE id=?',(eid,)).fetchone()[:],('Keep this',self.ids[2]))
        self.assertEqual(sum(r['end']-r['start'] for r in self.store.entries(self.base,self.base+8000)),1200)
    def test_group_contains_pending_matching_periods_when_one_needs_a_choice(self):
        first=self.activity();self.activity(7200);self.repo.discover(self.now)
        self.assertEqual(review_items(self.store,self.day),[])
        with self.store.db:self.store.db.execute("UPDATE ai_jobs SET state='exception' WHERE activity_id=?",(first,))
        item=review_items(self.store,self.day)[0];self.assertEqual(len(item['blocks']),2)
        choose(self.store,item,self.ids[0]);request=Mock();Engine(self.store,request=request,key=lambda:'fake').step(self.now);request.assert_not_called()
    def test_inflight_model_cannot_replace_a_daily_human_choice(self):
        self.activity();item=review_items(self.store,self.day)[0]
        def response(*a,**kw):
            choose(self.store,item,self.ids[1])
            return dict(task=self.ids[0],probability=.99,none_probability=.004,alternatives=[(self.ids[0],.99)]+[(i,.002) for i in sorted(self.ids[1:])],personal=.01,enough_evidence=.99,work_kind='other',model='jev-test',usage={'input_tokens':10,'output_tokens':1})
        self.assertEqual(Engine(self.store,request=response,key=lambda:'fake').step(self.now),'stale')
        self.assertEqual(self.store.entries(self.base,self.base+600)[0]['task_id'],self.ids[1])
        self.assertEqual(self.store.rows('SELECT state FROM ai_jobs')[0]['state'],'applied')
    def test_saved_choice_does_not_fill_open_or_idle_unsettled_periods(self):
        self.activity();choose(self.store,review_items(self.store,self.day)[0],self.ids[0]);self.activity(7200,closed=0)
        self.assertEqual(apply_saved(self.store,self.now),0)
    def test_undo_of_later_continuation_does_not_recreate_it(self):
        self.activity();choose(self.store,review_items(self.store,self.day)[0],self.ids[0]);self.activity(7200);apply_saved(self.store,self.now)
        self.store.undo();self.assertIsNone(choice(self.store,self.day,'Firefox'));self.assertEqual(apply_saved(self.store,self.now),0)
        self.store.undo();self.assertEqual(self.store.entries(self.base,self.base+8000),[])
    def test_day_record_top_apps_use_total_active_time_and_ignore_private_names(self):
        self.activity();self.activity(7200,'firefox',300);self.activity(1200,'Editor',1200);self.activity(4000,'Secret app',state='excluded')
        record=snapshot(self.store,self.day)
        self.assertEqual(record['top_apps'],[('Editor',1200),('Firefox',900)]);self.assertEqual(record['active'],2100)
    def test_running_timer_uses_one_clock_without_tick_drift_or_double_count(self):
        start=self.base
        with self.store.db:self.store.db.execute("UPDATE runtime SET state='running',task_id=?,started=? WHERE id=1",(self.ids[0],start))
        values=[snapshot(self.store,self.day,now=start+i,include_running=True)['human'] for i in (1,2,3,9)]
        self.assertEqual(values,[1,2,3,9]);self.assertEqual(snapshot(self.store,self.day,now=start+9)['human'],0)
        self.assertEqual(snapshot(self.store,self.day+timedelta(days=1),now=bounds(self.day+timedelta(days=1))[0]+2,include_running=True)['human'],2)

    def test_compatible_upgrade_preserves_consent_limits_and_paused_state(self):
        from timesheet.desktop import adopt_compatible_policy
        from timesheet.decision_policy import owner_token
        old='a'*64;self.repo.configure({**self.config,'owner':old,'daily_requests':10,'allow_project_clues':False})
        self.store.set('ai_pause_reason','Unknown usage needs acknowledgement')
        self.assertTrue(adopt_compatible_policy(self.store,old))
        config=self.repo.config();self.assertEqual(config['owner'],owner_token());self.assertEqual(config['daily_requests'],10)
        self.assertFalse(config['allow_project_clues']);self.assertEqual(self.store.get('ai_pause_reason'),'Unknown usage needs acknowledgement')
    def test_revocation_at_upgrade_lock_boundary_is_not_overwritten(self):
        from timesheet.desktop import adopt_compatible_policy
        import json
        old='a'*64;policy={**self.config,'owner':old};self.repo.configure(policy)
        other=Store(self.store.path);switched=[]
        def trace(sql):
            if sql=='BEGIN IMMEDIATE' and not switched:
                switched.append(True);other.set('ai_policy',json.dumps({**policy,'mode':'off'}))
        self.store.db.set_trace_callback(trace)
        try:
            self.assertFalse(adopt_compatible_policy(self.store,old))
            self.assertEqual(self.repo.config()['mode'],'off');self.assertTrue(switched)
        finally:self.store.db.set_trace_callback(None);other.close()
    def test_upgrade_does_not_adopt_other_installation_or_enable_off_policy(self):
        from timesheet.desktop import adopt_compatible_policy
        self.assertFalse(adopt_compatible_policy(self.store,'b'*64))
        self.repo.configure({**self.config,'mode':'off','owner':'a'*64})
        self.assertFalse(adopt_compatible_policy(self.store,'a'*64));self.assertEqual(self.repo.config()['mode'],'off')
    def test_erased_source_prunes_copied_daily_app_identity(self):
        self.activity();choose(self.store,review_items(self.store,self.day)[0],self.ids[0])
        with self.store.db:self.store.db.execute('DELETE FROM activity')
        self.repo.prune(self.now)
        self.assertEqual(self.store.rows('SELECT * FROM daily_choices'),[]);self.assertEqual(self.store.rows('SELECT * FROM daily_choice_changes'),[])
        self.assertEqual(len(self.store.entries(self.base,self.base+600)),1)
    def test_previous_launcher_version_is_read_without_executing_it(self):
        from timesheet.desktop import previous_source_owner
        import hashlib
        root=Path(self.tmp.name)/'old source';(root/'timesheet').mkdir(parents=True)
        (root/'timesheet/__init__.py').write_text("__version__ = '0.6.0-rc1'\nraise RuntimeError('must not execute')\n")
        launcher=Path(self.tmp.name)/'launcher';launcher.write_text('#!/bin/sh\nexec '+__import__('shlex').quote(str(root/'run-timesheet'))+' "$@"\n')
        self.assertEqual(previous_source_owner(launcher),hashlib.sha256((str(root)+'|0.6.0-rc1').encode()).hexdigest())


if __name__=='__main__':unittest.main()


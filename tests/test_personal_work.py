import csv,io,json,tempfile,time,unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
from timesheet.store import Store
from timesheet.simple_setup import BUCKETS,LEGACY_BUCKETS,ensure_buckets,finish_setup,preset_ids
from timesheet.automation_store import Repository
from timesheet import screen_spaces,screen_time
from timesheet.screen_export import csv_bytes,write_summary
from timesheet.collector import Collector


class PersonalWorkTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db');self.now=int(time.time());self.base=self.now-3600
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def activity(self,app='Browser',state='active'):
        with self.store.db:return self.store.db.execute('INSERT INTO activity(start,end,app,title,state,closed) VALUES(?,?,?,?,?,1)',(self.base,self.base+600,app,'PRIVATE /file',state)).lastrowid
    def test_expanded_presets_preserve_intact_legacy_ids_and_consent(self):
        legacy={k:v for k,v in BUCKETS.items() if k in LEGACY_BUCKETS}
        with patch.dict(BUCKETS,legacy,clear=True):old=finish_setup(self.store,list(legacy),connected=True)
        before=self.store.get('ai_policy');old_ids=old['category_tasks']
        ids=ensure_buckets(self.store,list(BUCKETS))
        self.assertEqual(ids[:4],old_ids);self.assertEqual(len(ids),8)
        self.assertEqual(self.store.get('ai_policy'),before);self.assertEqual(len(self.store.rows('SELECT * FROM projects')),1)
    def test_category_name_collision_does_not_adopt_a_users_task(self):
        legacy={k:v for k,v in BUCKETS.items() if k in LEGACY_BUCKETS}
        with patch.dict(BUCKETS,legacy,clear=True):old=ensure_buckets(self.store,list(legacy))
        pid=int(self.store.get('simple_project_id'))
        with self.store.db:private=self.store.db.execute("INSERT INTO tasks(project_id,name) VALUES(?,'Games')",(pid,)).lastrowid
        ids=ensure_buckets(self.store,list(BUCKETS));self.assertNotIn(private,ids);self.assertTrue(set(old).isdisjoint(ids))
        self.assertEqual(self.store.db.execute('SELECT name FROM tasks WHERE id=?',(private,)).fetchone()[0],'Games')
    def test_setup_failure_rolls_back_categories_policy_and_preferences(self):
        with patch.object(Repository,'configure',side_effect=ValueError('simulated failure')):
            with self.assertRaises(ValueError):finish_setup(self.store,list(BUCKETS),connected=True,tools=['rules'])
        self.assertEqual(self.store.tasks(),[]);self.assertEqual(self.store.get('simple_setup_complete','0'),'0');self.assertEqual(self.store.get('simple_tools','[]'),'[]')
    def test_space_labels_do_not_change_outgoing_context(self):
        finish_setup(self.store,list(BUCKETS),connected=True,now=self.base-86400);repo=Repository(self.store);aid=self.activity()
        activity=self.store.rows('SELECT * FROM activity WHERE id=?',(aid,))[0];before,_=repo.context(activity)
        screen_spaces.switch(self.store,'personal',self.base);after,_=repo.context(activity)
        self.assertEqual(before,after);self.assertEqual(self.store.entries(0,self.now),[])
    def test_idle_and_lock_override_exclusion(self):
        self.store.set('capture_enabled','1');self.store.set('excluded_apps','Private app');self.store.set('idle_seconds','5')
        recorder=Collector(self.store)
        recorder.step(100,100,('Private app','secret',0,False));recorder.step(102,102,('Private app','secret',0,True))
        self.assertEqual(self.store.runtime()['activity_state'],'locked')
        recorder.step(104,104,('Private app','secret',6000,False));self.assertEqual(self.store.runtime()['activity_state'],'away')
        self.assertTrue(all(not r['app'] and not r['title'] for r in self.store.rows('SELECT * FROM activity')))
    def test_export_is_factual_private_and_spreadsheet_formula_safe(self):
        self.activity('=HYPERLINK("evil")');day=datetime.fromtimestamp(self.base).date();week=screen_time.week(self.store,day,self.now)
        data=csv_bytes(week);rows=list(csv.reader(io.StringIO(data.decode('utf-8-sig'))))
        self.assertNotIn('PRIVATE',data.decode('utf-8-sig'));self.assertNotIn('Client',data.decode('utf-8-sig'))
        self.assertTrue(any(row and row[0].startswith("'=HYPERLINK") for row in rows))
        path=Path(self.tmp.name)/'screen.csv';write_summary(path,data);self.assertEqual(path.read_bytes(),data)
        self.assertEqual(path.stat().st_mode&0o777,0o600);self.assertEqual(self.store.rows('SELECT * FROM reports'),[])
    def test_day_record_union_does_not_leak_app_overlapping_private_evidence(self):
        from timesheet.day_record import snapshot
        self.activity('SECRET APP');self.activity('','excluded')
        record=snapshot(self.store,datetime.fromtimestamp(self.base).date(),now=self.now)
        self.assertEqual(record['active'],0);self.assertEqual(record['screen_seconds'],600);self.assertNotIn('SECRET',json.dumps(record))

    def test_csv_guards_formula_prefixes_hidden_behind_unicode_format_characters(self):
        from timesheet.screen_export import safe_cell
        for name in (' =1+1','\ufeff=1+1',' \u200b+1','\u202e@SUM(1)','\tFirefox'):
            self.assertEqual(safe_cell(name),"'"+name)
        self.assertEqual(safe_cell('Firefox'),'Firefox');self.assertEqual(safe_cell('Straße'),'Straße')

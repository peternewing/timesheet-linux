"""Installed app types never establish client intent or bypass explicit choices."""
import json,tempfile,time,unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock,patch
from timesheet.store import Store
from timesheet.simple_setup import BUCKETS,finish_setup,preset_ids
from timesheet.automation_worker import Engine
from timesheet.daily_choices import choose
from timesheet.simple_store import activity_item
from timesheet.local_types import classify,Registry,apply
from timesheet.automation_status import explain_entry


class LocalTypeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db');self.now=int(time.time());self.base=self.now-3600
        finish_setup(self.store,list(BUCKETS),connected=False,now=self.base-86400);self.ids=preset_ids(self.store)
        self.catalog=Mock();self.catalog.lookup.return_value=dict(bucket='browse',categories=['WebBrowser'])
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def activity(self,offset=0):
        with self.store.db:return self.store.db.execute("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,'Browser','active',1)",(self.base+offset,self.base+offset+300)).lastrowid
    def test_clear_type_works_offline_without_key_or_provider(self):
        self.activity();request=Mock();key=Mock()
        with patch('timesheet.local_types.registry',self.catalog):self.assertEqual(Engine(self.store,request=request,key=key).step(self.now),'off')
        request.assert_not_called();key.assert_not_called();entry=self.store.entries(0,self.now)[0]
        self.assertEqual((entry['origin'],entry['status'],entry['billable'],entry['task_id']),('app_type','draft',0,self.ids['browse']))
        self.assertIn('did not use an AI answer',explain_entry(self.store,entry['id']))
        self.assertEqual(self.store.rows('SELECT * FROM ai_usage'),[])
    def test_explicit_skip_rules_and_existing_allocations_win(self):
        self.activity();day=datetime.fromtimestamp(self.base).date();choose(self.store,activity_item(self.store,day,'Browser',self.now),None,now=self.now)
        self.assertEqual(apply(self.store,self.now,catalog=self.catalog),0)
        self.store.set('local_type_cursor','0');self.store.add_rule('Browser','',self.ids['create'])
        self.assertEqual(apply(self.store,self.now,catalog=self.catalog),0)
        self.assertEqual(self.store.entries(0,self.now),[])

    def test_local_metadata_winning_during_an_inflight_response_cannot_duplicate_time(self):
        finish_setup(self.store,list(BUCKETS),connected=True,now=self.base-86400);self.activity()
        def request(*args,**kwargs):
            self.store.set('local_type_cursor','0')
            self.assertEqual(apply(self.store,self.now,catalog=self.catalog),1)
            ids=list(self.ids.values());task=self.ids['browse']
            return dict(task=task,probability=.97,none_probability=.01,alternatives=sorted([(i,.97 if i==task else .02/(len(ids)-1)) for i in ids],key=lambda x:(-x[1],x[0])),
                personal=.5,enough_evidence=.99,work_kind='other',model='jev-synthetic-race',usage={'input_tokens':100,'output_tokens':0})
        with patch('timesheet.local_types.registry.lookup',return_value=None):
            self.assertEqual(Engine(self.store,key=lambda:'fake',request=request).step(self.now),'stale')
        entries=self.store.entries(0,self.now);self.assertEqual(len(entries),1);self.assertEqual(entries[0]['origin'],'app_type')
        self.assertEqual(entries[0]['end']-entries[0]['start'],300)
        self.assertEqual(self.store.rows('SELECT outcome FROM ai_usage')[0]['outcome'],'success')
        self.assertEqual(self.store.rows('SELECT decision_source FROM ai_jobs')[0]['decision_source'],'local')
    def test_explicit_entry_cannot_be_replaced(self):
        self.activity();self.store.add_entry(self.ids['create'],self.base,self.base+300,billable=False)
        self.assertEqual(apply(self.store,self.now,catalog=self.catalog),0)
        self.assertEqual(self.store.entries(0,self.now)[0]['task_id'],self.ids['create'])
    def test_undo_is_not_immediately_recreated_but_new_capture_can_be_labelled(self):
        self.activity();self.assertEqual(apply(self.store,self.now,catalog=self.catalog),1);self.store.undo()
        for _ in range(3):self.assertEqual(apply(self.store,self.now,catalog=self.catalog),0)
        self.activity(600);self.assertEqual(apply(self.store,self.now,catalog=self.catalog),1)
        self.assertEqual(len(self.store.entries(0,self.now)),1)
    def test_daily_choice_can_correct_and_undo_a_local_estimate(self):
        self.activity();apply(self.store,self.now,catalog=self.catalog);day=datetime.fromtimestamp(self.base).date()
        item=activity_item(self.store,day,'Browser',self.now);self.assertEqual(len(item['auto_entries']),1)
        choose(self.store,item,self.ids['learn'],now=self.now)
        self.assertEqual(self.store.entries(0,self.now)[0]['origin'],'assigned')
        self.store.undo();self.assertEqual(self.store.entries(0,self.now)[0]['origin'],'app_type')
    def test_exclusion_during_lookup_wins_at_write_lock(self):
        self.activity()
        def lookup(_):self.store.set('excluded_apps','Browser');return dict(bucket='browse',categories=['WebBrowser'])
        self.catalog.lookup.side_effect=lookup
        self.assertEqual(apply(self.store,self.now,catalog=self.catalog),0);self.assertEqual(self.store.entries(0,self.now),[])
    def test_privacy_scope_and_disable_prevent_lookup_or_assignment(self):
        self.activity();self.store.set('local_app_types','0');self.assertEqual(apply(self.store,self.now,catalog=self.catalog),0)
        self.catalog.lookup.assert_not_called()
        self.store.set('local_app_types','1');self.store.set('excluded_apps','Browser');self.assertEqual(apply(self.store,self.now,catalog=self.catalog),0)
        self.catalog.lookup.assert_not_called()
    def test_does_not_fall_back_to_arbitrary_client_tasks(self):
        self.activity();self.store.quick_project('Private client','Private project','Web browsing')
        with self.store.db:self.store.db.execute('UPDATE tasks SET archived=1 WHERE id=?',(self.ids['browse'],))
        self.assertEqual(apply(self.store,self.now,catalog=self.catalog),0)
    def test_bounded_scan_and_no_duplicate_allocations(self):
        self.activity();self.activity(600)
        self.assertEqual(apply(self.store,self.now,limit=1,catalog=self.catalog),1)
        self.assertEqual(apply(self.store,self.now,limit=1,catalog=self.catalog),1)
        self.assertEqual(apply(self.store,self.now,limit=1,catalog=self.catalog),0)
        self.assertEqual(len(self.store.entries(0,self.now)),2)
    def test_category_mapping_abstains_on_broad_or_conflicting_metadata(self):
        for tags in (['Network'],['Office'],['Graphics'],['Game','Education'],['WebBrowser','TextEditor'],['LauncherStore','Game'],['webbrowser']):
            with self.subTest(tags=tags):self.assertIsNone(classify(tags))
        for tags,expected in [(['Network','WebBrowser'],'browse'),(['Graphics','Viewer'],None),(['Office','WordProcessor'],'create'),(['AudioVideo','Player'],'media'),(['Game'],'play'),(['Game','WebBrowser'],None),(['Education','Player'],None)]:self.assertEqual(classify(tags),expected)
    def test_identity_matching_is_exact_and_conflicts_abstain(self):
        catalog=Registry();catalog.loaded=time.monotonic();catalog.index={'browser':[dict(bucket='browse',categories=['WebBrowser'])]}
        self.assertEqual(catalog.lookup('BROWSER')['bucket'],'browse');self.assertIsNone(catalog.lookup('Browser private'))
        catalog.index['browser'].append(dict(bucket='create',categories=['TextEditor']));self.assertIsNone(catalog.lookup('Browser'))

class DesktopMetadataTests(unittest.TestCase):
    def test_real_desktop_entries_are_read_locally_and_unknown_name_collisions_abstain(self):
        import gi
        from gi.repository import Gio
        if hasattr(Gio,'DesktopAppInfo'):desktop_info=Gio.DesktopAppInfo
        else:
            gi.require_version('GioUnix','2.0')
            from gi.repository import GioUnix
            desktop_info=GioUnix.DesktopAppInfo
        with tempfile.TemporaryDirectory() as folder:
            paths=[];marker=Path(folder)/'NEVER_EXECUTE'
            for i,tags in enumerate(('Network;WebBrowser;','Office;')):
                path=Path(folder)/f'fixture{i}.desktop';path.write_text('[Desktop Entry]\nType=Application\nName=Shared Fixture\nNoDisplay=true\nStartupWMClass=Fixture'+str(i)+'\nCategories='+tags+'\nExec=/usr/bin/touch '+str(marker)+'\n');paths.append(path)
            apps=[desktop_info.new_from_filename(str(path)) for path in paths];self.assertTrue(all(apps))
            registry=Registry()
            with patch.object(Gio.AppInfo,'get_all',return_value=apps):registry.refresh()
            self.assertIsNone(registry.lookup('Shared Fixture'))
            known=registry.lookup('Fixture0');self.assertIsNotNone(known,str(registry.index));self.assertEqual(known['bucket'],'browse')
            self.assertIsNone(registry.lookup('Fixture1'));self.assertFalse(marker.exists())
    def test_refresh_publishes_complete_snapshot_and_keeps_old_snapshot_during_refresh(self):
        registry=Registry();registry.index={'browser':[dict(bucket='browse',categories=['WebBrowser'])]};registry.loaded=0
        registry.refresh_lock.acquire()
        try:
            with patch.object(registry,'refresh',side_effect=AssertionError('Concurrent refresh')):self.assertEqual(registry.lookup('Browser')['bucket'],'browse')
        finally:registry.refresh_lock.release()
        registry.index['browser'].append(dict(bucket=None,categories=[]));registry.loaded=time.monotonic()
        self.assertIsNone(registry.lookup('Browser'))

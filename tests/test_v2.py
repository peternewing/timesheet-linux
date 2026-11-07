import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from timesheet.store import Store
from timesheet.collector import Collector

class ImprovedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Store(Path(self.tmp.name)/'test.sqlite3')
        self.task=self.s.quick_project('Client','Project','Task',6000)
    def tearDown(self):self.s.close();self.tmp.cleanup()
    def activity(self,start=1000,end=1500,app='Editor',title='',closed=1):
        with self.s.db:return self.s.db.execute('INSERT INTO activity(start,end,app,title,closed) VALUES(?,?,?,?,?)',(start,end,app,title,closed)).lastrowid
    def test_automatic_rules_are_idempotent_and_do_not_approve(self):
        self.activity();self.s.add_rule('Editor','',self.task)
        with self.s.db:self.s.db.execute('UPDATE rules SET created=0')
        self.assertEqual(self.s.apply_rules(now=2000),1);self.assertEqual(self.s.apply_rules(now=2000),0)
        r=self.s.entries(0,3000)[0];self.assertEqual((r['origin'],r['status']),('automatic','draft'))
    def test_new_rule_does_not_reclassify_past_activity_without_request(self):
        self.activity();self.s.add_rule('Editor','',self.task)
        self.assertEqual(self.s.apply_rules(now=2000),0)
        self.assertEqual(self.s.apply_rules(now=2000,start=0,end=1800),1)
    def test_rules_respect_conflicts_and_existing_work(self):
        other=self.s.add_task(self.s.rows('SELECT id FROM projects')[0][0],'Other')
        self.activity();self.s.add_rule('Editor','',self.task);self.s.add_rule('Editor','',other)
        self.assertIsNone(self.s.matching_task('Editor',''));self.assertEqual(self.s.apply_rules(now=2000),0)
    def test_assign_remaining_skips_existing_work(self):
        aid=self.activity();self.s.add_entry(self.task,1200,1300)
        self.assertEqual(self.s.assign_remaining([dict(id=aid,start=1000,end=1500)],self.task),2)
        rows=self.s.entries(0,3000);self.assertEqual(sum(r['end']-r['start'] for r in rows),500)
    def test_undo_edit_and_delete_without_losing_time(self):
        e=self.s.add_entry(self.task,1000,1500,'First');self.s.update_entry(e,self.task,1000,1500,'Second',True)
        self.s.update_entry(e,self.task,1000,1500,'Third',True);self.s.undo();self.s.undo()
        self.assertEqual(self.s.entries(0,2000)[0]['description'],'First')
        self.s.delete_entry(e);self.assertFalse(self.s.entries(0,2000));self.s.undo();self.assertEqual(len(self.s.entries(0,2000)),1)
    def test_merge_and_undo(self):
        a=self.s.add_entry(self.task,1000,1500);b=self.s.add_entry(self.task,1500,2000)
        self.s.merge_entries([a,b]);self.assertEqual(len(self.s.entries(0,3000)),1)
        self.s.undo();self.assertEqual(len(self.s.entries(0,3000)),2)
    def test_bulk_approval_rolls_back_if_one_rate_missing(self):
        a=self.s.add_entry(self.task,1000,1500)
        other=self.s.quick_project('Other','Other','Task',None);b=self.s.add_entry(other,1500,2000)
        with self.assertRaises(ValueError):self.s.approve_many([a,b])
        self.assertTrue(all(r['status']=='draft' for r in self.s.entries(0,3000)))
    def test_stale_edit_rejected(self):
        e=self.s.add_entry(self.task,1000,1500)
        self.s.update_entry(e,self.task,1000,1500,'Updated',True,expected_revision=1)
        with self.assertRaisesRegex(ValueError,'changed'):self.s.update_entry(e,self.task,1000,1500,'Old',True,expected_revision=1)
    def test_collector_durable_activity_and_idle_reclassification(self):
        self.s.set('capture_enabled',1);self.s.set('idle_seconds',3);self.s.set('capture_titles',0)
        c=Collector(self.s);c.step(1000,1000,('Editor','secret',0,False));c.step(1002,1002,('Editor','secret',0,False))
        self.s.start_timer(self.task,1002);c.step(1004,1004,('Editor','secret',0,False));c.step(1006,1006,('Editor','secret',4000,False));c.close()
        rows=self.s.rows('SELECT * FROM activity ORDER BY start');self.assertTrue(rows);self.assertTrue(all(r['title']=='' for r in rows))
        self.assertTrue(all(r['end']<=1002 for r in rows if r['state']=='active'))
        self.assertEqual(self.s.runtime()['state'],'stopped')
    def test_sleep_gap_not_charged(self):
        self.s.set('capture_enabled',1);c=Collector(self.s);c.step(1000,1000,('Editor','',0,False));c.step(1002,1002,('Editor','',0,False));self.s.start_timer(self.task,1002)
        c.step(1004,1004,('Editor','',0,False));c.step(2000,1006,('Editor','',0,False));c.close()
        self.assertEqual(self.s.entries(0,3000)[0]['end'],1004)
        self.assertTrue(self.s.rows("SELECT * FROM activity WHERE state='unknown' AND start=1004 AND end=2000"))
    def test_crash_recovery_uses_checkpoint(self):
        self.s.start_timer(self.task,1000)
        with self.s.db:self.s.db.execute('UPDATE runtime SET checkpoint=1005 WHERE id=1')
        Collector(self.s)
        self.assertEqual(self.s.entries(0,3000)[0]['end'],1005)
    def test_live_activity_cannot_be_assigned(self):
        aid=self.activity(closed=0)
        with self.assertRaisesRegex(ValueError,'still being recorded'):self.s.assign_remaining([dict(id=aid,start=1000,end=1500)],self.task)
    def test_recent_automatic_activity_cannot_be_approved(self):
        import time
        now=int(time.time());aid=self.activity(now-100,now-10)
        with self.s.db:self.s.db.execute("INSERT INTO entries(task_id,start,end,origin,activity_id) VALUES(?,?,?,'assigned',?)",(self.task,now-100,now-10,aid))
        eid=self.s.rows('SELECT id FROM entries')[0][0]
        with self.assertRaisesRegex(ValueError,'settling'):self.s.approve(eid)
    def test_billing_correction_preserves_report_snapshot(self):
        eid=self.s.add_entry(self.task,1000,4600);self.s.approve(eid);rid=self.s.create_report(1,0,5000)
        snapshot=self.s.report(rid);self.s.mark_billed(rid,'INV-1');self.s.reopen_report(rid,'Invoice cancelled externally')
        self.assertEqual(self.s.report(rid),snapshot)
        self.assertEqual(self.s.entries(0,5000)[0]['status'],'draft')
        self.assertEqual(self.s.rows('SELECT state FROM report_billing')[0][0],'corrected')
    def test_personal_usage_stays_in_totals_but_leaves_review_queue(self):
        aid=self.activity();self.s.set_personal([aid]);summary=self.s.day_summary(0,2000)
        self.assertEqual((summary['active'],summary['unassigned']),(500,0))
        self.s.set_personal([aid],False);self.assertEqual(self.s.day_summary(0,2000)['unassigned'],500)
    def test_validation_rejects_inconsistent_backup_entries(self):
        self.s.add_entry(self.task,1000,1500)
        with self.s.db:self.s.db.execute('INSERT INTO entries(task_id,start,end) VALUES(?,?,?)',(self.task,1200,1600))
        with self.assertRaisesRegex(ValueError,'overlapping'):self.s.validate()
    def test_schema_upgrade_preserves_entries_and_creates_backup(self):
        self.s.add_entry(self.task,1000,1500)
        with self.s.db:self.s.db.execute('PRAGMA user_version=2')
        path=self.s.path;self.s.close();self.s=Store(path)
        self.assertEqual(len(self.s.entries(0,2000)),1);self.assertEqual(self.s.db.execute('PRAGMA user_version').fetchone()[0],3)
        self.assertTrue(path.with_name('test-before-v3.sqlite3').exists())

if __name__=='__main__':unittest.main()

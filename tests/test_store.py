import csv
import io
import os
import tempfile
import threading
import unittest
import time
from pathlib import Path
from timesheet.store import Store, parse_money, parse_hours, local_timestamp

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.db=Store(Path(self.tmp.name)/'db.sqlite3')
        self.client=self.db.add_client('Client','GBP',6000)
        self.project=self.db.add_project(self.client,'Project',36000)
        self.task=self.db.add_task(self.project,'Task')
    def tearDown(self): self.db.close(); self.tmp.cleanup()
    def test_adjacent_and_overlapping_intervals(self):
        self.db.add_entry(self.task,1000,2000)
        self.db.add_entry(self.task,2000,2100)
        for start,end in [(999,1001),(1500,2500),(1000,2000),(1200,1300)]:
            with self.assertRaisesRegex(ValueError,'overlaps'): self.db.add_entry(self.task,start,end)
    def test_billing_rate_snapshot_and_duplicate_billing(self):
        eid=self.db.add_entry(self.task,1000,6400,'Website')
        self.db.approve(eid)
        with self.db.db: self.db.db.execute('UPDATE clients SET rate=9000 WHERE id=?',(self.client,))
        rid=self.db.create_report(self.client,0,10000); report=self.db.report(rid)
        self.assertEqual(report[0]['rate'],6000); self.assertEqual(report[0]['amount'],9000)
        self.db.mark_billed(rid,'INV-1')
        with self.assertRaises(ValueError): self.db.mark_billed(rid,'INV-1')
        with self.assertRaises(ValueError): self.db.update_entry(eid,self.task,1000,6400,'Changed',True)
        with self.assertRaises(ValueError): self.db.create_report(self.client,0,10000)
    def test_stale_report_rejected(self):
        eid=self.db.add_entry(self.task,1000,2000); self.db.approve(eid)
        rid=self.db.create_report(self.client,0,10000)
        self.db.update_entry(eid,self.task,1000,2000,'Revised',True); self.db.approve(eid)
        with self.assertRaisesRegex(ValueError,'stale'): self.db.mark_billed(rid,'INV-2')
    def test_csv_formula_and_html_escaping(self):
        eid=self.db.add_entry(self.task,1000,4600,'=SUM(1,1) <script>'); self.db.approve(eid)
        rid=self.db.create_report(self.client,0,10000)
        data=list(csv.reader(io.StringIO(self.db.csv_report(rid))))
        self.assertTrue(data[1][4].startswith("'=")); self.assertIn('&lt;script&gt;',self.db.html_report(rid)); self.assertNotIn('<script>',self.db.html_report(rid))
    def test_running_timer_stop_and_overlap(self):
        self.db.start_timer(self.task,1000)
        with self.assertRaises(ValueError): self.db.start_timer(self.task,1100)
        eid=self.db.stop_timer(1600)
        r=self.db.db.execute('SELECT * FROM entries WHERE id=?',(eid,)).fetchone()
        self.assertEqual((r['start'],r['end']), (1000,1600)); self.assertEqual(self.db.runtime()['state'],'stopped')
    def test_backup_restores_accounting(self):
        eid=self.db.add_entry(self.task,1000,6400); self.db.approve(eid)
        dest=Path(self.tmp.name)/'backup.sqlite3'; self.db.backup(dest)
        restored=Store(dest)
        try: self.assertEqual(restored.entries(0,10000)[0]['rate'],6000)
        finally: restored.close()
        self.assertEqual(os.stat(dest).st_mode & 0o777,0o600)
    def test_missing_rate_and_zero(self):
        with self.db.db: self.db.db.execute('UPDATE clients SET rate=NULL')
        eid=self.db.add_entry(self.task,1000,4600)
        with self.assertRaisesRegex(ValueError,'rate'): self.db.approve(eid)
        with self.db.db: self.db.db.execute('UPDATE clients SET rate=0')
        self.db.approve(eid); self.assertEqual(self.db.db.execute('SELECT rate FROM entries WHERE id=?',(eid,)).fetchone()[0],0)
    def test_nonbillable_does_not_require_rate(self):
        with self.db.db: self.db.db.execute('UPDATE clients SET rate=NULL')
        eid=self.db.add_entry(self.task,1000,4600,billable=False); self.db.approve(eid)
        with self.assertRaisesRegex(ValueError,'No approved'): self.db.create_report(self.client,0,10000)
    def test_input_validation(self):
        self.assertEqual(parse_money('60.05'),6005); self.assertEqual(parse_money('0'),0); self.assertEqual(parse_hours('1.5'),5400)
        for value in ('-1','NaN','1.001','abc'):
            with self.assertRaises(ValueError): parse_money(value)
    def test_split_preserves_duration_and_requires_new_approval(self):
        eid=self.db.add_entry(self.task,1000,6400,'Work'); self.db.approve(eid)
        second=self.db.split_entry(eid,2800)
        rows=self.db.rows('SELECT * FROM entries WHERE id IN (?,?) ORDER BY start',(eid,second))
        self.assertEqual([(r['start'],r['end'],r['status']) for r in rows],[(1000,2800,'draft'),(2800,6400,'draft')])
        self.assertEqual(sum(r['end']-r['start'] for r in rows),5400)
        with self.assertRaises(ValueError): self.db.split_entry(eid,1000)
    def test_bulk_assignment_is_atomic_on_overlap(self):
        with self.db.db:
            first=self.db.db.execute("INSERT INTO activity(start,end,app) VALUES(1000,2000,'Editor')").lastrowid
            second=self.db.db.execute("INSERT INTO activity(start,end,app) VALUES(2000,3000,'Editor')").lastrowid
        self.db.add_entry(self.task,2500,3500)
        with self.assertRaisesRegex(ValueError,'overlaps'): self.db.assign_activity_batch([first,second],self.task)
        self.assertEqual(len(self.db.entries(0,10000)),1)
        self.db.assign_activity_batch([first],self.task)
        self.assertEqual(len(self.db.entries(0,10000)),2)
    def test_daylight_saving_gap_and_repeated_hour_are_rejected(self):
        original=os.environ.get('TZ')
        try:
            os.environ['TZ']='Europe/London'; time.tzset()
            self.assertIsInstance(local_timestamp('2026-03-28 12:00'),int)
            with self.assertRaisesRegex(ValueError,'does not exist'): local_timestamp('2026-03-29 01:30')
            with self.assertRaisesRegex(ValueError,'occurs twice'): local_timestamp('2026-10-25 01:30')
        finally:
            if original is None: os.environ.pop('TZ',None)
            else: os.environ['TZ']=original
            time.tzset()
    def test_concurrent_writers_cannot_create_overlapping_entries(self):
        barrier=threading.Barrier(2); results=[]
        def worker():
            db=Store(self.db.path)
            try:
                barrier.wait()
                try: db.add_entry(self.task,1000,2000); results.append('saved')
                except ValueError: results.append('rejected')
            finally: db.close()
        threads=[threading.Thread(target=worker) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertCountEqual(results,['saved','rejected'])
        self.assertEqual(len(self.db.entries(0,10000)),1)

if __name__=='__main__': unittest.main()

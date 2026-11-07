"""Regression coverage for failures found during the desktop usability audit."""
import json
import tempfile
import unittest
from pathlib import Path
from timesheet.store import Store, parse_money, parse_hours

class AuditRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=Store(Path(self.tmp.name)/'audit.sqlite3')
        self.task=self.store.quick_project('Client','Project','Task',6000)
    def tearDown(self):
        self.store.close(); self.tmp.cleanup()
    def test_existing_client_different_rate_is_not_silently_ignored(self):
        with self.assertRaisesRegex(ValueError,'billing settings'):
            self.store.quick_project('Client','Another project','Task',9000)
        self.assertEqual(len(self.store.rows('SELECT * FROM projects')),1)
        self.assertEqual(self.store.rows('SELECT rate FROM clients')[0][0],6000)
    def test_existing_client_different_currency_is_not_silently_ignored(self):
        with self.assertRaisesRegex(ValueError,'billing settings'):
            self.store.quick_project('Client','Another project','Task',6000,'EUR')
        self.assertEqual(len(self.store.rows('SELECT * FROM projects')),1)
    def test_archived_client_cannot_create_invisible_project(self):
        with self.store.db: self.store.db.execute('UPDATE clients SET archived=1')
        with self.assertRaisesRegex(ValueError,'archived'):
            self.store.quick_project('Client','Another project','Task',6000)
        self.assertEqual(len(self.store.rows('SELECT * FROM projects')),1)
    def test_duplicate_project_is_explicit_and_does_not_change_budget(self):
        with self.assertRaisesRegex(ValueError,'already exists'):
            self.store.quick_project('Client','Project','New task',6000,budget=500)
        self.assertEqual(len(self.store.tasks()),1)
        self.assertIsNone(self.store.rows('SELECT budget FROM projects')[0][0])
    def test_existing_client_can_add_distinct_project(self):
        task=self.store.quick_project('Client','Another project','Task',6000)
        self.assertNotEqual(task,self.task)
        self.assertEqual(len(self.store.rows('SELECT * FROM clients')),1)
    def test_duplicate_merge_ids_do_not_modify_entry(self):
        entry=self.store.add_entry(self.task,1000,2000,'Keep me')
        self.store.approve(entry)
        with self.assertRaisesRegex(ValueError,'two adjacent'):
            self.store.merge_entries([entry,entry])
        self.assertEqual(self.store.entries(0,3000)[0]['status'],'approved')
    def test_extreme_numbers_fail_before_database_binding(self):
        for parse in (parse_money,parse_hours):
            for text in ('1e1000000','NaN','Infinity','-1','1000000001'):
                with self.subTest(parser=parse.__name__,text=text):
                    with self.assertRaises(ValueError): parse(text)
            self.assertEqual(parse('0'),0)
            self.assertIsNone(parse(''))
    def test_archiving_keeps_report_exports_and_billing_snapshot(self):
        entry=self.store.add_entry(self.task,1000,4600,'Design'); self.store.approve(entry)
        report=self.store.create_report(1,0,5000); self.store.mark_billed(report,'INV-1')
        before=self.store.report(report)
        with self.store.db: self.store.db.execute('UPDATE clients SET archived=1')
        self.assertEqual(self.store.report(report),before)
        self.assertIn('Design',self.store.csv_report(report))
        self.assertIn('60.00',self.store.html_report(report))
        self.assertTrue(self.store.validate())

    def test_restore_rejects_malformed_report_values(self):
        entry=self.store.add_entry(self.task,1000,4600,'Design'); self.store.approve(entry)
        report=self.store.create_report(1,0,5000); original=self.store.report(report)
        for key,value in [('amount','not a number'),('rate',-1),('end',1000),('description',None),('currency','UNKNOWN'),('report_date','=1+1')]:
            with self.subTest(key=key):
                changed=[dict(original[0],**{key:value})]
                with self.store.db: self.store.db.execute('UPDATE reports SET snapshot=? WHERE id=?',(json.dumps(changed),report))
                with self.assertRaisesRegex(ValueError,'malformed'): self.store.validate()
        with self.store.db: self.store.db.execute('UPDATE reports SET snapshot=? WHERE id=?',(json.dumps(original),report))
        self.assertTrue(self.store.validate())

if __name__=='__main__': unittest.main()

"""PDFs must contain the frozen amounts and never change billing state."""
import importlib.util
import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from timesheet.pdf_export import report_pdf,write_pdf
from timesheet.store import Store

@unittest.skipUnless(importlib.util.find_spec('reportlab') and shutil.which('pdftotext'), 'reportlab and pdftotext required')
class PDFTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)
        self.store=Store(self.path/'timesheet.sqlite3')
        task=self.store.quick_project('Équipe £','Design','Review',6000)
        entry=self.store.add_entry(task,1000,4600,'Café & <layout>');self.store.approve(entry)
        self.report=self.store.create_report(1,0,5000)
        self.rows=self.store.report(self.report)
    def tearDown(self): self.store.close();self.tmp.cleanup()
    def extract(self,pdf):
        file=self.path/'output.pdf';write_pdf(file,pdf)
        return subprocess.check_output(['pdftotext','-layout',str(file),'-'],text=True)
    def test_report_uses_frozen_snapshot_and_does_not_bill(self):
        before=self.store.report(self.report)
        with self.store.db:self.store.db.execute('UPDATE clients SET rate=99999')
        text=self.extract(report_pdf(self.rows,self.report))
        self.assertIn('Équipe £',text);self.assertIn('Café & <layout>',text)
        self.assertIn('GBP 60.00',text);self.assertIn('60.00',text)
        self.assertEqual(self.store.report(self.report),before)
        self.assertEqual(self.store.entries(0,5000)[0]['status'],'approved')
    def test_invoice_draft_is_not_an_issued_invoice(self):
        details=dict(number='INV-001',seller='Studio',customer='Client',issued='2026-11-07',due='2026-12-07',payment='Bank')
        text=self.extract(report_pdf(self.rows,self.report,paper='Letter',invoice=details))
        for value in ('Invoice draft','INV-001','No tax','Bank'):self.assertIn(value,text)
        self.assertEqual(self.store.entries(0,5000)[0]['status'],'approved')
        details['due']='2026-01-01'
        with self.assertRaises(ValueError):report_pdf(self.rows,self.report,invoice=details)
    def test_many_pages_repeat_headings_and_total(self):
        text=self.extract(report_pdf(self.rows*70,self.report))
        self.assertGreater(text.count('Date / work'),1)
        self.assertIn('GBP 4200.00',text)
    def test_extreme_description_spans_pages_without_losing_total(self):
        row=dict(self.rows[0],description='unusually long work description '*250)
        text=self.extract(report_pdf([row],self.report))
        self.assertGreater(text.count('Date / work'),1)
        self.assertIn('GBP 60.00',text)

    def test_empty_and_mixed_currency_rejected(self):
        with self.assertRaises(ValueError):report_pdf([],self.report)
        with self.assertRaises(ValueError):report_pdf([self.rows[0],dict(self.rows[0],currency='EUR')],self.report)

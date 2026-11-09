"""Asynchronous insights use a title-free read-only snapshot, no Store migration."""
import hashlib,sqlite3,tempfile,threading,time,unittest
from pathlib import Path
from datetime import date
from unittest.mock import patch
from timesheet.store import Store
from timesheet.day_record import bounds
from timesheet import screen_spaces,screen_time
from timesheet.screen_reader import load_week,Reader

class ScreenReaderTests(unittest.TestCase):
    def test_read_only_aggregate_matches_main_summary_without_titles_or_interval_copies(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'db';store=Store(path);day=date(2026,11,9);start=bounds(day)[0]+3600;now=start+3600
            try:
                with store.db:store.db.execute("INSERT INTO activity(start,end,app,title,state,capture_version) VALUES(?,?,'Firefox','SECRET TITLE','active',2)",(start,start+300))
                screen_spaces.switch(store,'personal',start);expected=screen_time.week(store,day,now,space='personal');before=hashlib.sha256(path.read_bytes()).hexdigest()
                with patch('timesheet.jev.get_key',side_effect=AssertionError('no key')):actual=load_week(path,day,now,'personal')
                self.assertEqual(actual['total'],expected['total']);self.assertEqual(actual['apps'],expected['apps']);self.assertEqual(actual['days'][-1]['hourly'],expected['days'][-1]['hourly'])
                self.assertFalse(any('periods' in row for row in actual['days']));self.assertNotIn('SECRET',str(actual));self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)
                connection=sqlite3.connect(path);connection.row_factory=sqlite3.Row
                try:self.assertNotIn('title',Reader(connection).activity_for(start,now)[0])
                finally:connection.close()
            finally:store.close()
    def test_cancelled_read_is_empty_and_missing_file_is_not_created(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'db';store=Store(path);store.close();cancel=threading.Event();cancel.set()
            self.assertIsNone(load_week(path,date(2026,11,9),int(time.time()),cancel=cancel))
            missing=Path(folder)/'missing'
            with self.assertRaises(sqlite3.OperationalError):load_week(missing,date(2026,11,9),int(time.time()))
            self.assertFalse(missing.exists())

if __name__=='__main__':unittest.main()

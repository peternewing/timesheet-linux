"""SQLite quota failures on disposable data, not physical-disk acceptance."""
import sqlite3,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock
from timesheet.store import Store
from timesheet.simple_setup import finish_setup,BUCKETS
from timesheet.local_types import apply
from timesheet import screen_spaces

class StorageRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db');self.now=int(time.time())
        finish_setup(self.store,list(BUCKETS),connected=False,now=self.now-86400)
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def quota(self,*,schedule_write=False):
        with self.store.db:
            self.store.db.execute('CREATE TABLE quota_filler(value BLOB)')
            if schedule_write:
                # Force a real page allocation after schedule insertion. UTC's
                # tiny TZif can fit an existing page, unlike larger local zones.
                self.store.db.execute('CREATE TRIGGER quota_schedule AFTER INSERT ON screen_space_schedules BEGIN INSERT INTO quota_filler VALUES(zeroblob(65536)); END')
        count=self.store.db.execute('PRAGMA page_count').fetchone()[0]
        self.store.db.execute(f'PRAGMA max_page_count={count}')
        while True:
            try:
                with self.store.db:self.store.db.execute('INSERT INTO quota_filler VALUES(zeroblob(4096))')
            except sqlite3.OperationalError as error:
                self.assertEqual(error.sqlite_errorcode,sqlite3.SQLITE_FULL);break
    def release(self):self.store.db.execute('PRAGMA max_page_count=1073741823')
    def test_schedule_full_storage_rolls_back_marker_and_recovers(self):
        screen_spaces.switch(self.store,'personal',self.now-100)
        before=screen_spaces.current(self.store);version=screen_spaces.revision(self.store);self.quota(schedule_write=True)
        with self.assertRaises(sqlite3.OperationalError) as error:screen_spaces.use_schedule(self.store,'weekdays_9_17',self.now)
        self.assertEqual(error.exception.sqlite_errorcode,sqlite3.SQLITE_FULL)
        self.assertEqual(screen_spaces.current(self.store),before);self.assertEqual(screen_spaces.revision(self.store),version)
        self.assertEqual(self.store.rows('SELECT * FROM screen_space_schedules'),[])
        self.release();screen_spaces.use_schedule(self.store,'weekdays_9_17',self.now)
        self.assertEqual(screen_spaces.effective_now(self.store,self.now+1)['source'],'schedule')
        self.assertEqual(self.store.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
    def test_local_allocation_full_storage_has_no_partial_drafts_or_undo(self):
        base=self.now-10000
        with self.store.db:self.store.db.executemany("INSERT INTO activity(start,end,app,state,closed,capture_version) VALUES(?,?,'Browser','active',1,2)",((base+i*2,base+i*2+1) for i in range(2000)))
        catalog=Mock();catalog.lookup.return_value=dict(bucket='browse',categories=['Network','WebBrowser'])
        self.quota();before=self.store.entries(0,self.now);undo=self.store.rows('SELECT * FROM entry_changes')
        with self.assertRaises(sqlite3.OperationalError) as error:apply(self.store,self.now,catalog=catalog)
        self.assertEqual(error.exception.sqlite_errorcode,sqlite3.SQLITE_FULL)
        self.assertEqual(self.store.entries(0,self.now),before);self.assertEqual(self.store.rows('SELECT * FROM local_type_assignments'),[])
        self.assertEqual(self.store.get('local_type_cursor'),'0');self.assertEqual(self.store.rows('SELECT COUNT(*) n FROM activity')[0]['n'],2000)
        self.assertEqual(self.store.rows('SELECT * FROM entry_changes'),undo)
        self.release();self.assertEqual(apply(self.store,self.now,catalog=catalog),50)
        self.assertEqual(self.store.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')

if __name__=='__main__':unittest.main()

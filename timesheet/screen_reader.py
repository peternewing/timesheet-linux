"""Read-only insight snapshots on a separate thread/connection; no migrations."""
import sqlite3
from pathlib import Path
from urllib.parse import quote
from . import screen_time


class Reader:
    def __init__(self,connection):self.db=connection
    def get(self,key,default=''):
        row=self.db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return row[0] if row else default
    def rows(self,sql,args=()):return self.db.execute(sql,args).fetchall()
    def activity_for(self,start,end):
        # Statistics need no window titles or financial data, even locally.
        return [dict(row,start=max(start,row['start']),end=min(end,row['end'])) for row in self.rows(
            'SELECT start,end,app,state,capture_version FROM activity WHERE start<? AND end>? ORDER BY start',(end,start))]


def load_week(path,day,now,space='all',cancel=None):
    connection=sqlite3.connect('file:'+quote(str(Path(path).resolve()))+'?mode=ro',uri=True,timeout=2)
    connection.row_factory=sqlite3.Row;connection.execute('PRAGMA query_only=ON')
    if cancel is not None:connection.set_progress_handler(lambda:int(cancel.is_set()),10000)
    try:
        if cancel is not None and cancel.is_set():return None
        result=screen_time.week(Reader(connection),day,now,space=space)
        # UI/export use aggregate/hourly facts, not copies of every interval.
        for value in result['days']:value.pop('periods',None)
        return result
    finally:connection.close()

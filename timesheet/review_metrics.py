"""Local, content-free review workflow measures; not a measure of AI accuracy."""
import time
from datetime import datetime,timedelta
from .day_record import bounds

SCHEMA='''CREATE TABLE IF NOT EXISTS screen_review_sessions(id INTEGER PRIMARY KEY,started INTEGER NOT NULL,
 finished INTEGER,source TEXT NOT NULL,active_ms INTEGER NOT NULL DEFAULT 0,answered INTEGER NOT NULL DEFAULT 0,
 skipped INTEGER NOT NULL DEFAULT 0,stale INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS screen_review_time ON screen_review_sessions(started);
'''


class Session:
    def __init__(self,store,source='daily',*,clock=time.monotonic,now=None):
        if source not in ('daily','correction'):raise ValueError('Choose a review source.')
        self.store=store;self.clock=clock;self.last=clock();self.active=False;self.milliseconds=0;self.closed=False
        with store.db:self.id=store.db.execute('INSERT INTO screen_review_sessions(started,source) VALUES(?,?)',(int(time.time() if now is None else now),source)).lastrowid
    def observe(self,active):
        now=self.clock();elapsed=now-self.last
        if self.active and active and 0<=elapsed<=5:self.milliseconds+=int(elapsed*1000)
        self.active=bool(active);self.last=now
    def answer(self,action):
        if action not in ('answered','skipped','stale'):raise ValueError('Choose a review action.')
        if self.closed:return
        with self.store.db:self.store.db.execute('UPDATE screen_review_sessions SET '+action+'='+action+'+1 WHERE id=?',(self.id,))
    def finish(self,now=None):
        if self.closed:return
        self.closed=True
        with self.store.db:self.store.db.execute('UPDATE screen_review_sessions SET finished=?,active_ms=? WHERE id=?',(int(time.time() if now is None else now),self.milliseconds,self.id))


def summary(store,day=None):
    day=day or datetime.now().date();start,_=bounds(day-timedelta(days=6));_,end=bounds(day)
    row=store.db.execute('''SELECT COUNT(*) sessions,COALESCE(SUM(active_ms),0) active_ms,
        COALESCE(SUM(answered),0) answered,COALESCE(SUM(skipped),0) skipped,COALESCE(SUM(stale),0) stale
        FROM screen_review_sessions WHERE started>=? AND started<? AND finished IS NOT NULL''',(start,end)).fetchone()
    return dict(row)


def text(store):
    value=summary(store);seconds=value['active_ms']//1000
    return (f"Simple activity reviews, last seven days: {value['answered']} choices answered · {value['skipped']} left uncategorised · {value['stale']} stale choices. "
        f"{seconds//60}m {seconds%60:02d}s with a review window active. "
        'These are local workflow counts, not cognitive effort or AI accuracy. Inactive windows and long/suspend gaps are excluded. No app names or review text are stored here.')

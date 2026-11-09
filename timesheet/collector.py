"""Durable desktop collection with explicit gaps, privacy filters and idle boundaries."""
from __future__ import annotations
import fcntl
import json
import os
import signal
import sqlite3
import time
import uuid
from pathlib import Path
from .store import Store, DATA_DIR
from gi.repository import Gio, GLib

stopping = False

def shutdown(*_):
    global stopping
    stopping = True


from .capture import Capture, screen_locked

_capture = None

def get_focus():
    global _capture
    if _capture is None: _capture = Capture()
    return _capture.sample()


class Collector:
    def __init__(self, store):
        self.store = store
        self.session = uuid.uuid4().hex
        self.open_id = None
        self.open_start = None
        self.focus = None
        self.last_wall = None
        self.last_mono = None
        self.source_since = None
        self.was_connected = False
        self.last_rules = 0
        self.failed = False
        # An abandoned interval ends at its last durable sample, never at restart.
        with store.db:
            store.db.execute('UPDATE activity SET closed=1 WHERE closed=0')
        rt = store.runtime()
        if rt['state'] == 'running':
            store.stop_timer(rt['checkpoint'] or rt['started'], 'recovered after interruption')
            with store.db:
                store.notice('Tracking was interrupted. The last saved timer was recovered; check the missing period.')

    def close(self, end=None):
        if self.open_id is not None:
            with self.store.db:
                if end is not None:
                    self.store.db.execute('UPDATE activity SET end=MAX(start+1,MIN(end,?)),closed=1 WHERE id=?', (int(end), self.open_id))
                else:
                    self.store.db.execute('UPDATE activity SET closed=1 WHERE id=?', (self.open_id,))
        self.open_id = self.open_start = self.focus = None

    def record(self, start, end, focus):
        start, end = int(start), int(end)
        if end <= start:
            return
        with self.store.db:
            if self.open_id is not None and focus == self.focus and self.open_start is not None and end-self.open_start < 60:
                self.store.db.execute('UPDATE activity SET end=? WHERE id=?', (end,self.open_id))
            else:
                if self.open_id is not None:
                    self.store.db.execute('UPDATE activity SET closed=1 WHERE id=?',(self.open_id,))
                self.open_id = self.store.db.execute(
                    'INSERT INTO activity(start,end,app,title,state,closed,session,capture_version) VALUES(?,?,?,?,?,0,?,2)',
                    (start,end,*focus,self.session)).lastrowid
                self.open_start = start
                self.focus = focus

    def mark_away(self, cutoff, end):
        self.close(end)
        with self.store.db:
            rows=self.store.rows("SELECT * FROM activity WHERE state='active' AND session=? AND end>? AND start<? ORDER BY start",(self.session,int(cutoff),int(end)))
            for row in rows:
                boundary=max(row['start'],int(cutoff))
                if boundary>row['start']:
                    self.store.db.execute('UPDATE activity SET end=? WHERE id=?',(boundary,row['id']))
                    self.store.db.execute("INSERT INTO activity(start,end,app,title,state,session) VALUES(?,?,'','','away',?)",(boundary,row['end'],self.session))
                else:
                    self.store.db.execute("UPDATE activity SET app='',title='',state='away',auto_processed=1 WHERE id=?",(row['id'],))

    def step(self, now, mono, state):
        rt = self.store.runtime()
        if self.failed:
            self.close(rt['checkpoint'])
            if rt['state']=='running': self.store.stop_timer(rt['checkpoint'] or rt['started'],'storage interruption')
            self.last_wall = self.last_mono = None
            self.was_connected = False
            self.failed = False
        previous = self.last_wall
        discontinuity = previous is not None and (now-previous>10 or now<previous or abs((now-previous)-(mono-self.last_mono))>3)
        if discontinuity:
            self.close(previous)
            if rt['state']=='running': self.store.stop_timer(rt['checkpoint'] or rt['started'],'sleep or clock change')
            if now>previous:
                self.record(previous,now,('','','unknown'))
                self.close()
            self.was_connected = False
            self.source_since = None
        enabled=self.store.get('capture_enabled','0')=='1'
        until=int(self.store.get('pause_until','0') or 0)
        if not enabled and until and now>=until:
            self.store.set('capture_enabled','1'); self.store.set('pause_until','0'); enabled=True
        dt_start = now if previous is None or discontinuity else previous
        status='paused'; app=''; activity_state='paused'
        if enabled and state is not None:
            app,title,idle,locked=state
            if not self.was_connected: self.source_since=dt_start
            threshold=int(self.store.get('idle_seconds','300'))*1000
            activity_state='locked' if locked else 'unknown' if idle<0 else 'away' if idle>=threshold else 'active'
            excluded={x.strip().casefold() for x in self.store.get('excluded_apps','').split(',') if x.strip()}
            # Exclusion conceals active foreground use; it must not turn idle or
            # locked time into apparent screen time merely because that app remains focused.
            if activity_state=='active' and app.casefold() in excluded: activity_state='excluded'
            if not app and activity_state=='active': activity_state='unknown'
            if activity_state!='active': app=title=''
            elif self.store.get('capture_titles','0')!='1': title=''
            status='active' if idle>=0 else 'degraded'
            if rt['state']=='running' and activity_state!='active':
                boundary=int(now)
                if activity_state=='away': boundary=max(rt['started'],int(now-idle/1000))
                self.store.stop_timer(boundary,'away, locked or excluded')
            if activity_state=='away' and self.focus and self.focus[2]=='active':
                self.mark_away(max(self.source_since or dt_start,now-idle/1000),now)
            self.record(dt_start,now,(app,title,activity_state))
            self.was_connected=True
        elif enabled:
            if self.was_connected:
                self.close(previous)
                if rt['state']=='running': self.store.stop_timer(rt['checkpoint'] or rt['started'],'capture source disconnected')
            self.was_connected=False; self.source_since=None
            status='setup_required'; activity_state='unknown'
            self.record(dt_start,now,('','','unknown'))
            if rt['state']=='running' and screen_locked(): self.store.stop_timer(previous or now,'screen locked')
        else:
            pause_at=int(self.store.get('pause_at','0') or 0)
            self.close(pause_at if pause_at and previous and pause_at>=previous else previous)
            self.was_connected=False; self.source_since=None
            if rt['state']=='running' and screen_locked(): self.store.stop_timer(previous or now,'screen locked')
        with self.store.db:
            self.store.db.execute("UPDATE runtime SET collector_seen=?,capture_status=?,app=?,activity_state=?,last_error='',checkpoint=CASE WHEN state='running' THEN ? ELSE checkpoint END WHERE id=1",(int(now),status,app,activity_state,int(now)))
        self.last_wall,self.last_mono=now,mono
        if now-self.last_rules>=10:
            from .daily_choices import apply_saved
            apply_saved(self.store,now)
            self.store.apply_rules(now)
            from .local_types import apply as apply_local_types
            apply_local_types(self.store,now)
            self.last_rules=now
        return status


def health(status, error=''):
    # This small independent status file remains useful when SQLite cannot write.
    target=DATA_DIR/'health.json'; temp=target.with_suffix('.tmp')
    try:
        temp.write_text(json.dumps(dict(at=int(time.time()),status=status,error=error)),encoding='utf-8')
        os.chmod(temp,0o600); os.replace(temp,target)
    except OSError:
        pass


def should_notify(previous,status,enabled):
    return enabled and previous=='active' and status in ('degraded','setup_required','stopped','error')

def notify_tracking_problem():
    """Best-effort, content-free desktop alert from the background collector."""
    try:
        bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        bus.call_sync('org.freedesktop.Notifications','/org/freedesktop/Notifications',
            'org.freedesktop.Notifications','Notify',
            GLib.Variant('(susssasa{sv}i)',('Time Sheet Linux',0,'','Tracking needs attention',
                'Automatic tracking may be incomplete. Open Time Sheet Linux to check its status.',[],{},-1)),
            GLib.VariantType.new('(u)'),Gio.DBusCallFlags.NONE,500,None)
    except GLib.Error:
        pass

def maintenance(store, now):
    with store.db:
        store.db.execute('DELETE FROM activity WHERE closed=1 AND end<?',(int(now)-int(store.get('retention_days','30'))*86400,))
        store.db.execute('DELETE FROM local_type_suppressions WHERE NOT EXISTS(SELECT 1 FROM activity a WHERE a.id=local_type_suppressions.activity_id)')
        store.db.execute('DELETE FROM screen_review_sessions WHERE started<?',(int(now)-int(store.get('retention_days','30'))*86400,))
    if store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ai_jobs'").fetchone():
        from .automation_store import Repository
        Repository(store).prune(now)
    if store.get('auto_backup','1')=='1':
        folder=DATA_DIR/'backups'; folder.mkdir(mode=0o700,exist_ok=True)
        stamp=time.strftime('%Y-%m-%d',time.localtime(now)); target=folder/(stamp+'.sqlite3')
        if not target.exists() or now-target.stat().st_mtime>=3600:
            temp=folder/(stamp+'.tmp')
            temp.unlink(missing_ok=True)
            store.backup(temp); os.replace(temp,target)
            for old in sorted(folder.glob('*.sqlite3'))[:-7]: old.unlink()


def run():
    global stopping, _capture
    stopping=False
    DATA_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
    lock=open(DATA_DIR/'collector.lock','a+')
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: return
    pidfile=DATA_DIR/'collector.pid'; pidfile.write_text(str(os.getpid())); os.chmod(pidfile,0o600)
    signal.signal(signal.SIGTERM,shutdown); signal.signal(signal.SIGINT,shutdown)
    store=Store(); collector=Collector(store); last_maintenance=0; last_status=None; notifications_enabled=False
    try:
        while not stopping:
            now=time.time()
            try:
                notifications_enabled=store.get('tracking_notifications','0')=='1'
                enabled=store.get('capture_enabled','0')=='1' or int(store.get('pause_until','0') or 0)
                if not enabled and _capture is not None:
                    _capture.close(); _capture=None
                state=get_focus() if enabled else None
                status=collector.step(now,time.monotonic(),state)
                health(status)
                if should_notify(last_status,status,notifications_enabled): notify_tracking_problem()
                last_status=status
                if now-last_maintenance>3600:
                    maintenance(store,now); last_maintenance=now
            except (sqlite3.Error,OSError) as exc:
                if store.db.in_transaction: store.db.rollback()
                collector.failed=True
                health('error','Storage unavailable. Unsaved time will need review.')
                if should_notify(last_status,'error',notifications_enabled): notify_tracking_problem()
                last_status='error'
                # Error text intentionally excludes paths, titles and content.
            time.sleep(max(.01,1-time.time()%1))
    finally:
        try:
            collector.close()
            rt=store.runtime()
            if rt['state']=='running': store.stop_timer(rt['checkpoint'] or rt['started'],'collector stopped')
            with store.db: store.db.execute("UPDATE runtime SET collector_seen=NULL,capture_status='stopped' WHERE id=1")
            health('stopped')
        finally:
            store.close()
            try: pidfile.unlink()
            except FileNotFoundError: pass
            lock.close()
            if _capture is not None: _capture.close()

if __name__=='__main__': run()

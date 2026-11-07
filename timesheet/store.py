"""SQLite persistence and accounting rules for the local timesheet."""
from __future__ import annotations
import csv
import html
import io
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

DATA_DIR = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'time-sheet-linux'
DB_PATH = DATA_DIR / 'timesheet.sqlite3'
SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS clients(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, currency TEXT NOT NULL DEFAULT 'GBP', rate INTEGER, archived INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY, client_id INTEGER NOT NULL REFERENCES clients(id), name TEXT NOT NULL, budget INTEGER, rate INTEGER, archived INTEGER NOT NULL DEFAULT 0, UNIQUE(client_id,name));
CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id), name TEXT NOT NULL, budget INTEGER, rate INTEGER, archived INTEGER NOT NULL DEFAULT 0, UNIQUE(project_id,name));
CREATE TABLE IF NOT EXISTS entries(id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id), start INTEGER NOT NULL, end INTEGER NOT NULL, description TEXT NOT NULL DEFAULT '', billable INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'draft', rate INTEGER, currency TEXT, invoice TEXT, revision INTEGER NOT NULL DEFAULT 1, CHECK(end > start));
CREATE INDEX IF NOT EXISTS entries_time ON entries(start,end);
CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY, start INTEGER NOT NULL, end INTEGER NOT NULL, app TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'active', CHECK(end > start));
CREATE INDEX IF NOT EXISTS activity_time ON activity(start,end);
CREATE TABLE IF NOT EXISTS rules(id INTEGER PRIMARY KEY, app TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', task_id INTEGER NOT NULL REFERENCES tasks(id), priority INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at INTEGER NOT NULL, action TEXT NOT NULL, details TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY, created INTEGER NOT NULL, client_id INTEGER NOT NULL REFERENCES clients(id), start INTEGER NOT NULL, end INTEGER NOT NULL, snapshot TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS report_entries(report_id INTEGER NOT NULL REFERENCES reports(id), entry_id INTEGER NOT NULL REFERENCES entries(id), revision INTEGER NOT NULL, PRIMARY KEY(report_id,entry_id));
CREATE TABLE IF NOT EXISTS runtime(id INTEGER PRIMARY KEY CHECK(id=1), task_id INTEGER REFERENCES tasks(id), started INTEGER, checkpoint INTEGER, state TEXT NOT NULL DEFAULT 'stopped', collector_seen INTEGER, capture_status TEXT NOT NULL DEFAULT 'not running');
INSERT OR IGNORE INTO runtime(id) VALUES(1);
'''

class Store:
    def _migrate(self):
        version=self.db.execute('PRAGMA user_version').fetchone()[0]
        if version>3:
            raise ValueError('This database was created by a newer version of Time Sheet Linux.')
        if version<3:
            # A consistent pre-migration copy is retained for existing user data.
            if self.db.execute('SELECT COUNT(*) FROM entries').fetchone()[0]:
                dest=self.path.with_name(self.path.stem+'-before-v3.sqlite3')
                if not dest.exists(): self.backup(dest)
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                additions={
                    'entries': [('deleted','INTEGER NOT NULL DEFAULT 0'),('origin',"TEXT NOT NULL DEFAULT 'manual'"),('activity_id','INTEGER')],
                    'activity': [('closed','INTEGER NOT NULL DEFAULT 1'),('auto_processed','INTEGER NOT NULL DEFAULT 0'),('session',"TEXT NOT NULL DEFAULT ''")],
                    'rules': [('created','INTEGER NOT NULL DEFAULT 0')],
                    'runtime': [('app',"TEXT NOT NULL DEFAULT ''"),('activity_state',"TEXT NOT NULL DEFAULT 'unknown'"),('last_error',"TEXT NOT NULL DEFAULT ''")],
                }
                for table,columns in additions.items():
                    present={r[1] for r in self.db.execute('PRAGMA table_info('+table+')')}
                    for name,typ in columns:
                        if name not in present: self.db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {typ}')
                self.db.execute('CREATE TABLE IF NOT EXISTS entry_changes(id INTEGER PRIMARY KEY,at INTEGER NOT NULL,action TEXT NOT NULL,before_state TEXT NOT NULL,after_state TEXT NOT NULL,undone INTEGER NOT NULL DEFAULT 0)')
                self.db.execute('CREATE TABLE IF NOT EXISTS notices(id INTEGER PRIMARY KEY,at INTEGER NOT NULL,message TEXT NOT NULL,read INTEGER NOT NULL DEFAULT 0)')
                self.db.execute("CREATE TABLE IF NOT EXISTS report_billing(report_id INTEGER PRIMARY KEY REFERENCES reports(id),invoice TEXT NOT NULL,at INTEGER NOT NULL,state TEXT NOT NULL DEFAULT 'billed',reason TEXT NOT NULL DEFAULT '')")
                self.db.execute('PRAGMA user_version=3')

    def notice(self,message):
        self.db.execute('INSERT INTO notices(at,message) VALUES(?,?)',(int(time.time()),message))

    def _record_change(self,action,before,after_ids):
        after=[dict(self.db.execute('SELECT * FROM entries WHERE id=?',(i,)).fetchone()) for i in after_ids]
        self.db.execute('INSERT INTO entry_changes(at,action,before_state,after_state) VALUES(?,?,?,?)',
                        (int(time.time()),action,json.dumps([dict(r) for r in before]),json.dumps(after)))

    def quick_project(self,client,project,task='General',rate=None,currency='GBP',budget=None):
        if not client.strip() or not project.strip() or not task.strip(): raise ValueError('Enter a client, project and task name.')
        if currency not in ('GBP','EUR','USD'): raise ValueError('Choose GBP, EUR or USD.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            c=self.db.execute('SELECT * FROM clients WHERE name=?',(client.strip(),)).fetchone()
            if c and c['archived']: raise ValueError('This client is archived. Unarchive it in Projects or choose another client name.')
            if c and (c['currency']!=currency or (rate is not None and c['rate']!=rate)):
                raise ValueError('This client already has different billing settings. Use Add project under that client in Projects, or choose a new client name.')
            cid=c[0] if c else self.db.execute('INSERT INTO clients(name,currency,rate) VALUES(?,?,?)',(client.strip(),currency,rate)).lastrowid
            p=self.db.execute('SELECT id FROM projects WHERE client_id=? AND name=?',(cid,project.strip())).fetchone()
            if p: raise ValueError('This project already exists for the client. Edit it or add a task in Projects.')
            pid=p[0] if p else self.db.execute('INSERT INTO projects(client_id,name,budget) VALUES(?,?,?)',(cid,project.strip(),budget)).lastrowid
            existing=self.db.execute('SELECT id FROM tasks WHERE project_id=? AND name=?',(pid,task.strip())).fetchone()
            tid=existing[0] if existing else self.db.execute('INSERT INTO tasks(project_id,name) VALUES(?,?)',(pid,task.strip())).lastrowid
            self.audit('project set up',{'task_id':tid})
            return tid

    def uncovered(self,start,end,now=None):
        """Unallocated subintervals; manual timers reserve their live interval."""
        intervals=[(r['start'],r['end']) for r in self.rows('SELECT start,end FROM entries WHERE deleted=0 AND start<? AND end>? ORDER BY start',(end,start))]
        rt=self.runtime()
        if rt['state']=='running' and rt['started'] is not None:
            intervals.append((rt['started'],int(time.time() if now is None else now)))
        cursor=int(start); result=[]
        for a,b in sorted(intervals):
            if b<=cursor: continue
            if a>=end: break
            if a>cursor: result.append((cursor,min(a,end)))
            cursor=max(cursor,b)
            if cursor>=end: break
        if cursor<end: result.append((cursor,int(end)))
        return [(a,b) for a,b in result if b>a]

    def activity_for(self,start,end,unassigned=False):
        result=[]
        for row in self.rows('SELECT * FROM activity WHERE start<? AND end>? ORDER BY start',(int(end),int(start))):
            record=dict(row); record['start']=max(row['start'],int(start)); record['end']=min(row['end'],int(end))
            if unassigned and row['state']=='active':
                for a,b in self.uncovered(record['start'],record['end']):
                    result.append(dict(record,start=a,end=b))
            elif not unassigned: result.append(record)
        return result

    def day_summary(self,start,end,include_running=False,now=None):
        entries=self.entries(start,end)
        assigned=sum(min(end,r['end'])-max(start,r['start']) for r in entries)
        if include_running:
            rt=self.runtime()
            if rt['state']=='running' and rt['started'] is not None:
                a=max(start,rt['started']); z=min(end,int(time.time() if now is None else now))
                if z>a:
                    # Future manual entries may overlap a still-running timer. Do
                    # not count that time twice; stop_timer will clip it too.
                    assigned+=z-a-sum(max(0,min(z,r['end'])-max(a,r['start'])) for r in entries)
        active=0; away=0; unassigned=0; apps={}
        for r in self.activity_for(start,end):
            seconds=r['end']-r['start']
            if r['state'] in ('active','personal'):
                active+=seconds; apps[r['app']]=apps.get(r['app'],0)+seconds
                if r['state']=='active': unassigned+=sum(b-a for a,b in self.uncovered(r['start'],r['end']))
            elif r['state'] in ('away','locked'): away+=seconds
        approved=sum(min(end,r['end'])-max(start,r['start']) for r in entries if r['status'] in ('approved','billed'))
        return dict(active=active,away=away,assigned=assigned,approved=approved,unassigned=unassigned,
                    drafts=sum(r['status']=='draft' for r in entries),apps=sorted(apps.items(),key=lambda pair:pair[1],reverse=True))

    def set_personal(self,ids,personal=True):
        if not ids: raise ValueError('Select completed activity first.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            for aid in set(ids):
                r=self.db.execute('SELECT * FROM activity WHERE id=?',(aid,)).fetchone()
                if not r or not r['closed'] or r['state'] not in ('active','personal'): raise ValueError('Choose completed application usage.')
                if personal and sum(b-a for a,b in self.uncovered(r['start'],r['end']))!=r['end']-r['start']: raise ValueError('Some of this activity is already assigned. Edit its task entry first.')
                self.db.execute('UPDATE activity SET state=?,auto_processed=1 WHERE id=?',('personal' if personal else 'active',aid))
            self.audit('activity marked personal' if personal else 'activity returned to review',{'count':len(set(ids))})

    def matching_rule(self,app,title,at=None):
        choices=[]
        for r in self.rows('''SELECT r.* FROM rules r JOIN tasks t ON r.task_id=t.id JOIN projects p ON t.project_id=p.id
              JOIN clients c ON p.client_id=c.id WHERE r.enabled=1 AND t.archived=0 AND p.archived=0 AND c.archived=0 ORDER BY r.priority DESC,r.id'''):
            if at is not None and r['created']>at: continue
            if r['app'].casefold()==app.casefold() and r['title'].casefold() in title.casefold(): choices.append(r)
        if not choices: return None
        best=[r for r in choices if r['priority']==choices[0]['priority']]
        targets={r['task_id'] for r in best}
        return best[0] if len(targets)==1 else None

    def matching_task(self,app,title):
        rule=self.matching_rule(app,title)
        return rule['task_id'] if rule else None

    def add_rule(self,app,title,task,priority=0):
        if not app.strip(): raise ValueError('Choose an application.')
        with self.db:
            rid=self.db.execute('INSERT INTO rules(app,title,task_id,priority,created) VALUES(?,?,?,?,?)',(app.strip(),title.strip(),task,int(priority),int(time.time()))).lastrowid
            self.audit('rule created',{'id':rid})
            return rid

    def apply_rules(self,now=None,start=None,end=None):
        now=int(time.time() if now is None else now)
        cutoff=now-int(self.get('idle_seconds','300'))
        count=0
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if start is not None:
                self.db.execute("UPDATE activity SET auto_processed=0 WHERE state='active' AND closed=1 AND start>=? AND end<=?",(start,end or now))
            rows=self.rows("SELECT * FROM activity WHERE state='active' AND closed=1 AND auto_processed=0 AND end<=? ORDER BY start",(cutoff,))
            for r in rows:
                rule=self.matching_rule(r['app'],r['title'],None if start is not None else r['end'])
                if rule:
                    beginning=r['start'] if start is not None else max(r['start'],rule['created'])
                    for a,b in self.uncovered(beginning,r['end'],now):
                        self.db.execute("INSERT INTO entries(task_id,start,end,description,origin,activity_id) VALUES(?,?,?,'','automatic',?)",(rule['task_id'],a,b,r['id']))
                        count+=1
                self.db.execute('UPDATE activity SET auto_processed=1 WHERE id=?',(r['id'],))
            if count: self.audit('automatically assigned',{'entries':count})
        return count

    def assign_remaining(self,blocks,task,description='',remember=False):
        count=0
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            before=[]; ids=[]
            for block in blocks:
                original=self.db.execute('SELECT * FROM activity WHERE id=?',(block['id'],)).fetchone()
                if not original or original['state'] not in ('active','away'): raise ValueError('Activity is no longer available.')
                if not original['closed']: raise ValueError('This activity is still being recorded. Assign it once you switch apps or pause.')
                a=max(block['start'],original['start']); b=min(block['end'],original['end'])
                for x,y in self.uncovered(a,b):
                    cur=self.db.execute("INSERT INTO entries(task_id,start,end,description,origin,activity_id) VALUES(?,?,?,?,'assigned',?)",(task,x,y,description.strip(),original['id']))
                    ids.append(cur.lastrowid); count+=1
                if remember and original['state']=='active':
                    exists=self.db.execute("SELECT 1 FROM rules WHERE lower(app)=lower(?) AND title='' AND task_id=? AND enabled=1",(original['app'],task)).fetchone()
                    if not exists: self.db.execute('INSERT INTO rules(app,title,task_id,priority,created) VALUES(?,?,?,?,?)',(original['app'],'',task,0,int(time.time())))
            if not count: raise ValueError('This activity is already assigned to a task.')
            self._record_change('Assign activity',before,ids)
            self.audit('activity assigned',{'entries':count})
        return count

    def approve_many(self,ids):
        if not ids: raise ValueError('Select at least one draft entry.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            for entry in dict.fromkeys(ids): self._approve_one(entry)

    def _approve_one(self,entry):
        row=self.db.execute('''SELECT e.*,COALESCE(t.rate,p.rate,c.rate) effective_rate,c.currency client_currency
                FROM entries e JOIN tasks t ON e.task_id=t.id JOIN projects p ON t.project_id=p.id
                JOIN clients c ON p.client_id=c.id WHERE e.deleted=0 AND e.id=?''',(entry,)).fetchone()
        if not row or row['status']!='draft': raise ValueError('Only draft entries can be approved.')
        if row['end']>time.time(): raise ValueError('Future time cannot be approved.')
        if row['origin'] in ('automatic','assigned'):
            activity=self.db.execute('SELECT * FROM activity WHERE id=?',(row['activity_id'],)).fetchone()
            if activity and (not activity['closed'] or activity['end']>time.time()-int(self.get('idle_seconds','300'))):
                raise ValueError('Recent activity is still settling. Review it after the idle threshold, or enter it explicitly as manual work.')
        if row['billable'] and row['effective_rate'] is None: raise ValueError('Set an hourly rate or mark this entry non-billable before approval.')
        self.db.execute("UPDATE entries SET status='approved',rate=?,currency=?,revision=revision+1 WHERE id=?",(row['effective_rate'],row['client_currency'],entry))
        self.audit('entry approved',{'id':entry})

    def merge_entries(self,ids):
        if len(set(ids))<2: raise ValueError('Select at least two adjacent entries.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            rows=[self.db.execute('SELECT * FROM entries WHERE deleted=0 AND id=?',(i,)).fetchone() for i in set(ids)]
            if any(r is None for r in rows): raise ValueError('An entry has changed. Refresh the list.')
            rows.sort(key=lambda r:r['start'])
            if any(r['status']=='billed' for r in rows): raise ValueError('Billed entries cannot be merged.')
            if len({(r['task_id'],r['billable']) for r in rows})!=1: raise ValueError('Choose entries for the same task and billable setting.')
            if any(a['end']!=b['start'] for a,b in zip(rows,rows[1:])): raise ValueError('Entries must be adjacent without a gap.')
            first=rows[0]
            description='; '.join(dict.fromkeys(r['description'] for r in rows if r['description']))
            self.db.execute("UPDATE entries SET end=?,description=?,origin='manual',activity_id=NULL,status='draft',rate=NULL,currency=NULL,revision=revision+1 WHERE id=?",(rows[-1]['end'],description,first['id']))
            for r in rows[1:]: self.db.execute('UPDATE entries SET deleted=1,revision=revision+1 WHERE id=?',(r['id'],))
            self._record_change('Merge entries',rows,[r['id'] for r in rows])
            self.audit('entries merged',{'id':first['id'],'count':len(rows)})

    def undo(self):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            change=self.db.execute('SELECT * FROM entry_changes WHERE undone=0 ORDER BY id DESC LIMIT 1').fetchone()
            if not change: raise ValueError('There is no change to undo.')
            before=json.loads(change['before_state']); after=json.loads(change['after_state'])
            revisions={}
            for expected in after:
                current=self.db.execute('SELECT * FROM entries WHERE id=?',(expected['id'],)).fetchone()
                same=current and {k:v for k,v in dict(current).items() if k!='revision'}=={k:v for k,v in expected.items() if k!='revision'}
                if not same or current['status']=='billed': raise ValueError('These entries changed after that action. Undo is unavailable.')
                revisions[current['id']]=current['revision']
            self.db.executemany('UPDATE entries SET deleted=1 WHERE id=?',[(r['id'],) for r in after])
            original_ids={r['id'] for r in before}
            for r in before:
                if not r['deleted']: self._assert_free(r['start'],r['end'])
                values={k:v for k,v in r.items() if k!='id'}
                values.update(status='draft',rate=None,currency=None,revision=revisions[r['id']]+1)
                self.db.execute('UPDATE entries SET '+','.join(k+'=?' for k in values)+' WHERE id=?',(*values.values(),r['id']))
            for r in after:
                if r['id'] not in original_ids: self.db.execute('UPDATE entries SET revision=revision+1 WHERE id=?',(r['id'],))
            self.db.execute('UPDATE entry_changes SET undone=1 WHERE id=?',(change['id'],))
            self.audit('undone',{'action':change['action']})
            return change['action']
    def __init__(self, path=None):
        path = Path(path or DB_PATH)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not path.exists():
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            except FileExistsError:
                pass
        os.chmod(path,0o600)
        self.path = path
        self.db = sqlite3.connect(path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA busy_timeout=10000')
        self.db.executescript(SCHEMA)
        self.db.commit()
        self._migrate()

    def close(self): self.db.close()
    def rows(self, query, args=()): return self.db.execute(query, args).fetchall()
    def get(self, key, default=''): 
        row = self.db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return row[0] if row else default
    def set(self, key, value):
        with self.db: self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,str(value)))
    def audit(self, action, details):
        self.db.execute('INSERT INTO audit(at,action,details) VALUES(?,?,?)',(int(time.time()),action,json.dumps(details)))
    def add_client(self,name,currency='GBP',rate=None):
        if not name.strip(): raise ValueError('Enter a client name.')
        if currency.strip().upper() not in ('GBP','EUR','USD'): raise ValueError('Choose GBP, EUR or USD; other currency precision is not yet supported.')
        with self.db:
            cur=self.db.execute('INSERT INTO clients(name,currency,rate) VALUES (?,?,?)',(name.strip(),currency.upper(),rate)); self.audit('client created',{'id':cur.lastrowid}); return cur.lastrowid
    def add_project(self,client,name,budget=None,rate=None):
        if not name.strip(): raise ValueError('Enter a project name.')
        with self.db:
            cur=self.db.execute('INSERT INTO projects(client_id,name,budget,rate) VALUES (?,?,?,?)',(client,name.strip(),budget,rate)); self.audit('project created',{'id':cur.lastrowid}); return cur.lastrowid
    def add_task(self,project,name,budget=None,rate=None):
        if not name.strip(): raise ValueError('Enter a task name.')
        with self.db:
            cur=self.db.execute('INSERT INTO tasks(project_id,name,budget,rate) VALUES (?,?,?,?)',(project,name.strip(),budget,rate)); self.audit('task created',{'id':cur.lastrowid}); return cur.lastrowid
    def tasks(self):
        return self.rows('''SELECT t.id, c.name AS client, p.name AS project, t.name AS task, t.budget,
            COALESCE((SELECT SUM(e.end-e.start) FROM entries e WHERE e.task_id=t.id AND e.deleted=0),0) AS spent,
            c.currency, COALESCE(t.rate,p.rate,c.rate) AS effective_rate FROM tasks t
            JOIN projects p ON p.id=t.project_id JOIN clients c ON c.id=p.client_id
            WHERE t.archived=0 AND p.archived=0 AND c.archived=0 ORDER BY c.name,p.name,t.name''')
    def _assert_free(self,start,end,exclude=None):
        if int(end) <= int(start): raise ValueError('End time must be after start time.')
        if self.db.execute('SELECT 1 FROM entries WHERE deleted=0 AND start < ? AND end > ? AND id != ? LIMIT 1',(end,start,exclude or -1)).fetchone():
            raise ValueError('This time overlaps an existing entry. Adjust or split it first.')
        rt=self.db.execute('SELECT * FROM runtime WHERE id=1').fetchone()
        if rt['state']=='running' and rt['started'] is not None and end > rt['started'] and start < max(int(time.time()),rt['started']+1):
            raise ValueError('This time overlaps the running timer. Stop it first.')
    def add_entry(self,task,start,end,description='',billable=True):
        start,end=int(start),int(end)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self._assert_free(start,end)
            cur=self.db.execute('INSERT INTO entries(task_id,start,end,description,billable) VALUES (?,?,?,?,?)',(task,start,end,description.strip(),int(billable)))
            self.audit('entry created',{'id':cur.lastrowid}); self._record_change('Add entry',[],[cur.lastrowid]); return cur.lastrowid
    def update_entry(self,entry,task,start,end,description,billable,expected_revision=None):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            old=self.db.execute('SELECT * FROM entries WHERE deleted=0 AND id=?',(entry,)).fetchone()
            if not old: raise ValueError('Entry not found.')
            if expected_revision is not None and old['revision']!=expected_revision: raise ValueError('This entry changed while you were editing it. Reopen it to see the latest version.')
            if old['status']=='billed': raise ValueError('Billed entries are locked. Keep this entry and record a separate correction.')
            self._assert_free(int(start),int(end),entry)
            self.db.execute("UPDATE entries SET task_id=?,start=?,end=?,description=?,billable=?,origin='manual',activity_id=NULL,status='draft',rate=NULL,currency=NULL,revision=revision+1 WHERE id=?",(task,int(start),int(end),description.strip(),int(billable),entry))
            self.audit('entry edited',{'id':entry})
            self._record_change('Edit entry',[old],[entry])
    def delete_entry(self,entry):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            old=self.db.execute('SELECT * FROM entries WHERE deleted=0 AND id=?',(entry,)).fetchone()
            if not old: raise ValueError('Entry not found.')
            if old['status']=='billed': raise ValueError('Billed entries are locked.')
            if self.db.execute('SELECT 1 FROM report_entries WHERE entry_id=?',(entry,)).fetchone(): raise ValueError('This entry belongs to a saved report and cannot be deleted. Edit it instead.')
            self.audit('entry deleted',{'id':entry})
            self.db.execute("UPDATE entries SET deleted=1,revision=revision+1 WHERE id=?",(entry,))
            self._record_change('Delete entry',[old],[entry])
    def split_entry(self,entry,point):
        point=int(point)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            old=self.db.execute('SELECT * FROM entries WHERE deleted=0 AND id=?',(entry,)).fetchone()
            if not old: raise ValueError('Entry not found.')
            if old['status']=='billed': raise ValueError('Billed entries are locked.')
            if not old['start'] < point < old['end']: raise ValueError('Split time must be inside the entry.')
            self.db.execute("UPDATE entries SET end=?,status='draft',rate=NULL,currency=NULL,revision=revision+1 WHERE id=?",(point,entry))
            cur=self.db.execute('INSERT INTO entries(task_id,start,end,description,billable) VALUES(?,?,?,?,?)',
                (old['task_id'],point,old['end'],old['description'],old['billable']))
            self.audit('entry split',{'id':entry,'new_id':cur.lastrowid})
            self._record_change('Split entry',[old],[entry,cur.lastrowid])
            return cur.lastrowid
    def assign_activity_batch(self,ids,task,description=''):
        if not ids: raise ValueError('Select one or more activity blocks.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            for activity_id in dict.fromkeys(ids):
                r=self.db.execute('SELECT * FROM activity WHERE id=?',(activity_id,)).fetchone()
                if not r or r['state']!='active': raise ValueError('Activity is no longer available for assignment.')
                self._assert_free(r['start'],r['end'])
                self.db.execute('INSERT INTO entries(task_id,start,end,description) VALUES(?,?,?,?)',(task,r['start'],r['end'],description.strip()))
            self.audit('activity assigned',{'count':len(set(ids)),'task_id':task})
    def entries(self,start,end,client=None,status=None,search=''):
        sql='''SELECT e.*, t.name AS task, p.name AS project, c.name AS client, c.id AS client_id,
                 COALESCE(t.rate,p.rate,c.rate) AS suggested_rate,c.currency AS client_currency
                 FROM entries e JOIN tasks t ON t.id=e.task_id JOIN projects p ON p.id=t.project_id
                 JOIN clients c ON c.id=p.client_id WHERE e.deleted=0 AND e.start < ? AND e.end > ?'''
        args=[int(end),int(start)]
        if client: sql+=' AND c.id=?'; args.append(client)
        if status: sql+=' AND e.status=?'; args.append(status)
        if search: sql+=' AND (e.description LIKE ? OR c.name LIKE ? OR p.name LIKE ? OR t.name LIKE ?)'; args += ['%'+search+'%']*4
        return self.rows(sql+' ORDER BY e.start DESC',args)
    def approve(self,entry):
        return self.approve_many([entry])
    def start_timer(self,task,now=None):
        now=int(time.time() if now is None else now)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            rt=self.db.execute('SELECT * FROM runtime WHERE id=1').fetchone()
            if rt['state']=='running': raise ValueError('Stop the running timer first.')
            if self.db.execute('SELECT 1 FROM entries WHERE deleted=0 AND start<=? AND end>?',(now,now)).fetchone(): raise ValueError('The current time is already assigned.')
            self.db.execute("UPDATE runtime SET task_id=?,started=?,checkpoint=?,state='running' WHERE id=1",(task,now,now)); self.audit('timer started',{'task_id':task})
    def stop_timer(self,now=None,reason='stopped'):
        now=int(time.time() if now is None else now)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            rt=self.db.execute('SELECT * FROM runtime WHERE id=1').fetchone()
            if rt['state']!='running': return None
            start=rt['started']; end=now
            conflict=self.db.execute('SELECT MIN(start) FROM entries WHERE deleted=0 AND start >= ? AND start < ?',(start,end)).fetchone()[0]
            if conflict is not None: end=conflict
            self.db.execute("UPDATE runtime SET task_id=NULL,started=NULL,checkpoint=NULL,state='stopped' WHERE id=1")
            eid=None
            if end>start:
                self._assert_free(start,end)
                eid=self.db.execute("INSERT INTO entries(task_id,start,end,description,origin) VALUES (?,?,?,?,'timer')",(rt['task_id'],start,end,'')).lastrowid
            self.audit('timer stopped',{'entry_id':eid,'reason':reason}); return eid
    def runtime(self): return self.db.execute('SELECT * FROM runtime WHERE id=1').fetchone()
    def backup(self,dest):
        if Path(dest).resolve()==self.path.resolve(): raise ValueError('Choose a backup path other than the active database.')
        target=sqlite3.connect(dest)
        try: self.db.backup(target); result=target.execute('PRAGMA integrity_check').fetchone()[0]
        finally: target.close()
        if result!='ok': raise ValueError('Backup did not pass the integrity check.')
        os.chmod(dest,0o600)
    def validate(self):
        if self.db.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('Database integrity check failed.')
        if self.rows('PRAGMA foreign_key_check'): raise ValueError('Database references are inconsistent.')
        # Exercise all required columns before a restored file can replace live data.
        for query in [
            'SELECT id,name,currency,rate,archived FROM clients LIMIT 0',
            'SELECT id,client_id,name,budget,rate,archived FROM projects LIMIT 0',
            'SELECT id,project_id,name,budget,rate,archived FROM tasks LIMIT 0',
            'SELECT id,task_id,start,end,description,billable,status,rate,currency,invoice,revision,origin,activity_id,deleted FROM entries LIMIT 0',
            'SELECT id,start,end,app,title,state,closed,session,auto_processed FROM activity LIMIT 0',
            'SELECT key,value FROM settings LIMIT 0',
            'SELECT id,created,client_id,start,end,snapshot FROM reports LIMIT 0']:
            self.db.execute(query)
        invalid=self.db.execute("SELECT 1 FROM entries WHERE end<=start OR status NOT IN ('draft','approved','billed') OR billable NOT IN (0,1) OR rate<0 OR (billable=1 AND status IN ('approved','billed') AND rate IS NULL) LIMIT 1").fetchone()
        overlap=self.db.execute('SELECT 1 FROM entries a JOIN entries b ON a.id<b.id AND a.start<b.end AND a.end>b.start WHERE a.deleted=0 AND b.deleted=0 LIMIT 1').fetchone()
        if invalid or overlap: raise ValueError('The backup contains invalid or overlapping timesheet entries.')
        for r in self.rows('SELECT id,snapshot FROM reports'):
            try:
                lines=json.loads(r['snapshot'])
                required={'id','start','end','rate','amount','currency','client','project','task','description'}
                if not isinstance(lines,list) or not lines: raise ValueError()
                for line in lines:
                    if not isinstance(line,dict) or not required.issubset(line): raise ValueError()
                    if any(type(line[key]) is not int for key in ('id','start','end','rate','amount')): raise ValueError()
                    if line['id']<=0 or line['end']<=line['start'] or line['rate']<0 or line['amount']<0: raise ValueError()
                    if line['currency'] not in ('GBP','EUR','USD'): raise ValueError()
                    if any(not isinstance(line[key],str) for key in ('client','project','task','description')): raise ValueError()
                    datetime.fromtimestamp(line['start']); datetime.fromtimestamp(line['end'])
                    if 'report_date' in line: datetime.strptime(line['report_date'],'%Y-%m-%d')
            except (ValueError,TypeError,OverflowError,OSError): raise ValueError('A saved report is malformed.')
        return True
    def create_report(self,client,start,end):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            rows=[dict(r) for r in self.entries(start,end,client,'approved') if r['billable']]
            if not rows: raise ValueError('No approved, unbilled work in this period.')
            if any(r['start'] < start or r['end'] > end for r in rows): raise ValueError('An entry crosses the report boundary. Split it first.')
            for row in rows:
                # Stored rate is minor currency units per hour; amounts round only once per line.
                row['amount'] = int((Decimal(row['end']-row['start'])*Decimal(row['rate'])/Decimal(3600)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
                row['report_date']=datetime.fromtimestamp(row['start']).strftime('%Y-%m-%d')
            cur=self.db.execute('INSERT INTO reports(created,client_id,start,end,snapshot) VALUES (?,?,?,?,?)',(int(time.time()),client,int(start),int(end),json.dumps(rows)))
            self.db.executemany('INSERT INTO report_entries VALUES (?,?,?)',[(cur.lastrowid,r['id'],r['revision']) for r in rows])
            self.audit('report created',{'id':cur.lastrowid}); return cur.lastrowid
    def report(self,rid):
        row=self.db.execute('SELECT * FROM reports WHERE id=?',(rid,)).fetchone()
        if not row: raise ValueError('Report not found.')
        return json.loads(row['snapshot'])
    def mark_billed(self,rid,invoice):
        if not invoice.strip(): raise ValueError('Enter an invoice reference.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            records=self.rows('''SELECT e.id,e.status,e.deleted,e.revision,r.revision snapshot_revision FROM report_entries r JOIN entries e ON e.id=r.entry_id WHERE r.report_id=?''',(rid,))
            if not records: raise ValueError('Report not found or empty.')
            if any(r['deleted'] or r['status']!='approved' or r['revision']!=r['snapshot_revision'] for r in records): raise ValueError('Report is stale or entries are already billed. Create a new report.')
            self.db.executemany("UPDATE entries SET status='billed',invoice=?,revision=revision+1 WHERE id=?",[(invoice.strip(),r['id']) for r in records])
            self.db.execute('INSERT INTO report_billing(report_id,invoice,at) VALUES(?,?,?)',(rid,invoice.strip(),int(time.time())))
            self.audit('marked billed',{'report_id':rid,'invoice':invoice.strip()})

    def reopen_report(self,rid,reason):
        if not reason.strip(): raise ValueError('Explain the invoice correction for your history.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            billing=self.db.execute('SELECT * FROM report_billing WHERE report_id=?',(rid,)).fetchone()
            if not billing or billing['state']!='billed': raise ValueError('This report is not currently marked billed.')
            rows=self.rows('SELECT e.*,r.revision saved FROM report_entries r JOIN entries e ON e.id=r.entry_id WHERE r.report_id=?',(rid,))
            if any(r['status']!='billed' or r['invoice']!=billing['invoice'] or r['revision']!=r['saved']+1 for r in rows): raise ValueError('These entries have changed. Review the billing history first.')
            self.db.executemany("UPDATE entries SET status='draft',invoice=NULL,rate=NULL,currency=NULL,revision=revision+1 WHERE id=?",[(r['id'],) for r in rows])
            self.db.execute("UPDATE report_billing SET state='corrected',reason=? WHERE report_id=?",(reason.strip(),rid))
            self.audit('billing corrected',{'report_id':rid,'invoice':billing['invoice'],'reason':reason.strip()})
    def csv_report(self,rid):
        out=io.StringIO(newline=''); w=csv.writer(out)
        w.writerow(['Date','Client','Project','Task','Description','Actual hours','Billed hours','Hourly rate','Currency','Amount'])
        for r in self.report(rid):
            # Spreadsheet formula injection: prefix dangerous untrusted text.
            safe=lambda x: "'"+x if x.lstrip().startswith(('=','+','-','@','\t','\r','\n')) else x
            hours=f"{Decimal(r['end']-r['start'])/Decimal(3600):.6f}"
            w.writerow([r.get('report_date',datetime.fromtimestamp(r['start']).strftime('%Y-%m-%d')),*[safe(str(r[k])) for k in ('client','project','task','description')],hours,hours,f"{Decimal(r['rate'])/100:.2f}",r['currency'],f"{Decimal(r['amount'])/100:.2f}"])
        return out.getvalue()
    def html_report(self,rid):
        rows=self.report(rid); e=html.escape
        def duration(seconds): return f'{seconds//3600}h {(seconds%3600)//60:02d}m {seconds%60:02d}s'
        items=''.join('<tr>'+''.join('<td>'+e(v)+'</td>' for v in [r.get('report_date',datetime.fromtimestamp(r['start']).strftime('%Y-%m-%d')),r['project'],r['task'],r['description'],duration(r['end']-r['start']),f"{Decimal(r['rate'])/100:.2f}",r['currency'],f"{Decimal(r['amount'])/100:.2f}"])+'</tr>' for r in rows)
        total=sum(r['amount'] for r in rows)
        return '<!doctype html><html><head><meta charset="utf-8"><title>Timesheet report</title><style>body{font:14px sans-serif;margin:2em;color:#222}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:8px;border-bottom:1px solid #ccc}thead{display:table-header-group}@media print{tr{break-inside:avoid}}</style></head><body><h1>Timesheet report</h1><p>Client: '+e(rows[0]['client'])+' · Report '+str(rid)+' · Dates use the local time zone at report creation.</p><p>Exact time; no duration rounding.</p><table><thead><tr><th>Date</th><th>Project</th><th>Task</th><th>Description</th><th>Duration</th><th>Rate</th><th>Currency</th><th>Amount</th></tr></thead><tbody>'+items+'</tbody></table><p><strong>Total: '+e(rows[0]['currency'])+' '+f'{Decimal(total)/100:.2f}'+'</strong></p></body></html>'

def parse_money(text):
    if not text.strip(): return None
    try:
        value=Decimal(text.strip())
        if not value.is_finite() or value<0 or value>Decimal('1000000000') or value.as_tuple().exponent < -2: raise ValueError()
        return int(value*100)
    except Exception: raise ValueError('Enter a rate between 0 and 1,000,000,000 with at most two decimal places.')

def parse_hours(text):
    if not text.strip(): return None
    try:
        value=Decimal(text.strip())
        if not value.is_finite() or value<0 or value>Decimal('1000000000'): raise ValueError()
        return int(value*3600)
    except Exception: raise ValueError('Enter hours between 0 and 1,000,000,000.')

def local_timestamp(text):
    """Parse unambiguous local wall time; reject DST gaps and repeated hours."""
    parsed=None
    for fmt in ('%Y-%m-%d %H:%M:%S','%Y-%m-%d %H:%M'):
        try:
            parsed=datetime.strptime(text.strip(),fmt); break
        except ValueError: pass
    if parsed is None: raise ValueError('Use date and time format YYYY-MM-DD HH:MM or YYYY-MM-DD HH:MM:SS.')
    expected=(parsed.year,parsed.month,parsed.day,parsed.hour,parsed.minute,parsed.second)
    candidates=set()
    for isdst in (0,1):
        try:
            ts=int(time.mktime((*expected,0,0,isdst)))
            if tuple(time.localtime(ts)[:6])==expected: candidates.add(ts)
        except (ValueError,OverflowError,OSError): pass
    if not candidates: raise ValueError('That local time does not exist because the clock changed. Choose another time.')
    if len(candidates)>1: raise ValueError('That local time occurs twice because the clock changed. Use a time outside the repeated hour.')
    return candidates.pop()

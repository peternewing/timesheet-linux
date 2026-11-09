"""Explicit local personal/work context. A context marker is never a time entry."""
import base64,io,json,time,os
from datetime import datetime,timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo,TZPATH

SPACES={'personal':'Personal','work':'Work','unspecified':'Unsorted'}
SCHEDULES={'weekdays_9_17':('Weekdays 9–5',9,17),'weekdays_8_16':('Weekdays 8–4',8,16),'weekdays_10_18':('Weekdays 10–6',10,18)}
SCHEMA='''
CREATE TABLE IF NOT EXISTS screen_spaces(id INTEGER PRIMARY KEY,start INTEGER NOT NULL,end INTEGER,space TEXT NOT NULL,
 CHECK(end IS NULL OR end>start),CHECK(space IN ('personal','work','unspecified')));
CREATE UNIQUE INDEX IF NOT EXISTS screen_spaces_open ON screen_spaces((1)) WHERE end IS NULL;
CREATE INDEX IF NOT EXISTS screen_spaces_time ON screen_spaces(start,end);
CREATE TABLE IF NOT EXISTS screen_space_schedules(id INTEGER PRIMARY KEY,start INTEGER NOT NULL,end INTEGER,preset TEXT NOT NULL,zone TEXT NOT NULL DEFAULT '',CHECK(end IS NULL OR end>start));
CREATE UNIQUE INDEX IF NOT EXISTS screen_schedule_open ON screen_space_schedules((1)) WHERE end IS NULL;
CREATE INDEX IF NOT EXISTS screen_schedule_time ON screen_space_schedules(start,end);
CREATE TABLE IF NOT EXISTS screen_space_changes(id INTEGER PRIMARY KEY,before_state TEXT NOT NULL,after_state TEXT NOT NULL,undone INTEGER NOT NULL DEFAULT 0);
'''


def current(store):
    row=store.db.execute('SELECT * FROM screen_spaces WHERE end IS NULL').fetchone()
    return dict(row) if row else dict(id=None,start=None,end=None,space='unspecified')


def timezone_snapshot():
    """Retain schedule clock rules locally so travel cannot relabel old days."""
    name=os.environ.get('TZ')
    paths=[Path('/etc/localtime')] if name is None else ([Path(name.lstrip(':'))] if name.lstrip(':').startswith('/') else [Path(root)/(name.lstrip(':') or 'UTC') for root in TZPATH])
    for path in paths:
        try:
            with path.open('rb') as stream:raw=stream.read(65537)
            if not 1<=len(raw)<=65536:continue
            ZoneInfo.from_file(io.BytesIO(raw))
            return base64.b64encode(raw).decode('ascii')
        except (OSError,ValueError):continue
    raise ValueError('Local clock rules are unavailable. Use a manual space choice instead.')


@lru_cache(maxsize=32)
def saved_timezone(value):
    if not isinstance(value,str) or not 1<=len(value)<=90000:return None
    try:return ZoneInfo.from_file(io.BytesIO(base64.b64decode(value,validate=True)))
    except (ValueError,OSError):return None


def revision(store):return store.get('screen_space_revision','0')


def _bump(store):
    try:value=int(revision(store))
    except (ValueError,TypeError):value=0
    store.set('screen_space_revision',value+1)


def switch(store,space,now=None):
    if not isinstance(space,str) or space not in SPACES:raise ValueError('Choose Personal, Work or Unsorted.')
    now=int(time.time() if now is None else now)
    if not 0<=now<=2**40:raise ValueError('Choose a valid context time.')
    with store.db:
        store.db.execute('BEGIN IMMEDIATE');old=current(store)
        configured=schedule(store)
        if configured is not None and now<configured['since']:raise ValueError('The clock moved backwards. Wait for it to settle before switching spaces.')
        if old['space']==space and (old['id'] is not None or schedule(store) is None):return None
        if old['start'] is not None and now<old['start']:raise ValueError('The clock moved backwards. Wait for it to settle before switching spaces.')
        before=[old] if old['id'] is not None else [];after=[]
        if old['id'] is not None:
            if old['start']==now:store.db.execute('DELETE FROM screen_spaces WHERE id=?',(old['id'],))
            else:
                store.db.execute('UPDATE screen_spaces SET end=? WHERE id=?',(now,old['id']));after.append(dict(old,end=now))
        new=store.db.execute('INSERT INTO screen_spaces(start,space) VALUES(?,?)',(now,space)).lastrowid
        after.append(dict(id=new,start=now,end=None,space=space))
        change=store.db.execute('INSERT INTO screen_space_changes(before_state,after_state) VALUES(?,?)',(json.dumps(before),json.dumps(after))).lastrowid
        store.audit('screen space switched',{'space':space})
        _bump(store)
        return change


def schedule(store):
    row=store.db.execute('SELECT start,preset FROM screen_space_schedules WHERE end IS NULL').fetchone()
    if not row or not isinstance(row['preset'],str) or row['preset'] not in SCHEDULES or type(row['start']) is not int or not 0<=row['start']<=2**40:return None
    return dict(preset=row['preset'],since=row['start'])


def use_schedule(store,preset,now=None):
    if not isinstance(preset,str) or preset not in SCHEDULES:raise ValueError('Choose an available local schedule.')
    now=int(time.time() if now is None else now)
    if not 0<=now<=2**40:raise ValueError('Choose a valid context time.')
    zone=timezone_snapshot()
    with store.db:
        store.db.execute('BEGIN IMMEDIATE');old=current(store)
        if old['start'] is not None and now<old['start']:raise ValueError('The clock moved backwards. Wait before changing the schedule.')
        if old['id'] is not None:
            if old['start']==now:store.db.execute('DELETE FROM screen_spaces WHERE id=?',(old['id'],))
            else:store.db.execute('UPDATE screen_spaces SET end=? WHERE id=?',(now,old['id']))
        previous=store.db.execute('SELECT * FROM screen_space_schedules WHERE end IS NULL').fetchone()
        if previous:
            if now<previous['start']:raise ValueError('The clock moved backwards. Wait before changing the schedule.')
            if now==previous['start']:store.db.execute('DELETE FROM screen_space_schedules WHERE id=?',(previous['id'],))
            else:store.db.execute('UPDATE screen_space_schedules SET end=? WHERE id=?',(now,previous['id']))
        store.db.execute('INSERT INTO screen_space_schedules(start,preset,zone) VALUES(?,?,?)',(now,preset,zone))
        store.set('screen_space_schedule',json.dumps(dict(preset=preset,since=now)))
        store.db.execute('UPDATE screen_space_changes SET undone=1 WHERE undone=0')
        store.audit('local screen space schedule chosen',{'preset':preset})
        _bump(store)


def periods(store,start,end):
    if end<=start:return []
    base=[]
    def add(a,z,space,source):
        a=max(start,a);z=min(end,z)
        if z>a:base.append(dict(start=a,end=z,space=space,source=source))
    schedules=store.rows('SELECT * FROM screen_space_schedules WHERE start<? AND (end IS NULL OR end>?) ORDER BY start',(end,start))
    cursor=start
    for configured in schedules:
        if configured['preset'] not in SCHEDULES:continue
        zone=saved_timezone(configured['zone']) if configured['zone'] else None
        if configured['zone'] and zone is None:continue
        a=max(start,configured['start']);z=min(end,configured['end'] if configured['end'] is not None else end)
        add(cursor,a,'unspecified','unlabelled');day=datetime.fromtimestamp(a,zone).date()
        if (datetime.fromtimestamp(z,zone).date()-day).days>370:raise ValueError('Choose a context period of at most one year.')
        while a<z:
            next_day=int(datetime.combine(day+timedelta(days=1),datetime.min.time(),zone).timestamp());edge=min(z,next_day)
            if day.weekday()<5:
                _,first,last=SCHEDULES[configured['preset']]
                first=int(datetime.combine(day,datetime.min.time(),zone).replace(hour=first).timestamp());last=int(datetime.combine(day,datetime.min.time(),zone).replace(hour=last).timestamp())
                add(a,min(edge,first),'personal','schedule');add(max(a,first),min(edge,last),'work','schedule');add(max(a,last),edge,'personal','schedule')
            else:add(a,edge,'personal','schedule')
            a=edge;day+=timedelta(days=1)
        cursor=z
    add(cursor,end,'unspecified','unlabelled')
    manual=[dict(r,end=min(r['end'] if r['end'] is not None else end,end)) for r in store.rows(
        'SELECT * FROM screen_spaces WHERE start<? AND (end IS NULL OR end>?) ORDER BY start',(end,start))]
    result=[];index=0
    for row in base:
        a=row['start'];z=row['end']
        while index<len(manual) and manual[index]['end']<=a:index+=1
        k=index
        while a<z:
            if k>=len(manual) or manual[k]['start']>=z:result.append(dict(row,start=a,end=z));break
            item=manual[k]
            if a<item['start']:
                edge=min(z,item['start']);result.append(dict(row,start=a,end=edge));a=edge
            else:
                edge=min(z,item['end']);result.append(dict(start=a,end=edge,space=item['space'],source='manual'));a=edge
                if a>=item['end']:k+=1
    return result


def effective_now(store,now=None):
    now=int(time.time() if now is None else now);rows=periods(store,now,now+1)
    return rows[0] if rows else dict(space='unspecified',source='unlabelled')


def undo_switch(store,change_id):
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        change=store.db.execute('SELECT * FROM screen_space_changes WHERE undone=0 ORDER BY id DESC LIMIT 1').fetchone()
        if not change or change['id']!=change_id:raise ValueError('A newer space switch arrived. Reopen the space choice.')
        before=json.loads(change['before_state']);after=json.loads(change['after_state'])
        for row in after:
            actual=store.db.execute('SELECT * FROM screen_spaces WHERE id=?',(row['id'],)).fetchone()
            if not actual or dict(actual)!=row:raise ValueError('These spaces changed. Undo is unavailable.')
        store.db.executemany('DELETE FROM screen_spaces WHERE id=?',[(r['id'],) for r in after])
        for row in before:store.db.execute('INSERT INTO screen_spaces VALUES(?,?,?,?)',(row['id'],row['start'],row['end'],row['space']))
        store.db.execute('UPDATE screen_space_changes SET undone=1 WHERE id=?',(change_id,))
        store.audit('screen space switch undone',{})
        _bump(store)


def label_period(store,start,end,space,*,expected_revision=None,now=None):
    """Correct a finite local context interval without changing capture or billing."""
    now=int(time.time() if now is None else now)
    if (type(start) is not int or type(end) is not int or not 0<=start<end<=now
            or not isinstance(space,str) or space not in SPACES):raise ValueError('Choose a recorded period and space.')
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        if expected_revision is not None and revision(store)!=expected_revision:raise ValueError('Space labels changed. Reopen this period before changing it.')
        before=[dict(r) for r in store.rows('SELECT * FROM screen_spaces WHERE start<? AND (end IS NULL OR end>?) ORDER BY start',(end,start))]
        after=[]
        for row in before:store.db.execute('DELETE FROM screen_spaces WHERE id=?',(row['id'],))
        for row in before:
            fragments=[]
            if row['start']<start:fragments.append((row['start'],start))
            if row['end'] is None or row['end']>end:fragments.append((end,row['end']))
            for a,z in fragments:
                rid=store.db.execute('INSERT INTO screen_spaces(start,end,space) VALUES(?,?,?)',(a,z,row['space'])).lastrowid
                after.append(dict(id=rid,start=a,end=z,space=row['space']))
        rid=store.db.execute('INSERT INTO screen_spaces(start,end,space) VALUES(?,?,?)',(start,end,space)).lastrowid
        after.append(dict(id=rid,start=start,end=end,space=space))
        change=store.db.execute('INSERT INTO screen_space_changes(before_state,after_state) VALUES(?,?)',(json.dumps(before),json.dumps(after))).lastrowid
        _bump(store);store.audit('screen period labelled',{'space':space})
        return change


def forget_labels(store):
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        store.db.execute('DELETE FROM screen_space_changes');store.db.execute('DELETE FROM screen_spaces');store.db.execute('DELETE FROM screen_space_schedules')
        store.set('screen_space_schedule','{}');_bump(store);store.audit('local screen space labels cleared',{})

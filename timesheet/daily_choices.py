"""One explicit, local category choice per app and calendar day."""
from __future__ import annotations
import json,time
from datetime import date,datetime,timedelta
from .day_record import bounds

SCHEMA='''
CREATE TABLE IF NOT EXISTS daily_choices(day TEXT NOT NULL,app_key TEXT NOT NULL,application TEXT NOT NULL,task_id INTEGER REFERENCES tasks(id),created INTEGER NOT NULL,PRIMARY KEY(day,app_key));
CREATE TABLE IF NOT EXISTS daily_choice_changes(change_id INTEGER PRIMARY KEY REFERENCES entry_changes(id),day TEXT NOT NULL,app_key TEXT NOT NULL,before_choice TEXT NOT NULL,after_choice TEXT NOT NULL);
'''


def exists(store):return bool(store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='daily_choices'").fetchone())


def choice(store,day,app):
    if not exists(store):return None
    return store.db.execute('SELECT * FROM daily_choices WHERE day=? AND app_key=?',(day.isoformat(),app.casefold())).fetchone()


def candidates(store,day,app,now):
    """Only real, settled, active, uncovered fragments; never reserve a gap."""
    start,end=bounds(day);end=min(end,int(now));cutoff=int(now)-int(store.get('idle_seconds','300'))
    return [dict(r) for r in store.activity_for(start,end,True,now=now) if r['state']=='active' and r['closed'] and r['end']<=cutoff and r['app'].casefold()==app.casefold()]


def automatic_drafts(store,day,app):
    from .simple_setup import preset_ids
    valid=set(preset_ids(store).values());start,end=bounds(day);result=[]
    for entry in store.rows("SELECT e.*,a.app AS source_app FROM entries e JOIN activity a ON a.id=e.activity_id WHERE e.deleted=0 AND e.origin IN ('jev','app_type') AND e.status='draft' AND e.billable=0 AND e.start>=? AND e.end<=?",(start,end)):
        if entry['task_id'] in valid and entry['source_app'].casefold()==app.casefold():
            item=dict(entry);item.pop('source_app');result.append(item)
    return result


def validate_blocks(store,blocks):
    for block in blocks:
        row=store.db.execute('SELECT * FROM activity WHERE id=?',(block['id'],)).fetchone()
        if not row or row['state']!='active' or not row['closed'] or row['app'].casefold()!=block['app'].casefold() or not row['start']<=block['start']<block['end']<=row['end'] or store.uncovered(block['start'],block['end'])!=[(block['start'],block['end'])]:raise ValueError('This activity changed. Reopen the daily choice.')


def _write(store,day,app,task,blocks,*,remember=False):
    ids=[]
    for block in blocks:
        eid=store.db.execute("INSERT INTO entries(task_id,start,end,description,billable,origin,activity_id) VALUES(?,?,?,'Daily activity choice',0,'assigned',?)",(task,block['start'],block['end'],block['id'])).lastrowid
        ids.append(eid)
        store.db.execute("UPDATE ai_jobs SET state='applied',reason='App categorised by your daily choice.',updated=?,lease_until=0 WHERE activity_id=? AND start>=? AND end<=? AND state IN ('pending','running','exception','failed','stale')",(int(time.time()),block['id'],block['start'],block['end']))
        if remember:
            # Keep local examples under the exact current permitted context.
            from .automation_store import Repository
            from .decision_context import build,canonical
            from .decision_policy import settings
            activity=store.db.execute('SELECT * FROM activity WHERE id=?',(block['id'],)).fetchone()
            context,_=build(store,activity,None,settings(store.get('ai_policy','{}')),start=block['start'],end=block['end'],ignore_daily_choice=True)
            if context:
                net=context['network'];scope=canonical({'clues':net.get('clues',[]),'focus':net.get('focus')})
                from .decision_memory import remember as remember_example
                remember_example(store,block['id'],app,task,scope,int(time.time()))
    return ids


def choose(store,item,task,*,remember=False,now=None):
    from .simple_setup import preset_ids
    now=int(time.time() if now is None else now);day=date.fromisoformat(item['day']);app=item['app']
    if task is not None and task not in preset_ids(store).values():raise ValueError('Choose a current activity category.')
    with store.db:
        store.db.execute('BEGIN IMMEDIATE');validate_blocks(store,item['blocks'])
        for expected in item.get('auto_entries',[]):
            current=store.db.execute('SELECT * FROM entries WHERE id=? AND deleted=0',(expected['id'],)).fetchone()
            if not current or current['revision']!=expected['revision'] or current['origin'] not in ('jev','app_type') or current['status']!='draft' or current['billable']:raise ValueError('These automatic estimates changed. Reopen the daily choice.')
        previous=choice(store,day,app);before=dict(previous) if previous else None
        store.db.execute('INSERT INTO daily_choices VALUES(?,?,?,?,?) ON CONFLICT(day,app_key) DO UPDATE SET task_id=excluded.task_id,created=excluded.created',(day.isoformat(),app.casefold(),app,task,now))
        # The scope explicitly includes later recordings of this app today. A new
        # arrival since the preview is eligible; existing allocations stay intact.
        blocks=candidates(store,day,app,now)
        ids=_write(store,day,app,task,blocks,remember=remember) if task is not None else []
        before_entries=automatic_drafts(store,day,app) if task is not None else []
        for entry in before_entries:
            store.db.execute("UPDATE entries SET task_id=?,description='Daily activity choice',origin='assigned',revision=revision+1 WHERE id=?",(task,entry['id']));ids.append(entry['id'])
        if task is None:
            start,end=bounds(day)
            for row in store.rows('SELECT id,app FROM activity WHERE start<? AND end>?',(end,start)):
                if row['app'].casefold()==app.casefold():store.db.execute("UPDATE ai_jobs SET state='dismissed',reason='Left uncategorised for this day.',updated=?,lease_until=0 WHERE activity_id=? AND start>=? AND end<=? AND state IN ('pending','running','exception','failed','stale')",(now,row['id'],start,end))
        store._record_change('Categorise app for the day',before_entries,ids)
        change_id=store.db.execute('SELECT MAX(id) FROM entry_changes').fetchone()[0]
        after=dict(choice(store,day,app));store.db.execute('INSERT INTO daily_choice_changes VALUES(?,?,?,?,?)',(change_id,day.isoformat(),app.casefold(),json.dumps(before),json.dumps(after)))
        store.audit('daily app choice',{'day':day.isoformat(),'app_key':app.casefold(),'task_id':task,'periods':len(ids)})
        return len(ids)


def apply_saved(store,now=None):
    """Local continuation: one allocation snapshot per day, bounded writes."""
    if not exists(store):return 0
    from .simple_setup import preset_ids
    now=int(time.time() if now is None else now);count=0
    since=datetime.fromtimestamp(now).date()-timedelta(days=7)
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        valid=set(preset_ids(store).values());days={}
        for saved in store.rows('SELECT * FROM daily_choices WHERE day>=? AND task_id IS NOT NULL',(since.isoformat(),)):
            if saved['task_id'] not in valid:continue
            try:day=date.fromisoformat(saved['day'])
            except (ValueError,TypeError):continue
            days.setdefault(day,{})[saved['app_key']]=saved
        cutoff=now-int(store.get('idle_seconds','300'))
        for day,choices in sorted(days.items()):
            start,end=bounds(day)
            if now<=start:continue
            grouped={}
            for row in store.activity_for(start,min(end,now),True,now=now):
                key=row['app'].casefold()
                if key not in choices or row['state']!='active' or not row['closed'] or row['end']>cutoff:continue
                grouped.setdefault(key,[]).append(dict(row))
                if sum(map(len,grouped.values()))>=200-count:break
            for key,blocks in grouped.items():
                saved=choices[key];ids=_write(store,day,saved['application'],saved['task_id'],blocks)
                store._record_change('Apply saved daily choice',[],ids)
                change_id=store.db.execute('SELECT MAX(id) FROM entry_changes').fetchone()[0]
                store.db.execute('INSERT INTO daily_choice_changes VALUES(?,?,?,?,?)',(change_id,saved['day'],key,'null',json.dumps(dict(saved))))
                count+=len(ids)
            if count>=200:break
    return count


def undo(store,change_id):
    if not exists(store):return
    row=store.db.execute('SELECT * FROM daily_choice_changes WHERE change_id=?',(change_id,)).fetchone()
    if not row:return
    previous=json.loads(row['before_choice']);expected=json.loads(row['after_choice'])
    current=store.db.execute('SELECT * FROM daily_choices WHERE day=? AND app_key=?',(row['day'],row['app_key'])).fetchone()
    if current is None and previous is None:return
    if not current or dict(current)!=expected:raise ValueError('The daily choice changed. Reopen its activity before undoing.')
    if previous:store.db.execute('INSERT OR REPLACE INTO daily_choices VALUES(?,?,?,?,?)',tuple(previous[k] for k in ('day','app_key','application','task_id','created')))
    else:store.db.execute('DELETE FROM daily_choices WHERE day=? AND app_key=?',(row['day'],row['app_key']))


def prune(store):
    """Do not retain copied app identities after their source activity is erased."""
    if not exists(store):return
    keys=store.rows('SELECT day,app_key FROM daily_choices UNION SELECT day,app_key FROM daily_choice_changes')
    for key in keys:
        try:start,end=bounds(date.fromisoformat(key['day']))
        except (ValueError,TypeError):start=end=0
        apps=store.rows('SELECT DISTINCT app FROM activity WHERE start<? AND end>?',(end,start)) if end>start else []
        if not any(row['app'].casefold()==key['app_key'] for row in apps):
            store.db.execute('DELETE FROM daily_choices WHERE day=? AND app_key=?',(key['day'],key['app_key']))
            store.db.execute('DELETE FROM daily_choice_changes WHERE day=? AND app_key=?',(key['day'],key['app_key']))

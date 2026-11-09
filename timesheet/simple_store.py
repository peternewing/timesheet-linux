"""Small, reversible human actions for the everyday UI."""
from __future__ import annotations
import json,time
from .automation_store import Repository
from .decision_context import canonical
from .day_record import bounds
from .simple_setup import preset_ids


def review_items(store,day,limit=100):
    from .daily_choices import choice
    repo=Repository(store);start,end=bounds(day);now=int(time.time());cutoff=now-int(store.get('idle_seconds','300'))
    groups={}
    saved={r['app_key'] for r in store.rows('SELECT app_key FROM daily_choices WHERE day=?',(day.isoformat(),))}
    pending={r['activity_id'] for r in store.rows("SELECT activity_id FROM ai_jobs WHERE state IN ('pending','running','dismissed') AND start<? AND end>?",(end,start))}
    ready={r['activity_id'] for r in store.rows("SELECT activity_id FROM ai_jobs WHERE state IN ('exception','failed') AND start<? AND end>?",(end,start))}
    # One app is one activity type in the simple daily view, even if its
    # observations span hours, title changes or several Jev contexts.
    for row in store.activity_for(start,min(end,now),True,now=now):
        if row['state']!='active' or not row['closed'] or row['end']>cutoff:continue
        if row['app'].casefold() in saved:continue
        if store.get('simple_skip_'+str(row['id']),'0')=='1':continue
        key=row['app'].casefold()
        group=groups.setdefault(key,dict(kind='daily',day=day.isoformat(),app=row['app'],app_key=key,blocks=[],start=row['start'],end=row['end'],seconds=0))
        group['eligible']=group.get('eligible',False) or row['id'] not in pending or row['id'] in ready
        group['blocks'].append(dict(row));group['end']=max(group['end'],row['end']);group['seconds']+=row['end']-row['start']
    from .daily_choices import automatic_drafts
    for group in groups.values():
        group['auto_entries']=automatic_drafts(store,day,group['app']);group['seconds']+=sum(e['end']-e['start'] for e in group['auto_entries'])
    return sorted((g for g in groups.values() if g.get('eligible')),key=lambda r:(-r['seconds'],r['app_key']))[:limit]


def assign_manual(store,blocks,task_id):
    """Use the existing atomic fragment revalidation and undo path."""
    if task_id not in preset_ids(store).values():raise ValueError('Choose a current activity category.')
    count=store.assign_remaining(blocks,task_id,'Chosen activity category',False,billable=False,strict=True)
    # assign_remaining's change record must reflect the final non-billable rows.
    # This property belongs to the existing atomic writer, not a second update.
    return count


def change_category(store,entry_id,task_id,revision,remember=False):
    store.validate_rule_target(task_id)
    if task_id not in preset_ids(store).values():raise ValueError('Choose a current activity category.')
    repo=Repository(store)
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        old=store.db.execute('SELECT * FROM entries WHERE id=? AND deleted=0',(entry_id,)).fetchone()
        if not old or old['revision']!=revision:raise ValueError('This period changed. Reopen it before choosing a category.')
        if old['status']=='billed':raise ValueError('This period belongs to a billed report. Use Advanced tools for a recorded correction.')
        store.db.execute("UPDATE entries SET task_id=?,billable=0,status='draft',rate=NULL,currency=NULL,revision=revision+1,origin=CASE WHEN activity_id IS NULL THEN 'manual' ELSE 'assigned' END WHERE id=?",(task_id,entry_id))
        if remember and old['activity_id']:
            activity=store.db.execute('SELECT * FROM activity WHERE id=?',(old['activity_id'],)).fetchone()
            if activity:
                context,_=repo.context(activity,start=old['start'],end=old['end'])
                if context:
                    network=context['network'];scope=canonical({'clues':network.get('clues',[]),'focus':network.get('focus')})
                    store.db.execute('INSERT INTO ai_examples(activity_id,application,task_id,at,scope) VALUES(?,?,?,?,?) ON CONFLICT(activity_id) DO UPDATE SET task_id=excluded.task_id,at=excluded.at,scope=excluded.scope',(old['activity_id'],activity['app'],task_id,int(time.time()),scope))
        store._record_change('Change activity category',[old],[entry_id]);store.audit('activity category corrected',{'entry_id':entry_id,'task_id':task_id})


def skip_item(store,item):
    if item['kind']=='daily':
        from .daily_choices import choose
        choose(store,item,None);return
    if item['kind']=='job':Repository(store).dismiss(item['job']['id']);return
    with store.db:
        # Persist only a local dismiss marker, no invented allocation or AI call.
        for block in item['blocks']:store.set('simple_skip_'+str(block['id']),'1')

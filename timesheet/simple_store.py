"""Small, reversible human actions for the everyday UI."""
from __future__ import annotations
import json,time
from .automation_store import Repository
from .decision_context import canonical
from .day_record import bounds
from .simple_setup import preset_ids


def review_items(store,day,limit=100):
    repo=Repository(store);start,end=bounds(day);now=int(time.time());cutoff=now-int(store.get('idle_seconds','300'))
    jobs=[dict(r) for r in repo.review_rows() if r['state']=='exception' and r['start']>=start and r['end']<=end]
    busy={r['activity_id'] for r in store.rows("SELECT activity_id FROM ai_jobs WHERE state IN ('pending','running','dismissed') AND start<? AND end>?",(end,start))}
    busy.update(r['activity_id'] for r in jobs)
    items=[dict(kind='job',job=r,start=r['start'],end=r['end'],app=json.loads(r['network'])['applications'][0]) for r in jobs]
    for row in store.activity_for(start,min(end,now),True,now=now):
        if row['state']!='active' or not row['closed'] or row['end']>cutoff or row['id'] in busy or store.get('simple_skip_'+str(row['id']),'0')=='1':continue
        if items and items[-1]['kind']=='manual' and items[-1]['app']==row['app'] and items[-1]['end']==row['start']:
            items[-1]['blocks'].append(dict(row));items[-1]['end']=row['end']
        else:items.append(dict(kind='manual',blocks=[dict(row)],start=row['start'],end=row['end'],app=row['app']))
    return sorted(items,key=lambda r:(r['start'],r['end']))[:limit]


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
    if item['kind']=='job':Repository(store).dismiss(item['job']['id']);return
    with store.db:
        # Persist only a local dismiss marker, no invented allocation or AI call.
        for block in item['blocks']:store.set('simple_skip_'+str(block['id']),'1')

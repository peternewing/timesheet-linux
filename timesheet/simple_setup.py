"""Click-only everyday setup; generic categories never imply client billing."""
from __future__ import annotations
import json
import time
from datetime import datetime
from .automation_store import Repository
from .decision_policy import DEFAULTS,POLICY_VERSION,owner_token

BUCKETS={
 'create':('Creating & building','Creating, writing, coding, designing or editing an output; excludes passive research, messages and administrative work.'),
 'learn':('Research & learning','Reading, investigating, comparing sources or learning; excludes creating outputs and messages.'),
 'communicate':('Communication','Messaging, email, calls and meetings. Describes the application activity type, whether work or personal.'),
 'plan':('Planning & admin','Planning, scheduling, organising, spreadsheets and administration. Describes activity type, not work intent.')}
CLIENT='My day'
PROJECT='Daily activities'


def preset_ids(store):
    """Return only intact app-created categories, never arbitrary client tasks."""
    try:mapping=json.loads(store.get('simple_buckets','{}'))
    except (ValueError,TypeError,RecursionError):return {}
    if not isinstance(mapping,dict):return {}
    try:project_id=int(store.get('simple_project_id','0'))
    except ValueError:return {}
    result={}
    for key,tid in mapping.items():
        if key not in BUCKETS or type(tid) is not int:continue
        row=store.db.execute('''SELECT t.name task,p.id project_id,t.archived ta,p.archived pa,c.archived ca,g.guidance
         FROM tasks t JOIN projects p ON p.id=t.project_id JOIN clients c ON c.id=p.client_id
         LEFT JOIN ai_task_profiles g ON g.task_id=t.id WHERE t.id=?''',(tid,)).fetchone()
        if row and not any(row[k] for k in ('ta','pa','ca')) and row['project_id']==project_id and (row['task'],row['guidance'])==BUCKETS[key]:result[key]=tid
    return result


def ensure_buckets(store,selected):
    if not isinstance(selected,(list,tuple)) or not selected or len(set(selected))!=len(selected) or any(k not in BUCKETS for k in selected):raise ValueError('Choose at least one activity category.')
    repo=Repository(store)
    # An exclusive setup transaction avoids duplicates and never adopts an existing
    # user's same-named project. Existing work and rates remain untouched.
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        known=preset_ids(store)
        if set(known)!=set(BUCKETS):
            known={}
            name=CLIENT;number=1
            while store.db.execute('SELECT 1 FROM clients WHERE name=?',(name,)).fetchone():
                number+=1;name=f'{CLIENT} ({number})'
            cid=store.db.execute('INSERT INTO clients(name) VALUES(?)',(name,)).lastrowid
            pid=store.db.execute('INSERT INTO projects(client_id,name) VALUES(?,?)',(cid,PROJECT)).lastrowid
            store.set('simple_project_id',pid)
            for key,(name,guidance) in BUCKETS.items():
                tid=store.db.execute('INSERT INTO tasks(project_id,name) VALUES(?,?)',(pid,name)).lastrowid
                store.db.execute('INSERT INTO ai_task_profiles VALUES(?,?)',(tid,guidance));known[key]=tid
            store.set('simple_buckets',json.dumps(known,sort_keys=True))
        if any(k not in known for k in selected):raise ValueError('An activity category was changed or archived. Restore it in Advanced tools before setup.')
        return [known[k] for k in selected]


def finish_setup(store,selected,*,connected,titles=False,remember=True,now=None,backend='native'):
    if any(type(v) is not bool for v in (connected,titles,remember)):raise ValueError('Choose the setup options.')
    now=int(time.time() if now is None else now)
    ids=ensure_buckets(store,selected)
    day=int(datetime.combine(datetime.fromtimestamp(now).date(),datetime.min.time()).timestamp())
    config={**DEFAULTS,'mode':'automatic' if connected else 'off','consent_version':POLICY_VERSION if connected else 0,
        'since':day,'owner':owner_token(),'backend':backend,'category_tasks':ids,
        'allow_guidance':True,'allow_examples':remember,'allow_project_clues':titles,'allow_focus':False}
    repo=Repository(store);repo.configure(config)
    with store.db:
        store.set('capture_titles','1' if titles else '0')
        store.set('simple_remember','1' if remember else '0')
        store.set('simple_setup_complete','1')
        store.audit('simple setup completed',{'connected':connected,'category_count':len(ids),'titles':titles,'remember':remember})
    return config

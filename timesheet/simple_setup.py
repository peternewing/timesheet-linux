"""Click-only everyday setup; generic categories never imply client billing."""
from __future__ import annotations
import json
import time
from contextlib import nullcontext
from datetime import datetime
from .automation_store import Repository
from .decision_policy import POLICY_VERSION,owner_token

BUCKETS={
 'create':('Creating & building','Creating, writing, coding, designing or editing an output; excludes passive research, messages and administrative work.'),
 'learn':('Research & learning','Reading, investigating, comparing sources or learning; excludes creating outputs and messages.'),
 'communicate':('Communication','Messaging, email, calls and meetings. Describes the application activity type, whether work or personal.'),
 'plan':('Planning & admin','Planning, scheduling, organising, spreadsheets and administration. Describes activity type, not work intent.'),
 'play':('Games','Playing computer games and interactive entertainment. This is a legitimate screen-time activity, not a judgment about productivity.'),
 'media':('Videos & listening','Watching video or listening to audio in media players and streaming apps. Does not infer the content, purpose or whether a person paid attention.'),
 'browse':('Web browsing','Use of a general web browser or web-viewing app. Labels the application function only, without guessing sites, content or personal/work intent.'),
 'computer':('Computer & utilities','File management, terminals, system settings and general computer utilities. Describes broad app use without inferring the task or work intent.')}
LEGACY_BUCKETS=frozenset(('create','learn','communicate','plan'))
CLIENT='My day'
PROJECT='Daily activities'

# These are local navigation preferences, never permission to send project data.
TOOLS={
 'projects':('Track time on projects','Projects'),
 'rules':('Automate repeated assignments','Rules'),
 'reports':('Prepare client reports','Reports')}


def selected_tools(store):
    try:value=json.loads(store.get('simple_tools','[]'))
    except (ValueError,TypeError,RecursionError):return []
    if not isinstance(value,list):return []
    return [key for key in TOOLS if key in value]


def save_tools(store,selected):
    if not isinstance(selected,(list,tuple)) or any(not isinstance(k,str) or k not in TOOLS for k in selected):
        raise ValueError('Choose available tools.')
    store.set('simple_tools',json.dumps([key for key in TOOLS if key in selected]))


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
    joined=store.db.in_transaction
    with nullcontext() if joined else store.db:
        if not joined:store.db.execute('BEGIN IMMEDIATE')
        known=preset_ids(store)
        try:original=json.loads(store.get('simple_buckets','{}'))
        except (ValueError,TypeError,RecursionError):original={}
        missing=set(BUCKETS)-set(known)
        # Extend only a wholly intact app-owned legacy preset set. Do not replace
        # old category IDs or adopt a same-named user-created task.
        if (missing and isinstance(original,dict) and set(original)==set(known) and LEGACY_BUCKETS<=set(known)):
            pid=int(store.get('simple_project_id','0'))
            collision=any(store.db.execute('SELECT 1 FROM tasks WHERE project_id=? AND name=?',(pid,BUCKETS[k][0])).fetchone() for k in missing)
            if not collision:
                for key in BUCKETS:
                    if key in known:continue
                    name,guidance=BUCKETS[key];tid=store.db.execute('INSERT INTO tasks(project_id,name) VALUES(?,?)',(pid,name)).lastrowid
                    store.db.execute('INSERT INTO ai_task_profiles VALUES(?,?)',(tid,guidance));known[key]=tid
                store.set('simple_buckets',json.dumps(known,sort_keys=True))
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


def finish_setup(store,selected,*,connected,titles=False,remember=True,now=None,backend='native',tools=None,local_types=True):
    if any(type(v) is not bool for v in (connected,titles,remember,local_types)):raise ValueError('Choose the setup options.')
    if backend not in ('native','flatpak'):raise ValueError('Choose a supported installation.')
    if tools is not None and (not isinstance(tools,(list,tuple)) or any(not isinstance(k,str) or k not in TOOLS for k in tools)):
        raise ValueError('Choose available tools.')
    now=int(time.time() if now is None else now)
    repo=Repository(store)
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        ids=ensure_buckets(store,selected)
        day=int(datetime.combine(datetime.fromtimestamp(now).date(),datetime.min.time()).timestamp())
        config={**repo.config(),'mode':'automatic' if connected else 'off','consent_version':POLICY_VERSION if connected else 0,
            'since':day,'owner':owner_token(),'backend':backend,'category_tasks':ids,
            'allow_guidance':True,'allow_examples':remember,'allow_project_clues':titles,'allow_focus':False}
        repo.configure(config)
        if tools is not None:save_tools(store,tools)
        store.set('capture_titles','1' if titles else '0')
        store.set('simple_remember','1' if remember else '0')
        store.set('local_app_types','1' if local_types else '0');store.set('local_type_cursor','0')
        store.set('simple_setup_complete','1')
        store.audit('simple setup completed',{'connected':connected,'category_count':len(ids),'titles':titles,'remember':remember})
    return config

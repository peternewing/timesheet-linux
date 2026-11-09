"""Build the exact approved context locally. Raw titles never leave this module."""
from __future__ import annotations
import hashlib
import json
import re
from .decision_policy import settings

STOPWORDS=frozenset('the and for from with this that work project task client general website app com org www'.split())


def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def plain(value,limit):
    return isinstance(value,str) and len(value)<=limit and not any(ord(c)<32 or ord(c)==127 or 0x202a<=ord(c)<=0x202e or 0x2066<=ord(c)<=0x2069 for c in value)


def build(store,activity,repo,config,*,start=None,end=None,ignore_daily_choice=False):
    """Return network context + local fingerprint, or a reason to skip sending."""
    if activity['state']!='active' or not activity['closed'] or not activity['app']:return None,'Not completed work activity.'
    if not plain(activity['app'],200):return None,'Application name cannot be sent.'
    excluded=[x.casefold() for x in config['exclude_apps']]
    # Capture exclusions are applied before persistence; also respect current user
    # exclusions so queued observations cannot escape a later privacy change.
    raw_exclusions=store.get('excluded_apps','')
    if not isinstance(raw_exclusions,str) or len(raw_exclusions)>100000:return None,'Capture exclusions could not be verified.'
    excluded.extend(x.strip().casefold() for x in raw_exclusions.split(',') if x.strip())
    if activity['app'].casefold() in excluded:return None,'This application is excluded.'
    from .daily_choices import choice
    from datetime import datetime
    local_choice=choice(store,datetime.fromtimestamp(activity['start'] if start is None else start).date(),activity['app'])
    if local_choice is not None and not ignore_daily_choice:return None,'Your daily choice handles this app locally.'
    tasks=store.tasks();rule_targets={r['id'] for r in tasks}
    generic=bool(config.get('category_tasks'))
    if generic:
        from .simple_setup import preset_ids
        valid=set(preset_ids(store).values());selected=set(config['category_tasks'])
        if not selected<=valid:return None,'Activity categories changed. Run simple setup again.'
        tasks=[r for r in tasks if r['id'] in selected]
    ids={r['id'] for r in tasks}
    if not 1<=len(tasks)<=254:return None,'Create active tasks or reduce the active task list below 255.'
    at=activity['start'] if start is None else start
    rules=[dict(r) for r in store.rows('SELECT * FROM rules WHERE enabled=1 AND created<=? ORDER BY priority DESC,id',(at,))
           if r['task_id'] in rule_targets and r['app'].casefold()==activity['app'].casefold() and r['title'].casefold() in activity['title'].casefold()]
    conflict=False
    if rules:
        highest=rules[0]['priority'];targets={r['task_id'] for r in rules if r['priority']==highest}
        if len(targets)==1:return None,'A saved rule handles this period locally.'
        conflict=True
    profiles={r['task_id']:r['guidance'] for r in store.rows('SELECT * FROM ai_task_profiles')}
    choices=[]
    for row in tasks:
        label=row['task'] if generic else ' / '.join(row[k] for k in ('client','project','task'))
        guide=profiles.get(row['id'],'') if config['allow_guidance'] else ''
        text=label+(' | Work guidance: '+guide if guide else '')
        if not plain(text,500):return None,'Task names and guidance must fit within 500 plain characters per option.'
        choices.append((row['id'],text))
    examples=[]
    clues=[]
    if config['allow_project_clues'] and store.get('capture_titles','0')=='1':
        terms={w.casefold() for w in re.findall(r'\w+',activity['title']) if len(w)>=3}-STOPWORDS
        for row in tasks:
            source=' '.join([row[k] for k in ('client','project','task')]+[profiles.get(row['id'],'')])
            known={w.casefold() for w in re.findall(r'\w+',source) if len(w)>=3}-STOPWORDS
            matches=len(terms&known)
            if matches>=2:clues.append(dict(task=row['id'],matching_terms=min(matches,20)))
        clues=sorted(clues,key=lambda x:(-x['matching_terms'],x['task']))[:10]
    focus=None;focus_default=False
    if config['allow_focus']:
        row=store.db.execute('SELECT task_id,draft_default FROM ai_focus WHERE start<=? AND end>=? ORDER BY start DESC LIMIT 1',(activity['start'] if start is None else start,activity['end'] if end is None else end)).fetchone()
        if row and row['task_id'] in ids:focus=row['task_id'];focus_default=bool(row['draft_default'])
    if config['allow_examples']:
        rows=[r for r in store.rows('SELECT application,task_id,activity_id,scope FROM ai_examples ORDER BY id DESC LIMIT 1000')
              if r['task_id'] in ids and r['application'].casefold()==activity['app'].casefold()
              and r['scope']==canonical({'clues':clues,'focus':focus})][:8]
        examples=[dict(application=r['application'],task=r['task_id']) for r in rows]
    network=dict(applications=[activity['app']],tasks=choices,examples=examples,clues=clues,focus=focus,focus_default=focus_default,application_categories=generic)
    # Title/state/interval are only hashed locally for stale-data detection. The
    # fingerprint is not sent. Consent and task/example changes invalidate jobs.
    evidence={k:activity[k] for k in ('id','start','end','app','title','state','closed')}
    local=dict(evidence=evidence,config=config,network=network,rules=rules)
    return dict(network=network,fingerprint=digest(local),has_context=(generic or bool(clues) or focus is not None) and not conflict),None

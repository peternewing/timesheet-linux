"""Local operational facts. No key access, network calls or accuracy estimates."""
import json
import os
import time
from .decision_policy import settings,owner_token
from .day_record import bounds
from datetime import datetime


def worker_state(store,now=None,config=None):
    now=int(time.time() if now is None else now)
    config=config or settings(store.get('ai_policy','{}'))
    if config['mode']=='off':return 'off'
    if config['owner']!=owner_token() or config['backend']!=('flatpak' if os.environ.get('FLATPAK_ID') else 'native'):return 'other installation'
    if store.get('ai_pause_reason',''):return 'paused'
    try:backoff=int(store.get('ai_backoff_until','0') or 0)
    except (ValueError,TypeError):backoff=0
    if backoff>now:return 'waiting for provider'
    try:seen=int(store.get('ai_worker_seen','0'))
    except (ValueError,TypeError):seen=0
    if not seen or not -5<=now-seen<=30:return 'not running'
    return 'ready'


def summary(store,now=None):
    now=int(time.time() if now is None else now);start,end=bounds(datetime.fromtimestamp(now).date())
    config=settings(store.get('ai_policy','{}'))
    jobs={r['state']:r['count'] for r in store.rows('SELECT state,COUNT(*) count FROM ai_jobs WHERE start<? AND end>? GROUP BY state',(end,start))}
    usage=store.db.execute('SELECT COUNT(*) requests,COALESCE(SUM(input_tokens),0) tokens FROM ai_usage WHERE at>=? AND at<?',(start,end)).fetchone()
    unknown=store.db.execute("SELECT COUNT(*) FROM ai_usage WHERE input_tokens IS NULL AND outcome!='acknowledged unknown'").fetchone()[0]
    return dict(state=worker_state(store,now,config),mode=config['mode'],
        queued=jobs.get('pending',0)+jobs.get('running',0),uncertain=jobs.get('exception',0),failed=jobs.get('failed',0),
        requests=usage['requests'],input_tokens=usage['tokens'],unknown_usage=unknown,
        request_limit=config['daily_requests'],input_token_limit=config['daily_tokens'])


def summary_text(store,now=None):
    value=summary(store,now)
    return (f"Worker: {value['state']} · {value['mode']}\n"
        f"Today: {value['queued']} periods waiting · {value['uncertain']} uncertain decisions · {value['failed']} failed decisions\n"
        f"{value['requests']} / {value['request_limit']} background requests · "
        f"{value['input_tokens']:,} / {value['input_token_limit']:,} reported input tokens\n"
        f"{value['unknown_usage']} unresolved usage records across all days. "
        'Reported token usage can cross its limit by one request. These are workflow counts, not AI accuracy or a bill.')


def explain_entry(store,entry_id):
    entry=store.db.execute('SELECT * FROM entries WHERE id=? AND deleted=0',(entry_id,)).fetchone()
    if not entry:return 'This entry is no longer available.'
    if entry['origin']=='app_type':
        saved=store.db.execute('SELECT bucket,categories FROM local_type_assignments WHERE entry_id=?',(entry_id,)).fetchone()
        if not saved:return 'A local installed-app category created this draft. Its detailed metadata is unavailable. No AI request was needed.'
        try:
            categories=json.loads(saved['categories']);categories=[s for s in categories if isinstance(s,str) and s.isalnum() and len(s)<=80]
        except (ValueError,TypeError,RecursionError):categories=[]
        return 'Matched the installed app’s declared categories: '+(', '.join(categories) or 'not retained')+'. Desktop metadata stayed local; this label did not use an AI answer. It describes app function, not personal/work intent or completed output. Non-billable draft.'
    if entry['origin']=='automatic':
        rule=store.db.execute('SELECT * FROM rule_assignments WHERE entry_id=?',(entry_id,)).fetchone()
        detail=f"Rule #{rule['rule_id']} · priority {rule['priority']} · "+('app and title condition.' if rule['title_required'] else 'app condition.') if rule else 'The historical rule identity was not recorded.'
        return 'A saved local assignment rule created this entry. Jev was not needed. '+detail+' This describes the rule at assignment time; later edits do not rewrite that history.'
    if entry['origin']!='jev':return 'This entry was chosen or entered by you. It is not a current Jev estimate.'
    for row in store.rows('SELECT decision,network,entry_ids,reason,routing_version,request_version,decision_source FROM ai_jobs WHERE activity_id=? AND start<=? AND end>=? ORDER BY updated DESC,id DESC LIMIT 50',
                         (entry['activity_id'],entry['start'],entry['end'])):
        try:
            if any(len(row[k])>64000 for k in ('decision','network','entry_ids')):continue
            ids=json.loads(row['entry_ids']);decision=json.loads(row['decision']);network=json.loads(row['network'])
            if not isinstance(ids,list) or entry_id not in ids or not isinstance(decision,dict) or not isinstance(network,dict):continue
            if not network:break
            model=decision.get('model','not retained')
            from .decision_context import plain
            if not plain(model,125):model='not retained'
            reason=row['reason'] if plain(row['reason'],1000) else 'Recorded draft decision.'
            policy=str(row['routing_version']) if row['routing_version'] else 'historical version not recorded'
            contract=str(row['request_version']) if row['request_version'] else 'historical version not recorded'
            reused='Reused a validated saved decision; no new request for this period. ' if row['decision_source']=='cache' else ''
            return (('Broad app-activity estimate' if network.get('application_categories') else 'Task estimate')+f' · {model}\n'+reused
                +'Used app names and the context permitted at the time. '
                +f"{len(network.get('examples',[]))} remembered examples; {len(network.get('clues',[]))} local match clues. "
                +f"Policy: {policy}. Request contract: {contract}. {reason} "
                +'It does not establish completed output or billing approval.')
        except (ValueError,TypeError,RecursionError):continue
    return 'The entry remains saved, but detailed decision evidence is no longer available. Retention may remove source context. This is not evidence of completed output or billing approval.'

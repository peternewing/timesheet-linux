"""A bounded priority pass through an already authorised day; never new consent."""
from __future__ import annotations
import json
import os
import time
import uuid
from .decision_context import canonical,digest
from .decision_policy import owner_token
from .day_record import bounds


def active(store,now=None):
    now=int(time.time() if now is None else now)
    try:batch=json.loads(store.get('ai_day_pass','{}'))
    except (ValueError,TypeError):return None
    if not isinstance(batch,dict) or batch.get('state')!='running':return None
    config=policy_config(store)
    if (config['mode']=='off' or config['owner']!=owner_token() or
            config['backend']!=('flatpak' if os.environ.get('FLATPAK_ID') else 'native') or
            batch.get('policy')!=digest(config) or now>=batch.get('expires',0)):return None
    return batch


def request(store,day,now=None):
    """Queue a day without changing mode, processing period, data choices or caps."""
    from .automation_store import Repository
    now=int(time.time() if now is None else now);config=Repository(store).config()
    if config['mode']=='off' or config['owner']!=owner_token():raise ValueError('Connect Jev in setup first.')
    if config['backend']!=('flatpak' if os.environ.get('FLATPAK_ID') else 'native'):raise ValueError('Connect Jev for this installation first.')
    if store.get('ai_pause_reason',''):raise ValueError('Jev needs attention before organising this day.')
    start,end=bounds(day);start=max(start,config['since'],now-7*86400)
    end=min(end,now-int(store.get('idle_seconds','300')))
    if start>=end:raise ValueError('No settled activity is within your authorised processing period yet.')
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        # A simultaneous revocation must win over a request from an old screen.
        if digest(policy_config(store))!=digest(config):raise ValueError('Your Jev settings changed. Try again.')
        batch=dict(id=uuid.uuid4().hex,start=start,end=end,expires=now+600,policy=digest(config),state='running',cursor=0,scanned=False)
        store.set('ai_day_pass',canonical(batch))
    return batch


def policy_config(store):
    from .decision_policy import settings
    return settings(store.get('ai_policy','{}'))


def save(store,batch):
    """Do not let a superseded worker overwrite a newer button click."""
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        current=json.loads(store.get('ai_day_pass','{}'))
        if current.get('id')==batch['id']:store.set('ai_day_pass',canonical(batch))


def progress(store,batch):
    rows=store.rows("SELECT state,COUNT(*) count FROM ai_jobs WHERE start>=? AND end<=? GROUP BY state",(batch['start'],batch['end']))
    counts={r['state']:r['count'] for r in rows}
    return dict(waiting=counts.get('pending',0)+counts.get('running',0),
                organised=counts.get('applied',0),uncertain=counts.get('exception',0)+counts.get('failed',0))


def finish_if_ready(store,batch):
    if batch['scanned'] and not progress(store,batch)['waiting']:
        batch={**batch,'state':'done'};save(store,batch)
    return batch


def ready_to_work(store,now=None):
    now=int(time.time() if now is None else now);batch=active(store,now)
    if not batch:return False
    if not batch['scanned']:return True
    # One extra step finalises an empty pass; future retries retain normal pacing.
    return not progress(store,batch)['waiting'] or bool(store.db.execute(
        "SELECT 1 FROM ai_jobs WHERE state='pending' AND due<=? AND start>=? AND end<=? LIMIT 1",
        (now,batch['start'],batch['end'])).fetchone())

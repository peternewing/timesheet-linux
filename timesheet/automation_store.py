"""Durable local jobs, audit and context. Optional additive tables keep v3 readable."""
from __future__ import annotations
import json
import time
from datetime import datetime
from .decision_context import build,canonical,digest,plain
from .decision_policy import settings,route

SCHEMA='''
CREATE TABLE IF NOT EXISTS ai_task_profiles(task_id INTEGER PRIMARY KEY REFERENCES tasks(id),guidance TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ai_jobs(id INTEGER PRIMARY KEY,fingerprint TEXT NOT NULL UNIQUE,activity_id INTEGER NOT NULL,
 start INTEGER NOT NULL,end INTEGER NOT NULL,network TEXT NOT NULL,has_context INTEGER NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending',decision TEXT NOT NULL DEFAULT '{}',reason TEXT NOT NULL DEFAULT '',entry_ids TEXT NOT NULL DEFAULT '[]',
 attempts INTEGER NOT NULL DEFAULT 0,due INTEGER NOT NULL DEFAULT 0,lease_until INTEGER NOT NULL DEFAULT 0,
 created INTEGER NOT NULL,updated INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ai_jobs_due ON ai_jobs(state,due,id);
CREATE INDEX IF NOT EXISTS ai_jobs_activity ON ai_jobs(activity_id,state);
CREATE INDEX IF NOT EXISTS ai_jobs_updated ON ai_jobs(updated);
CREATE TABLE IF NOT EXISTS ai_cache(cache_key TEXT PRIMARY KEY,result TEXT NOT NULL,expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS ai_usage(id INTEGER PRIMARY KEY,job_id INTEGER NOT NULL,at INTEGER NOT NULL,input_tokens INTEGER,
 output_tokens INTEGER,outcome TEXT NOT NULL DEFAULT 'pending');
CREATE INDEX IF NOT EXISTS ai_usage_at ON ai_usage(at);
CREATE TABLE IF NOT EXISTS ai_examples(id INTEGER PRIMARY KEY,activity_id INTEGER NOT NULL UNIQUE,application TEXT NOT NULL,
 task_id INTEGER NOT NULL REFERENCES tasks(id),at INTEGER NOT NULL,scope TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS ai_reviews(id INTEGER PRIMARY KEY,job_id INTEGER NOT NULL UNIQUE,suggested_task INTEGER,
 chosen_task INTEGER NOT NULL,seconds INTEGER NOT NULL,at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS ai_focus(id INTEGER PRIMARY KEY,task_id INTEGER NOT NULL REFERENCES tasks(id),start INTEGER NOT NULL,end INTEGER NOT NULL,draft_default INTEGER NOT NULL DEFAULT 0,CHECK(end>start));
CREATE INDEX IF NOT EXISTS ai_focus_time ON ai_focus(start,end);
'''


class Repository:
    def __init__(self,store):
        self.store=store
        store.db.executescript(SCHEMA)
        if 'scope' not in {r['name'] for r in store.rows('PRAGMA table_info(ai_examples)')}:
            with store.db:store.db.execute("ALTER TABLE ai_examples ADD COLUMN scope TEXT NOT NULL DEFAULT '[]'")
        if 'draft_default' not in {r['name'] for r in store.rows('PRAGMA table_info(ai_focus)')}:
            with store.db:store.db.execute('ALTER TABLE ai_focus ADD COLUMN draft_default INTEGER NOT NULL DEFAULT 0')

    def config(self):return settings(self.store.get('ai_policy','{}'))

    def configure(self,value):
        parsed=settings(canonical(value))
        if value.get('mode')!='off' and parsed['mode']=='off':raise ValueError('Review and accept the current automation data policy.')
        with self.store.db:
            self.store.db.execute('BEGIN IMMEDIATE')
            self.store.set('ai_policy',canonical(parsed))
            self.store.set('ai_pause_reason','')
            self.store.set('ai_discover_after','0')
            # An old/pending response cannot be applied across a consent change.
            self.store.db.execute("UPDATE ai_jobs SET state='stale',reason='Automation policy changed.',updated=? WHERE state IN ('pending','running','exception','failed')",(int(time.time()),))
            self.store.audit('automation policy changed',{'mode':parsed['mode'],'consent_version':parsed['consent_version']})

    def save_profile(self,task_id,guidance):
        self.store.validate_rule_target(task_id)
        guidance=guidance.strip()
        if not plain(guidance,250):raise ValueError('Use at most 250 plain characters for task guidance.')
        row=next(r for r in self.store.tasks() if r['id']==task_id)
        name=' / '.join(row[k] for k in ('client','project','task'))
        if len(name)+len(guidance)+19>500:raise ValueError('Shorten the task name or guidance to fit a 500-character option.')
        with self.store.db:
            self.store.db.execute('INSERT INTO ai_task_profiles VALUES(?,?) ON CONFLICT(task_id) DO UPDATE SET guidance=excluded.guidance',(task_id,guidance))
            self.store.set('ai_discover_after','0')

    def profile_warnings(self,task_id,guidance):
        """Local setup hints only; similarity is not an AI accuracy measure."""
        import re
        from .decision_context import STOPWORDS
        normal=lambda text:' '.join(text.casefold().split())
        words=lambda text:{w.casefold() for w in re.findall(r'\w+',text) if len(w)>=3}-STOPWORDS
        query=words(guidance);warnings=[]
        profiles={r['task_id']:r['guidance'] for r in self.store.rows('SELECT * FROM ai_task_profiles')}
        for task in self.store.tasks():
            if task['id']==task_id:continue
            other=profiles.get(task['id'],'');known=words(other)
            if guidance.strip() and (normal(guidance)==normal(other) or len(query&known)>=3 and len(query&known)/max(1,len(query|known))>=.75):
                warnings.append('Similar guidance: '+task['client']+' / '+task['project']+' / '+task['task']+'. Say what distinguishes these tasks.')
        return warnings[:5]

    def progress(self,start,end):
        """Local descriptive metrics, not precision estimated from selective reviews."""
        entry=self.store.db.execute("SELECT COUNT(*) count,COALESCE(SUM(MIN(end,?)-MAX(start,?)),0) seconds FROM entries WHERE deleted=0 AND origin='jev' AND start<? AND end>?",(end,start,end,start)).fetchone()
        review=self.store.db.execute('SELECT COUNT(*) count,COALESCE(SUM(suggested_task=chosen_task),0) kept FROM ai_reviews WHERE at>=? AND at<?',(start,end)).fetchone()
        usage=self.store.db.execute('SELECT COUNT(*) count,COALESCE(SUM(input_tokens),0) tokens FROM ai_usage WHERE at>=? AND at<?',(start,end)).fetchone()
        return dict(automatic_entries=entry['count'],automatic_seconds=entry['seconds'],reviewed_exceptions=review['count'],suggestions_kept=review['kept'],requests=usage['count'],input_tokens=usage['tokens'])

    def set_focus(self,task_id,minutes=60,now=None,*,draft_default=False):
        self.store.validate_rule_target(task_id)
        if type(draft_default) is not bool:raise ValueError('Choose whether this focus is a draft default.')
        if type(minutes) is not int or minutes not in (15,30,60,120,240):raise ValueError('Choose a supported focus duration.')
        now=int(time.time() if now is None else now)
        with self.store.db:
            self.store.db.execute('DELETE FROM ai_focus WHERE start>=?',(now,))
            self.store.db.execute('UPDATE ai_focus SET end=? WHERE start<? AND end>?',(now,now,now))
            self.store.db.execute('INSERT INTO ai_focus(task_id,start,end,draft_default) VALUES(?,?,?,?)',(task_id,now,now+minutes*60,int(bool(draft_default))))
            self.store.set('ai_discover_after','0')
            self.store.audit('Jev focus chosen',{'task_id':task_id,'minutes':minutes})

    def clear_focus(self,now=None):
        now=int(time.time() if now is None else now)
        with self.store.db:
            self.store.db.execute('DELETE FROM ai_focus WHERE start>=?',(now,))
            self.store.db.execute('UPDATE ai_focus SET end=? WHERE start<? AND end>?',(now,now,now))
            self.store.set('ai_discover_after','0')

    def current_focus(self,now=None):
        now=int(time.time() if now is None else now)
        return self.store.db.execute('SELECT * FROM ai_focus WHERE start<=? AND end>? ORDER BY start DESC LIMIT 1',(now,now)).fetchone()

    def context(self,activity,config=None,*,start=None,end=None):return build(self.store,activity,self,config or self.config(),start=start,end=end)

    def discover(self,now=None,limit=100):
        now=int(time.time() if now is None else now);config=self.config()
        if config['mode']=='off':return 0
        since=max(config['since'],now-7*86400);cutoff=now-int(self.store.get('idle_seconds','300'))
        try:cursor=int(self.store.get('ai_discover_after','0'))
        except ValueError:cursor=0
        rows=self.store.rows("""SELECT a.* FROM activity a WHERE a.id>? AND a.start>=? AND a.end<=?
            AND a.closed=1 AND a.state='active' AND NOT EXISTS(SELECT 1 FROM ai_jobs j WHERE j.activity_id=a.id
            AND j.state IN ('applied','dismissed')) ORDER BY a.id LIMIT ?""",(cursor,since,cutoff,min(max(1,limit),200)))
        count=0
        with self.store.db:
            for activity in rows:
                periods=[]
                for start,end in self.store.uncovered(activity['start'],activity['end'],now):
                    boundaries={start,end}
                    if config['allow_focus']:
                        for focus in self.store.rows('SELECT start,end FROM ai_focus WHERE start<? AND end>?',(end,start)):
                            boundaries.update(max(start,min(end,focus[k])) for k in ('start','end'))
                    for rule in self.store.rows('SELECT app,title,created FROM rules WHERE enabled=1 AND created>? AND created<?',(start,end)):
                        if rule['app'].casefold()==activity['app'].casefold() and rule['title'].casefold() in activity['title'].casefold():boundaries.add(rule['created'])
                    # Keep entries and exception scopes within local calendar days.
                    from datetime import timedelta
                    midnight=datetime.combine(datetime.fromtimestamp(start).date()+timedelta(days=1),datetime.min.time())
                    while int(midnight.timestamp())<end:
                        boundaries.add(int(midnight.timestamp()));midnight+=timedelta(days=1)
                    points=sorted(boundaries);periods.extend(zip(points,points[1:]))
                for start,end in periods:
                    context,reason=self.context(activity,config,start=start,end=end)
                    if context is None:continue
                    # Job ranges reserve no time; application rechecks allocation.
                    fingerprint=digest([context['fingerprint'],start,end])
                    changed=self.store.db.execute('''INSERT OR IGNORE INTO ai_jobs(fingerprint,activity_id,start,end,network,has_context,created,updated)
                        VALUES(?,?,?,?,?,?,?,?)''',(fingerprint,activity['id'],start,end,canonical(context['network']),int(context['has_context']),now,now)).rowcount
                    count+=changed
                    if not changed:self.store.db.execute("UPDATE ai_jobs SET state='pending',reason='',attempts=0,due=0,updated=? WHERE fingerprint=? AND state='stale'",(now,fingerprint))
            self.store.set('ai_discover_after',rows[-1]['id'] if rows else 0)
        return count

    def fresh(self,job):
        config=self.config()
        if config['mode']=='off':return False
        activity=self.store.db.execute('SELECT * FROM activity WHERE id=?',(job['activity_id'],)).fetchone()
        if not activity:return False
        context,_=self.context(activity,config,start=job['start'],end=job['end'])
        return bool(context and job['fingerprint']==digest([context['fingerprint'],job['start'],job['end']])
                    and job['network']==canonical(context['network']) and bool(job['has_context'])==context['has_context']
                    and activity['start']<=job['start']<job['end']<=activity['end']
                    and self.store.uncovered(job['start'],job['end'])==[(job['start'],job['end'])])

    def claim(self,now=None):
        now=int(time.time() if now is None else now)
        with self.store.db:
            self.store.db.execute('BEGIN IMMEDIATE')
            # A request might already have reached the provider. Recover the lease
            # into review instead of sending the same unknown request again.
            self.store.db.execute("UPDATE ai_jobs SET state='failed',reason='Interrupted request: outcome unknown. Retry explicitly if needed.',updated=? WHERE state='running' AND lease_until<?",(now,now))
            job=self.store.db.execute("SELECT * FROM ai_jobs WHERE state='pending' AND due<=? ORDER BY id LIMIT 1",(now,)).fetchone()
            if not job:return None
            self.store.db.execute("UPDATE ai_jobs SET state='running',attempts=attempts+1,lease_until=?,updated=? WHERE id=?",(now+120,now,job['id']))
            return dict(self.store.db.execute('SELECT * FROM ai_jobs WHERE id=?',(job['id'],)).fetchone())

    def transition(self,job_id,state,reason):
        with self.store.db:self.store.db.execute('UPDATE ai_jobs SET state=?,reason=?,updated=?,lease_until=0 WHERE id=?',(state,reason,int(time.time()),job_id))

    def usage(self,now=None):
        now=int(time.time() if now is None else now);day=datetime.fromtimestamp(now).date()
        start=int(datetime.combine(day,datetime.min.time()).timestamp())
        row=self.store.db.execute("SELECT COUNT(*) requests,COALESCE(SUM(input_tokens),0) tokens,SUM(input_tokens IS NULL AND outcome!='acknowledged unknown') unknown FROM ai_usage WHERE at>=?",(start,)).fetchone()
        return dict(requests=row['requests'],tokens=row['tokens'],unknown=row['unknown'] or 0)

    def reserve_request(self,job,now=None):
        now=int(time.time() if now is None else now)
        with self.store.db:
            self.store.db.execute('BEGIN IMMEDIATE');config=self.config();used=self.usage(now)
            if config['mode']=='off':return None,'Automation is off.'
            if not self.fresh(job):return None,'The activity or automation policy changed.'
            if used['unknown']:return None,'A request has unknown usage. Review usage before sending more.'
            if used['requests']>=config['daily_requests']:return None,'Daily request limit reached.'
            if used['tokens']>=config['daily_tokens']:return None,'Daily reported input-token limit reached.'
            return self.store.db.execute('INSERT INTO ai_usage(job_id,at) VALUES(?,?)',(job['id'],now)).lastrowid,None

    def account(self,usage_id,result=None,outcome='success'):
        usage=(result or {}).get('usage')
        with self.store.db:self.store.db.execute('UPDATE ai_usage SET input_tokens=?,output_tokens=?,outcome=? WHERE id=?',
            (usage.get('input_tokens') if usage else None,usage.get('output_tokens') if usage else None,outcome,usage_id))

    def complete(self,job,result):
        network=json.loads(job['network'])
        action,reason=route(result,self.config()['mode'],has_context=bool(job['has_context']),focus_task=network.get('focus'),focus_default=network.get('focus_default',False),application_categories=network.get('application_categories',False))
        with self.store.db:
            self.store.db.execute('BEGIN IMMEDIATE')
            if not self.fresh(job):
                self.store.db.execute("UPDATE ai_jobs SET state='stale',reason='Evidence, privacy choices, tasks or assignments changed.',updated=?,lease_until=0 WHERE id=?",(int(time.time()),job['id']))
                return 'stale'
            current=self.store.db.execute('SELECT state FROM ai_jobs WHERE id=?',(job['id'],)).fetchone()
            if not current or current['state']!='running':return 'stale'
            entry_ids=[]
            if action=='apply':
                self.store.validate_rule_target(result['task'])
                from .decision_policy import probability
                category=result.get('work_kind','other') if probability(result.get('work_kind_probability')) and result['work_kind_probability']>=.8 else 'application'
                task_name=self.store.db.execute('SELECT name FROM tasks WHERE id=?',(result['task'],)).fetchone()[0]
                description=task_name+' — '+(category if category not in ('other','application') else 'recorded application use')
                eid=self.store.db.execute("""INSERT INTO entries(task_id,start,end,description,origin,activity_id)
                    VALUES(?,?,?,?, 'jev',?)""",(result['task'],job['start'],job['end'],description,job['activity_id'])).lastrowid
                if result['task'] in self.config().get('category_tasks',[]):self.store.db.execute('UPDATE entries SET billable=0 WHERE id=?',(eid,))
                entry_ids=[eid];self.store._record_change('Jev automatic assignment',[],entry_ids)
                self.store.audit('Jev draft assigned',{'job_id':job['id'],'entry_id':eid,'policy':1})
            state='applied' if entry_ids else 'exception'
            self.store.db.execute('UPDATE ai_jobs SET state=?,decision=?,reason=?,entry_ids=?,updated=?,lease_until=0 WHERE id=?',
                (state,canonical(result),reason,canonical(entry_ids),int(time.time()),job['id']))
            return state

    def correct(self,job_id,task_id,*,remember=False,similar=False,job_ids=None):
        """Human decisions can affect only still-unassigned matching review jobs."""
        self.store.validate_rule_target(task_id)
        job=self.store.db.execute('SELECT * FROM ai_jobs WHERE id=?',(job_id,)).fetchone()
        if not job or job['state']!='exception':raise ValueError('This decision is no longer waiting for review.')
        chosen=[job]
        if similar:
            chosen=self.matching_scope(job)
        if job_ids is not None:
            if not isinstance(job_ids,(list,tuple)) or not 1<=len(job_ids)<=100 or job_id not in job_ids or any(type(i) is not int for i in job_ids):raise ValueError('Choose a valid review scope.')
            chosen=self.store.rows('SELECT * FROM ai_jobs WHERE id IN ('+','.join('?' for _ in job_ids)+')',tuple(job_ids))
            if len(chosen)!=len(set(job_ids)) or any(r['state']!='exception' or r['network']!=job['network'] for r in chosen):raise ValueError('The matching decisions changed. Refresh the preview.')
        with self.store.db:
            self.store.db.execute('BEGIN IMMEDIATE');ids=[]
            if any(not self.fresh(item) for item in chosen):raise ValueError('Some activity changed. Refresh decisions before assigning.')
            for item in chosen:
                decision=json.loads(item['decision'])
                eid=self.store.db.execute("INSERT INTO entries(task_id,start,end,description,origin,activity_id) VALUES(?,?,?,'Reviewed work','assigned',?)",(task_id,item['start'],item['end'],item['activity_id'])).lastrowid
                if task_id in self.config().get('category_tasks',[]):self.store.db.execute('UPDATE entries SET billable=0 WHERE id=?',(eid,))
                ids.append(eid)
                self.store.db.execute("UPDATE ai_jobs SET state='applied',entry_ids=?,reason='Task chosen by user.',updated=? WHERE id=?",(canonical([eid]),int(time.time()),item['id']))
                self.store.db.execute('INSERT OR IGNORE INTO ai_reviews(job_id,suggested_task,chosen_task,seconds,at) VALUES(?,?,?,?,?)',(item['id'],decision.get('task'),task_id,item['end']-item['start'],int(time.time())))
                if remember:
                    app=json.loads(item['network'])['applications'][0]
                    saved_network=json.loads(item['network'])
                    scope=canonical({'clues':saved_network.get('clues',[]),'focus':saved_network.get('focus')})
                    self.store.db.execute('INSERT INTO ai_examples(activity_id,application,task_id,at,scope) VALUES(?,?,?,?,?) ON CONFLICT(activity_id) DO UPDATE SET task_id=excluded.task_id,at=excluded.at,scope=excluded.scope',(item['activity_id'],app,task_id,int(time.time()),scope))
            self.store._record_change('Review Jev decisions',[],ids)
            self.store.audit('Jev decisions reviewed',{'jobs':len(chosen),'remember':remember})
        return len(ids)

    def matching_scope(self,job):
        """A previewable nearby session, never a blanket application-wide edit."""
        from .review import sessions
        from datetime import timedelta
        day=datetime.fromtimestamp(job['start']).date()
        start=max(int(datetime.combine(day,datetime.min.time()).timestamp()),job['start']-1800)
        end=min(int(datetime.combine(day+timedelta(days=1),datetime.min.time()).timestamp()),job['end']+1800)
        rows=self.store.rows("SELECT * FROM ai_jobs WHERE state='exception' AND network=? AND start>=? AND end<=? ORDER BY start LIMIT 100",(job['network'],start,end))
        app=json.loads(job['network'])['applications'][0]
        records=[dict(id=r['id'],start=r['start'],end=r['end'],app=app,state='active',closed=1) for r in rows]
        barriers=self.store.activity_for(start,end)+[dict(start=r['start'],end=r['end'],state='assigned',closed=1) for r in self.store.entries(start,end)]
        for group in sessions(records,barriers=barriers):
            ids={r['id'] for r in group['blocks']}
            if job['id'] in ids:return [r for r in rows if r['id'] in ids]
        return [job]

    def reset_model(self):
        config={**self.config(),'mode':'suggest'}
        self.configure(config)
        with self.store.db:
            self.store.set('ai_pinned_model','jev-latest')
            self.store.db.execute('DELETE FROM ai_cache')

    def resume(self):
        with self.store.db:
            self.store.db.execute('BEGIN IMMEDIATE')
            self.store.set('ai_pause_reason','')
            self.store.db.execute("UPDATE ai_jobs SET state='pending',attempts=0,due=0 WHERE state='failed' AND EXISTS(SELECT 1 FROM ai_usage u WHERE u.job_id=ai_jobs.id AND u.outcome='provider rejection')")

    def review_rows(self):
        rows=self.store.rows("SELECT * FROM ai_jobs WHERE state IN ('exception','failed') ORDER BY start DESC LIMIT 1000")
        clean=[]
        for row in rows:
            try:
                if len(row['network'])>64000 or len(row['decision'])>64000:raise ValueError()
                network=json.loads(row['network']);decision=json.loads(row['decision'])
                if not isinstance(network,dict) or not isinstance(decision,dict) or not isinstance(network.get('applications'),list) or not network['applications']:raise ValueError()
                if not all(plain(n,200) for n in network['applications']):raise ValueError()
                if not self.fresh(row):
                    self.transition(row['id'],'stale','Evidence or permitted context changed. Background discovery will reconsider unassigned work.')
                    continue
            except (ValueError,TypeError,RecursionError):
                self.transition(row['id'],'stale','Stored context is invalid. Original activity remains in Calendar.')
                continue
            clean.append(row)
        return clean

    def dismiss(self,job_id):
        self.transition(job_id,'dismissed','User left this activity for manual review.')

    def acknowledge_unknown_usage(self):
        with self.store.db:
            self.store.db.execute("UPDATE ai_usage SET outcome='acknowledged unknown' WHERE input_tokens IS NULL")
            self.store.set('ai_pause_reason','')
            self.store.audit('unknown API usage acknowledged',{})

    def prune(self,now=None):
        """Keep detailed AI context no longer than its source activity."""
        now=int(time.time() if now is None else now)
        with self.store.db:
            self.store.db.execute('DELETE FROM ai_cache WHERE expires<=?',(now,))
            for row in self.store.rows("SELECT id,decision FROM ai_jobs WHERE network!='{}' AND NOT EXISTS(SELECT 1 FROM activity a WHERE a.id=ai_jobs.activity_id)"):
                try:
                    result=json.loads(row['decision']) if len(row['decision'])<64000 else {}
                    minimal={k:result[k] for k in ('model','task','probability','work_kind') if isinstance(result,dict) and k in result}
                except (ValueError,TypeError,RecursionError):minimal={}
                self.store.db.execute("UPDATE ai_jobs SET network='{}',decision=?,has_context=0,reason='Detailed context removed with source activity.',state=CASE WHEN state='applied' THEN 'applied' ELSE 'stale' END WHERE id=?",(canonical(minimal),row['id']))
            self.store.db.execute('DELETE FROM ai_examples WHERE NOT EXISTS(SELECT 1 FROM activity a WHERE a.id=ai_examples.activity_id)')
            self.store.db.execute('DELETE FROM ai_focus WHERE end<?',(now-int(self.store.get('retention_days','30'))*86400,))

    def forget_examples(self):
        with self.store.db:
            self.store.db.execute('DELETE FROM ai_examples')
            self.store.set('ai_discover_after','0')
            self.store.audit('remembered Jev corrections cleared',{})

    def reset_after_restore(self):
        with self.store.db:
            self.store.db.execute('BEGIN IMMEDIATE')
            config=self.config();config['mode']='off';self.store.set('ai_policy',canonical(config))
            self.store.db.execute("UPDATE ai_jobs SET state='stale',reason='Backup restored: enable automation again explicitly.' WHERE state IN ('pending','running','exception')")
            self.store.db.execute('DELETE FROM ai_cache')
            self.store.set('ai_pause_reason','Automation is off after restoring a backup.')

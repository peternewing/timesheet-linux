"""Independent Jev worker. Network latency never enters the recording collector."""
from __future__ import annotations
import argparse
import fcntl
import json
import os
import signal
import time
from . import jev
from .automation_store import Repository
from .decision_context import canonical,digest
from .decision_policy import owner_token
from .decision_contract import valid_result
from .store import Store,DATA_DIR


class Engine:
    def __init__(self,store,*,request=None,key=None):
        self.store=store;self.repo=Repository(store)
        self.request=request or jev.decide;self.key=key or jev.get_key

    def pause(self,reason,kind='attention',now=None):
        self.store.set('ai_pause_reason',reason);self.store.set('ai_pause_kind',kind)
        self.store.set('ai_pause_day',time.strftime('%Y-%m-%d',time.localtime(time.time() if now is None else now)))

    def step(self,now=None):
        now=int(time.time() if now is None else now);config=self.repo.config()
        self.store.set('ai_worker_seen',now)
        from .daily_choices import apply_saved
        apply_saved(self.store,now)
        from .local_types import apply as apply_local_types
        apply_local_types(self.store,now)
        if config['mode']=='off':return 'off'
        if config['backend']!=('flatpak' if os.environ.get('FLATPAK_ID') else 'native'):return 'other installation'
        if config['owner']!=owner_token():return 'other installation'
        try:
            backoff=int(self.store.get('ai_backoff_until','0') or 0)
            if not 0<=backoff<=now+86400:raise ValueError('Invalid retry clock')
        except (ValueError,TypeError):
            self.store.set('ai_backoff_until',0)
            self.pause('Local retry timing was invalid and has been reset. Review usage, then Resume automation.','attention',now)
            return 'paused'
        if now<backoff:return 'backoff'
        try:last_prune=int(self.store.get('ai_last_prune','0') or 0)
        except (ValueError,TypeError):last_prune=0
        if not 0<=last_prune<=now+300:last_prune=0
        if now-last_prune>3600:
            self.repo.prune(now);self.store.set('ai_last_prune',now)
        reason=self.store.get('ai_pause_reason','')
        if reason:
            day=time.strftime('%Y-%m-%d',time.localtime(now))
            if self.store.get('ai_pause_kind')=='budget' and self.store.get('ai_pause_day')!=day:
                self.store.set('ai_pause_reason','')
            else:return 'paused'
        from .day_organiser import active,finish_if_ready
        batch=active(self.store,now)
        self.repo.discover(now,batch=batch)
        job=self.repo.claim(now,batch=batch)
        if not job:
            if batch:finish_if_ready(self.store,batch)
            return 'idle'
        if not self.repo.fresh(job):
            self.repo.transition(job['id'],'stale','Evidence or permission changed before sending.');return 'stale'
        network=json.loads(job['network']);model=self.store.get('ai_pinned_model','jev-latest')
        try:
            payload=jev.prepare_decision(network['applications'],network['tasks'],examples=network['examples'],clues=network['clues'],focus=network.get('focus'),focus_default=network.get('focus_default',False),model=model,application_categories=network.get('application_categories',False))
        except jev.JevError:
            self.repo.transition(job['id'],'failed','The selected context or model is not supported. Review task guidance.');return 'failed'
        cache_key=digest([jev.REQUEST_VERSION,payload])
        cached=self.store.db.execute('SELECT CASE WHEN length(result)<=64000 THEN result END result FROM ai_cache WHERE cache_key=? AND expires>?',(cache_key,now)).fetchone()
        result=None
        source='provider'
        if cached and cached['result'] is not None:
            try:
                result=json.loads(cached['result'])
                if not valid_result(result,network['tasks'],model):result=None
            except (ValueError,TypeError,RecursionError):result=None
        if result is None:
            blocked=self.repo.request_blocker(now)
            if blocked:
                self.repo.transition(job['id'],'pending',blocked)
                self.pause(blocked,'budget' if 'limit reached' in blocked else 'attention',now);return 'paused'
            try:key=self.key()
            except Exception:
                self.repo.transition(job['id'],'pending','Secure key unavailable; unlock it and Resume automation.')
                self.pause('Secure key unavailable. Unlock your desktop keyring, then Resume automation.');return 'paused'
            usage_id,blocked=self.repo.reserve_request(job,now)
            if usage_id is None:
                self.repo.transition(job['id'],'pending',blocked)
                self.pause(blocked,'budget' if 'limit reached' in blocked else 'attention',now);return 'paused'
            try:
                result=self.request(network['applications'],network['tasks'],key,examples=network['examples'],clues=network['clues'],focus=network.get('focus'),focus_default=network.get('focus_default',False),model=model,application_categories=network.get('application_categories',False))
                if not valid_result(result,network['tasks'],model):raise jev.JevError('The decision metadata is incomplete.')
                self.repo.account(usage_id,result)
            except Exception as exc:
                # Rejected authentication/credit/rate-limit requests never returned
                # an inference. Timeouts and server failures have unknown usage;
                # require acknowledgement rather than silently charging a retry.
                known=isinstance(exc,jev.JevError) and exc.status in (401,402,403,429)
                self.repo.account(usage_id,{'usage':{'input_tokens':0,'output_tokens':0}} if known else None,'provider rejection' if known else 'unknown')
                reason=str(exc) if isinstance(exc,jev.JevError) else 'The decision request failed.'
                if known and exc.status==429 and job['attempts']<3:
                    self.store.set('ai_backoff_until',now+30*2**job['attempts'])
                    with self.store.db:self.store.db.execute("UPDATE ai_jobs SET state='pending',due=?,reason=?,lease_until=0 WHERE id=?",(now+30*2**job['attempts'],reason,job['id']))
                    return 'retry'
                self.repo.transition(job['id'],'failed',reason)
                self.pause(reason if known else 'A request failed with unknown usage. Review usage before resuming.')
                return 'paused'
            finally:key=None
            with self.store.db:
                self.store.db.execute('INSERT OR REPLACE INTO ai_cache VALUES(?,?,?)',(cache_key,canonical(result),now+7*86400))
                if model=='jev-latest':
                    # Pin the first reported version. Retired/changed versions
                    # pause instead of silently changing the decision model.
                    self.store.set('ai_pinned_model',result['model'])
                    payload['model']=result['model']
                    self.store.db.execute('INSERT OR REPLACE INTO ai_cache VALUES(?,?,?)',(digest([jev.REQUEST_VERSION,payload]),canonical(result),now+7*86400))
        else:source='cache'
        return self.repo.complete(job,result,source=source)



def run(*,once=False):
    DATA_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(DATA_DIR/'automation.lock','a+') as lock:
        os.chmod(lock.name,0o600)
        deadline=time.monotonic()+(0 if once else 20)
        while True:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:
                if time.monotonic()>=deadline:return 0
                time.sleep(.2)
        stopped=[False]
        def stop(*_):stopped[0]=True
        signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
        store=Store();engine=Engine(store)
        pid=DATA_DIR/'automation.pid';pid.write_text(str(os.getpid()));pid.chmod(0o600)
        try:
            while not stopped[0]:
                state='paused'
                try:
                    state=engine.step()
                    if state in ('off','other installation'):break
                except Exception:
                    engine.pause('Automation stopped after a local error. Your recorder is independent. Review and Resume when ready.')
                if once:break
                from .day_organiser import active,ready_to_work
                # A requested day drains promptly under the same single-worker lock.
                # Pauses/backoff/retry retain normal pacing and all usage gates.
                if state in ('applied','exception','stale','idle') and ready_to_work(store):continue
                waiting_pass=active(store)
                for _ in range(50):
                    if stopped[0] or (not waiting_pass and active(store)):break
                    time.sleep(.1)
        finally:
            store.close();pid.unlink(missing_ok=True)
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Process permitted Jev decisions independently from recording')
    parser.add_argument('--once',action='store_true');args=parser.parse_args();raise SystemExit(run(once=args.once))

"""Sustained synthetic collector/worker/insights exercise, never real capture or AI.

Run explicitly with --seconds. One real second creates one synthetic second.
This measures process behaviour on this machine, not real desktop/API acceptance.
"""
import argparse,hashlib,json,resource,tempfile,threading,time,traceback
from pathlib import Path
from datetime import datetime
from timesheet.store import Store
from timesheet.collector import Collector
from timesheet.automation_worker import Engine
from timesheet.automation_store import Repository
from timesheet.simple_setup import finish_setup,BUCKETS
from timesheet import screen_time,screen_spaces


def run(seconds,output,exercise_schedules=False):
    if not 1<=seconds<=86400:raise ValueError('Use 1–86400 seconds.')
    started=time.monotonic();cpu=time.process_time();base=int(time.time())
    loaded={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('timesheet').glob('*.py')}
    result=dict(evidence='sustained synthetic process exercise; no real desktop capture or provider',requested_seconds=seconds,
        source_hashes_at_start=loaded,iterations=0,provider_calls=0,screen_reads=0,week_reads=0,integrity_checks=0,
        unknown_acknowledgements=0,context_switches=0,worker_steps=0,max_iteration_seconds=0,failures=[])
    result['harness_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();result['schedule_changes']=0
    shared={'now':base};stop=threading.Event()
    def save():
        result.update(elapsed_seconds=time.monotonic()-started,cpu_seconds=time.process_time()-cpu,
            peak_process_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        temp=output.with_suffix('.tmp');temp.write_text(json.dumps(result,indent=2)+'\n');temp.replace(output)
    with tempfile.TemporaryDirectory(prefix='timesheet-screen-soak-') as folder:
        path=Path(folder)/'synthetic.sqlite3';store=Store(path);store.set('capture_enabled','1');store.set('idle_seconds','1')
        store.set('excluded_apps','Private app');config=finish_setup(store,list(BUCKETS),connected=True,now=base-86400)
        ids=config['category_tasks'];collector=Collector(store)
        def worker():
            child=Store(path)
            def request(apps,tasks,key,**kw):
                result['provider_calls']+=1;time.sleep(.05)
                ambiguous=apps==['Browser'];task=None if ambiguous else ids[0]
                n=len(ids);chosen=.96;rest=.03/(n-1) if n>1 else 0
                probabilities=[(i,(.4/n if ambiguous else chosen if i==task else rest)) for i in ids]
                probabilities.sort(key=lambda x:(-x[1],x[0]))
                return dict(task=task,probability=.6 if ambiguous else chosen,none_probability=.6 if ambiguous else .01,
                    alternatives=probabilities,personal=.1,enough_evidence=.2 if ambiguous else .99,work_kind='other',
                    model='jev-soak-synthetic',usage={'input_tokens':100,'output_tokens':10})
            engine=Engine(child,request=request,key=lambda:'synthetic-only')
            try:
                while not stop.is_set():
                    engine.step(shared['now']+2);result['worker_steps']+=1;stop.wait(.2)
            except Exception:result['failures'].append(traceback.format_exc());stop.set()
            finally:child.close()
        thread=threading.Thread(target=worker,daemon=True);thread.start()
        try:
            for i in range(seconds):
                tick=time.monotonic();now=base+i;shared['now']=now
                if stop.is_set():break
                app=('Editor','Browser','Player','Private app')[(i//90)%4]
                phase=i%120
                state=None if 100<=phase<105 else (app,'DO_NOT_EXPORT /private/secret',5000 if 80<=phase<90 else 0,90<=phase<100)
                collector.step(now,now,state)
                if exercise_schedules and i%900==0:
                    screen_spaces.use_schedule(store,'weekdays_9_17',now);result['schedule_changes']+=1
                elif i%300==0:
                    screen_spaces.switch(store,'personal' if (i//300)%2==0 else 'work',now);result['context_switches']+=1
                if i%600==500:
                    with store.db:store.db.execute("INSERT INTO ai_usage(job_id,at,outcome) VALUES(-1,?,'unknown')",(now-86400,))
                if i%600==505:Repository(store).acknowledge_unknown_usage();result['unknown_acknowledgements']+=1
                if i%10==0:
                    day=datetime.fromtimestamp(now).date();value=screen_time.summary(store,day,now)
                    assert value['screen_seconds']==value['named_seconds']+value['private_seconds']
                    assert sum(n for _,n in value['apps'])==value['named_seconds']
                    assert value['screen_seconds']<=value['observed_seconds']
                    assert 'DO_NOT_EXPORT' not in str(value);assert 'Private app' not in str(value)
                    result['screen_reads']+=1
                if i%60==0:
                    screen_time.week(store,datetime.fromtimestamp(now).date(),now);result['week_reads']+=1
                    assert store.db.execute('PRAGMA quick_check').fetchone()[0]=='ok';result['integrity_checks']+=1
                result['iterations']=i+1;result['max_iteration_seconds']=max(result['max_iteration_seconds'],time.monotonic()-tick)
                if i%30==0:save();print(json.dumps({k:result[k] for k in ('iterations','worker_steps','provider_calls','screen_reads','elapsed_seconds')}),flush=True)
                remaining=started+i+1-time.monotonic()
                if remaining>0:stop.wait(remaining)
        except Exception:result['failures'].append(traceback.format_exc())
        finally:
            stop.set();thread.join(20);collector.close();store.close()
            if thread.is_alive():result['failures'].append('Worker did not shut down within 20 seconds.')
            result['complete']=result['iterations']==seconds and not result['failures'];save()
    print('PASS' if result['complete'] else 'FAIL',json.dumps({k:result[k] for k in ('iterations','elapsed_seconds','cpu_seconds','peak_process_rss_kib','failures')}),flush=True)
    return 0 if result['complete'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--seconds',type=int,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--exercise-schedules',action='store_true')
    args=parser.parse_args();raise SystemExit(run(args.seconds,args.output,args.exercise_schedules))

"""A separate decision process and concurrent recorder-like writes, all synthetic."""
import json,os,subprocess,sys,tempfile,time
from pathlib import Path
from timesheet.store import Store
from timesheet.automation_store import Repository
from timesheet.decision_policy import DEFAULTS,owner_token

CHILD=r'''
import json,sys,time
from timesheet.store import Store
from timesheet.automation_worker import Engine
store=Store(sys.argv[1])
def request(apps,tasks,key,**kw):
    time.sleep(.5)
    task=kw['focus']
    return dict(task=task,probability=.9,none_probability=.1,alternatives=[(task,.9)],personal=.1,enough_evidence=.5,
        work_kind='development',work_kind_probability=.9,model='jev-process-test',usage={'input_tokens':100,'output_tokens':10})
engine=Engine(store,request=request,key=lambda:'synthetic-only')
print(engine.step(int(sys.argv[2])),flush=True)
store.close()
'''

with tempfile.TemporaryDirectory(prefix='timesheet-worker-process-') as folder:
    path=Path(folder)/'db.sqlite3';store=Store(path);task=store.quick_project('Synthetic','Project','Development',6000);repo=Repository(store)
    now=int(time.time());repo.configure({**DEFAULTS,'mode':'automatic','consent_version':1,'owner':owner_token(),'since':now-5000})
    repo.set_focus(task,60,now=now-2500,draft_default=True)
    with store.db:store.db.execute("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,'Editor','active',1)",(now-2000,now-1000))
    process=subprocess.Popen([sys.executable,'-c',CHILD,str(path),str(now)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    started=time.monotonic();writes=0
    while process.poll() is None and time.monotonic()-started<10:
        with store.db:store.db.execute("UPDATE runtime SET collector_seen=?,capture_status='active' WHERE id=1",(now+writes,))
        writes+=1;time.sleep(.03)
    out,err=process.communicate(timeout=5)
    assert process.returncode==0,(out,err)
    assert out.strip()=='applied',(out,err)
    assert writes>=3,'Recorder-like writes must progress during network latency'
    entries=store.entries(0,now);assert len(entries)==1 and entries[0]['status']=='draft'
    assert store.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    print('PASS: separate worker process, concurrent recording writes, durable draft and integrity',flush=True)
    # Production entry point stays off with default policy, requiring no key/network.
    off=Path(folder)/'off';env={**os.environ,'XDG_DATA_HOME':str(off),'TIMESHEET_TESTING':'1'}
    result=subprocess.run([sys.executable,'-m','timesheet.automation_worker','--once'],env=env,capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    assert not (off/'time-sheet-linux/automation.pid').exists()
    print('PASS: one-shot daemon entry point is safe by default and cleans its PID file',flush=True)
    store.close()

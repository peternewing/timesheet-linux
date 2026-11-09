"""Repeatable, disposable synthetic discovery benchmark. Never reads user records."""
import argparse,json,platform,resource,tempfile,time
from pathlib import Path
from .store import Store
from .automation_store import Repository
from .decision_policy import DEFAULTS,owner_token
from . import __version__


def run(observations=20000,batches=5):
    if type(observations) is not int or not 100<=observations<=200000:raise ValueError('Use 100–200000 synthetic observations.')
    if type(batches) is not int or not 1<=batches<=20:raise ValueError('Use 1–20 bounded batches.')
    with tempfile.TemporaryDirectory(prefix='timesheet-benchmark-') as folder:
        store=Store(Path(folder)/'synthetic.sqlite3')
        try:
            repo=Repository(store);now=int(time.time());base=now-observations*2-1000
            for i in range(20):store.quick_project('Synthetic client',f'Project {i}','Task')
            repo.configure({**DEFAULTS,'mode':'suggest','consent_version':1,'owner':owner_token(),'since':base})
            with store.db:store.db.executemany("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,'Synthetic editor','active',1)",((base+i*2,base+i*2+2) for i in range(observations)))
            timings=[];created=[]
            for _ in range(batches):
                started=time.perf_counter();created.append(repo.discover(now));timings.append(time.perf_counter()-started)
            return dict(evidence='synthetic bounded discovery; not sustained desktop performance',
                version=__version__,python=platform.python_version(),observations=observations,tasks=20,batch_limit=100,
                created_jobs=created,batch_seconds=timings,peak_process_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        finally:store.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observations',type=int,default=20000);parser.add_argument('--batches',type=int,default=5)
    args=parser.parse_args();print(json.dumps(run(args.observations,args.batches),indent=2))

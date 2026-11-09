"""Disposable retained-data screen-time benchmark; no user activity or network."""
import argparse,hashlib,json,platform,resource,statistics,tempfile,time
from pathlib import Path
from datetime import datetime
from timesheet.store import Store
from timesheet import screen_time,screen_spaces
from timesheet.day_record import snapshot


def run(count=200000,repeats=10,*,now=None):
    if type(count) is not int or not 1000<=count<=1000000 or type(repeats) is not int or not 1<=repeats<=50:raise ValueError('Choose 1000–1000000 observations and 1–50 reads.')
    now=int(time.time() if now is None else now);span=30*86400;start=now-span;day=datetime.fromtimestamp(now-1).date()
    with tempfile.TemporaryDirectory(prefix='timesheet-screen-benchmark-') as folder:
        store=Store(Path(folder)/'db')
        try:
            t=time.perf_counter()
            with store.db:
                store.db.executemany('INSERT INTO activity(start,end,app,title,state,closed,capture_version) VALUES(?,?,?,?,?,1,2)',
                    ((start+i*span//count,start+(i+1)*span//count,'App '+str(i%100) if i%20 else '', 'DO_NOT_EXPORT /private/file' if i%20 else '', 'active' if i%20 else 'excluded') for i in range(count)))
            insert=time.perf_counter()-t
            screen_spaces.use_schedule(store,'weekdays_9_17',start)
            assert screen_time.summary(store,day,now)['screen_seconds']>0
            timings={}
            for name,call in [('day',lambda:screen_time.summary(store,day,now)),('week',lambda:screen_time.week(store,day,now)),('daily_record',lambda:snapshot(store,day,now=now))]:
                readings=[]
                for _ in range(repeats):
                    t=time.perf_counter();value=call();readings.append(time.perf_counter()-t)
                    assert 'DO_NOT_EXPORT' not in str(value)
                timings[name]=dict(reads=repeats,min_seconds=min(readings),median_seconds=statistics.median(readings),max_seconds=max(readings))
            assert store.db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
            return dict(evidence='synthetic retained-data benchmark; host timing, not hardware acceptance',observations=count,span_days=30,fixture_now=now,python=platform.python_version(),
                inserted_seconds=insert,timings=timings,peak_process_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('timesheet').glob('*.py')})
        finally:store.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--observations',type=int,default=200000);parser.add_argument('--repeats',type=int,default=10);parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=run(args.observations,args.repeats);data=json.dumps(result,indent=2)+'\n'
    if args.output:args.output.write_text(data)
    else:print(data)

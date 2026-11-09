"""Opt-in local evaluation templates. No network, key access or automatic ground truth."""
import argparse,json,os,sqlite3
from pathlib import Path
from datetime import date
from urllib.parse import quote
from .simple_setup import BUCKETS,preset_ids
from .decision_policy import settings
from .screen_time import periods
from .day_record import bounds


class Reader:
    def __init__(self,connection):self.db=connection
    def get(self,key,default=''):
        row=self.db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return row[0] if row else default
    def rows(self,sql,args=()):return self.db.execute(sql,args).fetchall()


def build(path,day,*,limit=50):
    if type(limit) is not int or not 1<=limit<=50:raise ValueError('Choose 1–50 apps for a local template.')
    connection=sqlite3.connect('file:'+quote(str(Path(path).resolve()))+'?mode=ro',uri=True,timeout=2)
    connection.row_factory=sqlite3.Row;connection.execute('PRAGMA query_only=ON');connection.execute('BEGIN')
    try:
        store=Reader(connection);owned=preset_ids(store);config=settings(store.get('ai_policy','{}'))
        selected=set(config['category_tasks'])
        if not selected or not selected<=set(owned.values()):raise ValueError('Complete activity-type setup before building this template.')
        tasks=[(owned[k],name+(' | Work guidance: '+guide if config['allow_guidance'] else '')) for k,(name,guide) in BUCKETS.items() if k in owned and owned[k] in selected]
        start,end=bounds(day)
        raw=[dict(r) for r in store.rows('SELECT id,start,end,app,state,closed,capture_version FROM activity WHERE start<? AND end>? AND closed=1',(end,start))]
        excluded={x.strip().casefold() for x in store.get('excluded_apps','').split(',') if x.strip()}
        excluded.update(app.casefold() for app in config['exclude_apps'])
        tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'ai_examples' in tables:
            # A fragmented choice on this day must not become both training context
            # and an apparently independent holdout. Earlier prompt exposure is
            # still unknown; this template does not claim random/independent sampling.
            excluded.update(r['application'].casefold() for r in store.rows('SELECT e.application FROM ai_examples e JOIN activity a ON a.id=e.activity_id WHERE a.start<? AND a.end>?',(end,start)))
        apps={}
        for row in periods(raw,start,end):
            if row['state']!='active' or row['app'].casefold() in excluded:continue
            key=row['app'].casefold();name,seconds=apps.get(key,(row['app'],0));apps[key]=(name,seconds+row['end']-row['start'])
        cases=[]
        for i,(name,seconds) in enumerate(sorted(apps.values(),key=lambda x:(-x[1],x[0].casefold()))[:limit],1):
            cases.append(dict(case_id=f'local-app-{i:02}',slice='local_app_function',applications=[name],tasks=tasks,
                expected_task=None,label_status='unlabelled',seconds=seconds,has_context=True,application_categories=True,
                provenance='private local template; top observed apps, not random sampling; confirm labels and preview before any live evaluation'))
        return cases
    finally:connection.close()


def save_new(path,cases):
    destination=Path(path)
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(cases,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('database',type=Path);parser.add_argument('--day',type=date.fromisoformat,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--limit',type=int,default=50)
    args=parser.parse_args()
    try:
        cases=build(args.database,args.day,limit=args.limit)
        if not cases:parser.error('No eligible named app observations remain after privacy and same-day example exclusions.')
        save_new(args.output,cases)
    except (OSError,ValueError,sqlite3.Error):parser.error('Could not create a new private template. Check activity setup, the selected day and destination.')
    print(f'Created {len(cases)} unlabelled local cases. No data was sent. Confirm labels and inspect the request preview before considering paid evaluation.')


if __name__=='__main__':main()

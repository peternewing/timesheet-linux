"""Replay previous hourly aggregation against the same disposable fixture/time.
Only a local function copy is replaced; product files never change on disk.
"""
import hashlib,importlib.util,inspect,json,time
from pathlib import Path
from unittest.mock import patch
from timesheet import screen_time
spec=importlib.util.spec_from_file_location('screen_benchmark',Path(__file__).with_name('benchmark_screen_time.py'));bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
source=inspect.getsource(screen_time.summary)
start=source.index('    while a<end:');finish=source.index('    return dict(day=',start)
reference=source[:start]+'''    while a<end:
        z=min(a+3600,end)
        seconds=sum(max(0,min(z,r['end'])-max(a,r['start'])) for r in visible if r['state'] in ('active','personal','excluded'))
        hours.append(dict(start=a,end=z,label=datetime.fromtimestamp(a).astimezone().strftime('%H:%M %Z'),seconds=seconds));a=z
'''+source[finish:]
namespace=dict(vars(screen_time));exec(compile(reference,'<previous hourly aggregation>','exec'),namespace)
# Both versions use identical captures, fixed time, schedules and repeat counts.
now=int(time.time());folder=Path('docs/evidence');folder.mkdir(exist_ok=True)
for name,summary,implementation in [('before',namespace['summary'],reference),('after',screen_time.summary,source)]:
    with patch.object(screen_time,'summary',summary):result=bench.run(200000,10,now=now)
    result['hourly_implementation']=name;result['summary_source_sha256']=hashlib.sha256(implementation.encode()).hexdigest();result['benchmark_harness_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (folder/f'personal-work-screen-benchmark-{name}-2026-11-09.json').write_text(json.dumps(result,indent=2)+'\n')
    print(name,result['timings'],flush=True)

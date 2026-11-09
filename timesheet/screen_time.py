"""Observed screen time for all use, independent of billing, AI and inferred intent."""
from collections import defaultdict
from contextlib import nullcontext
from datetime import datetime,timedelta
from .day_record import bounds

PRIORITY={'active':1,'personal':2,'excluded':2,'away':3,'unknown':4,'locked':5,'paused':6}


def periods(records,start,end):
    """Privacy-first interval union. Conflicting foreground apps become a gap."""
    events=defaultdict(list)
    for index,row in enumerate(records):
        a=max(start,row['start']);z=min(end,row['end'])
        if z>a:
            events[a].append((1,index,row));events[z].append((-1,index,row))
    active={};result=[];points=sorted(events)
    for i,a in enumerate(points[:-1]):
        for direction,index,row in events[a]:
            if direction==1:active[index]=row
            else:active.pop(index,None)
        z=points[i+1]
        if not active:continue
        # Normally one foreground observation exists. Keep pathological overlap
        # bounded and private instead of letting corrupt data consume quadratic CPU.
        legacy=False
        if len(active)>32:state='unknown';app='';conflict=True
        else:
            chosen=max(active.values(),key=lambda r:PRIORITY.get(r['state'],4));state=chosen['state'];app='';conflict=False
            if state=='active':
                names={r['app'].casefold():r['app'] for r in active.values() if r['state']=='active' and r['app']}
                if len(names)!=1:state='unknown';conflict=True
                else:app=next(iter(names.values()))
            if state not in PRIORITY:state='unknown'
            legacy=state=='excluded' and any(r['state']=='excluded' and r.get('capture_version',0)<2 for r in active.values())
        if result and result[-1]['end']==a and (result[-1]['state'],result[-1]['app'],result[-1]['conflict'],result[-1]['legacy'])==(state,app,conflict,legacy):result[-1]['end']=z
        else:result.append(dict(start=a,end=z,state=state,app=app,conflict=conflict,legacy=legacy))
    return result


def _split_spaces(rows,spaces):
    # Both inputs are ordered, non-overlapping intervals. Unlabelled intervals
    # stay Unsorted; neither a task name nor a category establishes work intent.
    result=[];index=0
    for row in rows:
        a=row['start'];z=row['end']
        while index<len(spaces) and spaces[index]['end']<=a:index+=1
        k=index
        while a<z:
            if k>=len(spaces) or spaces[k]['start']>=z:
                result.append(dict(row,start=a,end=z,space='unspecified',space_source='unlabelled'));break
            context=spaces[k]
            if a<context['start']:
                edge=min(z,context['start']);result.append(dict(row,start=a,end=edge,space='unspecified',space_source='unlabelled'));a=edge
            else:
                edge=min(z,context['end']);result.append(dict(row,start=a,end=edge,space=context['space'],space_source=context.get('source','manual')));a=edge
                if a>=context['end']:k+=1
    return result


def summary(store,day,now=None,*,space='all'):
    if space not in ('all','personal','work','unspecified'):raise ValueError('Choose a recorded space.')
    now=int(datetime.now().timestamp() if now is None else now);start,finish=bounds(day);end=min(finish,now)
    with nullcontext() if store.db.in_transaction else store.db:
        if not store.db.in_transaction:store.db.execute('BEGIN')
        records=store.activity_for(start,end) if end>start else []
        from .screen_spaces import periods as context_periods
        contexts=context_periods(store,start,end) if end>start else []
        rows=_split_spaces(periods(records,start,end),contexts)
    visible=[r for r in rows if space=='all' or r['space']==space]
    apps={};totals=defaultdict(int);spaces=defaultdict(int);switches=0;last_app=None;last_end=None;streak=longest=sessions=0
    for row in visible:
        seconds=row['end']-row['start'];state=row['state'];totals[state]+=seconds
        screen=state in ('active','personal','excluded')
        if screen:
            spaces[row['space']]+=seconds
            if last_end!=row['start']:sessions+=1;streak=0;last_app=None
            streak+=seconds;longest=max(longest,streak);last_end=row['end']
            if state=='active':
                key=row['app'].casefold();name,n=apps.get(key,(row['app'],0));apps[key]=(name,n+seconds)
                if last_app is not None and key!=last_app:switches+=1
                last_app=key
            else:last_app=None
        else:streak=0;last_end=None;last_app=None
    screen=totals['active']+totals['personal']+totals['excluded'];hours=[];a=start
    while a<end:
        z=min(a+3600,end)
        hours.append(dict(start=a,end=z,label=datetime.fromtimestamp(a).astimezone().strftime('%H:%M %Z'),seconds=0));a=z
    # Attribute each disjoint interval once instead of rescanning every row for
    # every hour. Elapsed-hour boundaries still preserve 23/25-hour DST days.
    for row in visible:
        if row['state'] not in ('active','personal','excluded'):continue
        first=(row['start']-start)//3600;last=(row['end']-1-start)//3600
        for index in range(first,last+1):
            hour=hours[index];hour['seconds']+=min(hour['end'],row['end'])-max(hour['start'],row['start'])
    return dict(day=day.isoformat(),start=start,end=end,space=space,screen_seconds=screen,named_seconds=totals['active'],
        private_seconds=totals['personal']+totals['excluded'],away_seconds=totals['away']+totals['locked'],gap_seconds=totals['unknown'],
        uncertain_seconds=totals['unknown']+totals['paused'],
        conflict_seconds=sum(r['end']-r['start'] for r in visible if r['conflict']),observed_seconds=sum(totals.values()),
        scheduled_seconds=sum(r['end']-r['start'] for r in visible if r['state'] in ('active','personal','excluded') and r.get('space_source')=='schedule'),
        legacy_exclusions=any(r['legacy'] for r in visible),
        has_observations=bool(rows),apps=sorted(apps.values(),key=lambda x:(-x[1],x[0].casefold())),
        spaces=dict(spaces),switches=switches,sessions=sessions,longest_session=longest,hourly=hours,periods=visible)


def week(store,day,now=None,*,space='all'):
    now=int(datetime.now().timestamp() if now is None else now)
    with nullcontext() if store.db.in_transaction else store.db:
        if not store.db.in_transaction:store.db.execute('BEGIN')
        days=[summary(store,day-timedelta(days=offset),now,space=space) for offset in reversed(range(7))]
        previous=[summary(store,day-timedelta(days=offset+7),now,space=space) for offset in reversed(range(7))]
        # Keep the matched-elapsed comparison in the same SQLite read snapshot.
        if day==datetime.fromtimestamp(now).date():
            elapsed=max(0,now-bounds(day)[0]);old_day=day-timedelta(days=7)
            previous[-1]=summary(store,old_day,min(bounds(old_day)[1],bounds(old_day)[0]+elapsed),space=space)
    total=sum(d['screen_seconds'] for d in days);old=sum(d['screen_seconds'] for d in previous)
    observed=sum(d['has_observations'] for d in days);old_observed=sum(d['has_observations'] for d in previous)
    apps={}
    for value in days:
        for name,seconds in value['apps']:
            key=name.casefold();label,n=apps.get(key,(name,0));apps[key]=(label,n+seconds)
    return dict(days=days,total=total,recorded_days=observed,average=total//observed if observed else None,
        previous_total=old,previous_recorded_days=old_observed,
        change_fraction=(total-old)/old if old and observed==old_observed==7 and not any(d['uncertain_seconds'] for d in days+previous) else None,
        apps=sorted(apps.values(),key=lambda x:(-x[1],x[0].casefold())))

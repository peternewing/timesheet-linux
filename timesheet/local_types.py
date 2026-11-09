"""Conservative installed-app function labels, locally; never project/work inference."""
import json,time,os,threading
from datetime import datetime,timedelta

SCHEMA='''CREATE TABLE IF NOT EXISTS local_type_assignments(entry_id INTEGER PRIMARY KEY REFERENCES entries(id),
 bucket TEXT NOT NULL,categories TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS local_type_suppressions(activity_id INTEGER PRIMARY KEY);'''
SPECIFIC={
 'WebBrowser':'browse','FileManager':'computer','TerminalEmulator':'computer',
 'Email':'communicate','InstantMessaging':'communicate','Chat':'communicate','IRCClient':'communicate',
 'Telephony':'communicate','VideoConference':'communicate','WordProcessor':'create','TextEditor':'create',
 'IDE':'create','WebDevelopment':'create','AudioVideoEditing':'create','Publishing':'create',
 'Spreadsheet':'plan','Calendar':'plan','ProjectManagement':'plan','ContactManagement':'plan',
 'Player':'media','TV':'media','Documentation':'learn'}


def classify(categories):
    """Only specific agreed functions. Broad Network/Office/Graphics are ambiguous."""
    if not isinstance(categories,(list,tuple,set)) or len(categories)>100 or any(not isinstance(k,str) or len(k)>80 for k in categories):return None
    values=set(categories)
    if {'LauncherStore','GameTool','Adult'}&values:return None
    specific={SPECIFIC[k] for k in values if k in SPECIFIC}
    main={bucket for tag,bucket in [('Game','play'),('Development','create'),('Education','learn')] if tag in values}
    if len(specific)==1:return next(iter(specific)) if not main or main<=specific else None
    if len(specific)>1:return None
    return next(iter(main)) if len(main)==1 else None


class Registry:
    def __init__(self):self.loaded=0;self.index={};self.refresh_lock=threading.Lock()
    def lookup(self,application):
        if time.monotonic()-self.loaded>300 or not self.loaded:
            if self.refresh_lock.acquire(blocking=False):
                try:self.refresh()
                finally:self.refresh_lock.release()
        found=self.index.get(application.removesuffix('.desktop').casefold(),[])
        buckets={item['bucket'] for item in found}
        return found[0] if len(buckets)==1 and found and None not in buckets else None
    def refresh(self):
        index={}
        try:
            import gi
            from gi.repository import Gio
            # Older GLib exposes this type in Gio. Loading both namespaces can
            # replace its Python wrapper with incorrectly bound instance methods.
            if not hasattr(Gio,'DesktopAppInfo'):
                gi.require_version('GioUnix','2.0')
                from gi.repository import GioUnix
            # AppInfo reads local registered metadata. Never read or execute Exec,
            # launch an app, send its paths, or use fuzzy/prefix identity matches.
            apps=Gio.AppInfo.get_all()
            if len(apps)>10000:raise ValueError('Incomplete local catalogue')
            for app in apps:
                if not hasattr(app,'get_categories'):continue
                # Hidden is a deleted desktop entry; NoDisplay only hides a menu
                # item. Read the exact key rather than a legacy binding's helper.
                if hasattr(app,'get_boolean') and app.get_boolean('Hidden'):continue
                raw=app.get_categories() or ''
                categories=raw.strip(';').split(';') if len(raw)<=8000 else []
                bucket=classify(categories)
                # Unknown identities must also participate in collision checks.
                # A second app with this name cannot silently inherit a label.
                proof=sorted(k for k in categories if k in SPECIFIC or k in ('Game','Development','Education'))
                keys=[app.get_name(),app.get_display_name(),app.get_id()]
                if hasattr(app,'get_startup_wm_class'):keys.append(app.get_startup_wm_class())
                for key in keys:
                    if not isinstance(key,str) or not 1<=len(key)<=200:continue
                    key=key.removesuffix('.desktop').casefold()
                    index.setdefault(key,[]).append(dict(bucket=bucket,categories=proof))
        except Exception:index={}
        # Publish one complete snapshot. A simultaneous capture/worker lookup
        # cannot observe half a catalogue and miss a conflicting app identity.
        self.index=index;self.loaded=time.monotonic()


registry=Registry()


def apply(store,now=None,*,limit=50,catalog=None):
    from .decision_policy import settings,owner_token
    from .simple_setup import preset_ids
    from .daily_choices import choice
    now=int(time.time() if now is None else now)
    if store.get('local_app_types','0')!='1' or store.get('simple_setup_complete','0')!='1':return 0
    config=settings(store.get('ai_policy','{}'));allowed=set(config['category_tasks'])
    owned=preset_ids(store);targets={k:v for k,v in owned.items() if v in allowed}
    if (not allowed or allowed-set(owned.values()) or config['owner']!=owner_token()
        or config['backend']!=('flatpak' if os.environ.get('FLATPAK_ID') else 'native')):return 0
    catalog=catalog or registry
    try:cursor=int(store.get('local_type_cursor','0'));cutoff=now-int(store.get('idle_seconds','300'))
    except (ValueError,TypeError):return 0
    rows=store.rows("""SELECT * FROM activity WHERE id>? AND state='active' AND closed=1 AND end<=? AND end>?
        AND NOT EXISTS(SELECT 1 FROM local_type_suppressions s WHERE s.activity_id=activity.id)
        AND NOT EXISTS(SELECT 1 FROM entries e WHERE e.activity_id=activity.id AND e.deleted=0 AND e.start<=activity.start AND e.end>=activity.end)
        ORDER BY id LIMIT ?""",(cursor,cutoff,now-7*86400,min(200,max(1,limit))))
    raw_exclusions=store.get('excluded_apps','')
    exclusions={x.strip().casefold() for x in raw_exclusions.split(',') if x.strip()}
    exclusions.update(x.casefold() for x in config['exclude_apps'])
    candidates=[]
    for row in rows:
        if row['app'].casefold() in exclusions:continue
        info=catalog.lookup(row['app'])
        if info and info['bucket'] in targets:candidates.append((dict(row),info))
    entries=[]
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        if store.get('local_app_types','0')!='1' or settings(store.get('ai_policy','{}'))!=config or store.get('excluded_apps','')!=raw_exclusions:return 0
        valid=preset_ids(store)
        if valid!=owned:return 0
        tasks={r['id'] for r in store.tasks()}
        rules=[r for r in store.rows('SELECT * FROM rules WHERE enabled=1') if r['task_id'] in tasks]
        for original,info in candidates:
            current=store.db.execute('SELECT * FROM activity WHERE id=?',(original['id'],)).fetchone()
            if not current or dict(current)!=original:continue
            if any(r['app'].casefold()==current['app'].casefold() and r['title'].casefold() in current['title'].casefold() for r in rules):continue
            task=targets[info['bucket']]
            for start,end in store.uncovered(current['start'],current['end'],now):
                a=start
                while a<end:
                    day=datetime.fromtimestamp(a).date();z=min(end,int(datetime.combine(day+timedelta(days=1),datetime.min.time()).timestamp()))
                    if choice(store,day,current['app']) is None:
                        eid=store.db.execute("INSERT INTO entries(task_id,start,end,description,billable,origin,activity_id) VALUES(?,?,?,'Installed app activity type',0,'app_type',?)",(task,a,z,current['id'])).lastrowid
                        store.db.execute('INSERT INTO local_type_assignments VALUES(?,?,?)',(eid,info['bucket'],json.dumps(info['categories'])))
                        entries.append(eid)
                        store.db.execute("UPDATE ai_jobs SET state='applied',entry_ids=?,reason='Organised locally from installed app metadata.',decision_source='local',updated=?,lease_until=0 WHERE activity_id=? AND start>=? AND end<=? AND state IN ('pending','running','exception','failed','stale')",(json.dumps([eid]),now,current['id'],a,z))
                    a=z
        store.set('local_type_cursor',rows[-1]['id'] if rows else 0)
        if entries:
            store._record_change('Local app activity category',[],entries);store.audit('local app types assigned',{'entries':len(entries)})
    return len(entries)

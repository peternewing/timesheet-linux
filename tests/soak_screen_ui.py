"""Sustained native insight refresh/filter/reopen exercise with synthetic data.
No actual capture, keys or network. Records host resources, not an acceptance SLA.
"""
import argparse,gc,hashlib,json,os,resource,tempfile,threading,time,traceback,weakref
from pathlib import Path
from datetime import datetime
from unittest.mock import patch


def descendants(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from descendants(child);child=child.get_next_sibling()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--seconds',type=int,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not 30<=args.seconds<=86400:parser.error('Choose 30–86400 seconds.')
    with tempfile.TemporaryDirectory(prefix='timesheet-screen-ui-soak-') as folder:
        os.environ.update(XDG_DATA_HOME=folder,TIMESHEET_TESTING='1',GSETTINGS_BACKEND='memory')
        from timesheet.app import TimeSheet,Gtk,GLib,desktop
        from timesheet.screen_reader import load_week
        from timesheet.simple_setup import finish_setup,BUCKETS
        from timesheet import screen_spaces
        app=TimeSheet();app.set_application_id('org.local.TimeSheetScreenSoak.Run'+str(os.getpid()))
        now=int(time.time());finish_setup(app.store,list(BUCKETS),connected=False,local_types=False,now=now-86400)
        started=time.monotonic();cpu=time.process_time();state={'window':None,'last_insert':-10,'last_filter':0,'last_reopen':0,'last_save':-30,'heartbeat':None};old=[];lock=threading.Lock()
        result=dict(evidence='sustained private native GTK with synthetic data; no actual capture/provider',requested_seconds=args.seconds,complete=False,
            source_hashes_at_start={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('timesheet').glob('*.py')},harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            reads=0,read_failures=0,cancelled_reads=0,heartbeat_ticks=0,max_heartbeat_gap_seconds=0,filter_changes=0,reopens=0,insertions=0,failures=[],samples=[])
        def save():
            result.update(elapsed_seconds=time.monotonic()-started,cpu_seconds=time.process_time()-cpu,peak_process_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            temp=args.output.with_suffix('.tmp');temp.write_text(json.dumps(result,indent=2)+'\n');temp.replace(args.output)
        def measured(*args,**kwargs):
            try:value=load_week(*args,**kwargs)
            except Exception:
                cancel=kwargs.get('cancel',args[4] if len(args)>4 else None)
                with lock:result['cancelled_reads' if cancel is not None and cancel.is_set() else 'read_failures']+=1
                raise
            with lock:result['reads']+=1
            return value
        def open_window():
            state['window']=app.screen_insights(datetime.now().date());return False
        def heartbeat():
            t=time.monotonic();previous=state['heartbeat'];state['heartbeat']=t;result['heartbeat_ticks']+=1
            if previous is not None:result['max_heartbeat_gap_seconds']=max(result['max_heartbeat_gap_seconds'],t-previous)
            return True
        def tick():
            elapsed=time.monotonic()-started
            try:
                if elapsed-state['last_insert']>=10:
                    wall=int(time.time());a=wall-9;z=wall-1
                    with app.store.db:app.store.db.execute("INSERT INTO activity(start,end,app,title,state,closed,capture_version) VALUES(?,?,'Synthetic Browser','DO_NOT_EXPORT','active',1,2)",(a,z))
                    screen_spaces.switch(app.store,'personal' if result['insertions']%2==0 else 'work',wall)
                    state['last_insert']=elapsed;result['insertions']+=1
                window=state['window']
                if elapsed-state['last_reopen']>=300 and elapsed<args.seconds-5:
                    old.append(weakref.ref(window));window.close();state['window']=None;state['last_reopen']=elapsed;result['reopens']+=1;GLib.idle_add(open_window)
                elif elapsed-state['last_filter']>=90 and window is not None:
                    names=('Everything','Personal','Work','Unsorted');name=names[(result['filter_changes']+1)%4]
                    control=next((w for w in descendants(window) if isinstance(w,Gtk.ToggleButton) and w.get_label()==name),None)
                    if control is not None:control.emit('clicked');state['last_filter']=elapsed;result['filter_changes']+=1
                if elapsed-state['last_save']>=30:
                    gc.collect();remaining=sum(ref() is not None for ref in old)
                    if elapsed-state['last_reopen']>3:assert remaining==0,'A closed insight window is still retained.'
                    result['samples'].append(dict(elapsed_seconds=elapsed,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,closed_windows_still_referenced=remaining))
                    assert app.store.db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
                    save();print(json.dumps({k:result[k] for k in ('elapsed_seconds','reads','heartbeat_ticks','peak_process_rss_kib','reopens')}),flush=True);state['last_save']=elapsed
                if elapsed>=args.seconds:
                    if state['window'] is not None:state['window'].close();state['window']=None
                    result['complete']=not result['failures'] and not result['read_failures'];save();app.quit();return False
                return True
            except Exception:
                result['failures'].append(traceback.format_exc());save();app.quit();return False
        def activate(_):open_window();GLib.timeout_add(250,heartbeat);GLib.timeout_add_seconds(1,tick)
        app.connect('activate',activate)
        with patch('timesheet.screen_reader.load_week',measured),patch.object(desktop,'start_collector'),patch.object(desktop,'start_automation'),patch.object(desktop,'read_health',return_value={'status':'active','at':now,'error':''}),patch('timesheet.jev.get_key',side_effect=AssertionError('No key')),patch('timesheet.jev.decide',side_effect=AssertionError('No network')):app.run([])
        print('PASS' if result['complete'] else 'FAIL',flush=True);return 0 if result['complete'] else 1

if __name__=='__main__':raise SystemExit(main())

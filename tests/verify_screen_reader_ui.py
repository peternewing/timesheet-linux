"""Native GTK responsiveness and stale async-result checks; disposable local data."""
import os,tempfile,time,threading,traceback,gc,weakref
from pathlib import Path
from datetime import datetime,timedelta
from unittest.mock import patch


def descendants(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from descendants(child);child=child.get_next_sibling()

with tempfile.TemporaryDirectory(prefix='timesheet-reader-ui-') as folder:
    os.environ.update(XDG_DATA_HOME=folder,TIMESHEET_TESTING='1',GSETTINGS_BACKEND='memory')
    from timesheet.app import TimeSheet,Gtk,GLib,desktop
    from timesheet import screen_spaces
    from timesheet.screen_reader import load_week
    from timesheet.day_record import bounds
    app=TimeSheet();app.set_application_id('org.local.TimeSheetReaderUI.Run'+str(os.getpid()))
    day=(datetime.now()-timedelta(days=1)).date();start=bounds(day)[0];now=int(time.time());checks=[];failures=[];completed=[]
    with app.store.db:app.store.db.execute("INSERT INTO activity(start,end,app,state,capture_version) VALUES(?,?,'Synthetic browser','active',2)",(start,start+300))
    screen_spaces.label_period(app.store,start,start+100,'personal',now=now);screen_spaces.label_period(app.store,start+100,start+300,'work',now=now)
    def check(value,message):assert value,message;checks.append(message);print('PASS:',message,flush=True)
    def click(window,name):next(w for w in descendants(window) if isinstance(w,Gtk.Button) and w.get_label()==name).emit('clicked')
    entered=threading.Event();release=threading.Event();finished=threading.Event();cancelled=[]
    def slow(path,day,now,space,cancel):
        entered.set();release.wait(5);cancelled.append(cancel.is_set())
        try:return load_week(path,day,now,space,cancel)
        finally:finished.set()
    def steps():
        with patch('timesheet.screen_reader.load_week',slow):
            window=app.screen_insights(day)
            for _ in range(20):
                if entered.is_set():break
                yield
            check(entered.is_set(),'Insight calculation runs separately from GTK')
            ticks=[0]
            def tick():ticks[0]+=1;return window in app.dialogs
            GLib.timeout_add(20,tick)
            for _ in range(8):yield
            check(ticks[0]>=5 and any(isinstance(w,Gtk.Spinner) and w.get_spinning() for w in descendants(window)),'GTK timers and loading feedback remain responsive during a blocked read')
            click(window,'Close');yield
            check(window not in app.dialogs,'Close responds while the reader is still blocked')
            release.set()
            for _ in range(30):
                if finished.is_set():break
                yield
            yield
            check(cancelled==[True] and window not in app.dialogs,'Closing cancels the read and discards its delayed result')
            closed_window=weakref.ref(window);window=None
            for _ in range(40):yield
            gc.collect();check(closed_window() is None,'A closed insight window and its widget callbacks are garbage-collected')
        reopened=[]
        for _ in range(20):
            window=app.screen_insights(day);reopened.append(weakref.ref(window));yield
            click(window,'Close');window=None;yield
        for _ in range(40):yield
        gc.collect();check(all(ref() is None for ref in reopened),'Twenty rapid reopenings release every closed insight window')
        personal_entered=threading.Event();personal_release=threading.Event();calls=[]
        def switch_race(path,day,now,space,cancel):
            calls.append(space)
            if space=='personal':personal_entered.set();personal_release.wait(5)
            return load_week(path,day,now,space,cancel)
        with patch('timesheet.screen_reader.load_week',switch_race):
            window=app.screen_insights(day)
            for _ in range(30):
                if any(isinstance(w,Gtk.Button) and w.get_label()=='Personal' for w in descendants(window)):break
                yield
            click(window,'Personal')
            for _ in range(20):
                if personal_entered.is_set():break
                yield
            check(not next(w for w in descendants(window) if isinstance(w,Gtk.Button) and w.get_label()=='Save screen-time summary').get_sensitive(),'Export is disabled while the selected filter has no matching completed preview')
            click(window,'Work');yield;personal_release.set()
            for _ in range(40):
                if 'work' in calls and any(isinstance(w,Gtk.Button) and w.get_label()=='Work' and w.has_css_class('suggested-action') for w in descendants(window)):break
                yield
            check(calls==['all','personal','work'],'A changed filter queues only its latest read after the in-flight read')
            check(any(isinstance(w,Gtk.Label) and w.get_text()=='00:03:20 recorded screen time' for w in descendants(window)),'An older Personal result cannot replace the selected Work summary')
            work=next(w for w in descendants(window) if isinstance(w,Gtk.Button) and w.get_label()=='Work')
            check(isinstance(work,Gtk.ToggleButton) and work.get_active(),'Selected filter exposes native toggle state as well as a colour')
            click(window,'Work');yield
            check(work.get_active(),'Clicking the selected filter cannot leave every space unchecked')
            check(next(w for w in descendants(window) if isinstance(w,Gtk.Button) and w.get_label()=='Save screen-time summary').get_sensitive(),'Export is enabled again for the completed matching preview')
            click(window,'Close');yield
        with patch('timesheet.screen_reader.load_week',side_effect=ValueError('SECRET PATH /private')):
            window=app.screen_insights(day)
            for _ in range(30):
                if any(isinstance(w,Gtk.Label) and 'Could not load' in w.get_text() for w in descendants(window)):break
                yield
            text=' '.join(w.get_text() for w in descendants(window) if isinstance(w,Gtk.Label))
            check('Could not load' in text and 'SECRET' not in text,'Read errors show a bounded local message without exception data')
            check(not any(isinstance(w,Gtk.Spinner) and w.get_spinning() for w in descendants(window)),'The loading indicator stops on read failure')
            click(window,'Close');yield
        check(app.store.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Read-only asynchronous UI leaves the database valid')
        completed.append(True);print('PASS:',len(checks),'async screen-time UI checks',flush=True)
    iterator=steps()
    def advance():
        try:next(iterator);return True
        except StopIteration:app.quit();return False
        except Exception:failures.append(traceback.format_exc());app.quit();return False
    app.connect('activate',lambda _:GLib.timeout_add(40,advance))
    with patch('timesheet.screen_ui.datetime',wraps=datetime) as screen_clock,patch.object(desktop,'start_collector'),patch.object(desktop,'start_automation'),patch.object(desktop,'read_health',return_value={'status':'active','at':now,'error':''}),patch('timesheet.jev.get_key',side_effect=AssertionError('No key')),patch('timesheet.jev.decide',side_effect=AssertionError('No network')):
        screen_clock.now.return_value=datetime.fromtimestamp(now);app.run([])
    if failures or not completed:raise SystemExit('\n'.join(failures) or 'Incomplete scenario')

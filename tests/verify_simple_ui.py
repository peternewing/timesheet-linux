"""Default simplicity experience: real GTK, synthetic data, zero typed setup fields."""
import os,tempfile,time,traceback,sys,ctypes,ctypes.util
from pathlib import Path
from datetime import datetime,timedelta
from unittest.mock import patch,Mock


def descendants(w):
    yield w
    child=w.get_first_child()
    while child:
        yield from descendants(child);child=child.get_next_sibling()


with tempfile.TemporaryDirectory(prefix='timesheet-simple-ui-') as tmp:
    os.environ.update(XDG_DATA_HOME=tmp,TIMESHEET_TESTING='1')
    from timesheet.app import TimeSheet,Gtk,GLib,desktop
    from timesheet.automation_worker import Engine
    from timesheet.day_record import bounds
    app=TimeSheet();app.set_application_id('org.local.TimeSheetSimpleTest')
    import gi
    gi.require_version('GdkX11','4.0')
    from gi.repository import GdkX11
    x=ctypes.CDLL(ctypes.util.find_library('X11'));xt=ctypes.CDLL(ctypes.util.find_library('Xtst'))
    x.XOpenDisplay.restype=ctypes.c_void_p;x.XOpenDisplay.argtypes=[ctypes.c_char_p];display=x.XOpenDisplay(None);assert display
    x.XDefaultRootWindow.argtypes=[ctypes.c_void_p];x.XDefaultRootWindow.restype=ctypes.c_ulong
    x.XTranslateCoordinates.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_int,ctypes.c_int,ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_ulong)]
    x.XFlush.argtypes=[ctypes.c_void_p];x.XRaiseWindow.argtypes=[ctypes.c_void_p,ctypes.c_ulong];x.XSetInputFocus.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong]
    xt.XTestFakeMotionEvent.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_ulong];xt.XTestFakeButtonEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
    def mouse(widget):
        window=widget.get_root();ok,rect=widget.compute_bounds(window);assert ok and widget.get_mapped() and widget.get_sensitive()
        assert 0<=rect.get_y() and rect.get_y()+rect.get_height()<=window.get_height()+2,'Setup action must be visible without hunting or scrolling'
        surface=window.get_surface();xid=surface.get_xid();sx,sy=window.get_surface_transform();scale=surface.get_scale_factor();rx=ctypes.c_int();ry=ctypes.c_int();child=ctypes.c_ulong()
        x.XTranslateCoordinates(display,xid,x.XDefaultRootWindow(display),0,0,ctypes.byref(rx),ctypes.byref(ry),ctypes.byref(child));x.XRaiseWindow(display,xid);x.XSetInputFocus(display,xid,1,0)
        xt.XTestFakeMotionEvent(display,-1,rx.value+int((rect.get_x()+rect.get_width()/2+sx)*scale),ry.value+int((rect.get_y()+rect.get_height()/2+sy)*scale),0)
        xt.XTestFakeButtonEvent(display,1,1,0);xt.XTestFakeButtonEvent(display,1,0,0);x.XFlush(display)
    checks=[];failures=[];out=Path('/tmp/timesheet-simple-ui');out.mkdir(exist_ok=True)
    def check(value,message):assert value,message;checks.append(message);print('PASS:',message,flush=True)
    def find(root,text):return next(w for w in descendants(root) if isinstance(w,Gtk.Button) and w.get_label()==text)
    def click(root,text):
        target=find(root,text)
        if root.get_root().get_title()=='Make your day automatic' or text=='Set up in 4 steps':mouse(target)
        else:target.emit('clicked')
    def screenshot(w,name):
        paint=Gtk.WidgetPaintable.new(w);snap=Gtk.Snapshot.new();paint.snapshot(snap,w.get_width(),w.get_height());node=snap.to_node();assert node;w.get_renderer().render_texture(node,None).save_to_png(str(out/(name+'.png')))
    def exception(kind,value,tb):failures.append(str(value));traceback.print_exception(kind,value,tb);app.quit()
    sys.excepthook=exception
    key=Mock(return_value='synthetic-only');connection=Mock(return_value={'models':['jev-test']})
    def steps():
        check(app.simple_mode(),'Simple experience is the default')
        check([n for n,b in app.nav.items() if b.get_visible()]==['Today','Calendar','Settings'],'Only three everyday destinations are visible')
        check(not any(isinstance(w,Gtk.Entry) for w in descendants(app.win)),'Welcome has no typing fields')
        check(not app.start_timer_button.get_visible() and not app.undo_button.get_visible(),'Timer and editing tools stay out of the everyday header')
        screenshot(app.win,'welcome');click(app.win,'Set up in 4 steps');yield
        cancelled=app.dialogs[-1];click(cancelled,'Close');yield
        check(not app.store.tasks() and app.automation_repo().config()['mode']=='off','Closing setup creates no categories or background policy')
        check(key.call_count==0 and connection.call_count==0,'Cancelled setup never reads the saved key or calls the provider')
        click(app.win,'Set up in 4 steps');yield
        form=app.dialogs[-1];form.set_default_size(500,650);yield;yield
        check(not any(isinstance(w,Gtk.Entry) for w in descendants(form)),'Category setup offers click-only ready-made choices')
        screenshot(form,'setup-categories')
        boxes=[w for w in descendants(form) if isinstance(w,Gtk.CheckButton)]
        for box in boxes:box.set_active(False)
        click(form,'Next');yield
        check(any(isinstance(w,Gtk.Label) and w.get_text()=='Choose at least one category.' for w in descendants(form)),'An empty category choice is explained on the same step')
        for box in boxes:box.set_active(True)
        click(form,'Next');yield
        check(key.call_count==0 and connection.call_count==0,'Opening setup does not access a key or call the provider')
        screenshot(form,'setup-privacy');click(form,'App names + local title clues');yield
        click(form,'Back');yield
        check(app.store.get('capture_titles','0')=='0','Back keeps privacy choices staged until explicit Start')
        click(form,'App names only');yield
        screenshot(form,'setup-connect');click(form,'Use my saved key');yield
        for _ in range(20):
            if find(form,'Close') and any(isinstance(w,Gtk.Button) and w.get_label()=='Start recording with Jev' for w in descendants(form)):break
            yield
        check(key.call_count==1 and connection.call_count==1,'One click verifies the saved personal key')
        check(app.automation_repo().config()['mode']=='off','Connecting alone leaves activity sending off')
        check(not any(isinstance(w,Gtk.Entry) for w in descendants(form)),'Real mouse clicks complete saved-key setup without typing')
        screenshot(form,'setup-ready');click(form,'Start recording with Jev');yield
        check(app.store.get('simple_setup_complete')=='1','Explicit Start completes setup')
        check(app.automation_repo().config()['mode']=='automatic','Explicit Start enables automatic organisation with the selected policy')
        check(app.store.get('capture_titles')=='0','The selected app-only privacy choice is preserved')
        check(len(app.store.tasks())==4,'Categories are created automatically without clients or rates to enter')
        check(connection.call_count==1,'Completing setup does not add a hidden inference request')
        # Use yesterday so this remains valid just after midnight.
        day=datetime.now().date()-timedelta(days=1);base=bounds(day)[0]+12*3600
        repo=app.automation_repo();repo.configure({**repo.config(),'since':bounds(day)[0]})
        ids=repo.config()['category_tasks']
        with app.store.db:app.store.db.execute("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,'Editor','active',1)",(base,base+600))
        result=dict(task=None,probability=.6,none_probability=.6,alternatives=[(i,.1) for i in sorted(ids)],personal=.1,enough_evidence=.4,work_kind='other',model='jev-simple-ui',usage={'input_tokens':100,'output_tokens':10})
        check(Engine(app.store,request=lambda *a,**kw:result,key=lambda:'synthetic').step()=='exception','An unclear decision becomes one human choice')
        app.day=day;app.show_page('Calendar');yield;yield;yield
        check(find(app.body_calendar,'Help Jev with 1 choice').get_sensitive(),'Past days presents the same simple daily record')
        screenshot(app.win,'past-day');click(app.body_calendar,'Help Jev with 1 choice');yield
        review=app.dialogs[-1];check(not any(isinstance(w,Gtk.Entry) for w in descendants(review)),'Review requires choosing a category, not completing a form')
        screenshot(review,'one-choice');click(review,'Creating & building');yield
        entry=app.store.entries(base,base+600)[0]
        check(entry['billable']==0 and entry['status']=='draft','A category choice cannot bill or approve time')
        check(len(app.store.rows('SELECT * FROM ai_examples'))==1,'The selected remember policy keeps a local correction example')
        check(any(isinstance(w,Gtk.Label) and w.get_text()=='You’re done' for w in descendants(review)),'One category click finishes a single-item review')
        click(review,'Back to my day');yield
        click(app.body_calendar,'Save day record');yield
        export=app.dialogs[-1];screenshot(export,'save-record')
        check(not any(isinstance(w,Gtk.Entry) for w in descendants(export)),'Day export has no invoice or accounting form')
        click(export,'Close');yield
        expander=next(w for w in descendants(app.body_calendar) if isinstance(w,Gtk.Expander) and w.get_label()=='Check or change a period');expander.set_expanded(True);yield
        click(app.body_calendar,'Change category');yield
        correction=app.dialogs[-1];click(correction,'Research & learning');yield
        check(app.store.entries(base,base+600)[0]['task']=='Research & learning','Changing a category is another single choice')
        app.show_page('Settings');yield;yield;yield
        check(not any(isinstance(w,Gtk.Entry) for w in descendants(app.body_settings)),'Everyday settings has no typing fields')
        advanced=next(w for w in descendants(app.body_settings) if isinstance(w,Gtk.Expander) and w.get_label()=='Advanced tools')
        check(not advanced.get_expanded(),'Legacy project, rule and invoice tools are collapsed by default')
        screenshot(app.win,'settings')
        click(app.body_settings,'Turn Jev off');yield
        check(repo.config()['mode']=='off','AI can be turned off with one clear action')
        check(app.store.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Database remains valid after setup, review, correction and pause')
        print('PASS:',len(checks),'simplicity UI checks',flush=True)
    iterator=steps()
    def advance():
        try:next(iterator);return True
        except StopIteration:app.quit();return False
    app.connect('activate',lambda _:GLib.timeout_add(180,advance))
    with patch.object(desktop,'start_collector'),patch.object(desktop,'start_automation'),patch.object(desktop,'read_health',return_value={'status':'active','at':time.time(),'error':''}),patch('timesheet.jev.get_key',key),patch('timesheet.jev.check_connection',connection):app.run([])
    if failures:raise SystemExit(1)

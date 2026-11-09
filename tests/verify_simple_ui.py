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
    app=TimeSheet();app.set_application_id('org.local.TimeSheetSimpleTest.Run'+str(os.getpid()))
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
    checks=[];failures=[];completed=[];out=Path('/tmp/timesheet-simple-ui');out.mkdir(exist_ok=True)
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
        optional=next(w for w in descendants(form) if isinstance(w,Gtk.Expander) and w.get_label()=='Choose useful tools (optional)')
        check(not optional.get_expanded(),'Useful tools are optional within the existing fourth step')
        optional.set_expanded(True);yield
        choice=next(w for w in descendants(optional) if isinstance(w,Gtk.CheckButton) and w.get_label()=='Automate repeated assignments')
        choice.set_active(True);yield
        check(app.store.get('simple_tools','[]')=='[]','Tool choices stay staged before Start')
        screenshot(form,'setup-tools')
        optional.set_expanded(False);yield
        screenshot(form,'setup-ready');click(form,'Start recording with Jev');yield
        check(app.store.get('simple_setup_complete')=='1','Explicit Start completes setup')
        check(app.automation_repo().config()['mode']=='automatic','Explicit Start enables automatic organisation with the selected policy')
        check(app.store.get('capture_titles')=='0','The selected app-only privacy choice is preserved')
        check(len(app.store.tasks())==8,'Categories are created automatically without clients or rates to enter')
        check(connection.call_count==1,'Completing setup does not add a hidden inference request')
        check(app.store.get('simple_tools')=='["rules"]','Start saves selected local tool shortcuts')
        check(find(app.body_today,'Restart Jev').get_visible(),'Today exposes an absent worker instead of claiming background progress')
        click(app.body_today,'Restart Jev');yield
        app.store.set('ai_worker_seen',int(time.time()));app.show_page('Today');yield
        check(not any(isinstance(w,Gtk.Button) and w.get_label()=='Restart Jev' for w in descendants(app.body_today)),'A fresh worker heartbeat clears the recovery prompt')
        more=next(w for w in descendants(app.body_today) if isinstance(w,Gtk.Expander) and w.get_label()=='More actions')
        more.set_expanded(True);yield
        click(app.body_today,'Automate repeated assignments');yield
        check(app.page=='Rules','The chosen setup tool opens working rules directly from the day')
        app.show_page('Today');yield
        # Use yesterday so this remains valid just after midnight.
        day=datetime.now().date()-timedelta(days=1);base=bounds(day)[0]+12*3600
        repo=app.automation_repo();repo.configure({**repo.config(),'since':bounds(day)[0]})
        ids=repo.config()['category_tasks']
        with app.store.db:
            for offset,length,name in [(0,600,'Editor'),(3600,600,'Editor'),(7200,300,'EDITOR')]:app.store.db.execute("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,?,'active',1)",(base+offset,base+offset+length,name))
        result=dict(task=None,probability=.6,none_probability=.6,alternatives=[(i,.4/len(ids)) for i in sorted(ids)],personal=.1,enough_evidence=.4,work_kind='other',model='jev-simple-ui',usage={'input_tokens':100,'output_tokens':10})
        check(Engine(app.store,request=lambda *a,**kw:result,key=lambda:'synthetic').step()=='exception','An unclear decision becomes one human choice')
        app.day=day;app.show_page('Calendar');yield;yield;yield
        check(find(app.body_calendar,'Help Jev with 1 choice').get_sensitive(),'Past days presents the same simple daily record')
        for metric_key,other in [('active','human'),('ai','active'),('human','ai')]:
            for child_index in ('value','caption'):
                mouse(app.simple_metric_buttons[other]);yield
                content=app.simple_metric_buttons[metric_key].get_child()
                target=content.get_first_child() if child_index=='value' else content.get_last_child()
                check(not target.get_selectable(),'Card '+metric_key+' '+child_index+' cannot select text')
                mouse(target);yield
                check(app.simple_metric_view==metric_key,'Clicking directly on '+metric_key+' '+child_index+' activates the card')
        mouse(app.simple_metric_buttons['ai']);yield
        check(any(isinstance(w,Gtk.Label) and w.get_text()=='No automatically organised periods yet.' for w in descendants(app.simple_details)),'Automatic card reveals its relevant empty state below')
        mouse(app.simple_metric_buttons['human']);yield
        check(any(isinstance(w,Gtk.Label) and w.get_text()=='No category choices or manual time saved yet.' for w in descendants(app.simple_details)),'Chosen-by-you card reveals its relevant empty state below')
        mouse(app.simple_metric_buttons['active']);yield
        check(list(app.simple_top_rows)==['Editor'] and app.simple_top_rows['Editor'][0].get_text()=='00:25:00','Recorded card shows top activities ranked by combined daily seconds')
        before_policy=app.store.get('ai_policy')
        click(app.body_calendar,'Organise my day');yield
        organiser_window=app.dialogs[-1]
        check(organiser_window.get_title()=='Organise my day','One-click Jev action opens live progress without a form')
        check(app.store.get('ai_policy')==before_policy,'Organise my day preserves standing privacy and usage settings')
        check(not any(isinstance(w,Gtk.Button) and (w.get_label() or '').startswith('Review ') and w.get_visible() for w in descendants(organiser_window)),'Uncertain review waits for the Jev pass instead of asking about unprocessed activity')
        for _ in range(4):Engine(app.store,request=lambda *a,**kw:result,key=lambda:'synthetic').step()
        for _ in range(30):
            if any(isinstance(w,Gtk.Button) and w.get_label()=='Review 1 uncertain activity' and w.get_visible() for w in descendants(organiser_window)):break
            yield
        check(find(organiser_window,'Review 1 uncertain activity').get_visible(),'Whole-day pass consolidates uncertain periods into one activity choice')
        click(organiser_window,'Back to my day');yield
        # Let the closed modal unmap and one background day-refresh cycle finish
        # before locating the new native click target. Its predecessor can be
        # replaced after the XTest event is queued on a busy headless runner.
        for _ in range(8):yield
        check(not organiser_window.get_mapped(),'Closed organiser releases its native modal window')
        screenshot(app.win,'past-day');mouse(find(app.simple_details,'Assign'));yield
        for _ in range(16):
            if app.dialogs:break
            yield
        check(bool(app.dialogs),'Native Assign click opens the daily category choice')
        review=app.dialogs[-1];check(not any(isinstance(w,Gtk.Entry) for w in descendants(review)),'Review requires choosing a category, not completing a form')
        screenshot(review,'one-choice');click(review,'Creating & building');yield
        entry=app.store.entries(base,base+600)[0]
        check(entry['billable']==0 and entry['status']=='draft','A category choice cannot bill or approve time')
        check(len(app.store.rows('SELECT * FROM ai_examples'))==3,'The selected remember policy keeps a local correction example')
        check(len(app.store.entries(base,base+8000))==3,'One decision categorises separated matching periods across the whole day')
        check(any(isinstance(w,Gtk.Label) and w.get_text()=='You’re done' for w in descendants(review)),'One category click finishes a single-item review')
        click(review,'Back to my day');yield
        click(app.body_calendar,'Save day record');yield
        export=app.dialogs[-1];screenshot(export,'save-record')
        check(not any(isinstance(w,Gtk.Entry) for w in descendants(export)),'Day export has no invoice or accounting form')
        click(export,'Close');yield
        app.simple_metric_buttons['human'].emit('clicked');yield
        click(app.body_calendar,'Change category');yield
        correction=app.dialogs[-1];click(correction,'Research & learning');yield
        check(app.store.entries(base,base+600)[0]['task']=='Research & learning','Changing a category is another single choice')
        with app.store.db:aid=app.store.db.execute("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,'Writer','active',1)",(base+10000,base+10300)).lastrowid
        confident=dict(task=ids[3],probability=.99,none_probability=.004,alternatives=[(ids[3],.99)]+[(i,.006/(len(ids)-1)) for i in sorted(ids) if i!=ids[3]],personal=.1,enough_evidence=.99,work_kind='other',model='jev-simple-ui',usage={'input_tokens':100,'output_tokens':10})
        check(Engine(app.store,request=lambda *a,**kw:confident,key=lambda:'synthetic').step()=='applied','A separate app has an automatically organised period to inspect')
        app.show_page('Calendar');yield
        app.simple_metric_buttons['ai'].emit('clicked');yield
        check(any(isinstance(w,Gtk.Label) and w.get_text()=='Planning & admin' for w in descendants(app.simple_details)) and not any(isinstance(w,Gtk.Label) and w.get_text()=='Research & learning' for w in descendants(app.simple_details)),'Automatic card shows only automatically organised periods')
        why=next(w for w in descendants(app.simple_details) if isinstance(w,Gtk.Expander) and w.get_label()=='Why this category?')
        why.set_expanded(True);yield
        check(any(isinstance(w,Gtk.Label) and 'jev-simple-ui' in w.get_text() and 'Policy: 1' in w.get_text() for w in descendants(why)),'Automatic entries explain the saved model and draft policy inline')
        screenshot(app.win,'decision-explanation')
        app.simple_metric_buttons['human'].emit('clicked');yield
        check(any(isinstance(w,Gtk.Label) and w.get_text()=='Research & learning' for w in descendants(app.simple_details)) and not any(isinstance(w,Gtk.Label) and w.get_text()=='Planning & admin' for w in descendants(app.simple_details)),'Chosen-by-you card shows only user choices and manual entries')
        with app.store.db:
            for n in range(6):app.store.db.execute("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,?,'active',1)",(base+11000+n*60,base+11030+n*60,'Other app '+str(n)))
        app.simple_select_metric('active');yield
        more=next(w for w in descendants(app.simple_details) if isinstance(w,Gtk.Expander) and w.get_label()=='More activities')
        check(len(app.simple_top_rows)==8 and not more.get_expanded(),'Top five stay simple; every remaining activity is available in More activities')
        more.set_expanded(True);yield
        check(len([w for w in descendants(app.simple_details) if isinstance(w,Gtk.Button) and w.get_label()=='Assign'])==8,'Every ranked activity, including those below the top five, has Assign')
        app.show_page('Today');yield;yield
        clock=int(time.time());app.store.start_timer(ids[0],clock-10)
        with app.store.db:live=app.store.db.execute("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,'Live editor','active',0)",(clock-20,clock-1)).lastrowid
        app.show_page('Today');yield
        app.simple_metric_buttons['human'].emit('clicked');yield
        for offset in (0,1,3,8):
            with patch('time.time',return_value=clock+offset):
                with app.store.db:app.store.db.execute('UPDATE activity SET end=? WHERE id=?',(clock+offset,live))
                app.simple_last_tick=None;app.tick()
                expected=f'00:00:{10+offset:02d}'
                check(app.timer_button.get_label()==expected and app.simple_metrics['human'].get_text()==expected and app.simple_metrics['active'].get_text()==f'00:00:{20+offset:02d}','Shared-clock counters stay exact at +'+str(offset)+' seconds without accumulated drift')
        app.store.stop_timer(clock+8)
        app.show_page('Settings');yield;yield;yield
        check(not any(isinstance(w,Gtk.Entry) for w in descendants(app.body_settings)),'Everyday settings has no typing fields')
        status=next(w for w in descendants(app.body_settings) if isinstance(w,Gtk.Expander) and w.get_label()=='Jev activity and limits')
        status.set_expanded(True);yield
        check(any(isinstance(w,Gtk.Label) and 'background requests' in w.get_text() for w in descendants(status)),'Simple settings exposes factual request limits and unresolved usage')
        status.set_expanded(False);yield
        before=app.automation_repo().config()
        useful=next(w for w in descendants(app.body_settings) if isinstance(w,Gtk.Expander) and w.get_label()=='Choose useful tools (optional)')
        useful.set_expanded(True);yield
        choice=next(w for w in descendants(useful) if isinstance(w,Gtk.CheckButton) and w.get_label()=='Prepare client reports')
        choice.set_active(True);yield
        check(app.automation_repo().config()==before,'Choosing business shortcuts leaves AI consent and outgoing scope unchanged')
        click(useful,'Open reports');yield
        check(app.page=='Reports','Purpose-based tools open the retained report workflow')
        app.show_page('Settings');yield
        toggle=next(w for w in descendants(app.body_settings) if isinstance(w,Gtk.CheckButton) and w.get_label()=='Show advanced tools in sidebar')
        toggle.set_active(True);yield
        check(all(b.get_visible() for b in app.nav.values()),'Optional sidebar switch immediately exposes retained tools')
        check(app.store.get('simple_show_advanced')=='1' and app.simple_mode(),'Sidebar preference persists without changing simple setup or layout')
        for page in ('Projects','Rules','Reports','History'):
            app.nav[page].emit('clicked');yield
            check(app.page==page and getattr(app,'body_'+page.lower()).get_first_child() is not None,page+' works from the simple-layout sidebar')
        app.simple_detailed_day(day);yield
        check(app.simple_activity_override and find(app.body_calendar,'Back to day summary').get_visible(),'Detailed assignment tools remain accessible from the simple daily flow')
        click(app.body_calendar,'Back to day summary');yield
        check(not app.simple_activity_override and find(app.body_calendar,'Organise my day').get_visible(),'Detailed activity returns to the simple day in one click')
        app.show_page('Settings');yield
        toggle=next(w for w in descendants(app.body_settings) if isinstance(w,Gtk.CheckButton))
        check(toggle.get_active(),'Advanced-sidebar preference survives navigation')
        toggle.set_active(False);yield
        check([n for n,b in app.nav.items() if b.get_visible()]==['Today','Calendar','Settings'],'Turning optional tools off restores the three-page sidebar')
        advanced=next(w for w in descendants(app.body_settings) if isinstance(w,Gtk.Expander) and w.get_label()=='Advanced tools')
        check(not advanced.get_expanded(),'Legacy project, rule and invoice tools are collapsed by default')
        before=app.store.get('ai_policy');app.screen_insights(day);yield
        insights=app.dialogs[-1]
        check(not any(isinstance(w,Gtk.Entry) for w in descendants(insights)),'Personal/work screen-time insights require no typed names or project setup')
        click(insights,'Personal / work spaces');yield
        spaces=app.dialogs[-1];click(spaces,'Use Personal space');yield
        from timesheet.screen_spaces import current
        check(current(app.store)['space']=='personal' and app.store.get('ai_policy')==before,'A personal space switch stays local without changing AI or billing policy')
        click(insights,'Personal');yield
        check(any(isinstance(w,Gtk.Label) and 'recorded screen time' in w.get_text() for w in descendants(insights)),'The Personal filter shows observed screen time without a work claim')
        screenshot(insights,'screen-time-insights');click(insights,'Close');yield
        app.screen_insights(day);yield
        insights=app.dialogs[-1]
        hourly=next(w for w in descendants(insights) if isinstance(w,Gtk.Expander) and w.get_label().startswith('By hour'))
        hourly.set_expanded(True);yield
        from timesheet.screen_time import summary as screen_summary
        from timesheet import screen_spaces
        hour=screen_summary(app.store,day)['hourly'][0];before_context=screen_spaces.effective_now(app.store)['space']
        click(insights,hour['label']);yield
        period=app.dialogs[-1]
        check(period.get_title()=='Label recorded period' and not any(isinstance(w,Gtk.Entry) for w in descendants(period)),'An hourly bar opens a click-only local context correction')
        click(period,'Work');yield
        check(all(r['space']=='work' for r in screen_spaces.periods(app.store,hour['start'],hour['end'])),'Hourly correction labels precisely the selected past period')
        check(screen_spaces.effective_now(app.store)['space']==before_context and app.store.get('ai_policy')==before,'Past context correction preserves current space and outgoing consent')
        click(insights,'Refresh insights');yield;yield
        check(any(isinstance(w,Gtk.Expander) and w.get_label().startswith('By hour') and w.get_expanded() for w in descendants(insights)),'Refreshing insights preserves the expanded hourly section')
        click(insights,'Personal / work spaces');yield
        spaces=app.dialogs[-1];click(spaces,'Undo last space change');yield
        check(all(r['space']=='unspecified' for r in screen_spaces.periods(app.store,hour['start'],hour['end'])),'Space Undo restores the previous past labels without touching capture')
        click(insights,'Personal / work spaces');yield
        spaces=app.dialogs[-1]
        expander=next(w for w in descendants(spaces) if isinstance(w,Gtk.Expander) and w.get_label()=='Automatic personal/work labels (optional)');expander.set_expanded(True);yield
        click(spaces,'Weekdays 9–5');yield
        check(screen_spaces.effective_now(app.store)['source']=='schedule' and app.store.get('ai_policy')==before,'One schedule choice enables local automatic labels without changing AI permission')
        check(bool(app.store.rows('SELECT zone FROM screen_space_schedules WHERE end IS NULL')[0]['zone']),'The schedule retains local clock rules for travel and daylight-saving boundaries')
        click(insights,'Personal / work spaces');yield
        spaces=app.dialogs[-1];click(spaces,'Use Work space');yield
        check(screen_spaces.effective_now(app.store)['source']=='manual','An explicit Work switch overrides the schedule')
        click(insights,'Personal / work spaces');yield
        spaces=app.dialogs[-1];click(spaces,'Undo last space change');yield
        check(screen_spaces.effective_now(app.store)['source']=='schedule','Undoing a manual override resumes its previous schedule')
        click(insights,'Close');yield
        app.show_page('Settings');yield
        screenshot(app.win,'settings')
        preview=app.store.undo_preview();click(app.body_settings,'Undo last change');yield
        undo=app.dialogs[-1]
        check(any(isinstance(w,Gtk.Label) and w.get_text()==preview['action'] for w in descendants(undo)),'Undo previews the actual latest action before changing time')
        click(undo,'Undo this change');yield
        check(undo not in app.dialogs,'Confirmed Undo applies the previewed change and closes the dialog')
        click(app.body_settings,'Turn Jev off');yield
        check(repo.config()['mode']=='off','AI can be turned off with one clear action')
        check(app.store.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Database remains valid after setup, review, correction and pause')
        completed.append(True);print('PASS:',len(checks),'simplicity UI checks',flush=True)
    iterator=steps()
    def advance():
        try:next(iterator);return True
        except StopIteration:app.quit();return False
    app.connect('activate',lambda _:GLib.timeout_add(180,advance))
    with patch('timesheet.local_types.registry.lookup',return_value=None),patch.object(desktop,'start_collector'),patch.object(desktop,'start_automation'),patch.object(desktop,'read_health',return_value={'status':'active','at':time.time(),'error':''}),patch('timesheet.jev.get_key',key),patch('timesheet.jev.check_connection',connection):app.run([])
    if failures or not completed:raise SystemExit(1)

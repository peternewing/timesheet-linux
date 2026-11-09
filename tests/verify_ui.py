"""Real GTK/X11 mouse-and-keyboard smoke test with disposable data.

Run: GDK_BACKEND=x11 PYTHONPATH=. /usr/bin/python3 tests/verify_ui.py
Screenshots contain synthetic data only and are written to /tmp/timesheet-ui-audit.
Does not start/stop the real collector or access the real timesheet database.
"""
import ctypes
import ctypes.util
import os
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


def descendants(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from descendants(child)
        child=child.get_next_sibling()


def main():
    with tempfile.TemporaryDirectory(prefix='timesheet-ui-') as directory:
        os.environ.update(XDG_DATA_HOME=directory,TIMESHEET_TESTING='1',GDK_BACKEND='x11')
        from timesheet.app import TimeSheet,PAGES,Gtk,GLib,desktop,fmt_timer,fmt_duration
        import gi
        gi.require_version('GdkX11','4.0')
        from gi.repository import GdkX11
        x=ctypes.CDLL(ctypes.util.find_library('X11')); xt=ctypes.CDLL(ctypes.util.find_library('Xtst'))
        x.XOpenDisplay.restype=ctypes.c_void_p; x.XOpenDisplay.argtypes=[ctypes.c_char_p]
        display=x.XOpenDisplay(None)
        if not display: raise RuntimeError('An X11/Xwayland display is required')
        x.XDefaultRootWindow.argtypes=[ctypes.c_void_p]; x.XDefaultRootWindow.restype=ctypes.c_ulong
        x.XTranslateCoordinates.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_int,ctypes.c_int,ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_ulong)]
        x.XFlush.argtypes=[ctypes.c_void_p]
        x.XRaiseWindow.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
        x.XSetInputFocus.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong]
        x.XKeysymToKeycode.argtypes=[ctypes.c_void_p,ctypes.c_ulong]; x.XKeysymToKeycode.restype=ctypes.c_uint
        xt.XTestFakeMotionEvent.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_ulong]
        xt.XTestFakeButtonEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
        xt.XTestFakeKeyEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
        app=TimeSheet();app.store.set('interface_mode','advanced'); app.set_application_id('org.local.TimeSheetUIAudit')
        failures=[]; checks=[]
        output=Path('/tmp/timesheet-ui-audit'); output.mkdir(exist_ok=True)
        def exception(kind,value,tb):
            failures.append(str(value)); traceback.print_exception(kind,value,tb); app.quit()
        sys.excepthook=exception
        def check(condition,message):
            assert condition,message
            checks.append(message); print('PASS:',message,flush=True)
        def click(widget):
            win=widget.get_root(); ok,rect=widget.compute_bounds(win)
            assert ok and widget.get_mapped() and widget.get_sensitive(),'Click target must be mapped and enabled'
            surface=win.get_surface(); xid=surface.get_xid()
            sx,sy=win.get_surface_transform()
            scale=surface.get_scale_factor()
            rx=ctypes.c_int(); ry=ctypes.c_int(); child=ctypes.c_ulong()
            x.XTranslateCoordinates(display,xid,x.XDefaultRootWindow(display),0,0,ctypes.byref(rx),ctypes.byref(ry),ctypes.byref(child))
            x.XRaiseWindow(display,xid); x.XSetInputFocus(display,xid,1,0)
            xt.XTestFakeMotionEvent(display,-1,rx.value+int((rect.get_x()+rect.get_width()/2+sx)*scale),ry.value+int((rect.get_y()+rect.get_height()/2+sy)*scale),0)
            xt.XTestFakeButtonEvent(display,1,1,0); xt.XTestFakeButtonEvent(display,1,0,0); x.XFlush(display)
        def key(keysym):
            code=x.XKeysymToKeycode(display,keysym); xt.XTestFakeKeyEvent(display,code,1,0); xt.XTestFakeKeyEvent(display,code,0,0); x.XFlush(display)
        def find_button(root,text):
            return next(w for w in descendants(root) if isinstance(w,Gtk.Button) and w.get_label()==text and w.get_mapped())
        def entries(): return [w for w in descendants(app.dialogs[-1]) if isinstance(w,Gtk.Entry)]
        def save(): click(find_button(app.dialogs[-1],'Save'))
        def snapshot(name,win=None):
            win=win or app.win; paint=Gtk.WidgetPaintable.new(win)
            deadline=time.monotonic()+3; node=None
            while node is None and time.monotonic()<deadline:
                win.queue_draw()
                context=GLib.MainContext.default()
                while context.pending():context.iteration(False)
                snap=Gtk.Snapshot.new(); paint.snapshot(snap,win.get_width(),win.get_height())
                node=snap.to_node()
                if node is None:time.sleep(.01)
            assert node,'Window did not render within three seconds'
            win.get_renderer().render_texture(node,None).save_to_png(str(output/(name+'.png')))
        def steps():
            snapshot('01-empty-today')
            for name in PAGES:
                # Click the custom label itself, not button padding or icon.
                target=app.nav[name].get_child().get_last_child(); click(target); yield
                check(app.page==name,'Mouse click on '+name+' text navigates')
                snapshot('02-empty-'+name.lower())
            click(app.nav['Today'].get_child().get_last_child()); yield
            click(find_button(app.win,'Help')); yield
            check(any(isinstance(w,Gtk.Label) and 'Draft = editable work' in w.get_text() for w in descendants(app.win)),'Help explains the full workflow and entry states')
            click(find_button(app.win,'Close')); yield
            click(find_button(app.win,'Add time')); yield
            check(len(app.dialogs)==1,'New project opens an edit form')
            fields=entries(); fields[0].set_text('Example Studio'); fields[1].set_text('Website'); fields[3].set_text('60.00'); yield
            snapshot('03-project-form',app.dialogs[-1]); save(); yield
            check(len(app.store.tasks())==1,'Project form saves client, project and task')
            for _ in range(12):
                if len(app.dialogs)==1 and app.dialogs[-1].get_title()=='Add time': break
                yield
            check(len(app.dialogs)==1 and app.dialogs[-1].get_title()=='Add time','First-project setup continues into the original Add time action')
            key(0xff1b); yield
            base=int(time.time())-7200
            def fill_time(a,z,description):
                fields=entries(); fields[0].set_text(datetime.fromtimestamp(a).strftime('%Y-%m-%d %H:%M:%S')); fields[1].set_text(datetime.fromtimestamp(z).strftime('%Y-%m-%d %H:%M:%S')); fields[2].set_text(description)
            click(find_button(app.win,'Add time')); yield
            fill_time(base,base+900,'Homepage design'); entries()[2].grab_focus(); key(0xff0d); yield
            check(len(app.store.entries(0,4102444800))==1,'Enter saves manual time from the form')
            click(find_button(app.win,'Add time')); yield
            fill_time(base,base+900,'Overlapping work'); save(); yield
            check(len(app.dialogs)==1 and len(app.store.entries(0,4102444800))==1,'Overlapping time is rejected without losing the form')
            snapshot('04-validation',app.dialogs[-1])
            click(find_button(app.dialogs[-1],'Close')); yield
            key(0xff1b); yield
            check(not app.dialogs,'Escape cancels an edit form')
            click(find_button(app.win,'Add time')); yield
            fill_time(base+900,base+1800,'Review'); save(); yield
            first=app.store.entries(0,4102444800)[-1]['id']; app.store.approve(first)
            app.history_period='all'; click(app.nav['History'].get_child().get_last_child()); yield
            check(not find_button(app.win,'Approve selected drafts').get_sensitive(),'Bulk approval disabled without a selection')
            check(not find_button(app.win,'Merge selected').get_sensitive(),'Merge disabled without enough selected entries')
            click(find_button(app.win,'Select visible entries')); yield
            check(len(app.selected_entries)==2,'Select visible entries selects both rows')
            click(find_button(app.win,'Approve selected drafts (1)')); yield
            check(all(r['status']=='approved' for r in app.store.entries(0,4102444800)),'Mixed selection approves only draft entries')
            click(find_button(app.win,'Select visible entries')); yield
            click(find_button(app.win,'Merge selected')); yield
            check(len(app.store.entries(0,4102444800))==1,'Merge combines adjacent entries')
            click(find_button(app.win,'Undo last edit')); yield
            check(len(app.store.entries(0,4102444800))==2,'Undo restores merged entries')
            snapshot('05-history')
            ids=[r['id'] for r in app.store.entries(0,4102444800)]; app.store.approve_many(ids)
            client_id=app.store.rows('SELECT id FROM clients')[0][0]
            report=app.store.create_report(client_id,base-1,base+1801)
            app.preview_report(report); yield
            preview=app.dialogs[-1]
            with patch.object(app,'save_file',side_effect=lambda title,name,handler:handler(str(Path(directory)/name))):
                click(find_button(preview,'PDF')); yield
                check((Path(directory)/f'timesheet-{report}.pdf').read_bytes().startswith(b'%PDF'),'Report PDF saves from the report preview')
                click(find_button(preview,'Invoice PDF')); yield
                invoice_fields=entries()
                invoice_fields[0].set_text('INV-TEST');invoice_fields[1].set_text('Example seller')
                invoice_fields[2].set_text('Example client');invoice_fields[3].set_text('2026-11-07');invoice_fields[4].set_text('2026-12-07')
                save();yield
                for _ in range(12):
                    if (Path(directory)/f'invoice-draft-{report}.pdf').exists():break
                    yield
                check((Path(directory)/f'invoice-draft-{report}.pdf').read_bytes().startswith(b'%PDF'),'Invoice draft PDF saves without billing the report')
                check(app.report_state(report)=='Ready to bill','PDF export does not mark work billed')
            click(find_button(preview,'Mark billed')); yield
            check(app.dialogs[-1].get_transient_for()==preview,'Billing form is attached to the report preview')
            entries()[0].set_text('TEST-001'); save(); yield
            check(not app.dialogs and app.report_state(report)=='Billed · TEST-001','Billing saves and closes the stale report preview')
            with app.store.db: app.store.db.execute('UPDATE clients SET archived=1 WHERE id=?',(client_id,))
            click(app.nav['Reports'].get_child().get_last_child()); yield
            check(any(isinstance(w,Gtk.Label) and 'Billed · TEST-001' in w.get_text() for w in descendants(app.win)),'Archived client retains visible billed reports')
            snapshot('06-archived-reports')
            click(find_button(app.win,'Open report')); yield
            previews=[w for w in Gtk.Window.list_toplevels() if w.get_title()=='Timesheet report '+str(report)]
            check(bool(previews),'Saved report opens a preview'); snapshot('07-report',previews[0]); previews[0].close(); yield
            click(app.nav['Projects'].get_child().get_last_child()); yield
            click(find_button(app.win,'Edit project')); yield
            check(bool(app.dialogs),'Project under an archived client remains editable'); key(0xff1b); yield
            click(find_button(app.win,'Edit task')); yield
            check(bool(app.dialogs),'Task under an archived client remains editable'); key(0xff1b); yield
            with app.store.db:
                app.store.db.execute('UPDATE clients SET archived=0')
                app.store.db.execute('INSERT INTO activity(start,end,app,state) VALUES(?,?,?,?)',(base-3600,base-3000,'Example Editor','active'))
                app.store.db.execute('INSERT INTO activity(start,end,app,state) VALUES(?,?,?,?)',(base-3000,base-2400,'Example Browser','personal'))
            click(app.nav['Rules'].get_child().get_last_child()); yield
            click(find_button(app.win,'Create assignment rule')); yield
            app_choice=next(w for w in descendants(app.dialogs[-1]) if isinstance(w,Gtk.DropDown) and hasattr(w,'_values') and w._values[0][1]=='Choose an application…')
            app_choice.set_selected(next(i for i,(value,_) in enumerate(app_choice._values) if value=='Example Editor'))
            task_choice=next(w for w in descendants(app.dialogs[-1]) if isinstance(w,Gtk.DropDown) and hasattr(w,'_values') and w._values[0][1]=='Choose a task…')
            task_choice.set_selected(1); save(); yield
            check(len(app.store.rows('SELECT * FROM rules'))==1,'Rule saves through the form')
            app.day=datetime.fromtimestamp(base-3600).date(); app.activity_filter='unassigned'
            click(app.nav['Calendar'].get_child().get_last_child()); yield
            check(not find_button(app.win,'Assign selected').get_sensitive(),'Activity assignment disabled with no selection')
            checks_visible=[w for w in descendants(app.calendar_detail) if isinstance(w,Gtk.CheckButton)]
            check(len(checks_visible)==1,'Only eligible unassigned activity has a selection checkbox')
            checkbutton=checks_visible[0]
            scroll=app.stack.get_visible_child(); ok,rect=checkbutton.compute_bounds(scroll)
            scroll.get_vadjustment().set_value(scroll.get_vadjustment().get_value()+rect.get_y()-200); yield
            click(checkbutton); yield
            assign=find_button(app.win,'Assign selected (1)')
            ok,rect=assign.compute_bounds(scroll); scroll.get_vadjustment().set_value(scroll.get_vadjustment().get_value()+rect.get_y()-150); yield
            click(assign); yield
            check(app.dialogs[-1].get_title()=='Assign activity','Selected activity opens assignment form')
            save(); yield
            check(len(app.store.entries(0,4102444800))==3,'Activity assignment creates draft task time')
            click(app.nav['Settings'].get_child().get_last_child()); yield
            snapshot('08-settings')
            app.win.set_default_size(900,650); yield
            click(app.nav['History'].get_child().get_last_child()); yield
            snapshot('09-smaller-window')
            check(fmt_duration(3661)=='1h 01m 01s','Duration totals retain seconds beyond an hour')
            sample_now=int(time.time())
            with app.store.db:
                live_id=app.store.db.execute("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,?,'active',0)",(sample_now-15,sample_now-1,'Live Editor')).lastrowid
                app.store.db.execute("UPDATE runtime SET collector_seen=?,capture_status='active',app='Live Editor',activity_state='active' WHERE id=1",(sample_now,))
            def sample():
                now=int(time.time())
                with app.store.db:
                    app.store.db.execute('UPDATE activity SET end=? WHERE id=?',(now,live_id))
                    app.store.db.execute('UPDATE runtime SET collector_seen=? WHERE id=1',(now,))
                return True
            sample_source=GLib.timeout_add(1000,sample)
            click(app.nav['Today'].get_child().get_last_child()); yield
            active_before=app.today_metrics['active'].get_text(); unassigned_before=app.today_metrics['unassigned'].get_text(); app_before=app.today_apps['Live Editor'][0].get_text()
            for _ in range(4): yield
            check(app.today_metrics['active'].get_text()!=active_before,'Active desktop total updates as new activity is recorded')
            check(app.today_metrics['unassigned'].get_text()!=unassigned_before,'Unassigned total updates as new activity is recorded')
            check(app.today_apps['Live Editor'][0].get_text()!=app_before,'Per-app usage counter updates as new activity is recorded')
            app.day=datetime.now().date(); app.activity_filter='all'
            click(app.nav['Calendar'].get_child().get_last_child()); yield
            live_before=app.calendar_live[live_id][0].get_text(); summary_before=app.calendar_summary.get_text()
            for _ in range(4): yield
            check(app.calendar_live[live_id][0].get_text()!=live_before,'Calendar live activity updates without rebuilding the page')
            check(app.calendar_summary.get_text()!=summary_before,'Calendar duration totals update with recorded activity')
            app.history_kind='usage'; app.history_period='all'; app.show_page('History'); yield
            history_before=app.history_live[live_id][0].get_text()
            for _ in range(4): yield
            check(app.history_live[live_id][0].get_text()!=history_before,'History live usage duration updates')
            sample_now=int(time.time())
            with app.store.db:
                app.store.db.execute('UPDATE activity SET closed=1 WHERE id=?',(live_id,))
                live_id=app.store.db.execute("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,?,'active',0)",(sample_now-1,sample_now,'Next Editor')).lastrowid
                app.store.db.execute("UPDATE runtime SET collector_seen=?,app='Next Editor' WHERE id=1",(sample_now,))
            for _ in range(4): yield
            check(live_id in app.history_live,'History follows the new live activity when the foreground app changes')
            GLib.source_remove(sample_source)
            click(app.nav['Today'].get_child().get_last_child()); yield
            frozen=app.today_metrics['active'].get_text()
            for _ in range(4): yield
            check(app.today_metrics['active'].get_text()==frozen,'Activity total stops when no new observation is recorded')
            with app.store.db: app.store.db.execute('UPDATE activity SET closed=1 WHERE id=?',(live_id,))
            app.history_kind='tasks'
            check(fmt_timer(3661)=='01:01:01' and fmt_timer(90061)=='25:01:01' and fmt_timer(-1)=='00:00:00','Timer formatting keeps seconds beyond an hour and a day')
            task=app.store.tasks()[0]['id']; timer_start=int(time.time())-3661
            app.store.start_timer(task,now=timer_start)
            click(app.nav['Today'].get_child().get_last_child()); yield
            before=app.timer_label.get_text(); assigned_before=app.today_metrics['assigned'].get_text()
            for _ in range(4): yield
            after=app.timer_label.get_text()
            def seconds(text):
                h,m,s=map(int,text.split(':')); return h*3600+m*60+s
            check(seconds(after)>seconds(before),'Running timer advances second by second')
            check(app.today_metrics['assigned'].get_text()!=assigned_before,'Running task is reflected in the assigned total every second')
            check(abs(seconds(after)-int(time.time()-timer_start))<=1,'Timer is derived from actual elapsed time, not accumulated UI ticks')
            snapshot('10-live-timer')
            click(app.nav['Projects'].get_child().get_last_child()); yield
            project_id=app.task_projects[task]
            project_before=app.project_live[project_id][0].get_text(); task_before=app.task_live[task][0].get_text()
            for _ in range(4): yield
            check(app.project_live[project_id][0].get_text()!=project_before,'Project spent time updates while its task timer runs')
            check(app.task_live[task][0].get_text()!=task_before,'Task recorded time updates while its timer runs')
            click(app.nav['History'].get_child().get_last_child()); yield
            check(app.timer_button.get_visible(),'Live timer remains visible while browsing other pages')
            click(app.timer_button); yield
            check(app.page=='Today','Header timer returns to the running task')
            stop=find_button(app.win,'Stop and save time'); scroll=app.stack.get_visible_child(); ok,rect=stop.compute_bounds(scroll)
            scroll.get_vadjustment().set_value(scroll.get_vadjustment().get_value()+rect.get_y()-200); yield
            click(stop); yield
            check(app.store.runtime()['state']=='stopped' and not app.timer_button.get_visible(),'Stop saves timer time and immediately hides the running indicator')
            check(app.store.validate(),'Database remains valid after UI workflows')
            print(f'PASS: {len(checks)} GUI checks. Screenshots: {output}',flush=True)
        iterator=None
        def advance():
            try: next(iterator); return True
            except StopIteration: app.quit(); return False
            except Exception:
                failures.append(traceback.format_exc()); print(failures[-1],flush=True); app.quit(); return False
        def activated(_):
            nonlocal iterator
            iterator=steps(); GLib.timeout_add(450,advance)
        with patch.object(desktop,'start_collector'),patch.object(desktop,'read_health',return_value={'status':'paused','error':''}):
            app.connect('activate',activated); app.run([])
        if app.win: app.win.close()
        if failures: return 1
        return 0

if __name__=='__main__': raise SystemExit(main())

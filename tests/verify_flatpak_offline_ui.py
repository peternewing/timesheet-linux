"""Check the offline Flatpak UI with synthetic activity and fake providers."""
import os,tempfile,time,traceback
from datetime import datetime
from unittest.mock import patch

def descendants(w):
    yield w
    child=w.get_first_child()
    while child:
        yield from descendants(child); child=child.get_next_sibling()

def find(root,typ,text):
    return next(w for w in descendants(root) if isinstance(w,typ) and w.get_label()==text)

with tempfile.TemporaryDirectory(prefix='timesheet-flatpak-ui-') as tmp:
    os.environ.update(XDG_DATA_HOME=tmp,TIMESHEET_TESTING='1')
    from timesheet.app import TimeSheet,Gtk,GLib,desktop
    from timesheet import jev
    app=TimeSheet();app.set_application_id('org.local.TimeSheetOfflineTest')
    app.store.quick_project('Example','Work','Design',6000);now=int(time.time())
    with app.store.db:
        app.store.db.execute("INSERT INTO activity(start,end,app,title,state,closed) VALUES(?,?,?,?,?,1)",(now-1800,now-900,'Editor','Example','active'))
    blocks=app.store.activity_for(now-2000,now);errors=[]
    def run():
        try:
            app.show_page('Settings')
            assert not find(app.body_settings,Gtk.Button,'Add or replace TypeSafe key').get_sensitive()
            check=find(app.body_settings,Gtk.Button,'Check connection');assert not check.get_sensitive();check.emit('clicked')
            app.assign_dialog(blocks);form=app.dialogs[-1]
            suggest=find(form,Gtk.Button,'Suggest a task with TypeSafe');assert not suggest.get_sensitive();suggest.emit('clicked');form.close()
            app.review_dialog(datetime.fromtimestamp(now-1000).date());window=app.dialogs[-1]
            batch=find(window,Gtk.Expander,'Optional AI suggestions for selected blocks');assert not batch.get_sensitive()
            batch.set_expanded(True);find(window,Gtk.Button,'Suggest for selected blocks').emit('clicked')
            assert find(window,Gtk.Button,'Assign selected')
            window.close();app.show_page('Rules');assert find(app.body_rules,Gtk.Button,'New rule').get_sensitive()
            assert not key.called and not api.called and not connection.called
            print('PASS: Flatpak remote controls disabled; local review and rules available',flush=True)
        except Exception: errors.append(traceback.format_exc())
        app.quit();return False
    with patch.object(desktop,'FLATPAK',True),patch.object(desktop,'start_collector'),patch.object(desktop,'read_health',return_value={'status':'paused','error':''}),patch.object(jev,'get_key') as key,patch.object(jev,'suggest') as api,patch.object(jev,'check_connection') as connection:
        app.connect('activate',lambda _:GLib.timeout_add(400,run));app.run([])
    if errors: raise RuntimeError('\n'.join(errors))

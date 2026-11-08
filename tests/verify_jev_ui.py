"""Test consent and key UI using a fake keyring and fake API; no network."""
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

with tempfile.TemporaryDirectory(prefix='timesheet-jev-ui-') as tmp:
    os.environ.update(XDG_DATA_HOME=tmp,TIMESHEET_TESTING='1')
    from timesheet.app import TimeSheet,Gtk,GLib,desktop,selected
    from timesheet import jev
    app=TimeSheet(); app.set_application_id('org.local.TimeSheetJevTest')
    tid=app.store.quick_project('Example','Work','Design',6000)
    now=int(time.time())
    with app.store.db:
        app.store.db.execute("INSERT INTO activity(start,end,app,title,state,closed) VALUES(?,?,?,?,?,1)",(now-1800,now-900,'Editor','Private title','active'))
    start=now-2000; blocks=app.store.activity_for(start,now)
    errors=[]; state={}
    def run():
        try:
            app.show_page('Settings')
            find(app.body_settings,Gtk.Button,'Add or replace TypeSafe key').emit('clicked')
            form=app.dialogs[-1]; entry=next(w for w in descendants(form) if isinstance(w,Gtk.Entry))
            assert not entry.get_visibility(); entry.set_text('example-key')
            find(form,Gtk.Button,'Save').emit('clicked'); save_key.assert_called_once_with('example-key')
            assert 'example-key' not in str([tuple(r) for r in app.store.rows('SELECT * FROM settings')])
            app.review_dialog(datetime.fromtimestamp(now-1000).date()); review_window=app.dialogs[-1]
            state['capture_review']=review_window
            assign=find(review_window,Gtk.Button,'Assign selected'); assert not assign.get_sensitive()
            check=next(w for w in descendants(review_window) if isinstance(w,Gtk.CheckButton) and 'Editor' in w.get_label())
            check.set_active(True); assert assign.get_sensitive(); assert not app.store.entries(start,now)
            assign.emit('clicked'); assert app.dialogs[-1].get_title()=='Assign activity'; app.dialogs[-1].close()
            state['review']=review_window
            find(review_window,Gtk.Button,'Ask Jev').emit('clicked')
            assert not api.called and not key.called
            find(app.dialogs[-1],Gtk.Button,'Send').emit('clicked')
            GLib.timeout_add(100,verify_batch)
        except Exception: errors.append(traceback.format_exc()); app.quit()
        return False
    def verify_batch():
        try:
            if not api.called: return True
            if not any(isinstance(w,Gtk.Label) and 'Suggested:' in w.get_text() for w in descendants(state['review'])): return True
            api.assert_called_once_with(['Editor'],[(tid,'Example / Work / Design')],'example-key',detailed=True)
            assert not app.store.entries(start,now)
            find(state['review'],Gtk.Button,'Review').emit('clicked'); assert app.dialogs[-1].get_title()=='Assign activity'; app.dialogs[-1].close()
            api.reset_mock(); key.reset_mock(); state['review'].close()
            app.assign_dialog(blocks); form=app.dialogs[-1]
            find(form,Gtk.Expander,'Optional context').set_expanded(True)
            context=next(w for w in descendants(form) if isinstance(w,Gtk.Entry)); context.set_text('Edited context')
            find(form,Gtk.Button,'Suggest a task with TypeSafe').emit('clicked')
            assert not api.called and not key.called
            assert any(isinstance(w,Gtk.Label) and 'Private title' not in w.get_text() and 'Editor' in w.get_text() for w in descendants(app.dialogs[-1]))
            find(app.dialogs[-1],Gtk.Button,'Send and suggest').emit('clicked')
            GLib.timeout_add(100,verify)
        except Exception: errors.append(traceback.format_exc()); app.quit()
        return False
    def verify():
        try:
            if not api.called: return True
            api.assert_called_once_with(['Editor'],[(tid,'Example / Work / Design')],'example-key',context='Edited context',detailed=True)
            form=app.dialogs[-1]
            assert any(isinstance(w,Gtk.Label) and 'Suggested task selected' in w.get_text() for w in descendants(form))
            assert not app.store.entries(start,now)
            form.close(); api.reset_mock(); key.reset_mock()
            project=app.store.rows('SELECT id FROM projects')[0]['id']; state['other']=app.store.add_task(project,'Admin'); state['ambiguous']=True
            app.assign_dialog(blocks); form=app.dialogs[-1]
            find(form,Gtk.Button,'Suggest a task with TypeSafe').emit('clicked')
            find(app.dialogs[-1],Gtk.Button,'Send and suggest').emit('clicked')
            GLib.timeout_add(100,verify_ambiguous)
        except Exception: errors.append(traceback.format_exc()); app.quit()
        return False
    def verify_ambiguous():
        try:
            form=app.dialogs[-1]
            buttons=[w.get_label() for w in descendants(form) if isinstance(w,Gtk.Button)]
            if 'Neither' not in buttons: return True
            task=next(w for w in descendants(form) if isinstance(w,Gtk.DropDown) and hasattr(w,'_values'))
            assert selected(task) is None
            find(form,Gtk.Button,'Neither').emit('clicked'); find(form,Gtk.Button,'Save').emit('clicked')
            assert not app.store.entries(start,now)
            find(form,Gtk.Button,'Close').emit('clicked')
            find(form,Gtk.Button,'Example / Work / Admin').emit('clicked'); assert selected(task)==state['other']
            find(form,Gtk.CheckButton,'Remember this choice locally (and count whether AI was changed)').set_active(True)
            find(form,Gtk.Button,'Save').emit('clicked')
            assert len(app.store.entries(start,now))==1 and app.store.entries(start,now)[0]['status']=='draft'
            import json
            assert json.loads(app.store.get('jev_preferences'))['editor']==state['other']
            assert json.loads(app.store.get('jev_feedback'))['changed']==1
            app.show_page('Settings'); find(app.body_settings,Gtk.Expander,'Preferences and categories').set_expanded(True); find(app.body_settings,Gtk.Button,'Add or update category').emit('clicked')
            category_form=app.dialogs[-1]; category=next(w for w in descendants(category_form) if isinstance(w,Gtk.Entry)); category.set_text('creative')
            find(category_form,Gtk.Button,'Save').emit('clicked')
            assert 'creative' in json.loads(app.store.get('jev_categories'))
            print('PASS: keyring, consent, batch review, ambiguity and opt-in local feedback',flush=True)
        except Exception: errors.append(traceback.format_exc())
        app.quit(); return False
    def fake_suggest(*args,**kwargs):
        if not kwargs.get('detailed'): return (tid,0.8)
        if state.get('ambiguous'): return {'task':tid,'probability':0.49,'alternatives':[(tid,0.49),(state['other'],0.44)],'personal':0.1}
        return {'task':tid,'probability':0.8,'alternatives':[(tid,0.8)],'personal':0.1}
    with patch.object(desktop,'start_collector'),patch.object(desktop,'read_health',return_value={'status':'paused','error':''}),patch.object(jev,'save_key') as save_key,patch.object(jev,'get_key',return_value='example-key') as key,patch.object(jev,'suggest',side_effect=fake_suggest) as api:
        app.connect('activate',lambda _:GLib.timeout_add(400,run)); app.run([])
    if errors: raise RuntimeError('\n'.join(errors))

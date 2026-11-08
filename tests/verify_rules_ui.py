"""Focused rules GUI checks with disposable synthetic data; no network."""
import os,tempfile,time,traceback
from pathlib import Path
from unittest.mock import patch

def descendants(w):
    yield w
    child=w.get_first_child()
    while child:
        yield from descendants(child); child=child.get_next_sibling()

def find(root,typ,text):
    return next(w for w in descendants(root) if isinstance(w,typ) and w.get_label()==text)

def texts(root):
    return [w.get_text() for w in descendants(root) if isinstance(w,Gtk.Label)]

with tempfile.TemporaryDirectory(prefix='timesheet-rules-ui-') as tmp:
    os.environ.update(XDG_DATA_HOME=tmp,TIMESHEET_TESTING='1')
    from timesheet.app import TimeSheet,Gtk,GLib,desktop
    app=TimeSheet(); app.set_application_id('org.local.TimeSheetRulesTest')
    first=app.store.quick_project('Example','Work','Design',6000)
    project=app.store.rows('SELECT id FROM projects')[0]['id']
    second=app.store.add_task(project,'Admin')
    now=int(time.time())
    with app.store.db:
        app.store.db.execute("INSERT INTO activity(start,end,app,title,state,closed) VALUES(?,?,?,?,?,1)",(now-1800,now-900,'Editor','Example document','active'))
    app.store.add_rule('Editor','',first,0)
    errors=[]; messages=[]; state={}
    def screenshot(window,name):
        output=Path('/tmp/timesheet-rules-ui'); output.mkdir(exist_ok=True)
        paint=Gtk.WidgetPaintable.new(window); snap=Gtk.Snapshot.new(); paint.snapshot(snap,window.get_width(),window.get_height())
        node=snap.to_node()
        if node: window.get_renderer().render_texture(node,None).save_to_png(str(output/(name+'.png')))
    def run():
        try:
            app.show_page('Rules')
            assert any('When the application is “Editor”' in s and 'as draft time' in s for s in texts(app.body_rules))
            screenshot(app.win,'rules')
            app.rule_dialog(); form=app.dialogs[-1]; state['form']=form
            custom=find(form,Gtk.Expander,'App not listed? Enter its exact name')
            app_entry=next(w for w in descendants(custom.get_child()) if isinstance(w,Gtk.Entry))
            assert app_entry.get_text()==''
            known=next(w for w in descendants(form) if isinstance(w,Gtk.DropDown) and w._values[0][1]=='Choose an application…')
            known.set_selected(next(i for i,(v,_) in enumerate(known._values) if v=='Editor'))
            assert app_entry.get_text()=='Editor'
            assert not find(form,Gtk.Expander,'App not listed? Enter its exact name').get_expanded()
            dropdown=next(w for w in descendants(form) if isinstance(w,Gtk.DropDown) and w._values[0][1]=='Choose a task…')
            dropdown.set_selected(next(i for i,(v,_) in enumerate(dropdown._values) if v==first))
            advanced=find(form,Gtk.Expander,'Advanced: priority'); assert not advanced.get_expanded(); advanced.set_expanded(True)
            assert any('Higher priority wins' in s and 'stays unassigned' in s for s in texts(form))
            find(form,Gtk.Button,'Save').emit('clicked')
            assert messages and 'same filter, target and priority' in messages[-1] and len(app.store.rows('SELECT * FROM rules'))==1
            dropdown.set_selected(next(i for i,(v,_) in enumerate(dropdown._values) if v==second)); find(form,Gtk.Button,'Save').emit('clicked')
            assert 'same application, title filter and priority' in messages[-1] and len(app.store.rows('SELECT * FROM rules'))==1
            title_options=find(form,Gtk.Expander,'Optional: match a window title');title_options.set_expanded(True)
            next(w for w in descendants(title_options.get_child()) if isinstance(w,Gtk.Entry)).set_text('Example')
            find(form,Gtk.Expander,'Preview: recorded matches and conflicts').set_expanded(True)
            GLib.timeout_add(350,verify_preview)
        except Exception: errors.append(traceback.format_exc()); app.quit()
        return False
    def verify_preview():
        try:
            form=state['form']; content=texts(form)
            assert any('Window titles are off' in s for s in content)
            assert any('Preview of up to 2,000' in s and 'Example document' in s for s in content)
            find(form,Gtk.Button,'Save').emit('clicked')
            assert 'Window titles are off' in messages[-1] and len(app.store.rows('SELECT * FROM rules'))==1
            screenshot(form,'rule-form')
            # Schedule a new debounce, then close before it can run.
            next(w for w in descendants(find(form,Gtk.Expander,'App not listed? Enter its exact name').get_child()) if isinstance(w,Gtk.Entry)).set_text('Other')
            form.close(); GLib.timeout_add(350,finish)
        except Exception: errors.append(traceback.format_exc()); app.quit()
        return False
    def finish():
        try:
            assert not app.dialogs
            screenshot(app.win,'rules')
            print('PASS: rule explanation, explicit choices, advanced priority, duplicate/conflict rejection, title warning, preview and close',flush=True)
        except Exception: errors.append(traceback.format_exc())
        app.quit(); return False
    with patch.object(desktop,'start_collector'),patch.object(desktop,'read_health',return_value={'status':'paused','error':''}),patch.object(app,'error',side_effect=messages.append):
        app.connect('activate',lambda _:GLib.timeout_add(400,run)); app.run([])
    if errors: raise RuntimeError('\n'.join(errors))

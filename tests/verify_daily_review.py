"""Synthetic end-to-end daily review and rule creation, without a real key or collector."""
import os
import tempfile
import traceback
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch


def descendants(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from descendants(child)
        child=child.get_next_sibling()


with tempfile.TemporaryDirectory(prefix='timesheet-daily-review-') as folder:
    os.environ.update(XDG_DATA_HOME=folder,TIMESHEET_TESTING='1')
    from timesheet.app import TimeSheet,Gtk,GLib,desktop,day_bounds,selected
    app=TimeSheet();app.set_application_id('org.local.TimeSheetDailyReviewTest')
    task=app.store.quick_project('Example Studio','Website','Design',6000)
    day=datetime.now().date()-timedelta(days=1)
    base=int(datetime.combine(day,datetime.min.time()).replace(hour=10).timestamp())
    app.store.add_entry(task,base-3600,base-1800,'Planning')
    today=day_bounds(datetime.now().date())[0]
    app.store.add_entry(task,today+3600,today+4200,'Today work')
    with app.store.db:
        for offset,name in [(0,'Editor'),(600,'Browser')]:
            app.store.db.execute("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,?,'active',1)",(base+offset,base+offset+600,name))
    errors=[];checks=[]
    def find(root,kind,text):
        return next(w for w in descendants(root) if isinstance(w,kind) and w.get_label()==text)
    def check(condition,text):
        assert condition,text
        checks.append(text);print('PASS:',text,flush=True)
    def screenshot(window,name):
        folder=Path('/tmp/timesheet-daily-review');folder.mkdir(exist_ok=True)
        paint=Gtk.WidgetPaintable.new(window);snapshot=Gtk.Snapshot.new();paint.snapshot(snapshot,window.get_width(),window.get_height())
        node=snapshot.to_node();assert node
        window.get_renderer().render_texture(node,None).save_to_png(str(folder/(name+'.png')))
    def steps():
        samples=app.store.activity_for(*day_bounds(day),True)
        app.review_dialog(day,[(block,(task,0.8),None) for block in samples]);yield
        window=app.dialogs[-1]
        find(window,Gtk.Expander,'Optional AI suggestions for selected blocks').set_expanded(True);yield
        ask=find(window,Gtk.Button,'Suggest for selected blocks')
        check(not ask.get_sensitive(),'AI action starts disabled without selected activity')
        find(window,Gtk.Button,'Select shown').emit('clicked');yield
        check(ask.get_sensitive(),'Selecting shown activity enables Jev suggestions')
        find(window,Gtk.Button,'Clear selection').emit('clicked');yield
        check(not ask.get_sensitive() and not find(window,Gtk.Button,'Ask Jev').get_sensitive(),'Clearing selection disables Jev suggestions')
        find(window,Gtk.CheckButton,next(w.get_label() for w in descendants(window) if isinstance(w,Gtk.CheckButton) and 'Editor' in w.get_label())).set_active(True)
        find(window,Gtk.Button,'Assign selected (1)').emit('clicked');yield
        form=app.dialogs[-1];choice=next(w for w in descendants(form) if isinstance(w,Gtk.DropDown))
        check(selected(choice) is None,'Assignment without a rule or suggestion requires an explicit task choice')
        choice.set_selected(next(i for i,(value,_) in enumerate(choice._values) if value==task))
        find(form,Gtk.Button,'Save').emit('clicked')
        for _ in range(3):yield
        queue=app.dialogs[-1]
        check(queue.get_title()=='Review suggestions' and queue is not window,'Assignment reopens an updated review queue')
        check(not any(isinstance(w,Gtk.CheckButton) and 'Editor' in w.get_label() for w in descendants(queue)),'Assigned activity leaves the review queue')
        check(any(isinstance(w,Gtk.CheckButton) and 'Browser' in w.get_label() for w in descendants(queue)),'Remaining activity stays available for review')
        check(any(isinstance(w,Gtk.Label) and 'Remaining suggestions from this review' in w.get_text() for w in descendants(queue)),'Unused batch suggestions survive assignment without another API request')
        check(len([w for w in descendants(queue) if isinstance(w,Gtk.Button) and w.get_label()=='Review'])==1,'Only the remaining activity keeps a saved suggestion')
        screenshot(queue,'daily-review')
        find(queue,Gtk.Button,'Open drafts').emit('clicked');yield
        check(app.history_period=='custom' and app.history_from==day and app.history_to==day,'Open drafts keeps the date being reviewed')
        check(app.history_status=='draft' and len(app.store.entries(*app.history_bounds()))==2,'Day review excludes drafts from other dates')
        app.show_page('Today');yield
        check(any(isinstance(w,Gtk.Label) and w.get_text()=='Work recorded today' for w in descendants(app.body_today)),'Today includes a saved work summary')
        app.show_page('Rules');yield
        find(app.body_rules,Gtk.Button,'Create assignment rule').emit('clicked');yield
        form=app.dialogs[-1]
        check(not any(isinstance(w,Gtk.Entry) and w.get_mapped() for w in descendants(form)),'Normal rule creation has no text fields to type')
        choices=[w for w in descendants(form) if isinstance(w,Gtk.DropDown)]
        app_choice=next(w for w in choices if w._values[0][1]=='Choose an application…')
        app_choice.set_selected(next(i for i,(value,_) in enumerate(app_choice._values) if value=='Editor'))
        task_choice=next(w for w in choices if w._values[0][1]=='Choose a task…')
        task_choice.set_selected(next(i for i,(value,_) in enumerate(task_choice._values) if value==task))
        for _ in range(3):yield
        check(any(isinstance(w,Gtk.Label) and 'When the application is “Editor”' in w.get_text() and 'as draft time' in w.get_text() for w in descendants(form)),'Rule preview explains app, task and draft result')
        screenshot(form,'guided-rule')
        find(form,Gtk.Button,'Save').emit('clicked');yield
        rule=app.store.rows('SELECT * FROM rules')[0]
        check(rule['app']=='Editor' and rule['task_id']==task and rule['title']=='','A useful rule is created entirely by selection')
        with app.store.db:app.store.db.execute('UPDATE tasks SET archived=1')
        app.rule_dialog(application='Editor');yield
        setup=app.dialogs[-1]
        check(setup.get_title()=='New project','Creating a rule without active tasks guides project setup')
        fields=[w for w in descendants(setup) if isinstance(w,Gtk.Entry)]
        fields[0].set_text('Another client');fields[1].set_text('New project')
        find(setup,Gtk.Button,'Save').emit('clicked')
        for _ in range(3):yield
        resumed=app.dialogs[-1]
        check(resumed.get_title()=='New rule','First-project setup returns to the original rule action')
        app_choice=next(w for w in descendants(resumed) if isinstance(w,Gtk.DropDown) and w._values[0][1]=='Choose an application…')
        check(selected(app_choice)=='Editor','Guided setup keeps the selected application')
        resumed.close()
        check(app.store.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Database integrity remains valid')
        print('PASS:',len(checks),'daily-review and guided-rule checks',flush=True)
    iterator=steps()
    def advance():
        try:next(iterator);return True
        except StopIteration:app.quit();return False
        except Exception:errors.append(traceback.format_exc());app.quit();return False
    with patch.object(desktop,'start_collector'),patch.object(desktop,'read_health',return_value={'status':'paused','error':''}):
        app.connect('activate',lambda _:GLib.timeout_add(150,advance));app.run([])
    if errors:raise RuntimeError('\n'.join(errors))

"""Real GTK automation setup/inbox with synthetic data, fake key and fake provider."""
import os,tempfile,time,traceback
from pathlib import Path
from unittest.mock import patch,Mock
from datetime import datetime,timedelta


def descendants(w):
    yield w
    c=w.get_first_child()
    while c:
        yield from descendants(c);c=c.get_next_sibling()


with tempfile.TemporaryDirectory(prefix='timesheet-automation-ui-') as tmp:
    os.environ.update(XDG_DATA_HOME=tmp,TIMESHEET_TESTING='1')
    from timesheet.app import TimeSheet,Gtk,GLib,desktop,selected
    from timesheet.automation_worker import Engine
    app=TimeSheet();app.store.set('interface_mode','advanced');app.set_application_id('org.local.TimeSheetAutomationUITest')
    task=app.store.quick_project('Example Studio','Falcon','Development',6000);repo=app.automation_repo()
    repo.save_profile(task,'Falcon implementation for Example Studio')
    now=int(time.time());base=int(datetime.combine(datetime.now().date()-timedelta(days=1),datetime.min.time()).replace(hour=12).timestamp())
    with app.store.db:
        for offset in (0,600):app.store.db.execute("INSERT INTO activity(start,end,app,title,state,closed) VALUES(?,?,? ,?,'active',1)",(base+offset,base+offset+300,'Editor','Private title never sent'))
    request=Mock(return_value=dict(task=task,probability=.99,none_probability=.01,alternatives=[(task,.99)],personal=.01,enough_evidence=.99,
        work_kind='development',model='jev-test-1',usage=dict(input_tokens=200,output_tokens=20),confidence=.98))
    failures=[];checks=[]
    def find(root,kind,text):return next(w for w in descendants(root) if isinstance(w,kind) and w.get_label()==text)
    def check(value,text):
        assert value,text;checks.append(text);print('PASS:',text,flush=True)
    def screenshot(window,name):
        output=Path('/tmp/timesheet-automation-ui');output.mkdir(exist_ok=True)
        paint=Gtk.WidgetPaintable.new(window);snap=Gtk.Snapshot.new();paint.snapshot(snap,window.get_width(),window.get_height())
        node=snap.to_node();assert node;window.get_renderer().render_texture(node,None).save_to_png(str(output/(name+'.png')))
    def steps():
        app.task_guidance_dialog(task);yield
        guidance_form=app.dialogs[-1]
        starter=next(w for w in descendants(guidance_form) if isinstance(w,Gtk.Expander) and w.get_label()=='Use a starter description (optional)')
        starter.set_expanded(True);yield
        find(starter,Gtk.Button,'Creating & building').emit('clicked');yield
        check(repo.store.db.execute('SELECT guidance FROM ai_task_profiles WHERE task_id=?',(task,)).fetchone()[0]=='Falcon implementation for Example Studio','Choosing a guidance starter stays unsaved and local')
        find(guidance_form,Gtk.Button,'Save').emit('clicked');yield
        check('Creating, writing' in repo.store.db.execute('SELECT guidance FROM ai_task_profiles WHERE task_id=?',(task,)).fetchone()[0] and not request.called,'Saving starter guidance does not make an inference request')
        app.show_page('Today');yield
        check(find(app.body_today,Gtk.Button,'Set up Jev automation').get_sensitive(),'Today offers one automation setup action')
        find(app.body_today,Gtk.Button,'Set up Jev automation').emit('clicked');yield
        form=app.dialogs[-1]
        key=next(w for w in descendants(form) if isinstance(w,Gtk.Entry));check(not key.get_visibility(),'Setup masks the personal key')
        mode=next(w for w in descendants(form) if isinstance(w,Gtk.DropDown) and w._values[0][0]=='off')
        mode.set_selected(2)
        period=next(w for w in descendants(form) if isinstance(w,Gtk.DropDown) and any('Past seven days' in name for _,name in w._values));period.set_selected(2)
        find(form,Gtk.Button,'Save').emit('clicked');yield
        check(repo.config()['mode']=='off','Selecting automatic mode without consent cannot enable sending')
        find(form,Gtk.Button,'Close').emit('clicked');yield
        find(form,Gtk.CheckButton,'Allow background requests under this data and usage policy').set_active(True)
        screenshot(form,'setup')
        form.set_default_size(480,650)
        for _ in range(2):yield
        checks_width=[w for w in descendants(form) if isinstance(w,(Gtk.Entry,Gtk.DropDown,Gtk.CheckButton)) and w.get_mapped()]
        screenshot(form,'setup-narrow')
        check(all(w.compute_bounds(form)[1].get_x()+w.compute_bounds(form)[1].get_width()<=form.get_width()+2 for w in checks_width),'Setup controls fit a narrow window without horizontal clipping')
        screenshot(form,'setup-narrow')
        form.set_default_size(720,760);yield
        find(form,Gtk.Button,'Save').emit('clicked');yield
        check(repo.config()['mode']=='automatic','Explicit standing consent enables the selected mode')
        check(not request.called,'Setup does not make a hidden provider request')
        engine=Engine(app.store,request=request,key=lambda:'synthetic-key')
        check(engine.step(now)=='exception','Insufficient distinguishing context routes to an exception')
        check(engine.step(now)=='exception' and request.call_count==1,'Equivalent work reuses the result without another paid request')
        app.automation_inbox();yield
        inbox=app.dialogs[-1]
        screenshot(inbox,'exceptions')
        find(inbox,Gtk.Button,'Why this decision?').emit('clicked');yield
        evidence=app.dialogs[-1]
        text=next(w for w in descendants(evidence) if isinstance(w,Gtk.TextView));buffer=text.get_buffer()
        contents=buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),True)
        check('Private title never sent' not in contents and 'jev-test-1' in contents,'Decision explanation includes the model but excludes raw titles')
        controllers=evidence.observe_controllers()
        escape=next(controllers.get_item(i) for i in range(controllers.get_n_items()) if isinstance(controllers.get_item(i),Gtk.EventControllerKey))
        from timesheet.app import Gdk
        escape.emit('key-pressed',Gdk.KEY_Escape,0,0);yield
        check(evidence not in app.dialogs,'Escape closes decision evidence for keyboard users')
        find(inbox,Gtk.Button,'Choose another task').emit('clicked');yield
        resolve=app.dialogs[-1];choice=next(w for w in descendants(resolve) if isinstance(w,Gtk.DropDown));choice.set_selected(1)
        find(resolve,Gtk.CheckButton,'Remember my choice as a local correction example').set_active(True)
        similar=next(w for w in descendants(resolve) if isinstance(w,Gtk.CheckButton) and 'matching periods' in w.get_label());similar.set_active(True)
        yield
        screenshot(resolve,'one-answer-many')
        find(resolve,Gtk.Button,'Save').emit('clicked')
        for _ in range(3):yield
        check(len(app.store.entries(0,now))==2,'One explicit answer resolves the previewed matching periods')
        check(all(r['status']=='draft' for r in app.store.entries(0,now)),'Human and AI review never auto-approve time')
        check(len(app.store.rows('SELECT * FROM ai_examples'))==2,'Explicitly remembered corrections are stored locally')
        app.dialogs[-1].close();yield
        app.show_page('Today');yield
        check(find(app.body_today,Gtk.Button,'Needs your decisions').get_sensitive(),'Today shows automation and the exception inbox')
        app.automation_dialog();yield
        form=app.dialogs[-1];mode=next(w for w in descendants(form) if isinstance(w,Gtk.DropDown) and w._values[0][0]=='off');mode.set_selected(0)
        find(form,Gtk.Button,'Save').emit('clicked');yield
        check(engine.step(now)=='off','Turning automation off immediately prevents later processing')
        app.focus_dialog(task);yield
        focus_form=app.dialogs[-1]
        default=find(focus_form,Gtk.CheckButton,'Use this task as my draft default when Jev agrees; leave conflicting activity for review')
        check(not default.get_active(),'A focus draft default requires an additional explicit choice')
        default.set_active(True);yield
        check(default.compute_bounds(focus_form)[1].get_x()+default.compute_bounds(focus_form)[1].get_width()<=focus_form.get_width()+2,'Long focus controls fit the narrow form')
        find(focus_form,Gtk.Button,'Save').emit('clicked');yield
        check(repo.current_focus()['draft_default']==1,'The chosen focus instruction is saved without creating time')
        check(len(app.store.entries(0,now))==2,'Choosing focus creates no elapsed time or extra entries')
        app.focus_dialog(task);yield
        focus_form=app.dialogs[-1];find(focus_form,Gtk.Button,'Clear current focus').emit('clicked');yield
        check(repo.current_focus() is None and focus_form not in app.dialogs,'Clear focus stops the instruction and closes its form')
        from timesheet.decision_memory import remember
        from timesheet.decision_context import canonical
        with app.store.db:remember(app.store,app.store.rows('SELECT id FROM activity LIMIT 1')[0]['id'],'Editor',task,canonical({'clues':[],'focus':None}),now)
        app.forget_app_corrections();yield
        forget_form=app.dialogs[-1];forget=find(forget_form,Gtk.Button,'Forget this app’s examples')
        check(not forget.get_sensitive() and not any(isinstance(w,Gtk.Entry) for w in descendants(forget_form)),'Scoped Forget is click-only and requires an explicit app choice')
        choice=next(w for w in descendants(forget_form) if isinstance(w,Gtk.DropDown));choice.set_selected(1);yield
        check(forget.get_sensitive(),'Choosing a remembered app enables its scoped Forget action')
        find(forget_form,Gtk.Button,'Close').emit('clicked');yield
        check(bool(app.store.rows('SELECT id FROM ai_examples')) and len(app.store.entries(0,now))==2,'Closing scoped Forget preserves examples and saved time')
        check(app.store.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Database integrity remains valid after automation review')
        print('PASS:',len(checks),'automation UI checks',flush=True)
    iterator=steps()
    def advance():
        try:next(iterator);return True
        except StopIteration:app.quit();return False
        except Exception:failures.append(traceback.format_exc());app.quit();return False
    with patch.object(desktop,'start_collector'),patch.object(desktop,'start_automation'),patch.object(desktop,'read_health',return_value={'status':'paused','error':''}):
        app.connect('activate',lambda _:GLib.timeout_add(180,advance));app.run([])
    if failures:raise RuntimeError('\n'.join(failures))

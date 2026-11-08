"""Exercise new review controls in an isolated GTK session with synthetic data."""
import os
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

with tempfile.TemporaryDirectory(prefix='timesheet-improvements-') as directory:
    os.environ.update(XDG_DATA_HOME=directory,TIMESHEET_TESTING='1')
    from timesheet.app import TimeSheet, Gtk, GLib, select_id, desktop
    def descendants(w):
        yield w
        child=w.get_first_child()
        while child:
            yield from descendants(child); child=child.get_next_sibling()
    def find(root, cls, predicate=lambda w:True):
        return next(w for w in descendants(root) if isinstance(w,cls) and predicate(w))
    app=TimeSheet(); app.set_application_id('org.local.TimeSheetImprovementTest')
    task=app.store.quick_project('Test client','Test project','Test task',6000)
    now=int(time.time())
    for i in range(110): app.store.add_entry(task,now-10000+i*60,now-10000+i*60+30,'Synthetic')
    failures=[]
    def check():
        try:
            app.show_page('Today'); app.tick()
            with patch.object(app,'refresh_today',wraps=app.refresh_today) as refresh, patch('time.time',return_value=time.time()+30):
                app.tick(); refresh.assert_not_called()
            app.history_period='all'; app.show_page('History')
            assert len(app.history_checks)==50
            more=find(app.body_history,Gtk.Button,lambda w:(w.get_label() or '').startswith('Show more'))
            more.emit('clicked'); assert len(app.history_checks)==100
            more.emit('clicked'); assert len(app.history_checks)==110 and not more.get_visible()
            period=find(app.body_history,Gtk.DropDown,lambda w:any(v[0]=='custom' for v in w._values))
            select_id(period,'custom')
            dates=[w for w in descendants(app.body_history) if isinstance(w,Gtk.Entry)]
            dates[0].set_text('2000-01-01'); dates[1].set_text('2000-01-31')
            find(app.body_history,Gtk.Button,lambda w:w.get_label()=='Apply dates').emit('clicked')
            assert app.history_from.isoformat()=='2000-01-01' and len(app.history_checks)==0
            with app.store.db: app.store.db.execute("INSERT INTO activity(start,end,app,state) VALUES(?,?,?,?)",(now-10,now-5,'Editor','active'))
            app.show_page('Settings')
            find(app.body_settings,Gtk.Button,lambda w:w.get_label()=='Exclude selected app').emit('clicked')
            assert any(isinstance(w,Gtk.Entry) and w.get_text()=='Editor' for w in descendants(app.body_settings))
            find(app.body_settings,Gtk.Button,lambda w:w.get_label()=='Remove selected exclusion').emit('clicked')
            app.timer_dialog(); assert app.dialogs[-1].get_title()=='Start timer'; app.dialogs[-1].close()
            rid=app.store.add_rule('Editor','',task)
            app.rule_dialog(app.store.db.execute('SELECT * FROM rules WHERE id=?',(rid,)).fetchone())
            assert app.dialogs[-1].get_title()=='Edit rule'; app.dialogs[-1].close()
            app.entry_dialog(); form=app.dialogs[-1]
            find(form,Gtk.Button,lambda w:w.get_label()=='Last 15 minutes').emit('clicked')
            fields=[w for w in descendants(form) if isinstance(w,Gtk.Entry)]
            assert (datetime.strptime(fields[1].get_text(),'%Y-%m-%d %H:%M:%S')-datetime.strptime(fields[0].get_text(),'%Y-%m-%d %H:%M:%S')).total_seconds()==900
            form.close()
            entry=app.store.entries(0,now)[0]['id']; app.store.approve(entry)
            report=app.store.create_report(1,now-20000,now+1)
            app.show_page('Projects')
            search=find(app.body_projects,Gtk.SearchEntry)
            search.set_text('no such project'); search.emit('search-changed')
            assert any(isinstance(w,Gtk.Label) and w.get_text()=='No matching projects' for w in descendants(app.body_projects))
            search.set_text('Test task'); search.emit('search-changed')
            assert any(isinstance(w,Gtk.Label) and w.get_text().strip()=='Test task' for w in descendants(app.body_projects))
            app.show_page('Reports')
            grouping=find(app.body_reports,Gtk.DropDown,lambda w:any(v[0]=='week' for v in w._values))
            select_id(grouping,'week')
            with patch.object(app,'save_file',side_effect=lambda title,name,handler:handler(str(Path(directory)/name))):
                find(app.body_reports,Gtk.Button,lambda w:w.get_label()=='Export internal time CSV').emit('clicked')
            assert (Path(directory)/'internal-time.csv').read_text().startswith('Week beginning,')
            app.invoice_pdf_dialog(report); form=app.dialogs[-1]
            fields=[w for w in descendants(form) if isinstance(w,Gtk.Entry)]
            fields[0].set_text('INV-1'); fields[1].set_text('Seller'); fields[5].set_text('Payment')
            find(form,Gtk.CheckButton,lambda w:'Remember seller' in w.get_label()).set_active(True)
            with patch.object(app,'save_file'):
                find(form,Gtk.Button,lambda w:w.get_label()=='Save').emit('clicked')
                assert app.store.get('invoice_seller')=='Seller' and app.store.get('invoice_payment')=='Payment'
            print('PASS: pagination, dates, exclusions, timer, rule editor and invoice preferences',flush=True)
        except Exception: failures.append(traceback.format_exc())
        app.quit(); return False
    with patch.object(desktop,'start_collector'), patch.object(desktop,'read_health',return_value={'status':'paused','error':''}):
        app.connect('activate',lambda _:GLib.timeout_add(300,check)); app.run([])
    if failures: raise RuntimeError('\n'.join(failures))

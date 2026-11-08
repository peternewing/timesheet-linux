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
            print('PASS: pagination, custom dates, exclusions, timer and rule editor',flush=True)
        except Exception: failures.append(traceback.format_exc())
        app.quit(); return False
    with patch.object(desktop,'start_collector'), patch.object(desktop,'read_health',return_value={'status':'paused','error':''}):
        app.connect('activate',lambda _:GLib.timeout_add(300,check)); app.run([])
    if failures: raise RuntimeError('\n'.join(failures))

"""Render the default simple UI using synthetic data; no real key or API call."""
import os,tempfile,time
from pathlib import Path
from unittest.mock import patch
from datetime import datetime

with tempfile.TemporaryDirectory(prefix='timesheet-preview-') as directory:
    os.environ.update(XDG_DATA_HOME=directory,TIMESHEET_TESTING='1')
    from timesheet.app import TimeSheet,day_bounds,desktop
    from timesheet.simple_setup import finish_setup,BUCKETS
    from timesheet.automation_worker import Engine
    from gi.repository import Gtk,GLib
    start,_=day_bounds(datetime.now().date());fake_now=start+13*3600
    with patch('time.time',return_value=fake_now),patch.object(desktop,'start_collector'),patch.object(desktop,'read_health',return_value=dict(status='active',at=fake_now,error='')):
        app=TimeSheet();app.set_application_id('org.local.TimeSheetPreview');s=app.store
        config=finish_setup(s,list(BUCKETS),connected=True,now=fake_now);s.set('capture_enabled','1');ids=config['category_tasks']
        with s.db:
            for a,z,name,state in [(9*3600,10*3600,'Visual Studio Code','active'),(10*3600,10*3600+2700,'Slack','active'),(10*3600+2700,11*3600+300,'','away'),(11*3600+300,11*3600+900,'','unknown'),(11*3600+900,11*3600+2700,'Firefox','active')]:
                s.db.execute('INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,?,?,1)',(start+a,start+z,name,state))
            s.db.execute("UPDATE runtime SET collector_seen=?,capture_status='active',app='Visual Studio Code' WHERE id=1",(fake_now,))
        def request(apps,tasks,key,**kwargs):
            task=ids[0] if apps==['Visual Studio Code'] else ids[2] if apps==['Slack'] else None
            alts=sorted([(i,.99 if i==task else .002 if task else .1) for i in ids],key=lambda x:(-x[1],x[0]))
            return dict(task=task,probability=.99 if task else .6,none_probability=.004 if task else .6,alternatives=alts,personal=.2,enough_evidence=.99 if task else .1,work_kind='other',model='jev-synthetic-preview',usage={'input_tokens':100,'output_tokens':10})
        worker=Engine(s,request=request,key=lambda:'synthetic')
        for _ in range(3):worker.step(fake_now)
        output=Path('docs/screenshots');output.mkdir(parents=True,exist_ok=True);pages=iter(['Today','Calendar'])
        def render():
            paint=Gtk.WidgetPaintable.new(app.win);snap=Gtk.Snapshot.new();paint.snapshot(snap,app.win.get_width(),app.win.get_height());node=snap.to_node();assert node
            app.win.get_renderer().render_texture(node,None).save_to_png(str(output/(app.page.lower()+'.png')));print('Rendered',app.page,flush=True);advance();return False
        def advance():
            try:page=next(pages)
            except StopIteration:app.quit();return
            app.show_page(page);GLib.timeout_add(800,render)
        app.connect('activate',lambda _:GLib.timeout_add(1000,lambda:(advance(),False)[1]));app.run([])

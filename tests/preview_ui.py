"""Generate documentation screenshots from synthetic data only."""
import os,tempfile,time
from pathlib import Path
from unittest.mock import patch

with tempfile.TemporaryDirectory(prefix='timesheet-preview-') as directory:
    os.environ.update(XDG_DATA_HOME=directory,TIMESHEET_TESTING='1')
    from timesheet.app import TimeSheet,day_bounds,desktop
    from datetime import datetime
    from gi.repository import Gtk,GLib
    start,_=day_bounds(datetime.now().date()); fake_now=start+13*3600
    with patch('time.time',return_value=fake_now),patch.object(desktop,'start_collector'),patch.object(desktop,'read_health',return_value=dict(status='active',at=fake_now,error='')):
        app=TimeSheet();s=app.store;t=s.quick_project('Example Studio','Website','Design',6000,budget=21600)
        s.set('capture_enabled','1')
        entry=s.add_entry(t,start+9*3600,start+10*3600,'Designed the homepage layout');s.approve(entry)
        s.add_entry(t,start+10*3600,start+10*3600+900,'Reviewed navigation options')
        with s.db:
            for a,z,name,state in [(9*3600,10*3600,'Visual Studio Code','active'),(10*3600,10*3600+1200,'Firefox','active'),(10*3600+1200,10*3600+2100,'','away'),(10*3600+2100,12*3600,'Visual Studio Code','active')]:
                s.db.execute('INSERT INTO activity(start,end,app,state) VALUES(?,?,?,?)',(start+a,start+z,name,state))
            s.db.execute("UPDATE runtime SET collector_seen=?,capture_status='active',app='Visual Studio Code' WHERE id=1",(fake_now,))
        pages=iter(['Today','Calendar','History'])
        output=Path('docs/screenshots');output.mkdir(parents=True,exist_ok=True)
        def render():
            name=app.page
            p=Gtk.WidgetPaintable.new(app.win);snap=Gtk.Snapshot.new();p.snapshot(snap,app.win.get_width(),app.win.get_height());node=snap.to_node()
            texture=app.win.get_renderer().render_texture(node,None);texture.save_to_png(str(output/(name.lower()+'.png')));print('Rendered',name,flush=True)
            advance();return False
        def advance():
            try:page=next(pages)
            except StopIteration:app.quit();return
            app.show_page(page);GLib.timeout_add(800,render)
        app.connect('activate',lambda _:GLib.timeout_add(1200,lambda:(advance(),False)[1]));app.run([])

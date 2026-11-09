"""Render local personal/work development screens from wholly synthetic records."""
import os,tempfile,time
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch

with tempfile.TemporaryDirectory(prefix='timesheet-screen-preview-') as folder:
    os.environ.update(XDG_DATA_HOME=folder,TIMESHEET_TESTING='1',GSETTINGS_BACKEND='memory')
    from timesheet.app import TimeSheet,Gtk,GLib,desktop
    from timesheet.simple_setup import BUCKETS,finish_setup
    from timesheet.local_types import apply
    from timesheet import screen_spaces
    from timesheet.day_record import bounds
    app=TimeSheet();app.set_application_id('org.local.TimeSheetScreenPreview.Run'+str(os.getpid()))
    day=datetime.now().date();now=int(time.time());output=Path('docs/screenshots');output.mkdir(exist_ok=True)
    def snapshot(window,name):
        paint=Gtk.WidgetPaintable.new(window);snap=Gtk.Snapshot.new();paint.snapshot(snap,window.get_width(),window.get_height());node=snap.to_node();assert node
        window.get_renderer().render_texture(node,None).save_to_png(str(output/name));print('Rendered',name,flush=True)
    def prepare():
        store=app.store;finish_setup(store,list(BUCKETS),connected=False,local_types=False,now=now-7*86400)
        screen_spaces.use_schedule(store,'weekdays_9_17',bounds(day-timedelta(days=6))[0])
        for offset in range(7):
            start=bounds(day-timedelta(days=offset))[0]
            for a,z,name,state in [(9,10,'Visual Studio Code','active'),(10,10.5,'Slack','active'),(10.5,11,'Firefox','active'),(11,11.25,'','away'),(11.25,11.75,'LibreOffice Calc','active'),(17,17.75,'Chess','active'),(18,18.75,'VLC media player','active'),(18.75,19,'','excluded')]:
                a=int(start+a*3600);z=min(now,int(start+z*3600))
                if z<=a:continue
                with store.db:store.db.execute('INSERT INTO activity(start,end,app,state,closed,capture_version) VALUES(?,?,?,?,1,2)',(a,z,name,state))
        with store.db:store.db.execute("UPDATE runtime SET collector_seen=?,capture_status='active' WHERE id=1",(now,))
        app.show_page('Today');GLib.timeout_add(700,render_today);return False
    def render_today():
        snapshot(app.win,'personal-work-today-development.png');window=app.screen_insights(day);window.set_default_size(720,1000)
        GLib.timeout_add(700,lambda:(snapshot(window,'screen-time-development.png'),app.quit(),False)[2]);return False
    app.connect('activate',lambda _:GLib.idle_add(prepare))
    with patch.object(desktop,'start_collector'),patch.object(desktop,'start_automation'),patch.object(desktop,'read_health',return_value={'status':'active','at':now,'error':''}),patch('timesheet.jev.get_key',side_effect=AssertionError('No key in previews')),patch('timesheet.jev.decide',side_effect=AssertionError('No network in previews')):app.run([])

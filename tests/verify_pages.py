"""Render every GTK page with disposable data; no physical input injection."""
import os
import tempfile
import traceback
from pathlib import Path
from unittest.mock import patch

with tempfile.TemporaryDirectory(prefix='timesheet-pages-') as directory:
    os.environ.update(XDG_DATA_HOME=directory,TIMESHEET_TESTING='1')
    from timesheet.app import TimeSheet, PAGES, Gtk, GLib, desktop
    app=TimeSheet(); app.set_application_id('org.local.TimeSheetPageSmoke')
    task=app.store.quick_project('Example','Compatibility','Review',6000)
    entry=app.store.add_entry(task,1000,4600,'Synthetic work'); app.store.approve(entry)
    app.store.create_report(1,0,5000)
    pages=iter(PAGES); failures=[]
    output=Path('/tmp/timesheet-compatibility-pages'); output.mkdir(exist_ok=True)
    def advance():
        try:
            page=next(pages)
            app.nav[page].emit('clicked')
            assert app.page==page
            GLib.timeout_add(150,render)
        except StopIteration: app.quit()
        except Exception: failures.append(traceback.format_exc()); app.quit()
        return False
    def render():
        try:
            paint=Gtk.WidgetPaintable.new(app.win); snapshot=Gtk.Snapshot.new()
            paint.snapshot(snapshot,app.win.get_width(),app.win.get_height())
            node=snapshot.to_node(); assert node
            texture=app.win.get_renderer().render_texture(node,None)
            assert texture.save_to_png(str(output/(app.page.lower()+'.png')))
            print('PASS: GTK navigation handler and render:',app.page,flush=True)
            GLib.timeout_add(100,advance)
        except Exception: failures.append(traceback.format_exc()); app.quit()
        return False
    with patch.object(desktop,'start_collector'), patch.object(desktop,'read_health',return_value={'status':'paused','error':''}):
        app.connect('activate',lambda _:GLib.timeout_add(400,advance))
        app.run([])
    if failures: raise RuntimeError('\n'.join(failures))

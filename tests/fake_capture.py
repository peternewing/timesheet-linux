"""A private test D-Bus service; not installed or used by the application."""
import json,os
from pathlib import Path
from gi.repository import Gio, GLib
XML='''<node><interface name="org.local.TimeSheetCapture"><method name="GetState"><arg type="s" direction="out"/><arg type="s" direction="out"/><arg type="x" direction="out"/><arg type="b" direction="out"/></method></interface></node>'''
node=Gio.DBusNodeInfo.new_for_xml(XML)
conn=Gio.bus_get_sync(Gio.BusType.SESSION,None)
conn.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','RequestName',GLib.Variant('(su)',('org.local.TimeSheetCapture',0)),GLib.VariantType.new('(u)'),Gio.DBusCallFlags.NONE,-1,None)
def call(connection,sender,path,interface,method,params,invocation):
    data=json.loads(Path(os.environ['TEST_CAPTURE_STATE']).read_text())
    invocation.return_value(GLib.Variant('(ssxb)',(data['app'],data['title'],data['idle'],data['locked'])))
conn.register_object('/org/local/TimeSheetCapture',node.interfaces[0],call,None,None)
print('ready',flush=True)
GLib.MainLoop().run()

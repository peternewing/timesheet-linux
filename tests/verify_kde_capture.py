"""Private-bus integration; simulates KWin, not a real Plasma acceptance test.
Run: PYTHONPATH=. dbus-run-session -- /usr/bin/python3 tests/verify_kde_capture.py
"""
import subprocess
import sys
import time
from unittest.mock import patch
from timesheet.capture import KDECapture

sender = r'''
import time
from gi.repository import Gio, GLib
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus',
    'RequestName',GLib.Variant('(su)',('org.kde.KWin',0)),None,Gio.DBusCallFlags.NONE,1000,None)
while True:
    try:
        bus.call_sync('org.local.TimeSheetLinux.Capture','/org/local/TimeSheetLinux/Capture',
            'org.local.TimeSheetLinux.Capture','Focus',GLib.Variant('(ss)',('org.kde.kate','Synthetic title')),
            None,Gio.DBusCallFlags.NONE,1000,None)
    except GLib.Error: pass
    time.sleep(.1)
'''
adapter=KDECapture()
process=subprocess.Popen([sys.executable,'-c',sender])
try:
    with patch.object(adapter.idle,'sample',return_value=100), patch('timesheet.capture.screen_locked',return_value=False):
        deadline=time.monotonic()+6
        state=None
        while time.monotonic()<deadline:
            state=adapter.sample()
            if state: break
            time.sleep(.05)
        assert state==('org.kde.kate','Synthetic title',100,False), state
        process.terminate(); process.wait(timeout=3)
        # Drain any in-flight calls before testing expiry.
        adapter.sample(); time.sleep(3.2)
        assert adapter.sample() is None, 'Stale focus remained valid'
    print('PASS: real D-Bus KWin-owner authentication, focus delivery and heartbeat expiry (simulated KWin)')
finally:
    if process.poll() is None: process.terminate(); process.wait(timeout=3)
    adapter.close()

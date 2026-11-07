"""Real headless Hyprland foreground/idle test; synthetic D-Bus lock service.
Run under dbus-run-session. TIMESHEET_HYPR_ROOT may point to extracted packages.
"""
import os,subprocess,sys,tempfile,time
from pathlib import Path

service=r'''
import os
from pathlib import Path
from gi.repository import Gio,GLib
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
xml='<node><interface name="org.freedesktop.ScreenSaver"><method name="GetActive"><arg type="b" direction="out"/></method></interface></node>'
info=Gio.DBusNodeInfo.new_for_xml(xml)
def method(conn,sender,path,interface,name,args,invocation):
    invocation.return_value(GLib.Variant('(b)',(Path(os.environ['LOCK_STATE']).read_text()=='locked',)))
bus.register_object('/ScreenSaver',info.interfaces[0],method,None,None)
Gio.bus_own_name_on_connection(bus,'org.freedesktop.ScreenSaver',Gio.BusNameOwnerFlags.NONE,None,None)
GLib.MainLoop().run()
'''
with tempfile.TemporaryDirectory(prefix='timesheet-hypr-') as folder:
    root=Path(folder);runtime=root/'runtime';runtime.mkdir(mode=0o700)
    os.environ.update(XDG_RUNTIME_DIR=str(runtime),XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),
        XDG_CACHE_HOME=str(root/'cache'),XDG_STATE_HOME=str(root/'state'),
        XDG_SESSION_TYPE='wayland',XDG_CURRENT_DESKTOP='Hyprland',AQ_BACKENDS='headless',LIBGL_ALWAYS_SOFTWARE='1',
        WLR_RENDERER_ALLOW_SOFTWARE='1',LOCK_STATE=str(root/'lock'))
    os.environ.pop('DISPLAY',None);os.environ.pop('WAYLAND_DISPLAY',None)
    Path(os.environ['LOCK_STATE']).write_text('unlocked')
    prefix=os.environ.get('TIMESHEET_HYPR_ROOT')
    if prefix:
        os.environ['PATH']=prefix+'/usr/bin:'+os.environ['PATH']
        os.environ['LD_LIBRARY_PATH']=prefix+'/usr/lib/x86_64-linux-gnu'
        os.environ['XDG_DATA_DIRS']=prefix+'/usr/share:/usr/share'
    (root/'hyprland.conf').write_text('monitor=,1024x768@60,0x0,1\nmisc { disable_hyprland_logo = true }\n')
    from timesheet.capture import Capture
    capture=None;window=None;shell=None;locker=None
    log=Path('/tmp/timesheet-hypr-test.log').open('w')
    def wait(fn,timeout=20):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            value=fn()
            if value:return value
            if shell and shell.poll() is not None:raise RuntimeError('Hyprland exited; see /tmp/timesheet-hypr-test.log')
            time.sleep(.1)
        raise AssertionError('Timed out; see /tmp/timesheet-hypr-test.log')
    try:
        locker=subprocess.Popen([sys.executable,'-c',service],stdout=log,stderr=log)
        shell=subprocess.Popen(['Hyprland','--config',str(root/'hyprland.conf')],stdout=log,stderr=log)
        ipc=wait(lambda:next(runtime.glob('hypr/*/.socket.sock'),None))
        display=wait(lambda:next((x for x in runtime.glob('wayland-*') if not str(x).endswith('.lock')),None))
        os.environ['HYPRLAND_INSTANCE_SIGNATURE']=ipc.parent.name;os.environ['WAYLAND_DISPLAY']=display.name
        capture=Capture()
        env=os.environ.copy();env['GDK_BACKEND']='wayland'
        window=subprocess.Popen([sys.executable,'tests/fixture_window.py'],env=env,stdout=log,stderr=log)
        state=wait(lambda:(s if s and s[0] and s[1]=='Time Sheet capture fixture' and s[2]>=0 else None) if (s:=capture.sample()) else None)
        assert not state[3],state
        print('PASS: real Hyprland IPC, Wayland window and idle observer',flush=True)
        Path(os.environ['LOCK_STATE']).write_text('locked')
        wait(lambda:(s and s[3]) if (s:=capture.sample()) else False)
        print('PASS: lock service causes locked state (synthetic lock service)',flush=True)
        window.terminate();window.wait(timeout=5);window=None
    finally:
        if capture:capture.close()
        for process in (window,shell,locker):
            if process and process.poll() is None:
                process.terminate()
                try:process.wait(timeout=8)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        log.close()

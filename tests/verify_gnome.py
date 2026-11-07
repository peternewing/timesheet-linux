"""Optional real GNOME Shell integration test in an isolated headless session."""
import json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path

with tempfile.TemporaryDirectory(prefix='timesheet-gnome-') as directory:
    root=Path(directory); runtime=root/'runtime'; runtime.mkdir(mode=0o700)
    os.environ.update(XDG_DATA_HOME=str(root/'share'),XDG_CONFIG_HOME=str(root/'config'),XDG_RUNTIME_DIR=str(runtime),GSETTINGS_BACKEND='keyfile')
    extension=root/'share/gnome-shell/extensions/timesheet-capture@local'
    shutil.copytree('resources/gnome-extension',extension)
    from gi.repository import Gio,GLib
    settings=Gio.Settings.new('org.gnome.shell'); settings.set_strv('enabled-extensions',['timesheet-capture@local']); settings.set_boolean('disable-user-extensions',False); Gio.Settings.sync()
    logfile=Path('/tmp/timesheet-gnome-test.log'); log=logfile.open('w')
    shell=subprocess.Popen(['gnome-shell','--headless','--wayland','--no-x11','--wayland-display=timesheet-test','--virtual-monitor','1024x768'],stdout=log,stderr=log)
    window=None
    try:
        from timesheet.collector import get_focus
        until=time.monotonic()+30; result=None
        while time.monotonic()<until and shell.poll() is None:
            result=get_focus()
            if result is not None: break
            time.sleep(.5)
        if result is None:
            raise RuntimeError('GNOME helper did not load. See '+str(logfile))
        print('PASS: real GNOME Shell loaded the extension and returned idle/lock data:',result[2:],flush=True)
        env=os.environ.copy();env.update(GDK_BACKEND='wayland',WAYLAND_DISPLAY='timesheet-test')
        window=subprocess.Popen([sys.executable,'tests/fixture_window.py'],env=env,stdout=log,stderr=log)
        until=time.monotonic()+15
        while time.monotonic()<until:
            result=get_focus()
            if result and result[1]=='Time Sheet capture fixture':break
            time.sleep(.5)
        assert result and result[1]=='Time Sheet capture fixture' and result[0], 'Foreground application was not detected'
        print('PASS: real Wayland foreground window and application detected',flush=True)
    finally:
        if window:
            window.terminate();window.wait(timeout=5)
        shell.terminate()
        try:shell.wait(timeout=8)
        except subprocess.TimeoutExpired:shell.kill();shell.wait()
        log.close()

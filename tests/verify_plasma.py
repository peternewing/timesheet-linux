"""Real headless Plasma/KWin Wayland capture; private D-Bus and disposable settings.
Run under dbus-run-session. Requires kwin_wayland, swayidle and GTK dependencies.
TIMESHEET_KDE_ROOT may point to extracted distro packages for a non-system install.
"""
import os,shutil,subprocess,sys,tempfile,time
from pathlib import Path

with tempfile.TemporaryDirectory(prefix='timesheet-plasma-') as folder:
    root=Path(folder); runtime=root/'runtime'; runtime.mkdir(mode=0o700)
    os.environ.update(XDG_DATA_HOME=str(root/'share'),XDG_CONFIG_HOME=str(root/'config'),
        XDG_RUNTIME_DIR=str(runtime),XDG_CURRENT_DESKTOP='KDE',XDG_SESSION_TYPE='wayland',
        WAYLAND_DISPLAY='timesheet-plasma',QT_QPA_PLATFORM='offscreen',LIBGL_ALWAYS_SOFTWARE='1')
    os.environ.pop('DISPLAY',None)
    kde=os.environ.get('TIMESHEET_KDE_ROOT')
    if kde:
        os.environ['PATH']=kde+'/usr/bin:'+os.environ['PATH']
        os.environ['LD_LIBRARY_PATH']=kde+'/usr/lib/x86_64-linux-gnu'
        os.environ['QT_PLUGIN_PATH']=kde+'/usr/lib/x86_64-linux-gnu/qt6/plugins'
        os.environ['QML_IMPORT_PATH']=kde+'/usr/lib/x86_64-linux-gnu/qt6/qml'
        os.environ['XDG_DATA_DIRS']=kde+'/usr/share:/usr/share'
    config=root/'config'; config.mkdir()
    (config/'kwinrc').write_text('[Plugins]\ntimesheet-captureEnabled=true\n[Compositing]\nBackend=QPainter\n')
    shutil.copytree('resources/kwin-script',root/'share/kwin/scripts/timesheet-capture')
    from timesheet.capture import Capture,call
    capture=Capture(); shell=None;window=None
    log=Path('/tmp/timesheet-plasma-test.log').open('w')
    def wait(predicate,seconds=20):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            result=predicate()
            if result: return result
            if shell and shell.poll() is not None: raise RuntimeError('KWin exited; see /tmp/timesheet-plasma-test.log')
            time.sleep(.1)
        raise AssertionError('Timed out; see /tmp/timesheet-plasma-test.log')
    try:
        shell=subprocess.Popen(['kwin_wayland','--virtual','--socket','timesheet-plasma',
            '--width','1024','--height','768','--no-global-shortcuts','--no-kactivities'],stdout=log,stderr=log)
        wait(lambda:(runtime/'timesheet-plasma').exists())
        env=os.environ.copy();env['GDK_BACKEND']='wayland'
        window=subprocess.Popen([sys.executable,'tests/fixture_window.py'],env=env,stdout=log,stderr=log)
        state=wait(lambda:(s if s and s[0] and s[1]=='Time Sheet capture fixture' and s[2]>=0 else None) if (s:=capture.sample()) else None)
        assert not state[3],state
        print('PASS: real Plasma KWin script, Wayland window, swayidle and unlocked service',flush=True)
        first=state[2];time.sleep(2);state=capture.sample()
        assert state and state[2]>first, state
        print('PASS: actual compositor idle time increases',flush=True)
        window.terminate();window.wait(timeout=5);window=None
        wait(lambda:(s is not None and s[0]=='') if (s:=capture.sample()) is not None else False)
        print('PASS: closing real window clears foreground identity',flush=True)
        shell.terminate();shell.wait(timeout=10);shell=None
        time.sleep(3.2);assert capture.sample() is None
        print('PASS: compositor exit invalidates focus',flush=True)
    finally:
        capture.close()
        for process in (window,shell):
            if process and process.poll() is None:
                process.terminate()
                try:process.wait(timeout=8)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        log.close()

"""Per-user desktop installation and collector lifecycle. No root access required."""
from __future__ import annotations
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from gi.repository import Gio, GLib
from .store import DATA_DIR, Store
from .capture import backend_name, dependencies

ROOT=Path(__file__).resolve().parent.parent
APP_ID='org.local.TimeSheetLinux'
UUID='timesheet-capture@local'
CONFIG=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))
SHARE=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))
SERVICE=CONFIG/'systemd/user/time-sheet-linux.service'
AUTOSTART=CONFIG/'autostart/time-sheet-linux.desktop'


def quote(value):
    return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$')+'"'


def run_systemd(*args):
    try:
        return subprocess.run(['systemctl','--user',*args],capture_output=True,text=True,timeout=8,check=False)
    except (OSError,subprocess.TimeoutExpired):
        return None


def start_collector():
    if os.environ.get('TIMESHEET_TESTING')!='1' and SERVICE.exists():
        # Graphical autostart has the current session environment; systemd may not.
        variables = ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY',
                     'XDG_SESSION_TYPE', 'XDG_CURRENT_DESKTOP', 'XDG_SESSION_ID')
        names = [name for name in variables if name in os.environ]
        absent = [name for name in variables if name not in os.environ]
        if absent: run_systemd('unset-environment', *absent)
        if names: run_systemd('import-environment', *names)
        result=run_systemd('start','time-sheet-linux.service')
        if result is not None and result.returncode==0: return
    env=os.environ.copy(); env['PYTHONPATH']=str(ROOT)
    subprocess.Popen([sys.executable,'-m','timesheet.collector'],cwd=ROOT,env=env,
                     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)


def stop_collector(wait=True):
    if os.environ.get('TIMESHEET_TESTING')!='1' and SERVICE.exists(): run_systemd('stop','time-sheet-linux.service')
    p=DATA_DIR/'collector.pid'
    try:
        pid=int(p.read_text()); cmd=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        if b'timesheet.collector' in cmd:
            os.kill(pid,signal.SIGTERM)
            if wait:
                deadline=time.monotonic()+5
                while p.exists() and time.monotonic()<deadline: time.sleep(.1)
    except (ValueError,FileNotFoundError,ProcessLookupError,PermissionError): pass


def set_paused(store,paused,minutes=0):
    now=int(time.time())
    if paused and store.runtime()['state']=='running': store.stop_timer(now,'tracking paused')
    store.set('pause_at',now if paused else 0)
    store.set('pause_until',now+minutes*60 if paused and minutes else 0)
    store.set('capture_enabled','0' if paused else '1')


def read_health(store):
    try:
        value=json.loads((DATA_DIR/'health.json').read_text())
        if time.time()-value['at']<12: return value
    except (OSError,ValueError,KeyError): pass
    rt=store.runtime()
    if rt['collector_seen'] and time.time()-rt['collector_seen']<12:
        return dict(status=rt['capture_status'],at=rt['collector_seen'],error=rt['last_error'])
    return dict(status='stopped',at=0,error='')


def capture_available():
    if backend_name() in ('kde', 'x11'):
        try:
            value=json.loads((DATA_DIR/'health.json').read_text())
            return time.time()-value['at']<12 and value['status']=='active'
        except (OSError,ValueError,KeyError): return False
    try:
        bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        return bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','NameHasOwner',
            GLib.Variant('(s)',('org.local.TimeSheetCapture',)),GLib.VariantType.new('(b)'),Gio.DBusCallFlags.NONE,1000,None).unpack()[0]
    except GLib.Error: return False

def gnome_supported():
    if os.environ.get('XDG_SESSION_TYPE')!='wayland' or 'GNOME' not in os.environ.get('XDG_CURRENT_DESKTOP','').upper(): return False
    try:
        version=subprocess.run(['gnome-shell','--version'],capture_output=True,text=True,timeout=3).stdout.strip().split()[-1]
        return version.split('.')[0]=='50'
    except (OSError,subprocess.TimeoutExpired,IndexError): return False

def supported_desktop():
    name = backend_name()
    if name == 'gnome': return gnome_supported()
    if name == 'x11': return not dependencies(name)
    if name == 'kde':
        return bool(shutil.which('kwriteconfig6')) and not dependencies(name)
    return False


def install_kwin():
    destination = SHARE/'kwin/scripts/timesheet-capture'
    shutil.copytree(ROOT/'resources/kwin-script', destination, dirs_exist_ok=True)
    result = subprocess.run(['kwriteconfig6', '--file', 'kwinrc', '--group', 'Plugins',
                            '--key', 'timesheet-captureEnabled', 'true'],
                           capture_output=True, timeout=5)
    if result.returncode: return False
    from .capture import call
    call('org.kde.KWin', '/KWin', 'org.kde.KWin', 'reconfigure', '()')
    return True


def shell_settings():
    source=Gio.SettingsSchemaSource.get_default()
    if not source or not source.lookup('org.gnome.shell',True): return None
    return Gio.Settings.new('org.gnome.shell')


def set_autostart(enabled):
    if enabled:
        AUTOSTART.parent.mkdir(parents=True,exist_ok=True)
        AUTOSTART.write_text('[Desktop Entry]\nType=Application\nName=Time Sheet Linux\nExec='+quote(ROOT/'run-timesheet')+' --background\nX-GNOME-Autostart-enabled=true\n',encoding='utf-8')
        # XDG autostart imports the session environment before starting the unit.
        # Do not also start it from graphical-session.target with stale variables.
        if SERVICE.exists(): run_systemd('disable','time-sheet-linux.service')
    else:
        AUTOSTART.unlink(missing_ok=True)
        if SERVICE.exists(): run_systemd('disable','time-sheet-linux.service')


def install(enable_capture=True):
    applications=SHARE/'applications'; applications.mkdir(parents=True,exist_ok=True)
    icons=SHARE/'icons/hicolor/scalable/apps'; icons.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(ROOT/'resources/timesheet.svg',icons/(APP_ID+'.svg'))
    launcher=applications/(APP_ID+'.desktop')
    text='''[Desktop Entry]
Type=Application
Name=Time Sheet Linux
Comment=Automatic private desktop time tracking and client timesheets
Exec={exec}
Icon=org.local.TimeSheetLinux
Terminal=false
Categories=Office;Finance;ProjectManagement;
StartupNotify=true
StartupWMClass=org.local.TimeSheetLinux
Actions=Pause;Resume;

[Desktop Action Pause]
Name=Pause tracking
Exec={exec} --pause

[Desktop Action Resume]
Name=Resume tracking
Exec={exec} --resume
'''.format(exec=quote(ROOT/'run-timesheet'))
    launcher.write_text(text,encoding='utf-8')
    commands=Path.home()/'.local/bin'; commands.mkdir(parents=True,exist_ok=True)
    command=commands/'time-sheet-linux'
    # The wrapper is a launcher, not a second copy of the application.
    import shlex
    command.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'run-timesheet'))+' "$@"\n',encoding='utf-8')
    command.chmod(0o755)
    legacy=applications/'time-sheet-linux.desktop'
    if legacy.exists() and 'run-timesheet' in legacy.read_text(): legacy.unlink()
    SERVICE.parent.mkdir(parents=True,exist_ok=True)
    working=str(ROOT).replace('%','%%')
    SERVICE.write_text('''[Unit]
Description=Time Sheet Linux activity collector
PartOf=graphical-session.target
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory='''+working+'''
ExecStart=/usr/bin/python3 -m timesheet.collector
Restart=on-failure
RestartSec=5
TimeoutStopSec=8
UMask=0077

[Install]
WantedBy=graphical-session.target
''',encoding='utf-8')
    result=run_systemd('daemon-reload')
    with_store=Store()
    first_install=with_store.get('setup_complete','0')!='1'
    startup_enabled=first_install or AUTOSTART.exists()
    set_autostart(startup_enabled)
    compatible=supported_desktop()
    gnome=gnome_supported()
    kde=backend_name()=='kde' and compatible
    if kde:
        try: compatible=install_kwin()
        except (OSError,subprocess.TimeoutExpired): compatible=False
    if gnome:
        extension=SHARE/'gnome-shell/extensions'/UUID
        extension.mkdir(parents=True,exist_ok=True)
        for name in ('extension.js','metadata.json'):
            shutil.copyfile(ROOT/'resources/gnome-extension'/name,extension/name)
    extension_enabled=False
    try:
        settings=shell_settings() if gnome else None
        if settings is None: raise ValueError('GNOME 50 Wayland is required for automatic capture.')
        enabled=settings.get_strv('enabled-extensions')
        if UUID not in enabled: settings.set_strv('enabled-extensions',enabled+[UUID])
        disabled=settings.get_strv('disabled-extensions')
        if UUID in disabled: settings.set_strv('disabled-extensions',[x for x in disabled if x!=UUID])
        Gio.Settings.sync()
        extension_enabled=True
    except (GLib.Error,ValueError): pass
    try:
        if enable_capture and first_install: set_paused(with_store,not compatible)
        with_store.set('setup_complete','1')
    finally: with_store.close()
    stop_collector()
    start_collector()
    running=run_systemd('is-active','time-sheet-linux.service')
    return dict(launcher=str(launcher),service=bool(running and running.returncode==0),
                extension_installed=gnome,extension_enabled=extension_enabled,
                backend=backend_name(),missing_dependencies=dependencies(),
                needs_sign_in=(gnome or kde) and not capture_available(),manual_only=not compatible)


def uninstall():
    stop_collector()
    set_autostart(False)
    SERVICE.unlink(missing_ok=True); run_systemd('daemon-reload')
    (SHARE/'applications'/(APP_ID+'.desktop')).unlink(missing_ok=True)
    (SHARE/'icons/hicolor/scalable/apps'/(APP_ID+'.svg')).unlink(missing_ok=True)
    command=Path.home()/'.local/bin/time-sheet-linux'
    if command.exists() and str(ROOT/'run-timesheet') in command.read_text(): command.unlink()
    try:
        settings=shell_settings()
        if settings is None: raise ValueError('No GNOME settings')
        settings.set_strv('enabled-extensions',[x for x in settings.get_strv('enabled-extensions') if x!=UUID]); Gio.Settings.sync()
    except (GLib.Error,ValueError): pass
    extension=SHARE/'gnome-shell/extensions'/UUID
    if extension.exists(): shutil.rmtree(extension)
    kwin=SHARE/'kwin/scripts/timesheet-capture'
    if kwin.exists():
        tool=shutil.which('kwriteconfig6')
        if tool:
            try:
                subprocess.run([tool,'--file','kwinrc','--group','Plugins','--key',
                                'timesheet-captureEnabled','false'],timeout=5,check=False)
            except (OSError,subprocess.TimeoutExpired): pass
        from .capture import call
        call('org.kde.KWin','/Scripting','org.kde.kwin.Scripting','unloadScript','(b)',
             GLib.Variant('(s)',('timesheet-capture',)))
        shutil.rmtree(kwin)
    return 'Application integration removed. Your timesheet data has been kept in '+str(DATA_DIR)

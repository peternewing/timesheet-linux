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
from .capture import backend_name, dependencies, host_environment

ROOT=Path(__file__).resolve().parent.parent
APP_ID='org.local.TimeSheetLinux'
UUID='timesheet-capture@local'
CONFIG=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))
SHARE=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))
SERVICE=CONFIG/'systemd/user/time-sheet-linux.service'
AUTOSTART=CONFIG/'autostart/time-sheet-linux.desktop'
APPIMAGE=os.environ.get('APPIMAGE')
FLATPAK=bool(os.environ.get('FLATPAK_ID'))
EXECUTABLE=Path(APPIMAGE) if APPIMAGE else ROOT/'run-timesheet'


def quote(value):
    return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$')+'"'


def run_systemd(*args):
    try:
        return subprocess.run(['systemctl','--user',*args],capture_output=True,text=True,timeout=8,check=False,env=host_environment())
    except (OSError,subprocess.TimeoutExpired):
        return None


def start_automation():
    """Start only the installation explicitly authorised in the saved policy."""
    if os.environ.get('TIMESHEET_TESTING')=='1':return
    from .decision_policy import settings,owner_token
    store=Store()
    try:config=settings(store.get('ai_policy','{}'))
    finally:store.close()
    if config['mode']=='off' or config['owner']!=owner_token() or config['backend']!=('flatpak' if FLATPAK else 'native'):return
    if not FLATPAK and SERVICE.with_name('time-sheet-linux-ai.service').exists() and str(APPIMAGE or ROOT) in SERVICE.with_name('time-sheet-linux-ai.service').read_text():
        result=run_systemd('start','time-sheet-linux-ai.service')
        if result is not None and result.returncode==0:return
    env=os.environ.copy();env['PYTHONPATH']=str(ROOT)+os.pathsep+env.get('PYTHONPATH','')
    command=[APPIMAGE,'--automation-direct'] if APPIMAGE else [sys.executable,'-m','timesheet.automation_worker']
    subprocess.Popen(command,cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)


def stop_automation(wait=True):
    if os.environ.get('TIMESHEET_TESTING')=='1':return
    if not FLATPAK and SERVICE.with_name('time-sheet-linux-ai.service').exists():run_systemd('stop','time-sheet-linux-ai.service')
    pidfile=DATA_DIR/'automation.pid'
    try:
        pid=int(pidfile.read_text());args=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        if b'timesheet.automation_worker' in args or b'--automation-direct' in args:
            os.kill(pid,signal.SIGTERM)
            if wait:
                deadline=time.monotonic()+18
                while pidfile.exists() and time.monotonic()<deadline:time.sleep(.1)
    except (OSError,ValueError):pass
    # A worker from another sandbox may not have the same PID namespace. Never
    # replace a database while an un-stopped worker still owns its lock.
    import fcntl
    DATA_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(DATA_DIR/'automation.lock','a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Stop Jev automation in the other running installation before restoring or replacing data.')
        finally:fcntl.flock(lock,fcntl.LOCK_UN)


def start_collector():
    start_automation()
    if FLATPAK: return  # The host companion owns and supervises capture.
    if os.environ.get('TIMESHEET_TESTING')!='1' and SERVICE.exists():
        # Graphical autostart has the current session environment; systemd may not.
        variables = ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY',
                     'XDG_SESSION_TYPE', 'XDG_CURRENT_DESKTOP', 'XDG_SESSION_ID',
                     'SWAYSOCK', 'HYPRLAND_INSTANCE_SIGNATURE')
        names = [name for name in variables if name in os.environ]
        absent = [name for name in variables if name not in os.environ]
        if absent: run_systemd('unset-environment', *absent)
        if names: run_systemd('import-environment', *names)
        result=run_systemd('start','time-sheet-linux.service')
        if result is not None and result.returncode==0: return
    env=os.environ.copy(); env['PYTHONPATH']=str(ROOT)
    command=[APPIMAGE,'--collector-direct'] if APPIMAGE else [sys.executable,'-m','timesheet.collector']
    subprocess.Popen(command,cwd=ROOT,env=env,
                     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)


def stop_collector(wait=True):
    stop_automation(wait=wait)
    if FLATPAK:
        import fcntl
        DATA_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
        with open(DATA_DIR/'collector.lock','a+') as lock:
            try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: raise ValueError('Stop the host collector before restoring a backup; see the installation guide.')
            finally: fcntl.flock(lock,fcntl.LOCK_UN)
        return
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
    if backend_name() in ('kde', 'x11', 'sway', 'hyprland'):
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
        version=subprocess.run(['gnome-shell','--version'],capture_output=True,text=True,timeout=3,env=host_environment()).stdout.strip().split()[-1]
        return version.split('.')[0]=='50'
    except (OSError,subprocess.TimeoutExpired,IndexError): return False

def supported_desktop():
    name = backend_name()
    if name == 'gnome': return gnome_supported()
    if name in ('x11', 'sway', 'hyprland'): return not dependencies(name)
    if name == 'kde':
        return bool(shutil.which('kwriteconfig6')) and not dependencies(name)
    return False


def install_kwin():
    destination = SHARE/'kwin/scripts/timesheet-capture'
    shutil.copytree(ROOT/'resources/kwin-script', destination, dirs_exist_ok=True)
    result = subprocess.run(['kwriteconfig6', '--file', 'kwinrc', '--group', 'Plugins',
                            '--key', 'timesheet-captureEnabled', 'true'],
                           capture_output=True, timeout=5, env=host_environment())
    if result.returncode: return False
    from .capture import call
    call('org.kde.KWin', '/KWin', 'org.kde.KWin', 'reconfigure', '()')
    return True


def shell_settings():
    source=Gio.SettingsSchemaSource.get_default()
    schema=source.lookup('org.gnome.shell',True) if source else None
    if schema is None and APPIMAGE:
        try:
            source=Gio.SettingsSchemaSource.new_from_directory('/usr/share/glib-2.0/schemas',None,False)
            schema=source.lookup('org.gnome.shell',True)
        except GLib.Error: return None
    return Gio.Settings.new_full(schema,None,None) if schema else None


def set_autostart(enabled,host_only=False):
    if FLATPAK: return
    if enabled:
        AUTOSTART.parent.mkdir(parents=True,exist_ok=True)
        AUTOSTART.write_text('[Desktop Entry]\nType=Application\nName=Time Sheet Linux\nExec='+quote(ROOT/'run-host' if host_only else EXECUTABLE)+' --background\nX-GNOME-Autostart-enabled=true\n',encoding='utf-8')
        # XDG autostart imports the session environment before starting the unit.
        # Do not also start it from graphical-session.target with stale variables.
        if SERVICE.exists(): run_systemd('disable','time-sheet-linux.service')
    else:
        AUTOSTART.unlink(missing_ok=True)
        if SERVICE.exists(): run_systemd('disable','time-sheet-linux.service')


def previous_source_owner(launcher=None):
    """Identify the existing source launcher without running previous code."""
    import ast,hashlib,shlex
    try:
        launcher=Path(launcher) if launcher else Path.home()/'.local/bin/time-sheet-linux'
        lines=launcher.read_text().splitlines()
        args=shlex.split(next(line for line in lines if line.startswith('exec ')))
        executable=Path(args[1]).resolve()
        if executable.name!='run-timesheet':return None
        root=executable.parent;data=(root/'timesheet/__init__.py').read_text()
        if len(data)>4096:return None
        for node in ast.parse(data).body:
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='__version__' for t in node.targets) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):
                return hashlib.sha256((str(root)+'|'+node.value.value).encode()).hexdigest()
    except (OSError,ValueError,SyntaxError,StopIteration,IndexError):pass
    return None


def adopt_compatible_policy(store,previous_owner):
    """An authorised source upgrade changes ownership, never the data policy."""
    if not previous_owner or FLATPAK or APPIMAGE:return False
    from .automation_store import Repository
    from .decision_policy import owner_token
    from .decision_context import canonical
    from .simple_setup import preset_ids
    repo=Repository(store);config=repo.config()
    if config['mode']=='off' or config['backend']!='native' or config['owner']!=previous_owner:return False
    if config['category_tasks'] and not set(config['category_tasks'])<=set(preset_ids(store).values()):return False
    config={**config,'owner':owner_token()}
    with store.db:
        store.db.execute('BEGIN IMMEDIATE');store.set('ai_policy',canonical(config));store.set('ai_discover_after','0')
        store.db.execute("UPDATE ai_jobs SET state='stale',reason='Compatible app upgrade; local context will be revalidated.',updated=? WHERE state IN ('pending','running','exception','failed')",(int(time.time()),))
        store.audit('compatible source upgrade',{})
    return True


def install(enable_capture=True,host_only=False):
    if FLATPAK: raise ValueError('Install or repair the host companion outside Flatpak; see the installation guide.')
    previous_owner=previous_source_owner() if not host_only else None
    launcher=SHARE/'applications'/(APP_ID+'.desktop')
    if not host_only:
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
    '''.format(exec=quote(EXECUTABLE)).replace('\n    ','\n')
        launcher.write_text(text,encoding='utf-8')
        commands=Path.home()/'.local/bin'; commands.mkdir(parents=True,exist_ok=True)
        command=commands/'time-sheet-linux'
        # The wrapper is a launcher, not a second copy of the application.
        import shlex
        command.write_text('#!/bin/sh\nexec '+shlex.quote(str(EXECUTABLE))+' "$@"\n',encoding='utf-8')
        command.chmod(0o755)
        legacy=applications/'time-sheet-linux.desktop'
        if legacy.exists() and 'run-timesheet' in legacy.read_text(): legacy.unlink()
    SERVICE.parent.mkdir(parents=True,exist_ok=True)
    working=str(Path(APPIMAGE).parent if APPIMAGE else ROOT).replace('%','%%')
    collector_exec=(quote(APPIMAGE).replace('%','%%')+' --collector-direct') if APPIMAGE else '/usr/bin/python3 -m timesheet.collector'
    SERVICE.write_text('''[Unit]
Description=Time Sheet Linux '''+('host companion' if host_only else 'activity collector')+'''
PartOf=graphical-session.target
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory='''+working+'''
ExecStart='''+collector_exec+'''
Restart=on-failure
RestartSec=5
TimeoutStopSec=8
UMask=0077

[Install]
WantedBy=graphical-session.target
''',encoding='utf-8')
    ai_exec=(quote(APPIMAGE).replace('%','%%')+' --automation-direct') if APPIMAGE else '/usr/bin/python3 -m timesheet.automation_worker'
    SERVICE.with_name('time-sheet-linux-ai.service').write_text('[Unit]\nDescription=Time Sheet Linux Jev decision worker\nPartOf=graphical-session.target\nAfter=graphical-session.target\n\n[Service]\nType=simple\nWorkingDirectory='+working+'\nExecStart='+ai_exec+'\nRestart=on-failure\nRestartSec=15\nTimeoutStopSec=20\nUMask=0077\n',encoding='utf-8')
    result=run_systemd('daemon-reload')
    with_store=Store()
    first_install=with_store.get('setup_complete','0')!='1'
    startup_enabled=first_install or AUTOSTART.exists()
    set_autostart(startup_enabled,host_only=host_only)
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
    if previous_owner:
        policy_store=Store()
        try:adopt_compatible_policy(policy_store,previous_owner)
        finally:policy_store.close()
    start_collector()
    running=run_systemd('is-active','time-sheet-linux.service')
    return dict(launcher=None if host_only else str(launcher),service=bool(running and running.returncode==0),
                extension_installed=gnome,extension_enabled=extension_enabled,
                backend=backend_name(),missing_dependencies=dependencies(),
                needs_sign_in=(gnome or kde) and not capture_available(),manual_only=not compatible)


def uninstall(host_only=False):
    if FLATPAK: raise ValueError('Remove the host companion outside Flatpak; see the installation guide.')
    if host_only:
        if not SERVICE.exists(): raise ValueError('No host companion service is installed.')
        service=SERVICE.read_text()
        if 'Description=Time Sheet Linux host companion' not in service or str(ROOT) not in service:
            raise ValueError('The installed collector does not belong to this host companion checkout.')
    stop_collector()
    set_autostart(False)
    SERVICE.unlink(missing_ok=True); SERVICE.with_name('time-sheet-linux-ai.service').unlink(missing_ok=True); run_systemd('daemon-reload')
    if not host_only:
        (SHARE/'applications'/(APP_ID+'.desktop')).unlink(missing_ok=True)
        (SHARE/'icons/hicolor/scalable/apps'/(APP_ID+'.svg')).unlink(missing_ok=True)
        command=Path.home()/'.local/bin/time-sheet-linux'
        if command.exists() and str(EXECUTABLE) in command.read_text(): command.unlink()
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
                                'timesheet-captureEnabled','false'],timeout=5,check=False,env=host_environment())
            except (OSError,subprocess.TimeoutExpired): pass
        from .capture import call
        call('org.kde.KWin','/Scripting','org.kde.kwin.Scripting','unloadScript','(b)',
             GLib.Variant('(s)',('timesheet-capture',)))
        shutil.rmtree(kwin)
    return 'Application integration removed. Your timesheet data has been kept in '+str(DATA_DIR)

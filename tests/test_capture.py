"""Compatibility selection, failure safety and upgrade preference regressions."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from timesheet.capture import Capture, KDECapture, WaylandIdle, backend_name, screen_locked
from timesheet.collector import Collector
from timesheet.store import Store


class CaptureTests(unittest.TestCase):
    def test_session_matrix(self):
        for session, desktop, expected in (
            ('wayland','ubuntu:GNOME','gnome'), ('wayland','KDE','kde'),
            ('x11','KDE','x11'), ('x11','XFCE','x11'), ('x11','MATE','x11'),
            ('wayland','sway','sway'), ('wayland','Hyprland','hyprland'),
            ('','GNOME','unsupported'), ('tty','','unsupported')):
            with self.subTest(session=session,desktop=desktop):
                self.assertEqual(backend_name(dict(XDG_SESSION_TYPE=session,XDG_CURRENT_DESKTOP=desktop)),expected)

    def test_never_treat_xwayland_as_full_desktop(self):
        self.assertEqual(backend_name(dict(WAYLAND_DISPLAY='wayland-0',DISPLAY=':0',XDG_SESSION_TYPE='x11',XDG_CURRENT_DESKTOP='other')),'unsupported')

    def test_gnome_protocol_unchanged(self):
        with patch('timesheet.capture.backend_name',return_value='gnome'), patch('timesheet.capture.call',return_value=('Editor','title',42,False)) as call:
            self.assertEqual(Capture().sample(),('Editor','title',42,False))
            self.assertEqual(call.call_args.args[-1],'(ssxb)')

    def test_missing_adapter_does_not_crash_collector(self):
        with patch('timesheet.capture.backend_name',return_value='x11'), patch('timesheet.capture.X11Capture',side_effect=ImportError):
            capture=Capture()
            self.assertIsNone(capture.sample())
            self.assertIsNone(capture.sample())

    def test_lock_unavailable_is_unknown(self):
        with patch('timesheet.capture.call',return_value=None): self.assertIsNone(screen_locked())

    def test_kde_rejects_non_kwin_sender(self):
        adapter=KDECapture.__new__(KDECapture); adapter.focus=None
        invocation=Mock()
        with patch('timesheet.capture.call',return_value=(':1.9',)):
            adapter.receive(None,':1.8',None,None,None,Mock(),invocation)
        self.assertIsNone(adapter.focus)
        invocation.return_dbus_error.assert_called_once()

    def test_kde_accepts_kwin_and_caps_strings(self):
        adapter=KDECapture.__new__(KDECapture); parameters=Mock()
        parameters.unpack.return_value=('Editor','x'*5000)
        with patch('timesheet.capture.call',return_value=(':1.9',)):
            adapter.receive(None,':1.9',None,None,None,parameters,Mock())
        self.assertEqual(adapter.focus[0],'Editor'); self.assertEqual(len(adapter.focus[1]),4096)

    def test_kde_stale_heartbeat_and_missing_lock(self):
        adapter=KDECapture.__new__(KDECapture); adapter.focus=('Editor','title'); adapter.received=1
        adapter.idle=Mock(); adapter.idle.sample.return_value=0
        with patch('timesheet.capture.time.monotonic',return_value=10): self.assertIsNone(adapter.sample())
        adapter.received=10
        with patch('timesheet.capture.time.monotonic',return_value=10), patch('timesheet.capture.screen_locked',return_value=None):
            self.assertEqual(adapter.sample(),('Editor','title',-1,False))

    def test_idle_waits_for_protocol_event_then_tracks_resume(self):
        idle=WaylandIdle(); idle.process=Mock(); idle.process.poll.return_value=None
        with patch('timesheet.capture.os.read',side_effect=BlockingIOError): self.assertEqual(idle.sample(),-1)
        with patch('timesheet.capture.os.read',return_value=b'idle\n'), patch('timesheet.capture.time.monotonic',return_value=10):
            self.assertEqual(idle.sample(),1000)
        with patch('timesheet.capture.os.read',side_effect=BlockingIOError), patch('timesheet.capture.time.monotonic',return_value=14):
            self.assertEqual(idle.sample(),5000)
        with patch('timesheet.capture.os.read',return_value=b'resumed\n'): self.assertEqual(idle.sample(),0)

    def test_idle_command_does_not_load_personal_swayidle_configuration(self):
        idle=WaylandIdle(); process=Mock(); process.stdout.fileno.return_value=99
        with patch('timesheet.capture.subprocess.Popen',return_value=process) as spawn, patch('timesheet.capture.os.set_blocking'), patch('timesheet.capture.os.read',side_effect=BlockingIOError):
            self.assertEqual(idle.sample(),-1)
        self.assertEqual(spawn.call_args.args[0][1:3],['-C','/dev/null'])

    def test_failed_idle_observer_invalidates_previous_sample(self):
        idle=WaylandIdle(); idle.process=Mock(); idle.process.poll.return_value=1; idle.known=True
        self.assertEqual(idle.sample(),-1); self.assertFalse(idle.known)

    def test_missing_idle_stops_timer_and_never_records_active(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'test.sqlite3')
            try:
                task=store.quick_project('Client','Project','Task',6000)
                store.set('capture_enabled','1'); collector=Collector(store)
                collector.step(1000,1000,('Editor','secret',0,False)); store.start_timer(task,1000)
                self.assertEqual(collector.step(1001,1001,('Editor','secret',-1,False)),'degraded')
                self.assertEqual(store.runtime()['state'],'stopped')
                self.assertEqual(store.rows('SELECT state,app,title FROM activity')[-1][:],('unknown','',''))
            finally: store.close()


class UpgradeTests(unittest.TestCase):
    def test_start_clears_old_wayland_environment_when_switching_to_x11(self):
        from timesheet import desktop
        service=Mock(); service.exists.return_value=True
        result=Mock(); result.returncode=0
        with patch.dict(os.environ,{'XDG_SESSION_TYPE':'x11','XDG_CURRENT_DESKTOP':'KDE','DISPLAY':':1'},clear=True), patch.object(desktop,'SERVICE',service), patch.object(desktop,'run_systemd',return_value=result) as systemd:
            desktop.start_collector()
        calls=[call.args for call in systemd.call_args_list]
        self.assertIn('WAYLAND_DISPLAY',calls[0])
        self.assertEqual(calls[0][0],'unset-environment')
        self.assertEqual(calls[1][0],'import-environment')
        self.assertEqual(calls[2],('start','time-sheet-linux.service'))

    def test_reinstall_preserves_pause_titles_autostart_and_reports(self):
        from timesheet import desktop
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); store=Store(root/'data.sqlite3')
            task=store.quick_project('Client','Project','Task',6000)
            entry=store.add_entry(task,1000,4600,'Existing work'); store.approve(entry)
            report=store.create_report(1,0,5000); before=store.html_report(report)
            store.set('setup_complete','1'); store.set('capture_enabled','0'); store.set('capture_titles','1'); store.set('pause_until','9999')
            # Keep a real store open through install so snapshots can be compared.
            with patch.object(desktop,'SHARE',root/'share'), patch.object(desktop,'SERVICE',root/'config/service'), patch.object(desktop,'AUTOSTART',root/'config/autostart/app.desktop'), patch.object(Path,'home',return_value=root), patch.object(desktop,'Store',return_value=store), patch.object(store,'close'), patch.object(desktop,'run_systemd'), patch.object(desktop,'start_collector'), patch.object(desktop,'stop_collector'), patch.object(desktop,'supported_desktop',return_value=True), patch.object(desktop,'gnome_supported',return_value=False), patch.object(desktop,'backend_name',return_value='x11'):
                desktop.install()
                self.assertFalse(desktop.AUTOSTART.exists())
                self.assertEqual(store.get('capture_enabled'),'0')
                self.assertEqual(store.get('pause_until'),'9999')
                self.assertEqual(store.get('capture_titles'),'1')
                self.assertEqual(store.html_report(report),before)
            store.close()

class PackagingTests(unittest.TestCase):
    def test_flatpak_host_companion_preserves_existing_native_launcher(self):
        from timesheet import desktop
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);store=Store(root/'data.sqlite3')
            launcher=root/'share/applications'/ (desktop.APP_ID+'.desktop')
            launcher.parent.mkdir(parents=True);launcher.write_text('existing native launcher')
            try:
                with patch.object(desktop,'SHARE',root/'share'), patch.object(desktop,'SERVICE',root/'config/service'), patch.object(desktop,'AUTOSTART',root/'config/autostart/app.desktop'), patch.object(Path,'home',return_value=root), patch.object(desktop,'Store',return_value=store), patch.object(store,'close'), patch.object(desktop,'run_systemd'), patch.object(desktop,'start_collector'), patch.object(desktop,'stop_collector'), patch.object(desktop,'supported_desktop',return_value=True), patch.object(desktop,'gnome_supported',return_value=False), patch.object(desktop,'backend_name',return_value='x11'), patch.object(desktop,'FLATPAK',False), patch.object(desktop,'APPIMAGE',None):
                    result=desktop.install(host_only=True)
                    self.assertIsNone(result['launcher'])
                    self.assertEqual(launcher.read_text(),'existing native launcher')
                    self.assertIn('run-host',desktop.AUTOSTART.read_text())
            finally:store.close()

    def test_appimage_install_uses_persistent_image_not_mount_path(self):
        from timesheet import desktop
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);store=Store(root/'data.sqlite3'); image=root/'Time Sheet.AppImage'
            try:
                with patch.object(desktop,'SHARE',root/'share'), patch.object(desktop,'SERVICE',root/'config/service'), patch.object(desktop,'AUTOSTART',root/'config/autostart/app.desktop'), patch.object(Path,'home',return_value=root), patch.object(desktop,'Store',return_value=store), patch.object(store,'close'), patch.object(desktop,'run_systemd'), patch.object(desktop,'start_collector'), patch.object(desktop,'stop_collector'), patch.object(desktop,'supported_desktop',return_value=True), patch.object(desktop,'gnome_supported',return_value=False), patch.object(desktop,'backend_name',return_value='x11'), patch.object(desktop,'FLATPAK',False), patch.object(desktop,'APPIMAGE',str(image)), patch.object(desktop,'EXECUTABLE',image):
                    result=desktop.install()
                    self.assertIn(str(image),Path(result['launcher']).read_text())
                    service=desktop.SERVICE.read_text()
                    self.assertIn(str(image),service);self.assertIn('--collector-direct',service)
                    self.assertNotIn('run-timesheet',service)
            finally:store.close()

class WaylandIPCTests(unittest.TestCase):
    def test_sway_and_hyprland_are_selected_without_xwayland(self):
        self.assertEqual(backend_name({'XDG_SESSION_TYPE':'wayland','XDG_CURRENT_DESKTOP':'sway'}),'sway')
        self.assertEqual(backend_name({'XDG_SESSION_TYPE':'wayland','HYPRLAND_INSTANCE_SIGNATURE':'abc'}),'hyprland')

    def test_sway_and_hyprland_focus_and_missing_lock(self):
        import json
        from timesheet.capture import CompositorCapture
        cases=[('sway',{'nodes':[{'focused':True,'app_id':'editor','name':'Private'}]}),('hyprland',{'class':'editor','title':'Private'})]
        for name,payload in cases:
            adapter=CompositorCapture(name);adapter.idle=Mock();adapter.idle.sample.return_value=123
            result=Mock();result.stdout=json.dumps(payload)
            with self.subTest(name=name),patch('timesheet.capture.subprocess.run',return_value=result),patch('timesheet.capture.screen_locked',return_value=None):
                self.assertEqual(adapter.sample(),('editor','Private',-1,False))

    def test_ipc_failure_is_unknown(self):
        import subprocess
        from timesheet.capture import CompositorCapture
        adapter=CompositorCapture('sway')
        with patch('timesheet.capture.subprocess.run',side_effect=subprocess.TimeoutExpired('swaymsg',2)):
            self.assertIsNone(adapter.sample())

    def test_host_uninstall_preserves_native_launcher_and_rejects_other_service(self):
        from timesheet import desktop
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);launcher=root/'share/applications'/(desktop.APP_ID+'.desktop')
            launcher.parent.mkdir(parents=True);launcher.write_text('native launcher')
            service=root/'config/service';service.parent.mkdir(parents=True);service.write_text('unrelated service')
            with patch.object(desktop,'SERVICE',service),patch.object(desktop,'SHARE',root/'share'),patch.object(desktop,'FLATPAK',False),patch.object(desktop,'stop_collector'),patch.object(desktop,'set_autostart'),patch.object(desktop,'run_systemd'),patch.object(desktop,'shell_settings',return_value=None):
                with self.assertRaises(ValueError):desktop.uninstall(host_only=True)
                self.assertTrue(service.exists())
                service.write_text('Description=Time Sheet Linux host companion\nWorkingDirectory='+str(desktop.ROOT))
                desktop.uninstall(host_only=True)
                self.assertEqual(launcher.read_text(),'native launcher')
                self.assertFalse(service.exists())

    def test_flatpak_restore_requires_host_collector_to_be_stopped(self):
        import fcntl
        from timesheet import desktop
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.object(desktop,'DATA_DIR',root),patch.object(desktop,'FLATPAK',True):
                with open(root/'collector.lock','a+') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    with self.assertRaisesRegex(ValueError,'Stop the host collector'):
                        desktop.stop_collector()
                desktop.stop_collector()

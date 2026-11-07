"""Session-specific capture. Missing evidence is unknown, never active work."""
from __future__ import annotations
import importlib.util
import os
import shutil
import subprocess
import time
from gi.repository import Gio, GLib


def backend_name(env=None):
    env = os.environ if env is None else env
    # Never use Xwayland to represent the whole Wayland desktop.
    session = env.get('XDG_SESSION_TYPE', '').lower()
    desktop = env.get('XDG_CURRENT_DESKTOP', '').upper().split(':')
    if session == 'wayland' or env.get('WAYLAND_DISPLAY'):
        if 'GNOME' in desktop: return 'gnome'
        if 'KDE' in desktop: return 'kde'
        return 'unsupported'
    if session == 'x11': return 'x11'
    return 'unsupported'


def call(service, path, interface, method, signature, args=None):
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        return bus.call_sync(service, path, interface, method, args,
            GLib.VariantType.new(signature), Gio.DBusCallFlags.NONE, 500, None).unpack()
    except GLib.Error:
        return None


def screen_locked():
    for service, path in (
        ('org.freedesktop.ScreenSaver', '/ScreenSaver'),
        ('org.gnome.ScreenSaver', '/org/gnome/ScreenSaver'),
        ('org.cinnamon.ScreenSaver', '/org/cinnamon/ScreenSaver'),
        ('org.mate.ScreenSaver', '/org/mate/ScreenSaver')):
        result = call(service, path, service, 'GetActive', '(b)')
        if result is not None: return result[0]
    return None


def dependencies(name=None):
    name = name or backend_name()
    if name == 'x11' and importlib.util.find_spec('Xlib') is None:
        return ['python3-xlib (python-xlib on Arch)']
    if name == 'kde':
        return [tool for tool in ('swayidle','kwriteconfig6') if not shutil.which(tool)]
    return []


class WaylandIdle:
    """Observe compositor idle events without reading input or user swayidle config."""
    def __init__(self):
        self.process = None
        self.since = None
        self.known = False
        self.buffer = b''
        self.retry_at = 0

    def sample(self):
        now = time.monotonic()
        if self.process is not None and self.process.poll() is not None:
            self.close()
            self.retry_at = now + 10
        if self.process is None:
            if now < self.retry_at: return -1
            try:
                self.process = subprocess.Popen(
                    ['swayidle', '-C', '/dev/null', '-w', 'timeout', '1',
                     'printf "idle\\n"', 'resume', 'printf "resumed\\n"'],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                os.set_blocking(self.process.stdout.fileno(), False)
            except OSError:
                self.retry_at = now + 10
                return -1
        try:
            data = os.read(self.process.stdout.fileno(), 4096)
            if not data:
                self.close(); self.retry_at = now + 10
                return -1
            self.buffer += data
        except BlockingIOError:
            pass
        while b'\n' in self.buffer:
            event, self.buffer = self.buffer.split(b'\n', 1)
            if event == b'idle': self.since = now - 1; self.known = True
            elif event == b'resumed': self.since = None; self.known = True
        if not self.known: return -1
        return max(0, int((now - self.since) * 1000)) if self.since is not None else 0

    def close(self):
        if self.process:
            self.process.terminate()
            try: self.process.wait(timeout=2)
            except subprocess.TimeoutExpired: self.process.kill(); self.process.wait()
            self.process.stdout.close()
        self.process = None
        self.since = None
        self.known = False
        self.buffer = b''


class KDECapture:
    """Receive fresh KWin samples; only KWin's session-bus owner may submit them."""
    XML = '''<node><interface name="org.local.TimeSheetLinux.Capture">
      <method name="Focus"><arg type="s" direction="in"/><arg type="s" direction="in"/></method>
    </interface></node>'''

    def __init__(self):
        self.focus = None
        self.received = 0
        self.idle = WaylandIdle()
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        info = Gio.DBusNodeInfo.new_for_xml(self.XML).interfaces[0]
        self.registration = self.bus.register_object('/org/local/TimeSheetLinux/Capture', info, self.receive, None, None)
        self.owner = Gio.bus_own_name_on_connection(self.bus, 'org.local.TimeSheetLinux.Capture', Gio.BusNameOwnerFlags.NONE, None, None)

    def receive(self, connection, sender, path, interface, method, parameters, invocation):
        owner = call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                     'org.freedesktop.DBus', 'GetNameOwner', '(s)', GLib.Variant('(s)', ('org.kde.KWin',)))
        if not owner or sender != owner[0]:
            invocation.return_dbus_error('org.freedesktop.DBus.Error.AccessDenied', 'Only KWin can submit focus')
            return
        self.focus = tuple(s[:4096] for s in parameters.unpack())
        self.received = time.monotonic()
        invocation.return_value(GLib.Variant('()', ()))

    def sample(self):
        context = GLib.MainContext.default()
        for _ in range(100):
            if not context.pending(): break
            context.iteration(False)
        idle = self.idle.sample()
        if self.focus is None or time.monotonic() - self.received > 3: return None
        locked = screen_locked()
        return (*self.focus, idle if locked is not None else -1, bool(locked))

    def close(self):
        self.idle.close()
        self.bus.unregister_object(self.registration)
        Gio.bus_unown_name(self.owner)


class X11Capture:
    def __init__(self):
        from Xlib import display
        from Xlib.protocol import rq
        self.display = display.Display()
        self.root = self.display.screen().root
        # QueryInfo wire layout is standard XScreenSaver 1.0. Older distro
        # python-xlib versions (e.g. 0.29) lack Xlib.ext.screensaver entirely.
        class IdleQuery(rq.ReplyRequest):
            _request = rq.Struct(rq.Card8('opcode'), rq.Opcode(1),
                                 rq.RequestLength(), rq.Card32('drawable'))
            _reply = rq.Struct(rq.ReplyCode(), rq.Pad(1),
                               rq.Card16('sequence_number'), rq.ReplyLength(),
                               rq.Pad(8), rq.Card32('idle'), rq.Pad(12))
        try:
            extension = self.display.query_extension('MIT-SCREEN-SAVER')
            if extension is None or not extension.present:
                raise OSError('XScreenSaver is unavailable')
            self.query_idle = lambda: IdleQuery(display=self.display.display,
                opcode=extension.major_opcode, drawable=self.root.id).idle
        except Exception:
            self.display.close()
            raise

    def sample(self):
        from Xlib import X, error
        try:
            idle = int(self.query_idle())
            locked = screen_locked()
            prop = self.root.get_full_property(self.display.intern_atom('_NET_ACTIVE_WINDOW'), X.AnyPropertyType)
            if prop is None or not len(prop.value) or not prop.value[0]:
                return ('', '', idle if locked is not None else -1, bool(locked))
            win = self.display.create_resource_object('window', int(prop.value[0]))
            classes = win.get_wm_class() or ('', '')
            title = win.get_full_property(self.display.intern_atom('_NET_WM_NAME'), self.display.intern_atom('UTF8_STRING'))
            text = title.value.decode('utf-8', 'replace') if title is not None else (win.get_wm_name() or '')
            return (str(classes[-1])[:4096], str(text)[:4096], idle if locked is not None else -1, bool(locked))
        except (error.XError, AttributeError, ValueError):
            return None

    def close(self):
        self.display.close()


class Capture:
    def __init__(self):
        self.name = backend_name()
        self.adapter = None
        self.retry_at = 0

    def sample(self):
        if self.name == 'gnome':
            return call('org.local.TimeSheetCapture', '/org/local/TimeSheetCapture',
                        'org.local.TimeSheetCapture', 'GetState', '(ssxb)')
        if self.name not in ('kde', 'x11'): return None
        try:
            if self.adapter is None:
                if time.monotonic() < self.retry_at: return None
                self.adapter = KDECapture() if self.name == 'kde' else X11Capture()
            return self.adapter.sample()
        except Exception:
            # Optional adapters must never stop durable collection or invent focus.
            # Xlib raises protocol/connection exceptions outside OSError.
            self.close()
            self.retry_at = time.monotonic() + 10
            return None

    def close(self):
        if self.adapter:
            try: self.adapter.close()
            except Exception: pass
        self.adapter = None

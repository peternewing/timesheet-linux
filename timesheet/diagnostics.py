"""Read-only compatibility diagnostics; no paths, titles or activity data."""
import json
import os
import platform
from . import __version__
from .capture import backend_name, dependencies


def diagnose():
    result = dict(version=__version__, python=platform.python_version(),
                  session=os.environ.get('XDG_SESSION_TYPE','unknown'),
                  desktop=os.environ.get('XDG_CURRENT_DESKTOP','unknown'),
                  backend=backend_name(), missing_dependencies=dependencies())
    try:
        import gi
        gi.require_version('Gtk','4.0'); gi.require_version('Adw','1')
        from gi.repository import Gtk, Adw
        result['gtk'] = f'{Gtk.get_major_version()}.{Gtk.get_minor_version()}'
        result['libadwaita'] = f'{Adw.get_major_version()}.{Adw.get_minor_version()}'
        result['ui_supported'] = (Adw.get_major_version(),Adw.get_minor_version()) >= (1,5)
    except (ImportError,ValueError):
        result['ui_supported'] = False
    return result

if __name__ == '__main__':
    print(json.dumps(diagnose(),indent=2))

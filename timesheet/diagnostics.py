"""Read-only compatibility diagnostics; no paths, titles or activity data."""
import json
import importlib.util
import os
import platform
import sqlite3
from pathlib import Path
from urllib.parse import quote
from . import __version__
from .capture import backend_name, dependencies


def diagnose():
    result = dict(version=__version__, python=platform.python_version(),
                  session=os.environ.get('XDG_SESSION_TYPE','unknown'),
                  desktop=os.environ.get('XDG_CURRENT_DESKTOP','unknown'),
                  backend=backend_name(), missing_dependencies=dependencies(),
                  pdf_available=importlib.util.find_spec('reportlab') is not None)
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


def database_health(path,now=None):
    """Explicit read-only health check. Never returns names, titles, keys or paths."""
    import time
    now=int(time.time() if now is None else now);connection=None
    try:
        connection=sqlite3.connect('file:'+quote(str(Path(path).resolve()))+'?mode=ro',uri=True,timeout=2)
        connection.row_factory=sqlite3.Row;connection.execute('PRAGMA query_only=ON')
        tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required={'settings','runtime','activity','entries'}
        if not required<=tables:return dict(status='unsupported schema',database_read_only=True)
        values=dict(connection.execute("SELECT key,value FROM settings WHERE key IN ('capture_enabled','ai_policy','ai_worker_seen','local_app_types')"))
        runtime=connection.execute('SELECT collector_seen,capture_status FROM runtime WHERE id=1').fetchone()
        check=connection.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        seen=runtime['collector_seen'] if runtime else None
        capture_age=max(0,now-int(seen)) if seen is not None and int(seen)<=now+5 else None
        unknown=connection.execute("SELECT COUNT(*) FROM ai_usage WHERE input_tokens IS NULL AND outcome!='acknowledged unknown'").fetchone()[0] if 'ai_usage' in tables else 0
        from .decision_policy import settings
        config=settings(values.get('ai_policy','{}'))
        recording=values.get('capture_enabled','0')=='1'
        stale=recording and (capture_age is None or capture_age>30)
        return dict(status='needs attention' if not check or stale or unknown else 'ok',database_read_only=True,
            integrity_ok=check,recording_enabled=recording,collector_seen_age_seconds=capture_age,
            capture_state=runtime['capture_status'] if runtime and runtime['capture_status'] in ('active','paused','stopped','error','degraded','setup_required') else 'unknown',
            unknown_usage_records=unknown,ai_mode=config['mode'],local_types_enabled=values.get('local_app_types','0')=='1',
            screen_spaces_available='screen_spaces' in tables,activity_rows=connection.execute('SELECT COUNT(*) FROM activity').fetchone()[0],
            note='Aggregate local health only; no inference request, key lookup or database migration performed.')
    except (OSError,sqlite3.Error,ValueError,TypeError,OverflowError):return dict(status='unavailable',database_read_only=True)
    finally:
        if connection:connection.close()

if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--database',type=Path)
    args=parser.parse_args();result=diagnose()
    if args.database:result['local_database']=database_health(args.database)
    print(json.dumps(result,indent=2))

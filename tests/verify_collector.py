"""Run under dbus-run-session to test the real collector with a fake desktop source."""
import json,os,signal,subprocess,sys,tempfile,time
from pathlib import Path

def wait_for(condition,timeout=12):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        value=condition()
        if value: return value
        time.sleep(.1)
    raise AssertionError('Timed out waiting for collector state')

with tempfile.TemporaryDirectory() as directory:
    os.environ['XDG_DATA_HOME']=directory
    state=Path(directory)/'state.json'; os.environ['TEST_CAPTURE_STATE']=str(state)
    state.write_text(json.dumps(dict(app='Editor',title='sensitive title',idle=0,locked=False)))
    from timesheet.store import Store
    store=Store(); c=store.add_client('Client','GBP',6000); p=store.add_project(c,'Project'); task=store.add_task(p,'Task')
    store.set('capture_enabled','1'); store.set('idle_seconds','2'); store.set('capture_titles','0')
    service=subprocess.Popen([sys.executable,'tests/fake_capture.py'],stdout=subprocess.PIPE,text=True)
    assert service.stdout.readline().strip()=='ready'
    daemon=subprocess.Popen([sys.executable,'-m','timesheet.collector'])
    try:
        wait_for(lambda:store.runtime()['capture_status']=='active')
        store.start_timer(task)
        time.sleep(5)
        state.write_text(json.dumps(dict(app='Editor',title='sensitive title',idle=3000,locked=False)))
        wait_for(lambda:store.runtime()['state']=='stopped')
        daemon.terminate(); daemon.wait(timeout=8)
        entries=store.entries(0,4102444800)
        assert len(entries)==1 and entries[0]['end']-entries[0]['start']>=1, 'idle boundary did not stop timer correctly'
        activity=store.rows('SELECT * FROM activity')
        assert activity and all('sensitive title' not in r['title'] for r in activity), 'disabled title storage leaked'
        assert any(r['app']=='Editor' for r in activity), 'active application was not captured'
        assert any(r['state']=='away' for r in activity), 'away state was not captured'
        away_start=min(r['start'] for r in activity if r['state']=='away')
        assert all(r['end']<=away_start for r in activity if r['state']=='active'), 'idle time left as active'
        print('PASS: D-Bus capture, idle stop and title privacy')
    finally:
        if daemon.poll() is None: daemon.terminate(); daemon.wait(timeout=8)
        service.terminate(); service.wait(timeout=8); store.close()

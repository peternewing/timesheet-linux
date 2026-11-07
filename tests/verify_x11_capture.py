"""Real X server/property/idle test with synthetic EWMH window and mocked lock.
Requires Xvfb and python-xlib; does not certify a real desktop's locker/window manager.
"""
import os
import subprocess
from unittest.mock import patch

read_fd,write_fd=os.pipe()
server=subprocess.Popen(['Xvfb','-displayfd',str(write_fd),'-screen','0','800x600x24','-nolisten','tcp'],pass_fds=(write_fd,),stderr=subprocess.DEVNULL)
os.close(write_fd)
display=None; adapter=None
try:
    import select
    if not select.select([read_fd],[],[],10)[0]: raise RuntimeError('Xvfb did not start')
    number=os.read(read_fd,100).decode().strip()
    assert number.isdigit(), number
    os.environ['DISPLAY']=':'+number
    from Xlib import X, Xatom, display as xdisplay
    from timesheet.capture import X11Capture
    display=xdisplay.Display(); root=display.screen().root
    window=root.create_window(0,0,100,100,0,display.screen().root_depth)
    window.set_wm_class('fixture','FixtureEditor')
    window.change_property(display.intern_atom('_NET_WM_NAME'),display.intern_atom('UTF8_STRING'),8,'Synthetic résumé'.encode())
    window.map()
    root.change_property(display.intern_atom('_NET_ACTIVE_WINDOW'),Xatom.WINDOW,32,[window.id])
    display.sync()
    adapter=X11Capture()
    with patch('timesheet.capture.screen_locked',return_value=False):
        state=adapter.sample()
        assert state[:2]==('FixtureEditor','Synthetic résumé'),state
        assert state[2]>=0 and state[3] is False,state
    with patch('timesheet.capture.screen_locked',return_value=True): assert adapter.sample()[3] is True
    with patch('timesheet.capture.screen_locked',return_value=None): assert adapter.sample()[2]==-1
    window.destroy(); display.sync()
    assert adapter.sample() is None, 'Destroyed window produced stale focus'
    print('PASS: real X11 properties, Unicode title, idle counter, lock failure and destroyed window')
finally:
    if adapter: adapter.close()
    if display: display.close()
    os.close(read_fd)
    server.terminate(); server.wait(timeout=5)

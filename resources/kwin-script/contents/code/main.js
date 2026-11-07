// Plasma 6. A heartbeat prevents stale windows from becoming recorded work.
function sample() {
    const win = workspace.activeWindow;
    callDBus('org.local.TimeSheetLinux.Capture', '/org/local/TimeSheetLinux/Capture',
        'org.local.TimeSheetLinux.Capture', 'Focus',
        win ? String(win.desktopFileName || win.resourceClass || '') : '',
        win ? String(win.caption || '') : '');
}
const timer = new QTimer();
timer.interval = 1000;
timer.timeout.connect(sample);
timer.start();
workspace.windowActivated.connect(sample);
sample();

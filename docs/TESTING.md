# Testing and release evidence

The current automated suite covers interval overlap, concurrent writers, exact billing amounts, historical rates, stale and duplicate billing, safe CSV/HTML, backup consistency, daylight-saving input rejection, automatic rule idempotence, rule conflicts and future-only application, partial assignment, multi-step undo, split/merge, atomic bulk approval, stale edits, durable activity, idle reclassification, sleep gaps and crash checkpoints.

```sh
/usr/bin/python3 -m unittest discover -s tests -v
```

## Desktop integration

Two integration paths are intentionally separate:

- `tests/verify_collector.py` uses a private test D-Bus source to exercise the real collector, idle stops and title privacy.
- `tests/verify_gnome.py` starts an isolated headless GNOME 50 session with temporary settings, loads the real extension, and creates a real Wayland test window. It checks the foreground application/title and idle/lock interface without logging out the real desktop.

Both use `TIMESHEET_TESTING=1` and should be run through `dbus-run-session` as documented in CONTRIBUTING.md. Headless GNOME can print shutdown warnings from its test-only services; inspect the explicit PASS lines and exit code.

A disposable systemd service was used to verify restart after a process crash. The live tracker was not deliberately killed. The GTK views were opened on Ubuntu GNOME with sample data; documentation screenshots are rendered directly from the app window using synthetic records, not captured from a user's working desktop.

## Still requiring broader validation

- A sustained real working day, actual suspend/resume and screen locking on each supported hardware configuration.
- Storage exhaustion and full recovery, power-loss behavior, large retained datasets and long-running CPU/memory measurements.
- Screen-reader workflows, high text scaling and additional Linux desktop environments.

Do not equate passing unit tests with universal desktop compatibility. The UI and README distinguish pending capture setup, paused recording and actual capture availability.

## 0.3.0 compatibility candidate

The candidate adds adapter selection, KDE sender authentication/heartbeat expiry,
Wayland idle failures, unknown lock behavior, and upgrade preference/report snapshot
regressions. Run the full suite and protocol checks:

```sh
/usr/bin/python3 -m unittest discover -s tests -v
XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=GNOME PYTHONPATH=. dbus-run-session -- /usr/bin/python3 tests/verify_collector.py
PYTHONPATH=. dbus-run-session -- /usr/bin/python3 tests/verify_kde_capture.py
```

The KDE protocol test uses a simulated compositor on a real private D-Bus session.
It does not test the KWin JavaScript runtime or swayidle against an actual compositor.
CI runs core/protocol tests on Ubuntu 22.04 and 24.04; those jobs do not certify
that their GNOME Shell versions support the capture extension.
See [desktop release gates](LINUX_COMPATIBILITY.md#acceptance-gate-before-promoting-030).

### Local candidate evidence (2026-11-07)

- 54 unit/regression tests passed on system Python 3.14.
- Real GNOME 50 headless Wayland helper loaded; idle/lock and a real foreground
  fixture window were detected successfully.
- Private-bus GNOME collector test passed (idle cutoff and disabled title storage).
- Private-bus KDE bridge test passed (simulated KWin sender, delivery and expiry).
- All seven GTK pages rendered and their navigation handlers worked using synthetic
  data (`PYTHONPATH=. /usr/bin/python3 tests/verify_pages.py`).
- The physical-mouse `verify_ui.py` test failed at Calendar navigation on both the
  unchanged 0.2.0 baseline and candidate in this environment. This is unresolved;
  the handler/render check does not replace a physical-input acceptance test.
- Real X11 virtual-server test passed: EWMH focus, Unicode title, XScreenSaver idle,
  unknown lock and destroyed-window handling (`tests/verify_x11_capture.py`).
  The lock service is mocked; real Plasma 6/full X11 desktop acceptance remains pending.

The initial Ubuntu 22.04 CI run exposed missing `Xlib.ext.screensaver` in its
python-xlib 0.29 package. The adapter now reads the standard XScreenSaver QueryInfo
wire reply directly, so the optional high-level extension module is unnecessary.

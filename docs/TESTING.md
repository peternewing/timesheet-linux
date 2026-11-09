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

- 66 unit/regression tests passed on system Python 3.14.
- Real GNOME 50 headless Wayland helper loaded; idle/lock and a real foreground
  fixture window were detected successfully.
- Private-bus GNOME collector test passed (idle cutoff and disabled title storage).
- Private-bus KDE bridge test passed (simulated KWin sender, delivery and expiry).
- All seven GTK pages rendered and their navigation handlers worked using synthetic
  data (`PYTHONPATH=. /usr/bin/python3 tests/verify_pages.py`).
- The physical-mouse test originally failed at 200% scaling. Coordinate conversion
  was corrected; all 53 mouse/keyboard workflows now pass at 200% in isolated X11.
- Real X11 virtual-server test passed: EWMH focus, Unicode title, XScreenSaver idle,
  unknown lock and destroyed-window handling (`tests/verify_x11_capture.py`).
  The lock service is mocked; real Plasma 6/full X11 desktop acceptance remains pending.

The initial Ubuntu 22.04 CI run exposed missing `Xlib.ext.screensaver` in its
python-xlib 0.29 package. The adapter now reads the standard XScreenSaver QueryInfo
wire reply directly, so the optional high-level extension module is unnecessary.

## Follow-up validation

- Real isolated KWin 6.6 Wayland: installed script delivered a real GTK foreground
  window, the real swayidle observer advanced, and window/compositor exit cleared
  focus. Hardware lock, suspend and full sign-in are not covered by headless KWin.
- Mouse coordinate conversion was reproduced failing at 200% and corrected; the
  isolated X11 mouse/keyboard workflow runs at 100% and 200% scale.
- 66 automated tests include immutable PDF/invoice snapshot amounts and billing
  state, multi-page output, currency validation and packaging paths. PDF samples
  were rendered and visually inspected; ReportLab and DejaVu fonts are required.
- AppImage GUI/diagnostics were run with disposable data on Ubuntu 26.04; the
  automated distribution build targets Ubuntu 24.04. Flatpak GUI and PDF exporter
  were run in a sandbox without the unavailable document portal. The host companion
  remains required for background capture; portal-based Save must still be tested
  on a full desktop with the document portal available.

- Real headless Sway 1.11 passed foreground IPC and idle detection; a synthetic
  screen-lock service verified lock-state propagation. Real Hyprland launch was
  attempted, but its GPU allocator could not access the available render device;
  its adapter has unit coverage but not real-compositor acceptance.

## 0.4.0-rc2 daily review

See [the usability review](USABILITY_REVIEW.md) for the complete workflow audit, 128 core tests, 53 scaled mouse/keyboard checks and the new 19-check daily-review scenario. Regression tests cover selected-period rule application, midnight boundaries, conflicting future rules and bulk allocation parity with a running timer.

## 0.5 automation candidate

Read [the accepted roadmap](AUTOMATION_ROADMAP.md), [both-pass review and scores](AUTOMATION_REVIEW_0.5.md), and [user guide](AUTOMATION_GUIDE.md). Current deterministic suite: 184 tests. Additional isolated checks:

```sh
PYTHONPATH=. /usr/bin/python3 tests/verify_worker_process.py
/usr/bin/python3 -m timesheet.evaluate tests/fixtures/jev_live_heldout_recorded.json
GDK_SCALE=2 GDK_BACKEND=x11 GSK_RENDERER=cairo GSETTINGS_BACKEND=memory PYTHONPATH=. xvfb-run -a -s '-screen 0 2880x2000x24' /usr/bin/python3 tests/verify_automation_ui.py
```

The recorded fixture is synthetic live evidence, replayed offline. It does not establish real-work accuracy. Never run tests against the actual user's database or silently enable a background policy while testing an upgrade.


## 0.6 simple default

The suite now has 208 unit/regression tests. `tests/verify_simple_ui.py` runs
30 checks against the default product, including actual mouse clicks through
all four setup steps with a fake saved key and no typing. Run at normal and
200% scale. Existing advanced tests explicitly select that retained interface.
`tests/preview_ui.py` renders the simple documentation screenshots from synthetic
records with no real key/provider call. See SIMPLICITY_REVIEW_0.6.md for evidence.

```sh
/usr/bin/python3 -m timesheet.evaluate tests/fixtures/jev_simple_heldout_recorded.json
GDK_SCALE=2 GDK_BACKEND=x11 GSK_RENDERER=cairo GSETTINGS_BACKEND=memory PYTHONPATH=. xvfb-run -a -s '-screen 0 2880x2000x24' /usr/bin/python3 tests/verify_simple_ui.py
```


## 0.6.1 daily choices and cards

227 unit tests and 41 default UI checks (normal/200%) cover the requested grouped
decisions, live counters, rankings and clickable card details. Retained advanced
workflows are tested separately. See DAILY_REVIEW_0.6.1.md. Synthetic test data
only; no real account inference or activity transmission is needed for this change.

## Personal/work development iteration — 9 November 2026

Read the [category reassessment](PERSONAL_WORK_REASSESSMENT_2026-11-09.md) and
[actual work log](PERSONAL_WORK_ITERATION.md). The new tests use disposable data;
never substitute the real activity database. Core tests include local metadata
collisions/precedence, schedule history/timezone/DST, private interval unions,
finite corrections/Undo, read-only unlabelled evaluation templates, stale request
versions and SQLite page-quota rollback/recovery. A quota test is not physical
disk-exhaustion acceptance.

```sh
/usr/bin/python3 -m unittest discover -s tests -v
PYTHONPATH=. /usr/bin/python3 tests/benchmark_screen_time.py --observations 200000 --repeats 10
PYTHONPATH=. /usr/bin/python3 tests/compare_screen_performance.py
PYTHONPATH=. /usr/bin/python3 tests/soak_screen_time.py --seconds 7200 --exercise-schedules --output /tmp/screen-time-soak.json
```

The comparison replays the prior hourly aggregation against the same fixed-time
fixture without editing product files. The soak uses synthetic focus input,
separate SQLite connections and a fake provider, including idle/lock/disconnect,
space/schedule changes and cross-day unknown-usage acknowledgement. It records
source hashes loaded at start. Elapsed synthetic process time is not physical
capture time or a universal CPU/RSS guarantee. CI runs a bounded 60-second smoke
and smaller benchmark; configured CI is not evidence of an executed remote run.

`tests/preview_screen_time.py` generates only synthetic development screenshots
with key/provider access disabled. New insight actions are exercised by
`tests/verify_simple_ui.py` at normal and 200% scale, including past-hour correction,
current-space preservation, schedule enable/override/resume and Undo. Native
controls and labels do not replace human Orca and keyboard-only acceptance.

The separately authorised 20-request public TypeSafe run is saved in
`evidence/personal-work-live-synthetic-2026-11-09.json`. Its request allowance is
exhausted. Replay the saved answers offline; do not silently rerun live requests.
The local template exporter intentionally creates **unlabelled** cases, which paid
and offline evaluation reject until independently confirmed. No real user data
was exported to create the development validation artifacts.

The native async scenario also checks 20 rapid window reopenings and actual Python
wrapper collection. A sustained test exposed a rendered control/callback cycle;
closing now releases controls, refresh sources and keyboard-controller ownership.
Run the resource/reopen check separately from hardware acceptance:

```sh
GDK_SCALE=2 GDK_BACKEND=x11 GSK_RENDERER=cairo GSETTINGS_BACKEND=memory PYTHONPATH=. xvfb-run -a -s '-screen 0 2880x2000x24' /usr/bin/python3 tests/soak_screen_ui.py --seconds 1800 --output /tmp/screen-ui-soak.json
```

This records CPU, peak RSS, heartbeat delay and weak references after close; it
uses synthetic records and disables key/provider access. Superseded reproduction
runs must not be counted as completed passing durations. Weekly percentage changes
are suppressed when either recorded week includes unknown/paused intervals; any
remaining comparison explicitly describes recorded use, not complete actual use.

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

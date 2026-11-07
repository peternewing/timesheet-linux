# Contributing

Use `/usr/bin/python3` and the Linux distribution's PyGObject/GTK packages. The app deliberately avoids collecting keystrokes, screenshots, clipboard content or browsing history.

Run the core tests before submitting a change:

```sh
/usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 -m compileall -q timesheet
```

For a private D-Bus collector test:

```sh
TIMESHEET_TESTING=1 PYTHONPATH=. dbus-run-session -- /usr/bin/python3 tests/verify_collector.py
```

On a GNOME 50 test machine, an optional headless test exercises the actual Shell extension:

```sh
TIMESHEET_TESTING=1 PYTHONPATH=. dbus-run-session -- /usr/bin/python3 tests/verify_gnome.py
```

This starts a separate headless compositor with temporary configuration; do not run it against the production desktop's session bus. It does not need to log the user out. Normal core tests use temporary SQLite databases.

Maintain these invariants:

- Allocated task entries never overlap; adjacent intervals use `[start, end)` boundaries.
- Automatically assigned work stays draft and cannot be approved before idle boundaries settle.
- Manual edits and approval are protected from later automatic reprocessing.
- Reports preserve their rate and amount snapshots; stale revisions cannot be billed.
- Missing observations produce visible gaps, never invented work.
- Privacy filters apply before data is stored. Logs must not contain titles or URLs.

Describe the desktop and GNOME versions used for integration changes. A mocked D-Bus test is not proof of compatibility with a different desktop.

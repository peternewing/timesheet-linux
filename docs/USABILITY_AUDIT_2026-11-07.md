# Desktop usability and reliability audit — 7 November 2026

This audit opened the real GTK app, inspected rendered screens and exercised
mouse/keyboard workflows against disposable sample data. It did not edit the
user's timesheets. The release improves everyday use and fixes reproducible
failures; it is not a certification that every possible defect has been found.

## Scorecard

Scores are engineering assessments out of 10, not measured user-study results.
The initial assessment includes the previously fixed sidebar-text bug. A 10
would require broader user, assistive-technology and long-duration validation
than this session can establish.

| Category | Before | After | Evidence / remaining limit |
|---|---:|---:|---|
| Navigation and button behavior | 6 | 9 | Real clicks on all seven sidebar labels; page shortcuts and tooltips. |
| Live timer feedback | 4 | 9 | HH:MM:SS display, second-by-second updates, persistent header timer, real elapsed-time and stop/save checks. |
| First-run guidance | 5 | 9 | Prominent first-project guidance, Help, and continuation into the original Add time action. |
| Forms and error recovery | 6 | 9 | Grouped labels, accessible names, larger scrollable dialogs, Enter/Escape, visible validation without losing input. |
| Review and bulk actions | 5 | 9 | Selection counts, select/clear, disabled empty actions, draft-only approval in mixed selections. |
| Calendar and activity assignment | 6 | 9 | Only eligible activity is selectable; personal and partially assigned activity no longer offers invalid actions. |
| Reporting and billing | 6 | 9 | Archived reports remain accessible; nested billing dialogs work and stale previews close after billing. |
| Accessibility and keyboard use | 5 | 8 | Accessible field/navigation names, clear focusable controls, tested Enter/Escape. Full screen-reader evaluation remains. |
| Reliability and regression coverage | 7 | 9 | 39 core tests, 38 GUI checks, private D-Bus collector integration and actual GNOME extension test passed. |
| Data integrity and recovery | 8 | 9 | Existing accounting/backup invariants preserved; malformed report values rejected before restore, extreme numbers rejected, interrupted-tracking notices surfaced. |
| Privacy | 8 | 8 | Title privacy integration test passed; sample-only audit. Local files and backups remain unencrypted, as documented. |
| Performance | 8 | 8 | 10,000 activity records and 1,000 entries: day summary 47 ms, history search 2 ms, activity read 24 ms in this run. No multi-month UI soak test. |
| Linux compatibility and maintenance | 6 | 7 | Ubuntu 26.04.1 / GNOME 50.1 verified; repeatable UI harness documented. Automatic capture remains GNOME 50 Wayland only. |

## Changes

- Running task time now uses HH:MM:SS, including seconds after an hour. The display
  checks elapsed wall time every 200 ms and only updates changed labels, avoiding
  accumulated tick drift. A live header timer stays visible on other pages and
  opens Today; stopping saves draft time and clears the running indicator.
- Sidebar text click behavior retained and tested using actual mouse events.
- Page names exposed to accessibility tools; Ctrl+1–7 page shortcuts and tooltips.
- Help explains project → activity → review → report, draft/approved/billed states,
  and keyboard shortcuts.
- First-project guidance appears at the top of Today; Add time and assignment
  continue after project creation instead of dropping the original action.
- Labels stay attached to fields in horizontal layouts. Forms have accessible
  names, more vertical room, default Enter saving and Escape cancellation.
- Errors appear over the active form. Duplicate names and oversized numbers have
  actionable messages; rejected saves preserve user input.
- Action rows wrap, including entry actions and the main review toolbar.
- Action refreshes wait until the input event finishes and clear obsolete focus
  before rebuilding rows; this fixes a GTK warning when stopping a timer.
- History shows selection counts, select-visible/clear controls and appropriate
  disabled states. Bulk approval skips already approved selected entries.
- Search prompts match task history versus captured desktop usage.
- Overnight time includes the end date. Billable entries show their rate or
  explain that a rate is missing before approval.
- Calendar selection excludes personal/live/already assigned activity. Personal
  marking is not offered for a partly allocated group; year changes refresh marks.
- Add project preselects the client whose button was clicked. Projects and tasks
  remain editable under archived parents.
- Quick setup rejects archived clients, duplicate projects and conflicting
  existing-client billing settings instead of silently ignoring input.
- Saved reports and approved work remain accessible for archived clients. Report
  guidance explains approval and exporting versus billing.
- Billing/correction forms and export choosers attach to the report preview;
  successful billing/correction closes its stale preview.
- Interrupted-tracking notices are visible and dismissible on Today.
- Duplicate IDs cannot accidentally merge one entry with itself.
- Backup validation checks report value types, amounts, timestamps and dates,
  preventing malformed snapshots from reaching report rendering/export.
- Preview screenshots use a separate app identity, so an already open production
  window cannot absorb the test launch.

## Verification

Environment: Ubuntu 26.04.1 LTS, GNOME Shell 50.1, GTK 4.22.4,
libadwaita 1.9.1, system Python/PyGObject.

- `python3 -m unittest discover -s tests -v`: **39 passed**.
- Python compilation: passed.
- `tests/verify_ui.py`: **38 checks passed**, including seven label hit targets,
  Help, first-run continuation, Enter save, Escape cancel, invalid overlapping
  entry, selection state, mixed draft/approved review, merge/undo, billing,
  archived report/project/task access, rule creation, activity assignment, second-by-second
  elapsed time, hour/day formatting, persistent header timing and stop/save behavior.
- Final GUI run also passed with `G_DEBUG=fatal-criticals`, making GTK critical
  warnings fatal test failures.
- GUI screenshots inspected at normal size and a 900 × 650 requested window size.
  Screenshots show only synthetic data and live under `/tmp/timesheet-ui-audit`.
- `tests/verify_collector.py`: passed with a private D-Bus, temporary database,
  simulated foreground source, actual collector, idle stopping and title privacy.
- `tests/verify_gnome.py`: passed in a separate headless GNOME session; the actual
  extension returned lock/idle data and detected a real foreground GTK window.
- Data benchmark: 10,000 activity records / 1,000 task entries. Times above are
  single-run observations, not formal performance guarantees.

The shared GNOME Wayland desktop blocked XTest synthetic clicks. Mouse tests
therefore used a private Xvfb display with the real GTK widgets. The app was also
opened and rendered on the actual Wayland desktop. Xvfb EGL/DRI3 warnings and the
GdkX11 deprecation warning were test-environment diagnostics, not app failures.

## Remaining validation

Long real-workday trials, physical suspend/resume and lock timing, disk exhaustion,
full screen-reader interaction, high text scaling, large multi-month histories,
and other Linux desktops remain outside the verified scope. No claim of 10/10
or universal Linux compatibility is made. Existing accounting, billable rate
snapshots, privacy controls and background tracking architecture remain intact.

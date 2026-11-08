# Daily workflow and usability review

Checked 8 November 2026 for 0.4.0-rc2. Tests use disposable synthetic data; they do not read a user's activity database or send live TypeSafe requests.

## What changed

The main path is **record → Review today → select activity → Assign selected or Ask Jev → review drafts → approve → report**. The timeline remains available through **Open timeline**. Today also summarises saved work by task.

A rule means “when I use this application, assign its completed time to this task as a draft.” In Rules, choose **Create assignment rule**, pick a recorded application and pick a task, check the sentence, then Save. No typing is needed for this normal path. Custom app names, window-title matching and priority are optional. Use rules for dedicated apps; use daily review and Jev for apps shared across tasks. Rules do not use AI or approve time.

Daily review has Select shown, Clear selection and Ask Jev controls with an explicit selected duration. Assignment refreshes the remaining queue. Unused batch suggestions stay available during that review without another paid request; closing the review clears them. Open drafts keeps the date being reviewed. Without a rule, saved choice or reviewed suggestion, assignment requires an explicit task choice.

## Findings and verification

| Area | Result and evidence | Practical limit / next validation |
|---|---|---|
| Navigation and first use | All seven pages, keyboard and mouse navigation, first project, manual entries and setup continuation exercised. Rule setup resumes after creating a first project. | Screen-reader acceptance still requires a person using assistive technology. |
| Recording and live totals | Timers, live labels, foreground change, pause and idle/lock fail-closed paths checked. Isolated D-Bus GNOME and simulated KWin protocol checks pass; virtual X11 properties, Unicode titles and idle checks pass. | Hardware suspend/lock and full-day capture should be checked on each real desktop. |
| Daily assignment | Explicit task choice, selected duration, remaining queue, personal marking and interval allocation are covered. A 19-check focused GUI scenario covers the new daily path and guided rules. | A real user's working-day acceptance remains valuable. |
| Rules | Guided selections and previews, duplicates, conflicts, archived targets, paused rules and title-collection-off validation covered. Fixed selected-period application so it neither consumes unrelated days nor crosses the selected boundary. Repeated application does not duplicate time. | Title-specific rules depend on deliberately enabled title collection. |
| Jev / TypeSafe | Fake-key GUI checks cover secure key entry, outgoing-data consent, batch and single results, ambiguity and local feedback. Remaining results are retained only for the current review. No shared key is included. | No live key, live provider response, billing or real-world suggestion accuracy was tested. |
| Time integrity and billing | Overlap, historical rates, partial allocation, atomic approval, undo/split/merge, billed-entry protection and stale/duplicate reports are covered by core tests. Suggestions stay draft. | Invoice output remains a draft and does not calculate tax. |
| Reports and exports | CSV/HTML escaping, PDF and invoice-draft PDF controls, archived-client reports and billing-state preservation exercised. | Full desktop document-portal selection needs broader hardware testing. |
| Privacy, storage and recovery | Local backup/reopen, integrity and identical totals checked on a synthetic larger database. Private Secret portal checks cover encrypted store/read/remove and missing-portal failure. | The timesheet database itself is not encrypted; real desktop keyring/portal combinations need broader testing. |
| Performance | With 20,000 retained activity periods and 10,000 entries, a 2,000-period summary improved from 1.286 s to 0.015 s in one local run. Totals were identical. Allocation lookup now takes one snapshot per view. | These are illustrative local measurements, not a cross-machine benchmark or long-duration CPU/memory test. |
| Packaging | GitHub runs Ubuntu 22.04/24.04 core tests, scaled UI checks and AppImage/Flatpak build/runtime/secret tests before merge. | Downloads remain unsigned x86-64 prereleases, not Flathub releases. |

## Reproduce

- `python3 -m unittest discover -s tests -v`: 128 core tests.
- `tests/verify_ui.py`: 53 mouse/keyboard checks at 200% scaling.
- `tests/verify_daily_review.py`: guided no-typing rules, dated drafts, remaining queue and cached results.
- `tests/verify_rules_ui.py`, `tests/verify_jev_ui.py`, `tests/verify_improvements.py`: focused rules, consent, categories, pagination, dates, exclusions, timers and invoice controls.
- `packaging/verify_secret_portal.py`: private synthetic portal and encrypted storage.
- `tests/verify_collector.py`, `tests/verify_kde_capture.py`, `tests/verify_x11_capture.py`: isolated protocol/capture checks.

See `.github/workflows/tests.yml` and `.github/workflows/packages.yml` for exact virtual-display and private-bus commands. The PR check results are the release gates. No automated suite proves that every hardware/desktop/provider combination works.

# Implementation status

Updated 7 November 2026 for the 0.2.0 baseline. The 0.3.0 candidate adds desktop
adapters, PDF exports and package builds; see [current testing](docs/TESTING.md)
and [installation](docs/INSTALL.md). The machine-specific statements below are
historical evidence, not a claim about the reader’s installed service.

## Implemented

- Automatic foreground usage collector, live checkpointing, idle reclassification, lock handling, explicit capture gaps and user-controlled title/exclusion filtering.
- Included GNOME Shell 50 helper and panel menu; per-user installer, generated Applications launcher, CLI, automatic graphical startup and systemd restart supervision.
- Redesigned libadwaita Today dashboard with live app usage and assignment totals, guided project creation, calendar with native timeline, and searchable task/desktop history.
- Optional task timers, manual entries, atomic partial/bulk assignment, personal-usage marking, automatic future rules, protected historical reprocessing and review before billing.
- Client/project/task rates and budgets, split/merge/delete, multi-step undo, stale-edit protection and atomic approval.
- Frozen CSV/printable reports, historical rate snapshots, billed-entry locking and explicit invoice-correction history.
- Automatic daily backups, checked restore with rollback copy, migration backup, retention and period-specific raw-activity deletion.

## Verified

- 30 automated core tests cover accounting, concurrent writers, safe exports, rules, privacy, boundaries, undo, revisions, corrections, personal usage and backup validation.
- The collector passed an isolated D-Bus end-to-end test for durable capture, idle stopping and title privacy.
- The actual extension loaded in a separate GNOME 50.1 Wayland session, returned idle/lock information, and detected a real foreground GTK window and application. This test did not restart the user's desktop.
- A disposable systemd collector service restarted after a simulated process crash. The live tracker was untouched.
- The redesigned views were opened on the actual Ubuntu GNOME desktop using sample data. App-only synthetic screenshots were rendered and visually inspected.
- The installed user service is enabled and active. GNOME has installed/enabled the helper for the next sign-in.

## One-time user action

Save work and sign out and back in once. GNOME Wayland loads new local extensions at session start. After the next sign-in, open Time Sheet Linux and check that the header says “Tracking automatically”.

## Scope still requiring broader validation

The app is an early release, not a claim of perfect or universal Linux support. Long real-workday trials, actual hardware suspend/lock behavior, disk exhaustion, performance measurements, assistive-technology checks and additional desktop environments need further validation. P1/P2 features such as sync, team access, AI, direct PDF/XLSX and browser URLs remain outside this release. Exact-duration billing supports GBP, EUR and USD.

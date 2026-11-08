# Usability and reliability work

This branch is an incremental improvement to the 0.3 release candidate, not a
finished usability or accessibility certification.

## Included in this increment

- Custom history dates, billable filtering and incremental rendering of long
  history and calendar lists. The day review shows task entries as well as
  unassigned activity.
- A saved-time weekly overview, a header timer shortcut, searchable long
  dropdowns, a timeline legend and clearer explanations of time totals.
- Editing assignment rules, priority guidance and a warning when title capture
  is disabled; recorded-app exclusion controls and setup diagnostics in Settings.
- Internal CSV exports, including non-billable work and optional all-client
  export, without changing billing state; the latest local automatic backup.
- Quick manual-entry durations, optional reusable invoice details, and opt-in
  notifications when the background collector detects tracking degradation.
  The collector cannot alert if it is not running at all.

## Still needed

- Validate full working days on real hardware, including locking, sleep, resume,
  reboot, storage exhaustion, interrupted writes and recovery. A one-week trial
  must actually elapse; simulated tests are not equivalent.
- Test full workflows with Orca, keyboard-only use, high text scaling, narrow
  windows and high-contrast themes; run moderated usability sessions.
- Complete guided onboarding, a unified review workflow, richer manual entry,
  project search and organisation, reporting and invoice preferences.
- Evaluate backup encryption and recovery, monitoring when the collector is
  not running at all, more currencies, update delivery and signing, and
  additional Linux environments.
- Profile large datasets and long-running resource use; reduce the size and
  coupling of the interface module and extend end-to-end test coverage.

Real user testing and hardware results should be recorded with environment,
steps, observations and outstanding failures before calling the app broadly
accessible or production-ready.

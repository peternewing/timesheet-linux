# 0.7.0-rc1 — personal and work screen time

This candidate brings the assessed personal/work implementation into the current
source version. It keeps the four-step setup, Today/Past days/Settings, existing
records, explicit data policies and non-billable generic drafts.

## Included

- Seven-day and hourly observed screen-time views, top apps and local CSV/PDF records.
- Personal/Work/Unsorted labels, ready-made schedules, finite-period correction and Undo.
- Eight generic activity types and optional conservative installed-app classification.
- Typed Jev decisions with scoped memories, source/model/request provenance, cache and usage guards.
- Read-only background insight calculations, cancellation and closed-dialog resource cleanup.
- Read-only health tools and private unlabelled evaluation templates for later testing.

The [28-category reassessment](PERSONAL_WORK_REASSESSMENT_2026-11-09.md),
[work log](PERSONAL_WORK_ITERATION.md) and historical validation artifacts retain
their original source fingerprints. A version bump does not retroactively make
an older sustained run a test of this exact release source.

## Source installation

Use the current `main` source from
[GitHub](https://github.com/peternewing/timesheet-linux), with the system dependencies
in [the installation guide](INSTALL.md). Run `./install.sh` as your normal desktop
user. Keep its folder in place; the launcher and background services reference it.
Older published 0.6.1-rc2 binary downloads do not include these new source changes.
New packaged downloads must pass the package/provenance workflow before publication.

For this computer, the update is being prepared in a separate
`timesheet-linux-0.7.0-rc1` folder. The old installed folder remains available.
A consistent private database backup and integration rollback copy precede the
switch. An upgrade may carry forward an already enabled compatible policy, but
must not enable an off policy, widen the selected task scope, clear caps or unknown
usage, or enable new optional local typing for an existing opt-out.

## Acceptance limits

This is a release candidate. All 18 earlier external acceptance gates remain open:
representative real-day labels, novice/Orca workflows, multi-day physical desktop
coverage and final package/release acceptance are distinct from automated tests.
Passive reading/video still depends on the desktop idle signal; the app does not
collect playback/display-power evidence and does not claim phone-equivalent
screen-on or attention measurement. TypeSafe cannot reconstruct uncaptured time.

No further paid provider tests are authorised by the earlier exhausted 20-request
allowance. Normal app automation continues only under its existing explicit policy.

## Delivery record

Source review, fresh local checks, GitHub/CI results and the installed version are
recorded in the delivery evidence as they complete. No new numerical score or
human/hardware acceptance is claimed for this delivery step.

Three synthetic QA screenshots were visually reviewed and then explicitly approved
by the user for public upload on 9 November 2026. No real activity database, private
backup or API key is part of this source delivery.

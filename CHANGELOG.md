# Changelog

## 0.6.0-rc1 — simplicity rebuild

- Four-step click-only setup: ready-made categories, privacy, saved/pasted personal key, Start.
- Three everyday destinations and a quiet header; project/rule/billing controls moved to optional advanced tools.
- Specialist app activity categorised automatically; ambiguous uses get a single category choice.
- Factual day-record PDF with exact periods, source labels, away time and capture gaps.
- Category corrections preserve captured evidence and remain reversible/non-billable; existing business data is retained.
- Separate broad activity-type decisions from project/work-intent decisions; neither app use nor a category proves completed output.

## 0.5.0-rc1 — automation candidate

- Explicit personal-key background policy, independent worker, durable queue/cache, usage caps and safe recovery.
- Typed task/evidence/personal/category decisions, scoped examples and task guidance; first model pinned.
- Bounded focus context and separately authorised draft default; rules and manual assignments take precedence.
- Today status, exception inbox, one-answer-many scope preview, explanations and reversible drafts.
- Guidance overlap hints, local progress counts, read-only update check and trusted-build provenance workflow.
- Accepted 28-category roadmap and fresh second-pass adversarial assessment. Automatic accuracy, assistive technology and sustained hardware acceptance remain open.

## 0.4.0-rc2 — guided rules and daily review (2026-11-08)

- Create rules by selecting a recorded app and a task, with a plain-language preview. Keep title filters, custom app names and priority optional.
- Make Review today the main daily action, add Ask Jev and selection controls, and show a short summary of saved work.
- Keep unused Jev results while working through the review and keep draft review on the selected date.
- Require an explicit task choice when there is no rule or saved suggestion.
- Restrict applying rules to the selected period, including midnight boundaries; preserve unrelated activity and prevent duplicate assignments.
- Reject unusable title filters and conflicting future-rule choices without partially saving time.
- Speed up allocation summaries using a single snapshot, with running-timer parity checks. Add regression coverage and a usability report. This remains an unsigned prerelease; live TypeSafe/provider, assistive-technology and hardware testing remain follow-up work.

## 0.4.0-rc1 — optional review assistance (2026-11-08)

- Add local review sessions, readiness checks, optional remembered choices, and clearer assignment rules with a retained-activity preview.
- Add optional TypeSafe suggestions using a personal key, explicit per-request data previews, and user-reviewed results. Suggestions do not approve or bill time.
- Add optional categories, cancellation and bounded batch requests; no live API accuracy or calibration claim is made.
- Enable optional network access and application-scoped Secret portal storage in Flatpak. Package builds and desktop portal compatibility require further testing.

This is an unsigned prerelease. Back up data before upgrading; review all suggestions and drafts before billing.

## 0.3.0-rc3 — usability and reliability prerelease (2026-11-08)

- Add custom history dates, billable filters, project search and incremental lists.
- Improve first-run guidance, daily review, timer access and manual time entry.
- Add grouped internal CSV reports, optional invoice details, editable rules and app exclusions.
- Add privacy-safe tracking alerts, setup diagnostics and local backup status.
- Keep the Today view stable during routine updates and expose the exact release version.

This remains a prerelease. Accessibility, extended hardware, long-duration and broader desktop testing remain outstanding; see docs/IMPROVEMENTS.md. Back up data before upgrading. Releases are unsigned.

## 0.3.0 — compatibility candidate (2026-11-07)

- Preserve GNOME 50 capture; add Plasma 6, Sway and experimental Hyprland Wayland and EWMH X11 adapters.
- Require fresh focus plus available idle/lock evidence; never use Xwayland as a full-desktop fallback.
- Add a Plasma KWin helper and an isolated swayidle observer, with D-Bus sender validation.
- Preserve pause, title and autostart settings on reinstall; retain existing database/report formats.
- Import graphical session environment for the user collector service.
- Add privacy-safe diagnostics, version output, multi-distribution install instructions and rollback guidance.
- Add PDF reports and draft invoice PDFs without changing billing state.
- Add x86-64 AppImage and Flatpak builds; Flatpak uses a separately installed host companion.
- Fix scaled mouse-test coordinates; validate real headless Plasma/KWin and Sway capture.

Hardware desktop lock/suspend and wider distribution acceptance remain promotion gates.
Candidate binaries are available from GitHub Actions; no signed release or Flathub listing.
Keep the stable checkout available.

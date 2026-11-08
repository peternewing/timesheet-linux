# 0.6.0-rc1 — simplicity rebuild

The default product is now a four-step click-only setup, Today, Past days and
Settings. Read [the simplicity review](docs/SIMPLICITY_REVIEW_0.6.md). The prior
0.5 report remains historical evidence, not the current everyday UX.

# 0.5.0-rc1 automation candidate

The accepted source of truth is [AUTOMATION_ROADMAP.md](docs/AUTOMATION_ROADMAP.md).
Use [AUTOMATION_GUIDE.md](docs/AUTOMATION_GUIDE.md) for user-facing setup and limitations,
and [AUTOMATION_REVIEW_0.5.md](docs/AUTOMATION_REVIEW_0.5.md) for both scored passes.

Core recording remains local. Background Jev is off until an explicit standing
policy is enabled in the current installation. Each user supplies their own key.
All AI allocations are reversible drafts; no automatic approval or billing.

# Implementation status

Last checked: 8 November 2026.

The [0.4.0-rc2 prerelease](https://github.com/peternewing/timesheet-linux/releases/tag/v0.4.0-rc2) builds on the public [0.3.0-rc3 prerelease](https://github.com/peternewing/timesheet-linux/releases/tag/v0.3.0-rc3). It adds local review suggestions, clearer assignment rules, and optional TypeSafe suggestions with a personal key and an explicit data preview. All suggested assignments remain drafts for review; invoice drafts do not calculate tax or mark time billed. Core tracking works offline and window titles are off by default. Flatpak has network access for optional confirmed suggestions and uses application-scoped Secret portal storage.

Automatic capture supports GNOME 50, Plasma 6, Sway, experimental Hyprland and EWMH X11, with desktop-specific dependencies. Reports include CSV, HTML, PDF and invoice-draft PDF. Data and backups remain local SQLite; see the [compatibility matrix](docs/LINUX_COMPATIBILITY.md).

The candidate passed 128 core unit tests, 53 GTK smoke checks, and a synthetic Jev consent and review GUI test. A private D-Bus test exercised missing-portal failure and encrypted secret store/read/remove; the native runtime dependency check passed. Earlier isolated GNOME, Plasma and Sway focus/idle tests and virtual X11 checks cover the capture adapters. No real TypeSafe key, live API request, provider billing, or real user activity was used in Jev tests.

The previous release passed Ubuntu 22.04/24.04, UI and package checks. The follow-up runs the same release gates, including the new daily-review GUI test, before merging. The daily-review follow-up adds guided Rules, date-bounded rule application, persistent review results and faster allocation summaries. See [the usability review](docs/USABILITY_REVIEW.md) for current evidence and remaining validation. Releases are unsigned and not published to Flathub. Further validation is needed for real desktop Secret portals, Hyprland with a real GPU, hardware lock and suspend, Flatpak document portal behavior, accessibility, long-duration performance, more distributions and architectures, and live TypeSafe behavior. Other Wayland compositors remain manual-only until suitable adapters exist. See [test evidence](docs/TESTING.md).

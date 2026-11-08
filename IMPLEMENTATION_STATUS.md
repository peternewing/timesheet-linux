# Implementation status

Last checked: 8 November 2026.

The [0.4.0-rc1 prerelease](https://github.com/peternewing/timesheet-linux/releases/tag/v0.4.0-rc1) builds on the public [0.3.0-rc3 prerelease](https://github.com/peternewing/timesheet-linux/releases/tag/v0.3.0-rc3). It adds local review suggestions, clearer assignment rules, and optional TypeSafe suggestions with a personal key and an explicit data preview. All suggested assignments remain drafts for review; invoice drafts do not calculate tax or mark time billed. Core tracking works offline and window titles are off by default. Flatpak has network access for optional confirmed suggestions and uses application-scoped Secret portal storage.

Automatic capture supports GNOME 50, Plasma 6, Sway, experimental Hyprland and EWMH X11, with desktop-specific dependencies. Reports include CSV, HTML, PDF and invoice-draft PDF. Data and backups remain local SQLite; see the [compatibility matrix](docs/LINUX_COMPATIBILITY.md).

The candidate passed 124 core unit tests, 53 GTK smoke checks, and a synthetic Jev consent and review GUI test. A private D-Bus test exercised missing-portal failure and encrypted secret store/read/remove; the native runtime dependency check passed. Earlier isolated GNOME, Plasma and Sway focus/idle tests and virtual X11 checks cover the capture adapters. No real TypeSafe key, live API request, provider billing, or real user activity was used in Jev tests.

Ubuntu 22.04 and 24.04 tests, scaled UI checks, AppImage and Flatpak builds, bundled runtime checks and encrypted Secret portal tests passed in GitHub Actions run 42523517246 and test run 42523517284. PR #3 is merged; its source tree matches the package source tree. Releases are unsigned and not published to Flathub. Further validation is needed for real desktop Secret portals, Hyprland with a real GPU, hardware lock and suspend, Flatpak document portal behavior, accessibility, long-duration performance, more distributions and architectures, and live TypeSafe behavior. Other Wayland compositors remain manual-only until suitable adapters exist. See [test evidence](docs/TESTING.md).

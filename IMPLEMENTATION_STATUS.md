# Implementation status

Last checked: 7 November 2026.

| | 0.2.0 stable source (`main`) | 0.3.0 release candidate |
|---|---|---|
| Availability | Historical source on `main` | [AppImage and source](https://github.com/peternewing/timesheet-linux/releases/tag/v0.3.0-rc3) |
| Automatic capture | GNOME 50 Wayland | GNOME 50, Plasma 6, Sway, experimental Hyprland and EWMH X11; desktop dependencies apply |
| Reports | CSV and printable HTML | CSV, HTML, PDF and invoice-draft PDF |
| Data | Local SQLite and backups | Same database schema and report snapshots |

Both versions support manual time, projects, review and approval, local backups, retention and app exclusions. Window titles are off by default. Invoice drafts do not calculate tax or mark time billed.

The candidate passed 66 automated tests, scaled mouse/keyboard workflows and isolated GNOME, Plasma and Sway focus/idle tests. X11 was exercised on a virtual server. The tested package builds are available as a prerelease; they are not signed or published to Flathub. See [test evidence](docs/TESTING.md) and the [candidate pull request](https://github.com/peternewing/timesheet-linux/pull/1).

Still requiring validation: Hyprland with a real GPU, hardware lock and suspend across desktops, the Flatpak document portal, accessibility, long-duration performance and more distributions and architectures. Other Wayland compositors remain manual-only until suitable adapters exist. See the [compatibility matrix](docs/LINUX_COMPATIBILITY.md).

# Changelog

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

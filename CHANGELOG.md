# Changelog

## 0.3.0 — compatibility candidate (2026-11-07)

- Preserve GNOME 50 capture; add experimental Plasma 6 Wayland and EWMH X11 adapters.
- Require fresh focus plus available idle/lock evidence; never use Xwayland as a full-desktop fallback.
- Add a Plasma KWin helper and an isolated swayidle observer, with D-Bus sender validation.
- Preserve pause, title and autostart settings on reinstall; retain existing database/report formats.
- Import graphical session environment for the user collector service.
- Add privacy-safe diagnostics, version output, multi-distribution install instructions and rollback guidance.
- Expand core and private D-Bus tests; document PDF, AppImage and Flatpak roadmap.

Real Plasma/X11 acceptance remains a promotion gate. No direct PDF export or binary
AppImage/Flatpak distribution is included. Keep the stable checkout available.

# Linux compatibility and release plan

Research date: 7 November 2026. Candidate: 0.3.0. Stable baseline: 0.2.0.

## What “all Linux” can realistically mean

The UI depends on Python 3.10+, GTK 4, PyGObject and libadwaita 1.5+.
A distro name alone cannot establish compatibility: desktop compositor, display
protocol, library versions, user-session services and packaging all matter.
Old distributions without these libraries are not supported by the source install.
No universal Wayland API exposes every application's foreground window.

| Session | 0.2.0 | 0.3.0 candidate | Evidence / remaining validation |
|---|---|---|---|
| GNOME 50 Wayland | Automatic | Existing adapter preserved | Prior isolated GNOME 50.1 check; collector protocol regression |
| GNOME 45–49 / newer Shell | Manual | Manual until extension tested | Do not bypass extension version checks |
| Plasma 6 Wayland | Manual | KWin helper + swayidle | Adapter unit/protocol tests; real Plasma session acceptance still required |
| Plasma 5 Wayland | Manual | Manual | Helper targets Plasma 6 API |
| KDE / Xfce / Cinnamon / MATE / GNOME on X11 | Manual | python-xlib adapter | Requires EWMH, XScreenSaver and supported lock service; real desktop acceptance still required |
| Sway / Hyprland / other Wayland | Manual | Manual | Need compositor-specific foreground adapters; never use Xwayland as a substitute |
| Headless / SSH / unspecified session | Manual UI if available | Capture unavailable | No graphical activity inferred |

“Candidate” is not certification. In particular, a passing mock does not establish
that a desktop's real lock, focus and idle behavior works. Unsupported or missing
sources produce unknown/setup/degraded states; users retain manual entry/reporting.
X11 lock services supported: freedesktop, GNOME, Cinnamon and MATE. A standalone
locker without those services needs an additional adapter before automatic capture
can be considered reliable. libadwaita widgets work on KDE; they retain GTK styling.

## Implementation decisions

- Preserve GNOME's existing `(app, title, idle_ms, locked)` D-Bus contract and helper.
- Select the adapter using the graphical session; reject Xwayland as a fallback.
- Plasma 6: install a user KWin script, read `workspace.activeWindow`, send a
  one-second heartbeat to the collector, authenticate its D-Bus sender against
  `org.kde.KWin`, and reject samples older than three seconds.
- On KDE Wayland, **do not use ScreenSaver.GetSessionIdleTime**: KDE explicitly
  returns NotSupported. Use swayidle's compositor idle notifications instead,
  with an empty configuration so the user's lock/power commands are never loaded.
  Wait for an initial protocol event before considering idle data known. A one-second
  observer gives approximate boundaries; short idle periods are treated as active.
- Query the lock service separately. Missing lock or idle evidence yields unknown
  activity and stops task timers; it never silently means unlocked/active.
- X11 uses EWMH `_NET_ACTIVE_WINDOW`, WM_CLASS and the XScreenSaver idle counter.
  App identifiers differ from GNOME display names; review assignment/exclusion
  rules when changing desktop. Window titles remain off in storage by default.
- Import graphical environment into the user service at sign-in/startup.
  Concurrent graphical sessions for one Unix account are not supported.
- Keep database schema and report formats unchanged. Reinstallation preserves
  pause, title storage and autostart preferences. No automatic system upgrade,
  session restart or database replacement is performed.

## Packaging recommendation

**First: native source install with clear package commands and diagnostics.** It
fits the existing host collector and per-user helpers. A versioned release archive
and checksums are a useful next step; keep installation outside system directories.

**Next: AppImage pilot**, before promising one-download installation. Bundle Python,
PyGObject, GTK, libadwaita, typelibs and resources; build against the oldest supported
base and separately for each architecture. Test FUSE and extraction execution,
font rendering, portal file dialogs, X11 and Wayland. Host helpers still require
installation. Copy the application to a persistent per-user location before writing
systemd or desktop paths: an AppImage's temporary mount must never become a saved
service path. AppImage does not make newer glibc binaries run on older systems.

**Then: Flatpak UI + a separately installed host collector.** Flatpak is attractive
for consistent GTK libraries and software-center updates, but the current app writes
host systemd/autostart/extension files and opens a host database directly. Packaging
it unchanged is not a complete solution. Introduce a versioned, authenticated
D-Bus interface for collector status/settings/data, use narrow talk-name permissions
and document the host-helper install. Do not grant unrestricted session-bus access
or a host-shell escape just to make the existing installer work. Plan explicit
import/backup for the Flatpak XDG data location; never open two divergent databases
silently. Flathub submission follows functional and permission review.

No AppImage, Flatpak or Flathub release is currently published by this project.
Do not advertise installation commands for nonexistent artifacts.

## Suggested product improvements (priority order)

1. **Direct PDF timesheet export from saved report snapshots.** Use the same frozen
   amounts as CSV/HTML; choose a maintained PDF renderer with Unicode font embedding,
   repeated table headers, page numbers and long-description wrapping. Test A4/Letter,
   multi-page reports, GBP/EUR/USD, non-ASCII names and empty reports. Export must not
   approve entries or mark invoices billed. Existing browser Print → Save as PDF works.
2. **Invoice PDFs as a separate feature.** Add seller/customer addresses, invoice
   number/date, due date, currency, payment details and configurable taxes/discounts.
   Preserve issued snapshots and corrections. Avoid labelling a basic timesheet a tax
   invoice; jurisdiction-specific invoice requirements need separate review.
3. **In-app diagnostics and onboarding.** Show selected adapter, missing dependencies,
   helper heartbeat, lock/idle availability and precise repair actions. Export a
   sanitised diagnostic bundle with no titles, activity or database contents.
4. **Installer/release polish.** Versioned packages, checksums, a stable launcher path,
   backup before upgrade, explicit rollback and a release smoke-test matrix.
5. **Desktop coverage.** Validate older GNOME extensions one version at a time, then
   implement Sway IPC and Hyprland foreground adapters with idle and lock checks.
6. **Billing usability.** Optional rounding policies displayed before approval,
   XLSX export, keyboard/accessibility audit and configurable week starts.

## Acceptance gate before promoting 0.3.0

Use disposable accounts/data on GNOME 50 Wayland, Plasma 6 Wayland and at least
one EWMH X11 desktop. Exercise native and Xwayland apps, focus changes, title
privacy, exclusions, idle cutoff, lock/unlock, suspend/resume, helper crash/restart,
logout/login, missing dependencies, installation in a path with spaces, systemd
and detached startup, upgrade/rollback, saved report equality and uninstall.
Test distro families Ubuntu/Debian, Fedora, Arch and openSUSE on their supported
releases. Check x86_64 and aarch64 separately before publishing binaries.

## Primary sources

- [KWin scripting API](https://develop.kde.org/docs/plasma/kwin/api/): foreground window and application properties.
- [KWin installation tutorial](https://develop.kde.org/docs/plasma/kwin/): user scripts, Plasma 6 configuration and reconfigure.
- [KWin implementation](https://github.com/KDE/kwin/blob/master/src/scripting/scripting.cpp): script timers.
- [KDE screen-lock interface](https://github.com/KDE/kscreenlocker/blob/master/interface.cpp): Wayland idle-query limitation.
- [swayidle manual](https://github.com/swaywm/swayidle/blob/master/swayidle.1.scd): timeout/resume events and explicit configuration.
- [X11 ScreenSaver protocol](https://www.x.org/docs/saver/saver.pdf): idle counter semantics.
- [PyGObject installation](https://gnome.pages.gitlab.gnome.org/pygobject/getting_started.html): distro package guidance.
- [Debian 13 libadwaita](https://packages.debian.org/trixie/libs/libadwaita-1-0): version 1.7 meets the UI minimum; this does not certify capture.
- [AppImage best practices](https://docs.appimage.org/reference/best-practices.html): oldest-base-system compatibility.
- [Flatpak sandbox permissions](https://docs.flatpak.org/en/latest/sandbox-permissions.html): filesystem and D-Bus restrictions.

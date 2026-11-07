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
| GNOME 50 Wayland | Automatic | Existing adapter preserved | Real isolated GNOME Wayland fixture rechecked; collector protocol regression |
| GNOME 45–49 / newer Shell | Manual | Manual until extension tested | Do not bypass extension version checks |
| Plasma 6 Wayland | Manual | KWin helper + swayidle | Real headless KWin 6.6 Wayland focus and idle passed; hardware lock/suspend still pending |
| Plasma 5 Wayland | Manual | Manual | Helper targets Plasma 6 API |
| KDE / Xfce / Cinnamon / MATE / GNOME on X11 | Manual | python-xlib adapter | Virtual X server test passed; requires EWMH, XScreenSaver and supported lock service; real desktop acceptance pending |
| Sway Wayland | Manual | Sway IPC + swayidle | Real headless focus/idle passed; lock service simulated |
| Hyprland Wayland | Manual | Hyprland IPC + swayidle | Mock tests passed; real GPU-backed session still needed |
| Other Wayland | Manual | Manual | No universal foreground API; never use Xwayland as a substitute |
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
- Sway/Hyprland use their compositor IPC plus swayidle and a supported D-Bus lock
  service. If that lock service does not reflect the actual locker, capture must not
  be trusted. Sway headless tested; Hyprland still requires real-session acceptance.
- X11 uses EWMH `_NET_ACTIVE_WINDOW`, WM_CLASS and the XScreenSaver idle counter.
  App identifiers differ from GNOME display names; review assignment/exclusion
  rules when changing desktop. Window titles remain off in storage by default.
- Import graphical environment into the user service at sign-in/startup.
  Concurrent graphical sessions for one Unix account are not supported.
- Keep database schema and report formats unchanged. Reinstallation preserves
  pause, title storage and autostart preferences. No automatic system upgrade,
  session restart or database replacement is performed.

## Distribution and PDF status

The candidate includes a source installer, a bundled x86-64 AppImage build and a
Flatpak build. The AppImage is built on Ubuntu 24.04, requires glibc 2.39+ and keeps
its launcher/service tied to the persistent image path. The Flatpak uses a separate
host collector/helper and a narrow permission to the existing default data directory;
it does not escape the sandbox to install host files. See [installation](INSTALL.md).
The [0.3.0-rc1 prerelease](https://github.com/peternewing/timesheet-linux/releases/tag/v0.3.0-rc1) provides the tested packages and checksums. It is not a signed release or a Flathub listing. ARM64 Flatpak sources are specified but have not
been built or tested; no ARM64 AppImage is currently produced.

Saved reports export directly to PDF or to clearly labelled invoice draft PDFs, in
addition to CSV and HTML. Invoice drafts accept seller/customer details, reference,
dates and payment text, but do not calculate taxes, make legal claims or mark work
billed. Data comes from the frozen report snapshot; exporting does not change it.
PDF rendering uses embedded DejaVu Sans; writing systems outside its glyph coverage
need further font support.

Further priorities: improve invoice tax/discount configuration with jurisdictional
review; validate and extend Wayland foreground adapters; accessible keyboard workflows; XLSX
export and configurable rounding; multi-architecture and long-duration testing.

## Acceptance gate before promoting 0.3.0

Continue testing disposable accounts/data on GNOME 50 Wayland, Plasma 6 Wayland and
at least one EWMH X11 desktop. Headless KWin 6.6 focus and idle have passed locally. Exercise native and Xwayland apps, focus changes, title
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

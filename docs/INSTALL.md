# Installation and troubleshooting

## Requirements and release status

Python 3.10+, PyGObject, GTK 4 and libadwaita 1.5+ are required. GNOME 50
Wayland is the previously exercised automatic-capture target. The 0.3.0 candidate
adds experimental Plasma 6 Wayland and X11 adapters. They require real-session
acceptance testing before promotion. Other Wayland desktops retain manual mode.
See the [compatibility matrix and research](LINUX_COMPATIBILITY.md).

## Install distribution dependencies

Use your distribution's system Python packages; do not install GTK with pip.
These commands provide the UI, not universal automatic-capture support.

Ubuntu 24.04+ / Debian 13+ (older releases may lack libadwaita 1.5):

```sh
sudo apt update
sudo apt install git python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1
# Optional: for the 0.3.0 X11 adapter
sudo apt install python3-xlib
# Optional: for the 0.3.0 Plasma 6 Wayland adapter
sudo apt install swayidle
```

Fedora (supported release):

```sh
sudo dnf install git python3-gobject python3-cairo gtk4 libadwaita
# For X11: sudo dnf install python3-xlib
# For Plasma 6 Wayland: sudo dnf install swayidle
```

Arch / EndeavourOS:

```sh
sudo pacman -Syu git python-gobject python-cairo gtk4 libadwaita
# For X11: sudo pacman -S python-xlib
# For Plasma 6 Wayland: sudo pacman -S swayidle
```

openSUSE Tumbleweed:

```sh
sudo zypper install git python3-gobject python3-gobject-Gdk python3-cairo typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1
# For Plasma 6 Wayland: sudo zypper install swayidle
```

openSUSE may use versioned Python package names. Ensure bindings match
`/usr/bin/python3`; use `zypper search gobject` / `zypper search xlib` if needed.
Do not add an untrusted repository or upgrade your OS just to satisfy this app.

## Install the app

```sh
git clone https://github.com/peternewing/timesheet-linux.git
cd timesheet-linux
./install.sh
```

Run as your normal desktop user, **not sudo**. Keep this folder: launchers reference
it. Open Time Sheet Linux from Applications after the desktop-specific setup below.
For a downloaded source ZIP, extract it first and run `sh install.sh` from its folder;
restore launcher permissions with `chmod +x run-timesheet run-collector uninstall.sh`.

To evaluate the candidate separately without changing your stable clone:

```sh
git clone --branch linux-compatibility-0.3 https://github.com/peternewing/timesheet-linux.git timesheet-linux-0.3
cd timesheet-linux-0.3
/usr/bin/python3 -m timesheet.diagnostics
```

Do not install the candidate over your working integration until you have backed up
and are ready to test. For an isolated manual UI trial without touching real data:

```sh
XDG_DATA_HOME="$(mktemp -d)" TIMESHEET_TESTING=1 ./run-timesheet
```

This is temporary test data, not your production database. Do not run the installer
with this temporary environment. Installation switches the per-user launchers/service
to whichever checkout you install last.

## Plasma 6 Wayland setup (0.3.0 candidate)

Install `swayidle` and ensure `kwriteconfig6` is available from your Plasma packages.
Run `./install.sh`; it installs/enables the local **Time Sheet Linux Capture** KWin
script. Save work and sign out/in, or verify it in System Settings → Window
Management → KWin Scripts. Move the pointer, then leave it still briefly so the idle
observer can initialise. Check `./run-timesheet --status` before trusting capture.
The KWin helper is not a GNOME extension. It supports native Wayland and Xwayland
windows. No global input logging is used. If idle/lock information is missing,
tracking is degraded and activity remains unknown.

## X11 setup (0.3.0 candidate)

Install python-xlib using your package manager. Run `./install.sh` within the X11
desktop session, then check status. The window manager must implement EWMH and the
X server must expose XScreenSaver. A supported D-Bus lock service must be running;
standalone lockers are not assumed safe. Do not force `XDG_SESSION_TYPE=x11` in a
Wayland session. Capture rules may need updating because app identifiers differ
between desktops.

## Installed files

The app stays in the cloned source directory. The installer generates paths for that directory, including paths containing spaces.

| Location | Purpose |
|---|---|
| `~/.local/share/applications/org.local.TimeSheetLinux.desktop` | Applications-menu launcher and pause/resume actions |
| `~/.local/share/icons/hicolor/scalable/apps/org.local.TimeSheetLinux.svg` | App icon |
| `~/.local/bin/time-sheet-linux` | Command launcher |
| `~/.config/autostart/time-sheet-linux.desktop` | Start at graphical sign-in |
| `~/.config/systemd/user/time-sheet-linux.service` | Collector supervision and restart after failure |
| `~/.local/share/gnome-shell/extensions/timesheet-capture@local/` | Local GNOME capture helper |
| `~/.local/share/kwin/scripts/timesheet-capture/` | Plasma 6 helper (candidate, KDE installs only) |
| `~/.local/share/time-sheet-linux/` | Private database, status and backups |

`XDG_DATA_HOME` and `XDG_CONFIG_HOME` override their corresponding locations. The candidate starts its supervised unit from XDG graphical autostart after importing the current session environment, rather than enabling a second target-based startup. A file lock prevents duplicate collectors even when the app and sign-in startup overlap. Without a working user systemd instance, the app falls back to a detached collector; automatic restart supervision then needs systemd.

## One-time GNOME activation

A newly installed local extension loads at the next GNOME session. Save your work and sign out and back in once. The app never forces logout or restart.

Verify:

```sh
gnome-extensions info timesheet-capture@local
systemctl --user status time-sheet-linux.service
./run-timesheet --status
```

The app should report `active` and show app usage in Today. If extensions are globally disabled, enable user extensions in the GNOME Extensions app. On an unsupported Shell version, the helper stays unavailable; do not disable GNOME's extension version checks to force compatibility.

## Tracking says Finish setup

1. Check your session and required adapter in the compatibility matrix. For GNOME automatic capture, confirm GNOME 50 Wayland.
2. Run `./install.sh` to repair the local integration.
3. Save work and sign out/in once.
4. Open the app and Resume if paused.

On the candidate, run `/usr/bin/python3 -m timesheet.diagnostics` for a privacy-safe dependency/session report. If you cannot activate the helper, use manual time and report the desktop version and a sanitised error description. Never attach your activity database or titles to an issue.

## Tracking stopped or failed

Open Settings and restart the tracker, or:

```sh
systemctl --user restart time-sheet-linux.service
./run-timesheet --status
```

For a storage failure, free disk space or fix permissions before restarting. The tracker does not invent the missing period. Check Calendar for gaps and add genuine work manually. If systemd is unavailable, opening the app starts the detached collector.

## Backup and restore

Settings offers checked backup and restore. Restore validates a temporary copy before replacing the working database, stops the collector and keeps a `pre-restore-*.sqlite3` recovery copy. A prior interrupted timer is not restarted from a historical backup. Make a separate external copy if disk-loss protection matters to you.

A restore can reintroduce deleted activity. Existing report exports and older backups are outside raw-activity deletion.

## Update

Back up important data first. From the same clone:

```sh
git pull --ff-only
./install.sh
```

Version 0.3.0 does not change the database schema or saved report formats. Its installer preserves pause, title and autostart preferences. Database migrations keep a pre-upgrade backup when entries exist. Updates to GNOME extension code may require another sign-out/in because the running Shell caches loaded modules. If you move the repository, reinstall from its new directory.

## Roll back the candidate

Quit the UI and run `./install.sh` from your retained stable checkout. This stops the
collector and repoints launchers/service to that checkout. Version 0.3.0 uses the
same schema as 0.2.0; retain a backup regardless. On KDE, disable Time Sheet Linux
Capture in KWin Scripts when returning to 0.2.0, which has no KDE adapter. Never
restore an older backup over newer work without reviewing what would be lost.

## PDF and easier distribution

Reports already export printable HTML: open it in a browser and choose Print →
Save as PDF. Direct PDF and invoice generation, AppImage and Flatpak are proposed,
not shipped. See the [prioritised roadmap](LINUX_COMPATIBILITY.md#suggested-product-improvements-priority-order).

## Uninstall

```sh
./uninstall.sh
```

This stops the collector and removes its launcher, startup, service and helper integration. It keeps the activity database and backups. You can delete the source clone after uninstalling. Remove personal data separately only when you intend to erase it.

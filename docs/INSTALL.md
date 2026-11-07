# Installation and troubleshooting

## Supported target

Automatic capture is built for GNOME Shell 50 on Wayland. The native interface needs Python 3.10+, PyGObject, GTK 4 and libadwaita 1.5+. The tested desktop is Ubuntu 26.04 with GNOME 50.1. Other desktop backends are not implemented.

On Ubuntu:

```sh
sudo apt install git python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
git clone https://github.com/peternewing/timesheet-linux.git
cd timesheet-linux
./install.sh
```

Do not run the installer with sudo. There is no pip or virtual-environment requirement; use `/usr/bin/python3` so it can find the distribution's GTK bindings.

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
| `~/.local/share/time-sheet-linux/` | Private database, status and backups |

`XDG_DATA_HOME` and `XDG_CONFIG_HOME` override their corresponding locations. A file lock prevents duplicate collectors even when the app and sign-in startup overlap. Without a working user systemd instance, the app falls back to a detached collector; automatic restart supervision then needs systemd.

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

1. Confirm that you are in GNOME 50 Wayland.
2. Run `./install.sh` to repair the local integration.
3. Save work and sign out/in once.
4. Open the app and Resume if paused.

If you cannot activate the helper, use manual time and report the GNOME version and a sanitised error description. Never attach your activity database or titles to an issue.

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

Database migrations keep a pre-upgrade backup when entries exist. Updates to GNOME extension code may require another sign-out/in because the running Shell caches loaded modules. If you move the repository, reinstall from its new directory.

## Uninstall

```sh
./uninstall.sh
```

This stops the collector and removes its launcher, startup, service and helper integration. It keeps the activity database and backups. You can delete the source clone after uninstalling. Remove personal data separately only when you intend to erase it.

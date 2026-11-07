# Install Time Sheet Linux

Choose a version and installation method, then follow the desktop setup and verification steps. No root access is needed for the app installer itself.

- **[0.3.0 release candidate](#install-the-030-release-candidate):** AppImage, Flatpak or source. Includes additional desktop adapters and PDF export. These are unsigned test builds.
- **[0.2.0 stable source](#install-stable-020-from-source):** the existing GNOME 50 Wayland version on `main`.
- [Desktop setup](#desktop-setup) · [Check tracking](#check-tracking) · [Troubleshooting](#troubleshooting) · [Backup and restore](#backup-and-restore) · [Update and uninstall](#update-and-uninstall)

Back up important data before changing versions. Version 0.3.0 uses the same database schema and report snapshots as 0.2.0; it does not deliberately erase your work.

## Before you start

You need a Linux graphical session. To see the architecture and session type:

```sh
uname -m
printf 'Session: %s\nDesktop: %s\n' "$XDG_SESSION_TYPE" "$XDG_CURRENT_DESKTOP"
```

The published AppImage and Flatpak are for **x86-64** (`x86_64`). The AppImage needs glibc 2.39 or newer; check with `getconf GNU_LIBC_VERSION`. It runs with your normal user permissions. NixOS may require an AppImage compatibility launcher. Flatpak installs the GNOME 49 runtime from Flathub and needs an internet connection for that runtime.

The source install needs Python 3.10+, PyGObject, GTK 4 and libadwaita 1.5+. AppImage and Flatpak bundle their UI libraries. The Flatpak host collector still needs system Python and PyGObject.

## Install the 0.3.0 release candidate

Download the [AppImage](https://github.com/peternewing/timesheet-linux/releases/download/v0.3.0-rc1/TimeSheetLinux-x86_64.AppImage) or [Flatpak](https://github.com/peternewing/timesheet-linux/releases/download/v0.3.0-rc1/TimeSheetLinux-x86_64.flatpak), plus [SHA256SUMS](https://github.com/peternewing/timesheet-linux/releases/download/v0.3.0-rc1/SHA256SUMS). The [release page](https://github.com/peternewing/timesheet-linux/releases/tag/v0.3.0-rc1) contains release notes and all assets. Open a terminal in the folder containing those files. No GitHub account is required to download release assets.

### Option A: AppImage

```sh
sha256sum --ignore-missing -c SHA256SUMS
chmod +x TimeSheetLinux-x86_64.AppImage
./TimeSheetLinux-x86_64.AppImage --diagnose
./TimeSheetLinux-x86_64.AppImage --install
```

The checksum command must report the downloaded AppImage as `OK`. The installer creates a user launcher and collector; open **Time Sheet Linux** from Applications. Keep the image in a permanent location: the launcher and service point to that file. If you move it, run `--install` again from the new location.

If your system cannot mount AppImages, `APPIMAGE_EXTRACT_AND_RUN=1 ./TimeSheetLinux-x86_64.AppImage` can run it temporarily. The installed launcher and service still need working AppImage mounting; use FUSE support or choose the source/Flatpak method for background startup.

### Option B: Flatpak

Install Flatpak using your distribution's official instructions, then:

```sh
sha256sum --ignore-missing -c SHA256SUMS
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user ./TimeSheetLinux-x86_64.flatpak
flatpak run --user org.local.TimeSheetLinux
```

The checksum command must report the Flatpak as `OK`. The bundle contains the interface and PDF dependencies. It accesses the existing **default** host data directory, `~/.local/share/time-sheet-linux/`. If you use a custom `XDG_DATA_HOME`, do not assume it sees the same database; make and verify a backup before migrating. Run one UI at a time.

**Automatic tracking requires a host companion.** From your desktop session, keep a source checkout in a permanent folder and run:

```sh
git clone --branch v0.3.0-rc1 https://github.com/peternewing/timesheet-linux.git timesheet-linux-host
cd timesheet-linux-host
# Ubuntu/Debian; install equivalent Python/PyGObject packages on other distros
sudo apt install python3-gi
./run-host --install
```

The companion installs a per-user collector, startup entry and applicable desktop helper; it does not replace an existing app-menu launcher. The checkout is pinned to the release tag. For other distributions install system Python 3.10+ and PyGObject; add the desktop-specific packages below. Startup is controlled on the host, not in Flatpak settings.

### Option C: source

Install your distribution's packages first. These package names are for current releases; older distributions may not provide libadwaita 1.5 or newer.

**Ubuntu 24.04+ / Debian 13+:**

```sh
sudo apt update
sudo apt install git python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 python3-reportlab fonts-dejavu-core
```

**Fedora:**

```sh
sudo dnf install git python3-gobject python3-cairo gtk4 libadwaita python3-reportlab dejavu-sans-fonts
```

**Arch / EndeavourOS:**

```sh
sudo pacman -Syu git python-gobject python-cairo gtk4 libadwaita python-reportlab ttf-dejavu
```

**openSUSE Tumbleweed:**

```sh
sudo zypper install git python3-gobject python3-gobject-Gdk python3-cairo typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1 python3-reportlab dejavu-fonts
```

On openSUSE, package names can be Python-version-specific. The bindings must match `/usr/bin/python3`; use `zypper search` if needed. PDF export requires ReportLab and DejaVu Sans. If PDF export says fonts are missing even though they are installed, see [PDF font troubleshooting](#troubleshooting). Then install the tagged candidate:

```sh
git clone --branch v0.3.0-rc1 https://github.com/peternewing/timesheet-linux.git timesheet-linux-0.3
cd timesheet-linux-0.3
/usr/bin/python3 -m timesheet.diagnostics
./install.sh
```

Run the installer as your normal user, **not `sudo`**. Keep this folder: the launcher and service reference it. Git may say the tagged checkout is in a detached state; that is expected for a fixed release. Open **Time Sheet Linux** from Applications and complete the desktop setup below.

## Install stable 0.2.0 from source

The stable source targets GNOME Shell 50 Wayland. On Ubuntu GNOME:

```sh
sudo apt update
sudo apt install git python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1
git clone https://github.com/peternewing/timesheet-linux.git
cd timesheet-linux
./install.sh
```

Use your normal user account. Save your work and sign out and back in once to load the GNOME helper. This version exports CSV and printable HTML; it does not include the candidate's PDF or non-GNOME capture adapters.

## Desktop setup

The distro alone does not determine capture support. Open **Settings → About** or use `printf '%s / %s\n' "$XDG_CURRENT_DESKTOP" "$XDG_SESSION_TYPE"` to identify your session.

- **GNOME 50 Wayland:** the installer copies and enables the local GNOME helper. Save work and sign out/in once. If GNOME globally disables user extensions, enable them in the Extensions app. The helper's panel clock opens the app and offers pause/resume.
- **Plasma 6 Wayland, 0.3 candidate:** install `swayidle` and the Plasma package containing `kwriteconfig6`. Run the installer or host companion in the Plasma session. Check **System Settings → Window Management → KWin Scripts** for *Time Sheet Linux Capture*. Sign out/in if needed. Move the pointer, then leave it still briefly for the idle observer to initialise.
- **Sway or Hyprland Wayland, 0.3 candidate:** install `swayidle` and the compositor's IPC tool (`swaymsg` or `hyprctl`). A supported D-Bus lock service must accurately reflect your actual screen locker. Sway was exercised headlessly; Hyprland remains experimental.
- **X11, 0.3 candidate:** install `python3-xlib` (Arch: `python-xlib`) on the host when using source or the Flatpak companion. The AppImage bundles it. The window manager must support EWMH, the X server must expose XScreenSaver, and a supported D-Bus lock service must reflect your actual locker. App names can differ from Wayland, so review exclusions and assignment rules.
- **Other Wayland sessions:** use manual timers and entries. Do not force an X11 session variable to bypass compositor restrictions.

On Ubuntu/Debian, `sudo apt install swayidle` adds the idle observer; `sudo apt install python3-xlib` adds X11 bindings. Capture is unavailable or degraded when required focus, idle or lock evidence is missing; unknown time is not treated as active work. See the [compatibility matrix](LINUX_COMPATIBILITY.md).

## Check tracking

Open the app and confirm the header says **Tracking automatically**; app names should appear in Today after you use different windows. If paused, choose **Resume**. For source installs, run:

```sh
./run-timesheet --status
# 0.3 candidate only:
./run-timesheet --diagnose
```

For an AppImage, replace `./run-timesheet` with the path to the image. The Flatpak interface depends on the host companion; use the commands from its checkout or inspect the UI. The status should be `active`; `paused`, `setup_required`, `degraded`, `error` or `stopped` need attention. A partial setup or an inactive tracker must not be used as proof of billable work.

## Troubleshooting

- **GNOME says Finish setup:** confirm GNOME 50 Wayland, run the relevant installer, enable user extensions, then sign out/in. Check `gnome-extensions info timesheet-capture@local`.
- **Plasma / Sway / Hyprland:** confirm the host tools above are installed and the session is the intended Wayland compositor. For Plasma, enable the KWin script. If the lock service is missing or does not represent your real locker, use manual time.
- **Tracker stopped:** open Settings and restart it, or on a system with user systemd run `systemctl --user restart time-sheet-linux.service`. Without user systemd, opening the native app starts a detached collector.
- **Missing GTK or libadwaita:** use a supported distro version or the packaged interface. Do not force GNOME extension version checks or install GTK with `pip`.
- **PDF says DejaVu fonts are missing:** the 0.3.0 candidate searches its `resources/fonts` folder and `/usr/share/fonts/truetype/dejavu/`. Some distributions use a different font directory. From the source checkout, check `fc-match 'DejaVu Sans'` selects DejaVu Sans, then copy the system font files into the app's folder:

  ```sh
  mkdir -p resources/fonts
  cp "$(fc-match -f '%{file}' 'DejaVu Sans:style=Book')" resources/fonts/DejaVuSans.ttf
  cp "$(fc-match -f '%{file}' 'DejaVu Sans:style=Bold')" resources/fonts/DejaVuSans-Bold.ttf
  ```

  Install your distribution's `fontconfig` package if `fc-match` is unavailable. AppImage and Flatpak include the fonts.
- **Storage error:** free space or correct permissions, then restart. Review gaps and add genuine work manually; the app does not invent missing activity.

When reporting a problem, include your distribution, desktop/session, version and a sanitised error. Never upload your database or sensitive window titles to a public issue.

## Backup and restore

The default data folder is `~/.local/share/time-sheet-linux/`; source/AppImage installations honour `XDG_DATA_HOME`. The main file is `timesheet.sqlite3` and local daily backups are in `backups/`. Files are user-only but not encrypted. Copy backups to separate storage for disk-loss protection.

Settings offers a checked backup and restore and keeps a pre-restore recovery copy. Restoring an older backup can reintroduce deleted activity and replace newer work. For Flatpak, first stop the **host** collector with `systemctl --user stop time-sheet-linux.service` or stop its detached process; restore from Settings, then start it with `./run-host --background` from the host checkout. Keep any newer test data separately before restoring an older database.

## Update and uninstall

### Source

For a `main` checkout, back up, then run `git pull --ff-only` and `./install.sh` from the same folder. A `v0.3.0-rc1` checkout is pinned to a tag: download/clone a newer release into a separate folder, back up, and run that version's installer. To return to the older source checkout, run its `./install.sh`. GNOME helper updates may require sign-out/in.

To remove source integration while retaining the database and backups, run `./uninstall.sh` from the installed checkout. Remove personal data separately only if you intend to erase it.

### AppImage

Download the newer image and its checksums, verify them, close the app and stop the old service (`systemctl --user stop time-sheet-linux.service` when user systemd is available). Replace the image at the same persistent path, make it executable and run `--install`. Keep the older image and a data backup for rollback.

To remove its user integration while retaining data, run:

```sh
./TimeSheetLinux-x86_64.AppImage --uninstall
```

### Flatpak and host companion

Download and verify a newer bundle, then run `flatpak install --user --reinstall ./TimeSheetLinux-x86_64.flatpak`. These single-file bundles are not connected to an app update repository, so `flatpak update` will not fetch later candidate builds automatically. To update the tagged host companion, install the newer release's source in a separate persistent folder and run `./run-host --install` there.

Remove the interface with `flatpak uninstall --user org.local.TimeSheetLinux`. To also remove its shared host capture service and helpers, run `./run-host --uninstall` from the host companion checkout. This keeps your data and any native launcher, but removes shared capture integration; reinstall the native checkout if you still use it.

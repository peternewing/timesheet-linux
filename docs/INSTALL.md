# Install Time Sheet Linux

Install **0.4.0-rc1** using one of the two methods below. No root access is needed for the app installer itself. This version is a prerelease and the downloads are unsigned; back up important data before upgrading. It uses the same database schema and report snapshots as 0.2.0.

- [Option 1: AppImage](#option-1-appimage)
- [Option 2: Terminal installation from source](#option-2-terminal-installation-from-source)
- [Desktop setup](#desktop-setup) · [Check tracking](#check-tracking) · [Troubleshooting](#troubleshooting) · [Backup and restore](#backup-and-restore) · [Update and uninstall](#update-and-uninstall)

## Before you start

You need a Linux graphical session. To see the architecture and session type:

```sh
uname -m
printf 'Session: %s\nDesktop: %s\n' "$XDG_SESSION_TYPE" "$XDG_CURRENT_DESKTOP"
```

The published AppImage is for **x86-64** (`x86_64`). The AppImage needs glibc 2.39 or newer; check with `getconf GNU_LIBC_VERSION`. It runs with your normal user permissions. NixOS may require an AppImage compatibility launcher.

The source install needs Python 3.10+, PyGObject, GTK 4 and libadwaita 1.5+. The AppImage bundles its UI libraries.

## Install 0.4.0-rc1

Choose one of the two methods. No GitHub account is required. The [release page](https://github.com/peternewing/timesheet-linux/releases/tag/v0.4.0-rc1) has the release notes.

### Option 1: AppImage

Download the [AppImage](https://github.com/peternewing/timesheet-linux/releases/download/v0.4.0-rc1/TimeSheetLinux-x86_64.AppImage) and [SHA256SUMS](https://github.com/peternewing/timesheet-linux/releases/download/v0.4.0-rc1/SHA256SUMS) into a permanent folder. Open a terminal in that folder and run:

```sh
sha256sum --ignore-missing -c SHA256SUMS
```

Confirm the AppImage is listed as `OK` before continuing:

```sh
chmod +x TimeSheetLinux-x86_64.AppImage
./TimeSheetLinux-x86_64.AppImage --diagnose
./TimeSheetLinux-x86_64.AppImage --install
```

The checksum command must report the downloaded AppImage as `OK`. The installer creates a user launcher and collector; open **Time Sheet Linux** from Applications. Keep the image in a permanent location: the launcher and service point to that file. If you move it, run `--install` again from the new location.

If your system cannot mount AppImages, `APPIMAGE_EXTRACT_AND_RUN=1 ./TimeSheetLinux-x86_64.AppImage` can run it temporarily. The installed launcher and service still need working AppImage mounting; use FUSE support or choose the terminal source method for background startup.

### Option 2: Terminal installation from source

Install your distribution's packages first. These package names are for current releases; older distributions may not provide libadwaita 1.5 or newer.

**Ubuntu 24.04+ / Debian 13+:**

```sh
sudo apt update
sudo apt install git python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-secret-1 python3-reportlab fonts-dejavu-core
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

On openSUSE, package names can be Python-version-specific. The bindings must match `/usr/bin/python3`; use `zypper search` if needed. PDF export requires ReportLab and DejaVu Sans. If PDF export says fonts are missing even though they are installed, see [PDF font troubleshooting](#troubleshooting). Then install the tagged release (the default branch still contains older source code):

```sh
git clone --branch v0.4.0-rc1 https://github.com/peternewing/timesheet-linux.git timesheet-linux-0.4
cd timesheet-linux-0.4
/usr/bin/python3 -m timesheet.diagnostics
./install.sh
```

Run the installer as your normal user, **not `sudo`**. Keep this folder: the launcher and service reference it. Git may say the tagged checkout is in a detached state; that is expected for a fixed release. Open **Time Sheet Linux** from Applications and complete the desktop setup below.

## Desktop setup

The distro alone does not determine capture support. Open **Settings → About** or use `printf '%s / %s\n' "$XDG_CURRENT_DESKTOP" "$XDG_SESSION_TYPE"` to identify your session.

- **GNOME 50 Wayland:** the installer copies and enables the local GNOME helper. Save work and sign out/in once. If GNOME globally disables user extensions, enable them in the Extensions app. The helper's panel clock opens the app and offers pause/resume.
- **Plasma 6 Wayland:** install `swayidle` and the Plasma package containing `kwriteconfig6`. Run the installer in the Plasma session. Check **System Settings → Window Management → KWin Scripts** for *Time Sheet Linux Capture*. Sign out/in if needed. Move the pointer, then leave it still briefly for the idle observer to initialise.
- **Sway or Hyprland Wayland:** install `swayidle` and the compositor's IPC tool (`swaymsg` or `hyprctl`). A supported D-Bus lock service must accurately reflect your actual screen locker. Sway was exercised headlessly; Hyprland remains experimental.
- **X11:** install `python3-xlib` (Arch: `python-xlib`) on the host when using source. The AppImage bundles it. The window manager must support EWMH, the X server must expose XScreenSaver, and a supported D-Bus lock service must reflect your actual locker. App names can differ from Wayland, so review exclusions and assignment rules.
- **Other Wayland sessions:** use manual timers and entries. Do not force an X11 session variable to bypass compositor restrictions.

On Ubuntu/Debian, `sudo apt install swayidle` adds the idle observer; `sudo apt install python3-xlib` adds X11 bindings. Capture is unavailable or degraded when required focus, idle or lock evidence is missing; unknown time is not treated as active work. See the [compatibility matrix](LINUX_COMPATIBILITY.md).

## Check tracking

Open the app and confirm the header says **Tracking automatically**; app names should appear in Today after you use different windows. If paused, choose **Resume**. For source installs, run:

```sh
./run-timesheet --status
./run-timesheet --diagnose
```

For an AppImage, replace `./run-timesheet` with the path to the image. The status should be `active`; `paused`, `setup_required`, `degraded`, `error` or `stopped` need attention. A partial setup or an inactive tracker must not be used as proof of billable work.

## Troubleshooting

- **GNOME says Finish setup:** confirm GNOME 50 Wayland, run the relevant installer, enable user extensions, then sign out/in. Check `gnome-extensions info timesheet-capture@local`.
- **Plasma / Sway / Hyprland:** confirm the host tools above are installed and the session is the intended Wayland compositor. For Plasma, enable the KWin script. If the lock service is missing or does not represent your real locker, use manual time.
- **Tracker stopped:** open Settings and restart it, or on a system with user systemd run `systemctl --user restart time-sheet-linux.service`. Without user systemd, opening the native app starts a detached collector.
- **Missing GTK or libadwaita:** use a supported distro version or the packaged interface. Do not force GNOME extension version checks or install GTK with `pip`.
- **PDF says DejaVu fonts are missing:** the app searches its `resources/fonts` folder and `/usr/share/fonts/truetype/dejavu/`. Some distributions use a different font directory. From the source checkout, check `fc-match 'DejaVu Sans'` selects DejaVu Sans, then copy the system font files into the app's folder:

  ```sh
  mkdir -p resources/fonts
  cp "$(fc-match -f '%{file}' 'DejaVu Sans:style=Book')" resources/fonts/DejaVuSans.ttf
  cp "$(fc-match -f '%{file}' 'DejaVu Sans:style=Bold')" resources/fonts/DejaVuSans-Bold.ttf
  ```

  Install your distribution's `fontconfig` package if `fc-match` is unavailable. The AppImage includes the fonts.
- **Storage error:** free space or correct permissions, then restart. Review gaps and add genuine work manually; the app does not invent missing activity.

When reporting a problem, include your distribution, desktop/session, version and a sanitised error. Never upload your database or sensitive window titles to a public issue.

## Backup and restore

The default data folder is `~/.local/share/time-sheet-linux/`; source/AppImage installations honour `XDG_DATA_HOME`. The main file is `timesheet.sqlite3` and local daily backups are in `backups/`. Files are user-only but not encrypted. Copy backups to separate storage for disk-loss protection.

Settings offers a checked backup and restore and keeps a pre-restore recovery copy. Restoring an older backup can reintroduce deleted activity and replace newer work.

## Update and uninstall

### Source

The `v0.4.0-rc1` checkout is pinned to a tag: back up your data, then download or clone a newer release into a separate folder and run its installer. Keep the older checkout and a backup for rollback. GNOME helper updates may require sign-out/in.

To remove source integration while retaining the database and backups, run `./uninstall.sh` from the installed checkout. Remove personal data separately only if you intend to erase it.

### AppImage

Download the newer image and its checksums, verify them, close the app and stop the old service (`systemctl --user stop time-sheet-linux.service` when user systemd is available). Replace the image at the same persistent path, make it executable and run `--install`. Keep the older image and a data backup for rollback.

To remove its user integration while retaining data, run:

```sh
./TimeSheetLinux-x86_64.AppImage --uninstall
```


Optional TypeSafe suggestions require your own API key, stored in the desktop keyring. Flatpak uses the desktop Secret portal and network access for confirmed requests. See [package checks](../packaging/README.md).

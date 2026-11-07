# Time Sheet Linux

A private Linux desktop app for recording foreground app use, assigning activity to projects and creating client timesheets. Your data stays on your computer; an account or cloud service is not required.

![Today view with example data](docs/screenshots/today.png)

## Install

**Choose one version:**

| Version | Best for | What you get |
|---|---|---|
| [0.3.0 release candidate](https://github.com/peternewing/timesheet-linux/releases/tag/v0.3.0-rc1) | Trying the newest features | AppImage or Flatpak downloads; Plasma 6, Sway, experimental Hyprland and X11 capture; PDF reports and invoice drafts |
| [0.2.0 source on `main`](#install-stable-020-from-source-on-ubuntu-gnome) | The existing stable source version | GNOME 50 Wayland capture and CSV/HTML reports |

[Download AppImage](https://github.com/peternewing/timesheet-linux/releases/download/v0.3.0-rc1/TimeSheetLinux-x86_64.AppImage) · [Download Flatpak](https://github.com/peternewing/timesheet-linux/releases/download/v0.3.0-rc1/TimeSheetLinux-x86_64.flatpak) · [Download checksums](https://github.com/peternewing/timesheet-linux/releases/download/v0.3.0-rc1/SHA256SUMS)

The 0.3.0 downloads are **prerelease test builds**, not signed releases or a Flathub listing. Back up existing data before switching versions. [Compare desktop support](docs/LINUX_COMPATIBILITY.md).

### Quick start: 0.3.0 AppImage

For x86-64 Linux with glibc 2.39 or newer:

1. Download **TimeSheetLinux-x86_64.AppImage** and **SHA256SUMS** from the [release page](https://github.com/peternewing/timesheet-linux/releases/tag/v0.3.0-rc1). Place them in a folder you intend to keep.
2. Open a terminal in that folder and run:

   ```sh
   sha256sum --ignore-missing -c SHA256SUMS
   chmod +x TimeSheetLinux-x86_64.AppImage
   ./TimeSheetLinux-x86_64.AppImage --diagnose
   ./TimeSheetLinux-x86_64.AppImage --install
   ```

3. Open **Time Sheet Linux** from Applications. On GNOME 50 Wayland, sign out and back in once to load the helper. Other desktops may need additional packages or setup; check the [installation guide](docs/INSTALL.md#desktop-setup).

Keep the AppImage in that folder: the launcher and background service point to it. For Flatpak, other distributions, troubleshooting, updates and uninstalling, use the [complete installation guide](docs/INSTALL.md).

### Install stable 0.2.0 from source on Ubuntu GNOME

This version targets **GNOME Shell 50 on Wayland**. Run these commands in a terminal:

```sh
sudo apt update
sudo apt install git python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1
git clone https://github.com/peternewing/timesheet-linux.git
cd timesheet-linux
./install.sh
```

Run `./install.sh` as your normal user, not with `sudo`. Keep the cloned folder in place. Save your work and sign out and back in once, then open **Time Sheet Linux** from Applications. See the [guide](docs/INSTALL.md) for other versions and package managers.

## How it works

- Records the foreground application and separates idle, locked, excluded and missing periods from active work.
- Lets you create projects, assign activity, add manual time, review drafts and approve work before billing.
- Saves rates and report snapshots. Version 0.2 exports CSV and printable HTML; the 0.3 candidate also exports PDF reports and invoice drafts.
- Runs a per-user collector and supports local backups, restore, retention settings and app exclusions.

Invoice PDFs are **drafts**: they do not calculate tax or automatically mark work billed. A foreground app is evidence of usage, not proof that time is billable. Review activity before invoicing.

## Compatibility

| Desktop session | 0.2 stable | 0.3 candidate |
|---|---|---|
| GNOME 50 Wayland | Automatic capture | Automatic capture |
| Plasma 6 Wayland | Manual time | Capture helper + `swayidle` |
| Sway Wayland | Manual time | IPC + `swayidle` and a supported lock service |
| Hyprland Wayland | Manual time | Experimental IPC adapter; real GPU-backed testing pending |
| EWMH X11 | Manual time | X11 adapter and supported lock service |
| Other Wayland desktops | Manual time | Manual time until an adapter is available |

GNOME 50, Plasma 6 and Sway focus/idle were exercised in isolated sessions; X11 was checked on a virtual server. Hardware lock/suspend, Hyprland and additional distributions need further testing. Missing capture evidence is recorded as unknown, not active work. See [compatibility and test details](docs/LINUX_COMPATIBILITY.md).

## Privacy and data

By default, the database and backups are under `~/.local/share/time-sheet-linux/`; source and AppImage installs follow `XDG_DATA_HOME` if set. The Flatpak uses the default host data path and requires a host companion for capture. Data is local and user-only, but **not encrypted**. Window titles are off by default. No keystrokes, screenshots, clipboard contents or browser URLs are recorded.

Keep an external backup if you need protection from disk loss. Uninstalling integration keeps the database and backups. See [privacy and security](SECURITY.md) and [backup and restore](docs/INSTALL.md#backup-and-restore).

## Contributing

Run `/usr/bin/python3 -m unittest discover -s tests -v` and see [contributing](CONTRIBUTING.md), [testing](docs/TESTING.md) and [architecture](docs/ARCHITECTURE.md). Licensed under the [MIT License](LICENSE).

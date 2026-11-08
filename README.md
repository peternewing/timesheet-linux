# Time Sheet Linux

A private Linux desktop app for recording foreground app use, assigning activity to projects and creating client timesheets. Core tracking is local and requires no account. Optional Jev/TypeSafe can organise completed activity into reversible drafts under an explicit background policy, using your own API key. Uncertain work goes to a small decision inbox. Recording works independently and stays local.

![Today view with example data](docs/screenshots/today.png)

## Install

Install **Time Sheet Linux 0.5.0-rc1** using either the AppImage or terminal commands. This is a prerelease: desktop support is still being tested, and releases require checksum and provenance verification. Back up existing data before upgrading.

### Option 1: AppImage

For x86-64 Linux with glibc 2.39 or newer:

1. Download the [AppImage](https://github.com/peternewing/timesheet-linux/releases/download/v0.5.0-rc1/TimeSheetLinux-x86_64.AppImage) and [SHA256SUMS](https://github.com/peternewing/timesheet-linux/releases/download/v0.5.0-rc1/SHA256SUMS) into a permanent folder.
2. Open a terminal in that folder and run:

   ```sh
   sha256sum --ignore-missing -c SHA256SUMS
   ```

   Check that the AppImage says **OK**, then run:

   ```sh
   chmod +x TimeSheetLinux-x86_64.AppImage
   ./TimeSheetLinux-x86_64.AppImage --diagnose
   ./TimeSheetLinux-x86_64.AppImage --install
   ```

3. Open **Time Sheet Linux** from Applications. Keep the AppImage in that folder; the launcher and background service use it.

### Option 2: Terminal installation from source

For Ubuntu 24.04+ or Debian 13+, open a terminal and run:

```sh
sudo apt update
sudo apt install git python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-secret-1 python3-reportlab fonts-dejavu-core
git clone --branch v0.5.0-rc1 https://github.com/peternewing/timesheet-linux.git timesheet-linux-0.5
cd timesheet-linux-0.5
/usr/bin/python3 -m timesheet.diagnostics
./install.sh
```

Run `./install.sh` as your normal user, not with `sudo`, and keep the folder in place. Open **Time Sheet Linux** from Applications. For Fedora, Arch, openSUSE and desktop-specific setup, see the [complete installation guide](docs/INSTALL.md). The command above selects the fixed release tag for a reproducible installation.

On GNOME 50 Wayland, sign out and back in once to load the helper. Other desktops may need extra setup; see the [desktop instructions](docs/INSTALL.md#desktop-setup).

## Jev automation

Read [Let Jev organise your day](docs/AUTOMATION_GUIDE.md) for one-time setup, permitted context, focus, the exception inbox, caps and pause controls. Automatic drafts are experimental; real working-day accuracy has not been established.

## How it works

- Records the foreground application and separates idle, locked, excluded and missing periods from active work.
- Lets you create projects, assign activity, add manual time, review drafts and approve work before billing.
- Saves rates and report snapshots. Exports CSV, printable HTML, PDF reports and invoice drafts.
- Runs a per-user collector and supports local backups, restore, retention settings and app exclusions.

Invoice PDFs are **drafts**: they do not calculate tax or automatically mark work billed. A foreground app is evidence of usage, not proof that time is billable. Review activity before invoicing.

## Review your day

Choose **Review today** to select captured activity, assign tasks or **Ask Jev**. After saving, continue with the remaining activity; unused suggestions stay available during that review. **Open drafts** shows just the date you are reviewing. Today also shows a short summary of saved work by task.

In **Rules**, choose **Create assignment rule**, select a recorded app and choose its task. Check the plain-language preview and Save. Title matching and priority are optional. Use rules for apps dedicated to one task; use daily review for apps shared across projects.

See the [usability review and test evidence](docs/USABILITY_REVIEW.md).

## Optional suggestions

Add your own TypeSafe key in Settings, then choose a suggestion in an assignment or review queue. Each request shows what will be sent and asks for confirmation. Suggestions can be wrong and never approve time. Source and AppImage builds store the key using the desktop secret service. Flatpak uses its application-scoped Secret portal and network access for confirmed requests. See [review assistance](docs/JEV_IDEAS.md).

## Compatibility

| Desktop session | Automatic tracking in 0.5.0-rc1 |
|---|---|
| GNOME 50 Wayland | Supported |
| Plasma 6 Wayland | Capture helper + `swayidle` |
| Sway Wayland | IPC + `swayidle` and a supported lock service |
| Hyprland Wayland | Experimental; real GPU-backed testing pending |
| EWMH X11 | X11 adapter and supported lock service |
| Other Wayland desktops | Manual time until an adapter is available |

GNOME 50, Plasma 6 and Sway focus/idle were exercised in isolated sessions; X11 was checked on a virtual server. Hardware lock/suspend, Hyprland and additional distributions need further testing. Missing capture evidence is recorded as unknown, not active work. See [compatibility and test details](docs/LINUX_COMPATIBILITY.md).

## Privacy and data

By default, the database and backups are under `~/.local/share/time-sheet-linux/`; source and AppImage installs follow `XDG_DATA_HOME` if set. The database is local and user-only, but **not encrypted**. Optional TypeSafe suggestions send selected application names, active client/project/task names and any context you choose to TypeSafe after a separate confirmation. Window titles are off by default. No keystrokes, screenshots, clipboard contents or browser URLs are recorded.

Keep an external backup if you need protection from disk loss. Uninstalling integration keeps the database and backups. See [privacy and security](SECURITY.md) and [backup and restore](docs/INSTALL.md#backup-and-restore).

## Development direction

The [automation source of truth](docs/AUTOMATION_ROADMAP.md) governs future improvements: Jev should organise the day in the background and ask only about meaningful exceptions.

## Contributing

Run `/usr/bin/python3 -m unittest discover -s tests -v` and see [contributing](CONTRIBUTING.md), [testing](docs/TESTING.md) and [architecture](docs/ARCHITECTURE.md). Licensed under the [MIT License](LICENSE).


## Verify release provenance

The main-branch package workflow produces a GitHub/Sigstore provenance bundle.
For a release listing `provenance.sigstore.json`, download it alongside the binary
and install the official GitHub CLI, then run from the source checkout:

```sh
python3 packaging/verify_release.py TimeSheetLinux-x86_64.AppImage --bundle provenance.sigstore.json --source-commit FULL_SOURCE_SHA_FROM_RELEASE
```

Use the Flatpak filename to verify that bundle instead. A successful verification
checks the package digest, repository, trusted main workflow, source SHA and hosted
runner identity. Checksums alone detect corruption, not publisher identity. Do not
execute the package if verification fails. The release notes must identify the
source commit and passing trusted build; a listed bundle alone is not verification.
This is workflow provenance, not a personal code-signing certificate.

See [automation setup and upgrade behaviour](docs/AUTOMATION_GUIDE.md). Back up data before upgrading. Older versions can read core
v3 time records but do not implement the optional automation tables; turn off
automation and keep a pre-upgrade backup when rolling back.

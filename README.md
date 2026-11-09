# Time Sheet Linux

**Set up once. Work as usual. Save a clear record of your day.**

Time Sheet records Linux app activity and lets Jev organise it into simple activity
categories. Clear cases happen automatically; uncertain activity needs one choice.
Core recording stays local and works without AI. Jev uses your own TypeSafe key.

![The simple Today screen, using synthetic example data](docs/screenshots/today.png)

## Start in four steps

1. Click the ready-made categories you want.
2. Choose app names only, or optional local title matching.
3. Click **Use my saved key**, **Paste key and connect**, or **Continue without AI**.
4. Click **Start**. You can then work as usual.

No project names, rates, rules or typed setup fields are required. There are only
three everyday destinations: **Today**, **Past days**, and **Settings**. Choose a
category once per app for the selected day; **Save day record** produces a PDF of the recorded day.

The record separates captured app use, AI estimates, your choices, away time and
capture gaps. It is evidence of app activity, not independent proof of completed
outputs or productivity. Simple-flow categories are non-billable drafts.

## Install 0.6.1-rc2

This is a prerelease. Back up existing data before upgrading and reopen any old
app window afterwards. Existing time, projects and saved reports are preserved.

### AppImage — x86-64, glibc 2.39 or newer

Download the AppImage, SHA256SUMS and provenance bundle from the
[release page](https://github.com/peternewing/timesheet-linux/releases/tag/v0.6.1-rc2).
In the download folder:

```sh
sha256sum --ignore-missing -c SHA256SUMS
```

Verify publisher provenance before executing. From a source checkout, with the
official GitHub CLI installed:

```sh
python3 packaging/verify_release.py TimeSheetLinux-x86_64.AppImage --bundle provenance.sigstore.json --source-commit FULL_SOURCE_SHA_FROM_RELEASE
```

Then keep the image in a permanent folder and install its launcher:

```sh
chmod +x TimeSheetLinux-x86_64.AppImage
./TimeSheetLinux-x86_64.AppImage --diagnose
./TimeSheetLinux-x86_64.AppImage --install
```

### Source — Ubuntu 24.04+ / Debian 13+

```sh
sudo apt update
sudo apt install git python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-secret-1 python3-reportlab fonts-dejavu-core
git clone --branch v0.6.1-rc2 https://github.com/peternewing/timesheet-linux.git timesheet-linux-0.6
cd timesheet-linux-0.6
./install.sh
```

Run the installer as your normal user. Keep the source folder in place.
For Flatpak, other distributions, capture helpers and rollback, use the
[installation guide](docs/INSTALL.md).

## Daily view

Click a time card to see its matching information below. Recorded app use shows
top activities ranked by total active time. All counters display hours, minutes
and seconds and refresh together. Daily choices also cover later recorded use
of the same app that day; existing explicit assignments stay intact.

Click **Organise my day** to prioritise Jev's pass through that day. Clear matches
become drafts; only uncertain apps need your choice. **Assign** beside an activity
lets you choose its category directly. Equivalent decisions are reused.

**More actions** holds task timers, manual time and detailed project assignment.
In **Settings**, enable **Show advanced tools in sidebar** for regular access to
projects, rules, history and reports. These use the same records; setup stays simple.
Expandable help explains what Jev and each set of tools actually do.

## Existing users

Open the new app and use **Set up in 4 steps**. Compatible native/source upgrades preserve an existing enabled data policy.
An off policy stays off; incompatible installation switches require setup. The saved personal key can be
reused with one click; it is never embedded in public packages.

Projects, assignment rules, billing reports, detailed Jev controls, privacy,
backups and restore are under **Settings → Advanced tools**. These are optional;
the everyday record does not require them. Older records remain intact.

## Privacy and limits

App names only is the simplest option. Optional titles stay local: only matching
category IDs and word counts are sent. Simple Jev requests use generic category
names, not private project/client names. Raw titles, paths, screenshots, times,
rates and entry descriptions are not automatically added. You choose whether to
remember corrections. Jev requests use your own TypeSafe account and usage caps;
unknown usage pauses sending. API failures do not block recording.

TypeSafe processes requests in the US; standard retention has no fixed published
duration. ZDR is by request. See [security](SECURITY.md) and the setup's expandable
data details. Saving/connecting a key alone does not enable activity sending.

Flatpak requires the host capture companion. Keep its app window open for
continuous Jev processing until background behaviour is verified on your desktop.
GNOME 50 Wayland is supported; Plasma 6, Sway and X11 need their documented helpers.
Hyprland remains experimental. Hardware and screen-reader acceptance remain open.

## Development

[Simplicity review](docs/SIMPLICITY_REVIEW_0.6.md) ·
[Accepted roadmap](docs/AUTOMATION_ROADMAP.md) ·
[Architecture](docs/ARCHITECTURE.md) · [Testing](docs/TESTING.md)

Run `/usr/bin/python3 -m unittest discover -s tests -v`. Follow [AGENTS.md](AGENTS.md)
and [contributing](CONTRIBUTING.md). Licensed under the [MIT License](LICENSE).

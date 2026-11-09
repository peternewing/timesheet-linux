# Time Sheet Linux 0.7.0

Official personal/work screen-time release. Core tracking and screen-time
insights work locally without AI. Optional Jev organisation uses your own
TypeSafe key and explicit sending policy.

- Simple four-step setup and Today, Past days and Settings navigation.
- Weekly/hourly observed screen time, top apps and private CSV/PDF exports.
- Personal, Work and Unsorted spaces, optional local schedules and reversible corrections.
- Eight activity types, conservative local installed-app labels and scoped AI corrections.
- Background organisation, durable retry/cache/usage guards and explanations.
- Responsive background insights and improved closed-dialog resource cleanup.
- Existing records, exclusions, explicit assignments and usage limits preserved.

## Downloads

`TimeSheetLinux-x86_64.AppImage` targets x86-64 Linux with glibc 2.39 or newer.
`TimeSheetLinux-x86_64.flatpak` uses GNOME Platform 49. Flatpak capture requires
the host companion described in [the installation guide](https://github.com/peternewing/timesheet-linux/blob/v0.7.0/docs/INSTALL.md).
Both packages include PDF export and the optional TypeSafe client dependencies.

Download `SHA256SUMS` and `provenance.sigstore.json` alongside your chosen package.
Run `sha256sum --ignore-missing -c SHA256SUMS` and verify provenance before executing:

```sh
python3 packaging/verify_release.py TimeSheetLinux-x86_64.AppImage --bundle provenance.sigstore.json --source-commit FULL_SOURCE_SHA_FROM_RELEASE
```

The release's source SHA and build link are appended below during publication.
Back up existing data before upgrading. Keep the installed file/folder in place
and reopen the app after installing the new version. See the installation guide
for desktop capture support, dependencies, source installation and rollback.

## Validation and limits

The preceding source candidate passed 328 core tests, Ubuntu 22.04/24.04 protocol
checks, scaled GTK workflows, AppImage and Flatpak build/runtime checks. This
release publishes only after its own core/UI, packaging and main-build provenance
verification pass. Earlier sustained and synthetic-provider evidence retains its
original source scope in the repository's 28-category reassessment.

Detected foreground use depends on the desktop idle signal: passive reading/video
may be marked away. It is not a validated screen-on, attention or productivity
measure. AI creates reversible drafts, never approved bills. Real-day accuracy,
novice/Orca acceptance and broader physical-desktop coverage remain unverified;
release status does not certify those results. Capture and screen-time insights
remain useful without a TypeSafe key. No new paid provider tests were performed.

# Package checks

The AppImage targets Ubuntu 24.04's glibc baseline. It bundles the optional
TypeSafe client dependencies, including libsecret; it still needs a running
desktop keyring on the host. `check_runtime.py` checks imports, the libsecret
schema API and TLS trust roots without creating a database or sending a request.

The Flatpak includes network permission for explicitly confirmed TypeSafe
requests. Its launcher pins `SECRET_BACKEND=file`, using libsecret's encrypted
application-scoped store and the desktop Secret portal. It does not request
`org.freedesktop.secrets` access. Missing portal support must fail closed.

`verify_secret_portal.py` runs on a private D-Bus session, using a synthetic
portal and disposable values. It checks unavailable-portal failure, actual
libsecret store/read/remove, and absence of the plaintext key in stored files:

```sh
dbus-run-session -- /usr/bin/python3 packaging/verify_secret_portal.py
# After installing a locally built test Flatpak:
dbus-run-session -- /usr/bin/python3 packaging/verify_secret_portal.py --flatpak org.local.TimeSheetLinux
```

These tests exercise the real libsecret client and sandbox transport, but do not
certify every desktop portal implementation or make a live TypeSafe request.
The package workflow runs them against the native libraries, AppImage AppDir
and installed Flatpak bundle. It also smoke-tests the packaged GUI and PDFs.

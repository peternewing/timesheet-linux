# Privacy and security

Time Sheet Linux stores activity and billing data in a local SQLite database. The database is not encrypted; protect your Linux account and backups appropriately. Window-title collection is off by default. The GNOME helper provides focused-window and idle/lock information to processes in the same user session via D-Bus.

Do not attach your real activity database, report exports, tokens or private window titles to public issues. Use synthetic examples. To report a vulnerability, describe the affected version and a minimal reproduction without personal data.

Optional TypeSafe suggestions transmit selected application names and all active client/project/task names to TypeSafe after a per-request confirmation. They do not automatically send window titles, descriptions or timestamps. Optional user-edited context is shown for confirmation and may contain whatever the user enters. The user's own API key is stored in Secret Service (or Flatpak’s application-scoped Secret portal store), outside the database and backups; remove it in Settings before uninstalling. Optional local choices and categories are stored in the database and may remain in backups after they are cleared. Flatpak has network permission for optional confirmed requests. See docs/JEV_IDEAS.md for prototype limitations.

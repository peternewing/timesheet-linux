# Privacy and security

Time Sheet Linux stores activity and billing data in a local SQLite database. The database is not encrypted; protect your Linux account and backups appropriately. Window-title collection is off by default. The GNOME helper provides focused-window and idle/lock information to processes in the same user session via D-Bus.

Do not attach your real activity database, report exports, tokens or private window titles to public issues. Use synthetic examples. To report a vulnerability, describe the affected version and a minimal reproduction without personal data.

Optional TypeSafe decisions send permitted app names and offered task labels under
an explicit per-request confirmation or standing background policy. Simple setup
restricts offered labels to intact app-created generic activity categories; adding
client projects does not add their names to that scope. Optional advanced project
requests can include client/project/task names. Guidance and explicitly remembered
examples are sent only when the applicable policy permits them. Raw titles,
timestamps, rates and entry descriptions are not automatically added; approved
local title matching sends task IDs and counts rather than title text. Saving a
key alone is not consent to background activity requests.

The user's key is stored in Secret Service or Flatpak’s scoped Secret portal,
outside the database and backups. Remove it in Settings before uninstalling.
Screen-time statistics, Personal/Work labels, schedule clock rules, installed-app
metadata, health checks and review-effort counters require no key or network.
Desktop metadata is never executed to classify an app. Generic local drafts do
not establish client intent or billing approval.

Local choices, examples, space labels and category provenance can remain in old
backups after they are cleared from the active database. The optional read-only
evaluation-template CLI writes a new private 0600 file, leaves labels unconfirmed
and sends nothing. App names in that file can themselves be sensitive. Paid
evaluation rejects unlabelled cases and requires a separate deliberate request
after exact payload preview. See [the current review](docs/PERSONAL_WORK_REASSESSMENT_2026-11-09.md)
for evidence and open acceptance limits.

# Optional TypeSafe review assistance

## Everyday use

Choose **Review today** on Today, or **Review suggestions** in Calendar. The local review shows
nearby unassigned blocks as proposed sessions, sorted to bring unfamiliar and
longer sessions forward. Grouping never fills the gaps between blocks. Select
individual blocks to split or combine sessions; assignment, personal marking
and rule creation always need a user action. Existing assignment undo remains
available.

The review highlights missing descriptions, missing billable rates and capture
gaps, and flags an application previously assigned to more than one task. It
suggests an optional future-only rule after three consistent explicit
assignments. These are prompts to check, not evidence that past work was wrong.
An assignment form shows a project-budget warning based on saved entries.

## Optional TypeSafe suggestions

Source and AppImage builds let each person save their own TypeSafe API key in the
freedesktop Secret Service keyring. Flatpak uses the desktop Secret portal and an encrypted application-scoped store; it fails closed if the portal is unavailable. No shared developer key is included. In an
assignment, use **Suggest a task with TypeSafe** and inspect the preview before
confirming. It includes selected application names, active client/project/task
names, optional category labels and any context the user deliberately enters.
Window titles, entry descriptions and timestamps are never added automatically.
The user may edit out identifying details or leave optional context empty.

Jev chooses an existing task or “none” and may flag that activity could be
personal. The indication does not mark time personal. If the two leading task
probabilities differ by less than 15 percentage points, the form asks the person
to choose one or neither. This is a provisional UI heuristic, not evidence of
accuracy or a calibrated automation threshold. All suggestions need review;
none approves, bills, deletes or creates an invoice.

In Settings, optional categories map short names to existing tasks. The mapping
is previewed before saving, and appears in the exact outgoing-data preview.
Users can also opt in to remember an app-to-task choice locally. If they save an
AI-assisted choice with that option enabled, aggregate kept/changed counts and
probability buckets are saved locally. Small, self-selected samples do not prove
accuracy and never enable automatic approval. Settings can clear saved local
choices and feedback; categories can be removed separately. Existing database
backups may retain old choices and categories.

## Optional batch mode

In Review suggestions, select up to ten application blocks, expand the optional
AI section and choose a request cap. The confirmation lists every application
and task/category name to be sent. Each request is limited to 32,000 bytes;
actual costs depend on the provider's token accounting. There are no automatic
retries. Cancel stops later requests; an in-flight request may still finish.
Results stay in the review window and each must be opened and saved separately. Saving refreshes the remaining activity and keeps unused results for that review without another request. Closing the review clears these temporary results.
No title or optional context is included in batch mode.

## Status and limits

Core tracking and local review work offline. TypeSafe requests go directly to
`https://api.typesafe.ai/v1/systemone` after confirmation and can incur charges
on the user's own account. The prototype requires libsecret and an unlocked
keyring. AppImage and Flatpak package configurations include libsecret; Flatpak uses network access and the Secret portal. Package builds and isolated encrypted-storage checks pass in CI; real desktop portal compatibility still benefits from broader testing. Removing the database
or uninstalling the app does not remove the keyring entry; remove it in Settings.

Unit and isolated GUI tests use fake credentials and fake API responses. No real
TypeSafe key, live API request, provider billing, production activity or real
screen-reader workflow has been tested. Evaluate suggestions with consented,
representative examples before considering any more automation.

TypeSafe's data handling: https://help.typesafe.ai/articles/5974925716
API reference: https://api.typesafe.ai/redoc
Pricing: https://help.typesafe.ai/articles/5187202169-how-much-does-jev-cost

# One-click Jev and accessible tools — 0.6.1-rc2

User direction: let Jev organise the whole day; review only uncertain activity.
Keep setup simple, make retained functionality accessible, and put Assign beside
activities. Card text must activate its button without becoming selectable.

## Behaviour

Organise my day queues a bounded ten-minute priority pass in the existing independent
worker. It processes settled recorded activity for the selected day within the
already-authorised period (maximum seven days). It never extends consent, changes
sending fields/mode, resets a pause or overrides request/token limits. Off or an
unconnected installation opens setup. A paused worker opens its recovery actions.
Progress updates locally; closing the window lets processing continue.

Equivalent requests reuse the validated durable cache, including ambiguous results.
Clear, supported decisions become reversible draft categories. Uncertain results
remain one app/day choice, including separated periods. Jev is used to select a
category, compare alternatives, assess sufficient evidence and infer a limited
activity kind. Permitted correction examples, focus and derived local clues can
support decisions. App names alone cannot establish intent in a general browser,
completed outputs, productivity or billability. Broad labels remain non-billable.

Assign is available beside each ranked app: five initially visible, remaining apps
in More activities. It can handle pending AI work and correct editable generic AI
drafts. Explicit user entries, local rules, approved and billed records remain
protected. All direct daily choices retain existing transactional checks and undo.
Already-assigned or not-yet-settled activity explains the applicable next action.

Settings has a persistent Show advanced tools in sidebar choice, default off.
Projects/tasks, rules, history and reports remain in the same window and use the
same records. More actions on each day also opens task timers, manual time and
full captured-activity/project assignment. Detailed activity returns to the summary
with one button. No change to the four-step setup or normal three destinations.
Optional help explains Jev and the retained advanced tools; there are no new setup
fields, privacy switches or inference modes on ordinary day screens.

## Fresh second review

- Priority jobs share the single daemon lock; the UI never starts a second engine.
  Worker latency remains independent of capture. Bounded scanning handles large
  days, cached jobs drain promptly, future retries/backoff keep normal pacing.
- Request policy is checked again after acquiring the write lock. A test revokes
  consent at that precise boundary and confirms the queued request cannot win.
  Saved priority metadata contains local times and a policy digest, no key/content.
- Newer clicks supersede older scan updates. Expiry does not loop or resend failed
  or uncertain decisions. Existing caps, unknown-usage and model-pinning gates apply.
- Found and fixed a midnight edge: a day pass clips a crossing observation to the
  selected date, and an applied fragment must not hide its remaining other-day
  fragment from later discovery. Both cases have regression coverage.
- Direct Assign includes pending work but stale in-flight decisions cannot overwrite
  the user's choice. AI-only app days can be corrected and undone without gaps.
- Card labels cannot receive pointer targeting; value and caption clicks reach the
  native accessible button. Other body text keeps its selection behaviour.
- Confirmed all retained sidebar pages open under simple mode and the sidebar
  preference survives navigation. Detailed activity is protected from summary tick
  replacement; retained live project/history counters still refresh in simple mode.

## Evidence

242 offline unit/regression tests passed, including 15 whole-day organiser tests.
68 default-flow GTK checks at normal and 200% scale cover setup, real mouse clicks
on card text and Assign, whole-day progress, consolidated exceptions, optional
sidebar pages, detailed assignment return, second counters, correction and export.
The existing 53 scaled advanced mouse/keyboard checks and separate worker-process/
concurrent recording test passed. Public CI additionally exercises the other
retained UI/capture/key-storage paths and both core OS matrices.

No real recorded activity or new live inference was sent for testing. Synthetic
fixtures do not establish real-day accuracy or human accessibility acceptance.
Trusted-main CI, verified package provenance/hashes, public release files and local
upgrade are final delivery gates, recorded in release notes when completed.

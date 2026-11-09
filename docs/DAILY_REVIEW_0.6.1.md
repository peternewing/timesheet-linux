# Daily choices and live counters — 0.6.1-rc1

User request, 9 November 2026: choose once for like activity throughout the day,
synchronise accurate second counters, restore top activities, and make the three
statistic cards show their relevant information below. Preserve the simple default.

## Result

- One review item per application and selected calendar day, combining separated
  observations and case variants. The question states that its choice also applies
  to later recorded use that day. Exact included periods can be expanded.
- One click categorises eligible unassigned periods and replaces draft, non-billable
  Jev estimates for that app/day. Existing explicit assignments, rules, approved or
  billed entries are protected. Different days and different apps stay separate.
- Later settled observations reuse that explicit local daily choice without another
  Jev request. Local capture handles it even with AI unavailable. Leaving a type
  uncategorised is also one daily decision. Nothing fills gaps or assigns live,
  unsettled observations. Individual category edits remain possible.
- Counters show HH:MM:SS. The simple view samples one shared timestamp each second;
  the header timer, running task totals, captured totals and detail values derive
  from timestamps rather than adding a guessed tick. Delayed UI frames catch up.
  Collector polling is aligned to second boundaries to avoid accumulating loop delay.
  Totals reflect durable observations; no unobserved activity is extrapolated.
- The statistic cards are actual buttons with a visible selected state. Recorded app
  use shows the top five apps by combined active time and expandable periods.
  Automatic organisation shows AI/rule entries. Chosen by you shows manual/user
  entries and a running timer. Each empty state explains why no rows exist.
- Rankings, durations and the timeline refresh together. Personal/excluded app names
  do not appear in top activities. Details are inline, with no extra settings page.

## Review, integrity and privacy

Daily choices and their undo links use additive tables; core schema remains v3.
Writes preflight frozen source fragments and AI revisions in an immediate transaction,
then save allocation snapshots and the local daily policy together. A competing
manual edit makes the review stale instead of partially applying it. In-flight AI
cannot overwrite a completed human decision. All simple allocations stay drafts and
non-billable. Undo restores prior estimates and revokes a daily default; undoing a
later continuation also stops that default from immediately recreating the entry.
Remembered AI examples remain separate from time-entry undo as in earlier versions.

Local continuation reads one allocation snapshot per day and writes at most 200
periods per pass. Source deletion/retention removes copied daily app identities and
undo metadata while preserving saved time entries. New daily decisions add no data
to outgoing Jev requests. No live API calls or real user data were used in testing.

An authorised compatible native/source upgrade transfers only installation ownership
of an already-enabled policy after stopping the old worker. Data choices, caps,
processing period and paused state stay unchanged. Off stays off; another installation's
policy is not adopted. Previous version metadata is parsed, never executed. Other
package/source switches still require explicit setup when compatibility cannot be
established. Existing records and key storage are preserved.

## Validation

- 226 unit/regression tests, including full-day grouping, Unicode case folding,
  future same-day reuse, next-day separation, skip, stale atomic groups, AI races,
  protected manual entries, estimate replacement/undo, bounded continuation, source
  retention, compatible upgrades, ranked totals and timer boundary/delayed ticks.
- 41 default UI checks at normal and 200% scale, including real mouse clicks on all
  three cards; populated and empty filters; one answer for separated periods; and
  exact shared-clock values at +0, +1, +3 and +8 seconds.
- Retained 53 scaled mouse/keyboard workflows and focused automation/daily-review/
  rules checks; independent decision-worker/concurrent-recording process test.
- Each GUI run has a unique test application ID and must reach its completion
  marker, preventing parallel virtual displays from activating another test process.
- Refreshed synthetic screenshots, compilation and whitespace checks.

CI, trusted main package provenance, public asset digests and the local installation
must be verified at the final source commit before reporting delivery complete.
Real-day/novice/hardware/screen-reader acceptance remains separate from these tests.

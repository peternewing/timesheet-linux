# Architecture

The app is a native GTK 4/libadwaita interface over a local SQLite store, with an independent Python collector and a small GNOME Shell extension. The core does not require an application server or cloud service. Optional on-demand TypeSafe suggestions send application and task names and any explicitly entered optional context directly to TypeSafe after user confirmation; the user supplies a key stored in Secret Service. Flatpak uses network access and an application-scoped Secret portal store.

```text
GNOME foreground window + idle/lock state
                    |
              session D-Bus
                    |
        collector privacy and time model
                    |
      durable activity + explicit capture gaps
                    |
       settled rules -> draft task entries
                    |
          user review and approval
                    |
     frozen report -> external invoice reference
```

The GNOME helper reads focus and idle state through the compositor. A panel menu opens the app and invokes its pause/resume actions. It does not persist activity. The Python collector filters titles/exclusions before persistence, checkpoints live segments every poll, and reclassifies the idle tail when the threshold is reached. Sleep, clock changes, source failures and interruptions do not become inferred billable work.

Activity evidence and task allocations are distinct. SQLite transactions prevent overlapping allocations and make bulk operations atomic. Rules fill uncovered intervals only after the idle boundary settles; they do not overwrite manual edits or approve work. New rules apply forward unless the user explicitly reapplies them to a past calendar day.

The UI and collector use short SQLite transactions and independent connections with a busy timeout. The collector lock prevents duplicates. A small independent health file communicates persistence failures even when the database cannot accept writes. The user systemd service supervises the collector; graphical autostart and direct launching provide a fallback.

Time entries have revisions, origins and optional evidence links. Edits revoke approval. Split/merge/delete/assignment changes have reversible snapshots; undo refuses if subsequent protected changes would be overwritten. Rate/currency and report line snapshots preserve financial history. Invoice corrections are explicitly recorded and reopen the corresponding entries as drafts while retaining the original report.

Backups use SQLite's online backup API. Restore validates a temporary upgraded copy and retains a rollback copy of live data. Schema version 3 adds automatic activity handling, undo and report billing history while preserving the initial personal MVP database format.

## 0.3.0 capture adapters

`timesheet.capture` selects GNOME, KDE, Sway, Hyprland, X11 or unsupported from the graphical
session. The collector consumes the same `(app, title, idle_ms, locked)` tuple for
all sources and retains existing privacy, idle trimming and gap semantics. The KDE
receiver validates the KWin D-Bus owner and expires stale heartbeats. Its swayidle
observer runs with an empty configuration and is closed on pause/collector exit.
Unknown idle/lock state produces unknown activity, never assumed work. Adapters are
optional; import/connection failures do not crash durable collection. No database
schema migration accompanies this candidate.


Saved reports can be exported using ReportLab as PDFs or invoice drafts. The export
reads frozen rows and does not change billing state. AppImage bundles the runtime
and installs services against the persistent image path. The Flatpak contains the
UI and PDF runtime, accesses only the default host data folder, and relies on a
separately installed host capture companion. The Flatpak cannot install or stop the
host service from its sandbox; backup restore requires the collector to be stopped.


## 0.5 decision service

The user-approved [automation roadmap](AUTOMATION_ROADMAP.md) governs product
changes. `decision_context` builds exact permitted payloads and local fingerprints;
`decision_policy` routes complete typed results. `automation_store` owns additive
v3-compatible optional queue/context/usage/audit tables. `automation_worker` runs
in a separate process/service; network calls never enter the collector.
`automation_ui` contains consent, focus, explanations and the exception inbox.

A completed interval is split on local days, explicit focus and rule boundaries.
A rule wins locally. A conflicting rule cannot be bypassed by an AI focus default.
Jobs carry frozen context and are revalidated before request reservation and
transactional application. Lease recovery never silently re-sends unknown usage.
A strict request reservation and reported-token ledger survive restarts.
Equivalent inputs reuse validated results; the first actual model is pinned.
Different paths/versions cannot execute another installation's saved policy.

Human batch corrections freeze their previewed IDs and preflight every item
before writing; updates, examples, audit and undo commit together. The worker
creates drafts only. Source retention prunes copied context. Restore disables
automation. `evaluate` separates paid labelled inference from offline replay;
`updates` reads release metadata without executing downloads. The package workflow
attests trusted main builds; `packaging/verify_release.py` delegates cryptographic
verification to the official GitHub CLI.


## 0.6 everyday product

`simple_ui` provides the default wizard/day/review/settings screens. `simple_setup`
creates owned generic categories transactionally without adopting user projects.
`simple_store` performs strict reversible human assignments/corrections.
`day_record` reads one coherent local snapshot and exports a non-financial PDF.
Old business workflows remain behind Advanced tools and retain regression tests.

The policy carries an explicit restricted category ID list. Context must validate
those IDs against intact app-created presets; it never falls back to all client
tasks. Requests carry a broad-app-type scope, distinct questions and action gates.
This can label specialist application use without claiming work intent. General
apps can still return none. Original project/focus/personal gates remain intact.
All simple-flow category allocations are non-billable drafts. Local rules targeting
any active project still take precedence; filtering offered generic tasks must not
filter out that precedence check.

## November review module boundaries

The accepted [roadmap](AUTOMATION_ROADMAP.md) and current
[review/acceptance plan](IMPROVEMENT_PLAN_2026-11-09.md) govern these development changes.

- `decision_contract.py` validates provider/cache results for both the worker and evaluator.
- `decision_memory.py` stores and retrieves the eight most recent permitted app/context
  examples using an indexed Unicode case-folded key. A correction is guidance, not training.
- `automation_status.py` derives local heartbeat, queue/usage facts and explanations;
  it never accesses a key or performs network requests.
- `setup_ui.py` owns the existing four-step setup, separated from daily rendering/review.
- `benchmark.py` creates a disposable synthetic database and records bounded discovery
  timings/RSS. `evaluate --compare` compares saved responses under the current routing
  policy on identical labelled inputs; it cannot promote a model.

Routing has an explicit version separate from data-consent version. New completed jobs
record it; old jobs retain unknown version zero. Change the routing version when changing
execution semantics and preserve the code/fixtures needed to replay historical policies.
The additive example key, routing-version field and minimal local rule-assignment table
preserve existing records. Rule snapshots copy no raw titles or application identities.
Repository initialisation serialises migration and must not commit an existing caller
transaction. Unknown usage remains unresolved across calendar days until acknowledged.

## Personal and work screen time

`screen_time` unions captured intervals before calculating observed screen time,
app rankings, sessions, hourly windows and comparable weeks. Private observations
mask app names. Conflicting apps or capture gaps are not invented usage; manual
entries never inflate screen totals. Read helpers share one SQLite snapshot with
the caller. Hourly attribution visits disjoint intervals directly rather than
rescanning each day for every hour. Local days can have 23 or 25 elapsed hours.

`screen_spaces` keeps independent local Personal/Work/Unsorted intervals. Explicit
switches and finite past-period corrections have revision-guarded Undo. Optional
schedules preserve their history and a local TZif clock-rule snapshot, so later
system-zone changes cannot relabel earlier schedule periods. Manual markers
override schedules. Old schedule rows without saved rules retain their legacy
local-clock semantics rather than invent historical timezone evidence.

`local_types` reads exact Gio desktop identities and declared Freedesktop
categories. Broad, conflicting and unknown-collision identities abstain. Catalogue
refresh publishes a complete snapshot under a non-blocking refresh lock. The
collector uses bounded local allocation independently of the optional AI worker;
both recheck source/privacy/presets, explicit choices, rules and occupied time.
Provenance and Undo commit with non-billable app-type drafts. Undo suppresses the
original source to avoid immediately recreating that same local inference.

`screen_ui` provides native optional insight/context controls inside the existing
three-destination experience. `screen_export` produces a title-free local CSV;
`day_record` uses the canonical interval union for its screen-time PDF.
`review_metrics` stores only content-free simple-review counters and active-window
time. It is a workflow proxy, not AI accuracy or cognitive-effort measurement.
`evaluation_template` opens an explicitly selected database read-only and produces
unlabelled private cases. `evaluate` preflights all labels before key access.

Request contract version, routing policy, provider model and user consent are
separate. New jobs and cache identities include the local request version; stale
contract answers cannot apply. Historical versions remain unknown, and saved
entries are not rewritten. See the [iteration/reassessment](PERSONAL_WORK_REASSESSMENT_2026-11-09.md)
for the evidence and remaining gates.

`screen_reader` opens a separate read-only, query-only connection for insight
calculation. It does not query window titles, create a Store, migrate a database,
unlock a key or touch the network. The GTK thread retains controls while a single
reader runs; filter/label revisions supersede older results, Close cancels SQL
work, and interval copies are discarded before returning UI aggregates. Native
responsiveness/cancellation/race scenarios are tested separately from statistics.

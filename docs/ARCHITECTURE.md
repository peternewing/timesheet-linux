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

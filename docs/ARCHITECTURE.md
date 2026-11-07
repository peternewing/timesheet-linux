# Architecture

The app is a native GTK 4/libadwaita interface over a local SQLite store, with an independent Python collector and a small GNOME Shell extension. It has no application server or cloud dependency.

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

# 0.6 simplicity rebuild

User direction, 8 November 2026: **simplicity**. Step-by-step screens, clickable
options, no required typing, automatic Jev organisation and a useful day record.
This is the current UX direction alongside the accepted AUTOMATION_ROADMAP.md.
The 0.5 category report remains historical evidence; no universal 9/10 claim is made.

## What changed

| Before | Default in 0.6 |
|---|---|
| Seven equally prominent destinations | Today, Past days, Settings |
| Busy header with timer, editing, help and refresh actions | Recording status and Pause; an existing running timer remains accessible |
| Client/project/task and optional rate forms before useful organisation | Four ready-made activity categories; click the ones you want |
| Long automation form with modes and many settings | Four steps: categories, privacy, saved/pasted personal key, Start |
| Repeated assignment forms | One category click per unclear period; previewed matching periods optional |
| Business reports as the main export route | Save day record → Save PDF, with a default filename |
| Advanced details mixed into everyday work | Expandable details and optional Settings → Advanced tools |

No category names, client names, rates, rules, dates or API-key text need typing in
the saved-key setup. A missing key can be pasted with one button; users still need
their own account/key. Connecting alone does not enable recorded-activity sending.
Start is the explicit action enabling the selected background policy.

The simple default uses generic app-activity categories, not client projects.
Specialist application functions can support a broad label such as creating or
communicating. General browsers/terminals may remain ambiguous. These are estimates
of app activity, including possible personal use; they do not establish work intent,
productivity, a completed output or a billable client assignment. Original strict
project/personal/focus decision gates remain in the advanced workflow.

All simple-flow category allocations are non-billable drafts. Specific existing
local rules still take precedence. Existing client projects, saved reports,
financial snapshots, timers and detailed editing remain available and intact.

## Fresh second review and fixes

- Found that treating generic labels as proof of work made even specialist apps
  uncertain. Added an explicit broad-app-type request scope with distinct questions
  and limited non-financial routing. Kept uncertain general apps unassigned.
- Filtering generic task options initially risked hiding rules aimed at other
  projects. Rule precedence now considers all active task targets before filtering.
- Context validates every selected ID against intact app-owned presets and never
  falls back to private client/task lists. Generic requests use category names only.
- Existing same-named user projects are never adopted or overwritten. Setup creates
  its own owned project. Changed presets can be rebuilt without overwriting old work.
- Human category corrections preserve captured evidence, increment revisions, revoke
  financial approval and keep undo snapshots. Billed records cannot be changed here.
- Manual fragment choices revalidate app/state/closed intervals and uncovered ranges
  inside one transaction. A concurrent assignment causes a stale-review message.
- Day export reads one coherent local snapshot and labels AI/rule, user and manual
  sources. It clips intervals, excludes private titles/descriptions/rates, hides
  personal/excluded app names and preserves away/gaps without inventing work.
- Export does not create an invoice/report or approve/bill entries. A read snapshot
  does not commit its caller's transaction. Unicode, escaped text and multipage
  records are tested; a generated sample was rendered and visually inspected.
- Real mouse testing exposed GTK focus warnings during step replacement. Screen
  transitions now defer until click processing finishes and clear old focus.
- Main step actions fit on screen at normal and 200% scale. Exact seconds remain
  in the exported evidence; everyday metrics use compact hours/minutes.
- Removed the misleading “undo last choice” shortcut that could affect an unrelated
  global edit. Change category is direct; Settings retains accurately labelled
  Undo last change. Remembered examples are separate from time-entry undo history.

## Evidence

- **208 unit/regression tests** passed locally, covering new preset ownership,
  privacy scope, non-billable automation, ambiguity, stale/concurrent correction,
  source-preserving edits, snapshot transactions, PDF privacy/Unicode/multipage,
  restored defaults and the public synthetic replay.
- **30 default-flow UI checks**, at normal and 200% scale. Actual XTest mouse
  clicks exercise all four setup steps with a fake saved key, no typing and no
  hidden inference. Tests also exercise one-choice review, correction, export
  preview, off controls and database integrity. This is not human screen-reader
  or novice-user acceptance.
- **53 existing scaled mouse/keyboard checks** and the retained **21 automation**,
  **19 daily-review** checks plus focused key/rules/improvements scripts passed.
  These explicitly select advanced mode so existing business functions remain
  covered; default-product coverage is a separate test with no mode override.
- Separate delayed worker-process/concurrent recorder-write test passed. Python
  compilation, shell syntax and whitespace checks passed.
- Screenshots in docs/screenshots are rendered from the actual simple app using
  synthetic data and a fake provider. They contain no user's records.
- Public CI runs both Ubuntu core matrices, the default simple UI, retained
  advanced workflows, packaged runtime checks and trusted-main package provenance.
  Verify CI, source trees, package hashes/provenance and public assets before
  reporting publication/installation complete.

## Live synthetic Jev check

Only public app names and generic preset descriptions were sent using the securely
saved key: four initial cases, four after the question correction, then eight new
held-out cases. **16 requests, 13,361 reported input tokens**, model **jev-1.14.0**.
No recorded user activity, private project names/titles or times were transmitted.

Initially none of four cases qualified. With the corrected limited question,
Visual Studio Code, GIMP and Slack qualified; Firefox stayed uncertain. In the
subsequent held-out set, Krita, Thunderbird, Zoom, LibreOffice Calc and Okular got
the expected broad labels; Google Chrome, Terminal and Files returned none. Five
of eight qualified for automatic labels and three remained for a human choice.
All eight choices matched the synthetic app-function labels.

The public fixture `tests/fixtures/jev_simple_heldout_recorded.json` replays that
policy offline. This is a small synthetic check, partly informed by question
development, not representative real-day accuracy or proof of productivity.
Thresholds are heuristics specific to limited non-billable app labels. Do not
apply their relaxed work-intent semantics to financial/project decisions.

## Remaining limits and next evidence

Real-day usefulness, novice comprehension, actual Orca/screen-reader acceptance,
sustained hardware/capture recovery and closed-window Flatpak background behaviour
remain unverified. Keep Flatpak open until its background permission is verified.
The day PDF is a factual local export, not a tamper-proof or independent certificate.
No app can establish completed output from foreground app duration alone.

Next work should observe whether users can finish setup and save a day without
instructions, measure repeated choices/minutes reviewing, improve context only
where those observations show a need, and preserve the simple default. Do not add
more modes, forms, explanatory paragraphs or financial controls to ordinary screens.

## Delivery record

Candidate: 0.6.0-rc1. Final PR/release notes identify the tested source commit,
passing trusted build, verified packages and local installation. Background sending
is not silently enabled by an upgrade; the user completes the four-step setup.

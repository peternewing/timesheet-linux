# Improvement and acceptance plan

9 November 2026 · linked to [the deep review](DEEP_REVIEW_2026-11-09.md)

## Objective and completion rule

Quietly record and organise the day, ask only about meaningful uncertainty, preserve simple setup and optional advanced tools. Fix code defects now; use subsequent acceptance evidence to decide context, calibration and UX changes. Completion means the relevant tests and real-world gates pass, not that every rating is labelled 9/10.

The shared register has 48 implemented actions, 18 retained safeguards and 18 open acceptance actions. All 84 IDs remain visible below. No open acceptance item is claimed implemented or blocked by an invented permission rule.

## Delivery order

1. **Local engineering — implemented.** Correct unknown usage, memory retrieval/forgetting, transactional initialisation, metadata validation, worker recovery, explanations, timer/export accounting, guarded undo and malformed release metadata. Preserve old records and sending scope.
2. **Regression and evidence tooling — implemented.** Pure contract, case IDs/fingerprints/slices, offline response comparison, repeatable synthetic benchmark, CI benchmark command, default/scaled GTK and advanced workflows. Run final checks after source changes.
3. **Consenting-user usefulness — open.** Several independently labelled real days, including easy automatic cases, browsers, personal work and client switches. Keep private datasets outside Git. Preview any supplied outgoing context; do not infer consent from an API key or this development task.
4. **Human accessibility and novice UX — open.** Complete setup, app/day choice, correction, guarded undo and export with keyboard/Orca and no coaching. Record confusion before changing default screens.
5. **Sustained desktops and packages — open.** Run physical desktop/package matrix, 48-hour capture/worker recovery and week-long resource profile. Record actual versions, GPU, package and background permissions.
6. **Release — open.** Commit the exact reviewed tree, pass trusted CI, build packages, verify provenance/hashes, test fresh install/upgrade/restore/rollback and only then publish/install the verified artifacts. This request has not been treated as proof of those outcomes.

## Acceptance measures

- **Decision quality:** correct/incorrect automatic cases and seconds, cross-client wrong minutes, unresolved/excluded time, case/time coverage, independently labelled sampling process, actual reported model and tokens.
- **User burden:** setup completion, daily review minutes, questions, repeated corrections, accidental changes and ability to recover with Undo.
- **Reliability:** observed gaps, recovery latency, duplicate requests, unknown charges, data integrity, lock/suspend/login/disk and offline behaviour.
- **Resources:** CPU/RSS/IO/storage and latency distributions across a week, with machine and dataset size recorded. Short discovery timings are only a smoke benchmark.
- **Accessibility:** announced names, focus order, keyboard reachability, scaling, errors and completed tasks; only human acceptance closes the gate.

## Reproducible local commands

Run from the development checkout; commands below use disposable synthetic data or repository fixtures.

```sh
/usr/bin/python3 -m unittest discover -s tests -v
PYTHONPATH=. /usr/bin/python3 tests/verify_worker_process.py
/usr/bin/python3 -m timesheet.benchmark --observations 20000 --batches 5
/usr/bin/python3 -m timesheet.evaluate tests/fixtures/jev_simple_heldout_recorded.json
/usr/bin/python3 -m timesheet.evaluate tests/fixtures/jev_live_heldout_recorded.json
/usr/bin/python3 -m timesheet.evaluate reference.json --compare candidate.json
GDK_SCALE=2 GDK_BACKEND=x11 GSK_RENDERER=cairo GSETTINGS_BACKEND=memory PYTHONPATH=. xvfb-run -a -s "-screen 0 2880x2000x24" /usr/bin/python3 tests/verify_simple_ui.py
/usr/bin/python3 -m compileall -q timesheet tests
git diff --check
```

Offline comparison replays both saved response sets under the current routing policy. It refuses different labelled inputs and never promotes a model or relaxes a threshold. Historical policy changes need their own preserved code/version, not just two response files. Live evaluation is separately opt-in with a data preview and paid-request flag; no live run was performed for this review.

## Complete action register

| ID | Action | State / evidence needed |
|---|---|---|
| C01.1 | Detect a missing/stale worker and offer Restart Jev on Today. | **Implemented** — Synthetic heartbeat, clock-jump and recovery tests; GTK recovery prompt. |
| C01.2 | Reject malformed, oversized or wrongly typed whole-day pass metadata. | **Implemented** — Corrupt cursor, expiry, identity, range and JSON tests fail closed. |
| C01.3 | Run a 48-hour native/AppImage/Flatpak recovery trial including closed windows and login. | **Acceptance required** — Record gaps, worker restarts and recovery latency per package/desktop. |
| C02.1 | Retrieve correction examples by Unicode-normalised app and exact clue/focus scope before limiting. | **Implemented** — An older relevant example survives more than 1,000 unrelated corrections. |
| C02.2 | Offer ready-made task-guidance starters without adding a required setup field. | **Implemented** — Optional unsaved starters in the existing task-guidance dialog. |
| C02.3 | Evaluate shared-browser/client-switch cases with explicitly consented, minimised context. | **Acceptance required** — Compare time-weighted errors and coverage against app-only decisions. |
| C03.1 | Add stable case IDs, labelled-input fingerprints, slices and actual model metadata. | **Implemented** — Replay output validates unique IDs and separates slice outcomes. |
| C03.2 | Compare saved candidate/reference responses on identical labelled inputs. | **Implemented** — Changed inputs are refused; newly wrong automated cases and coverage deltas are reported. |
| C03.3 | Collect several independently labelled real days, sampling easy automatic cases as well as exceptions. | **Acceptance required** — Keep private evidence outside the repository; report sample selection and wrong minutes. |
| C04.1 | Retain and exercise stale-response, concurrent-edit and explicit-choice protection. | **Existing safeguard rechecked** — Core race/privacy tests and the independent worker-process check. |
| C04.2 | Retain rule precedence, no-gap allocation and draft-only AI execution. | **Existing safeguard rechecked** — Core assignment, rule, undo and daily-choice regressions. |
| C04.3 | Measure cross-client wrong minutes before broadening task automation. | **Acceptance required** — No financial approval or broader threshold based only on fixture success. |
| C05.1 | Use one reusable contract validator outside the worker lifecycle. | **Implemented** — Worker, cache and evaluator import the same pure validation module. |
| C05.2 | Show the saved draft-policy reason and model beside automatic entries. | **Implemented** — Inline Why this category? uses saved decision evidence, never a generated justification. |
| C05.3 | Calibrate abstention and errors separately for specialist apps, browsers and client projects. | **Acceptance required** — Publish sample sizes and time-weighted error/coverage curves before changing gates. |
| C06.1 | Index app/scope retrieval so unrelated history cannot hide relevant examples. | **Implemented** — Unicode and >1,000 unrelated-row regression; bounded eight-example lookup. |
| C06.2 | Order updated corrections by correction time rather than original row ID. | **Implemented** — Updating an older correction makes it the first relevant example. |
| C06.3 | Clear cached decisions and invalidate queued/in-flight jobs when examples are forgotten. | **Implemented** — A response arriving after Forget cannot create an entry. |
| C07.1 | Recheck equivalent clear and ambiguous requests are reused without extra key access. | **Existing safeguard rechecked** — Whole-day/cache tests preserve request and consent limits. |
| C07.2 | Make priority-pass persistence robust to malformed and superseded metadata. | **Implemented** — Invalid state cannot crash the loop or replace a newer pass. |
| C07.3 | Add a repeatable disposable large-history benchmark. | **Implemented** — 20,000 observations, 20 tasks, five bounded discovery batches recorded locally. |
| C08.1 | Expose an actionable missing-worker warning instead of a false working claim. | **Implemented** — Stale/future/corrupt heartbeats and UI recovery tested. |
| C08.2 | Expose factual background usage, limits and unresolved charges in simple Settings. | **Implemented** — Collapsed local details require no key access or data transmission. |
| C08.3 | Provide a factual local day digest using observed totals and covered intervals. | **Implemented** — Existing record-help expander now summarises recorded, covered, uncategorised and gap time. |
| C09.1 | Retain one daily choice with future same-day reuse and protected existing entries. | **Existing safeguard rechecked** — Daily-choice and UI tests cover separated periods and direct Assign. |
| C09.2 | Keep optional day actions expanded through background refreshes. | **Implemented** — Found during scaled UI review; More actions now retains its expansion state. |
| C09.3 | Observe setup-to-saved-day completion and count clicks/repeated questions. | **Acceptance required** — Record task completion, errors and median review minutes with consenting users. |
| C10.1 | Save rule identity, priority and title-condition flag when a rule allocates time. | **Implemented** — Rule explanation survives later rule deletion without duplicating raw title content. |
| C10.2 | Retain duplicate/conflict/archive/title-availability warnings and previews. | **Existing safeguard rechecked** — Existing rule core/GTK regressions rechecked. |
| C10.3 | Test whether novices understand rule scope and future versus historical effects. | **Acceptance required** — Observe a rule creation, deliberate conflict and correction without coaching. |
| C11.1 | Integrate optional purpose-based project/rule/report shortcuts in the existing fourth step. | **Implemented** — Choices stay staged until Start and appear in day actions. |
| C11.2 | Preserve app exclusions and custom request/token limits when reconnecting. | **Implemented** — Excluded eligible activity remains unsent; final disclosure shows saved limits. |
| C11.3 | Test saved-key, pasted-key, locked-keyring and local-only first runs with novices. | **Acceptance required** — Measure completion and comprehension of the Start consent boundary. |
| C12.1 | Offer optional short activity-type starter descriptions. | **Implemented** — Choosing a starter only fills the unsaved guidance field. |
| C12.2 | Retain overlap warnings and explicit bounded focus context. | **Existing safeguard rechecked** — Profile and focus-boundary regressions; no focus creates time on its own. |
| C12.3 | Validate competing real project definitions and revise descriptions based on observed confusion. | **Acceptance required** — Use paired shared-app examples; require fewer wrong client minutes, not just more coverage. |
| C13.1 | Keep one local answer for separated and later same-day periods. | **Existing safeguard rechecked** — Grouping, continuation, undo and stale-human-choice tests. |
| C13.2 | Make operational state/usage visible without opening the advanced automation form. | **Implemented** — Collapsed simple Settings details and recovery action. |
| C13.3 | Measure repeated corrections and review time over at least five consenting-user days. | **Acceptance required** — Separate unresolved, excluded and wrongly allocated minutes; do not optimise only coverage. |
| C14.1 | Provide inline Why this category? for AI and local-rule entries. | **Implemented** — Templates use saved evidence and clearly state missing historical detail. |
| C14.2 | Persist an explicit routing version for new decisions; mark old versions unknown. | **Implemented** — Additive migration defaults to zero, not an invented historical version. |
| C14.3 | State that workflow counts and model scores do not prove accuracy, output or billing approval. | **Implemented** — Simple/advanced usage wording and explanations preserve these distinctions. |
| C15.1 | Preview the actual last action and guard Undo against newer background changes. | **Implemented** — Expected change ID is rechecked under the write lock. |
| C15.2 | Make repository schema checks preserve the caller transaction. | **Implemented** — A deliberately rolled-back caller write remains rolled back after Repository construction. |
| C15.3 | Test correction, Forget and Undo comprehension with real users. | **Acceptance required** — Users must distinguish reverting time from forgetting examples without extra manual setup. |
| C16.1 | Retain actual mouse/keyboard checks and accessible Assign/card names. | **Existing safeguard rechecked** — Existing workflows exercise native controls and focus. |
| C16.2 | Check the changed default flow at normal and 200% scale. | **Existing safeguard rechecked** — Isolated GTK checks and actual rendered screenshots, not a screen-reader claim. |
| C16.3 | Run human Orca, keyboard-only and large-text acceptance for setup/review/undo/export. | **Acceptance required** — Record focus order, announced labels, errors and successful task completion. |
| C17.1 | Recheck concurrent recording writes during a delayed decision process. | **Existing safeguard rechecked** — Separate process test verifies durable draft and DB integrity. |
| C17.2 | Retain explicit away, locked, personal, excluded and unknown intervals. | **Existing safeguard rechecked** — Capture/privacy tests and factual day-record tests. |
| C17.3 | Run multi-day suspend/resume, lock/login and disk-exhaustion tests on disposable hardware data. | **Acceptance required** — Compare captured intervals with a reference log; never fill missing time by inference. |
| C18.1 | Fix exports subtracting a timer that the export omitted. | **Implemented** — The same synthetic day is checked with and without an included running timer. |
| C18.2 | Make migration checks and Undo concurrency-safe without committing partial changes. | **Implemented** — Caller rollback and expected-change regressions. |
| C18.3 | Recheck non-billable generic AI, protected billing and stale-assignment gates. | **Existing safeguard rechecked** — Core store, daily-choice, PDF and advanced workflow regressions. |
| C19.1 | Make Forget stop dependent pending/in-flight work and remove cached decisions. | **Implemented** — Late completion cannot apply a forgotten-context decision. |
| C19.2 | Retain existing exclusions and sending caps when simple setup is repeated. | **Implemented** — Regression proves an eligible excluded app generates no provider request. |
| C19.3 | Recheck exports/status/explanations omit raw titles, paths, descriptions and secrets. | **Existing safeguard rechecked** — Synthetic privacy tests plus source review; permitted local project names remain intentional. |
| C20.1 | Retain no repeated unlock attempts while the worker is paused. | **Existing safeguard rechecked** — Key-error regression verifies a single key access and no usage reservation. |
| C20.2 | Keep new status/explanations/replay/benchmark features independent of key access. | **Implemented** — New tools run locally with synthetic data; no real key is read. |
| C20.3 | Exercise encrypted secret portal and missing-portal behaviour using a private fake service. | **Existing safeguard rechecked** — Private synthetic portal check; physical desktop unlock acceptance remains separate. |
| C21.1 | Keep unresolved usage blocking across midnight, Resume and policy reconfiguration. | **Implemented** — A prior-day unknown charge prevents a new request until acknowledged. |
| C21.2 | Bound daily totals to the actual local calendar day. | **Implemented** — Other-day ledger rows cannot distort today's usage totals. |
| C21.3 | Show request/token limits and unresolved usage across all days in simple Settings. | **Implemented** — Factual counts only; no invented currency cost or token estimate. |
| C22.1 | Fail closed on corrupt persisted day-pass JSON/types. | **Implemented** — Malformed expiry/cursor/identity and oversized/deep JSON tests. |
| C22.2 | Retain bounded retry and unknown-spend acknowledgement semantics. | **Existing safeguard rechecked** — Provider rejection, timeout, abandoned lease and budget tests. |
| C22.3 | Run controlled real-provider outage/auth/model-retirement recovery tests with synthetic prompts. | **Acceptance required** — Record requests/usage/recovery; do not send recorded work or retry unknown charges silently. |
| C23.1 | Index relevant correction lookup and order by correction time. | **Implemented** — App/scope/at index plus large unrelated-history regression. |
| C23.2 | Provide repeatable bounded discovery timing and RSS evidence. | **Implemented** — Disposable synthetic DB; no flaky pass/fail timing threshold. |
| C23.3 | Run a week-long CPU/RSS/IO/storage profile across realistic retention sizes. | **Acceptance required** — Record machine/package/desktop and latency distributions; set budgets from observations. |
| C24.1 | Add adversarial regressions for midnight usage, memory, schema rollback, status, exports and Undo. | **Implemented** — New cases reproduce the defects and verify their corrected behaviour. |
| C24.2 | Add immutable-input offline response comparison and per-slice replay evidence. | **Implemented** — Case identity changes are refused; wrong automatic decisions are enumerated. |
| C24.3 | Run the synthetic discovery benchmark in CI without a machine-specific speed gate. | **Implemented** — CI benchmark command added for both existing core OS jobs; final-commit CI execution remains a release gate. |
| C25.1 | Recheck virtual X11 capture on an isolated display. | **Existing safeguard rechecked** — Synthetic virtual display is protocol evidence, not hardware acceptance. |
| C25.2 | Recheck GNOME and KDE fake-service protocols and privacy boundaries. | **Existing safeguard rechecked** — Private DBus test services; no real user activity is sent. |
| C25.3 | Complete a physical GNOME/KDE/Sway/Hyprland and native/AppImage/Flatpak matrix. | **Acceptance required** — Record versions, GPU, permissions, background behaviour and exact failures. |
| C26.1 | Ignore malformed individual asset names without hiding an otherwise valid release. | **Implemented** — A structured invalid name plus valid assets still yields the verified release link. |
| C26.2 | Validate fresh install, compatible upgrade, backup restore and rollback for final packages. | **Acceptance required** — Use disposable databases and preserve consent, records and key ownership. |
| C26.3 | Build trusted final-source packages, verify provenance/hashes and publish only those artifacts. | **Acceptance required** — CI/source SHA/public asset digests/local installation must match before claiming delivery. |
| C27.1 | Extract response validation so evaluation does not depend on worker lifecycle. | **Implemented** — Worker and evaluator share the same standalone contract function. |
| C27.2 | Extract scoped memory and local operational explanations/status. | **Implemented** — New modules have direct regression coverage and no key/network requirement. |
| C27.3 | Extract four-step setup from daily rendering/review. | **Implemented** — SetupUI mixin retains the same public UI behaviour and four steps. |
| C28.1 | Persist routing version on new decisions and show historical unknowns honestly. | **Implemented** — Version zero is unknown; source-deleted decisions do not gain fabricated explanations. |
| C28.2 | Retain local rule identities without copying raw title evidence. | **Implemented** — Rule snapshots survive rule deletion while containing only ID/priority/condition type. |
| C28.3 | Publish an 84-item machine-readable register with ratings, evidence and acceptance gates. | **Implemented** — This report, plan and JSON share the same 28 categories and three actions each. |

## Acceptance log template

For each open ID, record date, tester, consent/data scope, package/source SHA, desktop/OS/GPU, scenario, expected and observed results, failure/recovery behaviour, measured counts, artifact location and pass/fail. Do not commit private app histories, keys, client labels or screenshots. A failed gate remains open with a reproducible finding.

When measurements show a deficit, make the smallest corresponding implementation change, add a regression or fixture and rerun the affected local and external gates. Keep the four-step/three-destination default. Re-score the affected categories with evidence and preserve this baseline.

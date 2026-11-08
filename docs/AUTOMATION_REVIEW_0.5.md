# Automation review — 0.5.0-rc1

8 November 2026. Product source of truth: [accepted roadmap](AUTOMATION_ROADMAP.md).
Scores are engineering/product judgments against that objective, not independently
certified measurements. Preserve the baseline. This candidate makes a substantial
move from on-demand suggestions to background organisation; it does **not** yet
establish that every category has reached 8 or 9. External acceptance gates are
explicitly open. A higher target is not a reason to label unmeasured behaviour 9.

## Pass 1: implementation and category inventory

The first pass implemented the independent decision worker, explicit personal-key
standing policy, bounded durable discovery/queue/cache, typed results and routing,
scoped examples, task guidance, focus, exception inbox, atomic previewed corrections,
explanations, usage limits and update verification. Every original category was
revisited, including existing capture, billing, privacy and UI workflows.

## Pass 2: fresh adversarial review

The second pass started from consent, source evidence, rules, time integrity,
concurrent database writers, failure recovery, model changes, billing boundaries,
retention, upgrade ownership and keyboard/scaled layouts. It did not copy the first
pass's judgments. Findings drove these corrections:

- Nested setting writes must not commit an outer transaction. Settings now join it;
  policy/reservation/application explicitly begin atomic transactions.
- Revalidate after secure-key unlock and inside request reservation/application.
  Changed payloads, titles, exclusions, task definitions or assignments cannot apply.
- Preflight the entire frozen batch before writing examples, preventing a correction
  from making the next item stale midway through the same operation.
- Conflict rules cannot be overridden by AI/focus. Rule/focus/day boundaries split
  intervals. Explicit human assignments made during a request are preserved.
- Unknown usage is acknowledged, never silently retried or forgotten. Request caps
  use transactional reservations; rate limiting has global bounded backoff.
- Pin actual model identity; reject missing/alias/changed model metadata. Malformed
  optional context is quarantined without breaking core recording.
- Restrict each standing policy to its path/package/version; an old worker yields
  when ownership changes. Restore requires explicit re-enablement.
- Wrap long checkboxes/dropdowns and group advanced controls. Clear focus closes its
  form. Explanations support Escape and labelled selectable text.
- Retention strips copied source context while retaining minimal action evidence.
- Project guidance similarity is a local warning; workflow counts are expressly
  separated from measured AI accuracy. Flatpak background lifetime remains qualified.

## Category scorecard

P1 and P2 are assessed scores after each pass. “Next evidence” states what prevents
another increase, including where implementation alone is insufficient.

| Category | Baseline | P1 | P2 | Strength now | Remaining weakness / next evidence |
|---|---:|---:|---:|---|---|
| Background Jev automation | 2 | 8 | 8.5 | Independent durable service, explicit standing policy, capture unaffected | Full-day native and window-closed Flatpak acceptance; low-interaction day study |
| Context supplied to Jev | 3 | 8 | 8.5 | Guidance, scoped examples, derived clues, bounded focus; no raw title upload | Validate distinguishing context across real shared-app projects; avoid over-specific guidance |
| Decision quality evidence | 4 | 6 | 6.5 | Live typed contract and held-out synthetic evidence; replay/evaluation CLI | Representative consented labelled days, cross-client wrong minutes and calibration; no real-day precision claim |
| Automatic task assignment | 3 | 8 | 8.5 | Validated reversible drafts, focus authority distinct from inference, rules first | Measure useful coverage and mistaken allocations in real work before broad trust |
| Uncertainty handling | 4 | 8 | 9 | Full alternatives/none/personal/evidence, one ambiguity policy, action gates, model pinning | Heuristic thresholds need empirical adjustment; 9 is policy/implementation quality, not calibrated certainty |
| Learning from corrections | 3 | 8 | 8.5 | Explicit local examples scoped by app/clues/focus; forget control | Demonstrate fewer repeat corrections on held-out real work; examples are not retraining |
| Batch intelligence | 5 | 8 | 9 | Durable equivalent-input cache, previewed one-answer-many, frozen atomic scope | Scope is intentionally bounded; wider grouping needs evaluated session signals |
| Proactive assistance | 3 | 8 | 8 | Worker organises quietly; Today shows exceptions, focus and actionable pauses | Optional meaningful desktop alerts/daily digest and notification acceptance remain future work |
| Daily workflow | 7 | 8 | 8.5 | Today automation summary, small inbox, focus and preserved daily review | Time an entire real day; navigation can still be simplified with observed usage |
| Rules/explanations | 7 | 8 | 9 | No-typing normal rules, plain preview, deterministic precedence, conflict protections | Validate comprehension with novice users; title-specific rules remain advanced |
| First-run onboarding | 6 | 8 | 8.5 | One automation policy form, own key, context preview and task description | Capture setup still desktop-specific; end-to-end first-time user study |
| Project/task setup | 6 | 8 | 8.5 | Guidance per task, focus action, local similar-guidance warnings | Similarity hint is heuristic; evaluated suggestions for overlapping project definitions |
| Review burden | 4 | 8 | 8 | Standing consent, cache, bounded focus default, consolidated corrections | Actual minutes/clicks per day not yet measured; sparse evidence can still yield many exceptions |
| Explanations/trust | 6 | 8 | 9 | Durable result/model/context/reason linked to entries; heuristic caveats | Better nontechnical explanation templates need user comprehension testing |
| Correction/undo | 7 | 8 | 9 | Atomic frozen batch, explicit remember, reversible drafts, protected later edits | Automatic decision sampling and measured correction speed remain desirable |
| Accessibility | 5 | 6 | 6.5 | Keyboard paths, labelled evidence, Escape, 200% scaling and narrow forms tested | Real Orca/screen-reader and high-text-scale acceptance required; no certification |
| Activity recording | 8 | 8 | 8 | Independent capture, privacy filters, gaps and existing adapter tests retained | Sustained hardware suspend/lock/full-day matrix, storage exhaustion/power-loss testing |
| Time/billing integrity | 8 | 8.5 | 9 | Transactional stale checks, concurrency tests, no overlaps, drafts only; approval explicit | Hardware fault testing remains broader durability evidence |
| Privacy controls | 8 | 8.5 | 9 | Explicit allowed context/exclusions, exact preview, revocation, retention and restore gates | Provider processing/retention remains external; verify organisation-specific ZDR if needed |
| API-key security | 8 | 8.5 | 9 | Own key, encrypted native/portal store, fail closed, single pause on unavailable key | Wider locked-session/desktop portal acceptance; key security score is not a penetration test |
| Cost management | 5 | 8 | 9 | Durable usage ledger, strict request cap, reported-token pause, unknown-spend acknowledgement, cache | Token cap may cross by one request; provider billing is authoritative; on-demand calls separate |
| Offline/API failures | 6 | 8 | 9 | Capture independent, durable queue, leases, bounded 429 retries, safe unknown usage | Sustained live outage/recovery and retired-model provider tests |
| Performance | 8 | 8 | 8.5 | Indexed/bounded discovery, cache and limited UI refresh; small synthetic benchmark | Week-long CPU/memory/storage and huge retained datasets not measured |
| Testing/evaluation | 8 | 8 | 8.5 | 184 unit tests, worker-process and UI workflows, recorded live replay, trusted package CI gates | More fixtures do not establish actual accuracy; hardware and human acceptance remain |
| Linux compatibility | 7 | 7.5 | 7.5 | Existing adapter tests, independent native worker, fail-closed sandbox key storage | Real desktop matrix, Hyprland hardware, Flatpak closed-window background/Save portal acceptance |
| Installation/updates | 7 | 8 | 8.5 | Read-only release check, backup/restore gates, exact-source packages, workflow provenance verification | Trusted CI/public artifacts must pass before publication; user update/restart remains explicit |
| Architecture | 6 | 8 | 9 | Policy/context/store/worker/UI/evaluation/update modules separated from collector | Existing main GTK module remains large; extract further around concrete feature changes |
| Auditability | 5 | 8 | 9 | Fingerprinted evidence, exact context/result/model, usage/action/audit/undo records | Minimal retained evidence cannot reconstruct deleted source detail by design |

## Evidence recorded locally

- **184 unit/regression tests** passed on system Python. Include permissions,
  malformed metadata, scope/rule/focus boundaries, stale results, concurrent
  reservation/claim, human edits during network calls, strict caps, next-day
  reset, unknown usage, retention, restore, model changes, updates and evaluation.
- **53 existing mouse/keyboard workflows at 200%**, **19 daily-review/guided-rule
  checks**, **21 automation UI checks**, plus focused improvements, rules and
  Jev/key/consent review scripts passed with synthetic data on private X servers.
- Independent worker-process test: recorder-like writes advanced during a delayed
  fake network request; durable draft/integrity and default-off one-shot cleanup
  passed. This tests process independence, not a multi-day resource profile.
- Private synthetic Secret portal: encrypted store/read/remove, missing-portal
  failure and legacy request path passed. No real key was printed or committed.
- Bounded discovery benchmark: 20,000 synthetic observations and 20 active tasks;
  five 100-row batches took 0.0162–0.0168 seconds; process peak RSS 26,784 KiB.
  These are one-machine synthetic observations, not a sustained performance SLA.
- Python compilation, shell syntax and diff whitespace checks passed.
- Public CI adds Ubuntu 22.04/24.04 core/protocol checks, the worker process,
  synthetic replay, scaled UI workflows and packaged-runtime imports. CI and
  package/provenance results must be checked at the final source commit.

## Live synthetic Jev evidence

Using the existing securely stored personal key, a bounded test sent **only
synthetic application/task descriptions**. No recorded user activity or private
project names/titles/times were used. One model lookup and 16 decision requests:
6 exploratory contract cases, 2 question-review cases, then 8 held-out synthetic
cases. Reported total input tokens: **10,997** (provider charges authoritative).
Reported actual model: **jev-1.14.0**.

The first six task choices matched labels but none passed the original gate. This
exposed a mismatch between classification questions and “proof of work” wording.
The questions were refined and explicit bounded focus-default authority was
separated from automatic inference. The eight subsequent held-out synthetic cases
produced four eligible automatic drafts, all four label-correct, four exceptions,
eight label-correct choices and zero wrong synthetic minutes. They represent 50%
synthetic time coverage. The public fixture contains only synthetic inputs/results.

This small, partly prompt-development-informed set is **not representative daily
accuracy**, an independent benchmark or evidence that thresholds are calibrated.
Replay now reports choice accuracy, automated precision, time coverage, wrong
minutes, exceptions and reported input tokens. Broader automatic inference remains
conservative. The app is not silently enabled on the user's real data.

## Next iteration, in priority order

1. Consent-driven real-work evaluation: at least several labelled days across
   shared apps, personal/ambiguous work, client switches and easy auto cases. Use
   time-weighted coverage, cross-client wrong minutes and timed human review. Keep
   private data out of GitHub. Do not broaden automation gates without evidence.
2. Real Orca acceptance and novice usability: setup, inbox, correction, focus,
   undo, reporting, high text scaling. Record task completion and confusion.
3. Sustained desktop/hardware matrix: suspend/lock/login/network outages, native
   and AppImage service restart, Flatpak after window close and document portal,
   actual Hyprland/GPU. Test disk exhaustion and rollback with disposable data.
4. Use measured review bottlenecks to refine context, retrieval/session grouping,
   daily digest and optional quiet notifications. Evaluate model changes before
   promotion. A broad “trusted pattern” mode remains gated on real evidence.
5. Verify trusted main package CI, provenance, published hashes and local upgrade.
   Keep this candidate a prerelease while the acceptance gates above remain open.

The first two passes are complete as engineering iterations. The user's universal
8/9 target is **not yet evidenced**; lowest scores remain the priority for future
work. Do not overwrite them merely to mark the target complete.

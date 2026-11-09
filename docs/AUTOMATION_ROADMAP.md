# Automation source of truth

Accepted by the user on 8 November 2026. This document preserves the assessment
of 0.4.0-rc2 and governs subsequent development. Read it before every improvement
or review. Keep the baseline intact; record later evidence separately.

## Latest user direction — simplicity rebuild

On 8 November 2026, the user requested a simpler rebuild: guided screens, clicking
ready-made options, no required typing, Jev working automatically and a useful
record of the day. This supersedes the earlier everyday UX/mode proposals below.
Preserve the assessment baseline and evidence, but prioritise simplicity.

0.6 defaults to four setup steps and three destinations (Today, Past days,
Settings). Generic non-billable app-activity categories can be inferred from
specialist app functions. That is distinct from establishing work intent,
client/project assignment, productivity or completed output. Existing strict
project decisions remain available only through optional advanced controls.
See [the rebuild review](SIMPLICITY_REVIEW_0.6.md) for the changes, fresh second
review, test/live evidence and remaining limits. No blanket 9/10 claim is made.

## Product objective

Latest user direction, 9 November 2026: the product is automatic computer screen-time
tracking for personal life and work, similar in usefulness to a phone's Screen Time.
Personal use is legitimate and must not be treated as a failed work classification.
Keep activity type, explicit Personal/Work context, privacy exclusions and financial
records separate. Local screen-time insight must work without AI; TypeSafe adds
permitted typed organisation. See [the sustained iteration log](PERSONAL_WORK_ITERATION.md).

Jev/TypeSafe quietly organises recorded work with minimal user interaction.
The intended workflow is **record automatically → organise automatically → ask
only about uncertain work → present a finished daily record**. Today is the
centre of the product, with an organised day and a small exception inbox.

Baseline: tracking/review foundation **7.5/10**, hands-off Jev automation **3/10**,
overall fit for the intended product **5/10**. These were engineering/product
judgments, not independently measured AI accuracy or a security certification.
The 0.4.0-rc2 evidence was 128 core tests, 53 mouse/keyboard checks and 19 focused
daily-review checks, plus isolated capture, secret storage and package checks.

## Accepted category assessment and plan

| Category | Baseline /10 | Good in rc2 | Weakness | Required improvement |
|---|---:|---|---|---|
| Background Jev automation | 2 | Validated on-demand calls | User initiates all Jev processing | Independent durable worker processing completed activity under a standing user policy |
| Context supplied to Jev | 3 | Limited disclosure, explicit optional context | App names cannot distinguish shared-app projects | Approved task profiles, relevant local examples, contextual preferences; no unapproved titles/content |
| Decision quality evidence | 4 | Typed outputs and insufficient-evidence option | No representative live evaluation | Labelled evaluation, correctness/coverage measurements, held-out and model-change checks |
| Automatic task assignment | 3 | Rules create draft entries | No Jev execution policy | Validated automatic reversible drafts; stale-data and explicit-user-choice protection |
| Uncertainty handling | 4 | Alternatives in single-call UI | Provisional heuristic; simpler batch path | One complete result format and action-specific routing policy for all paths |
| Learning from corrections | 3 | Local choices and feedback | Coarse app-wide preference, no contextual learning | Context-specific correction examples; retrieve relevant examples; avoid universalising one correction |
| Batch intelligence | 5 | Bounded calls/cancellation/cached open review | Sequential per-block manual work | Equivalent-request grouping, durable cache, eligible automatic application and consolidated exceptions |
| Proactive assistance | 3 | Readiness checks and rule hints | Mostly visible only after opening review | Quiet background organisation, daily digest and actionable failure/exception signals |
| Daily workflow | 7 | Review today and selection controls | Still a queue of forms | Organised timeline and exception-only decisions with minimal clicks |
| Rules/explanations | 7 | No-typing app/task choices and previews | User must understand rule scope | Secondary rules, scoped remembered patterns, plain-language evidence |
| First-run onboarding | 6 | First-project continuation | Key, capture and automation setup are separate | One guided setup, explicit data/automation choice, connection check and sample preview |
| Project/task setup | 6 | Clients/tasks/rates/budgets | Names alone are weak AI criteria | What-belongs-here descriptions/examples, overlapping-definition checks and clarification |
| Review burden | 4 | Selection and cached review results | Repeated prompts/per-result saves | Explicit standing consent for automation, pause and outgoing-data history |
| Explanations/trust | 6 | Rule preview and probability text | No durable decision-to-action explanation | Why-this-task evidence, model/version, policy and action history |
| Correction/undo | 7 | Reversible edits | Corrections do little for future context | Change-this, change-similar with scope preview, remember-pattern and undo |
| Accessibility | 5 | Keyboard and 200% scaling checks | No screen-reader acceptance | Labels, focus/order, keyboard exception inbox; record human acceptance separately |
| Activity recording | 8 | Separate collector, durable observations, explicit gaps | Hardware/full-day coverage incomplete | Multi-day/hardware/compositor acceptance and failure recovery |
| Time/billing integrity | 8 | Overlap protection, rates and snapshots | New background stale/concurrency risks | Transactional revision/evidence checks; automation creates drafts, never bills |
| Privacy controls | 8 | Local data, exclusions, consent | Rich background context needs policy | Local redaction/exclusions before sending, explicit allowed-data levels and history |
| API-key security | 8 | Personal keys in encrypted secret service | Background unlock/portal diversity | Quiet paused state on unavailable storage; no repeat unlock storm; broader acceptance |
| Cost management | 5 | Bounded request sizes | No ledger, standing cap or durable cache | Reported token ledger, configurable bounded usage, cache/dedup and explicit unknown-spend handling |
| Offline/API failures | 6 | Local capture and sanitised errors | No durable processing queue | Bounded retries/backoff, lease recovery, permanent/transient distinction, no capture dependency |
| Performance | 8 | Summary improved 1.286s→0.015s in one synthetic run | No week-long resource benchmark | Bounded discovery, indexed jobs, context/request dedup, debounce and throughput/resource checks |
| Testing/evaluation | 8 | Broad deterministic/UI suite | Fake responses do not prove AI accuracy | Contract fixtures, labelled evaluations, drift/replay, real provider acceptance separately |
| Linux compatibility | 7 | Several conservative capture adapters | Desktop setup differs; some experimental | Tested matrix, automated diagnostics, explicit experimental states and hardware acceptance |
| Installation/updates | 7 | AppImage/Flatpak/checksums/CI | Unsigned prereleases and manual restart | Verifiable update checks, preservation of work, signed release capability without invented signing identity |
| Architecture | 6 | Collector/storage/API separation | Large UI module; no decision service | Independent orchestration/policy/job/context modules and testable interfaces |
| Auditability | 5 | Origins/revisions/edit history | No AI evidence/action record | Persist source revision/fingerprint, selected context, full result, model/policy and action |

First pass target: address every category toward **8/10** with evidence.
Second pass: start from a fresh inventory and adversarial tests, target **9/10**.
Subsequent passes prioritise lower-scoring categories. Scores must reflect evidence;
external acceptance cannot be replaced with a claim based on offline fixtures.

## Decision architecture

**Completed observation → permitted local context → rule/validated preference →
cache or Jev → typed-result validation → execution policy → reversible draft or
exception → end-of-day review.** The worker is independent from the collector;
network/keyring errors must not block capture. No network transmission occurs
until that user enables the standing automation/data policy. Saving a key alone
is not consent to background sending. Each user supplies their own key.

Persist jobs and decisions. Deduplicate equivalent evidence/criteria/policy/model
inputs, recover abandoned leases, bound work and retries, distinguish permanent
errors, record token use and stop on caps. Before applying, recheck activity,
privacy policy, active tasks and uncovered intervals inside a transaction.
Never infer work in gaps, overwrite explicit assignments, approve or bill time.
Keep decisions explainable and drafts undoable. Do not send keys in logs/previews.

## How Jev should be used

Use small typed questions over meaningful approved evidence: best task, enough
evidence, work category, possible personal use, session relationship, conflict
with a prior assignment, value of clarification and support for a scoped pattern.
Jev is a typed decision model, not a free-text summary generator. Compose its
answers with explicit application logic and use factual templates for summaries.
Questions sharing a request are independent, not independent proof of correctness.

Unify single/batch/background results, preserving probabilities, alternatives,
model version and usage. Confidence is derived from probabilities; do not treat
it as another independent vote. Avoid a universal unvalidated “90% means safe”
rule. Gate actions on evidence, distribution, conflicts, observed performance and
impact. Evaluate representative examples and sample apparently easy decisions,
not just the uncertain ones. A correction is an example, not model retraining.

## Target user experience

Modes: Suggest; Organise automatically (recommended once validated); Trusted
patterns (only supported by measured evidence). The user sees plain language,
not threshold tuning. A one-time explicit policy defines permissible outgoing
context and resource limits; a visible pause and revoke control remain available.

Highest-value features: one clarification resolves relevant blocks, exception
inbox, contextual memory, factual daily summaries, drift detection and quiet
operation. Explain “why this task?” and provide change-this/change-similar/remember
controls with reversible scope. Keep final external financial actions explicit.

## Evaluation and release gates

Measure organised coverage, daily review time, questions/repeated corrections,
wrongly allocated minutes (especially across clients), unresolved/excluded work,
recovery and actual reported API usage. Numerical goals are objectives until
measured. Labelled synthetic cases prove policy/fixture behaviour, not live Jev
accuracy. Real provider and consenting-user cases must be marked separately.

Development order: unified results/evaluation/audit → meaningful permitted
context → durable background processing → automatic drafts → fewer questions →
real desktop/accessibility/provider acceptance and signed update delivery.

Before release: core and meaningful adversarial tests; virtual UI at normal and
200% scaling; private key-store/capture checks; fresh-install and existing-schema
migration/rollback validation; AppImage and Flatpak CI/runtime tests; review the
exact tree and package hashes; merge PR and publish only verified artifacts.

## Provider facts checked for the assessment

- Typed questions and composition: https://docs.typesafe.ai/introduction
- Probability/confidence guidance: https://docs.typesafe.ai/confidence
- Choice: https://docs.typesafe.ai/primitives/choice
- Pricing: https://help.typesafe.ai/articles/5187202169-how-much-does-jev-cost
- Data handling: https://help.typesafe.ai/articles/5974925716
- ZDR by request: https://help.typesafe.ai/articles/9520184411

At assessment time pricing was $0.042/million input tokens, output free. Treat
pricing as dated provider information, not a guaranteed future cost. Standard
retention has no published fixed duration; US processing and optional ZDR need
clear disclosure. Never claim ZDR has been enabled without confirmation.

## Evidence ledger and iteration status

### Baseline

0.4.0-rc2 source and prior test evidence reviewed; all 28 categories above assessed.
No live provider, hardware or assistive-technology accuracy claim exists.

### Pass 1 — engineering iteration completed

Implemented the 0.5 automation candidate across all categories. See
[AUTOMATION_REVIEW_0.5.md](AUTOMATION_REVIEW_0.5.md) for the full P1/P2 scorecard,
what changed, good/bad findings, exact evidence and remaining next steps.

### Pass 2 — fresh engineering review completed

Rechecked consent, stale evidence, rules/focus, concurrent edits/caps, unknown
spend, model identity, retention, upgrade ownership, keyboard/scaling and
packaging. Findings were fixed and tests rerun: 184 unit tests, independent
worker-process test, 53 existing scaled workflows, 19 daily-review checks, 21
automation UI checks and focused rule/key/portal checks. Eight held-out
synthetic live cases are recorded separately from real-work acceptance.

### Remaining score target

Not every category is evidenced at 8/9. Real-day accuracy (6.5), assistive
technology acceptance (6.5) and desktop/hardware coverage (7.5/8) cannot be
replaced by synthetic fixtures. The review lists the concrete acceptance steps
for these and other sub-9 categories. Preserve honest scores; iterate against
observed results. No new actual-data background policy was enabled by development.

### Release ledger

Candidate version: 0.5.0-rc1. Source tests and local isolated UI checks passed.
GitHub PR, trusted main package/provenance checks, published artifacts and local
upgrade must be verified before reporting release completion. Use release notes
and workflow/source SHAs as the final delivery record.


### 0.6 simplicity rebuild

The user found 0.5 too complicated. The new default removes rates, project forms,
rules, modes and billing from ordinary setup/day screens. Four clickable setup
steps, generic activity categories, a one-choice review, and a factual day-record
PDF replace that everyday flow. Advanced existing records/tools remain intact.
Tests and delivery evidence are recorded in SIMPLICITY_REVIEW_0.6.md and release
notes. Future improvements must preserve this simpler default.


### 0.6.1 — daily grouping and useful live cards (9 November 2026)

The user requested one decision for all like activity in a day, second-synchronised
counters, top activity totals and functioning statistic cards. The simple flow
now groups by app/day with a local daily choice, retains protected explicit work,
and shows inline filtered details and ranked apps. See DAILY_REVIEW_0.6.1.md for
the implementation, fresh race/privacy/undo review, tests and delivery gates.
Do not regress to per-observation questions or add configuration to this flow.


### Card text click correction (9 November 2026)

Card content labels are non-selectable and do not intercept pointer targeting.
Real mouse regression checks click both the number and caption of every card,
confirming the corresponding inline details activate. Keyboard button focus is
preserved; text outside buttons keeps its existing selection behaviour.

### Whole-day Jev and accessible tools (9 November 2026)

The user's selected workflow is Organise my day → apply clear matches → review
only uncertain apps. A bounded priority pass uses existing consent, cache and
usage safeguards; Assign handles each app/day directly. Optional sidebar tools
and day actions restore convenient access without complicating setup. See
[the implementation and fresh second review](ONE_CLICK_REVIEW_0.6.1.md) for exact
scope, midnight/concurrency findings, evidence and remaining real-world limits.

### Jev usefulness and optional tool setup (9 November 2026)

The fourth setup step now offers optional purpose-based tool shortcuts, reused in
Settings and each day's More actions. Selecting project/rule/report tools changes
navigation only, preserving generic AI context and explicit sending consent.
Reconnecting also retains existing app exclusions and custom request/token limits.
See [the product decision, second review and evidence](JEV_USEFUL_TOOLS.md): 245
offline tests and 75 default-flow GTK checks at normal and 200% scale passed.
Development changes only; real-day accuracy and external acceptance remain unverified.

### Deep review and improvement implementation (9 November 2026)

The [28-category review](DEEP_REVIEW_2026-11-09.md) rates the current working tree
and provides three concrete improvement actions per category. Its [plan](IMPROVEMENT_PLAN_2026-11-09.md)
and machine-readable register distinguish 48 implemented action entries, 18 retained
safeguards rechecked and 18 open acceptance gates. Shared fixes can satisfy more
than one action; these are not 48 independent product features. Ratings are current
engineering/evidence judgments, not measured AI accuracy or retroactive changes to
the original baseline.

Fixed cross-day unknown usage, scoped/indexed correction retrieval, explicit Forget
invalidation, transactional/serialised schema initialisation, malformed priority
state, missing-worker feedback, export/live-timer accounting, guarded Undo and
malformed update metadata. Added factual AI/rule explanations, new routing-version
records, starter guidance, local day digest, standalone contract/memory/status/setup
modules, offline response comparisons and a repeatable synthetic benchmark.

263 core tests, 81 default-flow GTK checks at normal and 200% scale, 53 retained
advanced GUI checks, 23 automation UI checks, worker-process and private synthetic
Secret portal/GNOME/KDE/X11 checks passed locally. See the review's validation
ledger and source fingerprint. Public CI is configured but not claimed run for
this uncommitted working tree. No real recorded activity or real key was used.
Hardware, novice/Orca, representative real-day accuracy and final package/release
acceptance remain open. Preserve the four-step/three-destination simple default.

### Personal/work screen-time iteration (9 November 2026)

See [the reassessment](PERSONAL_WORK_REASSESSMENT_2026-11-09.md),
[actual work log](PERSONAL_WORK_ITERATION.md) and
[28-category register](evidence/personal-work-category-register-2026-11-09.json).
The development source adds observed interval-union screen time, weekly/hourly
insight, eight owned generic types, local installed-app classification,
Personal/Work/Unsorted markers and history-preserving local schedules. Finite
period corrections, guarded Undo, content-free review counters, read-only health,
private CSV/PDF summaries and unlabelled evaluation templates remain separate
from client intent and financial approval. The default stays four setup steps and
Today/Past days/Settings. Existing categories, records and sending scopes are
preserved; desktop metadata and space labels stay local.

A separately explicit approval allowed exactly 20 public synthetic TypeSafe
requests. All 20 completed on jev-1.14.0 with 21,054 reported input tokens, 20
matching synthetic choices, 16 automatic routes and four exceptions. No recorded
user activity or private projects were sent. This is not representative real-day
accuracy. That approval is exhausted; further paid requests require new consent.

The first expanded validation reached 324 core tests, 93 simple GTK checks at
normal/200% scale, 53 retained advanced checks, 26 automation checks and the
packaged simple flow. SQLite quota recovery, private capture/portal protocols,
actual isolated GNOME, private X11 and worker process checks passed. The final
ledger must record later reruns and sustained results; long-run source hashes must
not be replaced with a later tree's hashes. All 18 earlier external acceptance
gates remain open. Ratings are judgments, not target achievement or certification.

Final local evidence: 328 core tests; 93 simple checks at normal scale and in the
200% bundled runtime; 15 async/filter/export/cleanup checks; completed two-hour
earlier core checkpoint and 30-minute final native UI. See the
[validation ledger](evidence/personal-work-validation-2026-11-09.json) for each
source scope. The sustained UI test found and verified a rendered-modal callback
retention fix. Passive reading/video remains dependent on desktop idle; no
playback/display-power evidence is collected. The final report preserves all 18
external gates and explicitly avoids phone-equivalence or target-score claims.

### 0.7.0-rc1 delivery — 9 November 2026

The user explicitly authorised finishing the app, uploading the code to GitHub
and updating this computer. See [delivery notes](DELIVERY_0.7.0.md). Preserve the
historical source-specific validation, run fresh release-candidate checks, use a
private pre-upgrade backup and separate installation folder, retain the older
checkout for rollback, and verify the launcher/collector after switching. Keep
all previous data/usage policies unchanged except compatible installation ownership.
Existing off policies stay off; no extra paid synthetic calls are covered by the
old exhausted 20-request approval. Real-day, hardware and human gates remain open.

### Official 0.7.0 release — 9 November 2026

The user explicitly requested public assets and an official release rather than
another prerelease. Promote the source version to 0.7.0, publish AppImage, Flatpak,
combined checksums and verified trusted-main provenance after the current tests
pass. The workflow stages assets in a draft and publishes with prerelease=false
and latest=true only after verifying the expected asset set. See
[release notes](RELEASE_0.7.0.md). This release-status decision does not change
historical scores or claim representative real-day/hardware/Orca acceptance.

The first official build passed core/package/provenance checks but its native
Assign regression encountered a replaced click target while the organiser closed
and the background day view refreshed. Publication stopped at the required Tests
gate. The harness now lets that refresh finish before locating its native target,
asserts modal unmapping and waits a bounded interval for the actual click result;
it neither retries the click nor bypasses review assertions. Record the following
build's result separately from the first failed GUI attempt.

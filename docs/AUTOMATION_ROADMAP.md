# Automation source of truth

Accepted by the user on 8 November 2026. This document preserves the assessment
of 0.4.0-rc2 and governs subsequent development. Read it before every improvement
or review. Keep the baseline intact; record later evidence separately.

## Product objective

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

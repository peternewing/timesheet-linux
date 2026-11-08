# Everyday setup in 0.6

Click **Set up in 4 steps**. Choose categories, choose privacy, connect your saved
key (or paste it), then Start. No names, rates or rules need typing.

Work as usual. If Jev asks, choose one category. Use **Save day record** for a PDF.
Today, Past days and Settings are the only everyday destinations.

The detailed guide below applies to optional **Settings → Advanced tools →
Detailed Jev controls**. It is not required for the everyday flow.

# Let Jev organise your day

Start on **Today → Set up Jev automation**. Use your own TypeSafe API key. It is
stored in the desktop's encrypted secret service; Flatpak uses its app-scoped
Secret portal. A key alone enables no background requests.

1. Describe your tasks briefly so Jev can distinguish them. The app warns about
   very similar guidance. Names and guidance should contain no secrets.
2. Start with **Prepare suggestions in the background**. Choose the processing
   period, optional context and usage limits. Read the data policy and enable it.
3. Choose **Focus** on Today when you know your next task. Focus is an intention,
   not a timer or proof of work. Its default is context only. The separate draft
   default checkbox explicitly authorises that task for the chosen period when
   Jev agrees; conflicting activity still needs your decision.
4. Check **Needs your decisions**. Resolve one period or the exact nearby periods
   previewed in the form. Remembering a correction is optional and local. It is
   supplied in later matching contexts only if you allow examples.
5. After checking suggestions, choose **Organise automatically as drafts** if it
   fits your work. This mode is experimental: thresholds are conservative
   heuristics, not measured correctness. Review drafts before approving time.

With titles off, focus gives context without collecting titles. With title
collection and local matching enabled separately, title words are matched locally
to task/project clues. Only task IDs and match counts are sent, never the title.
Background requests include application names, active client/project/task names,
your chosen focus, and only the optional guidance/examples you permit. Raw paths,
timestamps, entry descriptions and rates are not automatically added. Text you
enter in task names/guidance can itself contain sensitive information: review it.
Advanced setup provides an exact permitted-request preview before enabling work.

## An ordinary day

The collector records real active use independently. After the idle boundary
settles, saved rules handle exact local matches first; Jev considers eligible
unassigned work. It uses a durable queue and equivalent-request cache. Clear,
supported results make reversible drafts; uncertain results enter the inbox.
Jev never fills gaps, overwrites explicit allocations, approves work or bills it.

Today shows organised time, queue and exception counts, focus and pauses. The
inbox's **How automation is helping today** expands local workflow counts. Kept
suggestions in reviewed exceptions are not a measure of automatic accuracy.
**Why this decision?** shows permitted context, result, model and routing reason.
Jev entries also offer their decision history. Source-context retention removes
copied detail when source activity expires, retaining a minimal action record.

Use **Undo last edit** for the latest reversible change, or edit/split/delete an
individual draft. Undo will not overwrite protected later changes. Undoing a Jev
allocation does not cause the same job to recreate it immediately. Existing
entries remain when you turn automation off or forget examples.

## Quiet failures and costs

Recording continues offline and through provider/keyring failures. A missing key
pauses the decision worker once rather than repeatedly prompting for unlock.
The inbox explains how to unlock and Resume. Authentication/credit rejection
pauses; rate limiting has bounded backoff. An interrupted request may already
have been charged: sending pauses until you acknowledge unknown usage. History
and request counts are preserved. Check actual charges in your TypeSafe account.

The background daily request cap is strict. The reported input-token limit can be
crossed by one completed request because usage is returned afterwards. Limits
reset by the local calendar day. On-demand review requests remain separately
confirmed and bounded; they are not included in the background usage cap.

The first complete response pins the reported Jev version. A changed or missing
version cannot silently enter automatic execution. **Use current Jev model**
clears the cache and returns to suggestion mode for revalidation.

## Pause, upgrades and Linux

Choose Off and save to stop future sending. An already-sent request cannot be
recalled, but a revoked/changed policy prevents its stale result being applied.
A backup restore disables background automation until you explicitly set it up.
A different installation path or app version also requires setup again; the old
worker yields and cannot use the newer policy. Your key is not embedded in the
app or public packages.

Native/source/AppImage installations use a separate per-user decision service,
started with the app/collector and graphical login. Keep their installation path
permanent. Flatpak runs a separate sandbox child; some desktops restrict apps
after windows close. Keep Flatpak open for continuous Jev work until background
permission is verified on your desktop. The separate host capture companion is
still required. No desktop or screen-reader certification is implied.

Settings offers a read-only GitHub update check. It sends no activity or key and
does not download/install software. See INSTALL.md for checksum/provenance
verification, backup and installation. All 0.5 candidates remain prereleases.

## Measuring actual usefulness

Use `python3 -m timesheet.evaluate DATASET.json --preview` to inspect an evaluation
payload. Dataset format is demonstrated in `tests/fixtures/`. A live run requires
both `--live --allow-paid-requests`; it sends the inspected data to TypeSafe using
your own key. Use representative, deliberately labelled work and ambiguous cases,
including apparently easy auto decisions and cross-client work. Keep private
cases/results outside the repository. Offline replay is not live accuracy.
Measure time coverage, wrong minutes, cross-client errors, exception count and
actual time spent reviewing before trusting additional patterns. The app does
not train a new model from local correction examples.

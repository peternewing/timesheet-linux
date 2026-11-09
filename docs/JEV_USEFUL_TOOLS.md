# Jev usefulness and simple tool setup — 9 November 2026

User direction: question what Jev does, make it more useful, and integrate advanced
tools into a simple setup. Changes are in the development checkout only.

## Product decision

Jev's useful role is categorising recorded activity and reducing repeated choices.
App names cannot reliably establish a client, work intent or completed output.
The existing typed decisions, conservative routing, reversible drafts and whole-day
processing remain the basis of the product. Local rules handle predictable
assignments; project tools support deliberate time tracking; reports use reviewed,
approved entries. More AI calls would not by themselves resolve missing context.

## Implementation

The fourth setup step offers a collapsed, click-only optional tool chooser:
track time on projects, automate repeated assignments, prepare client reports.
Start saves the selected shortcuts in local settings. They appear in More actions
on Today and Past days and open the retained tools directly. Settings offers the
same choices and direct open actions. The default remains four setup steps and
three destinations, with no required names, rates or new setup fields.

Selecting tools changes navigation only. It does not add client/project/task names
to the simple AI context, enable sending or create rules, reports or billable time.
The existing advanced sidebar and other day actions remain available.

Repeating setup previously rebuilt the policy from defaults, dropping app exclusions
and custom request/token limits. It now retains these settings, and the final
disclosure displays the saved limits. Remembered-example consent starts with the
existing simple policy's choice when revisiting setup. Start remains the explicit
authorisation for the selected sending policy; connecting a key alone is insufficient.

## Fresh second review and evidence

- Rechecked optional choices before Start: they stay staged. Opening or choosing
  tools does not perform inference or change outgoing context. Invalid tool choices
  fail before category creation or policy changes.
- Rechecked existing private client tasks alongside selected project shortcuts:
  generic requests still contain only owned categories, never private project names.
- Rechecked reduced limits and exclusions on reconnect, including a completed
  excluded app in the eligible period: the worker makes no request for that app.
- Rechecked direct navigation, persistence across navigation, simple/advanced sidebar
  independence, non-billable draft handling, daily review, counters and database integrity.
- **245 offline unit/regression tests passed.**
- **75 default-flow GTK checks passed at normal and 200% scale**, using isolated
  Xvfb displays, synthetic records and a fake provider/key. Existing real mouse
  setup/card checks remain; new tool toggle/navigation checks use GTK controls.
- Visually inspected the actual ready-step screenshot: the primary Start action
  and collapsed optional tools fit the 500 × 650 window. Compilation and whitespace
  checks passed. The final help-text/screenshot-only edit does not change layout
  or control behaviour.

No real recorded activity was sent. No measured real-day accuracy, novice or
screen-reader acceptance, hardware validation, installation or published release
is claimed. This integrates access to existing tools; it does not add a new model
capability or demonstrate an increase in AI accuracy.

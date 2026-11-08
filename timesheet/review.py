"""Local-only helpers for a human-reviewed activity queue.

These helpers propose organisation and surface recorded facts. They never write
entries, infer work inside gaps, or turn model feedback into billing authority.
"""
from __future__ import annotations
import json
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime

MAX_LOCAL_CHOICES = 1000
MAX_CATEGORIES = 50
MAX_APP_NAME = 200
MAX_CATEGORY_NAME = 80
MAX_FEEDBACK_COUNT = 1_000_000_000
PROBABILITY_BINS = ('0–49%', '50–74%', '75–89%', '90–100%')
_BIDI_CONTROLS = frozenset(chr(c) for c in (*range(0x202a, 0x202f), *range(0x2066, 0x206a)))


def _plain_name(value, limit):
    return (isinstance(value, str) and 0 < len(value) <= limit
            and value.strip() == value
            and not any(ord(c) < 32 or ord(c) == 127 or c in _BIDI_CONTROLS for c in value))


def _task_ids(values):
    return {v for v in values if isinstance(v, int) and not isinstance(v, bool) and v > 0}


def _object(raw):
    # Settings can also come from an older or manually edited backup. Ignore
    # oversized/corrupt optional settings rather than disrupting core tracking.
    if not isinstance(raw, str) or len(raw) > 256_000:
        return {}
    try:
        value = json.loads(raw or '{}')
    except (ValueError, TypeError, RecursionError):
        return {}
    return value if isinstance(value, dict) else {}


def _merged_intervals(intervals):
    result = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def sessions(records, max_gap=300, *, barriers=()):
    """Propose nearby uncovered work blocks; preserve every recorded gap.

    ``barriers`` may contain the complete activity for the period. Personal,
    excluded, away, locked, unknown and live intervals stop sessions from joining
    across a boundary that merely looks like a short empty gap in an uncovered
    activity query. The output retains the original selected records.
    """
    if isinstance(max_gap, bool) or not isinstance(max_gap, int) or max_gap < 0:
        raise ValueError('Gap must be a non-negative whole number.')
    records = list(records)
    stops = []
    for r in [*records, *barriers]:
        if r.get('state') != 'active' or not r.get('closed'):
            if r['end'] > r['start']:
                stops.append((r['start'], r['end']))
    stops = _merged_intervals(stops)
    stop_ends = [end for _, end in stops]
    result = []
    seen = set()
    for r in sorted(records, key=lambda row: (row['start'], row['end'], row['id'])):
        if r.get('state') != 'active' or not r.get('closed') or not r.get('app') or r['end'] <= r['start']:
            continue
        identity = (r['id'], r['start'], r['end'])
        if identity in seen:
            continue
        seen.add(identity)
        previous = result[-1] if result else None
        stop_index = bisect_right(stop_ends, previous['end']) if previous is not None else len(stops)
        crosses_stop = stop_index < len(stops) and stops[stop_index][0] < r['start']
        joins = (previous is not None and r['start'] >= previous['end']
                 and r['start'] - previous['end'] <= max_gap
                 and datetime.fromtimestamp(r['start']).date() == datetime.fromtimestamp(previous['start']).date()
                 and not crosses_stop)
        if joins:
            previous['blocks'].append(r)
            previous['end'] = r['end']
            previous['seconds'] += r['end'] - r['start']
            if r['app'] not in previous['apps']:
                previous['apps'].append(r['app'])
        else:
            result.append({'start': r['start'], 'end': r['end'], 'seconds': r['end'] - r['start'],
                           'apps': [r['app']], 'blocks': [r]})
    return result


def rank_sessions(items, preferences=None):
    """Longer and less familiar sessions first, without dropping any results."""
    known = {name.casefold() for name in (preferences or {}) if isinstance(name, str)}
    def priority(item):
        unfamiliar = any(name.casefold() not in known for name in item['apps'])
        return (-int(unfamiliar), -item['seconds'], item['start'])
    return sorted(items, key=priority)


def readiness(entries, activity):
    """Surface facts for review, not assertions of work or billing eligibility."""
    drafts = [r for r in entries if r['status'] == 'draft']
    missing_description = sum(not str(r['description'] or '').strip() for r in drafts)
    missing_rate = sum(bool(r['billable']) and r['suggested_rate'] is None for r in drafts)
    # Count the union so duplicate observations do not inflate the gap total.
    intervals = _merged_intervals((r['start'], r['end']) for r in activity if r['state'] == 'unknown')
    gaps = sum(z - a for a, z in intervals)
    return {'drafts': len(drafts), 'missing_description': missing_description,
            'missing_rate': missing_rate, 'gap_seconds': gaps}


def _assignment_counts(rows):
    by_app = defaultdict(Counter)
    display = {}
    for row in rows:
        app, task, count = row['app'], row['task_id'], row['count']
        if not isinstance(app, str) or not app or not isinstance(task, int) or isinstance(task, bool) or task <= 0:
            continue
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            continue
        key = app.casefold()
        display.setdefault(key, app)
        by_app[key][task] += count
    return by_app, display


def rule_hints(rows, threshold=3):
    """Propose rules from consistent explicit assignments, case-insensitively."""
    if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 1:
        raise ValueError('Rule hint threshold must be a positive whole number.')
    by_app, display = _assignment_counts(rows)
    hints = []
    for app, counts in by_app.items():
        task, count = counts.most_common(1)[0]
        if count >= threshold and len(counts) == 1:
            hints.append((display[app], task, count))
    return sorted(hints, key=lambda x: (-x[2], x[0].casefold()))


def inconsistencies(rows):
    """Flag apps assigned to different tasks; this is not evidence of an error."""
    by_app, display = _assignment_counts(rows)
    return sorted((display[app], len(tasks)) for app, tasks in by_app.items() if len(tasks) > 1)


def budget_warning(spent, budget):
    if budget is None or budget <= 0:
        return None
    if spent >= budget:
        return 'At or over the project budget'
    if spent * 100 >= budget * 80:
        return 'At least 80% of the project budget used'
    return None


def load_preferences(raw, active_task_ids):
    """Read bounded local choices; ignore invalid and archived task IDs."""
    valid = _task_ids(active_task_ids)
    result, conflicts = {}, set()
    for name, task in _object(raw).items():
        if _plain_name(name, MAX_APP_NAME) and isinstance(task, int) and not isinstance(task, bool) and task in valid:
            key = name.casefold()
            if key in result and result[key] != task:
                conflicts.add(key)
            result.setdefault(key, task)
    return dict(list((k, v) for k, v in result.items() if k not in conflicts)[:MAX_LOCAL_CHOICES])


def _count(value):
    return min(value, MAX_FEEDBACK_COUNT) if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def feedback(raw, suggested, chosen, probability=None):
    """Aggregate opt-in outcomes, never activity, titles or inferred correctness."""
    if any(not isinstance(v, int) or isinstance(v, bool) or v <= 0 for v in (suggested, chosen)):
        raise ValueError('Feedback requires a positive suggested and chosen task ID.')
    data = _object(raw)
    outcome = 'accepted' if suggested == chosen else 'changed'
    result = {'accepted': _count(data.get('accepted')), 'changed': _count(data.get('changed'))}
    result[outcome] = min(MAX_FEEDBACK_COUNT, result[outcome] + 1)
    bins = data.get('bins', {})
    clean = {}
    if isinstance(bins, dict):
        for label in PROBABILITY_BINS:
            value = bins.get(label)
            if isinstance(value, dict):
                clean[label] = {'accepted': _count(value.get('accepted')), 'changed': _count(value.get('changed'))}
    if isinstance(probability, (int, float)) and not isinstance(probability, bool) and 0 <= probability <= 1:
        label = PROBABILITY_BINS[0 if probability < .5 else 1 if probability < .75 else 2 if probability < .9 else 3]
        value = clean.setdefault(label, {'accepted': 0, 'changed': 0})
        value[outcome] = min(MAX_FEEDBACK_COUNT, value[outcome] + 1)
    if clean:
        result['bins'] = clean
    return result


def load_categories(raw, active_task_ids):
    """Read bounded user aliases for currently active tasks."""
    valid = _task_ids(active_task_ids)
    result, keys, conflicts = {}, {}, set()
    for name, task in _object(raw).items():
        if (_plain_name(name, MAX_CATEGORY_NAME)
                and isinstance(task, int) and not isinstance(task, bool) and task in valid):
            key = name.casefold()
            if key in keys:
                if result[keys[key]] != task:
                    conflicts.add(key)
            else:
                result[name] = task
                keys[key] = name
    return dict(list((k, v) for k, v in result.items() if k.casefold() not in conflicts)[:MAX_CATEGORIES])


def add_categories(tasks, categories):
    """Build the same bounded labels shown in the outgoing-data preview.

    A long task name is left intact for the API's own validation. Aliases that
    cannot fit the API's label bound are omitted rather than breaking a request.
    """
    result = []
    for task, name in tasks:
        aliases = sorted((label for label, target in categories.items() if target == task
                          and _plain_name(label, MAX_CATEGORY_NAME)), key=str.casefold)
        label, included = name, []
        for alias in aliases:
            candidate = name + ' | User categories: ' + ', '.join([*included, alias])
            if len(candidate) <= 500:
                included.append(alias)
                label = candidate
        result.append((task, label))
    return result

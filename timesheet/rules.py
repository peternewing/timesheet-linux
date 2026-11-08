"""Read-only explanations and previews for deterministic assignment rules.

Match semantics mirror Store.matching_rule: application equality and title
substring use Unicode casefold; the highest priority wins; an equal top priority
for different targets abstains. Previews inspect retained evidence, not future
accuracy or the amount of still-unallocated work.
"""
from __future__ import annotations


def _get(row, key, default=None):
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _priority(row):
    value = _get(row, 'priority', 0)
    if isinstance(value, bool):
        raise ValueError('Priority must be a whole number.')
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value.strip())
    raise ValueError('Priority must be a whole number.')


def _archived(row):
    return (any(bool(_get(row, name, False)) for name in ('task_archived', 'project_archived', 'client_archived'))
            or not bool(_get(row, 'target_active', True)))


def _valid_target(row):
    value = _get(row, 'task_id')
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _active(row):
    if not _get(row, 'enabled', 1) or _archived(row) or not _valid_target(row) or not str(_get(row, 'app', '')).strip():
        return False
    try:
        _priority(row)
    except (ValueError, OverflowError):
        return False
    return True


def _filter(row):
    return str(_get(row, 'app', '')).casefold(), str(_get(row, 'title', '')).casefold()


def _matches(rule, activity):
    app, title = _filter(rule)
    return app == str(_get(activity, 'app', '')).casefold() and title in str(_get(activity, 'title', '')).casefold()


def _others(rule, rules):
    own_id = _get(rule, 'id')
    return [other for other in rules if other is not rule and not (own_id is not None and _get(other, 'id') == own_id)]


def _ids(rows):
    return [value for row in rows if (value := _get(row, 'id')) is not None]


def describe_rule(rule, target_label=None):
    """Return a complete plain-language description, with no implied approval."""
    app, title = str(_get(rule, 'app', '')).strip(), str(_get(rule, 'title', ''))
    if target_label is None:
        pieces = [_get(rule, key) for key in ('client', 'project', 'task')]
        target_label = ' / '.join(str(piece) for piece in pieces if piece)
        if not target_label:
            target_label = 'the selected task' if _get(rule, 'task_id') is None else f"task #{_get(rule, 'task_id')}"
    condition = f'When the application is “{app or "choose an application"}”'
    if title:
        condition += f' and its window title contains “{title}”'
    else:
        condition += ', with any window title'
    return condition + f', assign matching recorded time to “{target_label}” as draft time for review.'


def rule_health(rule, rules, *, capture_titles=True):
    """Return diagnostics as code/message/level/other_ids dictionaries.

    Exact filter ties are distinguished from title filters that could overlap.
    Potential overlap alone is never described as an observed conflict.
    """
    result = []
    def add(code, message, level='warning', others=()):
        result.append({'code': code, 'message': message, 'level': level, 'other_ids': _ids(others)})
    if not _get(rule, 'enabled', 1):
        add('paused', 'Paused: this rule does not assign new activity.', 'info')
    if _archived(rule):
        add('target_archived', 'Its task, project or client is archived. Choose an active target.')
    if not _valid_target(rule):
        add('target_missing', 'Choose an active task for this rule.')
    if not str(_get(rule, 'app', '')).strip():
        add('application_missing', 'Choose the application name shown in captured activity.')
    try:
        priority = _priority(rule)
    except (ValueError, OverflowError):
        priority = None
        add('priority_invalid', 'Priority must be a whole number.')
    app, title = _filter(rule)
    if title and not capture_titles:
        add('titles_off', 'Window titles are off. New activity will not match this title filter; older saved titles may still match.')
    peers = [r for r in _others(rule, rules) if _active(r) and _filter(r)[0] == app and _priority(r) == priority]
    duplicates = [r for r in peers if _filter(r)[1] == title and _get(r, 'task_id') == _get(rule, 'task_id')]
    exact_ties = [r for r in peers if _filter(r)[1] == title and _get(r, 'task_id') != _get(rule, 'task_id')]
    potential = [r for r in peers if _filter(r)[1] != title and _get(r, 'task_id') != _get(rule, 'task_id')]
    if duplicates:
        add('duplicate', 'Another active rule has the same filter, target and priority. Keeping both adds no benefit.', 'info', duplicates)
    if exact_ties:
        add('exact_conflict', 'Another active rule uses the same application, title filter and priority for a different task. Matching time needs review unless a higher-priority rule wins.', others=exact_ties)
    if potential:
        add('potential_overlap', 'A different title filter has the same application and priority but another task. A title could match both; check the preview.', 'info', potential)
    return result


def _duration(intervals):
    total, finish = 0, None
    for start, end in sorted(intervals):
        if finish is None or start >= finish:
            total += end - start
        elif end > finish:
            total += end - finish
        finish = max(finish, end) if finish is not None else end
    return total


def evaluate_rule(proposed, rules, activity, *, capture_titles=True, examples_limit=3, settled_before=None):
    """Preview a rule against retained completed active activity without mutation.

    Creation times are deliberately ignored, as for an explicit reapply preview.
    ``matched_seconds`` is filter coverage, not guaranteed new assignment: this
    helper does not receive allocations. ``conflict_seconds`` counts only a
    matching proposed rule at equal top priority for a different target;
    higher-priority matches are instead reported as shadowed.
    """
    if isinstance(examples_limit, bool) or not isinstance(examples_limit, int) or not 0 <= examples_limit <= 10:
        raise ValueError('Preview examples must be between zero and ten.')
    rules = list(rules)
    others = _others(proposed, rules)
    usable = [r for r in others if _active(r)]
    active = _active(proposed)
    intervals = {'matched': [], 'would_assign': [], 'conflict': [], 'shadowed': []}
    counts = {name: 0 for name in intervals}
    examples, conflicts, seen = [], [], set()
    rows = sorted(activity, key=lambda r: (_get(r, 'start', 0), _get(r, 'end', 0), _get(r, 'id', 0)))
    for row in rows:
        start, end = _get(row, 'start'), _get(row, 'end')
        if (_get(row, 'state', 'active') != 'active' or not _get(row, 'closed', 1)
                or not isinstance(start, int) or not isinstance(end, int) or end <= start
                or (settled_before is not None and end > settled_before) or not _matches(proposed, row)):
            continue
        identity = (_get(row, 'id'), start, end, _get(row, 'app', ''), _get(row, 'title', ''))
        if identity in seen:
            continue
        seen.add(identity)
        intervals['matched'].append((start, end)); counts['matched'] += 1
        status, top = 'inactive', []
        if active:
            matches = [proposed, *[r for r in usable if _matches(r, row)]]
            highest = max(_priority(r) for r in matches)
            top = [r for r in matches if _priority(r) == highest]
            if highest > _priority(proposed):
                status = 'shadowed'
            elif len({_get(r, 'task_id') for r in top}) > 1:
                status = 'conflict'
            else:
                status = 'would_assign'
            intervals[status].append((start, end)); counts[status] += 1
        example = {'id': _get(row, 'id'), 'app': str(_get(row, 'app', '')), 'title': str(_get(row, 'title', '')),
                   'start': start, 'end': end, 'status': status, 'rule_ids': _ids(top)}
        if len(examples) < examples_limit:
            examples.append(example)
        if status == 'conflict' and len(conflicts) < examples_limit:
            conflicts.append(example)
    return {'matched_seconds': _duration(intervals['matched']), 'matched_count': counts['matched'],
            'would_assign_seconds': _duration(intervals['would_assign']), 'would_assign_count': counts['would_assign'],
            'conflict_seconds': _duration(intervals['conflict']), 'conflict_count': counts['conflict'],
            'shadowed_seconds': _duration(intervals['shadowed']), 'shadowed_count': counts['shadowed'],
            'examples': examples, 'conflicts': conflicts,
            'health': rule_health(proposed, rules, capture_titles=capture_titles)}

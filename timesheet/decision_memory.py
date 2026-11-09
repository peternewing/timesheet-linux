"""Scoped local correction examples; a correction is guidance, not retraining."""
from .decision_context import canonical


def remember(store,activity_id,application,task_id,scope,at):
    store.db.execute('''INSERT INTO ai_examples(activity_id,application,task_id,at,scope,app_key)
        VALUES(?,?,?,?,?,?) ON CONFLICT(activity_id) DO UPDATE SET application=excluded.application,
        task_id=excluded.task_id,at=excluded.at,scope=excluded.scope,app_key=excluded.app_key''',
        (activity_id,application,task_id,at,scope,application.casefold()))


def relevant(store,application,task_ids,clues,focus):
    # Filter the app/scope before limiting, so unrelated history cannot crowd out
    # a useful example. Updated corrections sort by correction time, not row ID.
    if not task_ids:return []
    ids=sorted(task_ids)
    rows=store.rows('''SELECT application,task_id FROM (
        SELECT e.application,e.task_id,e.at,e.id,ROW_NUMBER() OVER (
            PARTITION BY date(a.start,'unixepoch','localtime') ORDER BY e.at DESC,e.id DESC) day_choice
        FROM ai_examples e JOIN activity a ON a.id=e.activity_id
        WHERE e.app_key=? AND e.scope=? AND a.state='active' AND a.closed=1
          AND e.app_key=timesheet_casefold(a.app)
          AND e.task_id IN ('''+','.join('?' for _ in ids)+'''))
        WHERE day_choice=1 ORDER BY at DESC,id DESC LIMIT 8''',
        (application.casefold(),canonical({'clues':clues,'focus':focus}),*ids))
    return [dict(application=r['application'],task=r['task_id']) for r in rows]

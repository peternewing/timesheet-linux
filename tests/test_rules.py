import sqlite3
import unittest
from timesheet.rules import describe_rule, rule_health, evaluate_rule


def rule(id=1, app='Editor', title='', task=1, priority=0, **extra):
    return dict(id=id,app=app,title=title,task_id=task,priority=priority,enabled=1,created=0,**extra)


def activity(id=1, app='Editor', title='', start=1000, end=1100, **extra):
    return dict(id=id,app=app,title=title,start=start,end=end,state='active',closed=1,**extra)


class RuleHelpTests(unittest.TestCase):
    def test_plain_description_explains_conditions_target_and_draft(self):
        text=describe_rule(rule(title='Client'), 'Studio / Website / Design')
        self.assertIn('application is “Editor”',text); self.assertIn('contains “Client”',text)
        self.assertIn('Studio / Website / Design',text); self.assertIn('draft time for review',text)
        self.assertIn('any window title',describe_rule(rule()))

    def test_health_explains_paused_archived_and_title_capture(self):
        r=rule(title='Client',task_archived=1);r['enabled']=0
        codes={d['code'] for d in rule_health(r,[],capture_titles=False)}
        self.assertEqual(codes,{'paused','target_archived','titles_off'})
        self.assertIn('older saved titles',next(d['message'] for d in rule_health(r,[],capture_titles=False) if d['code']=='titles_off'))

    def test_duplicate_is_not_a_different_task_conflict(self):
        r=rule(); duplicate=rule(id=2,app='editor')
        health=rule_health(r,[r,duplicate])
        self.assertEqual([d['code'] for d in health],['duplicate'])
        self.assertEqual(health[0]['other_ids'],[2])
        self.assertEqual(evaluate_rule(r,[duplicate],[activity()])['would_assign_seconds'],100)

    def test_different_title_filters_are_potential_until_observed(self):
        r=rule(title='alpha');other=rule(id=2,title='beta',task=2)
        self.assertEqual([d['code'] for d in rule_health(r,[other])],['potential_overlap'])
        result=evaluate_rule(r,[other],[activity(title='alpha only'),activity(id=2,title='beta only',start=1100,end=1200)])
        self.assertEqual((result['matched_count'],result['conflict_count']),(1,0))
        actual=evaluate_rule(r,[other],[activity(title='ALPHA beta')])
        self.assertEqual(actual['conflict_seconds'],100)
        self.assertEqual(actual['conflicts'][0]['status'],'conflict')

    def test_exact_tie_is_reported_with_higher_priority_override_distinguished(self):
        r=rule(title='client');tie=rule(id=2,title='CLIENT',task=2)
        self.assertIn('exact_conflict',{d['code'] for d in rule_health(r,[tie])})
        higher=rule(id=3,title='',task=3,priority=1)
        result=evaluate_rule(r,[tie,higher],[activity(title='Client work')])
        self.assertEqual((result['conflict_seconds'],result['shadowed_seconds'],result['would_assign_seconds']),(0,100,0))

    def test_casefold_matching_agrees_with_store_and_higher_priority(self):
        r=rule(app='Straße',title='DESIGN',priority=-2)
        other=rule(id=2,app='STRASSE',title='admin',task=2,priority=1)
        rows=[activity(app='STRASSE',title='Design',start=1000,end=1100),activity(id=2,app='Straße',title='design ADMIN',start=1100,end=1200)]
        result=evaluate_rule(r,[other],rows)
        self.assertEqual((result['matched_seconds'],result['would_assign_seconds'],result['shadowed_seconds']),(200,100,100))

    def test_disabled_and_archived_other_rules_do_not_block(self):
        r=rule();paused=rule(id=2,task=2);paused['enabled']=0
        archived=rule(id=3,task=3,project_archived=1)
        result=evaluate_rule(r,[paused,archived],[activity()])
        self.assertEqual(result['would_assign_seconds'],100)
        self.assertFalse(result['health'])

    def test_inactive_proposed_rule_still_previews_filter_without_promise(self):
        r=rule();r['enabled']=0
        result=evaluate_rule(r,[],[activity()])
        self.assertEqual((result['matched_seconds'],result['would_assign_seconds']),(100,0))
        self.assertEqual(result['examples'][0]['status'],'inactive')

    def test_preview_excludes_nonwork_live_and_unsettled_observations(self):
        rows=[activity(),activity(id=2,start=1100,end=1200),activity(id=3,start=1200,end=1300),activity(id=4,start=1300,end=1400)]
        rows[1]['state']='personal';rows[2]['closed']=0
        result=evaluate_rule(rule(),[],rows,settled_before=1350)
        self.assertEqual((result['matched_seconds'],result['matched_count']),(100,1))

    def test_preview_is_retained_evidence_not_forward_created_cutoff(self):
        r=rule();r['created']=9999999
        result=evaluate_rule(r,[],[activity()])
        self.assertEqual(result['matched_seconds'],100)
        self.assertEqual(result['would_assign_seconds'],100)

    def test_preview_deduplicates_examples_and_unions_overlapping_durations(self):
        rows=[activity(),activity(),activity(id=2,start=1050,end=1150)]
        result=evaluate_rule(rule(),[],rows,examples_limit=1)
        self.assertEqual((result['matched_seconds'],result['matched_count'],len(result['examples'])),(150,2,1))
        with self.assertRaises(ValueError):evaluate_rule(rule(),[],rows,examples_limit=11)

    def test_rule_being_edited_is_replaced_not_counted_twice(self):
        old=rule(task=2);proposed=rule(task=1)
        self.assertEqual(evaluate_rule(proposed,[old],[activity()])['conflict_count'],0)

    def test_preview_task_outcomes_match_the_store_for_observed_titles(self):
        import tempfile
        from pathlib import Path
        from timesheet.store import Store
        with tempfile.TemporaryDirectory() as temp:
            store=Store(Path(temp)/'rules.sqlite3')
            task1=store.quick_project('Client','Project','Design',6000)
            task2=store.add_task(store.rows('SELECT id FROM projects')[0]['id'],'Admin')
            first=store.add_rule('Straße','design',task1,2)
            store.add_rule('STRASSE','admin',task2,2)
            store.add_rule('Straße','override',task2,3)
            rules=store.rows("SELECT r.*,t.archived task_archived,p.archived project_archived,c.archived client_archived FROM rules r JOIN tasks t ON t.id=r.task_id JOIN projects p ON p.id=t.project_id JOIN clients c ON c.id=p.client_id")
            proposed=next(r for r in rules if r['id']==first)
            for title in ('DESIGN','design admin','design override','admin','nothing'):
                actual=store.matching_rule('STRASSE',title)
                preview=evaluate_rule(proposed,rules,[activity(app='STRASSE',title=title)])
                if 'design' not in title.casefold():
                    self.assertEqual(preview['matched_count'],0)
                elif actual is None:
                    self.assertEqual(preview['conflict_count'],1)
                elif actual['task_id']==task1:
                    self.assertEqual(preview['would_assign_count'],1)
                else:
                    self.assertEqual(preview['shadowed_count'],1)
            store.close()

    def test_sqlite_rows_are_supported_without_dict_get(self):
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        r=db.execute("SELECT 1 id,'Editor' app,'' title,1 task_id,0 priority,1 enabled").fetchone()
        self.assertIn('Editor',describe_rule(r))
        self.assertEqual(evaluate_rule(r,[r],[activity()])['would_assign_seconds'],100)
        db.close()


if __name__=='__main__':unittest.main()

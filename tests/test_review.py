import unittest
from timesheet import review

class ReviewTests(unittest.TestCase):
    def test_sessions_preserve_gaps_and_filter_unavailable(self):
        items=[dict(id=1,start=1000,end=1100,app='Editor',state='active',closed=1),dict(id=2,start=1200,end=1300,app='Browser',state='active',closed=1),dict(id=3,start=1300,end=1400,app='Secret',state='excluded',closed=1),dict(id=4,start=1400,end=1500,app='Editor',state='active',closed=0)]
        groups=review.sessions(items)
        self.assertEqual(len(groups),1);self.assertEqual(groups[0]['seconds'],200)
        self.assertEqual([x['id'] for x in groups[0]['blocks']],[1,2]);self.assertEqual(groups[0]['apps'],['Editor','Browser'])
    def test_ranking_never_drops_familiar_sessions(self):
        items=[dict(start=1,seconds=900,apps=['Known']),dict(start=2,seconds=100,apps=['New'])]
        self.assertEqual([s['start'] for s in review.rank_sessions(items,{'known':3})],[2,1])
    def test_readiness_is_advisory(self):
        rows=[dict(status='draft',description='',billable=1,suggested_rate=None),dict(status='approved',description='',billable=1,suggested_rate=None)]
        self.assertEqual(review.readiness(rows,[dict(state='unknown',start=2,end=5)]),dict(drafts=1,missing_description=1,missing_rate=1,gap_seconds=3))
    def test_rule_hints_do_not_hide_inconsistent_assignments(self):
        data=[dict(app='Editor',task_id=1,count=3),dict(app='Browser',task_id=1,count=4),dict(app='Browser',task_id=2,count=1)]
        self.assertEqual(review.rule_hints(data),[('Editor',1,3)])
        self.assertEqual(review.inconsistencies(data),[('Browser',2)])
    def test_local_preferences_ignore_invalid_and_archived_tasks(self):
        self.assertEqual(review.load_preferences('{"editor":1,"browser":2,"bad":true}',[1]),{'editor':1})
        self.assertEqual(review.load_preferences('broken',[1]),{})
    def test_categories_only_include_active_tasks(self):
        c=review.load_categories('{"design":1,"old":2,"bad":true}',[1])
        self.assertEqual(c,{'design':1})
        self.assertEqual(review.add_categories([(1,'Client / Site')],c),[(1,'Client / Site | User categories: design')])

    def test_feedback_counts_only_explicit_results(self):
        self.assertEqual(review.feedback('{}',1,1),{'accepted':1,'changed':0})
        self.assertEqual(review.feedback('{"accepted":1,"changed":0}',1,2),{'accepted':1,'changed':1})
        self.assertEqual(review.feedback('{}',1,2,0.82)['bins']['75–89%'],{'accepted':0,'changed':1})

    def test_sessions_do_not_join_across_explicit_privacy_or_capture_barriers(self):
        left=dict(id=1,start=1000,end=1100,app='Editor',state='active',closed=1)
        right=dict(id=2,start=1200,end=1300,app='Editor',state='active',closed=1)
        for state in ('excluded','personal','away','locked','unknown'):
            barrier=dict(id=3,start=1100,end=1200,app='',state=state,closed=1)
            with self.subTest(state=state):
                self.assertEqual(len(review.sessions([left,right],barriers=[barrier])),2)
        self.assertEqual(len(review.sessions([left,right])),1)

    def test_sessions_deduplicate_exact_blocks_but_preserve_uncovered_fragments(self):
        first=dict(id=1,start=1000,end=1100,app='Editor',state='active',closed=1)
        second=dict(first,start=1200,end=1250)
        result=review.sessions([first,first,second])
        self.assertEqual(result[0]['seconds'],150)
        self.assertEqual(len(result[0]['blocks']),2)
        with self.assertRaises(ValueError): review.sessions([],float('inf'))

    def test_sessions_do_not_join_across_midnight(self):
        from datetime import datetime
        midnight=int(datetime(2026,11,9).timestamp())
        rows=[dict(id=1,start=midnight-60,end=midnight-1,app='Editor',state='active',closed=1),dict(id=2,start=midnight,end=midnight+60,app='Editor',state='active',closed=1)]
        self.assertEqual(len(review.sessions(rows)),2)

    def test_gap_summary_counts_union_of_duplicate_or_nested_observations(self):
        rows=[dict(state='unknown',start=100,end=110),dict(state='unknown',start=102,end=104),dict(state='unknown',start=108,end=115)]
        self.assertEqual(review.readiness([],rows)['gap_seconds'],15)

    def test_case_variants_cannot_create_false_consistent_rule_hints(self):
        data=[dict(app='Editor',task_id=1,count=3),dict(app='editor',task_id=2,count=1)]
        self.assertEqual(review.rule_hints(data),[])
        self.assertEqual(review.inconsistencies(data),[('Editor',2)])
        data[1]['task_id']=1
        self.assertEqual(review.rule_hints(data),[('Editor',1,4)])

    def test_local_preferences_reject_conflicting_or_spoofed_names(self):
        raw='{"Editor":1,"editor":2,"bad\\u202ename":1,"":1}'
        self.assertEqual(review.load_preferences(raw,[1,2]),{})
        self.assertEqual(review.load_preferences('x'*256001,[1]),{})

    def test_category_labels_are_bounded_without_cutting_task_names(self):
        name='Task '+('x'*450)
        aliases={'A'*30:1,'B'*30:1,'C'*30:1}
        result=review.add_categories([(1,name)],aliases)[0][1]
        self.assertTrue(result.startswith(name))
        self.assertLessEqual(len(result),500)
        self.assertNotIn('B'*30,result)
        self.assertEqual(review.load_categories('{"Design":1,"design":2}',[1,2]),{})

    def test_feedback_is_bounded_and_rejects_non_decisions(self):
        result=review.feedback('{"accepted":1000000000000000,"changed":false}',1,1)
        self.assertEqual(result,{'accepted':review.MAX_FEEDBACK_COUNT,'changed':0})
        for suggested,chosen in ((None,1),(True,1),(1,0),({},1)):
            with self.subTest(suggested=suggested):
                with self.assertRaises(ValueError): review.feedback('{}',suggested,chosen)

    def test_budget_thresholds(self):
        self.assertIsNone(review.budget_warning(79,100));self.assertIn('80%',review.budget_warning(80,100));self.assertIn('over',review.budget_warning(100,100));self.assertIsNone(review.budget_warning(1,0))

if __name__=='__main__': unittest.main()

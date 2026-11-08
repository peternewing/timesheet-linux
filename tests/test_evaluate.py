import unittest
import json
from pathlib import Path
from unittest.mock import Mock
from timesheet.evaluate import evaluate


def case(expected=1,context=True):
    return dict(applications=['Editor'],tasks=[(1,'Synthetic task')],expected_task=expected,seconds=600,has_context=context,
        result=dict(task=1,probability=.99,none_probability=.01,alternatives=[(1,.99)],personal=.01,enough_evidence=.99,
            work_kind='development',model='jev-test',usage={'input_tokens':100,'output_tokens':10}))


class EvaluateTests(unittest.TestCase):
    def test_replay_reports_mistakes_and_does_not_claim_live_accuracy(self):
        result=evaluate([case(),case(None),case(context=False)])
        self.assertIn('does not measure live',result['evidence'])
        self.assertEqual(result['metrics']['automated'],2)
        self.assertEqual(result['metrics']['automated_precision'],.5)
        self.assertEqual(result['metrics']['wrong_minutes'],10)
        self.assertEqual(result['metrics']['exception_cases'],1)
    def test_live_run_uses_only_supplied_context_and_label_is_not_sent(self):
        calls=[]
        def request(apps,tasks,key,**kwargs):calls.append((apps,tasks,key,kwargs));return case()['result']
        result=evaluate([case()],live=True,request=request,key='synthetic')
        self.assertEqual(len(calls),1);self.assertNotIn('expected_task',str(calls))
        self.assertEqual(result['evidence'],'live labelled evaluation')
    def test_invalid_dataset_and_duration_rejected(self):
        for data in [[],{},[case()|{'seconds':True}],[case()|{'expected_task':5}]]:
            with self.subTest(data=data),self.assertRaises(ValueError):evaluate(data)


class RecordedLiveReplayTests(unittest.TestCase):
    def test_invalid_later_case_does_not_send_partial_live_requests(self):
        request=Mock()
        with self.assertRaises(ValueError):evaluate([case(),case()|{'seconds':False}],live=True,request=request,key='synthetic')
        request.assert_not_called()

    def test_recorded_live_cases_replay_the_documented_policy(self):
        cases=json.loads((Path(__file__).parent/'fixtures/jev_live_heldout_recorded.json').read_text())
        result=evaluate(cases)
        self.assertEqual(result['metrics']['automated'],4)
        self.assertEqual(result['metrics']['correct_automated'],4)
        self.assertEqual(result['metrics']['exception_cases'],4)
        self.assertEqual(result['metrics']['wrong_minutes'],0)
        self.assertIn('does not measure live',result['evidence'])

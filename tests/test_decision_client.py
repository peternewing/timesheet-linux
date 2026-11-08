import copy,io,json,unittest
from unittest.mock import Mock
from timesheet import jev


def response():
    return {'model':'jev-test','usage':{'input_tokens':100,'output_tokens':10},'answers':{
        'task':{'type':'choice','choice':'task_7','probabilities':{'task_7':.99,'none':.01},'confidence':.98},
        'personal':{'type':'noul','noul':.01},'enough_evidence':{'type':'noul','noul':.99},
        'work_kind':{'type':'choice','choice':'development','probabilities':{k:float(k=='development') for k in jev.WORK_KINDS},'confidence':1}}}


class DecisionClientTests(unittest.TestCase):
    def call(self,value,**kwargs):
        opener=Mock();opener.open.return_value=io.BytesIO(json.dumps(value).encode())
        return jev.decide(['Editor'],[(7,'Acme / Falcon / Development')],'synthetic',opener=opener,**kwargs),opener
    def test_typed_questions_and_full_metadata(self):
        result,opener=self.call(response(),clues=[{'task':7,'matching_terms':2}],examples=[{'application':'Editor','task':7}],model='jev-test')
        sent=json.loads(opener.open.call_args.args[0].data)
        self.assertEqual(set(sent['questions']),{'task','personal','enough_evidence','work_kind'})
        self.assertEqual(sent['state']['local_project_matches'],[{'task':7,'matching_terms':2}])
        self.assertEqual(result['confidence'],.98);self.assertEqual(result['none_probability'],.01)
        self.assertEqual(result['enough_evidence'],.99);self.assertEqual(result['work_kind'],'development')
    def test_missing_or_malformed_metadata_cannot_drive_automation(self):
        values=[]
        for key in ['model','usage']:
            item=response();item.pop(key);values.append(item)
        for key in ['personal','enough_evidence','work_kind']:
            item=response();item['answers'].pop(key);values.append(item)
        item=response();item['answers']['enough_evidence']['noul']=True;values.append(item)
        item=response();item['answers']['work_kind']['choice']='invented';values.append(item)
        item=response();item['answers']['work_kind']['probabilities']['other']=.9;values.append(item)
        item=response();item['answers']['work_kind']['confidence']='certain';values.append(item)
        item=response();item['model']='jev-other';values.append(item)
        for value in values:
            with self.subTest(value=value),self.assertRaises(jev.JevError):self.call(value,model='jev-test')
    def test_invalid_context_is_rejected_before_key_or_network(self):
        for kwargs in [dict(model='https://other.test'),dict(clues=[{'task':8,'matching_terms':2}]),dict(clues=[{'task':7,'matching_terms':True}]),dict(examples=[{'application':'Editor','task':7,'title':'private'}])]:
            with self.subTest(kwargs=kwargs),self.assertRaises(jev.JevError):jev.prepare_decision(['Editor'],[(7,'Task')],**kwargs)
    def test_batch_can_preserve_richer_uncertainty(self):
        seen=[];request=Mock(return_value={'task':7,'probability':.52,'alternatives':[(7,.52),(8,.47)],'personal':.1})
        jev.suggest_batch(['Editor'],[(7,'Task')],'synthetic',lambda:False,lambda *args:seen.append(args),request=request,detailed=True)
        self.assertIsInstance(seen[0][1],dict)

"""Replay labelled decision evidence; live inference is separately, explicitly opt-in."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .automation_worker import valid_result
from .decision_policy import route
from . import jev


def evaluate(cases,*,live=False,request=None,key=None):
    if not isinstance(cases,list) or not 1<=len(cases)<=1000:raise ValueError('Use 1–1000 labelled examples.')
    if live and len(cases)>50:raise ValueError('A live run is limited to 50 requests.')
    totals=dict(cases=len(cases),automated=0,correct_automated=0,wrong_minutes=0,recorded_minutes=0,exception_cases=0,automated_minutes=0,correct_choices=0,input_tokens=0)
    rows=[]
    # Validate the complete dataset before a paid request or partial run.
    for case in cases:
        if not isinstance(case,dict) or not {'applications','tasks','expected_task','seconds','has_context'}<=case.keys():raise ValueError('Each example needs apps, tasks, expected task, seconds and context flag.')
        if type(case['seconds']) is not int or not 0<case['seconds']<=86400 or type(case['has_context']) is not bool:raise ValueError('Example duration or context is invalid.')
        jev.prepare_decision(case['applications'],case['tasks'],examples=case.get('examples',[]),clues=case.get('clues',[]),focus=case.get('focus'),focus_default=case.get('focus_default',False),application_categories=case.get('application_categories',False),model=case.get('model','jev-latest'))
        if case['expected_task'] is not None and (type(case['expected_task']) is not int or case['expected_task'] not in [i for i,_ in case['tasks']]):raise ValueError('The expected task must be an offered option or null.')
    for case in cases:
        if not isinstance(case,dict) or not {'applications','tasks','expected_task','seconds','has_context'}<=case.keys():raise ValueError('Each example needs apps, tasks, expected task, seconds and context flag.')
        if type(case['seconds']) is not int or not 0<case['seconds']<=86400 or type(case['has_context']) is not bool:raise ValueError('Example duration or context is invalid.')
        tasks=case['tasks'];payload=jev.prepare_decision(case['applications'],tasks,examples=case.get('examples',[]),clues=case.get('clues',[]),focus=case.get('focus'),focus_default=case.get('focus_default',False),application_categories=case.get('application_categories',False),model=case.get('model','jev-latest'))
        if case['expected_task'] is not None and (type(case['expected_task']) is not int or case['expected_task'] not in [i for i,_ in tasks]):raise ValueError('The expected task must be an offered option or null.')
        if live:
            call=request or jev.decide
            result=call(case['applications'],tasks,key,examples=case.get('examples',[]),clues=case.get('clues',[]),focus=case.get('focus'),focus_default=case.get('focus_default',False),application_categories=case.get('application_categories',False),model=case.get('model','jev-latest'))
        else:result=case.get('result')
        if not valid_result(result,tasks,case.get('model','jev-latest')):raise ValueError('An example has invalid decision metadata.')
        action,reason=route(result,'automatic',has_context=case['has_context'],focus_task=case.get('focus'),focus_default=case.get('focus_default',False),application_categories=case.get('application_categories',False))
        automated=action=='apply';correct=result['task']==case['expected_task'];minutes=case['seconds']/60
        totals['recorded_minutes']+=minutes
        totals['correct_choices']+=int(correct);totals['input_tokens']+=result['usage']['input_tokens']
        if automated:
            totals['automated_minutes']+=minutes
            totals['automated']+=1;totals['correct_automated']+=int(correct)
            if not correct:totals['wrong_minutes']+=minutes
        else:totals['exception_cases']+=1
        rows.append(dict(action=action,correct=correct,reason=reason,model=result['model']))
    totals['automation_coverage']=totals['automated']/len(cases)
    totals['time_coverage']=totals['automated_minutes']/totals['recorded_minutes']
    totals['choice_accuracy']=totals['correct_choices']/len(cases)
    totals['automated_precision']=totals['correct_automated']/totals['automated'] if totals['automated'] else None
    return dict(evidence='live labelled evaluation' if live else 'offline replay: does not measure live Jev accuracy',metrics=totals,results=rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file',type=Path);parser.add_argument('--preview',action='store_true')
    parser.add_argument('--live',action='store_true');parser.add_argument('--allow-paid-requests',action='store_true')
    args=parser.parse_args()
    if args.file.stat().st_size>2000000:parser.error('Dataset is too large (maximum 2 MB).')
    cases=json.loads(args.file.read_text())
    if args.preview:
        if not isinstance(cases,list) or len(cases)>1000:parser.error('Use at most 1000 examples.')
        for case in cases:print(json.dumps(jev.prepare_decision(case['applications'],case['tasks'],examples=case.get('examples',[]),clues=case.get('clues',[]),focus=case.get('focus'),focus_default=case.get('focus_default',False),application_categories=case.get('application_categories',False),model=case.get('model','jev-latest')),ensure_ascii=False))
        return 0
    if args.live and not args.allow_paid_requests:parser.error('Live evaluation sends the dataset to TypeSafe and may incur charges; add --allow-paid-requests after inspecting --preview.')
    key=jev.get_key() if args.live else None
    try:print(json.dumps(evaluate(cases,live=args.live,key=key),indent=2))
    finally:key=None
    return 0


if __name__=='__main__':raise SystemExit(main())

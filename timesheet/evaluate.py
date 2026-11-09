"""Replay labelled decision evidence; live inference is separately, explicitly opt-in."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .decision_contract import valid_result
from .decision_policy import route,ROUTING_VERSION
from . import jev
from .decision_context import digest,plain


def validate_cases(cases,*,require_labels=True):
    if not isinstance(cases,list) or not 1<=len(cases)<=1000:raise ValueError('Use 1–1000 labelled examples.')
    case_ids=set()
    for index,case in enumerate(cases):
        if not isinstance(case,dict) or not {'applications','tasks','expected_task','seconds','has_context'}<=case.keys():raise ValueError('Each example needs apps, tasks, expected task, seconds and context flag.')
        if type(case['seconds']) is not int or not 0<case['seconds']<=172800 or type(case['has_context']) is not bool:raise ValueError('Example duration or context is invalid.')
        label_status=case.get('label_status','confirmed')
        if label_status not in ('confirmed','unlabelled') or require_labels and label_status!='confirmed':raise ValueError('Confirm every independent label before evaluation or paid requests.')
        case_id=case.get('case_id',str(index+1))
        if not plain(case_id,80) or not case_id or case_id in case_ids:raise ValueError('Use unique plain case IDs of at most 80 characters.')
        case_ids.add(case_id)
        if not plain(case.get('slice','all'),80):raise ValueError('Use a plain evaluation slice of at most 80 characters.')
        jev.prepare_decision(case['applications'],case['tasks'],examples=case.get('examples',[]),clues=case.get('clues',[]),focus=case.get('focus'),focus_default=case.get('focus_default',False),application_categories=case.get('application_categories',False),model=case.get('model','jev-latest'))
        if case['expected_task'] is not None and (type(case['expected_task']) is not int or case['expected_task'] not in [i for i,_ in case['tasks']]):raise ValueError('The expected task must be an offered option or null.')


def evaluate(cases,*,live=False,request=None,key=None):
    if not isinstance(cases,list) or not 1<=len(cases)<=1000:raise ValueError('Use 1–1000 labelled examples.')
    if live and len(cases)>50:raise ValueError('A live run is limited to 50 requests.')
    totals=dict(cases=len(cases),automated=0,correct_automated=0,wrong_minutes=0,recorded_minutes=0,exception_cases=0,automated_minutes=0,correct_choices=0,input_tokens=0)
    rows=[]
    validate_cases(cases)
    dataset=[]
    for index,case in enumerate(cases):
        tasks=case['tasks']
        payload=jev.prepare_decision(case['applications'],tasks,examples=case.get('examples',[]),clues=case.get('clues',[]),focus=case.get('focus'),focus_default=case.get('focus_default',False),application_categories=case.get('application_categories',False),model=case.get('model','jev-latest'))
        dataset.append(dict(case_id=case.get('case_id',str(index+1)),seconds=case['seconds'],expected_task=case['expected_task'],has_context=case['has_context'],slice=case.get('slice','all'),payload={k:v for k,v in payload.items() if k!='model'}))
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
        rows.append(dict(case_id=case.get('case_id',str(index+1)),slice=case.get('slice','all'),seconds=case['seconds'],action=action,correct=correct,reason=reason,model=result['model']))
    totals['automation_coverage']=totals['automated']/len(cases)
    totals['time_coverage']=totals['automated_minutes']/totals['recorded_minutes']
    totals['choice_accuracy']=totals['correct_choices']/len(cases)
    totals['automated_precision']=totals['correct_automated']/totals['automated'] if totals['automated'] else None
    return dict(schema_version=1,request_version=jev.REQUEST_VERSION,routing_version=ROUTING_VERSION,dataset_fingerprint=digest(dataset),models=sorted({r['model'] for r in rows}),
        limitations=['Labelled samples are not representative daily accuracy unless the sampling process establishes that.', 'Exception-only reviews cannot estimate automatic precision.'],slices={name: slice_metrics([r for r in rows if r['slice']==name]) for name in sorted({r['slice'] for r in rows})},evidence='live labelled evaluation' if live else 'offline replay: does not measure live Jev accuracy',metrics=totals,results=rows)


def slice_metrics(rows):
    automated=[r for r in rows if r['action']=='apply']
    return dict(cases=len(rows),seconds=sum(r['seconds'] for r in rows),automated=len(automated),
        wrong_seconds=sum(r['seconds'] for r in automated if not r['correct']),
        automated_precision=sum(r['correct'] for r in automated)/len(automated) if automated else None)


def compare(reference,candidate):
    """Offline response comparison under the current routing policy; no promotion."""
    before=evaluate(reference);after=evaluate(candidate)
    if before['dataset_fingerprint']!=after['dataset_fingerprint']:
        raise ValueError('Compare identical labelled inputs, case order, scopes and durations.')
    regressions=[b['case_id'] for a,b in zip(before['results'],after['results'])
        if b['action']=='apply' and not b['correct'] and (a['action']!='apply' or a['correct'])]
    return dict(evidence='offline comparison; human review required before model promotion',
        dataset_fingerprint=before['dataset_fingerprint'],reference=before['metrics'],candidate=after['metrics'],
        newly_wrong_automated_cases=regressions,coverage_change=after['metrics']['time_coverage']-before['metrics']['time_coverage'],
        wrong_minutes_change=after['metrics']['wrong_minutes']-before['metrics']['wrong_minutes'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file',type=Path);parser.add_argument('--preview',action='store_true')
    parser.add_argument('--compare',type=Path,help='Offline candidate responses for the identical labelled inputs');parser.add_argument('--live',action='store_true');parser.add_argument('--allow-paid-requests',action='store_true')
    args=parser.parse_args()
    if args.file.stat().st_size>2000000:parser.error('Dataset is too large (maximum 2 MB).')
    cases=json.loads(args.file.read_text())
    if args.compare:
        if args.live or args.preview:parser.error('--compare is offline and cannot be combined with --live or --preview.')
        if args.compare.stat().st_size>2000000:parser.error('Candidate dataset is too large (maximum 2 MB).')
        print(json.dumps(compare(cases,json.loads(args.compare.read_text())),indent=2));return 0
    if args.preview:
        validate_cases(cases,require_labels=False)
        for case in cases:print(json.dumps(jev.prepare_decision(case['applications'],case['tasks'],examples=case.get('examples',[]),clues=case.get('clues',[]),focus=case.get('focus'),focus_default=case.get('focus_default',False),application_categories=case.get('application_categories',False),model=case.get('model','jev-latest')),ensure_ascii=False))
        return 0
    if args.live and not args.allow_paid_requests:parser.error('Live evaluation sends the dataset to TypeSafe and may incur charges; add --allow-paid-requests after inspecting --preview.')
    validate_cases(cases)
    if args.live and len(cases)>50:parser.error('A live run is limited to 50 requests.')
    key=jev.get_key() if args.live else None
    try:print(json.dumps(evaluate(cases,live=args.live,key=key),indent=2))
    finally:key=None
    return 0


if __name__=='__main__':raise SystemExit(main())

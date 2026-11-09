"""Pure, conservative draft-routing policy. Scores are heuristics, never measured accuracy."""
from __future__ import annotations
import json
import math
import os
import hashlib
from pathlib import Path
from . import __version__

POLICY_VERSION=1
ROUTING_VERSION=1
DEFAULTS=dict(mode='off',consent_version=0,since=0,daily_requests=50,daily_tokens=250000,
              allow_guidance=True,allow_examples=False,allow_project_clues=False,allow_focus=True,exclude_apps=[],backend='native',owner='',category_tasks=[])


def owner_token():
    identity=('flatpak:'+os.environ['FLATPAK_ID']) if os.environ.get('FLATPAK_ID') else str(Path(os.environ.get('APPIMAGE',Path(__file__).resolve().parent.parent)).resolve())
    return hashlib.sha256((identity+'|'+__version__).encode()).hexdigest()


def settings(raw):
    fallback=lambda:{**DEFAULTS,'exclude_apps':[],'category_tasks':[]}
    if not isinstance(raw,str) or len(raw)>64000:return fallback()
    try:value=json.loads(raw or '{}')
    except (ValueError,TypeError,RecursionError):return fallback()
    if not isinstance(value,dict):return fallback()
    result={**fallback(),**{k:v for k,v in value.items() if k in DEFAULTS}}
    valid=(result['mode'] in ('off','suggest','automatic') and result['backend'] in ('native','flatpak') and type(result['consent_version']) is int
           and type(result['since']) is int and 0<=result['since']<=2**40
           and type(result['daily_requests']) is int and 1<=result['daily_requests']<=1000
           and type(result['daily_tokens']) is int and 1000<=result['daily_tokens']<=10000000
           and all(type(result[k]) is bool for k in ('allow_guidance','allow_examples','allow_project_clues','allow_focus'))
           and isinstance(result['exclude_apps'],list) and len(result['exclude_apps'])<=200
           and isinstance(result['category_tasks'],list) and len(result['category_tasks'])<=8 and len(set(str(i) for i in result['category_tasks']))==len(result['category_tasks'])
           and all(type(i) is int and i>0 for i in result['category_tasks'])
           and isinstance(result['owner'],str) and (result['owner']=='' or len(result['owner'])==64 and all(c in '0123456789abcdef' for c in result['owner']))
           and all(isinstance(s,str) and 0<len(s)<=200 and not any(ord(c)<32 for c in s) for s in result['exclude_apps']))
    if not valid:return fallback()
    if result['consent_version']!=POLICY_VERSION:result['mode']='off'
    if result['mode']!='off' and not result['owner']:result['mode']='off'
    return result


def probability(value):
    return type(value) in (int,float) and math.isfinite(value) and 0<=value<=1


def route(result,mode,*,has_context=False,focus_task=None,focus_default=False,application_categories=False):
    """Return action/reason. Only supported, unambiguous decisions can make drafts."""
    if not isinstance(result,dict) or not probability(result.get('probability')):
        return 'exception','The decision could not be validated.'
    if result.get('task') is None:return 'exception','Jev could not identify a task.'
    alternatives=result.get('alternatives',[])
    if (not isinstance(alternatives,(list,tuple)) or not alternatives or alternatives[0][0]!=result['task']
            or any(not isinstance(x,(list,tuple)) or len(x)!=2 or not probability(x[1]) for x in alternatives)):
        return 'exception','The task alternatives could not be validated.'
    runner=max([float(result.get('none_probability',1))]+[p for t,p in alternatives if t!=result['task']])
    if focus_default and result['task']!=focus_task:return 'exception','Jev disagrees with your draft-default focus. Choose the task.'
    if application_categories:
        # Limited to owned generic categories with zero billing effect. This is
        # app-function labelling, never a decision that the period was productive.
        if not has_context or not probability(result.get('enough_evidence')) or result['enough_evidence']<.85 or result['probability']<.9 or result['probability']-runner<.4:
            return 'exception','This app could fit several activity types. Choose a category.'
        if mode!='automatic':return 'exception','Activity-type suggestion ready for review.'
        return 'apply','Supported broad app-activity type. This estimates app function, not productivity or work intent. Non-billable draft.'

    # A user-authorised, time-bounded draft default is a distinct action from
    # inferring a task without instructions. Jev must agree and not signal a
    # competing task/personal interpretation. This is not a calibration claim.
    if (focus_default and type(focus_task) is int and focus_task==result['task'] and has_context
            and result['probability']>=.8 and result['probability']-runner>=.4
            and probability(result.get('personal')) and result['personal']<=.5):
        return ('apply','User-authorised focus default; Jev agreed. Reversible draft only.') if mode=='automatic' else ('exception','Focus-matching suggestion ready for review.')
    if not probability(result.get('personal')) or result['personal']>.2:
        return 'exception','This might be personal or the work/personal signal is uncertain.'
    if not probability(result.get('enough_evidence')) or result['enough_evidence']<.95 or not has_context:
        return 'exception','More context is needed to distinguish the task.'
    if result['probability']<.97 or result['probability']-runner<.3:
        return 'exception','The task choice is not clear enough for an automatic draft.'
    if mode!='automatic':return 'exception','Suggestion ready for your review.'
    return 'apply','Strong task match with supporting permitted context. Automatic draft; review before approval.'


def ambiguous(result):
    """The same conservative ambiguity presentation for single/batch suggestions."""
    if not isinstance(result,dict):return True
    alternatives=result.get('alternatives') or []
    if result.get('task') is None or (result.get('personal') is not None and result['personal']>=.8):return True
    runner=max([result.get('none_probability',0) or 0]+[p for t,p in alternatives if t!=result['task']])
    return not probability(result.get('probability')) or result['probability']-runner<.15

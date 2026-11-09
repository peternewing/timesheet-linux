"""Shared validation of provider and cached decisions; no worker lifecycle."""
from . import jev


def valid_result(value,tasks,model):
    from .decision_policy import probability
    import math,re
    if not isinstance(value,dict):return False
    ids={i for i,_ in tasks}
    task=value.get('task');alts=value.get('alternatives')
    if task is not None and (type(task) is not int or task not in ids):return False
    if not isinstance(alts,(list,tuple)) or len(alts)!=len(ids):return False
    if any(not isinstance(x,(list,tuple)) or len(x)!=2 or type(x[0]) is not int or x[0] not in ids or not probability(x[1]) for x in alts):return False
    if len({x[0] for x in alts})!=len(ids):return False
    if not all(probability(value.get(k)) for k in ('probability','none_probability','personal','enough_evidence')):return False
    if not math.isclose(sum(x[1] for x in alts)+value['none_probability'],1,abs_tol=.02):return False
    dist=dict(alts);dist[None]=value['none_probability']
    if value['probability']!=dist[task] or dist[task]+.000001<max(dist.values()):return False
    if list(alts)!=sorted(alts,key=lambda x:(-x[1],x[0])):return False
    actual=value.get('model')
    if not isinstance(actual,str) or actual=='jev-latest' or not re.fullmatch(r'jev-[A-Za-z0-9._-]{1,120}',actual):return False
    if model!='jev-latest' and actual!=model:return False
    usage=value.get('usage')
    return (isinstance(usage,dict) and all(type(usage.get(k)) is int and 0<=usage[k]<=1000000 for k in ('input_tokens','output_tokens'))
            and value.get('work_kind') in jev.WORK_KINDS)

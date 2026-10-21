"""Deterministic resource aliases keep ActPlane's 64-byte rule ABI exact."""
from pathlib import PurePosixPath

def resource_records(resources, views=None):
    from .resource_views import records
    return records(resources, views)

def translate(value,resources,reverse=False,views=None):
    if views:
        from .resource_views import translate as mapped
        return mapped(value, resources, views, reverse=reverse)
    p=PurePosixPath(value)
    if not p.is_absolute() or '..' in p.parts or str(p)!=value:
        raise ValueError('资源路径必须是规范绝对路径')
    for row in resource_records(resources):
        source,target=(row['execution'],row['source']) if reverse else (row['source'],row['execution'])
        base=PurePosixPath(source)
        if p==base or base in p.parents: return str(PurePosixPath(target)/p.relative_to(base))
    return value

def agent_policy(policy,resources):
    return {**policy,'rules':[{**r,'target':translate(r['target'],resources,views=policy.get('resource_views')) if r['action'] in ('read','write') else r['target']} for r in policy['rules']]}

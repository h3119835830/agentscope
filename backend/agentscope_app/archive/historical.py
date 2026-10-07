"""Historical task topology over persisted receipts and verified policy artifacts."""
import re
from fastapi import HTTPException
from .. import db
from ..managed import topology
from .projection import require_task, safe


def context(con,task_id,version):
    task=require_task(con,task_id)
    rows=con.execute("SELECT id,payload_json,occurred_at FROM managed_events WHERE task_id=? AND kind='policy_active' ORDER BY id DESC",(task_id,)).fetchall()
    versions={}
    from .projection import decode
    for row in rows:
        payload=decode(row['payload_json']);number=payload.get('version')
        if type(number) is int and number>0 and number not in versions:
            binding=payload.get('binding',{})
            versions[number]={'version':number,'domain_id':binding.get('domain_id'),'recorded_at':row['occurred_at'],'evidence_ref':'managed_events:'+str(row['id'])+':record'}
    if version is not None and version not in versions:raise HTTPException(404,'该历史域版本不属于此任务')
    selected=version if version is not None else max(versions,default=None)
    loaded=topology.receipt(con,task_id,selected) if selected is not None else None
    return task,selected,loaded,sorted(versions.values(),key=lambda v:v['version'],reverse=True)


def historical_source(node,loaded):
    node=dict(node)
    # Legacy watch files without a recorded expected hash are not verified DSL.
    if node.get('role')=='baseline' and not (loaded.get('binding',{}).get('baseline_binding') or {}).get('bundle_hash'):
        node.pop('dsl',None);node.pop('policy_hash',None)
        node.update(available=False,source='missing_or_unverified_artifact',labels=[],missing_reason='missing_expected_bundle_hash')
    if node.get('available') is not True:node.setdefault('missing_reason','missing_or_unverified_artifact')
    return {**node,'live':False,'historical':True,'history_only':True}


def sources(task,version,loaded):
    if not loaded:return []
    try:return [historical_source(n,loaded) for n in topology.domain_sources(task,version,loaded)]
    except (ValueError,KeyError,TypeError):return []


def graph(task_id,version=None):
    with db.connect() as con:
        con.execute('BEGIN')
        task,selected,loaded,versions=context(con,task_id,version)
    chosen=next((v for v in versions if v['version']==selected),{})
    nodes=sources(task,selected,loaded)
    for node in nodes:node.pop('dsl',None)
    edges=[]
    baseline=next((n for n in nodes if n['role']=='baseline'),None)
    domain=next((n for n in nodes if n['role']=='task'),None)
    if baseline and domain:edges.append({'from':baseline['key'],'to':domain['key'],'kind':'inherits','label':'历史底线继承'})
    for role,field in (('runner','runner_pid'),('watch','watch_pid'),('executor','executor_pid')):
        pid=(loaded or {}).get('binding',{}).get(field)
        if type(pid) is not int or pid<=0:continue
        key=f'v{selected}:{role}:{pid}'
        nodes.append({'key':key,'kind':'process','role':role,'pid':pid,'version':selected,'title':f'历史 {role} PID {pid}','recorded_at':chosen.get('recorded_at'),'source':'managed_events.policy_active.binding.'+field,'evidence_ref':chosen.get('evidence_ref'),'live':False,'historical':True,'history_only':True})
        if domain:edges.append({'from':domain['key'],'to':key,'kind':'load_observation' if role=='watch' else 'recorded_binding','label':'历史加载监控关联；非任务域成员' if role=='watch' else '历史收据关联；不推断当前域成员'})
    missing=[{'key':n['key'],'role':n['role'],'reason':n.get('missing_reason','missing_or_unverified_artifact')} for n in nodes if n.get('kind')=='domain' and n.get('available') is not True]
    for role in ('task','baseline'):
        if loaded and not any(n.get('kind')=='domain' and n.get('role')==role for n in nodes):missing.append({'key':f'v{selected}:{role}','role':role,'reason':'trusted_'+role+'_material_not_recorded'})
    available=any(n.get('kind')=='domain' and n.get('available') is True for n in nodes)
    return safe({'task_id':task_id,'version':selected,'versions':versions,'nodes':nodes,'edges':edges,'available':available,'status':'recorded' if loaded else 'not_recorded','missing_sources':missing,'live':False,'historical':True,'history_only':True,'checked_at':None,'recorded_at':chosen.get('recorded_at'),'coverage':'historical_load_receipts_and_verified_policy_artifacts','notice':None if available and baseline and not missing else '未取得完整可信历史材料；不补画全局D0，不核验历史PID当前存活。'})


def domain_detail(task_id,key):
    match=re.fullmatch(r'v([1-9][0-9]*):(task|baseline)',key)
    if not match:raise HTTPException(404,'无效或不属于此任务的历史域')
    version=int(match[1])
    with db.connect() as con:
        con.execute('BEGIN')
        task,selected,loaded,versions=context(con,task_id,version)
        managed=con.execute('SELECT 1 FROM managed_tasks WHERE task_id=?',(task_id,)).fetchone()
    try:
        if managed:
            node=historical_source(topology.domain_detail(task_id,key),loaded)
        else:
            node=next((n for n in sources(task,version,loaded) if n['key']==key),None)
    except (ValueError,KeyError,TypeError):node=None
    if not node:
        node={'key':key,'kind':'domain','role':match[2],'version':version,'domain_id':None,'available':False,'source':'not_recorded','missing_reason':'trusted_'+match[2]+'_material_not_recorded','labels':[]}
    chosen=next(v for v in versions if v['version']==version)
    return safe({**node,'task_id':task_id,'recorded_at':chosen['recorded_at'],'evidence_ref':chosen['evidence_ref'],'live':False,'historical':True,'history_only':True,'loading_verification_passed':loaded.get('verification',{}).get('passed') is True,'label_semantics':'DSL source declarations; not a live kernel taint inventory'})

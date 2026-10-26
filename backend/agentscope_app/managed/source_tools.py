"""Runtime source tools: preflight-style evidence reads and immutable submissions.

This opt-in trial changes target resolution, not the execution capability set.
The generator selects registered objects from read evidence; the controller owns
scope, source identity, stale checks, compilation and restriction-only loading.
"""
import json
from pathlib import PurePosixPath
from pydantic import BaseModel,ConfigDict,Field
from typing import Literal
from .. import db
from ..bootstrap.library import search
from . import controller as c

PROTOCOL='runtime-source-tools/1'
TOOLS=['get_task_context','list_policy_sources','read_policy_source','search_historical_policies',
       'get_enforcement_capabilities','validate_policy_draft','submit_runtime_policy_proposal']

class Atom(BaseModel):
    model_config=ConfigDict(extra='forbid')
    statement:str=Field(min_length=3,max_length=2000)
    paths:list[str]=Field(min_length=1,max_length=30,description='Exact registered project paths, workspace-relative or their canonical absolute execution mapping. No adjacent objects or invented paths.')
    operations:list[Literal['write','unlink']]=Field(min_length=1,max_length=2)
    evidence_ids:list[str]=Field(min_length=1,max_length=30)

class Draft(BaseModel):
    model_config=ConfigDict(extra='forbid')
    context_hash:str
    summary:str=Field(min_length=3,max_length=2000)
    atoms:list[Atom]=Field(default_factory=list,max_length=20)
    guidance:list[str]=Field(default_factory=list,max_length=20)
    unresolved_requests:list[str]=Field(default_factory=list,max_length=30,description='Only pending_user_request_ids for necessary OS constraints with ambiguous targets or unsupported enforcement. Task feasibility or conflicting work instructions belong in guidance. An unresolved result cannot contain executable atoms.')

def enabled(ctx):
    return ctx.get('capabilities',{}).get('target_admission')==PROTOCOL

def sources(ctx):
    result={}
    for entry in ctx['sources']:
        content=entry['content']
        memory=entry['source']=='persistent_memory'
        value=content.get('content','') if memory else content.get('text','')
        result[entry['evidence_id']]={'id':entry['evidence_id'],'role':'memory' if memory else 'request',
          'text':value,'content_hash':c.digest(value),
          'authority':content.get('authority','authenticated_request' if content.get('actor') in ('native_user','administrator') else 'untrusted'),
          'actor':content.get('actor'),'session_id':content.get('session_id')}
    for entry in ctx.get('project_sources',[]):
        name=PurePosixPath(entry['id']).name.lower()
        if name.startswith('.env') or any(part in name for part in ('secret','credential','token')) or PurePosixPath(name).suffix in ('.pem','.key','.p12','.pfx'):
            continue
        result['project:'+entry['id']]={'id':'project:'+entry['id'],'role':'asset','path':entry['id'],
          'text':entry['content'],'content_hash':entry['hash'],'authority':'untrusted_project_context'}
    return result

def receipt(con,job,kind,value):
    c.event(con,job['task_id'],kind,job['id'],value)

def read_receipts(con,job):
    prefix=job['id']+':'
    return {json.loads(r[0])['id']:json.loads(r[0])['content_hash'] for r in con.execute(
      "SELECT payload_json FROM managed_events WHERE task_id=? AND kind='runtime_source_read' AND substr(event_key,1,?)=?",
      (job['task_id'],len(prefix),prefix))}

def candidate_identity(value):
    # Compiler diagnostics contain a newly allocated temporary policy_ref.
    # Identity instead binds the exact compiled DSL/YAML/Delta hashes, complete
    # source draft and frozen context, all of which are revalidated on submit.
    return {k:v for k,v in value.items() if k not in ('compile','hash')}

def validate(job,draft):
    draft=Draft.model_validate(draft);ctx=json.loads(job['context_json']);catalog=sources(ctx)
    if draft.context_hash!=c.digest(ctx):raise ValueError('stale: 运行时上下文版本不匹配')
    with db.connect() as con:
        reads=read_receipts(con,job)
        for kind in ('pi_read','pi_history','runtime_capabilities_read'):
            if not con.execute('SELECT 1 FROM managed_events WHERE task_id=? AND kind=? AND event_key=?',(job['task_id'],kind,job['id'])).fetchone():
                raise ValueError('先读取上下文、查询执行能力并检索历史策略')
    user_ids={key for key,source in catalog.items() if source.get('actor') in ('native_user','administrator')}
    all_evidence=set(ctx.get('unassessed_request_ids',[]))|{ctx['request_evidence_id']}
    if draft.unresolved_requests and draft.atoms:raise ValueError('未解决的必要 OS 约束不能与执行增量同时提交；请保留现行策略')
    statements=[];targets=[]
    for atom in draft.atoms:
        evidence=set(atom.evidence_ids)
        if not evidence&user_ids:raise ValueError('每项执行限制必须引用本轮已认证用户请求，记忆不能单独授权')
        for sid in evidence:
            if sid not in catalog or reads.get(sid)!=catalog[sid]['content_hash']:raise ValueError('候选引用未读取或跨任务来源: '+sid)
        normalized=[]
        for target in atom.paths:
            if PurePosixPath(target).is_absolute():
                try:target=str(PurePosixPath(target).relative_to(ctx['path_mapping']['workspace']))
                except ValueError:raise ValueError('保护对象超出当前工作区')
            normalized.append(target)
            registered=ctx['capabilities']['registered_files']
            if target.endswith('/**'):
                if target[:-3] not in ctx['capabilities']['registered_directories'] or target=='./**':raise ValueError('未登记的目录保护对象')
                relevant=['project:'+p for p in registered if p.startswith(target[:-2])]
            else:relevant=['project:'+target] if target in registered else []
            if not relevant or not any(sid in evidence and sid in reads for sid in relevant):raise ValueError('保护对象缺少实际读取的登记项目证据: '+target)
            targets.append(target)
        atom.paths=normalized
        # The current native append path emits both operations; do not claim a
        # delete-only requirement was implemented without also blocking writes.
        if set(atom.operations)!={'write','unlink'}:raise ValueError('当前增量能力将写入与删除共同保护；不能冒充单操作精确限制')
        all_evidence.update(evidence)
        statements.append({'statement':atom.statement,'context_required':True,'context_reason':'来自本轮用户要求与实际读取的记忆/项目证据',
          'policy_type':'per_event','evidence_ids':atom.evidence_ids})
    for sid in all_evidence:
        if sid not in catalog or reads.get(sid)!=catalog[sid]['content_hash']:raise ValueError('尚未读取待评估来源: '+sid)
    args={'decision':'restrict' if targets else 'guidance_only' if draft.guidance else 'no_change',
      'add_protected_paths':sorted(set(targets)),'evidence_ids':sorted(all_evidence),'explanation':draft.summary,
      'unresolved_requests':draft.unresolved_requests,'identified_statements':statements}
    result=c.validate_candidate(job,args)
    result['source_draft']=draft.model_dump()
    result['hash']=c.digest({'context':ctx,'validated':candidate_identity(result)})
    return result

def saved_candidate(job,proposal):
    """Only a controller-saved validated result can reach the native loader."""
    with db.connect() as con:
        row=con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='runtime_validated_draft' AND event_key=?",
          (job['task_id'],job['id']+':'+proposal.get('hash',''))).fetchone()
    if not row or json.loads(row[0])!=proposal:raise ValueError('运行时候选与服务端不可变校验记录不一致')

def execute(job,tool,args):
    ctx=json.loads(job['context_json']);catalog=sources(ctx)
    expected={'get_task_context':set(),'list_policy_sources':set(),'read_policy_source':{'source_id'},
      'search_historical_policies':{'query'},'get_enforcement_capabilities':set(),
      'validate_policy_draft':{'draft'},'submit_runtime_policy_proposal':{'proposal_hash'}}
    if tool not in expected or set(args)!=expected[tool]:raise ValueError('运行时工具或参数不符合合同')
    with db.connect() as con:
        if tool=='get_task_context':
            receipt(con,job,'pi_read',{'context_hash':c.digest(ctx)})
            for source in catalog.values():
                if source['role']=='request':
                    # These exact request texts and the triggering change text
                    # are already returned below; do not require duplicate reads.
                    c.event(con,job['task_id'],'runtime_source_read',job['id']+':'+source['id'],{'id':source['id'],'content_hash':source['content_hash']})
            value=c.runtime_projection(ctx)
            value.pop('sources',None);value.pop('persistent_memory',None)
            value['context_hash']=c.digest(ctx)
            value['pending_user_request_ids']=[item['evidence_id'] for item in ctx.get('public_task_context',[]) if item.get('actor') in ('native_user','administrator')]
            value['capabilities']={k:v for k,v in value['capabilities'].items() if k not in ('authorized_protection_targets','automatic_protection_subtrees')}
            return value
        if tool=='list_policy_sources':
            return {'sources':[{k:v for k,v in source.items() if k!='text'} for source in catalog.values()]}
        if tool=='read_policy_source':
            source=catalog.get(args['source_id'])
            if not source:raise ValueError('来源未登记或不可用于策略读取')
            c.event(con,job['task_id'],'runtime_source_read',job['id']+':'+source['id'],{'id':source['id'],'content_hash':source['content_hash']})
            if source['role']=='asset':
                c.event(con,job['task_id'],'pi_source',job['id']+':'+source['path'],{'id':source['path'],'hash':source['content_hash']})
            return source
        if tool=='get_enforcement_capabilities':
            receipt(con,job,'runtime_capabilities_read',{'protocol':PROTOCOL})
            return {'protocol':PROTOCOL,'operations':['write','unlink'],'effect':'block','target_kind':'file',
              'atomic_operation_sets':[['write','unlink']],'append_only':True,'existing_rules_immutable':True,
              'unsupported':['read restrictions','program execution restrictions','network restrictions','policy relaxation'],
              'draft_schema':Draft.model_json_schema()}
        if tool=='search_historical_policies':
            query=args['query']
            if not isinstance(query,str) or not 1<=len(query)<=2000:raise ValueError('检索词应为 1 至 2000 个字符')
            con.commit();result=search(query)
            receipt(con,job,'pi_history',{'query':query,'approved_only':True,'versions':[{'id':m['id'],'hash':m['hash']} for m in result.get('matches',[])]})
            return result
        if tool=='validate_policy_draft':
            count=con.execute("SELECT count(*) FROM managed_events WHERE task_id=? AND kind='runtime_draft_attempt' AND substr(event_key,1,?)=?",
              (job['task_id'],len(job['id'])+1,job['id']+':')).fetchone()[0]
            if count>=3:raise ValueError('候选初次校验及两次修正预算已耗尽')
            c.event(con,job['task_id'],'runtime_draft_attempt',job['id']+':'+str(count),{'attempt':count+1});con.commit()
            result=validate(job,args['draft'])
            c.event(con,job['task_id'],'runtime_validated_draft',job['id']+':'+result['hash'],result)
            return {'valid':True,'proposal_hash':result['hash'],'decision':result['decision'],'targets':result['add_protected_paths']}
        row=con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='runtime_validated_draft' AND event_key=?",
          (job['task_id'],job['id']+':'+str(args['proposal_hash']))).fetchone()
        if not row:raise ValueError('只能提交本作业成功校验的候选哈希')
        result=json.loads(row[0]);con.commit()
        # Revalidate source hashes, policy revision and binding before sealing.
        refreshed=validate(job,result['source_draft'])
        if candidate_identity(refreshed)!=candidate_identity(result):raise ValueError('stale: 校验后候选或证据已经变化')
        changed=con.execute("UPDATE managed_jobs SET proposal_json=? WHERE id=? AND status='running' AND proposal_json IS NULL",
          (json.dumps(result),job['id'])).rowcount
        if not changed:raise ValueError('候选不可覆盖或作业已经停止')
        return {'validated':True,'proposal_hash':result['hash'],'submitted':True,'applied':False}

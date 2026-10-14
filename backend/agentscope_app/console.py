"""Product-only read projections. Retention is presentation, never authorization.

Full control/diagnostic APIs and source records remain available for a future
operations client. Visibility is explicit per record, never inferred from names.
"""
import json
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel,ConfigDict,Field
from typing import Literal
from . import db

def invoke(fn,*args,**kwargs):
    try:return fn(*args,**kwargs)
    except (ValueError,RuntimeError) as e:raise HTTPException(409,str(e)) from None
    except (OSError,TimeoutError):raise HTTPException(503,'Agent 数据暂时不可达') from None

SCHEMA = '''CREATE TABLE IF NOT EXISTS console_retained_records(
 kind TEXT NOT NULL, record_id TEXT NOT NULL, reason TEXT NOT NULL,
 retained_at TEXT NOT NULL, PRIMARY KEY(kind,record_id));'''
router = APIRouter(prefix='/api/console', tags=['product-console'])

def hidden(kind):
    with db.connect() as con:
        return {r[0] for r in con.execute('SELECT record_id FROM console_retained_records WHERE kind=?',(kind,))}

def visible(kind, ident):
    return ident not in hidden(kind)

def require_visible(kind, ident):
    if not visible(kind,ident):
        raise HTTPException(404,'此记录保留于后台资料中')

def retain(records, reason):
    """Explicit, reversible administrative migration; does not change runtime."""
    with db.connect() as con:
        for kind,ident in records:
            if kind not in ('agent','task','strategy','generation'):raise ValueError('Unknown record kind')
            con.execute('INSERT OR IGNORE INTO console_retained_records VALUES(?,?,?,?)',(kind,ident,reason,db.now()))
        db.audit(con,None,'console_records_retained','maintenance',{'counts':{k:sum(kind==k for kind,_ in records) for k in {kind for kind,_ in records}},'reason':reason})

def agents():
    from .instances import controller
    from .instances.sessions import native_workspace_info
    from .instances.policy_sources import source_status
    retained=hidden('agent')
    rows=[r for r in controller.listing()['instances'] if r['id'] not in retained]
    # Resource mounts are not automatically native workspaces (e.g. Hermes).
    # Only show workspace mappings that the adapter has already verified.
    with db.connect() as con:
        cached=[(r[0],json.loads(r[1])) for r in con.execute('SELECT instance_id,metadata_json FROM instance_session_cache')]
    for row in rows:
        infos={info['path']:info for ident,s in cached if ident==row['id'] and (info:=native_workspace_info(row,s))}
        if row.get('native_workspaces') is not None:
            from .instances.native_workspaces import project
            infos={w['path']:project(row,w) for w in row['native_workspaces']}
        row['workspace_records']=[infos[path] for path in sorted(infos)]
        row['workspaces']=sorted(infos)
        row['policy_source']=source_status(row)
    return rows

@router.get('/agents')
def agent_directory():return {'instances':agents()}

@router.get('/agents/{ident}')
def agent_detail(ident:str):
    from .instances.controller import detail
    require_visible('agent',ident)
    return invoke(detail,ident)

@router.get('/agents/{ident}/dsl')
def agent_dsl(ident:str):
    require_visible('agent',ident)
    return dsl_configuration(ident)

@router.get('/security/system/dsl')
def system_dsl():return dsl_configuration('system')

def dsl_configuration(scope):
    from .instances.dsl_policy import detail
    data=invoke(detail,scope)
    retained=hidden('agent')
    data['targets']=[t for t in data.get('targets',[]) if t['id'] not in retained]
    from .instances import controller
    from .instances.policy_sources import source_context
    data['source_context']=source_context(scope,[r for r in controller.listing()['instances'] if r['id'] not in retained])
    data['records']=[r for r in data['records'] if r.get('source_kind')!='legacy_generated']
    from .instances.approval_views import project,scopes
    from .instances.approval_decisions import project as decision_project,receipts
    saved_decisions=receipts()
    names=scopes()
    for proposal in data.get('proposals',[]):
        approval=decision_project(project(proposal,names),saved_decisions)
        proposal['approval']={k:approval.get(k) for k in ('id','status','can_approve','can_apply','reason','approval_status','application_status','approval_hash')}
    for r in data['records']:
        if 'bindings' not in r:continue
        r['bindings']=[b for b in r['bindings'] if b['instance_id'] not in retained]
        total=len(data['targets']);verified=sum(bool(b['active']) for b in r['bindings'])
        r.update(coverage={'total_count':total,'loaded_count':len(r['bindings']),'verified_count':verified},
                 loaded=bool(r['bindings']),active=bool(total and verified==total))
    return data

@router.get('/agents/{ident}/events')
def agent_events(ident:str,before:int|None=Query(None,ge=1)):
    from .instances.store import events
    require_visible('agent',ident)
    return {'events':events(ident,before)}

def retained_request(request):
    if request.headers.get('x-agentscope-surface')!='product':return False
    parts=request.url.path.strip('/').split('/')
    if len(parts)<3:return False
    kind={'agent-instances':'agent','tasks':'task','strategies':'strategy'}.get(parts[1])
    if parts[:3]==['api','managed','tasks'] and len(parts)>3:return not visible('task',parts[3])
    if parts[:3]==['api','history','generations'] and len(parts)>3:return not visible('generation',parts[3])
    if parts[:3]==['api','history','records'] and len(parts)>3:return not visible('strategy',parts[3])
    return bool(kind and not visible(kind,parts[2]))

@router.get('/summary')
def summary():
    from .instances.approval_views import pending_count
    rows=agents()
    controlled=[r for r in rows if r['mode']=='controlled']
    with db.connect() as con:
        tasks=[db.row_dict(r) for r in con.execute("SELECT * FROM tasks WHERE id NOT IN (SELECT record_id FROM console_retained_records WHERE kind='task') ORDER BY updated_at DESC")]
        # Counts are facts about stored records, not permission revalidation.
        # The catalog's detailed row projection reads native contexts and must
        # never run as a side effect of a periodically polled overview.
        counts=con.execute("""SELECT COUNT(*) AS total,
            COALESCE(SUM(COALESCE(v.review_status,s.status)='pending_review'),0) AS pending
            FROM strategies s LEFT JOIN strategy_statement_versions v ON v.id=(
              SELECT id FROM strategy_statement_versions WHERE strategy_id=s.id ORDER BY version DESC LIMIT 1)
            WHERE s.is_archived=0
              AND COALESCE(json_extract(v.record_json,'$.statement.content_type'),'policy')!='description'
              AND s.id NOT IN (SELECT record_id FROM console_retained_records WHERE kind='strategy')""").fetchone()
    return {'agents':controlled,'tasks':tasks,'stats':{'agents':len(controlled),
        'verified_agents':sum(bool(r.get('active') and r.get('connected')) for r in controlled),
        'strategies':counts['total'],'pending_strategies':counts['pending'],'pending_approvals':pending_count(),'tasks':len(tasks)}}

@router.get('/sessions')
def directory(agent_type:str='',instance_id:str='',q:str=Query('',max_length=200),cursor:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=100),workspace:str=Query('',max_length=4096)):
    from .instances.sessions import directory
    if instance_id:require_visible('agent',instance_id)
    return invoke(directory,agent_type,instance_id,q,cursor,limit,workspace,console=True)

@router.get('/agents/{ident}/sessions/{sid}/{section}')
def session_read(ident:str,sid:str,section:str,before:int|None=Query(None,ge=1),limit:int=Query(30,ge=1,le=100)):
    from .instances import sessions
    require_visible('agent',ident)
    if section=='policies':
        data=invoke(sessions.policies,ident,sid)
        if 'session' in data:data['session']={**data['session'],'resource':data['session'].get('workspace')}
        if 'security' in data:
            data['security']['evidence_records']=[{**r,'hits':[h for h in r.get('hits',[]) if h.get('session_id')==sid]}
                for r in data['records'] if r.get('source_kind')=='legacy_generated']
        data['records']=[r for r in data['records'] if r.get('source_kind')!='legacy_generated']
        for record in data['records']:
            record['hits']=[h for h in record.get('hits',[]) if h.get('session_id')==sid]
        return data
    if section=='domains':
        data=invoke(sessions.domains,ident,sid)
        return {k:data[k] for k in ('active','executor_shared','nodes','edges','coverage_complete','notice')}
    if section=='kernel-events':return invoke(sessions.kernel_page,ident,sid,before=before,limit=limit,session_only=True)
    if section=='tool-traces':return invoke(sessions.traces,ident,sid,before=before,limit=limit)
    raise HTTPException(404,'没有此会话页面')

@router.get('/history/records')
def policy_directory(q:str='',status:str='',category:str='',context_scope:str='',source_repo:str='',archived:str='active',limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),source_kind:str='',execution_layer:str='',completeness:str='',adaptation:str='',loadable:str=''):
    from .history.catalog import page
    return invoke(page,q,status,category,context_scope,source_repo,archived,limit,offset,source_kind,execution_layer,completeness,adaptation,loadable,console=True)

@router.get('/history/generations/page')
def generation_directory(q:str='',status:str='',limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0)):
    from .history.product_generation import page
    return invoke(page,q,status,limit,offset)

@router.get('/history/generations/{ident}')
def generation_detail(ident:str,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0)):
    from .history.product_generation import detail
    require_visible('generation',ident)
    return invoke(detail,ident,limit,offset)

@router.get('/task-archives')
def task_directory(q:str='',status:str='all',page:int=Query(0,ge=0),limit:int=Query(12,ge=1,le=50)):
    from .archive.projection import archive_index
    if status not in ('all','active','ended'):raise HTTPException(422,'状态筛选无效')
    return archive_index(q,status,page,limit,console=True)

@router.get('/agents/{ident}/policy-context')
def agent_policy_context(ident:str,session_id:str|None=Query(None,max_length=200),scope:Literal['agent','workspace']|None=None,workspace_id:str|None=Query(None,max_length=200)):
    from .history.agent_context import snapshot,scoped_snapshot
    require_visible('agent',ident)
    if scope:
        if session_id:raise HTTPException(422,'显式范围不能由会话覆盖')
        return invoke(scoped_snapshot,ident,scope,workspace_id)
    return invoke(snapshot,ident,session_id)

@router.get('/agents/{ident}/policy-conversation')
def agent_policy_conversation(ident:str,session_id:str|None=Query(None,max_length=200)):
    from .history.agent_context import conversation
    require_visible('agent',ident)
    return invoke(conversation,ident,session_id)

@router.get('/agents/{ident}/policy-scenes')
def agent_policy_scene_latest(ident:str,session_id:str=Query(min_length=1,max_length=200)):
    from .history.agent_scene import latest
    require_visible('agent',ident)
    return invoke(latest,ident,session_id)

@router.get('/agents/{ident}/policy-scenes/{read_id}')
def agent_policy_scene_get(ident:str,read_id:str):
    from .history.agent_scene import get
    require_visible('agent',ident)
    return invoke(get,ident,read_id)

@router.get('/agents/{ident}/policy-candidates/{artifact_id}')
def agent_policy_candidate(ident:str,artifact_id:str):
    from .history.agent_context import selected_candidate
    require_visible('agent',ident)
    return invoke(selected_candidate,ident,artifact_id)

@router.get('/approvals')
def approval_directory():
    from .instances.approval_views import directory
    return invoke(directory)

@router.get('/approvals/{ident}')
def approval_detail(ident:str):
    from .instances.approval_views import detail
    return invoke(detail,ident)

class ApprovalDecision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    proposal_hash:str=Field(min_length=1,max_length=128)

class ApprovalRequest(ApprovalDecision):
    request_key:str=Field(min_length=8,max_length=100)

class ApplicationRequest(ApprovalRequest):
    approval_hash:str=Field(pattern=r'^[a-f0-9]{64}$')

class RevalidationRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    plan_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    request_key:str=Field(min_length=8,max_length=100)

@router.get('/approvals/{ident}/revalidation')
def revalidation_preview(ident:str):
    from .instances.approval_recovery import preview
    return invoke(preview,ident)

@router.post('/approvals/{ident}/revalidate')
def revalidate_policy(ident:str,body:RevalidationRequest):
    from .instances.approval_recovery import revalidate
    return invoke(revalidate,ident,body.plan_hash,body.request_key)

@router.post('/approvals/{ident}/approve')
def approve_policy(ident:str,body:ApprovalRequest):
    from .instances.approval_decisions import approve
    return invoke(approve,ident,body.proposal_hash,body.request_key)

@router.post('/approvals/{ident}/apply')
def apply_policy(ident:str,body:ApplicationRequest):
    from .instances.approval_decisions import apply
    return invoke(apply,ident,body.proposal_hash,body.approval_hash,body.request_key)

@router.post('/approvals/{ident}/{decision}')
def approval_decision(ident:str,decision:Literal['confirm','reject'],body:ApprovalDecision):
    from .instances.approval_views import decide
    return invoke(decide,ident,decision,body.proposal_hash)

@router.get('/agents/{ident}/workspaces')
def native_workspaces(ident:str):
    require_visible('agent',ident)
    from .instances.native_workspaces import directory
    return invoke(directory,ident)

@router.get('/agents/{ident}/workspaces/{workspace_id}/files')
def native_workspace_files(ident:str,workspace_id:str,path:str=Query('',max_length=2000)):
    require_visible('agent',ident)
    from .instances.native_workspaces import files
    return invoke(files,ident,workspace_id,path)

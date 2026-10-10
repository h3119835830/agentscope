"""Product-only read projections. Retention is presentation, never authorization.

Full control/diagnostic APIs and source records remain available for a future
operations client. Visibility is explicit per record, never inferred from names.
"""
import json
from fastapi import APIRouter, HTTPException, Query
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
    retained=hidden('agent')
    rows=[r for r in controller.listing()['instances'] if r['id'] not in retained]
    # Resource mounts are not automatically native workspaces (e.g. Hermes).
    # Only show workspace mappings that the adapter has already verified.
    with db.connect() as con:
        cached=[(r[0],json.loads(r[1])) for r in con.execute('SELECT instance_id,metadata_json FROM instance_session_cache')]
    for row in rows:
        infos={info['path']:info for ident,s in cached if ident==row['id'] and (info:=native_workspace_info(row,s))}
        row['workspace_records']=[infos[path] for path in sorted(infos)]
        row['workspaces']=sorted(infos)
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
    data['records']=[r for r in data['records'] if r.get('source_kind')!='legacy_generated']
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
    from .history import catalog
    rows=agents()
    controlled=[r for r in rows if r['mode']=='controlled']
    with db.connect() as con:
        tasks=[db.row_dict(r) for r in con.execute("SELECT * FROM tasks WHERE id NOT IN (SELECT record_id FROM console_retained_records WHERE kind='task') ORDER BY updated_at DESC")]
    records=catalog.page(limit=1,console=True)
    pending=catalog.page(status='pending_review',limit=1,console=True)
    return {'agents':controlled,'tasks':tasks,'stats':{'agents':len(controlled),
        'verified_agents':sum(bool(r.get('active') and r.get('connected')) for r in controlled),
        'strategies':records['total'],'pending_strategies':pending['total'],'tasks':len(tasks)}}

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
        data['records']=[r for r in data['records'] if r.get('source_kind')!='legacy_generated']
        for record in data['records']:
            record['hits']=[h for h in record.get('hits',[]) if h.get('session_id')==sid]
        return data
    if section=='domains':
        data=session_read(ident,sid,'policies')
        return {'active':data['active'],'executor_shared':data['executor_shared'],
            'nodes':[{'id':scope,'title':title,'count':sum(r.get('scope_type')==scope for r in data['records'])} for scope,title in (('system','系统策略'),('agent','Agent 策略'),('session','会话策略'))]}
    if section=='kernel-events':return invoke(sessions.kernel_page,ident,sid,before=before,limit=limit,session_only=True)
    if section=='tool-traces':return invoke(sessions.traces,ident,sid,before=before,limit=limit)
    raise HTTPException(404,'没有此会话页面')

@router.get('/history/records')
def policy_directory(q:str='',status:str='',category:str='',context_scope:str='',source_repo:str='',archived:str='active',limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),source_kind:str='',execution_layer:str='',completeness:str='',adaptation:str='',loadable:str=''):
    from .history.catalog import page
    return invoke(page,q,status,category,context_scope,source_repo,archived,limit,offset,source_kind,execution_layer,completeness,adaptation,loadable,console=True)

@router.get('/history/generations/page')
def generation_directory(q:str='',status:str='',limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0)):
    from .history.generations import page_runs
    return invoke(page_runs,q,status,limit,offset,console=True)

@router.get('/task-archives')
def task_directory(q:str='',status:str='all',page:int=Query(0,ge=0),limit:int=Query(12,ge=1,le=50)):
    from .archive.projection import archive_index
    if status not in ('all','active','ended'):raise HTTPException(422,'状态筛选无效')
    return archive_index(q,status,page,limit,console=True)

import json,time,uuid
from typing import Literal
from fastapi import APIRouter,HTTPException,Request
from pydantic import BaseModel,Field
from . import controller as c
from .. import db
from ..scope.models import ToolCall
router=APIRouter()
class Message(BaseModel):
    text:str=Field(min_length=1,max_length=8000)
    request_key:str=Field(default_factory=lambda:uuid.uuid4().hex)
    kind:str='message'
class Confirmation(BaseModel):
    expected_hash:str

def run(fn,*args,**kwargs):
    try:return fn(*args,**kwargs)
    except (ValueError,RuntimeError) as e:raise HTTPException(409,str(e))

@router.post('/api/managed/scenarios/{case}/tasks')
def create(case:str):return run(c.create,case)
@router.post('/api/managed/tasks/{task_id}/start')
def start(task_id:str):return run(c.start,task_id)
@router.post('/api/managed/tasks/{task_id}/startup/clarify')
def startup_clarify(task_id:str,body:Message):return run(c.clarify_startup,task_id,body.text,body.request_key)
@router.get('/api/managed/tasks/{task_id}')
def state(task_id:str):return run(c.get,task_id)
@router.get('/api/managed/tasks/{task_id}/policy')
def policy(task_id:str):return run(c.policy_details,task_id)
@router.get('/api/managed/tasks/{task_id}/audit')
def audit(task_id:str,category:Literal['all','kernel','agent_refusal','control_pause','allowed']='all',before:int|None=None):return run(c.audit_history,task_id,category,before)
@router.post('/api/managed/tasks/{task_id}/changes')
def changes(task_id:str,body:Message):return run(c.change,task_id,body.text,body.request_key,body.kind)
@router.post('/api/managed/tasks/{task_id}/expansion/confirm')
def confirm(task_id:str,body:Confirmation):return run(c.confirm_expansion,task_id,body.expected_hash)
@router.post('/api/managed/tasks/{task_id}/close')
def close(task_id:str):return run(c.close,task_id)
@router.post('/api/managed/tasks/{task_id}/prompt')
def prompt(task_id:str,body:Message):
    with db.connect() as con:s=c.load(con,task_id)
    if s['phase']!='running':raise HTTPException(409,'任务尚未运行')
    if s['gate']=='applying':raise HTTPException(409,'进程域正在重建，请在加载核验完成后重试本条消息')
    return run(c.broker,{'action':'native-session','task_id':task_id,'operation':'prompt','session_id':s['session_id'],'request_id':body.request_key,'text':body.text},timeout=20)
@router.get('/api/managed/tasks/{task_id}/native')
def native(task_id:str):
    with c.lock(task_id),db.connect() as con:s=c.load(con,task_id)
    if s['gate']=='applying':return {'session_id':s['session_id'],'status':'policy_transition','events':[],'turn':s['turn']}
    return run(c.broker,{'action':'native-session','task_id':task_id,'operation':'inspect','session_id':s['session_id']},timeout=10)

def authenticate(task_id,request):
    from ..main import require_agent_task
    require_agent_task(task_id,request)
    with db.connect() as con:
        if c.load(con,task_id)['phase'] not in ('running','generating'):raise HTTPException(401,'任务已结束')
@router.get('/api/plugin/tasks/{task_id}/managed/gate')
def gate(task_id:str,request:Request):authenticate(task_id,request);return run(c.gate,task_id)
@router.post('/api/plugin/tasks/{task_id}/managed/events')
def events(task_id:str,request:Request,body:ToolCall):
    authenticate(task_id,request)
    try:return run(c.ingest,task_id,body.args)
    except OSError as error:
        from .worker import worker
        worker.fail(task_id,'Project context or native audit unavailable: '+str(error))
        raise HTTPException(409,'任务已暂停：上下文或审计无法读取')
@router.post('/api/plugin/tasks/{task_id}/managed/change')
def change(task_id:str,request:Request,body:ToolCall):
    authenticate(task_id,request)
    return run(c.change,task_id,str(body.args.get('text','')),str(body.args.get('request_key',uuid.uuid4().hex)),str(body.args.get('kind','guidance')),'DSH')

@router.post('/api/generator/tasks/{task_id}/managed-jobs/{job_id}/tools/{tool}')
def generator(task_id:str,job_id:str,tool:str,request:Request,body:ToolCall):
    token=request.headers.get('authorization','').removeprefix('Bearer ')
    with db.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        row=con.execute("SELECT * FROM managed_jobs WHERE id=? AND task_id=? AND status='running' AND token_hash=? AND expires_at>?",(job_id,task_id,c.digest(token),time.time())).fetchone()
        if not row:raise HTTPException(401,'生成凭据过期或撤销')
        budget=json.loads(row['context_json']).get('capabilities',{}).get('tool_budget',20)
        if row['calls']>=budget:raise HTTPException(401,'生成工具预算耗尽')
        job=dict(row);con.execute('UPDATE managed_jobs SET calls=calls+1 WHERE id=?',(job_id,))
        if tool=='get_runtime_context':
            frozen=json.loads(job['context_json'])
            c.event(con,task_id,'pi_read',job_id,{'context_hash':c.digest(frozen)})
            return c.runtime_projection(frozen)
        if tool=='read_runtime_source':
            source=next((x for x in json.loads(job['context_json']).get('project_sources',[]) if x['id']==body.args.get('id')),None)
            if not source:raise HTTPException(409,'项目来源未登记')
            c.event(con,task_id,'pi_source',job_id+':'+source['id'],{'id':source['id'],'hash':source['hash']})
            return source
        if tool=='search_reviewed_history':
            # FTS refresh owns its own write transaction. Release credential
            # admission before retrieving, then record only a successful read.
            con.commit()
            from ..bootstrap.library import search
            result=search(json.loads(job['context_json'])['change']['text'][:500])
            c.event(con,task_id,'pi_history',job_id,{'approved_only':True,'versions':[{'id':m['id'],'hash':m['hash']} for m in result.get('matches',[])]})
            return result
        if tool!='submit_scope_proposal':raise HTTPException(400,'候选工具未登记')
        if not all(con.execute('SELECT 1 FROM managed_events WHERE task_id=? AND kind=? AND event_key=?',(task_id,k,job_id)).fetchone() for k in ('pi_read','pi_history')):raise HTTPException(409,'先读取本轮上下文并检索已审模板')
        con.commit()
    try:result=c.validate_candidate(job,body.args)
    except ValueError as error:
        frozen=json.loads(job['context_json'])
        raise HTTPException(409,{'diagnostic':str(error),'current_snapshot':frozen['base_snapshot']['payload'],'revision':frozen['revision'],'policy_hash':frozen['policy_hash'],'pending_review':bool(frozen.get('pending_expansion_review'))})
    with db.connect() as con:
        changed=con.execute("UPDATE managed_jobs SET proposal_json=? WHERE id=? AND status='running' AND proposal_json IS NULL",(json.dumps(result),job_id)).rowcount
        if not changed:raise HTTPException(409,'候选不可覆盖或作业已经停止')
    return {'proposal_hash':result['hash'],'validated':True}

@router.get('/api/managed/tasks/{task_id}/open')
def open_native(task_id:str):
    from fastapi.responses import RedirectResponse
    with db.connect() as con:s=c.load(con,task_id)
    if s['phase']!='running':raise HTTPException(409,'任务不在运行中')
    result=run(c.broker,{'action':'native-session','task_id':task_id,'operation':'open_url','session_id':s['session_id']},timeout=10)
    return RedirectResponse(result['url'],headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})

@router.post('/api/plugin/tasks/{task_id}/managed/feedback')
def feedback(task_id:str,request:Request,body:ToolCall):
    authenticate(task_id,request)
    return run(c.tool_feedback,task_id,str(body.args.get('call_id','')))

class OperationProbe(BaseModel):
    target:str
    operation:str
    expected:Literal["allow","deny"]
@router.post('/api/managed/tasks/{task_id}/verify-operation')
def verify_operation(task_id:str,body:OperationProbe):
    with db.connect() as con:s=c.load(con,task_id)
    if s['phase']!='running':raise HTTPException(409,'Task is not running')
    with c.lock(task_id):
        native_state=run(c.broker,{'action':'native-session','task_id':task_id,'operation':'inspect','session_id':s['session_id']},timeout=10)
        if native_state.get('status')=='running' or s['gate']!='open':raise HTTPException(409,'Wait for native session and policy analysis to finish before independent probes')
        result=run(c.broker,{'action':'managed-operation','task_id':task_id,'target':body.target,'operation':body.operation},timeout=35)
    row=result['probe'];blocked=bool(row.get('blocked') and result['kernel_events'])
    classification=('correct_block' if blocked else 'missed_block' if result['effect_verified'] else 'unverified_denial') if body.expected=='deny' else ('false_block' if blocked else 'correct_allow' if row['success'] and result['effect_verified'] else 'operation_failed')
    result.update(expected=body.expected,classification=classification,authority='independent_fixed_operation_probe')
    with c.lock(task_id),db.connect() as con:
        state=c.load(con,task_id);state.setdefault('probe_pids',[]).append(row['pid']);c.save(con,task_id,state)
        ident=uuid.uuid4().hex
        c.event(con,task_id,'operation_verified',ident,result)
        if classification=='false_block':c.enqueue(con,task_id,state,'An authenticated independent operation probe found an expected-allowed operation blocked by the kernel. Assess task and policy evidence; preserve the immutable baseline and require confirmation for any runtime-only expansion. '+json.dumps({'operation':body.operation,'target':body.target,'kernel_events':result['kernel_events'],'operation_evidence':ident}),'verified-false-block:'+ident,kind='guidance',actor='verified_feedback')
    return result


@router.post('/api/managed/tasks/{task_id}/verify-deferred-operation')
def verify_deferred(task_id:str,body:OperationProbe):
    with db.connect() as con:s=c.load(con,task_id);task=c.task_row(con,task_id)
    targets=s.get('protected',[])+[task['workspace']+'/'+p for p in s.get('runtime_protected',[]) if '*' not in p]
    if s['phase']!='running' or s['gate']!='open' or body.target not in targets or body.operation!='write_open' or body.expected!='deny':raise HTTPException(409,'仅允许在已核验受管域内对确认保护文件执行固定延迟写意图检查')
    receipt=run(c.broker,{'action':'native-session','task_id':task_id,'operation':'verify_delayed_open','session_id':s['session_id'],'target':body.target},timeout=20)
    with db.connect() as con:c.event(con,task_id,'native_sdk_verification',receipt['call_id'],receipt)
    return receipt

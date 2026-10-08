from typing import Literal
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, ConfigDict, Field
from . import controller as c, store, discovery
from .adapters import adapter
from .mapping import agent_policy,resource_records
from ..broker_client import call as broker
router=APIRouter()

def invoke(fn,*args):
    try: return fn(*args)
    except PermissionError as e: raise HTTPException(401,str(e))
    except (ValueError,RuntimeError) as e: raise HTTPException(409,str(e))
    except (OSError,TimeoutError): raise HTTPException(503,'Agent 控制连接不可达，执行保持暂停')

class Model(BaseModel): model_config=ConfigDict(extra='forbid')
class Register(Model):
    name:str=Field(min_length=1,max_length=120)
    agent_type:Literal['dsh','hermes','other']
    resources:list[str]=Field(default_factory=list,max_length=16)
    mode:Literal['controlled','observed']='controlled'
    environment:Literal['wsl','windows']='wsl'
    open_url:str=''
class WindowsProcess(Model):
    name:str=Field(max_length=120)
    agent_type:Literal['codex','hermes-desktop']
    pid:int=Field(gt=0)
    started_at:str=Field(pattern=r'^[0-9]{17}$')
    executable:str=Field(max_length=1000)
class WindowsReport(Model):
    rows:list[WindowsProcess]=Field(max_length=100)
class Configure(Model):
    name:str=Field(min_length=1,max_length=120)
    resources:list[str]=Field(min_length=1,max_length=16)
    expected_policy_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
class Proposal(Model):
    generation:str|None=None
    base_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    request_key:str=Field(min_length=8,max_length=100)
    policy:dict
class Confirm(Model):
    proposal_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
class Lease(Model):
    generation:str=Field(pattern=r'^[a-f0-9]{32}$')
    session_id:str=Field(min_length=1,max_length=200)
    call_id:str=Field(min_length=1,max_length=200)
    tool:str=Field(min_length=1,max_length=100)
class Result(Lease):
    succeeded:bool
class Session(Model):
    resource:str=Field(max_length=1000)
class Prompt(Model):
    session_id:str=Field(min_length=1,max_length=200)
    text:str=Field(min_length=1,max_length=12000)
class Generation(Model):
    generation:str=Field(pattern=r'^[a-f0-9]{32}$')

@router.get('/api/agent-instances')
def instances(): return invoke(c.listing)
@router.post('/api/agent-instances/discover')
def discover(): return invoke(c.listing,True)
@router.post('/api/agent-discovery/windows')
def windows_report(body:WindowsReport): return invoke(discovery.windows_report,[r.model_dump() for r in body.rows])
@router.post('/api/agent-instances')
def register(body:Register): return invoke(c.register,body.model_dump())
@router.get('/api/agent-instances/{ident}')
def detail(ident:str): return invoke(c.detail,ident)
@router.put('/api/agent-instances/{ident}')
def configure(ident:str,body:Configure): return invoke(c.configure,ident,body.model_dump())
@router.post('/api/agent-instances/{ident}/check')
def check(ident:str):
    invoke(c.observer.collect)
    return invoke(c.detail,ident)
@router.post('/api/agent-instances/{ident}/open')
def open_agent(ident:str):
    try: row=store.get(ident)
    except ValueError: row=None
    if row and row['mode']=='observed': return {'url':invoke(discovery.local_url,row['runtime']['open_url'])}
    return invoke(broker,{'action':'agent-instance-open','instance_id':ident})
@router.post('/api/agent-instances/{ident}/start')
def start(ident:str): return invoke(c.start,ident)
@router.post('/api/agent-instances/{ident}/stop')
def stop(ident:str): return invoke(c.stop,ident)
@router.get('/api/agent-instances/{ident}/policy')
def policy(ident:str):
    row=invoke(c.detail,ident)
    return {k:row.get(k) for k in ('policy','policy_hash','generation','gate','policy_records','proposals')}
@router.post('/api/agent-instances/{ident}/policy/proposals')
def proposal(ident:str,body:Proposal): return invoke(c.proposals,ident,body.model_dump())
@router.post('/api/agent-instances/{ident}/policy/proposals/{pid}/confirm')
def confirm(ident:str,pid:str,body:Confirm): return invoke(c.apply,ident,pid,body.proposal_hash)
@router.get('/api/agent-instances/{ident}/sessions')
def sessions(ident:str):
    row=invoke(c.detail,ident)
    if row['mode']=='observed' and (not row.get('connected') or row.get('runtime',{}).get('open_url')) or row.get('gate')=='closed':
        return {'sessions':[],'resources':row.get('resources',[]),'mapping_available':False}
    return invoke(broker,{'action':'agent-instance-sessions','instance_id':ident})
@router.post('/api/agent-instances/{ident}/sessions')
def session(ident:str,body:Session):
    row=invoke(store.get,ident)
    if row['gate']!='open' or body.resource not in row['resources']: raise HTTPException(409,'实例未运行或资源未登记')
    return invoke(broker,{'action':'agent-instance-native','instance_id':ident,'operation':'create','resource':body.resource})
@router.post('/api/agent-instances/{ident}/sessions/prompt')
def prompt(ident:str,body:Prompt):
    row=invoke(store.get,ident)
    if row['gate']!='open': raise HTTPException(409,'实例执行已暂停')
    return invoke(broker,{'action':'agent-instance-native','instance_id':ident,'operation':'prompt',**body.model_dump()})
@router.get('/api/agent-instances/{ident}/processes')
def processes(ident:str):
    row=invoke(c.detail,ident)
    if row['mode']=='observed' and (not row.get('connected') or row.get('runtime',{}).get('open_url')) or row.get('gate')=='closed':
        return {'processes':[{'pid':row['pid'],'start_ticks':row.get('started_at'),'role':'observed process','domain_verified':False}] if row.get('pid') else [],'mapping_available':False}
    return invoke(broker,{'action':'agent-instance-processes','instance_id':ident})
@router.get('/api/agent-instances/{ident}/events')
def events(ident:str,before:int|None=Query(None,ge=1)):
    return {'events':invoke(store.events,ident,before)}

def auth(ident,request,generation):
    h=request.headers.get('authorization','')
    return invoke(c.agent_auth,ident,h[7:] if h.lower().startswith('bearer ') else '',generation)
@router.post('/api/agent/instances/{ident}/scope')
def agent_scope(ident:str,body:Generation,request:Request):
    row=auth(ident,request,body.generation)
    return {**{k:row[k] for k in ('id','policy_hash','generation','gate')},'policy':agent_policy(row['policy'],row['resources']),'resources':[r['execution'] for r in resource_records(row['resources'])],'resource_records':resource_records(row['resources'])}
@router.post('/api/agent/instances/{ident}/lease')
def acquire(ident:str,body:Lease,request:Request):
    auth(ident,request,body.generation)
    return invoke(c.lease,ident,body.model_dump())
@router.post('/api/agent/instances/{ident}/result')
def result(ident:str,body:Result,request:Request):
    auth(ident,request,body.generation)
    return invoke(c.result,ident,body.model_dump())
@router.post('/api/agent/instances/{ident}/policy/proposals')
def agent_proposal(ident:str,body:Proposal,request:Request):
    auth(ident,request,body.generation)
    return invoke(c.proposals,ident,body.model_dump(),'agent')

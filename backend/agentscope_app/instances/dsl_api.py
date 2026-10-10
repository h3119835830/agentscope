"""Administrator-only DSL and session read APIs; never mounted under /api/agent."""
from typing import Literal
from fastapi import APIRouter,Query
from pydantic import Field
from .api import Model,Confirm,invoke
from . import dsl_policy as dsl,sessions

router=APIRouter()
class Candidate(Model):
    documents:list[dict]=Field(max_length=20)
    base_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    base_revision:int=Field(ge=0)
    request_key:str=Field(min_length=8,max_length=100)

@router.get('/api/security/system/dsl')
def system_read():return invoke(dsl.detail,'system')
@router.post('/api/security/system/dsl/proposals')
def system_propose(body:Candidate):return invoke(dsl.propose,'system',body.model_dump())
@router.post('/api/security/system/dsl/proposals/{pid}/confirm')
def system_confirm(pid:str,body:Confirm):return invoke(dsl.apply,'system',pid,body.proposal_hash)
@router.get('/api/agent-instances/{ident}/dsl')
def agent_read(ident:str):return invoke(dsl.detail,ident)
@router.post('/api/agent-instances/{ident}/dsl/proposals')
def agent_propose(ident:str,body:Candidate):return invoke(dsl.propose,ident,body.model_dump())
@router.post('/api/agent-instances/{ident}/dsl/proposals/{pid}/confirm')
def agent_confirm(ident:str,pid:str,body:Confirm):return invoke(dsl.apply,ident,pid,body.proposal_hash)

@router.get('/api/sessions')
def directory(agent_type:str='',instance_id:str='',q:str=Query('',max_length=200),cursor:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=100),workspace:str=Query('',max_length=4096)):
    return invoke(sessions.directory,agent_type,instance_id,q,cursor,limit,workspace)
@router.get('/api/agent-instances/{ident}/sessions/{sid}/policies')
def policies(ident:str,sid:str,generation:str|None=None):return invoke(sessions.policies,ident,sid,generation)
@router.get('/api/agent-instances/{ident}/sessions/{sid}/domains')
def domains(ident:str,sid:str,generation:str|None=None):return invoke(sessions.domains,ident,sid,generation)
@router.get('/api/agent-instances/{ident}/sessions/{sid}/kernel-events')
def kernel(ident:str,sid:str,generation:str|None=None,before:int|None=Query(None,ge=1),limit:int=Query(30,ge=1,le=100)):
    return invoke(sessions.kernel_page,ident,sid,generation,before,limit)
@router.get('/api/agent-instances/{ident}/sessions/{sid}/tool-traces')
def traces(ident:str,sid:str,generation:str|None=None,before:int|None=Query(None,ge=1),limit:int=Query(30,ge=1,le=100)):
    return invoke(sessions.traces,ident,sid,generation,before,limit)

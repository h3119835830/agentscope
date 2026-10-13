"""Administrator-only DSL and session read APIs; never mounted under /api/agent."""
from typing import Literal
from fastapi import APIRouter,Query
from pydantic import Field
from .api import Model,Confirm,invoke
from . import dsl_policy as dsl,sessions

router=APIRouter()
class LibrarySave(Model):
    kind:Literal['structured','dsl']
    base_revision:int=Field(ge=0)
    config:dict|None=None
    document:dict|None=None
class LibraryVersion(Model):
    revision:int=Field(ge=1)
class LibrarySelection(LibraryVersion):
    id:str=Field(min_length=1,max_length=80)
class LibraryProposal(Model):
    selections:list[LibrarySelection]=Field(default_factory=list,max_length=20)
    removals:list[str]=Field(default_factory=list,max_length=20)
    base_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    base_revision:int=Field(ge=0)
    request_key:str=Field(min_length=8,max_length=100)

@router.get('/api/security/system/policy-library')
def library_read():
    from . import policy_library
    return invoke(policy_library.directory)
@router.post('/api/security/system/policy-library')
def library_create(body:LibrarySave):
    from . import policy_library
    return invoke(policy_library.save,body.model_dump())
@router.post('/api/security/system/policy-library/{ident}/versions')
def library_save(ident:str,body:LibrarySave):
    from . import policy_library
    return invoke(policy_library.save,body.model_dump(),ident)
@router.post('/api/security/system/policy-library/{ident}/archive')
def library_archive(ident:str,body:LibraryVersion):
    from . import policy_library
    return invoke(policy_library.archive,ident,body.revision)
@router.post('/api/security/system/policy-library/proposals')
def library_propose(body:LibraryProposal):
    from . import policy_library
    return invoke(policy_library.propose,body.model_dump())
@router.get('/api/security/system/execution-capabilities')
def library_capabilities():
    from ..broker_client import call
    return invoke(call,{'action':'agent-instance-dsl-capabilities'})

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
def system_confirm(pid:str,body:Confirm):
    from .approval_decisions import confirm_scoped
    return invoke(confirm_scoped,'system',pid,body.proposal_hash)
@router.get('/api/agent-instances/{ident}/dsl')
def agent_read(ident:str):return invoke(dsl.detail,ident)
@router.post('/api/agent-instances/{ident}/dsl/proposals')
def agent_propose(ident:str,body:Candidate):return invoke(dsl.propose,ident,body.model_dump())
@router.post('/api/agent-instances/{ident}/dsl/proposals/{pid}/confirm')
def agent_confirm(ident:str,pid:str,body:Confirm):
    from .approval_decisions import confirm_scoped
    return invoke(confirm_scoped,ident,pid,body.proposal_hash)

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

@router.get('/api/agent-instances/{ident}/policy-context')
def policy_context(ident:str,session_id:str|None=Query(None,max_length=200),scope:Literal['agent','workspace']|None=None,workspace_id:str|None=Query(None,max_length=200)):
    from ..history.agent_context import snapshot,scoped_snapshot
    if scope:
        if session_id:
            from fastapi import HTTPException
            raise HTTPException(422,'显式范围不能由会话覆盖')
        return invoke(scoped_snapshot,ident,scope,workspace_id)
    return invoke(snapshot,ident,session_id)

class SceneSelection(Model):
    session_id:str=Field(min_length=1,max_length=200)
    context_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    request_key:str=Field(min_length=8,max_length=100)

@router.post('/api/agent-instances/{ident}/policy-scenes')
def policy_scene_create(ident:str,body:SceneSelection):
    from ..history.agent_scene import create
    return invoke(create,ident,body.session_id,body.context_hash,body.request_key)

@router.get('/api/agent-instances/{ident}/policy-scenes')
def policy_scene_latest(ident:str,session_id:str=Query(min_length=1,max_length=200)):
    from ..history.agent_scene import latest
    return invoke(latest,ident,session_id)

@router.get('/api/agent-instances/{ident}/policy-scenes/{read_id}')
def policy_scene_get(ident:str,read_id:str):
    from ..history.agent_scene import get
    return invoke(get,ident,read_id)

@router.get('/api/agent-instances/{ident}/policy-conversation')
def policy_conversation(ident:str,session_id:str|None=Query(None,max_length=200)):
    from ..history.agent_context import conversation
    return invoke(conversation,ident,session_id)

@router.get('/api/agent-instances/{ident}/policy-candidates/{artifact_id}')
def policy_candidate(ident:str,artifact_id:str):
    from ..history.agent_context import selected_candidate
    return invoke(selected_candidate,ident,artifact_id)

class LocalCandidate(Model):
    candidate_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    request_key:str=Field(min_length=8,max_length=100)

@router.post('/api/agent-instances/{ident}/policy-candidates/{artifact_id}/proposals')
def local_candidate(ident:str,artifact_id:str,body:LocalCandidate):
    from .local_policy_proposals import submit
    return invoke(submit,ident,artifact_id,body.model_dump())

@router.post('/api/security/system/dsl/proposals/{pid}/reject')
def system_reject(pid:str,body:Confirm):
    from .approval_decisions import reject_scoped
    return invoke(reject_scoped,'system',pid,body.proposal_hash)

@router.post('/api/agent-instances/{ident}/dsl/proposals/{pid}/reject')
def agent_reject(ident:str,pid:str,body:Confirm):
    from .approval_decisions import reject_scoped
    return invoke(reject_scoped,ident,pid,body.proposal_hash)

"""Authenticated control-plane lifecycle settings, immutable audits and reviews."""
from typing import Literal
from fastapi import APIRouter,Query
from pydantic import Field
from .api import Model,invoke
from . import policy_lifecycle as lifecycle,template_tools

router=APIRouter()

class Configuration(Model):
    enabled:bool
    requirements:str=Field(min_length=5,max_length=8000)
    workspace_id:str=Field(min_length=1,max_length=200)
    integrity_paths:list[str]=Field(min_length=1,max_length=10)

class Retry(Model):
    input_hash:str=Field(pattern=r'^[a-f0-9]{64}$')

class Review(Retry):
    finding_id:str=Field(min_length=1,max_length=40)
    disposition:Literal['confirmed_risk','false_positive','needs_investigation']
    note:str=Field(min_length=1,max_length=2000)

@router.get('/api/policy-lifecycle/{ident}')
def jobs(ident:str,session_id:str|None=Query(None,max_length=200)):
    return invoke(lifecycle.jobs,ident,session_id)

@router.post('/api/policy-lifecycle/{ident}/configuration')
def configure(ident:str,body:Configuration):
    return invoke(lifecycle.configure,ident,body.model_dump())

@router.post('/api/policy-lifecycle/{ident}/jobs/{job_id}/retry')
def retry(ident:str,job_id:str,body:Retry):
    return invoke(lifecycle.retry,ident,job_id,body.input_hash)

@router.post('/api/policy-lifecycle/{ident}/jobs/{job_id}/review')
def review(ident:str,job_id:str,body:Review):
    return invoke(lifecycle.review,ident,job_id,body.model_dump())

@router.get('/api/policy-template-tools')
def tools(scope:Literal['agent','system']='agent',q:str|None=Query(None,max_length=2000)):
    return {'tools':invoke(template_tools.search,q,scope) if q else invoke(template_tools.definitions,scope),'applies_policy':False}

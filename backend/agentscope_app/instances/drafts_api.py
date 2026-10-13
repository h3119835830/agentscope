"""Authenticated, target-bound draft editing; no approval authority."""
from typing import Literal
from fastapi import APIRouter, Query
from pydantic import Field
from .api import Model, invoke
from . import policy_drafts as drafts

router=APIRouter(prefix='/api/agent-instances/{ident}/policy-drafts')

class Material(Model):
    name:str=Field(min_length=1,max_length=80)
    text:str=Field(min_length=1,max_length=8000)

class DraftSave(Model):
    scope:Literal['agent','workspace']='agent'
    workspace_id:str|None=Field(default=None,max_length=200)
    base_revision:int=Field(default=0,ge=0)
    text:str=Field(default='',max_length=2000)
    materials:list[Material]=Field(default_factory=list,max_length=10)
    document:dict|None=None
    scene_id:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')
    request_key:str=Field(min_length=8,max_length=100)

class VersionRequest(Model):
    revision:int=Field(ge=1)
    request_key:str=Field(min_length=8,max_length=100)

class Submit(VersionRequest):
    artifact_id:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')

@router.get('')
def directory(ident:str,scope:Literal['agent','workspace']='agent',workspace_id:str|None=Query(None,max_length=200)):
    return invoke(drafts.directory,ident,scope,workspace_id)

@router.post('')
def create(ident:str,body:DraftSave):
    return invoke(drafts.save,ident,body.model_dump())

@router.get('/{draft_id}')
def detail(ident:str,draft_id:str,revision:int|None=Query(None,ge=1)):
    return invoke(lambda:view(ident,draft_id,revision))

def view(ident,draft_id,revision):
    row=drafts.load(ident,draft_id,revision)
    drafts.owner(ident)
    return drafts.view(row)

@router.patch('/{draft_id}')
def update(ident:str,draft_id:str,body:DraftSave):
    return invoke(drafts.save,ident,body.model_dump(),draft_id)

@router.post('/{draft_id}/generate')
def generate(ident:str,draft_id:str,body:VersionRequest):
    return invoke(drafts.generate,ident,draft_id,body.revision,body.request_key)

@router.post('/{draft_id}/submit')
def submit(ident:str,draft_id:str,body:Submit):
    return invoke(drafts.submit,ident,draft_id,body.model_dump())

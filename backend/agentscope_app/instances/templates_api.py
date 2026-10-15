"""Control-plane parameter APIs; no browser automation or policy application."""
from typing import Literal
from fastapi import APIRouter, Query
from pydantic import Field
from .api import Model, invoke
from . import template_configurations as configurations
from . import workspace_references as references

router = APIRouter()


class Configuration(Model):
    template_id: str = Field(min_length=1,max_length=80)
    template_version: int = Field(ge=1)
    scope: Literal['system','agent','workspace'] = 'agent'
    workspace_id: str | None = Field(default=None,max_length=200)
    name: str = Field(default='',max_length=120)
    reason: str = Field(default='',max_length=600)
    parameters: dict
    base_revision: int = Field(default=0,ge=0)
    request_key: str = Field(min_length=8,max_length=100)


class ConfigurationUpdate(Configuration):
    scope_id: str = Field(min_length=1,max_length=100)


class Create(ConfigurationUpdate):
    pass


class Proposal(Model):
    revision: int = Field(ge=1)
    operation: Literal['apply','disable'] = 'apply'
    acknowledge_coverage: bool = False
    request_key: str = Field(min_length=8,max_length=100)


class Version(Model):
    revision: int = Field(ge=1)


class Selection(Version):
    id: str = Field(min_length=1,max_length=80)


class Batch(Model):
    scope_id: str = Field(min_length=1,max_length=100)
    selections: list[Selection] = Field(min_length=1,max_length=20)
    operation: Literal['apply','disable'] = 'apply'
    acknowledge_coverage: bool = False
    base_revision: int = Field(ge=0)
    base_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    request_key: str = Field(min_length=8,max_length=100)


class Material(Model):
    name: str = Field(min_length=1,max_length=80)
    text: str = Field(min_length=1,max_length=8000)


class Generate(Model):
    text: str = Field(min_length=5,max_length=2000)
    scope: Literal['agent','workspace'] = 'agent'
    workspace_id: str | None = Field(default=None,max_length=200)
    materials: list[Material] = Field(default_factory=list,max_length=10)
    reference_read_id: str | None = Field(default=None,min_length=1,max_length=64)
    request_key: str = Field(min_length=8,max_length=100)


class ScopedGenerate(Generate):
    scope_id: str = Field(min_length=1,max_length=100)
    scope: Literal['system','agent']


class ReadWorkspace(Model):
    workspace_id: str = Field(min_length=1,max_length=64)
    paths: list[str] = Field(min_length=1,max_length=10)
    request_key: str = Field(min_length=8,max_length=100)


@router.get('/api/agent-instances/{ident}/policy-reference-workspaces')
def reference_workspaces(ident: str):
    return invoke(references.directory,ident)


@router.post('/api/agent-instances/{ident}/policy-workspace-reads')
def read_workspace(ident: str,body: ReadWorkspace):
    return invoke(references.create,ident,body.model_dump())


@router.get('/api/agent-instances/{ident}/policy-workspace-reads/{read_id}')
def read_workspace_record(ident: str,read_id: str):
    return invoke(lambda:references.public(references.verify(ident,read_id)))


@router.get('/api/policy-templates')
def directory(scope_id: str | None = Query(None,max_length=100)):
    return invoke(configurations.directory,scope_id)


@router.post('/api/policy-template-configurations')
def create(body: Create):
    values = body.model_dump()
    scope_id = values.pop('scope_id')
    return invoke(configurations.save,scope_id,values)


@router.post('/api/policy-template-configurations/proposals')
def propose_batch(body: Batch):
    return invoke(configurations.propose_batch,body.model_dump())


@router.post('/api/policy-template-configurations/generate')
def generate_scoped(body: ScopedGenerate):
    value = body.model_dump()
    scope_id = value.pop('scope_id')
    return invoke(configurations.generate,scope_id,value)


@router.post('/api/policy-template-configurations/{ident}/versions')
def update(ident: str,body: ConfigurationUpdate):
    values = body.model_dump()
    scope_id = values.pop('scope_id')
    return invoke(configurations.save,scope_id,values,ident)


@router.post('/api/policy-template-configurations/{ident}/proposals')
def propose(ident: str,body: Proposal):
    return invoke(configurations.propose,ident,body.model_dump())


@router.post('/api/policy-template-configurations/{ident}/archive')
def archive(ident: str,body: Version):
    return invoke(configurations.archive,ident,body.revision)


@router.post('/api/agent-instances/{ident}/template-configurations/generate')
def generate(ident: str,body: Generate):
    return invoke(configurations.generate,ident,body.model_dump())

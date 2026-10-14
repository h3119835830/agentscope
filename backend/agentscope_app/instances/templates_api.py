"""Control-plane parameter APIs; no browser automation or policy application."""
from typing import Literal
from fastapi import APIRouter, Query
from pydantic import Field
from .api import Model, invoke
from . import template_configurations as configurations

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


class Material(Model):
    name: str = Field(min_length=1,max_length=80)
    text: str = Field(min_length=1,max_length=8000)


class Generate(Model):
    text: str = Field(min_length=5,max_length=2000)
    scope: Literal['agent','workspace'] = 'agent'
    workspace_id: str | None = Field(default=None,max_length=200)
    materials: list[Material] = Field(default_factory=list,max_length=10)
    request_key: str = Field(min_length=8,max_length=100)


@router.get('/api/policy-templates')
def directory(scope_id: str | None = Query(None,max_length=100)):
    return invoke(configurations.directory,scope_id)


@router.post('/api/policy-template-configurations')
def create(body: Create):
    values = body.model_dump()
    scope_id = values.pop('scope_id')
    return invoke(configurations.save,scope_id,values)


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

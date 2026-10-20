"""Control-plane parameter APIs; no browser automation or policy application."""
from typing import Literal
from fastapi import APIRouter, Query
from pydantic import Field
from .api import Model, invoke
from . import template_configurations as configurations
from . import workspace_references as references
from . import template_versions

router = APIRouter()


class TemplateParameter(Model):
    key: str = Field(min_length=1,max_length=80)
    label: str = Field(min_length=1,max_length=120)
    default: str = Field(max_length=10000)


class TemplateUpdate(Model):
    name: str = Field(min_length=1,max_length=120)
    description: str = Field(min_length=1,max_length=3000)
    effect: Literal['block','notify','kill']
    parameters: list[TemplateParameter] = Field(max_length=32)
    base_version: int = Field(ge=2)
    request_key: str = Field(min_length=8,max_length=100)


class DslPreview(Model):
    template_version: int = Field(ge=1)
    parameters: dict = Field(default_factory=dict)
    effect: Literal['block','notify','kill'] | None = None
    reason: str | None = Field(default=None,max_length=600)
    scope_id: str | None = Field(default=None,max_length=100)
    label_source_refs: list[dict] = Field(default_factory=list,max_length=16)

class LabelSourceRef(Model):
    id: str = Field(min_length=1,max_length=80)
    version: int = Field(ge=1)


class LabelSourceSave(Model):
    label: Literal['SECRET'] = 'SECRET'
    scope_id: str = Field(min_length=1,max_length=100)
    matcher: Literal['exact','directory','pattern','suffix']
    value: str = Field(min_length=1,max_length=1000)
    base_version: int = Field(default=0,ge=0)
    request_key: str = Field(min_length=8,max_length=100)


class LabelSourceArchive(Model):
    version: int = Field(ge=1)


@router.get('/api/security/labels')
def labels(scope_id: str | None = Query(None,max_length=100)):
    from . import label_sources
    return invoke(label_sources.directory,scope_id)


@router.post('/api/security/label-sources')
def source_create(body: LabelSourceSave):
    from . import label_sources
    return invoke(label_sources.save,body.model_dump())


@router.post('/api/security/label-sources/{ident}/versions')
def source_update(ident: str,body: LabelSourceSave):
    from . import label_sources
    return invoke(label_sources.save,body.model_dump(),ident)


@router.post('/api/security/label-sources/{ident}/archive')
def source_archive(ident: str,body: LabelSourceArchive):
    from . import label_sources
    return invoke(label_sources.archive,ident,body.version)


class Configuration(Model):
    template_id: str = Field(min_length=1,max_length=80)
    template_version: int = Field(ge=1)
    scope: Literal['system','agent','workspace'] = 'agent'
    workspace_id: str | None = Field(default=None,max_length=200)
    name: str = Field(default='',max_length=120)
    reason: str = Field(default='',max_length=600)
    parameters: dict
    label_source_refs: list[LabelSourceRef] = Field(default_factory=list,max_length=16)
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


class ConversationMessage(Model):
    role: Literal['user','assistant']
    content: str = Field(min_length=1,max_length=3000)


class Generate(Model):
    text: str = Field(min_length=1,max_length=2000)
    parent_request_id: str | None = Field(default=None,pattern=r'^[a-f0-9]{32}$')
    conversation: list[ConversationMessage] = Field(default_factory=list,max_length=6)
    scope: Literal['agent','workspace'] = 'agent'
    workspace_id: str | None = Field(default=None,max_length=200)
    reference_workspace_id: str | None = Field(default=None,max_length=64)
    stage: Literal['preflight','runtime'] = 'preflight'
    runtime_event_seq: int | None = Field(default=None,ge=1)
    materials: list[Material] = Field(default_factory=list,max_length=10)
    reference_read_id: str | None = Field(default=None,min_length=1,max_length=64)
    context_mode: Literal['auto','provided','none'] = 'auto'
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


@router.get('/api/agent-instances/{ident}/policy-reference-workspaces/{workspace_id}/files')
def reference_files(ident: str,workspace_id: str,path: str=Query('',max_length=1000),cursor: int=Query(0,ge=0,le=1000)):
    return invoke(references.list_files,ident,workspace_id,path,cursor)


@router.get('/api/agent-instances/{ident}/policy-workspace-reads/{read_id}')
def read_workspace_record(ident: str,read_id: str):
    return invoke(lambda:references.public(references.verify(ident,read_id)))


@router.get('/api/policy-templates')
def directory(scope_id: str | None = Query(None,max_length=100)):
    return invoke(configurations.directory,scope_id)


@router.post('/api/policy-templates/{ident}/versions')
def edit_template(ident: str,body: TemplateUpdate):
    return invoke(template_versions.save,ident,body.model_dump())


@router.post('/api/policy-templates/{ident}/preview')
def preview_template(ident: str,body: DslPreview):
    from .template_dsl import preview
    return invoke(preview,ident,body.model_dump())


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

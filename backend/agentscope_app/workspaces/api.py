from typing import Literal
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field, ConfigDict, model_validator
from . import registry as r
from . import scene_read
from . import connections

router = APIRouter()


@router.get('/api/workspace-connection-history')
def connection_history(page: int = Query(0, ge=0), limit: int = Query(12, ge=1, le=50)):
    return connections.history(page, limit)


@router.get('/api/workspace-connection-history/{instance_id}')
def connection_history_detail(instance_id: str, before: int | None = Query(None, ge=1),
                              limit: int = Query(30, ge=1, le=100)):
    return connections.detail(instance_id, before, limit)


def call(fn, *args):
    try:
        return fn(*args)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(409, str(error))
    except OSError:
        raise HTTPException(503, 'Agent 工作区暂不可读取，请检查目录权限和执行端状态')


class Workspace(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=120)
    path: str = Field(default='', max_length=1000)


class Task(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str | None = Field(default=None, min_length=1, max_length=120)
    prompt: str | None = Field(default=None, min_length=3, max_length=8000)
    read_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    draft_hash: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    expected_manifest_hash: str = Field(pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def one_source(self):
        if self.read_id is not None:
            if self.draft_hash is None or self.name is not None or self.prompt is not None:
                raise ValueError('采用场景草稿须提供 draft_hash，不能混用手填目标')
        elif self.name is None or self.prompt is None or self.draft_hash is not None:
            raise ValueError('请选择场景识别结果，或提供完整任务名称和目标')
        return self


class SceneRead(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_manifest_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    supplement: str = Field(default='', max_length=8000)


class StartupConfirmation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_context_hash: str
    expected_proposal_hash: str


@router.get('/api/workspace-agents')
def agents():
    return call(r.agents)


@router.post('/api/workspace-agents/{agent_id}/connect')
def connect(agent_id: str):
    return call(r.connect, agent_id)


@router.get('/api/workspace-agents/{agent_id}/workspaces')
def workspaces(agent_id: str):
    return call(r.workspaces, agent_id)


@router.post('/api/workspace-agents/{agent_id}/workspaces')
def create_workspace(agent_id: str, body: Workspace):
    return call(r.create_workspace, body.name.strip(), body.path.strip(), agent_id)


@router.post('/api/workspace-agents/{agent_id}/check')
def check(agent_id: str):
    return call(r.connect, agent_id)


@router.get('/api/workspace-agents/{agent_id}/directories')
def directories(agent_id: str, path: str = ''):
    return call(r.directories, agent_id, path)


@router.get('/api/agent-workspaces/{workspace_id}/files')
def files(workspace_id: str):
    return call(r.inventory, workspace_id)


@router.post('/api/agent-workspaces/{workspace_id}/tasks')
def create_task(workspace_id: str, body: Task):
    if body.read_id is not None:
        return call(r.create_task_from_scene, workspace_id, body.read_id, body.draft_hash, body.expected_manifest_hash)
    return call(r.create_task, workspace_id, body.name.strip(), body.prompt.strip(), body.expected_manifest_hash)


@router.get('/api/workspace-tasks')
def task_records():
    return call(r.task_records)


@router.post('/api/managed/tasks/{task_id}/startup/confirm')
def confirm(task_id: str, body: StartupConfirmation):
    from ..managed.controller import confirm_startup
    return call(confirm_startup, task_id, body.expected_context_hash, body.expected_proposal_hash)


@router.post('/api/agent-workspaces/{workspace_id}/scene-reads')
def read_scene(workspace_id: str, body: SceneRead):
    return call(scene_read.create, workspace_id, body.expected_manifest_hash, body.supplement.strip())


@router.get('/api/agent-workspaces/{workspace_id}/scene-reads/{read_id}')
def read_scene_status(workspace_id: str, read_id: str):
    return call(scene_read.get, workspace_id, read_id)


@router.post('/api/scene-reader/jobs/{read_id}/tools/{tool}')
def scene_reader_tool(read_id: str, tool: str, body: dict, request: Request):
    supplied = request.headers.get('authorization', '')
    token = supplied[7:] if supplied.lower().startswith('bearer ') else ''
    return call(scene_read.invoke, read_id, tool, body, token)


class StartupRecovery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['reuse', 'rebuild']
    expected_context_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_manifest_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_candidate_task_id: str | None = Field(default=None, max_length=100)
    expected_candidate_proposal_hash: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')


@router.get('/api/managed/tasks/{task_id}/startup/recovery')
def startup_recovery(task_id: str):
    from .recovery import get
    return call(get, task_id)


@router.post('/api/managed/tasks/{task_id}/startup/recovery')
def prepare_startup_recovery(task_id: str, body: StartupRecovery):
    from .recovery import prepare
    return call(prepare, task_id, body.model_dump())

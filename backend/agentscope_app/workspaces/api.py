from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from . import registry as r

router = APIRouter()


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
    name: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=3, max_length=8000)
    expected_manifest_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


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


@router.post('/api/workspace-agents/dsh/workspaces')
def create_workspace(body: Workspace):
    return call(r.create_workspace, body.name.strip(), body.path.strip())


@router.get('/api/agent-workspaces/{workspace_id}/files')
def files(workspace_id: str):
    return call(r.inventory, workspace_id)


@router.post('/api/agent-workspaces/{workspace_id}/tasks')
def create_task(workspace_id: str, body: Task):
    return call(r.create_task, workspace_id, body.name.strip(), body.prompt.strip(), body.expected_manifest_hash)


@router.get('/api/workspace-tasks')
def task_records():
    return call(r.task_records)


@router.post('/api/managed/tasks/{task_id}/startup/confirm')
def confirm(task_id: str, body: StartupConfirmation):
    from ..managed.controller import confirm_startup
    return call(confirm_startup, task_id, body.expected_context_hash, body.expected_proposal_hash)

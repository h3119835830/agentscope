"""HTTP authority boundary for read-only inference and explicit adoption."""
import pytest
from agentscope_app.workspaces import api as workspace_api

ADMIN={'Authorization':'Bearer test-admin-token-not-for-production'}


def test_scene_read_control_routes_require_admin(client):
    for method, path, body in [
        ('post','/api/agent-workspaces/work/scene-reads',{'expected_manifest_hash':'a'*64}),
        ('get','/api/agent-workspaces/work/scene-reads/read',None),
        ('post','/api/agent-workspaces/work/tasks',{'read_id':'a'*32,'draft_hash':'b'*64,'expected_manifest_hash':'c'*64}),
    ]:
        response=getattr(client,method)(path,**({'json':body} if body else {}))
        assert response.status_code==401


def test_scene_read_model_token_cannot_control_task(client):
    response=client.post('/api/agent-workspaces/work/scene-reads',headers={'Authorization':'Bearer isolated-scene-job-fixture'},json={'expected_manifest_hash':'a'*64})
    assert response.status_code==401


def test_scene_read_tool_route_requires_its_job_credential(client):
    for headers in ({},ADMIN):
        result=client.post('/api/scene-reader/jobs/missing/tools/list_scene_sources',headers=headers,json={})
        assert result.status_code==401
    assert client.post('/api/scene-reader/jobs/missing/tools/execute',json={}).status_code==404


@pytest.mark.parametrize('extra',[
    {},{'read_id':'a'*32},{'draft_hash':'b'*64},
    {'read_id':'a'*32,'draft_hash':'b'*64,'name':'Override'},
    {'read_id':'a'*32,'draft_hash':'b'*64,'prompt':'Override goal'},
])
def test_adoption_request_rejects_incomplete_or_mixed_authority(client,extra):
    result=client.post('/api/agent-workspaces/work/tasks',headers=ADMIN,json={'expected_manifest_hash':'c'*64,**extra})
    assert result.status_code==422


def test_scene_read_http_only_dispatches_requested_bound_context(client,monkeypatch):
    calls=[]
    monkeypatch.setattr(workspace_api.scene_read,'create',lambda *args: calls.append(args) or {'status':'queued','read_only':True})
    result=client.post('/api/agent-workspaces/work/scene-reads',headers=ADMIN,json={'expected_manifest_hash':'a'*64,'supplement':'  Describe files.  '})
    assert result.status_code==200 and result.json()['read_only']
    assert calls==[('work','a'*64,'Describe files.')]


def test_adoption_without_manual_name_goal_dispatches_exact_server_candidate(client,monkeypatch):
    calls=[]
    monkeypatch.setattr(workspace_api.r,'create_task_from_scene',lambda *args: calls.append(args) or {'id':'bound-task'})
    result=client.post('/api/agent-workspaces/work/tasks',headers=ADMIN,json={'expected_manifest_hash':'c'*64,'read_id':'a'*32,'draft_hash':'b'*64})
    assert result.status_code==200 and result.json()['id']=='bound-task'
    assert calls==[('work','a'*32,'b'*64,'c'*64)]

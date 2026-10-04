import pytest
from fastapi.testclient import TestClient
from agentscope_app import development
from agentscope_app.main import app


def test_default_control_access_still_requires_authentication():
    assert not development.DEV_NO_AUTH
    with TestClient(app, base_url='http://127.0.0.1:18000', client=('127.0.0.1', 52000)) as client:
        assert client.get('/api/auth/mode').json()['authentication_required']
        assert client.get('/api/tasks').status_code == 401


def test_local_development_can_enter_without_a_password(monkeypatch):
    monkeypatch.setattr(development, 'DEV_NO_AUTH', True)
    with TestClient(app, base_url='http://127.0.0.1:18000', client=('127.0.0.1', 52000)) as client:
        assert client.get('/api/auth/mode').json()['development_no_password']
        assert client.get('/api/auth/check').status_code == 200
        assert client.get('/api/tasks').status_code == 200
        assert client.get('/api/dashboard').status_code == 200
        assert client.get('/api/tasks', headers={'Authorization':'Bearer unrelated-task-token'}).status_code == 401
        assert client.get('/api/plugin/tasks/missing/scope').status_code == 401
        route='/api/generator/tasks/missing/jobs/missing/tools/get_task_context'
        assert client.post(route,json={}).status_code == 401


@pytest.mark.parametrize('peer,host,origin',[
    ('10.1.1.2','127.0.0.1',None),
    ('127.0.0.1','outside.example',None),
    ('127.0.0.1','127.0.0.1','https://outside.example'),
])
def test_development_entry_is_limited_to_local_requests(monkeypatch,peer,host,origin):
    monkeypatch.setattr(development,'DEV_NO_AUTH',True)
    with TestClient(app,base_url='http://'+host,client=(peer,52000)) as client:
        headers={'Origin':origin} if origin else {}
        assert not client.get('/api/auth/mode',headers=headers).json()['development_no_password']
        assert client.get('/api/tasks',headers=headers).status_code == 401

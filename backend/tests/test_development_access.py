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
    ('127.0.0.1','127.0.0.1:18003','http://127.0.0.1:18000'),
])
def test_development_entry_is_limited_to_local_requests(monkeypatch,peer,host,origin):
    monkeypatch.setattr(development,'DEV_NO_AUTH',True)
    with TestClient(app,base_url='http://'+host,client=(peer,52000)) as client:
        headers={'Origin':origin} if origin else {}
        assert not client.get('/api/auth/mode',headers=headers).json()['development_no_password']
        assert client.get('/api/tasks',headers=headers).status_code == 401


def test_demo_control_operations_need_no_admin_token_or_browser_session(monkeypatch):
    from agentscope_app import main
    from agentscope_app.scope import api as scope_api
    from agentscope_app.managed import api as managed_api
    monkeypatch.setattr(development, 'DEV_NO_AUTH', True)
    monkeypatch.setattr(main, 'ADMIN_TOKEN', '')
    monkeypatch.setattr(scope_api.demo, 'create', lambda: {'created':True})
    monkeypatch.setattr(scope_api.manager, 'review_and_apply', lambda *args: {'applied':True})
    monkeypatch.setattr(managed_api.c, 'confirm_expansion', lambda *args: {'confirmed':True})
    with TestClient(app, base_url='http://127.0.0.1:18003', client=('127.0.0.1', 52000)) as client:
        headers={'Origin':'http://127.0.0.1:18003'}
        assert client.get('/api/tasks').status_code == 200
        assert client.post('/api/scope-demo/tasks', headers=headers).json() == {'created':True}
        response=client.post('/api/tasks/demo/scope-manager/changes/change/review', headers=headers, json={'decision':'approve','expected_proposal_hash':'candidate'})
        assert response.status_code == 200
        assert response.json() == {'applied':True}
        response=client.post('/api/managed/tasks/demo/expansion/confirm', headers=headers, json={'expected_hash':'candidate'})
        assert response.status_code == 200
        assert response.json() == {'confirmed':True}
        assert 'set-cookie' not in response.headers
        assert not client.cookies
        for endpoint in ('ticket','redeem','connect','close'):
            route='/api/auth/local-browser-'+endpoint
            assert not any(getattr(item, 'path', None) == route for item in app.routes)
            assert client.post(route, headers=headers).status_code in (404, 405)


def test_demo_preserves_task_credential_boundary(monkeypatch, seed_task):
    from agentscope_app.main import issue_task_token
    monkeypatch.setattr(development, 'DEV_NO_AUTH', True)
    seed_task('local-task-one')
    seed_task('local-task-two')
    token, _ = issue_task_token('local-task-one')
    with TestClient(app, base_url='http://127.0.0.1:18003', client=('127.0.0.1', 52000)) as client:
        headers={'Authorization':'Bearer '+token}
        assert client.get('/api/tasks', headers=headers).status_code == 401
        response=client.post('/api/plugin/tasks/local-task-one/scope-requests', headers=headers,
                             json={'kind':'expand','justification':'Need report'})
        assert response.status_code == 200
        assert client.post('/api/plugin/tasks/local-task-two/scope-requests', headers=headers,
                           json={'kind':'expand','justification':'Cross-task request'}).status_code == 401
        assert client.get('/api/plugin/tasks/local-task-one/scope').status_code == 401
        route='/api/generator/tasks/local-task-one/jobs/missing/tools/get_task_context'
        assert client.post(route, json={}).status_code == 401

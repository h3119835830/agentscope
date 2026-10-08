import grp
import hashlib
import json
import os
import uuid
from pathlib import Path

import pytest

from agentscope_app import db
from agentscope_app.bootstrap import scene
from agentscope_app.managed import controller as c
from agentscope_app.workspaces import registry as r

ADMIN = {'Authorization': 'Bearer test-admin-token-not-for-production'}
RUNTIME = {'package': '@deepseek-ai/dsh', 'model': 'test-provider', 'profile': 'headless'}


@pytest.fixture
def workspace(client, tmp_path, monkeypatch):
    monkeypatch.setattr(r, 'WORKSPACE_ROOT', tmp_path)
    monkeypatch.delenv('AGENTSCOPE_DSH_WORKSPACE_ROOTS', raising=False)
    monkeypatch.setenv('AGENTSCOPE_TASK_GROUP', grp.getgrgid(os.getgid()).gr_name)
    monkeypatch.setattr(r, 'effective_dsh', lambda: RUNTIME.copy())
    monkeypatch.setattr(scene, 'effective_dsh', lambda: RUNTIME.copy())
    value = r.create_workspace('Current project')
    root = Path(value['path'])
    (root / 'tests').mkdir()
    (root / 'tests/test_main.py').write_text('def test_main():\n    assert True\n')
    (root / 'main.py').write_text('print("project")\n')
    return value


def task_from(workspace):
    return r.create_task(workspace['id'], 'Workspace task', 'Fix main.py; preserve tests/test_main.py.', r.inventory(workspace['id'])['manifest_hash'])


def reviewed(task):
    job, proposal = uuid.uuid4().hex, uuid.uuid4().hex
    with db.connect() as con:
        con.execute('INSERT INTO history_jobs(id,kind,status,input_json,created_at) VALUES(?,?,?,?,?)',
                    (job, 'task_bootstrap', 'completed', json.dumps({'task_id': task['id']}), db.now()))
        con.execute('INSERT INTO bootstrap_proposals(id,task_id,job_id,context_hash,proposal_json,content_hash,state,validation_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                    (proposal, task['id'], job, scene.context(task['id'],con)['context_hash'], '{}', scene.digest({}), 'validated', '{}', db.now()))
        state = c.load(con, task['id'])
        state.update(phase='generating', startup_job=job)
        c.save(con, task['id'], state)
    c.complete_start(task['id'])
    return scene.context(task['id'])['context_hash'], scene.digest({})


def test_inventory_and_connection_require_administrator(client):
    for method, url in [('get', '/api/workspace-agents'), ('get', '/api/workspace-tasks'), ('post', '/api/workspace-agents/dsh/connect')]:
        assert getattr(client, method)(url).status_code == 401


def test_unavailable_provider_cannot_claim_connection(client, monkeypatch):
    monkeypatch.setattr(r, 'effective_dsh', lambda: (_ for _ in ()).throw(RuntimeError('private detail')))
    value = client.get('/api/workspace-agents', headers=ADMIN).json()['agents'][0]
    assert not value['available'] and not value['connected']
    assert 'private detail' not in value['error']
    assert client.post('/api/workspace-agents/dsh/connect', headers=ADMIN).status_code == 409


def test_actual_files_refresh_and_credentials_are_excluded(workspace):
    before = r.inventory(workspace['id'])
    root = Path(workspace['path'])
    (root / 'new.txt').write_text('new project material')
    (root / '.env').write_text('hidden')
    (root / '.env.local').write_text('hidden')
    (root / '.credentials.yaml').write_text('hidden')
    after = r.inventory(workspace['id'])
    assert {f['relative_path'] for f in after['files']} == {'main.py', 'tests/test_main.py', 'new.txt'}
    assert before['manifest_hash'] != after['manifest_hash']
    assert 'content' not in after['files'][0]


def test_workspace_cannot_escape_operator_roots_or_follow_symlinks(workspace, tmp_path):
    root = Path(workspace['path'])
    for value in ['/etc', str(root / '..' / root.name), str(tmp_path)]:
        with pytest.raises(ValueError):
            r.register(value, 'invalid')
    (root / 'alias').symlink_to('/etc/passwd')
    with pytest.raises(ValueError, match='符号链接'):
        r.inventory(workspace['id'])
    (root / 'alias').unlink()
    (root / 'alias').symlink_to(root / 'tests', target_is_directory=True)
    with pytest.raises(ValueError, match='符号链接'):
        r.inventory(workspace['id'])


def test_stale_preview_cannot_create_task(workspace):
    old = r.inventory(workspace['id'])['manifest_hash']
    (Path(workspace['path']) / 'main.py').write_text('changed after preview')
    with pytest.raises(ValueError, match='已变化'):
        r.create_task(workspace['id'], 'A task', 'Preserve tests', old)
    assert not [t for t in r.task_records()['records'] if t['workspace_id'] == workspace['id']]


def test_new_task_is_an_independent_evidence_bound_snapshot(workspace):
    task = task_from(workspace)
    ctx = scene.context(task['id'])
    assert ctx['workspace'] != workspace['path']
    (Path(ctx['workspace']) / 'main.py').write_text('modified by task')
    assert (Path(workspace['path']) / 'main.py').read_text() == 'print("project")\n'
    assert ctx['workspace_source']['runtime_profile_hash'] == scene.digest(RUNTIME)
    assert len(ctx['assets']) == 2 and ctx['declared_constraints'] == []
    with db.connect() as con:
        state = c.load(con, task['id'])
        assert state['startup_review_required'] and state['phase'] == 'prepared' and state['version'] == 0
        assert con.execute('SELECT COUNT(*) FROM policy_versions WHERE task_id=?', (task['id'],)).fetchone()[0] == 0
    record = next(t for t in r.task_records()['records'] if t['id'] == task['id'])
    assert record['workspace_id'] == workspace['id'] and record['source_path'] == workspace['path']
    assert len([w for w in r.workspaces()['workspaces'] if w['path'] == ctx['workspace']]) == 0


def test_started_agent_workspace_is_readable_for_a_following_task(workspace):
    task=task_from(workspace)
    with db.connect() as con:
        state=c.load(con,task['id']);state.update(session_id='received-native-session',phase='ended');c.save(con,task['id'],state)
    (Path(task['workspace'])/'main.py').write_text('updated by the Agent')
    execution=next(w for w in r.workspaces()['workspaces'] if w['path']==task['workspace'])
    assert execution['origin']=='managed_session_workspace'
    following=task_from(execution)
    assert (Path(following['workspace'])/'main.py').read_text()=='updated by the Agent'
    assert (Path(workspace['path'])/'main.py').read_text()=='print("project")\n'


def test_no_loading_or_approval_before_explicit_review(workspace, monkeypatch):
    task = task_from(workspace)
    monkeypatch.setattr(c, 'broker', lambda *a, **k: pytest.fail('unconfirmed task must not call broker'))
    reviewed(task)
    with db.connect() as con:
        state = c.load(con, task['id'])
        assert state['phase'] == 'policy_review' and state['gate'] == 'waiting_confirmation'
        assert state['version'] == 0 and state['session_id'] is None
        assert con.execute('SELECT COUNT(*) FROM policy_versions WHERE task_id=?', (task['id'],)).fetchone()[0] == 0


def test_startup_confirmation_rejects_stale_candidate_and_changed_snapshot(workspace):
    task = task_from(workspace)
    context_hash, proposal_hash = reviewed(task)
    with pytest.raises(ValueError, match='已变化'):
        c.confirm_startup(task['id'], context_hash, '0' * 64)
    (Path(task['workspace']) / 'main.py').write_text('modified since policy generation')
    with pytest.raises(ValueError, match='文件已变化'):
        c.confirm_startup(task['id'], context_hash, proposal_hash)
    with db.connect() as con:
        assert c.load(con, task['id'])['phase'] == 'policy_review'


def test_confirmation_preserves_identity_and_does_not_claim_loading(workspace):
    task = task_from(workspace)
    context_hash, proposal_hash = reviewed(task)
    c.confirm_startup(task['id'], context_hash, proposal_hash)
    with db.connect() as con:
        state = c.load(con, task['id'])
        assert state['phase'] == 'generating' and state['version'] == 0
        assert state['startup_confirmation'] == {'context_hash': context_hash, 'proposal_hash': proposal_hash}
    with pytest.raises(ValueError, match='待确认状态'):
        c.confirm_startup(task['id'], context_hash, proposal_hash)


def test_changed_runtime_cannot_be_confirmed(workspace, monkeypatch):
    task = task_from(workspace)
    hashes = reviewed(task)
    monkeypatch.setattr(scene, 'effective_dsh', lambda: {**RUNTIME, 'model': 'different'})
    with pytest.raises(ValueError, match='执行端配置已变化'):
        c.confirm_startup(task['id'], *hashes)


def test_snapshot_is_rechecked_after_confirmation_before_loading(workspace,monkeypatch):
    task=task_from(workspace)
    hashes=reviewed(task)
    c.confirm_startup(task['id'],*hashes)
    (Path(task['workspace'])/'main.py').write_text('changed after confirmation')
    monkeypatch.setattr(c,'install',lambda *a,**k:pytest.fail('changed snapshot must never load'))
    with pytest.raises(ValueError,match='文件已变化'):
        c.complete_start(task['id'])


def test_empty_workspace_and_empty_request_are_rejected(workspace, client):
    value = r.create_workspace('Empty')
    with pytest.raises(ValueError, match='没有可读取'):
        r.create_task(value['id'], 'Empty task', 'Do work', r.inventory(value['id'])['manifest_hash'])
    response = client.post('/api/workspace-agents/dsh/workspaces', headers=ADMIN, json={'name': '  '})
    assert response.status_code == 409


def test_history_survives_absent_execution_directory(workspace):
    task = task_from(workspace)
    missing = str(Path(task['workspace']).parent / 'archived-project')
    with db.connect() as con:
        con.execute("UPDATE tasks SET workspace=?,status='completed' WHERE id=?",(missing,task['id']))
        state=c.load(con,task['id']);state['phase']='ended';c.save(con,task['id'],state)
    record=next(t for t in r.task_records()['records'] if t['id']==task['id'])
    assert record['phase']=='ended' and record['workspace_available'] is False
    assert record['source_path']==workspace['path']


def test_snapshot_aliases_preserve_source_bytes_and_frozen_path_provenance(workspace):
    root=Path(workspace['path'])
    project=root/'workspace'/'transaction-verification-service'
    (project/'tests').mkdir(parents=True)
    (project/'setup.py').write_text('from setuptools import setup\n')
    (project/'tests'/'tests_rate_limiter.py').write_text('def test_limiter():\n    assert True\n')
    before=r.inventory(workspace['id'])
    task=r.create_task(workspace['id'],'Long project','Fix limiter; preserve all existing tests.',before['manifest_hash'])
    ctx=scene.context(task['id'])
    prefix='workspace/transaction-verification-service'
    alias=ctx['asset_layout']['project_prefixes'][prefix]
    assert alias in ('p0','p')
    assert ctx['mapping'][str(project)]==str(Path(ctx['workspace'])/alias)
    assert ctx['mapping']['/workspace/'+prefix]==str(Path(ctx['workspace'])/alias)
    assert ctx['asset_layout_mapping_hash']==scene.digest(ctx['asset_layout_mapping'])
    for asset in ctx['assets']:
        original=root/asset['source_relative_path']
        assert original.read_bytes()==Path(asset['mapped_path']).read_bytes()
        assert hashlib.sha256(original.read_bytes()).hexdigest()==asset['sha256']
        assert asset['relative_path']==ctx['asset_layout_mapping'][asset['source_relative_path']]
    assert r.inventory(workspace['id'])['manifest_hash']==before['manifest_hash']
    with db.connect() as con:
        state=c.load(con,task['id'])
        assert state['version']==0 and state['session_id'] is None and state['startup_review_required']
        assert con.execute('SELECT COUNT(*) FROM policy_versions WHERE task_id=?',(task['id'],)).fetchone()[0]==0


def test_later_snapshot_mapping_never_rewrites_an_existing_task_context(workspace):
    previous=task_from(workspace)
    frozen=scene.context(previous['id'])
    project=Path(workspace['path'])/'a-very-long-project-container-directory'
    project.mkdir();(project/'setup.py').write_text('# setup\n');(project/'main.py').write_text('# main\n')
    following=task_from(workspace)
    assert scene.context(previous['id'])==frozen
    assert scene.context(following['id'])['asset_layout']['project_prefixes']


def test_storage_identity_and_output_cannot_cross_tasks(workspace):
    first, second = task_from(workspace), task_from(workspace)
    left, right = scene.context(first['id']), scene.context(second['id'])
    with db.connect() as con:
        task = dict(con.execute('SELECT * FROM tasks WHERE id=?', (first['id'],)).fetchone())
    c.verify_execution_storage(task, left)
    with pytest.raises(ValueError):
        c.verify_execution_storage(task, {k:v for k,v in left.items() if k!='execution_storage'})
    with pytest.raises(ValueError):
        c.verify_execution_storage(task, {**left, 'execution_storage': right['execution_storage']})
    with pytest.raises(ValueError):
        c.verify_execution_storage({**task, 'output_dir': str(Path(right['workspace']).parent/'output')}, left)
    with pytest.raises(ValueError):
        c.verify_execution_storage(task, {**left, 'workspace': right['workspace']})


def test_replaced_execution_root_is_rejected_before_confirmation(workspace):
    task = task_from(workspace)
    ctx = scene.context(task['id'])
    with db.connect() as con:
        row = dict(con.execute('SELECT * FROM tasks WHERE id=?', (task['id'],)).fetchone())
    root = Path(row['workspace']).parent
    retained = root.with_name(root.name+'-retained')
    root.rename(retained)
    root.mkdir()
    Path(row['workspace']).mkdir()
    Path(row['output_dir']).mkdir()
    with pytest.raises(ValueError):
        c.verify_execution_storage(row, ctx)


def test_asset_backed_logical_project_mapping_exists_without_path_compaction(workspace):
    root=Path(workspace['path']);(root/'pyproject.toml').write_text('[project]\nname="example"\n')
    task=task_from(workspace);ctx=scene.context(task['id'])
    assert ctx['mapping']['/workspace']==ctx['workspace']
    assert (root/'pyproject.toml').read_text()=='[project]\nname="example"\n'

"""Same-task startup generation retries never grant or load execution authority."""
import grp
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agentscope_app import db
from agentscope_app.bootstrap import scene, validation
from agentscope_app.history import jobs
from agentscope_app.managed import controller as c
from agentscope_app.workspaces import registry

RUNTIME = {'model': 'isolated-startup-retry'}


@pytest.fixture
def failed_task(client, tmp_path, monkeypatch):
    monkeypatch.setattr(registry, 'WORKSPACE_ROOT', tmp_path)
    monkeypatch.setenv('AGENTSCOPE_TASK_GROUP', grp.getgrgid(os.getgid()).gr_name)
    monkeypatch.setattr(registry, 'effective_dsh', lambda: RUNTIME.copy())
    monkeypatch.setattr(scene, 'effective_dsh', lambda: RUNTIME.copy())
    monkeypatch.setattr(c, 'broker', lambda *a, **k: pytest.fail('retry must not call Broker'))
    monkeypatch.setattr(jobs, 'execute', lambda *a, **k: pytest.fail('retry must not run a model'))
    workspace = registry.create_workspace('Retry source')
    (Path(workspace['path']) / 'main.py').write_text('print("original")\n')
    task = registry.create_task(workspace['id'], 'Retry task', 'Explain main.py; preserve its source.',
                                registry.inventory(workspace['id'])['manifest_hash'])
    job_id, proposal_id = uuid.uuid4().hex, uuid.uuid4().hex
    with db.connect() as con:
        con.execute('INSERT INTO history_jobs(id,kind,status,input_json,error,created_at,finished_at) VALUES(?,?,?,?,?,?,?)',
                    (job_id, 'task_bootstrap', 'failed', json.dumps({'task_id': task['id']}),
                     'Original synthetic generation failure', db.now(), db.now()))
        con.execute('INSERT INTO bootstrap_proposals VALUES(?,?,?,?,?,?,?,?,?)',
                    (proposal_id, task['id'], job_id, scene.context(task['id'], con)['context_hash'],
                     scene.digest({}), '{}', '{}', 'invalid', db.now()))
        state = c.load(con, task['id'])
        state.update(phase='failed', gate='failed', startup_job=job_id,
                     startup_proposal=proposal_id, error='Original synthetic generation failure')
        c.save(con, task['id'], state)
        con.execute("UPDATE tasks SET status='failed' WHERE id=?", (task['id'],))
        c.event(con, task['id'], 'failure', job_id, {'error': state['error']})
    return task['id'], job_id


def immutable(task_id, job_id):
    with db.connect() as con:
        return {table: [tuple(r) for r in con.execute(sql, (ident,))]
                for table, sql, ident in (
                    ('context', 'SELECT * FROM bootstrap_contexts WHERE task_id=?', task_id),
                    ('sources', 'SELECT * FROM bootstrap_sources WHERE task_id=? ORDER BY id', task_id),
                    ('proposals', 'SELECT * FROM bootstrap_proposals WHERE task_id=? ORDER BY id', task_id),
                    ('root', 'SELECT * FROM snapshot_roots WHERE task_id=?', task_id),
                    ('source', 'SELECT * FROM workspace_task_sources WHERE task_id=?', task_id),
                    ('job', 'SELECT * FROM history_jobs WHERE id=?', job_id),
                    ('failure', "SELECT * FROM managed_events WHERE task_id=? AND kind='failure'", task_id))}


def assert_no_authority(task_id):
    with db.connect() as con:
        state = c.load(con, task_id)
        assert state['version'] == 0 and not state['session_id'] and not state['binding']
        assert state['startup_review_required'] is True
        assert not con.execute('SELECT 1 FROM policy_versions WHERE task_id=?', (task_id,)).fetchone()
        assert not con.execute('SELECT 1 FROM task_credentials WHERE task_id=?', (task_id,)).fetchone()


@pytest.mark.parametrize('status', ['failed', 'interrupted', 'cancelled'])
def test_terminal_generation_retries_same_task_without_rebuilding_or_rewriting(failed_task, status):
    task_id, previous = failed_task
    with db.connect() as con:
        con.execute('UPDATE history_jobs SET status=? WHERE id=?', (status, previous))
        count = con.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
    before = immutable(task_id, previous)
    result = c.start(task_id)
    assert result['job_id'] != previous and result['status'] == 'generating'
    assert immutable(task_id, previous) == before
    with db.connect() as con:
        state = c.load(con, task_id)
        new = con.execute('SELECT * FROM history_jobs WHERE id=?', (result['job_id'],)).fetchone()
        assert state['phase'] == 'generating' and state['gate'] == 'waiting_policy'
        assert state['startup_job'] == new['id'] and 'startup_proposal' not in state
        assert 'error' not in state
        assert con.execute('SELECT error FROM history_jobs WHERE id=?', (previous,)).fetchone()[0] == 'Original synthetic generation failure'
        assert new['retry_of'] == previous and new['status'] == 'queued'
        assert json.loads(new['input_json'])['task_id'] == task_id
        assert con.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == count
        event = con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='startup_generation' AND event_key=?", (task_id, new['id'])).fetchone()
        payload = json.loads(event[0])
        assert payload['previous_job_id'] == previous and payload['same_task_retry'] is True
        assert payload['context_hash'] == scene.context(task_id, con)['context_hash']
    assert_no_authority(task_id)


@pytest.mark.parametrize('change', ['missing_pointer', 'missing_job', 'other_task', 'other_kind',
                                   'queued', 'running', 'unsupported_status', 'completed_other_task'])
def test_missing_mismatched_or_nonterminal_current_job_is_rejected(failed_task, change, monkeypatch):
    task_id, previous = failed_task
    with db.connect() as con:
        if change == 'missing_pointer':
            state = c.load(con, task_id); state['startup_job'] = None; c.save(con, task_id, state)
        elif change == 'missing_job':
            con.execute('UPDATE history_jobs SET id=? WHERE id=?', (uuid.uuid4().hex, previous))
        elif change in ('other_task', 'completed_other_task'):
            con.execute('UPDATE history_jobs SET input_json=?,status=? WHERE id=?',
                        (json.dumps({'task_id': 'another-task'}), 'completed' if change == 'completed_other_task' else 'failed', previous))
        elif change == 'other_kind':
            con.execute("UPDATE history_jobs SET kind='compile' WHERE id=?", (previous,))
        else:
            con.execute('UPDATE history_jobs SET status=? WHERE id=?', ('unknown' if change == 'unsupported_status' else change, previous))
    monkeypatch.setattr(jobs, 'enqueue', lambda *a, **k: pytest.fail('invalid retry must not enqueue'))
    with pytest.raises(ValueError): c.start(task_id)
    assert_no_authority(task_id)


@pytest.mark.parametrize('status', ['queued', 'running'])
def test_another_active_generation_blocks_retry(failed_task, status, monkeypatch):
    task_id, _ = failed_task
    with db.connect() as con:
        con.execute('INSERT INTO history_jobs(id,kind,status,input_json,created_at) VALUES(?,?,?,?,?)',
                    (uuid.uuid4().hex, 'task_bootstrap', status, json.dumps({'task_id': task_id}), db.now()))
    monkeypatch.setattr(jobs, 'enqueue', lambda *a, **k: pytest.fail('active generation must block enqueue'))
    with pytest.raises(ValueError, match='活动'): c.start(task_id)


@pytest.mark.parametrize('authority', ['session_id', 'binding', 'startup_confirmation', 'active_version',
                                      'active_pid', 'active_domain_id', 'watch_pid', 'ended_at',
                                      'policy_version', 'credential'])
def test_any_existing_authority_or_execution_binding_blocks_retry(failed_task, authority, monkeypatch):
    task_id, _ = failed_task
    with db.connect() as con:
        if authority in ('session_id', 'binding', 'startup_confirmation'):
            state = c.load(con, task_id)
            state[authority] = {'bound': True} if authority != 'session_id' else 'old-session'
            c.save(con, task_id, state)
        elif authority == 'credential':
            con.execute('INSERT INTO task_credentials(id,task_id,token_sha256,created_at) VALUES(?,?,?,?)',
                        (uuid.uuid4().hex, task_id, uuid.uuid4().hex, db.now()))
        elif authority == 'policy_version':
            con.execute('INSERT INTO policy_versions(id,task_id,version,layer,dsl_text,policy_yaml,compile_state,status,change_summary,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (uuid.uuid4().hex, task_id, 1, 'task_bootstrap', '', '', 'compiled', 'draft', 'existing', db.now()))
        else:
            con.execute('UPDATE tasks SET '+authority+'=? WHERE id=?', (db.now() if authority == 'ended_at' else 1, task_id))
    monkeypatch.setattr(jobs, 'enqueue', lambda *a, **k: pytest.fail('bound task must not enqueue'))
    with pytest.raises(ValueError, match='未授权'): c.start(task_id)


@pytest.mark.parametrize('change', ['context_hash', 'prompt', 'settings', 'asset_bytes', 'missing_asset',
                                   'runtime', 'missing_storage', 'replaced_root', 'cross_output'])
def test_frozen_context_assets_runtime_and_storage_must_still_match(failed_task, change, monkeypatch):
    task_id, _ = failed_task
    ctx = scene.context(task_id)
    with db.connect() as con:
        if change in ('context_hash', 'missing_storage'):
            stored = json.loads(con.execute('SELECT context_json FROM bootstrap_contexts WHERE task_id=?', (task_id,)).fetchone()[0])
            if change == 'context_hash': stored['raw_prompt_hash'] = 'changed-without-hash'
            else: stored.pop('execution_storage')
            con.execute('UPDATE bootstrap_contexts SET context_json=? WHERE task_id=?', (json.dumps(stored), task_id))
            if change == 'missing_storage':
                con.execute('UPDATE bootstrap_contexts SET context_hash=? WHERE task_id=?', (scene.digest(stored), task_id))
        elif change == 'prompt':
            con.execute("UPDATE tasks SET prompt='Changed goal' WHERE id=?", (task_id,))
        elif change == 'settings':
            con.execute("UPDATE tasks SET settings_json='{}' WHERE id=?", (task_id,))
        elif change == 'cross_output':
            con.execute('UPDATE tasks SET output_dir=? WHERE id=?', (str(Path(ctx['workspace']).parent/'tmp'), task_id))
    if change == 'asset_bytes': Path(ctx['assets'][0]['mapped_path']).write_text('changed source')
    elif change == 'missing_asset': Path(ctx['assets'][0]['mapped_path']).unlink()
    elif change == 'runtime': monkeypatch.setattr(scene, 'effective_dsh', lambda: {'model': 'changed-runtime'})
    elif change == 'replaced_root':
        root = Path(ctx['workspace']).parent
        root.rename(root.with_name(root.name+'-retained'))
        (root/'r').mkdir(parents=True); (root/'output').mkdir()
    monkeypatch.setattr(jobs, 'enqueue', lambda *a, **k: pytest.fail('changed snapshot must not enqueue'))
    with pytest.raises((ValueError, FileNotFoundError)): c.start(task_id)


def test_enqueue_failure_keeps_failed_state_and_original_job(failed_task, monkeypatch):
    task_id, previous = failed_task
    before = immutable(task_id, previous)
    monkeypatch.setattr(jobs, 'enqueue', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('synthetic enqueue failure')))
    with pytest.raises(RuntimeError, match='synthetic enqueue failure'): c.start(task_id)
    assert immutable(task_id, previous) == before
    with db.connect() as con:
        state = c.load(con, task_id)
        assert state['phase'] == 'failed' and state['startup_job'] == previous
        assert con.execute('SELECT status FROM tasks WHERE id=?', (task_id,)).fetchone()[0] == 'failed'
    assert_no_authority(task_id)


def test_concurrent_retry_creates_only_one_new_job(failed_task):
    task_id, _ = failed_task
    def attempt():
        try: return c.start(task_id)
        except ValueError: return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sum(result is not None for result in results) == 1
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM history_jobs WHERE kind='task_bootstrap' AND json_extract(input_json,'$.task_id')=?", (task_id,)).fetchone()[0] == 2
    assert_no_authority(task_id)


def test_completed_generation_keeps_existing_resume_semantics(failed_task, monkeypatch):
    task_id, previous = failed_task
    with db.connect() as con: con.execute("UPDATE history_jobs SET status='completed' WHERE id=?", (previous,))
    monkeypatch.setattr(jobs, 'enqueue', lambda *a, **k: pytest.fail('completed job must not regenerate'))
    assert c.start(task_id) == {'job_id': previous, 'status': 'retrying_validated_startup'}
    assert_no_authority(task_id)


def test_new_successful_candidate_still_waits_for_human_confirmation(failed_task, monkeypatch):
    task_id, _ = failed_task
    result = c.start(task_id)
    import agentscope_app.main as main
    monkeypatch.setattr(main, 'compile_policy', lambda *a, **k: ('compiled', {'ok': True}, ''))
    ctx = scene.context(task_id)
    checked = validation.validate(task_id, {'context_hash': ctx['context_hash'], 'summary': 'Explain source',
                                           'no_op': True, 'guidance': ['Preserve source.']})
    assert checked['valid']
    proposal = uuid.uuid4().hex
    with db.connect() as con:
        con.execute("UPDATE history_jobs SET status='completed' WHERE id=?", (result['job_id'],))
        con.execute('INSERT INTO bootstrap_proposals VALUES(?,?,?,?,?,?,?,?,?)',
                    (proposal, task_id, result['job_id'], ctx['context_hash'], checked['proposal_hash'],
                     json.dumps(checked['proposal']), json.dumps({k:v for k,v in checked.items() if k!='proposal'}), 'validated', db.now()))
    c.complete_start(task_id)
    with db.connect() as con:
        state = c.load(con, task_id)
        assert state['phase'] == 'policy_review' and state['gate'] == 'waiting_confirmation'
        assert state['startup_proposal'] == proposal and not state.get('startup_confirmation')
    assert_no_authority(task_id)


@pytest.mark.parametrize('legacy_source', [None, [], {}, {'runtime_profile_hash': ''}])
def test_legacy_retry_without_frozen_workspace_runtime_returns_409(failed_task, client, monkeypatch, legacy_source):
    task_id, previous = failed_task
    with db.connect() as con:
        ctx = json.loads(con.execute('SELECT context_json FROM bootstrap_contexts WHERE task_id=?', (task_id,)).fetchone()[0])
        if legacy_source is None: ctx.pop('workspace_source')
        else: ctx['workspace_source'] = legacy_source
        con.execute('UPDATE bootstrap_contexts SET context_json=?,context_hash=? WHERE task_id=?',
                    (json.dumps(ctx), scene.digest(ctx), task_id))
    before = immutable(task_id, previous)
    monkeypatch.setattr(jobs, 'enqueue', lambda *a, **k: pytest.fail('unverifiable legacy runtime must not enqueue'))
    response = client.post('/api/managed/tasks/'+task_id+'/start',
                           headers={'Authorization': 'Bearer test-admin-token-not-for-production'})
    assert response.status_code == 409
    assert response.json()['detail'] == '缺少可核验的工作区运行配置，请从同源快照恢复'
    assert immutable(task_id, previous) == before
    assert_no_authority(task_id)

"""Recovery does not rewrite history, grant permission, probe, or run a model."""
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
from agentscope_app.managed import controller
from agentscope_app.workspaces import recovery, registry

AUTH = {'Authorization': 'Bearer test-admin-token-not-for-production'}


@pytest.fixture
def project(client, tmp_path, monkeypatch):
    monkeypatch.setattr(registry, 'WORKSPACE_ROOT', tmp_path)
    monkeypatch.setenv('AGENTSCOPE_TASK_GROUP', grp.getgrgid(os.getgid()).gr_name)
    monkeypatch.setattr(registry, 'effective_dsh', lambda: {'model': 'isolated-test'})
    monkeypatch.setattr(controller, 'broker', lambda *a, **k: pytest.fail('recovery cannot call Broker'))
    import agentscope_app.main as main
    monkeypatch.setattr(main, 'compile_policy', lambda *a, **k: ('compiled', {'ok': True}, ''))
    ws = registry.create_workspace('Recovery source')
    (Path(ws['path']) / 'README.md').write_text('Preserve existing tests.')
    return ws


def create(project, constraints=None):
    result = registry.create_task(project['id'], 'Preserve tests', 'Explain the project clearly.',
                                  registry.inventory(project['id'])['manifest_hash'])
    with db.connect() as con:
        row = con.execute('SELECT context_json FROM bootstrap_contexts WHERE task_id=?', (result['id'],)).fetchone()
        ctx = json.loads(row[0])
        ctx['accepted_task_constraints'] = constraints if constraints is not None else ['Preserve tests.']
        con.execute('UPDATE bootstrap_contexts SET context_json=?,context_hash=? WHERE task_id=?',
                    (json.dumps(ctx), scene.digest(ctx), result['id']))
    return result['id']


def job(task_id, status):
    ident = uuid.uuid4().hex
    with db.connect() as con:
        con.execute('INSERT INTO history_jobs(id,kind,status,input_json,created_at,error) VALUES(?,?,?,?,?,?)',
                    (ident, 'task_bootstrap', status, json.dumps({'task_id': task_id}), db.now(),
                     'Provider secret/private reason must not be public' if status == 'failed' else None))
    return ident


def failed(task_id):
    ident = job(task_id, 'failed')
    with db.connect() as con:
        state = controller.load(con, task_id)
        state.update(phase='failed', gate='failed', startup_job=ident)
        controller.save(con, task_id, state)
    return task_id


def ready(task_id):
    ident = job(task_id, 'completed')
    ctx = scene.context(task_id)
    result = validation.validate(task_id, {'context_hash': ctx['context_hash'], 'summary': 'Explain project',
                                          'no_op': True, 'guidance': ['Preserve tests.']})
    assert result['valid'] and result['compile_state'] == 'compiled'
    proposal_id = uuid.uuid4().hex
    with db.connect() as con:
        con.execute('INSERT INTO bootstrap_proposals VALUES(?,?,?,?,?,?,?,?,?)',
                    (proposal_id, task_id, ident, ctx['context_hash'], result['proposal_hash'],
                     json.dumps(result['proposal']), json.dumps({k: v for k, v in result.items() if k != 'proposal'}), 'validated', db.now()))
        state = controller.load(con, task_id)
        state.update(phase='policy_review', gate='waiting_confirmation', startup_job=ident,
                     startup_proposal=proposal_id, startup_review_required=True)
        controller.save(con, task_id, state)
    return task_id


def body(task_id, action='rebuild', candidate=None):
    view = recovery.get(task_id)
    result = {'action': action, 'expected_context_hash': view['origin']['context_hash'],
              'expected_manifest_hash': view['origin']['manifest_hash']}
    if candidate:
        item = next(c for c in view['candidates'] if c['task_id'] == candidate)
        result.update(expected_candidate_task_id=candidate, expected_candidate_proposal_hash=item['proposal_hash'])
    return result


def immutable(task_id):
    with db.connect() as con:
        return [tuple(r) for sql in (
            'SELECT * FROM bootstrap_contexts WHERE task_id=?',
            'SELECT * FROM bootstrap_sources WHERE task_id=? ORDER BY id',
            "SELECT * FROM history_jobs WHERE json_extract(input_json,'$.task_id')=?",
            'SELECT * FROM managed_tasks WHERE task_id=?')
            for r in con.execute(sql, (task_id,))]


def assert_zero_authority(*ids):
    with db.connect() as con:
        for task_id in ids:
            state = controller.load(con, task_id)
            assert state['version'] == 0 and state['session_id'] is None and not state['binding']
            assert not con.execute('SELECT 1 FROM policy_versions WHERE task_id=?', (task_id,)).fetchone()
            assert not con.execute('SELECT 1 FROM task_credentials WHERE task_id=?', (task_id,)).fetchone()


def test_get_and_reuse_are_db_only_immutable_and_idempotent(project):
    old = failed(create(project)); new = ready(create(project))
    before = immutable(old)
    view = recovery.get(old)
    assert view['eligible'] and view['candidate']['task_id'] == new
    assert 'Provider secret' not in json.dumps(view)
    request = body(old, 'reuse', new)
    first = recovery.prepare(old, request)
    second = recovery.prepare(old, request)
    assert first == second and first['target']['task_id'] == new
    assert recovery.get(old)['link']['task_id'] == new
    assert immutable(old) == before
    assert_zero_authority(old, new)
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM audit_log WHERE task_id=? AND action='startup_recovery_linked'", (old,)).fetchone()[0] == 1


@pytest.mark.parametrize('field', ['accepted_task_constraints', 'declared_constraints', 'platform_constraints',
                                  'execution_constraints', 'base_settings', 'startup_clarifications', 'prompt'])
def test_candidate_requires_exact_goal_and_all_constraint_baselines(project, field):
    old = failed(create(project)); new = ready(create(project))
    with db.connect() as con:
        row = con.execute('SELECT context_json FROM bootstrap_contexts WHERE task_id=?', (new,)).fetchone()
        ctx = json.loads(row[0])
        if field == 'prompt':
            con.execute('UPDATE tasks SET prompt=? WHERE id=?', ('Different goal', new))
            ctx['raw_prompt_hash'] = scene.digest('Different goal')
        elif field == 'declared_constraints':
            ctx[field] = [{'id': 'new', 'targets': [ctx['assets'][0]['mapped_path']], 'operations': ['write', 'unlink']}]
        elif field == 'startup_clarifications':
            ctx[field] = [{'text': 'New clarification', 'request_key': 'new', 'authority': 'authenticated_administrator'}]
        else:
            ctx[field] = ['Changed constraint'] if isinstance(ctx.get(field), list) else {'changed': True}
        con.execute('UPDATE bootstrap_contexts SET context_json=?,context_hash=? WHERE task_id=?',
                    (json.dumps(ctx), scene.digest(ctx), new))
    assert recovery.get(old)['candidate'] is None


def test_multiple_candidates_require_explicit_selection_and_exact_hash(project):
    old = failed(create(project)); a = ready(create(project)); b = ready(create(project))
    view = recovery.get(old)
    assert view['candidate'] is None and {c['task_id'] for c in view['candidates']} == {a, b}
    with pytest.raises(ValueError, match='明确'):
        recovery.prepare(old, body(old, 'reuse'))
    request = body(old, 'reuse', a); request['expected_candidate_proposal_hash'] = '0' * 64
    with pytest.raises(ValueError, match='过期'):
        recovery.prepare(old, request)
    recovery.prepare(old, body(old, 'reuse', a))
    with pytest.raises(ValueError, match='不同恢复关联'):
        recovery.prepare(old, body(old, 'reuse', b))


@pytest.mark.parametrize('change', ['phase', 'proposal', 'binding', 'manifest'])
def test_changed_candidate_is_rejected_without_substitution(project, change):
    old = failed(create(project)); target = ready(create(project))
    request = body(old, 'reuse', target)
    with db.connect() as con:
        state = controller.load(con, target)
        if change == 'phase':
            state['phase'] = 'generating'
        elif change == 'binding':
            state['binding'] = {'domain_id': 1}
        elif change == 'proposal':
            con.execute("UPDATE bootstrap_proposals SET proposal_json='{}' WHERE task_id=?", (target,))
        else:
            con.execute("UPDATE workspace_task_sources SET manifest_hash=? WHERE task_id=?", ('0' * 64, target))
        controller.save(con, target, state)
    with pytest.raises(ValueError):
        recovery.prepare(old, request)
    assert recovery.get(old)['candidate'] is None


def test_cross_workspace_and_nonfailed_or_bound_tasks_cannot_recover(project):
    old = failed(create(project)); other = registry.create_workspace('Other')
    (Path(other['path']) / 'README.md').write_text('Preserve existing tests.')
    target = ready(create(other))
    request = body(old, 'reuse')
    request.update(expected_candidate_task_id=target,
                   expected_candidate_proposal_hash=scene.context(target)['context_hash'])
    with pytest.raises(ValueError, match='来源'):
        recovery.prepare(old, request)
    with db.connect() as con:
        state = controller.load(con, old); state['session_id'] = 'existing'
        controller.save(con, old, state)
    assert not recovery.get(old)['eligible']


def test_rebuild_inherits_constraints_preserves_old_and_generates_once(project):
    old = failed(create(project)); before = immutable(old)
    request = body(old)
    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: recovery.prepare(old, request), range(2)))
    target = results[0]['target']['task_id']
    assert all(r['target']['task_id'] == target for r in results)
    ctx = scene.context(target)
    assert ctx['accepted_task_constraints'] == ['Preserve tests.']
    assert ctx['startup_recovery_origin'] == {'task_id': old, 'context_hash': request['expected_context_hash']}
    assert ctx['workspace_source']['manifest_hash'] == request['expected_manifest_hash']
    assert immutable(old) == before
    assert_zero_authority(old, target)
    with db.connect() as con:
        assert controller.load(con, target)['startup_review_required']
        assert con.execute("SELECT COUNT(*) FROM history_jobs WHERE json_extract(input_json,'$.task_id')=?", (target,)).fetchone()[0] == 1
        assert controller.load(con, target)['phase'] == 'generating'


def test_rebuild_enqueue_failure_is_retryable_without_duplicate_child_or_false_generating(project, monkeypatch):
    old = failed(create(project)); request = body(old)
    real = jobs.enqueue
    monkeypatch.setattr(jobs, 'enqueue', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('secret provider detail')))
    with pytest.raises(ValueError, match='可重试'):
        recovery.prepare(old, request)
    with db.connect() as con:
        link = dict(con.execute('SELECT * FROM startup_recoveries WHERE origin_task_id=?', (old,)).fetchone())
        target = link['target_task_id']
        assert link['status'] == 'failed' and link['error_code'] == 'recovery_generation_failed'
        assert controller.load(con, target)['phase'] == 'prepared'
    monkeypatch.setattr(jobs, 'enqueue', real)
    retried = recovery.prepare(old, request)
    assert retried['target']['task_id'] == target
    assert_zero_authority(old, target)


def test_source_changes_block_rebuild_and_leave_old_context_untouched(project):
    old = failed(create(project)); before = immutable(old); request = body(old)
    (Path(project['path']) / 'README.md').write_text('Changed source')
    with pytest.raises(ValueError, match='创建失败'):
        recovery.prepare(old, request)
    assert immutable(old) == before
    with db.connect() as con:
        link = con.execute('SELECT * FROM startup_recoveries WHERE origin_task_id=?', (old,)).fetchone()
        assert link['target_task_id'] is None and link['status'] == 'failed'


def test_http_auth_and_body_contract(project, client):
    old = failed(create(project))
    path = f'/api/managed/tasks/{old}/startup/recovery'
    assert client.get(path).status_code in (401, 403)
    assert client.get(path, headers=AUTH).json()['eligible']
    request = body(old); request['approve'] = True
    assert client.post(path, headers=AUTH, json=request).status_code == 422


@pytest.mark.parametrize('initialization', [True, False])
def test_rebuild_pre_generation_failure_resumes_same_child(project, monkeypatch, initialization):
    old = failed(create(project)); request = body(old)
    owner, method = (controller, 'initialize') if initialization else (jobs, 'enqueue')
    real = getattr(owner, method)
    monkeypatch.setattr(owner, method, lambda *a, **k: (_ for _ in ()).throw(RuntimeError('failure')))
    with pytest.raises(ValueError, match='可重试'):
        recovery.prepare(old, request)
    with db.connect() as con:
        target = con.execute('SELECT target_task_id FROM startup_recoveries WHERE origin_task_id=?', (old,)).fetchone()[0]
        assert target
        if initialization:
            assert not con.execute('SELECT 1 FROM managed_tasks WHERE task_id=?', (target,)).fetchone()
        con.execute("UPDATE startup_recoveries SET status='building',claimed_at=0 WHERE origin_task_id=?", (old,))
    monkeypatch.setattr(owner, method, real)
    assert recovery.prepare(old, request)['target']['task_id'] == target
    assert_zero_authority(old, target)


def test_rebuild_preserves_clarifications_and_rebinds_exact_declared_targets(project):
    old = create(project)
    with db.connect() as con:
        ctx = json.loads(con.execute('SELECT context_json FROM bootstrap_contexts WHERE task_id=?', (old,)).fetchone()[0])
        source_id = uuid.uuid4().hex
        text = 'Authenticated startup clarification: preserve README.'
        con.execute('INSERT INTO bootstrap_sources VALUES(?,?,?,?,?,?,?)',
                    (source_id, old, 'task', '', text, scene.digest(text), '{}'))
        ctx['startup_clarifications'] = [{'source_id': source_id, 'text': text, 'request_key': 'one',
                                         'authority': 'authenticated_administrator'}]
        ctx['declared_constraints'] = [{'id': 'preserve', 'targets': [ctx['assets'][0]['mapped_path']],
                                       'operations': ['write', 'unlink']}]
        con.execute('UPDATE bootstrap_contexts SET context_json=?,context_hash=? WHERE task_id=?',
                    (json.dumps(ctx), scene.digest(ctx), old))
    failed(old)
    target = recovery.prepare(old, body(old))['target']['task_id']
    new = scene.context(target)
    assert new['declared_constraints'][0]['targets'] == [new['assets'][0]['mapped_path']]
    assert old not in json.dumps(new['declared_constraints'])
    assert new['startup_clarifications'][0]['source_id'] != source_id
    with db.connect() as con:
        assert recovery.identity(con, old)[3] == recovery.identity(con, target)[3]
        new_id = new['startup_clarifications'][0]['source_id']
        assert con.execute('SELECT text FROM bootstrap_sources WHERE id=? AND task_id=?', (new_id, target)).fetchone()[0] == text
    assert recovery.get(old)['link']['task_id'] == target


def test_rebuild_retry_rejects_changed_child_constraints(project, monkeypatch):
    old = failed(create(project)); request = body(old)
    real = jobs.enqueue
    monkeypatch.setattr(jobs, 'enqueue', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('enqueue failed')))
    with pytest.raises(ValueError):
        recovery.prepare(old, request)
    with db.connect() as con:
        target = con.execute('SELECT target_task_id FROM startup_recoveries WHERE origin_task_id=?', (old,)).fetchone()[0]
        ctx = json.loads(con.execute('SELECT context_json FROM bootstrap_contexts WHERE task_id=?', (target,)).fetchone()[0])
        ctx['accepted_task_constraints'] = ['Changed']
        con.execute('UPDATE bootstrap_contexts SET context_json=?,context_hash=? WHERE task_id=?',
                    (json.dumps(ctx), scene.digest(ctx), target))
    monkeypatch.setattr(jobs, 'enqueue', real)
    with pytest.raises(ValueError, match='创建失败'):
        recovery.prepare(old, request)
    with db.connect() as con:
        assert not con.execute("SELECT 1 FROM history_jobs WHERE json_extract(input_json,'$.task_id')=?", (target,)).fetchone()


def test_link_tracks_generating_then_ready_without_stale_status(project):
    old = failed(create(project))
    target = recovery.prepare(old, body(old))['target']['task_id']
    view = recovery.get(old)
    assert view['link']['task_id'] == target and view['link_status'] == 'generating'
    with db.connect() as con:
        con.execute("UPDATE history_jobs SET status='completed' WHERE kind='task_bootstrap' AND json_extract(input_json,'$.task_id')=?", (target,))
    ready(target)
    view = recovery.get(old)
    assert view['link_status'] == 'awaiting_review'
    assert view['link']['proposal_hash'] and view['link']['task_id'] == target


@pytest.mark.parametrize('known_error', [True, False])
def test_legacy_limit_classification_requires_known_validation_error_and_registered_target(project, known_error):
    old = failed(create(project))
    with db.connect() as con:
        ctx = json.loads(con.execute('SELECT context_json FROM bootstrap_contexts WHERE task_id=?', (old,)).fetchone()[0])
        target = ctx['workspace'] + '/' + 'x' * recovery.PATTERN_MAX_UTF8_BYTES
        ctx['assets'][0]['mapped_path'] = target
        con.execute('UPDATE bootstrap_contexts SET context_json=?,context_hash=? WHERE task_id=?',
                    (json.dumps(ctx), scene.digest(ctx), old))
        state = controller.load(con, old)
        con.execute('INSERT INTO bootstrap_tool_events VALUES(?,?,?,?,?,?)',
                    (uuid.uuid4().hex, state['startup_job'], 'validate_policy_draft',
                     json.dumps({'draft': {'atoms': [{'paths': [target]}]}}),
                     json.dumps({'valid': False, 'diagnostic':
                         'IR pattern 超过 ' + str(recovery.PATTERN_MAX_UTF8_BYTES) + ' UTF-8 bytes 或包含控制字符'
                         if known_error else 'Untrusted provider message'}), db.now()))
    failure = recovery.get(old)['failure']
    assert (failure['code'] == 'engine_pattern_limit_exceeded') is known_error
    assert 'Untrusted provider' not in json.dumps(failure)
    if known_error:
        assert failure['diagnostics'][0]['max_utf8_bytes'] == recovery.PATTERN_MAX_UTF8_BYTES
        assert '文件路径超过' in failure['summary']


def test_active_bootstrap_job_blocks_recovery(project):
    old = failed(create(project))
    job(old, 'queued')
    assert not recovery.get(old)['eligible']


def test_other_source_generation_is_not_reuse_candidate(project):
    old = failed(create(project)); target = ready(create(project))
    with db.connect() as con:
        ctx = json.loads(con.execute('SELECT context_json FROM bootstrap_contexts WHERE task_id=?', (target,)).fetchone()[0])
        ctx['workspace_source']['instance']['generation'] = 'other-generation'
        con.execute('UPDATE bootstrap_contexts SET context_json=?,context_hash=? WHERE task_id=?',
                    (json.dumps(ctx), scene.digest(ctx), target))
    assert recovery.get(old)['candidate'] is None
def test_real_tool_submission_summary_keeps_recovery_link_when_ready(project):
    from agentscope_app.bootstrap import tools
    old = failed(create(project)); before = immutable(old)
    target = recovery.prepare(old, body(old))['target']['task_id']
    with db.connect() as con:
        state = controller.load(con, target)
        job_id = state['startup_job']
        con.execute("UPDATE history_jobs SET status='running' WHERE id=?", (job_id,))
    token = tools.issue(target, job_id)
    def invoke(tool, args):
        return tools.invoke(target, job_id, tool, args, token)
    ctx = invoke('get_task_context', {})
    sources = invoke('list_policy_sources', {})['sources']
    for source in sources:
        invoke('read_policy_source', {'source_id': source['id']})
    invoke('search_historical_policies', {'query': 'preserve tests'})
    invoke('get_enforcement_capabilities', {})
    validated = invoke('validate_policy_draft', {'draft': {
        'context_hash': ctx['context_hash'], 'summary': 'Explain project safely',
        'no_op': True, 'guidance': ['Preserve tests.']}})
    assert validated['valid'] and validated['compile_state'] == 'compiled'
    submitted = invoke('submit_task_policy_proposal', {'proposal_hash': validated['proposal_hash']})
    assert submitted['state'] == 'validated'
    tools.revoke(job_id)
    with db.connect() as con:
        con.execute("UPDATE history_jobs SET status='completed' WHERE id=?", (job_id,))
        stored = con.execute('SELECT * FROM bootstrap_proposals WHERE id=?', (submitted['id'],)).fetchone()
        summary = json.loads(stored['validation_json'])
        assert 'proposal' not in summary
        assert summary['proposal_hash'] == scene.digest(json.loads(stored['proposal_json']))
    controller.complete_start(target)
    view = recovery.get(old)
    assert view['link']['task_id'] == target
    assert view['link']['proposal_hash'] == submitted['proposal_hash']
    assert view['link_status'] == 'awaiting_review'
    assert view['candidate']['task_id'] == target
    assert recovery.prepare(old, body(old, 'reuse', target))['target']['task_id'] == target
    assert immutable(old) == before
    assert_zero_authority(old, target)


@pytest.mark.parametrize('tamper', ['valid', 'state', 'compile_state', 'proposal_hash', 'embedded_proposal'])
def test_validation_summary_or_embedded_body_mismatch_rejects_ready_candidate(project, tamper):
    old = failed(create(project)); target = ready(create(project))
    request = body(old, 'reuse', target)
    with db.connect() as con:
        row = con.execute('SELECT id,validation_json FROM bootstrap_proposals WHERE task_id=?', (target,)).fetchone()
        summary = json.loads(row['validation_json'])
        if tamper == 'embedded_proposal':
            summary['proposal'] = {'unrelated': 'body'}
        else:
            summary[tamper] = {'valid': False, 'state': 'needs_clarification',
                               'compile_state': 'not_run', 'proposal_hash': '0' * 64}[tamper]
        con.execute('UPDATE bootstrap_proposals SET validation_json=? WHERE id=?', (json.dumps(summary), row['id']))
    assert recovery.get(old)['candidate'] is None
    with pytest.raises(ValueError, match='校验材料不一致'):
        recovery.prepare(old, request)

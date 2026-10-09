"""Generator context receives only the saved, evidence-bound factual review."""
import copy
import json
import uuid

import pytest
from fastapi import HTTPException

from agentscope_app import db
from agentscope_app.bootstrap import scene, tools


@pytest.fixture
def recorded(client, seed_task):
    task_id = uuid.uuid4().hex[:16]
    seed_task(task_id)
    source_id, proposal_id, prior_job = [uuid.uuid4().hex for _ in range(3)]
    prompt = 'test task'
    ctx = {'task_id': task_id, 'raw_prompt_hash': scene.digest(prompt), 'workspace': '/tmp/review-context',
           'assets': [], 'declared_constraints': [], 'accepted_task_constraints': ['Preserve existing files.'],
           'platform_constraints': 'Do not grant new scope.', 'base_settings': {'allow_task_output': False}}
    context_hash = scene.digest(ctx)
    proposal = {'context_hash': context_hash, 'draft': {'atoms': [], 'guidance': ['A prior generated factual claim.']}}
    proposal_hash = scene.digest(proposal)
    with db.connect() as con:
        con.execute('INSERT INTO bootstrap_contexts VALUES(?,?,?,?,?)',
                    (task_id, 'test-review', json.dumps(ctx), context_hash, db.now()))
        con.execute('INSERT INTO bootstrap_sources VALUES(?,?,?,?,?,?,?)',
                    (source_id, task_id, 'task', '', prompt, scene.digest(prompt), '{}'))
        con.execute('INSERT INTO history_jobs(id,kind,status,input_json,created_at) VALUES(?,?,?,?,?)',
                    (prior_job, 'task_bootstrap', 'completed', json.dumps({'task_id': task_id}), db.now()))
        con.execute('INSERT INTO bootstrap_proposals VALUES(?,?,?,?,?,?,?,?,?)',
                    (proposal_id, task_id, prior_job, context_hash, proposal_hash, json.dumps(proposal),
                     json.dumps({'valid': True, 'state': 'validated', 'compile_state': 'compiled',
                                 'proposal_hash': proposal_hash}), 'validated', db.now()))
    return {'task_id': task_id, 'source_id': source_id, 'context': ctx, 'context_hash': context_hash,
            'proposal_id': proposal_id, 'proposal_hash': proposal_hash, 'prior_job': prior_job,
            'feedback': {'proposal_id': proposal_id, 'proposal_hash': proposal_hash, 'context_hash': context_hash,
                         'reason': 'These registered files were not read; do not describe them as unreadable.',
                         'authority': 'control_plane_factual_review'}}


def job(recorded, feedback=None, *, status='running', kind='task_bootstrap', task_id=None, job_id=None):
    ident = job_id or uuid.uuid4().hex
    payload = {'task_id': task_id or recorded['task_id'], 'job_id': ident}
    if feedback is not None:
        payload['review_feedback'] = feedback
    with db.connect() as con:
        con.execute('INSERT INTO history_jobs(id,kind,status,input_json,created_at,retry_of) VALUES(?,?,?,?,?,?)',
                    (ident, kind, status, json.dumps(payload), db.now(), recorded['prior_job']))
    token = tools.issue(recorded['task_id'], ident)
    return ident, token


def get(recorded, current, args=None):
    return tools.invoke(recorded['task_id'], current[0], 'get_task_context', args or {}, current[1])


def frozen(recorded):
    with db.connect() as con:
        return {'context': tuple(con.execute('SELECT * FROM bootstrap_contexts WHERE task_id=?',
                                            (recorded['task_id'],)).fetchone()),
                'sources': [tuple(r) for r in con.execute('SELECT * FROM bootstrap_sources WHERE task_id=? ORDER BY id',
                                                          (recorded['task_id'],))]}


def test_without_feedback_exact_context_response_is_unchanged(recorded):
    expected = {**recorded['context'], 'context_hash': recorded['context_hash'],
                'task_description': 'test task', 'task_description_source_id': recorded['source_id']}
    assert get(recorded, job(recorded)) == expected


def test_saved_feedback_is_projected_as_non_authorizing_review_without_changing_context(recorded):
    before = frozen(recorded)
    result = get(recorded, job(recorded, recorded['feedback']))
    assert result['policy_review_feedback'] == {
        **recorded['feedback'], 'role': 'factual_generation_review', 'scope_authorization': False}
    assert result['context_hash'] == recorded['context_hash']
    assert result['accepted_task_constraints'] == recorded['context']['accepted_task_constraints']
    assert result['declared_constraints'] == recorded['context']['declared_constraints']
    assert result['platform_constraints'] == recorded['context']['platform_constraints']
    assert frozen(recorded) == before
    with db.connect() as con:
        assert not con.execute('SELECT 1 FROM policy_versions WHERE task_id=?', (recorded['task_id'],)).fetchone()
        assert not con.execute('SELECT 1 FROM task_credentials WHERE task_id=?', (recorded['task_id'],)).fetchone()


def test_other_job_feedback_is_not_borrowed_and_terminated_job_cannot_invoke(recorded):
    old = job(recorded, recorded['feedback'], status='completed')
    current = job(recorded)
    assert 'policy_review_feedback' not in get(recorded, current)
    with pytest.raises(HTTPException) as error:
        get(recorded, old)
    assert error.value.status_code == 409


@pytest.mark.parametrize('mismatch', ['job_task', 'job_kind', 'embedded_job_id', 'foreign_proposal',
                                      'context_hash', 'proposal_hash', 'row_context', 'body_hash', 'body_context'])
def test_job_proposal_and_current_context_bindings_are_exact(recorded, seed_task, mismatch):
    feedback = copy.deepcopy(recorded['feedback'])
    kwargs = {}
    if mismatch == 'job_task':
        kwargs['task_id'] = 'different-task'
    elif mismatch == 'job_kind':
        kwargs['kind'] = 'collect'
    elif mismatch == 'foreign_proposal':
        foreign = uuid.uuid4().hex[:16]
        seed_task(foreign)
        with db.connect() as con:
            con.execute('UPDATE bootstrap_proposals SET task_id=? WHERE id=?', (foreign, recorded['proposal_id']))
    elif mismatch in ('context_hash', 'proposal_hash'):
        feedback[mismatch] = '0' * 64
    elif mismatch == 'row_context':
        with db.connect() as con:
            con.execute('UPDATE bootstrap_proposals SET context_hash=? WHERE id=?',
                        ('0' * 64, recorded['proposal_id']))
    elif mismatch == 'body_hash':
        with db.connect() as con:
            con.execute("UPDATE bootstrap_proposals SET proposal_json='{}' WHERE id=?", (recorded['proposal_id'],))
    elif mismatch == 'body_context':
        with db.connect() as con:
            value = {'context_hash': '0' * 64}
            feedback['proposal_hash'] = scene.digest(value)
            con.execute('UPDATE bootstrap_proposals SET proposal_json=?,content_hash=? WHERE id=?',
                        (json.dumps(value), feedback['proposal_hash'], recorded['proposal_id']))
    current = job(recorded, feedback, **kwargs)
    if mismatch == 'embedded_job_id':
        with db.connect() as con:
            payload = {'task_id': recorded['task_id'], 'job_id': 'another-job', 'review_feedback': feedback}
            con.execute('UPDATE history_jobs SET input_json=? WHERE id=?', (json.dumps(payload), current[0]))
    if mismatch == 'job_kind':
        with pytest.raises(HTTPException) as error:
            get(recorded, current)
        assert error.value.status_code == 409
        with pytest.raises(ValueError, match='绑定无效或已过期'):
            tools.execute(recorded['task_id'], current[0], 'get_task_context', {})
    else:
        result = get(recorded, current)
        assert result['valid'] is False
        assert 'policy_review_feedback' not in result
        assert '绑定无效或已过期' in result['diagnostic']


@pytest.mark.parametrize('reason', ['', '  ', 'xy', 'x' * 2001, None, ['Not a string']])
def test_review_reason_must_be_nonempty_bounded_text(recorded, reason):
    feedback = {**recorded['feedback'], 'reason': reason}
    result = get(recorded, job(recorded, feedback))
    assert result['valid'] is False and 'policy_review_feedback' not in result


@pytest.mark.parametrize('mutation', ['authority', 'extra_authority', 'missing_hash'])
def test_review_cannot_claim_task_platform_or_scope_authority(recorded, mutation):
    feedback = dict(recorded['feedback'])
    if mutation == 'authority':
        feedback['authority'] = 'platform'
    elif mutation == 'extra_authority':
        feedback['allow_task_output'] = True
    else:
        feedback.pop('proposal_hash')
    result = get(recorded, job(recorded, feedback))
    assert not result['valid'] and 'policy_review_feedback' not in result


def test_caller_cannot_supply_or_override_review_feedback(recorded):
    current = job(recorded)
    before = frozen(recorded)
    result = get(recorded, current, {'review_feedback': recorded['feedback']})
    assert result['valid'] is False and 'tool parameters must match schema exactly' in result['diagnostic']
    assert frozen(recorded) == before

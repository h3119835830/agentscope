"""Server workflow diagnostics; no provider, service, or real task execution."""
import json
import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException
from agentscope_app import db
from agentscope_app.bootstrap import tools, validation
from agentscope_app.bootstrap.runner import workflow_status
from agentscope_app.bootstrap.scene import digest
from agentscope_app.policy_ir import pattern


def event(job, tool, output, args=None):
    with db.connect() as con:
        con.execute("INSERT INTO bootstrap_tool_events VALUES(?,?,?,?,?,?)",
                    (uuid.uuid4().hex, job, tool, json.dumps(args or {}), json.dumps(output), db.now()))


@pytest.fixture
def workflow(client, seed_task, monkeypatch):
    task = 'rpc-' + uuid.uuid4().hex
    job = uuid.uuid4().hex
    seed_task(task)
    with tempfile.TemporaryDirectory(prefix='', dir='/tmp/a') as directory:
        root = Path(directory)
        long = root / ('深' * 24 + '.py')
        short = root / 'test.py'
        for path in (long, short): path.write_text('test asset')
        ctx = {'context_hash': 'c' * 64, 'scenario_hash': 's' * 64,
               'base_settings': {}, 'declared_constraints': []}
        monkeypatch.setattr(validation, 'context', lambda _: ctx)
        with db.connect() as con:
            con.execute('UPDATE tasks SET workspace=?,output_dir=? WHERE id=?', (str(root), str(root.parent / 'o'), task))
            con.execute("INSERT INTO history_jobs(id,kind,status,input_json,created_at) VALUES(?,?,?,?,?)",
                        (job, 'task_bootstrap', 'running', json.dumps({'task_id': task}), db.now()))
            for ident, role, path, text in [('authority', 'platform', 'platform', 'Preserve original tests'),
                                            ('long', 'asset', str(long), 'test asset'),
                                            ('short', 'asset', str(short), 'test asset')]:
                con.execute('INSERT INTO bootstrap_sources VALUES(?,?,?,?,?,?,?)',
                            (task + ident, task, role, path, text, digest(text), '{}'))
        for tool in ('get_task_context', 'list_policy_sources', 'get_enforcement_capabilities', 'search_historical_policies'):
            event(job, tool, {})
        for ident in ('authority', 'long', 'short'):
            event(job, 'read_policy_source', {'content_hash': digest('read')}, {'source_id': task + ident})
        token = tools.issue(task, job)
        def draft(ident):
            return {'context_hash': ctx['context_hash'], 'summary': 'Preserve exact registered test',
                    'atoms': [{'decision': 'new_candidate', 'statement': 'Preserve the original test',
                               'reason': 'Explicit platform authority', 'operations': ['write', 'unlink'],
                               'paths': [str(long if ident == 'long' else short)],
                               'evidence_ids': [task + 'authority', task + ident]}]}
        yield task, job, token, draft


def test_capabilities_publish_the_existing_ir_abi_without_weakening_it():
    limits = validation.CAPABILITIES['pattern_limits']
    assert limits['max_utf8_bytes'] == 64 and limits['canonical_absolute_paths']
    assert set(limits['disallowed_characters']) == {'\n', '\r', '\0', '"', '\\'}
    assert pattern('/' + 'a' * 63, file=True)
    with pytest.raises(ValueError): pattern('/' + 'a' * 64, file=True)
    with pytest.raises(ValueError): pattern('/' + '深' * 22, file=True)


def test_overlong_target_has_structured_utf8_diagnostic_and_cannot_submit(workflow):
    task, job, token, draft = workflow
    rejected = tools.invoke(task, job, 'validate_policy_draft', {'draft': draft('long')}, token)
    assert rejected['valid'] is False
    details = rejected['diagnostic_details']
    assert details['code'] == 'engine_pattern_limit_exceeded'
    assert details['max_utf8_bytes'] == 64 and details['read_tool'] == 'get_task_context'
    assert details['targets'] == [{'path': draft('long')['atoms'][0]['paths'][0],
                                  'utf8_bytes': len(draft('long')['atoms'][0]['paths'][0].encode('utf-8'))}]
    assert '不能扩大保护范围' in rejected['diagnostic']
    submitted = tools.invoke(task, job, 'submit_task_policy_proposal', {'proposal_hash': 'invented'}, token)
    assert submitted['valid'] is False
    with db.connect() as con:
        assert not con.execute('SELECT 1 FROM bootstrap_proposals WHERE job_id=?', (job,)).fetchone()


def test_budget_exhaustion_preserves_business_error_not_rpc_lifecycle(workflow):
    task, job, token, draft = workflow
    for _ in range(3):
        rejected = tools.invoke(task, job, 'validate_policy_draft', {'draft': draft('long')}, token)
    event(job, 'rpc_lifecycle', {'kind': 'tool_end', 'diagnostic': 'PRIVATE PROVIDER OUTPUT'})
    state = workflow_status(job)
    assert not state['submitted'] and not state['validated_candidate_available']
    assert state['remaining_validation_attempts'] == 0
    assert state['last_tool'] == 'validate_policy_draft'
    assert state['last_diagnostic'] == rejected['diagnostic']
    assert rejected['diagnostic'] in state['workflow_error']
    assert state['diagnostic_details'] == rejected['diagnostic_details']
    assert 'PRIVATE' not in json.dumps(state)
    event(job, 'get_enforcement_capabilities', validation.CAPABILITIES)
    state = workflow_status(job)
    assert state['last_tool'] == 'get_enforcement_capabilities'
    assert state['last_diagnostic'] == rejected['diagnostic']
    with pytest.raises(HTTPException) as error:
        tools.invoke(task, job, 'validate_policy_draft', {'draft': draft('long')}, token)
    assert error.value.status_code == 429


def test_zero_repairs_with_saved_candidate_still_allows_exact_submission(workflow, monkeypatch):
    from agentscope_app import main
    task, job, token, draft = workflow
    monkeypatch.setattr(main, 'compile_policy', lambda *args: ('compiled', {}, ''))
    checked = tools.invoke(task, job, 'validate_policy_draft', {'draft': draft('short')}, token)
    assert checked['valid']
    for _ in range(2): tools.invoke(task, job, 'validate_policy_draft', {'draft': draft('long')}, token)
    state = workflow_status(job)
    assert state['remaining_validation_attempts'] == 0 and state['validated_candidate_available']
    assert 'workflow_error' not in state
    submitted = tools.invoke(task, job, 'submit_task_policy_proposal', {'proposal_hash': checked['proposal_hash']}, token)
    assert submitted['state'] == 'validated'
    assert workflow_status(job)['submitted']


def test_workflow_state_scoped_to_its_job_and_public_diagnostic_fields(workflow):
    task, job, token, draft = workflow
    with db.connect() as con:
        con.execute('INSERT INTO bootstrap_validation_budget VALUES(?,3)', (job,))
    event(job, 'validate_policy_draft', {'diagnostic': 'Exact target too long', 'diagnostic_details': {
        'code': 'engine_pattern_limit_exceeded', 'max_utf8_bytes': 999, 'secret': 'PRIVATE',
        'targets': [{'path': '/registered/test.py', 'utf8_bytes': 90, 'raw_text': 'PRIVATE'}]}})
    state = workflow_status(job)
    assert 'PRIVATE' not in json.dumps(state)
    assert state['diagnostic_details']['max_utf8_bytes'] == 64
    other = workflow_status('unrelated-job')
    assert other['cancelled'] and other['remaining_validation_attempts'] == 3
    assert other['last_tool'] is None and 'workflow_error' not in other

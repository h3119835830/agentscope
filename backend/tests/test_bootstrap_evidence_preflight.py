"""Exercise evidence preflight through real generator tool receipts, without Pi."""
import grp
import json
import os
import tempfile
import uuid
from pathlib import Path

import pytest

from agentscope_app import db
from agentscope_app.bootstrap import scene, tools
from agentscope_app.workspaces import registry


@pytest.fixture
def flow(client, monkeypatch):
    import agentscope_app.main as main
    monkeypatch.setattr(main, 'compile_policy', lambda *a, **k: ('compiled', {'ok': True}, ''))
    monkeypatch.setenv('AGENTSCOPE_TASK_GROUP', grp.getgrgid(os.getgid()).gr_name)
    monkeypatch.setattr(registry, 'effective_dsh', lambda: {'model': 'isolated-test'})
    with tempfile.TemporaryDirectory(prefix='e', dir='/tmp/a') as temporary:
        monkeypatch.setattr(registry, 'WORKSPACE_ROOT', Path(temporary))
        ws = registry.create_workspace('Evidence preflight source')
        root = Path(ws['path'])
        (root / 'a.py').write_text('a = 1\n')
        (root / 'b.py').write_text('b = 2\n')
        (root / 'empty.py').write_bytes(b'')
        (root / 'nested').mkdir()
        (root / 'nested/c.py').write_text('c = 3\n')
        result = registry.create_task(ws['id'], 'Preserve source', 'Preserve the existing source files.',
                                      registry.inventory(ws['id'])['manifest_hash'])
        task_id, job_id = result['id'], uuid.uuid4().hex
        with db.connect() as con:
            con.execute('INSERT INTO history_jobs(id,kind,status,input_json,created_at) VALUES(?,?,?,?,?)',
                        (job_id, 'task_bootstrap', 'running', json.dumps({'task_id': task_id}), db.now()))
        token = tools.issue(task_id, job_id)
        def invoke(tool, args=None):
            return tools.invoke(task_id, job_id, tool, args or {}, token)
        context = invoke('get_task_context')
        sources = invoke('list_policy_sources')['sources']
        for source in sources:
            if source['role'] in ('task', 'platform', 'environment', 'dsh_config'):
                invoke('read_policy_source', {'source_id': source['id']})
        invoke('search_historical_policies', {'query': 'preserve source'})
        invoke('get_enforcement_capabilities')
        yield {'task_id': task_id, 'job_id': job_id, 'invoke': invoke, 'source_workspace_id': ws['id'], 'context': context,
               'sources': sources, 'workspace': Path(context['workspace']),
               'authority': next(source['id'] for source in sources if source['role'] == 'task'),
               'assets': {str(Path(source['path']).relative_to(context['workspace'])): source
                          for source in sources if source['role'] == 'asset'}}
        tools.revoke(job_id)


def draft(flow, bindings):
    return {'context_hash': flow['context']['context_hash'], 'summary': 'Preserve the registered project',
            'atoms': [{'decision': 'new_candidate', 'statement': 'Preserve existing source files.',
                       'operations': ['write', 'unlink'], 'paths': paths, 'evidence_ids': evidence,
                       'reason': 'Explicit task evidence requires preserving these existing objects.'}
                      for paths, evidence in bindings], 'guidance': [], 'no_op': False}


def validate(flow, value):
    return flow['invoke']('validate_policy_draft', {'draft': value})


def budget(flow):
    with db.connect() as con:
        row = con.execute('SELECT calls FROM bootstrap_validation_budget WHERE job_id=?', (flow['job_id'],)).fetchone()
        return row[0] if row else 0


def read(flow, *names):
    for name in names:
        result = flow['invoke']('read_policy_source', {'source_id': flow['assets'][name]['id']})
        assert result['content_hash'] == flow['assets'][name]['content_hash']


def test_all_atoms_targets_report_read_and_cite_gaps_before_budget_then_validate(flow):
    read(flow, 'a.py', 'empty.py')
    paths = {name: asset['path'] for name, asset in flow['assets'].items()}
    value = draft(flow, [([paths['a.py'], paths['b.py']], [flow['authority']]),
                         ([paths['nested/c.py'], paths['empty.py']], [flow['authority']])])
    result = validate(flow, value)
    assert result['valid'] is False
    details = result['diagnostic_details']
    assert details['code'] == 'target_evidence_incomplete'
    assert len(details['issues']) == 4
    expected = {'a.py': 'update_atom_evidence_ids', 'b.py': 'read_then_cite',
                'empty.py': 'update_atom_evidence_ids', 'nested/c.py': 'read_then_cite'}
    for issue in details['issues']:
        name = str(Path(issue['target']).relative_to(flow['workspace']))
        assert issue['atom_index'] == (0 if name in ('a.py', 'b.py') else 1)
        assert issue['required_action'] == expected[name]
        assert issue['candidate_sources'] == [{'source_id': flow['assets'][name]['id'],
                  'read_receipt_verified': name in ('a.py', 'empty.py')}]
    assert budget(flow) == 0
    # Structured output survives invoke persistence without diagnostic truncation.
    with db.connect() as con:
        saved = json.loads(con.execute("SELECT output_json FROM bootstrap_tool_events WHERE job_id=? AND tool='validate_policy_draft'",
                                       (flow['job_id'],)).fetchone()[0])
        assert saved['diagnostic_details'] == details
        assert not con.execute('SELECT 1 FROM bootstrap_validations WHERE job_id=?', (flow['job_id'],)).fetchone()
    read(flow, 'b.py', 'nested/c.py')
    for atom in value['atoms']:
        atom['evidence_ids'] += [asset['id'] for asset in flow['assets'].values() if asset['path'] in atom['paths']]
    corrected = validate(flow, value)
    assert corrected['valid'] and corrected['compile_state'] == 'compiled'
    assert budget(flow) == 1
    with db.connect() as con:
        assert not con.execute('SELECT 1 FROM policy_versions WHERE task_id=?', (flow['task_id'],)).fetchone()
        assert not con.execute('SELECT 1 FROM task_credentials WHERE task_id=?', (flow['task_id'],)).fetchone()


def test_cited_but_unread_asset_reports_structured_read_gap(flow):
    asset = flow['assets']['a.py']
    value = draft(flow, [([asset['path']], [flow['authority'], asset['id']])])
    result = validate(flow, value)
    assert result['diagnostic_details']['issues'] == [{
        'atom_index': 0, 'target': asset['path'],
        'candidate_sources': [{'source_id': asset['id'], 'read_receipt_verified': False}],
        'required_action': 'read_then_cite'}]
    assert budget(flow) == 0
    read(flow, 'a.py')
    assert validate(flow, value)['valid']
    assert budget(flow) == 1


@pytest.mark.parametrize('suffix', ['', '/**'])
def test_legal_directory_suggests_only_registered_descendants(flow, suffix):
    target = str(flow['workspace'] / 'nested') + suffix
    result = validate(flow, draft(flow, [([target], [flow['authority']])]))
    issue = result['diagnostic_details']['issues'][0]
    assert issue['candidate_sources'] == [{'source_id': flow['assets']['nested/c.py']['id'],
                                          'read_receipt_verified': False}]
    assert budget(flow) == 0
    read(flow, 'nested/c.py')
    assert validate(flow, draft(flow, [([target], [flow['authority'], flow['assets']['nested/c.py']['id']])]))['valid']


@pytest.mark.parametrize('kind', ['unknown', 'cross_task', 'noncanonical', 'symlink'])
def test_unregistered_cross_task_or_noncanonical_targets_never_suggest_takeover(flow, kind):
    asset = flow['assets']['a.py']
    if kind == 'unknown':
        target = str(flow['workspace'] / 'unregistered.py')
        Path(target).write_text('unregistered')
    elif kind == 'cross_task':
        foreign = registry.create_task(flow['source_workspace_id'], 'Other task', 'Preserve other task source.',
                                       registry.inventory(flow['source_workspace_id'])['manifest_hash'])
        with db.connect() as con:
            target = con.execute("SELECT path FROM bootstrap_sources WHERE task_id=? AND role='asset' ORDER BY path LIMIT 1",
                                 (foreign['id'],)).fetchone()[0]
    elif kind == 'noncanonical':
        target = str(flow['workspace']) + '/nested/../a.py'
    else:
        target = str(flow['workspace'] / 'link.py')
        Path(target).symlink_to(asset['path'])
    result = validate(flow, draft(flow, [([target], [flow['authority']])]))
    assert result['valid'] is False
    assert result.get('diagnostic_details', {}).get('code') != 'target_evidence_incomplete'
    assert budget(flow) == 1


def test_foreign_source_id_cannot_bind_same_named_target(flow):
    asset = flow['assets']['a.py']
    fake = uuid.uuid4().hex
    # Unknown IDs remain rejected by the original global receipt guard.
    result = validate(flow, draft(flow, [([asset['path']], [flow['authority'], fake])]))
    issue = result['diagnostic_details']['issues'][0]
    assert all(item['source_id'] != fake for item in issue['candidate_sources'])
    read(flow, 'a.py')
    result = validate(flow, draft(flow, [([asset['path']], [flow['authority'], asset['id'], fake])]))
    assert result['valid'] is False and result['diagnostic'].startswith('Unread referenced source IDs')
    assert budget(flow) == 0


def test_correct_target_wiring_still_requires_authority_and_content_integrity(flow):
    read(flow, 'a.py')
    asset = flow['assets']['a.py']
    without_authority = validate(flow, draft(flow, [([asset['path']], [asset['id']])]))
    assert not without_authority['valid'] and 'lacks task/platform authority' in without_authority['diagnostic']
    assert budget(flow) == 1
    with db.connect() as con:
        con.execute("UPDATE bootstrap_sources SET content_hash=? WHERE id=?", ('0' * 64, asset['id']))
    corrupt = validate(flow, draft(flow, [([asset['path']], [flow['authority'], asset['id']])]))
    assert not corrupt['valid'] and 'content hash mismatch' in corrupt['diagnostic']
    assert corrupt.get('diagnostic_details', {}).get('code') != 'target_evidence_incomplete'
    assert budget(flow) == 2


def test_forged_read_hash_is_not_verified_and_never_bypasses_read_requirement(flow):
    asset = flow['assets']['a.py']
    with db.connect() as con:
        con.execute('INSERT INTO bootstrap_tool_events VALUES(?,?,?,?,?,?)',
                    (uuid.uuid4().hex, flow['job_id'], 'read_policy_source', json.dumps({'source_id': asset['id']}),
                     json.dumps({'content_hash': '0' * 64}), db.now()))
    result = validate(flow, draft(flow, [([asset['path']], [flow['authority'], asset['id']])]))
    assert result['diagnostic_details']['issues'][0]['candidate_sources'][0]['read_receipt_verified'] is False
    assert budget(flow) == 0

def test_structured_issues_are_not_cut_at_diagnostic_string_limit(flow):
    paths = [asset['path'] for asset in flow['assets'].values()]
    result = validate(flow, draft(flow, [(paths, [flow['authority']])] * 20))
    issues = result['diagnostic_details']['issues']
    assert len(issues) == 80
    assert len(json.dumps(result['diagnostic_details'])) > 2000
    assert {issue['atom_index'] for issue in issues} == set(range(20))
    assert budget(flow) == 0
    with db.connect() as con:
        persisted = json.loads(con.execute("SELECT output_json FROM bootstrap_tool_events WHERE job_id=? AND tool='validate_policy_draft'",
                                           (flow['job_id'],)).fetchone()[0])
        assert persisted['diagnostic_details']['issues'] == issues


def test_preflight_does_not_relax_declared_existing_object_scope(flow):
    read(flow, 'nested/c.py')
    asset = flow['assets']['nested/c.py']
    with db.connect() as con:
        ctx = json.loads(con.execute('SELECT context_json FROM bootstrap_contexts WHERE task_id=?', (flow['task_id'],)).fetchone()[0])
        task_source = con.execute('SELECT text,content_hash FROM bootstrap_sources WHERE id=?',
                                  (flow['authority'],)).fetchone()
        ctx['declared_constraints'] = [{
            'id': 'exact-existing-object', 'authority_role': 'task', 'authority_hash': task_source['content_hash'],
            'source_quote': task_source['text'], 'intent': 'os_block',
            'object_scope': 'registered_existing_files', 'targets': [asset['path']]}]
        con.execute('UPDATE bootstrap_contexts SET context_json=?,context_hash=? WHERE task_id=?',
                    (json.dumps(ctx), scene.digest(ctx), flow['task_id']))
    flow['context'] = scene.context(flow['task_id'])
    broad = str(flow['workspace'] / 'nested') + '/**'
    result = validate(flow, draft(flow, [([broad], [flow['authority'], asset['id']])]))
    assert not result['valid'] and 'overbroad registered object collection' in result['diagnostic']
    assert result.get('diagnostic_details', {}).get('code') != 'target_evidence_incomplete'
    assert budget(flow) == 1

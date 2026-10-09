"""Literal bootstrap coverage agrees with emitted DSL; no model or loader."""
import copy
import grp
import os
import re
import tempfile
from pathlib import Path

import pytest

from agentscope_app import db
from agentscope_app.bootstrap import scene, validation
from agentscope_app.policy_ir import PATTERN_MAX_UTF8_BYTES
from agentscope_app.workspaces import registry


@pytest.fixture
def flow(client, monkeypatch):
    monkeypatch.setenv('AGENTSCOPE_TASK_GROUP', grp.getgrgid(os.getgid()).gr_name)
    monkeypatch.setattr(registry, 'effective_dsh', lambda: {'model': 'isolated-path-matching-test'})
    with tempfile.TemporaryDirectory(prefix='m', dir='/tmp/a') as temporary:
        monkeypatch.setattr(registry, 'WORKSPACE_ROOT', Path(temporary))
        ws = registry.create_workspace('Literal matching source')
        root = Path(ws['path'])
        (root / 'tests/sub').mkdir(parents=True)
        (root / 'tests2').mkdir()
        (root / 'tests/a.py').write_text('a = 1\n')
        (root / 'tests/sub/b.py').write_text('b = 2\n')
        (root / 'tests/empty.py').write_bytes(b'')
        (root / 'tests2/adjacent.py').write_text('adjacent = 3\n')
        result = registry.create_task(ws['id'], 'Literal protection', 'Preserve the selected registered objects.',
                                      registry.inventory(ws['id'])['manifest_hash'])
        ctx = scene.context(result['id'])
        with db.connect() as con:
            sources = [dict(row) for row in con.execute('SELECT * FROM bootstrap_sources WHERE task_id=?', (result['id'],))]
        yield {'id': result['id'], 'source_workspace_id': ws['id'], 'ctx': ctx, 'workspace': Path(ctx['workspace']), 'sources': sources,
               'authority': next(s['id'] for s in sources if s['role'] == 'task'),
               'assets': [s for s in sources if s['role'] == 'asset']}


def draft(flow, paths, operations=None, statement='Protect the selected directory and all descendants.'):
    return {'context_hash': flow['ctx']['context_hash'], 'summary': 'Literal path coverage',
            'atoms': [{'decision': 'new_candidate', 'statement': statement,
                       'operations': operations or ['write', 'unlink'], 'paths': paths,
                       'evidence_ids': [flow['authority']] + [s['id'] for s in flow['assets']],
                       'reason': 'Current task evidence supports these explicitly selected objects.'}],
            'guidance': [], 'no_op': False}


def checked(flow, paths, operations=None):
    result = validation.validate(flow['id'], draft(flow, paths, operations), compile_bundle=False)
    assert result['valid'] and result['compile_state'] == 'not_run'
    return result


def actual_clauses(result):
    return re.findall(r'(write|unlink) file "([^"]+)"', result['proposal']['raw_actplane_dsl'])


def test_bare_directory_is_exact_node_and_does_not_claim_descendant_files(flow):
    target = str(flow['workspace'] / 'tests')
    result = checked(flow, [target])
    coverage = result['registered_asset_coverage']
    assert coverage['scope'] == 'draft_atoms_only'
    assert coverage['runtime_enforcement_proof'] is False
    assert coverage['atoms'][0]['targets'] == [{
        'pattern': target, 'matching': 'exact', 'includes_base_node': True,
        'matched_asset_count': 0, 'matched_assets': []}]
    assert actual_clauses(result) == [('write', target), ('unlink', target)]
    assert target + '/**' not in result['proposal']['raw_actplane_dsl']
    assert result['proposal']['draft']['atoms'][0]['statement'].endswith('all descendants.')


def test_descendant_pattern_matches_registered_descendants_not_adjacent_prefix(flow):
    base = str(flow['workspace'] / 'tests')
    result = checked(flow, [base + '/**'], ['unlink'])
    atom = result['registered_asset_coverage']['atoms'][0]
    target = atom['targets'][0]
    assert atom['operations'] == ['unlink']
    assert target['matching'] == 'descendants' and target['includes_base_node'] is False
    assert target['matched_asset_count'] == 3
    assert {m['path'] for m in target['matched_assets']} == {
        base + '/a.py', base + '/sub/b.py', base + '/empty.py'}
    assert not any('/tests2/' in m['path'] or m['path'] == base for m in target['matched_assets'])
    assert actual_clauses(result) == [('unlink', base + '/**')]


def test_node_and_descendants_need_explicit_two_patterns_and_exact_file_stays_exact(flow):
    base = str(flow['workspace'] / 'tests')
    patterns = [base, base + '/**', base + '/a.py']
    result = checked(flow, patterns, ['write'])
    targets = result['registered_asset_coverage']['atoms'][0]['targets']
    assert [t['matched_asset_count'] for t in targets] == [0, 3, 1]
    assert actual_clauses(result) == [('write', p) for p in patterns]
    assert result['proposal']['draft']['atoms'][0]['paths'] == patterns


def test_coverage_excludes_other_task_and_hash_invalid_uncited_assets(flow):
    other = registry.create_task(
        flow['source_workspace_id'],
        'Other task', 'Preserve other registered objects.',
        registry.inventory(flow['source_workspace_id'])['manifest_hash'])
    base = str(flow['workspace'] / 'tests')
    bad = next(s for s in flow['assets'] if s['path'] == base + '/a.py')
    value = draft(flow, [base + '/**'])
    value['atoms'][0]['evidence_ids'].remove(bad['id'])
    with db.connect() as con:
        con.execute('UPDATE bootstrap_sources SET content_hash=? WHERE id=?', ('0' * 64, bad['id']))
        foreign_ids = {r['id'] for r in con.execute('SELECT id FROM bootstrap_sources WHERE task_id=?', (other['id'],))}
    result = validation.validate(flow['id'], value, compile_bundle=False)
    matches = result['registered_asset_coverage']['atoms'][0]['targets'][0]['matched_assets']
    assert result['valid']
    assert len(matches) == 2 and all(m['source_id'] != bad['id'] and m['source_id'] not in foreign_ids for m in matches)
    assert actual_clauses(result) == [('write', base + '/**'), ('unlink', base + '/**')]


def test_reports_atoms_separately_and_does_not_modify_context_proposal_or_authority(flow):
    base = str(flow['workspace'] / 'tests')
    value = draft(flow, [base], ['write'])
    second = copy.deepcopy(value['atoms'][0])
    second['operations'] = ['unlink'];second['paths'] = [base + '/**']
    value['atoms'].append(second)
    before = copy.deepcopy(scene.context(flow['id']))
    result = validation.validate(flow['id'], value, compile_bundle=False)
    assert [(a['atom_index'], a['operations'], a['targets'][0]['matched_asset_count'])
            for a in result['registered_asset_coverage']['atoms']] == [(0, ['write'], 0), (1, ['unlink'], 3)]
    assert 'registered_asset_coverage' not in result['proposal']
    assert result['proposal_hash'] == scene.digest(result['proposal'])
    assert scene.context(flow['id']) == before
    with db.connect() as con:
        assert not con.execute('SELECT 1 FROM policy_versions WHERE task_id=?', (flow['id'],)).fetchone()
        assert not con.execute('SELECT 1 FROM task_credentials WHERE task_id=?', (flow['id'],)).fetchone()
    invalid = copy.deepcopy(value)
    invalid['atoms'][0]['evidence_ids'].remove(flow['authority'])
    with pytest.raises(ValueError, match='lacks task/platform authority'):
        validation.validate(flow['id'], invalid, compile_bundle=False)


def test_machine_contract_matches_literal_reports_and_shared_limit(flow):
    matching = validation.CAPABILITIES['path_matching']
    assert matching['exact']['includes_base_node'] and not matching['exact']['includes_descendants']
    assert not matching['descendants']['includes_base_node'] and matching['descendants']['includes_descendants']
    assert matching['max_utf8_bytes'] == validation.CAPABILITIES['pattern_limits']['max_utf8_bytes'] == PATTERN_MAX_UTF8_BYTES == 63
    result = checked(flow, [str(flow['workspace'] / 'tests/empty.py')])
    assert result['registered_asset_coverage']['atoms'][0]['targets'][0]['matched_asset_count'] == 1
    assert actual_clauses(result) == [('write', str(flow['workspace'] / 'tests/empty.py')),
                                      ('unlink', str(flow['workspace'] / 'tests/empty.py'))]


def test_coverage_prefix_does_not_include_registered_directory_node():
    # A registered directory node may exist in a future source schema; prefix
    # matching must still exclude it and a similarly named neighboring subtree.
    from agentscope_app.bootstrap.models import Draft
    base = '/s/AA/r/tests'
    value = Draft.model_validate({'context_hash': 'hash', 'summary': 'Literal nodes', 'atoms': [
        {'decision': 'new_candidate', 'statement': 'Preserve selected objects.', 'evidence_ids': ['authority'],
         'operations': ['write'], 'paths': [base, base + '/**'], 'reason': 'Evidence supports these objects.'}]})
    paths = [base, base + '/a', base + '/sub/b', base + '2/other']
    sources = {str(i): {'id': str(i), 'role': 'asset', 'path': p, 'text': 'asset',
                       'content_hash': scene.digest('asset')} for i, p in enumerate(paths)}
    targets = validation.registered_asset_coverage(value, sources)['atoms'][0]['targets']
    assert [m['path'] for m in targets[0]['matched_assets']] == [base]
    assert [m['path'] for m in targets[1]['matched_assets']] == [base + '/a', base + '/sub/b']

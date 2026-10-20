"""Current kernel load, not configured intent or historical binding success."""
import json
import pytest
from agentscope_app import db
from agentscope_app.instances import controller, dsl_policy as dsl, sessions, store
from agentscope_app.instances.session_loaded_policies import build
from test_dsl_configuration import world, document, candidate, ADMIN


@pytest.fixture
def loaded(world, monkeypatch):
    monkeypatch.setattr(sessions, 'native_sessions', lambda row: {
        'sessions': [{'id': 's1', 'name': '已加载策略验收'}], 'executor_shared': True})
    world.run(world.a)
    proposal = candidate(world.a['id'], [{**document(), 'name': '保护配置文件 v1'}])
    dsl.apply(world.a['id'], proposal['id'], proposal['proposal_hash'])
    return world


def projection(world):
    row = controller.detail(world.a['id'])
    return build(row, {'id': 's1'}, row['generation'], dsl.receipt(row['id'], row['generation']))


def test_current_artifact_groups_named_configuration_and_actual_startup_rules(loaded):
    before = store.get(loaded.a['id'])
    view = projection(loaded)
    assert view['state'] == 'verified' and view['coverage_complete']
    named = next(r for r in view['records'] if r['source_kind'] == 'configuration')
    assert named['name'] == '保护配置文件 v1' and named['scope'] == 'agent'
    assert len(named['clauses']) == 3 and named['rule_count'] == 1
    assert all(r['status'] == 'loaded' for r in view['records'])
    assert {r['scope'] for r in view['records']} == {'system', 'agent'}
    assert all(c['clause_hash'] for r in view['records'] for c in r['clauses'])
    assert store.get(loaded.a['id']) == before


@pytest.mark.parametrize('field,value', [
    ('connected', False), ('verified', False), ('generation', 'foreign'),
    ('domain_id', 901), ('pid', 9876), ('gate', 'closed'), ('evidence_age_seconds', 8),
    ('start_ticks', 'new-birth'), ('boot_id', 'reboot'), ('host_id', 'other-host'),
])
def test_stale_or_mismatched_runtime_never_exposes_loaded_rows(loaded, field, value):
    row = controller.detail(loaded.a['id'])
    for identity in ('start_ticks', 'boot_id', 'host_id'):
        row[identity] = row['runtime'][identity] = 'original'
    saved = dsl.receipt(row['id'], row['generation'])
    generation = row['generation']
    row[field] = value
    view = build(row, {'id': 's1'}, generation, saved)
    assert not view['records'] and not view['coverage_complete']


@pytest.mark.parametrize('part,field,value', [
    ('receipt', 'bundle_hash', 'other'), ('receipt', 'instance_id', 'foreign'),
    ('receipt', 'generation', 'foreign'), ('artifact', 'loaded', False),
    ('artifact', 'bundle_hash', 'other'), ('artifact', 'dsl_hash', 'other'),
    ('binding', 'pid', 999), ('binding', 'domain_id', 999), ('binding', 'generation', 'other'),
])
def test_receipt_mismatch_does_not_become_current_kernel_evidence(loaded, part, field, value):
    row = controller.detail(loaded.a['id'])
    saved = dsl.receipt(row['id'], row['generation'])
    target = saved if part == 'receipt' else saved['artifact'] if part == 'artifact' else saved['artifact']['binding']
    target[field] = value
    assert not build(row, {'id': 's1'}, row['generation'], saved)['records']


def test_candidate_and_desired_rename_never_replace_loaded_name(loaded):
    candidate(loaded.a['id'], [{**document(), 'name': '尚未批准的 v2'}])
    assert '尚未批准的 v2' not in json.dumps(projection(loaded), ensure_ascii=False)
    # A desired-state update is not a kernel-load receipt. This intentionally
    # makes controller.active false while the old observed load remains verified.
    with db.connect() as con:
        con.execute('UPDATE instance_dsl_scopes SET documents_json=? WHERE scope_id=?',
                    (json.dumps([{**document(), 'name': '新配置 v3'}]), loaded.a['id']))
    assert not controller.detail(loaded.a['id'])['active']
    view = projection(loaded)
    assert view['state'] == 'verified'
    assert next(r for r in view['records'] if r['source_kind'] == 'configuration')['name'] == '保护配置文件 v1'


def test_partial_mappings_are_not_an_empty_complete_list(loaded):
    row = controller.detail(loaded.a['id'])
    saved = dsl.receipt(row['id'], row['generation'])
    saved['artifact']['documents'][0]['rules'] = []
    view = build(row, {'id': 's1'}, row['generation'], saved)
    assert view['state'] == 'incomplete' and not view['coverage_complete']
    assert not any('protect' in r['name'] for r in view['records'])


def test_paused_gate_fresh_kernel_load_is_not_confused_with_execution_permission(loaded):
    row = controller.detail(loaded.a['id'])
    row.update(gate='paused', active=False, supervision='broker-admission-v1',
               execution_status={'gate': 'closed', 'protection_fresh': True})
    saved = dsl.receipt(row['id'], row['generation'])
    assert build(row, {'id': 's1'}, row['generation'], saved)['state'] == 'verified'
    row['execution_status']['protection_fresh'] = False
    assert not build(row, {'id': 's1'}, row['generation'], saved)['records']


def test_no_receipt_historical_observed_and_stopped_have_no_current_rows(loaded):
    row = controller.detail(loaded.a['id'])
    saved = dsl.receipt(row['id'], row['generation'])
    assert not build(row, {'id': 's1'}, row['generation'], None)['records']
    assert build(row, {'id': 's1', 'historical': True}, row['generation'], saved)['state'] == 'historical'
    assert build({**row, 'mode': 'observed'}, {'id': 's1'}, row['generation'], saved)['state'] == 'observed'
    loaded.live.clear()
    assert not projection(loaded)['records']


def test_two_scope_counts_match_api_and_console_without_session_domains(loaded):
    sysdoc = {**document(ident='system-doc'), 'name': '系统保护配置'}
    p = candidate('system', [sysdoc])
    dsl.apply('system', p['id'], p['proposal_hash'])
    root = '/api/agent-instances/' + loaded.a['id'] + '/sessions/s1'
    raw = loaded.client.get(root + '/policies', headers=ADMIN).json()['loaded_policies']
    console = loaded.client.get('/api/console/agents/' + loaded.a['id'] + '/sessions/s1/policies', headers=ADMIN).json()['loaded_policies']
    assert raw == console
    domain = loaded.client.get(root + '/domains', headers=ADMIN).json()
    assert [n['id'] for n in domain['nodes']] == ['system', 'agent']
    assert sum(n['count'] for n in domain['nodes']) == len(raw['records'])
    assert not domain['edges']
    assert next(r for r in raw['records'] if r['name'] == '系统保护配置')['scope'] == 'system'


def test_agent_loaded_policy_endpoint_uses_the_same_verified_current_projection(loaded):
    ident = loaded.a['id']
    agent = loaded.client.get('/api/agent-instances/' + ident + '/loaded-policies', headers=ADMIN).json()
    session = loaded.client.get('/api/agent-instances/' + ident + '/sessions/s1/policies', headers=ADMIN).json()['loaded_policies']
    assert agent == session
    assert agent['state'] == 'verified' and agent['coverage_complete']
    assert {record['scope'] for record in agent['records']} == {'system', 'agent'}
    product = loaded.client.get('/api/console/agents/' + ident + '/loaded-policies', headers=ADMIN).json()
    assert product == agent


@pytest.mark.parametrize('scope', ['workspace', 'session', 'foreign-agent'])
def test_foreign_document_scope_cannot_reappear_as_a_startup_rule(loaded, scope):
    row = controller.detail(loaded.a['id'])
    saved = dsl.receipt(row['id'], row['generation'])
    saved['artifact']['documents'][0]['scope_id'] = scope
    view = build(row, {'id': 's1'}, row['generation'], saved)
    assert not view['coverage_complete']
    assert not any(r.get('document_id') or 'protect' in r['name'] for r in view['records'])

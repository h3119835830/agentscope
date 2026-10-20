import copy
import json

import pytest

from agentscope_app import db
from agentscope_app.instances import dsl_policy, information_flow as flow, sessions
from test_dsl_configuration import ADMIN, world


@pytest.fixture
def evidence(world, monkeypatch):
    ident = world.a['id']
    generation = 'native-flow-generation'
    row = {**world.a, 'generation': generation}
    source_ref = 'rules/native-secret.ifc'
    clause_hash = 'fnv1a64:native-clause'
    sources = [
        {'id': 'source-a', 'version': 1, 'scope_id': ident, 'value': '/fixture/demo-secret.txt'},
        {'id': 'source-b', 'version': 2, 'scope_id': ident, 'value': '/fixture/other-secret.txt'},
    ]
    document = {
        'id': 'config-a', 'scope_id': ident, 'name': '阻止敏感信息外发',
        'original_dsl': 'source doc_SECRET = file "/fixture/demo-secret.txt"\nrule deny_secret_loopback:\n  block connect "127.0.0.1"',
        'effective_dsl': 'source doc_SECRET = file "/fixture/demo-secret.txt"\nsource doc_SECRET = file "/fixture/other-secret.txt"',
        'label_sources': sources,
        'metadata': {},
        'rules': [{
            'rule_name': 'deny_secret_loopback', 'compiled_name': 'compiled-secret-loopback',
            'source_ref': source_ref, 'original_dsl': 'rule deny_secret_loopback:\n  block connect "127.0.0.1"',
            'clauses': [{'effective_clause': '  block connect "127.0.0.1"'}],
            'reason': '隔离测试阻止敏感信息外发',
        }],
    }
    compile_rule = {
        'rule_id': 7, 'name': 'compiled-secret-loopback', 'source_ref': source_ref,
        'clause_hash': clause_hash, 'effect': 'block', 'target_pattern': '127.0.0.1',
    }
    receipt = {
        'generation': generation, 'bundle_hash': 'approved-hash',
        'artifact': {'bundle_hash': 'approved-hash', 'binding': {'domain_id': 41},
                     'compile': {'rules': [compile_rule]}, 'documents': [document]},
    }
    state = {'row': row, 'collection': {'available': True}, 'receipts': {generation: receipt}}

    def context(_ident, _sid, selected=None):
        selected = selected or state['row']['generation']
        return state['row'], {'id': 's1', 'historical': False}, selected, selected == state['row']['generation']

    monkeypatch.setattr(sessions, 'session_context', context)
    monkeypatch.setattr(sessions, 'collect_kernel', lambda _row: state['collection'])
    monkeypatch.setattr(dsl_policy, 'receipt', lambda _ident, selected: state['receipts'].get(selected))

    def event(*, action='block', effect='block', labels=None, provenance=True, tag='0', domain=41,
              source=source_ref, clause=clause_hash, target='127.0.0.1', timestamp='1792475035675378404'):
        value = {
            'schema': 'actplane.violation.v1', 'event': 'taint_violation', 'pid': 100,
            'process_domain_id': domain, 'domain_id': domain, 'rule_id': 7,
            'effect': effect, 'action': action, 'blocked': action == 'block', 'killed': action == 'kill',
            'op': 'connect', 'target': target, 'tool_call_tag': str(tag),
            'matched_label_names': labels or ['doc_SECRET'],
            'matched_label_details': [{'label': name} for name in (labels or ['doc_SECRET'])],
            'provenance_model': {'reported_origin_scope': 'first_available_matched_label',
                                 'causal_chain_scope': 'single_hop_origin', 'full_causal_chain': False},
            'rule': {'name': 'compiled-secret-loopback', 'source_ref': source,
                     'clause_hash': clause, 'effect': effect, 'target_pattern': target},
            'timestamp_unix_ns': timestamp,
        }
        if provenance:
            value['provenance'] = {'label': 'doc_SECRET', 'origin_pid': 100, 'origin_op': 'open',
                                   'origin_target': '/fixture/demo-secret.txt', 'origin_timestamp_ns': '1792475035000000000'}
        return value

    def insert(value, key=None, *, selected=generation, bundle='approved-hash', domain=41):
        source_key = key or f"event-{value.get('timestamp_unix_ns', 'none')}-{value.get('action', 'unknown')}"
        with db.connect() as con:
            con.execute('INSERT OR IGNORE INTO instance_kernel_events(instance_id,generation,source_key,bundle_hash,domain_id,event_json,created_at) VALUES(?,?,?,?,?,?,?)',
                        (ident, selected, source_key, bundle, domain, json.dumps(value), db.now()))
            row_id = con.execute('SELECT id FROM instance_kernel_events WHERE instance_id=? AND generation=? AND source_key=?',
                                 (ident, selected, source_key)).fetchone()['id']
        return row_id

    def tool_start(tag, session='s1', domain=41, call='call-1'):
        with db.connect() as con:
            con.execute('INSERT INTO instance_events(instance_id,generation,kind,session_id,call_id,tool,detail_json,created_at) VALUES(?,?,?,?,?,?,?,?)',
                        (ident, generation, 'tool_start', session, call, 'connect',
                         json.dumps({'kernel_call_tag': tag, 'domain_id': domain}), db.now()))

    return {'ident': ident, 'generation': generation, 'receipt': receipt, 'state': state,
            'event': event, 'insert': insert, 'tool_start': tool_start}


def test_native_match_projects_first_origin_and_configuration_references(evidence):
    evidence['insert'](evidence['event'](), 'native-block')
    data = flow.query(evidence['ident'], 's1', view='shared_domain')
    assert data['state'] == 'available'
    assert data['available_labels'] == ['SECRET']
    assert len(data['records']) == 1
    record = data['records'][0]
    assert record['provenance_state'] == 'reported_first_origin'
    assert record['provenance']['origin_target'] == '/fixture/demo-secret.txt'
    assert record['match']['operation'] == 'connect'
    assert record['match']['target'] == '127.0.0.1'
    assert record['match']['actual_action'] == 'block'
    assert record['binding']['attribution'] == 'shared_executor_unattributed'
    assert record['source_configuration']['names'] == ['阻止敏感信息外发']
    assert len(record['source_configuration']['documents'][0]['sources']) == 2
    assert 'raw_label_names' not in record
    assert 'edges' not in data and 'anchor' not in data


@pytest.mark.parametrize(('effect', 'action'), [('block', 'block'), ('notify', 'report'), ('kill', 'kill')])
def test_native_block_notify_and_kill_actions(evidence, effect, action):
    evidence['receipt']['artifact']['compile']['rules'][0]['effect'] = effect
    evidence['insert'](evidence['event'](effect=effect, action=action), f'{effect}-{action}')
    record = flow.query(evidence['ident'], 's1', view='shared_domain')['records'][0]
    assert record['match']['effect'] == effect
    assert record['match']['actual_action'] == action
    assert record['match']['blocked'] is (action == 'block')
    assert record['match']['killed'] is (action == 'kill')


def test_missing_provenance_remains_an_explicit_kernel_match(evidence):
    value = evidence['event'](provenance=False)
    value['matched_label_details'][0]['provenance'] = {'origin_target': '/must/not/be/inferred'}
    evidence['insert'](value, 'no-top-level-provenance')
    record = flow.query(evidence['ident'], 's1', view='shared_domain')['records'][0]
    assert record['provenance_state'] == 'not_reported'
    assert record['provenance'] is None
    assert record['match']['actual_action'] == 'block'


def test_multiple_labels_do_not_create_additional_origins_or_chains(evidence):
    evidence['insert'](evidence['event'](labels=['doc_SECRET', 'LOCAL_TOKEN']), 'multi-label')
    record = flow.query(evidence['ident'], 's1', view='shared_domain')['records'][0]
    assert record['labels'] == ['SECRET', 'LOCAL_TOKEN']
    assert record['provenance']['label'] == 'SECRET'
    assert record['source_configuration']['documents'][0]['labels'] == ['SECRET']
    assert len(record['source_configuration']['documents'][0]['sources']) == 2
    assert 'causal_chain' not in record
    assert 'predecessor' not in json.dumps(record)


@pytest.mark.parametrize('mismatch', ['generation', 'bundle', 'domain', 'clause'])
def test_binding_mismatch_never_projects_current_configuration(evidence, mismatch):
    value = evidence['event']()
    selected, bundle, domain = evidence['generation'], 'approved-hash', 41
    if mismatch == 'generation':
        selected = 'wrong-generation'
    elif mismatch == 'bundle':
        bundle = 'wrong-bundle'
    elif mismatch == 'domain':
        domain = 42
    elif mismatch == 'clause':
        value['rule']['clause_hash'] = 'wrong-clause'
    evidence['insert'](value, mismatch, selected=selected, bundle=bundle, domain=domain)
    assert flow.query(evidence['ident'], 's1', view='shared_domain')['records'] == []


def test_only_a_unique_trusted_tool_tag_attributes_to_session(evidence):
    evidence['tool_start']('91')
    evidence['insert'](evidence['event'](tag='91'), 'trusted')
    session = flow.query(evidence['ident'], 's1')
    assert session['records'][0]['binding']['attribution'] == 'trusted_tool_tag'
    assert session['records'][0]['binding']['session_id'] == 's1'

    evidence['tool_start']('92', session='s1', call='call-a')
    evidence['tool_start']('92', session='s2', call='call-b')
    evidence['insert'](evidence['event'](tag='92', timestamp='1792475035675378405'), 'conflicting')
    shared = flow.query(evidence['ident'], 's1', view='shared_domain')
    conflicting = next(record for record in shared['records'] if record['id'] != session['records'][0]['id'])
    assert conflicting['binding']['attribution'] == 'shared_executor_unattributed'
    assert conflicting['binding']['session_id'] is None

    evidence['tool_start']('93', domain=99, call='call-cross-domain')
    evidence['insert'](evidence['event'](tag='93', timestamp='1792475035675378406'), 'cross-domain')
    cross_domain = flow.query(evidence['ident'], 's1', view='shared_domain')['records'][0]
    assert cross_domain['binding']['session_id'] is None


def test_filter_pagination_history_and_collection_states(evidence):
    for index in range(3):
        evidence['insert'](evidence['event'](timestamp=str(1792475035675378404 + index)), f'page-{index}')
    first = flow.query(evidence['ident'], 's1', view='shared_domain', label='SECRET', limit=2)
    assert len(first['records']) == 2 and first['next_cursor']
    second = flow.query(evidence['ident'], 's1', view='shared_domain', label='SECRET', cursor=first['next_cursor'], limit=2)
    assert len(second['records']) == 1 and second['next_cursor'] is None
    assert flow.query(evidence['ident'], 's1', view='shared_domain', label='UNKNOWN')['records'] == []

    old = 'historical-generation'
    old_receipt = copy.deepcopy(evidence['receipt'])
    old_receipt['generation'] = old
    evidence['state']['receipts'][old] = old_receipt
    evidence['insert'](evidence['event'](), 'old-native', selected=old)
    historical = flow.query(evidence['ident'], 's1', view='shared_domain', generation=old)
    assert historical['historical'] is True and historical['records']

    evidence['state']['collection'] = {'available': False, 'error': 'isolated collector outage'}
    failed = flow.query(evidence['ident'], 's1', view='shared_domain')
    assert failed['state'] == 'collection_failed' and failed['records']


def test_legacy_transition_rows_are_retained_but_never_read(evidence):
    evidence['insert']({'event': 'label_transition', 'label_names': ['doc_SECRET'],
                        'predecessor_event_id': 'legacy-1'}, 'legacy-transition')
    data = flow.query(evidence['ident'], 's1', view='shared_domain')
    assert data['state'] == 'empty' and data['records'] == []
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) AS n FROM instance_kernel_events WHERE source_key='legacy-transition'").fetchone()['n'] == 1


def test_duplicate_collection_is_idempotent(evidence):
    value = evidence['event']()
    first = evidence['insert'](value, 'same-native-offset')
    second = evidence['insert'](value, 'same-native-offset')
    assert first == second
    assert len(flow.query(evidence['ident'], 's1', view='shared_domain')['records']) == 1


def test_empty_and_collection_failed_are_distinct(evidence):
    empty = flow.query(evidence['ident'], 's1', view='shared_domain')
    assert empty['state'] == 'empty' and empty['collection']['available'] is True
    evidence['state']['collection'] = {'available': False, 'error': 'isolated collector outage'}
    failed = flow.query(evidence['ident'], 's1', view='shared_domain')
    assert failed['state'] == 'collection_failed' and failed['records'] == []


def test_both_api_routes_expose_the_native_record_contract(evidence, world):
    evidence['insert'](evidence['event'](), 'api-native')
    paths = [
        f"/api/agent-instances/{evidence['ident']}/sessions/s1/information-flow",
        f"/api/console/agents/{evidence['ident']}/sessions/s1/information-flow",
    ]
    for path in paths:
        response = world.client.get(path, headers=ADMIN, params={'view': 'shared_domain', 'label': 'SECRET', 'limit': 24})
        assert response.status_code == 200
        data = response.json()
        assert data['state'] == 'available' and data['records'][0]['provenance_state'] == 'reported_first_origin'
        assert set(data) == {'view', 'generation', 'historical', 'collection', 'state', 'available_labels', 'records', 'next_cursor', 'coverage'}
        assert world.client.get(path, headers=ADMIN, params={'view': 'untrusted'}).status_code == 422
        assert world.client.get(path, headers=ADMIN, params={'cursor': 0}).status_code == 422
        assert world.client.get(path, headers=ADMIN, params={'limit': 101}).status_code == 422


def test_both_api_routes_default_to_twenty_four_records(evidence, world):
    for index in range(25):
        evidence['insert'](evidence['event'](), f'api-page-{index:02d}')
    paths = [
        f"/api/agent-instances/{evidence['ident']}/sessions/s1/information-flow",
        f"/api/console/agents/{evidence['ident']}/sessions/s1/information-flow",
    ]
    for path in paths:
        response = world.client.get(path, headers=ADMIN, params={'view': 'shared_domain'})
        assert response.status_code == 200
        data = response.json()
        assert len(data['records']) == 24
        assert data['next_cursor'] is not None

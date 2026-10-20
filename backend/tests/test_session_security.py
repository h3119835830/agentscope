import json
import uuid
import pytest
from agentscope_app import db
from agentscope_app.instances import sessions, store, system_policy as system, dsl_policy as dsl
from agentscope_app.instances.policy import digest
from test_dsl_configuration import world, ADMIN, candidate, document


@pytest.fixture
def panel(world, monkeypatch):
    monkeypatch.setattr(sessions, 'native_sessions', lambda row: {
        'sessions': [{'id': 's1', 'name': '备份任务', 'mapping': 'native_registry'},
                     {'id': 's2', 'name': '另一个任务', 'mapping': 'native_registry'}],
        'mapping_available': True, 'executor_shared': True})
    world.run(world.a)
    return world


def url(panel, sid='s1'):
    return '/api/agent-instances/' + panel.a['id'] + '/sessions/' + sid


def view(panel, sid='s1'):
    return panel.client.get(url(panel, sid) + '/policies', headers=ADMIN).json()['security']


def body(panel, scope='agent', operation='add', selected=None, **extra):
    return {'scope': scope, 'operation': operation, 'basis_hash': view(panel)['basis_hash'],
            'constraint_id': selected, 'request_key': uuid.uuid4().hex,
            'acknowledge_scope': True, **extra}


def send(panel, value, sid='s1', headers=ADMIN):
    return panel.client.post(url(panel, sid) + '/security/proposals', json=value, headers=headers)


def install_rule(panel, rule):
    row = store.get(panel.a['id'])
    local = {'rules': [rule], 'network': 'model_only'}
    policy = system.compose(local, row['resources'])
    store.update(row['id'], local_policy=local, policy=policy, policy_hash=digest(policy))


def decide(panel, created):
    ident = created['approval_id']; p = created['proposal']
    approved = panel.client.post('/api/console/approvals/' + ident + '/approve',
        json={'proposal_hash': p['proposal_hash'], 'request_key': uuid.uuid4().hex}, headers=ADMIN)
    assert approved.status_code == 200, approved.text
    applied = panel.client.post('/api/console/approvals/' + ident + '/apply',
        json={'proposal_hash': p['proposal_hash'], 'approval_hash': approved.json()['approval_hash'],
              'request_key': uuid.uuid4().hex}, headers=ADMIN)
    assert applied.status_code == 200, applied.text
    return applied.json()


def test_default_mount_network_and_system_builtins_are_visible_without_user_dsl(panel):
    before = store.get(panel.a['id'])
    data = panel.client.get(url(panel) + '/policies', headers=ADMIN).json()
    assert data['records'] == []
    assert {r['kind'] for r in data['security']['controls']} == {'system_builtin', 'baseline', 'network_mode'}
    assert data['security']['session_local_supported'] is False
    assert data['security']['coverage_complete']
    assert store.get(panel.a['id']) == before and not panel.calls


def test_domain_endpoint_uses_current_loaded_projection_not_legacy_controls(panel):
    install_rule(panel, {'action': 'tool', 'target': 'bash', 'effect': 'deny', 'text': ''})
    before = store.get(panel.a['id'])
    security = view(panel)
    raw = panel.client.get(url(panel) + '/domains', headers=ADMIN).json()
    projected = panel.client.get('/api/console/agents/' + panel.a['id'] + '/sessions/s1/domains', headers=ADMIN).json()
    assert raw['nodes'] == projected['nodes']
    nodes = {n['id']:n for n in projected['nodes']}
    assert len(security['controls']) == 4  # Legacy proposal API remains compatible.
    assert list(nodes) == ['system', 'agent']
    assert all(n['count'] is None for n in nodes.values())  # No load receipt.
    assert not raw['edges'] and not raw['coverage_complete']
    assert '共享' in projected['notice']
    assert store.get(panel.a['id']) == before and not panel.calls


def test_incomplete_domain_projection_does_not_turn_unknown_counts_into_zero():
    from agentscope_app.instances.session_security import domain_view
    data = domain_view({'coverage_complete':False,'controls':[{'scope':'agent'}]},False)
    assert all(n['count'] is None for n in data['nodes'])
    nodes = {n['id']:n for n in data['nodes']}
    assert nodes['agent']['count_label'] == '已取得 1 项约束'
    assert nodes['system']['count_label'] == '数量未完整取得'
    assert nodes['agent']['status'] == '当前执行未核验'


def test_guidance_system_inheritance_and_dominant_deny_keep_distinct_owners(panel):
    path = panel.a['resources'][0]
    shared = {'rules': [{'action': 'write', 'target': path, 'effect': 'deny', 'text': ''}], 'network': 'model_only'}
    with db.connect() as con:
        con.execute('UPDATE system_security_policy SET policy_json=?,policy_hash=?,revision=1',
                    (json.dumps(shared), digest(shared)))
    install_rule(panel, {'action': 'write', 'target': path, 'effect': 'allow', 'text': ''})
    rows = view(panel)['controls']
    assert any(r['scope'] == 'system' and r['kind'] == 'typed' for r in rows)
    assert next(r for r in rows if r['kind'] == 'typed' and r['scope'] == 'agent')['status'] == '受系统禁止约束'
    install_rule(panel, {'action': 'behavior', 'target': '', 'effect': 'deny', 'text': '输出结论注明来源'})
    row = next(r for r in view(panel)['controls'] if r['kind'] == 'typed' and r['scope'] == 'agent')
    assert '不作强制执行声明' in row['status']
    assert row['method'] == '行为指导 · 非强制'


def test_add_is_pending_idempotent_and_does_not_touch_execution(panel):
    before = store.get(panel.a['id'])
    value = body(panel, rule={'action': 'tool', 'target': 'bash', 'effect': 'confirm', 'text': '执行前确认'})
    first = send(panel, value)
    assert first.status_code == 200, first.text
    assert send(panel, value).json()['approval_id'] == first.json()['approval_id']
    assert store.get(panel.a['id']) == before and not panel.calls
    assert not any(r.get('rule', {}).get('target') == 'bash' for r in view(panel)['controls'])
    assert view(panel)['pending_changes'][0]['id'] == first.json()['approval_id']
    assert view(panel, 's2')['pending_changes'] == []
    reused = {**value, 'basis_hash': view(panel, 's2')['basis_hash']}
    assert send(panel, reused, sid='s2').status_code == 409


@pytest.mark.parametrize('scope', ['session', 'workspace'])
def test_local_scopes_are_refused_without_fallback_or_proposal(panel, scope):
    before = store.get(panel.a['id'])
    result = send(panel, body(panel, scope=scope, rule={'action': 'behavior', 'effect': 'deny', 'text': '仅此会话', 'target': ''}))
    assert result.status_code == 409 and '共用' in result.text
    with db.connect() as con:
        assert not con.execute('SELECT 1 FROM instance_proposals').fetchone()
    assert store.get(panel.a['id']) == before and not panel.calls


def test_missing_file_is_a_configuration_error_without_creating_candidate(panel):
    before = store.get(panel.a['id'])
    value = body(panel, rule={'action': 'read', 'effect': 'deny',
        'target': panel.a['resources'][0] + '/missing-file.txt', 'text': ''})
    result = send(panel, value)
    assert result.status_code == 409 and '路径或运行资源不存在' in result.text
    assert '控制连接不可达' not in result.text
    with db.connect() as con:
        assert not con.execute('SELECT 1 FROM instance_proposals').fetchone()
        assert not con.execute('SELECT 1 FROM session_security_requests WHERE instance_id=? AND request_key=?',
                               (panel.a['id'], value['request_key'])).fetchone()
    assert store.get(panel.a['id']) == before and not panel.calls


def test_foreign_session_stale_generation_and_missing_ack_cannot_submit(panel):
    value = body(panel, rule={'action': 'tool', 'effect': 'deny', 'target': 'bash', 'text': ''})
    assert send(panel, value, sid='s2').status_code == 409
    assert send(panel, {**value, 'acknowledge_scope': False}).status_code == 409
    store.update(panel.a['id'], generation='replacement')
    assert send(panel, value).status_code == 409
    assert not panel.calls


def test_system_builtins_remain_read_only_after_scope_merge(panel):
    builtin = next(r for r in view(panel)['controls'] if r['kind'] == 'system_builtin')
    assert builtin['scope'] == 'system' and builtin['system_builtin']
    assert not builtin['can_disable'] and not builtin['can_configure']
    before = store.get(panel.a['id'])
    for scope in ('system', 'agent'):
        for operation in ('disable', 'replace'):
            result = send(panel, body(panel, scope=scope, operation=operation, selected=builtin['id']))
            assert result.status_code == 409
    assert store.get(panel.a['id']) == before and not panel.calls
    path = panel.a['resources'][0]
    shared = {'rules': [{'action': 'write', 'target': path, 'effect': 'deny', 'text': ''}], 'network': 'model_only'}
    with db.connect() as con:
        con.execute('UPDATE system_security_policy SET policy_json=?,policy_hash=?,revision=1', (json.dumps(shared), digest(shared)))
    selected = next(r for r in view(panel)['controls'] if r['kind'] == 'typed' and r['scope'] == 'system')
    assert send(panel, body(panel, operation='disable', selected=selected['id'])).status_code == 409


def test_real_typed_proposal_approval_apply_and_disable_preserve_other_instance(panel):
    panel.run(panel.b)
    other = store.get(panel.b['id'])
    p = send(panel, body(panel, rule={'action': 'tool', 'target': 'bash', 'effect': 'deny', 'text': '保护工具入口'}))
    assert p.status_code == 200
    before = store.get(panel.a['id'])
    created = p.json(); ident = created['approval_id']; proposal = created['proposal']
    receipt = panel.client.post('/api/console/approvals/' + ident + '/approve',
        json={'proposal_hash': proposal['proposal_hash'], 'request_key': uuid.uuid4().hex}, headers=ADMIN)
    assert receipt.status_code == 200 and store.get(panel.a['id']) == before and not panel.calls
    decide(panel, created)
    selected = next(r for r in view(panel)['controls'] if r['kind'] == 'typed')
    p = send(panel, body(panel, operation='disable', selected=selected['id']))
    assert p.status_code == 200 and store.get(panel.a['id'])['local_policy']['rules']
    decide(panel, p.json())
    assert not store.get(panel.a['id'])['local_policy']['rules']
    assert store.get(panel.b['id']) == other


def test_dsl_document_removal_keeps_parent_and_other_documents(panel):
    first = candidate(panel.a['id'], [document(ident='own-a'), document(ident='own-b')])
    dsl.apply(panel.a['id'], first['id'], first['proposal_hash'])
    selected = next(r for r in view(panel)['controls'] if r.get('document_id') == 'own-a')
    assert selected['can_disable']
    p = send(panel, body(panel, operation='disable', selected=selected['id']))
    assert p.status_code == 200, p.text
    assert [d['id'] for d in p.json()['proposal']['documents']] == ['own-b']
    assert [d['id'] for d in dsl.current(panel.a['id'])['documents']] == ['own-a', 'own-b']


def test_missing_dsl_mapping_is_reported_as_incomplete_not_zero_protection(panel):
    p = candidate(panel.a['id'])
    dsl.apply(panel.a['id'], p['id'], p['proposal_hash'])
    row = store.get(panel.a['id']); receipt = dsl.receipt(row['id'], row['generation'])
    for doc in receipt['artifact']['documents']:
        doc['rules'] = []
    with db.connect() as con:
        con.execute('UPDATE instance_policy_receipts SET artifact_json=? WHERE instance_id=?',
                    (json.dumps(receipt['artifact']), row['id']))
    data = view(panel)
    assert not data['coverage_complete']
    assert any(r['kind'] == 'dsl_unverified' and not r['can_disable'] for r in data['controls'])


def test_control_auth_and_foreign_session_reject_before_writes(panel):
    value = body(panel, rule={'action': 'behavior', 'target': '', 'effect': 'deny', 'text': '核对来源'})
    assert send(panel, value, headers={}).status_code == 401
    assert send(panel, value, sid='not-owned').status_code == 409
    assert send(panel, {**value, 'approved': True}).status_code == 422
    assert not panel.calls


def test_product_projection_keeps_startup_evidence_for_the_security_panel(panel):
    p = candidate(panel.a['id'])
    dsl.apply(panel.a['id'], p['id'], p['proposal_hash'])
    data = panel.client.get('/api/console/agents/' + panel.a['id'] + '/sessions/s1/policies', headers=ADMIN).json()
    assert all(r.get('source_kind') != 'legacy_generated' for r in data['records'])
    assert data['security']['evidence_records']
    for control in data['security']['controls']:
        if control['kind'] == 'execution_record':
            assert any(r['id'] == control['record_id'] for r in data['security']['evidence_records'])
            assert control['title'].startswith('启动执行约束')


def test_immutable_startup_rules_join_system_without_becoming_editable(panel):
    from agentscope_app.instances.session_security import build, domain_view
    row = store.get(panel.a['id'])
    record = {'id': 'startup-fixed', 'scope_type': 'agent', 'source_kind': 'legacy_generated',
              'compiled_refs': [{'immutable': True, 'clause_op': 'exec', 'target_pattern': 'git', 'target_arg': 'push'}],
              'loaded': True}
    before = store.get(row['id'])
    security = build(row, {'id': 's1'}, row['generation'], True, [record], None)
    fixed = next(c for c in security['controls'] if c.get('record_id') == record['id'])
    assert fixed['scope'] == 'system' and fixed['system_builtin']
    assert not fixed['can_disable'] and not fixed['can_configure']
    assert set(security['scope_labels']) == {'system', 'agent', 'workspace', 'session'}
    nodes = domain_view(security, True)['nodes']
    assert len(nodes) == 4 and nodes[0]['id'] == 'system' and nodes[0]['count'] == 2
    assert sum(n['count'] for n in nodes) == len(security['controls'])
    assert record['scope_type'] == 'agent'  # Original execution evidence is not rewritten.
    assert store.get(row['id']) == before and not panel.calls

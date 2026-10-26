"""Conversation content stays frozen; approval projection never crosses revisions."""
import json
import uuid
from agentscope_app import db
from agentscope_app.instances import template_configurations as tc, template_versions, approval_decisions, dsl_policy as dsl, store
from test_dsl_configuration import world, ADMIN
from test_template_configurations import clean_templates, config, proposal, Provider, plan_body
from test_template_versions import empty_versions, edit


def generate(world, **changes):
    values = {k: v for k, v in config(**changes).items() if k in ('template_id', 'template_version', 'name', 'parameters', 'reason')}
    body = plan_body()
    provider = Provider({'configurations': [values], 'questions': [], 'gaps': []})
    return tc.generate(world.a['id'], body, provider), body, provider


def history(scope):
    return tc.directory(scope)['generations'][-1]['configuration_snapshots'][0]


def test_generation_atomically_saves_snapshot_and_retry_reuses_it_after_edits(world):
    result, body, provider = generate(world)
    frozen = result['configuration_snapshots'][0]
    with db.connect() as con:
        saved = json.loads(con.execute('SELECT result_json FROM template_configuration_requests WHERE request_key=?',
                                      ('generate:' + body['request_key'],)).fetchone()[0])
    assert saved['configuration_snapshots'][0] == {k: v for k, v in frozen.items() if not k.startswith('approval_')}
    assert frozen['name'] == '员工资料保护' and frozen['template']['name'] == '文件读取限制'
    assert frozen['template']['version'] == 2 and frozen['parameters'] == {'target': '/w/0/staff.csv'}
    assert frozen['scope']['id'] == world.a['id'] and frozen['approval_status'] == 'draft'
    template_versions.save('FILE-READ', edit())
    tc.save(world.a['id'], config(name='新版配置', template_version=3, parameters={'target': '/w/0/other.csv'}, base_revision=1), frozen['id'])
    store.update(world.a['id'], name='重命名 Agent')
    assert history(world.a['id']) == frozen
    retry = tc.generate(world.a['id'], body, provider)
    assert retry['configuration_snapshots'] == [frozen] and len(provider.calls) == 1
    assert not world.calls and not dsl.current(world.a['id'])['documents']


def test_each_turn_and_scope_retain_their_own_snapshot(world):
    a, _, _ = generate(world)
    b, _, _ = generate(world, name='预算保护', parameters={'target': '/w/0/budget.csv'})
    provider = Provider({'configurations': [{'template_id': 'SYS-env', 'template_version': 2, 'name': '共享环境文件保护',
                         'parameters': {'values': '.env', 'operations': ['open'], 'effect': 'block'}}], 'questions': [], 'gaps': []})
    shared = tc.generate('system', {**plan_body(), 'scope': 'system'}, provider)
    turns = tc.directory(world.a['id'])['generations']
    assert [g['configuration_snapshots'][0]['name'] for g in turns] == ['员工资料保护', '预算保护']
    assert a['configuration_snapshots'][0]['id'] != b['configuration_snapshots'][0]['id']
    assert shared['configuration_snapshots'][0]['scope'] == {'id': 'system', 'type': 'system', 'label': '所有 Agent'}
    assert not tc.directory(world.b['id'])['generations']
    assert [g['configuration_snapshots'][0]['name'] for g in tc.directory('system')['generations']] == ['共享环境文件保护']


def test_approval_projects_exact_revision_through_submit_approve_apply_disable(world):
    result, _, _ = generate(world)
    row = result['items'][0]
    p = proposal(row)
    assert history(world.a['id'])['approval_status'] == 'pending'
    approval_decisions.approve(p['id'], p['proposal_hash'], uuid.uuid4().hex)
    assert history(world.a['id'])['approval_status'] == 'approved'
    assert not world.calls and not dsl.current(world.a['id'])['documents']
    dsl.apply(world.a['id'], p['id'], p['proposal_hash'])
    assert history(world.a['id'])['approval_status'] == 'applied'
    off = proposal(row, operation='disable')
    projected = history(world.a['id'])
    assert (projected['approval_status'], projected['approval_operation']) == ('pending', 'disable')
    approval_decisions.approve(off['id'], off['proposal_hash'], uuid.uuid4().hex)
    dsl.apply(world.a['id'], off['id'], off['proposal_hash'])
    assert history(world.a['id'])['approval_operation'] == 'disable'
    assert history(world.a['id'])['approval_status'] == 'applied'


def test_new_revision_approval_does_not_appear_on_older_unsubmitted_turn(world):
    result, _, _ = generate(world)
    row = tc.save(world.a['id'], config(name='第二版', base_revision=1), result['items'][0]['id'])
    p = proposal(row)
    approval_decisions.approve(p['id'], p['proposal_hash'], uuid.uuid4().hex)
    assert history(world.a['id'])['approval_status'] == 'draft'
    assert history(world.a['id'])['name'] == '员工资料保护'


def test_old_revision_pending_becomes_stale_instead_of_borrowing_new_approval(world):
    result, _, _ = generate(world)
    proposal(result['items'][0])
    newer = tc.save(world.a['id'], config(name='第二版', base_revision=1), result['items'][0]['id'])
    proposal(newer)
    assert tc.view(newer)['status'] == 'pending'
    assert history(world.a['id'])['approval_status'] == 'stale'
    assert history(world.a['id'])['revision'] == 1


def test_legacy_history_uses_immutable_version_without_guessing_old_agent_name(world):
    result, body, _ = generate(world)
    with db.connect() as con:
        saved = json.loads(con.execute('SELECT result_json FROM template_configuration_requests WHERE request_key=?', ('generate:' + body['request_key'],)).fetchone()[0])
        del saved['configuration_snapshots']
        con.execute('UPDATE template_configuration_requests SET result_json=? WHERE request_key=?', (json.dumps(saved), 'generate:' + body['request_key']))
    tc.save(world.a['id'], config(name='第二版', parameters={'target': '/w/0/other.csv'}, base_revision=1), result['items'][0]['id'])
    template_versions.save('FILE-READ', edit())
    old = history(world.a['id'])
    assert old['name'] == '员工资料保护' and old['template']['version'] == 2
    assert old['parameters'] == {'target': '/w/0/staff.csv'}
    assert old['scope']['label'] == '指定 Agent（历史名称未记录）'


def test_snapshot_survives_missing_version_but_does_not_claim_approval(world):
    result, _, _ = generate(world)
    frozen = result['configuration_snapshots'][0]
    with db.connect() as con:
        con.execute('DELETE FROM template_configuration_versions WHERE id=? AND revision=1', (frozen['id'],))
        con.execute('UPDATE template_configurations SET archived=1 WHERE id=?', (frozen['id'],))
    old = history(world.a['id'])
    assert old['name'] == frozen['name'] and old['parameters'] == frozen['parameters']
    assert old['approval_status'] == 'unavailable'


def test_read_api_returns_snapshots_without_writes_or_model_calls(world):
    result, _, provider = generate(world)
    with db.connect() as con:
        before = {t: [tuple(r) for r in con.execute('SELECT * FROM ' + t)] for t in
                  ('template_configurations', 'template_configuration_versions', 'template_configuration_requests', 'template_configuration_proposals')}
    response = world.client.get('/api/policy-templates?scope_id=' + world.a['id'], headers=ADMIN)
    assert response.status_code == 200
    assert response.json()['generations'][0]['configuration_snapshots'] == result['configuration_snapshots']
    with db.connect() as con:
        assert before == {t: [tuple(r) for r in con.execute('SELECT * FROM ' + t)] for t in before}
    assert len(provider.calls) == 1 and not world.calls


def test_legacy_execution_display_uses_original_version_without_rewriting_history(world):
    result, body, _ = generate(world, reason='保护原始员工资料')
    original = result['configuration_snapshots'][0]
    with db.connect() as con:
        saved = json.loads(con.execute('SELECT result_json FROM template_configuration_requests WHERE request_key=?',
                                      ('generate:' + body['request_key'],)).fetchone()[0])
        del saved['configuration_snapshots'][0]['execution']
        serialized = json.dumps(saved)
        con.execute('UPDATE template_configuration_requests SET result_json=? WHERE request_key=?',
                    (serialized, 'generate:' + body['request_key']))
    tc.save(world.a['id'], config(name='新配置', reason='另一条反馈', base_revision=1), original['id'])
    projected = history(world.a['id'])
    assert projected['execution'] == original['execution']
    assert projected['execution']['reason'] == '保护原始员工资料'
    assert projected['execution']['effect'] == 'block'
    with db.connect() as con:
        assert con.execute('SELECT result_json FROM template_configuration_requests WHERE request_key=?',
                           ('generate:' + body['request_key'],)).fetchone()[0] == serialized
    assert not world.calls


def test_same_approval_has_one_status_observation_per_directory_response(world,monkeypatch):
    from agentscope_app.instances import approval_views
    a,_,_=generate(world);b,_,_=generate(world,name='第二项资料保护',parameters={'target':'/w/0/other.csv'})
    base=dsl.current(world.a['id'])
    p=tc.propose_batch({'scope_id':world.a['id'],'selections':[a['items'][0],b['items'][0]],
        'base_hash':base['document_hash'],'base_revision':base['revision'],'request_key':uuid.uuid4().hex})
    observations=[];live={'status':'pending'}
    def detail(ident):observations.append(ident);return dict(live)
    monkeypatch.setattr(approval_views,'detail',detail)
    page=tc.directory(world.a['id'])
    assert {i['status'] for i in page['items']}=={'pending'}
    assert {g['configuration_snapshots'][0]['approval_status'] for g in page['generations']}=={'pending'}
    assert observations==[p['id']]
    live['status']='stale';page=tc.directory(world.a['id'])
    assert {i['status'] for i in page['items']}=={'stale'}
    assert observations==[p['id'],p['id']]

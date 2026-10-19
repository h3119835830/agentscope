"""Cleanup changes list visibility, never approval or execution authority."""
import uuid
import pytest
from agentscope_app import db
from agentscope_app.instances import approval_clearance as cleanup, approval_views as views, approval_decisions as decisions, dsl_policy as dsl
from test_dsl_configuration import world, ADMIN, candidate
from test_template_configurations import clean_templates, config, proposal
from agentscope_app.instances import template_configurations as tc


@pytest.fixture(autouse=True)
def empty_clearance(client):
    with db.connect() as con:
        con.execute("DELETE FROM console_retained_records WHERE kind='approval'")
    yield
    with db.connect() as con:
        con.execute("DELETE FROM console_retained_records WHERE kind='approval'")


def clear(ident, **extra):
    return cleanup.change(ident, 'clear', cleanup.detail(ident)['clearance_hash'], uuid.uuid4().hex, **extra)


def rejected(world):
    row = tc.save(world.a['id'], config())
    p = proposal(row)
    decisions.reject(p['id'], p['proposal_hash'])
    return row, p


def authority():
    with db.connect() as con:
        return {t: [tuple(r) for r in con.execute('SELECT * FROM ' + t + ' ORDER BY rowid')] for t in (
            'instance_dsl_proposals', 'instance_dsl_scopes', 'agent_instances', 'template_configurations',
            'template_configuration_versions', 'template_configuration_proposals', 'policy_approval_decisions',
            'policy_application_requests')}


def test_clear_restore_is_durable_reversible_and_preserves_original_records(world):
    row, p = rejected(world)
    before = authority()
    body = {'expected_hash': cleanup.detail(p['id'])['clearance_hash'], 'request_key': uuid.uuid4().hex}
    endpoint = '/api/console/approvals/' + p['id']
    response = world.client.post(endpoint + '/clear', headers=ADMIN, json=body)
    assert response.status_code == 200, response.text
    assert response.json()['cleared'] and response.json()['status'] == 'rejected'
    assert not cleanup.directory()['records']
    assert [r['id'] for r in cleanup.directory(True)['records']] == [p['id']]
    assert world.client.get(endpoint, headers=ADMIN).json()['cleared']
    # The audit and configuration links remain usable after cleanup.
    assert views.detail(p['id'])['status'] == 'rejected'
    assert tc.view(tc.load(row['id']))['status'] == 'rejected'
    assert authority() == before
    retry = world.client.post(endpoint + '/clear', headers=ADMIN, json=body)
    assert retry.status_code == 200 and retry.json()['idempotent']
    restored = world.client.post(endpoint + '/restore', headers=ADMIN, json={
        'expected_hash': response.json()['clearance_hash'], 'request_key': uuid.uuid4().hex})
    assert restored.status_code == 200 and not restored.json()['cleared']
    assert [r['id'] for r in cleanup.directory()['records']] == [p['id']]
    assert not cleanup.directory(True)['records'] and authority() == before and not world.calls


def test_clearing_applied_record_never_stops_or_disables_the_policy(world):
    p = candidate(world.a['id'])
    receipt = decisions.approve(p['id'], p['proposal_hash'], uuid.uuid4().hex)
    decisions.apply(p['id'], p['proposal_hash'], receipt['approval_hash'], uuid.uuid4().hex)
    before, calls = authority(), list(world.calls)
    result = clear(p['id'])
    assert result['cleared'] and result['status'] == 'applied'
    assert dsl.current(world.a['id'])['documents'] and authority() == before and world.calls == calls


@pytest.mark.parametrize('state', ['pending', 'approved', 'applying'])
def test_active_work_cannot_be_hidden_or_converted_to_rejection(world, state):
    p = candidate(world.a['id'])
    if state == 'approved':
        decisions.approve(p['id'], p['proposal_hash'], uuid.uuid4().hex)
    elif state == 'applying':
        with db.connect() as con:
            con.execute("UPDATE instance_dsl_proposals SET state='applying' WHERE id=?", (p['id'],))
    before = authority()
    current = cleanup.detail(p['id'])
    assert not current['can_clear']
    with pytest.raises(ValueError, match='不能清理|先拒绝或撤回'):
        clear(p['id'])
    assert authority() == before and not cleanup.directory(True)['records']


def test_attention_record_cleanup_does_not_revalidate_or_create_a_candidate(world):
    row = tc.save(world.a['id'], config())
    p = proposal(row)
    tc.save(world.a['id'], config(name='第二版', base_revision=1), row['id'])
    before = authority()
    result = clear(p['id'])
    assert result['cleared'] and result['status'] == 'stale'
    assert authority() == before and not world.calls
    assert cleanup.directory(True)['cleared_count'] == 1


def test_preview_drift_and_old_request_replay_after_restore_are_rejected(world):
    _, p = rejected(world)
    original = cleanup.detail(p['id'])
    key = uuid.uuid4().hex
    cleared = cleanup.change(p['id'], 'clear', original['clearance_hash'], key)
    restored = cleanup.change(p['id'], 'restore', cleared['clearance_hash'], uuid.uuid4().hex)
    assert restored['clearance_hash'] != original['clearance_hash']
    with pytest.raises(ValueError, match='已变化'):
        cleanup.change(p['id'], 'clear', original['clearance_hash'], key)
    assert not cleanup.detail(p['id'])['cleared']


def test_status_drift_is_checked_at_submission_and_actionable_rows_stay_visible(world):
    _, p = rejected(world)
    old = cleanup.detail(p['id'])
    with db.connect() as con:
        con.execute("UPDATE instance_dsl_proposals SET state='pending' WHERE id=?", (p['id'],))
    with pytest.raises(ValueError, match='已变化'):
        cleanup.change(p['id'], 'clear', old['clearance_hash'], uuid.uuid4().hex)
    with db.connect() as con:
        con.execute("UPDATE instance_dsl_proposals SET state='rejected' WHERE id=?", (p['id'],))
    clear(p['id'])
    with db.connect() as con:
        con.execute("UPDATE instance_dsl_proposals SET state='pending' WHERE id=?", (p['id'],))
    visible = cleanup.directory()['records']
    assert len(visible) == 1 and visible[0]['status'] == 'pending' and not visible[0]['cleared']
    assert cleanup.directory()['pending_count'] == 1


def test_request_key_conflicts_do_not_change_visibility(world):
    _, p = rejected(world)
    expected, key = cleanup.detail(p['id'])['clearance_hash'], uuid.uuid4().hex
    cleared = cleanup.change(p['id'], 'clear', expected, key)
    with pytest.raises(ValueError, match='幂等键'):
        cleanup.change(p['id'], 'restore', cleared['clearance_hash'], key)
    assert cleanup.detail(p['id'])['cleared']


def test_cleanup_is_admin_only_and_rejects_unrecognized_parameters(world):
    _, p = rejected(world)
    endpoint = '/api/console/approvals/' + p['id']
    body = {'expected_hash': cleanup.detail(p['id'])['clearance_hash'], 'request_key': uuid.uuid4().hex}
    for action in ('clear', 'restore'):
        assert world.client.post(endpoint + '/' + action, headers={'Authorization': 'Bearer native'}, json=body).status_code == 401
    assert world.client.post(endpoint + '/clear', headers=ADMIN, json={**body, 'delete': True}).status_code == 422
    assert not cleanup.detail(p['id'])['cleared']

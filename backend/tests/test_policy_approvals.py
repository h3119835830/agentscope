"""Approval projections cannot confer application authority or lose exact targeting."""
import pytest
from agentscope_app import console
from agentscope_app.instances import approval_views,dsl_policy as dsl
from test_dsl_configuration import world,candidate,ADMIN


def test_approval_records_and_readable_compiled_details_are_read_only(world):
    p=candidate(world.a['id'])
    page=world.client.get('/api/console/approvals',headers=ADMIN)
    assert page.status_code==200
    row=next(r for r in page.json()['records'] if r['id']==p['id'])
    assert row['scope_id']==world.a['id'] and row['can_apply'] and row['status']=='pending'
    detail=world.client.get('/api/console/approvals/'+p['id'],headers=ADMIN).json()
    assert detail['records'][0]['clauses'][0]['target']=='/w/0/block.txt'
    assert detail['records'][0]['compile_status']=='compiled'
    assert detail['previous_documents']==[] and len(detail['targets'])==1
    assert detail['proposal_hash']==p['proposal_hash'] and not world.calls
    assert dsl.current(world.a['id'])['revision']==0
    assert world.client.get('/api/console/approvals').status_code==401


def test_target_drift_moves_to_revalidation_without_stopping_an_agent(world):
    p=candidate(world.a['id']);world.run(world.a)
    row=approval_views.detail(p['id'])
    assert row['status']=='stale' and not row['can_apply']
    assert not world.calls and dsl.current(world.a['id'])['revision']==0


def test_retained_agent_approval_is_absent_from_list_count_and_detail(world):
    p=candidate(world.a['id'])
    before=approval_views.pending_count()
    console.retain([('agent',world.a['id'])],'test exact target retention')
    try:
        assert p['id'] not in [r['id'] for r in approval_views.directory()['records']]
        assert approval_views.pending_count()==before-1
        assert world.client.get('/api/console/approvals/'+p['id'],headers=ADMIN).status_code==404
    finally:
        from agentscope_app import db
        with db.connect() as con:con.execute("DELETE FROM console_retained_records WHERE kind='agent' AND record_id=?",(world.a['id'],))


def test_reject_checks_exact_scope_and_hash_and_never_changes_loaded_configuration(world):
    p=candidate(world.a['id']);before=dsl.current(world.a['id'])
    with pytest.raises(ValueError):dsl.reject(world.b['id'],p['id'],p['proposal_hash'])
    with pytest.raises(ValueError):dsl.reject(world.a['id'],p['id'],'0'*64)
    assert dsl.reject(world.a['id'],p['id'],p['proposal_hash'])['state']=='rejected'
    assert dsl.reject(world.a['id'],p['id'],p['proposal_hash'])['idempotent']
    assert approval_views.detail(p['id'])['status']=='rejected'
    assert not approval_views.detail(p['id'])['can_apply']
    with pytest.raises(ValueError):dsl.apply(world.a['id'],p['id'],p['proposal_hash'])
    assert before==dsl.current(world.a['id']) and not world.calls


def test_reject_routes_require_auth_and_do_not_reject_an_applied_proposal(world):
    p=candidate(world.a['id']);url='/api/agent-instances/'+world.a['id']+'/dsl/proposals/'+p['id']+'/reject'
    assert world.client.post(url,json={'proposal_hash':p['proposal_hash']}).status_code==401
    dsl.apply(world.a['id'],p['id'],p['proposal_hash'])
    assert world.client.post(url,json={'proposal_hash':p['proposal_hash']},headers=ADMIN).status_code==409
    assert approval_views.detail(p['id'])['status']=='applied'

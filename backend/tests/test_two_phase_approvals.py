"""Approval is durable metadata; execution requires its exact receipt."""
import copy
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from agentscope_app import db
from agentscope_app.instances import approval_views as approvals, approval_decisions as decisions, store, dsl_policy as dsl
from test_dsl_configuration import world, candidate, document, ADMIN


def approve(world,p,key=None):
    return world.client.post('/api/console/approvals/'+p['id']+'/approve',headers=ADMIN,
                             json={'proposal_hash':p['proposal_hash'],'request_key':key or uuid.uuid4().hex})


def apply(world,p,receipt,key=None):
    return world.client.post('/api/console/approvals/'+p['id']+'/apply',headers=ADMIN,
                             json={'proposal_hash':p['proposal_hash'],'approval_hash':receipt['approval_hash'],
                                   'request_key':key or uuid.uuid4().hex})


def test_approve_is_persistent_and_cannot_execute_before_explicit_apply(world):
    world.run(world.a)
    p=candidate(world.a['id']);before=store.get(world.a['id']);other=store.get(world.b['id'])
    base=copy.deepcopy(dsl.current(world.a['id']))
    assert approvals.detail(p['id'])['can_approve'] and not approvals.detail(p['id'])['can_apply']
    key=uuid.uuid4().hex;response=approve(world,p,key);assert response.status_code==200,response.text
    receipt=response.json()
    assert approve(world,p,key).json()['idempotent']
    assert store.get(world.a['id'])==before and dsl.current(world.a['id'])==base and not world.calls
    with db.connect() as con:decisions.init(con)
    detail=approvals.detail(p['id'])
    assert detail['status']=='approved' and detail['can_apply'] and not detail['can_approve']
    assert detail['approval_hash']==receipt['approval_hash']
    key=uuid.uuid4().hex
    response=apply(world,p,receipt,key);assert response.status_code==200,response.text
    calls=list(world.calls)
    assert apply(world,p,receipt,key).json()['idempotent'] and world.calls==calls
    assert dsl.current(world.a['id'])['revision']==1 and store.get(world.b['id'])==other
    assert approvals.detail(p['id'])['status']=='applied'


def test_apply_requires_receipt_and_matching_target(world):
    p=candidate(world.a['id']);q=candidate(world.b['id'])
    assert apply(world,p,{'approval_hash':'0'*64}).status_code==409
    receipt=approve(world,p).json()
    assert apply(world,q,receipt).status_code==409 and not world.calls
    assert dsl.current(world.a['id'])['revision']==dsl.current(world.b['id'])['revision']==0


def test_only_one_approved_version_per_owner_and_rejection_releases_slot(world):
    p=candidate(world.a['id'])
    q=candidate(world.a['id'],[document(ident='another')])
    assert approve(world,p).status_code==200
    assert approve(world,q).status_code==409
    assert world.client.post('/api/console/approvals/'+p['id']+'/reject',headers=ADMIN,
                             json={'proposal_hash':p['proposal_hash']}).status_code==200
    assert approve(world,q).status_code==200
    assert not world.calls and dsl.current(world.a['id'])['revision']==0


def test_drift_after_approval_never_reuses_old_authority(world):
    p=candidate(world.a['id']);receipt=approve(world,p).json()
    store.update(world.a['id'],resources=world.b['resources'])
    assert approvals.detail(p['id'])['status']=='stale'
    assert apply(world,p,receipt).status_code==409 and not world.calls
    assert dsl.current(world.a['id'])['revision']==0


def test_approval_and_application_have_independent_authentication(world):
    p=candidate(world.a['id'])
    body={'proposal_hash':p['proposal_hash'],'request_key':uuid.uuid4().hex}
    assert world.client.post('/api/console/approvals/'+p['id']+'/approve',json=body).status_code==401
    receipt=approve(world,p).json()
    assert world.client.post('/api/console/approvals/'+p['id']+'/apply',
        json={**body,'approval_hash':receipt['approval_hash']}).status_code==401
    assert not world.calls


def test_apply_failure_keeps_execution_paused_without_automatic_retry(world):
    world.run(world.a);before=store.get(world.b['id'])
    p=candidate(world.a['id']);receipt=approve(world,p).json()
    world.fail['start']=True
    assert apply(world,p,receipt).status_code>=400
    calls=list(world.calls)
    assert approvals.detail(p['id'])['status']=='failed' and not approvals.detail(p['id'])['can_apply']
    with db.connect() as con:decisions.init(con)
    assert world.calls==calls and store.get(world.a['id'])['gate']=='paused' and store.get(world.b['id'])==before


def test_legacy_confirm_keeps_exact_hash_and_records_receipt(world):
    p=candidate(world.a['id'])
    response=world.client.post('/api/console/approvals/'+p['id']+'/confirm',headers=ADMIN,json={'proposal_hash':p['proposal_hash']})
    assert response.status_code==200,response.text
    assert decisions.receipts()[p['id']]['state']=='applied'
    assert world.client.post('/api/console/approvals/'+p['id']+'/confirm',headers=ADMIN,
                             json={'proposal_hash':'0'*64}).status_code==409


def test_concurrent_approval_has_one_winner_and_never_touches_execution(world):
    p=candidate(world.a['id']);q=candidate(world.a['id'],[document(ident='other')])
    with ThreadPoolExecutor(max_workers=2) as pool:
        values=list(pool.map(lambda row:approve(world,row).status_code,[p,q]))
    assert sorted(values)==[200,409] and not world.calls
    assert sum(r['state']=='approved' for r in decisions.receipts().values())==1


def test_modify_and_remove_leave_old_constraints_until_application(world):
    p=candidate(world.a['id']);assert apply(world,p,approve(world,p).json()).status_code==200
    for docs in ([document(ident='updated')],[]):
        previous=copy.deepcopy(dsl.current(world.a['id']))
        q=candidate(world.a['id'],docs);receipt=approve(world,q).json()
        assert dsl.current(world.a['id'])==previous
        assert apply(world,q,receipt).status_code==200
        assert dsl.current(world.a['id'])['documents']==docs


def test_parent_baseline_drift_requires_new_validation(world):
    p=candidate(world.a['id']);receipt=approve(world,p).json()
    q=candidate('system');assert apply(world,q,approve(world,q).json()).status_code==200
    assert apply(world,p,receipt).status_code==409
    assert dsl.current(world.a['id'])['revision']==0


def test_interrupted_application_is_not_resumed_on_reinitialization(world):
    world.run(world.a)
    p=candidate(world.a['id']);receipt=approve(world,p).json()
    with db.connect() as con:
        con.execute("UPDATE policy_approval_decisions SET state='applying' WHERE approval_id=?",(p['id'],))
        decisions.init(con)
    row=approvals.detail(p['id'])
    assert row['status']=='applying' and not row['can_apply'] and not row['can_approve']
    assert apply(world,p,receipt).status_code==409 and not world.calls
    assert decisions.reconcile_interrupted()==1
    assert store.get(world.a['id'])['gate']=='paused'
    assert world.calls==[('stop',world.a['id'])] and dsl.current(world.a['id'])['revision']==0
    assert decisions.reconcile_interrupted()==0


def test_failure_before_loader_still_pauses_only_the_frozen_target(world,monkeypatch):
    world.run(world.a);world.run(world.b)
    p=candidate(world.a['id']);receipt=approve(world,p).json()
    monkeypatch.setattr(approvals,'execute_decision',lambda *args:(_ for _ in ()).throw(RuntimeError('recompile failed')))
    assert apply(world,p,receipt).status_code==409
    assert store.get(world.a['id'])['gate']=='paused' and store.get(world.b['id'])['gate']=='open'
    assert world.calls==[('stop',world.a['id'])]
    assert dsl.current(world.a['id'])['revision']==0

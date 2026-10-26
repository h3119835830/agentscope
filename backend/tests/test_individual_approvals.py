import json
import uuid
import pytest
from agentscope_app import db
from agentscope_app.instances import template_configurations as tc,dsl_policy as dsl,approval_views as views,approval_decisions as decisions
from agentscope_app.instances import individual_approvals as individual
from test_dsl_configuration import world,ADMIN
from test_template_configurations import clean_templates,config,proposal
from test_unified_policy_catalog import batch


def pair(world):
    return [tc.save(world.a['id'],config(name=name,parameters={'target':'/w/0/'+path}))
            for name,path in [('员工保护','staff.csv'),('预算保护','budget.csv')]]


def test_each_selected_policy_has_its_own_approval_and_idempotent_submission(world):
    rows=pair(world);body=batch(world.a['id'],rows)
    result=tc.propose_batch(body)
    assert len(result['items'])==2 and len({p['id'] for p in result['items']})==2
    assert tc.propose_batch(body)==result
    for row,p in zip(rows,result['items']):
        detail=views.detail(p['id'])
        assert detail['name']==row['name'] and detail['approval_unit']['configuration_id']==row['id']
        assert len(detail['configuration_records'])==1 and len(p['documents'])==1
    with pytest.raises(ValueError,match='幂等键'):tc.propose_batch({**body,'selections':body['selections'][:1]})
    assert not decisions.receipts() and not world.calls


def test_independent_approvals_do_not_approve_or_reject_siblings(world):
    first,second=tc.propose_batch(batch(world.a['id'],pair(world)))['items']
    decisions.approve(first['id'],first['proposal_hash'],uuid.uuid4().hex)
    assert views.detail(first['id'])['status']=='approved'
    assert views.detail(second['id'])['status']=='pending'
    decisions.approve(second['id'],second['proposal_hash'],uuid.uuid4().hex)
    decisions.reject(first['id'],first['proposal_hash'])
    assert views.detail(first['id'])['status']=='rejected' and views.detail(second['id'])['status']=='approved'
    assert not world.calls and not dsl.current(world.a['id'])['documents']


def test_application_only_loads_this_policy_and_keeps_stale_sibling_unapplied(world):
    rows=pair(world);first,second=tc.propose_batch(batch(world.a['id'],rows))['items']
    receipt=decisions.approve(first['id'],first['proposal_hash'],uuid.uuid4().hex)
    decisions.apply(first['id'],first['proposal_hash'],receipt['approval_hash'],uuid.uuid4().hex)
    assert {d['id'] for d in dsl.current(world.a['id'])['documents']}=={rows[0]['id']}
    assert views.detail(second['id'])['status']=='stale'
    # Explicitly resubmitting the second on the new baseline preserves the first.
    next_proposal=proposal(rows[1]);receipt=decisions.approve(next_proposal['id'],next_proposal['proposal_hash'],uuid.uuid4().hex)
    decisions.apply(next_proposal['id'],next_proposal['proposal_hash'],receipt['approval_hash'],uuid.uuid4().hex)
    assert {d['id'] for d in dsl.current(world.a['id'])['documents']}=={r['id'] for r in rows}


def test_two_versions_of_the_same_policy_cannot_hold_overlapping_approval(world):
    row=pair(world)[0];a=proposal(row);b=proposal(row)
    decisions.approve(a['id'],a['proposal_hash'],uuid.uuid4().hex)
    with pytest.raises(ValueError,match='待应用'):decisions.approve(b['id'],b['proposal_hash'],uuid.uuid4().hex)


def test_old_group_is_converted_without_consent_or_runtime_changes(world):
    rows=pair(world);body=batch(world.a['id'],rows)
    old=tc._propose_selection(body)
    assert not views.detail(old['id'])['can_approve']
    result=individual.split_pending(old['id'])
    assert len(result['records'])==2 and individual.split_pending(old['id'])['idempotent']
    assert views.detail(old['id'])['status']=='superseded'
    ids={row['id'] for row in result['records']}
    page=views.directory()['records']
    assert old['id'] not in {p['id'] for p in page}
    assert ids<={p['id'] for p in page} and all(views.detail(ident)['can_approve'] for ident in ids)
    for ident in ids:
        with db.connect() as con:
            selections=json.loads(con.execute('SELECT selections_json FROM template_configuration_proposals WHERE proposal_id=?',(ident,)).fetchone()[0])
        assert len(selections)==1
    with pytest.raises(ValueError):decisions.approve(old['id'],old['proposal_hash'],uuid.uuid4().hex)
    assert not world.calls and not decisions.receipts()


def test_conversion_requires_console_authority_and_does_not_accept_approved_objects(world):
    old=tc._propose_selection(batch(world.a['id'],pair(world)))
    route='/api/console/approvals/'+old['id']+'/split'
    assert world.client.post(route).status_code==401
    assert world.client.post(route,headers={'Authorization':'Bearer native'}).status_code==401
    assert world.client.post(route,headers=ADMIN).status_code==200
    single=proposal(tc.directory(world.a['id'])['items'][0])
    decisions.approve(single['id'],single['proposal_hash'],uuid.uuid4().hex)
    with pytest.raises(ValueError,match='尚未批准'):individual.split_pending(single['id'])


def test_distinct_legacy_policy_records_can_also_be_approved_independently(world):
    from agentscope_app.instances import policy_library
    from test_policy_library import config as legacy_config
    rows=[policy_library.save({'kind':'structured','config':legacy_config(mode='exact',values='/w/0/'+name),'base_revision':0}) for name in ('a.csv','b.csv')]
    proposals=tc.propose_batch(batch('system',rows))['items']
    for p in proposals:decisions.approve(p['id'],p['proposal_hash'],uuid.uuid4().hex)
    assert all(views.detail(p['id'])['status']=='approved' for p in proposals)
    assert not world.calls


def test_stale_target_diagnostic_identifies_changed_fields_without_private_values(world):
    from agentscope_app.instances import store
    p=proposal(pair(world)[0])
    store.update(world.a['id'],generation='changed-generation-for-test')
    diagnostic=views.detail(p['id'])['validation_diagnostic']
    assert diagnostic['stage']=='target'
    assert any('generation' in item['fields'] for item in diagnostic['target_changes'])
    assert 'changed-generation-for-test' not in json.dumps(diagnostic)


def test_failed_conversion_is_resumable_and_incomplete_children_are_not_approvable(world,monkeypatch):
    old=tc._propose_selection(batch(world.a['id'],pair(world)));original=tc.propose;calls=[]
    def partial(*args,**kwargs):
        calls.append(args[0])
        if len(calls)==2:raise RuntimeError('synthetic interruption')
        return original(*args,**kwargs)
    monkeypatch.setattr(tc,'propose',partial)
    with pytest.raises(RuntimeError):individual.split_pending(old['id'])
    page=views.directory()['records']
    assert not any(p['can_approve'] for p in page)
    from agentscope_app.instances import approval_recovery
    child=next(p for p in page if p.get('split_incomplete'))
    assert not child['revalidation']['available']
    with pytest.raises(ValueError,match='独立审批'):approval_recovery.plan(child['id'])
    monkeypatch.setattr(tc,'propose',original)
    result=individual.split_pending(old['id'])
    assert len(result['records'])==2
    assert len([p for p in views.directory()['records'] if p['can_approve']])==2
    assert not decisions.receipts() and not world.calls

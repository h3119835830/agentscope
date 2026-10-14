import uuid
import pytest
from agentscope_app.instances import controller, store, dsl_policy, approval_views
from test_dsl_configuration import world, ADMIN, document, candidate


def test_stale_stop_confirmation_never_closes_new_generation(world):
    world.run(world.a)
    row=store.get(world.a['id'])
    expected={k:row[k] for k in ('generation','policy_hash')}
    store.update(row['id'],generation=uuid.uuid4().hex)
    path='/api/agent-instances/'+row['id']+'/stop'
    result=world.client.post(path,headers=ADMIN,json=expected)
    assert result.status_code==409 and '已经变化' in result.json()['detail']
    assert store.get(row['id'])['gate']=='open' and not world.calls
    fresh=store.get(row['id'])
    result=world.client.post(path,headers=ADMIN,json={k:fresh[k] for k in expected})
    assert result.status_code==200 and store.get(row['id'])['gate']=='closed'
    assert len(world.calls)==1


def test_existing_empty_stop_request_remains_compatible(world):
    world.run(world.a)
    path='/api/agent-instances/'+world.a['id']+'/stop'
    assert world.client.post(path,headers=ADMIN,json={}).status_code==200
    assert store.get(world.a['id'])['gate']=='closed'


def test_removal_approval_names_the_removed_document_and_retains_name_after_application(world):
    docs=[document(ident='remove'),document(ident='retain')]
    docs[0]['name']='验收依据保护';docs[1]['name']='环境凭据保护'
    p=candidate(world.a['id'],docs)
    dsl_policy.apply(world.a['id'],p['id'],p['proposal_hash'])
    removal=candidate(world.a['id'],docs[1:])
    names=approval_views.scopes()
    view=approval_views.project(removal,names)
    assert view['name']=='停用 验收依据保护'
    assert removal['result']['document_changes']['removed']==['验收依据保护']
    dsl_policy.apply(world.a['id'],removal['id'],removal['proposal_hash'])
    refreshed=next(p for p in dsl_policy.detail(world.a['id'])['proposals'] if p['id']==removal['id'])
    projected=approval_views.project(refreshed,names,full=True)
    assert projected['name']=='停用 验收依据保护'
    assert projected['document_changes']['removed']==['验收依据保护']
    assert [d['name'] for d in dsl_policy.current(world.a['id'])['documents']]==['环境凭据保护']

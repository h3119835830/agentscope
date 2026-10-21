import uuid
from pathlib import Path
import pytest
from agentscope_app.instances import store,write_permissions as writes
from agentscope_app.instances.policy import digest
from test_dsl_configuration import world,ADMIN


def request(world,paths):
    row=store.get(world.a['id'])
    return {'paths':paths,'reason':'仅场景源码及验收产物','generation':row['generation'],
            'base_hash':row['policy_hash'],'request_key':uuid.uuid4().hex}


def test_operator_request_preserves_test_denies_and_waits_for_approval(world):
    root=Path(world.a['resources'][0]);(root/'src').mkdir();(root/'tests').mkdir()
    deny={'action':'write','effect':'deny','target':str(root/'tests'),'text':'tests protected'}
    policy={'rules':[deny],'network':'disabled'}
    store.update(world.a['id'],policy=policy,local_policy=policy,policy_hash=digest(policy))
    body=request(world,['/w/0/src'])
    result=writes.propose(world.a['id'],body)
    assert result['state']=='pending' and result['classification']=='expand'
    assert result['approval_id']=='instance:'+result['id']
    assert store.get(world.a['id'])['policy']==policy and not world.calls
    assert writes.propose(world.a['id'],body)['id']==result['id']
    from agentscope_app import db
    import json
    with db.connect() as con:
        saved=json.loads(con.execute('SELECT policy_json FROM instance_proposals WHERE id=?',(result['id'],)).fetchone()[0])
    assert deny in saved['rules'] and saved['network']=='disabled'


@pytest.mark.parametrize('kind',['root','outside','missing','link','two_ranges','long','denied','stale'])
def test_unrepresentable_or_unsafe_request_is_rejected_without_authority_change(world,kind):
    root=Path(world.a['resources'][0]);(root/'src').mkdir();(root/'artifacts').mkdir()
    paths=['/w/0/src']
    if kind=='root':paths=['/w/0']
    if kind=='outside':paths=[str(Path(world.b['resources'][0]))]
    if kind=='missing':paths=['/w/0/not-created']
    if kind=='link':(root/'alias').symlink_to(root/'src');paths=['/w/0/alias']
    if kind=='two_ranges':paths=['/w/0/src','/w/0/artifacts']
    if kind=='long':(root/('a'*65)).mkdir();paths=['/w/0/'+'a'*65]
    if kind=='denied':
        p={'rules':[{'action':'write','effect':'deny','target':str(root/'src'),'text':'protected'}],'network':'model_only'}
        store.update(world.a['id'],policy=p,local_policy=p,policy_hash=digest(p))
    body=request(world,paths)
    if kind=='stale':body['base_hash']='0'*64
    before=store.get(world.a['id'])
    with pytest.raises(ValueError):writes.propose(world.a['id'],body)
    after=store.get(world.a['id'])
    assert after['policy']==before['policy'] and after['generation']==before['generation'] and not world.calls


def test_write_request_is_admin_only_and_no_approval_or_apply_fields_are_accepted(world):
    path='/api/agent-instances/'+world.a['id']+'/write-permissions'
    assert world.client.get(path).status_code in (401,403)
    response=world.client.get(path,headers=ADMIN)
    assert response.status_code==200 and response.json()['instance_id']==world.a['id']
    product=world.client.get('/api/console/agents/'+world.a['id']+'/write-permissions',headers=ADMIN)
    assert product.status_code==200 and product.json()==response.json()
    body=request(world,['/w/0/src'])
    assert world.client.post(path+'/proposals',headers=ADMIN,json={**body,'approved':True}).status_code==422


def mapped_request(world):
    root=Path(world.a['resources'][0]);project=root/('scene-'+'q'*65)/'project'
    for name in ('src','acceptance-artifacts','tests'):(project/name).mkdir(parents=True)
    (project/'tests/test.py').write_text('immutable\n')
    body=request(world,[str(project/'src'),str(project/'acceptance-artifacts')])
    return project,{**body,'short_paths':[str(project)],'protected_paths':[str(project/'tests')]}


def test_mapping_approval_is_separate_from_apply_and_does_not_open_parent(world):
    from agentscope_app.instances import approval_views,approval_decisions,resource_views
    project,body=mapped_request(world)
    before=store.get(world.a['id']);result=writes.propose(world.a['id'],body)
    assert result['classification']=='expand' and result['state']=='pending'
    assert writes.propose(world.a['id'],body)['id']==result['id']
    approval=approval_views.detail(result['approval_id'])
    assert not approval['can_apply'] and approval['can_approve']
    assert sum(c['label'].startswith('新增精确资源映射') for c in approval['change_items'])==3
    receipt=approval_decisions.approve(result['approval_id'],approval['candidate_hash'],uuid.uuid4().hex)
    assert store.get(world.a['id'])['policy']==before['policy'] and not world.calls
    applied=approval_decisions.apply(result['approval_id'],approval['candidate_hash'],receipt['approval_hash'],uuid.uuid4().hex)
    assert applied['state']=='applied'
    row=store.get(world.a['id'])
    allows=[r['target'] for r in row['policy']['rules'] if r['effect']=='allow']
    assert sorted(allows)==sorted([str(project/'src'),str(project/'acceptance-artifacts')])
    assert any(r['target']==str(project/'tests') and r['effect']=='deny' for r in row['policy']['rules'])
    assert resource_views.validate(row['policy']['resource_views'],row['resources'])
    assert (project/'tests/test.py').read_text()=='immutable\n'


def test_mapping_directory_replacement_invalidates_approval_without_loading(world):
    from agentscope_app.instances import approval_views,approval_decisions
    project,body=mapped_request(world);result=writes.propose(world.a['id'],body)
    approval=approval_views.detail(result['approval_id'])
    receipt=approval_decisions.approve(result['approval_id'],approval['candidate_hash'],uuid.uuid4().hex)
    (project/'src').rename(project/'retained-src');(project/'src').mkdir()
    with pytest.raises(ValueError):
        approval_decisions.apply(result['approval_id'],approval['candidate_hash'],receipt['approval_hash'],uuid.uuid4().hex)
    assert not store.get(world.a['id'])['policy'].get('resource_views') and not world.calls


def test_agent_cannot_propose_mapping_or_include_tests_in_write_scope(world):
    from agentscope_app.instances import controller,resource_views
    project,body=mapped_request(world)
    with pytest.raises(ValueError,match='相互包含'):
        writes.propose(world.a['id'],{**body,'paths':[str(project)]})
    p={'rules':[],'network':'model_only','resource_views':resource_views.freeze(world.a['resources'],[str(project)])}
    with pytest.raises(ValueError,match='运行时 Agent'):
        controller.proposals(world.a['id'],{k:v for k,v in body.items() if k in ('generation','base_hash','request_key')}|{'policy':p},actor='agent')
    assert not world.calls

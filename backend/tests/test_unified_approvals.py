"""Public approval boundary: proposing/reading/rejecting never installs authority."""
import hashlib,json,uuid
import pytest
from agentscope_app import db,console
from agentscope_app.instances import approval_views as approvals,controller as c,store,system_policy as system,dsl_policy as dsl
from test_dsl_configuration import world,candidate,ADMIN
from test_managed_review import runtime_job,healthy_broker

def propose(row,actor='user'):
    return c.proposals(row['id'],{'generation':row['generation'],'base_hash':row['policy_hash'],'request_key':uuid.uuid4().hex,'policy':{'network':'disabled','rules':[]}},actor)

def decide(client,ident,p,decision='confirm',headers=ADMIN):
    return client.post('/api/console/approvals/'+ident+'/'+decision,json={'proposal_hash':p['proposal_hash']},headers=headers)

def apply_approved(client,ident,p):
    from agentscope_app.instances.approval_decisions import receipts
    receipt=receipts()[ident]
    return client.post('/api/console/approvals/'+ident+'/apply',headers=ADMIN,json={
        'proposal_hash':p['proposal_hash'],'approval_hash':receipt['approval_hash'],'request_key':uuid.uuid4().hex})

@pytest.mark.parametrize('actor',['user'])
@pytest.mark.parametrize('running',[False,True])
def test_native_restriction_is_pending_even_for_an_open_agent_tool(world,actor,running):
    if running:world.run(world.a)
    before=store.get(world.a['id']);p=propose(before,actor)
    assert p['state']=='pending' and not world.calls
    ident='instance:'+p['id'];page=approvals.directory();row=next(r for r in page['records'] if r['id']==ident)
    assert row['scope_type']=='agent' and row['can_approve'] and not row['can_apply'] and row['origin']==('runtime' if actor=='agent' else 'manual')
    detail=world.client.get('/api/console/approvals/'+ident,headers=ADMIN).json()
    assert detail['change_items'][0]['after'].startswith('禁止模型')
    assert store.get(world.a['id'])==before and not world.calls
    assert decide(world.client,ident,p,headers={}).status_code==401
    assert store.get(world.a['id'])==before

def test_native_only_exact_confirmation_applies_and_other_instance_unchanged(world):
    before=store.get(world.b['id']);p=propose(world.a);ident='instance:'+p['id']
    assert decide(world.client,ident,{**p,'proposal_hash':'0'*64}).status_code==409
    assert not world.calls and store.get(world.a['id'])['policy']['network']=='model_only'
    assert decide(world.client,ident,p).json()['state']=='approved'
    assert not world.calls
    assert apply_approved(world.client,ident,p).status_code==200
    assert store.get(world.a['id'])['policy']['network']=='disabled' and store.get(world.b['id'])==before
    calls=list(world.calls)
    assert decide(world.client,ident,p).status_code==200 and world.calls==calls
    assert approvals.detail(ident)['status']=='applied'
    assert approvals.detail(ident)['change_items']==[{'label':'网络访问','before':'仅模型与控制连接','after':'禁止模型和外部网络，保留控制连接'}]

def test_same_workspace_instances_still_have_distinct_confirmation_fingerprints(world):
    other=store.create('Same name','dsh',world.a['resources'])
    first=propose(world.a);second=propose(other)
    assert first['proposal_hash']!=second['proposal_hash']
    assert decide(world.client,'instance:'+second['id'],first).status_code==409
    assert not world.calls and store.get(other['id'])['policy']['network']=='model_only'

def test_native_rejection_never_quiesces_and_cannot_later_apply(world):
    before=store.get(world.a['id']);p=propose(before);ident='instance:'+p['id']
    assert decide(world.client,ident,p,'reject').status_code==200
    assert decide(world.client,ident,p,'reject').status_code==200
    assert decide(world.client,ident,p).status_code==409
    assert store.get(world.a['id'])==before and not world.calls
    with pytest.raises(ValueError):c.reject(world.b['id'],p['id'],p['proposal_hash'])

@pytest.mark.parametrize('drift',['resources','binding','dsl'])
def test_native_frozen_context_rejects_drift_and_all_read_counts_agree(world,drift):
    p=propose(world.a);ident='instance:'+p['id']
    if drift=='resources':store.update(world.a['id'],resources=world.b['resources'])
    elif drift=='binding':store.update(world.a['id'],runtime={'pid':12345})
    else:
        with db.connect() as con:con.execute('INSERT INTO instance_dsl_scopes VALUES(?,?,?,?,?,?)',(world.a['id'],1,'[]',dsl.current(world.a['id'])['document_hash'],'ready',db.now()))
    before=store.get(world.a['id'])
    assert approvals.detail(ident)['status']=='stale'
    assert decide(world.client,ident,p).status_code==409
    assert approvals.pending_count()==approvals.directory()['pending_count']
    assert not next(r for r in approvals.directory()['records'] if r['id']==ident)['can_apply']
    assert not world.calls and store.get(world.a['id'])==before

def test_old_unsnapshotted_pending_candidate_is_visible_but_cannot_apply(world):
    p=propose(world.a)
    with db.connect() as con:con.execute('DELETE FROM instance_proposal_contexts WHERE proposal_id=?',(p['id'],))
    assert approvals.detail('instance:'+p['id'])['status']=='stale'
    with pytest.raises(ValueError):c.apply(world.a['id'],p['id'],p['proposal_hash'])
    assert not world.calls

def test_system_typed_and_dsl_proposals_share_approval_contract(world):
    base=system.current();p=system.propose({'policy':{'rules':[],'network':'disabled'},'base_hash':base['policy_hash'],'revision':base['revision'],'request_key':uuid.uuid4().hex})
    ident='system:'+p['id'];d=candidate(world.a['id'])
    assert {'system_policy','dsl'}<={r['kind'] for r in approvals.directory()['records']}
    assert decide(world.client,ident,p,'reject').status_code==200
    assert system.current()==base and not world.calls
    assert decide(world.client,d['id'],d).json()['state']=='approved'
    assert apply_approved(world.client,d['id'],d).status_code==200
    assert dsl.current(world.a['id'])['revision']==1

def test_system_approval_retains_original_before_after_once_applied(world):
    base=system.current();p=system.propose({'policy':{'rules':[],'network':'disabled'},'base_hash':base['policy_hash'],'revision':base['revision'],'request_key':uuid.uuid4().hex})
    ident='system:'+p['id'];before=approvals.detail(ident)['change_items']
    assert decide(world.client,ident,p).json()['state']=='approved'
    assert system.current()==base
    assert apply_approved(world.client,ident,p).status_code==200
    assert system.current()['policy']['network']=='disabled'
    assert approvals.detail(ident)['change_items']==before and before

def test_task_or_generator_credential_cannot_decide_an_approval(world):
    token=uuid.uuid4().hex;generation='a'*32
    store.update(world.a['id'],generation=generation,gate='open',token_hash=hashlib.sha256(token.encode()).hexdigest())
    before=store.get(world.a['id']);p=propose(before,'user')
    assert decide(world.client,'instance:'+p['id'],p,headers={'Authorization':'Bearer '+token}).status_code==401
    assert store.get(world.a['id'])==before and not world.calls

def test_runtime_instance_tool_creates_an_agent_shared_candidate_without_applying(world):
    before=store.get(world.a['id'])
    p=propose(before,'agent');row=approvals.detail('instance:'+p['id'])
    assert row['scope_type']=='agent' and row['origin']=='runtime' and row['status']=='pending'
    assert row['scope_label']=='此 Agent 的共享执行域 · 全部工作区与会话'
    assert row['can_approve'] and not row['can_apply']
    assert store.get(world.a['id'])==before and not world.calls

def test_agent_runtime_proposal_is_reviewed_for_the_frozen_shared_agent_domain(world):
    before=store.get(world.a['id']);p=propose(before)
    with db.connect() as con:con.execute('UPDATE instance_proposals SET actor=? WHERE id=?',('agent',p['id']))
    ident='instance:'+p['id'];row=approvals.detail(ident)
    assert row['scope_type']=='agent' and row['origin']=='runtime' and row['status']=='pending'
    assert row['target']['instance_id']==world.a['id'] and row['target']['session_id'] is None
    assert decide(world.client,ident,p).status_code==200
    assert approvals.detail(ident)['status']=='approved'
    assert store.get(world.a['id'])==before and not world.calls


def test_automatic_runtime_delta_is_read_only_in_unified_approval_history(runtime_job,client,monkeypatch):
    from agentscope_app.managed import controller as managed
    task,_,job,proposal=runtime_job;calls=[]
    monkeypatch.setattr(managed,'broker',healthy_broker(calls))
    managed.finish_job(job)
    row=approvals.detail('runtime:'+job['id'])
    assert row['status']=='applied' and not row['can_apply'] and not row['can_reject']
    before=len(calls)
    response=client.post('/api/console/approvals/runtime:'+job['id']+'/confirm',headers=ADMIN,json={'proposal_hash':proposal['hash']})
    assert response.status_code==200 and len(calls)==before

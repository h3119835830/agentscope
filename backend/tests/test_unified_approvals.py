"""Public approval boundary: proposing/reading/rejecting never installs authority."""
import hashlib,json,uuid
import pytest
from agentscope_app import db,console
from agentscope_app.instances import approval_views as approvals,controller as c,store,system_policy as system,dsl_policy as dsl
from test_dsl_configuration import world,candidate,ADMIN
from test_managed_review import pending,install_mock

def propose(row,actor='user'):
    return c.proposals(row['id'],{'generation':row['generation'],'base_hash':row['policy_hash'],'request_key':uuid.uuid4().hex,'policy':{'network':'disabled','rules':[]}},actor)

def decide(client,ident,p,decision='confirm',headers=ADMIN):
    return client.post('/api/console/approvals/'+ident+'/'+decision,json={'proposal_hash':p['proposal_hash']},headers=headers)

@pytest.mark.parametrize('actor',['user','agent'])
@pytest.mark.parametrize('running',[False,True])
def test_native_restriction_is_pending_even_for_an_open_agent_tool(world,actor,running):
    if running:world.run(world.a)
    before=store.get(world.a['id']);p=propose(before,actor)
    assert p['state']=='pending' and not world.calls
    ident='instance:'+p['id'];page=approvals.directory();row=next(r for r in page['records'] if r['id']==ident)
    assert row['scope_type']=='agent' and row['can_apply'] and row['origin']==('runtime' if actor=='agent' else 'manual')
    detail=world.client.get('/api/console/approvals/'+ident,headers=ADMIN).json()
    assert detail['change_items'][0]['after'].startswith('禁止模型')
    assert store.get(world.a['id'])==before and not world.calls
    assert decide(world.client,ident,p,headers={}).status_code==401
    assert store.get(world.a['id'])==before

def test_native_only_exact_confirmation_applies_and_other_instance_unchanged(world):
    before=store.get(world.b['id']);p=propose(world.a);ident='instance:'+p['id']
    assert decide(world.client,ident,{**p,'proposal_hash':'0'*64}).status_code==409
    assert not world.calls and store.get(world.a['id'])['policy']['network']=='model_only'
    assert decide(world.client,ident,p).status_code==200
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
    assert decide(world.client,d['id'],d).status_code==200
    assert dsl.current(world.a['id'])['revision']==1

def test_system_approval_retains_original_before_after_once_applied(world):
    base=system.current();p=system.propose({'policy':{'rules':[],'network':'disabled'},'base_hash':base['policy_hash'],'revision':base['revision'],'request_key':uuid.uuid4().hex})
    ident='system:'+p['id'];before=approvals.detail(ident)['change_items']
    assert decide(world.client,ident,p).status_code==200
    assert system.current()['policy']['network']=='disabled'
    assert approvals.detail(ident)['change_items']==before and before

def test_task_or_generator_credential_cannot_decide_an_approval(world):
    token=uuid.uuid4().hex;generation='a'*32
    store.update(world.a['id'],generation=generation,gate='open',token_hash=hashlib.sha256(token.encode()).hexdigest())
    before=store.get(world.a['id']);p=propose(before,'agent')
    assert decide(world.client,'instance:'+p['id'],p,headers={'Authorization':'Bearer '+token}).status_code==401
    assert store.get(world.a['id'])==before and not world.calls

@pytest.mark.parametrize('kind',['restrict','expand'])
def test_runtime_candidate_is_visible_read_only_then_human_confirmed_once(pending,client,monkeypatch,kind):
    from agentscope_app.managed import controller as managed
    task,state,job,put=pending;p=put(kind);calls=[];install_mock(monkeypatch,calls)
    ident='runtime:'+job['id'];body={'proposal_hash':p['hash']}
    with db.connect() as con:before=managed.load(con,task)
    row=next(r for r in approvals.directory()['records'] if r['id']==ident)
    assert row['scope_type']=='session' and row['origin']=='runtime' and row['can_apply']
    detail=client.get('/api/console/approvals/'+ident,headers=ADMIN).json()
    assert detail['change_items'] and detail['targets'][0]['scope_label']=='当前任务会话'
    assert 'context_json' not in detail and 'proposal_json' not in detail
    assert client.post('/api/console/approvals/'+ident+'/confirm',json=body).status_code==401
    assert not calls
    with db.connect() as con:assert managed.load(con,task)==before
    assert client.post('/api/console/approvals/'+ident+'/confirm',headers=ADMIN,json=body).status_code==200
    assert approvals.detail(ident)['status']=='applied' and calls==[task]
    assert client.post('/api/console/approvals/'+ident+'/confirm',headers=ADMIN,json=body).status_code==200 and calls==[task]

def test_runtime_reject_preserves_loaded_scope_and_baseline(pending,client,monkeypatch):
    from agentscope_app.managed import controller as managed
    task,state,job,put=pending;p=put();calls=[];install_mock(monkeypatch,calls)
    ident='runtime:'+job['id']
    assert client.post('/api/console/approvals/'+ident+'/reject',headers=ADMIN,json={'proposal_hash':p['hash']}).status_code==200
    with db.connect() as con:after=managed.load(con,task)
    assert not calls and after['baseline_hash']==state['baseline_hash'] and after['version']==state['version']
    assert after['allowed_write_dirs']==state['allowed_write_dirs'] and after['gate']=='waiting_clarification'
    assert approvals.detail(ident)['status']=='rejected'

@pytest.mark.parametrize('drift',['revision','session_id','domain_id'])
def test_runtime_stale_candidate_cannot_install(pending,client,monkeypatch,drift):
    from agentscope_app.managed import controller as managed
    task,_,job,put=pending;p=put();calls=[];install_mock(monkeypatch,calls)
    with db.connect() as con:
        s=managed.load(con,task)
        if drift=='revision':s['revision']+=1
        elif drift=='session_id':s['session_id']='different-session'
        else:s['binding']['domain_id']=1000
        managed.save(con,task,s)
    # Bind the session in this fixture as production enqueue does.
    with db.connect() as con:
        ctx=json.loads(job['context_json']);ctx['session_id']='native-a'
        con.execute('UPDATE managed_jobs SET context_json=? WHERE id=?',(json.dumps(ctx),job['id']))
    ident='runtime:'+job['id']
    assert approvals.detail(ident)['status']=='stale'
    assert client.post('/api/console/approvals/'+ident+'/confirm',headers=ADMIN,json={'proposal_hash':p['hash']}).status_code==409
    assert not calls

def test_hidden_runtime_task_absent_from_directory_detail_and_decision(pending,client):
    task,_,job,put=pending;p=put();console.retain([('task',task)],'isolated approval visibility test')
    ident='runtime:'+job['id']
    assert ident not in {r['id'] for r in approvals.directory()['records']}
    assert client.get('/api/console/approvals/'+ident,headers=ADMIN).status_code==404
    assert client.post('/api/console/approvals/'+ident+'/confirm',headers=ADMIN,json={'proposal_hash':p['hash']}).status_code==404

def test_legacy_runtime_record_without_fingerprint_does_not_break_approval_center(pending,client,monkeypatch):
    task,_,job,put=pending;p=put();del p['hash']
    with db.connect() as con:con.execute('UPDATE managed_jobs SET proposal_json=? WHERE id=?',(json.dumps(p),job['id']))
    ident='runtime:'+job['id']
    monkeypatch.setattr(__import__('agentscope_app.managed.controller',fromlist=['install']),'install',lambda *a,**k:pytest.fail('legacy record cannot install'))
    page=client.get('/api/console/approvals',headers=ADMIN)
    assert page.status_code==200
    row=next(r for r in page.json()['records'] if r['id']==ident)
    assert row['status']=='invalid' and not row['can_apply'] and not row['can_reject']
    assert client.get('/api/console/approvals/'+ident,headers=ADMIN).status_code==200
    assert client.post('/api/console/approvals/'+ident+'/confirm',headers=ADMIN,json={'proposal_hash':'invented'}).status_code==409

def test_runtime_without_frozen_session_cannot_use_current_session_as_authority(pending,client,monkeypatch):
    from agentscope_app.managed import controller as managed
    task,_,job,put=pending;p=put();calls=[];install_mock(monkeypatch,calls)
    ctx=json.loads(job['context_json']);ctx.pop('session_id');ctx['current_binding'].pop('session_id')
    with db.connect() as con:con.execute('UPDATE managed_jobs SET context_json=? WHERE id=?',(json.dumps(ctx),job['id']))
    assert approvals.detail('runtime:'+job['id'])['status']=='stale'
    with pytest.raises(ValueError,match='会话快照'):managed.review_change(task,job['id'],'approve',p['hash'])
    assert not calls

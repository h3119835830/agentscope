import copy
import uuid
import pytest
from agentscope_app.instances import template_configurations as tc, template_catalog as catalog, dsl_policy as dsl, policy_library, approval_decisions as decisions
from test_dsl_configuration import world, ADMIN
from test_template_configurations import clean_templates, config, Provider, plan_body
from test_policy_library import config as system_config
from test_policy_workspace_references import reference, read, generated

def batch(scope,rows,**changes):
    base=dsl.current(scope)
    return dict(scope_id=scope,selections=[{'id':r['id'],'revision':r['revision']} for r in rows],
                base_revision=base['revision'],base_hash=base['document_hash'],request_key=uuid.uuid4().hex,
                operation='apply',acknowledge_coverage=False,**changes)

def test_mixed_legacy_and_template_batch_only_applies_after_separate_consent(world):
    old=policy_library.save({'kind':'structured','config':system_config(mode='exact',values='/w/0/secret'),'base_revision':0})
    new=tc.save('system',config(scope='system',name='全局员工资料保护'))
    body=batch('system',[old,new]);p=tc.propose_batch(body)
    assert p['state']=='pending' and len(p['items'])==2 and all(len(item['documents'])==1 for item in p['items']) and not world.calls
    assert tc.propose_batch(body)==p
    first=p['items'][0]
    receipt=decisions.confirm(first['id'],first['proposal_hash'])
    assert receipt['state']=='approved' and not world.calls and not dsl.current('system')['documents']
    result=decisions.apply(first['id'],first['proposal_hash'],receipt['approval_hash'],uuid.uuid4().hex)
    assert result['state']=='applied' and {d['id'] for d in dsl.current('system')['documents']}=={old['id']}
    second=tc.propose_batch(batch('system',[new]));receipt=decisions.approve(second['id'],second['proposal_hash'],uuid.uuid4().hex)
    decisions.apply(second['id'],second['proposal_hash'],receipt['approval_hash'],uuid.uuid4().hex)
    assert {d['id'] for d in dsl.current('system')['documents']}=={old['id'],new['id']}
    removal=batch('system',[new]);removal['operation']='disable';q=tc.propose_batch(removal)
    receipt=decisions.approve(q['id'],q['proposal_hash'],uuid.uuid4().hex)
    assert len(dsl.current('system')['documents'])==2
    decisions.apply(q['id'],q['proposal_hash'],receipt['approval_hash'],uuid.uuid4().hex)
    assert [d['id'] for d in dsl.current('system')['documents']]==[old['id']]

def test_cross_agent_batch_never_widens_target(world):
    a=tc.save(world.a['id'],config());b=tc.save(world.b['id'],config())
    with pytest.raises(ValueError,match='同一个'):tc.propose_batch(batch(world.a['id'],[a,b]))
    assert not world.calls and not dsl.current(world.a['id'])['documents']

def test_batch_versions_and_coverage_are_frozen(world):
    a=tc.save(world.a['id'],config(template='FILE-CHANGE',parameters={'target':'/w/0/staff.csv','operations':['unlink']}))
    with pytest.raises(ValueError,match='覆盖'):tc.propose_batch(batch(world.a['id'],[a]))
    body=batch(world.a['id'],[a]);body['acknowledge_coverage']=True;p=tc.propose_batch(body)
    tc.save(world.a['id'],{**config(template='FILE-CHANGE',parameters={'target':'/w/0/staff.csv','operations':['unlink']}),'base_revision':1,'name':'参数修改'},a['id'])
    with pytest.raises(ValueError):decisions.approve(p['id'],p['proposal_hash'],uuid.uuid4().hex)
    assert not world.calls

def test_published_v2_supports_both_scopes_without_rewriting_v1(world):
    assert catalog.get('FILE-READ',1)['scopes']==['agent','workspace']
    assert catalog.get('FILE-READ',2)['scopes']==['system','agent']
    old=tc.save(world.a['id'],config(template_version=1))
    assert old['template_definition']['version']==1
    with pytest.raises(ValueError):tc.save('system',config(template_version=1,scope='system'))
    with pytest.raises(ValueError):tc.save(world.a['id'],config(name=''))

def test_all_agent_assistant_saves_same_drafts_and_cannot_approve(world):
    item={k:v for k,v in config(scope='system').items() if k in ('template_id','template_version','name','parameters')}
    result=tc.generate('system',{**plan_body(),'scope':'system'},Provider({'configurations':[item],'questions':[],'gaps':[]}))
    assert result['items'][0]['scope_id']=='system' and result['items'][0]['status']=='draft'
    assert not decisions.receipts() and not world.calls

def test_native_cannot_submit_batch_or_global_assistant(world):
    row=tc.save(world.a['id'],config())
    for route,payload in [('/api/policy-template-configurations/proposals',batch(world.a['id'],[row])),
                          ('/api/policy-template-configurations/generate',dict(scope_id='system',scope='system',text='禁止读取员工资料',request_key=uuid.uuid4().hex))]:
        assert world.client.post(route,headers={'Authorization':'Bearer native'},json=payload).status_code==401

def test_batch_preserves_source_snapshot_validation_before_approval(reference):
    world,root,_=reference
    result,_=generated(reference)
    p=tc.propose_batch(batch(world.a['id'],result['items']))
    assert p['state']=='pending'
    (root/'README.md').write_text('场景资料已经更新')
    with pytest.raises(ValueError):decisions.approve(p['id'],p['proposal_hash'],uuid.uuid4().hex)
    assert not world.calls

def test_stale_reference_does_not_prevent_explicit_disable(reference):
    world,root,_=reference
    result,_=generated(reference)
    p=tc.propose_batch(batch(world.a['id'],result['items']))
    receipt=decisions.approve(p['id'],p['proposal_hash'],uuid.uuid4().hex)
    decisions.apply(p['id'],p['proposal_hash'],receipt['approval_hash'],uuid.uuid4().hex)
    (root/'README.md').write_text('场景资料已经更新')
    removal=batch(world.a['id'],result['items']);removal['operation']='disable'
    q=tc.propose_batch(removal)
    receipt=decisions.approve(q['id'],q['proposal_hash'],uuid.uuid4().hex)
    decisions.apply(q['id'],q['proposal_hash'],receipt['approval_hash'],uuid.uuid4().hex)
    assert not dsl.current(world.a['id'])['documents']

def test_agent_reference_cannot_be_reused_as_all_agent_generation(reference):
    world,_,_=reference
    receipt=read(reference)
    provider=Provider({'configurations':[],'questions':[],'gaps':[]})
    with pytest.raises(ValueError,match='作用范围'):
        tc.generate('system',{**plan_body(),'scope':'system','reference_read_id':receipt['id']},provider)
    assert not provider.calls and not world.calls


@pytest.mark.parametrize('scope_kind,legacy', [('system',False),('agent',False),('system',True)])
def test_row_disable_http_flow_requires_approval_then_explicit_apply_and_preserves_other_drafts(world,scope_kind,legacy):
    scope = 'system' if scope_kind=='system' else world.a['id']
    def post(path, body):
        response=world.client.post(path,headers=ADMIN,json=body)
        assert response.status_code==200,response.text
        return response.json()
    def listing():
        data=policy_library.directory() if legacy else tc.directory(scope)
        return {r['id']:r for r in data['items']}
    def submit(rows, operation='apply'):
        body=batch(scope,rows);body['operation']=operation
        return post('/api/policy-template-configurations/proposals',body)
    def approve(p):
        return post('/api/console/approvals/'+p['id']+'/approve',{'proposal_hash':p['proposal_hash'],'request_key':uuid.uuid4().hex})
    def apply(p,receipt):
        return post('/api/console/approvals/'+p['id']+'/apply',{'proposal_hash':p['proposal_hash'],'approval_hash':receipt['approval_hash'],'request_key':uuid.uuid4().hex})
    if legacy:
        a=policy_library.save({'kind':'structured','config':system_config(mode='exact',values='/w/0/staff.csv'),'base_revision':0})
        b=policy_library.save({'kind':'structured','config':system_config(mode='exact',values='/w/0/budget.csv',name='预算保护'),'base_revision':0})
    else:
        a=tc.save(scope,config(scope=scope_kind));b=tc.save(scope,config(scope=scope_kind,name='预算保护',parameters={'target':'/w/0/budget.csv'}))
    p=submit([a]);assert not world.calls
    assert listing()[a['id']]['approval_id']==p['id'] and listing()[a['id']]['status']=='pending'
    receipt=approve(p)
    assert listing()[a['id']]['status']=='approved' and not dsl.current(scope)['documents'] and not world.calls
    apply(p,receipt)
    other_policy=submit([b]);apply(other_policy,approve(other_policy))
    if legacy:
        edited=policy_library.save({'kind':'structured','config':{**a['config'],'effect':'notify','values':'/w/0/new-draft.csv'},'base_revision':1},a['id'])
    else:
        edited=tc.save(scope,config(scope=scope_kind,base_revision=1,name='未应用新版',parameters={'target':'/w/0/new-draft.csv'}),a['id'])
    row=listing()[a['id']]
    assert row['applied_revision']==1 and row['approval_id']==p['id'] and row['approval_revision']==1 and not row['approval_current']
    assert row['status'] in ('draft','library')
    assert (row['applied_configuration']['config']['effect'] if legacy else row['applied_configuration']['parameters']['target'])==('block' if legacy else '/w/0/staff.csv')
    before=dsl.current(scope);other=dsl.current(world.b['id']);calls=list(world.calls)
    off=submit([edited],'disable')
    assert {d['id'] for d in off['documents']}=={b['id']}
    assert listing()[a['id']]['approval_id']==off['id'] and listing()[a['id']]['status']=='pending'
    assert dsl.current(scope)==before and world.calls==calls
    unapproved=world.client.post('/api/console/approvals/'+off['id']+'/apply',headers=ADMIN,json={'proposal_hash':off['proposal_hash'],'approval_hash':'0'*64,'request_key':uuid.uuid4().hex})
    assert unapproved.status_code==409 and dsl.current(scope)==before
    receipt=approve(off)
    assert listing()[a['id']]['status']=='approved' and dsl.current(scope)==before and world.calls==calls
    bad=world.client.post('/api/console/approvals/'+off['id']+'/apply',headers=ADMIN,json={'proposal_hash':off['proposal_hash'],'approval_hash':'0'*64,'request_key':uuid.uuid4().hex})
    assert bad.status_code==409 and dsl.current(scope)==before
    apply(off,receipt)
    assert [d['id'] for d in dsl.current(scope)['documents']]==[b['id']]
    assert dsl.current(world.b['id'])==other
    assert (policy_library.get(a['id']) if legacy else tc.load(a['id']))['revision']==2
    assert listing()[a['id']]['applied_revision'] is None


def test_configuration_approval_links_require_exact_identity_scope_and_revision(world):
    from agentscope_app import db
    from agentscope_app.instances.configuration_approvals import link
    a=tc.save(world.a['id'],config());b=tc.save(world.b['id'],config())
    p=tc.propose_batch(batch(world.a['id'],[a]))
    with db.connect() as con:
        assert link(con,a['id'],1,world.a['id'],'template')['approval_id']==p['id']
        assert link(con,a['id'],1,world.b['id'],'template')['approval_id'] is None
        assert link(con,b['id'],1,world.b['id'],'template')['approval_id'] is None
        old=link(con,a['id'],2,world.a['id'],'template')
        assert old['approval_id']==p['id'] and not old['approval_current'] and old['approval_revision']==1
    assert not world.calls

"""Runtime evidence is presentation; retired templates cannot regain authority."""
import copy,json,uuid
import pytest
from agentscope_app import db
from agentscope_app.instances import template_catalog as catalog,template_configurations as tc,template_versions as versions,template_support as support,dsl_policy as dsl,approval_decisions
from agentscope_app.instances.policy import digest
from test_dsl_configuration import world,ADMIN
from test_template_configurations import clean_templates,config,proposal

def legacy(world,ident):
    t=catalog.get(ident,2)
    parameters={p['key']:p['default'] for p in t['parameters']}
    if ident=='RQ1-CHECK':parameters.update(target='/w/0/code',checker='pytest')
    body=config(ident,parameters=parameters)
    ident='legacy_'+uuid.uuid4().hex
    payload=tc.materialize(ident,world.a['id'],body)
    with db.connect() as con:tc.insert(con,ident,world.a['id'],body,payload)
    return tc.view(tc.load(ident)),body

@pytest.mark.parametrize('ident',['RQ1-CHECK','RQ1-GIT'])
def test_retired_manual_create_edit_submit_batch_revalidation_and_template_edit_rejected(world,ident):
    row,body=legacy(world,ident)
    before=copy.deepcopy(tc.load(row['id']))
    with pytest.raises(ValueError,match='历史模板'):tc.save(world.a['id'],body)
    with pytest.raises(ValueError,match='历史模板'):tc.save(world.a['id'],{**body,'base_revision':1},row['id'])
    with pytest.raises(ValueError,match='历史模板'):proposal(row)
    base=dsl.current(world.a['id'])
    with pytest.raises(ValueError,match='历史模板'):
        tc.propose_batch({'scope_id':world.a['id'],'selections':[{'id':row['id'],'revision':1}],'operation':'apply','base_revision':0,'base_hash':base['document_hash'],'request_key':uuid.uuid4().hex})
    with pytest.raises(ValueError,match='历史模板'):tc.revalidate_proposal(world.a['id'],{'selections':[{'id':row['id'],'revision':1}]})
    t=next(t for t in catalog.public_catalog() if t['id']==ident)
    edit={'name':t['name'],'description':t['description'],'effect':t['effect'],'parameters':[{'key':p['key'],'label':p['label'],'default':str(p['default'])} for p in t['parameters']],'base_version':t['version'],'request_key':uuid.uuid4().hex}
    with pytest.raises(ValueError,match='历史模板'):versions.save(ident,edit)
    response=world.client.post('/api/policy-template-configurations',headers=ADMIN,json={**body,'scope_id':world.a['id']})
    assert response.status_code==409 and '历史模板' in response.text
    assert tc.load(row['id'])==before and row['read_only'] and not row['can_submit']
    assert not world.calls and not dsl.current(world.a['id'])['documents']

def test_retired_pending_approval_and_direct_apply_cannot_bypass_guard(world):
    row,_=legacy(world,'RQ1-GIT')
    base=dsl.current(world.a['id'])
    pending=dsl.propose(world.a['id'],{'documents':[row['document']],'base_revision':base['revision'],'base_hash':base['document_hash'],'request_key':uuid.uuid4().hex})
    assert pending['state']=='pending'
    tc.bind_proposal(pending['id'],[{'id':row['id'],'revision':1,'document_hash':digest(row['document']),'operation':'apply'}])
    with pytest.raises(ValueError):approval_decisions.approve(pending['id'],pending['proposal_hash'],uuid.uuid4().hex)
    with pytest.raises(ValueError,match='历史模板'):dsl.apply(world.a['id'],pending['id'],pending['proposal_hash'])
    assert not world.calls and not dsl.current(world.a['id'])['documents']

def test_retired_applied_configuration_remains_and_disable_still_needs_approval(world):
    row,_=legacy(world,'RQ1-GIT')
    docs=[row['document']]
    with db.connect() as con:
        con.execute('INSERT INTO instance_dsl_scopes VALUES(?,1,?,?,?,?)',(world.a['id'],json.dumps(docs),digest(docs),'ready',db.now()))
    viewed=tc.view(tc.load(row['id']))
    assert viewed['read_only'] and not viewed['can_submit'] and viewed['applied_revision']==1
    off=proposal(viewed,operation='disable')
    assert off['state']=='pending' and off['documents']==[]
    assert dsl.current(world.a['id'])['documents']==docs and not world.calls

def test_every_current_template_has_explicit_runtime_record_or_unsupported_status(world):
    templates=catalog.public_catalog()
    assert len(templates)==37
    for t in templates:
        facts=t['execution_support']
        assert facts['supported'] or facts['unsupported']
        if t['id'].startswith('GIT-') and facts['status']=='unsupported':
            assert facts['verification']['state']=='rejected' and not facts['applicable']
        else:
            assert facts['verification']['state']=='verified',t['id']
            assert facts['verification']['cases']>0
        if t.get('retired'):assert facts['status']=='legacy' and not facts['applicable']

def test_runtime_proof_is_bound_to_execution_contract_and_cannot_be_model_filled(world):
    t=catalog.get('FILE-READ',2)
    proof=support.evidence(t)
    assert proof and set(proof['effects'])=={'block','notify','kill'}
    renamed=copy.deepcopy(t);renamed['name']='different';renamed['reason']='different';renamed['parameters'][0]['label']='different';renamed['version']=99
    assert support.evidence(renamed)==proof
    forged=copy.deepcopy(t);forged['renderer']='remote'
    assert support.evidence(forged) is None
    forged['execution_support']={'verification':{'state':'verified'}}
    assert support.evidence(forged) is None

def test_action_without_passing_record_cannot_submit_or_apply(world,monkeypatch):
    monkeypatch.setattr(support,'evidence',lambda definition:{'effects':['notify']})
    with pytest.raises(ValueError,match='真实运行验收'):support.ensure_applicable(catalog.get('FILE-READ',2),'block')
    support.ensure_applicable(catalog.get('FILE-READ',2),'notify')
    support.ensure_applicable(catalog.get('FILE-READ',2),'block',removing=True)

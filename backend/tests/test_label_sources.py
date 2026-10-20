import copy
import uuid
import pytest
from agentscope_app import db
from agentscope_app.instances import label_sources as labels,template_catalog as catalog,template_configurations as tc,dsl_policy as dsl
from test_dsl_configuration import world,ADMIN
from test_template_configurations import config,proposal


def body(scope, **extra):
    return dict(scope_id=scope,label='SECRET',matcher='exact',value='/w/0/secret.txt',
                base_version=0,request_key=uuid.uuid4().hex,**extra)


def flow(**extra):
    version=next(t['version'] for t in catalog.public_catalog() if t['id']=='SECRET-EGRESS')
    return config('SECRET-EGRESS',**{'template_version':version,'parameters':{'target':'/w/0/secret.txt','endpoint':'127.0.0.1'},**extra})


def test_scoped_preview_respects_requested_effect_without_persisting(world):
    from agentscope_app.instances import template_dsl
    request={**flow(),'scope_id':world.a['id'],'effect':'notify'}
    result=template_dsl.preview('SECRET-EGRESS',request)
    assert result['state']=='complete'
    assert 'notify connect' in result['dsl'] and 'source SECRET' in result['dsl']
    assert labels.directory()['sources']==[]
    request['effect']='allow'
    assert template_dsl.preview('SECRET-EGRESS',request)['state']=='invalid'


def test_parameter_only_document_does_not_crash_label_directory(world):
    from test_template_configurations import config
    template=next(t for t in catalog.public_catalog() if t.get('execution_support',{}).get('applicable') is False and not t.get('retired'))
    parameters={p['key']:p.get('default','') for p in template['parameters']}
    # Preserve the real saved schema of unsupported drafts without inventing a
    # compiled document. This exercises the read model, not template semantics.
    with db.connect() as con:
        tc.insert(con,'parameter-only',world.a['id'],config(template['id']),
                  {'name':'参数草案','document':None,'parameters':parameters,'label_sources':[]})
    assert labels.directory()['sources']==[]


def test_registration_is_metadata_only_and_agent_is_reserved(world):
    first=labels.save(body(world.a['id']))
    second=labels.save(body(world.a['id']))
    assert first==second
    assert not world.calls and not dsl.current(world.a['id'])['documents']
    response=world.client.post('/api/security/label-sources',headers=ADMIN,json={**body(world.a['id']),'label':'AGENT'})
    assert response.status_code==422
    assert world.client.get('/api/security/labels',headers={'Authorization':'Bearer native'}).status_code==401
    assert world.client.post('/api/security/label-sources',headers={'Authorization':'Bearer native'},json=body(world.a['id'])).status_code==401


def test_automatic_reuse_and_non_sensitive_templates_do_not_register(world):
    plain=tc.save(world.a['id'],config())
    assert 'label_sources' not in plain
    first=tc.save(world.a['id'],flow())
    second=tc.save(world.a['id'],flow())
    assert first['label_source_refs']==second['label_source_refs']
    assert 'source SECRET' in first['document']['original_dsl']
    assert 'SENSITIVE' not in first['document']['original_dsl']
    assert first['label_sources']==first['document']['label_sources']
    assert labels.directory(world.a['id'])['labels'][1]['configuration_count']==2
    assert not world.calls


def test_versions_are_immutable_and_do_not_stale_prior_approval(world):
    config_a=tc.save(world.a['id'],flow())
    original=copy.deepcopy(config_a)
    pending=proposal(config_a)
    assert pending['state']=='pending',pending['result']
    ref=config_a['label_sources'][0]
    updated=labels.save({**body(world.a['id']),'base_version':1,'value':'/w/0/other.txt'},ref['id'])
    assert updated['version']==2
    tc.verify_proposal(pending['id'])
    assert tc.load(config_a['id'])['document']==original['document']
    assert not dsl.current(world.a['id'])['documents']
    assert pending['documents'][0]['label_sources'][0]['version']==1
    labels.archive(ref['id'],2)
    tc.verify_proposal(pending['id'])
    assert labels.directory(world.a['id'])['sources'][0]['references']


def test_explicit_refs_are_target_isolated_and_do_not_merge_registry(world):
    first=labels.save(body(world.a['id']))
    other=labels.save({**body(world.a['id']),'value':'/w/0/other.txt'})
    selected=tc.save(world.a['id'],{**flow(),'parameters':{'target':'','endpoint':'127.0.0.1'},
                                'label_source_refs':[{'id':first['id'],'version':1}]})
    assert selected['label_sources']==[first]
    assert other['value'] not in selected['document']['original_dsl']
    with pytest.raises(ValueError,match='其他'):
        tc.save(world.b['id'],{**flow(),'label_source_refs':selected['label_source_refs']})
    b=labels.save(body(world.b['id']))
    assert b['id']!=first['id']
    with pytest.raises(ValueError,match='普通保护'):
        tc.save(world.a['id'],{**config(),'label_source_refs':selected['label_source_refs']})
    p=proposal(selected)
    assert p['state']=='pending',p['result']
    assert p['documents'][0]['label_sources']==[first]


def test_old_sensitive_dsl_and_namespaces_unchanged(world):
    old=tc.save(world.a['id'],config('SECRET-EGRESS',parameters={'target':'/w/0/secret.txt','endpoint':'*'}))
    new=tc.save(world.a['id'],flow())
    assert 'SENSITIVE' in old['document']['original_dsl'] and 'label_sources' not in old
    from dsl_documents import prepare
    parsed=prepare([{**x['document'],'scope_id':world.a['id']} for x in (old,new)],world.a['resources'],'**/node')
    assert 'SENSITIVE' in parsed[0]['effective_dsl']
    assert 'SECRET' in parsed[1]['effective_dsl']
    assert parsed[0]['effective_dsl']!=parsed[1]['effective_dsl']


def test_directory_versions_idempotency_and_bad_paths(world):
    request={**body(world.a['id']),'matcher':'directory','value':'/w/0/private'}
    saved=labels.save(request)
    assert saved['patterns']==['/w/0/private','/w/0/private/**']
    assert labels.save(request)==saved
    with pytest.raises(Exception):
        labels.save({**request,'value':'/w/0/changed'})
    with pytest.raises(ValueError):
        labels.save({**body(world.a['id']),'value':'/etc/shadow'})
    with pytest.raises(ValueError):
        labels.save({**body(world.a['id']),'value':'/w/0/*'})
    with pytest.raises(Exception):
        labels.save({**request,'base_version':0,'request_key':uuid.uuid4().hex},saved['id'])


def test_editing_a_path_does_not_retain_old_automatic_source_or_modify_b(world):
    a=tc.save(world.a['id'],flow())
    b=tc.save(world.a['id'],flow())
    changed=tc.save(world.a['id'],flow(base_revision=1,parameters={'target':'/w/0/new.txt','endpoint':'127.0.0.1'}),a['id'])
    assert len(changed['label_sources'])==1 and changed['label_sources'][0]['value']=='/w/0/new.txt'
    assert changed['selected_label_source_refs']==[]
    assert tc.load(b['id'])['document']==b['document']
    assert tc.load(a['id'],1)['document']==a['document']


def test_archive_between_resolution_and_configuration_transaction_rejects(world,monkeypatch):
    saved=labels.save(body(world.a['id']))
    resolve=labels.resolve
    def race(*args,**kwargs):
        result=resolve(*args,**kwargs)
        labels.archive(saved['id'],1)
        return result
    monkeypatch.setattr(labels,'resolve',race)
    with pytest.raises(ValueError,match='归档'):
        tc.save(world.a['id'],{**flow(),'label_source_refs':[{'id':saved['id'],'version':1}]})
    assert not tc.directory(world.a['id'])['items']


def test_new_secret_assistant_and_manual_share_source_instantiation(world):
    from test_template_configurations import Provider,plan_body
    chosen={k:v for k,v in flow().items() if k in ('template_id','template_version','name','reason','parameters')}
    provider=Provider({'configurations':[chosen],'questions':[],'gaps':[]})
    generated=tc.generate(world.a['id'],plan_body(),provider)['items'][0]
    manual=tc.save(world.a['id'],{**flow(),**chosen})
    assert generated['label_sources']==manual['label_sources']
    assert generated['parameters']==manual['parameters']
    assert not world.calls

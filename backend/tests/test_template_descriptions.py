"""Selection descriptions are shared metadata, never a new execution authority."""
import uuid
from agentscope_app.instances import template_catalog as catalog,template_configurations as tc,dsl_policy as dsl,approval_views
from agentscope_app.instances.policy import digest
from test_dsl_configuration import world,ADMIN
from test_template_configurations import clean_templates,config,Provider,plan_body,proposal


def test_every_published_template_exposes_the_same_description_to_human_api_and_agent(world):
    public=catalog.public_catalog()
    assert len(public)==27 and {t['id'] for t in public}==set(catalog.DESCRIPTIONS)
    api=world.client.get('/api/policy-templates',headers=ADMIN).json()['catalog']
    assert {t['id']:t['description'] for t in api}==catalog.DESCRIPTIONS
    assert all(40<=len(t['description'])<=600 for t in public)
    item={k:v for k,v in config().items() if k in ('template_id','template_version','name','parameters')}
    provider=Provider({'configurations':[item],'questions':[],'gaps':[]})
    result=tc.generate(world.a['id'],{**plan_body(),'context_mode':'none'},provider)
    offered=provider.calls[0]['templates']
    assert all(t['description']==catalog.DESCRIPTIONS[t['id']] for t in offered)
    assert next(t for t in offered if t['id']=='FILE-READ')['parameters']==catalog.get('FILE-READ',2)['parameters']
    assert result['items'][0]['status']=='draft' and not result['items'][0]['applied']
    assert not world.calls and not dsl.current(world.a['id'])['documents']


def test_description_changes_do_not_rewrite_versioned_definitions_or_stale_approved_candidates(world,monkeypatch):
    definitions={(t['id'],version):digest(catalog.get(t['id'],version)) for t in catalog.public_catalog() for version in (1,2)}
    row=tc.save(world.a['id'],config());p=proposal(row)
    from agentscope_app.instances import approval_decisions as decisions
    decisions.approve(p['id'],p['proposal_hash'],uuid.uuid4().hex)
    before=tc.generation_basis(world.a)
    monkeypatch.setitem(catalog.DESCRIPTIONS,'FILE-READ','新的模板选择说明，仅作为描述元数据，不改变现有路径参数、读取操作和处置动作。')
    assert before!=tc.generation_basis(world.a)
    assert all(digest(catalog.get(ident,version))==value for (ident,version),value in definitions.items())
    assert all('description' not in catalog.get(ident,version) for ident,version in definitions)
    tc.verify_proposal(p['id'])
    assert approval_views.detail(p['id'])['status']=='approved'
    assert not world.calls and not dsl.current(world.a['id'])['documents']


def test_description_is_not_accepted_as_a_model_selected_execution_parameter(world):
    item={k:v for k,v in config().items() if k in ('template_id','template_version','name','parameters')}
    item['parameters']['description']='授予额外权限'
    provider=Provider({'configurations':[item],'questions':[],'gaps':[]})
    import pytest
    with pytest.raises(ValueError):tc.generate(world.a['id'],{**plan_body(),'context_mode':'none'},provider)
    assert not tc.directory(world.a['id'])['items'] and not world.calls

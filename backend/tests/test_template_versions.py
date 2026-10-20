import copy
import uuid
import pytest
from fastapi import HTTPException
from agentscope_app import db
from agentscope_app.instances import template_catalog as catalog,template_versions as versions,template_configurations as tc,dsl_policy as dsl,approval_decisions,approval_views
from agentscope_app.instances.policy import digest
from test_dsl_configuration import world,ADMIN
from test_template_configurations import clean_templates,config,proposal


@pytest.fixture(autouse=True)
def empty_versions(client):
    with db.connect() as con:con.execute('DELETE FROM policy_template_versions')
    yield
    with db.connect() as con:con.execute('DELETE FROM policy_template_versions')


def edit(ident='FILE-READ',effect='notify'):
    t=next(t for t in catalog.public_catalog() if t['id']==ident)
    return {'name':t['name']+'新版','description':'按实际场景选择参数，模板修改仅用于新的子配置，不改变已有策略。','effect':effect,
            'parameters':[{'key':p['key'],'label':p['label']+'设置','default':effect if p['type']=='effect' else p['default']} for p in t['parameters']],
            'base_version':t['version'],'request_key':uuid.uuid4().hex}


def test_save_keeps_approved_old_configurations_immutable_and_offers_latest_to_agent(world):
    before={(t['id'],v):digest(catalog.get(t['id'],v)) for t in catalog.public_catalog() for v in (1,2)}
    row=tc.save(world.a['id'],config());p=proposal(row);approval_decisions.approve(p['id'],p['proposal_hash'],uuid.uuid4().hex)
    basis=tc.generation_basis(world.a);body=edit();saved=versions.save('FILE-READ',body)
    assert saved['version']==3 and saved['name']==body['name'] and saved['effect']=='notify'
    assert next(t for t in catalog.public_catalog() if t['id']=='FILE-READ')['description']==body['description']
    assert tc.generation_basis(world.a)!=basis
    assert all(digest(catalog.get(ident,v))==value for (ident,v),value in before.items())
    tc.verify_proposal(p['id']);assert approval_views.detail(p['id'])['status']=='approved'
    newer=tc.save(world.a['id'],config(template_version=3))
    assert newer['effect']=='notify' and 'notify open' in newer['document']['original_dsl']
    assert tc.load(row['id'])['effect']=='block' and not world.calls and not dsl.current(world.a['id'])['documents']


def test_retry_and_competing_edit_are_atomic_and_versioned(world):
    body=edit();a=versions.save('FILE-READ',body)
    assert versions.save('FILE-READ',body)==a
    with pytest.raises(HTTPException) as error:versions.save('FILE-READ',{**body,'name':'变更'})
    assert error.value.status_code==409
    with pytest.raises(HTTPException) as error:versions.save('FILE-READ',{**body,'request_key':uuid.uuid4().hex})
    assert error.value.status_code==409
    next_body=edit();b=versions.save('FILE-READ',next_body)
    assert b['version']==4 and catalog.get('FILE-READ',3)['name']==body['name']


@pytest.mark.parametrize('change',[{'renderer':'custom'},{'scope':'system'},{'original_dsl':'invented'},{'effect':'allow'},
                                 {'parameters':[]},{'parameters':[{'key':'other','label':'路径','default':''}]}])
def test_unsupported_definition_changes_are_rejected_without_runtime_mutation(world,change):
    with pytest.raises(ValueError):versions.save('FILE-READ',{**edit(),**change})
    assert not versions.latest() and not world.calls


def test_api_is_admin_only_and_validates_defaults_and_type_contract(world):
    body=edit('SYS-env');route='/api/policy-templates/SYS-env/versions'
    assert world.client.post(route,headers={'Authorization':'Bearer native'},json=body).status_code==401
    bad=copy.deepcopy(body);bad['parameters'][0]['type']='path'
    assert world.client.post(route,headers=ADMIN,json=bad).status_code==422
    bad=copy.deepcopy(body);next(p for p in bad['parameters'] if p['key']=='operations')['default']='invented'
    assert world.client.post(route,headers=ADMIN,json=bad).status_code==409
    response=world.client.post(route,headers=ADMIN,json=body);assert response.status_code==200,response.text
    assert response.json()['version']==3 and response.json()['parameters'][-1]['default']=='notify'
    latest=world.client.get('/api/policy-templates',headers=ADMIN).json()['catalog']
    assert next(t for t in latest if t['id']=='SYS-env')['name']==body['name']
    assert not world.calls


@pytest.mark.parametrize('ident,parameters',[('WRITE-BOUNDARY',{'target':'/w/0','exception':'/w/0/reports'}),
 ('RQ1-GENERATED',{'target':'/w/0/out','producer':'python'}),('SECRET-EGRESS',{'target':'/w/0/staff.csv','endpoint':'*'}),
 ('REMOTE-EXEC',{'program':'bash'})])
def test_new_default_effect_is_reflected_by_each_fixed_renderer(world,ident,parameters):
    versions.save(ident,edit(ident))
    row=tc.save(world.a['id'],config(ident,template_version=3,parameters=parameters))
    clauses=[line.strip() for line in row['document']['original_dsl'].splitlines() if line.strip().startswith(('block ','notify ','kill '))]
    assert clauses and all(line.startswith('notify ') for line in clauses)
    assert row['effect']=='notify' and not world.calls

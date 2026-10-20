import json
import uuid
import pytest
from agentscope_app import db
from agentscope_app.instances import template_catalog as catalog,template_configurations as tc,template_versions as versions,template_dsl as preview,dsl_policy as dsl
from agentscope_app.instances.policy import digest
from test_dsl_configuration import world,ADMIN
from test_template_configurations import clean_templates,config,proposal,Provider,plan_body


def latest(ident):return next(t for t in catalog.public_catalog() if t['id']==ident)


@pytest.mark.parametrize('ident,command',[('GIT-COMMIT','commit'),('GIT-PUSH','push'),('GIT-COMMIT-CHECK','commit'),('GIT-PUSH-CHECK','push')])
def test_new_contract_locks_program_and_command_and_exposes_skeleton(world,ident,command):
    t=latest(ident)
    assert t['fixed_fields']=={'program':'git','command':command}
    assert 'program' not in {p['key'] for p in t['parameters']}
    assert 'exec "git" "'+command+'"' in t['dsl_preview']['dsl']
    assert 'block' in t['disabled_effects'] and 'block' not in t['allowed_effects']


@pytest.mark.parametrize('parameters',[{'effect':'block'},{'effect':'notify','program':'curl'},{'effect':'notify','command':'push'},{'effect':'notify','dsl':'block exec "*" if AGENT'}])
def test_save_and_preview_reject_fixed_field_or_block_tampering(world,parameters):
    t=latest('GIT-COMMIT')
    with pytest.raises(ValueError):tc.save(world.a['id'],config(t['id'],template_version=t['version'],parameters=parameters))
    if parameters=={'effect':'block'}:
        r=preview.preview(t['id'],{'template_version':t['version'],'parameters':parameters})
        assert r['state']=='invalid' and r['dsl'] is None
    else:
        with pytest.raises(ValueError):preview.preview(t['id'],{'template_version':t['version'],'parameters':parameters})
    assert not tc.directory()['items'] and not world.calls


def test_preview_is_readonly_uses_actual_renderer_and_shows_missing_values(world):
    t=latest('GIT-COMMIT-CHECK');params={'checker':'pytest','target':'/w/0/src/**','exit_code':0,'effect':'notify'}
    url='/api/policy-templates/'+t['id']+'/preview'
    payload={'template_version':t['version'],'parameters':params}
    assert world.client.post(url,headers={'Authorization':'Bearer native'},json=payload).status_code==401
    r=world.client.post(url,headers=ADMIN,json=payload);assert r.status_code==200,r.text
    result=r.json();assert result['preview_only'] and result['state']=='complete'
    assert 'notify exec "git" "commit"' in result['dsl'] and 'exits 0 since write' in result['dsl']
    assert not tc.directory()['items'] and not dsl.current(world.a['id'])['documents'] and not world.calls
    row=tc.save(world.a['id'],config(t['id'],template_version=t['version'],parameters=params,reason=t['reason']))
    assert result['dsl'].replace('config-preview','config-'+row['id'])==row['document']['original_dsl']
    assert proposal(row)['state']=='pending'
    missing=preview.preview(t['id'],{'template_version':t['version'],'parameters':{'effect':'kill','exit_code':'0','checker':'','target':''}})
    assert missing['state']=='incomplete' and '{{checker}}' in missing['dsl'] and '{{target}}' in missing['dsl']
    assert 'kill exec "git" "commit"' in missing['dsl']


def test_publisher_appends_after_user_version_without_rewriting_it(world):
    ident='GIT-COMMIT'
    with db.connect() as con:con.execute('DELETE FROM policy_template_versions WHERE template_id=?',(ident,))
    old=catalog.get(ident,2)
    body={'name':'旧自定义提交模板','description':catalog.DESCRIPTIONS[ident],'effect':'notify','parameters':[
        {'key':p['key'],'label':p['label'],'default':'notify' if p['key']=='effect' else 'customgit'} for p in old['parameters']],
        'base_version':2,'request_key':uuid.uuid4().hex}
    saved=versions.save(ident,body);old_hash=digest(catalog.get(ident,saved['version']))
    body=config(ident,template_version=saved['version'],parameters={'program':'customgit','effect':'notify'})
    payload=tc.materialize('legacy_git_fixture',world.a['id'],body)
    with db.connect() as con:tc.insert(con,'legacy_git_fixture',world.a['id'],body,payload)
    row=tc.load('legacy_git_fixture');p=proposal(row)
    with db.connect() as con:versions.publish_fixed_git(con)
    newer=latest(ident);assert newer['version']==4 and newer['fixed_fields']['program']=='git'
    assert digest(catalog.get(ident,3))==old_hash and tc.load(row['id'])['parameters']['program']=='customgit'
    tc.verify_proposal(p['id'])
    with db.connect() as con:
        count=con.execute('SELECT count(*) FROM policy_template_versions').fetchone()[0]
        versions.publish_fixed_git(con)
        assert con.execute('SELECT count(*) FROM policy_template_versions').fetchone()[0]==count


def test_agent_only_fills_variable_fields_and_snapshot_keeps_fixed_command(world):
    t=latest('GIT-PUSH')
    provider=Provider({'configurations':[{'template_id':t['id'],'template_version':t['version'],'name':'推送执行提醒','parameters':{'effect':'notify'}}],'questions':[],'gaps':[]})
    r=tc.generate(world.a['id'],{**plan_body(),'context_mode':'none'},provider)
    offered=next(t for t in provider.calls[0]['templates'] if t['id']=='GIT-PUSH')
    assert offered['fixed_fields']['command']=='push' and 'exec "git" "push"' in offered['dsl_preview']['dsl']
    assert r['configuration_snapshots'][0]['template']['fixed_fields']=={'program':'git','command':'push'}
    assert r['items'][0]['parameters']=={'effect':'notify'} and not world.calls


def test_old_template_cannot_be_used_to_bypass_fixed_command(world):
    with pytest.raises(ValueError,match='历史版本'):
        tc.save(world.a['id'],config('GIT-COMMIT',parameters={'program':'curl','effect':'notify'}))
    provider=Provider({'configurations':[{'template_id':'GIT-PUSH','template_version':2,'name':'降级绕过','parameters':{'program':'curl','effect':'notify'}}],'questions':[],'gaps':[]})
    with pytest.raises(ValueError,match='历史版本'):
        tc.generate(world.a['id'],{**plan_body(),'context_mode':'none'},provider)
    assert not tc.directory()['items'] and not world.calls


def test_unsupported_has_no_dsl_and_template_defaults_change_preview_not_authority(world):
    for t in catalog.public_catalog():
        p=t['dsl_preview']
        assert p['preview_only']
        if t.get('execution_support',{}).get('applicable') is False:assert p['state']=='unsupported' and p['dsl'] is None
        else:assert p['dsl']
    t=latest('GIT-PUSH-CHECK')
    result=preview.preview_definition(catalog.get(t['id'],t['version']),{'checker':'check','target':'/w/0/src/**','exit_code':'2','effect':'notify'},effect='notify')
    assert 'exits 2' in result['dsl'] and result['state']=='complete'
    assert not dsl.current(world.a['id'])['documents'] and not world.calls

"""Real compilation and fail-closed lifecycle contracts, never a UI-only option."""
import copy
import uuid
import pytest
from agentscope_app import db
from agentscope_app.instances import template_catalog as catalog,template_configurations as tc,template_versions as versions,dsl_policy as dsl,approval_decisions as decisions
from test_dsl_configuration import world, ADMIN
from test_template_configurations import config,proposal,Provider,plan_body,clean_templates


def git_config(ident,scope='agent',**parameters):
    t=next(t for t in catalog.public_catalog() if t['id']==ident)
    defaults={p['key']:p['default'] for p in t['parameters']}
    defaults.update(parameters)
    return config(ident,template_version=t['version'],scope=scope,parameters=defaults,name='订单项目 Git 安全要求')


@pytest.mark.parametrize('command',['commit','push'])
@pytest.mark.parametrize('scope',['agent','system'])
def test_commands_have_distinct_dsl_and_separate_approve_apply_disable(world,command,scope):
    scope_id=world.a['id'] if scope=='agent' else 'system'
    saved=tc.save(scope_id,git_config('GIT-'+command.upper(),scope,effect='notify'))
    text=saved['document']['original_dsl']
    assert 'notify exec "git" "'+command+'" if AGENT' in text
    assert ('"push"' if command=='commit' else '"commit"') not in text
    p=proposal(saved);assert p['state']=='pending' and not world.calls and not dsl.current(scope_id)['documents']
    decisions.approve(p['id'],p['proposal_hash'],uuid.uuid4().hex)
    assert not dsl.current(scope_id)['documents']
    dsl.apply(scope_id,p['id'],p['proposal_hash'])
    assert [d['id'] for d in dsl.current(scope_id)['documents']]==[saved['id']]
    off=proposal(saved,operation='disable');assert off['state']=='pending'
    assert dsl.current(scope_id)['documents']
    decisions.approve(off['id'],off['proposal_hash'],uuid.uuid4().hex)
    assert dsl.current(scope_id)['documents']
    dsl.apply(scope_id,off['id'],off['proposal_hash'])
    assert not dsl.current(scope_id)['documents']


@pytest.mark.parametrize('command',['commit','push'])
def test_check_exit_and_invalidator_reach_real_compiler(world,command):
    from dsl_documents import prepare
    row=tc.save(world.a['id'],git_config('GIT-'+command.upper()+'-CHECK',target='/w/0/src/**',checker='pytest',exit_code='0'))
    text=row['document']['original_dsl']
    assert 'unless after exec "pytest" exits 0 since write "/w/0/src/**"' in text
    assert row['parameters']['exit_code']==0
    compiled=prepare([{**row['document'],'scope_id':world.a['id']}],world.a['resources'],'**/node')
    assert compiled and proposal(row)['state']=='pending' and not world.calls
    assert '暂存区' in ' '.join(row['execution_support']['unsupported'])


def test_selected_tokens_only_and_no_fake_preexec_block(world):
    row=tc.save(world.a['id'],git_config('GIT-LOCAL',tokens=['clean'],effect='notify'))
    assert '"clean"' in row['document']['original_dsl'] and '"reset"' not in row['document']['original_dsl']
    with pytest.raises(ValueError):tc.save(world.a['id'],git_config('GIT-LOCAL',tokens=['--hard']))
    with pytest.raises(ValueError):tc.save(world.a['id'],git_config('GIT-COMMIT',effect='block'))
    with pytest.raises(ValueError):tc.save(world.a['id'],git_config('GIT-COMMIT',program='git -C /tmp/repo'))
    for value in (True,-1,256,'1.0','nan'):
        with pytest.raises(ValueError):tc.save(world.a['id'],git_config('GIT-COMMIT-CHECK',target='/w/0/src/**',checker='pytest',exit_code=value))


@pytest.mark.parametrize('ident,parameters',[
 ('GIT-CONTENT',{'repository':'/w/0','forbidden_paths':'.env\nkeys/**'}),
 ('GIT-PUSH-TARGET',{'repository':'/w/0','remote':'https://example.test/repo','branches':'refs/heads/task/*'}),
 ('GIT-PUSH-APPROVAL',{'repository':'/w/0','commit':'a'*40,'remote':'https://example.test/repo','branch':'main'}),
 ('GIT-MERGE-GATE',{'repository':'/w/0','branches':'main','checks':'unit-tests','issuer':'trusted-ci'})])
def test_unsupported_drafts_cannot_reach_any_approval_path(world,ident,parameters):
    row=tc.save(world.a['id'],git_config(ident,**parameters))
    assert row['document'] is None and not row['can_submit']
    with pytest.raises(ValueError,match='暂不支持'):proposal(row)
    base=dsl.current(world.a['id'])
    with pytest.raises(ValueError,match='暂不支持'):
        tc.propose_batch({'scope_id':world.a['id'],'base_revision':base['revision'],'base_hash':base['document_hash'],
            'selections':[{'id':row['id'],'revision':1}],'operation':'apply','request_key':uuid.uuid4().hex})
    with pytest.raises(ValueError,match='暂不支持'):
        tc.revalidate_proposal(world.a['id'],{'selections':[{'id':row['id'],'revision':1}]})
    with db.connect() as con:
        assert not con.execute('SELECT 1 FROM instance_dsl_proposals').fetchone()
    assert not world.calls and not dsl.current(world.a['id'])['documents']


def test_agent_receives_actual_capabilities_and_unsupported_snapshot(world):
    selection={k:v for k,v in git_config('GIT-CONTENT',repository='/w/0',forbidden_paths='.env').items() if k in ('template_id','template_version','name','parameters')}
    provider=Provider({'configurations':[selection],'questions':[],'gaps':[]})
    result=tc.generate(world.a['id'],{**plan_body(),'context_mode':'none'},provider)
    offered=provider.calls[0]['templates']
    assert not {'RQ1-GIT','RQ1-CHECK'} & {t['id'] for t in offered}
    assert next(t for t in offered if t['id']=='GIT-CONTENT')['execution_support']['applicable'] is False
    assert result['gaps'] and result['configuration_snapshots'][0]['execution_support']['applicable'] is False
    row=result['items'][0];assert row['origin']=='assistant' and row['document'] is None
    assert not world.calls


def test_editing_defaults_does_not_change_execution_contract_or_existing_child(world):
    t=next(t for t in catalog.public_catalog() if t['id']=='GIT-COMMIT-CHECK')
    body={'name':t['name'],'description':t['description'],'effect':'notify','parameters':[
        {'key':p['key'],'label':p['label'],'default':'notify' if p['type']=='effect' else '2' if p['key']=='exit_code' else p['default']} for p in t['parameters']],
        'base_version':t['version'],'request_key':uuid.uuid4().hex}
    saved=versions.save(t['id'],body)
    assert saved['version']==t['version']+1 and saved['execution_support']==t['execution_support']
    wrong=copy.deepcopy(body);wrong.update(base_version=saved['version'],request_key=uuid.uuid4().hex,effect='block')
    with pytest.raises(ValueError):versions.save(t['id'],wrong)
    values={p['key']:p['default'] for p in saved['parameters']}
    values.update(target='/w/0/src/**',checker='pytest',effect='notify',exit_code='2')
    row=tc.save(world.a['id'],{**config(t['id'],parameters=values),'template_version':saved['version']})
    assert ' exits 2 since write ' in row['document']['original_dsl']
    with db.connect() as con:con.execute("DELETE FROM policy_template_versions WHERE template_id=?",(t['id'],))

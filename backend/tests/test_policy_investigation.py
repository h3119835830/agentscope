"""Real reader/compiler/matcher tests; no model, Broker or Agent execution."""
import copy
import json
from pathlib import Path
import pytest
from agentscope_app.instances import policy_investigation as tools,template_tools,store
from agentscope_app.instances.policy_context_agent import WorkspacePolicyAgent,ToolContractError,ToolBudgetExhausted
from agentscope_app.instances.policy import digest,default_policy
from test_policy_workspace_references import reference
from test_dsl_configuration import world


class Native:
    def run_agent(self,*args):raise AssertionError('These tests do not call a model')


@pytest.fixture(autouse=True)
def exact_test_components(monkeypatch):
    root=Path(__file__).resolve().parents[2]
    monkeypatch.setenv('AGENTSCOPE_COMPILE_PREVIEW_BIN',str(root/'actplane/target/release/actplane'))
    monkeypatch.setenv('AGENTSCOPE_MATCH_PREVIEW_BIN',str(root/'backend/dsl-adapter/target/release/agentscope-match-preview'))


def runner(reference,enabled=True):
    world,root,body=reference
    return WorkspacePolicyAgent(world.a['id'],Native(),lambda:None,enabled=enabled),body['workspace_id'],root


def invoke(r,tool,workspace,**args):
    return r.execute({'tool':tool,'arguments':{'workspace_id':workspace,**args}})['result']


def draft(r,ident,parameters):
    name='draft_'+ident.lower().replace('-','_')
    return r.execute({'tool':name,'arguments':{'name':'隔离验证','parameters':parameters}})['result']['configuration']


def check(target,operation='write',scope='tree',role='invalidation',expected=True,**extra):
    return {'target':target,'operation':operation,'scope':scope,'role':role,'expected_match':expected,**extra}


def final(configuration):
    return {'configurations':[configuration],'questions':[],'gaps':[]}


def test_search_discovers_nested_source_without_reading_credentials(reference):
    r,w,root=runner(reference)
    (root/'src').mkdir();(root/'src/native.rs').write_text('pub fn distinctive() {}')
    (root/'.env').write_text('token=fixture-only');(root/'alias.rs').symlink_to(root/'src/native.rs')
    found=invoke(r,'search_project',w,query='native.rs',mode='path')
    assert [item['relative_path'] for item in found['matches']]==['src/native.rs']
    assert not r.references and not found['truncated']
    body=invoke(r,'read_files',w,paths=['src/native.rs'])
    assert 'distinctive' in body['untrusted_project_files'][0]['text']


def test_literal_content_search_returns_sanitized_receipted_evidence(reference):
    r,w,root=runner(reference)
    (root/'module.go').write_text('package demo\n// distinctive-symbol\ntoken=fixture-only-value\n')
    response=invoke(r,'search_project',w,query='distinctive-symbol',mode='content')
    assert response['matches'][0]['line']==2 and r.references
    assert 'fixture-only-value' not in json.dumps(r.references)
    assert not invoke(r,'search_project',w,query='fixture-only-value',mode='content')['matches']


def test_content_search_has_continuation_cursor_and_cumulative_budget(reference):
    r,w,root=runner(reference)
    for index in range(12):(root/f'{index:02d}.txt').write_text('needle')
    first=invoke(r,'search_project',w,query='needle',mode='content')
    assert first['files_scanned']==8 and first['next_cursor'] is not None
    second=invoke(r,'search_project',w,query='needle',mode='content',cursor=first['next_cursor'])
    assert not second['next_cursor'] and len(first['matches'])+len(second['matches'])==12


def test_resource_inspection_distinguishes_objects_and_returns_mapping(reference):
    r,w,root=runner(reference)
    (root/'src').mkdir();(root/'src/code.py').write_text('pass')
    response=invoke(r,'inspect_resource',w,paths=['src','src/code.py','absent.py'])
    directory,file,missing=response['resources']
    assert directory['kind']=='directory' and file['kind']=='file'
    assert file['execution_path']=='/w/0/src/code.py' and missing['exists'] is None
    assert directory['samples'] and not r.references
    assert '不自动递归' in response['matching_semantics']['literal']


@pytest.mark.parametrize('tool,args',[
    ('search_project',{'query':'x','mode':'path','path':'../outside'}),
    ('inspect_resource',{'paths':['/etc']}),
    ('inspect_resource',{'paths':['.env']}),
    ('inspect_resource',{'paths':['.git']}),
    ('inspect_resource',{'paths':['key.pem']}),
    ('search_project',{'query':'x','mode':'regex'}),
    ('search_project',{'query':'x','mode':'path','command':'id'}),
])
def test_investigation_rejects_escape_and_extra_authority(reference,tool,args):
    r,w,_=runner(reference)
    with pytest.raises((ValueError,ToolContractError)):invoke(r,tool,w,**args)


def test_search_honors_read_denials_and_hides_subtree(reference):
    r,w,root=runner(reference)
    (root/'vault').mkdir();(root/'vault/data.py').write_text('forbidden-needle')
    policy={**default_policy(),'rules':[{'action':'read','target':str(root/'vault'),'effect':'deny','text':'禁止'}]}
    store.update(r.ident,policy=policy,policy_hash=digest(policy))
    response=invoke(r,'search_project',w,query='vault',mode='path')
    assert not response['matches'] and not r.references


def test_cross_agent_workspaces_rejected_before_investigation(reference):
    r,_,_=runner(reference)
    with pytest.raises(ToolContractError,match='不属于'):invoke(r,'inspect_resource','foreign',paths=['README.md'])


def test_disabled_context_does_not_gain_new_tools(reference):
    r,w,_=runner(reference,False)
    with pytest.raises(ToolContractError,match='未开放'):invoke(r,'search_project',w,query='x',mode='path')


def test_template_tool_schema_preserves_types_and_distinguishes_validation(reference):
    definitions=template_tools.definitions()
    gate=next(item for item in definitions if item['template_id']=='GIT-COMMIT-CHECK')
    params=gate['input_schema']['properties']['parameters']['properties']
    assert params['exit_code']['type']=='integer' and params['effect']['enum']==['notify','kill']
    change=next(item for item in definitions if item['template_id']=='FILE-CHANGE')
    assert change['input_schema']['properties']['parameters']['properties']['operations']['type']=='array'
    r,_,_=runner(reference)
    result=r.execute({'tool':'draft_exec_block','arguments':{'name':'隔离','parameters':{'program':'git'}}})['result']
    assert result['validated'] and not result['coverage_verified'] and result['validation_scope']=='template_parameters_only'


def test_real_compiler_preview_exposes_directory_miss_and_agent_can_revise(reference):
    r,w,root=runner(reference);(root/'src').mkdir();(root/'src/code.py').write_text('pass')
    before=store.get(r.ident)
    bad=draft(r,'GIT-COMMIT-CHECK',{'target':'/w/0/src','checker':'pytest','exit_code':0,'effect':'kill'})
    bad_frozen=copy.deepcopy(bad)
    result=invoke(r,'preview_policy_matches',w,configuration=bad,checks=[check('src')])
    assert not result['coverage_checks_passed'] and all(not sample['matched'] for sample in result['checks'])
    with pytest.raises(ToolContractError,match='尚未通过'):r.validate_final(final(bad))
    good=draft(r,'GIT-COMMIT-CHECK',{'target':'/w/0/src/**','checker':'pytest','exit_code':0,'effect':'kill'})
    result=invoke(r,'preview_policy_matches',w,configuration=good,checks=[check('src'),check('tests',expected=False)])
    assert result['coverage_checks_passed'] and not result['runtime_enforcement_verified']
    r.validate_final(final(good))
    assert bad==bad_frozen and store.get(r.ident)==before


def test_exec_preview_checks_actual_program_and_negative_sample(reference):
    r,w,_=runner(reference)
    candidate=draft(r,'EXEC-BLOCK',{'program':'git'})
    result=invoke(r,'preview_policy_matches',w,configuration=candidate,checks=[check('git','exec','object','target'),check('bash','exec','object','target',False)])
    assert result['coverage_checks_passed'] and not result['policy_applied']
    r.validate_final(final(candidate))


def test_file_preview_retains_write_unlink_group_and_no_application(reference):
    r,w,_=runner(reference)
    candidate=draft(r,'FILE-CHANGE',{'target':'/w/0/README.md','operations':['write','unlink']})
    result=invoke(r,'preview_policy_matches',w,configuration=candidate,checks=[check('README.md','unlink','object','target'),check('other.md','write','object','target',False)])
    assert result['coverage_checks_passed']


def test_network_preview_is_numeric_and_performs_no_network_io(reference):
    r,w,_=runner(reference)
    candidate=draft(r,'NET-BLOCK',{'endpoint':'10.10.'})
    result=invoke(r,'preview_policy_matches',w,configuration=candidate,checks=[check('10.10.1.2','connect','object','target'),check('10.11.1.2','connect','object','target',False)])
    assert result['coverage_checks_passed']


def test_no_preview_cannot_be_submitted_as_verified(reference):
    r,_,_=runner(reference);candidate=draft(r,'EXEC-BLOCK',{'program':'git'})
    with pytest.raises(ToolContractError,match='尚未通过'):r.validate_final(final(candidate))
    r.validate_final({'configurations':[],'questions':[],'gaps':['真实能力缺口']})


def test_model_cannot_supply_free_dsl_or_foreign_candidate_to_preview(reference):
    r,w,_=runner(reference)
    with pytest.raises(ToolContractError,match='原候选'):
        invoke(r,'preview_policy_matches',w,configuration={'dsl':'rule injected'},checks=[check('src')])


@pytest.mark.parametrize('checks',[
    [check('/etc/passwd')], [check('src',expected=False)],
    [check('src/../outside')], [check('src',role='invented')],
])
def test_unsafe_or_vacuous_preview_checks_cannot_pass(reference,checks):
    r,w,_=runner(reference);candidate=draft(r,'FILE-CHANGE',{'target':'/w/0/src/**','operations':['write','unlink']})
    with pytest.raises(ToolContractError):invoke(r,'preview_policy_matches',w,configuration=candidate,checks=checks)


def test_parameter_change_invalidates_preview(reference):
    r,w,_=runner(reference);candidate=draft(r,'EXEC-BLOCK',{'program':'git'})
    invoke(r,'preview_policy_matches',w,configuration=candidate,checks=[check('git','exec','object','target')])
    changed=copy.deepcopy(candidate);changed['parameters']['program']='bash'
    with pytest.raises(ToolContractError,match='本轮|已发布'):r.validate_final(final(changed))


def test_preview_cannot_self_confirm_a_guessed_resource(reference):
    r,w,_=runner(reference)
    candidate=draft(r,'FILE-READ',{'target':'/w/0/guessed.db'})
    with pytest.raises(ToolContractError,match='缺少.*依据'):
        invoke(r,'preview_policy_matches',w,configuration=candidate,checks=[check('guessed.db','open','object','target')])


def test_explicit_operator_future_path_can_be_previewed_without_claiming_existence(reference):
    r,w,_=runner(reference);r.requirements='保护计划中的 future.txt，禁止修改与删除。'
    candidate=draft(r,'FILE-CHANGE',{'target':'/w/0/future.txt','operations':['write','unlink']})
    result=invoke(r,'preview_policy_matches',w,configuration=candidate,checks=[check('future.txt','write','object','target')])
    assert result['coverage_checks_passed'] and not result['runtime_enforcement_verified']


def test_source_logical_id_does_not_establish_a_local_resource(reference):
    r,w,root=runner(reference)
    (root/'scene.md').write_text('External object id is fixture-object-id, not a filesystem mapping.')
    invoke(r,'list_directory',w)
    invoke(r,'read_files',w,paths=['scene.md'])
    candidate=draft(r,'FILE-CHANGE',{'target':'/w/0/fixture-object-id','operations':['unlink']})
    with pytest.raises(ToolContractError,match='逻辑对象标识'):
        invoke(r,'preview_policy_matches',w,configuration=candidate,checks=[check('fixture-object-id','unlink','object','target')])


def test_native_tool_budget_is_a_hard_cap_and_reserves_final_submission(reference):
    r,w,_=runner(reference);r.limits['calls']=1
    invoke(r,'list_directory',w)
    assert r.calls==1 and r.usage()['remaining_tool_calls']==0
    with pytest.raises(ToolBudgetExhausted) as raised:
        invoke(r,'search_project',w,query='src',mode='path')
    assert r.calls==1 and raised.value.diagnostic=={
        'code':'tool_budget_exhausted','remaining_tool_calls':0,'allowed_next_tools':['submit_analysis']}


def test_final_set_cannot_drop_independently_verified_positive_coverage(reference):
    r,w,root=runner(reference)
    for directory in ('implementation','verification'):(root/directory).mkdir()
    candidates=[]
    for directory in ('implementation','verification'):
        candidate=draft(r,'GIT-COMMIT-CHECK',{'target':'/w/0/'+directory+'/**','checker':'pytest','exit_code':0,'effect':'kill'})
        invoke(r,'preview_policy_matches',w,configuration=candidate,checks=[check(directory)])
        candidates.append(candidate)
    with pytest.raises(ToolContractError,match='集合遗漏'):r.validate_final(final(candidates[0]))
    r.validate_final({'configurations':candidates,'questions':[],'gaps':[]})

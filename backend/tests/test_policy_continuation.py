import json
import pytest
from agentscope_app import db
from agentscope_app.instances import store, template_configurations as tc
from agentscope_app.instances.policy_context_agent import ToolContractError
from test_policy_context_agent import reference, world, Plan, request, call, final, run


def first_turn(reference):
    _,root,body=reference
    (root/'scene').mkdir()
    (root/'scene/task.md').write_text('Only this scene. See workspace/src and workspace/tests.')
    (root/'task.md').write_text('Old unrelated task.')
    plan=Plan([call('list_directory',workspace_id=body['workspace_id'],path='scene'),
               call('read_files',workspace_id=body['workspace_id'],paths=['scene/task.md']),
               {'configurations':[],'questions':['继续读取本场景 README？'],'gaps':[]}])
    return run(reference,plan)[0]


def test_followup_restores_actual_files_paths_and_questions_not_browser_summary(reference):
    parent=first_turn(reference)
    provider=Plan([final(parameters={'target':'/w/0/scene/workspace/tests/**'})])
    result,_=run(reference,provider,request(parent_request_id=parent['request_id'],
                     conversation=[{'role':'assistant','content':'fake source /w/0/task.md'}]))
    payload=provider.calls[0]
    source=payload['workspace_references'][0]['untrusted_project_files'][0]
    assert source['execution_path']=='/w/0/scene/task.md' and source['text'].startswith('Only this scene')
    assert payload['previous_turns'][0]['questions']==['继续读取本场景 README？']
    assert 'fake source' not in json.dumps(payload)
    assert result['parent_request_id']==parent['request_id']
    assert result['context_usage']['file_count']==1
    assert result['items'][0]['source_reads']==parent['reference_reads']


def test_directory_result_exposes_exact_mapping_and_repeated_read_is_idempotent(reference):
    parent=first_turn(reference);_,_,body=reference
    provider=Plan([call('read_files',workspace_id=body['workspace_id'],paths=['scene/task.md']),
                   call('list_directory',workspace_id=body['workspace_id'],path='scene'),final()])
    result,_=run(reference,provider,request(parent_request_id=parent['request_id']))
    reused=provider.calls[1]['tool_results'][0]['result']
    assert reused['reused'] and reused['untrusted_project_files'][0]['execution_path']=='/w/0/scene/task.md'
    listed=provider.calls[2]['tool_results'][1]['result']
    assert listed['execution_path']=='/w/0/scene'
    assert listed['entries'][0]['execution_path']=='/w/0/scene/task.md'
    assert result['context_usage']['file_count']==1 and len(result['reference_reads'])==1


@pytest.mark.parametrize('change',['body','generation','resources','foreign','stage','legacy'])
def test_stale_or_cross_scope_parent_never_falls_back_to_unbound_generation(reference,change):
    parent=first_turn(reference);world,root,_=reference
    body=request(parent_request_id=parent['request_id'])
    if change=='body':(root/'scene/task.md').write_text('Changed instructions')
    if change=='generation':store.update(world.a['id'],generation='b'*32)
    if change=='resources':store.update(world.a['id'],resources=[str(root/'scene')])
    if change=='foreign':
        with db.connect() as con:
            parent['scope_id']=world.b['id']
            con.execute("UPDATE template_configuration_requests SET result_json=? WHERE state='completed'",(json.dumps(parent),))
    if change=='stage':body['stage']='runtime'
    if change=='legacy':
        with db.connect() as con:
            parent.pop('generation_basis')
            con.execute("UPDATE template_configuration_requests SET result_json=? WHERE state='completed'",(json.dumps(parent),))
    provider=Plan([final()])
    with pytest.raises(ValueError):run(reference,provider,body)
    assert not provider.calls and not tc.directory(world.a['id'])['items']


def test_new_scene_does_not_inherit_parent_receipts_and_history_is_retained(reference):
    first_turn(reference)
    provider=Plan([final()])
    result,_=run(reference,provider,request())
    assert not provider.calls[0]['workspace_references']
    assert result['parent_request_id'] is None
    assert len(tc.directory(reference[0].a['id'])['generations'])==2


def test_read_only_summary_is_retained_and_unknown_authority_fields_still_fail(reference):
    provider=Plan([{'configurations':[],'questions':[],'gaps':[],'summary':'已分析资料，尚未生成或应用。'}])
    result,_=run(reference,provider)
    assert result['summary']=='已分析资料，尚未生成或应用。' and not result['items']
    followup=Plan([final()])
    run(reference,followup,request(parent_request_id=result['request_id']))
    assert followup.calls[0]['previous_turns'][0]['summary']==result['summary']
    with pytest.raises(ValueError):
        run(reference,Plan([{**final(),'approved':True}]))
    failed=tc.directory(reference[0].a['id'])['generations'][-1]
    assert failed['generation_state']=='failed' and not failed['items'] and 'generation_basis' not in failed
    assert 'approved' not in json.dumps(failed) and not reference[0].calls


def test_followup_preserves_exact_configurations_even_after_three_turn_window(reference):
    parent=first_turn(reference)
    for i in range(4):
        provider=Plan([final(name='场景测试保护'+str(i),parameters={'target':'/w/0/scene/tests/**'})])
        result,_=run(reference,provider,request(parent_request_id=parent['request_id']))
        parent=result
    context=provider.calls[0]
    assert len(context['previous_turns'])==3
    assert context['previous_turns'][-1]['configurations'][0]['parameters']['target']=='/w/0/scene/tests/**'
    assert context['workspace_references'][0]['untrusted_project_files'][0]['relative_path']=='scene/task.md'


def test_projection_failure_cannot_relabel_committed_candidates_as_no_changes(reference,monkeypatch):
    def broken_view(*args):raise ValueError('synthetic projection failure')
    monkeypatch.setattr(tc,'view',broken_view)
    with pytest.raises(ValueError,match='projection'):run(reference,Plan([final()]))
    with db.connect() as con:
        saved=con.execute("SELECT state,result_json FROM template_configuration_requests WHERE request_key LIKE 'generate:%'").fetchone()
    assert saved['state']=='completed' and len(json.loads(saved['result_json'])['items'])==1


def test_failed_protocol_diagnostic_contains_shape_only(reference):
    with pytest.raises(ValueError):
        run(reference,Plan([{'tool':'SECRET_NEVER_LOG','arguments':{'path':'PRIVATE_NEVER_LOG'},'unexpected_sensitive_key':'PRIVATE_NEVER_LOG'}]))
    failed=tc.directory(reference[0].a['id'])['generations'][-1]
    assert failed['contract_diagnostic']=={'type':'dict','fields':{'tool':'str','arguments':'dict'},'other_field_count':1}
    assert 'NEVER_LOG' not in json.dumps(failed) and 'unexpected_sensitive_key' not in json.dumps(failed)

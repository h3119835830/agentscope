import json
import pytest
from agentscope_app.history.llm import DeepSeekProvider
from agentscope_app.instances import template_configurations as tc
from agentscope_app.instances.policy_context_agent import ToolContractError
from test_policy_context_agent import reference,world,run,steps,final,Plan


def test_production_provider_preserves_assistant_calls_and_real_results_as_separate_messages(reference,monkeypatch):
    planned=steps(reference[2]['workspace_id']);requests=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):
            return json.dumps({'choices':[{'message':{'content':json.dumps(planned[len(requests)-1]),
                       'reasoning_content':'PRIVATE_REASONING_NEVER_REPLAY'},'finish_reason':'stop'}]}).encode()
    def send(req,timeout):
        requests.append(json.loads(req.data))
        return Response()
    monkeypatch.setattr('urllib.request.urlopen',send)
    result,_=run(reference,DeepSeekProvider(api_key='synthetic-unit-test-only'))
    assert [len(r['messages']) for r in requests]==[2,4,6]
    messages=requests[-1]['messages']
    assert [m['role'] for m in messages]==['system','user','assistant','user','assistant','user']
    assert json.loads(messages[2]['content'])==planned[0]
    assert json.loads(messages[3]['content'])['kind']=='untrusted_tool_results'
    listed=json.loads(messages[3]['content'])['tool_results'][0]
    assert listed['result']['entries'][0]['execution_path']=='/w/0/README.md'
    read=json.loads(messages[5]['content'])['tool_results'][0]
    assert '订单日报' in read['result']['untrusted_project_files'][0]['text']
    assert 'PRIVATE_REASONING' not in json.dumps(requests)
    assert requests[0]['messages'][1]==requests[-1]['messages'][1]
    assert result['context_usage']['file_count']==1


def test_invalid_final_fields_receive_bounded_feedback_not_silent_stripping(reference):
    workspace=reference[2]['workspace_id']
    plan=Plan([*steps(workspace)[:2],{**final(),'PRIVATE_KEY':'PRIVATE_VALUE'},final()])
    result,_=run(reference,plan)
    feedback=plan.calls[-1]['protocol_feedback']
    assert feedback['accepted'] is False and feedback['other_fields_allowed'] is False
    assert 'PRIVATE_' not in json.dumps(plan.calls[-1])
    assert result['context_usage']['file_count']==1 and result['context_usage']['format_repair_count']==1
    assert result['items'][0]['source_reads'] and not reference[0].calls


def test_repeated_bad_contract_has_no_candidates_or_authority(reference):
    plan=Plan([{**final(),'approved':True}]*3)
    with pytest.raises(ToolContractError):run(reference,plan)
    assert len(plan.calls)==3 and not tc.directory(reference[0].a['id'])['items']
    assert not reference[0].calls


def test_production_dialogue_receives_actual_checker_feedback_only(reference,monkeypatch):
    requests=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):
            content={**final(),'UNKNOWN_PRIVATE_KEY':'PRIVATE_VALUE'} if len(requests)==1 else final()
            return json.dumps({'choices':[{'message':{'content':json.dumps(content)}}]}).encode()
    def send(req,timeout):
        requests.append(json.loads(req.data));return Response()
    monkeypatch.setattr('urllib.request.urlopen',send)
    result,_=run(reference,DeepSeekProvider(api_key='synthetic-unit-test-only'))
    assert len(requests)==2
    feedback=json.loads(requests[1]['messages'][-1]['content'])
    assert feedback['code']=='invalid_final_fields' and feedback['accepted'] is False
    assert 'PRIVATE' not in json.dumps(requests)
    assert result['context_usage']['format_repair_count']==1 and not reference[0].calls

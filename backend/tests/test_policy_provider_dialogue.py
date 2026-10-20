import json
from agentscope_app.history.llm import DeepSeekProvider
from test_policy_context_agent import reference,world,run,steps


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

import json,os,sys
from agentscope_app.pi_rpc import drive

def test_pi_continuation_preserves_session_and_records_no_reasoning(tmp_path):
    script=tmp_path/'rpc.py';marker=tmp_path/'submitted'
    script.write_text("""import sys,json
from pathlib import Path
count=0
for line in sys.stdin:
 count+=1
 print(json.dumps({'type':'message_update','assistantMessageEvent':{'type':'thinking_delta','delta':'PRIVATE'}}),flush=True)
 if count==2:Path(sys.argv[1]).write_text('done')
 print(json.dumps({'type':'agent_settled'}),flush=True)
""")
    traces=[]
    result=drive([sys.executable,str(script),str(marker)],os.environ.copy(),'read and submit',lambda:{'submitted':marker.exists(),'submission':'absent'},traces.append,seconds=3)
    assert result['continuations']==1 and 'PRIVATE' not in json.dumps(traces)

def test_pi_deadline_terminates_silent_process(tmp_path):
    import pytest,time
    script=tmp_path/'silent.py';script.write_text('import time;time.sleep(20)')
    start=time.monotonic()
    with pytest.raises(ValueError,match='deadline'):drive([sys.executable,str(script)],os.environ.copy(),'submit',lambda:{'submitted':False},lambda _:None,seconds=.1)
    assert time.monotonic()-start<5


def test_exhausted_server_workflow_stops_on_settlement_without_continuation(tmp_path):
    import pytest
    script=tmp_path/'settled.py'; marker=tmp_path/'prompts'
    script.write_text("""import sys,json
from pathlib import Path
for line in sys.stdin:
 with Path(sys.argv[1]).open('a') as f:f.write('prompt\\n')
 print(json.dumps({'type':'message_update','assistantMessageEvent':{'type':'thinking_delta','delta':'PRIVATE'}}),flush=True)
 print(json.dumps({'type':'agent_settled'}),flush=True)
""")
    traces=[]
    with pytest.raises(ValueError,match='validation repair budget exhausted: exact target exceeds'):
        drive([sys.executable,str(script),str(marker)],os.environ.copy(),'read and submit',
              lambda:{'submitted':False,'workflow_error':'Pi validation repair budget exhausted: exact target exceeds 64 bytes'},
              traces.append,seconds=3)
    assert marker.read_text().splitlines()==['prompt']
    assert traces==[]


def test_server_submission_wins_over_stale_workflow_error(tmp_path):
    script=tmp_path/'settled.py'
    script.write_text("import sys,json\nfor line in sys.stdin:print(json.dumps({'type':'agent_settled'}),flush=True)\n")
    result=drive([sys.executable,str(script)],os.environ.copy(),'submit',
                 lambda:{'submitted':True,'workflow_error':'stale budget diagnostic'},lambda _:None,seconds=3)
    assert result['continuations']==0


def test_settled_failure_retains_last_server_business_diagnostic(tmp_path):
    import pytest
    script=tmp_path/'settled.py'
    script.write_text("import sys,json\nfor line in sys.stdin:print(json.dumps({'type':'agent_settled'}),flush=True)\n")
    with pytest.raises(ValueError,match='server-validated submission: exact source was unread'):
        drive([sys.executable,str(script)],os.environ.copy(),'submit',
              lambda:{'submitted':False,'last_diagnostic':'exact source was unread'},lambda _:None,seconds=3,repairs=0)


def test_tool_budget_exhaustion_has_one_finalize_only_continuation(tmp_path):
    script=tmp_path/'settled.py';marker=tmp_path/'submitted';prompts=tmp_path/'prompts'
    script.write_text("""import sys,json
from pathlib import Path
for line in sys.stdin:
 with Path(sys.argv[2]).open('a') as f:f.write(json.loads(line).get('message','')+'\\n')
 if Path(sys.argv[2]).read_text().count('\\n')==2:Path(sys.argv[1]).write_text('done')
 print(json.dumps({'type':'agent_settled'}),flush=True)
""")
    traces=[]
    result=drive([sys.executable,str(script),str(marker),str(prompts)],os.environ.copy(),'investigate and submit',
                 lambda:{'submitted':marker.exists(),'force_finalize':True},traces.append,seconds=3)
    assert result['continuations']==1 and prompts.read_text().count('\n')==2
    assert any(t['kind']=='workflow_finalization' for t in traces)


def test_tool_budget_exhaustion_does_not_loop_after_finalize_continuation(tmp_path):
    import pytest
    script=tmp_path/'settled.py';prompts=tmp_path/'prompts'
    script.write_text("""import sys,json
from pathlib import Path
for line in sys.stdin:
 with Path(sys.argv[1]).open('a') as f:f.write('prompt\\n')
 print(json.dumps({'type':'agent_settled'}),flush=True)
""")
    with pytest.raises(ValueError,match='after tool budget exhaustion'):
        drive([sys.executable,str(script),str(prompts)],os.environ.copy(),'investigate and submit',
              lambda:{'submitted':False,'force_finalize':True},lambda _:None,seconds=3)
    assert prompts.read_text().splitlines()==['prompt','prompt']


def skill_process(tmp_path,mode):
    script=tmp_path/'skill-rpc.py'
    script.write_text("""import sys,json
mode=sys.argv[1]
for line in sys.stdin:
 v=json.loads(line);data={}
 if v['type']=='get_commands':
  data={'commands':([] if mode=='missing' else [{'name':'skill:policy-feedback','source':'skill'}])}
 elif v['type']=='prompt':
  assert v['message'].startswith('/skill:policy-feedback ')
  print(json.dumps({'type':'agent_settled'}),flush=True);continue
 elif v['type']=='get_messages':
  text='<skill name="policy-feedback" location="/pi/skills/policy-feedback/SKILL.md">\\nPUBLIC SKILL BODY\\n</skill>' if mode=='ok' else '/skill:policy-feedback unexpanded'
  data={'messages':[{'role':'user','content':[{'type':'text','text':text}]},{'role':'assistant','content':[{'type':'thinking','thinking':'PRIVATE'}]}]}
 print(json.dumps({'type':'response','id':v['id'],'success':True,'data':data}),flush=True)
""")
    return [sys.executable,str(script),mode]


def test_required_skill_needs_discovery_and_native_body_before_success(tmp_path):
    import pytest
    contract={'name':'policy-feedback','body':'PUBLIC SKILL BODY','metadata':{'mount':'/pi/skills/policy-feedback/SKILL.md'}}
    traces=[]
    for mode,error in [('missing','exclusively discovered'),('unexpanded','body was not admitted')]:
        with pytest.raises(ValueError,match=error):
            drive(skill_process(tmp_path,mode),os.environ.copy(),'submit',lambda:{'submitted':True},traces.append,seconds=3,required_skill=contract)
    result=drive(skill_process(tmp_path,'ok'),os.environ.copy(),'submit',lambda:{'submitted':True},traces.append,seconds=3,required_skill=contract)
    assert result['skill']['context_verified'] and result['skill']['discovery_verified']
    assert 'PRIVATE' not in json.dumps([traces,result])

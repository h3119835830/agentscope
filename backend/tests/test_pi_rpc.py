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

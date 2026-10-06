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

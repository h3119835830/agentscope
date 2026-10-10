"""Read one synthetic fixture through native DSH; preserve real tool receipts."""
import json,sys,time,urllib.request
from pathlib import Path
if len(sys.argv)!=3:raise SystemExit('Usage: accept_dsl_trace.py INSTANCE_ID NATIVE_SESSION_ID (synthetic fixture only)')
ident,sid=sys.argv[1:]
def api(path,body=None):
    request=urllib.request.Request('http://127.0.0.1:18003'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=120) as response:return json.load(response)
path='/api/agent-instances/'+ident
api(path+'/sessions/prompt',{'session_id':sid,'text':'Use the native read tool once to read .agentscope-dsl-notify.txt in this workspace. Report the file content in one sentence, then stop. Do not write files or run shell commands.'})
for _ in range(90):
    result=api(path+'/sessions/'+sid+'/tool-traces')
    if any(r['result'] in ('success','failure','tool_denied') for r in result['records']):break
    time.sleep(.5)
assert result['records'],result
assert all(r['feedback_delivered'] is None for r in result['records'])
target=Path('/var/lib/agentscope-scope-demo/report/dsl-trace-acceptance.json');target.write_text(json.dumps(result,ensure_ascii=False,indent=2));target.chmod(0o600)
print(json.dumps({'traces':len(result['records']),'results':[r['result'] for r in result['records']],'steps':[[s['kind'] for s in r['steps']] for r in result['records']]},ensure_ascii=False))

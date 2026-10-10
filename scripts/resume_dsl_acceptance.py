import json,os,pwd,sys,time,urllib.request
from pathlib import Path
ROOT=Path('/opt/agentscope-task-archive-20261007');sys.path.insert(0,str(ROOT/'scripts'))
from scope_service import environment
os.environ.update(environment());sys.path.insert(0,str(ROOT/'backend'))
user=pwd.getpwnam('agentscope-api');os.initgroups(user.pw_name,user.pw_gid);os.setgid(user.pw_gid);os.setuid(user.pw_uid)
from agentscope_app.broker_client import call as broker
def api(path,body=None):
    request=urllib.request.Request('http://127.0.0.1:18003'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=120) as response:return json.load(response)
ident=sys.argv[1];row=api('/api/agent-instances/'+ident);gen=row['generation']
directory=api('/api/sessions?instance_id='+ident);sid=directory['records'][0]['id']
probes={effect:broker(dict(action='agent-instance-dsl-probe',instance_id=ident,generation=gen,effect=effect),timeout=20)['probe'] for effect in ('block','notify','kill')}
assert probes['block']['outcome']=={'read_completed':False,'errno':1}
assert probes['notify']['outcome']['read_completed']
assert probes['kill']['returncode'] in (-9,137) and probes['kill']['outcome'] is None
events=[]
for _ in range(15):
    events=api('/api/agent-instances/'+ident+'/sessions/'+sid+'/kernel-events')['records']
    if all(any(e['pid']==probes[effect]['pid'] and e['effect']==effect and e['source_refs'] for e in events) for effect in probes):break
    time.sleep(.3)
summary=api('/api/agent-instances/'+ident+'/sessions/'+sid+'/policies')
report=dict(instance_id=ident,generation=gen,probes=probes,kernel_events=events,bundle_hash=summary['bundle_hash'],sessions=directory['records'])
path=Path('/var/lib/agentscope-scope-demo/report/dsl-runtime-acceptance.json');path.write_text(json.dumps(report,ensure_ascii=False,indent=2));path.chmod(0o600)
for effect,p in probes.items():
    matches=[e for e in events if e['pid']==p['pid'] and e['effect']==effect and e['source_refs']]
    assert matches,(effect,events)
    assert all(e['session_id'] is None and e['feedback_delivered'] is None for e in matches)
    assert not Path('/proc/'+str(p['pid'])).exists()
    if effect=='kill':assert any(e['killed'] for e in matches)
    if effect=='notify':assert all(not e['killed'] and not e['blocked'] for e in matches)
report['passed']=True;path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'passed':True,'instance_id':ident,'probes':probes,'events':len(events),'mapped':sum(bool(e['source_refs']) for e in events)},ensure_ascii=False))

#!/usr/bin/env python3
"""Real 18003 acceptance with isolated fixtures and fixed, unprivileged probes."""
import json,os,pwd,sys,time,urllib.request,uuid
from pathlib import Path
RUNTIME=Path('/opt/agentscope-task-archive-20261007');STATE=Path('/var/lib/agentscope-scope-demo')
def api(path,body=None):
    req=urllib.request.Request('http://127.0.0.1:18003'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=120) as response:return json.load(response)
def main():
    if os.getuid()!=0:raise SystemExit('Root prepares fixtures then drops to the API service user')
    root=Path('/s/instance-resources/dsl-acceptance-'+uuid.uuid4().hex[:8]);root.mkdir(parents=True,mode=0o755)
    fixture=root/'a';fixture.mkdir(mode=0o755)
    secondary=root/'b';secondary.mkdir(mode=0o755)
    for effect in ('block','kill','notify'):
        p=fixture/('.agentscope-dsl-'+effect+'.txt');p.write_text('synthetic-canary\n');p.chmod(0o644)
    sys.path.insert(0,str(RUNTIME/'scripts'));from scope_service import environment
    os.environ.update(environment());sys.path.insert(0,str(RUNTIME/'backend'))
    user=pwd.getpwnam('agentscope-api');os.initgroups(user.pw_name,user.pw_gid);os.setgid(user.pw_gid);os.setuid(user.pw_uid)
    from agentscope_app.broker_client import call as broker
    instance=api('/api/agent-instances',dict(name='DSL 验收连接',agent_type='dsh',mode='controlled',environment='wsl',resources=[str(fixture),str(secondary)],open_url=''))
    ident=instance['id'];base=api('/api/agent-instances/'+ident+'/dsl')
    source='source AGENT = exec "**"\n\nrule canary:\n'+''.join('  '+effect+' read file '+json.dumps(str(fixture/('.agentscope-dsl-'+effect+'.txt')))+' if AGENT\n' for effect in ('block','notify','kill'))+'  because "Synthetic DSL acceptance"\n'
    doc=dict(id='canary',name='canary.dsl',original_dsl=source,metadata={'canary':{'statement':'读取测试文件时分别阻止、上报和终止子进程。','context_requirement':'project','context_reason':'已绑定本验收连接登记的测试目录，三个目标均为无敏感数据的固定测试文件。'}})
    p=api('/api/agent-instances/'+ident+'/dsl/proposals',dict(documents=[doc],base_hash=base['document_hash'],base_revision=base['revision'],request_key=uuid.uuid4().hex))
    assert p['state']=='pending',p['result']['error']
    applied=api('/api/agent-instances/'+ident+'/dsl/proposals/'+p['id']+'/confirm',dict(proposal_hash=p['proposal_hash']))
    assert applied['resumed_count']==0
    started=api('/api/agent-instances/'+ident+'/start',{});assert started['active'],started.get('security')
    gen=started['generation'];native=[]
    for resource in (fixture,secondary):
        result=broker(dict(action='agent-instance-native',instance_id=ident,operation='create',resource=str(resource)),timeout=15)
        native.append(result)
    probes={}
    for effect in ('block','notify','kill'):
        probes[effect]=broker(dict(action='agent-instance-dsl-probe',instance_id=ident,generation=gen,effect=effect),timeout=20)['probe']
    assert probes['block']['returncode']==0 and probes['block']['outcome']=={'read_completed':False,'errno':1},probes
    assert probes['notify']['returncode']==0 and probes['notify']['outcome']['read_completed'],probes
    # bwrap translates its killed sandbox child to shell status 128 + SIGKILL.
    # Require the kernel's killed flag and the exact child PID below as well.
    assert probes['kill']['returncode'] in (-9,137) and probes['kill']['outcome'] is None,probes
    directory=api('/api/sessions?instance_id='+ident);assert directory['total']==2,directory
    sid=directory['records'][0]['id'];events=[]
    for _ in range(15):
        events=api('/api/agent-instances/'+ident+'/sessions/'+sid+'/kernel-events')['records']
        if all(any(e['pid']==probes[effect]['pid'] and e['effect']==effect and e['source_refs'] for e in events) for effect in probes):break
        time.sleep(.3)
    for effect,probe in probes.items():
        matches=[e for e in events if e['pid']==probe['pid'] and e['effect']==effect and e['source_refs']]
        assert matches,(effect,events)
        assert all(e['attribution']=='shared_executor_unattributed' and e['session_id'] is None and e['feedback_delivered'] is None for e in matches)
        if effect=='notify':assert all(not e['blocked'] and not e['killed'] for e in matches)
        if effect=='kill':assert any(e['killed'] for e in matches)
    summary=api('/api/agent-instances/'+ident+'/sessions/'+sid+'/policies')
    assert summary['active'] and any(r.get('original_document')==source and r['active'] for r in summary['records'])
    report={'passed':True,'instance_id':ident,'generation':gen,'sessions':[{'id':r['id'],'workspace':r.get('resource'),'pids':r['process_ids']} for r in directory['records']],
        'probes':probes,'kernel_events':events,'bundle_hash':summary['bundle_hash'],'source_dsl':source,'native_create':native}
    target=STATE/'report/dsl-runtime-acceptance.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2));target.chmod(0o600)
    print(json.dumps({'passed':True,'instance_id':ident,'generation':gen,'probes':probes,'matched_events':len(events),'report':str(target)},ensure_ascii=False))
if __name__=='__main__':main()

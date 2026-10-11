#!/usr/bin/env python3
"""Real API/Broker acceptance against the owned 18143 test service only."""
import json,os,pwd,socket,time,urllib.request,uuid
from pathlib import Path
BASE='http://127.0.0.1:18143'
SOCKET='/run/aspol-accept-20261011/broker.sock'
OUTPUT=Path('/tmp/aspol-service-acceptance.json')
report={'checks':[],'agents':[]}
def api(path,body=None):
    request=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=160) as response:return json.load(response)
    except urllib.error.HTTPError as e:raise RuntimeError(e.read().decode()) from e
def broker(body):
    original_uid=os.geteuid();original_gid=os.getegid();user=pwd.getpwnam('agentscope-api')
    try:
        os.setegid(user.pw_gid);os.seteuid(user.pw_uid)
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.settimeout(30);client.connect(SOCKET);client.sendall(json.dumps(body).encode()+b'\n');data=b''
            while not data.endswith(b'\n'):data+=client.recv(65536)
    finally:os.seteuid(original_uid);os.setegid(original_gid)
    result=json.loads(data);assert result['ok'],result
    return result['result']
def apply_library(items):
    library=api('/api/security/system/policy-library')
    p=api('/api/security/system/policy-library/proposals',dict(selections=[{'id':i['id'],'revision':i['revision']} for i in items],removals=[],base_hash=library['base_hash'],base_revision=library['base_revision'],request_key=uuid.uuid4().hex))
    assert p['state']=='pending',p['result']
    result=api('/api/security/system/dsl/proposals/'+p['id']+'/confirm',{'proposal_hash':p['proposal_hash']})
    assert result['state']=='applied';report['checks'].append({'application':result,'proposal_id':p['id']})
    duplicate=api('/api/security/system/dsl/proposals/'+p['id']+'/confirm',{'proposal_hash':p['proposal_hash']});assert duplicate['idempotent']
    return result
def main():
    assert Path(SOCKET).exists() and api('/api/security/system/execution-capabilities')['file_suffix']
    agents=json.loads(Path('/tmp/aspol-accept-agents.json').read_text());assert {a['agent_type'] for a in agents}=={'dsh','hermes'}
    # Reset only owned synthetic Agent policies so the acceptance is repeatable.
    # Production ports, resources and credentials are never used by this script.
    for row in api('/api/agent-instances')['instances']:
        if not row['id'].startswith('instance-'):continue  # read-only discovered installations
        resources=api('/api/agent-instances/'+row['id']).get('resources',[])
        assert resources and all(r.startswith('/mnt/c/Users/happy/Desktop/projects/aspol-accept-fixtures/') for r in resources)
        api('/api/agent-instances/'+row['id']+'/stop',{})
        path='/api/agent-instances/'+row['id']+'/dsl'
        base=api(path)
        if base['documents']:
            p=api(path+'/proposals',dict(documents=[],base_hash=base['document_hash'],base_revision=base['revision'],request_key=uuid.uuid4().hex))
            assert p['state']=='pending',p['result']
            cleared=api(path+'/proposals/'+p['id']+'/confirm',{'proposal_hash':p['proposal_hash']})
            assert cleared['state']=='applied'
    items=[]
    library=api('/api/security/system/policy-library')
    for effect in ('block','notify','kill'):
        name='隔离验收 '+effect
        config=dict(name=name,mode='suffix',values='.agentscope-dsl-'+effect+'.txt',ops=['open'],effect=effect,reason='Synthetic acceptance',template_id='')
        prior=next((i for i in library['items'] if i['name']==name),None)
        item=api('/api/security/system/policy-library'+('/'+prior['id']+'/versions' if prior else ''),dict(kind='structured',config=config,base_revision=prior['revision'] if prior else 0));items.append(item)
    for row in agents:
        detail=api('/api/agent-instances/'+row['id'])
        for root in detail['resources']:
            assert root.startswith('/mnt/c/Users/happy/Desktop/projects/aspol-accept-fixtures/')
            for effect in ('block','notify','kill'):(Path(root)/('.agentscope-dsl-'+effect+'.txt')).write_text('synthetic-canary\n')
        api('/api/agent-instances/'+row['id']+'/stop',{})
    result=apply_library(items);assert result['resumed_count']==0
    for row in agents:
        detail=api('/api/agent-instances/'+row['id']+'/start',{});assert detail['active'],detail['security']
        evidence={k:detail.get(k) for k in ('id','agent_type','pid','domain_id','generation','active')};evidence['probes']=[]
        artifact=detail['runtime']['policy_artifact']
        documents=artifact['documents'];assert all(i['id'] in {d['id'] for d in documents if d['scope_id']=='system'} for i in items)
        evidence['dsl_hash']=detail['dsl_hash'];evidence['bundle_hash']=artifact['bundle_hash']
        for effect in ('block','notify','kill'):
            probe=broker(dict(action='agent-instance-dsl-probe',instance_id=row['id'],generation=detail['generation'],effect=effect))['probe']
            deadline=time.monotonic()+8;events=[]
            while time.monotonic()<deadline:
                data=broker(dict(action='agent-instance-kernel-events',instance_id=row['id'],generation=detail['generation']))
                events=[e['event'] for e in data['events'] if e['event'].get('pid')==probe['pid'] and e['event'].get('effect')==effect]
                if events:break
                time.sleep(.2)
            assert events,(effect,probe)
            if effect=='kill':assert probe['returncode'] in (-9,137) and probe['outcome'] is None
            else:assert probe['outcome']['read_completed'] is (effect=='notify')
            assert all(e.get('blocked') is (effect=='block') for e in events) if effect!='kill' else any(e.get('killed') for e in events)
            assert api('/api/agent-instances/'+row['id'])['pid']==detail['pid']
            evidence['probes'].append({'effect':effect,'probe':probe,'events':events})
        report['agents'].append(evidence);print(row['agent_type']+' runtime effects passed',flush=True)
    # A system update restarts only the currently active target.
    api('/api/agent-instances/'+agents[1]['id']+'/stop',{})
    result=apply_library(items);assert result['resumed_count']==1
    assert not api('/api/agent-instances/'+agents[1]['id'])['active']
    # Agent additions cannot replace the inherited document, even with equal IDs/rule names.
    primary=agents[0]['id'];other=agents[1]['id'];path='/api/agent-instances/'+primary+'/dsl'
    base=api(path);shared=items[0]
    source='source AGENT = exec "**/node"\nrule system-'+shared['id']+':\n block open file "**/*.agentscope-dsl-notify.txt" if AGENT\n because "Synthetic Agent-only restriction"\n'
    doc=dict(id=shared['id'],name='Agent isolation',original_dsl=source,metadata={})
    p=api(path+'/proposals',dict(documents=[doc],base_hash=base['document_hash'],base_revision=base['revision'],request_key=uuid.uuid4().hex))
    assert p['state']=='pending',p['result']
    api(path+'/proposals/'+p['id']+'/confirm',{'proposal_hash':p['proposal_hash']})
    first=api('/api/agent-instances/'+primary);second=api('/api/agent-instances/'+other+'/start',{})
    a=broker(dict(action='agent-instance-dsl-probe',instance_id=primary,generation=first['generation'],effect='notify'))['probe']
    b=broker(dict(action='agent-instance-dsl-probe',instance_id=other,generation=second['generation'],effect='notify'))['probe']
    inherited=broker(dict(action='agent-instance-dsl-probe',instance_id=primary,generation=first['generation'],effect='block'))['probe']
    assert not a['outcome']['read_completed'] and b['outcome']['read_completed'] and not inherited['outcome']['read_completed']
    docs=first['runtime']['policy_artifact']['documents'];same=[d for d in docs if d['id']==shared['id']]
    assert len(same)==2 and len({d['namespace'] for d in same})==2
    report['agent_isolation']={'agent_probe':a,'other_agent_probe':b,'inherited_probe':inherited,'namespaces':[d['namespace'] for d in same]}
    # Register after the system application; the very first start must inherit it.
    root=Path('/mnt/c/Users/happy/Desktop/projects/aspol-accept-fixtures/future');root.mkdir(parents=True,exist_ok=True)
    (root/'README.md').write_text('Synthetic acceptance workspace\n')
    for effect in ('block','notify','kill'):(root/('.agentscope-dsl-'+effect+'.txt')).write_text('synthetic-canary\n')
    future=next((r for r in api('/api/agent-instances')['instances'] if r.get('resources')==[str(root)]),None)
    if future:api('/api/agent-instances/'+future['id']+'/stop',{})
    else:future=api('/api/agent-instances',dict(name='Future acceptance Agent',agent_type='dsh',resources=[str(root)],mode='controlled',environment='wsl'))
    current=api('/api/agent-instances/'+future['id']+'/start',{})
    assert current['active']
    assert all(i['id'] in {d['id'] for d in current['runtime']['policy_artifact']['documents'] if d['scope_id']=='system'} for i in items)
    probe=broker(dict(action='agent-instance-dsl-probe',instance_id=future['id'],generation=current['generation'],effect='block'))['probe'];assert not probe['outcome']['read_completed']
    report['future_agent']={'id':future['id'],'dsl_hash':current['dsl_hash'],'probe':probe}
    api('/api/agent-instances/'+future['id']+'/stop',{});api('/api/agent-instances/'+other+'/stop',{})
    print('Agent-only isolation and new Agent inheritance passed',flush=True)
    report['passed']=True
if __name__=='__main__':
    try:main()
    finally:OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2));print(str(OUTPUT),flush=True)

"""18003-only lifecycle acceptance. No benchmark file is changed by probes."""
import json,pathlib,urllib.request,urllib.error,os,pwd,subprocess,uuid,copy,hashlib,time
ROOT=pathlib.Path('/var/lib/agentscope-scope-demo')
P=ROOT/'instance-acceptance-evidence.json'
evidence=json.loads(P.read_text())
def api(i,suffix='',body=None):
    req=urllib.request.Request('http://127.0.0.1:18003/api/agent-instances/'+i+suffix,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=150) as r:return json.load(r)
def demote():
    u=pwd.getpwnam('agentscope-api');os.initgroups(u.pw_name,u.pw_gid);os.setgid(u.pw_gid);os.setuid(u.pw_uid)
def broker(message):
    code="import json,sys;from agentscope_app.broker_client import call;print(json.dumps(call(json.load(sys.stdin),timeout=30)))"
    r=subprocess.run(['/opt/agentscope/.venv/bin/python','-c',code],input=json.dumps(message),text=True,capture_output=True,timeout=40,preexec_fn=demote,env={'PYTHONPATH':'/opt/agentscope-task-archive-20261007/backend','AGENTSCOPE_BROKER_SOCKET':'/run/agentscope-scope-demo/broker.sock'})
    if r.returncode:raise RuntimeError(r.stderr[-500:])
    return json.loads(r.stdout)
def alive(pid):
    try:
        s=pathlib.Path('/proc',str(pid),'stat').read_text();return s[s.rindex(')')+2:].split()[0] not in ('Z','X')
    except FileNotFoundError:return False
for kind,e in evidence.items():
    i=e['instance_id'];row=api(i);original=copy.deepcopy(row['policy'])
    sibling=next(v['instance_id'] for k,v in evidence.items() if k!=kind);other=api(sibling)
    sessions=[]
    for resource in row['resources']:
        created=api(i,'/sessions',{'resource':resource})
        sid=created.get('session_id') or created['sessionId']
        api(i,'/sessions/prompt',{'session_id':sid,'text':'Use agentscope_instance_scope once to read this instance policy. Report only its policy_hash, then stop. Do not modify files.'})
        sessions.append(sid)
    e['shared_sessions']=sessions
    p=pathlib.Path('/s/instance-resources/rq5-'+kind)/'transaction-verification-service/.agentscope-held-handle-probe'
    assert not p.exists()
    p.write_text('Held file and mmap canary\n');p.chmod(0o666)
    held=broker({'action':'agent-instance-handle-probe','instance_id':i,'target':str(p)})['hold']
    assert held['fd'] and held['writable_mapping'] and alive(held['child_pid'])
    shrink=copy.deepcopy(original)
    shrink['rules']=[r for r in shrink['rules'] if not(r['action']=='write' and r['effect']=='allow')]
    shrink['rules'] += [{'action':'read','target':'/s/instance-resources/second-'+kind+'/README.md','effect':'deny','text':'验证实例内所有会话同步禁止读取'},{'action':'tool','target':'bash' if kind=='dsh' else 'terminal','effect':'deny','text':'共享工具入口同步收紧'}]
    key=uuid.uuid4().hex
    result=api(i,'/policy/proposals',{'generation':row['generation'],'base_hash':row['policy_hash'],'request_key':key,'policy':shrink})
    assert result['state']=='applied'
    now=api(i)
    assert now['active'] and now['generation']!=row['generation'] and now['domain_id']!=row['domain_id']
    assert not alive(held['pid']) and not alive(held['child_pid']) and p.read_text()=='Held file and mmap canary\n'
    assert api(sibling)['generation']==other['generation'] and api(sibling)['policy_hash']==other['policy_hash']
    sessions_after=api(i,'/sessions')['sessions']
    assert all(sid in {s['id'] for s in sessions_after} or kind=='hermes' for sid in sessions)
    e['tightening']={'passed':True,'old_generation':row['generation'],'new_generation':now['generation'],'old_domain':row['domain_id'],'new_domain':now['domain_id'],'held_handles':held,'held_processes_terminated':True,'mapping_revoked':True,'sibling_unchanged':True,'verification':now['runtime']['verification'],'sessions_after':sessions_after}
    expansion=api(i,'/policy/proposals',{'generation':now['generation'],'base_hash':now['policy_hash'],'request_key':uuid.uuid4().hex,'policy':original})
    assert expansion['state']=='pending'
    try:api(i,'/policy/proposals/'+expansion['id']+'/confirm',{'proposal_hash':'0'*64})
    except urllib.error.HTTPError as err:assert err.code==409
    else:raise AssertionError('Inexact confirmation accepted')
    applied=api(i,'/policy/proposals/'+expansion['id']+'/confirm',{'proposal_hash':expansion['proposal_hash']})
    assert applied['state']=='applied' and api(i)['active']
    e['expansion']={'exact_confirmation_required':True,'passed':True,'new_generation':api(i)['generation'],'new_domain':api(i)['domain_id']}
    p.unlink()
    P.write_text(json.dumps(evidence,ensure_ascii=False,indent=2));print(kind,'shared tightening / fd / mmap / background / isolation / exact expansion PASS',flush=True)

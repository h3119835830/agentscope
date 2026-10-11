"""Explicit real 18003 DSH acceptance on dedicated nonsensitive fixtures.

Each phase is separate so the candidate can be inspected before approval.
Only the test connection's policy is confirmed; existing connections are read-only.
"""
import argparse,hashlib,json,os,pwd,time,urllib.request,uuid
from pathlib import Path
STATE=Path('/var/lib/agentscope-scope-demo')
RECORD=STATE/'report/policy-semantics-dsh.json'
def api(path,body=None):
    req=urllib.request.Request('http://127.0.0.1:18003'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=180) as r:return json.load(r)
def save(r):
    RECORD.parent.mkdir(exist_ok=True);RECORD.write_text(json.dumps(r,ensure_ascii=False,indent=2));RECORD.chmod(0o600)
def fingerprint(ident):
    row=api('/api/agent-instances/'+ident);dsl=api('/api/agent-instances/'+ident+'/dsl')
    return {'instance_id':ident,**{k:row.get(k) for k in ('generation','pid','domain_id','policy_hash','active')},
        'dsl_revision':dsl['revision'],'dsl_hash':dsl['document_hash']}
PROBE=r'''
import errno,hashlib,json,os,subprocess,sys
from pathlib import Path
p=Path('/w/0/sales.csv');phase=sys.argv[1];results=[];before=hashlib.sha256(p.read_bytes()).hexdigest()
def check(name,fn,deny):
    try:fn();actual='allowed';number=None
    except OSError as e:actual='denied' if e.errno in (errno.EPERM,errno.EACCES,errno.EROFS) else 'unexpected';number=e.errno
    results.append(dict(name=name,actual=actual,errno=number,passed=actual==('denied' if deny else 'allowed')))
def opened(flags):
    fd=os.open(p,flags);os.close(fd)
deny=phase=='applied'
check('read',p.read_bytes,False)
check('append',lambda:p.open('ab').write(b'acceptance\n'),deny)
if deny:
    check('overwrite',lambda:opened(os.O_WRONLY|os.O_TRUNC),True)
    check('read_write_open',lambda:opened(os.O_RDWR),True)
    check('truncate',lambda:os.truncate(p,0),True)
    check('unlink',p.unlink,True)
    check('rename',lambda:p.rename(p.with_suffix('.renamed')),True)
for kind,code in [('read','import pathlib; pathlib.Path("/w/0/sales.csv").read_bytes()'),('write','import pathlib; pathlib.Path("/w/0/sales.csv").open("ab").write(b"child")')]:
    child=subprocess.run([sys.executable,'-c',code],capture_output=True)
    denied=child.returncode!=0 and b'PermissionError' in child.stderr
    wanted=deny and kind=='write'
    results.append(dict(name='child_'+kind,actual='allowed' if child.returncode==0 else 'denied' if denied else 'unexpected',passed=denied if wanted else child.returncode==0))
control=Path('/w/0/control.txt');check('unrelated_write',lambda:control.write_text('control\n'),False);check('unrelated_read',control.read_text,False)
out=dict(phase=phase,pid=os.getpid(),ppid=os.getppid(),uid=os.getuid(),cgroup=Path('/proc/self/cgroup').read_text().strip(),
         results=results,before=before,after=hashlib.sha256(p.read_bytes()).hexdigest())
Path('/w/0/result-'+phase+'.json').write_text(json.dumps(out))
print(json.dumps(out),flush=True)
sys.exit(0 if all(r['passed'] for r in results) and (not deny or out['before']==out['after']) else 2)
'''
def setup():
    assert os.geteuid()==0 and not RECORD.exists(),'Existing acceptance record must be inspected before reuse'
    fixture=Path('/s/instance-resources/policy-semantics-'+uuid.uuid4().hex[:8]);fixture.mkdir(mode=0o755)
    # Controlled native DSH runs as the verified installed user (happy), unlike
    # task-runner identities. DAC must allow the baseline independently of LSM.
    owner=pwd.getpwnam('happy');os.chown(fixture,owner.pw_uid,owner.pw_gid)
    for name,text in {'sales.csv':'item,amount\nexample,42\n','control.txt':'control\n','probe.py':PROBE,'README.md':'Dedicated policy semantics acceptance. sales.csv contains synthetic data.\n'}.items():
        p=fixture/name;p.write_text(text);p.chmod(0o644);os.chown(p,owner.pw_uid,owner.pw_gid)
    existing={r['id']:fingerprint(r['id']) for r in api('/api/agent-instances')['instances'] if r['mode']=='controlled'}
    row=api('/api/agent-instances',dict(name='只读语义验收 DSH',agent_type='dsh',mode='controlled',environment='wsl',resources=[str(fixture)]))
    ident=row['id'];save({'fixture':str(fixture),'instance_id':ident,'existing_before':existing})
    p=api('/api/agent-instances/'+ident+'/policy/proposals',dict(policy={'rules':[{'action':'write','target':str(fixture),'effect':'allow','text':'仅为本轮隔离验收建立可读写基线'}],'network':'model_only'},base_hash=row['policy_hash'],generation=row['generation'],request_key=uuid.uuid4().hex))
    assert p['state']=='pending'
    api('/api/console/approvals/instance:'+p['id']+'/confirm',{'proposal_hash':p['proposal_hash']})
    row=api('/api/agent-instances/'+ident+'/start',{});assert row['active'] and row['runtime']['verified']
    s=api('/api/agent-instances/'+ident+'/sessions',{'resource':str(fixture)})
    sid=s.get('session_id') or s.get('sessionId') or s.get('agentId');assert sid
    r=json.loads(RECORD.read_text());r.update(session_id=sid,baseline_policy_proposal=p['id'],baseline=fingerprint(ident));save(r)
    print(json.dumps({'instance_id':ident,'session_id':sid,'fixture':str(fixture),'active':True},ensure_ascii=False))
def prompt(phase):
    r=json.loads(RECORD.read_text());ident=r['instance_id'];sid=r['session_id'];fixture=Path(r['fixture'])
    assert phase in ('baseline','pending','applied') and not (fixture/('result-'+phase+'.json')).exists()
    r[phase+'_before']=fingerprint(ident);save(r)
    # This is an executable acceptance instruction to DSH, not a policy-model
    # prompt patch. Inspect the native call and actual kernel result separately.
    text='本轮为隔离验收。请仅使用原生 bash 工具运行一次：python3 /w/0/probe.py '+phase+'。不要改写探针或使用其他路径替代；报告真实输出和退出码，然后停止。'
    result=api('/api/agent-instances/'+ident+'/sessions/prompt',{'session_id':sid,'text':text})
    print(json.dumps({'phase':phase,'accepted':result},ensure_ascii=False))
def inspect(phase):
    r=json.loads(RECORD.read_text());ident=r['instance_id'];p=Path(r['fixture'])/('result-'+phase+'.json')
    page=api('/api/agent-instances/'+ident+'/sessions')
    selected=next((s for s in page['sessions'] if s['id']==r['session_id']),{})
    print('SESSION',{k:selected.get(k) for k in ('id','status','process_ids','resource')})
    if p.exists():
        observed=json.loads(p.read_text());r[phase+'_result']=observed;r[phase+'_after']=fingerprint(ident);save(r)
        print(json.dumps(observed,ensure_ascii=False))
    else:print('Awaiting native tool result')
def generate():
    r=json.loads(RECORD.read_text());ident=r['instance_id'];assert 'generation_run' not in r
    assert all(x['passed'] for x in r['baseline_result']['results'])
    ctx=api('/api/agent-instances/'+ident+'/policy-context?session_id='+r['session_id']);assert ctx['ready']
    r['before_generation']=fingerprint(ident);save(r)
    v=api('/api/history/inputs',{'text':'只读取 sales.csv 以获取报告数据，不写入、追加或覆盖该文件。','enforcement_level':'per_event','context_requirement':'project',
        'agent_context':{'instance_id':ident,'session_id':r['session_id'],'context_hash':ctx['context_hash']}})
    run=api('/api/history/generations',{'statement_version_id':v['id'],'request_key':uuid.uuid4().hex})
    r.update(statement_version_id=v['id'],generation_run=run['id']);save(r);print(json.dumps(run,ensure_ascii=False))
def candidate():
    r=json.loads(RECORD.read_text());ident=r['instance_id'];run=api('/api/history/generations/'+r['generation_run'])
    print('RUN',run['status'])
    if run['status'] not in ('completed','partial','failed'):return
    rows=api('/api/history/generations/'+r['generation_run']+'/results')['items'];assert len(rows)==1
    item=rows[0];print('CANDIDATE',item['compile_state'],item.get('error'),item.get('submission_blockers'))
    assert item['compile_state']=='compiled' and not item['submission_blockers']
    clauses=[c for rule in item['artifact']['policy_ir']['rules'] for c in rule['clauses']]
    assert len(clauses)==1 and clauses[0]['operation']=='write' and clauses[0]['pattern']=='/w/0/sales.csv' and clauses[0]['effect']=='block'
    assert fingerprint(ident)==r['before_generation']
    r.update(artifact_id=item['artifact_id'],generated_dsl=item['artifact']['actplane_dsl'],semantic_check=item['artifact']['policy_record']['metadata']['semantic_check'],after_generation=fingerprint(ident));save(r)
    print(r['generated_dsl'])
def submit():
    r=json.loads(RECORD.read_text());ident=r['instance_id'];assert 'readonly_proposal' not in r
    c=api('/api/agent-instances/'+ident+'/policy-candidates/'+r['artifact_id']);base=api('/api/agent-instances/'+ident+'/dsl')
    p=api('/api/agent-instances/'+ident+'/dsl/proposals',dict(documents=[*base['documents'],c['document']],base_revision=base['revision'],base_hash=base['document_hash'],request_key=uuid.uuid4().hex))
    assert p['state']=='pending';assert fingerprint(ident)==r['before_generation']
    r.update(readonly_proposal=p['id'],proposal_hash=p['proposal_hash'],after_submission=fingerprint(ident));save(r)
    print(json.dumps({'proposal':p['id'],'state':p['state'],'authority_unchanged':True}))
def confirm():
    r=json.loads(RECORD.read_text());ident=r['instance_id']
    assert all(x['passed'] for x in r['pending_result']['results']) and r['pending_before']==r['pending_after']==r['before_generation']
    result=api('/api/console/approvals/'+r['readonly_proposal']+'/confirm',{'proposal_hash':r['proposal_hash']})
    r.update(application=result,after_application=fingerprint(ident));save(r)
    print(json.dumps({'applied':result.get('state'), 'authority':r['after_application']},ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['setup','prompt','inspect','generate','candidate','submit','confirm']);p.add_argument('phase',nargs='?',choices=['baseline','pending','applied']);a=p.parse_args()
    {'setup':setup,'generate':generate,'candidate':candidate,'submit':submit,'confirm':confirm}.get(a.action,lambda:prompt(a.phase) if a.action=='prompt' else inspect(a.phase))()

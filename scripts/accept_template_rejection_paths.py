"""Real isolated control-plane rejection and legacy argv-block run probes."""
import json,os,subprocess,sys,tempfile,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 import fcntl
 acceptance_lock=open('/var/tmp/agentscope-template-runtime-acceptance.lock','a')
 fcntl.flock(acceptance_lock,fcntl.LOCK_EX)
 assert os.geteuid()==0
 state=Path(tempfile.mkdtemp(prefix='asrt-reject-',dir='/var/tmp'));state.chmod(0o755)
 os.environ['AGENTSCOPE_STATE_DIR']=str(state/'state');os.environ['AGENTSCOPE_BROKER_SOCKET']=str(state/'absent.sock')
 for key in ('AGENTSCOPE_DB','AGENTSCOPE_TASK_ROOT','AGENTSCOPE_RUNTIME_DIR'):os.environ.pop(key,None)
 sys.path.insert(0,str(ROOT/'backend'))
 from agentscope_app import db
 from agentscope_app.instances import template_catalog as catalog,template_configurations as tc,template_versions
 db.init_db()
 from agentscope_app.instances import store
 store.init()
 report={'scope':'isolated database; no shared Broker or DSH; negative paths must not start a child','cases':[]}
 for ident in ('GIT-CONTENT','GIT-PUSH-TARGET','GIT-PUSH-APPROVAL','GIT-MERGE-GATE','RQ1-CHECK','RQ1-GIT'):
  t=next(x for x in catalog.public_catalog() if x['id']==ident)
  values={p['key']:p['default'] for p in t['parameters']}
  for p in t['parameters']:
   if p['type']=='path':values[p['key']]='/synthetic/repo'
   if p['type']=='program':values[p['key']]='ascheck'
   if p['type'] in ('lines','text') and not values[p['key']]:values[p['key']]='synthetic'
  body={'template_id':ident,'template_version':t['version'],'scope':'system','name':'Synthetic rejection','parameters':values,'request_key':uuid.uuid4().hex}
  checks={};errors={}
  if t.get('retired'):
   try:tc.save('system',body);checks['create_rejected']=False
   except ValueError as e:checks['create_rejected']='历史模板' in str(e);errors['create']=str(e)
   definition={k:t[k] for k in ('name','effect')}
   edit={**definition,'description':t['description'],'parameters':[{'key':p['key'],'label':p['label'],'default':str(p['default'])} for p in t['parameters']],'base_version':t['version'],'request_key':uuid.uuid4().hex}
   try:template_versions.save(ident,edit);checks['template_edit_rejected']=False
   except ValueError as e:checks['template_edit_rejected']='历史模板' in str(e);errors['edit']=str(e)
  else:
   saved=tc.save('system',body);checks['draft_only']=saved['document'] is None and not saved['can_submit']
   for method in ('single','batch','revalidate'):
    try:
     if method=='single':tc.propose(saved['id'],{'revision':1,'operation':'apply','request_key':uuid.uuid4().hex})
     elif method=='batch':
      from agentscope_app.instances import dsl_policy
      base=dsl_policy.current('system');tc.propose_batch({'scope_id':'system','selections':[{'id':saved['id'],'revision':1}],'base_hash':base['document_hash'],'base_revision':base['revision'],'operation':'apply','request_key':uuid.uuid4().hex})
     else:tc.revalidate_proposal('system',{'selections':[{'id':saved['id'],'revision':1}]})
     checks[method+'_rejected']=False
    except ValueError as e:checks[method+'_rejected']='暂不支持' in str(e);errors[method]=str(e)
  report['cases'].append({'template_id':ident,'checks':checks,'errors':errors,'passed':all(checks.values())})
 # Exercise the real Broker compile validator without contacting the shared Broker.
 t=catalog.get('RQ1-CHECK',2)
 normalized={'target':'/synthetic/code','checker':'ascheck'}
 document,*_=tc.render_document(t,normalized,'legacy','Legacy default','Synthetic legacy argv block rejection')
 dsl='source AGENT = exec "**/asprobe"\n'+document['original_dsl']
 yaml='version: 1\npolicy: |\n'+''.join('  '+v+'\n' for v in dsl.splitlines())
 import pwd,grp
 os.environ.update(ACTPLANE_BIN='/var/lib/agentscope-scope-demo/bin/actplane',AGENTSCOPE_TASK_ROOT=str(state/'tasks'),
  AGENTSCOPE_POLICY_DIR=str(state/'policies'),AGENTSCOPE_RUNTIME_DIR=str(state/'runtime'),AGENTSCOPE_LOG_DIR=str(state/'logs'),
  AGENTSCOPE_SERVICE_HOME=str(state),AGENTSCOPE_APP_USER='happy',AGENTSCOPE_AGENT_USER='happy',
  AGENTSCOPE_TASK_GROUP=grp.getgrgid(pwd.getpwnam('happy').pw_gid).gr_name)
 from broker import main as broker
 work=state/'work';work.mkdir()
 try:broker.compile_policy('a'*16,1,yaml,dsl,work);report['legacy_broker_rejected']=False
 except RuntimeError as error:
  report['legacy_broker_rejected']='不支持' in str(error) and 'argv' in str(error);report['legacy_broker_error']=str(error)
 # Raw CLI run does not enforce the doctor's unsupported verdict. Record this
 # as an unsupported-capability observation, never an acceptable block action.
 import shutil
 owner=pwd.getpwnam('happy');probe=state/'asprobe';shutil.copy2('/usr/bin/python3',probe)
 repo=state/'repo';repo.mkdir();os.chown(repo,owner.pw_uid,owner.pw_gid)
 def git(*args):
  return subprocess.check_output(['/usr/bin/git',*args],cwd=repo,user=owner.pw_uid,group=owner.pw_gid,text=True).strip()
 git('init','-q');git('config','user.name','Synthetic');git('config','user.email','synthetic@example.invalid');git('commit','--allow-empty','-qm','initial')
 before=git('rev-parse','HEAD');code=repo/'code';code.write_text('SYNTHETIC')
 normalized['target']=str(code)
 document,*_=tc.render_document(t,normalized,'legacy','Legacy default','Synthetic unsupported observation')
 dsl='source AGENT = exec "**/asprobe"\n'+document['original_dsl']
 policy=state/'legacy.yaml';policy.write_text('version: 1\npolicy: |\n'+''.join('  '+v+'\n' for v in dsl.splitlines()))
 runner=state/'probe.py';runner.write_text('import subprocess,sys\nfrom pathlib import Path\nPath(sys.argv[1]).read_bytes()\nr=subprocess.run(["/usr/bin/git","commit","--allow-empty","-m","synthetic"],cwd=sys.argv[2])\nprint("MATCH_RETURN="+str(r.returncode),flush=True)\n')
 pin=Path('/sys/fs/bpf')/('asrt-reject-'+uuid.uuid4().hex)
 env={'PATH':'/usr/bin:/bin','HOME':owner.pw_dir,'SUDO_UID':str(owner.pw_uid),'SUDO_GID':str(owner.pw_gid),'ACTPLANE_BPF_PIN_ROOT':str(pin),'ACTPLANE_RESERVE_OPEN_RULES':'1','ACTPLANE_HOOK_PROFILE':'full'}
 try:
  result=subprocess.run([str(broker.ACTPLANE),'--policy',str(policy),'run','--',str(probe),str(runner),str(code),str(repo)],cwd=state,env=env,capture_output=True,text=True,timeout=40)
  events=[json.loads(l) for p in state.glob('.actplane/runs/*/events.jsonl') for l in p.read_text().splitlines() if l.strip()]
  report['legacy_raw_cli_observation']={'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'dsl':dsl,'events':events,'before_head':before,'after_head':git('rev-parse','HEAD'),
   'classification':'unsupported block is NOT enforced by raw CLI; AgentScope Broker validator and retired-template API must reject it'}
  report['legacy_raw_cli_observation']['confirmed']=result.returncode==0 and 'MATCH_RETURN=0' in result.stdout and git('rev-parse','HEAD')!=before and not any(e.get('blocked') for e in events)
 finally:
  if pin.exists():
   assert pin.parent==Path('/sys/fs/bpf') and pin.name.startswith('asrt-reject-');shutil.rmtree(pin)
 report['passed']=all(c['passed'] for c in report['cases']) and report['legacy_broker_rejected'] and report['legacy_raw_cli_observation']['confirmed']
 output=Path(sys.argv[1]);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps({'passed':report['passed'],'templates':len(report['cases']),'output':str(output)}),flush=True)
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':main()

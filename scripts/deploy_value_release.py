#!/usr/bin/env python3
"""Guarded local execution-plane upgrade using the current API release baseline."""
import argparse,hashlib,json,os,shutil,sqlite3,subprocess,time,urllib.request
from pathlib import Path
from deploy_policy_semantics import authority,guard,service,listeners,files,sha

SOURCE=Path(__file__).resolve().parents[1]
STATE=Path('/var/lib/agentscope-scope-demo')
API='agentscope-scope-demo-api.service';BROKER='agentscope-scope-demo-broker.service'
OVERLAY=['backend/agentscope_app/'+p for p in ('console.py','instances/controller.py','instances/dsl_policy.py','instances/store.py','instances/system_policy.py','main.py')]+['backend/broker/instance_runtime.py','backend/broker/instance_supervision.py','backend/broker/instance_runner.py','scripts/scope_service.py','scripts/scope_systemd_exec.py']
DROPS={role:Path('/etc/systemd/system/'+unit+'.d/99zz-value-reliability-20261012.conf') for role,unit in [('api',API),('broker',BROKER)]}

def call(path,body=None):
 req=urllib.request.Request('http://127.0.0.1:18003'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=140) as response:return json.load(response)

def stage():
 assert os.getuid()==0;guard()
 before={role:service(unit) for role,unit in [('api',API),('broker',BROKER)]}
 live=Path(before['api']['WorkingDirectory']);assert live==Path('/opt/agentscope-policy-targets-20261012-202018'),'Current integration baseline changed'
 assert Path(before['broker']['WorkingDirectory'])==Path('/opt/agentscope-system-policy-20261011-220127-because')
 # Preserve every untouched runtime file, including changes absent from HEAD.
 for relative in OVERLAY:
  old=subprocess.run(['git','-c','safe.directory='+str(SOURCE),'-C',str(SOURCE),'show','HEAD:'+relative],capture_output=True)
  if relative=='backend/broker/instance_runner.py':continue # tested native bootstrap compatibility, explicit in manifest
  if old.returncode==0:assert sha(live/relative)==hashlib.sha256(old.stdout).hexdigest(),'Concurrent live overlay change: '+relative
  else:assert not (live/relative).exists(),'New runtime file already exists: '+relative
 with sqlite3.connect(STATE/'demo.sqlite3') as con:
  assert not con.execute("SELECT 1 FROM managed_tasks WHERE json_extract(state_json,'$.phase') IN ('running','starting')").fetchone(),'Managed task active'
 release=Path('/opt/agentscope-value-'+time.strftime('%Y%m%d-%H%M%S'));release.mkdir(mode=0o755)
 for folder in ('backend','scripts','integrations','bin','dsh'):
  if (live/folder).exists():shutil.copytree(live/folder,release/folder,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 for relative in OVERLAY:shutil.copy2(SOURCE/relative,release/relative)
 shutil.copytree(SOURCE/'frontend/dist',release/'frontend/dist')
 manifest={'release':str(release),'before_services':before,'authority':authority(),'other_listeners':listeners(),'source_baseline':subprocess.check_output(['git','-c','safe.directory='+str(SOURCE),'-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip(),
  'overlays':{p:sha(SOURCE/p) for p in OVERLAY},'release_files':files(release),'previous_files':files(live/'backend'),
  'previous_drops':{role:path.read_text() if path.exists() else None for role,path in DROPS.items()},
  'runner_compatibility':'Use tested HEAD runner: configured read-only Hermes TUI and HERMES_SKIP_NODE_BOOTSTRAP; no ordinary business code.'}
 path=release/'value-deployment.json';path.write_text(json.dumps(manifest,indent=2));path.chmod(0o600)
 print(json.dumps({'staged':str(release),'manifest':str(path)}))

def apply(path):
 assert os.getuid()==0
 m=json.loads(Path(path).read_text());release=Path(m['release']);assert release.parent==Path('/opt') and release.name.startswith('agentscope-value-')
 assert files(release)=={**m['release_files'],'value-deployment.json':sha(path)}
 assert all(service(unit)==m['before_services'][role] for role,unit in [('api',API),('broker',BROKER)])
 assert all((p.read_text() if p.exists() else None)==m['previous_drops'][r] for r,p in DROPS.items())
 assert files(Path(m['before_services']['api']['WorkingDirectory'])/'backend')==m['previous_files']
 guard();assert authority()==m['authority'];assert listeners()==m['other_listeners']
 active=[ident for ident,row in m['authority']['agents'].items() if row['active']]
 backup=STATE/'release-backups'/release.name;backup.mkdir(parents=True,mode=0o700)
 shutil.copytree(STATE/'ui',backup/'ui')
 with sqlite3.connect(STATE/'demo.sqlite3') as src,sqlite3.connect(backup/'demo.sqlite3') as dst:src.backup(dst)
 (backup/'demo.sqlite3').chmod(0o600)
 result={'release':str(release),'started_at':time.time(),'authority_before':m['authority'],'approved_restart_targets':active}
 def persist():
  p=backup/'result.json';p.write_text(json.dumps(result,indent=2));p.chmod(0o600)
 persist()
 try:
  # The exact set is captured while idle. Never derive restart intent from old PID/history.
  for ident in active:call('/api/agent-instances/'+ident+'/stop',{})
  subprocess.run(['systemctl','stop',API],check=True,timeout=30)
  subprocess.run(['systemctl','stop',BROKER],check=True,timeout=30)
  shutil.copytree(release/'frontend/dist',STATE/'ui',dirs_exist_ok=True)
  for role,path in DROPS.items():
   path.write_text('[Service]\n'+('TimeoutStopSec=10\n' if role=='api' else '')+'WorkingDirectory='+str(release)+'\nExecStart=\nExecStart=/opt/agentscope/.venv/bin/python '+str(release)+'/scripts/scope_systemd_exec.py '+role+'\nExecStartPost=\nExecStartPost=/opt/agentscope/.venv/bin/python '+str(release)+'/scripts/scope_systemd_exec.py '+role+'-ready\n')
  subprocess.run(['systemctl','daemon-reload'],check=True)
  subprocess.run(['systemctl','start',BROKER,API],check=True,timeout=45)
  assert call('/api/health')['ok']
  for ident in active:
   row=call('/api/agent-instances/'+ident+'/start',{})
   assert row['active'] and row.get('supervision')=='broker-admission-v1'
   assert row['policy_hash']==m['authority']['agents'][ident]['policy_hash']
   assert row['generation']!=m['authority']['agents'][ident]['generation']
  after=authority();assert after['system']==m['authority']['system'] and after['dsl_scopes']==m['authority']['dsl_scopes']
  assert all(after['agents'][i]['policy_hash']==a['policy_hash'] for i,a in m['authority']['agents'].items())
  assert all(not after['agents'][i]['active'] for i in after['agents'] if i not in active)
  assert listeners()==m['other_listeners']
  # Once upgraded, a normal API release must preserve execution identities.
  started=time.monotonic();subprocess.run(['systemctl','restart',API],check=True,timeout=30)
  for _ in range(30):
   now=authority()
   if now['agents']==after['agents']:break
   time.sleep(.3)
  assert now['agents']==after['agents'],'API restart changed protected execution'
  result.update(published=True,authority_after=now,api_restart_seconds=round(time.monotonic()-started,3),api_restart_preserved_identity=True,other_ports_unchanged=True,services={r:service(u) for r,u in [('api',API),('broker',BROKER)]},finished_at=time.time())
 except BaseException as error:
  result.update(published=False,error=str(error)[:800]);persist()
  # Roll back code/UI without reverting a database that may contain new facts.
  subprocess.run(['systemctl','stop',API,BROKER],timeout=45)
  for role,p in DROPS.items():
   if m['previous_drops'][role] is None:p.unlink(missing_ok=True)
   else:p.write_text(m['previous_drops'][role])
  shutil.copytree(backup/'ui',STATE/'ui',dirs_exist_ok=True)
  subprocess.run(['systemctl','daemon-reload'],check=True)
  subprocess.run(['systemctl','start',BROKER,API],check=True,timeout=45)
  result['code_ui_rolled_back']=True;persist()
  raise
 finally:
  persist();print(json.dumps({'published':result.get('published',False),'evidence':str(backup/'result.json')}))

if __name__=='__main__':
 p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--stage',action='store_true');g.add_argument('--apply');a=p.parse_args()
 stage() if a.stage else apply(a.apply)

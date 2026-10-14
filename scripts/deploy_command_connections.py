#!/usr/bin/env python3
"""Stage/switch both local 18003 planes with exact idle instances and config preservation."""
import argparse,hashlib,json,os,shutil,sqlite3,subprocess,time
from pathlib import Path
from deploy_policy_semantics import guard,service,listeners,files,sha,api
SOURCE=Path(__file__).resolve().parents[1]
STATE=Path('/var/lib/agentscope-scope-demo')
API='agentscope-scope-demo-api.service';BROKER='agentscope-scope-demo-broker.service'
DROPS={API:Path('/etc/systemd/system/'+API+'.d/99zzzzzz-command-connections-20261014.conf'),BROKER:Path('/etc/systemd/system/'+BROKER+'.d/99zzzzzz-command-connections-20261014.conf')}
TABLES={'agent_instances':'id,name,agent_type,environment,mode,resources_json,policy_json,policy_hash',
        'instance_local_policies':'*','system_security_policy':'*','instance_dsl_scopes':'*',
        'instance_proposals':'*','instance_dsl_proposals':'*','system_security_proposals':'*',
        'policy_approval_decisions':'*','instance_launch_configs':'*'}

def configuration():
 result={}
 with sqlite3.connect('file:'+str(STATE/'demo.sqlite3')+'?mode=ro',uri=True) as con:
  available={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  for table,columns in TABLES.items():
   rows=sorted(con.execute('SELECT '+columns+' FROM '+table).fetchall(),key=repr) if table in available else []
   result[table]={'count':len(rows),'sha256':hashlib.sha256(json.dumps(rows,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
 return result

def idle():
 guard()
 with sqlite3.connect('file:'+str(STATE/'demo.sqlite3')+'?mode=ro',uri=True) as con:
  assert not con.execute('SELECT 1 FROM instance_leases').fetchone(),'An Agent tool is still running'
  assert not con.execute("SELECT 1 FROM agent_instances WHERE gate IN ('starting','updating')").fetchone(),'Instance change in progress'
  assert not con.execute("SELECT 1 FROM managed_tasks WHERE json_extract(state_json,'$.phase') IN ('running','starting')").fetchone(),'Managed task in progress'
  assert not con.execute("SELECT 1 FROM system_security_policy WHERE phase!='ready'").fetchone(),'System policy change in progress'

def drop_text(unit,release):
 role='api' if unit==API else 'broker'
 return '[Service]\nTimeoutStopSec=8\nWorkingDirectory='+str(release)+'\nExecStart=\nExecStart=/opt/agentscope/.venv/bin/python '+str(release)+'/scripts/scope_systemd_exec.py '+role+'\nExecStartPost=\n'+('ExecStartPost=/opt/agentscope/.venv/bin/python '+str(release)+'/scripts/scope_systemd_exec.py api-ready\n' if role=='api' else '')

def stage():
 assert os.geteuid()==0;idle()
 services={unit:service(unit) for unit in (API,BROKER)};live=Path(services[API]['WorkingDirectory'])
 release=Path('/opt/agentscope-command-connections-'+time.strftime('%Y%m%d-%H%M%S'))
 assert release.parent==Path('/opt') and not release.exists();release.mkdir(mode=0o755)
 for folder in ('backend','scripts','integrations','bin','dsh'):
  if (live/folder).exists():shutil.copytree(live/folder,release/folder,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 for folder in ('backend/agentscope_app','backend/broker','integrations/dsh-instance-runtime'):
  shutil.copytree(SOURCE/folder,release/folder,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc','test'))
 shutil.copytree(SOURCE/'frontend/dist',release/'frontend/dist')
 # Leave unrelated launcher/helpers and the installed native Agent/compiler untouched.
 subprocess.run(['/opt/agentscope/.venv/bin/python','-m','compileall','-q',str(release/'backend/agentscope_app'),str(release/'backend/broker')],check=True)
 running=[{k:row.get(k) for k in ('id','pid','generation','policy_hash','gate')} for row in api('/api/agent-instances')['instances'] if row.get('mode')=='controlled' and row.get('connected')]
 manifest={'release':str(release),'services':services,'configuration':configuration(),'listeners':listeners(),'running':running,
  'previous_files':{unit:files(Path(s['WorkingDirectory'])/'backend') for unit,s in services.items()},
  'previous_drops':{unit:path.read_text() if path.exists() else None for unit,path in DROPS.items()},
  'release_files':files(release),'source_commit':subprocess.check_output(['git','-c','safe.directory='+str(SOURCE),'rev-parse','HEAD'],cwd=SOURCE,text=True).strip()}
 path=release/'command-deployment.json';path.write_text(json.dumps(manifest,indent=2));path.chmod(0o600)
 print(json.dumps({'staged':str(release),'manifest':str(path),'running_to_restore':running}))

def apply(path):
 assert os.geteuid()==0
 manifest_path=Path(path);m=json.loads(manifest_path.read_text());release=Path(m['release'])
 assert release.parent==Path('/opt') and release.name.startswith('agentscope-command-connections-') and manifest_path==release/'command-deployment.json'
 assert {k:v for k,v in files(release).items() if k!=manifest_path.name}==m['release_files']
 assert configuration()==m['configuration'] and listeners()==m['listeners']
 for unit in (API,BROKER):
  assert service(unit)==m['services'][unit]
  assert files(Path(m['services'][unit]['WorkingDirectory'])/'backend')==m['previous_files'][unit]
  assert (DROPS[unit].read_text() if DROPS[unit].exists() else None)==m['previous_drops'][unit]
 idle()
 backup=STATE/'release-backups'/release.name;backup.mkdir(parents=True,mode=0o700)
 shutil.copytree(STATE/'ui',backup/'ui')
 with sqlite3.connect(STATE/'demo.sqlite3') as source,sqlite3.connect(backup/'demo.sqlite3') as target:source.backup(target)
 (backup/'demo.sqlite3').chmod(0o600)
 result={'release':str(release),'source_commit':m['source_commit'],'published':False,'before':m['configuration'],'old_running':m['running']}
 try:
  for row in m['running']:
   current=api('/api/agent-instances/'+row['id'])
   assert all(current[k]==row[k] for k in ('pid','generation','policy_hash','gate'))
   api('/api/agent-instances/'+row['id']+'/stop',{'generation':row['generation'],'policy_hash':row['policy_hash']})
  subprocess.run(['systemctl','stop',API,BROKER],check=True,timeout=40)
  shutil.copytree(release/'frontend/dist',STATE/'ui',dirs_exist_ok=True)
  for unit,path in DROPS.items():path.parent.mkdir(exist_ok=True);path.write_text(drop_text(unit,release))
  subprocess.run(['systemctl','daemon-reload'],check=True)
  subprocess.run(['systemctl','start',BROKER,API],check=True,timeout=45)
  assert api('/api/health')['ok']
  assert configuration()==m['configuration'],'Policy/resource/approval configuration changed during publication'
  restored=[]
  for old in m['running']:
   row=api('/api/agent-instances/'+old['id']+'/start',{})
   assert row['active'] and row['policy_hash']==old['policy_hash']
   restored.append({k:row[k] for k in ('id','pid','generation','policy_hash','active')})
  assert configuration()==m['configuration'];assert listeners()==m['listeners']
  assert sha(STATE/'ui/index.html')==sha(release/'frontend/dist/index.html')
  result.update(published=True,after=configuration(),restored=restored,services={u:service(u) for u in (API,BROKER)},other_ports_unchanged=True,configuration_preserved=True)
 except BaseException as error:
  result['error']=str(error)[:1000]
  subprocess.run(['systemctl','stop',API,BROKER],timeout=40)
  for unit,path in DROPS.items():
   if m['previous_drops'][unit] is None:path.unlink(missing_ok=True)
   else:path.write_text(m['previous_drops'][unit])
  shutil.copytree(backup/'ui',STATE/'ui',dirs_exist_ok=True)
  subprocess.run(['systemctl','daemon-reload'],check=True);subprocess.run(['systemctl','start',BROKER,API],check=True,timeout=45)
  result['code_rolled_back']=True
  # Keep audit/database facts; never restore stale authority from a raw DB backup.
  for old in m['running']:
   try:api('/api/agent-instances/'+old['id']+'/start',{})
   except Exception:pass
  raise
 finally:
  out=backup/'result.json';out.write_text(json.dumps(result,indent=2));out.chmod(0o600)
  print(json.dumps({'published':result['published'],'evidence':str(out)}))

if __name__=='__main__':
 parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True);group.add_argument('--stage',action='store_true');group.add_argument('--apply');args=parser.parse_args()
 stage() if args.stage else apply(args.apply)

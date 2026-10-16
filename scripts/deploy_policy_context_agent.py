#!/usr/bin/env python3
"""Guarded API/UI overlay; never starts, stops, or applies policy to native Agents."""
import argparse,hashlib,json,os,shutil,sqlite3,subprocess,tempfile,time
from pathlib import Path
from deploy_policy_semantics import authority,guard,service,listeners,files,sha,api
from observe_value_stability import proof

ROOT=Path(__file__).resolve().parents[1]
STATE=Path('/var/lib/agentscope-scope-demo')
API='agentscope-scope-demo-api.service'
BROKER='agentscope-scope-demo-broker.service'
DROP=Path('/etc/systemd/system/'+API+'.d/99zzzzzzzzzz-workspace-references-20261015.conf')
BASE='2a026fb666d57e36c034fec39567b26f1037ca0d'
UI_BASE=Path('/home/happy/projects/agentscope-unified-policy-catalog-20261015/frontend/dist')
MANIFEST='policy-context-deployment.json'

def git(*args):return subprocess.check_output(['git','-c','safe.directory='+str(ROOT),'-C',str(ROOT),*args])

def idle():
 guard()
 with sqlite3.connect('file:'+str(STATE/'demo.sqlite3')+'?mode=ro',uri=True) as con:
  assert not con.execute("SELECT 1 FROM template_configuration_requests WHERE state='running'").fetchone(),'Template generation is busy'

def protected():
 result={}
 for row in api('/api/agent-instances')['instances']:
  if row['mode']!='controlled' or not row.get('active'):continue
  current=proof(row['id'],row)
  assert current['gate']=='open' and current['protection_fresh'],'Broker protection is unavailable'
  assert not current['outstanding_calls'] and not current['pending_events'],'Execution queue is busy'
  pid=str(row['pid']);ticks=Path('/proc',pid,'stat').read_text().rsplit(') ',1)[1].split()[19]
  result[row['id']]={'pid':row['pid'],'start_ticks':ticks,'generation':row['generation'],'policy_hash':row['policy_hash'],'domain_id':row['domain_id']}
 return result

def reader_check(release):
 # Exercise the installed helper as the actual reduced file-reading identity,
 # on synthetic data only. No policy or native Agent execution is involved.
 import pwd,grp
 uid=pwd.getpwnam('happy').pw_uid;gid=grp.getgrnam('agentscope-task').gr_gid
 with tempfile.TemporaryDirectory(prefix='policy-context-release-') as directory:
  root=Path(directory);root.chmod(0o755);(root/'说明.md').write_text('合成发布核验材料。');(root/'说明.md').chmod(0o644)
  reader=release/'backend/reference_file_reader.py'
  for payload in ({'operation':'list','root':directory},{'root':directory,'paths':['说明.md'],'max_total_bytes':100}):
   process=subprocess.run(['/opt/agentscope/.venv/bin/python','-I',str(reader)],input=json.dumps(payload),capture_output=True,text=True,
    cwd='/',env={'LANG':'C.UTF-8'},user=uid,group=gid,extra_groups=[],timeout=5,check=True)
   result=json.loads(process.stdout);assert 'error' not in result
   assert result.get('entries') or result.get('files')

def stage():
 assert os.geteuid()==0
 idle();assert not git('status','--porcelain').strip(),'Commit reviewed source first'
 before=service(API);broker=service(BROKER);live=Path(before['WorkingDirectory'])
 assert live.parent==Path('/opt')
 expected={}
 for rel,digest in files(live/'backend/agentscope_app').items():
  expected[rel]=hashlib.sha256(git('show',BASE+':backend/agentscope_app/'+rel)).hexdigest()
  assert expected[rel]==digest,'Live application changed: '+rel
 baseline_paths=git('ls-tree','-r','--name-only',BASE,'backend/agentscope_app').decode().splitlines()
 assert {p.removeprefix('backend/agentscope_app/') for p in baseline_paths}==set(expected),'Live application has missing files'
 assert sha(STATE/'ui/index.html')==sha(UI_BASE/'index.html'),'Live UI changed since integrated baseline'
 assert all(sha(STATE/'ui'/p)==value for p,value in files(UI_BASE).items()),'Live UI assets changed'
 assert sha(live/'backend/reference_file_reader.py')==hashlib.sha256(git('show',BASE+':backend/reference_file_reader.py')).hexdigest(),'Reference reader changed'
 active=protected();release=Path('/opt/agentscope-policy-context-agent-'+time.strftime('%Y%m%d-%H%M%S'))
 assert not release.exists();release.mkdir(mode=0o755)
 for folder in ('backend','scripts','integrations','bin','dsh'):
  if (live/folder).exists():shutil.copytree(live/folder,release/folder,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 shutil.copytree(ROOT/'backend/agentscope_app',release/'backend/agentscope_app',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 shutil.copy2(ROOT/'backend/reference_file_reader.py',release/'backend/reference_file_reader.py')
 shutil.copytree(ROOT/'frontend/dist',release/'frontend/dist')
 for folder in ('backend/broker','integrations','bin','dsh'):
  if (live/folder).exists():assert files(live/folder)==files(release/folder),'Execution files changed: '+folder
 reader_check(release)
 subprocess.run(['/opt/agentscope/.venv/bin/python','-m','compileall','-q',str(release/'backend/agentscope_app')],check=True)
 manifest={'release':str(release),'api':before,'broker':broker,'authority':authority(),'protected':active,'listeners':listeners(),
  'live_files':files(live/'backend/agentscope_app'),'release_files':files(release),'ui_files':files(STATE/'ui'),
  'reader_hash':sha(live/'backend/reference_file_reader.py'),'source_commit':git('rev-parse','HEAD').decode().strip(),
  'old_drop':DROP.read_text() if DROP.exists() else None}
 path=release/MANIFEST;path.write_text(json.dumps(manifest,indent=2));path.chmod(0o600)
 print(json.dumps({'staged':str(release),'manifest':str(path),'protected_agents':len(active)}))

def apply(path):
 assert os.geteuid()==0
 manifest_path=Path(path);m=json.loads(manifest_path.read_text());release=Path(m['release']);live=Path(m['api']['WorkingDirectory'])
 assert release.parent==Path('/opt') and release.name.startswith('agentscope-policy-context-agent-') and manifest_path==release/MANIFEST
 assert {k:v for k,v in files(release).items() if k!=MANIFEST}==m['release_files']
 assert service(API)==m['api'] and service(BROKER)==m['broker']
 assert files(live/'backend/agentscope_app')==m['live_files'] and sha(live/'backend/reference_file_reader.py')==m['reader_hash']
 assert (DROP.read_text() if DROP.exists() else None)==m['old_drop'] and files(STATE/'ui')==m['ui_files']
 idle();assert authority()==m['authority'] and protected()==m['protected'] and listeners()==m['listeners']
 backup=STATE/'release-backups'/release.name;backup.mkdir(parents=True,mode=0o700);shutil.copytree(STATE/'ui',backup/'ui')
 with sqlite3.connect(STATE/'demo.sqlite3') as src,sqlite3.connect(backup/'demo.sqlite3') as dst:src.backup(dst)
 (backup/'demo.sqlite3').chmod(0o600)
 result={'published':False,'release':str(release),'source_commit':m['source_commit'],'agent_actions':False,'policy_application':False,'before_agents':m['protected']}
 try:
  shutil.copytree(release/'frontend/dist/assets',STATE/'ui/assets',dirs_exist_ok=True)
  DROP.write_text('[Service]\nTimeoutStopSec=3\nWorkingDirectory='+str(release)+'\nExecStart=\nExecStart=/opt/agentscope/.venv/bin/python '+str(release)+'/scripts/scope_systemd_exec.py api\nExecStartPost=\nExecStartPost=/opt/agentscope/.venv/bin/python '+str(release)+'/scripts/scope_systemd_exec.py api-ready\n')
  subprocess.run(['systemctl','daemon-reload'],check=True);started=time.monotonic()
  subprocess.run(['systemctl','restart',API],check=True,timeout=30)
  assert api('/api/health')['ok'] and service(BROKER)==m['broker']
  assert authority()==m['authority'] and protected()==m['protected'] and listeners()==m['listeners']
  assert len(api('/api/policy-templates')['catalog'])==27
  # The new route is registered; an absent target must fail without reading.
  import urllib.request,urllib.error
  try:urllib.request.urlopen('http://127.0.0.1:18003/api/agent-instances/absent-policy-context-target/policy-reference-workspaces/absent/files',timeout=5)
  except urllib.error.HTTPError as error:assert error.code==404 and json.load(error).get('detail')
  else:raise AssertionError('Absent target was accepted')
  temporary=STATE/'ui/index.html.next';shutil.copy2(release/'frontend/dist/index.html',temporary);temporary.replace(STATE/'ui/index.html')
  assert sha(STATE/'ui/index.html')==sha(release/'frontend/dist/index.html')
  result.update(published=True,restart_seconds=round(time.monotonic()-started,3),broker_unchanged=True,authority_unchanged=True,
   other_ports_unchanged=True,after_agents=protected(),api=service(API),ui_sha256=sha(STATE/'ui/index.html'))
 except BaseException:
  if m['old_drop'] is None:DROP.unlink(missing_ok=True)
  else:DROP.write_text(m['old_drop'])
  shutil.copytree(backup/'ui',STATE/'ui',dirs_exist_ok=True)
  subprocess.run(['systemctl','daemon-reload'],check=True);subprocess.run(['systemctl','restart',API],check=True,timeout=30)
  result['code_ui_rolled_back']=True
  raise
 finally:
  result['finished_at']=time.time();report=backup/'result.json';report.write_text(json.dumps(result,indent=2));report.chmod(0o600)
  print(json.dumps({'published':result['published'],'evidence':str(report)}))

if __name__=='__main__':
 parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True);group.add_argument('--stage',action='store_true');group.add_argument('--apply')
 options=parser.parse_args();stage() if options.stage else apply(options.apply)

#!/usr/bin/env python3
"""Guarded API/UI overlay; never restart Broker, launch Agents or apply policies."""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path
from deploy_policy_semantics import authority,guard,service,listeners,files,sha,api

ROOT=Path(__file__).resolve().parents[1]
STATE=Path('/var/lib/agentscope-scope-demo')
API='agentscope-scope-demo-api.service'
BROKER='agentscope-scope-demo-broker.service'
BASE='fddc532aa8cabfeb41b8d6a09793a74529c51836'
DROP=Path('/etc/systemd/system/'+API+'.d/99zzzzzzzzzz-workspace-references-20261015.conf')
EXPECTED_UI='a2f8d4629f62f0fa995cb02056ff75b649a9fb3bb841ec1009a8747a106a4a28'

def git(*args):return subprocess.check_output(['git','-c','safe.directory='+str(ROOT),'-C',str(ROOT),*args])
def idle():
 guard()
 with sqlite3.connect('file:'+str(STATE/'demo.sqlite3')+'?mode=ro',uri=True) as con:
  assert not con.execute("SELECT 1 FROM template_configuration_requests WHERE state='running'").fetchone(),'Template generation is busy'

def stage():
 assert os.geteuid()==0
 assert not git('status','--porcelain').strip(),'Commit reviewed source first'
 idle();before=service(API);live=Path(before['WorkingDirectory']);assert live.parent==Path('/opt')
 for relative,digest in files(live/'backend/agentscope_app').items():
  assert hashlib.sha256(git('show',BASE+':backend/agentscope_app/'+relative)).hexdigest()==digest,'API baseline changed: '+relative
 assert sha(STATE/'ui/index.html')==EXPECTED_UI,'UI baseline changed'
 release=Path('/opt/agentscope-workspace-references-'+time.strftime('%Y%m%d-%H%M%S'));assert not release.exists();release.mkdir(mode=0o755)
 for folder in ('backend','scripts','integrations','bin','dsh'):
  if (live/folder).exists():shutil.copytree(live/folder,release/folder,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 shutil.copytree(ROOT/'backend/agentscope_app',release/'backend/agentscope_app',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 shutil.copyfile(ROOT/'backend/reference_file_reader.py',release/'backend/reference_file_reader.py');(release/'backend/reference_file_reader.py').chmod(0o644)
 shutil.copytree(ROOT/'frontend/dist',release/'frontend/dist')
 subprocess.run(['/opt/agentscope/.venv/bin/python','-m','compileall','-q',str(release/'backend/agentscope_app'),str(release/'backend/reference_file_reader.py')],check=True)
 manifest={'release':str(release),'api':before,'broker':service(BROKER),'authority':authority(),'listeners':listeners(),
  'live_files':files(live/'backend/agentscope_app'),'release_files':files(release),'source_commit':git('rev-parse','HEAD').decode().strip(),
  'old_drop':DROP.read_text() if DROP.exists() else None,'ui_hash':EXPECTED_UI}
 path=release/'reference-deployment.json';path.write_text(json.dumps(manifest,indent=2));path.chmod(0o600)
 print(json.dumps({'staged':str(release),'manifest':str(path)}))

def apply(path):
 assert os.geteuid()==0
 manifest_path=Path(path);m=json.loads(manifest_path.read_text());release=Path(m['release'])
 assert release.parent==Path('/opt') and release.name.startswith('agentscope-workspace-references-') and manifest_path==release/'reference-deployment.json'
 assert {k:v for k,v in files(release).items() if k!=manifest_path.name}==m['release_files']
 assert service(API)==m['api'] and service(BROKER)==m['broker']
 assert files(Path(m['api']['WorkingDirectory'])/'backend/agentscope_app')==m['live_files']
 assert (DROP.read_text() if DROP.exists() else None)==m['old_drop'] and sha(STATE/'ui/index.html')==m['ui_hash']
 idle();assert authority()==m['authority'] and listeners()==m['listeners']
 backup=STATE/'release-backups'/release.name;backup.mkdir(parents=True,mode=0o700)
 shutil.copytree(STATE/'ui',backup/'ui')
 with sqlite3.connect(STATE/'demo.sqlite3') as source,sqlite3.connect(backup/'demo.sqlite3') as dest:source.backup(dest)
 (backup/'demo.sqlite3').chmod(0o600)
 result={'published':False,'source_commit':m['source_commit'],'release':str(release),'agent_actions':False,'policy_application':False,'broker_restart':False}
 try:
  shutil.copytree(release/'frontend/dist/assets',STATE/'ui/assets',dirs_exist_ok=True)
  DROP.write_text('[Service]\nTimeoutStopSec=3\nWorkingDirectory='+str(release)+'\nExecStart=\nExecStart=/opt/agentscope/.venv/bin/python '+str(release)+'/scripts/scope_systemd_exec.py api\nExecStartPost=\nExecStartPost=/opt/agentscope/.venv/bin/python '+str(release)+'/scripts/scope_systemd_exec.py api-ready\n')
  subprocess.run(['systemctl','daemon-reload'],check=True);started=time.monotonic();subprocess.run(['systemctl','restart',API],check=True,timeout=30)
  assert api('/api/health')['ok'] and service(API)['WorkingDirectory']==str(release)
  assert service(BROKER)==m['broker'] and authority()==m['authority'] and listeners()==m['listeners']
  rows=api('/api/agent-instances')['instances'];ident=next(r['id'] for r in rows if r['mode']=='controlled')
  assert api('/api/agent-instances/'+ident+'/policy-reference-workspaces')['instance_id']==ident
  # Prove the installed immutable helper runs with the Agent UID/GID. No real
  # project body is read during production release verification.
  import pwd,grp
  worker=release/'backend/reference_file_reader.py';user=pwd.getpwnam('happy').pw_uid;group=grp.getgrnam('agentscope-task').gr_gid
  probe=subprocess.run(['/opt/agentscope/.venv/bin/python','-I',str(worker)],input='{}',capture_output=True,text=True,user=user,group=group,extra_groups=[],timeout=5)
  assert probe.returncode==1 and json.loads(probe.stdout).get('error'),'Installed fixed reader is inaccessible'
  temporary=STATE/'ui/index.html.reference-upload';assert not temporary.exists()
  shutil.copyfile(release/'frontend/dist/index.html',temporary);temporary.chmod(0o644);os.replace(temporary,STATE/'ui/index.html')
  result.update(published=True,api_restart_seconds=round(time.monotonic()-started,3),broker_identity_unchanged=True,agent_authority_unchanged=True,
   other_ports_unchanged=True,reader_installed=True,index_sha256=sha(STATE/'ui/index.html'))
 except BaseException:
  if m['old_drop'] is None:DROP.unlink(missing_ok=True)
  else:DROP.write_text(m['old_drop'])
  shutil.copytree(backup/'ui',STATE/'ui',dirs_exist_ok=True)
  subprocess.run(['systemctl','daemon-reload'],check=True);subprocess.run(['systemctl','restart',API],check=True,timeout=30)
  result['code_ui_rolled_back']=True
  raise
 finally:
  out=backup/'result.json';out.write_text(json.dumps(result,indent=2)+'\n');out.chmod(0o600)
 print(json.dumps({**result,'evidence':str(out)}))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--stage',action='store_true');parser.add_argument('--apply');args=parser.parse_args()
 if args.stage:stage()
 elif args.apply:apply(args.apply)
 else:parser.error('Choose --stage or --apply')

#!/usr/bin/env python3
"""API-only follow-up; preserve upgraded Broker and all protected identities."""
import argparse,json,os,shutil,sqlite3,subprocess,time
from pathlib import Path
from deploy_policy_semantics import service,guard,authority,listeners,sha
from deploy_value_release import API,BROKER,STATE,SOURCE,DROPS,call

def apply():
 assert os.getuid()==0;guard();before=service(API);broker=service(BROKER);saved=authority();ports=listeners()
 live=Path(before['WorkingDirectory']);assert live==Path('/opt/agentscope-value-20261012-223824')
 paths=['backend/agentscope_app/managed/schema.py','backend/agentscope_app/managed/worker.py','backend/agentscope_app/instances/approval_views.py']
 for p in paths:
  raw=subprocess.check_output(['git','-c','safe.directory='+str(SOURCE),'-C',str(SOURCE),'show','HEAD:'+p])
  import hashlib
  assert sha(live/p)==hashlib.sha256(raw).hexdigest(),'Unexpected live change: '+p
 release=Path('/opt/agentscope-value-read-'+time.strftime('%Y%m%d-%H%M%S'));release.mkdir(mode=0o755)
 for folder in ('backend','scripts','integrations','bin','dsh','frontend'):
  if (live/folder).exists():shutil.copytree(live/folder,release/folder,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 for p in paths:shutil.copy2(SOURCE/p,release/p)
 backup=STATE/'release-backups'/release.name;backup.mkdir(parents=True,mode=0o700)
 with sqlite3.connect(STATE/'demo.sqlite3') as src,sqlite3.connect(backup/'demo.sqlite3') as dst:src.backup(dst)
 (backup/'demo.sqlite3').chmod(0o600)
 drop=DROPS['api'];previous=drop.read_text();assert service(API)==before and service(BROKER)==broker and authority()==saved
 result={'release':str(release),'previous_api':before,'broker':broker,'authority_before':saved,'started_at':time.time(),'overlay_sha256':{p:sha(SOURCE/p) for p in paths}}
 try:
  drop.write_text('[Service]\nTimeoutStopSec=10\nWorkingDirectory='+str(release)+'\nExecStart=\nExecStart=/opt/agentscope/.venv/bin/python '+str(release)+'/scripts/scope_systemd_exec.py api\nExecStartPost=\nExecStartPost=/opt/agentscope/.venv/bin/python '+str(release)+'/scripts/scope_systemd_exec.py api-ready\n')
  subprocess.run(['systemctl','daemon-reload'],check=True)
  subprocess.run(['systemctl','restart',API],check=True,timeout=30)
  for _ in range(30):
   now=authority()
   if now['agents']==saved['agents']:break
   time.sleep(.3)
  assert now==saved and service(BROKER)==broker and listeners()==ports
  result.update(published=True,authority_after=now,identity_preserved=True,finished_at=time.time(),api=service(API))
 except BaseException:
  drop.write_text(previous);subprocess.run(['systemctl','daemon-reload'],check=True);subprocess.run(['systemctl','restart',API],check=True,timeout=30)
  result.update(published=False,code_rolled_back=True);raise
 finally:
  path=backup/'result.json';path.write_text(json.dumps(result,indent=2));path.chmod(0o600);print(json.dumps({'published':result.get('published',False),'evidence':str(path)}))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true',required=True);p.parse_args();apply()

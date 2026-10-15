#!/usr/bin/env python3
"""Publish only immutable UI assets and atomically switch index.html; no services."""
import argparse
import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from deploy_policy_semantics import authority,service,listeners,sha,guard,files,api

ROOT=Path(__file__).resolve().parents[1]
STATE=Path('/var/lib/agentscope-scope-demo')
BASE='fddc532aa8cabfeb41b8d6a09793a74529c51836'
EXPECTED_INDEX='c0401cf7dbd1eccde602fea924ccc1bec95e1c1b9857190fb5003ec082b8066f'
API='agentscope-scope-demo-api.service'
BROKER='agentscope-scope-demo-broker.service'

def git(*args):return subprocess.check_output(['git','-c','safe.directory='+str(ROOT),'-C',str(ROOT),*args])
def publish():
 assert os.geteuid()==0,'Run explicit publication as root'
 assert not git('status','--porcelain').strip(),'Commit reviewed source first'
 guard()
 before_api,before_broker=service(API),service(BROKER)
 before_authority,before_listeners=authority(),listeners()
 live=Path(before_api['WorkingDirectory'])
 # This is a UI overlay on the reviewed API baseline, not a backend release.
 import hashlib
 for rel,digest in files(live/'backend/agentscope_app').items():
  assert hashlib.sha256(git('show',BASE+':backend/agentscope_app/'+rel)).hexdigest()==digest,'API baseline changed: '+rel
 ui=STATE/'ui';dist=ROOT/'frontend/dist'
 assert sha(ui/'index.html')==EXPECTED_INDEX,'Another UI release has changed the baseline'
 for p in dist.iterdir():
  if p.is_file() and p.name!='index.html':
   assert (ui/p.name).is_file() and sha(ui/p.name)==sha(p),'Unexpected public-file change: '+p.name
 backup=STATE/'release-backups'/('unified-policy-scope-'+time.strftime('%Y%m%d-%H%M%S'))
 backup.mkdir(mode=0o700,parents=True)
 shutil.copy2(ui/'index.html',backup/'index.html')
 result={'published':False,'source_commit':git('rev-parse','HEAD').decode().strip(),'publication':'static-ui-only','previous_index_sha256':EXPECTED_INDEX,'agent_actions':False,'policy_application':False,'service_restart':False}
 try:
  # Assets are content addressed. Keep all old assets for already-open pages.
  for p in (dist/'assets').iterdir():
   assert p.is_file() and not p.is_symlink()
   dest=ui/'assets'/p.name
   if dest.exists():assert sha(dest)==sha(p),'Immutable asset collision'
   else:
    temporary=dest.with_name(dest.name+'.scope-upload')
    assert not temporary.exists()
    shutil.copyfile(p,temporary);temporary.chmod(0o644);os.replace(temporary,dest)
  guard()
  assert service(API)==before_api and service(BROKER)==before_broker
  assert authority()==before_authority and listeners()==before_listeners
  temporary=ui/'index.html.scope-upload'
  assert not temporary.exists()
  shutil.copyfile(dist/'index.html',temporary);temporary.chmod(0o644);os.replace(temporary,ui/'index.html')
  with urllib.request.urlopen('http://127.0.0.1:18003/',timeout=10) as response:
   assert response.status==200 and hashlib.sha256(response.read()).hexdigest()==sha(dist/'index.html')
  assert api('/api/health')['ok']
  assert service(API)==before_api and service(BROKER)==before_broker
  assert authority()==before_authority and listeners()==before_listeners
  result.update(published=True,index_sha256=sha(ui/'index.html'),api_identity_unchanged=True,broker_identity_unchanged=True,agent_authority_unchanged=True,other_ports_unchanged=True)
 except BaseException:
  temporary=ui/'index.html.scope-rollback'
  shutil.copyfile(backup/'index.html',temporary);temporary.chmod(0o644);os.replace(temporary,ui/'index.html')
  result['entry_rolled_back']=True
  raise
 finally:
  (backup/'result.json').write_text(json.dumps(result,indent=2)+'\n');(backup/'result.json').chmod(0o600)
 print(json.dumps({**result,'evidence':str(backup/'result.json')}))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true',required=True);parser.parse_args();publish()

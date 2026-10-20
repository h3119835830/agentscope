#!/usr/bin/env python3
"""Publish the reviewed polling-snapshot UI without restarting any service."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

from deploy_policy_semantics import api,authority,guard,listeners,service,sha

ROOT=Path(__file__).resolve().parents[1]
STATE=Path('/var/lib/agentscope-scope-demo')
API='agentscope-scope-demo-api.service'
BROKER='agentscope-scope-demo-broker.service'

def git(*args):
 return subprocess.check_output(['git','-c','safe.directory='+str(ROOT),'-C',str(ROOT),*args],text=True).strip()

def runtime():
 return {'api':service(API),'broker':service(BROKER),'authority':authority(),'other_listeners':listeners()}

def verify_source():
 assert not git('status','--porcelain'),'Commit reviewed source and rebuild before publication'
 dist=ROOT/'frontend/dist';index=dist/'index.html';assets=dist/'assets'
 assert index.is_file() and assets.is_dir()
 html=index.read_text()
 referenced=[p.split('"',1)[0] for p in html.split('/assets/')[1:]]
 assert referenced and all((assets/p).is_file() for p in referenced),'Built index references missing assets'
 return dist

def check():
 dist=verify_source();live=STATE/'ui';before=runtime()
 assert live.is_dir() and (live/'index.html').is_file()
 unchanged=[]
 for source in dist.iterdir():
  if source.is_file() and source.name!='index.html':
   target=live/source.name
   assert target.is_file() and sha(target)==sha(source),'Unexpected top-level UI change: '+source.name
   unchanged.append(source.name)
 return {'source_commit':git('rev-parse','HEAD'),'dist_index_sha256':sha(dist/'index.html'),
         'live_index_sha256':sha(live/'index.html'),'unchanged_top_level':sorted(unchanged),'runtime':before}

def publish():
 assert os.geteuid()==0,'Run explicit publication as root'
 dist=verify_source();ui=STATE/'ui';before=runtime();guard()
 checked=check();assert runtime()==before,'Runtime changed during preflight'
 backup=STATE/'release-backups'/('session-snapshot-ui-'+time.strftime('%Y%m%d-%H%M%S'))
 backup.mkdir(parents=True,mode=0o700);shutil.copy2(ui/'index.html',backup/'index.html')
 result={**checked,'published':False,'publication':'static-ui-only','service_restart':False,
         'agent_actions':False,'policy_application':False,'started_at':time.time()}
 def persist():
  path=backup/'result.json';path.write_text(json.dumps(result,indent=2)+'\n');path.chmod(0o600)
 persist()
 try:
  for source in (dist/'assets').iterdir():
   assert source.is_file() and not source.is_symlink()
   target=ui/'assets'/source.name
   if target.exists():assert sha(target)==sha(source),'Immutable asset collision: '+source.name
   else:
    temporary=target.with_name(target.name+'.snapshot-upload');assert not temporary.exists()
    shutil.copyfile(source,temporary);temporary.chmod(0o644);os.replace(temporary,target)
  guard();assert runtime()==before,'Runtime changed before entry switch'
  temporary=ui/'index.html.snapshot-upload';assert not temporary.exists()
  shutil.copyfile(dist/'index.html',temporary);temporary.chmod(0o644);os.replace(temporary,ui/'index.html')
  with urllib.request.urlopen('http://127.0.0.1:18003/',timeout=10) as response:
   assert response.status==200 and hashlib.sha256(response.read()).hexdigest()==sha(dist/'index.html')
  assert api('/api/health')['ok'] and runtime()==before,'Runtime changed after static publication'
  result.update(published=True,index_sha256=sha(ui/'index.html'),runtime_after=runtime(),finished_at=time.time())
 except BaseException as error:
  result.update(error=str(error)[:800],entry_rolled_back=False)
  rollback=ui/'index.html.snapshot-rollback';shutil.copyfile(backup/'index.html',rollback);rollback.chmod(0o644);os.replace(rollback,ui/'index.html')
  result['entry_rolled_back']=True
  raise
 finally:
  persist();print(json.dumps({'published':result['published'],'evidence':str(backup/'result.json')}))

if __name__=='__main__':
 parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True)
 group.add_argument('--check',action='store_true');group.add_argument('--publish',action='store_true')
 args=parser.parse_args()
 if args.check:print(json.dumps(check(),indent=2))
 else:publish()

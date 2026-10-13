#!/usr/bin/env python3
"""Publish the announcement at both existing URLs, preserving overview and runtime."""
import argparse,hashlib,json,os,shutil,subprocess,time,urllib.request
from pathlib import Path
from deploy_policy_semantics import authority,files,listeners,service,sha

ROOT=Path(__file__).resolve().parents[1]
STATE=Path('/var/lib/agentscope-scope-demo')
UNITS=['agentscope-scope-demo-api.service','agentscope-scope-demo-broker.service']
NAMES=('value-announcement.html','value-evidence.html')

def runtime():
 return {'services':{u:service(u) for u in UNITS},'authority':authority(),'other_listeners':listeners()}

def main():
 assert os.geteuid()==0
 ui=STATE/'ui';source=ROOT/'frontend/public'
 assert ui.resolve()==ui
 for name in NAMES:
  target=ui/name
  assert target.is_file() and not target.is_symlink()
  assert not os.path.lexists(target.with_name(name+'.article-staging'))
 expected=sha(source/NAMES[0]);source_hash=sha(ROOT/'docs/research/value-reliability-20261012/announcement.md')
 assert all(sha(source/name)==expected for name in NAMES),'Announcement URLs must contain identical content'
 assert 'name="announcement-source-sha256" content="'+source_hash+'"' in (source/NAMES[0]).read_text()
 before=runtime();before_files=files(ui)
 expected_changes={name for name in NAMES if before_files[name]!=expected}
 backup=STATE/'release-backups'/('announcement-page-'+time.strftime('%Y%m%d-%H%M%S'))
 backup.mkdir(parents=True,mode=0o700);(backup/'previous').mkdir();(backup/'articles').mkdir()
 for name in NAMES:
  shutil.copy2(ui/name,backup/'previous'/name);shutil.copy2(source/name,backup/'articles'/name)
 result={'started_at':time.time(),'source_commit_baseline':subprocess.check_output(['git','-c','safe.directory='+str(ROOT),'-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
  'article_sha256':expected,'source_sha256':source_hash,'before':before,'ui_files_before':before_files,
  'target_files':list(NAMES),'services_restarted':False,'policy_mutated':False}
 def persist():
  p=backup/'result.json';p.write_text(json.dumps(result,indent=2));p.chmod(0o600)
 persist()
 try:
  assert files(ui)==before_files and runtime()==before
  for name in NAMES:
   target=ui/name;temp=target.with_name(name+'.article-staging')
   shutil.copy2(backup/'articles'/name,temp);os.replace(temp,target)
   with urllib.request.urlopen('http://localhost:18003/'+name,timeout=10) as response:
    assert hashlib.sha256(response.read()).hexdigest()==expected
  after_files=files(ui)
  changed={p for p in before_files.keys()|after_files.keys() if before_files.get(p)!=after_files.get(p)}
  assert changed==expected_changes,'An overview or another static asset changed'
  after=runtime();assert after==before,'Live execution identity changed'
  if (ROOT/'frontend/dist').is_dir():
   for name in NAMES:shutil.copy2(source/name,ROOT/'frontend/dist'/name)
  result.update(published=True,after=after,ui_files_after=after_files,changed_files=sorted(changed),finished_at=time.time())
 except BaseException as error:
  result.update(published=False,error=str(error)[:500],articles_rolled_back=[])
  for name in NAMES:
   target=ui/name;temp=target.with_name(name+'.article-staging')
   if target.exists() and sha(target)==expected and before_files[name]!=expected:
    shutil.copy2(backup/'previous'/name,temp);os.replace(temp,target)
    result['articles_rolled_back'].append(name)
  raise
 finally:
  persist();print(json.dumps({'published':result.get('published',False),'evidence':str(backup/'result.json')}))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true',required=True);p.parse_args();main()

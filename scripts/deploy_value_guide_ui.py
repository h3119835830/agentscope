#!/usr/bin/env python3
"""Publish static UI without restarting services or changing policy authority."""
import argparse,hashlib,json,os,pwd,shutil,subprocess,time,urllib.request
from pathlib import Path
from deploy_policy_semantics import authority,files,listeners,service,sha

SOURCE=Path(__file__).resolve().parents[1]
STATE=Path('/var/lib/agentscope-scope-demo')
UNITS=['agentscope-scope-demo-api.service','agentscope-scope-demo-broker.service']

def main():
 assert os.getuid()==0
 ui=STATE/'ui';info=ui.lstat()
 # Existing static assets belong to the trusted local installer (happy).
 # They are display resources, not root-owned execution authority artifacts.
 assert ui.resolve()==ui and info.st_uid in (0,pwd.getpwnam('happy').pw_uid) and not info.st_mode&0o022
 before={'services':{u:service(u) for u in UNITS},'authority':authority(),'other_listeners':listeners(),'ui_files':files(ui)}
 assert before['services'][UNITS[0]]['WorkingDirectory']=='/opt/agentscope-value-read-20261012-224541'
 assert before['services'][UNITS[1]]['WorkingDirectory']=='/opt/agentscope-value-startup-20261012-225631'
 name='agentscope-value-guide-ui-'+time.strftime('%Y%m%d-%H%M%S')
 release=Path('/opt')/name;shutil.copytree(SOURCE/'frontend/dist',release)
 backup=STATE/'release-backups'/name;backup.mkdir(parents=True,mode=0o700)
 shutil.copytree(ui,backup/'ui')
 result={'release':str(release),'started_at':time.time(),'before':before,'static_files':files(release),
  'source_baseline':subprocess.check_output(['git','-c','safe.directory='+str(SOURCE),'-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip(),
  'source_hashes':{str(p.relative_to(SOURCE)):sha(p) for p in [SOURCE/'frontend/src/SecurityNotice.jsx',SOURCE/'frontend/src/ProductOverview.jsx',SOURCE/'frontend/src/securitySceneStories.mjs',SOURCE/'frontend/src/securityNotice.css',SOURCE/'scripts/build_value_announcement.py',SOURCE/'docs/research/value-reliability-20261012/announcement.md']},
  'services_restarted':False,'policy_mutated':False}
 published=[]
 def persist():
  p=backup/'result.json';p.write_text(json.dumps(result,indent=2));p.chmod(0o600)
 def replace(src,dst):
  assert not dst.is_symlink()
  dst.parent.mkdir(parents=True,exist_ok=True)
  temp=dst.with_name(dst.name+'.guide-staging');assert not temp.exists()
  shutil.copy2(src,temp);os.replace(temp,dst)
 persist()
 try:
  assert files(ui)==before['ui_files'] and authority()==before['authority']
  assert {u:service(u) for u in UNITS}==before['services']
  # Retain old hashed assets. Publish references only after all new assets exist.
  paths=sorted(p for p in release.rglob('*') if p.is_file())
  paths.sort(key=lambda p:p.name=='index.html')
  for src in paths:
   rel=src.relative_to(release);dst=ui/rel
   if dst.exists() and sha(dst)==sha(src):continue
   replace(src,dst);published.append(str(rel))
  for url,relative in [('http://localhost:18003/','index.html'),('http://localhost:18003/value-announcement.html','value-announcement.html')]:
   with urllib.request.urlopen(url,timeout=10) as response:assert hashlib.sha256(response.read()).hexdigest()==sha(release/relative)
  after={'services':{u:service(u) for u in UNITS},'authority':authority(),'other_listeners':listeners()}
  assert all(after[k]==before[k] for k in after),'Live identity changed during static publication'
  result.update(published=True,after=after,published_files=published,finished_at=time.time())
 except BaseException as error:
  result.update(published=False,error=str(error)[:500])
  for rel in reversed(published):
   dst=ui/rel;old=backup/'ui'/rel
   # Never overwrite a concurrent publisher's different result.
   if old.exists() and sha(dst)==sha(release/rel):replace(old,dst)
  result['baseline_files_restored']=True
  raise
 finally:
  persist();print(json.dumps({'published':result.get('published',False),'evidence':str(backup/'result.json')}))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true',required=True);p.parse_args();main()

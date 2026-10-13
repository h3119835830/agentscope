#!/usr/bin/env python3
"""Replace only the article HTML; preserve every overview asset and live identity."""
import argparse,hashlib,json,os,shutil,subprocess,time,urllib.request
from pathlib import Path
from deploy_policy_semantics import authority,files,listeners,service,sha

ROOT=Path(__file__).resolve().parents[1]
STATE=Path('/var/lib/agentscope-scope-demo')
UNITS=['agentscope-scope-demo-api.service','agentscope-scope-demo-broker.service']
NAME='value-announcement.html'

def runtime():
 return {'services':{u:service(u) for u in UNITS},'authority':authority(),'other_listeners':listeners()}

def main():
 assert os.geteuid()==0
 source=ROOT/'frontend/public'/NAME;ui=STATE/'ui';target=ui/NAME
 assert ui.resolve()==ui and target.is_file() and not target.is_symlink()
 before=runtime();before_files=files(ui)
 name='announcement-public-'+time.strftime('%Y%m%d-%H%M%S')
 backup=STATE/'release-backups'/name;backup.mkdir(parents=True,mode=0o700)
 shutil.copy2(target,backup/'previous.html');shutil.copy2(source,backup/'article.html')
 expected=sha(source)
 result={'started_at':time.time(),'source_commit_baseline':subprocess.check_output(['git','-c','safe.directory='+str(ROOT),'-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
  'article_sha256':expected,'source_sha256':sha(ROOT/'docs/research/value-reliability-20261012/announcement.md'),
  'before':before,'ui_files_before':before_files,'only_target':NAME,'services_restarted':False,'policy_mutated':False}
 temp=target.with_name(NAME+'.article-staging')
 def persist():
  p=backup/'result.json';p.write_text(json.dumps(result,indent=2));p.chmod(0o600)
 persist()
 try:
  assert not temp.exists() and files(ui)==before_files and runtime()==before
  shutil.copy2(backup/'article.html',temp);os.replace(temp,target)
  with urllib.request.urlopen('http://localhost:18003/'+NAME,timeout=10) as response:
   assert hashlib.sha256(response.read()).hexdigest()==expected
  after_files=files(ui);changed={p for p in before_files.keys()|after_files.keys() if before_files.get(p)!=after_files.get(p)}
  assert changed=={NAME},'An overview or another static asset changed'
  after=runtime();assert after==before,'Live execution identity changed'
  # Keep the prepared distribution consistent without rebuilding its overview.
  dist=ROOT/'frontend/dist'/NAME
  if dist.parent.is_dir():shutil.copy2(source,dist)
  result.update(published=True,after=after,ui_files_after=after_files,changed_files=sorted(changed),finished_at=time.time())
 except BaseException as error:
  result.update(published=False,error=str(error)[:500])
  if target.exists() and sha(target)==expected:
   shutil.copy2(backup/'previous.html',temp);os.replace(temp,target)
   result['article_rolled_back']=True
  raise
 finally:
  persist();print(json.dumps({'published':result.get('published',False),'evidence':str(backup/'result.json')}))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true',required=True);p.parse_args();main()

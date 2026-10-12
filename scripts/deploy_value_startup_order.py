#!/usr/bin/env python3
"""Finalize the tested startup publication order; exact live baseline, no approval restore."""
import argparse,json,os,shutil,subprocess,time,urllib.request
from pathlib import Path
from deploy_policy_semantics import authority,guard,service,listeners,files,sha

SOURCE=Path(__file__).resolve().parents[1]
STATE=Path('/var/lib/agentscope-scope-demo')
API='agentscope-scope-demo-api.service';BROKER='agentscope-scope-demo-broker.service'
DROP=Path('/etc/systemd/system/'+BROKER+'.d/99zz-value-reliability-20261012.conf')

def call(path):
 req=urllib.request.Request('http://localhost:18003'+path,data=b'{}',headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=140) as response:return json.load(response)

def main():
 assert os.getuid()==0;guard()
 api_before=service(API);before=service(BROKER)
 assert api_before['WorkingDirectory']=='/opt/agentscope-value-read-20261012-224541'
 old=Path('/opt/agentscope-value-20261012-223824');assert before['WorkingDirectory']==str(old)
 relative='backend/broker/instance_runtime.py'
 original=(old/relative).read_text()
 earlier="            record['ready']=True\n            record['agent_identity']=identity(record['agent_pid'])\n"
 corrected="            record['agent_identity']=identity(record['agent_pid'])\n            record['ready']=True\n"
 assert original.count(earlier)==1
 assert (SOURCE/relative).read_text()==original.replace(earlier,corrected),'Only verified readiness ordering may differ'
 before_authority=authority();other=listeners();previous_drop=DROP.read_text()
 targets=[ident for ident,row in before_authority['agents'].items() if row['active']]
 assert len(targets)==3
 release=Path('/opt/agentscope-value-startup-'+time.strftime('%Y%m%d-%H%M%S'))
 shutil.copytree(old,release,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 shutil.copy2(SOURCE/relative,release/relative)
 backup=STATE/'release-backups'/release.name;backup.mkdir(parents=True,mode=0o700)
 result={'release':str(release),'started_at':time.time(),'previous_broker':before,'api_before':api_before,
  'authority_before':before_authority,'restart_targets':targets,'source_hash':sha(SOURCE/relative),
  'change':'Publish agent_identity before ready; no other live code differences','previous_drop':previous_drop}
 def persist():
  path=backup/'result.json';path.write_text(json.dumps(result,indent=2));path.chmod(0o600)
 persist()
 assert service(API)==api_before and service(BROKER)==before and authority()==before_authority and listeners()==other
 try:
  for ident in targets:call('/api/agent-instances/'+ident+'/stop')
  subprocess.run(['systemctl','stop',BROKER],check=True,timeout=30)
  DROP.write_text(previous_drop.replace(str(old),str(release)))
  subprocess.run(['systemctl','daemon-reload'],check=True)
  # The API has a systemd BindsTo/After dependency on Broker. A Broker stop
  # intentionally stops API too; start both, without assuming its PID survives.
  subprocess.run(['systemctl','start',BROKER,API],check=True,timeout=45)
  for ident in targets:
   row=call('/api/agent-instances/'+ident+'/start')
   assert row['active'] and row['policy_hash']==before_authority['agents'][ident]['policy_hash']
   assert row['generation']!=before_authority['agents'][ident]['generation']
  after=authority()
  assert after['system']==before_authority['system'] and after['dsl_scopes']==before_authority['dsl_scopes']
  assert all(after['agents'][i]['policy_hash']==r['policy_hash'] for i,r in before_authority['agents'].items())
  assert all(not r['active'] for i,r in after['agents'].items() if i not in targets)
  assert service(API)['WorkingDirectory']==api_before['WorkingDirectory'] and listeners()==other
  result.update(published=True,authority_after=after,services={'api':service(API),'broker':service(BROKER)},api_restarted_by_systemd_dependency=True,finished_at=time.time())
 except BaseException as error:
  result.update(published=False,error=str(error)[:800]);persist()
  subprocess.run(['systemctl','stop',BROKER],timeout=30)
  DROP.write_text(previous_drop);subprocess.run(['systemctl','daemon-reload'],check=True)
  subprocess.run(['systemctl','start',BROKER,API],check=True,timeout=45)
  result['code_rolled_back_without_restarting_agents']=True
  raise
 finally:
  persist();print(json.dumps({'published':result.get('published',False),'evidence':str(backup/'result.json')}))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true',required=True);p.parse_args();main()

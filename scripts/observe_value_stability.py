#!/usr/bin/env python3
"""Read-only observation of live authority; writes metadata, never restarts agents."""
import argparse,json,os,pwd,subprocess,time,urllib.request
from pathlib import Path

STATE=Path('/var/lib/agentscope-scope-demo/value-observation-20261012')
UNITS=['agentscope-scope-demo-api.service','agentscope-scope-demo-broker.service']

def services():
 result={}
 for unit in UNITS:
  raw=subprocess.check_output(['systemctl','show',unit,'-p','MainPID','-p','NRestarts','-p','ActiveState','-p','WorkingDirectory'],text=True)
  item=dict(line.split('=',1) for line in raw.splitlines());pid=item['MainPID']
  if pid!='0':item['start_ticks']=Path('/proc',pid,'stat').read_text().rsplit(') ',1)[1].split()[19]
  result[unit]=item
 return result

def api(path):
 start=time.perf_counter()
 with urllib.request.urlopen('http://localhost:18003'+path,timeout=6) as response:data=json.load(response)
 return data,round((time.perf_counter()-start)*1000,2)

def proof(ident,row):
 user=pwd.getpwnam('agentscope-api')
 def demote():os.initgroups(user.pw_name,user.pw_gid);os.setgid(user.pw_gid);os.setuid(user.pw_uid)
 code='import socket,sys;s=socket.socket(socket.AF_UNIX);s.settimeout(4);s.connect("/run/agentscope-scope-demo/broker.sock");s.sendall(sys.stdin.buffer.read()+b"\\n");print(s.makefile("rb").readline().decode())'
 payload={'action':'agent-instance-execution-status','instance_id':ident,'generation':row['generation'],'policy_hash':row['policy_hash']}
 r=subprocess.run(['/usr/bin/python3','-c',code],input=json.dumps(payload),text=True,capture_output=True,timeout=5,preexec_fn=demote,check=True)
 result=json.loads(r.stdout)
 if not result['ok']:raise ValueError('Broker proof unavailable')
 return result['result']

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--init',action='store_true');args=parser.parse_args()
 assert os.getuid()==0
 STATE.mkdir(mode=0o700,exist_ok=True);assert STATE.stat().st_uid==0 and not STATE.stat().st_mode&0o077
 path=STATE/'observation.json'
 if args.init:
  assert not path.exists(),'Observation already exists; use check without --init'
  rows,_=api('/api/agent-instances')
  active={r['id']:{k:r[k] for k in ('pid','generation','policy_hash')} for r in rows['instances'] if r['mode']=='controlled' and r['active']}
  assert len(active)==3 and all(proof(i,r)['protection_fresh'] for i,r in active.items())
  data={'schema':'agentscope.stability-observation.v1','started_at':time.time(),'due_at':time.time()+86400,'baseline':active,'services':services(),'samples':[],
   'method':'Hourly samples plus systemd/Broker journal review. No claim of continuous latency measurement. No automatic permission recovery.'}
 else:data=json.loads(path.read_text())
 sample={'at':time.time(),'issues':[],'services':services(),'execution':{}}
 try:
  health,latency=api('/api/health');sample['health_ms']=latency
  assert health['ok'];_,sample['overview_ms']=api('/api/console/summary')
 except Exception as error:sample['issues'].append('console_unreachable:'+type(error).__name__)
 for ident,row in data['baseline'].items():
  try:
   current=proof(ident,row);sample['execution'][ident]={k:current[k] for k in ('gate','protection_fresh','pending_events','outstanding_calls')}
   if current['gate']!='open' or not current['protection_fresh']:sample['issues'].append('protection_not_verified:'+ident)
  except Exception:sample['issues'].append('execution_identity_or_broker_changed:'+ident)
 if sample['services']!=data['services']:sample['issues'].append('service_identity_or_state_changed')
 if sample.get('overview_ms',0)>5000:sample['issues'].append('overview_read_over_5s')
 raw=subprocess.check_output(['journalctl','-u',UNITS[0],'-u',UNITS[1],'--since','@'+str(int(data['started_at'])),'--no-pager','-o','json'],text=True)
 failures=sum(any(word in json.loads(line).get('MESSAGE','') for word in ('Protection check failed','Failed with result','stop-sigterm timed out')) for line in raw.splitlines() if line)
 sample['journal_failure_count']=failures
 if failures:sample['issues'].append('journal_failure_during_window')
 data['samples'].append(sample);data['status']='needs_review' if any(s['issues'] for s in data['samples']) else 'observing'
 if time.time()>=data['due_at']:
  gaps=[b['at']-a['at'] for a,b in zip(data['samples'],data['samples'][1:])]
  enough=len(data['samples'])>=20 and max(gaps,default=86400)<=7200
  data['status']='passed_hourly_observation' if data['status']=='observing' and enough else 'needs_review'
  data['sampling_sufficient']=enough
 path.write_text(json.dumps(data,indent=2));path.chmod(0o600)
 print(json.dumps({'status':data['status'],'elapsed_hours':round((time.time()-data['started_at'])/3600,3),'due_at':data['due_at'],'sample_count':len(data['samples']),'latest':sample,'report':str(path)}))

if __name__=='__main__':main()

#!/usr/bin/env python3
"""Root-only fixed protocol checks for local controller/oracle read isolation.
No arbitrary command, private file bytes, or model reasoning are exported.
"""
import grp,json,os,sys,time,uuid
from pathlib import Path
from managed_control import api
STATE=Path('/var/lib/agentscope-scope-demo')
ROOT=Path(__file__).resolve().parents[1]

def run(task,output=None):
 if os.getuid()!=0:raise RuntimeError('Fixed isolated acceptance requires root')
 end=time.monotonic()+700
 while time.monotonic()<end:
  state=api('/api/managed/tasks/'+task)['state']
  if state['phase']=='failed':raise RuntimeError(state.get('error'))
  if state['phase']=='running' and state['gate']=='open':
   native=api('/api/managed/tasks/'+task+'/native')
   if native['status']=='idle' and native['active_tools']==0:break
  time.sleep(1)
 else:raise TimeoutError('Native initial read did not finish')
 assert 'block read file '+json.dumps(str(ROOT)+'/**') in state['baseline_extra']
 canary=STATE/'report/controller-read-canary.txt';canary.write_text('public control read canary\n');canary.chmod(0o644)
 fixture=ROOT/'backend/agentscope_app/bootstrap/fixtures/rq5/manifest.json'
 targets=[(fixture,False),(STATE/'demo.sqlite3',False),(canary,False),(Path('/var/lib/agentscope-rq5-v1/task-python/pyvenv.cfg'),True)]
 commands=Path('/run/agentscope-scope-demo/commands')/task
 assert commands.resolve()==commands and commands.is_dir()
 workspace=Path('/s')/task/'r';events=workspace/'.actplane/events.jsonl';results=[]
 for target,expected_allow in targets:
  assert target.is_file()
  ident=uuid.uuid4().hex;scratch=workspace.parent/'tmp'/('control-read-'+ident)
  scratch.mkdir();os.chown(scratch,0,grp.getgrnam('agentscope-task').gr_gid);scratch.chmod(0o2770)
  request={'request_id':ident,'kind':'managed-operation','operation':'read','target':str(target),'scratch':str(scratch)}
  temporary=commands/('request-'+ident+'.json')
  fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o640)
  try:os.write(fd,json.dumps(request).encode());os.fsync(fd)
  finally:os.close(fd)
  os.replace(temporary,commands/'request.json')
  result_path=workspace.parent/'.runtime-control/scope-result.json';deadline=time.monotonic()+12
  while time.monotonic()<deadline:
   try:
    result=json.loads(result_path.read_text())
    if result.get('request_id')==ident:break
   except (FileNotFoundError,ValueError):pass
   time.sleep(.1)
  else:raise TimeoutError('Fixed root protocol probe did not return')
  probe=result['probe'];matching=[]
  for _ in range(30):
   matching=[json.loads(line) for line in events.read_text().splitlines() if json.loads(line).get('pid')==probe['pid'] and json.loads(line).get('process_domain_id')==state['binding']['domain_id'] and json.loads(line).get('blocked') and json.loads(line).get('target')==str(target)]
   if matching:break
   time.sleep(.1)
  passed=(probe['success'] and not probe['blocked']) if expected_allow else (probe['blocked'] and not probe['success'] and bool(matching))
  classification=('correct_allow' if expected_allow else 'correct_block') if passed else ('false_block' if expected_allow and probe['blocked'] else 'missed_or_unverified_block')
  row={'target':str(target),'pid':probe['pid'],'process_domain_id':state['binding']['domain_id'],'errno':probe.get('errno'),'kernel_records':len(matching),'operation':'read','expected':'allow' if expected_allow else 'deny','classification':classification,'attempted_by_agent':False,'private_bytes_exported':False}
  results.append(row);print(json.dumps(row),flush=True)

 after=api('/api/managed/tasks/'+task)['state']
 assert after['version']==state['version'] and after['baseline_hash']==state['baseline_hash'] and after['session_id']==state['session_id']
 report={'schema':'ControlReadIsolation/1','task':task,'session_id':state['session_id'],'version':state['version'],'baseline_hash':state['baseline_hash'],'passed':all(x['classification'] in ('correct_block','correct_allow') for x in results),'same_loaded_policy':True,'probes':results,'oracle_content_exported':False}
 (output or STATE/'report/control-read-isolation.json').write_text(json.dumps(report,indent=2))
 return report
if __name__=='__main__':
 result=run(sys.argv[1],Path(sys.argv[2]) if len(sys.argv)>2 else None)
 if not result['passed']:raise SystemExit(1)

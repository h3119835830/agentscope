#!/usr/bin/env python3
"""Native conversation and bounded public sandbox evidence; no private exports."""
import argparse,json,time,hashlib,urllib.error
from pathlib import Path
from managed_control import api
STATE=Path('/var/lib/agentscope-scope-demo')
def wait_idle(task,deadline=240):
 base='/api/managed/tasks/'+task
 end=time.monotonic()+deadline
 while time.monotonic()<end:
  try:r=api(base)
  except urllib.error.URLError:
   time.sleep(1);continue
  s=r['state']
  if s['phase']!='running':raise RuntimeError('Task paused or stopped: '+str(s['phase']))
  if s['gate']=='open':
   n=api(base+'/native')
   if n['status']=='idle' and not n['active_tools']:return r,n
  time.sleep(1)
 raise RuntimeError('Native turn or Pi analysis did not settle')
def prompt(task,message):
 before,_=wait_idle(task)
 receipt=api('/api/managed/tasks/'+task+'/prompt',{'text':message})
 time.sleep(.2)
 after,native=wait_idle(task)
 row={'message':message,'native_receipt':receipt,'turn':native['turn'],'version':after['state']['version'],'revision':after['state']['revision'],'completed':True,'before_version':before['state']['version'],'message_sha256':hashlib.sha256(message.encode()).hexdigest()}
 path=STATE/'report/task-sandbox-conversation.jsonl'
 with path.open('a') as f:f.write(json.dumps({'task':task,**row},ensure_ascii=False)+'\n')
 print(json.dumps(row,ensure_ascii=False),flush=True)
 return row
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('task');p.add_argument('message');a=p.parse_args();prompt(a.task,a.message)

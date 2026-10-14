#!/usr/bin/env python3
"""Isolated command / PTY / native-workspace acceptance. Never writes 18003 authority."""
import argparse,base64,csv,hashlib,json,os,shutil,socket,time,urllib.request,uuid
from pathlib import Path
import system_policy_acceptance_service as service
ROOT=Path(__file__).resolve().parents[1]
STATE=Path('/var/lib/aslaunch14a'); SOURCE=Path('/opt/aslaunch14a'); PORT=18190

def configure():
 service.STATE=STATE;service.SOURCE=SOURCE;service.TASKS=Path('/sla14a');service.RUNTIME=Path('/run/aslaunch14a');service.PORT=PORT
 original=service.environment
 def environment():
  env=original();env['ACTPLANE_BPF_PIN_ROOT']='/sys/fs/bpf/aslaunch14a';return env
 service.environment=environment

def api(path,body=None):
 req=urllib.request.Request(f'http://127.0.0.1:{PORT}'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=120) as response:return json.load(response)
 except urllib.error.HTTPError as error:raise RuntimeError(f'{error.code} {path}: '+error.read().decode()[:1000]) from None

def apply(prefix,proposal):
 ident=prefix+':'+proposal['id'];body={'proposal_hash':proposal['proposal_hash'],'request_key':uuid.uuid4().hex}
 receipt=api('/api/console/approvals/'+ident+'/approve',body)
 return api('/api/console/approvals/'+ident+'/apply',{**body,'approval_hash':receipt['approval_hash'],'request_key':uuid.uuid4().hex})

def agent_policy(ident,rules):
 row=api('/api/agent-instances/'+ident)
 p=api('/api/agent-instances/'+ident+'/policy/proposals',{'generation':row['generation'],'base_hash':row['policy_hash'],'request_key':uuid.uuid4().hex,'policy':{'network':'model_only','rules':rules}})
 return apply('instance',p)

def rule(action,target,effect):return {'action':action,'target':str(target),'effect':effect,'text':''}

def terminal(ident,action='read',data='',row=None,cursor=0):
 row=row or api('/api/agent-instances/'+ident)
 return api('/api/agent-instances/'+ident+'/terminal',{'generation':row['generation'],'policy_hash':row['policy_hash'],'action':action,'cursor':cursor,'data':base64.b64encode(data.encode()).decode()})

def output(ident,needle):
 deadline=time.monotonic()+12;text=''
 while time.monotonic()<deadline:
  got=terminal(ident);text=base64.b64decode(got['data']).decode(errors='replace')
  if needle in text:return text
  time.sleep(.15)
 raise AssertionError('Expected terminal result not received: '+needle+'; '+text[-1000:])

def prepare():
 if STATE.exists():raise RuntimeError('Owned immutable run already exists')
 project=Path('/s/instance-resources/command-launch-20261014a')
 if project.exists():raise RuntimeError('Refusing existing fixture directory')
 for name,src in [('a','workspace-a'),('b','workspace-b'),('native','workspace-a')]:
  target=project/name;shutil.copytree(ROOT/'examples/manual-session-lab-20261014'/src,target)
  (target/'terminal_agent.py').write_text(TERMINAL_AGENT)
  for item in [target,*target.rglob('*')]:
   os.chown(item,1000,1000);item.chmod(0o755 if item.is_dir() else 0o644)
 service.start()
 (STATE/'fixture.json').write_text(json.dumps({'project':str(project)}));print(json.dumps({'url':f'http://127.0.0.1:{PORT}/?view=connections'}))

TERMINAL_AGENT = '''import csv,json,os,subprocess,sys
print('READY',os.getpid(),flush=True)
def probe():
 result={}
 for label,file in [('normal','input/orders.csv'),('system','vault/token.txt'),('agent','internal/staff.csv')]:
  try:
   with open(file,'rb') as stream:stream.read(1)
   result[label]='allowed'
  except OSError as error:result[label]=error.errno
 child=subprocess.run(['/usr/bin/cat','vault/token.txt'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 result['child_system_denied']=child.returncode!=0
 rows=list(csv.DictReader(open('input/orders.csv')))
 # Fixture business output is independently checked by the oracle, never part of Agent context.
 try:
  open('reports/command-check.txt','w').write('ok')
  result['report_write']='allowed'
 except OSError as error:result['report_write']=error.errno
 print('RESULT '+json.dumps(result),flush=True)
for line in sys.stdin:
 if line.strip()=='probe':probe()
 else:print('ECHO '+line.strip(),flush=True)
'''

def exercise():
 project=Path(json.loads((STATE/'fixture.json').read_text())['project'])
 if (STATE/'ids.json').exists():ids=json.loads((STATE/'ids.json').read_text())
 else:
  ids={}
  for name in ('a','b'):
   row=api('/api/agent-instances',{'name':'Command terminal '+name,'agent_type':'other','resources':[], 'launch':{'command':'python3 -u terminal_agent.py','cwd':str(project/name),'kind':'terminal'}});ids[name]=row['id']
  native=api('/api/agent-instances',{'name':'Native DSH command','agent_type':'dsh','resources':[], 'launch':{'command':'dsh web --host 127.0.0.1 --port {port} --no-open','cwd':str(project/'native'),'kind':'web','web_url':'http://127.0.0.1:{port}/'}});ids['native']=native['id']
  (STATE/'ids.json').write_text(json.dumps(ids))
 shared=api('/api/security/system')
 p=api('/api/security/system/proposals',{'policy':{'network':'model_only','rules':[rule('read',project/name/'vault/token.txt','deny') for name in ('a','b','native')]},'base_hash':shared['policy_hash'],'revision':shared['revision'],'request_key':uuid.uuid4().hex})
 apply('system',p)
 for name in ('a','b','native'):
  rules=[rule('write',project/name/'reports','allow')]
  if name!='b':rules.append(rule('read',project/name/'internal/staff.csv','deny'))
  agent_policy(ids[name],rules)
 results={}
 for name in ('a','b','native'):
  row=api('/api/agent-instances/'+ids[name]+'/start',{})
  assert row['active'] and row['runtime']['verification']['passed']
  before={k:row[k] for k in ('pid','generation','policy_hash')}
  opened=api('/api/agent-instances/'+ids[name]+'/open',{})
  assert opened['url'].startswith(f'http://127.0.0.1:{PORT}/terminal/') if name!='native' else opened['url'].startswith('http://127.0.0.1:')
  assert {k:api('/api/agent-instances/'+ids[name])[k] for k in before}==before
  results[name]={'identity':before,'launch_hash':row['launch']['hash'],'verification_passed':True,'open_reuses_process':True}
  if name!='native':
   output(ids[name],'READY');terminal(ids[name],'write','probe\n')
   text=output(ids[name],'RESULT ');payload=json.loads(next(line.split('RESULT ',1)[1] for line in text.splitlines() if 'RESULT ' in line))
   assert payload['normal']=='allowed' and payload['system'] in (1,13) and payload['child_system_denied'] and payload['report_write']=='allowed'
   assert payload['agent'] in (1,13) if name=='a' else payload['agent']=='allowed'
   results[name]['probe']=payload
 previous=api('/api/agent-instances/'+ids['a'])
 agent_policy(ids['a'],[rule('write',project/'a/reports','allow')])
 current=api('/api/agent-instances/'+ids['a']);assert current['active'] and current['generation']!=previous['generation'] and current['pid']!=previous['pid']
 try:terminal(ids['a'],'write','probe\n',row=previous)
 except RuntimeError as error:assert '409' in str(error)
 else:raise AssertionError('Old terminal identity was accepted')
 terminal(ids['a'],'write','probe\n');text=output(ids['a'],'RESULT ');payload=json.loads(next(line.split('RESULT ',1)[1] for line in text.splitlines() if 'RESULT ' in line))
 assert payload['agent']=='allowed' and payload['system'] in (1,13)
 results['revoke']={'old_identity_rejected':True,'new_generation':current['generation'],'probe':payload}
 (STATE/'acceptance.json').write_text(json.dumps({'passed':True,'instances':ids,'results':results},indent=2));print(json.dumps({'passed':True,'report':str(STATE/'acceptance.json'),'instances':ids}))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','exercise','stop','refresh']);args=parser.parse_args();configure()
 if args.action=='prepare':prepare()
 elif args.action=='exercise':exercise()
 elif args.action=='refresh':service.start()
 else:service.stop()

#!/usr/bin/env python3
"""Isolated HTTP + real provider + real UID-dropped reads, no Agent launch/apply."""
import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path
from deploy_policy_semantics import authority,service,listeners

ROOT=Path(__file__).resolve().parents[1]
PORT=18155
BASE='http://127.0.0.1:'+str(PORT)

def api(path,body=None,status=200):
 request=urllib.request.Request(BASE+path,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(request,timeout=95) as response:
   assert response.status==status
   return json.load(response)
 except urllib.error.HTTPError as error:
  assert error.code==status,('Unexpected isolated HTTP status',error.code)
  return {'status':error.code}

def main():
 assert os.geteuid()==0
 with socket.socket() as check:
  check.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);check.bind(('127.0.0.1',PORT))
 before={'api':service('agentscope-scope-demo-api.service'),'broker':service('agentscope-scope-demo-broker.service'),'authority':authority(),'listeners':listeners()}
 pid=before['api']['MainPID']
 env={k:v for k,v in os.environ.items() if not k.startswith('AGENTSCOPE_') and k not in ('ACTPLANE_BIN','DSH_BIN','DSH_HOME')}
 deployed=dict(v.split(b'=',1) for v in Path('/proc',pid,'environ').read_bytes().split(b'\0') if b'=' in v)
 for name in ('AGENTSCOPE_HISTORY_LLM_KEY','AGENTSCOPE_HISTORY_LLM_MODEL','AGENTSCOPE_HISTORY_LLM_URL'):
  if name.encode() in deployed:env[name]=deployed[name.encode()].decode()
 assert env.get('AGENTSCOPE_HISTORY_LLM_KEY'),'No configured provider; do not fabricate a model run'
 state=Path(tempfile.mkdtemp(prefix='agentscope-reference-accept-'))
 env.update(AGENTSCOPE_STATE_DIR=str(state),AGENTSCOPE_RUNTIME_DIR=str(state/'run'),AGENTSCOPE_BROKER_SOCKET=str(state/'unavailable.sock'),
  AGENTSCOPE_ADMIN_TOKEN=secrets.token_urlsafe(32),AGENTSCOPE_DEV_NO_AUTH='1',AGENTSCOPE_PUBLIC_URL=BASE,
  AGENTSCOPE_INSTANCE_WORKER='0',AGENTSCOPE_HISTORY_WORKER='0',AGENTSCOPE_SCOPE_WORKER='0',
  ACTPLANE_BIN='/missing/actplane',DSH_BIN='/missing/dsh',PYTHONPATH=str(ROOT/'backend'))
 log=(state/'api.log').open('w')
 process=subprocess.Popen(['/opt/agentscope/.venv/bin/python','-m','uvicorn','agentscope_app.main:app','--host','127.0.0.1','--port',str(PORT)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 report={'passed':False,'real_provider':True,'isolated_http_port':PORT,'agent_started':False,'policy_applied':False,'computer_use':False,'checks':[]}
 output=ROOT/'docs/REVIEW/evidence/workspace-reference-reader-20261015';output.mkdir(parents=True,exist_ok=True)
 try:
  for _ in range(80):
   assert process.poll() is None,'Isolated API exited'
   try:
    if api('/api/health')['ok']:break
   except OSError:time.sleep(.15)
  else:raise RuntimeError('Isolated API readiness timeout')
  root=Path('/home/happy/projects/agentscope-reference-fixtures-20261015')/state.name
  (root/'internal').mkdir(parents=True);(root/'input').mkdir()
  (root/'README.md').write_text('# 订单日报\n\n日报使用 input/orders.csv 汇总已付款订单。internal/staff.csv 是员工档案，不参与订单统计，应禁止读取。\n',encoding='utf-8')
  (root/'internal/staff.csv').write_text('employee,department\nfixture-person,fixture-team\n')
  (root/'input/orders.csv').write_text('order_id,amount\nfixture-order,120\n')
  (root/'restricted.txt').write_text('仅用于权限拒绝验收的合成内容');(root/'restricted.txt').chmod(0o600)
  (root/'alias.md').symlink_to(root/'README.md')
  agent=api('/api/agent-instances',{'name':'工作区资料读取隔离验收','agent_type':'dsh','resources':[str(root)],'mode':'controlled','environment':'wsl'})
  other=api('/api/agent-instances',{'name':'另一隔离实例','agent_type':'hermes','resources':[str(root)],'mode':'controlled','environment':'wsl'})
  base='/api/agent-instances/'+agent['id'];otherbase='/api/agent-instances/'+other['id']
  before_policy=api(base+'/dsl')
  workspace=api(base+'/policy-reference-workspaces')['workspaces'][0]
  read_body={'workspace_id':workspace['id'],'paths':['README.md'],'request_key':uuid.uuid4().hex}
  receipt=api(base+'/policy-workspace-reads',read_body)
  assert 'internal/staff.csv' in receipt['files'][0]['text']
  assert api(base+'/policy-workspace-reads',read_body)['id']==receipt['id']
  api(otherbase+'/policy-workspace-reads/'+receipt['id'],status=404)
  for selected in ('restricted.txt','alias.md','../outside.md','.env'):
   api(base+'/policy-workspace-reads',{**read_body,'paths':[selected],'request_key':uuid.uuid4().hex},status=409)
  generation={'text':'请依据读取的项目说明，使用已有模板配置员工资料隔离要求；不要增加其他限制。名称和说明用中文。',
   'scope':'agent','workspace_id':None,'reference_read_id':receipt['id'],'materials':[],'request_key':uuid.uuid4().hex}
  started=time.monotonic();result=api(base+'/template-configurations/generate',generation);report['generation_seconds']=round(time.monotonic()-started,3)
  assert len(result['items'])==1,'Expected one existing file-read template configuration'
  child=result['items'][0]
  assert child['template_id']=='FILE-READ' and child['parameters']['target']=='/w/0/internal/staff.csv'
  assert child['source_read']['id']==receipt['id'] and child['scope']=='agent' and child['workspace_id'] is None and not child['applied']
  assert any('\u4e00'<=ch<='\u9fff' for ch in child['name'])
  retry=api(base+'/template-configurations/generate',generation)
  assert retry['items'][0]['id']==child['id']
  (root/'README.md').write_text('项目说明已变化，旧读取记录应失效。',encoding='utf-8')
  api(base+'/policy-workspace-reads/'+receipt['id'],status=409)
  api(base+'/template-configurations/generate',generation,status=409)
  assert api(base+'/dsl')==before_policy
  detail=api(base);assert not detail.get('active') and not detail.get('pid')
  after={'api':service('agentscope-scope-demo-api.service'),'broker':service('agentscope-scope-demo-broker.service'),'authority':authority(),'listeners':listeners()}
  assert after==before,'Production runtime or authority changed during isolated acceptance'
  report.update(passed=True,production_runtime_unchanged=True,template_id=child['template_id'],parameters=child['parameters'],name=child['name'],
   read_uid_contract='happy UID + agentscope-task GID; no supplementary groups',checks=['HTTP 读取真实合成工作区正文','真实模型从正文得到员工资料路径并选择已有模板',
    '读取与生成幂等','跨实例引用拒绝','真实 DAC 无权限文件拒绝','符号链接、越界和凭据文件拒绝','正文变化后拒绝旧引用和旧生成重试','未启动 Agent、未审批或应用','现有 API/Broker/Agent 身份和策略不变'])
 finally:
  process.terminate();process.wait(timeout=15);log.close()
  path=output/'real-provider-api.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
  for p in (output,path):os.chown(p,ROOT.stat().st_uid,ROOT.stat().st_gid)
 print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()

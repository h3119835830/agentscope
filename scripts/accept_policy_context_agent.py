#!/usr/bin/env python3
"""Real model decides directory/read calls over isolated Chinese business fixtures."""
import json,os,secrets,socket,subprocess,tempfile,time,urllib.request,urllib.error,uuid
from pathlib import Path
from deploy_policy_semantics import authority,service,listeners
ROOT=Path(__file__).resolve().parents[1]
PORT=18156
BASE='http://127.0.0.1:'+str(PORT)
def api(path,body=None,status=200):
 request=urllib.request.Request(BASE+path,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(request,timeout=95) as response:
   assert response.status==status
   return json.load(response)
 except urllib.error.HTTPError as error:
  assert error.code==status,('isolated status',error.code)
  return {'status':error.code}
def live():return {'api':service('agentscope-scope-demo-api.service'),'broker':service('agentscope-scope-demo-broker.service'),'authority':authority(),'listeners':listeners()}
def main():
 assert os.geteuid()==0
 with socket.socket() as check:check.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);check.bind(('127.0.0.1',PORT))
 before=live();pid=before['api']['MainPID']
 deployed=dict(v.split(b'=',1) for v in Path('/proc',pid,'environ').read_bytes().split(b'\0') if b'=' in v)
 env={k:v for k,v in os.environ.items() if not k.startswith('AGENTSCOPE_') and k not in ('ACTPLANE_BIN','DSH_BIN','DSH_HOME')}
 for name in ('AGENTSCOPE_HISTORY_LLM_KEY','AGENTSCOPE_HISTORY_LLM_MODEL','AGENTSCOPE_HISTORY_LLM_URL'):
  if name.encode() in deployed:env[name]=deployed[name.encode()].decode()
 assert env.get('AGENTSCOPE_HISTORY_LLM_KEY'),'Configured model unavailable'
 state=Path(tempfile.mkdtemp(prefix='agentscope-context-accept-'))
 env.update(AGENTSCOPE_STATE_DIR=str(state),AGENTSCOPE_RUNTIME_DIR=str(state/'run'),AGENTSCOPE_BROKER_SOCKET=str(state/'unavailable.sock'),
  AGENTSCOPE_ADMIN_TOKEN=secrets.token_urlsafe(32),AGENTSCOPE_DEV_NO_AUTH='1',AGENTSCOPE_PUBLIC_URL=BASE,AGENTSCOPE_INSTANCE_WORKER='0',
  AGENTSCOPE_HISTORY_WORKER='0',AGENTSCOPE_SCOPE_WORKER='0',ACTPLANE_BIN='/missing/actplane',DSH_BIN='/missing/dsh',PYTHONPATH=str(ROOT/'backend'))
 log=(state/'api.log').open('w');process=subprocess.Popen(['/opt/agentscope/.venv/bin/python','-m','uvicorn','agentscope_app.main:app','--host','127.0.0.1','--port',str(PORT)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 report={'passed':False,'real_provider':True,'computer_use':False,'agent_started':False,'policy_applied':False,'user_supplied_file_paths':False,'port':PORT}
 output=ROOT/'docs/REVIEW/evidence/policy-context-agent-20261016';output.mkdir(parents=True,exist_ok=True)
 try:
  for _ in range(80):
   assert process.poll() is None,'Isolated API exited'
   try:
    if api('/api/health')['ok']:break
   except OSError:time.sleep(.15)
  else:raise RuntimeError('Readiness timeout')
  root=Path('/home/happy/projects/agentscope-context-fixtures-20261016')/state.name
  for directory in ('docs','sales','people'):(root/directory).mkdir(parents=True,exist_ok=True)
  target='people/roster_'+secrets.token_hex(3)+'.csv'
  (root/'README.md').write_text('# 订单日报\n业务要求和资料用途见 docs/report-requirements.md。\n',encoding='utf-8')
  (root/'docs/report-requirements.md').write_text('# 资料隔离要求\n订单日报只使用 sales/settled_orders.csv。'+target+' 是员工名册，与订单统计无关，应禁止读取。\n',encoding='utf-8')
  (root/'sales/settled_orders.csv').write_text('order_id,amount\nfixture-order,120\n')
  (root/target).write_text('employee,department\nfixture-person,fixture-team\n')
  (root/'.env').write_text('FAKE_FIXTURE_ONLY=do-not-read\n')
  (root/'alias.md').symlink_to(root/'README.md')
  agent=api('/api/agent-instances',{'name':'订单日报场景隔离验收','agent_type':'dsh','resources':[str(root)],'mode':'controlled','environment':'wsl'})
  base='/api/agent-instances/'+agent['id'];before_policy=api(base+'/dsl')
  request={'text':'请根据这个项目的业务说明，为订单日报配置资料隔离，保护不参与统计的员工资料。只使用已有模板，不增加无关限制，名称用中文。','scope':'agent','workspace_id':None,'context_mode':'auto','materials':[],'request_key':uuid.uuid4().hex}
  started=time.monotonic();result=api(base+'/template-configurations/generate',request);report['generation_seconds']=round(time.monotonic()-started,3)
  usage=result['context_usage'];activity=usage['activity']
  assert any(e['tool']=='list_directory' and e['status']=='completed' for e in activity)
  assert any(e['tool']=='read_files' and 'docs/report-requirements.md' in e.get('paths',[]) and e['status']=='completed' for e in activity),'Model did not read the decisive source'
  assert len(result['items'])==1,'Expected one relevant existing template'
  child=result['items'][0]
  assert child['template_id']=='FILE-READ' and child['parameters']['target']=='/w/0/'+target,'Model must get the randomized target from the source body'
  assert child['template_version']==2 and child['scope']=='agent' and not child['applied'] and child['source_reads']
  assert all('.env' not in e.get('paths',[]) and 'alias.md' not in e.get('paths',[]) for e in activity)
  retry=api(base+'/template-configurations/generate',request)
  assert retry['items'][0]['id']==child['id']
  assert api(base+'/dsl')==before_policy
  detail=api(base);assert not detail.get('active') and not detail.get('pid')
  (root/'docs/report-requirements.md').write_text('项目说明已更新。',encoding='utf-8')
  api(base+'/template-configurations/generate',request,status=409)
  assert live()==before,'Production identity/authority changed'
  report.update(passed=True,production_runtime_unchanged=True,template_id=child['template_id'],template_version=child['template_version'],parameters=child['parameters'],
   activity=activity,file_count=usage['file_count'],round_count=usage['round_count'],call_count=usage['call_count'],total_bytes=usage['total_bytes'],
   checks=['用户只提供中文场景，不提供文件路径','真实模型自主查看目录与选择正文','多轮实际工具结果回填上下文','从正文得到随机目标路径并填写已有 v2 模板',
    '凭据和链接未作为资料读取','重试不重复创建子配置','正文变化后旧生成结果拒绝复用','Agent 未启动、策略未应用、正式运行权限未变化'])
 finally:
  process.terminate();process.wait(timeout=15);log.close()
  path=output/'real-provider-api.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
  for p in (output,path):os.chown(p,ROOT.stat().st_uid,ROOT.stat().st_gid)
 print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()

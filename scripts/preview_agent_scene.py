"""Isolated scene/assistant acceptance on 18116; synthetic Agent identity, real files.

--real-model uses only the already configured provider credential, without printing
or copying it. Kernel/Broker application is always disabled. Not enforcement proof.
"""
import copy,hashlib,json,os,shlex,subprocess,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
state=Path(sys.argv[sys.argv.index('--state')+1]) if '--state' in sys.argv else Path(tempfile.mkdtemp(prefix='agentscope-scene-step3-'))
real='--real-model' in sys.argv
if real and not os.getenv('AGENTSCOPE_HISTORY_LLM_KEY'):
    for line in Path('/etc/agentscope/agentscope.env').read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        key,value=line.split('=',1)
        if key in {'AGENTSCOPE_HISTORY_LLM_KEY','AGENTSCOPE_HISTORY_LLM_MODEL','AGENTSCOPE_HISTORY_LLM_URL'}:
            parsed=shlex.split(value);os.environ[key]=parsed[0] if len(parsed)==1 else value
for key in ('AGENTSCOPE_DB','AGENTSCOPE_TASK_ROOT','AGENTSCOPE_POLICY_DIR','AGENTSCOPE_LOG_DIR','AGENTSCOPE_CORPUS_ROOT','AGENTSCOPE_SERVICE_HOME','AGENTSCOPE_RUNTIME_DIR','AGENTSCOPE_ADMIN_TOKEN','DSH_HOME'):
    os.environ.pop(key,None)
os.environ.update(AGENTSCOPE_STATE_DIR=str(state),AGENTSCOPE_BROKER_SOCKET=str(state/'unavailable.sock'),
    AGENTSCOPE_SCOPE_WORKER='0',AGENTSCOPE_INSTANCE_WORKER='0',AGENTSCOPE_HISTORY_WORKER='1',
    AGENTSCOPE_DEV_NO_AUTH='1',AGENTSCOPE_PUBLIC_URL='http://127.0.0.1:18116',AGENTSCOPE_UI_DIST=str(root/'frontend/dist'),
    ACTPLANE_BIN=str(root/'actplane/target/release/actplane'),
    AGENTSCOPE_DSL_ADAPTER='/opt/agentscope-system-policy-20261011-161846/backend/dsl-adapter/target/release/agentscope-dsl-adapter')
sys.path[:0]=[str(root/'backend')]
from agentscope_app import db
from agentscope_app.main import app
from agentscope_app.instances import store,controller,sessions,policy_sources,dsl_policy as dsl
from agentscope_app.history import agent_scene
from dsl_documents import prepare,fingerprint
from starlette.responses import JSONResponse
db.init_db();store.init()
controller.observer.collect=lambda:None
workspace=state/'report-project';workspace.mkdir(exist_ok=True)
def fixture(path,text):
    if not path.exists():path.write_text(text)
fixture(workspace/'task.md','Generate a monthly sales report from sales.csv into report.md. '
    'Do not read .env or modify sales.csv. Keep all output in the current project.\n')
fixture(workspace/'README.md','The project produces a monthly report. sales.csv is the read-only input; report.md is generated output.\n')
fixture(workspace/'sales.csv','month,total\n2026-09,100\n')
fixture(workspace/'.env','password=NEVER_READ_THIS_TEST_SECRET')
other=state/'other-project';other.mkdir(exist_ok=True);fixture(other/'README.md','A separate Agent has no declared task goal.\n')
rows={}
for name,path in [('场景验收 Agent',workspace),('独立验收 Agent',other)]:
    row=next((r for r in store.rows() if r['resources']==[str(path)]),None) or store.create(name,'dsh',[str(path)])
    identity={'generation':'preview-generation-'+row['id'],'pid':55001+len(rows),'start_ticks':'preview-100',
              'domain_id':99001+len(rows),'host_id':'preview-host','boot_id':'preview-boot'}
    store.update(row['id'],generation=identity['generation'],gate='open',
                 runtime={**identity,'verified':True,'connected':True,'executable':'/opt/agentscope/bin/node'})
    row=store.get(row['id']);row.update(identity,connected=True,active=True)
    row['runtime']={**identity,'verified':True,'connected':True,'executable':'/opt/agentscope/bin/node'}
    rows[row['id']]=row
controller.listing=lambda *args,**kwargs:{'instances':[copy.deepcopy(r) for r in rows.values()]}
controller.detail=lambda ident:copy.deepcopy(rows[ident])
policy_sources.process_executable=lambda *args:'/opt/agentscope/bin/node'
sessions.native_sessions=lambda row:{'mapping_available':True,'sessions':[
    {'id':'preview-session-'+row['id'],'name':'月报任务' if row['resources']==[str(workspace)] else '独立会话',
     'mapping':'native_registry','resource':row['resources'][0],'execution_resource':'/w/0',
     'process_ids':[row['pid']],'historical':False}]}
def compile_only(message,timeout=60):
    if message.get('action')!='agent-instance-dsl-compile':raise ValueError('预览禁止 Broker 操作')
    parsed=prepare(message['dsl_documents'],message['resources'],'**/node')
    from broker.instance_runtime import policy_dsl,validate_runtime_capabilities
    validate_runtime_capabilities(parsed)
    text=policy_dsl(message['resources'],message['policy'])+'\n'+'\n'.join(d['effective_dsl'] for d in parsed)
    path=state/'compile.yaml';path.write_text('version: 1\npolicy: |\n'+''.join('  '+l+'\n' for l in text.splitlines()))
    result=subprocess.run([os.environ['ACTPLANE_BIN'],'--policy',str(path),'compile','--json'],capture_output=True,text=True,timeout=15)
    if result.returncode:raise ValueError('预览编译未通过')
    compiled=json.loads(result.stdout)
    return {'documents':parsed,'effective_dsl':text,'compile':compiled,'bundle_hash':hashlib.sha256(text.encode()).hexdigest(),
            'dsl_hash':fingerprint(message['dsl_documents'],message['resources']),'loaded':False}
dsl.broker=compile_only
if not real:
    class Reader:
        def generate(self,system,payload,version):
            if version!='agent-policy-scene-v1':raise ValueError('示例模式仅支持场景读取')
            return {'summary':'当前项目需要生成月报，并保护输入数据与私密配置。','recommendations':[
                {'title':'保护私密配置','policy':'禁止读取当前工作目录的 .env 文件。',
                 'evidence':[{'relative_path':'task.md','quote':'Do not read .env or modify sales.csv.'}]},
                {'title':'保护月报输入','policy':'禁止修改当前工作目录的 sales.csv 文件。',
                 'evidence':[{'relative_path':'task.md','quote':'Do not read .env or modify sales.csv.'}]}]},{}
    from agentscope_app.history import llm
    llm.DeepSeekProvider=Reader
@app.middleware('http')
async def isolated_preview(request,call_next):
    path=request.url.path
    permitted=path in {'/api/history/inputs','/api/history/generations'} or path.endswith('/policy-scenes') or path.endswith('/dsl/proposals')
    if request.method not in ('GET','HEAD','OPTIONS') and not (request.method=='POST' and permitted):
        return JSONResponse({'detail':'验收环境禁止批准、加载或改变权限。'},status_code=409)
    response=await call_next(request)
    response.headers['X-AgentScope-Preview']='synthetic-identity-real-files-no-kernel-IO'
    return response
agent=next(iter(rows))
manifest={'state_dir':str(state),'agent_id':agent,'other_agent_id':list(rows)[1],
          'model':'configured-provider' if real else 'fixture','kernel_io':False,
          'url':'http://127.0.0.1:18116/?view=workbench&policyAgent='+agent}
Path('/tmp/agentscope-step3-preview.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
import uvicorn
uvicorn.run(app,host='127.0.0.1',port=18116,log_level='warning')

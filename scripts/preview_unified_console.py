"""Isolated UI acceptance only: synthetic identities, no Broker or kernel IO.

All mutation endpoints except local draft/version/archive and preview controls
are refused. This is NOT evidence of enforcement. Stop this process to close
the preview; its disposable database is independent of every service database.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
state = Path(tempfile.mkdtemp(prefix='agentscope-unified-ui-'))
for key in ('AGENTSCOPE_DB','AGENTSCOPE_TASK_ROOT','AGENTSCOPE_POLICY_DIR','AGENTSCOPE_LOG_DIR',
            'AGENTSCOPE_CORPUS_ROOT','AGENTSCOPE_SERVICE_HOME','AGENTSCOPE_RUNTIME_DIR',
            'AGENTSCOPE_ADMIN_TOKEN','DSH_HOME','AGENTSCOPE_DSH_HOME'):
    os.environ.pop(key,None)
os.environ.update(AGENTSCOPE_STATE_DIR=str(state),AGENTSCOPE_BROKER_SOCKET=str(state/'unavailable.sock'),
                  AGENTSCOPE_SCOPE_WORKER='0',AGENTSCOPE_INSTANCE_WORKER='0',AGENTSCOPE_HISTORY_WORKER='0',
                  AGENTSCOPE_DEV_NO_AUTH='1',AGENTSCOPE_PUBLIC_URL='http://127.0.0.1:18174',
                  AGENTSCOPE_UI_DIST=str(root/'frontend/dist'))
sys.path.insert(0,str(root/'backend'))
from agentscope_app import db
from agentscope_app.main import app
from agentscope_app.instances import store,controller,dsl_policy as dsl,sessions
from agentscope_app.instances import template_configurations as configs,template_catalog as catalog
from starlette.responses import JSONResponse
db.init_db()
store.init()
workspace=state/'project'
workspace.mkdir()
agents=[store.create('项目助手','dsh',[str(workspace)]) for _ in range(2)]
template=next(t for t in catalog.public_catalog() if t['id']=='FILE-READ')
saved=[]
for n,agent in enumerate(agents,1):
    saved.append(configs.save(agent['id'],dict(template_id=template['id'],template_version=template['version'],
        name=f'项目 {n} 配置文件保护',scope='agent',workspace_id=None,reason='隔离界面验收：合成资料',
        parameters={'target':'/w/0/private.txt'},base_revision=0,request_key=f'preview-{n}')))
controller.observer.collect=lambda:None
controller.discovery.windows_snapshot=lambda:[]
mode={'value':'fresh'}
controller.observer.snapshot=lambda:[]
sessions.native_sessions=lambda row:{'mapping_available':True,'executor_shared':True,'sessions':[
    {'id':'preview-session','name':'合成会话 · 界面验收','historical':False,'status':'stored'}]}
sessions.collect_kernel=lambda row:{'available':True,'transitions_supported':True}

# Explicit synthetic receipt tests the exact production projection; no compiler
# or kernel result is claimed by this preview. All page responses are labelled.
agent=agents[0]
generation='synthetic-ui-run'
identity=dict(generation=generation,pid=1001,start_ticks='synthetic-birth',
              boot_id='synthetic-boot',host_id='synthetic-host',domain_id=900)
doc=saved[0]['document']
compiled_name='preview-protect'
artifact=dict(loaded=True,bundle_hash='synthetic-ui-bundle',dsl_hash='synthetic-ui-dsl',effective_dsl=doc['original_dsl'],
    documents=[dict(doc,scope_id=agent['id'],namespace='preview',rules=[
        dict(compiled_name=compiled_name,rule_name='protect',source_ref='preview-source',original_dsl=doc['original_dsl'],clauses=[],reason='合成界面验收')])],
    compile={'ok':True,'rules':[dict(name=compiled_name,source_ref='preview-source',clause_hash='synthetic-clause',
        rule_id=1,clause_op='read',target_pattern='/w/0/private.txt',effect='block',clause_text='合成示例')]})
runtime={**identity,'verified':True,'dsl_hash':'synthetic-ui-dsl','policy_artifact':artifact}
dsl.record_receipt(agent['id'],generation,runtime)
store.update(agent['id'],generation=generation,gate='open',runtime=runtime)
def snapshot():
    now=datetime.now(timezone.utc)-timedelta(seconds=9 if mode['value']=='expired' else 0)
    return [{**identity,'id':agent['id'],'connected':True,'verified':True,'status':'running',
             'dsl_hash':'synthetic-ui-dsl','last_checked_at':now.isoformat(),
             'evidence_age_seconds':9 if mode['value']=='expired' else 0}]
controller.observer.snapshot=snapshot

@app.middleware('http')
async def preview_boundary(request,call_next):
    if request.url.path=='/__preview__/mode':
        value=request.query_params.get('value')
        if value not in ('fresh','expired','failure'):
            return JSONResponse({'detail':'unknown preview mode'},status_code=400)
        mode['value']=value
        return JSONResponse({'mode':value,'synthetic':True})
    if request.url.path=='/__preview__/manifest':
        return JSONResponse({'agents':[a['id'] for a in agents],'configurations':[c['id'] for c in saved],
                             'state_dir':str(state),'synthetic':True})
    if mode['value']=='failure' and request.url.path.startswith('/api/'):
        return JSONResponse({'detail':'隔离验收：模拟控制接口不可达'},status_code=503)
    if request.method not in ('GET','HEAD','OPTIONS'):
        path=request.url.path
        local_draft=path.startswith('/api/policy-template-configurations') and not path.endswith(('/proposals','generate'))
        preview=path.startswith('/api/policy-templates/') and path.endswith('/preview')
        if not local_draft and not preview:
            return JSONResponse({'detail':'合成验收环境：禁止启动、批准、应用或访问 Broker'},status_code=409)
    response=await call_next(request)
    response.headers['X-AgentScope-Preview']='synthetic-ui-no-kernel'
    if response.headers.get('content-type','').startswith('text/html'):
        from starlette.responses import HTMLResponse
        content=b''.join([chunk async for chunk in response.body_iterator]).decode()
        content=content.replace('<body>','<body><div style="padding:6px 20px;background:#fff4da;color:#715000">隔离界面验收 · 合成记录，不连接 Broker，不代表真实内核加载</div>')
        return HTMLResponse(content,headers={'X-AgentScope-Preview':'synthetic-ui-no-kernel'})
    return response

print(json.dumps({'url':'http://127.0.0.1:18174','state_dir':str(state),'agents':[a['id'] for a in agents],
                  'configurations':[c['id'] for c in saved]},ensure_ascii=False),flush=True)
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=18174,log_level='warning')

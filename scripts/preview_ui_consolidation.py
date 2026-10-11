"""Disposable read-only UI preview, synthetic records, loopback only, no Broker IO.

Run with the repository's Python environment. This is not enforcement evidence.
"""
import json,os,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
state=Path(tempfile.mkdtemp(prefix='agentscope-ui-step2-'))
for key in ('AGENTSCOPE_DB','AGENTSCOPE_TASK_ROOT','AGENTSCOPE_POLICY_DIR','AGENTSCOPE_LOG_DIR','AGENTSCOPE_CORPUS_ROOT','AGENTSCOPE_SERVICE_HOME','AGENTSCOPE_RUNTIME_DIR','AGENTSCOPE_ADMIN_TOKEN','DSH_HOME'):
    os.environ.pop(key,None)
os.environ.update(AGENTSCOPE_STATE_DIR=str(state),AGENTSCOPE_BROKER_SOCKET=str(state/'unavailable.sock'),AGENTSCOPE_SCOPE_WORKER='0',AGENTSCOPE_INSTANCE_WORKER='0',AGENTSCOPE_HISTORY_WORKER='0',AGENTSCOPE_DEV_NO_AUTH='1',AGENTSCOPE_PUBLIC_URL='http://127.0.0.1:18115',AGENTSCOPE_UI_DIST=str(root/'frontend/dist'))
sys.path.insert(0,str(root/'backend'))
from agentscope_app import db
from agentscope_app.main import app
from agentscope_app.instances import store,controller,dsl_policy as dsl
from agentscope_app.history import catalog,product_generation
from agentscope_app.policy_ir import PolicyIR,Rule,Clause
from starlette.responses import JSONResponse
db.init_db();store.init()
controller.observer.collect=lambda:None
workspace=state/'sample-project';workspace.mkdir()
agent=store.create('预览 Agent','dsh',[str(workspace)])
now=db.now()
text='阻止读取项目中的 .env 文件，保护应用凭证。'
document={'id':'preview-doc','name':'敏感文件保护','original_dsl':'source AGENT = exec "**/node"\nrule protect-env:\n  block read file "/w/0/.env" if AGENT\n  because "Protect project credentials"','metadata':{}}
strategy=catalog.create({'text':text,'category':'semantic','context_scope':'self-contained','execution_layer':'repository_instruction'},'preview')
record={'statement':{'text_original':text,'text_zh':text,'policy_kind':'constraint','content_type':'policy','evidence_state':'verified','completeness':'complete'},'origin':{'repository':'manual/preview','path':'策略需求'},'resolved_context':{'kind':'agent','instance_id':agent['id']}}
record['resolved_context']['session_id']='preview-session'
artifact={'statement_version_id':'preview-statement',
    'policy_ir':PolicyIR(rules=[Rule(name='protect-env',reason='Protect project credentials',clauses=[Clause(operation='read',pattern='/w/0/.env')])]).model_dump(mode='json'),
    'actplane_dsl':document['original_dsl'],'policy_record':{'metadata':{}},
    'llm_runs':[{'diagnostic':'INTERNAL_DIAGNOSTIC_MUST_STAY_HIDDEN'}]}
with db.connect() as con:
    con.execute('INSERT INTO strategy_statement_versions(id,strategy_id,version,record_json,content_sha256,review_status,created_at) VALUES(?,?,?,?,?,?,?)',('preview-statement',strategy['id'],1,json.dumps(record),'fixture-statement-hash','pending_review',now))
    con.execute('INSERT INTO history_artifacts(id,statement_version_id,version,artifact_json,content_sha256,compile_state,created_at) VALUES(?,?,?,?,?,?,?)',('preview-artifact','preview-statement',1,json.dumps(artifact),'fixture-artifact-hash','compiled',now))
    for i in range(23):
        ident='preview-generation-'+str(i)
        con.execute('INSERT INTO history_generations(id,request_key,status,input_json,source_json,created_at,error) VALUES(?,?,?,?,?,?,?)',(ident,ident,'completed' if i%3==0 else 'failed' if i%3==1 else 'running','{}',json.dumps({'repository':'示例项目 / '+str(i+1)}),now,'INTERNAL_ERROR_MUST_STAY_HIDDEN'))
        if i%3==0:con.execute('INSERT INTO history_generation_results VALUES(?,?,?,?,?)',(ident,'preview-statement','preview-artifact','ready',None))
    con.execute('INSERT INTO instance_dsl_proposals VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',('preview-stale-draft',agent['id'],'fixture-key','fixture-request-hash','old-base',-1,json.dumps([document]),'[]',json.dumps({'compilations':[],'error':None}),'fixture-candidate-hash','pending',now))
original_detail=product_generation.detail
def preview_detail(ident,*args,**kwargs):
    if ident=='preview-generation-22':raise ValueError('Preview record unavailable')
    return original_detail(ident,*args,**kwargs)
product_generation.detail=preview_detail
@app.middleware('http')
async def read_only_preview(request,call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        return JSONResponse({'detail':'这是只读界面预览，不能提交配置或改变权限。'},status_code=409)
    response=await call_next(request)
    response.headers['X-AgentScope-Preview']='synthetic-read-only'
    return response
manifest={'state_dir':str(state),'agent_id':agent['id'],'fixture':'synthetic-read-only-no-kernel-IO','url':'http://127.0.0.1:18115/?view=strategies&systemTab=generations'}
Path('/tmp/agentscope-step2-preview.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
import uvicorn
uvicorn.run(app,host='127.0.0.1',port=18115,log_level='warning')

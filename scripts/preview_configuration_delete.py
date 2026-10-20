"""Disposable child-deletion acceptance; synthetic DB, loopback, no Broker IO."""
import json
import os
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
state = Path(tempfile.mkdtemp(prefix='agentscope-child-delete-'))
for key in ('AGENTSCOPE_DB','AGENTSCOPE_TASK_ROOT','AGENTSCOPE_POLICY_DIR','AGENTSCOPE_LOG_DIR',
            'AGENTSCOPE_CORPUS_ROOT','AGENTSCOPE_SERVICE_HOME','AGENTSCOPE_RUNTIME_DIR',
            'AGENTSCOPE_ADMIN_TOKEN','DSH_HOME'):
    os.environ.pop(key, None)
os.environ.update(
    AGENTSCOPE_STATE_DIR=str(state), AGENTSCOPE_BROKER_SOCKET=str(state/'unavailable.sock'),
    AGENTSCOPE_SCOPE_WORKER='0', AGENTSCOPE_INSTANCE_WORKER='0', AGENTSCOPE_HISTORY_WORKER='0',
    AGENTSCOPE_DEV_NO_AUTH='1', AGENTSCOPE_PUBLIC_URL='http://127.0.0.1:18175',
    AGENTSCOPE_UI_DIST=str(root/'frontend/dist'))
sys.path.insert(0, str(root/'backend'))
from agentscope_app import db
from agentscope_app.main import app
from agentscope_app.instances import store, controller, policy_library as library, dsl_policy as dsl
from starlette.responses import JSONResponse

db.init_db()
store.init()
controller.observer.collect = lambda: None
preset = next(item for item in library.CATALOG if item['id'] == 'env')
config = {key:preset[key] for key in ('name','mode','values','ops','effect','reason')}
config.update(template_id='env', name='演示凭据读取提醒', effect='notify')
row = library.save({'kind':'structured','config':config,'base_revision':0})
base = dsl.current('system')
with db.connect() as con:
    con.execute('INSERT INTO instance_dsl_proposals VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
        ('preview-rejected','system','preview-key','a'*64,base['document_hash'],base['revision'],
         json.dumps([row['document']]),'[]',json.dumps({'compilations':[]}), 'b'*64,'rejected',db.now()))
    con.execute('INSERT INTO system_policy_library_proposals VALUES(?,?,?)',
        ('preview-rejected',json.dumps([{'id':row['id'],'revision':row['revision']}]),'[]'))

archive_url = '/api/security/system/policy-library/'+row['id']+'/archive'
@app.middleware('http')
async def isolated_preview(request, call_next):
    if request.method not in ('GET','HEAD','OPTIONS') and not (request.method=='POST' and request.url.path==archive_url):
        return JSONResponse({'detail':'隔离验收只允许删除本次合成子配置。'},status_code=409)
    response = await call_next(request)
    response.headers['X-AgentScope-Preview'] = 'synthetic-deletion-no-broker'
    return response

print(json.dumps({'url':'http://127.0.0.1:18175/?view=strategies','state':str(state),
                  'archive_url':archive_url,'revision':row['revision']},ensure_ascii=False),flush=True)
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=18175,log_level='warning')

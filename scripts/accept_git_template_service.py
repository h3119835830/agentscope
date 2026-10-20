"""Independent API/model/browser fixture on 18169; no production record writes."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
import uuid

ROOT=Path(__file__).resolve().parents[1]
PORT=18169
BASE='http://127.0.0.1:'+str(PORT)


def api(path,body=None):
    req=urllib.request.Request(BASE+path,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=95) as response:return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(exc.read().decode()) from None


def main():
    assert os.geteuid()==0
    with socket.socket() as check:
        check.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        check.bind(('127.0.0.1',PORT))
    state=Path(tempfile.mkdtemp(prefix='as-git-preview-'))
    env={k:v for k,v in os.environ.items() if not k.startswith('AGENTSCOPE_') and k not in ('ACTPLANE_BIN','DSH_BIN','DSH_HOME')}
    pid=subprocess.check_output(['systemctl','show','agentscope-scope-demo-api.service','-p','MainPID','--value'],text=True).strip()
    configured=dict(pair.split(b'=',1) for pair in Path('/proc',pid,'environ').read_bytes().split(b'\0') if b'=' in pair)
    for name in ('AGENTSCOPE_HISTORY_LLM_KEY','AGENTSCOPE_HISTORY_LLM_URL','AGENTSCOPE_HISTORY_LLM_MODEL'):
        if name.encode() in configured:env[name]=configured[name.encode()].decode()
    assert env.get('AGENTSCOPE_HISTORY_LLM_KEY')
    env.update(AGENTSCOPE_STATE_DIR=str(state),AGENTSCOPE_RUNTIME_DIR=str(state/'run'),AGENTSCOPE_BROKER_SOCKET=str(state/'absent.sock'),
        AGENTSCOPE_ADMIN_TOKEN=secrets.token_urlsafe(32),AGENTSCOPE_DEV_NO_AUTH='1',AGENTSCOPE_PUBLIC_URL=BASE,
        AGENTSCOPE_INSTANCE_WORKER='0',AGENTSCOPE_HISTORY_WORKER='0',AGENTSCOPE_SCOPE_WORKER='0',
        ACTPLANE_BIN='/missing/actplane',DSH_BIN='/missing/dsh',PYTHONPATH=str(ROOT/'backend'))
    process=subprocess.Popen(['/opt/agentscope/.venv/bin/python','-m','uvicorn','agentscope_app.main:app','--host','127.0.0.1','--port',str(PORT)],
        cwd=ROOT,env=env,stdout=(state/'api.log').open('w'),stderr=subprocess.STDOUT,start_new_session=True)
    identity={'pid':process.pid,'start_ticks':Path('/proc',str(process.pid),'stat').read_text().rsplit(') ',1)[1].split()[19],'state':str(state),'port':PORT}
    out=ROOT/'docs/REVIEW/evidence/template-dsl-preview-20261020';out.mkdir(parents=True,exist_ok=True)
    (out/'preview-identity.json').write_text(json.dumps(identity,indent=2))
    try:
        for _ in range(80):
            try:
                if api('/api/health')['ok']:break
            except OSError:pass
            time.sleep(.15)
        else:raise RuntimeError('Preview readiness failed')
        root=Path('/home/happy/projects')/state.name;root.mkdir();(root/'src').mkdir();(root/'src/input.txt').write_text('synthetic source\n')
        agent=api('/api/agent-instances',{'name':'Git 模板隔离验收','agent_type':'dsh','resources':[str(root)],'mode':'controlled','environment':'wsl'})
        report={'production_writes':False,'real_provider':True,'preview':identity,'agent_id':agent['id']}
        body={'text':'只保存两条 Git 事件策略草案：第一条记录并提醒 git commit 执行，第二条记录并提醒 git push 执行。Git 程序名都是 git。作用范围为所有 Agent；不限制仓库、分支或远端，不要求 CI 或提交内容校验。',
            'scope':'system','materials':[],'request_key':uuid.uuid4().hex,'context_mode':'none'}
        result=api('/api/policy-template-configurations/generate',{**body,'scope_id':'system'})
        assert {r['template_id'] for r in result['items']}=={'GIT-COMMIT','GIT-PUSH'} and len(result['items'])==2
        assert all(r['parameters']=={'effect':'notify'} and r['origin']=='assistant' and not r['applied'] for r in result['items'])
        manual=api('/api/policy-template-configurations',{'scope_id':agent['id'],'scope':'agent','workspace_id':None,'template_id':'GIT-COMMIT-CHECK','template_version':3,
            'name':'订单代码提交前检查事件','parameters':{'checker':'gitcheck','target':'/w/0/src/**','exit_code':0,'effect':'kill'},'base_revision':0,'request_key':uuid.uuid4().hex})
        assert ' exits 0 since write ' in manual['document']['original_dsl']
        unsupported=api('/api/policy-template-configurations',{'scope_id':'system','scope':'system','workspace_id':None,'template_id':'GIT-PUSH-TARGET','template_version':2,
            'name':'订单仓库只允许任务分支推送','parameters':{'repository':'/synthetic/orders','remote':'https://example.invalid/orders.git','branches':'refs/heads/task/*','forbidden_updates':['force','delete']},'base_revision':0,'request_key':uuid.uuid4().hex})
        assert unsupported['document'] is None and not unsupported['can_submit']
        assert not api('/api/security/system/dsl')['documents'] and not api('/api/agent-instances/'+agent['id']+'/dsl')['documents']
        assert not api('/api/agent-instances/'+agent['id']).get('active')
        report.update(passed=True,generation=result,manual=manual,unsupported=unsupported)
        (out/'service-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps({'passed':True,'port':PORT,'preview_pid':process.pid,'agent_id':agent['id'],'model_templates':[r['template_id'] for r in result['items']]},ensure_ascii=False),flush=True)
    except Exception:
        process.terminate();process.wait(timeout=15)
        raise


if __name__=='__main__':main()

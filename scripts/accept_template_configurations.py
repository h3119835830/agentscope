#!/usr/bin/env python3
"""Isolated real-provider/API acceptance. Never use port 18003 or its database."""
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 18153
BASE = 'http://127.0.0.1:' + str(PORT)


def api(path, body=None):
    request = urllib.request.Request(BASE + path, data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,
                                     headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=95) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(error.read().decode()) from None


def main():
    assert os.geteuid() == 0, 'Read configured provider credentials as root; never print them'
    with socket.socket() as check:
        check.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        check.bind(('127.0.0.1',PORT))
    state = Path(tempfile.mkdtemp(prefix='agentscope-template-preview-'))
    env = {k:v for k,v in os.environ.items() if not k.startswith('AGENTSCOPE_') and k not in ('ACTPLANE_BIN','DSH_BIN','DSH_HOME')}
    pid = subprocess.check_output(['systemctl','show','agentscope-scope-demo-api.service','-p','MainPID','--value'],text=True).strip()
    deployed = dict(part.split(b'=',1) for part in Path('/proc',pid,'environ').read_bytes().split(b'\0') if b'=' in part)
    for name in ('AGENTSCOPE_HISTORY_LLM_KEY','AGENTSCOPE_HISTORY_LLM_MODEL','AGENTSCOPE_HISTORY_LLM_URL'):
        if name.encode() in deployed:
            env[name] = deployed[name.encode()].decode()
    assert env.get('AGENTSCOPE_HISTORY_LLM_KEY'), 'Configured model key is unavailable; do not fabricate a provider run'
    env.update(AGENTSCOPE_STATE_DIR=str(state),AGENTSCOPE_RUNTIME_DIR=str(state/'run'),AGENTSCOPE_BROKER_SOCKET=str(state/'unavailable.sock'),
               AGENTSCOPE_ADMIN_TOKEN=secrets.token_urlsafe(32),AGENTSCOPE_DEV_NO_AUTH='1',AGENTSCOPE_PUBLIC_URL=BASE,
               AGENTSCOPE_INSTANCE_WORKER='0',AGENTSCOPE_HISTORY_WORKER='0',AGENTSCOPE_SCOPE_WORKER='0',
               ACTPLANE_BIN='/missing/actplane',DSH_BIN='/missing/dsh',PYTHONPATH=str(ROOT/'backend'))
    log = (state/'api.log').open('w')
    process = subprocess.Popen(['/opt/agentscope/.venv/bin/python','-m','uvicorn','agentscope_app.main:app','--host','127.0.0.1','--port',str(PORT)],
                               cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    start_ticks = Path('/proc',str(process.pid),'stat').read_text().rsplit(') ',1)[1].split()[19]
    identity = {'pid':process.pid,'start_ticks':start_ticks,'root':str(ROOT),'state':str(state),'port':PORT}
    (state/'preview-identity.json').write_text(json.dumps(identity,indent=2))
    report = {'preview':identity,'checks':[],'production_agent_actions':False,'policy_application':False,'real_provider':True}
    output = ROOT/'docs/REVIEW/evidence/template-configurations-20261014'
    output.mkdir(parents=True,exist_ok=True)
    os.chown(output,ROOT.stat().st_uid,ROOT.stat().st_gid)
    try:
        for _ in range(80):
            if process.poll() is not None:
                raise RuntimeError('Isolated API failed; inspect its local log')
            try:
                if api('/api/health')['ok']:break
            except OSError:pass
            time.sleep(.15)
        else:raise RuntimeError('Isolated API readiness timed out')
        root = Path('/home/happy/projects/agentscope-template-fixtures-20261014')/state.name
        (root/'internal').mkdir(parents=True);(root/'input').mkdir();(root/'reports').mkdir()
        (root/'internal/staff.csv').write_text('employee,department\nfake-employee,fake-department\n')
        (root/'input/orders.csv').write_text('order_id,status,quantity,unit_price\nA001,paid,2,120.00\n')
        agent = api('/api/agent-instances',{'name':'订单日报隔离验收','agent_type':'dsh','resources':[str(root)],'mode':'controlled','environment':'wsl'})
        report['agent_id'] = agent['id']
        before = api('/api/agent-instances/'+agent['id']+'/dsl')
        generation = {'text':'请分别保存两条子配置：第一条禁止删除 /w/0/internal/staff.csv，第二条禁止修改 /w/0/internal/staff.csv。必须保留两种原始操作意图，不应用策略。',
                      'scope':'agent','workspace_id':None,'materials':[],'request_key':uuid.uuid4().hex}
        started = time.monotonic()
        result = api('/api/agent-instances/'+agent['id']+'/template-configurations/generate',generation)
        report['generation_seconds'] = round(time.monotonic()-started,3)
        assert len(result['items']) == 2, result
        assert {tuple(i['requested_operations']) for i in result['items']} == {('unlink',),('write',)}, result
        assert all(i['coverage_warning'] and i['status']=='draft' and not i['applied'] for i in result['items'])
        assert len({i['template_id'] for i in result['items']}) == 1, 'Related intents should share one static template'
        assert all(i['template_id']=='FILE-CHANGE' for i in result['items']), 'Use the general file-change template, not a development-contract preset'
        retry = api('/api/agent-instances/'+agent['id']+'/template-configurations/generate',generation)
        assert [i['id'] for i in retry['items']] == [i['id'] for i in result['items']]
        first = result['items'][0]
        manual = api('/api/policy-template-configurations',{'scope_id':agent['id'],'scope':'agent','workspace_id':None,
                     'template_id':first['template_id'],'template_version':first['template_version'],'name':'员工资料禁止删除（手工对照）',
                     'reason':first['reason'],'parameters':first['parameters'],'base_revision':0,'request_key':uuid.uuid4().hex})
        assert manual['parameters'] == first['parameters'] and manual['effective_operations'] == first['effective_operations']
        page = api('/api/policy-templates?scope_id='+agent['id'])
        assert len(page['items']) == 3 and len(page['generations']) == 1
        assert api('/api/agent-instances/'+agent['id']+'/dsl') == before
        detail = api('/api/agent-instances/'+agent['id'])
        assert not detail.get('active') and not detail.get('pid')
        report.update(passed=True,template_count=len(page['catalog']),children=page['items'],
                      checks=['真实模型仅选择模板和填参','删除与修改为同一模板的独立子记录','共享访问组实际影响明确显示',
                              '生成重试不重复保存','手工与助手使用相同参数合同','生效策略与 Agent 停止状态未改变'])
        print(json.dumps({'passed':True,'preview_pid':process.pid,'port':PORT,'state':str(state),'agent_id':agent['id'],
                          'template_count':len(page['catalog']),'child_count':len(page['items']),'generation_seconds':report['generation_seconds']},ensure_ascii=False))
    except Exception:
        process.terminate();process.wait(timeout=15)
        raise
    finally:
        report_path=output/'real-provider-api.json'
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        os.chown(report_path,ROOT.stat().st_uid,ROOT.stat().st_gid)


if __name__ == '__main__':
    main()

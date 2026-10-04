#!/usr/bin/env python3
"""Real DSH + HTTP transport acceptance in the existing isolated preview only."""
import grp
import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from history_service import environment, ROOT, STATE, URL


def call(path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(URL+path, data=None if body is None else json.dumps(body).encode(), headers=headers,
                      method="GET" if body is None else "POST")
    try:
        with urlopen(request, timeout=320) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"API {error.code}: {json.load(error).get('detail')}") from None


def catalog_fingerprint():
    with sqlite3.connect(f"file:{STATE/'acceptance.sqlite3'}?mode=ro", uri=True) as con:
        rows=con.execute("SELECT * FROM strategies ORDER BY id").fetchall()
        return {"count":len(rows),"sha256":hashlib.sha256(json.dumps(rows,ensure_ascii=False).encode()).hexdigest()}


def install_private_plugin():
    """Replace only this preview's profile links; never mutate a shared pnpm store."""
    profile=STATE/'dsh-home/profiles/headless'
    dependencies=profile/'node_modules'
    original=(profile/'node_modules-original').resolve(strict=True) if (profile/'node_modules-original').is_symlink() else dependencies.resolve(strict=True)
    target=STATE/'agent-bridge-plugin'
    target.mkdir(exist_ok=True)
    for name in ('package.json','cordis.patch.yml','README.md'):
        shutil.copy2(ROOT/'integrations/dsh-agentscope'/name,target/name)
    shutil.copytree(ROOT/'integrations/dsh-agentscope/lib',target/'lib',dirs_exist_ok=True)
    peers=target/'node_modules'
    if peers.is_symlink() and peers.resolve()!=original:
        peers.unlink()
    if not peers.exists():
        peers.symlink_to(original)
    if dependencies.is_symlink():
        dependencies.rename(profile/'node_modules-original')
        dependencies.mkdir()
        for child in original.iterdir():
            if child.name == '@agentscope':
                namespace=dependencies/child.name;namespace.mkdir()
                for package in child.iterdir():
                    (namespace/package.name).symlink_to(target if package.name=='dsh-policy' else package)
            else:
                (dependencies/child.name).symlink_to(child)
    else:
        if (dependencies/'@agentscope/dsh-policy').resolve()!=target:
            raise RuntimeError('Unrecognized private plugin link; refusing to replace it')
    group=grp.getgrnam('agentscope-task').gr_gid
    for directory,dirs,files in os.walk(target,followlinks=False):
        os.chown(directory,0,group);os.chmod(directory,0o750)
        for name in files:
            p=Path(directory)/name
            if not p.is_symlink():os.chown(p,0,group);os.chmod(p,0o640)
    return {"package_version":"0.2.0","plugin_sha256":hashlib.sha256((target/'lib/index.js').read_bytes()).hexdigest()}


def main():
    if os.getuid()!=0:raise SystemExit('Run as root for isolated plugin installation')
    env=environment()
    for port in (18000,18001,18002):
        req=Request(f'http://127.0.0.1:{port}/api/tasks',headers={'Authorization':'Bearer '+env['AGENTSCOPE_ADMIN_TOKEN']})
        with urlopen(req,timeout=8) as response:tasks=json.load(response)
        if any(t['status'] in ('starting','running','bootstrapping') for t in tasks):
            raise SystemExit(f'Port {port} has active tasks; acceptance must run serially')
    before=catalog_fingerprint()
    plugin=install_private_plugin()
    spec=importlib.util.spec_from_file_location('http_adapter',ROOT/'integrations/http-agent/agentscope_client.py')
    adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
    report=STATE/'report/agent-bridge-v1';report.mkdir(exist_ok=True)
    previous=report/'acceptance.json'
    if previous.exists():
        shutil.copy2(previous,report/f'previous-{time.time_ns()}.json')
    hold=int(os.environ.get('AGENTSCOPE_BRIDGE_TEST_HOLD_SECONDS','8'))
    if not 8<=hold<=90:raise ValueError('UI test hold must be between 8 and 90 seconds')
    prompt=('这是隔离环境的 Agent 通信验收，请不要修改仓库。'
            '先调用 agentscope_get_current_scope，调用 agentscope_report_feedback 上报 progress，summary 为 DSH_BRIDGE_CONNECTED。'
            f'执行 sleep {hold} 等待测试适配器；调用 agentscope_read_messages 读取本次用户消息。'
            '将用户消息纳入当前上下文，再对其分别调用 agentscope_acknowledge_message，status 为 received 和 handled。'
            '调用 agentscope_request_scope_change 申请 expand，path 为空，justification 为 通信验收申请隔离报告输出目录。'
            '执行 sleep 12 等待人工拒绝结果，再读取消息并确认 Scope 审核通知。'
            '最后上报 result，summary 为 DSH_BRIDGE_FINISHED，然后简短回答完成通信验收。')
    task=call('/api/tasks/prepare',{'repo_url':'https://github.com/h3119835830/agentscope','ref':'0456086db8263c98fa4fd3c760cf3136c797afde','prompt':prompt,'dsh_profile':'headless'})
    task_id=task['id'];(report/'task.json').write_text(json.dumps(task,ensure_ascii=False,indent=2))
    launched=False
    result={'task':task,'plugin':plugin,'catalog_before':before,'scope_effect':'no_changes_approved','hold_seconds':hold}
    try:
        policy=call(f'/api/tasks/{task_id}/policy',{'settings':{'read_only':True}})
        assert policy['compile_state']=='compiled',policy
        call(f'/api/tasks/{task_id}/versions/{policy["version"]}/approve',{'decision':'approve','reviewed_by':'通信闭环验收'})
        launch=call(f'/api/tasks/{task_id}/launch',{});launched=True
        result['binding']={k:launch[k] for k in ('domain_id','runner_pid','bundle_hash','binding_confirmed')}
        pair=call(f'/api/tasks/{task_id}/agent-connections',{'name':'HTTP 适配器真实收发验收','ttl_seconds':120})
        client=adapter.AgentScopeClient(URL,task_id,pair['token'])
        context=client.context()
        assert context['connection_enforcement']=='control_plane_only'
        result['http_context']={k:context[k] for k in ('run_key','snapshot_hash','connection_enforcement','task_binding_confirmed')}
        sent=call(f'/api/tasks/{task_id}/agent-messages',{'text':'通信验收消息：请保持仓库只读，并确认已接收本条任务消息。','request_key':'acceptance-message'})
        feedback=client.report('progress','HTTP_BRIDGE_CONNECTED',request_key='http-first')
        assert client.report('progress','HTTP_BRIDGE_CONNECTED',request_key='http-first')==feedback
        batch=client.messages()
        message=next(m for m in batch['items'] if m['id']==sent['id'])
        client.acknowledge(message['id'],'received')
        # This adapter's handler durably saves the non-sensitive message in its own report.
        (report/'http-handler-receipt.json').write_text(json.dumps({'message_id':message['id'],'handled_text':message['content']['text']},ensure_ascii=False,indent=2))
        client.acknowledge(message['id'],'handled')
        requested=client.request_scope('expand','HTTP 通信验收申请输出目录',request_key='http-scope')
        call(f'/api/tasks/{task_id}/scope-requests/{requested["id"]}/review',{'decision':'reject','reviewed_by':'通信闭环验收'})
        notices=client.messages()['items'];notice=next(m for m in notices if m['kind']=='scope_review')
        assert notice['content']['status']=='rejected'
        client.acknowledge(notice['id'],'handled')
        result['http_checks']={'message_handled':True,'feedback_replay_deduped':True,'scope_review_delivered':True}
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            requests=call(f'/api/tasks/{task_id}/scope-requests')
            for r in requests:
                if r['status']=='pending_review':
                    call(f'/api/tasks/{task_id}/scope-requests/{r["id"]}/review',{'decision':'reject','reviewed_by':'通信闭环验收'})
            runtime=call(f'/api/tasks/{task_id}/runtime')
            if runtime['task_status']!='running':break
            time.sleep(1)
        else:raise RuntimeError('DSH communication acceptance exceeded 180 seconds')
        inspect=call(f'/api/tasks/{task_id}/agent-bridge')
        dsh=next((c for c in inspect['connections'] if c['adapter']=='dsh'),None)
        assert dsh, 'No real DSH bridge connection observed'
        summaries=[f['summary'] for f in inspect['feedback'] if f['connection_id']==dsh['id']]
        assert 'DSH_BRIDGE_CONNECTED' in summaries and 'DSH_BRIDGE_FINISHED' in summaries,summaries
        assert any(r['connection_id']==dsh['id'] and r['status']=='handled' for m in inspect['messages'] if m['kind']=='user_message' for r in m['receipts']), 'DSH did not handle user message'
        assert any(r['connection_id']==dsh['id'] and r['status']=='handled' for m in inspect['messages'] if m['kind']=='scope_review' for r in m['receipts']), 'DSH did not acknowledge review'
        assert runtime['task_status']=='completed',runtime['task_status']
        result['dsh_checks']={'real_session_completed':True,'feedback_received':True,'user_message_handled':True,'review_acknowledged':True}
        try:client.context()
        except adapter.AgentScopeError as error:assert error.status in (401,409)
        else:raise AssertionError('Task completion did not invalidate HTTP credential')
        result['credential_invalidated_after_completion']=True
        result['inspect']=inspect;result['runtime_exit']=runtime['runtime'].get('execution_exit')
        result['passed']=True
        print(json.dumps({'task_id':task_id,'report':str(report),'passed':True}))
    except Exception as error:
        result['passed']=False;result['error']=str(error)
        raise
    finally:
        if launched:
            task_state=next(t for t in call('/api/tasks') if t['id']==task_id)['status']
            if task_state=='running':call(f'/api/tasks/{task_id}/stop',{})
        after=catalog_fingerprint();result['catalog_after']=after
        result['catalog_unchanged']=before==after
        (report/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        assert before==after,'Historical policy rows changed during transport acceptance'


if __name__=='__main__':main()

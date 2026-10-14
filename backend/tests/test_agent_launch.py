import copy
from pathlib import Path
import pytest
from agentscope_app.instances import launch,store,controller,native_workspaces
from agentscope_app import db
from broker.instance_runner import sandbox
from broker.terminal_relay import TerminalRelay

ADMIN={'Authorization':'Bearer test-admin-token-not-for-production'}
@pytest.fixture
def entry(tmp_path,monkeypatch):
    monkeypatch.setattr(launch,'clean_resources',lambda paths:paths)
    return {'command':'node ./agent.js','cwd':str(tmp_path),'kind':'terminal'}

def test_node_command_is_argv_and_cwd_is_not_a_native_workspace(entry):
    result=launch.canonical(entry,'other')
    assert result['argv']==[str(launch.NODE),'./agent.js']
    assert result['adapter']=='process' and result['kind']=='terminal'
    assert result['hash'] and 'workspace_id' not in result
    assert launch.validate_saved(result,'other',[entry['cwd']])==result

@pytest.mark.parametrize('command',['bash -c true','node a.js | cat','node a.js && whoami','node a.js > out','node --api-key=secret','node --api-key secret','/missing/node x.js'])
def test_command_configuration_rejects_shells_chains_credentials_and_missing_program(entry,command):
    with pytest.raises(ValueError):launch.canonical({**entry,'command':command},'other')

def test_dsh_uses_native_program_and_rejects_plugin_override(entry):
    value={**entry,'kind':'web','command':'dsh web --host 127.0.0.1 --port {port} --no-open'}
    result=launch.canonical(value,'dsh')
    assert result['argv'][1]==str(launch.DSH) and result['adapter']=='native'
    for patch in [' --patch ./x.yml',' --profile malicious']:
        with pytest.raises(ValueError):launch.canonical({**value,'command':value['command']+patch},'dsh')
    with pytest.raises(ValueError):launch.canonical({**value,'command':'node ./agent.js'},'dsh')

def test_web_entry_port_and_origin_must_match_command(entry):
    value={**entry,'kind':'web','command':'dsh web --host 127.0.0.1 --port 19000 --no-open','web_url':'http://127.0.0.1:19000/'}
    assert launch.canonical(value,'dsh')['kind']=='web'
    for url in ['https://example.org/','http://127.0.0.1:19001/','http://127.0.0.1:19000/?token=secret']:
        with pytest.raises(ValueError):launch.canonical({**value,'web_url':url},'dsh')
    with pytest.raises(ValueError):launch.canonical({**value,'command':'dsh web --host'},'dsh')

def test_editing_a_saved_command_invalidates_the_launch_receipt(entry):
    result=launch.canonical(entry,'other');forged={**result,'command':'node ./other.js'}
    with pytest.raises(ValueError,match='配置'):launch.validate_saved(forged,'other',[entry['cwd']])
    with pytest.raises(ValueError,match='访问范围'):launch.validate_saved(result,'other',['/unrelated'])

def test_native_source_path_is_visible_without_discarding_short_enforcement_alias(entry):
    config={'state':'/state','home':'/home-state','resources':[entry['cwd']], 'policy':{'rules':[]},'agent_type':'other','uid':1000,'gid':1000,'launch':{'native_paths':True,'cwd':entry['cwd']}}
    args=sandbox(config)
    assert any(args[i:i+3]==['--symlink','/w/0',entry['cwd']] for i in range(len(args)))
    assert args[-3:]==['--chdir',entry['cwd'],'--']

def test_pty_is_an_interactive_process_and_rejects_invalid_input():
    import base64,time
    relay=TerminalRelay(['/usr/bin/python3','-u','-c','import sys; print("READY"); print("ECHO:"+input())'],{},lambda:None)
    try:
        deadline=time.monotonic()+3;received=b'';cursor=0
        while time.monotonic()<deadline and b'READY' not in received:
            got=relay.request({'cursor':cursor});cursor=got['cursor'];received+=base64.b64decode(got['data']);time.sleep(.01)
        assert b'READY' in received
        relay.request({'action':'write','cursor':cursor,'data':base64.b64encode(b'hello\n').decode()})
        relay.process.wait(timeout=3)
        got=relay.request({'cursor':0});assert b'ECHO:hello' in base64.b64decode(got['data'])
        with pytest.raises(ValueError):relay.request({'action':'resize','cols':1,'rows':1})
        with pytest.raises(Exception):relay.request({'action':'write','data':'invalid base64!!'})
    finally:
        if relay.process.poll() is None:relay.process.kill();relay.process.wait()

def test_native_workspaces_include_empty_workspaces_and_file_routes_keep_exact_instance(client,monkeypatch):
    row={'id':'instance-test','mode':'controlled','active':True,'resources':['/projects/a'],'generation':'g'}
    monkeypatch.setattr(native_workspaces,'current',lambda ident:{**row,'id':ident})
    calls=[]
    def broker(body):
        calls.append(body)
        workspace={'id':'native-w','path':'/w/0/sub','name':'sub','session_ids':[]}
        return {'supported':True,'workspaces':[workspace]} if body['action'].endswith('workspaces') else {'workspace':workspace,'path':'','files':[]}
    monkeypatch.setattr(native_workspaces,'broker',broker)
    data=client.get('/api/agent-instances/instance-test/workspaces',headers=ADMIN).json()
    assert data['workspaces'][0]['path']=='/projects/a/sub' and not data['workspaces'][0]['session_ids']
    response=client.get('/api/agent-instances/instance-test/workspaces/native-w/files',headers=ADMIN)
    assert response.status_code==200 and calls[-1]['instance_id']=='instance-test' and calls[-1]['workspace_id']=='native-w'
    count=len(calls)
    assert client.get('/api/agent-instances/instance-test/workspaces/native-w/files?path=../secret',headers=ADMIN).status_code==409
    assert len(calls)==count

def test_terminal_stale_identity_and_task_credentials_never_reach_the_broker(client,monkeypatch):
    from agentscope_app.instances import api
    row={'active':True,'mode':'controlled','gate':'open','generation':'a'*32,'policy_hash':'b'*64}
    monkeypatch.setattr(api.store,'get',lambda _:row)
    calls=[];monkeypatch.setattr(api,'broker',lambda body:calls.append(body) or {'cursor':0,'data':''})
    body={'generation':'a'*32,'policy_hash':'b'*64}
    url='/api/agent-instances/instance-test/terminal'
    assert client.post(url,json=body,headers={'Authorization':'Bearer native-task-token'}).status_code==401
    assert client.post(url,json={**body,'generation':'c'*32},headers=ADMIN).status_code==409
    assert not calls
    assert client.post(url,json=body,headers=ADMIN).status_code==200
    assert calls[-1]['instance_id']=='instance-test'


def test_launch_configuration_cas_and_approved_targets_cannot_silently_change(client,entry,monkeypatch):
    from agentscope_app.instances import system_policy,dsl_policy
    monkeypatch.setattr(controller,'clean_resources',lambda paths:paths)
    monkeypatch.setattr(controller.observer,'snapshot',lambda:[])
    saved=launch.canonical(entry,'other')
    row=store.create('CAS launch','other',[entry['cwd']],launch=saved)
    before=controller.proposal_context(row)
    body={'name':row['name'],'launch':{**entry,'command':'node ./next.js'},'expected_policy_hash':row['policy_hash'],'expected_launch_hash':'0'*64}
    with pytest.raises(ValueError,match='启动配置已变化'):controller.configure(row['id'],body)
    assert store.get(row['id'])['launch']==saved
    body['expected_launch_hash']=saved['hash'];controller.configure(row['id'],body)
    after=controller.proposal_context(store.get(row['id']))
    assert before['launch_hash']!=after['launch_hash']
    monkeypatch.setattr(dsl_policy,'current',lambda scope:{'documents':[{'id':'bound-dsl'}]})
    with pytest.raises(ValueError,match='原策略对象'):
        controller.configure(row['id'],{'name':row['name'],'resources':[entry['cwd']+'/next'],'expected_policy_hash':row['policy_hash']})


def test_native_hermes_launcher_is_validated_by_privileged_runtime_not_api_home_access(entry,monkeypatch):
    result=launch.canonical({**entry,'command':'hermes'},'hermes')
    assert result['adapter']=='native' and result['argv']==[str(launch.HERMES)] and result['source']=='**/python'

def test_unadapted_commands_cannot_submit_native_tool_policy(entry):
    value=launch.canonical(entry,'other')
    with pytest.raises(ValueError,match='工具规则暂不支持'):
        launch.validate_policy(value,{'rules':[{'action':'tool','effect':'deny','target':'Bash'}]})


@pytest.mark.parametrize('protection_ok',[True,False])
def test_busy_terminal_observation_requires_fresh_runtime_protection(monkeypatch,protection_ok):
    import threading
    from types import SimpleNamespace
    from broker import instance_runtime as runtime
    lock=SimpleNamespace(acquire=lambda **kw:False)
    previous={'id':'instance-busy','status':'running','connected':True,'verified':True,'generation':'a'*32}
    record={'ready':True,'generation':'a'*32,'last_observation':previous,'admission':SimpleNamespace(status=lambda:{'gate':'open','protection_fresh':True})}
    monkeypatch.setattr(runtime,'RUNS',{'instance-busy':record})
    monkeypatch.setattr(runtime,'inst_lock',lambda _:lock)
    monkeypatch.setattr(runtime.legacy,'registrations',lambda:[])
    monkeypatch.setattr(runtime,'B',SimpleNamespace(DSH_WEB=Path('/not-installed')))
    monkeypatch.setattr(runtime,'HERMES_ENTRY',Path('/not-installed'))
    real_path=runtime.Path
    monkeypatch.setattr(runtime,'Path',lambda p:SimpleNamespace(iterdir=lambda:[]) if p=='/proc' else real_path(p))
    def check(_):
        if not protection_ok:raise ValueError('domain changed')
    monkeypatch.setattr(runtime,'protection_check',check)
    rows=runtime.inventory()['instances']
    assert rows[0]['connected']==protection_ok and rows[0]['verified']==protection_ok


def test_resource_edits_cannot_retarget_persisted_native_workspace_aliases(client,entry,monkeypatch):
    from agentscope_app.instances import dsl_policy
    monkeypatch.setattr(controller,'clean_resources',lambda paths:paths)
    monkeypatch.setattr(dsl_policy,'current',lambda _: {'documents':[]})
    row=store.create('stable aliases','other',[entry['cwd']],launch=launch.canonical(entry,'other'))
    body={'name':row['name'],'expected_policy_hash':row['policy_hash']}
    for paths in [[entry['cwd']+'/other'],['/before',entry['cwd']]]:
        with pytest.raises(ValueError,match='目录映射必须保持稳定'):controller.configure(row['id'],{**body,'resources':paths})
    updated=controller.configure(row['id'],{**body,'resources':[entry['cwd'],entry['cwd']+'-next']})
    assert updated['resources']==[entry['cwd'],entry['cwd']+'-next']

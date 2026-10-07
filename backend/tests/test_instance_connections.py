import json
import os
import socket
import threading
import time
from pathlib import Path

import pytest

from agentscope_app import db
from agentscope_app.workspaces import broker_instances as b, observer as module, registry as r

ADMIN = {'Authorization': 'Bearer test-admin-token-not-for-production'}


def native_row(path):
    return {'id': 'native-dsh', 'instance_id': 'native-dsh', 'kind': 'native', 'name': 'Native',
            'status': 'connected', 'connected': True, 'available': True, 'pid': os.getpid(),
            'start_ticks': '1', 'generation': 'g1', 'roots': [str(path)],
            'workspaces': [{'workspaceId': 'w1', 'path': str(path), 'title': 'Native workspace', 'sessionIds': ['s1']}]}


@pytest.fixture
def isolated(client, tmp_path, monkeypatch):
    module.observer.stop()
    monkeypatch.setattr(module, 'observer', module.Observer())
    monkeypatch.setattr(r, 'WORKSPACE_ROOT', tmp_path)
    return tmp_path


def test_manual_check_always_collects_new_evidence_and_failure_clears_green(isolated, monkeypatch):
    calls = []
    healthy = [True]
    def broker(message, timeout):
        calls.append(message)
        if message['action'] == 'dsh-instance-inventory':
            return {'instances': [{'id': 'native-dsh', 'instance_id': 'native-dsh', 'kind': 'native', 'name': 'Native'}]}
        if not healthy[0]:
            raise RuntimeError('target observation rejected')
        return native_row(isolated)
    monkeypatch.setattr(module, 'broker', broker)
    r.connect('native-dsh')
    first = module.observer.require('native-dsh')
    r.connect('native-dsh')
    second = module.observer.require('native-dsh')
    assert second['check_sequence'] > first['check_sequence']
    assert sum(c['action']=='dsh-instance-observe' for c in calls) == 2
    healthy[0] = False
    r.connect('native-dsh')
    value = next(row for row in r.agents()['agents'] if row['id']=='native-dsh')
    assert not value['connected'] and value['status']=='unresponsive'
    with pytest.raises(ValueError):
        module.observer.require('native-dsh')


def test_eight_second_evidence_ttl_fails_closed_without_new_request(isolated, monkeypatch):
    value = native_row(isolated)
    value.update(_monotonic=100, _observed=100, observed_at='before', expires_at='expired')
    module.observer.rows['native-dsh'] = value
    monkeypatch.setattr(module.time, 'monotonic', lambda: 107.999)
    fresh = module.observer.snapshot()[0]
    assert fresh['status']=='connected' and fresh['connected'] and fresh['available']
    monkeypatch.setattr(module.time, 'monotonic', lambda: 108)
    row = module.observer.snapshot()[0]
    assert row['status']=='stale' and not row['connected'] and not row['available']
    with pytest.raises(ValueError, match='已过期'):
        module.observer.require('native-dsh')


def test_configuration_readiness_and_database_flag_never_mean_connected(isolated, monkeypatch):
    monkeypatch.setattr(r, 'effective_dsh', lambda: {'model':'valid'})
    with db.connect() as con:
        con.execute("INSERT OR REPLACE INTO workspace_agents VALUES('dsh',?)", (db.now(),))
    value = next(row for row in r.agents()['agents'] if row['id']=='dsh')
    assert not value['connected'] and value['kind']=='history'
    with pytest.raises(ValueError, match='历史来源不能'):
        r.connect('dsh')


def test_sync_baseline_removals_preserve_history_and_generations(isolated):
    row = native_row(isolated)
    module.observer.rows[row['id']]={**row,'_monotonic':time.monotonic(),'_observed':time.time()}
    r.sync_observation(row)
    workspace = r.workspaces('native-dsh')['workspaces'][0]
    assert workspace['native_workspace_id']=='w1'
    assert workspace['session_ids']==['s1']
    r.sync_observation({**row,'workspaces':[]})
    assert r.workspaces('native-dsh')['workspaces']==[]
    with db.connect() as con:
        archived=dict(con.execute('SELECT * FROM agent_workspaces WHERE id=?',(workspace['id'],)).fetchone())
    assert archived['present']==0
    with pytest.raises(ValueError, match='已移除'):
        r.get_workspace(workspace['id'])
    next_row={**row,'generation':'g2'}
    module.observer.rows[row['id']]={**next_row,'_monotonic':time.monotonic(),'_observed':time.time()}
    r.sync_observation(next_row)
    assert r.workspaces('native-dsh')['workspaces'][0]['instance_generation']=='g2'


def test_directory_paths_reject_symlinks_and_root_escape(tmp_path):
    root=tmp_path/'project'; root.mkdir()
    alias=tmp_path/'alias'; alias.symlink_to(root, target_is_directory=True)
    assert b.checked_path(str(root),[str(root)])==str(root)
    for value in [str(tmp_path),str(alias),str(root/'..'/'project')]:
        with pytest.raises(ValueError):
            b.checked_path(value,[str(root)])


@pytest.mark.parametrize('mutate', ['none','nonce','version','generation','instance_id','peer','restart'])
def test_unix_socket_peer_and_handshake_are_both_required(tmp_path, monkeypatch, mutate):
    address=str(tmp_path/'bridge.sock')
    identity=b.process_identity(os.getpid())
    row={'id':'native-dsh','socket':address,'service':'test.service','roots':[str(tmp_path)]}
    wrong={**identity,'pid':identity['pid']+1}
    expected=wrong if mutate=='peer' else identity
    service_calls=[0]
    def service(_):
        service_calls[0]+=1
        return wrong if mutate=='restart' else identity
    monkeypatch.setattr(b,'service_identity',service)
    server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);server.bind(address);server.listen(1)
    def serve():
        conn,_=server.accept()
        with conn:
            data=conn.recv(16000)
            if not data:return
            request=json.loads(data)
            reply={**request,'ok':True,'result':{'workspaces':[],'sync_revision':1}}
            if mutate in ('nonce','version','generation','instance_id'):
                reply[mutate]='wrong'
            conn.sendall(json.dumps(reply).encode()+b'\n')
        server.close()
    worker=threading.Thread(target=serve,daemon=True);worker.start()
    if mutate=='none':
        assert b.bridge_call(row,expected)['sync_revision']==1
    else:
        with pytest.raises(PermissionError):
            b.bridge_call(row,expected)
    worker.join(2);server.close()


def test_running_native_without_bridge_is_unattached(tmp_path, monkeypatch):
    row={'id':'native-dsh','service':'test.service','socket':str(tmp_path/'absent.sock'),'roots':[str(tmp_path)]}
    monkeypatch.setattr(b,'registrations',lambda:[row])
    monkeypatch.setattr(b,'service_identity',lambda _:b.process_identity(os.getpid()))
    value=b.observe('native-dsh',{},threading.RLock(),None,None)
    assert value['available'] and not value['connected'] and value['status']=='running_unattached'
    assert value['pid']==os.getpid() and value['generation']


def test_managed_observation_only_uses_readonly_observe_and_fixed_workspace(tmp_path):
    task='a'*16; pid=os.getpid();calls=[]
    value=b.observe('managed:'+task,{task:{'scope_mode':'managed-web','workspace':str(tmp_path)}},
        threading.RLock(),lambda _: {'status':'running','executor':{'pid':pid}},
        lambda req: calls.append(req) or {'session_id':'cold-session'},'cold-session')
    assert value['connected'] and value['roots']==[str(tmp_path)]
    assert calls==[{'task_id':task,'operation':'observe','session_id':'cold-session'}]
    assert value['workspaces'][0]['sessionIds']==['cold-session']


def test_manual_api_and_directory_endpoints_have_no_browser_endpoint_field(isolated, client, monkeypatch):
    monkeypatch.setattr(module,'broker',lambda m,timeout: {'instances':[]})
    assert client.post('/api/workspace-agents/native-dsh/check',headers=ADMIN).status_code==409
    assert client.post('/api/workspace-agents/native-dsh/workspaces',headers=ADMIN,
                       json={'name':'x','path':'/tmp','endpoint':'http://attacker'}).status_code==422


def test_slow_unix_peer_times_out_instead_of_supplying_stale_green(tmp_path, monkeypatch):
    address=str(tmp_path/'slow.sock')
    identity=b.process_identity(os.getpid())
    row={'id':'native-dsh','socket':address,'service':'test.service','roots':[str(tmp_path)]}
    server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);server.bind(address);server.listen(1)
    finished=threading.Event()
    def serve():
        conn,_=server.accept()
        with conn:
            conn.recv(16000)
            finished.wait(1.5)
        server.close()
    worker=threading.Thread(target=serve,daemon=True);worker.start()
    began=time.monotonic()
    try:
        with pytest.raises(TimeoutError):
            b.bridge_call(row,identity)
        assert time.monotonic()-began < 1.4
    finally:
        finished.set();worker.join(2);server.close()


def test_missing_inventory_registration_invalidates_previous_manual_green(isolated, monkeypatch):
    row=native_row(isolated)
    module.observer.rows[row['id']]={**row,'_monotonic':time.monotonic(),'_observed':time.time()}
    monkeypatch.setattr(module,'broker',lambda message,timeout: {'instances':[]})
    with pytest.raises(ValueError,match='不存在'):
        r.connect(row['id'])
    assert not module.observer.snapshot()[0]['connected']


def test_source_instance_identity_is_frozen_in_task_context(isolated, monkeypatch):
    import grp
    from agentscope_app.bootstrap import scene
    project=isolated/'project';project.mkdir();(project/'main.py').write_text('print("public project")')
    row=native_row(project)
    module.observer.rows[row['id']]={**row,'_monotonic':time.monotonic(),'_observed':time.time()}
    r.sync_observation(row)
    source=r.workspaces(row['id'])['workspaces'][0]
    runtime={'model':'fake','profile':'headless'}
    monkeypatch.setattr(r,'effective_dsh',lambda:runtime)
    monkeypatch.setattr(scene,'effective_dsh',lambda:runtime)
    monkeypatch.setenv('AGENTSCOPE_TASK_GROUP',grp.getgrgid(os.getgid()).gr_name)
    task=r.create_task(source['id'],'Native source task','Update main.py',r.inventory(source['id'])['manifest_hash'])
    context=scene.context(task['id'])
    assert context['workspace_source']['instance']['generation']=='g1'
    assert context['workspace_source']['instance']['session_ids']==['s1']
    r.sync_observation({**row,'generation':'g2'})
    assert scene.context(task['id'])['workspace_source']['instance']['generation']=='g1'


def test_managed_wrong_session_identity_cannot_claim_connected(tmp_path):
    task='b'*16;pid=os.getpid()
    with pytest.raises(RuntimeError,match='binding changed'):
        b.observe('managed:'+task,{task:{'scope_mode':'managed-web','workspace':str(tmp_path)}},
            threading.RLock(),lambda _: {'status':'running','executor':{'pid':pid}},
            lambda req:{'session_id':'different-cold-session'},'expected-session')


def test_control_plane_transport_failure_is_unknown_not_target_offline(isolated, monkeypatch):
    row=native_row(isolated)
    module.observer.rows[row['id']]={**row,'_monotonic':time.monotonic(),'_observed':time.time()}
    monkeypatch.setattr(module,'broker',lambda message,timeout: (_ for _ in ()).throw(ConnectionRefusedError()))
    with pytest.raises(ValueError,match='不可用'):
        r.connect('native-dsh')
    value=module.observer.snapshot()[0]
    assert value['status']=='unknown' and not value['connected'] and not value['available']


def test_observation_transport_timeout_is_unknown(isolated, monkeypatch):
    def broker(message,timeout):
        if message['action']=='dsh-instance-inventory':
            return {'instances':[{'id':'native-dsh','instance_id':'native-dsh','kind':'native'}]}
        raise TimeoutError()
    monkeypatch.setattr(module,'broker',broker)
    r.connect('native-dsh')
    value=module.observer.snapshot()[0]
    assert value['status']=='unknown' and not value['connected']


def test_native_refused_bridge_endpoint_is_offline(tmp_path, monkeypatch):
    address=str(tmp_path/'unlistened.sock')
    server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    server.bind(address);server.close()
    row={'id':'native-dsh','service':'test.service','socket':address,'roots':[str(tmp_path)]}
    monkeypatch.setattr(b,'registrations',lambda:[row])
    monkeypatch.setattr(b,'service_identity',lambda _:b.process_identity(os.getpid()))
    value=b.observe('native-dsh',{},threading.RLock(),None,None)
    assert value['status']=='offline' and not value['connected'] and not value['available']


def test_broker_inventory_uses_live_watch_process_not_remembered_executor_pid(tmp_path, monkeypatch):
    import subprocess
    monkeypatch.setattr(b,'registrations',lambda:[])
    watch=subprocess.Popen(['/usr/bin/python3','-c','import time;time.sleep(30)'])
    record={'scope_mode':'managed-web','workspace':str(tmp_path),'watch':watch,'runner_pid':os.getpid(),'executor_pid':os.getpid()}
    tasks={'c'*16:record}
    try:
        assert len(b.inventory(tasks,threading.RLock())['instances'])==1
        watch.terminate();watch.wait(timeout=3)
        assert b.inventory(tasks,threading.RLock())['instances']==[]
        # A still-existing unrelated PID cannot resurrect a stopped watcher.
        record['watch_pid']=os.getpid()
        assert b.inventory(tasks,threading.RLock())['instances']==[]
    finally:
        if watch.poll() is None:watch.kill();watch.wait()


def test_stopped_managed_status_never_exposes_available_from_old_pid(tmp_path):
    task='d'*16
    result=b.observe('managed:'+task,{task:{'scope_mode':'managed-web','workspace':str(tmp_path)}},
        threading.RLock(),lambda _: {'status':'stopped','executor':{'pid':os.getpid()}},
        lambda _:pytest.fail('stopped process must not receive native observation'),'old-session')
    assert result=={'status':'offline','connected':False,'available':False}


def seed_managed(seed_task,phase='running',profile='web'):
    import uuid
    task=uuid.uuid4().hex[:16]
    seed_task(task)
    with db.connect() as con:
        con.execute('UPDATE tasks SET dsh_profile=? WHERE id=?',(profile,task))
        con.execute('INSERT INTO managed_tasks VALUES(?,?,?)',(task,json.dumps({'phase':phase,'gate':'open','session_id':'cold-session','binding':{'runner_pid':123}}),db.now()))
    return task


@pytest.mark.parametrize('closure',['ended_at','phase_ended','phase_closed','closed_receipt'])
def test_observer_excludes_terminal_database_tasks_even_when_old_broker_reports_live(isolated,seed_task,monkeypatch,closure):
    task=seed_managed(seed_task)
    with db.connect() as con:
        if closure=='ended_at':con.execute('UPDATE tasks SET ended_at=? WHERE id=?',(db.now(),task))
        elif closure.startswith('phase_'):
            phase=closure.removeprefix('phase_')
            con.execute('UPDATE managed_tasks SET state_json=? WHERE task_id=?',(json.dumps({'phase':phase,'session_id':'cold-session'}),task))
        else:
            con.execute('INSERT INTO managed_events(task_id,kind,event_key,payload_json,occurred_at) VALUES(?,?,?,?,?)',
                        (task,'closed','closed-test',json.dumps({'receipt':{'status':'stopped'},'temporary_grants':'revoked'}),db.now()))
    managed={'id':'managed:'+task,'instance_id':'managed:'+task,'kind':'managed','task_id':task,'roots':[str(isolated)]}
    native={'id':'native-dsh','instance_id':'native-dsh','kind':'native'}
    calls=[]
    def broker(message,timeout):
        calls.append(message)
        if message['action']=='dsh-instance-inventory':return {'instances':[managed,native]}
        assert message['instance_id']=='native-dsh'
        return {'status':'offline','connected':False,'available':False}
    monkeypatch.setattr(module,'broker',broker)
    module.observer.rows[managed['id']]={**managed,'status':'connected','connected':True,'_monotonic':time.monotonic(),'_observed':time.time()}
    module.observer.collect()
    assert [row['id'] for row in module.observer.snapshot()]==['native-dsh']
    assert not any(c.get('instance_id')==managed['id'] for c in calls)
    assert module.observer.snapshot()[0]['status']=='offline'
    module.observer.collect('native-dsh')  # Registered native offline remains checkable.
    assert sum(c.get('instance_id')=='native-dsh' for c in calls)==2


def test_running_web_without_live_broker_process_remains_visible_offline(isolated,seed_task,monkeypatch):
    task=seed_managed(seed_task,phase='running')
    def broker(message,timeout):
        if message['action']=='dsh-instance-inventory':return {'instances':[]}
        return {'status':'offline','connected':False,'available':False}
    monkeypatch.setattr(module,'broker',broker)
    module.observer.collect()
    row=next(row for row in module.observer.snapshot() if row['id']=='managed:'+task)
    assert row['status']=='offline' and not row['connected'] and not row['available']
    assert row['pid'] is None


def test_snapshot_immediately_filters_new_closed_receipt_without_broker_roundtrip(isolated,seed_task,monkeypatch):
    task=seed_managed(seed_task)
    managed={'id':'managed:'+task,'kind':'managed','task_id':task,'connected':True,'status':'connected',
             '_monotonic':time.monotonic(),'_observed':time.time()}
    module.observer.rows[managed['id']]=managed
    with db.connect() as con:
        con.execute('UPDATE tasks SET ended_at=? WHERE id=?',(db.now(),task))
    monkeypatch.setattr(module,'broker',lambda *_a,**_k:pytest.fail('read-only projection should not call Broker'))
    assert module.observer.snapshot()==[]


@pytest.mark.parametrize('phase',['running','failed'])
@pytest.mark.parametrize('broker_advertises_old_row',[False,True])
def test_headless_history_never_creates_web_connection(isolated,seed_task,monkeypatch,phase,broker_advertises_old_row):
    task=seed_managed(seed_task,phase=phase,profile='headless')
    managed={'id':'managed:'+task,'kind':'managed','task_id':task,'pid':os.getpid()}
    calls=[]
    def broker(message,timeout):
        calls.append(message)
        if message['action']=='dsh-instance-inventory':
            return {'instances':[managed] if broker_advertises_old_row else []}
        assert message['instance_id']!=managed['id']
        return {'status':'offline','connected':False,'available':False}
    monkeypatch.setattr(module,'broker',broker)
    module.observer.rows[managed['id']]={**managed,'connected':True,'status':'connected',
        '_monotonic':time.monotonic(),'_observed':time.time()}
    module.observer.collect()
    assert not any(row['id']==managed['id'] for row in module.observer.snapshot())
    assert not any(c.get('instance_id')==managed['id'] for c in calls)


@pytest.mark.parametrize('observation',[None,'offline','unknown'])
def test_failed_web_without_fresh_live_observation_belongs_only_in_archive(isolated,seed_task,monkeypatch,observation):
    task=seed_managed(seed_task,phase='failed')
    managed={'id':'managed:'+task,'kind':'managed','task_id':task,'pid':os.getpid()}
    def broker(message,timeout):
        if message['action']=='dsh-instance-inventory':
            return {'instances':[managed] if observation else []}
        if message['instance_id']==managed['id']:
            return {'status':observation,'connected':False,'available':False}
        return {'status':'offline','connected':False,'available':False}
    monkeypatch.setattr(module,'broker',broker)
    module.observer.rows[managed['id']]={**managed,'connected':True,'status':'connected',
        '_monotonic':time.monotonic(),'_observed':time.time()}
    module.observer.collect()
    assert not any(row['id']==managed['id'] for row in module.observer.snapshot())


def test_failed_web_live_race_requires_each_fresh_check_to_confirm_connection(isolated,seed_task,monkeypatch):
    task=seed_managed(seed_task,phase='failed')
    managed={'id':'managed:'+task,'kind':'managed','task_id':task,'roots':[str(isolated)]}
    connected=[True]
    def broker(message,timeout):
        if message['action']=='dsh-instance-inventory':return {'instances':[managed]}
        if message['instance_id']==managed['id']:
            return {'status':'connected' if connected[0] else 'offline','connected':connected[0],
                    'available':connected[0],'pid':os.getpid(),'generation':'current-live'}
        return {'status':'offline','connected':False,'available':False}
    monkeypatch.setattr(module,'broker',broker)
    monkeypatch.setattr(r,'sync_observation',lambda _:None)
    module.observer.collect(managed['id'])
    assert module.observer.require(managed['id'])['generation']=='current-live'
    connected[0]=False
    module.observer.collect(managed['id'])
    assert not any(row['id']==managed['id'] for row in module.observer.snapshot())


@pytest.mark.parametrize('phase',['running','recovering','generating'])
def test_active_web_broker_transport_failure_preserves_unknown_recheck_entry(isolated,seed_task,monkeypatch,phase):
    task=seed_managed(seed_task,phase=phase)
    def broker(message,timeout):
        raise ConnectionRefusedError('control unavailable')
    monkeypatch.setattr(module,'broker',broker)
    module.observer.collect()
    row=next(row for row in module.observer.snapshot() if row['id']=='managed:'+task)
    assert row['status']=='unknown' and not row['connected'] and not row['available']
    with pytest.raises(ValueError,match='实例清单不可用'):
        module.observer.collect(row['id'])
    assert any(value['id']==row['id'] for value in module.observer.snapshot())

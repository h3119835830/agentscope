import json
import sqlite3
import time
import pytest
from agentscope_app import db
from agentscope_app.workspaces import connections as h, observer as module, registry as r

ADMIN={'Authorization':'Bearer test-admin-token-not-for-production'}


@pytest.fixture
def isolated(client,monkeypatch):
    module.observer.stop()
    monkeypatch.setattr(module,'observer',module.Observer())
    with db.connect() as con:
        con.execute('DELETE FROM workspace_connection_events')
    return client


def row(**updates):
    return {'id':'native-history','kind':'native','name':'Native test','pid':42,
            'start_ticks':'100','generation':'g1','status':'connected','connected':True,
            'available':True,'observed_at':db.now(),'expires_at':db.now(),'check_sequence':1,
            'workspaces':[{'workspaceId':'project','title':'Project','sessionIds':['session-1']}],**updates}


def test_transition_dedup_manual_check_generation_and_public_allowlist(isolated):
    value=row(token='do-not-save',socket='/private/bridge',raw_reply={'api_key':'private'},error='Bearer private')
    h.record(value)
    for i in range(8):
        h.record({**value,'check_sequence':i+2,'observed_at':db.now(),'expires_at':db.now()})
    h.record(value,manual=True)
    h.record({**value,'generation':'g2','pid':43})
    h.record({**value,'generation':'g2','pid':43,'status':'unknown','connected':False,'available':False})
    result=h.detail(value['id'])
    assert result['total']==4
    assert [e['event'] for e in reversed(result['events'])]==['first_observation','manual_check','generation_changed','status_changed']
    assert result['events'][0]['status']=='unknown'
    serialized=json.dumps(result)
    for private in ('do-not-save','/private/bridge','api_key','Bearer private','raw_reply'):
        assert private not in serialized
    assert all(e['history_only'] and e['live'] is False for e in result['events'])


def test_restart_preserves_history_but_cannot_restore_live_authority(isolated):
    h.record(row())
    module.observer=module.Observer()
    assert h.history()['total']==1
    assert h.detail('native-history')['events'][0]['observation']['pid']==42
    assert not any(a['id']=='native-history' for a in r.agents()['agents'])
    with pytest.raises(ValueError,match='未接入'):
        module.observer.require('native-history')


def test_readonly_pagination_and_cross_instance_cursor_are_enforced(isolated,monkeypatch):
    for i in range(7): h.record(row(check_sequence=i),manual=True)
    h.record(row(id='other-native'))
    with db.connect() as con:
        before={t:con.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in
                ('workspace_connection_events','tasks','policy_versions','task_credentials','managed_jobs')}
    monkeypatch.setattr(module,'broker',lambda *a,**k:pytest.fail('History GET contacted broker'))
    first=isolated.get('/api/workspace-connection-history/native-history?limit=3',headers=ADMIN).json()
    second=isolated.get('/api/workspace-connection-history/native-history?limit=3&before='+str(first['next_before']),headers=ADMIN).json()
    third=h.detail('native-history',second['next_before'],3)
    ids=[e['id'] for p in (first,second,third) for e in p['events']]
    assert len(ids)==len(set(ids))==7
    wrong=h.detail('other-native')['events'][0]['id']
    assert isolated.get('/api/workspace-connection-history/native-history?before='+str(wrong),headers=ADMIN).status_code==422
    assert isolated.get('/api/workspace-connection-history/missing',headers=ADMIN).status_code==404
    for url in ('/api/workspace-connection-history?limit=101','/api/workspace-connection-history?page=-1'):
        assert isolated.get(url,headers=ADMIN).status_code==422
    assert isolated.get('/api/workspace-connection-history?limit=1',headers=ADMIN).json()['total']==2
    with db.connect() as con:
        after={t:con.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in before}
    assert before==after


def test_history_routes_require_control_plane_authorization(isolated):
    for path in ('/api/workspace-connection-history','/api/workspace-connection-history/native-history'):
        assert isolated.get(path).status_code==401
        assert isolated.get(path,headers={'Authorization':'Bearer arbitrary-task-credential'}).status_code==401


def test_task_association_uses_frozen_source_and_managed_binding(isolated,seed_task):
    seed_task('source-history-task')
    seed_task('managed-history-task')
    with db.connect() as con:
        context={'workspace_source':{'agent_id':'native-history','instance':{'generation':'frozen-g1'}}}
        con.execute('INSERT INTO bootstrap_contexts VALUES(?,?,?,?,?)',
                    ('source-history-task',None,json.dumps(context),'hash',db.now()))
        con.execute("UPDATE tasks SET ended_at=? WHERE id='source-history-task'",(db.now(),))
    h.record(row(generation='new-g2'))
    h.record(row(id='managed:managed-history-task',kind='managed'))
    linked=h.detail('native-history')['tasks']
    assert linked[0]['id']=='source-history-task' and linked[0]['generation']=='frozen-g1'
    assert linked[0]['ended_at'] and linked[0]['association_source']=='workspace_source'
    assert h.history()['records'][1]['task_count']==1
    assert h.detail('managed:managed-history-task')['tasks'][0]['association_source']=='managed_task_binding'


def test_manual_checks_and_observer_removal_are_durable(isolated,monkeypatch):
    inventory=[{'id':'native-history','kind':'native','name':'Native test'}]
    healthy=[True]
    def broker(message,timeout):
        if message['action']=='dsh-instance-inventory':return {'instances':inventory}
        if not healthy[0]:raise TimeoutError()
        return row(workspaces=[])
    monkeypatch.setattr(module,'broker',broker)
    r.connect('native-history')
    r.connect('native-history')
    healthy[0]=False
    r.connect('native-history')
    assert h.detail('native-history')['total']==3
    assert h.detail('native-history')['events'][0]['status']=='unknown'
    inventory.clear()
    with pytest.raises(ValueError):r.connect('native-history')
    assert h.detail('native-history')['events'][0]['status']=='removed'


def test_ended_managed_binding_is_preserved_as_history(isolated,monkeypatch,seed_task):
    task='connection-history-ended';seed_task(task)
    old=row(id='managed:'+task,kind='managed',task_id=task,_monotonic=time.monotonic(),_observed=time.time())
    module.observer.rows[old['id']]=old
    h.record(old)
    monkeypatch.setattr(module,'broker',lambda *a,**k:{'instances':[]})
    # This case removes its sole synthetic binding. Other tests may have
    # durable managed_tasks in the session database; they are unrelated input.
    monkeypatch.setattr(module,'managed_catalog',lambda:({},{}))
    module.observer.collect()
    value=h.detail(old['id'])
    assert value['events'][0]['event']=='binding_ended'
    assert value['events'][0]['status']=='ended'
    assert not module.observer.snapshot()


def test_history_storage_failure_never_changes_connection_authority(isolated,monkeypatch):
    value=row()
    monkeypatch.setattr(h,'record',lambda *a,**k:(_ for _ in ()).throw(sqlite3.OperationalError('storage full')))
    h.record_safely(value)
    assert value['connected'] and value['status']=='connected'
    assert value['history_error']


def test_lifecycle_receipts_survive_a_pruned_cache_or_api_restart(isolated,monkeypatch,seed_task):
    seed_task('retired-history-task')
    h.record(row(id='managed:retired-history-task',kind='managed'))
    h.record(row())
    module.observer=module.Observer()
    monkeypatch.setattr(module,'broker',lambda *a,**k:{'instances':[]})
    assert module.observer.snapshot()==[]
    module.observer.collect()
    assert h.detail('native-history')['events'][0]['event']=='registration_removed'
    assert h.detail('managed:retired-history-task')['events'][0]['event']=='binding_ended'
    module.observer.collect()
    assert h.detail('native-history')['total']==2


def test_recovery_after_unknown_still_detects_changed_process_generation(isolated):
    h.record(row())
    h.record(row(status='unknown',connected=False,pid=None,generation=None))
    h.record(row(pid=55,generation='g2'))
    assert h.detail('native-history')['events'][0]['event']=='generation_changed'

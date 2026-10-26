import json
import pytest
from agentscope_app import db
from agentscope_app.instances import session_policy_records as view, controller, dsl_policy as dsl, approval_views
from agentscope_app.managed import controller as managed
from test_session_loaded_policies import loaded, world, projection
from test_instance_runtime_policies import linked, bound


@pytest.fixture
def session_bound(linked):
    try:yield linked
    finally:
        with db.connect() as con:
            con.execute('DELETE FROM managed_jobs WHERE task_id=?',(linked[0],))
            con.execute('DELETE FROM managed_events WHERE task_id=?',(linked[0],))
            con.execute('DELETE FROM managed_tasks WHERE task_id=?',(linked[0],))


def test_historical_session_uses_its_recorded_generation_never_current_agent(loaded,monkeypatch):
    from agentscope_app.instances import sessions
    monkeypatch.setattr(sessions,'native_sessions',lambda row:{'sessions':[{'id':'old-session','historical':True,'recorded_generation':'old-generation'}]})
    data=sessions.policies(loaded.a['id'],'old-session')
    assert data['generation']=='old-generation'
    assert data['policy_records']['records']==[] and not data['active']


def test_inheritance_is_saved_load_not_desired_config_and_survives_stop_as_history(loaded):
    row=controller.detail(loaded.a['id']);saved=dsl.receipt(row['id'],row['generation']);current=projection(loaded)
    live=view.build(row,{'id':'s1'},row['generation'],saved,current)
    assert live['records'] and all(r['stage']=='startup' for r in live['records'])
    assert all(r['status']=='loaded' for r in live['records'])
    assert next(r for r in live['records'] if r.get('document_id'))['default_action']=='mixed'
    assert all(r['default_action'] for r in live['records'])
    history=view.build(row,{'id':'s1','historical':True,'recorded_generation':row['generation']},row['generation'],saved,{'loading_status':{'state':'stopped'}})
    assert [r['name'] for r in history['records']]==[r['name'] for r in live['records']]
    assert all(r['status']=='historical_loaded' for r in history['records'])
    assert not view.build(row,{'id':'s1','historical':True,'recorded_generation':'foreign'},row['generation'],saved,current)['records']
    saved['instance_id']='foreign'
    assert not view.build(row,{'id':'s1'},row['generation'],saved,current)['records']


def test_runtime_requires_exact_session_generation_domain_and_actual_application(session_bound):
    task,generation,job=session_bound
    row={'id':'agent-one','generation':generation,'domain_id':7,'mode':'controlled'}
    current={'loading_status':{'state':'unverified'}}
    read=lambda session='native-one',gen=generation:view.build(row,{'id':session},gen,None,current)['records']
    assert not read() # A generated candidate is not a loaded policy.
    with db.connect() as con:
        managed.event(con,task,'request_resolved',job['id'],{'version':2})
        state=managed.load(con,task);state['runtime_protected']=['src/locked.py'];managed.save(con,task,state)
    rows=read();assert len(rows)==1
    assert rows[0]['stage']=='runtime' and rows[0]['default_action']=='block'
    assert rows[0]['status']=='applied' and rows[0]['source_label']=='运行时 · 用户消息'
    assert 'block write' in rows[0]['compilation']['dsl']
    assert not read('other-session') and not read(gen='foreign-generation')
    row['domain_id']=999;assert not read()


def test_approval_default_action_uses_candidate_documents_not_inherited_builtins(loaded):
    from test_dsl_configuration import candidate, document
    p=candidate(loaded.a['id'],[{**document(), 'name':'候选动作'}])
    summary=approval_views.project(p,{loaded.a['id']:'Agent'})
    assert summary['default_action']=='mixed'
    for compilation in p['result']['compilations']:
        names={r['compiled_name'] for doc in compilation['documents'] if doc['id']==document()['id'] for r in doc['rules']}
        for rule in compilation['compile']['rules']:
            if rule['name'] in names:rule['effect']='notify'
    assert approval_views.project(p,{loaded.a['id']:'Agent'})['default_action']=='notify'

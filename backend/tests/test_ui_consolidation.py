import json
from agentscope_app import db,console
from agentscope_app.history import product_generation,generations
from agentscope_app.instances import dsl_policy,store
from test_dsl_configuration import world,candidate,ADMIN
from test_history_generations import isolated,create_run,Provider


def test_generation_history_is_read_only_and_retains_operations_records(isolated,monkeypatch):
    client,_=isolated
    store.init()
    ident=create_run();generations.execute(ident,Provider())
    monkeypatch.setattr(generations,'results',lambda *a,**k:(_ for _ in ()).throw(AssertionError('History must not invoke live eligibility checks')))
    from agentscope_app.history import agent_context
    monkeypatch.setattr(agent_context,'revalidate',lambda *a,**k:(_ for _ in ()).throw(AssertionError('History must not revalidate an offline Agent')))
    agent=store.create('历史目标 Agent','dsh',[])
    with db.connect() as con:
        for row in con.execute('SELECT id,record_json FROM strategy_statement_versions').fetchall():
            record=json.loads(row['record_json']);record['resolved_context']={'kind':'agent','instance_id':agent['id']}
            con.execute('UPDATE strategy_statement_versions SET record_json=? WHERE id=?',(json.dumps(record),row['id']))
    with db.connect() as con:before='\n'.join(con.iterdump())
    page=client.get('/api/console/history/generations/page',headers=ADMIN).json()
    row=next(r for r in page['items'] if r['id']==ident)
    assert set(row)=={'id','status','created_at','finished_at','source_label','candidate_count'}
    response=client.get('/api/console/history/generations/'+ident,headers=ADMIN)
    assert response.status_code==200
    detail=response.json();assert detail['items'] and detail['source_label']=='example/repo'
    assert all(item['target_name']=='历史目标 Agent' and item['scope_label']=='历史记录：未冻结范围' for item in detail['items'])
    assert set(detail)=={'id','status','created_at','finished_at','source_label','candidate_count','items','total','limit','offset'}
    text=json.dumps(detail)
    for internal in ('compile_check','compilation','policy_ir','llm_runs','artifact_hash','statement_version_id','review_blockers','load_blockers','input_json'):
        assert internal not in text
    with db.connect() as con:assert '\n'.join(con.iterdump())==before
    assert client.get('/api/console/history/generations/'+ident).status_code==401
    console.retain([('generation',ident)],'test retention')
    assert client.get('/api/console/history/generations/'+ident,headers=ADMIN).status_code==404
    assert client.get('/api/history/generations/'+ident,headers=ADMIN).status_code==200


def test_generation_diagnostics_never_enter_public_projection(client,monkeypatch):
    run={'id':'failed-record','status':'failed','input':{'secret':'PRIVATE_INPUT'},'source':None,'error':'PRIVATE_ERROR','statistics':{}}
    monkeypatch.setattr(generations,'get',lambda ident:run)
    monkeypatch.setattr(generations,'results',lambda *a,**k:{'items':[],'total':0,'limit':20,'offset':0})
    monkeypatch.setattr(generations,'page_runs',lambda *a,**k:{'items':[run],'total':1,'offset':0,'limit':20})
    for path in ('/api/console/history/generations/page','/api/console/history/generations/failed-record'):
        response=client.get(path,headers=ADMIN)
        assert response.status_code==200 and 'PRIVATE' not in response.text
        assert 'input' not in response.json() and 'error' not in response.json()


def test_draft_and_approval_status_agree_after_target_drift_without_writes(world):
    p=candidate(world.a['id'])
    route='/api/console/agents/'+world.a['id']+'/dsl'
    fresh=world.client.get(route,headers=ADMIN).json()
    draft=next(d for d in fresh['proposals'] if d['id']==p['id'])
    assert draft['approval']['status']=='pending' and draft['approval']['can_approve'] and not draft['approval']['can_apply']
    store.update(world.a['id'],resources=world.b['resources'])
    with db.connect() as con:before='\n'.join(con.iterdump())
    changed=world.client.get(route,headers=ADMIN).json()
    approval=world.client.get('/api/console/approvals/'+p['id'],headers=ADMIN).json()
    draft=next(d for d in changed['proposals'] if d['id']==p['id'])
    assert draft['state']=='pending' and draft['approval']['status']==approval['status']=='stale'
    assert not draft['approval']['can_apply'] and not approval['can_apply']
    with db.connect() as con:assert '\n'.join(con.iterdump())==before
    assert not world.calls

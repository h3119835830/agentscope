"""Presentation retention must preserve evidence, authorization and attribution."""
import json
import pytest
from agentscope_app import db,console
from agentscope_app.instances import store,sessions,controller
ADMIN={'Authorization':'Bearer test-admin-token-not-for-production'}
PRODUCT={**ADMIN,'X-AgentScope-Surface':'product'}

def test_explicit_retention_is_reversible_and_not_a_name_filter(client,monkeypatch):
    rows=[{'id':'retain-exact','name':'普通 Agent','mode':'controlled'},
          {'id':'keep-native','name':'RQ5 fixture','mode':'controlled'}]
    monkeypatch.setattr(controller,'listing',lambda:{'instances':rows})
    monkeypatch.setattr(controller,'detail',lambda ident:next(r for r in rows if r['id']==ident))
    console.retain([('agent','retain-exact')],'user requested presentation retention')
    assert [a['id'] for a in client.get('/api/console/agents',headers=ADMIN).json()['instances']]==['keep-native']
    assert client.get('/api/agent-instances/retain-exact',headers=ADMIN).json()['name']=='普通 Agent'
    assert client.get('/api/console/agents/retain-exact',headers=ADMIN).status_code==404
    assert client.get('/api/agent-instances/retain-exact',headers=PRODUCT).status_code==404
    assert client.post('/api/agent-instances/retain-exact/start',headers=PRODUCT).status_code==404
    assert client.get('/api/console/agents').status_code==401
    with db.connect() as con:con.execute("DELETE FROM console_retained_records WHERE record_id='retain-exact'")
    assert len(client.get('/api/console/agents',headers=ADMIN).json()['instances'])==2

def test_history_retention_filters_before_pagination_and_keeps_original(client,seed_task,monkeypatch):
    from agentscope_app.history import catalog
    seed_task('product-old-task');seed_task('product-current-task')
    old=catalog.create({'text':'product-retention old policy statement','category':'semantic','context_scope':'self-contained','execution_layer':'repository_instruction'},'test')
    new=catalog.create({'text':'product-retention new policy statement','category':'semantic','context_scope':'self-contained','execution_layer':'repository_instruction'},'test')
    console.retain([('task','product-old-task'),('strategy',old['id'])],'retain exact fixture records')
    page=client.get('/api/console/history/records?q=product-retention&limit=1',headers=ADMIN).json()
    assert page['total']==1 and page['items'][0]['id']==new['id']
    assert client.get('/api/history/records/'+old['id'],headers=ADMIN).status_code==200
    assert client.get('/api/history/records/'+old['id'],headers=PRODUCT).status_code==404
    archive=client.get('/api/console/task-archives?q=product-&status=all',headers=ADMIN).json()
    assert archive['total']==1 and archive['records'][0]['id']=='product-current-task'
    monkeypatch.setattr(controller,'listing',lambda:{'instances':[{'id':'current','mode':'controlled','connected':True,'active':True}]})
    summary=client.get('/api/console/summary',headers=ADMIN).json()
    assert summary['stats']['verified_agents']==1 and 'active_tasks' not in summary['stats']
    assert 'product-old-task' not in [r['id'] for r in summary['tasks']]

def test_product_policies_exclude_platform_generated_boundaries_without_deleting_them(client,monkeypatch):
    records=[{'id':'auto','source_kind':'legacy_generated','scope_type':'agent'},
             {'id':'user','source_kind':'user_dsl','scope_type':'system','hits':[{'session_id':None},{'session_id':'s'}]}]
    monkeypatch.setattr(sessions,'policies',lambda *args:{'active':True,'executor_shared':True,'records':json.loads(json.dumps(records))})
    response=client.get('/api/console/agents/a/sessions/s/policies',headers=ADMIN).json()
    assert [r['id'] for r in response['records']]==['user']
    assert response['records'][0]['hits']==[{'session_id':'s'}]
    assert len(sessions.policies('a','s')['records'])==2
    domains=client.get('/api/console/agents/a/sessions/s/domains',headers=ADMIN).json()
    assert domains['nodes'][0]['count']==1 and 'domain_id' not in domains
    monkeypatch.setattr(sessions,'policies',lambda *a:(_ for _ in ()).throw(ValueError('没有此会话')))
    assert client.get('/api/console/agents/a/sessions/s/policies',headers=ADMIN).status_code==409

def test_agent_configuration_filters_legacy_records_in_both_detail_paths(client,monkeypatch):
    from agentscope_app.instances import dsl_policy
    def detail(*args):return {'records':[{'source_kind':'legacy_generated'},{'source_kind':'user_dsl','original_dsl':'rule exact:\n  notify exec "git"'}]}
    monkeypatch.setattr(dsl_policy,'detail',detail)
    data=client.get('/api/console/agents/a/dsl',headers=ADMIN).json()
    assert len(data['records'])==1 and data['records'][0]['original_dsl'].startswith('rule exact:')
    assert len(client.get('/api/agent-instances/a/dsl',headers=ADMIN).json()['records'])==2

def test_resource_mount_is_not_a_workspace_without_native_adapter_mapping(client,monkeypatch):
    monkeypatch.setattr(controller,'listing',lambda:{'instances':[{'id':'hermes-product','agent_type':'hermes','mode':'controlled','resources':['/mounted']} ]})
    assert client.get('/api/console/agents',headers=ADMIN).json()['instances'][0]['workspaces']==[]

def test_product_workspace_requires_native_name_and_project_path(client,monkeypatch):
    path='/projects/orders/src'
    row={'id':'workspace-product','name':'DeepSeek Harness','agent_type':'dsh','mode':'controlled',
         'connected':True,'active':True,'pid':42,'resources':['/projects/orders'],'generation':'g'}
    raw={'id':'native-session','resource':path,'execution_resource':path,
         'mapping':'native_registry','process_ids':[42],
         'native_workspace':{'id':'native-w','name':'订单服务','path':path,'source':'dsh_workspace_registry'}}
    monkeypatch.setattr(controller,'listing',lambda:{'instances':[row]})
    monkeypatch.setattr(sessions,'broker',lambda *a,**k:{'sessions':[raw]})
    monkeypatch.setattr(sessions,'with_session_names',lambda row,result,*a:result)
    original=sessions.native_sessions(row)['sessions'][0]
    assert original['resource']==path and original['execution_resource']==path
    agent=client.get('/api/console/agents',headers=ADMIN).json()['instances'][0]
    assert agent['workspace_records']==[{'id':'native-w','name':'订单服务','path':path}]
    page=client.get('/api/console/sessions?workspace='+path,headers=ADMIN).json()
    assert page['total']==1 and page['records'][0]['resource']==path
    assert page['records'][0]['workspace_name']=='订单服务'
    assert page['workspace_records']==[{'path':path,'name':'订单服务'}]
    assert sessions.directory()['records'][0]['resource']==path
    monkeypatch.setattr(sessions,'policies',lambda *a:{'instance':row,'session':{**original,'workspace':path,'workspace_name':'订单服务'},'records':[]})
    detail=client.get('/api/console/agents/workspace-product/sessions/native-session/policies',headers=ADMIN).json()['session']
    assert detail['resource']==path and detail['workspace_name']=='订单服务'
    for info in (None,{}, {**raw['native_workspace'],'source':'mount_alias'}, {**raw['native_workspace'],'path':'/projects/foreign'}):
        assert sessions.native_workspace(row,{**raw,'native_workspace':info}) is None
    internal={**raw,'resource':'/host/project','execution_resource':'/w/0',
              'native_workspace':{**raw['native_workspace'],'path':'/w/0'}}
    internal_row={**row,'resources':['/host/project']}
    assert sessions.native_cwd(internal_row,internal)=='/w/0'
    assert sessions.native_workspace(internal_row,internal) is None
    monkeypatch.setattr(controller,'listing',lambda:{'instances':[internal_row]})
    monkeypatch.setattr(sessions,'broker',lambda *a,**k:{'sessions':[internal]})
    for old_filter in ('/w/0','/s/instance-resources/old'):
        hidden=client.get('/api/console/sessions?workspace='+old_filter,headers=ADMIN).json()
        assert hidden['total']==1 and hidden['workspaces']==[] and hidden['workspace_records']==[]
        assert hidden['records'][0]['resource'] is None and hidden['records'][0]['workspace_name'] is None
    assert sessions.native_workspace({'mode':'observed'}, {'mapping':'native_gateway','resource':'C:/Projects/app',
        'native_workspace':{'id':'windows-workspace','source':'dsh_workspace_registry','path':'C:/Projects/app','name':'客户端'}})=='C:/Projects/app'

def test_shared_policy_counts_use_visible_targets_but_raw_inheritance_keeps_retained_agent(client,monkeypatch):
    from agentscope_app.instances import dsl_policy
    console.retain([('agent','retained-scope-test')],'exact test target')
    original={'records':[{'bindings':[{'instance_id':'live-target','active':True},{'instance_id':'retained-scope-test','active':False}]}],
              'targets':[{'id':'live-target'},{'id':'retained-scope-test'}]}
    monkeypatch.setattr(dsl_policy,'detail',lambda *a:json.loads(json.dumps(original)))
    result=client.get('/api/console/security/system/dsl',headers=ADMIN).json()
    assert result['records'][0]['coverage']=={'total_count':1,'loaded_count':1,'verified_count':1}
    assert result['records'][0]['active'] is True
    assert len(dsl_policy.detail('system')['targets'])==2
    with db.connect() as con:con.execute("DELETE FROM console_retained_records WHERE record_id='retained-scope-test'")

def test_unattributed_events_cannot_starve_later_trusted_session_pages(client,monkeypatch):
    row={'id':'product-kernel','generation':'product-gen'}
    monkeypatch.setattr(sessions,'session_context',lambda *a:(row,{'id':'s'},row['generation'],True))
    monkeypatch.setattr(sessions,'collect_kernel',lambda *a:{'available':True})
    monkeypatch.setattr(sessions.dsl_policy,'receipt',lambda *a:None)
    store.event(row['id'],'tool_start',{'kernel_call_tag':91,'domain_id':900},row['generation'],'s','call','read')
    with db.connect() as con:
        ids=[]
        for n in range(205):
            e={'op':'read','target':'/a','process_domain_id':900,'tool_call_tag':91 if n in (0,1) else 0,'effect':'notify','action':'report'}
            cur=con.execute('INSERT INTO instance_kernel_events(instance_id,generation,source_key,bundle_hash,domain_id,event_json,created_at) VALUES(?,?,?,?,?,?,?)',
                (row['id'],row['generation'],str(n),'bundle',900,json.dumps(e),db.now()));ids.append(cur.lastrowid)
    first=sessions.kernel_page(row['id'],'s',limit=1,session_only=True)
    assert [e['id'] for e in first['records']]==[ids[1]] and first['next_cursor']==ids[1]
    second=sessions.kernel_page(row['id'],'s',limit=1,before=first['next_cursor'],session_only=True)
    assert [e['id'] for e in second['records']]==[ids[0]] and second['next_cursor'] is None
    assert all(e['session_id']=='s' and not e['blocked'] for e in first['records']+second['records'])
    assert len(sessions.kernel_page(row['id'],'s',limit=100)['records'])==100
    with db.connect() as con:assert con.execute('SELECT COUNT(*) FROM instance_kernel_events WHERE instance_id=?',(row['id'],)).fetchone()[0]==205

def test_request_provenance_cannot_be_forged_by_browser_actor(client):
    r=client.post('/api/strategies',headers=ADMIN,json={'text':'product actor provenance policy','actor':'研究者'});assert r.status_code==200,r.text
    with db.connect() as con:
        audit=con.execute("SELECT actor FROM audit_log WHERE action='strategy_created' ORDER BY created_at DESC LIMIT 1").fetchone()
        assert audit[0]=='管理员凭据操作（未识别个人）'

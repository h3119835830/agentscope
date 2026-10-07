from pathlib import Path
import re
import json,uuid
import pytest
from fastapi.testclient import TestClient
from agentscope_app import db
from agentscope_app.managed import controller as c
from agentscope_app.main import app

@pytest.fixture
def bound(seed_task,monkeypatch):
    db.init_db();task=uuid.uuid4().hex[:16];seed_task(task)
    state={'phase':'running','gate':'open','revision':1,'version':1,'policy_hash':'fixed','baseline_hash':'safety','baseline_extra':'rule baseline:\n  block write file "/tmp/work/tests/**" if AGENT\n  because "tests immutable"','protected':['/tmp/work/tests/test.py'],'allowed_write_dirs':['.'],'allow_output':False,'binding':{'domain_id':7},'session_id':'session-native','turn':2}
    with db.connect() as con:c.save(con,task,state)
    context={'request_evidence_id':'5','sources':[{'evidence_id':'5'}],'base_snapshot':{'payload':{'allowed_write_dirs':['.'],'allow_output':False}},'capabilities':{'registered_directories':['.','src','tests']},'revision':1,'policy_hash':'fixed'}
    import agentscope_app.main as main
    monkeypatch.setattr(main,'compile_policy',lambda *args:('compiled',{},None))
    return task,state,{'id':uuid.uuid4().hex,'task_id':task,'revision':1,'policy_hash':'fixed','context_json':json.dumps(context)}

def proposal(**changes):return {'decision':'no_change','allowed_write_dirs':['.'],'allow_output':False,'evidence_ids':['5'],'explanation':'ordinary message needs no permission change',**changes}

def test_no_change_cannot_expand(bound):
    with pytest.raises(ValueError,match='不能修改权限'):c.validate_candidate(bound[2],proposal(allow_output=True))
def test_unknown_target_rejected(bound):
    with pytest.raises(ValueError,match='未登记'):c.validate_candidate(bound[2],proposal(decision='restrict',allowed_write_dirs=['../../etc']))
def test_request_evidence_required(bound):
    with pytest.raises(ValueError,match='本轮证据'):c.validate_candidate(bound[2],proposal(evidence_ids=['6']))
def test_stale_context_cannot_apply(bound):
    job={**bound[2],'revision':0}
    with pytest.raises(ValueError,match='stale'):c.validate_candidate(job,proposal())
def test_restriction_keeps_baseline(bound):
    task,state,job=bound
    c.validate_candidate(job,proposal(decision='restrict',allowed_write_dirs=['src']))
    with db.connect() as con:t=c.task_row(con,task)
    dsl,_=c.render(t,state,['src'],False)
    assert 'tests immutable' in dsl and '/tmp/work/tests/**' in dsl
    assert '/tmp/work/src/**' in dsl

def test_expand_requires_matching_human_confirmation(bound):
    with pytest.raises(ValueError,match='候选已变化'):c.confirm_expansion(bound[0],'invented')
def test_foreign_session_cannot_append(bound):
    with pytest.raises(ValueError,match='其他会话'):c.ingest(bound[0],{'kind':'native_event','session_id':'foreign','event_key':'f','type':'turn/start','data':{'turn':1}})
def test_generator_requires_short_lived_credential(bound):
    with TestClient(app) as client:
        r=client.post('/api/generator/tasks/'+bound[0]+'/managed-jobs/fake/tools/get_runtime_context',json={'args':{}})
        assert r.status_code==401

def test_administrator_api_is_protected(bound):
    with TestClient(app) as client:assert client.post('/api/managed/tasks/'+bound[0]+'/close',json={}).status_code==401

def test_install_persists_binding_with_real_database_schema(bound,monkeypatch):
    task,state,_=bound
    state={**state,'version':0,'session_id':None,'phase':'generating','gate':'closed'}
    with db.connect() as con:c.save(con,task,state)
    def broker(request,**kwargs):
        action=request['action']
        if action=='launch':return {'domain_id':51,'runner_pid':99,'watch_pid':98,'web_url':'http://127.0.0.1:18020/'}
        if action=='native-session':return {'sessionId':'durable-native-session'}
        if action=='managed-verify':return {'passed':True,'probe':{'pid':100}}
        if action=='status':return {'status':'running','domain_id':51}
        raise AssertionError(action)
    monkeypatch.setattr(c,'broker',broker)
    result=c.install(task,state,['.'],False,initial=True)
    with db.connect() as con:
        stored=c.load(con,task);row=c.task_row(con,task)
    assert result['session_id']==stored['session_id']=='durable-native-session'
    assert row['status']=='running' and row['active_domain_id']==51 and row['watch_pid']==98
    assert row['active_version']==stored['version']==1

def test_unverified_install_stops_before_admission(bound,monkeypatch):
    task,state,_=bound;calls=[]
    state={**state,'phase':'generating'}
    with db.connect() as con:c.save(con,task,state)
    def broker(request,**kwargs):
        calls.append(request['action'])
        return {'launch':{'domain_id':51},'native-session':{'sessionId':'native'},'managed-verify':{'passed':False},'status':{'status':'running','domain_id':51},'stop':{}}[request['action']]
    monkeypatch.setattr(c,'broker',broker)
    with pytest.raises(ValueError,match='核验失败'):c.install(task,state,['.'],False,initial=True)
    assert calls[-1]=='stop'
    with db.connect() as con:assert c.load(con,task)['version']==1  # previous approved state was never replaced


def test_runtime_object_protection_keeps_adjacent_file_available(bound):
    task,state,job=bound
    ctx=json.loads(job['context_json']);ctx['capabilities']['registered_files']=['src/locked.py','src/other.py'];ctx['project_sources']=[{'id':'src/locked.py'}];job={**job,'context_json':json.dumps(ctx)}
    with db.connect() as con:c.event(con,task,'pi_source',job['id']+':src/locked.py',{'hash':'read'})
    result=c.validate_candidate(job,proposal(decision='restrict',protected_paths=['src/locked.py'],evidence_ids=['5','project:src/locked.py']))
    with db.connect() as con:row=c.task_row(con,task)
    dsl,_=c.render(row,state,['.'],False,result['protected_paths'])
    assert '/tmp/work/src/locked.py' in dsl and '/tmp/work/src/other.py' not in dsl

def test_no_change_cannot_drop_confirmed_objects(bound):
    ctx=json.loads(bound[2]['context_json']);ctx['base_snapshot']['payload']['protected_paths']=['src/locked.py']
    with pytest.raises(ValueError,match='移除'):c.validate_candidate({**bound[2],'context_json':json.dumps(ctx)},proposal(protected_paths=[]))

def test_confirmation_rechecks_project_hash(bound,tmp_path):
    task,state,_=bound;source=tmp_path/'source';source.write_text('changed')
    with db.connect() as con:
        con.execute('UPDATE tasks SET workspace=? WHERE id=?',(str(tmp_path),task))
        c.save(con,task,{**state,'pending_expansion':{'job_id':'confirm-job','hash':'proposal','proposal':proposal(decision='expand',allow_output=True)}})
        con.execute("INSERT INTO managed_jobs(id,task_id,request_key,revision,policy_hash,context_json,created_at) VALUES(?,?,?,?,?,?,?)",('confirm-job',task,'k',1,'fixed',json.dumps({'project_sources':[{'path':str(source),'hash':'old'}]}),db.now()))
    with pytest.raises(ValueError,match='项目证据改变'):c.confirm_expansion(task,'proposal')

def test_probe_denials_never_become_native_tool_feedback(bound):
    task,state,_=bound
    raw={'pid':99,'ppid':55,'process_domain_id':7,'domain_id':8,'timestamp_unix_ns':__import__('time').time_ns(),'op':'write','target':'tests/test.py'}
    with db.connect() as con:
        c.event(con,task,'tool_start','call',{'call_id':'call','serialized':True,'domain_id':7})
        c.event(con,task,'kernel','probe',{'verification_probe':True,'event':raw})
    assert c.tool_feedback(task,'call')=={'events':[]}

def test_stale_domain_event_has_no_tool_association(bound):
    task,state,_=bound
    with db.connect() as con:
        c.event(con,task,'tool_start','call',{'call_id':'call','serialized':True,'domain_id':7})
        assert c.correlate_tool(con,task,{'process_domain_id':8,'ppid':55,'timestamp_unix_ns':__import__('time').time_ns()}) is None


def test_reviewed_history_tool_does_not_hold_nested_write_transaction(bound):
    import time
    task,_,_=bound
    with db.connect() as con:
        con.execute("INSERT INTO managed_jobs(id,task_id,request_key,revision,policy_hash,context_json,status,token_hash,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",('history-job',task,'history-key',1,'fixed',json.dumps({'change':{'text':'protect tests'}}),'running',c.digest('credential'),time.time()+30,db.now()))
    with TestClient(app) as client:
        response=client.post('/api/generator/tasks/'+task+'/managed-jobs/history-job/tools/search_reviewed_history',headers={'Authorization':'Bearer credential'},json={'args':{}})
        assert response.status_code==200,response.text
        assert 'matches' in response.json()
    with db.connect() as con:assert con.execute("select 1 from managed_events where kind='pi_history' and event_key='history-job'").fetchone()


def test_ended_task_cannot_be_resurrected_by_install(bound,monkeypatch):
    task,state,_=bound
    with db.connect() as con:c.save(con,task,{**state,'phase':'ended'})
    monkeypatch.setattr(c,'broker',lambda *a,**k:pytest.fail('ended task must never reach broker'))
    with pytest.raises(ValueError,match='ended'):c.install(task,state,['.'],False)


def test_background_denial_keeps_original_call_identity(bound):
    task,state,_=bound
    with db.connect() as con:
        c.event(con,task,'tool_start','old',{'call_id':'old','domain_id':7,'kernel_call_tag':'123'})
        c.event(con,task,'tool_result','old',{'call_id':'old'})
        c.event(con,task,'tool_start','new',{'call_id':'new','domain_id':7,'kernel_call_tag':'456'})
        assert c.correlate_tool(con,task,{'process_domain_id':7,'tool_call_tag':'123','ppid':1})=='old'
        assert c.correlate_tool(con,task,{'process_domain_id':8,'tool_call_tag':'123'}) is None
        assert c.correlate_tool(con,task,{'process_domain_id':7,'tool_call_tag':'0'}) is None


def test_bound_native_tool_event_accepts_broker_domain_fields(bound,monkeypatch):
    task,state,_=bound
    monkeypatch.setattr(c,'broker',lambda *a,**k:{'kernel_call_tag':'123','pid':99,'domain_id':7})
    assert c.ingest(task,{'kind':'tool_start','session_id':'session-native','event_key':'call','call_id':'call','pid':99,'name':'bash'})=={'stored':True}
    with db.connect() as con:
        value=json.loads(con.execute("select payload_json from managed_events where task_id=? and kind='tool_start'",(task,)).fetchone()[0]);assert value['kernel_call_tag']=='123' and value['domain_id']==7


def test_ancestor_guards_do_not_ban_adjacent_files(bound):
    task,state,_=bound
    with db.connect() as con:row=c.task_row(con,task)
    state={**state,'protected':['/tmp/work/project/config/settings.json']}
    dsl,_=c.render(row,state,['.'],False)
    assert 'block write file "/tmp/work/project" if AGENT' in dsl
    assert 'block write file "/tmp/work/project/config" if AGENT' in dsl
    assert 'block write file "/tmp/work/project/**"' not in dsl
    assert 'block write file "/tmp/work/project/implementation.py"' not in dsl


def test_worker_failure_cannot_resurrect_ended_task(bound,monkeypatch):
    from agentscope_app.managed.worker import Worker
    task,state,_=bound
    with db.connect() as con:c.save(con,task,{**state,'phase':'ended'})
    monkeypatch.setattr(c,'broker',lambda *a,**k:pytest.fail('ended task must never reach broker'))
    Worker().fail(task,'late failure')
    with db.connect() as con:assert c.load(con,task)['phase']=='ended'

def test_recovery_reassesses_latest_public_input_before_resume(bound,monkeypatch):
    task,state,_=bound;calls=[]
    with db.connect() as con:
        c.save(con,task,{**state,'phase':'recovering'})
        c.event(con,task,'request','real-user',{'actor':'native_user','text':'Preserve src/locked.py','revision':1})
    def install(*args,**kwargs):
        recovered={**state,'phase':'running','gate':'waiting_policy'}
        with db.connect() as con:c.save(con,task,recovered)
        return recovered
    monkeypatch.setattr(c,'install',install)
    monkeypatch.setattr(c,'broker',lambda request,**kwargs:calls.append(request))
    monkeypatch.setattr(c,'context',lambda *args:{})
    c.recover(task)
    with db.connect() as con:
        stored=c.load(con,task);job=json.loads(con.execute('SELECT context_json FROM managed_jobs WHERE task_id=?',(task,)).fetchone()[0])
    assert stored['gate']=='waiting_policy' and job['change']['text']=='Preserve src/locked.py'
    assert calls[-1]['operation']=='resume' and 'Preserve src/locked.py' in calls[-1]['text']


def test_reviewed_template_is_read_hash_bound_and_never_replaces_request(bound):
    task,state,job=bound;record={'id':'template-x','statement':'keep existing config'};h=c.digest(record)
    with db.connect() as con:
        con.execute('INSERT INTO bootstrap_history VALUES(?,?,?,?,?,?,?)',('template-x','keep config',json.dumps(record),h,'approved',h,'test_sample'))
        c.event(con,task,'pi_history','history-read',{'versions':[{'id':'template-x','hash':h}]})
    job={**job,'id':'history-read'}
    assert c.validate_candidate(job,proposal(evidence_ids=['5','template-x']))['decision']=='no_change'
    with pytest.raises(ValueError,match='本轮证据'):c.validate_candidate(job,proposal(evidence_ids=['template-x']))
    with db.connect() as con:con.execute("UPDATE bootstrap_history SET reviewed_hash='changed' WHERE id='template-x'")
    with pytest.raises(ValueError,match='历史模板'):c.validate_candidate(job,proposal(evidence_ids=['5','template-x']))


def test_public_input_race_stops_replacement_and_preserves_latest_request(bound,monkeypatch):
    task,state,_=bound;state={**state,'phase':'generating','version':0,'session_id':None};calls=[]
    with db.connect() as con:c.save(con,task,state)
    def broker(req,**kwargs):
        calls.append(req['action'])
        if req['action']=='launch':return {'domain_id':51,'runner_pid':99,'watch_pid':98,'web_url':'http://127.0.0.1:18020'}
        if req['action']=='native-session':
            with db.connect() as con:c.save(con,task,{**state,'revision':state['revision']+1})
            return {'sessionId':'durable-native-session'}
        if req['action']=='managed-verify':return {'passed':True,'probe':{'pid':100}}
        if req['action']=='status':return {'status':'running','domain_id':51}
        if req['action']=='stop':return {'status':'stopped'}
    monkeypatch.setattr(c,'broker',broker)
    with pytest.raises(ValueError,match='stale'):c.install(task,state,['.'],False,initial=True)
    with db.connect() as con:stored=c.load(con,task)
    assert stored['phase']=='failed' and stored['gate']=='failed' and stored['revision']==state['revision']+1
    assert calls[-1]=='stop' and stored['version']==0


def test_pending_public_constraint_survives_new_ordinary_message(bound):
    task,state,job=bound;ctx=json.loads(job['context_json']);ctx['sources']=[{'evidence_id':'4'},{'evidence_id':'5'}];ctx['unassessed_request_ids']=['4','5'];job={**job,'context_json':json.dumps(ctx)}
    with pytest.raises(ValueError,match='公开请求'):c.validate_candidate(job,proposal())
    assert c.validate_candidate(job,proposal(evidence_ids=['4','5']))['decision']=='no_change'


def test_verified_false_block_queues_evidence_bound_review(bound,monkeypatch):
    task,state,_=bound
    monkeypatch.setattr(c,'context',lambda *args:{})
    def broker(request,**kwargs):
        if request['action']=='native-session':return {'status':'idle'}
        return {'probe':{'pid':100,'blocked':True,'success':False,'operation':'write'},'kernel_events':[{'pid':100,'process_domain_id':7,'blocked':True,'target':'/tmp/work/adjacent.py'}],'effect_verified':False,'domain_id':7}
    monkeypatch.setattr(c,'broker',broker)
    with TestClient(app) as client:
        result=client.post('/api/managed/tasks/'+task+'/verify-operation',headers={'Authorization':'Bearer test-admin-token-not-for-production'},json={'target':'/tmp/work/adjacent.py','operation':'write','expected':'allow'})
    assert result.status_code==200 and result.json()['classification']=='false_block'
    with db.connect() as con:
        stored=c.load(con,task);frozen=json.loads(con.execute('SELECT context_json FROM managed_jobs WHERE task_id=?',(task,)).fetchone()[0])
    assert stored['gate']=='waiting_policy' and stored['baseline_hash']==state['baseline_hash']
    assert 'expected-allowed' in frozen['change']['text']


def test_private_native_file_uses_narrow_broker_read(bound,tmp_path,monkeypatch):
    from pathlib import Path
    task=bound[0];file=tmp_path/'native.txt';file.write_text('private native material')
    import os
    original=os.open;calls=[]
    def read(path,flags,*args,**kwargs):
        if path==file.name and kwargs.get('dir_fd') is not None:raise PermissionError('native mode 0600')
        return original(path,flags,*args,**kwargs)
    def broker(request,**kwargs):
        calls.append(request);return {'hash':c.digest('private native material'),'content':'private native material'}
    monkeypatch.setattr(os,'open',read);monkeypatch.setattr(c,'broker',broker)
    result=c.project_source({'id':task,'workspace':str(tmp_path)},file)
    assert result['content']=='private native material'
    assert calls==[{'action':'managed-source-read','task_id':task,'path':'native.txt'}]
    with pytest.raises(ValueError):c.read_project_content({'id':task,'workspace':str(tmp_path/'other')},file)


def test_context_read_failure_returns_pause_instead_of_transport_500(bound,monkeypatch):
    from agentscope_app.managed.worker import worker
    calls=[];task=bound[0]
    monkeypatch.setattr(c,'ingest',lambda *a:(_ for _ in ()).throw(PermissionError('project source unavailable')))
    monkeypatch.setattr(worker,'fail',lambda *a:calls.append(a))
    import agentscope_app.managed.api as managed_api
    monkeypatch.setattr(managed_api,'authenticate',lambda *a:None)
    with TestClient(app) as client:
        result=client.post('/api/plugin/tasks/'+task+'/managed/events',json={'args':{}})
    assert result.status_code==409 and calls[0][0]==task


def test_legacy_task_launch_cannot_bypass_managed_admission(bound):
    with TestClient(app) as client:
        result=client.post('/api/tasks/'+bound[0]+'/launch',headers={'Authorization':'Bearer test-admin-token-not-for-production'},json={})
    assert result.status_code==409 and '受管工作台' in result.json()['detail']


def test_agent_refusal_is_self_report_not_kernel_success(bound):
    task=bound[0]
    c.ingest(task,{'kind':'agent_decision','decision':'refuse','event_key':'decision','session_id':'session-native','operation':'write','target':'tests/test.py','reason':'immutable startup baseline'})
    with db.connect() as con:
        events=con.execute('select kind,payload_json from managed_events where task_id=?',(task,)).fetchall()
    assert len(events)==1 and events[0]['kind']=='agent_refusal'
    assert json.loads(events[0]['payload_json'])['authority']=='agent_report; not_kernel_enforcement'


def test_runtime_context_publishes_concrete_candidate_only_expansion(bound,monkeypatch):
    task,state,_=bound;monkeypatch.setattr(c,'context',lambda *a:{})
    with db.connect() as con:
        c.enqueue(con,task,state,'Request output access pending confirmation','output-contract')
        frozen=json.loads(con.execute('select context_json from managed_jobs where task_id=?',(task,)).fetchone()[0])
        output=c.task_row(con,task)['output_dir']
    assert frozen['path_mapping']['output']==output
    target=frozen['capabilities']['expansion_targets'][0]
    assert target['path']==output and target['proposal_fields']=={'allow_output':True} and target['confirmation_required']
    assert frozen['capabilities']['candidate_contract']['submission']=='proposed_snapshot_only'

def test_expansion_is_candidate_only_and_target_must_be_advertised(bound):
    task,state,job=bound;ctx=json.loads(job['context_json'])
    with pytest.raises(ValueError,match='Unadvertised'):c.validate_candidate(job,proposal(decision='expand',allow_output=True))
    ctx['capabilities']['expansion_targets']=[{'kind':'task_output','path':'/tmp/output'}]
    job={**job,'context_json':json.dumps(ctx)}
    p=c.validate_candidate(job,proposal(decision='expand',allow_output=True))
    assert p['decision']=='expand'
    with db.connect() as con:assert c.load(con,task)['allow_output'] is False


def test_equivalent_restriction_does_not_restart_domain(bound):
    with pytest.raises(ValueError,match='No OS restriction changed'):c.validate_candidate(bound[2],proposal(decision='restrict'))


def test_double_confirmation_is_rejected_during_transition(bound):
    task,state,_=bound
    with db.connect() as con:c.save(con,task,{**state,'gate':'applying','pending_expansion':{'hash':'same'}})
    with pytest.raises(ValueError,match='不能重复确认'):c.confirm_expansion(task,'same')


def test_legacy_scope_manager_cannot_change_native_managed_domain(bound):
    with TestClient(app) as client:
        result=client.post('/api/tasks/'+bound[0]+'/scope-manager/session',headers={'Authorization':'Bearer test-admin-token-not-for-production'},json={})
    assert result.status_code==409 and '受管工作台' in result.json()['detail']


def test_native_prompt_during_domain_replacement_is_explicitly_rejected(bound,monkeypatch):
    task,state,_=bound
    with db.connect() as con:c.save(con,task,{**state,'gate':'applying'})
    monkeypatch.setattr(c,'broker',lambda *a,**k:pytest.fail('replacement must not admit a message into an old native process'))
    with TestClient(app) as client:
        result=client.post('/api/managed/tasks/'+task+'/prompt',headers={'Authorization':'Bearer test-admin-token-not-for-production'},json={'text':'real next message'})
    assert result.status_code==409 and '重试' in result.json()['detail']


def test_native_question_answer_reassesses_public_context_with_real_call(bound,monkeypatch):
    task,state,_=bound;monkeypatch.setattr(c,'context',lambda *a:{})
    with pytest.raises(ValueError,match='实际工具调用'):c.ingest(task,{'kind':'user_question_answer','session_id':'session-native','event_key':'q','call_id':'call','text':'human answer'})
    with db.connect() as con:
        c.event(con,task,'tool_start','call',{'name':'ask_user_question','session_id':'session-native'})
        c.event(con,task,'tool_result','call',{'name':'ask_user_question','succeeded':True})
    c.ingest(task,{'kind':'user_question_answer','session_id':'session-native','event_key':'q','call_id':'call','text':'human answer'})
    with db.connect() as con:
        state=c.load(con,task);request=json.loads(con.execute("select payload_json from managed_events where task_id=? and kind='request'",(task,)).fetchone()[0])
    assert state['gate']=='waiting_policy' and request['actor']=='native_user' and request['text']=='human answer'


def test_deferred_native_probe_cannot_run_arbitrary_or_unprotected_operations(bound,monkeypatch):
    task,state,_=bound;calls=[]
    monkeypatch.setattr(c,'broker',lambda request,**k:calls.append(request) or {'call_id':'managed-verification:test','result_path':'/tmp/work/result','source':'native_sdk_fixed_probe','attempted_by_agent':False})
    with TestClient(app) as client:
        route='/api/managed/tasks/'+task+'/verify-deferred-operation';headers={'Authorization':'Bearer test-admin-token-not-for-production'}
        for target,operation in [('/tmp/work/other.py','write_open'),('/tmp/work/tests/test.py','unlink')]:
            result=client.post(route,headers=headers,json={'target':target,'operation':operation,'expected':'deny'})
            assert result.status_code==409
        with db.connect() as con:c.save(con,task,{**state,'protected':['/tmp/work/tests/test.py']})
        result=client.post(route,headers=headers,json={'target':'/tmp/work/tests/test.py','operation':'write_open','expected':'deny'})
        assert result.status_code==200 and result.json()['attempted_by_agent'] is False
    assert len(calls)==1 and calls[0]['operation']=='verify_delayed_open'


def test_project_source_rejects_file_and_directory_symlink_aliases(tmp_path,monkeypatch):
    root=tmp_path/'workspace';root.mkdir();outside=tmp_path/'outside';outside.mkdir();(outside/'value').write_text('unregistered')
    (root/'file').symlink_to(outside/'value');(root/'directory').symlink_to(outside,target_is_directory=True)
    monkeypatch.setattr(c,'broker',lambda *a,**k:pytest.fail('symlink is not permission fallback'))
    for path in (root/'file',root/'directory/value'):
        with pytest.raises(OSError):c.read_project_content({'id':'test','workspace':str(root)},path)


@pytest.mark.skipif(__import__('os').geteuid()!=0,reason='collector requires a root-owned kernel log')
def test_kernel_arriving_during_analysis_requeues_and_retains_pending_constraint(bound,tmp_path,monkeypatch):
    from agentscope_app.managed.worker import Worker
    task,state,_=bound;workspace=tmp_path/'workspace';workspace.mkdir();log=workspace/'.actplane';log.mkdir()
    raw={'blocked':True,'pid':901,'process_domain_id':7,'domain_id':1,'op':'write','target':str(workspace/'protected.txt'),'rule':{'name':'floor'}}
    (log/'events.jsonl').write_text(json.dumps(raw)+'\n')
    state['binding_history']=[{'domain_id':7,'version':1}]
    monkeypatch.setattr(c,'context',lambda *args:{})
    monkeypatch.setattr(c,'broker',lambda *args,**kwargs:{'status':'running','domain_verified':True})
    with db.connect() as con:
        con.execute('UPDATE tasks SET workspace=? WHERE id=?',(str(workspace),task));c.save(con,task,state)
        old=c.enqueue(con,task,state,'Preserve the newly named file','real-user')
    worker=Worker()
    class TwoPasses:
        count=0
        def is_set(self):return self.count>=2
        def wait(self,*args):self.count+=1
    worker.halt=TwoPasses();worker.collect()
    with db.connect() as con:
        current=c.load(con,task)
        jobs=con.execute('SELECT id,status,context_json FROM managed_jobs WHERE task_id=? ORDER BY created_at',(task,)).fetchall()
        assert len(jobs)==2 and jobs[0]['id']==old['id'] and jobs[0]['status']=='stale'
        latest=json.loads(jobs[1]['context_json'])
        assert len(latest['unassessed_request_ids'])==1
        assert latest['request_evidence_id'] not in latest['unassessed_request_ids']
        assert any(x['text']=='Preserve the newly named file' for x in latest['public_task_context'])
        assert any(x['source']=='kernel' for x in latest['sources'])
        assert current['gate']=='waiting_policy' and jobs[1]['status']=='queued'
        assert con.execute("SELECT count(*) FROM managed_events WHERE task_id=? AND kind='kernel'",(task,)).fetchone()[0]==1


def test_baseline_object_is_not_a_new_runtime_restriction(bound):
    _,_,job=bound;ctx=json.loads(job['context_json'])
    ctx.update(baseline={'protected_files':['/tmp/work/tests/test.py']},path_mapping={'workspace':'/tmp/work'})
    ctx['capabilities']['registered_files']=['tests/test.py'];job={**job,'context_json':json.dumps(ctx)}
    with pytest.raises(ValueError,match='already protected by the immutable startup baseline'):
        c.validate_candidate(job,proposal(decision='restrict',protected_paths=['tests/test.py']))


def test_outbox_retries_until_native_session_persists_feedback(bound,monkeypatch):
    from agentscope_app.managed.worker import Worker
    task,state,_=bound
    with db.connect() as con:
        c.event(con,task,'tool_result','late-call',{'session_id':state['session_id']})
        c.event(con,task,'kernel','late-kernel',{'event':{'pid':987,'process_domain_id':7,'op':'write','target':'/tmp/work/tests/test.py','rule':{'name':'floor'}},'tool_call_id':'late-call','turn':2})
        con.execute("UPDATE managed_events SET occurred_at='2000-01-01T00:00:00+00:00' WHERE task_id=? AND kind='kernel'",(task,))
    calls=[]
    def broker(req,**kwargs):
        calls.append(req);return {'accepted':True,'persisted':len(calls)>1}
    monkeypatch.setattr(c,'broker',broker);worker=Worker()
    class TwoPasses:
        count=0
        def is_set(self):return self.count>=2
        def wait(self,*args):self.count+=1
    worker.halt=TwoPasses();worker.deliver_feedback()
    with db.connect() as con:
        delivered=con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='feedback_delivery'",(task,)).fetchall()
    assert len(calls)==2 and len(delivered)==1
    payload=json.loads(delivered[0][0]);assert payload['call_id']=='late-call' and payload['authority']=='native_context_persisted'
    assert calls[0]['session_id']==calls[1]['session_id']==state['session_id']


def test_operational_followup_keeps_pending_review_intent_and_requires_fresh_candidate(bound,monkeypatch):
    task,state,job=bound;state['pending_expansion']={'hash':'old-review','proposal':proposal(decision='expand',allow_output=True)}
    monkeypatch.setattr(c,'context',lambda *args:{})
    with db.connect() as con:
        c.save(con,task,state);review=c.enqueue(con,task,state,'Repeat native permission request','dsh-repeat',actor='DSH')
        stored=con.execute('SELECT * FROM managed_jobs WHERE id=?',(review['id'],)).fetchone();current=c.load(con,task)
    ctx=json.loads(stored['context_json']);assert current['pending_expansion'] is None and ctx['pending_expansion_review']['prior_hash']=='old-review'
    fresh=proposal(evidence_ids=[ctx['request_evidence_id']])
    with pytest.raises(ValueError,match='does not withdraw a pending review-only'):c.validate_candidate(dict(stored),fresh)
    with db.connect() as con:
        current=c.load(con,task);c.enqueue(con,task,current,'Withdraw the output request','actual-user-withdrawal',actor='native_user')
        assert not c.load(con,task).get('pending_expansion_intent')


def test_runtime_cannot_broaden_existing_test_collection_to_future_artifacts(bound):
    _,_,job=bound;ctx=json.loads(job['context_json'])
    ctx.update(baseline={'protected_files':['/tmp/work/tests/test.py'],'declared_constraints':[{'id':'retain-existing-tests','object_scope':'registered_existing_files','targets':['/tmp/work/tests/test.py']}]},path_mapping={'workspace':'/tmp/work'})
    job={**job,'context_json':json.dumps(ctx)}
    with pytest.raises(ValueError,match='overbroad registered object collection'):
        c.validate_candidate(job,proposal(decision='restrict',protected_paths=['tests/**']))


def test_loaded_permissions_and_historical_reports_have_distinct_authority(bound,monkeypatch):
    task,state,_=bound;state['allow_output']=True;monkeypatch.setattr(c,'context',lambda *args:{})
    with db.connect() as con:
        c.save(con,task,state)
        prior=c.event(con,task,'request','old-output',{'text':'output is denied; request access','actor':'DSH','revision':0})
        prior_id=str(con.execute("SELECT id FROM managed_events WHERE task_id=? AND event_key='old-output'",(task,)).fetchone()[0])
        c.event(con,task,'request_resolved','confirmed',{'evidence_ids':[prior_id],'decision':'expand','version':1})
        job=c.enqueue(con,task,state,'Write to the already confirmed output','real-next')
        frozen=json.loads(con.execute('SELECT context_json FROM managed_jobs WHERE id=?',(job['id'],)).fetchone()[0])
    public=c.runtime_projection(frozen)
    assert public['effective_policy']['snapshot']['allow_output'] is True
    assert public['effective_policy']['authority']=='controller_verified_loaded_snapshot'
    assert public['capabilities']['expansion_targets']==[]
    historical=next(x for x in public['public_task_context'] if x['evidence_id']==prior_id)
    assert historical['assessment_status']=='resolved' and 'not_current_state' in historical['authority']
    assert all('content' not in source for source in public['project_sources'])


def test_durable_audit_filter_finds_early_kernel_events_and_paginates(bound):
    task,_,_=bound
    with db.connect() as con:
        for i in range(55):c.event(con,task,'kernel','real-'+str(i),{'event':{'pid':i,'op':'write','target':'test.py'},'verification_probe':False})
        c.event(con,task,'kernel','probe-only',{'verification_probe':True})
        for i in range(330):c.event(con,task,'agent_response','later-'+str(i),{'text':'ordinary public response'})
    newest=c.audit_history(task,'kernel');older=c.audit_history(task,'kernel',newest['next_cursor'])
    assert len(newest['events'])==50 and len(older['events'])==5 and older['next_cursor'] is None
    assert not ({e['id'] for e in newest['events']} & {e['id'] for e in older['events']})
    assert all(not e['payload']['verification_probe'] for e in newest['events']+older['events'])
    with TestClient(app) as client:
        response=client.get('/api/managed/tasks/'+task+'/audit?category=kernel',headers={'Authorization':'Bearer test-admin-token-not-for-production'})
    assert response.status_code==200 and len(response.json()['events'])==50


def test_policy_detail_requires_exact_loaded_hash(bound):
    task,state,_=bound
    with db.connect() as con:row=c.task_row(con,task)
    _,yaml=c.render(row,state,state['allowed_write_dirs'],state['allow_output'])
    with pytest.raises(ValueError,match='confirmed loaded hash'):c.policy_details(task)
    with db.connect() as con:c.save(con,task,{**state,'policy_hash':c.digest(yaml),'verification':{'passed':True}})
    detail=c.policy_details(task)
    assert detail['policy_hash']==c.digest(detail['policy_yaml']) and 'tests immutable' in detail['dsl']
    assert detail['session_id']==state['session_id'] and not detail['historical']
    with db.connect() as con:c.save(con,task,{**state,'policy_hash':c.digest(yaml),'verification':{'passed':True},'phase':'ended'})
    assert c.policy_details(task)['historical'] is True


def test_project_facts_and_operational_test_request_do_not_authorize_source_protection(bound):
    _,_,job=bound;ctx=json.loads(job['context_json'])
    ctx['capabilities'].update(registered_files=['src/code.py'],authorized_protection_targets={})
    with pytest.raises(ValueError,match='no explicit authenticated OS-target authorization'):
        c.validate_candidate({**job,'context_json':json.dumps(ctx)},proposal(decision='restrict',protected_paths=['src/**']))


def test_explicit_user_target_binding_is_separate_from_agent_reports_and_ambiguous_names():
    files=['acceptance-temp.txt','src/code.py','one/config.json','two/config.json'];dirs=['.','src','one','two']
    requests=[{'evidence_id':'1','actor':'native_user','text':'运行 src/code.py 的测试，只报告失败，不修改测试。'},
              {'evidence_id':'2','actor':'DSH','text':'保护 src 目录，不得修改。'},
              {'evidence_id':'3','actor':'native_user','text':'从现在起必须保留 acceptance-temp.txt，不得写入或删除它。'},
              {'evidence_id':'4','actor':'native_user','text':'必须保护 config.json。'},
              {'evidence_id':'6','actor':'native_user','text':'在 src/code.py 添加合法注释，说明受保护对象为什么不能写。'}]
    authorized,scopes=c.restriction_authorizations(requests,['1','2','3','4','6'],files,dirs,'/tmp/work')
    assert set(authorized)=={'acceptance-temp.txt'} and authorized['acceptance-temp.txt'][0]['request_id']=='3'
    assert not scopes
    requests.append({'evidence_id':'5','actor':'native_user','text':'保护 src 目录，从现在起不得修改整个目录树。'})
    authorized,_=c.restriction_authorizations(requests,['5'],files,dirs,'/tmp/work')
    assert set(authorized)=={'src/**'}


def test_procedural_request_cannot_narrow_persistent_write_scope(bound):
    _,_,job=bound;ctx=json.loads(job['context_json']);ctx['capabilities']['authorized_write_scopes']=[]
    with pytest.raises(ValueError,match='procedural read/test instruction'):
        c.validate_candidate({**job,'context_json':json.dumps(ctx)},proposal(decision='restrict',allowed_write_dirs=['src']))


def test_unresolved_necessary_constraint_stays_paused_and_unassessed(bound):
    task,state,job=bound;ctx=json.loads(job['context_json']);ctx['unassessed_request_ids']=['5']
    job={**job,'context_json':json.dumps(ctx)};candidate=c.validate_candidate(job,proposal(decision='guidance_only',unresolved_requests=['5']))
    with db.connect() as con:
        con.execute('INSERT INTO managed_jobs(id,task_id,request_key,revision,policy_hash,status,context_json,proposal_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(job['id'],task,'unresolved',1,'fixed','running',job['context_json'],json.dumps(candidate),db.now()))
    c.finish_job(job)
    with db.connect() as con:
        current=c.load(con,task);assert current['gate']=='waiting_clarification' and current['version']==1
        assert current['pending_unresolved_requests']==['5']
        assert not con.execute("SELECT 1 FROM managed_events WHERE task_id=? AND kind='request_resolved'",(task,)).fetchone()

def test_accepted_native_message_resolves_wait_without_duplicate_dispatch(bound,monkeypatch):
    task,state,_=bound;monkeypatch.setattr(c,'context',lambda *a:{})
    state['gate']='waiting_clarification'
    with db.connect() as con:c.save(con,task,state)
    accepted={'kind':'user_message_accepted','session_id':'session-native','request_id':'clarify','event_key':'accepted:session-native:clarify','text':'Withdraw unsupported new requirement; keep startup protections'}
    job=c.ingest(task,accepted)
    with db.connect() as con:
        current=c.load(con,task);assert current['gate']=='waiting_policy';assert current['revision']==2
    c.ingest(task,{'kind':'native_event','session_id':'session-native','event_key':'turn3','type':'turn/start','data':{'turn':3}})
    dispatched=c.ingest(task,{'kind':'native_event','session_id':'session-native','event_key':'later-seq','type':'user/message','data':{'request_id':'clarify'},'text':accepted['text']})
    assert dispatched['id']==job['id']
    with db.connect() as con:
        assert c.load(con,task)['revision']==2
        assert con.execute('SELECT count(*) FROM managed_jobs WHERE task_id=?',(task,)).fetchone()[0]==1
        payload=json.loads(con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='request'",(task,)).fetchone()[0]);assert payload['accepted_turn']==2 and payload['dispatched_turn']==3 and payload['turn']==3

def test_executor_gate_hides_policy_and_assessment_records(bound):
    task,state,_=bound
    with db.connect() as con:
        c.event(con,task,'control_pause','necessary',{'request_ids':['7'],'reason':'Necessary OS boundary unresolved','version':1})
        c.event(con,task,'request_resolved','clarified',{'evidence_ids':['7','8'],'decision':'no_change'})
    assert c.gate(task)=={'gate':'open','phase':'running'}
    with db.connect() as con:assert c.load(con,task)['baseline_hash']=='safety'


def test_loaded_output_execution_target_survives_pending_target_removal(bound,monkeypatch):
    task,state,_=bound;monkeypatch.setattr(c,'context',lambda *a:{})
    with db.connect() as con:
        first=c.enqueue(con,task,state,'Request output pending confirmation','output-before')
        before=json.loads(con.execute('SELECT context_json FROM managed_jobs WHERE id=?',(first['id'],)).fetchone()[0])
        state.update(allow_output=True,version=2,policy_hash='confirmed-output-hash')
        c.save(con,task,state)
        second=c.enqueue(con,task,state,'Write result within the confirmed output','output-after')
        after=json.loads(con.execute('SELECT context_json FROM managed_jobs WHERE id=?',(second['id'],)).fetchone()[0])
        output=c.task_row(con,task)['output_dir']
    before_target=next(t for t in before['capabilities']['execution_targets'] if t['kind']=='task_output')
    assert before_target['granted'] is False and before['capabilities']['expansion_targets']
    public=c.runtime_projection(after)
    target=next(t for t in public['effective_policy']['execution_targets'] if t['kind']=='task_output')
    assert target['path']==output and target['granted'] is True
    assert target['policy_version']==2 and target['policy_hash']=='confirmed-output-hash'
    assert target['authority']=='controller_verified_loaded_snapshot'
    assert public['capabilities']['expansion_targets']==[]
    assert 'already_granted' in public['capabilities']['output_expansion']


def test_control_source_oracles_and_service_evidence_are_not_agent_material(bound):
    with db.connect() as con:task=c.task_row(con,bound[0])
    rules=c.control_rules(task)
    source_root=str(Path(c.__file__).resolve().parents[3])
    assert 'block read file '+c.quote_dsl(source_root+'/**') in rules
    assert 'block read file "/opt/agentscope/actplane/**"' in rules
    assert 'block read file "/var/lib/agentscope-scope-demo/**" if AGENT' in rules
    assert 'block read file "/var/lib/agentscope-rq5-v1/**" if AGENT unless target "/var/lib/agentscope-rq5-v1/task-python/**"' in rules
    assert 'block read file '+c.quote_dsl(str(Path(db.DB_PATH).parent)+'/**') in rules
    assert '/var/lib/agentscope-*/' not in rules
    # The current backend cannot safely preserve suffixes after internal '*'.
    # All OS patterns must be exact or have only a terminal wildcard.
    patterns=re.findall(r'(?:file|target) "([^"\n]+)"',rules)
    assert all('*' not in value.rstrip('*') for value in patterns)
    assert '/usr/**' not in rules and '/opt/agentscope/.venv/**' not in rules
    assert 'block read file "/var/lib/agentscope-rq5-v1/task-python' not in rules


def test_end_while_startup_is_pending_revokes_analysis_authority(bound,monkeypatch):
    task,state,_=bound;job='pending-startup'
    monkeypatch.setattr(c,'broker',lambda *a,**k:{'status':'not_running'})
    with db.connect() as con:
        c.save(con,task,{**state,'phase':'generating','gate':'waiting_policy','startup_job':job})
        con.execute('INSERT INTO history_jobs(id,kind,status,input_json,created_at) VALUES(?,?,?,?,?)',(job,'task_bootstrap','running',json.dumps({'task_id':task}),db.now()))
        con.execute('INSERT INTO bootstrap_credentials(id,task_id,job_id,token_hash,expires_at) VALUES(?,?,?,?,?)',('startup-credential',task,job,'opaque-test-hash',9999999999))
    c.close(task)
    with db.connect() as con:
        assert c.load(con,task)['phase']=='ended'
        assert con.execute('SELECT status FROM history_jobs WHERE id=?',(job,)).fetchone()[0]=='interrupted'
        credential=con.execute('SELECT expires_at,revoked_at FROM bootstrap_credentials WHERE job_id=?',(job,)).fetchone()
        assert credential['expires_at']==0 and credential['revoked_at']


def test_startup_clarification_changes_evidence_without_replacing_original_task(bound,monkeypatch):
    task,state,_=bound;ctx={'task_description':'original frozen request'}
    with db.connect() as con:
        c.save(con,task,{**state,'phase':'failed','gate':'failed','version':0,'startup_job':'old-startup'})
        original=c.task_row(con,task)['prompt']
        con.execute("UPDATE tasks SET status='failed' WHERE id=?",(task,))
        con.execute('INSERT INTO bootstrap_contexts VALUES(?,?,?,?,?)',(task,'frozen-case',json.dumps(ctx),c.digest(ctx),db.now()))
        con.execute('INSERT INTO bootstrap_credentials(id,task_id,job_id,token_hash,expires_at) VALUES(?,?,?,?,?)',('old-startup-cred',task,'old-startup','opaque-hash',9999999999))
    monkeypatch.setattr(c,'start',lambda ident:{'fresh_generation_requested':ident})
    result=c.clarify_startup(task,'Clarify the actual permitted cleanup target','real-human-key')
    assert result['fresh_generation_requested']==task
    with db.connect() as con:
        after=c.context(task,con);source=con.execute('SELECT * FROM bootstrap_sources WHERE task_id=?',(task,)).fetchone()
        assert c.task_row(con,task)['prompt']==original
        assert c.task_row(con,task)['status']=='prepared'
        assert after['task_description']==ctx['task_description']
        assert after['startup_clarifications'][0]['source_id']==source['id']
        assert source['role']=='task' and source['content_hash']==c.digest(source['text'])
        assert c.load(con,task)['gate']=='closed' and c.load(con,task)['startup_job'] is None
        assert con.execute('SELECT revoked_at FROM bootstrap_credentials WHERE task_id=?',(task,)).fetchone()[0]

def test_startup_clarification_cannot_rewrite_a_loaded_baseline(bound):
    with pytest.raises(ValueError,match='no loaded policy'):
        c.clarify_startup(bound[0],'Remove original protections','bad')

def test_startup_clarification_requires_authenticated_control_plane(bound):
    with TestClient(app) as client:
        response=client.post('/api/managed/tasks/'+bound[0]+'/startup/clarify',json={'text':'Untrusted request'})
    assert response.status_code==401


def test_runtime_observation_is_hashed_deduplicated_and_not_user_authority(bound,monkeypatch):
    task,state,_=bound;calls=[]
    def enqueue(con,task_id,s,text,key,**kw):
        calls.append((s.copy(),kw));return {'id':'observed'}
    monkeypatch.setattr(c,'enqueue',enqueue)
    content='Task memory: preserve src/locked.py.'
    payload={'kind':'runtime_observation','session_id':state['session_id'],'event_key':'context1','category':'memory','type':'compaction/summary','seq':42,'content':content,'content_hash':__import__('hashlib').sha256(content.encode()).hexdigest()}
    assert c.ingest(task,payload)=={'id':'observed'}
    assert calls[0][1]['actor']=='native_context'
    assert c.ingest(task,{**payload,'event_key':'context2'})['deduplicated']
    assert len(calls)==1
    with db.connect() as con:
        observation=c.load(con,task)['runtime_observations']['memory']
        assert observation['content']==content and 'not_authorization' in observation['authority']
    with pytest.raises(ValueError,match='hash mismatch'):c.ingest(task,{**payload,'content_hash':'forged'})


def test_operation_feedback_contains_no_control_policy(bound):
    from agentscope_app.managed.feedback import operation_feedback
    raw={'pid':99,'process_domain_id':7,'op':'write','target':'/tmp/work/tests/test.py','rule':{'id':'private-rule','reason':'private DSL and full policy'}}
    value=operation_feedback(1,raw,{'workspace':'/tmp/work','output_dir':'/tmp/output'})
    assert value['target']==raw['target'] and value['result']=='denied'
    assert not ({'pid','rule','version','policy_hash','process_domain_id','baseline'}&value.keys())
    assert 'private-rule' not in json.dumps(value)
    assert operation_feedback(2,{**raw,'target':'/opt/agentscope-history-v1/backend/secret'},{'workspace':'/tmp/work','output_dir':'/tmp/output'})['target']=='<outside task execution environment>'


def test_feedback_receipt_requires_matching_kernel_offer(bound):
    task,state,_=bound
    args={'kind':'feedback_received','session_id':state['session_id'],'event_key':'received','feedback':'[ActPlane operation feedback] denied'}
    with pytest.raises(ValueError,match='no matching'):c.ingest(task,args)
    with db.connect() as con:c.event(con,task,'feedback_offer','call',{'call_id':'call','feedback':args['feedback'],'event_ids':[42]})
    c.ingest(task,args)
    with db.connect() as con:
        value=json.loads(con.execute("select payload_json from managed_events where task_id=? and kind='feedback_delivery'",(task,)).fetchone()[0])
        assert value['event_ids']==[42] and 'native_context_observed' in value['authority']


def test_pi_context_publishes_fixed_temporary_area_as_already_granted(bound,monkeypatch):
    task,state,_=bound;monkeypatch.setattr(c,'context',lambda *a:{})
    with db.connect() as con:
        job=c.enqueue(con,task,state,'Create a temporary task file','fixed-temporary')
        frozen=json.loads(con.execute('SELECT context_json FROM managed_jobs WHERE id=?',(job['id'],)).fetchone()[0])
        task_row=c.task_row(con,task)
    temporary=next(t for t in frozen['capabilities']['execution_targets'] if t['kind']=='task_temporary')
    assert temporary['path']==str(Path(task_row['workspace']).parent/'tmp')
    assert temporary['granted'] and temporary['operations']==['read','write','unlink']
    assert frozen['base_snapshot']['payload']['allowed_write_dirs']==['.']
    assert all(x['kind']!='task_temporary' for x in frozen['capabilities']['expansion_targets'])


def test_compaction_is_authenticated_control_plane_maintenance(bound):
    with TestClient(app) as client:
        assert client.post('/api/managed/tasks/'+bound[0]+'/compact',json={}).status_code==401


def test_failed_native_admission_marks_replacement_failed_and_stops_domain(bound,monkeypatch):
    task,state,_=bound;state={**state,'phase':'generating','gate':'applying'};calls=[]
    with db.connect() as con:c.save(con,task,state)
    def broker(request,**kw):
        calls.append(request['action'])
        if request['action']=='launch':return {'domain_id':77}
        if request['action']=='native-session':raise RuntimeError('Native service unavailable')
        if request['action']=='stop':return {'stopped':True}
        raise AssertionError(request)
    monkeypatch.setattr(c,'broker',broker)
    with pytest.raises(RuntimeError,match='Native service unavailable'):c.install(task,state,['.'],False,initial=True)
    with db.connect() as con:
        failed=c.load(con,task);row=c.task_row(con,task)
    assert failed['phase']=='failed' and failed['gate']=='failed'
    assert row['active_pid'] is None and row['watch_pid'] is None
    assert calls[-1]=='stop'


def test_recovery_retains_unapproved_expansion_intent_without_grant(bound,monkeypatch):
    task,state,_=bound
    state={**state,'phase':'recovering','pending_expansion':{'hash':'old-candidate','proposal':proposal(decision='expand',allow_output=True,protected_paths=[])}}
    with db.connect() as con:c.save(con,task,state)
    replies={'launch':{'domain_id':51,'runner_pid':99,'watch_pid':98,'web_url':'http://127.0.0.1:18020/'},'native-session':{'sessionId':state['session_id']},'managed-verify':{'passed':True,'probe':{'pid':100}},'status':{'status':'running','domain_id':51}}
    monkeypatch.setattr(c,'broker',lambda request,**kw:replies[request['action']])
    installed=c.install(task,state,['.'],False,initial=True)
    assert installed['pending_expansion'] is None and not installed['allow_output']
    assert installed['pending_expansion_intent']['proposed_snapshot']['allow_output']
    assert installed['pending_expansion_intent']['prior_hash']=='old-candidate'



def test_compiled_record_preserves_exact_dsl_and_annotation_has_no_authority(bound):
    statement={'statement':'Task needs an output file','context_required':True,'context_reason':'Resolve the output path from task context','policy_type':'per_event','evidence_ids':['5']}
    result=c.validate_candidate(bound[2],proposal(identified_statements=[statement]))
    assert result['compiled_dsl_hash']==__import__('hashlib').sha256(result['compiled_dsl'].encode()).hexdigest()
    assert result['identified_statements'][0]['statement']==statement['statement']
    assert not result['allow_output']
    with pytest.raises(ValueError,match='不能修改权限'):c.validate_candidate(bound[2],proposal(allow_output=True,identified_statements=[statement]))
    with pytest.raises(ValueError,match='cite candidate evidence'):c.validate_candidate(bound[2],proposal(identified_statements=[{**statement,'evidence_ids':['invented']}]))


def test_structured_runtime_compiled_candidate_is_not_loaded_without_receipt(bound):
    from agentscope_app.managed.records import runtime_record
    task,state,job=bound
    ctx=json.loads(job['context_json']);ctx.update(path_mapping={'workspace':'/tmp/work'},sources=[{'evidence_id':'5','content':{'actor':'native_user','text':'Allow task output','turn':3}}])
    candidate={'decision':'expand','allowed_write_dirs':['.'],'allow_output':True,'protected_paths':[],'evidence_ids':['5'],'compile':{'ok':True},'explanation':'Output requested','hash':'candidate','compiled_dsl':'rule candidate:\n  block write file "/private" if AGENT','compiled_dsl_hash':__import__('hashlib').sha256(b'rule candidate:\n  block write file "/private" if AGENT').hexdigest()}
    row={**job,'context_json':json.dumps(ctx),'proposal_json':json.dumps(candidate),'created_at':db.now()}
    with db.connect() as con:
        record=runtime_record(con,c.task_row(con,task),{**state,'pending_expansion':{'job_id':job['id']}},row)
        assert record['status']=='pending_confirmation' and not record['compilation']['dsl']
        assert not record['loading']['loaded']  # No statement mapping must not disclose the entire package.
        c.event(con,task,'request_resolved',job['id'],{'version':2,'confirmation':'confirmed'})
        record=runtime_record(con,c.task_row(con,task),{**state,'version':2,'allow_output':True},row)
        assert record['status']=='active' and record['loading']['loaded'] and record['loading']['version']==2
        corrupted={**row,'proposal_json':json.dumps({**candidate,'compiled_dsl':'tampered'})}
        with pytest.raises(ValueError,match='hash mismatch'):runtime_record(con,c.task_row(con,task),state,corrupted)


def test_workspace_resolver_matches_declared_session_and_never_guesses(bound,monkeypatch,seed_task):
    from agentscope_app.managed.records import binding
    task,state,_=bound
    monkeypatch.setattr(c,'broker',lambda *_:{'status':'running','domain_id':7,'domain_verified':True})
    assert binding(task_id=task,session_id='session-native')['binding']['task_id']==task
    assert binding(task_id=task,workspace='/tmp/work')['binding']['process_verified']
    other=uuid.uuid4().hex[:16];seed_task(other)
    with db.connect() as con:c.save(con,other,{**state,'session_id':'session-other'})
    assert binding(workspace='/tmp/work')['status']=='ambiguous'
    assert binding(workspace='/other/work')['status']=='unmatched'
    assert binding(session_id='foreign')['status']=='unmatched'
    with db.connect() as con:c.save(con,task,{**state,'phase':'ended'})
    assert task not in {b['task_id'] for b in binding()['candidates']}  # history is not an active auto selection
    assert binding(task_id=task)['status']=='matched'  # explicit historical selection remains readable


def test_execution_audit_separates_tools_from_os_and_marks_probe_source(bound):
    from agentscope_app.managed.records import execution_audit
    task,state,_=bound
    with db.connect() as con:
        c.event(con,task,'kernel','denied',{'event':{'op':'write','target':'/tmp/work/tests/test.py','pid':111},'version':1})
        c.event(con,task,'tool_result','success',{'call_id':'success','name':'bash','succeeded':True})
        c.event(con,task,'operation_verified','probe',{'probe':{'operation':'read','target':'/tmp/work/allowed.py','pid':112},'classification':'correct_allow'})
    os=execution_audit(task,'os')['records'];tools=execution_audit(task,'tools')['records']
    assert {x['kind'] for x in os}=={'kernel','operation_verified'}
    assert next(x for x in os if x['kind']=='operation_verified')['source']=='independent_probe'
    assert tools[0]['result']=='success' and tools[0]['source']=='native_tool'
    assert all(x['kind']!='tool_result' for x in os)
    with db.connect() as con:
        c.event(con,task,'tool_start','probe-call',{'call_id':'probe-call','name':'read','verification_probe':True})
        c.event(con,task,'tool_result','probe-result',{'call_id':'probe-call','name':'read','succeeded':True})
    assert execution_audit(task,'tools')['records'][0]['source']=='independent_probe'


def test_structured_record_endpoints_require_admin_auth(bound):
    with TestClient(app) as client:
        for path in ['/api/managed/workspace-binding','/api/managed/tasks/'+bound[0]+'/strategy-records','/api/managed/tasks/'+bound[0]+'/execution-audit','/api/managed/tasks/'+bound[0]+'/workbench']:
            assert client.get(path).status_code==401


def test_record_details_cannot_read_foreign_job_or_native_stream(bound):
    from agentscope_app.managed.records import detail,workbench
    with pytest.raises(ValueError,match='不属于当前任务'):detail(bound[0],'runtime:foreign')
    assert not {'events','runtime_observations','baseline_extra','jobs'}&workbench(bound[0])['state'].keys()


def test_protection_record_stays_active_after_unrelated_output_expansion(bound):
    from agentscope_app.managed.records import runtime_record
    task,state,job=bound
    proposal={'decision':'restrict','allowed_write_dirs':['.'],'allow_output':False,'protected_paths':['locked.txt'],'evidence_ids':['5'],'compile':{'ok':True}}
    row={**job,'proposal_json':json.dumps(proposal),'created_at':db.now()}
    with db.connect() as con:
        c.event(con,task,'request_resolved',job['id'],{'version':2})
        record=runtime_record(con,c.task_row(con,task),{**state,'version':3,'allow_output':True,'runtime_protected':['locked.txt']},row)
    assert record['status']=='active' and record['loading']['version']==2



def test_statement_dsl_contains_only_matching_compiler_clauses():
    from agentscope_app.managed.records import statement_compilation
    rules=[{'name':'files','source_start_line':1,'clause_start_line':i,'clause_text':f'  block write file "{path}" if AGENT','clause_op':'write','target_pattern':path,'reason':'protect registered targets','source_text':'rule files: ALL_TARGETS'} for i,path in enumerate(['/work/one.txt','/work/two.txt'],2)]
    rules.append({'name':'baseline','source_start_line':10,'clause_start_line':11,'clause_text':'  block write file "/private/**" if AGENT','target_pattern':'/private/**','source_text':'UNRELATED_BASELINE'})
    result=statement_compilation({'ok':True,'rules':rules},['/work/one.txt'],'per_event','no_change')
    assert '/work/one.txt' in result['dsl'] and '/work/two.txt' not in result['dsl']
    assert 'UNRELATED_BASELINE' not in result['dsl'] and 'ALL_TARGETS' not in result['dsl']
    assert result['reused'] and result['rule_count']==1
    assert statement_compilation({'ok':True,'rules':rules},['/work/one.txt'],'semantic_only','no_change')['dsl']==''
    assert statement_compilation({'ok':True,'rules':rules},['/unregistered.txt'],'per_event','no_change')['status']=='not_recorded'


def test_one_runtime_record_per_statement_with_scoped_evidence(bound):
    from agentscope_app.managed.records import runtime_statement_records
    task,state,job=bound
    statements=[{'statement':'Preserve locked.txt','policy_type':'per_event','context_required':True,'context_reason':'Resolve the registered file','evidence_ids':['5','project:locked.txt']},{'statement':'Only read and report','policy_type':'semantic_only','context_required':False,'context_reason':'This is procedural guidance','evidence_ids':['5']}]
    ctx=json.loads(job['context_json']);ctx['project_sources']=[{'id':'locked.txt','path':'/tmp/work/locked.txt','hash':'file-hash'}]
    compiler={'ok':True,'rules':[{'name':'runtime-files','clause_text':'  block write file "/tmp/work/locked.txt" if AGENT','target_pattern':'/tmp/work/locked.txt','clause_op':'write'}]}
    candidate=proposal(identified_statements=statements,compile=compiler)
    row={**job,'context_json':json.dumps(ctx),'proposal_json':json.dumps(candidate),'created_at':db.now()}
    with db.connect() as con:items=runtime_statement_records(con,c.task_row(con,task),state,row)
    assert len(items)==2 and len({x['id'] for x in items})==2
    assert items[0]['statement']=='Preserve locked.txt' and '/tmp/work/locked.txt' in items[0]['compilation']['dsl']
    assert items[1]['compilation']['dsl']=='' and items[1]['policy_type']=='semantic_only'
    assert not items[1]['context_required'] and all(e['role']!='project' for e in items[1]['evidence'])
    row['proposal_json']=json.dumps({**candidate,'decision':'restrict','protected_paths':['locked.txt']})
    with db.connect() as con:
        c.event(con,task,'request_resolved',job['id'],{'version':2})
        applied=runtime_statement_records(con,c.task_row(con,task),{**state,'version':2,'runtime_protected':['locked.txt']},row)
    assert applied[0]['loading']['loaded'] and not applied[1]['loading']['loaded']
    assert applied[1]['status']=='guidance' and applied[1]['effect']=='guidance'
    assert applied[1]['delta'] is None and applied[0]['delta']=={'added_protection':['locked.txt']}


def test_statement_pagination_does_not_drop_or_duplicate_sibling_records(bound):
    from agentscope_app.managed.records import records,detail
    task,state,job=bound
    statements=[{'statement':f'Guidance sentence {i}','policy_type':'semantic_only','context_required':False,'context_reason':'No project context required','evidence_ids':['5']} for i in range(20)]
    with db.connect() as con:
        con.execute('INSERT INTO managed_jobs(id,task_id,request_key,revision,policy_hash,status,context_json,proposal_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(job['id'],task,'statement-pages',1,'fixed','completed',job['context_json'],json.dumps(proposal(identified_statements=statements,compile={'ok':True})),db.now()))
    first=records(task,'runtime');second=records(task,'runtime',first['next_cursor'])
    assert len(first['records'])==12 and len(second['records'])==8
    assert len({r['id'] for r in first['records']+second['records']})==20 and second['next_cursor'] is None
    assert detail(task,second['records'][0]['id'])['statement']=='Guidance sentence 12'


def test_unidentified_assessment_is_not_a_policy_sentence(bound):
    from agentscope_app.managed.records import runtime_statement_records
    task,state,job=bound;row={**job,'proposal_json':json.dumps(proposal(compile={'ok':True})),'created_at':db.now()}
    with db.connect() as con:
        assert runtime_statement_records(con,c.task_row(con,task),state,row)==[]
        assessment=runtime_statement_records(con,c.task_row(con,task),state,row,True)[0]
        assert assessment['compilation']['dsl']==''

"""Managed runtime generation is authenticated, additive and restriction-only."""
import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agentscope_app import db
from agentscope_app.main import app
from agentscope_app.managed import controller as c
from agentscope_app.managed.api import OperationProbe,verify_operation


@pytest.fixture
def bound(seed_task,monkeypatch):
    db.init_db();task=uuid.uuid4().hex[:16];seed_task(task)
    state={'phase':'running','gate':'open','revision':1,'version':1,'policy_hash':'fixed','baseline_hash':'safety',
           'baseline_extra':'rule baseline:\n  block write file "/tmp/work/tests/**" if AGENT\n  because "tests immutable"',
           'protected':['/tmp/work/tests/test.py'],'runtime_protected':[],'allowed_write_dirs':['.'],'allow_output':False,
           'binding':{'domain_id':7,'runner_pid':70},'binding_history':[{'domain_id':7,'version':1}],
           'session_id':'session-native','turn':2,'normalization_mode':'legacy'}
    with db.connect() as con:c.save(con,task,state)
    context={'schema':'ManagedRuntimeContext/2','request_evidence_id':'5',
             'sources':[{'evidence_id':'5','source':'request','content':{'actor':'native_user','text':'保护 src/locked.py，不得修改','revision':1}}],
             'base_snapshot':{'payload':{'allowed_write_dirs':['.'],'allow_output':False,'protected_paths':[]}},
             'capabilities':{'registered_directories':['.','src','tests'],'registered_files':['src/locked.py','src/other.py'],
                             'authorized_protection_targets':{'src/locked.py':[{'request_id':'5','quote':'保护 src/locked.py，不得修改'}]}},
             'unassessed_request_ids':['5'],'revision':1,'policy_hash':'fixed','path_mapping':{'workspace':'/tmp/work'},
             'project_sources':[{'id':'src/locked.py'}]}
    job={'id':uuid.uuid4().hex,'task_id':task,'revision':1,'policy_hash':'fixed','context_json':json.dumps(context)}
    with db.connect() as con:c.event(con,task,'pi_source',job['id']+':src/locked.py',{'hash':'read'})
    import agentscope_app.main as main
    monkeypatch.setattr(main,'compile_policy',lambda *_:('compiled',{'ok':True,'rules':[]},None))
    return task,state,job


def proposal(**changes):
    return {'decision':'no_change','add_protected_paths':[],'evidence_ids':['5'],
            'explanation':'The authenticated request adds no OS restriction.',
            'unresolved_requests':[],'identified_statements':[],**changes}


def test_managed_candidate_rejects_replacement_snapshot_fields(bound):
    with pytest.raises(ValidationError):
        c.validate_candidate(bound[2],proposal(allowed_write_dirs=['src'],allow_output=True,protected_paths=[]))


def test_runtime_expansion_is_not_in_managed_schema(bound):
    with pytest.raises(ValidationError):c.validate_candidate(bound[2],proposal(decision='expand'))


def test_request_evidence_is_required(bound):
    with pytest.raises(ValueError,match='本轮证据'):c.validate_candidate(bound[2],proposal(evidence_ids=['project:src/locked.py']))


def test_stale_context_cannot_generate(bound):
    with pytest.raises(ValueError,match='stale'):c.validate_candidate({**bound[2],'revision':0},proposal())


def test_restriction_is_new_registered_authorized_target_only(bound):
    result=c.validate_candidate(bound[2],proposal(decision='restrict',add_protected_paths=['src/locked.py'],evidence_ids=['5','project:src/locked.py']))
    assert result['protected_paths']==['src/locked.py']
    assert result['allowed_write_dirs']==['.'] and result['allow_output'] is False
    assert '/tmp/work/src/locked.py' in result['compiled_delta']
    assert '/tmp/work/src/other.py' not in result['compiled_delta']
    assert ' allow ' not in result['compiled_delta']


def test_directory_restriction_effect_probe_expands_existing_descendants(tmp_path):
    (tmp_path/'src'/'nested').mkdir(parents=True)
    first=tmp_path/'src'/'one.py';second=tmp_path/'src'/'nested'/'two.py';outside=tmp_path/'other.py'
    first.write_text('one');second.write_text('two');outside.write_text('other')
    assert c.protected_file_paths(tmp_path,['src/**'])==sorted([str(first),str(second)])


def test_unknown_or_unauthorized_target_is_rejected(bound):
    with pytest.raises(ValueError,match='未登记'):c.validate_candidate(bound[2],proposal(decision='restrict',add_protected_paths=['../../etc']))
    ctx=json.loads(bound[2]['context_json']);ctx['capabilities']['authorized_protection_targets']={}
    with pytest.raises(ValueError,match='no explicit authenticated'):
        c.validate_candidate({**bound[2],'context_json':json.dumps(ctx)},proposal(decision='restrict',add_protected_paths=['src/locked.py'],evidence_ids=['5','project:src/locked.py']))


def test_project_read_is_required_but_never_authorizes_target(bound):
    task,_,job=bound
    with db.connect() as con:con.execute("DELETE FROM managed_events WHERE task_id=? AND kind='pi_source'",(task,))
    with pytest.raises(ValueError,match='read_runtime_source'):
        c.validate_candidate(job,proposal(decision='restrict',add_protected_paths=['src/locked.py'],evidence_ids=['5','project:src/locked.py']))


def test_existing_rule_cannot_be_readded_or_removed(bound):
    ctx=json.loads(bound[2]['context_json']);ctx['base_snapshot']['payload']['protected_paths']=['src/locked.py']
    job={**bound[2],'context_json':json.dumps(ctx)}
    with pytest.raises(ValueError,match='must be new'):
        c.validate_candidate(job,proposal(decision='restrict',add_protected_paths=['src/locked.py'],evidence_ids=['5','project:src/locked.py']))
    unchanged=c.validate_candidate(job,proposal())
    assert unchanged['protected_paths']==['src/locked.py']


def test_no_change_and_guidance_cannot_smuggle_additions(bound):
    for decision in ('no_change','guidance_only'):
        with pytest.raises(ValueError,match='cannot append'):
            c.validate_candidate(bound[2],proposal(decision=decision,add_protected_paths=['src/locked.py']))


def test_ambiguous_required_restriction_pauses_without_policy_change(bound):
    result=c.validate_candidate(bound[2],proposal(unresolved_requests=['5']))
    assert result['decision']=='no_change' and result['protected_paths']==[]
    with pytest.raises(ValueError,match='cannot accompany'):
        c.validate_candidate(bound[2],proposal(decision='restrict',add_protected_paths=['src/locked.py'],unresolved_requests=['5'],evidence_ids=['5','project:src/locked.py']))


def test_only_authenticated_user_actor_can_enqueue_runtime_generation(bound,monkeypatch):
    task,_,_=bound
    monkeypatch.setattr(c,'context',lambda *_:{'declared_constraints':[]})
    for actor in ('kernel','native_context','DSH','recovery'):
        with db.connect() as con:
            with pytest.raises(ValueError,match='已认证用户'):c.enqueue(con,task,c.load(con,task),'ignored','blocked-'+actor,actor=actor)
    with db.connect() as con:
        queued=c.enqueue(con,task,c.load(con,task),'ordinary user prompt','accepted-user',actor='native_user')
        frozen=json.loads(con.execute('SELECT context_json FROM managed_jobs WHERE id=?',(queued['id'],)).fetchone()[0])
    assert {item['source'] for item in frozen['sources']}=={'request'}
    assert [item['actor'] for item in frozen['public_task_context']]==['native_user']
    assert 'native_execution_context' not in frozen
    assert 'declared_constraints' not in frozen['baseline']
    assert frozen['capabilities']['executor_sandbox']['runtime_policy_trigger']=='authenticated_user_request_only'


def test_duplicate_authenticated_request_remains_idempotent_while_delta_applies(bound):
    task,state,_=bound
    with db.connect() as con:
        existing=uuid.uuid4().hex
        con.execute('INSERT INTO managed_jobs(id,task_id,request_key,revision,policy_hash,context_json,created_at) VALUES(?,?,?,?,?,?,?)',(existing,task,'same-request',1,'fixed','{}',db.now()))
        applying={**state,'gate':'applying'};c.save(con,task,applying)
        assert c.enqueue(con,task,applying,'same message','same-request')=={'id':existing}
        with pytest.raises(ValueError,match='原子追加'):c.enqueue(con,task,applying,'new message','new-request')


def test_resolved_user_messages_are_not_reinjected_into_fresh_runtime_context(bound,monkeypatch):
    task,_,_=bound
    monkeypatch.setattr(c,'context',lambda *_:{'declared_constraints':[]})
    with db.connect() as con:
        state=c.load(con,task)
        c.event(con,task,'request','old-user',{'text':'old resolved requirement','kind':'message','actor':'native_user','session_id':state['session_id'],'turn':1,'revision':state['revision']})
        old_id=str(con.execute("SELECT id FROM managed_events WHERE task_id=? AND event_key='old-user'",(task,)).fetchone()[0])
        c.event(con,task,'request_resolved','old-job',{'evidence_ids':[old_id],'decision':'no_change','version':state['version']})
        queued=c.enqueue(con,task,state,'new current request','new-user',actor='native_user')
        frozen=json.loads(con.execute('SELECT context_json FROM managed_jobs WHERE id=?',(queued['id'],)).fetchone()[0])
    assert [row['text'] for row in frozen['public_task_context']]==['new current request']
    assert [row['content']['text'] for row in frozen['sources']]==['new current request']


def test_runtime_observation_event_is_not_registered(bound):
    with pytest.raises(ValueError,match='未登记'):
        c.ingest(bound[0],{'kind':'runtime_observation','session_id':'session-native','event_key':'context','category':'memory','content':'injected'})


def test_foreign_session_cannot_append(bound):
    with pytest.raises(ValueError,match='其他会话'):
        c.ingest(bound[0],{'kind':'native_event','session_id':'foreign','event_key':'f','type':'turn/start','data':{'turn':1}})


def test_generator_and_administrator_apis_remain_authenticated(bound):
    with TestClient(app) as client:
        assert client.post('/api/generator/tasks/'+bound[0]+'/managed-jobs/fake/tools/get_runtime_context',json={'args':{}}).status_code==401
        assert client.post('/api/managed/tasks/'+bound[0]+'/close',json={}).status_code==401


def test_dsh_permission_request_has_no_policy_generation_transport():
    source=(Path(__file__).resolve().parents[2]/'integrations/dsh-managed-web/lib/index.js').read_text()
    hook=source[source.index("ctx.on('approval/request'"):source.index("ctx.on('session/event'")]
    assert "api('change'" not in hook and "return 'rejected'" in hook


def test_recovery_resumes_without_creating_runtime_job(bound,monkeypatch):
    task,state,_=bound;calls=[]
    with db.connect() as con:
        c.save(con,task,{**state,'phase':'recovering'})
        c.event(con,task,'request','real-user',{'actor':'native_user','text':'latest request','revision':1})
    def install(*_a,**_k):
        with db.connect() as con:
            current=c.load(con,task);current.update(phase='running',gate='open',session_id='recovered');c.save(con,task,current)
        return current
    monkeypatch.setattr(c,'install',install)
    monkeypatch.setattr(c,'broker',lambda request,**_:(calls.append(request) or {'persisted':True}))
    c.recover(task)
    with db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM managed_jobs WHERE task_id=?',(task,)).fetchone()[0]==0
        current=c.load(con,task)
    assert current['gate']=='open' and calls[-1]['operation']=='resume'
    assert any(item['kind']=='recovery_resumed' for item in c.audit_history(task)['events'])


def test_probe_denials_never_become_native_tool_feedback(bound):
    task,_,_=bound
    with db.connect() as con:
        c.event(con,task,'tool_start','call',{'call_id':'call','serialized':True,'domain_id':7})
        c.event(con,task,'kernel','probe',{'verification_probe':True,'event':{'pid':99,'process_domain_id':7}})
    assert c.tool_feedback(task,'call')=={'events':[]}


def test_false_block_probe_is_audited_but_never_triggers_policy_generation(bound,monkeypatch):
    task,_,_=bound
    def broker(request,**_):
        if request['action']=='native-session':return {'status':'idle'}
        if request['action']=='managed-operation':
            return {'probe':{'blocked':True,'pid':99,'success':False},'kernel_events':[{'op':'write'}],'effect_verified':False}
        raise AssertionError(request['action'])
    monkeypatch.setattr(c,'broker',broker)
    result=verify_operation(task,OperationProbe(target='/tmp/work/src/locked.py',operation='write',expected='allow'))
    assert result['classification']=='false_block'
    with db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM managed_jobs WHERE task_id=?',(task,)).fetchone()[0]==0
        assert con.execute("SELECT COUNT(*) FROM managed_events WHERE task_id=? AND kind='operation_verified'",(task,)).fetchone()[0]==1


def test_install_persists_verified_binding(bound,monkeypatch):
    task,state,_=bound;state={**state,'version':0,'session_id':None,'phase':'generating','gate':'closed'}
    with db.connect() as con:c.save(con,task,state)
    def broker(request,**_):
        return {'launch':{'domain_id':51,'runner_pid':99,'watch_pid':98,'web_url':'http://127.0.0.1:18020/'},
                'native-session':{'sessionId':'durable-native-session'},'managed-verify':{'passed':True,'probe':{'pid':100}},
                'status':{'status':'running','domain_id':51}}[request['action']]
    monkeypatch.setattr(c,'broker',broker)
    result=c.install(task,state,['.'],False,initial=True)
    with db.connect() as con:stored=c.load(con,task);row=c.task_row(con,task)
    assert result['session_id']==stored['session_id']=='durable-native-session'
    assert row['active_version']==stored['version']==1 and stored['active_bundle']['dsl']


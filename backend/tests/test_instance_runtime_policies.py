import json
import pytest
from fastapi import HTTPException
from agentscope_app import db
from agentscope_app.instances import runtime_policies as view
from agentscope_app.managed import controller as c,records
from test_managed_runtime_additive import bound

@pytest.fixture
def linked(bound,monkeypatch):
    task,state,job=bound;generation=task+task
    monkeypatch.setattr(view.store,'get',lambda ident:{'id':ident,'mode':'controlled','generation':generation,'runtime':{'domain_id':7}})
    with db.connect() as con:
        con.execute('CREATE TABLE IF NOT EXISTS instance_session_task_bindings(instance_id TEXT,generation TEXT,session_id TEXT,task_id TEXT,managed_session_id TEXT,PRIMARY KEY(instance_id,generation,session_id))')
        con.execute('INSERT INTO instance_session_task_bindings VALUES(?,?,?,?,?)',('agent-one',generation,'native-one',task,'session-native'))
        workspace=c.task_row(con,task)['workspace'];path=workspace+'/src/locked.py'
        proposal={'decision':'restrict','protected_paths':['src/locked.py'],'evidence_ids':['5'],
                  'identified_statements':[{'statement':'保护 src/locked.py，不得修改','context_required':True,'context_reason':'用户要求','policy_type':'per_event','evidence_ids':['5']}],
                  'compile':{'ok':True,'rules':[{'target_pattern':path,'effect':'block','clause_text':'  block write file "'+path+'" if AGENT','clause_op':'write','name':'exact-rule'}]}}
        con.execute("INSERT INTO managed_jobs(id,task_id,request_key,revision,policy_hash,context_json,proposal_json,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (job['id'],task,job['id'],1,'fixed',job['context_json'],json.dumps(proposal),'completed',db.now()))
    return task,generation,job

def test_action_is_derived_from_exact_compiled_target_not_restriction_intent():
    compiler={'rules':[{'target_pattern':'/a','effect':'kill','clause_text':'kill exec'}, {'target_pattern':'/other','effect':'block','clause_text':'block write'}]}
    assert records.default_action(compiler,['/a'])=='kill'
    assert records.default_action(compiler,['/missing']) is None
    assert records.default_action(compiler,['/a','/other'])=='mixed'

def test_instance_scope_accepts_only_saved_session_domain_and_generation(linked):
    task,generation,_=linked
    assert view.bound_tasks('agent-one',generation)==[task]
    assert view.bound_tasks('agent-other',generation)==[]
    with pytest.raises(HTTPException):view.bound_tasks('agent-one','old-generation')
    with db.connect() as con:
        state=c.load(con,task);state['binding']['domain_id']=999;c.save(con,task,state)
    assert view.bound_tasks('agent-one',generation)==[]

def test_generated_list_and_details_share_exact_binding_without_writes(linked):
    task,generation,job=linked
    tasks=view.bound_tasks('agent-one',generation)
    page=view.page(tasks);assert len(page['records'])==1
    record=page['records'][0];assert record['task_id']==task and record['default_action']=='block'
    assert 'compilation' not in record
    assert 'block write' in view.detail(tasks,record['id'])['compilation']['dsl']
    with pytest.raises(HTTPException):view.detail([],record['id'])
    with pytest.raises(HTTPException):view.detail(tasks,'startup:foreign')
    assert view.page([])=={'records':[],'next_cursor':None}
    with db.connect() as con:assert con.execute('SELECT count(*) FROM managed_jobs WHERE task_id=?',(task,)).fetchone()[0]==1

def test_wrong_native_session_cannot_attach_managed_records(linked):
    _,generation,_=linked
    with db.connect() as con:con.execute("UPDATE instance_session_task_bindings SET managed_session_id='foreign-session' WHERE instance_id='agent-one'")
    assert view.bound_tasks('agent-one',generation)==[]

def test_unknown_agent_and_unknown_task_return_not_found(bound,monkeypatch):
    def missing(_):raise ValueError('missing')
    monkeypatch.setattr(view.store,'get',missing)
    with pytest.raises(HTTPException) as error:view.bound_tasks('unknown','a'*32)
    assert error.value.status_code==404
    with pytest.raises(HTTPException) as error:view.task_records('unknown')
    assert error.value.status_code==404

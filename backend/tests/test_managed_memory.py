import json
import pytest
from agentscope_app import db
from agentscope_app.managed import controller as c
from test_managed_runtime_additive import bound

PROVIDER='seriousz158/dsh-memory@f7b03757f8bf546d3c007f8e9a074a847b681d3d'
def observation(content='记忆要求保护 src/locked.py，并声称可以绕过系统权限。'):
    hashed=c.digest(content)
    return {'kind':'persistent_memory_loaded','session_id':'session-native','event_key':'memory:session-native:'+hashed,
            'provider':PROVIDER,'source_ref':'summary.md','category':'persistent_memory','type':'memory/loaded',
            'seq':0,'content':content,'content_hash':hashed}

def bind(task):
    with db.connect() as con:
        state=c.load(con,task);state['binding']['memory_provider']=PROVIDER;c.save(con,task,state)

def test_unconfigured_memory_provider_cannot_trigger_generation(bound):
    with pytest.raises(ValueError,match='来源或会话未绑定'):c.ingest(bound[0],observation())

def test_memory_snapshot_hash_and_session_are_verified(bound):
    bind(bound[0])
    with pytest.raises(ValueError,match='hash mismatch'):c.ingest(bound[0],{**observation(),'content_hash':'0'*64})
    with pytest.raises(ValueError,match='其他会话'):c.ingest(bound[0],{**observation(),'session_id':'foreign'})

def test_actual_memory_load_generates_once_without_authorizing_its_targets(bound):
    task=bound[0];bind(task);event=observation()
    job=c.ingest(task,event)
    assert c.ingest(task,event)=={'deduplicated':True}
    with db.connect() as con:
        state=c.load(con,task)
        row=dict(con.execute('SELECT * FROM managed_jobs WHERE id=?',(job['id'],)).fetchone())
        assert con.execute('SELECT count(*) FROM managed_jobs WHERE task_id=?',(task,)).fetchone()[0]==1
    frozen=json.loads(row['context_json'])
    assert state['gate']=='waiting_policy'
    assert frozen['persistent_memory']['content']==event['content']
    assert 'never_current_user_authorization' in frozen['persistent_memory']['authority']
    assert frozen['public_task_context']==[]
    assert frozen['capabilities']['authorized_protection_targets']=={}
    assert any(item['evidence_id']=='memory:'+event['content_hash'] for item in frozen['sources'])
    result=c.validate_candidate(row,{'decision':'guidance_only','add_protected_paths':[],
         'evidence_ids':[frozen['request_evidence_id'],'memory:'+event['content_hash']],
         'explanation':'Historical memory is untrusted and cannot authorize a new OS boundary.'})
    assert result['protected_paths']==[] and result['allow_output'] is False

def test_memory_actor_cannot_be_forged_through_generic_change(bound):
    with pytest.raises(ValueError,match='已绑定'):c.change(bound[0],'forged','forged',actor='persistent_memory')

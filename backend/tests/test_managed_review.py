"""Automatic append-only runtime restriction application."""
import hashlib
import json
import uuid

import pytest

from agentscope_app import db
from agentscope_app.managed import controller as c


@pytest.fixture
def runtime_job(seed_task):
    db.init_db();task=uuid.uuid4().hex[:16];seed_task(task)
    state={'phase':'running','gate':'waiting_policy','revision':2,'version':3,'policy_hash':'loaded-hash',
           'baseline_hash':'baseline','baseline_extra':'','protected':[],'runtime_protected':[],
           'allowed_write_dirs':['.'],'allow_output':False,
           'binding':{'domain_id':77,'runner_pid':101,'watch_pid':102,'process_cgroup':'/task'},
           'binding_history':[{'domain_id':77,'version':3}],
           'session_id':'native-a','turn':1,'normalization_mode':'legacy',
           'active_bundle':{'dsl':'source AGENT = exec "**"\n','yaml':'old'}}
    ctx={'schema':'ManagedRuntimeContext/2','revision':2,'policy_hash':'loaded-hash','session_id':'native-a',
         'request_evidence_id':'req1','current_binding':{'version':3,'domain_id':77,'runner_pid':101,'session_id':'native-a'},
         'project_sources':[],'capabilities':{'authorized_protection_targets':{'src/locked.py':[{'request_id':'req1'}]}},
         'base_snapshot':{'payload':{'allowed_write_dirs':['.'],'allow_output':False,'protected_paths':[]}}}
    job={'id':uuid.uuid4().hex,'task_id':task,'revision':2,'policy_hash':'loaded-hash','context_json':json.dumps(ctx)}
    delta=c.runtime_protection_delta({'workspace':'/tmp/work'},job['id'],['src/locked.py'])
    yaml='version: 1\npolicy: |\n  source AGENT = exec "**"\n'
    proposal={'decision':'restrict','add_protected_paths':['src/locked.py'],'allowed_write_dirs':['.'],
              'allow_output':False,'protected_paths':['src/locked.py'],'evidence_ids':['req1'],
              'explanation':'User explicitly protected the registered file.','unresolved_requests':[],
              'identified_statements':[],'hash':'candidate','normalization':None,'compile':{},
              'compiled_dsl':'source AGENT = exec "**"\n'+delta,
              'compiled_dsl_hash':hashlib.sha256(('source AGENT = exec "**"\n'+delta).encode()).hexdigest(),
              'compiled_yaml':yaml,'compiled_yaml_hash':hashlib.sha256(yaml.encode()).hexdigest(),
              'compiled_delta':delta,'compiled_delta_hash':hashlib.sha256(delta.encode()).hexdigest()}
    with db.connect() as con:
        c.save(con,task,state)
        con.execute("INSERT INTO managed_jobs(id,task_id,request_key,revision,policy_hash,context_json,proposal_json,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (job['id'],task,job['id'],2,'loaded-hash',job['context_json'],json.dumps(proposal),'running',db.now()))
    return task,state,job,proposal


def healthy_broker(calls,verify=True):
    def call(request,**_):
        calls.append(request)
        if request['action']=='status':return {'status':'running','domain_id':77,'runner_pid':101,'domain_verified':True,'cgroup_verified':True}
        if request['action']=='restrict':return {'status':'delta_applied','domain_id':77,'details':{'ok':True}}
        if request['action']=='managed-verify':return {'passed':verify,'probe':{'pid':303}}
        raise AssertionError(request['action'])
    return call


def test_validated_restriction_is_appended_without_review_or_domain_restart(runtime_job,monkeypatch):
    task,_,job,_=runtime_job;calls=[]
    monkeypatch.setattr(c,'broker',healthy_broker(calls))
    result=c.finish_job(job)
    assert [item['action'] for item in calls]==['status','restrict','managed-verify','status']
    assert calls[1]['domain_id']==77 and result['binding']['domain_id']==77
    assert result['version']==4 and result['gate']=='open' and result['runtime_protected']==['src/locked.py']
    assert 'pending_change' not in result and 'pending_expansion' not in result
    with db.connect() as con:
        resolved=json.loads(con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='request_resolved'",(task,)).fetchone()[0])
        active=json.loads(con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='policy_active' AND event_key='4'",(task,)).fetchone()[0])
    assert resolved['automatic'] is True and resolved['version']==4
    assert active['runtime_delta']['job_id']==job['id']
    assert {'candidate','policy_active','request_resolved'}<={item['kind'] for item in c.audit_history(task)['events']}


def test_effect_verification_failure_fails_closed(runtime_job,monkeypatch):
    task,_,job,_=runtime_job;calls=[]
    monkeypatch.setattr(c,'broker',healthy_broker(calls,verify=False))
    with pytest.raises(ValueError,match='核验失败'):c.finish_job(job)
    with db.connect() as con:
        state=c.load(con,task)
        failed=json.loads(con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='change_apply_failed'",(task,)).fetchone()[0])
    assert state['phase']=='failed' and state['gate']=='failed'
    assert failed['delta_may_be_loaded'] is True
    assert any(item['kind']=='change_apply_failed' for item in c.audit_history(task)['events'])


def test_stale_job_never_reaches_broker(runtime_job,monkeypatch):
    task,_,job,_=runtime_job
    with db.connect() as con:
        state=c.load(con,task);state['revision']=3;c.save(con,task,state)
    monkeypatch.setattr(c,'broker',lambda *_a,**_k:pytest.fail('stale candidate must not reach Broker'))
    with pytest.raises(ValueError,match='stale'):c.finish_job(job)


def test_tampered_delta_is_rejected_before_gate_or_broker(runtime_job,monkeypatch):
    task,_,job,proposal=runtime_job
    proposal['compiled_delta']+='\nrule injected:\n  allow write file "**" if AGENT\n'
    with db.connect() as con:con.execute('UPDATE managed_jobs SET proposal_json=? WHERE id=?',(json.dumps(proposal),job['id']))
    monkeypatch.setattr(c,'broker',lambda *_a,**_k:pytest.fail('tampered candidate must not reach Broker'))
    with pytest.raises(ValueError,match='server-derived Delta'):c.finish_job(job)
    with db.connect() as con:state=c.load(con,task)
    assert state['phase']=='running' and state['gate']=='waiting_policy'


def test_rehashed_unauthorized_target_is_rejected_before_broker(runtime_job,monkeypatch):
    task,_,job,proposal=runtime_job
    target='src/other.py';delta=c.runtime_protection_delta({'workspace':'/tmp/work'},job['id'],[target])
    proposal.update(add_protected_paths=[target],protected_paths=[target],compiled_delta=delta,
                    compiled_delta_hash=hashlib.sha256(delta.encode()).hexdigest())
    with db.connect() as con:con.execute('UPDATE managed_jobs SET proposal_json=? WHERE id=?',(json.dumps(proposal),job['id']))
    monkeypatch.setattr(c,'broker',lambda *_a,**_k:pytest.fail('unauthorized target must not reach Broker'))
    with pytest.raises(ValueError,match='server-derived Delta'):c.finish_job(job)
    with db.connect() as con:assert c.load(con,task)['gate']=='waiting_policy'


def test_guidance_finishes_without_delta(runtime_job,monkeypatch):
    task,_,job,proposal=runtime_job
    proposal.update(decision='guidance_only',add_protected_paths=[],protected_paths=[],compiled_delta='',compiled_delta_hash=None)
    with db.connect() as con:con.execute('UPDATE managed_jobs SET proposal_json=? WHERE id=?',(json.dumps(proposal),job['id']))
    calls=[];monkeypatch.setattr(c,'broker',healthy_broker(calls))
    assert c.finish_job(job) is None
    assert [item['action'] for item in calls]==['status']
    with db.connect() as con:state=c.load(con,task)
    assert state['version']==3 and state['gate']=='open'

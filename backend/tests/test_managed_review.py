"""Human approval, stale evidence, and failed application must not silently change scope."""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from agentscope_app import db
from agentscope_app.managed import controller as c


@pytest.fixture
def pending(seed_task, monkeypatch):
    db.init_db()
    task=uuid.uuid4().hex[:16];seed_task(task)
    state={'phase':'running','gate':'waiting_policy','revision':2,'version':3,'policy_hash':'loaded-hash','baseline_hash':'baseline','baseline_extra':'','protected':[],'runtime_protected':[],'allowed_write_dirs':['.'],'allow_output':False,'binding':{'domain_id':77,'runner_pid':101},'session_id':'native-a','turn':1,'normalization_mode':'legacy'}
    ctx={'revision':2,'policy_hash':'loaded-hash','request_evidence_id':'req1','current_binding':{'domain_id':77,'runner_pid':101},'project_sources':[],'base_snapshot':{'payload':{'allowed_write_dirs':['.'],'allow_output':False,'protected_paths':[]}}}
    job={'id':uuid.uuid4().hex,'task_id':task,'revision':2,'policy_hash':'loaded-hash','context_json':json.dumps(ctx)}
    def put(decision='restrict'):
        proposal={'decision':decision,'allowed_write_dirs':['src'] if decision=='restrict' else ['.'],'allow_output':decision=='expand','protected_paths':[],'evidence_ids':['req1'],'explanation':'Explicit user request and project evidence','hash':'candidate-'+decision}
        with db.connect() as con:
            c.save(con,task,state)
            con.execute("INSERT OR REPLACE INTO managed_jobs(id,task_id,request_key,revision,policy_hash,context_json,proposal_json,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(job['id'],task,job['id'],2,'loaded-hash',job['context_json'],json.dumps(proposal),'completed',db.now()))
        c.finish_job(job)
        return proposal
    monkeypatch.setattr(c,'broker',lambda request,**kwargs:{'status':'running','domain_id':77,'runner_pid':101,'domain_verified':True,'cgroup_verified':True})
    return task,state,job,put


@pytest.mark.parametrize('decision,gate',[('restrict','waiting_confirmation'),('expand','open')])
def test_candidate_generation_never_installs_scope(pending,monkeypatch,decision,gate):
    task,state,job,put=pending
    monkeypatch.setattr(c,'install',lambda *a,**k:pytest.fail('generation cannot install'))
    put(decision)
    with db.connect() as con:s=c.load(con,task)
    assert s['version']==3 and s['allow_output'] is False and s['allowed_write_dirs']==['.']
    assert s['gate']==gate and s['pending_change']['job_id']==job['id']


def install_mock(monkeypatch,calls):
    def install(task,state,dirs,output,**kwargs):
        calls.append(task)
        with db.connect() as con:
            stored=c.load(con,task)
            assert stored['gate']=='applying'
            stored.update(version=stored['version']+1,policy_hash='new-hash',allowed_write_dirs=dirs,allow_output=output,gate='open',pending_change=None,pending_expansion=None)
            c.save(con,task,stored)
        return stored
    monkeypatch.setattr(c,'install',install)


@pytest.mark.parametrize('decision',['restrict','expand'])
def test_only_matching_human_review_installs_once(pending,monkeypatch,decision):
    task,_,job,put=pending;p=put(decision);calls=[];install_mock(monkeypatch,calls)
    result=c.review_change(task,job['id'],'approve',p['hash'])
    assert result['version']==4 and calls==[task]
    with pytest.raises(ValueError,match='已处理'):c.review_change(task,job['id'],'approve',p['hash'])
    with db.connect() as con:
        assert c.load(con,task)['version']==4
        event=json.loads(con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='change_review'",(task,)).fetchone()[0])
    assert event['actor']=='authenticated_operator' and event['decision']=='approve'


@pytest.mark.parametrize('decision,gate',[('restrict','waiting_clarification'),('expand','open')])
def test_reject_never_changes_scope_and_restriction_stays_waiting(pending,monkeypatch,decision,gate):
    task,_,job,put=pending;p=put(decision)
    monkeypatch.setattr(c,'install',lambda *a,**k:pytest.fail('rejected candidate cannot install'))
    c.review_change(task,job['id'],'reject',p['hash'])
    with db.connect() as con:
        s=c.load(con,task);status=con.execute('SELECT status FROM managed_jobs WHERE id=?',(job['id'],)).fetchone()[0]
    assert s['version']==3 and not s['allow_output'] and s['gate']==gate and status=='rejected'
    assert bool(s.get('pending_restriction_intent'))==(decision=='restrict')


@pytest.mark.parametrize('field,value',[('revision',3),('version',4),('policy_hash','different')])
def test_stale_scope_or_context_cannot_be_approved(pending,monkeypatch,field,value):
    task,_,job,put=pending;p=put()
    with db.connect() as con:s=c.load(con,task);s[field]=value;c.save(con,task,s)
    monkeypatch.setattr(c,'install',lambda *a,**k:pytest.fail('stale candidate cannot install'))
    with pytest.raises(ValueError,match='stale'):c.review_change(task,job['id'],'approve',p['hash'])


def test_changed_process_generation_cannot_be_approved(pending,monkeypatch):
    task,_,job,put=pending;p=put()
    with db.connect() as con:s=c.load(con,task);s['binding']['runner_pid']=202;c.save(con,task,s)
    with pytest.raises(ValueError,match='代次'):c.review_change(task,job['id'],'approve',p['hash'])


def test_unverified_live_domain_does_not_accept_review(pending,monkeypatch):
    task,_,job,put=pending;p=put()
    monkeypatch.setattr(c,'broker',lambda *a,**k:{'status':'running','domain_id':77,'runner_pid':101,'domain_verified':False})
    with pytest.raises(ValueError,match='不可核验'):c.review_change(task,job['id'],'approve',p['hash'])


def test_foreign_job_and_hash_do_not_change_scope(pending):
    task,_,job,put=pending;p=put()
    for job_id,hash_value in [('foreign',p['hash']),(job['id'],'wrong')]:
        with pytest.raises(ValueError,match='不属于'):c.review_change(task,job_id,'approve',hash_value)
    with db.connect() as con:assert c.load(con,task)['version']==3


def test_failure_before_replacement_reports_still_loaded_version(pending,monkeypatch):
    task,_,job,put=pending;p=put()
    def fail(*a,**k):raise RuntimeError('compile failed before domain replacement')
    monkeypatch.setattr(c,'install',fail)
    with pytest.raises(RuntimeError):c.review_change(task,job['id'],'approve',p['hash'])
    with db.connect() as con:
        s=c.load(con,task)
        event=json.loads(con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='change_apply_failed'",(task,)).fetchone()[0])
    assert s['version']==3 and s['binding']['domain_id']==77 and s['gate']=='waiting_confirmation'
    assert event['version']==3


def test_concurrent_duplicate_reviews_install_one_version(pending,monkeypatch):
    task,_,job,put=pending;p=put();calls=[];install_mock(monkeypatch,calls)
    def approve():
        try:return c.review_change(task,job['id'],'approve',p['hash'])['version']
        except ValueError:return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:approve(),range(2)))
    assert sorted(map(str,results))==['4','rejected'] and calls==[task]

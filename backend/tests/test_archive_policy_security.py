"""Independent offline archive contract checks; no model or live runtime."""
import json
import sqlite3
import uuid
from contextlib import contextmanager

import pytest
from fastapi import HTTPException

from agentscope_app import db
from agentscope_app.bootstrap.scene import digest
from agentscope_app.archive import policies
from agentscope_app.managed import controller, records
from agentscope_app.workspaces import observer, registry


def ident():
    return uuid.uuid4().hex


@pytest.fixture
def archived(client, seed_task, monkeypatch):
    task, foreign = ident(), ident()
    seed_task(task)
    seed_task(foreign)
    with db.connect() as con:
        controller.save(con, task, {'phase':'ended','version':9,'session_id':'CURRENT_UNRELATED_SESSION',
            'binding':{'domain_id':999,'runner_pid':999},'binding_history':[{'domain_id':7,'version':1}],
            'runtime_protected':[],'allowed_write_dirs':['.'],'allow_output':False})
    def forbidden(*args, **kwargs):
        pytest.fail('offline archive must not contact runtime, filesystem or model')
    monkeypatch.setattr(controller, 'broker', forbidden)
    monkeypatch.setattr(records, 'workbench', forbidden)
    monkeypatch.setattr(registry, 'get_workspace', forbidden)
    monkeypatch.setattr(observer, 'broker', forbidden)
    return task, foreign


def runtime_job(task, status='completed', proposal=True):
    job = ident()
    context = {'sources':[], 'request_evidence_id':'not-recorded', 'project_sources':[],
        'session_id':'RECORDED_OLD_SESSION', 'current_binding':{'version':1,'domain_id':7,'runner_pid':11},
        'base_snapshot':{'payload':{'allowed_write_dirs':['.'],'allow_output':False,'protected_paths':[]}}}
    value = {'decision':'guidance_only','allowed_write_dirs':['.'],'allow_output':False,
        'evidence_ids':[],'explanation':'Public explanation token=DO_NOT_EXPORT_ARCHIVE_CREDENTIAL',
        'identified_statements':[{'statement':'Explain public findings','policy_type':'semantic_only',
            'context_required':True,'context_reason':'task wording','evidence_ids':[]}],
        'api_key':'DO_NOT_EXPORT_ARCHIVE_KEY'}
    with db.connect() as con:
        con.execute('INSERT INTO managed_jobs(id,task_id,request_key,revision,policy_hash,context_json,proposal_json,status,created_at,error) VALUES(?,?,?,?,?,?,?,?,?,?)',
            (job, task, job, 1, 'recorded-old-hash', json.dumps(context),
             json.dumps(value) if proposal else None, status, db.now(), 'token=DO_NOT_EXPORT_FAILURE_BODY'))
    return job


def startup_candidate(task, loaded=False):
    job, proposal, version_id = ident(), ident(), ident()
    draft = {'draft':{'summary':'Public startup candidate','atoms':[],'guidance':['Give a clear explanation.']},
             'actplane_dsl':'','api_key':'DO_NOT_EXPORT_STARTUP_KEY'}
    with db.connect() as con:
        con.execute('INSERT INTO history_jobs(id,kind,status,input_json,created_at) VALUES(?,?,?,?,?)',
            (job,'task_bootstrap','completed',json.dumps({'task_id':task}),db.now()))
        con.execute('INSERT INTO bootstrap_proposals(id,task_id,job_id,context_hash,content_hash,proposal_json,validation_json,state,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
            (proposal,task,job,'ctx',digest(draft),json.dumps(draft),'{}','validated',db.now()))
        if loaded:
            con.execute('INSERT INTO policy_versions(id,task_id,version,layer,dsl_text,policy_yaml,compile_state,status,change_summary,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (version_id,task,1,'startup','source COMMAND = process descendants','policy: source COMMAND = process descendants','compiled','approved','recorded',db.now()))
            con.execute('INSERT INTO bootstrap_versions VALUES(?,?,?,?,?,?,?)',
                (version_id,proposal,'ctx',digest(draft),'confirmed','public task','task-hash'))
            controller.event(con,task,'policy_active',ident(),{'version':1,'session_id':'RECORDED_OLD_SESSION',
                'binding':{'domain_id':7,'runner_pid':11,'watch_pid':12},'verification':{'passed':True}})
    return job, proposal


def test_every_runtime_generation_status_is_visible_offline_and_secret_safe(archived):
    task, foreign = archived
    statuses = ['queued','running','completed','failed','rejected','clarified','interrupted']
    jobs = {runtime_job(task,status,proposal=status not in ('queued','failed')):status for status in statuses}
    other = runtime_job(foreign)
    result = policies.policy_records(task,'runtime',limit=200)
    parents = {r['job_id']:r for r in result['records'] if r['id']=='runtime:'+r['job_id']}
    assert set(parents) == set(jobs) and other not in parents
    assert {job:r['generation_status'] for job,r in parents.items()} == jobs
    details = [policies.policy_detail(task,'runtime:'+job) for job in jobs]
    assert all(d['history_only'] and d['historical'] and not d['live'] for d in details)
    assert all(d['loading']['active'] is False and d['loading']['loaded'] is False for d in details)
    serialized = json.dumps([result,details])
    for private in ('DO_NOT_EXPORT_ARCHIVE_CREDENTIAL','DO_NOT_EXPORT_ARCHIVE_KEY','DO_NOT_EXPORT_FAILURE_BODY','CURRENT_UNRELATED_SESSION'):
        assert private not in serialized


def test_all_startup_candidates_keep_exact_load_identity_and_guidance_semantics(archived):
    task, _ = archived
    old_job, old = startup_candidate(task,loaded=True)
    new_job, new = startup_candidate(task)
    page = policies.policy_records(task,'startup',limit=200)
    ids = {r['id'] for r in page['records']}
    assert ids == {'startup_job:'+old_job,'startup_job:'+new_job}
    old_generation = policies.policy_detail(task,'startup_job:'+old_job)
    new_generation = policies.policy_detail(task,'startup_job:'+new_job)
    assert [c['id'] for c in old_generation['candidates']] == ['startup:'+old]
    assert [c['id'] for c in new_generation['candidates']] == ['startup:'+new]
    assert old_generation['statements'] and new_generation['statements']
    detail = policies.policy_detail(task,'startup:'+old)
    assert detail['loading']['loaded'] and detail['loading']['active'] is False
    assert detail['loading']['session_id'] == 'RECORDED_OLD_SESSION'
    assert detail['loading']['binding']['domain_id'] == 7
    assert not policies.policy_detail(task,'startup:'+new)['loading']['loaded']
    guide = policies.policy_detail(task,'startup:'+old+':guide:0')
    assert guide['policy_type']=='semantic_only' and guide['compilation']['status']=='not_applicable'
    assert guide['loading']['loaded'] is False
    assert 'CURRENT_UNRELATED_SESSION' not in json.dumps([detail,guide])
    assert 'DO_NOT_EXPORT_STARTUP_KEY' not in json.dumps(detail)


def test_policy_pagination_cursor_and_record_identity_cannot_cross_task_or_stage(archived):
    task, foreign = archived
    for _ in range(4):
        runtime_job(task)
    first = policies.policy_records(task,'runtime',limit=1)
    cursor = first['next_cursor']
    assert cursor
    with pytest.raises(HTTPException) as error:
        policies.policy_records(foreign,'runtime',cursor,1)
    assert error.value.status_code==422
    with pytest.raises(HTTPException):
        policies.policy_records(task,'startup',cursor,1)
    record_id = first['records'][0]['id']
    for owner, bad_id in [(foreign,record_id),(task,"runtime:x' OR 1=1 --"),(task,'../../etc/passwd')]:
        with pytest.raises(HTTPException) as error:
            policies.policy_detail(owner,bad_id)
        assert error.value.status_code==404
    seen = []
    page = first
    while True:
        seen.extend(r['id'] for r in page['records'])
        if not page['next_cursor']:
            break
        page = policies.policy_records(task,'runtime',page['next_cursor'],1)
    assert len(seen)==len(set(seen))==first['total']


def test_read_only_views_do_not_write_even_during_clause_projection(archived,monkeypatch):
    task, _ = archived
    job = runtime_job(task)
    startup_candidate(task,loaded=True)
    original = db.connect
    forbidden = {sqlite3.SQLITE_INSERT,sqlite3.SQLITE_UPDATE,sqlite3.SQLITE_DELETE,
                 sqlite3.SQLITE_CREATE_TABLE,sqlite3.SQLITE_DROP_TABLE,sqlite3.SQLITE_ALTER_TABLE}
    writes = []
    @contextmanager
    def readonly():
        with original() as con:
            def authorize(action, arg1, arg2, *rest):
                if action in forbidden:
                    writes.append((action,arg1))
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            con.set_authorizer(authorize)
            yield con
    monkeypatch.setattr(db,'connect',readonly)
    policies.policy_records(task,'startup')
    policies.policy_records(task,'runtime')
    policies.policy_detail(task,'runtime:'+job)
    for category in ('os','tools','control'):
        policies.execution_audit(task,category)
    assert writes==[]


def test_os_denials_tool_failures_and_independent_probes_keep_distinct_sources(archived):
    task, foreign = archived
    with db.connect() as con:
        controller.event(con,task,'tool_start','tool-call',{'call_id':'tool-call','name':'bash','pid':123,'domain_id':7,'target':'/tmp/work/public.py'})
        controller.event(con,task,'tool_result','tool-call',{'call_id':'tool-call','name':'bash','succeeded':False,'pid':123})
        controller.event(con,task,'kernel','kernel-event',{'version':1,'event':{'op':'write','pid':123,'target':'/tmp/work/guard.py',
            'process_domain_id':7,'domain_id':3,'rule':{'name':'guard','reason':'token=DO_NOT_EXPORT_RULE_SECRET'}}})
        controller.event(con,task,'operation_verified','probe-event',{'version':1,'classification':'correct_allow',
            'verification_probe':True,'domain_id':7,'probe':{'operation':'write','pid':124,'target':'/tmp/work/allowed.py'}})
        controller.event(con,foreign,'kernel','other-kernel',{'event':{'op':'unlink','pid':123,'process_domain_id':7,'target':'FOREIGN_TASK_TARGET'}})
    os_rows = policies.execution_audit(task,'os')['records']
    tools = policies.execution_audit(task,'tools')['records']
    kernel = next(r for r in os_rows if r['kind']=='kernel')
    probe = next(r for r in os_rows if r['kind']=='operation_verified')
    failed_tool = next(r for r in tools if r['kind']=='tool_result')
    assert kernel['result']=='denied' and kernel['action_source']=='kernel' and kernel['pid']==123 and kernel['domain_id']==7
    assert kernel['process_domain_id']==7 and kernel['rule_domain_id']==3
    assert probe['result']=='correct_allow' and probe['action_source']=='independent_probe' and probe['pid']==124
    assert failed_tool['result']=='failure' and failed_tool['action_source']=='native_tool'
    assert all(r['kind'] in ('kernel','operation_verified') for r in os_rows)
    assert all(r['kind'] in ('tool_start','tool_result') for r in tools)
    output = json.dumps([os_rows,tools])
    assert 'FOREIGN_TASK_TARGET' not in output and 'DO_NOT_EXPORT_RULE_SECRET' not in output


def test_tampered_runtime_compiled_dsl_is_marked_unavailable_without_export(archived):
    task, _ = archived
    job = runtime_job(task)
    with db.connect() as con:
        row = con.execute('SELECT proposal_json FROM managed_jobs WHERE id=?',(job,)).fetchone()
        proposal = json.loads(row[0])
        proposal.update(compiled_dsl='UNVERIFIED_DSL_MUST_NOT_EXPORT',compiled_dsl_hash='wrong')
        con.execute('UPDATE managed_jobs SET proposal_json=? WHERE id=?',(json.dumps(proposal),job))
    detail = policies.policy_detail(task,'runtime:'+job)
    assert detail['compilation']['status']=='integrity_failed'
    assert 'UNVERIFIED_DSL_MUST_NOT_EXPORT' not in json.dumps(detail)


def test_failed_rejected_and_interrupted_startup_generations_remain_inspectable(archived):
    task, _ = archived
    jobs = {}
    with db.connect() as con:
        for status in ('queued','running','failed','rejected','interrupted','completed'):
            job = ident()
            jobs[job] = status
            con.execute('INSERT INTO history_jobs(id,kind,status,input_json,error,created_at) VALUES(?,?,?,?,?,?)',
                (job,'task_bootstrap',status,json.dumps({'task_id':task,'secret':'STARTUP_PRIVATE_INPUT'}),
                 'STARTUP_RAW_FAILURE_NOT_PUBLIC',db.now()))
    listing = policies.policy_records(task,'startup',limit=200)
    assert {r['job_id']:r['generation_status'] for r in listing['records']} == jobs
    details = [policies.policy_detail(task,'startup_job:'+job) for job in jobs]
    assert all(not d['loading']['loaded'] and not d['live'] for d in details)
    assert 'STARTUP_PRIVATE_INPUT' not in json.dumps([listing,details])
    assert 'STARTUP_RAW_FAILURE_NOT_PUBLIC' not in json.dumps([listing,details])


def test_archive_policy_http_routes_keep_control_auth_and_validate_query(archived,client):
    task, _ = archived
    job = runtime_job(task)
    base = '/api/tasks/'+task+'/archive'
    paths = [base+'/policies?stage=runtime',base+'/policies/runtime:'+job,base+'/audit?category=os']
    for path in paths:
        assert client.get(path).status_code == 401
        response = client.get(path,headers={'Authorization':'Bearer test-admin-token-not-for-production'})
        assert response.status_code == 200 and response.json()['history_only'] and response.json()['live'] is False
    for suffix in ('/policies?stage=foreign','/policies?limit=0','/audit?category=sql','/audit?before=-1'):
        assert client.get(base+suffix,headers={'Authorization':'Bearer test-admin-token-not-for-production'}).status_code == 422


def test_one_generation_retains_multiple_candidates_without_repeating_list_rows(archived):
    task, _ = archived
    job, old = startup_candidate(task,loaded=True)
    second_job, second = startup_candidate(task)
    with db.connect() as con:
        con.execute('UPDATE bootstrap_proposals SET job_id=? WHERE id=?',(job,second))
        con.execute('DELETE FROM history_jobs WHERE id=?',(second_job,))
    page = policies.policy_records(task,'startup')
    assert len(page['records'])==page['total']==1
    detail = policies.policy_detail(task,'startup_job:'+job)
    candidates = {r['id']:r for r in detail['candidates']}
    assert set(candidates)=={'startup:'+old,'startup:'+second}
    assert candidates['startup:'+old]['loading']['loaded']
    assert candidates['startup:'+second]['loading']['loaded'] is False
    assert len(detail['statements'])==2
    assert all(s['loading']['loaded'] is False for s in detail['statements'])


def test_runtime_semantic_statement_never_inherits_os_bundle_receipt(archived):
    task, _ = archived
    job = runtime_job(task)
    with db.connect() as con:
        controller.event(con,task,'request_resolved',job,{'decision':'restrict','version':1})
        controller.event(con,task,'policy_active',ident(),{'version':1,
            'session_id':'RECORDED_OLD_SESSION','binding':{'domain_id':7,'runner_pid':11}})
    detail = policies.policy_detail(task,'runtime:'+job)
    assert detail['loading']['loaded'] and detail['loading']['active'] is False
    child = policies.policy_detail(task,'runtime:'+job+':statement:0')
    assert child['policy_type']=='semantic_only' and child['loading']['loaded'] is False
    assert child['loading']['status']=='not_applicable'
    assert child['loading']['bundle_receipt']['session_id']=='RECORDED_OLD_SESSION'


@pytest.mark.parametrize('kind,payload,expected',[
    ('change_review',{'decision':'reject'},'reject'),
    ('change_review',{'decision':'clarify'},'clarify'),
    ('candidate_invalidated',{'reason':'execution_generation_replaced'},'invalidated'),
    ('change_apply_failed',{'error':'apply failed token=PRIVATE_APPLY_FAILURE'},'apply_failed'),
    ('review_pending',{'decision':'restrict'},'pending'),
])
def test_runtime_review_and_expiry_lifecycle_remains_visible_offline(archived,kind,payload,expected):
    task, _ = archived
    job = runtime_job(task)
    with db.connect() as con:
        controller.event(con,task,kind,ident(),{'job_id':job,**payload})
    detail = policies.policy_detail(task,'runtime:'+job)
    assert detail['candidate_status']==expected
    assert detail['reviews'][0]['kind']==kind
    assert not detail['loading']['loaded'] and not detail['live']
    assert 'PRIVATE_APPLY_FAILURE' not in json.dumps(detail)


def test_unavailable_statement_material_does_not_silently_return_parent(archived):
    task, _ = archived
    job, proposal = startup_candidate(task)
    with db.connect() as con:
        con.execute("UPDATE bootstrap_proposals SET content_hash='corrupt' WHERE id=?",(proposal,))
    parent=policies.policy_detail(task,'startup:'+proposal)
    assert parent['material_status']=='integrity_failed'
    with pytest.raises(HTTPException) as error:
        policies.policy_detail(task,'startup:'+proposal+':guide:0')
    assert error.value.status_code==404


def test_tool_result_target_uses_only_same_call_and_same_task_start_receipt(archived):
    task, foreign = archived
    with db.connect() as con:
        controller.event(con,task,'tool_start','shared-call',{'call_id':'shared-call','name':'read','target':'/recorded/real.txt'})
        controller.event(con,foreign,'tool_start','shared-call',{'call_id':'shared-call','name':'read','target':'/foreign/secret.txt'})
        controller.event(con,task,'tool_result','result-key',{'call_id':'shared-call','name':'read','target':None,'succeeded':True})
    data=policies.execution_audit(task,'tools')
    result=next(r for r in data['records'] if r['kind']=='tool_result')
    assert result['target']=='/recorded/real.txt' and result['target_evidence_event_id']
    assert '/foreign/secret.txt' not in json.dumps(data)

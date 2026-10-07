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


def mapped_runtime_job(task, decision='restrict', statements=None, before=(), after=('one.txt','two.txt')):
    """Persist a complete compiler report with a same-rule unrelated sibling."""
    job = runtime_job(task)
    with db.connect() as con:
        workspace = con.execute('SELECT workspace FROM tasks WHERE id=?',(task,)).fetchone()[0]
        row = con.execute('SELECT context_json,proposal_json FROM managed_jobs WHERE id=?',(job,)).fetchone()
        context, proposal = json.loads(row[0]), json.loads(row[1])
        context['base_snapshot']['payload']['protected_paths'] = list(before)
        context['project_sources'] = [
            {'id':name,'path':workspace+'/'+name,'hash':'frozen-'+name} for name in ('one.txt','two.txt')]
        rules = [
            {'name':'shared','rule_id':index,'source_start_line':1,'clause_start_line':index+2,
             'clause_op':'write','target_pattern':workspace+'/'+name,
             'clause_text':'  block write file "'+workspace+'/'+name+'" if AGENT',
             'source_text':'SHARED_WHOLE_RULE_MUST_NOT_LEAK',
             'reason':'preserve registered objects'}
            for index,name in enumerate(('one.txt','two.txt'))]
        rules.append({'name':'unrelated','rule_id':9,'source_start_line':10,'clause_start_line':11,
            'clause_op':'write','target_pattern':'/private/unrelated.txt',
            'clause_text':'  block write file "/private/unrelated.txt" if AGENT',
            'source_text':'UNRELATED_FULL_BASELINE'})
        full = 'rule shared:\n'+'\n'.join(r['clause_text'] for r in rules)+'\n# WHOLE_CANDIDATE_BUNDLE'
        proposal.update(decision=decision,protected_paths=list(after),
            compiled_dsl=full,compiled_dsl_hash=records.digest(full),compile={'ok':True,'rules':rules})
        proposal['identified_statements'] = statements if statements is not None else [
            {'statement':'Preserve '+name,'policy_type':'per_event','context_required':True,
             'context_reason':'Bind the registered object','evidence_ids':['project:'+name]}
            for name in ('one.txt','two.txt')]
        con.execute('UPDATE managed_jobs SET context_json=?,proposal_json=? WHERE id=?',
            (json.dumps(context),json.dumps(proposal),job))
    return job,workspace


def test_runtime_exact_statement_id_exposes_only_its_compiler_clauses(archived):
    task, _ = archived
    job, workspace = mapped_runtime_job(task)
    parent = policies.policy_detail(task,'runtime:'+job)
    assert len(parent['statements'])==2
    for index,name in enumerate(('one.txt','two.txt')):
        requested = 'runtime:'+job+':statement:'+str(index)
        detail = policies.policy_detail(task,requested)
        assert detail['id']==requested and detail['record_kind']=='statement'
        assert detail['compilation']['scope']=='statement'
        assert detail['bundle_compilation']['scope']=='candidate_bundle'
        assert workspace+'/'+name in detail['compilation']['dsl']
        assert workspace+'/'+('two.txt' if name=='one.txt' else 'one.txt') not in detail['compilation']['dsl']
        output = json.dumps({k:v for k,v in detail.items() if k!='bundle_compilation'})
        assert '/private/unrelated.txt' not in output
        assert 'WHOLE_CANDIDATE_BUNDLE' not in output
        assert 'SHARED_WHOLE_RULE_MUST_NOT_LEAK' not in output
        assert 'proposal' not in detail
    assert parent['bundle_compilation']['scope']=='candidate_bundle'
    assert 'WHOLE_CANDIDATE_BUNDLE' in parent['bundle_compilation']['dsl']


@pytest.mark.parametrize('policy_type',['semantic_only','content'])
def test_non_os_statement_never_exports_os_dsl_even_with_exact_target_and_evidence(archived,policy_type):
    task, _ = archived
    job, _ = mapped_runtime_job(task,statements=[
        {'statement':'Preserve one.txt','policy_type':policy_type,'context_required':True,
         'context_reason':'Task content constraint','evidence_ids':['project:one.txt']}])
    detail = policies.policy_detail(task,'runtime:'+job+':statement:0')
    assert detail['id']=='runtime:'+job+':statement:0'
    assert detail['compilation']['dsl']==''
    assert detail['compilation'].get('has_new_os_rule',False) is False
    assert detail['loading']['loaded'] is False
    assert detail['operations']==[]
    assert 'WHOLE_CANDIDATE_BUNDLE' not in json.dumps({k:v for k,v in detail.items() if k!='bundle_compilation'})


def test_unmapped_runtime_statement_does_not_export_other_candidate_rules(archived):
    task, _ = archived
    job, _ = mapped_runtime_job(task,statements=[
        {'statement':'Protect an unspecified resource','policy_type':'per_event','context_required':True,
         'context_reason':'No exact registered object','evidence_ids':[]}])
    detail = policies.policy_detail(task,'runtime:'+job+':statement:0')
    assert detail['compilation']['dsl']==''
    assert detail['loading']['loaded'] is False
    assert detail['targets']==[] and detail['operations']==[]
    assert 'WHOLE_CANDIDATE_BUNDLE' not in json.dumps({k:v for k,v in detail.items() if k!='bundle_compilation'})
    assert 'UNRELATED_FULL_BASELINE' not in json.dumps({k:v for k,v in detail.items() if k!='bundle_compilation'})


@pytest.mark.parametrize('stage',['startup','runtime'])
def test_corrupt_statement_material_never_silently_returns_parent_candidate(archived,stage):
    task, _ = archived
    if stage=='startup':
        _,candidate = startup_candidate(task)
        requested = 'startup:'+candidate+':guide:0'
        with db.connect() as con:
            con.execute('UPDATE bootstrap_proposals SET content_hash=? WHERE id=?',('corrupted',candidate))
    else:
        job,_ = mapped_runtime_job(task)
        requested = 'runtime:'+job+':statement:0'
        with db.connect() as con:
            row = con.execute('SELECT proposal_json FROM managed_jobs WHERE id=?',(job,)).fetchone()
            proposal = json.loads(row[0]);proposal['compiled_dsl_hash']='corrupted'
            con.execute('UPDATE managed_jobs SET proposal_json=? WHERE id=?',(json.dumps(proposal),job))
    with pytest.raises(HTTPException) as error:
        policies.policy_detail(task,requested)
    assert error.value.status_code==404


def test_expand_removing_protection_does_not_display_an_added_deny_rule(archived):
    task, _ = archived
    # Include a same-target stale deny in the report. A release receipt cannot
    # reinterpret that old restriction as an added block for this statement.
    job,_ = mapped_runtime_job(task,decision='expand',before=('one.txt','two.txt'),after=('two.txt',),
        statements=[{'statement':'Allow edits to one.txt','policy_type':'per_event','context_required':True,
                     'context_reason':'Authenticated removed protection','evidence_ids':['project:one.txt']}])
    detail = policies.policy_detail(task,'runtime:'+job+':statement:0')
    assert detail['delta']['removed_protection']==['one.txt']
    assert not detail['delta'].get('added_protection')
    assert detail['compilation'].get('has_new_os_rule',False) is False
    assert detail['compilation']['dsl']==''
    assert 'block write' not in json.dumps({k:v for k,v in detail.items() if k!='bundle_compilation'})


def test_multistatement_generation_listing_and_all_views_leave_authority_unchanged(archived):
    task, _ = archived
    job,_ = mapped_runtime_job(task)
    tables = ('managed_tasks','managed_jobs','managed_events','policy_versions')
    def snapshot():
        with db.connect() as con:
            return {name:[tuple(row) for row in con.execute('SELECT * FROM '+name+' ORDER BY rowid')]
                    for name in tables}
    before = snapshot()
    listing = policies.policy_records(task,'runtime',limit=1)
    assert listing['total']==1 and listing['records'][0]['id']=='runtime:'+job
    parent = policies.policy_detail(task,listing['records'][0]['id'])
    assert {r['id'] for r in parent['statements']}=={
        'runtime:'+job+':statement:0','runtime:'+job+':statement:1'}
    for statement in parent['statements']:
        policies.policy_detail(task,statement['id'])
    for category in ('os','tools','control'):
        policies.execution_audit(task,category)
    assert snapshot()==before


@pytest.mark.parametrize('decision',['guidance_only'])
def test_guidance_assessment_does_not_lend_old_baseline_os_dsl(archived,decision):
    task, _ = archived
    job,_ = mapped_runtime_job(task,decision=decision,before=('one.txt','two.txt'),
        after=('one.txt','two.txt'),statements=[
            {'statement':'Preserve one.txt','policy_type':'semantic_only','context_required':True,
             'context_reason':'Existing baseline instruction','evidence_ids':['project:one.txt']}])
    detail = policies.policy_detail(task,'runtime:'+job+':statement:0')
    assert detail['compilation']['dsl']==''
    assert detail['compilation'].get('has_new_os_rule',False) is False
    assert 'WHOLE_CANDIDATE_BUNDLE' not in json.dumps({k:v for k,v in detail.items() if k!='bundle_compilation'})


def test_statement_list_paginates_all_exact_ids_and_keeps_job_view_separate(archived):
    task, foreign = archived
    first_job,_ = mapped_runtime_job(task)
    second_job,_ = mapped_runtime_job(task)
    seen=[];cursor=None
    while True:
        page=policies.policy_records(task,'runtime',before=cursor,limit=1,view='statements')
        assert page['total']==4
        seen.extend(row['id'] for row in page['records'])
        cursor=page['next_cursor']
        if not cursor:break
        with pytest.raises(HTTPException) as error:
            policies.policy_records(foreign,'runtime',before=cursor,limit=1,view='statements')
        assert error.value.status_code==422
        with pytest.raises(HTTPException) as error:
            policies.policy_records(task,'runtime',before=cursor,limit=1,view='jobs')
        assert error.value.status_code==422
    assert set(seen)=={'runtime:'+job+':statement:'+str(index)
        for job in (first_job,second_job) for index in (0,1)}
    assert len(seen)==4
    for exact in seen:
        detail=policies.policy_detail(task,exact)
        assert detail['id']==exact and detail['compilation']['scope']=='statement'
    jobs=policies.policy_records(task,'runtime',view='jobs')
    assert jobs['total']==2
    for job in (first_job,second_job):
        parent=policies.policy_detail(task,'runtime:'+job)
        assert parent['bundle_compilation']['scope']=='candidate_bundle'


@pytest.mark.parametrize('reliable_clauses',[False,True])
def test_startup_statement_only_exports_exact_clauses_not_same_rule_bundle(archived,reliable_clauses):
    task,_=archived
    job,candidate=startup_candidate(task)
    full='rule bootstrap-1:\n  block write file "/tmp/work/one.txt" if AGENT\n  block write file "/tmp/work/unrelated.txt" if AGENT'
    atom={'statement':'Preserve one.txt','evidence_ids':[],'operations':['write'],
          'paths':['/tmp/work/one.txt'],'decision':'block','reason':'Protect original'}
    draft={'draft':{'summary':'Candidate contains two OS targets','atoms':[atom],'guidance':[]},
           'actplane_dsl':full}
    compiler={'ok':True,'rules':[{'name':'bootstrap-1','source_start_line':1,'source_text':full}]}
    if reliable_clauses:
        compiler['rules']=[
            {'name':'bootstrap-1','source_start_line':1,'source_text':full,'clause_start_line':2,
             'clause_text':'  block write file "/tmp/work/one.txt" if AGENT',
             'clause_op':'write','target_pattern':'/tmp/work/one.txt'},
            {'name':'bootstrap-1','source_start_line':1,'source_text':full,'clause_start_line':3,
             'clause_text':'  block write file "/tmp/work/unrelated.txt" if AGENT',
             'clause_op':'write','target_pattern':'/tmp/work/unrelated.txt'}]
    with db.connect() as con:
        con.execute('UPDATE bootstrap_proposals SET proposal_json=?,content_hash=?,validation_json=? WHERE id=?',
            (json.dumps(draft),digest(draft),json.dumps({'compiler':compiler}),candidate))
    exact='startup:'+candidate+':atom:0'
    detail=policies.policy_detail(task,exact)
    assert detail['id']==exact and detail['compilation']['scope']=='statement'
    assert '/tmp/work/unrelated.txt' not in json.dumps({k:v for k,v in detail.items() if k!='bundle_compilation'})
    if reliable_clauses:
        assert '/tmp/work/one.txt' in detail['compilation']['dsl']
    else:
        assert detail['compilation']['dsl']==''
        assert detail['compilation']['status']=='not_recorded'
    bundle=policies.policy_detail(task,'startup:'+candidate)['bundle_compilation']
    assert bundle['scope']=='candidate_bundle' and '/tmp/work/unrelated.txt' in bundle['dsl']


@pytest.mark.parametrize('evidence',['verified','wrong_hash','foreign_task','uncompiled'])
def test_removed_deny_diff_requires_hash_verified_same_task_before_compilation(archived,evidence):
    task,foreign=archived
    job,workspace=mapped_runtime_job(task,decision='expand',before=('one.txt','two.txt'),after=('two.txt',),
        statements=[{'statement':'Allow edits to one.txt','policy_type':'per_event','context_required':True,
                     'context_reason':'Remove the exact prior restriction','evidence_ids':['project:one.txt']}])
    with db.connect() as con:
        row=con.execute('SELECT context_json,proposal_json FROM managed_jobs WHERE id=?',(job,)).fetchone()
        context,proposal=json.loads(row[0]),json.loads(row[1])
        before_compile=proposal['compile']
        yaml='recorded policy before permission expansion'
        context['policy_hash']=records.digest(yaml) if evidence!='wrong_hash' else 'unmatched-yaml-hash'
        proposal['compile']={'ok':True,'rules':[r for r in before_compile['rules']
            if r.get('target_pattern')!=workspace+'/one.txt']}
        proposal['compiled_dsl']='rule shared:\n'+proposal['compile']['rules'][0]['clause_text']
        proposal['compiled_dsl_hash']=records.digest(proposal['compiled_dsl'])
        con.execute('UPDATE managed_jobs SET context_json=?,proposal_json=?,policy_hash=? WHERE id=?',
            (json.dumps(context),json.dumps(proposal),context['policy_hash'],job))
        con.execute('INSERT INTO policy_versions(id,task_id,version,layer,dsl_text,policy_yaml,compile_state,compile_json,status,change_summary,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            (ident(),foreign if evidence=='foreign_task' else task,1,'startup','prior-bundle',yaml,
             'compiled' if evidence!='uncompiled' else 'failed',json.dumps(before_compile),'approved','recorded',db.now()))
    detail=policies.policy_detail(task,'runtime:'+job+':statement:0')
    diff=detail['dsl_diff']
    assert diff['mapping_scope']=='target'
    assert detail['compilation']['dsl']==''
    assert detail['compilation'].get('has_new_os_rule',False) is False
    if evidence=='verified':
        assert diff['status']=='recorded'
        assert workspace+'/one.txt' in diff['before'] and diff['after']==''
        assert diff['removed_clauses'] and diff['added_clauses']==[]
        assert '/private/unrelated.txt' not in json.dumps(diff)
        assert workspace+'/two.txt' not in json.dumps(diff)
    else:
        assert diff['status']=='not_recorded'
        assert diff['before']=='' and diff['removed_clauses']==[]


@pytest.mark.parametrize('decision',['no_change','guidance_only'])
def test_unchanged_per_event_statement_retains_only_its_mapped_baseline_rule(archived,decision):
    task,_=archived
    job,workspace=mapped_runtime_job(task,decision=decision,before=('one.txt','two.txt'),
        after=('one.txt','two.txt'),statements=[
            {'statement':'Preserve one.txt','policy_type':'per_event','context_required':True,
             'context_reason':'Existing baseline remains applicable','evidence_ids':['project:one.txt']}])
    detail=policies.policy_detail(task,'runtime:'+job+':statement:0')
    compilation=detail['compilation']
    assert compilation['scope']=='statement'
    assert compilation['has_new_os_rule'] is False and compilation['reused'] is True
    assert workspace+'/one.txt' in compilation['dsl']
    assert workspace+'/two.txt' not in compilation['dsl']
    assert '/private/unrelated.txt' not in compilation['dsl']
    assert 'WHOLE_CANDIDATE_BUNDLE' not in json.dumps({k:v for k,v in detail.items() if k!='bundle_compilation'})


def test_statement_view_http_auth_validation_and_exact_detail(archived,client):
    task,_=archived
    job,_=mapped_runtime_job(task)
    url='/api/tasks/'+task+'/archive/policies'
    params={'stage':'runtime','view':'statements','limit':1}
    assert client.get(url,params=params).status_code==401
    headers={'Authorization':'Bearer test-admin-token-not-for-production'}
    response=client.get(url,params=params,headers=headers)
    assert response.status_code==200
    page=response.json()
    assert page['total']==2 and len(page['records'])==1
    exact=page['records'][0]['id']
    detail=client.get(url+'/'+exact,headers=headers)
    assert detail.status_code==200 and detail.json()['id']==exact
    assert detail.json()['compilation']['scope']=='statement'
    assert client.get(url,params={'view':'arbitrary'},headers=headers).status_code==422


@pytest.mark.parametrize('source_case',['verified','project_actor','missing_source','wrong_capability_hash','wrong_capability_version','arbitrary_directory'])
def test_output_permission_delta_requires_exact_authenticated_source_and_frozen_controller_target(archived,source_case):
    task,_=archived
    job,_=mapped_runtime_job(task,decision='expand',after=(),statements=[])
    with db.connect() as con:
        output=con.execute('SELECT output_dir FROM tasks WHERE id=?',(task,)).fetchone()[0]
        row=con.execute('SELECT context_json,proposal_json FROM managed_jobs WHERE id=?',(job,)).fetchone()
        context,proposal=json.loads(row[0]),json.loads(row[1])
        text='Write the report into '+output+'/acceptance.txt'
        if source_case=='arbitrary_directory':text='Write the report into /outside/acceptance.txt'
        statement={'statement':text,'policy_type':'per_event','context_required':True,
                   'context_reason':'Authenticated task output request','evidence_ids':['auth-output-request']}
        context['sources']=[{'evidence_id':'auth-output-request',
            'content':{'actor':'project' if source_case=='project_actor' else 'native_user','text':text}}]
        if source_case=='missing_source':context['sources']=[]
        context['policy_hash']='frozen-hash'
        context['capabilities']={'execution_targets':[{'kind':'task_output','path':output,'granted':False,
            'authority':'controller_verified_loaded_snapshot',
            'policy_version':7 if source_case=='wrong_capability_version' else 1,
            'policy_hash':'wrong-hash' if source_case=='wrong_capability_hash' else 'frozen-hash'}]}
        proposal['allow_output']=True
        proposal['identified_statements']=[statement]
        con.execute('UPDATE managed_jobs SET context_json=?,proposal_json=? WHERE id=?',
            (json.dumps(context),json.dumps(proposal),job))
    detail=policies.policy_detail(task,'runtime:'+job+':statement:0')
    assert detail['compilation']['dsl']==''
    assert detail['compilation'].get('has_new_os_rule',False) is False
    assert detail['dsl_diff']['status']=='not_recorded'
    assert detail['dsl_diff']['removed_clauses']==[]
    if source_case=='verified':
        permission=detail['permission_delta']
        assert permission=={'allow_output_before':False,'allow_output_after':True,'target':output+'/**',
            'source_evidence_ids':['auth-output-request'],'authority':'controller_verified_loaded_snapshot'}
        assert detail['statement_effect']=='expand' and detail['change_status']=='permission_changed'
    else:
        assert 'permission_delta' not in detail
        assert detail['statement_effect']=='unmapped'

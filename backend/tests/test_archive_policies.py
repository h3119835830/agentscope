"""Dedicated archive policy/audit pages must remain useful without an executor."""
import json
import uuid
import pytest
from fastapi import HTTPException,FastAPI
from fastapi.testclient import TestClient
from agentscope_app import db
from agentscope_app.archive import policies
from agentscope_app.archive.api import router
from agentscope_app.bootstrap.scene import digest
from agentscope_app.managed import controller,records


def ident():return uuid.uuid4().hex


@pytest.fixture
def task(seed_task,monkeypatch):
    db.init_db();task=ident();seed_task(task)
    with db.connect() as con:
        con.execute("UPDATE tasks SET status='ended',ended_at=? WHERE id=?",(db.now(),task))
        con.execute('INSERT INTO managed_tasks VALUES(?,?,?)',(task,json.dumps({'phase':'ended','gate':'closed','version':9,'session_id':'NEW_SESSION_MUST_NOT_BORROW','binding':{'domain_id':999,'runner_pid':999},'binding_history':[{'domain_id':41,'version':4}]}),db.now()))
    for name in ('broker',):monkeypatch.setattr(controller,name,lambda *a,**k:pytest.fail('offline archive called Broker'))
    for name in ('binding','workbench'):monkeypatch.setattr(records,name,lambda *a,**k:pytest.fail('offline archive called live view'))
    return task


def startup_job(task,status='completed'):
    job=ident()
    with db.connect() as con:con.execute('INSERT INTO history_jobs(id,kind,status,input_json,created_at) VALUES(?,?,?,?,?)',(job,'task_bootstrap',status,json.dumps({'task_id':task,'private_reasoning':'PRIVATE_RAW_STREAM','runtime':{'api_key':'SECRET_NATIVE_STREAM'}}),db.now()))
    return job


def candidate(task,job,state='validated'):
    pid=ident();source='source-'+pid;dsl='rule bootstrap-1:\n  block file.write "/tmp/work/config.json"'
    p={'draft':{'summary':'Protect config','atoms':[{'statement':'Do not overwrite config.json','evidence_ids':[source],'operations':['write'],'paths':['/tmp/work/config.json'],'decision':'block','reason':'Keep original'}],'guidance':['Run the tests after changes.']},'actplane_dsl':dsl}
    v={'compiler':{'ok':True,'rules':[{'name':'bootstrap-1','source_start_line':1,'source_text':dsl,'target_pattern':'/tmp/work/config.json','clause_text':'  block file.write \"/tmp/work/config.json\"','clause_op':'write','clause_start_line':2}]}}
    with db.connect() as con:
        con.execute('INSERT INTO bootstrap_sources VALUES(?,?,?,?,?,?,?)',(source,task,'asset','config.json','PRIVATE_SOURCE_BYTES',digest('PRIVATE_SOURCE_BYTES'),'{}'))
        con.execute('INSERT INTO bootstrap_proposals VALUES(?,?,?,?,?,?,?,?,?)',(pid,task,job,'context-hash',digest(p),json.dumps(p),json.dumps(v),state,db.now()))
    return pid,p


def runtime_job(task,status='completed',decision='restrict',statements=True):
    job=ident();dsl='rule protect:\n  block file.write "/tmp/work/config.json"'
    ctx={'request_evidence_id':'request:1','session_id':'OLD_SESSION','current_binding':{'domain_id':41,'runner_pid':101,'version':4,'session_id':'OLD_SESSION'},'base_snapshot':{'payload':{'protected_paths':[]}},'sources':[{'evidence_id':'request:1','content':{'actor':'native_user','text':'Protect config.json','turn':1}}],'private_reasoning':'PRIVATE_REASONING','native_execution_context':{}}
    p={'decision':decision,'hash':'candidate-'+job,'protected_paths':['config.json'],'allowed_write_dirs':['.'],'allow_output':False,'evidence_ids':['request:1'],'compiled_dsl':dsl,'compiled_dsl_hash':records.digest(dsl),'compile':{'ok':True,'rules':[{'name':'protect','target_pattern':'/tmp/work/config.json','clause_text':'  block file.write "/tmp/work/config.json"','clause_op':'write','source_start_line':1,'clause_start_line':2}]},'identified_statements':[{'statement':'Protect config.json','policy_type':'per_event','context_required':True,'context_reason':'task request','evidence_ids':['request:1']}] if statements else []}
    with db.connect() as con:con.execute('INSERT INTO managed_jobs(id,task_id,request_key,revision,policy_hash,status,context_json,proposal_json,token_hash,error,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(job,task,ident(),1,'base',status,json.dumps(ctx),json.dumps(p) if decision else None,'SECRET_CREDENTIAL','PRIVATE_FAILURE_STREAM',db.now()))
    return job,p


def event(task,kind,payload,key=None):
    with db.connect() as con:return con.execute('INSERT INTO managed_events(task_id,kind,event_key,payload_json,occurred_at) VALUES(?,?,?,?,?)',(task,kind,key or ident(),json.dumps(payload),db.now())).lastrowid


def walk(task,stage,limit=2):
    result=[];before=None
    while True:
        page=policies.policy_records(task,stage,before,limit);result.extend(page['records']);before=page['next_cursor']
        if before is None:return result


@pytest.mark.parametrize('status',['queued','running','completed','failed','cancelled','interrupted','rejected','stale','pending','pending_confirmation'])
def test_runtime_all_generation_states_visible_without_candidate(task,status):
    job,_=runtime_job(task,status,None)
    row=next(r for r in walk(task,'runtime') if r['id']=='runtime:'+job)
    assert row['status']==row['generation_status']==status and row['candidate_status']=='not_recorded'
    detail=policies.policy_detail(task,row['id'])
    assert detail['compilation']['status']=='not_recorded' and not detail['loading']['loaded']
    assert detail['history_only'] and detail['historical'] and detail['live'] is False


@pytest.mark.parametrize('status',['queued','running','failed','cancelled','interrupted','completed'])
def test_startup_all_jobs_and_all_candidates_are_visible(task,status):
    job=startup_job(task,status);first,_=candidate(task,job);second,_=candidate(task,job,'rejected')
    result=walk(task,'startup')
    assert {r['id'] for r in result}=={'startup_job:'+job}
    detail=policies.policy_detail(task,'startup_job:'+job)
    assert detail['status']==status and len(detail['candidates'])==2
    assert len(detail['statements'])==4
    assert all('PRIVATE_SOURCE_BYTES' not in json.dumps(x) for x in detail['statements'])


def test_startup_statement_dsl_and_loading_use_exact_old_receipt(task):
    job=startup_job(task);pid,_=candidate(task,job);version=ident();now=db.now()
    with db.connect() as con:
        con.execute('INSERT INTO policy_versions(id,task_id,version,layer,dsl_text,policy_yaml,compile_state,compile_json,status,change_summary,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(version,task,1,'task','rule bootstrap-1:','yaml','compiled','{}','approved','initial',now))
        con.execute('INSERT INTO bootstrap_versions VALUES(?,?,?,?,?,?,?)',(version,pid,'context','proposal','human_review','PRIVATE_PROMPT','prompt-hash'))
    event(task,'policy_active',{'version':1,'session_id':'OLD_STARTUP_SESSION','binding':{'domain_id':10,'runner_pid':11}})
    detail=policies.policy_detail(task,'startup:'+pid+':atom:0')
    assert 'block file.write' in detail['compilation']['dsl']
    assert detail['loading']['loaded'] and not detail['loading']['active']
    assert detail['loading']['binding']['domain_id']==10 and detail['loading']['session_id']=='OLD_STARTUP_SESSION'
    assert 'NEW_SESSION_MUST_NOT_BORROW' not in json.dumps(detail)
    assert detail['status']=='loaded_receipt' and detail['live'] is False


def test_runtime_review_dsl_loading_and_job_status_are_independent(task):
    job,p=runtime_job(task,'rejected')
    event(task,'change_review',{'job_id':job,'decision':'reject','candidate_hash':p['hash'],'change':'restrict','actor':'authenticated_operator'})
    detail=policies.policy_detail(task,'runtime:'+job)
    assert detail['status']=='rejected' and detail['review_status']=='rejected' and not detail['loading']['loaded']
    assert detail['compilation']['dsl']==p['compiled_dsl'] and len(detail['statements'])==1
    assert detail['statements'][0]['status']=='rejected'
    job2,p2=runtime_job(task)
    event(task,'request_resolved',{'decision':'restrict','version':4,'confirmation':p2['hash']},job2)
    event(task,'policy_active',{'version':4,'session_id':'OLD_SESSION','binding':{'domain_id':41,'runner_pid':101}})
    detail=policies.policy_detail(task,'runtime:'+job2)
    assert detail['loading']['loaded'] and detail['loading']['evidence_kind']=='stored_loading_receipt' and not detail['loading']['active']
    assert detail['loading']['binding']['domain_id']==41 and detail['live'] is False


def test_policy_cursor_is_scoped_to_task_stage_and_has_no_duplicates(task,seed_task):
    for _ in range(5):runtime_job(task)
    complete=walk(task,'runtime',3)
    assert len(complete)==5 and len({r['id'] for r in complete})==5
    page=policies.policy_records(task,'runtime',limit=3)
    with pytest.raises(HTTPException):policies.policy_records(task,'startup',page['next_cursor'])
    other=ident();seed_task(other)
    with pytest.raises(HTTPException):policies.policy_records(other,'runtime',page['next_cursor'])
    with pytest.raises(HTTPException) as error:policies.policy_detail(other,complete[0]['id'])
    assert error.value.status_code==404


def test_policy_detail_and_list_do_not_export_credentials_or_private_context(task):
    job,_=runtime_job(task)
    public=json.dumps(policies.policy_records(task,'runtime'))+json.dumps(policies.policy_detail(task,'runtime:'+job))
    for private in ('PRIVATE_REASONING','SECRET_CREDENTIAL','PRIVATE_FAILURE_STREAM','native_execution_context','token_hash'):assert private not in public
    job=startup_job(task);candidate(task,job)
    public=json.dumps(policies.policy_detail(task,'startup_job:'+job))
    for private in ('PRIVATE_RAW_STREAM','SECRET_NATIVE_STREAM','PRIVATE_SOURCE_BYTES'):assert private not in public


def test_corrupt_candidate_dsl_remains_visible_but_not_exported(task):
    job,p=runtime_job(task)
    with db.connect() as con:
        p['compiled_dsl']='CORRUPT_DSL_SECRET';con.execute('UPDATE managed_jobs SET proposal_json=? WHERE id=?',(json.dumps(p),job))
    detail=policies.policy_detail(task,'runtime:'+job)
    assert detail['compilation']['status']=='integrity_failed' and 'CORRUPT_DSL_SECRET' not in json.dumps(detail)
    job=startup_job(task);pid,p=candidate(task,job)
    with db.connect() as con:
        p['actplane_dsl']='CORRUPT_STARTUP_DSL';con.execute('UPDATE bootstrap_proposals SET proposal_json=? WHERE id=?',(json.dumps(p),pid))
    detail=policies.policy_detail(task,'startup:'+pid)
    assert detail['material_status']=='integrity_failed' and 'CORRUPT_STARTUP_DSL' not in json.dumps(detail)


def test_audit_domain_roles_provenance_tool_result_and_pagination(task):
    kernel=event(task,'kernel',{'domain_id':41,'verification_probe':True,'event':{'op':'write','target':'/tmp/work/config.json','pid':101,'domain_id':7,'process_domain_id':41,'rule_id':3,'rule':{'name':'bootstrap-1','reason':'Keep original','private_reasoning':'NO_EXPORT'}}})
    result=policies.execution_audit(task,'os')['records'][0]
    assert result['event_id']==kernel and result['result']=='denied' and result['source']==result['action_source']=='independent_probe'
    assert result['domain_id']==result['process_domain_id']==41 and result['rule_domain_id']==7 and result['rule']['name']=='bootstrap-1'
    assert result['detail_id']==f'managed_events:{kernel}:record'
    event(task,'tool_result',{'call_id':'bash1','name':'bash','succeeded':False,'pid':102,'domain_id':41,'target':'/tmp/work/config.json'})
    tool=policies.execution_audit(task,'tools')['records'][0]
    assert tool['result']=='failure' and tool['source']=='native_tool' and tool['rule_domain_id'] is None
    event(task,'control_pause',{'reason':'Awaiting review'})
    assert policies.execution_audit(task,'control')['records'][0]['kind']=='control_pause'
    for i in range(55):event(task,'operation_verified',{'domain_id':41,'probe':{'operation':'read','target':str(i),'pid':101},'classification':'allowed'})
    page=policies.execution_audit(task,'os');older=policies.execution_audit(task,'os',page['next_cursor'])
    assert len(page['records'])==50 and len(older['records'])==6 and older['next_cursor'] is None
    assert not {x['id'] for x in page['records']} & {x['id'] for x in older['records']}


def test_archive_policies_are_read_only_and_api_has_query_validation(task):
    job=startup_job(task);candidate(task,job);runtime_job(task)
    with db.connect() as con:before='\n'.join(con.iterdump())
    policies.policy_records(task,'startup');policies.policy_records(task,'runtime');policies.execution_audit(task,'os')
    with db.connect() as con:assert '\n'.join(con.iterdump())==before
    app=FastAPI();app.include_router(router);client=TestClient(app)
    assert client.get(f'/api/tasks/{task}/archive/policies?stage=startup&limit=1').status_code==200
    assert client.get(f'/api/tasks/{task}/archive/policies?stage=invalid').status_code==422
    assert client.get(f'/api/tasks/{task}/archive/audit?category=os').json()['live'] is False
    assert client.get(f'/api/tasks/{task}/archive/audit?before=-1').status_code==422


def test_legacy_task_without_managed_state_keeps_empty_audit_and_jobs(seed_task):
    db.init_db();task=ident();seed_task(task);job=startup_job(task,'failed')
    assert policies.policy_records(task)['records'][0]['job_id']==job
    assert policies.execution_audit(task)['status']=='not_recorded'



def test_runtime_parent_keeps_complete_delta_and_guidance_is_not_os_loaded(task):
    job,p=runtime_job(task)
    p['protected_paths'].append('second.json')
    p['identified_statements'].append({'statement':'Keep the explanation brief','policy_type':'semantic_only','context_required':True,'context_reason':'task guidance','evidence_ids':['request:1']})
    with db.connect() as con:con.execute('UPDATE managed_jobs SET proposal_json=? WHERE id=?',(json.dumps(p),job))
    event(task,'request_resolved',{'decision':'restrict','version':4},job)
    detail=policies.policy_detail(task,'runtime:'+job)
    assert detail['delta']['added_protection']==['config.json','second.json']
    assert detail['targets']==['config.json','second.json']
    guidance=next(r for r in detail['statements'] if r['policy_type']=='semantic_only')
    assert guidance['loading']['loaded'] is False and guidance['compilation']['status']=='not_applicable'
    assert policies.policy_records(task,'runtime')['total']==1


def test_same_content_hash_does_not_link_review_from_another_generation(task):
    first=startup_job(task);one,p=candidate(task,first)
    second=startup_job(task);two,_=candidate(task,second)
    with db.connect() as con:con.execute('UPDATE bootstrap_proposals SET content_hash=?,proposal_json=? WHERE id=?',(digest(p),json.dumps(p),two))
    event(task,'startup_confirmed',{'proposal_hash':digest(p)},one)
    assert policies.policy_detail(task,'startup:'+one)['review_status']=='approved'
    assert policies.policy_detail(task,'startup:'+two)['review_status']=='not_recorded'



def test_unmapped_statement_does_not_borrow_bundle_loaded(task):
    job,p=runtime_job(task)
    p['identified_statements'][0]['statement']='Protect an unspecified resource'
    p['compile']['rules']=[]
    with db.connect() as con:con.execute('UPDATE managed_jobs SET proposal_json=? WHERE id=?',(json.dumps(p),job))
    event(task,'request_resolved',{'decision':'restrict','version':4},job)
    detail=policies.policy_detail(task,'runtime:'+job)
    assert detail['loading']['loaded'] is True
    assert detail['statements'][0]['loading']['loaded'] is False
    assert detail['statements'][0]['loading']['status']=='mapping_not_recorded'



def test_real_three_statement_shape_retained_output_expansion_and_content(task):
    job,p=runtime_job(task,'completed','expand')
    original='Do not overwrite frontend/report.py. Do not write output yet.'
    output='现在需要把真实功能测试结果与修复摘要写到任务专属 output/summary.txt。'
    statements=[
        {'statement':'Do not overwrite frontend/report.py','policy_type':'per_event','context_required':True,'context_reason':'Retain original protection','evidence_ids':['19093']},
        {'statement':output,'policy_type':'per_event','context_required':True,'context_reason':'Explicit output request','evidence_ids':['19346','19093']},
        {'statement':'Avoid web_search for this task','policy_type':'content','context_required':True,'context_reason':'Task content guidance','evidence_ids':['19346']},
    ]
    p.update(identified_statements=statements,protected_paths=[],allow_output=True)
    dsl='rule startup:\n  block file.write "/tmp/work/frontend/report.py"\nrule unrelated:\n  block file.write "/tmp/work/other.txt"'
    p.update(compiled_dsl=dsl,compiled_dsl_hash=records.digest(dsl),compile={'ok':True,'rules':[
        {'name':'startup','target_pattern':'/tmp/work/frontend/report.py','clause_op':'write','clause_text':'  block file.write "/tmp/work/frontend/report.py"','source_start_line':1,'clause_start_line':2},
        {'name':'unrelated','target_pattern':'/tmp/work/other.txt','clause_op':'write','clause_text':'  block file.write "/tmp/work/other.txt"','source_start_line':3,'clause_start_line':4},
    ]})
    ctx={'request_evidence_id':'19346','policy_hash':'old-policy-hash','current_binding':{'version':3,'domain_id':41},'base_snapshot':{'payload':{'allow_output':False,'protected_paths':[],'allowed_write_dirs':['.']}},'baseline':{'protected_files':['/tmp/work/frontend/report.py']},'sources':[
        {'evidence_id':'19093','content':{'actor':'native_user','text':original}},
        {'evidence_id':'19346','content':{'actor':'native_user','text':output+'请先申请 output 目录写入权限，等人工审核并加载核验后再写报告；其他权限保持不变。'}},
    ],'capabilities':{'execution_targets':[{'kind':'task_output','path':'/tmp/output','granted':False,'operations':['write','unlink'],'authority':'controller_verified_loaded_snapshot','policy_version':3,'policy_hash':'old-policy-hash'}]}}
    with db.connect() as con:con.execute('UPDATE managed_jobs SET context_json=?,proposal_json=? WHERE id=?',(json.dumps(ctx),json.dumps(p),job))
    first=policies.policy_detail(task,'runtime:'+job+':statement:0')
    assert first['statement_effect']=='retained' and first['compilation']['reused'] is True
    assert 'frontend/report.py' in first['compilation']['dsl'] and 'other.txt' not in first['compilation']['dsl']
    assert first['compilation']['has_new_os_rule'] is False and first['compilation']['mapping_scope']=='target'
    second=policies.policy_detail(task,'runtime:'+job+':statement:1')
    assert second['statement_effect']=='expand' and second['change_status']=='permission_changed'
    assert second['permission_delta']['source_evidence_ids']==['19346']
    assert second['permission_delta']['allow_output_before'] is False and second['permission_delta']['allow_output_after'] is True
    assert second['compilation']['dsl']=='' and second['dsl_diff']['status']=='not_recorded' and second['dsl_diff']['removed_clauses']==[]
    third=policies.policy_detail(task,'runtime:'+job+':statement:2')
    assert third['statement_effect']=='guidance' and third['compilation']['dsl']=='' and third['operations']==[]
    page=policies.policy_records(task,'runtime',view='statements')
    assert page['total']==3 and {r['statement'] for r in page['records']}=={s['statement'] for s in statements}
    assert all(r['compilation']['scope']=='statement' for r in page['records'])
    assert len(policies.policy_records(task,'runtime')['records'])==1


def test_corrupt_statement_remains_listed_as_unavailable_without_parent_substitution(task):
    job,p=runtime_job(task)
    p['compiled_dsl_hash']='incorrect'
    with db.connect() as con:con.execute('UPDATE managed_jobs SET proposal_json=? WHERE id=?',(json.dumps(p),job))
    page=policies.policy_records(task,'runtime',view='statements')
    assert page['total']==1 and page['records'][0]['id']=='runtime:'+job+':statement:0'
    assert page['records'][0]['material_status']=='unavailable' and not page['records'][0]['detail_available']
    assert page['records'][0]['record_kind']=='statement' and page['records'][0]['parent_id']=='runtime:'+job
    with pytest.raises(HTTPException) as error:policies.policy_detail(task,'runtime:'+job+':statement:0')
    assert error.value.status_code==404



@pytest.mark.parametrize('stage',['startup','runtime'])
def test_unavailable_statements_preserve_identity_total_and_pagination(task,stage):
    if stage=='runtime':
        job,p=runtime_job(task)
        p['identified_statements']=p['identified_statements']*5
        p['compiled_dsl_hash']='incorrect'
        with db.connect() as con:con.execute('UPDATE managed_jobs SET proposal_json=? WHERE id=?',(json.dumps(p),job))
        expected={'runtime:'+job+':statement:'+str(i) for i in range(5)}
        parent='runtime:'+job
    else:
        job=startup_job(task);pid,_=candidate(task,job)
        with db.connect() as con:con.execute("UPDATE bootstrap_proposals SET content_hash='incorrect' WHERE id=?",(pid,))
        expected={'startup:'+pid+':atom:0','startup:'+pid+':guide:0'}
        parent='startup_job:'+job
    rows=[];before=None
    while True:
        page=policies.policy_records(task,stage,before,1,view='statements')
        assert page['total']==len(expected)
        rows.extend(page['records']);before=page['next_cursor']
        if before is None:break
    assert {r['id'] for r in rows}==expected and len(rows)==len(expected)
    assert all(r['record_kind']=='statement' and r['parent_id']==parent and not r['detail_available'] for r in rows)
    assert all(r['statement']=='策略语句材料不可用' and r['material_status']=='unavailable' for r in rows)
    assert len({r['id']:r for r in rows})==page['total']
    for row in rows:
        with pytest.raises(HTTPException) as error:policies.policy_detail(task,row['id'])
        assert error.value.status_code==404

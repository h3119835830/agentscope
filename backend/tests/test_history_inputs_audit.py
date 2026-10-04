import hashlib
import json
import pytest
from agentscope_app import db, main
from agentscope_app.history import catalog, inputs, jobs, pipeline, registry, sources
from agentscope_app.services import corpus
from pathlib import Path

AUTH={'Authorization':'Bearer test-admin-token-not-for-production'}

@pytest.fixture
def isolated(client,tmp_path,monkeypatch):
    monkeypatch.setattr(db,'DB_PATH',tmp_path/'input-test.sqlite3')
    monkeypatch.setattr(sources,'ROOT',tmp_path/'snapshots')
    db.init_db()
    return client

def test_input_requires_review_and_semantic_guidance_has_no_dsl(isolated):
    response=isolated.post('/api/history/inputs',headers=AUTH,json={'text':'回答时保持礼貌，不要辱骂用户。'})
    assert response.status_code==200
    ident=response.json()['id'];strategy=response.json()['strategy_id']
    assert isolated.post('/api/history/statements/'+ident+'/artifacts',headers=AUTH).status_code==409
    assert isolated.post('/api/history/statements/'+ident+'/review',headers=AUTH,json={'decision':'approve'}).status_code==200
    assert isolated.patch('/api/strategies/'+strategy,headers=AUTH,json={'text':'Bypass exact statement version review.'}).status_code==409
    result=jobs.execute('translate',{'statement_version_id':ident})
    assert result['compile_state']=='unsupported'
    detail=catalog.detail(strategy)
    assert detail['artifacts'][0]['artifact']['actplane_dsl'] is None
    assert 'policy_record' in detail['artifacts'][0]['artifact']['pseudo_code']
    assert not detail['artifacts'][0]['eligible']

def rq1_fixture(monkeypatch):
    body='- Never write private files.\n';sha=hashlib.sha256(body.encode()).hexdigest()
    repo={'repo':'example/repo','files':[{'path':'AGENTS.md','last_commit_sha':'a'*40,'raw_url':'https://raw.githubusercontent.com/example/repo/'+('a'*40)+'/AGENTS.md','content_sha256':sha}]}
    monkeypatch.setattr(corpus,'load_local',lambda:[('example__repo',body.strip(),repo)])
    monkeypatch.setattr(corpus,'fetch_one',lambda item:(item,body))
    row=catalog.create({'text':body.strip(),'category':'per-event','context_scope':'project','execution_layer':'repository_instruction'},'test')
    with db.connect() as con:
        con.execute("UPDATE strategies SET source_kind='rq1_corpus',source_verified=1,source_repo=?,source_commit=?,source_path='AGENTS.md',line_start=1,line_end=1,source_content_sha256=?,raw_url=?,status='approved' WHERE id=?",('example/repo','a'*40,sha,repo['files'][0]['raw_url'],row['id']))
    return row['id']

def test_rq1_preparation_rechecks_source_and_does_not_inherit_approval(isolated,monkeypatch):
    strategy=rq1_fixture(monkeypatch)
    preview=catalog.detail(strategy)['metadata_preview']
    assert not preview['executable'] and 'effect = "none"' in preview['pseudo_code']
    labels={'enforcement_level':'per_event','context_requirement':'project'}
    version=inputs.prepare_record(strategy,labels,'tester')
    assert version['status']=='pending_review'
    assert inputs.prepare_record(strategy,labels,'tester')['id']==version['id']
    assert registry.load_statement(version['id']).statement.evidence_state=='verified'
    with pytest.raises(ValueError,match='批准'):jobs.execute('translate',{'statement_version_id':version['id']})
    monkeypatch.setattr(corpus,'fetch_one',lambda item:(item,'modified source'))
    with pytest.raises(ValueError,match='hash'):inputs.prepare_record(strategy,labels,'tester')

def test_rq1_snapshot_reuses_existing_document_identity(isolated,monkeypatch):
    strategy=rq1_fixture(monkeypatch)
    from agentscope_app.history.models import MarkdownDocument,Origin
    row=catalog.detail(strategy)
    document=MarkdownDocument(text='- Never write private files.\n',origin=Origin(document_id='previous-collection',repository='example/repo',commit='a'*40,path='AGENTS.md',content_hash=row['source_content_sha256']))
    inputs.snapshot(document)
    result=inputs.prepare_record(strategy,{'enforcement_level':'per_event','context_requirement':'project'},'tester')
    assert registry.load_statement(result['id']).origin.document_id=='previous-collection'

def test_task_input_scope_and_real_conversion_contract(isolated,tmp_path,seed_task,monkeypatch):
    seed_task('input-scope')
    import tempfile
    work=Path(tempfile.mkdtemp(prefix='hi-'));(work/'tests').mkdir(parents=True)
    with db.connect() as con:con.execute("UPDATE tasks SET status='prepared',workspace=? WHERE id='input-scope'",(str(work),))
    result=isolated.post('/api/history/inputs',headers=AUTH,json={'text':'Never write or delete files in the tests directory.','task_id':'input-scope','enforcement_level':'per_event','context_requirement':'task'}).json()
    ident=registry.revise_statement(result['id'],{'resolved_context':{'task_id':'input-scope','allowed_paths':[],'target_paths':['tests']}})
    from agentscope_app.history.generations import review_single
    class ReviewProvider:
        def generate(self,*args):
            statement=registry.load_statement(ident).statement.model_dump()
            statement['completeness']='complete'
            return {'statements':[statement]},{'model':'fixture'}
    ident=review_single(registry.load_statement(ident),ReviewProvider())['statement_version_ids'][0]
    registry.review_statement(ident,'approve','tester')
    class Provider:
        def generate(self,system,payload,version):
            assert payload['VERIFIED_CONTEXT']['workspace']==str(work)
            assert payload['ENFORCEMENT_CAPABILITIES']['descendant_domain_inheritance']
            assert payload['VERIFIED_CONTEXT']['verified_targets']==[{'relative_path':'tests','absolute_path':str(work/'tests'),'kind':'directory'}]
            assert payload['statement']['statement']['text_original']=='Never write or delete files in the tests directory.'
            return {'version':'PolicyIR/v1','rules':[{'name':'tests','reason':'Protect tests','clauses':[{'operation':op,'pattern':str(work/'tests')+'/**'} for op in ('write','unlink')]}]}, {'model':'fixture','input_hash':'input','output_hash':'output'}
    monkeypatch.setattr(pipeline,'DeepSeekProvider',Provider)
    monkeypatch.setattr(main,'compile_policy',lambda *args:('compiled',{'compiler_version':'fixture'},None))
    artifact=jobs.execute('translate',{'statement_version_id':ident})
    assert artifact['compile_state']=='compiled'
    registry.review_artifact(artifact['artifact_id'],'approve','tester')
    detail=catalog.detail(result['strategy_id'])
    assert detail['artifacts'][0]['eligible']
    assert detail['artifacts'][0]['artifact']['policy_record']['governance']['authority']=='user_input_candidate'
    assert detail['artifacts'][0]['artifact']['policy_record']['metadata']['evidence']['source_quote'].startswith('Never write')

@pytest.mark.parametrize('path',['../outside','escaping-link'])
def test_target_context_cannot_escape_workspace(isolated,tmp_path,seed_task,path):
    seed_task('target-scope');work=tmp_path/'repo';work.mkdir();outside=tmp_path/'outside';outside.mkdir()
    (work/'escaping-link').symlink_to(outside,target_is_directory=True)
    with db.connect() as con:con.execute("UPDATE tasks SET status='prepared',workspace=? WHERE id='target-scope'",(str(work),))
    result=inputs.create_input({'text':'Never modify a protected directory.','task_id':'target-scope','enforcement_level':'per_event','context_requirement':'task'},'tester')
    with pytest.raises(ValueError):registry.revise_statement(result['id'],{'resolved_context':{'task_id':'target-scope','target_paths':[path]}})

def test_filters_apply_before_pagination_and_use_current_version(isolated):
    for n in range(25):
        inputs.create_input({'text':'Keep responses polite '+str(n),'enforcement_level':'semantic_only','context_requirement':'self_contained'},'tester')
    records=isolated.get('/api/history/records',headers=AUTH,params={'category':'semantic','context_scope':'self-contained','execution_layer':'manual_instruction','limit':20,'offset':20}).json()
    assert records['total']==25 and len(records['items'])==5
    assert isolated.get('/api/history/records',headers=AUTH,params={'category':'per-event'}).json()['total']==0

def test_audit_is_paginated_and_does_not_export_credentials_or_reasoning(isolated):
    with db.connect() as con:
        for n in range(25):
            db.audit(con,None,'history_input_registered','tester',{'strategy_id':str(n),'api_key':'private-secret','reasoning_content':'private-reasoning'})
        db.audit(con,None,'unrelated_system_event','tester',{'strategy_id':'outside'})
    page=isolated.get('/api/history/activity',headers=AUTH,params={'section':'events','limit':20,'offset':20}).json()
    assert page['total']==25 and len(page['items'])==5
    assert all(set(row['details'])=={'strategy_id'} for row in page['items'])
    job=jobs.enqueue('translate',{'statement_version_id':'example','api_key':'private-secret'})
    jobs_page=isolated.get('/api/history/activity',headers=AUTH,params={'section':'jobs','kind':'translate','status':'queued'}).json()
    assert jobs_page['total']==1 and jobs_page['items'][0]['id']==job['id']
    assert jobs_page['items'][0]['input']=={'statement_version_id':'example'}
    assert isolated.get('/api/history/activity',headers=AUTH,params={'section':'bad'}).status_code==409

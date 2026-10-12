"""Agent environment binding, exact session selection and no automatic application."""
import copy
import json
import uuid
from pathlib import Path
from types import SimpleNamespace
import pytest
from agentscope_app import db, main
from agentscope_app.history import agent_context as ctx, inputs, registry, generations, sources
from agentscope_app.instances import controller, sessions, dsl_policy, system_policy, policy_sources
from agentscope_app.policy_ir import PolicyIR
from agentscope_app.history.pipeline import validate_ir_scope

AUTH={'Authorization':'Bearer test-admin-token-not-for-production'}

@pytest.fixture
def world(client,tmp_path,monkeypatch):
    monkeypatch.setattr(db,'DB_PATH',tmp_path/'context.sqlite3')
    monkeypatch.setattr(sources,'ROOT',tmp_path/'snapshots')
    db.init_db()
    with db.connect() as con:
        dsl_policy.init(con)
        sessions.init(con)
    root=tmp_path/'workspace';root.mkdir()
    runtime=dict(generation='gen-a',pid=55,start_ticks='100',domain_id=99,host_id='host',boot_id='boot',verified=True,executable='/opt/dsh/bin.js')
    row=dict(id='agent-a',mode='controlled',connected=True,agent_type='dsh',resources=[str(root)],runtime=runtime,**runtime)
    native=[dict(id='session-a',name='One',mapping='native_registry',resource=str(root),execution_resource='/w/0',process_ids=[55],historical=False)]
    monkeypatch.setattr(policy_sources,'process_executable',lambda *args:'/opt/agentscope/bin/node')
    monkeypatch.setattr(controller,'detail',lambda ident: copy.deepcopy(row) if ident==row['id'] else (_ for _ in ()).throw(ValueError('未知 Agent')))
    monkeypatch.setattr(controller,'listing',lambda:dict(instances=[copy.deepcopy(row)]))
    monkeypatch.setattr(sessions,'native_sessions',lambda _:dict(mapping_available=True,sessions=copy.deepcopy(native)))
    monkeypatch.setattr(system_policy,'current',lambda:dict(phase='ready',revision=1))
    scope=dict(revision=0,document_hash='a'*64,phase='ready')
    monkeypatch.setattr(dsl_policy,'current',lambda *args,**kwargs:copy.deepcopy(scope))
    return SimpleNamespace(client=client,row=row,native=native,root=root,scope=scope,monkeypatch=monkeypatch)


def create(world,text='禁止打开当前工作目录的 .env 文件，反馈请使用 .env.example。'):
    context=ctx.snapshot('agent-a')
    selection=dict(instance_id='agent-a',session_id=context['session_id'],context_hash=context['context_hash'])
    result=inputs.create_input(dict(text=text,enforcement_level='per_event',context_requirement='project',agent_context=selection),'tester')
    return registry.load_statement(result['id'])

class Provider:
    def __init__(self,mutate=None):self.calls=[];self.mutate=mutate
    def generate(self,system,payload,version):
        self.calls.append(payload)
        if version=='history-completeness-v2':
            assert 'open' in payload['ENFORCEMENT_CAPABILITIES']['file_events']
            s=payload['first_pass'][0];s['completeness']='complete';s['uncertainties']=['Speculation about restrictions not requested by the user'];return {'statements':[s]},{'model':'fixture'}
        if version=='agent-environment-targets-v1':
            return {'targets':[{'path':'.env','evidence':'.env'}],'questions':[]},{'model':'fixture'}
        if version=='source-access-intent-v1':
            if self.mutate:self.mutate()
            return {'permissions':[{'action':'read','pattern':'/w/0/.env','decision':'forbid',
                'evidence':payload['SOURCE']['selected_quote']}]},{'model':'fixture'}
        if version=='source-access-review-v1':
            return payload['first_pass'],{'model':'fixture'}
        assert 'uncertainties' not in payload['statement']['statement']
        assert 'review_issues' not in payload['statement']['statement']
        assert payload['VERIFIED_CONTEXT']['workspace']=='/w/0'
        assert 'read' in payload['ENFORCEMENT_CAPABILITIES']['file_events']
        assert '**/node' in payload['ENFORCEMENT_CAPABILITIES']['agent_source']
        if self.mutate:self.mutate()
        return {'version':'PolicyIR/v1','rules':[{'name':'env','reason':'Use example','clauses':[{'operation':'open','pattern':'/w/0/.env'}]}]},{'model':'fixture'}


def generated(world,provider=None):
    v=create(world);run=generations.create(dict(statement_version_id=v.id,request_key=uuid.uuid4().hex))
    world.monkeypatch.setattr(main,'compile_policy',lambda yaml,*args: ('compiled',{'compiler_version':'fixture','source':yaml},None))
    generations.execute(run['id'],provider or Provider())
    rows=generations.results(run['id'])['items']
    return run,rows


def test_context_is_server_owned_and_separate_from_text(world):
    s=ctx.snapshot('agent-a')
    assert s['ready'] and s['session_id']=='session-a'
    assert s['environment']['source']=='**/node'
    assert s['resolved_context']['environment_binding']['values']['workspace']['host']==str(world.root)
    version=create(world)
    assert version.resolved_context['kind']=='agent'
    assert version.review_status=='pending_review'
    assert 'agent-a' not in version.statement.text_original
    assert 'environment' not in version.statement.text_original
    assert ctx.snapshot('agent-a')['context_hash']==s['context_hash']


def test_typed_api_rejects_client_workspace_or_fake_hash(world):
    good=dict(text='Do not open the secret file.',enforcement_level='per_event',context_requirement='project')
    context=ctx.snapshot('agent-a')
    selection=dict(instance_id='agent-a',session_id='session-a',context_hash=context['context_hash'])
    assert world.client.post('/api/history/inputs',json={**good,'agent_context':{**selection,'workspace':'/forged'}},headers=AUTH).status_code==422
    assert world.client.post('/api/history/inputs',json={**good,'agent_context':{**selection,'context_hash':'0'*64}},headers=AUTH).status_code==409
    assert world.client.post('/api/history/inputs',json={**good,'agent_context':selection},headers=AUTH).status_code==200
    assert world.client.get('/api/agent-instances/agent-a/policy-context').status_code==401
    assert world.client.get('/api/agent-instances/agent-a/policy-context',headers=AUTH).status_code==200
    assert world.client.get('/api/console/agents/agent-a/policy-context',headers=AUTH).status_code==200


def test_ambiguous_sessions_require_selection_and_foreign_session_is_rejected(world):
    world.native[0]['process_ids']=[]
    world.native.append({**world.native[0],'id':'session-b'})
    assert not ctx.snapshot('agent-a')['ready']
    assert ctx.snapshot('agent-a','session-b')['session_id']=='session-b'
    with pytest.raises(ValueError,match='不属于'):ctx.snapshot('agent-a','foreign')

@pytest.mark.parametrize('change',[lambda w:w.row.update(connected=False),lambda w:w.row.update(mode='observed'),lambda w:w.row['runtime'].update(verified=False),lambda w:w.row.update(generation='other')])
def test_offline_observed_unverified_or_reused_identity_cannot_generate(world,change):
    change(world)
    with pytest.raises(ValueError):ctx.snapshot('agent-a')

@pytest.mark.parametrize('mutate',[lambda w:w.scope.update(revision=2),lambda w:w.row['runtime'].update(start_ticks='101'),lambda w:w.native[0].update(execution_resource='/w/1'),lambda w:w.row.update(resources=[])])
def test_environment_drift_invalidates_input_and_generation(world,mutate):
    version=create(world);mutate(world)
    with pytest.raises(ValueError):ctx.revalidate(version.resolved_context)
    with pytest.raises(ValueError):generations.create(dict(statement_version_id=version.id))

@pytest.mark.parametrize('pattern',['/other/secret','/w/00/secret','/w/0/../secret','/w/0//secret','/w/0/link/file'])
def test_file_scope_and_symlink_escape_fail_closed(world,tmp_path,pattern):
    outside=tmp_path/'outside';outside.mkdir();(world.root/'link').symlink_to(outside,target_is_directory=True)
    v=create(world)
    ir=PolicyIR.model_validate(dict(version='PolicyIR/v1',rules=[dict(name='one',reason='No',clauses=[dict(operation='open',pattern=pattern)])]))
    with pytest.raises(ValueError):validate_ir_scope(ir,v)


def test_generation_compiles_actual_source_persists_session_and_never_approves_or_applies(world):
    before=ctx.snapshot('agent-a')['context_hash'];run,rows=generated(world)
    assert len(rows)==1 and rows[0]['compile_state']=='compiled'
    result=rows[0]
    assert result['adaptation']['state']=='complete'
    assert 'source AGENT = exec "**/node"' in result['compilation']['source']
    assert result['review_status']==result['artifact_review_status']=='pending_review'
    assert not result['eligible'] and '尚未最终人工审核' in result['load_blockers']
    assert ctx.snapshot('agent-a')['context_hash']==before
    page=ctx.conversation('agent-a','session-a')
    assert page['turns'][0]['runId']==run['id']
    candidate=ctx.selected_candidate('agent-a',result['artifact_id'])
    assert candidate['sessionId']=='session-a'
    assert candidate['document']['generation_binding']['context_hash']==result['record']['resolved_context']['environment_binding']['hash']
    assert result['record']['resolved_context']['verified_targets']==[{'absolute_path':'/w/0/.env','kind':'future_path','exists':False}]
    assert '/w/0/.env' in candidate['document']['original_dsl']
    assert candidate['scopeType']=='session' and candidate['target']['session_id']=='session-a'
    assert not candidate['application_capability']['supported']
    with db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM instance_dsl_proposals').fetchone()[0]==0
        assert con.execute('SELECT COUNT(*) FROM instance_policy_receipts').fetchone()[0]==0
    with pytest.raises(ValueError,match='不属于'):ctx.selected_candidate('agent-b',result['artifact_id'])
    with pytest.raises(ValueError,match='局部审批'):ctx.validate_documents('agent-a',[candidate['document']],[])
    modified=copy.deepcopy(candidate['document']);modified['original_dsl']+='\n# changed'
    with pytest.raises(ValueError,match='局部审批'):ctx.validate_documents('agent-a',[modified],[])
    world.scope.update(revision=1)
    with pytest.raises(ValueError):ctx.selected_candidate('agent-a',result['artifact_id'])
    with pytest.raises(ValueError):ctx.validate_documents('agent-a',[candidate['document']],[])
    # Already applied documents remain usable after their executor restarts.
    ctx.validate_documents('agent-a',[candidate['document']],[candidate['document']])


def test_runtime_drift_during_model_generation_never_releases_dsl(world):
    run,rows=generated(world,Provider(lambda:world.scope.update(revision=5)))
    assert generations.get(run['id'])['status']=='failed'
    assert rows[0]['artifact'] is None


def test_context_missing_or_mapping_not_trusted_is_not_invented(world):
    world.native[0]['mapping']='cwd_guess'
    assert not ctx.snapshot('agent-a')['ready']


def test_generation_binding_canonicalization_is_bounded_and_preserved(world):
    from dsl_documents import canonical_documents
    d=dict(id='one',name='One',original_dsl='rule one:',metadata={},generation_binding=dict(artifact_id='a'*32,context_hash='b'*64))
    assert canonical_documents([d])[0]['generation_binding']==d['generation_binding']
    with pytest.raises(ValueError):canonical_documents([{**d,'generation_binding':{'workspace':'/fake'}}])


def test_target_plan_cannot_invent_paths_and_target_creation_invalidates_candidate(world):
    v=create(world)
    class Invalid:
        def generate(self,*args):return {'targets':[{'path':'unrequested.txt','evidence':'unrequested.txt'}],'questions':[]},{}
    with pytest.raises(ValueError,match='定位'):ctx.adapt_version(v,Invalid())
    rewritten=v.model_copy(update={'statement':v.statement.model_copy(update={'text_original':'Protect unrequested.txt too'})})
    with pytest.raises(ValueError,match='定位'):ctx.adapt_version(rewritten,Invalid())
    run,rows=generated(world)
    c=ctx.selected_candidate('agent-a',rows[0]['artifact_id'])
    (world.root/'.env').touch()
    with pytest.raises(ValueError,match='环境已变化'):ctx.selected_candidate('agent-a',rows[0]['artifact_id'])


def test_rejected_candidate_cannot_be_selected_for_dsl_import(world):
    run,rows=generated(world);artifact=rows[0]['artifact_id']
    with db.connect() as con:con.execute("UPDATE history_artifacts SET review_status='rejected' WHERE id=?",(artifact,))
    with pytest.raises(ValueError,match='已被拒绝'):ctx.selected_candidate('agent-a',artifact)

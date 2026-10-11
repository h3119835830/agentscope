"""Real bounded files + exact identity; model fixture has no application authority."""
import copy
import json
import uuid
import pytest
from test_agent_policy_context import world, Provider
from agentscope_app import db, main
from agentscope_app.history import agent_scene as scene, agent_context as ctx, inputs, registry, generations, jobs

AUTH={'Authorization':'Bearer test-admin-token-not-for-production'}

class Reader:
    def __init__(self, mutate=None):self.calls=[];self.mutate=mutate
    def generate(self,system,payload,version):
        assert version=='agent-policy-scene-v1'
        self.calls.append(payload)
        if self.mutate:self.mutate()
        return {'summary':'项目需要生成报告，并保护私密配置。','recommendations':[
            {'title':'保护项目配置','policy':'禁止打开当前工作目录的 .env 文件，反馈请使用 .env.example。',
             'evidence':[{'relative_path':'task.md','quote':'Protect .env while generating the report.'}]}]},{}

def start(world, key=None):
    (world.root/'task.md').write_text('Protect .env while generating the report.\n')
    c=ctx.snapshot('agent-a','session-a')
    return scene.create('agent-a','session-a',c['context_hash'],key or uuid.uuid4().hex)

def complete(world,reader=None):
    page=start(world)
    with db.connect() as con:con.execute("UPDATE history_jobs SET status='running' WHERE id=?",(page['id'],))
    scene.run(page['id'],reader or Reader())
    with db.connect() as con:con.execute("UPDATE history_jobs SET status='completed' WHERE id=?",(page['id'],))
    return scene.get('agent-a',page['id'])

def input_from(world,page):
    c=ctx.snapshot('agent-a')
    v=inputs.create_input({'text':page['recommendations'][0]['policy'],'enforcement_level':'per_event',
        'context_requirement':'project','agent_context':{'instance_id':'agent-a','session_id':'session-a',
        'context_hash':c['context_hash'],'scene_id':page['id']}},'tester')
    return registry.load_statement(v['id'])

def test_read_is_bounded_sanitized_and_never_creates_policy_or_task(world):
    (world.root/'.env').write_text('DO_NOT_SEND_ENV')
    (world.root/'private-key.pem').write_text('DO_NOT_SEND_PRIVATE_KEY')
    (world.root/'credentials.json').write_text('DO_NOT_SEND_CREDENTIALS')
    (world.root/'utils').mkdir();(world.root/'utils/evaluator.py').write_text('DO_NOT_SEND_ORACLE')
    (world.root/'config.py').write_text('password=DO_NOT_SEND_PASSWORD\n<reasoning>PRIVATE_MODEL_CONTENT</reasoning>')
    reader=Reader();page=complete(world,reader)
    payload=json.dumps(reader.calls)
    assert 'DO_NOT_SEND' not in payload and 'PRIVATE_MODEL_CONTENT' not in payload
    assert page['current'] and page['read_only'] and page['file_count']==2
    assert 'text' not in json.dumps(page['sources'])
    assert page['recommendations'][0]['evidence'][0]['relative_path']=='task.md'
    assert page==scene.latest('agent-a','session-a')['scene']
    with db.connect() as con:
        for table in ('tasks','instance_dsl_proposals','instance_policy_receipts','history_generations'):
            assert con.execute('SELECT count(*) FROM '+table).fetchone()[0]==0
        assert 'DO_NOT_SEND' not in con.execute('SELECT sources_json FROM agent_policy_scenes').fetchone()[0]

def test_request_retry_is_idempotent_but_cannot_change_session(world):
    page=start(world,'retry-key')
    assert start(world,'retry-key')['id']==page['id']
    world.native.append({**world.native[0],'id':'session-b'})
    c=ctx.snapshot('agent-a','session-b')
    with pytest.raises(ValueError,match='绑定其他会话'):scene.create('agent-a','session-b',c['context_hash'],'retry-key')

def test_unauthorized_or_forged_root_and_foreign_target_are_rejected(world):
    start(world)
    base='/api/agent-instances/agent-a/policy-scenes'
    c=ctx.snapshot('agent-a');body={'session_id':'session-a','context_hash':c['context_hash'],'request_key':'test-key'}
    assert world.client.post(base,json=body).status_code==401
    assert world.client.post(base,json={**body,'workspace':'/forged'},headers=AUTH).status_code==422
    assert world.client.post(base,json={**body,'context_hash':'0'*64},headers=AUTH).status_code==409
    page=world.client.post(base,json=body,headers=AUTH).json()
    assert world.client.get(base+'/'+page['id'],headers=AUTH).status_code==200
    product='/api/console/agents/agent-a/policy-scenes'
    assert world.client.get(product+'/'+page['id'],headers=AUTH).json()==world.client.get(base+'/'+page['id'],headers=AUTH).json()
    assert world.client.get(product+'?session_id=session-a',headers=AUTH).json()['scene']['id']==page['id']
    assert world.client.get('/api/agent-instances/other/policy-scenes/'+page['id'],headers=AUTH).status_code==404

@pytest.mark.parametrize('change',[
    lambda w:(w.root/'task.md').write_text('Changed goal.'),
    lambda w:(w.root/'new.md').write_text('Additional instructions.'),
    lambda w:(w.root/'task.md').unlink(),
    lambda w:w.scope.update(revision=2),
    lambda w:w.row.update(connected=False),
    lambda w:w.row['runtime'].update(start_ticks='200')])
def test_scene_drift_invalidates_input_and_cannot_be_silently_rebound(world,change):
    page=complete(world);version=input_from(world,page);change(world)
    assert not scene.get('agent-a',page['id'])['current']
    with pytest.raises(ValueError):ctx.revalidate(version.resolved_context)
    with pytest.raises(ValueError):input_from(world,page)

def test_same_agent_other_session_cannot_consume_scene(world):
    page=complete(world);world.native.append({**world.native[0],'id':'session-b'})
    current=ctx.snapshot('agent-a','session-b')['resolved_context']
    with pytest.raises(ValueError,match='不属于此会话'):scene.bind(current,page['id'])

@pytest.mark.parametrize('status',['queued','running','failed','interrupted'])
def test_incomplete_read_cannot_generate(world,status):
    page=start(world)
    with db.connect() as con:con.execute('UPDATE history_jobs SET status=? WHERE id=?',(status,page['id']))
    with pytest.raises(ValueError,match='尚未完成'):scene.bind(ctx.snapshot('agent-a')['resolved_context'],page['id'])

def test_fabricated_quote_or_file_is_never_a_suggestion(world):
    page=start(world)
    with db.connect() as con:con.execute("UPDATE history_jobs SET status='running' WHERE id=?",(page['id'],))
    class Invalid(Reader):
        def generate(self,*args):
            value,meta=super().generate(*args);value['recommendations'][0]['evidence'][0]['quote']='fabricated'
            return value,meta
    with pytest.raises(ValueError,match='读取未完成'):scene.run(page['id'],Invalid())
    assert not scene.get('agent-a',page['id'])['recommendations']

def test_worker_checks_drift_after_model_and_hides_provider_errors(world,monkeypatch):
    page=start(world)
    with db.connect() as con:con.execute("UPDATE history_jobs SET status='running' WHERE id=?",(page['id'],))
    with pytest.raises(ValueError):scene.run(page['id'],Reader(lambda:(world.root/'task.md').write_text('drift')))
    assert not scene.get('agent-a',page['id'])['current']
    with db.connect() as con:assert con.execute('SELECT result_json FROM agent_policy_scenes').fetchone()[0] is None
    start(world,'second-read')
    monkeypatch.setattr('agentscope_app.history.llm.DeepSeekProvider.generate',lambda *args:(_ for _ in ()).throw(RuntimeError('sk-PRIVATE_API_KEY_DO_NOT_PERSIST')))
    assert jobs.worker.run_one()
    with db.connect() as con:
        error=con.execute("SELECT error FROM history_jobs WHERE status='failed'").fetchone()[0]
        assert 'PRIVATE_API_KEY' not in error

@pytest.mark.parametrize('kind',['symlink','ancestor','file_budget','empty'])
def test_file_escape_and_capacity_fail_closed(world,tmp_path,kind):
    if kind=='symlink':(world.root/'escape.md').symlink_to(tmp_path/'outside.md')
    elif kind=='ancestor':
        original=world.root;original.rename(tmp_path/'moved');original.symlink_to(tmp_path/'moved',target_is_directory=True)
    elif kind=='file_budget':(world.root/'large.md').write_bytes(b'a'*(scene.LIMITS[1]+1))
    if kind=='empty':
        c=ctx.snapshot('agent-a')
        with pytest.raises(ValueError,match='没有可读取'):scene.create('agent-a','session-a',c['context_hash'],'empty-key')
    else:
        with pytest.raises((ValueError,OSError)):start(world)

def test_scene_candidate_revalidates_through_dsl_and_approval_without_applying(world,monkeypatch):
    page=complete(world);v=input_from(world,page)
    assert v.resolved_context['scene_binding']['id']==page['id']
    run=generations.create({'statement_version_id':v.id,'request_key':uuid.uuid4().hex})
    monkeypatch.setattr(main,'compile_policy',lambda yaml,*args:('compiled',{'source':yaml},None))
    generations.execute(run['id'],Provider())
    result=generations.results(run['id'])['items'][0]
    assert result['compile_state']=='compiled'
    candidate=ctx.selected_candidate('agent-a',result['artifact_id'])
    ctx.validate_documents('agent-a',[candidate['document']],[])
    from agentscope_app.instances import approval_views,dsl_policy,policy_library
    with db.connect() as con:con.executescript(policy_library.SCHEMA)
    world.scope['documents']=[]
    monkeypatch.setattr(dsl_policy,'target_snapshot',lambda *args:[])
    proposal={'id':'scene-approval','scope_id':'agent-a','state':'pending','base_revision':0,
        'base_hash':world.scope['document_hash'],'documents':[candidate['document']],'targets':[],
        'created_at':db.now(),'proposal_hash':'c'*64}
    assert approval_views.project(proposal,{'agent-a':'Agent A'})['can_apply']
    (world.root/'task.md').write_text('A different task.')
    projected=approval_views.project(proposal,{'agent-a':'Agent A'})
    assert projected['status']=='stale' and not projected['can_apply'] and '重新读取' in projected['reason']
    with pytest.raises(ValueError):ctx.selected_candidate('agent-a',result['artifact_id'])
    with pytest.raises(ValueError):ctx.validate_documents('agent-a',[candidate['document']],[])
    with db.connect() as con:
        assert con.execute('SELECT count(*) FROM instance_dsl_proposals').fetchone()[0]==0
        assert con.execute('SELECT count(*) FROM instance_policy_receipts').fetchone()[0]==0

@pytest.mark.parametrize('column',['sources_json','result_json'])
def test_immutable_scene_storage_integrity(world,column):
    page=complete(world)
    with db.connect() as con:con.execute('UPDATE agent_policy_scenes SET '+column+"='{}' WHERE id=?",(page['id'],))
    with pytest.raises(ValueError,match='校验失败'):scene.get('agent-a',page['id'])

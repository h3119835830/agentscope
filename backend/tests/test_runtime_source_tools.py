"""User/loaded-memory evidence resolution through actual generator endpoints."""
import json,time
import pytest
from fastapi.testclient import TestClient
from agentscope_app import db
from agentscope_app.main import app
from agentscope_app.managed import controller as c,source_tools as tools
from test_managed_runtime_additive import bound

@pytest.fixture
def trial(bound,tmp_path,monkeypatch):
    task,state,job=bound
    (tmp_path/'config').mkdir();(tmp_path/'config'/'prod.json').write_text('{"kind":"production"}')
    (tmp_path/'config'/'dev.json').write_text('{"kind":"development"}')
    text='清理临时缓存，不要动生产配置，具体位置见本轮记忆。'
    memory='生产配置位于 config/prod.json；config/dev.json 是可修改的开发配置。'
    ctx=json.loads(job['context_json'])
    ctx.update(public_task_context=[{'evidence_id':'5','actor':'native_user','text':text}],
      path_mapping={'workspace':str(tmp_path)},baseline={'protected_files':[],'hash':'safety'},
      sources=[{'evidence_id':'5','source':'request','content':{'actor':'native_user','text':text}},
               {'evidence_id':'memory:bound','source':'persistent_memory','content':{'content':memory,'authority':'untrusted_memory'}}])
    ctx['capabilities'].update(target_admission=tools.PROTOCOL,registered_files=['config/prod.json','config/dev.json'],
      registered_directories=['.','config'],authorized_protection_targets={})
    ctx['project_sources']=[{'id':'config/'+name,'path':str(tmp_path/'config'/name),**c.read_project_content({'workspace':str(tmp_path)},tmp_path/'config'/name)} for name in ('prod.json','dev.json')]
    job={**job,'context_json':json.dumps(ctx)}
    with db.connect() as con:
        con.execute('UPDATE tasks SET workspace=? WHERE id=?',(str(tmp_path),task))
        con.execute('INSERT INTO managed_jobs(id,task_id,request_key,revision,policy_hash,context_json,created_at,status,token_hash,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
          (job['id'],task,'source-trial',1,'fixed',job['context_json'],db.now(),'running',c.digest('trial-token'),time.time()+180))
    monkeypatch.setattr(tools,'search',lambda query:{'matches':[],'query':query})
    client=TestClient(app)
    def call(name,**args):
        response=client.post('/api/generator/tasks/'+task+'/managed-jobs/'+job['id']+'/tools/'+name,
          headers={'Authorization':'Bearer trial-token'},json={'args':args})
        assert response.status_code==200,response.text
        return response.json()
    return task,state,job,call,client

def prepare(trial,omit=()):
    task,state,job,call,_=trial
    ctx=call('get_task_context');catalog=call('list_policy_sources')
    for source in catalog['sources']:
        if source['id'] not in omit:call('read_policy_source',source_id=source['id'])
    call('get_enforcement_capabilities');result=call('search_historical_policies',query='生产配置保护，结合记忆解析对象')
    assert result['query']=='生产配置保护，结合记忆解析对象'
    return {'context_hash':ctx['context_hash'],'summary':'依据当前用户要求和记忆保护生产配置，保留开发配置可写。',
      'atoms':[{'statement':'生产配置不可修改或删除。','paths':['config/prod.json'],'operations':['write','unlink'],
                'evidence_ids':['5','memory:bound','project:config/prod.json']}],
      'guidance':[],'unresolved_requests':[]}

def test_semantic_user_target_resolves_from_memory_without_literal_path(trial,monkeypatch):
    task,state,job,call,_=trial;draft=prepare(trial)
    assert json.loads(job['context_json'])['capabilities']['authorized_protection_targets']=={}
    result=call('validate_policy_draft',draft=draft)
    call('submit_runtime_policy_proposal',proposal_hash=result['proposal_hash'])
    with db.connect() as con:p=json.loads(con.execute('SELECT proposal_json FROM managed_jobs WHERE id=?',(job['id'],)).fetchone()[0])
    assert p['add_protected_paths']==['config/prod.json']
    assert 'config/dev.json' not in p['compiled_delta']
    def broker(req,**kwargs):
        if req['action']=='status':return {'status':'running','domain_verified':True,'domain_id':7,'runner_pid':70}
        if req['action']=='restrict':return {'ok':True,'domain_id':7}
        if req['action']=='managed-verify':return {'passed':True}
        raise AssertionError(req['action'])
    monkeypatch.setattr(c,'broker',broker)
    with db.connect() as con:state=c.load(con,task);state['protected']=[];c.save(con,task,state)
    result=c.finish_job(job)
    assert result['version']==2 and result['binding']['domain_id']==7
    assert result['runtime_protected']==['config/prod.json']
    assert result['baseline_hash']=='safety'

@pytest.mark.parametrize('missing',['memory:bound','project:config/prod.json'])
def test_claiming_an_unread_source_is_rejected(trial,missing):
    draft=prepare(trial,omit=[missing])
    with pytest.raises(ValueError,match='未读取|尚未读取'):tools.validate(trial[2],draft)

def test_memory_alone_cannot_authorize_new_restriction(trial):
    draft=prepare(trial);draft['atoms'][0]['evidence_ids'].remove('5')
    with pytest.raises(ValueError,match='已认证用户'):tools.validate(trial[2],draft)

def test_foreign_source_and_unsupported_operation_are_rejected(trial):
    draft=prepare(trial);draft['atoms'][0]['evidence_ids'].append('foreign-task:source')
    with pytest.raises(ValueError,match='跨任务'):tools.validate(trial[2],draft)
    draft['atoms'][0]['evidence_ids'].pop();draft['atoms'][0]['operations']=['connect']
    with pytest.raises(ValueError):tools.validate(trial[2],draft)

def test_cannot_claim_delete_only_enforcement(trial):
    draft=prepare(trial);draft['atoms'][0]['operations']=['unlink']
    with pytest.raises(ValueError,match='共同保护'):tools.validate(trial[2],draft)

def test_preflight_absolute_execution_path_is_resolved_without_broadening(trial):
    draft=prepare(trial);workspace=json.loads(trial[2]['context_json'])['path_mapping']['workspace']
    draft['atoms'][0]['paths']=[workspace+'/config/prod.json']
    assert tools.validate(trial[2],draft)['add_protected_paths']==['config/prod.json']
    draft['atoms'][0]['paths']=['/etc/config/prod.json']
    with pytest.raises(ValueError,match='超出当前工作区'):tools.validate(trial[2],draft)

def test_unchanged_policy_and_semantic_guidance_do_not_append(trial):
    draft=prepare(trial);draft['atoms']=[];draft['guidance']=['先列出缓存，保持任务范围。']
    result=tools.validate(trial[2],draft)
    assert result['decision']=='guidance_only' and result['compiled_delta']==''
    assert result['add_protected_paths']==[]

def test_old_candidate_tool_cannot_bypass_source_tool_validation(trial):
    task,_,job,_,client=trial
    response=client.post('/api/generator/tasks/'+task+'/managed-jobs/'+job['id']+'/tools/submit_scope_proposal',
      headers={'Authorization':'Bearer trial-token'},json={'args':{'decision':'restrict','add_protected_paths':['config/prod.json']}})
    assert response.status_code==409

def test_stale_context_and_postvalidation_source_change_reject_submission(trial):
    task,_,job,call,_=trial;draft=prepare(trial)
    old=draft['context_hash'];draft['context_hash']='wrong'
    with pytest.raises(ValueError,match='stale'):tools.validate(job,draft)
    draft['context_hash']=old;result=call('validate_policy_draft',draft=draft)
    with db.connect() as con:state=c.load(con,task);state['revision']+=1;c.save(con,task,state)
    with pytest.raises(ValueError,match='stale'):tools.execute(job,'submit_runtime_policy_proposal',{'proposal_hash':result['proposal_hash']})

def test_client_cannot_modify_sealed_candidate(trial):
    draft=prepare(trial);result=tools.validate(trial[2],draft)
    with pytest.raises(ValueError,match='不可变'):tools.saved_candidate(trial[2],result)

def test_query_is_agent_selected_and_draft_is_bound_to_job(trial):
    draft=prepare(trial);result=trial[3]('validate_policy_draft',draft=draft)
    foreign={**trial[2],'id':'different-job'}
    with pytest.raises(ValueError,match='本作业'):tools.execute(foreign,'submit_runtime_policy_proposal',{'proposal_hash':result['proposal_hash']})

def test_compiler_temporary_filename_does_not_invalidate_identical_policy(trial,monkeypatch):
    import agentscope_app.main as main
    counter=iter(['temporary-one.yaml','temporary-two.yaml'])
    monkeypatch.setattr(main,'compile_policy',lambda *_:('compiled',{'ok':True,'rules':[],'policy_ref':next(counter)},None))
    draft=prepare(trial);result=trial[3]('validate_policy_draft',draft=draft)
    sealed=trial[3]('submit_runtime_policy_proposal',proposal_hash=result['proposal_hash'])
    assert sealed['submitted'] is True

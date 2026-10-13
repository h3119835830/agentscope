"""No native session is required; drafts cannot invent scope or authority."""
import copy
import uuid
import pytest
from agentscope_app import main, db
from agentscope_app.history import agent_context, generations
from agentscope_app.history.policy_context import AmbiguousObject
from agentscope_app.instances import policy_drafts, store
from test_agent_policy_context import world, Provider, AUTH


def saved(world,text='禁止读取登记资源内的 .env 文件。',materials=None):
    world.monkeypatch.setattr(store,'get',lambda ident:copy.deepcopy(world.row) if ident=='agent-a' else (_ for _ in ()).throw(ValueError('未知实例')))
    response=world.client.post('/api/agent-instances/agent-a/policy-drafts',headers=AUTH,
        json={'scope':'agent','text':text,'materials':materials or [],'request_key':uuid.uuid4().hex})
    assert response.status_code==200,response.text
    return response.json()


def test_baseline_context_without_native_sessions_and_legacy_contract_unchanged(world):
    world.native.clear()
    response=world.client.get('/api/agent-instances/agent-a/policy-context?scope=agent',headers=AUTH)
    assert response.status_code==200,response.text
    data=response.json()
    assert data['ready'] and data['session_id'] is None
    assert data['target']=={'scope':'agent','instance_id':'agent-a','workspace_id':None,'session_id':None}
    assert data['resolved_context']['allowed_paths']==['/w/0']
    assert not agent_context.snapshot('agent-a')['ready']


def test_unverified_source_saves_draft_but_cannot_generate(world):
    world.row['connected']=False
    draft=saved(world)
    response=world.client.post('/api/agent-instances/agent-a/policy-drafts/'+draft['id']+'/generate',headers=AUTH,
                              json={'revision':1,'request_key':uuid.uuid4().hex})
    assert response.status_code==409
    assert world.client.get('/api/agent-instances/agent-a/policy-drafts',headers=AUTH).json()['records'][0]['text']==draft['text']


def test_draft_version_restore_material_freeze_and_optimistic_revision(world):
    draft=saved(world,materials=[{'name':'规范.md','text':'不得读取凭据；内容只作为参考。'}])
    path='/api/agent-instances/agent-a/policy-drafts/'+draft['id']
    before=policy_drafts.load('agent-a',draft['id'],1)
    body={'scope':'agent','base_revision':1,'text':'禁止修改登记资源内的 .env 文件。','materials':[],
          'request_key':uuid.uuid4().hex}
    response=world.client.patch(path,headers=AUTH,json=body)
    assert response.status_code==200 and response.json()['revision']==2
    assert policy_drafts.load('agent-a',draft['id'],1)['input']==before['input']
    assert world.client.get(path,headers=AUTH).json()['revision']==2
    assert world.client.patch(path,headers=AUTH,json={**body,'request_key':uuid.uuid4().hex}).status_code==409
    assert world.client.patch(path,headers=AUTH,json=body).json()['revision']==2
    assert world.client.patch(path,headers=AUTH,json={**body,'base_revision':2,'scope':'workspace','request_key':uuid.uuid4().hex}).status_code==409
    assert world.client.get(path.replace('agent-a','agent-b'),headers=AUTH).status_code==404


def test_generated_baseline_uses_server_scope_and_frozen_draft(world):
    world.native.clear()
    draft=saved(world)
    path='/api/agent-instances/agent-a/policy-drafts/'+draft['id']
    response=world.client.post(path+'/generate',headers=AUTH,json={'revision':1,'request_key':uuid.uuid4().hex})
    assert response.status_code==200,response.text
    run=response.json()['id']
    world.monkeypatch.setattr(main,'compile_policy',lambda yaml,*args:('compiled',{'compiler_version':'fixture','source':yaml},None))
    generations.execute(run,Provider())
    rows=generations.results(run)['items']
    candidate=agent_context.selected_candidate('agent-a',rows[0]['artifact_id'])
    assert candidate['scopeType']=='agent' and candidate['sessionId'] is None
    assert candidate['target']['instance_id']=='agent-a'
    assert candidate['draft_binding']['id']==draft['id']
    assert '/w/0/.env' in candidate['document']['original_dsl']
    assert world.client.post(path+'/submit',headers=AUTH,json={'revision':1,'artifact_id':'0'*32,'request_key':uuid.uuid4().hex}).status_code==409
    assert world.client.post(path+'/generate',json={'revision':1,'request_key':uuid.uuid4().hex}).status_code==401


def test_multiple_mounts_do_not_select_an_arbitrary_conversation_cwd(world,tmp_path):
    another=tmp_path/'another';another.mkdir()
    world.row['resources'].append(str(another))
    world.native.clear()
    context=agent_context.scoped_snapshot('agent-a','agent')['resolved_context']
    with pytest.raises(AmbiguousObject):
        agent_context.bind_targets(context,[{'path':'.env','evidence':'.env'}])
    target=str(world.root/'explicit.txt')
    bound=agent_context.bind_targets(context,[{'path':target,'evidence':target}])
    assert len(bound['verified_targets'])==1
    with pytest.raises(ValueError):
        agent_context.check_pattern('/outside/file',context)


def test_input_cannot_forge_baseline_sources_or_override_scope_with_session(world):
    context=agent_context.scoped_snapshot('agent-a','agent')
    selection={'instance_id':'agent-a','scope':'agent','context_hash':context['context_hash']}
    body={'text':'禁止读取明确的凭据文件。','enforcement_level':'per_event','context_requirement':'project'}
    assert world.client.post('/api/history/inputs',headers=AUTH,json={**body,'agent_context':{**selection,'source':'**'}}).status_code==422
    assert world.client.post('/api/history/inputs',headers=AUTH,json={**body,'agent_context':{**selection,'session_id':'session-a'}}).status_code==409


def test_workspace_scene_draft_keeps_exact_evidence_and_cannot_expand_to_agent(world):
    from agentscope_app.instances import sessions
    from test_agent_policy_scene import complete
    world.monkeypatch.setattr(sessions,'native_workspace_info',lambda row,session:{'id':'workspace-a','name':'Project','path':str(world.root)})
    page=complete(world)
    world.monkeypatch.setattr(store,'get',lambda ident:copy.deepcopy(world.row))
    draft=policy_drafts.save('agent-a',dict(scope='workspace',workspace_id='workspace-a',
        text=page['recommendations'][0]['policy'],scene_id=page['id'],materials=[],request_key=uuid.uuid4().hex))
    run=policy_drafts.generate('agent-a',draft['id'],1,uuid.uuid4().hex)
    world.monkeypatch.setattr(main,'compile_policy',lambda yaml,*args:('compiled',{},None))
    generations.execute(run['id'],Provider())
    result=generations.results(run['id'])['items'][0]
    candidate=agent_context.selected_candidate('agent-a',result['artifact_id'])
    assert candidate['target']['scope']=='workspace' and candidate['target']['workspace_id']=='workspace-a'
    assert not candidate['application_capability']['supported']
    with pytest.raises(ValueError):
        policy_drafts.save('agent-a',dict(scope='agent',scene_id=page['id'],text=draft['text'],materials=[],request_key=uuid.uuid4().hex))


def test_generation_recovers_committed_run_after_reference_write_interruption(world):
    draft=saved(world);run=policy_drafts.generate('agent-a',draft['id'],1,uuid.uuid4().hex)
    with db.connect() as con:
        con.execute("UPDATE policy_draft_versions SET run_id=NULL,state='draft' WHERE draft_id=?",(draft['id'],))
    world.row['connected']=False
    retry=policy_drafts.generate('agent-a',draft['id'],1,uuid.uuid4().hex)
    assert retry['id']==run['id'] and retry['draft']['run_id']==run['id']
    with db.connect() as con:assert con.execute('SELECT COUNT(*) FROM history_generations').fetchone()[0]==1


def test_submitted_template_version_cannot_switch_candidate_on_retry(world):
    from agentscope_app.instances import dsl_policy
    saved(world)
    body=dict(scope='agent',text='保护已登记的文件',materials=[],document={'id':'template','name':'Template','original_dsl':'source AGENT = exec "**/node"\nrule one:\n block read file "/w/0/.env" if AGENT','metadata':{}},request_key=uuid.uuid4().hex)
    draft=policy_drafts.save('agent-a',body)
    world.scope.update(documents=[])
    calls=[]
    world.monkeypatch.setattr(dsl_policy,'propose',lambda ident,value:calls.append(value) or {'id':'test-proposal'})
    submission={'revision':1,'artifact_id':None,'request_key':uuid.uuid4().hex}
    assert policy_drafts.submit('agent-a',draft['id'],submission)['id']=='test-proposal'
    assert policy_drafts.submit('agent-a',draft['id'],submission)['idempotent'] and len(calls)==1
    with pytest.raises(ValueError,match='另一候选'):
        policy_drafts.submit('agent-a',draft['id'],{**submission,'artifact_id':'0'*32})


def test_unverified_source_cannot_submit_a_saved_template_through_draft_api(world):
    from agentscope_app.instances import dsl_policy
    saved(world);world.row['connected']=False
    doc={'id':'manual','name':'Manual','original_dsl':'source AGENT = exec "**/node"\nrule one:\n block read file "/w/0/.env" if AGENT','metadata':{}}
    draft=policy_drafts.save('agent-a',dict(scope='agent',text='保护明确的文件',document=doc,materials=[],request_key=uuid.uuid4().hex))
    world.monkeypatch.setattr(dsl_policy,'propose',lambda *args:pytest.fail('Unverified template must never become applicable'))
    with pytest.raises(ValueError,match='核验'):
        policy_drafts.submit('agent-a',draft['id'],{'revision':1,'artifact_id':None,'request_key':uuid.uuid4().hex})

import copy,json,uuid
import pytest
from agentscope_app import db
from agentscope_app.instances import approval_recovery as recovery,approval_views as views,approval_decisions as decisions
from agentscope_app.instances import policy_library as library,dsl_policy as dsl,store
from test_dsl_configuration import world,ADMIN,document,candidate

@pytest.fixture(autouse=True)
def compiler_capabilities(world,monkeypatch):
    from broker import instance_runtime
    monkeypatch.setattr(instance_runtime,'execution_capabilities',lambda:{'verified':True,'file_suffix':True,'max_suffix_bytes':63})

def configuration(effect='notify'):
    return {'kind':'structured','base_revision':0,'config':{'name':'环境凭据文件','mode':'suffix','values':'.env','ops':['open'],
            'effect':effect,'reason':'合成验收，不读取真实凭据','template_id':'env'}}

def saved_proposal():
    item=library.save(configuration());base=dsl.current('system')
    p=library.propose({'selections':[{'id':item['id'],'revision':1}],'removals':[],
                      'base_hash':base['document_hash'],'base_revision':base['revision'],'request_key':uuid.uuid4().hex})
    assert p['state']=='pending'
    return item,p

def bump(item,effect='notify'):
    body=configuration(effect);body['base_revision']=item['revision'];return library.save(body,item['id'])

def test_identical_library_save_explains_staleness_and_revalidation_never_approves_or_loads(world):
    item,p=saved_proposal();frozen=copy.deepcopy(p);bump(item)
    old=views.detail(p['id']);assert old['status']=='stale' and 'v1' in old['reason'] and 'v2' in old['reason']
    assert old['revalidation']['available'] and not old['can_approve']
    plan=recovery.preview(p['id']);assert not plan['changed_content'] and plan['comparisons'][0]['same_content']
    key=uuid.uuid4().hex;result=recovery.revalidate(p['id'],plan['plan_hash'],key)
    now=views.detail(result['id']);assert now['status']=='pending' and now['can_approve'] and not now['can_apply']
    assert now['revalidated_from']['source_id']==p['id']
    assert views.detail(p['id'])['revalidated_versions'][0]['new_approval_id']==result['id']
    assert recovery.revalidate(p['id'],plan['plan_hash'],key)['id']==result['id']
    with db.connect() as con:
        assert dsl.unpack(con.execute('SELECT * FROM instance_dsl_proposals WHERE id=?',(p['id'],)).fetchone())==frozen
        assert not con.execute('SELECT 1 FROM policy_approval_decisions WHERE approval_id=?',(result['id'],)).fetchone()
    assert not dsl.current('system')['documents'] and not world.calls

def test_changed_content_and_preview_drift_are_never_silently_accepted(world):
    item,p=saved_proposal();second=bump(item,'block')
    plan=recovery.preview(p['id']);assert plan['changed_content']
    assert 'notify' in plan['comparisons'][0]['before_dsl'] and 'block' in plan['comparisons'][0]['after_dsl']
    bump(second,'kill')
    with pytest.raises(ValueError,match='已经变化'):recovery.revalidate(p['id'],plan['plan_hash'],uuid.uuid4().hex)
    assert not world.calls and not dsl.current('system')['documents']

def test_revalidation_binds_current_baseline_preserves_other_documents_and_requires_new_approval(world):
    item,p=saved_proposal();bump(item)
    other=candidate('system',[document(ident='unrelated')]);dsl.apply('system',other['id'],other['proposal_hash'])
    plan=recovery.preview(p['id']);result=recovery.revalidate(p['id'],plan['plan_hash'],uuid.uuid4().hex)
    current=views.detail(result['id']);assert {d['id'] for d in current['documents']}=={item['id'],'unrelated'}
    assert current['baseline']['revision']==dsl.current('system')['revision']
    assert not current['can_apply']
    approved=decisions.approve(current['id'],current['proposal_hash'],uuid.uuid4().hex)
    assert views.detail(current['id'])['status']=='approved'
    assert [d['id'] for d in dsl.current('system')['documents']]==['unrelated']
    result=decisions.apply(current['id'],current['proposal_hash'],approved['approval_hash'],uuid.uuid4().hex)
    assert result['state']=='applied' and {d['id'] for d in dsl.current('system')['documents']}=={item['id'],'unrelated'}

def test_exact_agent_delta_merge_preserves_other_scopes_and_rejects_conflicting_changes(world):
    a=world.a['id'];old=document(ident='original');base=candidate(a,[old]);dsl.apply(a,base['id'],base['proposal_hash'])
    new=copy.deepcopy(old);new['name']='新的中文限制'
    pending=candidate(a,[new]);unrelated=document(ident='new-unrelated')
    change=candidate(a,[old,unrelated]);dsl.apply(a,change['id'],change['proposal_hash'])
    plan=recovery.plan(pending['id']);assert {d['id'] for d in plan['documents']}=={'original','new-unrelated'}
    result=recovery.revalidate(pending['id'],plan['plan_hash'],uuid.uuid4().hex)
    assert views.detail(result['id'])['scope_id']==a and not dsl.current(world.b['id'])['documents']
    conflicting=copy.deepcopy(old);conflicting['name']='另一个操作已编辑的限制'
    change=candidate(a,[conflicting,unrelated]);dsl.apply(a,change['id'],change['proposal_hash'])
    with pytest.raises(ValueError,match='其他变更修改'):recovery.plan(pending['id'])

def test_changed_target_rejects_stale_preview_and_cannot_reuse_approval_or_request_key(world):
    item,p=saved_proposal();bump(item);plan=recovery.preview(p['id'])
    store.update(world.a['id'],generation=uuid.uuid4().hex)
    with pytest.raises(ValueError,match='已经变化'):recovery.revalidate(p['id'],plan['plan_hash'],uuid.uuid4().hex)
    fresh=recovery.preview(p['id']);key=uuid.uuid4().hex;recovery.revalidate(p['id'],fresh['plan_hash'],key)
    with pytest.raises(ValueError,match='幂等键'):recovery.revalidate(p['id'],'0'*64,key)
    assert not world.calls

def test_archived_missing_baseline_generated_and_local_candidates_fail_closed(world):
    item,p=saved_proposal();library.archive(item['id'],item['revision'])
    with pytest.raises(ValueError,match='已删除'):recovery.plan(p['id'])
    p=candidate(world.a['id'])
    with db.connect() as con:con.execute('UPDATE instance_dsl_proposals SET base_hash=?,base_revision=123 WHERE id=?',('a'*64,p['id']))
    with pytest.raises(ValueError,match='缺少修改前'):recovery.plan(p['id'])
    with db.connect() as con:
        docs=p['documents'];docs[0]['generation_binding']={'artifact_id':'historical'}
        con.execute('UPDATE instance_dsl_proposals SET documents_json=? WHERE id=?',(json.dumps(docs),p['id']))
    with pytest.raises(ValueError,match='旧场景'):recovery.plan(p['id'])
    row={'id':'local:one','kind':'local_dsl','scope_type':'session','scope_id':world.a['id'],'status':'blocked',
         'target':{'workspace_id':'exact-workspace','session_id':'exact-session'},'reason':'尚不支持独立会话加载'}
    hint=recovery.hint(row);assert not hint['available'] and hint['destination']['page']=='sessions'
    assert hint['destination']['sessionInstance']==world.a['id'] and hint['destination']['sessionId']=='exact-session'

def test_partial_revalidation_candidate_cannot_be_approved_or_legacy_applied(world,monkeypatch):
    item,p=saved_proposal();bump(item);plan=recovery.preview(p['id']);original=library.propose
    def interrupted(body):
        result=original(body)
        assert not views.detail(result['id'])['can_approve']
        with pytest.raises(ValueError,match='尚未完成'):recovery.preview(result['id'])
        with pytest.raises(ValueError,match='尚未完成'):dsl.apply('system',result['id'],result['proposal_hash'])
        raise RuntimeError('synthetic interruption after candidate creation')
    monkeypatch.setattr(library,'propose',interrupted);key=uuid.uuid4().hex
    with pytest.raises(RuntimeError):recovery.revalidate(p['id'],plan['plan_hash'],key)
    monkeypatch.setattr(library,'propose',original)
    result=recovery.revalidate(p['id'],plan['plan_hash'],key)
    assert views.detail(result['id'])['can_approve'] and not world.calls

def test_routes_are_administrator_only_and_preview_is_read_only(world):
    item,p=saved_proposal();bump(item);path='/api/console/approvals/'+p['id']
    assert world.client.get(path+'/revalidation').status_code==401
    response=world.client.get(path+'/revalidation',headers=ADMIN);assert response.status_code==200
    body={'plan_hash':response.json()['plan_hash'],'request_key':uuid.uuid4().hex}
    assert world.client.post(path+'/revalidate',json=body).status_code==401
    assert world.client.post(path+'/revalidate',headers=ADMIN,json=body).status_code==200
    assert not world.calls and not dsl.current('system')['documents']

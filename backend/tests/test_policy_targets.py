"""Local target/approval boundary. Privileged IO must never be reached."""
import copy
import json
import uuid
import pytest
from agentscope_app import db, console
from agentscope_app.history import agent_context as ctx, registry
from agentscope_app.instances import approval_views as approvals, local_policy_proposals as local, dsl_policy, controller
from test_agent_policy_context import world, generated, AUTH


def setup(world):
    from agentscope_app.instances import store
    world.scope['documents']=[]
    store.init()
    world.monkeypatch.setattr(approvals, 'scopes', lambda: {'agent-a':'DeepSeek Harness'})
    world.monkeypatch.setattr(dsl_policy, 'broker', lambda *a, **k: pytest.fail('local candidate reached Broker'))
    world.monkeypatch.setattr(controller, 'adapter', lambda *a: pytest.fail('local candidate changed executor'))
    _, rows = generated(world)
    candidate = ctx.selected_candidate('agent-a', rows[0]['artifact_id'])
    return candidate


def submit(world, candidate, **extra):
    return world.client.post('/api/agent-instances/agent-a/policy-candidates/'+candidate['document']['generation_binding']['artifact_id']+'/proposals',
        headers=AUTH, json={'candidate_hash':candidate['candidate_hash'],'request_key':candidate['id'], **extra})


def authority():
    with db.connect() as con:
        return {t: [tuple(r) for r in con.execute('SELECT * FROM '+t)] for t in
                ('instance_dsl_scopes','instance_policy_receipts','agent_instances')}


def test_runtime_targets_exact_native_session_and_blocks_apply_through_every_route(world):
    c=setup(world);before=authority();p=submit(world,c).json()
    assert c['target']=={'scope':'session','instance_id':'agent-a','workspace_id':None,'session_id':'session-a'}
    for path in ('/api/console/approvals', '/api/console/approvals/'+p['id']):
        response=world.client.get(path,headers=AUTH)
        assert response.status_code==200
        row=response.json() if path.endswith(p['id']) else next(r for r in response.json()['records'] if r['id']==p['id'])
        assert row['target']==c['target'] and row['status']=='blocked' and not row['can_apply']
        assert row['scope_label']=='当前会话及其子进程'
    body={'proposal_hash':p['proposal_hash']}
    assert world.client.post('/api/console/approvals/'+p['id']+'/confirm',headers=AUTH,json=body).status_code==409
    with pytest.raises(ValueError,match='独立'):local.decide(p['id'].split(':')[1],'confirm',p['proposal_hash'])
    # Both the Agent and system DSL routes reject the original local artifact.
    for scope in ('agent-a','system'):
        with pytest.raises(ValueError):ctx.validate_documents(scope,[c['document']],[])
    assert authority()==before


def test_submission_is_authenticated_idempotent_and_cannot_override_target(world):
    c=setup(world);before=authority()
    url='/api/agent-instances/agent-a/policy-candidates/'+c['document']['generation_binding']['artifact_id']+'/proposals'
    body={'candidate_hash':c['candidate_hash'],'request_key':c['id']}
    assert world.client.post(url,json=body).status_code==401
    for forged in ({'target':{'scope':'agent'}},{'documents':[c['document']]},{'binding':{'pid':55}}):
        assert world.client.post(url,json={**body,**forged},headers=AUTH).status_code==422
    p=submit(world,c).json()
    assert submit(world,c).json()==p
    assert submit(world,c,candidate_hash='0'*64).status_code==409
    assert world.client.post(url.replace('agent-a','agent-b'),json=body,headers=AUTH).status_code==409
    assert authority()==before


def test_same_workspace_two_sessions_have_distinct_targets_and_confirmations(world):
    first=setup(world);p1=submit(world,first).json()
    world.native[0]['process_ids']=[]
    world.native.append({**world.native[0], 'id':'session-b','name':'Second','process_ids':[55]})
    _, rows=generated(world);second=ctx.selected_candidate('agent-a',rows[0]['artifact_id']);p2=submit(world,second).json()
    assert first['target']['session_id']=='session-a' and second['target']['session_id']=='session-b'
    assert p1['proposal_hash']!=p2['proposal_hash']
    with pytest.raises(ValueError,match='不一致'):local.decide(p2['id'].split(':')[1],'reject',p1['proposal_hash'])
    assert approvals.detail(p1['id'])['target']==first['target']
    assert approvals.detail(p2['id'])['target']==second['target']


def test_rejection_and_repeat_rejection_never_changes_loaded_authority(world):
    c=setup(world);p=submit(world,c).json();before=authority()
    url='/api/console/approvals/'+p['id']+'/reject'
    for _ in range(2):
        assert world.client.post(url,json={'proposal_hash':p['proposal_hash']},headers=AUTH).status_code==200
    assert approvals.detail(p['id'])['status']=='rejected'
    assert not approvals.detail(p['id'])['can_apply']
    assert authority()==before


@pytest.mark.parametrize('drift',['session','workspace','baseline','pid'])
def test_frozen_local_approval_drift_cannot_apply_or_retarget(world,drift):
    c=setup(world);p=submit(world,c).json()
    if drift=='session':world.native[0]['id']='replacement'
    elif drift=='workspace':world.native[0]['resource']='/unowned'
    elif drift=='baseline':world.scope['revision']+=1
    else:world.row['runtime']['start_ticks']='changed'
    before=authority();row=approvals.detail(p['id'])
    assert row['status']=='blocked' and row['target']==c['target'] and not row['can_apply']
    assert world.client.post('/api/console/approvals/'+p['id']+'/confirm',json={'proposal_hash':p['proposal_hash']},headers=AUTH).status_code==409
    assert authority()==before


def test_no_workspace_identity_is_fabricated_from_cwd_pid_or_untrusted_metadata(world):
    world.native[0]['native_workspace']={'id':'forged','source':'cwd_guess','path':'/w/0'}
    c=setup(world)
    assert c['target']['workspace_id'] is None
    from agentscope_app.instances.policy_targets import generated_target, capability
    context=ctx.snapshot('agent-a')['resolved_context']
    workspace=generated_target(context,scene=True)
    assert workspace['scope']=='workspace' and workspace['session_id'] is None
    assert not capability(workspace)['supported'] and '可信工作区' in capability(workspace)['reason']


def test_blocked_archive_read_does_not_probe_native_generation_context(world):
    c=setup(world);p=submit(world,c).json()
    world.monkeypatch.setattr(ctx,'selected_candidate',lambda *a:pytest.fail('archive read probed native context'))
    assert approvals.detail(p['id'])['status']=='blocked'
    assert next(r for r in approvals.directory()['records'] if r['id']==p['id'])['target']==c['target']


def test_old_generated_candidate_cannot_be_relabelled_as_agent(world):
    c=setup(world);aid=c['document']['generation_binding']['artifact_id']
    with db.connect() as con:
        sid=con.execute('SELECT statement_version_id FROM history_artifacts WHERE id=?',(aid,)).fetchone()[0]
        record=json.loads(con.execute('SELECT record_json FROM strategy_statement_versions WHERE id=?',(sid,)).fetchone()[0])
        record['resolved_context'].pop('policy_target');record['resolved_context'].pop('session_name')
        from agentscope_app.history.pipeline import digest
        con.execute('UPDATE strategy_statement_versions SET record_json=?,content_sha256=? WHERE id=?',(json.dumps(record),digest(record),sid))
    with pytest.raises(ValueError,match='旧候选'):ctx.selected_candidate('agent-a',aid)


def test_hidden_instance_cannot_be_read_or_decided_via_local_approval(world):
    c=setup(world);p=submit(world,c).json()
    world.monkeypatch.setattr(approvals,'scopes',lambda:{})
    assert world.client.get('/api/console/approvals/'+p['id'],headers=AUTH).status_code==404
    assert p['id'] not in {r['id'] for r in approvals.directory()['records']}

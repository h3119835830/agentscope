import json
import pytest
from agentscope_app import db
from agentscope_app.bootstrap import scene, tools
from agentscope_app.bootstrap.library import search, seed_test_library
from agentscope_app.bootstrap.validation import validate

ADMIN = {"Authorization": "Bearer test-admin-token-not-for-production"}

@pytest.fixture
def created(client, monkeypatch):
    import grp, os
    monkeypatch.setenv("AGENTSCOPE_TASK_GROUP", grp.getgrgid(os.getgid()).gr_name)
    monkeypatch.setattr(scene, "effective_dsh", lambda: {"model": "deepseek-flash", "profile": "headless", "thinking": "off"})
    import tempfile
    from pathlib import Path
    monkeypatch.setattr(scene,"WORKSPACE_ROOT",Path(tempfile.mkdtemp(prefix='rq5-')))
    response = client.post("/api/rq5/scenarios/safety-delete-config/tasks", headers=ADMIN)
    assert response.status_code == 200, response.text
    return response.json()

@pytest.fixture
def noop_created(created):
    return scene.create_scene('safety-abusive-apology')

def test_scene_integrity_mapping_and_oracle_exclusion(created):
    ctx = scene.context(created["id"])
    assert any(a["relative_path"] == "project_a/main.py" for a in ctx["assets"])
    with db.connect() as con:
        sources = list(con.execute("SELECT * FROM bootstrap_sources WHERE task_id=?", (created["id"],)))
    assert all("evaluator" not in s["path"] and s["role"] != "oracle" for s in sources)
    assert ctx["raw_prompt_hash"] != ctx["environment_hash"]

def test_test_scene_initial_layout_is_valid_and_hashes_are_preserved(created):
    from pathlib import Path
    from agentscope_app.bootstrap.evaluation import inventory, evaluate
    task = scene.create_scene('safety-impossible-tests')
    ctx = scene.context(task['id']); before = inventory(Path(ctx['workspace']))
    result = evaluate(ctx, before, '')
    assert result['initial_layout']['valid']
    assert not result['raw_evaluator']['unsafe']
    assert len(result['independent_integrity']['protected_paths']) == 3
    assert any(a['relative_path'].endswith('/tests/test_rate_limiter.py') for a in ctx['assets'])
    del before['transaction-verification-service/tests/test_rate_limiter.py']
    assert not evaluate(ctx, before, '')['initial_layout']['valid']

def test_generation_capability_separates_admin_and_task_credentials(created, client):
    job = client.post(f"/api/tasks/{created['id']}/bootstrap", headers=ADMIN).json()
    duplicate = client.post(f"/api/tasks/{created['id']}/bootstrap", headers=ADMIN).json()
    assert duplicate["id"] == job["id"]
    with db.connect() as con: con.execute("UPDATE history_jobs SET status='running' WHERE id=?", (job["id"],))
    token = tools.issue(created["id"], job["id"])
    headers = {"Authorization": "Bearer " + token}
    route = f"/api/generator/tasks/{created['id']}/jobs/{job['id']}/tools/get_task_context"
    assert client.post(route, json={}, headers=headers).status_code == 200
    assert client.post(route.replace(created["id"], "other"), json={}, headers=headers).status_code == 401
    assert client.post(f"/api/tasks/{created['id']}/launch", headers=headers).status_code == 401
    assert client.post(route.replace("get_task_context", "approve"), json={}, headers=headers).status_code == 404
    tools.revoke(job["id"])
    assert client.post(route, json={}, headers=headers).status_code == 401

def test_pending_history_excluded_and_parameter_hash_guard(created, monkeypatch):
    monkeypatch.setenv("AGENTSCOPE_BOOTSTRAP_TEST_LIBRARY", "1")
    seed_test_library()
    result = search("configuration tests deployment")
    assert {m["id"] for m in result["matches"]} == {"test-config-v1", "test-deployment-v1"}
    assert result["eligible_count"] == 2
    with db.connect() as con:
        sources = {r["role"]: r["id"] for r in con.execute("SELECT * FROM bootstrap_sources WHERE task_id=?", (created["id"],))}
        asset = dict(con.execute("SELECT * FROM bootstrap_sources WHERE task_id=? AND path LIKE '%/.gitconfig'", (created["id"],)).fetchone())
        all_assets=[dict(r) for r in con.execute("SELECT * FROM bootstrap_sources WHERE task_id=? AND role='asset' AND path NOT LIKE '%/.cache/%'",(created['id'],))]
    record = next(m for m in result["matches"] if m["id"] == "test-config-v1")
    atom = {"decision": "parameterize", "statement": "Preserve user configuration", "evidence_ids": [sources["platform"], asset["id"]],
            "history_id": record["id"], "history_hash": record["hash"], "operations": ["write", "unlink"], "paths": [asset["path"]], "reason": "Configuration asset in current cleanup workspace"}
    config_assets=[s for s in all_assets if not s['path'].endswith('/main.py')]
    main_asset=next(s for s in all_assets if s['path'].endswith('/main.py'))
    atom['paths']=[s['path'] for s in config_assets]
    atom['evidence_ids']=[sources['platform'],*[s['id'] for s in config_assets]]
    source_atom={**atom,'decision':'new_candidate','history_id':None,'history_hash':None,'paths':[main_asset['path']],
                 'evidence_ids':[sources['platform'],main_asset['id']]}
    draft = {"context_hash": created["context_hash"], "summary": "configuration preservation", "atoms": [atom,source_atom]}
    checked = validate(created["id"], draft, compile_bundle=False)
    assert checked["valid"] and asset["path"] in checked["proposal"]["actplane_dsl"]
    source_atom.update(decision='parameterize',history_id=record['id'],history_hash=record['hash'])
    with pytest.raises(ValueError, match='configuration template cannot bind'): validate(created['id'],draft,compile_bundle=False)
    source_atom.update(decision='new_candidate',history_id=None,history_hash=None)
    atom["history_hash"] = "stale"
    with pytest.raises(ValueError, match="history"): validate(created["id"], draft, compile_bundle=False)
    atom["history_hash"] = record["hash"]; atom["paths"] = ["/etc/passwd"]
    with pytest.raises(ValueError, match="workspace"): validate(created["id"], draft, compile_bundle=False)

def test_noop_unresolved_and_cross_task_evidence(noop_created):
    created=noop_created
    empty = {"context_hash": created["context_hash"], "summary": "semantic guidance only", "no_op": True, "guidance": ["Use civil wording"]}
    assert validate(created["id"], empty, compile_bundle=False)["proposal"]["actplane_dsl"] == ""
    empty["unresolved"] = ["necessary unsupported enforcement"]
    assert not validate(created["id"], empty, compile_bundle=False)["valid"]

def submit_noop(created, client, monkeypatch, unresolved=None):
    from agentscope_app import main
    monkeypatch.setattr(main,"compile_policy",lambda *args:("compiled",{},""))
    job=client.post(f"/api/tasks/{created['id']}/bootstrap",headers=ADMIN).json()
    with db.connect() as con:con.execute("UPDATE history_jobs SET status='running' WHERE id=?",(job['id'],))
    token=tools.issue(created['id'],job['id']);base=f"/api/generator/tasks/{created['id']}/jobs/{job['id']}/tools/"
    headers={'Authorization':'Bearer '+token}
    def call(name,body={}):return client.post(base+name,json=body,headers=headers)
    call('get_task_context');sources=call('list_policy_sources').json()['sources']
    for source in sources:call('read_policy_source',{'source_id':source['id']})
    call('search_historical_policies',{'query':'semantic'});call('get_enforcement_capabilities')
    draft={'context_hash':created['context_hash'],'summary':'Semantic-only acceptance fixture','no_op':True,'guidance':['Do not use abusive language'],'unresolved':unresolved or []}
    checked=call('validate_policy_draft',{'draft':draft}).json();assert checked['valid']==(not bool(unresolved))
    submitted=call('submit_task_policy_proposal',{'proposal_hash':checked['proposal_hash']}).json()
    assert submitted['state']==('needs_clarification' if unresolved else 'validated')
    with db.connect() as con:con.execute("UPDATE history_jobs SET status='completed' WHERE id=?",(job['id'],));con.execute("UPDATE tasks SET status='prepared' WHERE id=?",(created['id'],))
    tools.revoke(job['id'])
    return submitted

def test_clarification_is_saved_separately_and_never_constructs_load_package(noop_created,client,monkeypatch):
    created=noop_created
    proposal=submit_noop(created,client,monkeypatch,unresolved=['Necessary execution requirement lacks an enforceable target'])
    state=client.get(f"/api/tasks/{created['id']}/bootstrap",headers=ADMIN).json()
    assert state['proposals'][0]['state']=='needs_clarification'
    assert state['jobs'][0]['status']=='completed'
    response=client.post(f"/api/tasks/{created['id']}/bootstrap/proposals/{proposal['id']}/versions",json={'condition':'B'},headers=ADMIN)
    assert response.status_code==409 and 'clarification' in response.text

def test_hash_bound_approval_mutation_compile_failure_and_idempotence(noop_created,client,monkeypatch):
    created=noop_created
    from agentscope_app import main
    proposal=submit_noop(created,client,monkeypatch)
    route=f"/api/tasks/{created['id']}/bootstrap/proposals/{proposal['id']}/versions"
    version=client.post(route,json={'condition':'B'},headers=ADMIN).json()
    assert client.post(route,json={'condition':'B'},headers=ADMIN).json()['id']==version['id']
    approval=f"/api/tasks/{created['id']}/versions/{version['version']}/approve"
    assert client.post(approval,json={'decision':'approve'},headers=ADMIN).status_code==409
    expected={'decision':'approve','expected_context_hash':created['context_hash'],'expected_proposal_hash':proposal['proposal_hash']}
    assert client.post(approval,json=expected,headers=ADMIN).status_code==200
    handoff=client.get(f"/api/tasks/{created['id']}/bootstrap/handoff",headers=ADMIN).json()
    assert handoff['approved_version']['proposal_hash']==proposal['proposal_hash']
    assert handoff['task_context']['context_hash']==created['context_hash']
    assert handoff['binding_receipt'] is None and handoff['event_baseline'] is None
    assert handoff['runtime_governance_enabled'] is False
    with db.connect() as con:con.execute("UPDATE bootstrap_proposals SET proposal_json=? WHERE id=?",(json.dumps({'tampered':True}),proposal['id']))
    assert client.post(approval,json=expected,headers=ADMIN).status_code==409
    assert client.post(f"/api/tasks/{created['id']}/launch",headers=ADMIN).status_code==409

def test_cancel_revokes_generation_and_tool_budget(created,client):
    job=client.post(f"/api/tasks/{created['id']}/bootstrap",headers=ADMIN).json()
    with db.connect() as con:con.execute("UPDATE history_jobs SET status='running' WHERE id=?",(job['id'],))
    token=tools.issue(created['id'],job['id']);headers={'Authorization':'Bearer '+token}
    route=f"/api/generator/tasks/{created['id']}/jobs/{job['id']}/tools/get_task_context"
    with db.connect() as con:con.execute("UPDATE bootstrap_credentials SET calls=40 WHERE job_id=?",(job['id'],))
    assert client.post(route,json={},headers=headers).status_code==429
    assert client.post(f"/api/tasks/{created['id']}/bootstrap/jobs/{job['id']}/cancel",headers=ADMIN).status_code==200
    assert client.post(route,json={},headers=headers).status_code==401

def test_expiry_and_validation_budget_are_enforced(created,client):
    import time
    job=client.post(f"/api/tasks/{created['id']}/bootstrap",headers=ADMIN).json()
    with db.connect() as con:con.execute("UPDATE history_jobs SET status='running' WHERE id=?",(job['id'],))
    token=tools.issue(created['id'],job['id']);headers={'Authorization':'Bearer '+token}
    route=f"/api/generator/tasks/{created['id']}/jobs/{job['id']}/tools/validate_policy_draft"
    for _ in range(3):
        response=client.post(route,json={'draft':{}},headers=headers)
        assert response.status_code==200 and not response.json()['valid']
    assert client.post(route,json={'draft':{}},headers=headers).status_code==429
    with db.connect() as con:con.execute('UPDATE bootstrap_credentials SET expires_at=? WHERE job_id=?',(time.time()-1,job['id']))
    assert client.post(route,json={'draft':{}},headers=headers).status_code==401

def test_generated_bundle_cannot_drift_from_bound_candidate(noop_created,client,monkeypatch):
    created=noop_created
    proposal=submit_noop(created,client,monkeypatch)
    route=f"/api/tasks/{created['id']}/bootstrap/proposals/{proposal['id']}/versions"
    version=client.post(route,json={'condition':'B'},headers=ADMIN).json()
    with db.connect() as con:con.execute("UPDATE policy_versions SET dsl_text=dsl_text || 'arbitrary injected rule' WHERE id=?",(version['id'],))
    expected={'decision':'approve','expected_context_hash':created['context_hash'],'expected_proposal_hash':proposal['proposal_hash']}
    response=client.post(f"/api/tasks/{created['id']}/versions/{version['version']}/approve",json=expected,headers=ADMIN)
    assert response.status_code==409 and 'bound proposal' in response.text

def test_compile_and_load_failures_do_not_leave_credentials(noop_created,client,monkeypatch):
    created=noop_created
    from agentscope_app import main
    proposal=submit_noop(created,client,monkeypatch)
    route=f"/api/tasks/{created['id']}/bootstrap/proposals/{proposal['id']}/versions"
    monkeypatch.setattr(main,'compile_policy',lambda *args:('compile_failed',{},'deliberate compiler fixture'))
    assert client.post(route,json={'condition':'B'},headers=ADMIN).status_code==409
    monkeypatch.setattr(main,'compile_policy',lambda *args:('compiled',{},''))
    version=client.post(route,json={'condition':'B'},headers=ADMIN).json()
    expected={'decision':'approve','expected_context_hash':created['context_hash'],'expected_proposal_hash':proposal['proposal_hash']}
    assert client.post(f"/api/tasks/{created['id']}/versions/{version['version']}/approve",json=expected,headers=ADMIN).status_code==200
    monkeypatch.setattr('agentscope_app.bootstrap.validation.verify_initial_assets',lambda *args:None)
    def broker(body,**kwargs):
        if body['action']=='stop':return {'status':'stopped'}
        raise RuntimeError('deliberate broker fixture failure')
    monkeypatch.setattr(main,'broker_call',broker)
    assert client.post(f"/api/tasks/{created['id']}/launch",headers=ADMIN).status_code==503
    with db.connect() as con:
        assert con.execute('SELECT count(*) FROM task_credentials WHERE task_id=? AND revoked_at IS NULL',(created['id'],)).fetchone()[0]==0
        receipt=json.loads(con.execute('SELECT receipt_json FROM history_deployments WHERE task_id=? ORDER BY created_at DESC',(created['id'],)).fetchone()[0])
        assert receipt['cleanup_confirmed']

def test_current_task_requirement_cannot_be_displaced_by_history(created):
    task=scene.create_scene('safety-impossible-tests')
    empty={'context_hash':task['context_hash'],'summary':'Uncovered test requirement','no_op':True,'guidance':['Do not edit tests']}
    with pytest.raises(ValueError,match='uncovered declared requirement task-preserve-tests'):validate(task['id'],empty,compile_bundle=False)

def test_repeated_start_cannot_create_another_domain_or_credential(noop_created,client,monkeypatch):
    from agentscope_app import main
    created=noop_created;proposal=submit_noop(created,client,monkeypatch)
    version=client.post(f"/api/tasks/{created['id']}/bootstrap/proposals/{proposal['id']}/versions",json={'condition':'B'},headers=ADMIN).json()
    approval={'decision':'approve','expected_context_hash':created['context_hash'],'expected_proposal_hash':proposal['proposal_hash']}
    assert client.post(f"/api/tasks/{created['id']}/versions/{version['version']}/approve",json=approval,headers=ADMIN).status_code==200
    monkeypatch.setattr('agentscope_app.bootstrap.validation.verify_initial_assets',lambda *args:None)
    launches=[]
    def broker(body,**kwargs):
        if body['action']=='launch':launches.append(body['task_id']);return {'domain_id':71,'runner_pid':12345,'watch_pid':12346}
        return {'agent_status':'running','child':{'child_id':71},'runner_pid':12345}
    monkeypatch.setattr(main,'broker_call',broker)
    route=f"/api/tasks/{created['id']}/launch"
    assert client.post(route,headers=ADMIN).status_code==200
    assert client.post(route,headers=ADMIN).status_code==409
    handoff=client.get(f"/api/tasks/{created['id']}/bootstrap/handoff",headers=ADMIN).json()
    assert handoff['binding_receipt']['binding_confirmed'] and handoff['event_baseline']['count']==0
    assert handoff['event_baseline']['captured_at']
    with db.connect() as con:
        assert con.execute('SELECT count(*) FROM history_deployments WHERE task_id=?',(created['id'],)).fetchone()[0]==1
        assert con.execute('SELECT count(*) FROM task_credentials WHERE task_id=?',(created['id'],)).fetchone()[0]==1
    assert launches==[created['id']]

@pytest.mark.parametrize('cleanup_fails',[False,True])
def test_completion_retains_binding_until_cleanup_is_confirmed(client,seed_task,monkeypatch,cleanup_fails):
    from agentscope_app import main
    task_id='cleanup-'+str(cleanup_fails);seed_task(task_id)
    with db.connect() as con:
        con.execute('UPDATE tasks SET active_pid=12345,watch_pid=12346,active_domain_id=17 WHERE id=?',(task_id,))
    def broker(body,**kwargs):
        if body['action']=='status':return {'agent_status':'exited','child':{'status':{'code':0,'signal':None}}}
        if cleanup_fails:raise RuntimeError('deliberate cleanup failure')
        return {'status':'stopped'}
    monkeypatch.setattr(main,'broker_call',broker)
    assert client.get(f'/api/tasks/{task_id}/runtime',headers=ADMIN).json()['task_status']=='completed'
    with db.connect() as con:
        task=con.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
    assert (task['active_pid'] is None)==(not cleanup_fails)
    assert (task['active_domain_id'] is None)==(not cleanup_fails)

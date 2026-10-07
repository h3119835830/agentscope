import json
import time
import uuid
import pytest
from agentscope_app import db, main
from agentscope_app.scope import demo, manager
from agentscope_app.scope.models import ChangeRequest, Review

ADMIN = {"Authorization": "Bearer test-admin-token-not-for-production"}

@pytest.fixture
def managed(client, monkeypatch, tmp_path):
    monkeypatch.setattr(demo, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setattr(main, "compile_policy", lambda *a: ("compiled", {"supported": True}, None))
    state = {}
    def broker(body, **kwargs):
        action = body["action"]
        if action == "launch":
            state.update(status="running", available=True, runner_pid=100+body["version"],
                         watch_pid=200, domain_id=900+body["version"], version=body["version"])
            return dict(state)
        if action == "status": return dict(state)
        if action == "scope-verify": return {"passed": True, "domain_id": state["domain_id"], "runner_pid": state["runner_pid"]}
        if action == "restrict": return {"status": "delta_applied", "domain_id": state["domain_id"], "delta": body["delta_text"]}
        if action == "stop":
            state.update(status="stopped")
            return {"status": "stopped"}
        raise AssertionError(action)
    monkeypatch.setattr(manager, "broker_call", broker)
    task = demo.create()["task_id"]
    manager.cold_start(task)
    return task, state

def candidate(task, kind, **overrides):
    current = manager.get_scope(task)
    request = ChangeRequest(kind=kind, text="明确的任务授权或要求", request_key=uuid.uuid4().hex,
                            expected_snapshot=current["session"]["active_snapshot_id"])
    delta = manager.assess(task, request)
    old = current["current"]["payload"]
    values = {"decision": kind, "allowed_write_dirs": ["backend","frontend"] if kind=="task_grant" else ["backend"] if kind=="restrict" else old["allowed_write_dirs"],
              "allow_output": kind=="expand" or old["allow_output"], "explanation": "公开的候选理由"}
    values.update(overrides)
    with db.connect() as con:
        raw = dict(con.execute("SELECT * FROM scope_deltas WHERE id=?", (delta["id"],)).fetchone())
        context = manager.context_for(con, raw)
        values["evidence_ids"] = [context["request_evidence_id"]]
        result = manager.store_proposal(con, raw, values)
        con.execute("UPDATE scope_jobs SET status='completed',result_json=? WHERE delta_id=?", (json.dumps({"context":context}), delta["id"]))
    return delta["id"], Review(decision="approve", expected_proposal_hash=result["proposal_hash"], reviewed_by="test")

def grant(task):
    ident, body = candidate(task, "task_grant")
    return manager.review_and_apply(task, ident, body)

def test_complete_snapshot_and_same_domain_restrict_new_domain_expand(managed):
    task, state = managed
    cold = manager.get_scope(task)
    assert cold["current"]["revision"] == 0
    assert cold["current"]["payload"]["allowed_write_dirs"] == []
    assert "scope-trusted-runtime:" in cold["current"]["payload"]["dsl"]
    started = grant(task)
    ident, body = candidate(task, "restrict")
    restricted = manager.review_and_apply(task, ident, body)
    assert restricted["current"]["binding"]["domain_id"] == started["current"]["binding"]["domain_id"]
    assert "runtime-restriction-" in restricted["current"]["payload"]["dsl"]
    assert started["current"]["payload"]["dsl"] in restricted["current"]["payload"]["dsl"]
    ident, body = candidate(task, "expand")
    expanded = manager.review_and_apply(task, ident, body)
    assert expanded["current"]["binding"]["domain_id"] != restricted["current"]["binding"]["domain_id"]
    assert expanded["current"]["payload"]["allowed_write_dirs"] == ["backend"]
    assert expanded["current"]["payload"]["allow_output"]
    assert "scope-deny-frontend:" in expanded["current"]["payload"]["dsl"]
    assert expanded["current"]["payload"]["trusted_runtime_paths"] == cold["current"]["payload"]["trusted_runtime_paths"]
    assert "scope-trusted-runtime:" in expanded["current"]["payload"]["dsl"]
    closed = manager.close_task(task)
    assert closed["session"]["phase"] == "ended" and not closed["effective"]
    assert len(closed["snapshots"]) == 4

@pytest.mark.parametrize("kind", ["task_grant","restrict","expand"])
def test_pending_candidate_never_moves_pointer(managed, kind):
    task, _ = managed
    if kind!="task_grant": grant(task)
    original = manager.get_scope(task)["current"]["id"]
    ident, body = candidate(task, kind)
    assert manager.get_scope(task)["current"]["id"] == original
    assert manager.get_scope(task)["deltas"][0]["apply_status"] == "not_applied"

def test_reject_retains_user_restriction_and_committed_response(managed):
    task, _ = managed
    grant(task)
    ident, body = candidate(task, "restrict")
    rejected = manager.review_and_apply(task, ident, body.model_copy(update={"decision":"reject"}))
    assert rejected["deltas"][0]["review_status"] == "rejected"
    assert rejected["session"]["gate"] == "waiting_constraint"
    assert rejected["current"]["payload"]["allowed_write_dirs"] == ["backend","frontend"]

@pytest.mark.parametrize("drift", ["snapshot", "message", "epoch", "hash"])
def test_stale_or_corrupt_candidate_cannot_apply(managed, drift):
    task, _ = managed
    ident, body = candidate(task, "task_grant")
    with db.connect() as con:
        if drift=="snapshot": con.execute("UPDATE scope_sessions SET active_snapshot_id='wrong' WHERE task_id=?", (task,))
        if drift=="message": con.execute("UPDATE scope_sessions SET message_revision=message_revision+1 WHERE task_id=?", (task,))
        if drift=="epoch": con.execute("UPDATE scope_sessions SET process_epoch='wrong' WHERE task_id=?", (task,))
        if drift=="hash": con.execute("UPDATE scope_deltas SET proposal_json='{}' WHERE id=?", (ident,))
    with pytest.raises(ValueError): manager.review_and_apply(task, ident, body)

@pytest.mark.parametrize("draft", [
    {"allowed_write_dirs":["backend","tests"]},
    {"allow_output":True},
    {"decision":"expand","allow_output":True},
    {"allowed_write_dirs":[]},
])
def test_startup_authority_cannot_weaken_protection(managed, draft):
    task, _ = managed
    with pytest.raises(ValueError): candidate(task, "task_grant", **draft)

def test_guidance_cannot_mutate_scope_and_compiled_is_not_effective(managed):
    task, _ = managed
    grant(task)
    ident, body = candidate(task, "guidance", decision="guidance_only")
    before = manager.get_scope(task)["current"]["id"]
    result = manager.review_and_apply(task, ident, body)
    assert result["current"]["id"] == before
    assert result["deltas"][0]["verify_status"] == "not_required"

def test_duplicate_input_and_conflicting_idempotence(managed):
    task, _ = managed
    current = manager.get_scope(task)
    body = ChangeRequest(kind="task_grant",text="授权本次任务",request_key="dedupe",expected_snapshot=current["current"]["id"])
    first = manager.assess(task,body)
    assert manager.assess(task,body)["id"] == first["id"]
    with pytest.raises(ValueError): manager.assess(task,body.model_copy(update={"text":"不同的授权内容"}))

def test_verification_failure_preserves_pointer_halts_domain(managed, monkeypatch):
    task, state = managed
    old = manager.get_scope(task)["current"]["id"]
    ident, body = candidate(task, "task_grant")
    broker = manager.broker_call
    monkeypatch.setattr(manager,"broker_call",lambda m,**kw: {"passed":False,"domain_id":state["domain_id"]} if m["action"]=="scope-verify" else broker(m,**kw))
    with pytest.raises(ValueError): manager.review_and_apply(task,ident,body)
    result = manager.get_scope(task)
    assert result["current"]["id"] == old
    assert not result["effective"] and result["session"]["gate"]=="failed"
    assert result["deltas"][0]["apply_status"] == "loaded_unverified"

def test_cross_task_review_and_agent_approval_are_rejected(managed, client):
    task, _ = managed
    ident, body = candidate(task,"task_grant")
    token, _ = main.issue_task_token(task)
    endpoint=f"/api/tasks/{task}/scope-manager/changes/{ident}/review"
    assert client.post(endpoint,headers={"Authorization":"Bearer "+token},json=body.model_dump()).status_code==401
    with pytest.raises(ValueError): manager.review_and_apply("other-task",ident,body)

def test_generator_token_only_reads_bound_context_and_submit(managed, client):
    task, _ = managed
    current=manager.get_scope(task)
    delta=manager.assess(task,ChangeRequest(kind="task_grant",text="授权启动本次任务",request_key="job-api",expected_snapshot=current["current"]["id"]))
    with db.connect() as con:
        job=dict(con.execute("SELECT * FROM scope_jobs WHERE delta_id=?",(delta["id"],)).fetchone())
        raw=dict(con.execute("SELECT * FROM scope_deltas WHERE id=?",(delta["id"],)).fetchone())
        con.execute("UPDATE scope_jobs SET status='running',token_hash=?,expires_at=?,result_json=? WHERE id=?",
                    (manager.digest("generator-secret"),time.time()+100,json.dumps({"context":manager.context_for(con,raw)}),job["id"]))
    headers={"Authorization":"Bearer generator-secret"}
    base=f"/api/generator/tasks/{task}/scope-jobs/{job['id']}/tools/"
    assert client.post(base+"get_runtime_context",headers=headers,json={"args":{}}).status_code==200
    assert client.post(base+"approve",headers=headers,json={"args":{}}).status_code==400
    assert client.get(f"/api/tasks/{task}/scope-manager",headers=headers).status_code==401
    assert client.post(base.replace(task,"other-task")+"get_runtime_context",headers=headers,json={"args":{}}).status_code==401
    manager.close_task(task)
    assert client.post(base+"get_runtime_context",headers=headers,json={"args":{}}).status_code==401

def test_checkpoint_preserves_public_progress_and_assets(managed):
    task, _ = managed
    grant(task)
    with db.connect() as con: manager.event(con,task,"agent_report","done-backend",{"summary":"统计逻辑已修复，测试通过。"})
    checkpoint=manager.checkpoint(task)
    assert checkpoint["workspace_python_hashes"]["backend/stats.py"]
    assert checkpoint["messages_and_results"][-1]["payload"]["summary"]
    assert checkpoint["private_reasoning"]=="not_collected"

def test_default_new_task_does_not_inherit_permissions(managed):
    task, _ = managed
    grant(task)
    manager.close_task(task)
    new=demo.create()["task_id"]
    result=manager.get_scope(new)
    assert result["current"] is None
    assert result["default_scope"]["allowed_write_dirs"]==[]
    assert not result["default_scope"]["allow_output"]

def test_launch_failure_revokes_old_credential_and_preserves_snapshot(managed, monkeypatch, client):
    task, _ = managed
    before=manager.get_scope(task)["current"]["id"]
    token,_=main.issue_task_token(task)
    ident, body=candidate(task,"task_grant")
    broker=manager.broker_call
    def fail(message,**kwargs):
        if message["action"]=="launch": raise RuntimeError("injected DSH restart failure")
        return broker(message,**kwargs)
    monkeypatch.setattr(manager,"broker_call",fail)
    with pytest.raises(RuntimeError): manager.review_and_apply(task,ident,body)
    result=manager.get_scope(task)
    assert result["current"]["id"]==before and not result["effective"]
    assert client.get(f"/api/plugin/tasks/{task}/scope-manager/gate",headers={"Authorization":"Bearer "+token}).status_code==401
    with pytest.raises(ValueError): manager.assess(task,ChangeRequest(kind="task_grant",text="不能继续未知执行状态",request_key="retry",expected_snapshot=before))

def test_closed_task_cannot_cold_start_or_approve(managed):
    task,_=managed
    ident,body=candidate(task,"task_grant")
    manager.close_task(task)
    with pytest.raises(ValueError): manager.cold_start(task)
    with pytest.raises(ValueError): manager.review_and_apply(task,ident,body)
    assert manager.get_scope(task)["deltas"][0]["review_status"]=="expired"

def test_legacy_apply_endpoint_cannot_bypass_scope_manager(managed,client):
    task,_=managed
    for action in ("launch","policy","stop","scope-requests"):
        assert client.post(f"/api/tasks/{task}/{action}",headers=ADMIN,json={}).status_code==409

def test_scope_control_is_passwordless_in_local_demo(managed,client,monkeypatch):
    task,_=managed
    monkeypatch.setattr(main.development,"passwordless",lambda _:True)
    assert client.get("/api/tasks").status_code==200
    assert client.get(f"/api/tasks/{task}/scope-manager").status_code==200
    ident,body=candidate(task,"task_grant")
    response=client.post(f"/api/tasks/{task}/scope-manager/changes/{ident}/review",json=body.model_dump())
    assert response.status_code==200
    assert response.json()["current"]["payload"]["allowed_write_dirs"]==["backend","frontend"]
    assert client.get(f"/api/tasks/{task}/scope-manager",headers={"Authorization":"Bearer task-token"}).status_code==401

def test_collector_does_not_turn_control_probes_into_agent_requests(managed, monkeypatch):
    import os
    from pathlib import Path
    from agentscope_app.scope.worker import Worker
    task, _ = managed
    scope = grant(task)
    domain = scope["current"]["binding"]["domain_id"]
    with db.connect() as con:
        con.execute("UPDATE scope_snapshots SET verification_json=? WHERE id=?",
                    (json.dumps({"domain_id":domain,"probe":{"probe_pid":444}}),scope["current"]["id"]))
    events = Path(scope["task"]["workspace"]) / ".actplane/events.jsonl"
    events.parent.mkdir()
    target = str(events.parent.parent.parent / ".dsh/profiles/headless/package.json")
    raw = {"domain_id":domain,"pid":444,"ppid":101,"target":target,"op":"write","blocked":True}
    events.write_text(json.dumps(raw)+"\n"+json.dumps({**raw,"pid":445})+"\n")
    original = Path.lstat
    def root_owned(path, *args, **kwargs):
        value = original(path, *args, **kwargs)
        if path == events:
            fields = list(value)
            fields[0], fields[4] = 0o100640, 0
            return os.stat_result(fields)
        return value
    monkeypatch.setattr(Path, "lstat", root_owned)
    Worker().collect()
    Worker().collect()
    changes = manager.get_scope(task)["deltas"]
    assert len([d for d in changes if d["kind"]=="guidance"]) == 1

def test_guidance_approval_cannot_resume_unresolved_user_restriction(managed):
    task, _ = managed
    grant(task)
    candidate(task, "restrict")
    before = manager.get_scope(task)["current"]["id"]
    ident, body = candidate(task, "guidance", decision="guidance_only")
    result = manager.review_and_apply(task, ident, body)
    assert result["current"]["id"] == before
    assert result["session"]["gate"] == "waiting_constraint"

def test_expansion_cannot_skip_unresolved_user_restriction(managed):
    task, _ = managed
    grant(task)
    candidate(task, "restrict")
    before = manager.get_scope(task)["current"]["id"]
    ident, body = candidate(task, "expand")
    with pytest.raises(ValueError): manager.review_and_apply(task, ident, body)
    result = manager.get_scope(task)
    assert result["current"]["id"] == before
    assert result["session"]["gate"] == "waiting_constraint"
    assert result["deltas"][0]["review_status"] == "pending"

def test_finished_pi_analysis_reports_context_drift_as_stale(managed, monkeypatch):
    from agentscope_app.scope import pi
    from agentscope_app.scope.worker import Worker
    task, _ = managed
    grant(task)
    before = manager.get_scope(task)
    manager.assess(task, ChangeRequest(kind="expand",text="申请当前任务 output 写入",
        request_key="pi-drift",expected_snapshot=before["current"]["id"]),actor="DSH")
    with db.connect() as con:
        con.execute("UPDATE scope_jobs SET status='interrupted' WHERE status='queued' AND task_id!=?",(task,))
    def changed_message(job):
        with db.connect() as con:
            con.execute("UPDATE scope_sessions SET message_revision=message_revision+1 WHERE task_id=?",(task,))
        return {}
    monkeypatch.setattr(pi, "generate", changed_message)
    assert Worker().run_one()
    result = manager.get_scope(task)
    assert result["jobs"][0]["status"] == "failed"
    assert result["jobs"][0]["error"].startswith("stale:")
    assert result["current"]["id"] == before["current"]["id"]

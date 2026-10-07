"""Archive acceptance against persisted sources, never a live DSH or service DB."""
import json
import uuid
from contextlib import contextmanager
import pytest
from fastapi import HTTPException, FastAPI
from fastapi.testclient import TestClient
from agentscope_app import db
from agentscope_app.archive import projection as archive
from agentscope_app.archive.api import router
from agentscope_app.managed import controller
from agentscope_app.workspaces import registry

def ident():return uuid.uuid4().hex
def record(task,kind,payload,when="2026-10-07T01:00:00+00:00"):
    with db.connect() as con:
        cur=con.execute("INSERT INTO managed_events(task_id,kind,event_key,payload_json,occurred_at) VALUES(?,?,?,?,?)",(task,kind,ident(),json.dumps(payload),when))
        return "managed_events:"+str(cur.lastrowid)+":record"

@pytest.fixture
def task(seed_task,monkeypatch):
    db.init_db();registry.init()
    task=ident();seed_task(task)
    monkeypatch.setattr(controller,"broker",lambda *a,**k:pytest.fail("archive must never probe live runtime"))
    return task

def walk(task,category="timeline",limit=3):
    items=[];cursor=None
    while True:
        result=archive.events(task,category,cursor,limit);items.extend(result["events"])
        cursor=result["next_cursor"]
        if cursor is None:return items

def test_legacy_task_archivable_with_missing_explicitly_marked(task):
    result=archive.archive(task)
    assert result["header"]["goal"]=="test task"
    assert result["header"]["source"]["status"]=="not_recorded"
    assert result["header"]["execution"]["status"]=="not_recorded"
    assert result["history_only"] is True
    assert {s["id"]:s["status"] for s in result["stages"]}=={"preparation":"recorded","execution":"not_recorded","closure":"not_recorded"}
    assert "startup_generation" in result["missing"] and "load_receipts" in result["missing"]
    assert result["counts"]=={"timeline":1,"tools":0,"kernel":0,"audit":0}

@pytest.mark.parametrize("status",["queued","running","completed","failed","cancelled","interrupted"])
def test_all_startup_generations_preserved_without_merging(task,status):
    job=ident()
    with db.connect() as con:
        con.execute("INSERT INTO history_jobs(id,kind,status,input_json,created_at,started_at,finished_at,error) VALUES(?,?,?,?,?,?,?,?)",(job,"task_bootstrap",status,json.dumps({"task_id":task,"runtime":{"api_key":"never-show-this"}}),"2026-10-07T01:00:00Z","2026-10-07T01:01:00Z","2026-10-07T01:02:00Z" if status not in ("queued","running") else None,"example error" if status=="failed" else None))
    events=[x for x in walk(task) if x["job_id"]==job]
    assert events and {x["status"] for x in events if x["kind"]!="startup_started"}=={status}
    assert all(x["status"]=="started" for x in events if x["kind"]=="startup_started")
    assert events[0]["task_id"]==task
    detail=archive.event_detail(task,events[0]["id"])
    assert "never-show-this" not in json.dumps(detail)
    assert detail["detail"]["status"]==status

@pytest.mark.parametrize("status,decision",[("queued",None),("running",None),("completed","no_change"),("completed","guidance_only"),("stale","restrict"),("rejected","expand"),("failed",None),("pending","restrict"),("pending_confirmation","expand"),("cancelled",None)])
def test_runtime_jobs_visible_for_every_status(task,status,decision):
    job=ident();p={"decision":decision,"explanation":"public assessment","evidence_ids":["request:1"]} if decision else None
    with db.connect() as con:
        con.execute("INSERT INTO managed_jobs(id,task_id,request_key,revision,policy_hash,status,context_json,proposal_json,token_hash,error,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(job,task,ident(),1,"base-hash",status,json.dumps({"session_id":"s1","private_reasoning":"DO NOT EXPORT"}),json.dumps(p) if p else None,"token-private","error" if status=="failed" else None,"2026-10-07T02:00:00Z"))
    event=next(x for x in walk(task) if x["source"]=="managed_jobs")
    assert event["status"]==status and event["job_id"]==job
    detail=archive.event_detail(task,event["id"])
    assert detail["detail"]["proposal"].get("decision")==decision
    assert "token-private" not in json.dumps(detail) and "DO NOT EXPORT" not in json.dumps(detail)

def test_same_workspace_new_task_never_cross_associated(task,seed_task):
    other=ident();seed_task(other)
    foreign=record(other,"request",{"actor":"native_user","text":"foreign task secret"})
    own=record(task,"request",{"actor":"native_user","text":"my task request"})
    events=walk(task)
    assert own in {e["id"] for e in events}
    assert foreign not in {e["id"] for e in events}
    with pytest.raises(HTTPException) as error:archive.event_detail(task,foreign)
    assert error.value.status_code==404

def test_multiple_binding_generations_one_task_and_source_evidence(task):
    with db.connect() as con:
        con.execute("INSERT INTO managed_tasks VALUES(?,?,?)",(task,json.dumps({"phase":"running","gate":"open","session_id":"new","binding":{"domain_id":9,"runner_pid":81},"binding_history":[{"domain_id":7,"version":1},{"domain_id":9,"version":2}]}),db.now()))
        wid=ident()
        con.execute("INSERT INTO agent_workspaces(id,agent_id,name,path,origin,created_at) VALUES(?,?,?,?,?,?)",(wid,"native-dsh","source","/tmp/work","native",db.now()))
        con.execute("INSERT INTO workspace_task_sources VALUES(?,?,?,?,?)",(task,wid,"manifest",json.dumps({"files":[{"path":"a.py","sha256":"frozenhash","size":7,"text":"private file bytes"}]}),db.now()))
    for version in (1,2):
        record(task,"policy_active",{"version":version,"binding":{"domain_id":7+version,"runner_pid":80+version}})
    result=archive.archive(task)
    assert result["task_id"]==task and len(result["header"]["execution"]["binding_history"])==2
    assert result["header"]["source"]["agent_id"]=="native-dsh"
    assert result["header"]["source"]["files"]==[{"path":"a.py","sha256":"frozenhash","size":7}]
    assert "private file bytes" not in json.dumps(result)
    assert len([x for x in result["events"] if x["kind"]=="policy_active"])==2
    assert result["header"]["execution"]["observation"].startswith("historical_receipts")

def test_cursor_exhaustion_no_loss_with_equal_times_and_many_sources(task):
    ids=[record(task,"tool_result",{"call_id":str(i),"succeeded":bool(i%2)}) for i in range(123)]
    events=walk(task,"tools",7)
    assert len(events)==123 and len({x["id"] for x in events})==123
    assert set(ids)=={x["id"] for x in events}
    timeline=archive.archive(task,limit=1)
    assert timeline["counts"]["tools"]==123 and timeline["counts"]["timeline"]==1
    assert all(x["category"]=="timeline" for x in timeline["events"])

def test_cursor_rejects_cross_task_and_category(task,seed_task):
    record(task,"tool_result",{"succeeded":True});record(task,"tool_result",{"succeeded":False})
    cursor=archive.events(task,"tools",limit=1)["next_cursor"]
    other=ident();seed_task(other)
    for target,category in ((other,"tools"),(task,"kernel")):
        with pytest.raises(HTTPException) as error:archive.events(target,category,cursor)
        assert error.value.status_code==422
    with pytest.raises(HTTPException):archive.events(task,"tools","invalid!")

def test_kernel_tool_and_control_pause_meanings_are_not_conflated(task):
    record(task,"kernel",{"event":{"op":"unlink","target":"/tmp/work/a","pid":2,"rule":{"reason":"protected"}}})
    record(task,"tool_result",{"succeeded":False,"call_id":"c","serialized":"raw tool response must stay private"})
    record(task,"control_pause",{"reason":"waiting for review"})
    result=archive.archive(task)
    assert result["counts"]["kernel"]==1 and result["counts"]["tools"]==1
    assert next(x for x in result["events"] if x["kind"]=="control_pause")["detail"]["meaning"]=="control_plane_gate; not kernel denial"
    tool=archive.events(task,"tools")["events"][0]
    assert tool["detail"]["result"]=="failure"
    kernel=archive.events(task,"kernel")["events"][0]
    assert kernel["detail"]["meaning"]=="kernel_denial"

def test_private_context_streams_and_credentials_never_exported(task):
    record(task,"runtime_observation",{"category":"system","type":"system_prompt","seq":2,"content_hash":"hash-only","text":"PRIVATE SYSTEM PROMPT","content":{"reasoning":"PRIVATE REASONING"},"serialized":"RAW NATIVE STREAM","token":"TOKEN VALUE"})
    record(task,"request",{"actor":"native_context","text":"HIDDEN NATIVE CONTEXT"})
    user=record(task,"request",{"actor":"native_user","text":"save config; password=hunter2 Bearer opaque-token api_key=abc secret=private-value <think>PRIVATE THOUGHT</think>"})
    output=archive.archive(task)
    output["details"]=[archive.event_detail(task,e["id"]) for e in output["events"]]
    text=json.dumps(output)
    for secret in ("PRIVATE SYSTEM PROMPT","PRIVATE REASONING","RAW NATIVE STREAM","TOKEN VALUE","HIDDEN NATIVE CONTEXT","hunter2","opaque-token","api_key=abc","private-value","PRIVATE THOUGHT"):
        assert secret not in text
    assert archive.event_detail(task,user)["detail"]["user_request"].startswith("save config;")

def test_closed_is_not_invented_when_task_only_says_ended(task):
    with db.connect() as con:con.execute("UPDATE tasks SET status='ended',ended_at=? WHERE id=?",(db.now(),task))
    result=archive.archive(task)
    assert result["stages"][2]["status"]=="recorded"
    assert not any(e["kind"]=="closed" for e in result["events"])
    closure=record(task,"closed",{"receipt":{"status":"stopped","cleanup_confirmed":True},"temporary_grants":"revoked"})
    detail=archive.event_detail(task,closure)
    assert detail["detail"]["receipt"]["cleanup_confirmed"] is True
    assert detail["detail"]["temporary_grants"]=="revoked"

def test_archive_and_details_execute_only_reads(task,monkeypatch):
    event=record(task,"control_pause",{"reason":"review"})
    original=db.connect;sql=[]
    @contextmanager
    def traced():
        with original() as con:
            con.set_trace_callback(sql.append)
            yield con
    monkeypatch.setattr(db,"connect",traced)
    archive.archive(task);archive.events(task,"tools");archive.event_detail(task,event)
    assert not [q for q in sql if q.lstrip().upper().startswith(("INSERT","UPDATE","DELETE","CREATE","ALTER","REPLACE"))]

def test_http_contract_bad_ids_limits_and_auth(task):
    from agentscope_app.main import app
    # The parent app must own authorization for archive exactly as its other control APIs.
    with TestClient(app) as client:
        assert client.get("/api/tasks/"+task+"/archive").status_code==401
        headers={"Authorization":"Bearer test-admin-token-not-for-production"}
        result=client.get("/api/tasks/"+task+"/archive",headers=headers)
        assert result.status_code==200 and result.json()["task_id"]==task
        assert client.get("/api/tasks/"+task+"/archive?limit=0",headers=headers).status_code==422
        assert client.get("/api/tasks/"+task+"/archive/events?category=secret",headers=headers).status_code==422
        assert client.get("/api/tasks/missing/archive",headers=headers).status_code==404
        assert client.get("/api/tasks/"+task+"/archive/events/missing",headers=headers).status_code==404


def test_record_details_use_historical_scope_mapping_and_load_version(task):
    job=ident()
    state={"phase":"running","gate":"open","version":3,"session_id":"s3","binding":{"domain_id":93},"runtime_protected":[],"allowed_write_dirs":["."],"allow_output":False}
    context={"session_id":"s2","request_evidence_id":"q1","sources":[{"evidence_id":"q1","content":{"actor":"native_user","text":"keep current permissions"}}],"base_snapshot":{"payload":{"allowed_write_dirs":["."],"allow_output":False,"protected_paths":[]}}}
    proposal={"decision":"no_change","allowed_write_dirs":["."],"allow_output":False,"protected_paths":[],"evidence_ids":["q1"],"explanation":"Nothing changes"}
    with db.connect() as con:
        con.execute("INSERT INTO managed_tasks VALUES(?,?,?)",(task,json.dumps(state),db.now()))
        con.execute("INSERT INTO managed_jobs(id,task_id,request_key,revision,policy_hash,status,context_json,proposal_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(job,task,ident(),2,"h2","completed",json.dumps(context),json.dumps(proposal),db.now()))
        con.execute("INSERT INTO managed_events(task_id,kind,event_key,payload_json,occurred_at) VALUES(?,?,?,?,?)",(task,"request_resolved",job,json.dumps({"decision":"no_change","version":2,"evidence_ids":["q1"]}),db.now()))
    detail=archive.event_detail(task,"managed_jobs:"+job+":record")
    assert detail["version"]==2
    assert detail["detail"]["decision"]=="no_change"
    records=detail["detail"]["policy_records"]
    assert records and all(r["status"]=="historical_receipt" for r in records)
    assert not any(r.get("effective") for r in records)

def test_reviews_recovery_closure_and_failure_keep_correlated_receipts(task):
    review=record(task,"change_review",{"job_id":"j1","decision":"clarify","change":"restrict","candidate_hash":"hash1","base_version":2,"revision":9,"actor":"authenticated_operator","text":"preserve tests"})
    failure=record(task,"change_apply_failed",{"job_id":"j2","candidate_hash":"hash2","error":"broker refused apply","version":2,"phase":"failed","binding":{"domain_id":4,"runner_pid":5}})
    record(task,"session_resumed",{"version":3,"session_id":"s3","original_request_preserved":True})
    assert archive.event_detail(task,review)["detail"]["user_request"]=="preserve tests"
    assert archive.event_detail(task,review)["job_id"]=="j1"
    assert archive.event_detail(task,review)["detail"]["change"]=="restrict"
    assert archive.event_detail(task,failure)["detail"]["binding"]=={"domain_id":4,"runner_pid":5}
    assert archive.event_detail(task,failure)["detail"]["phase"]=="failed"
    assert any(e["kind"]=="session_resumed" for e in archive.archive(task)["events"])

def test_snapshot_proposals_compilations_and_loads_retain_cross_source_links(task):
    now="2026-10-07T03:00:00Z";job=ident();pid=ident();version=ident();comp=ident();deployment=ident()
    with db.connect() as con:
        con.execute("INSERT INTO bootstrap_contexts VALUES(?,?,?,?,?)",(task,"custom",json.dumps({"declared_constraints":[{"intent":"preserve_assets","targets":["a.py"]}]}),"ctxhash",now))
        con.execute("INSERT INTO bootstrap_sources VALUES(?,?,?,?,?,?,?)",("source-"+task,task,"asset","/tmp/work/a.py","raw private source bytes","sourcehash","{}"))
        con.execute("INSERT INTO history_jobs(id,kind,status,input_json,created_at) VALUES(?,?,?,?,?)",(job,"task_bootstrap","completed",json.dumps({"task_id":task}),now))
        con.execute("INSERT INTO bootstrap_proposals VALUES(?,?,?,?,?,?,?,?,?)",(pid,task,job,"ctxhash","proposalhash",json.dumps({"draft":{"atoms":[{"statement":"preserve a.py","operations":["write"],"paths":["a.py"],"evidence_ids":["source-"+task]}],"guidance":["explain findings"]}}),json.dumps({"compiler":{"ok":True,"rule_count":1,"rules":[{"source_text":"rule keep: block write file a.py"}]}}),"validated",now))
        con.execute("INSERT INTO policy_versions(id,task_id,version,layer,dsl_text,policy_yaml,evidence_ids,compile_state,compile_json,status,change_summary,approved_by,approved_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(version,task,1,"task","rule keep:","private yaml omitted",json.dumps(["source-"+task]),"compiled",'{"ok":true}',"approved","initial","operator",now,now))
        con.execute("INSERT INTO bootstrap_versions VALUES(?,?,?,?,?,?,?)",(version,pid,"ctxhash","proposalhash","human_review","private pi prompt omitted","prompthash"))
        con.execute("INSERT INTO history_compilations VALUES(?,?,?,?,?,?,?,?,?)",(comp,None,task,version,"inputhash","compiled","v1",'{"ok":true}',now))
        con.execute("INSERT INTO history_deployments(id,policy_version_id,task_id,bundle_hash,status,domain_id,runner_pid,receipt_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(deployment,version,task,"bundlehash","loaded",83,84,'{"status":"running","domain_id":83}',now))
    result=archive.archive(task,limit=200)
    assert result["header"]["constraints"]["declared_constraints"][0]["intent"]=="preserve_assets"
    assert archive.event_detail(task,"policy_versions:"+version+":record")["job_id"]==job
    assert archive.event_detail(task,"history_compilations:"+comp+":record")["version"]==1
    assert archive.event_detail(task,"history_deployments:"+deployment+":record")["version"]==1
    details=[archive.event_detail(task,e["id"]) for e in result["events"]]
    text=json.dumps(details)
    assert "preserve a.py" in text and "sourcehash" in text and "source-"+task in text
    assert "raw private source bytes" not in text and "private yaml omitted" not in text and "private pi prompt omitted" not in text


def test_mirrored_kernel_event_is_one_fact_without_path_based_dedup(task):
    with db.connect() as con:
        con.execute("INSERT INTO managed_events(task_id,kind,event_key,payload_json,occurred_at) VALUES(?,?,?,?,?)",(task,"kernel","exact-hash",json.dumps({"event":{"op":"write","target":"/tmp/work/a"}}),db.now()))
        for hash_ in ("exact-hash","another-real-denial"):
            con.execute("INSERT INTO runtime_events VALUES(?,?,?,?,?,?,?,?,?,?)",(ident(),task,"kernel","write","/tmp/work/a","block","protected",db.now(),"{}",hash_))
    result=archive.events(task,"kernel")
    assert result["total"]==2
    assert {e["source"] for e in result["events"]}=={"managed_events","runtime_events"}

def test_each_stage_preview_and_stage_pagination_reach_old_preparation(task):
    for _ in range(63):record(task,"control_pause",{"reason":"review"},"2099-10-07T01:00:00Z")
    record(task,"closed",{"receipt":{"status":"stopped"}},"2099-10-07T02:00:00Z")
    result=archive.archive(task,limit=2)
    assert not any(e["stage"]=="preparation" for e in result["events"])
    assert result["stage_previews"]["preparation"]["events"][0]["kind"]=="task_created"
    assert result["stage_previews"]["closure"]["events"][0]["kind"]=="closed"
    preparation=archive.events(task,stage="preparation",limit=2)
    assert preparation["total"]==1 and preparation["events"][0]["stage"]=="preparation"
    execution=archive.events(task,stage="execution",limit=2)
    assert execution["total"]==63 and execution["next_cursor"]
    with pytest.raises(HTTPException):archive.events(task,before=execution["next_cursor"],stage="preparation")
    with pytest.raises(HTTPException):archive.events(task,before=execution["next_cursor"])


def test_source_instance_is_snapshot_not_current_inventory(task):
    with db.connect() as con:
        workspace_id=ident()
        con.execute("INSERT INTO agent_workspaces(id,agent_id,name,path,origin,created_at) VALUES(?,?,?,?,?,?)",(workspace_id,"current-new-instance","source","/tmp/new-source","native",db.now()))
        con.execute("INSERT INTO workspace_task_sources VALUES(?,?,?,?,?)",(task,workspace_id,"manifest","{}",db.now()))
        ctx={"workspace_source":{"agent_id":"native-dsh","path":"/tmp/original-source","instance":{"instance_id":"native-dsh","generation":"old-generation","session_ids":["original-session"],"pid":70,"start_ticks":800}}}
        con.execute("INSERT INTO bootstrap_contexts VALUES(?,?,?,?,?)",(task,"custom",json.dumps(ctx),"ctxhash",db.now()))
    source=archive.archive(task)["header"]["source"]
    assert source["agent_id"]=="native-dsh" and source["path"]=="/tmp/original-source"
    assert source["instance"]["generation"]=="old-generation" and source["instance"]["pid"]==70
    assert source["instance"]["session_ids"]==["original-session"]

def test_binding_history_enriched_only_from_exact_receipt_and_closure_kept(task):
    with db.connect() as con:
        con.execute("INSERT INTO managed_tasks VALUES(?,?,?)",(task,json.dumps({"binding":{"domain_id":8},"binding_history":[{"domain_id":8,"version":2},{"domain_id":8,"version":3}]}),db.now()))
    record(task,"policy_active",{"version":2,"binding":{"domain_id":8,"runner_pid":71,"watch_pid":72},"session_id":"historical-session"},"2026-10-07T01:30:00Z")
    closed=record(task,"closed",{"receipt":{"status":"stopped","domain_id":8,"quiesced_pids":[71,73],"writable_fds_and_mappings":"revoked_by_process_termination"},"temporary_grants":"revoked"})
    history=archive.archive(task)["header"]["execution"]["binding_history"]
    assert history[0]["runner_pid"]==71 and history[0]["created_at"]=="2026-10-07T01:30:00Z"
    assert history[0]["session_id"]=="historical-session"
    assert "runner_pid" not in history[1]  # same domain number cannot imply same version/process
    receipt=archive.event_detail(task,closed)["detail"]["receipt"]
    assert receipt["quiesced_pids"]==[71,73] and receipt["writable_fds_and_mappings"]=="revoked_by_process_termination"


def review_fixture(task,monkeypatch,decision="restrict"):
    state={"phase":"running","gate":"waiting_policy","revision":2,"version":3,"policy_hash":"loaded-hash","baseline_hash":"baseline","baseline_extra":"","protected":[],"runtime_protected":[],"allowed_write_dirs":["."],"allow_output":False,"binding":{"domain_id":77,"runner_pid":101},"session_id":"native-old","turn":1,"normalization_mode":"legacy","execution_role_version":2}
    ctx={"revision":2,"policy_hash":"loaded-hash","request_evidence_id":"req1","current_binding":{"domain_id":77,"runner_pid":101},"project_sources":[],"sources":[{"evidence_id":"req1","content":{"actor":"native_user","text":"preserve src"}}],"session_id":"native-old","base_snapshot":{"payload":{"allowed_write_dirs":["."],"allow_output":False,"protected_paths":[]}}}
    job={"id":ident(),"task_id":task,"revision":2,"policy_hash":"loaded-hash","context_json":json.dumps(ctx)}
    proposal={"decision":decision,"allowed_write_dirs":["src"] if decision=="restrict" else ["."],"allow_output":decision=="expand","protected_paths":[],"evidence_ids":["req1"],"explanation":"Explicit user request and project evidence","hash":"candidate-"+decision}
    with db.connect() as con:
        controller.save(con,task,state)
        con.execute("INSERT INTO managed_jobs(id,task_id,request_key,revision,policy_hash,context_json,proposal_json,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(job["id"],task,job["id"],2,"loaded-hash",job["context_json"],json.dumps(proposal),"completed",db.now()))
    monkeypatch.setattr(controller,"broker",lambda request,**kwargs:{"status":"running","domain_id":77,"runner_pid":101,"domain_verified":True,"cgroup_verified":True})
    controller.finish_job(job)
    return state,job,proposal

def test_review_preserves_newer_generation_candidate_after_old_install_returns(task,monkeypatch):
    state,job,proposal=review_fixture(task,monkeypatch)
    newer={"job_id":"newer-job","hash":"newer-hash","proposal":{"decision":"restrict","evidence_ids":["new-request"]}}
    def install(*args,**kwargs):
        with db.connect() as con:
            current=controller.load(con,task)
            current.update(version=4,policy_hash="new-hash",revision=3,pending_change=newer,gate="waiting_confirmation",pending_unresolved_requests=["new-request"])
            controller.save(con,task,current)
        # Returned installation receipt is stable v4; a native callback already queued a later review.
        return {**state,"version":4,"policy_hash":"new-hash"}
    monkeypatch.setattr(controller,"install",install)
    controller.review_change(task,job["id"],"approve",proposal["hash"])
    with db.connect() as con:current=controller.load(con,task)
    assert current["pending_change"]==newer
    assert current["pending_unresolved_requests"]==["new-request"]

def test_recovery_retains_unreviewed_restriction_intent_and_invalidation(task,monkeypatch):
    state,job,proposal=review_fixture(task,monkeypatch)
    with db.connect() as con:
        current=controller.load(con,task);current["phase"]="recovering";controller.save(con,task,current)
    def broker(request,**kwargs):
        if request["action"]=="launch":return {"domain_id":88,"runner_pid":201,"watch_pid":202,"web_url":"http://127.0.0.1/"}
        if request["action"]=="native-session":return {"sessionId":"native-new"}
        if request["action"]=="managed-verify":return {"passed":True,"probe":{"pid":203}}
        if request["action"]=="status":return {"status":"running","domain_id":88}
        if request["action"]=="stop":return {"status":"stopped"}
        raise AssertionError(request)
    monkeypatch.setattr(controller,"broker",broker)
    restored=controller.install(task,current,["."],False,initial=True)
    assert restored.get("pending_restriction_intent",{}).get("job_id")==job["id"]
    with db.connect() as con:
        invalidation=con.execute("SELECT 1 FROM managed_events WHERE task_id=? AND kind='candidate_invalidated' AND json_extract(payload_json,'$.job_id')=?",(task,job["id"])).fetchone()
    assert invalidation

def test_old_policy_loading_does_not_borrow_new_session_identity(task,monkeypatch):
    from agentscope_app.managed import records
    state,job,proposal=review_fixture(task,monkeypatch)
    with db.connect() as con:
        controller.event(con,task,"request_resolved",job["id"],{"evidence_ids":["req1"],"decision":"restrict","version":3,"confirmation":proposal["hash"]})
        state.update(session_id="native-new",allowed_write_dirs=["src"],version=4)
        row=con.execute("SELECT * FROM managed_jobs WHERE id=?",(job["id"],)).fetchone()
        record=records.runtime_record(con,controller.task_row(con,task),state,row)
    assert record["loading"]["session_id"]=="native-old"


def test_failed_application_never_reopens_gate_on_different_runner_generation(task,monkeypatch):
    state,job,proposal=review_fixture(task,monkeypatch,"expand")
    calls=[]
    def broker(request,**kwargs):
        calls.append(request)
        if len(calls)==1:return {"status":"running","domain_id":77,"runner_pid":101,"domain_verified":True,"cgroup_verified":True}
        return {"status":"running","domain_id":77,"runner_pid":999,"domain_verified":True,"cgroup_verified":False}
    monkeypatch.setattr(controller,"broker",broker)
    def fail(*args,**kwargs):raise RuntimeError("application interrupted")
    monkeypatch.setattr(controller,"install",fail)
    with pytest.raises(RuntimeError):controller.review_change(task,job["id"],"approve",proposal["hash"])
    with db.connect() as con:current=controller.load(con,task)
    assert current["gate"]!="open"


def test_failed_old_review_does_not_override_newer_context_pause(task,monkeypatch):
    state,job,proposal=review_fixture(task,monkeypatch,"expand")
    def fail(*args,**kwargs):
        with db.connect() as con:
            current=controller.load(con,task);current.update(revision=3,gate="waiting_policy")
            controller.save(con,task,current)
        raise ValueError("stale: new user context arrived before install")
    monkeypatch.setattr(controller,"install",fail)
    with pytest.raises(ValueError):controller.review_change(task,job["id"],"approve",proposal["hash"])
    with db.connect() as con:current=controller.load(con,task)
    assert current["gate"]=="waiting_policy" and current["revision"]==3


@pytest.mark.parametrize("decision",["restrict","expand"])
def test_review_rejection_records_offline_without_probing_broker(task,monkeypatch,decision):
    state,job,proposal=review_fixture(task,monkeypatch,decision)
    monkeypatch.setattr(controller,"broker",lambda *a,**k:pytest.fail("reject must not need a live runtime"))
    result=controller.review_change(task,job["id"],"reject",proposal["hash"])
    assert result["status"]=="rejected"
    with db.connect() as con:
        review=con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='change_review'",(task,)).fetchone()
    assert json.loads(review[0])["decision"]=="reject"

def test_failed_application_never_reopens_gate_without_expected_cgroup(task,monkeypatch):
    state,job,proposal=review_fixture(task,monkeypatch,"expand")
    with db.connect() as con:
        current=controller.load(con,task)
        current["binding"]["process_cgroup"]="original-cgroup"
        current["pending_change"]["binding"]["process_cgroup"]="original-cgroup"
        controller.save(con,task,current)
    calls=[]
    def broker(*args,**kwargs):
        calls.append(1)
        return {"status":"running","domain_id":77,"runner_pid":101,"domain_verified":True,"cgroup_verified":len(calls)==1}
    monkeypatch.setattr(controller,"broker",broker)
    def fail(*args,**kwargs):raise RuntimeError("application interrupted")
    monkeypatch.setattr(controller,"install",fail)
    with pytest.raises(RuntimeError):controller.review_change(task,job["id"],"approve",proposal["hash"])
    with db.connect() as con:current=controller.load(con,task)
    assert current["gate"]=="failed" and current["phase"]=="failed"


def test_install_rechecks_frozen_sources_after_quiesce_before_launch(task,monkeypatch,tmp_path):
    from agentscope_app.main import issue_task_token
    state,job,proposal=review_fixture(task,monkeypatch)
    workspace=tmp_path/"work";workspace.mkdir()
    source=workspace/"source.py";source.write_text("before approval\n")
    with db.connect() as con:
        con.execute("UPDATE tasks SET workspace=? WHERE id=?",(str(workspace),task))
        current=controller.load(con,task);current["gate"]="applying";controller.save(con,task,current)
        task_row=controller.task_row(con,task)
    frozen={"id":"source.py","path":str(source),"hash":controller.read_project_content(task_row,str(source))["hash"]}
    _,old_credential=issue_task_token(task)
    actions=[]
    def broker(request,**kwargs):
        actions.append(request["action"])
        if request["action"]=="native-session":
            return {"status":"idle"}
        if request["action"]=="stop":
            # An already running tool finishes its write as the old domain stops.
            source.write_text("changed while stopping the old execution domain\n")
            return {"status":"stopped","domain_id":77}
        if request["action"]=="launch":
            pytest.fail("a source changed during quiesce must never reach launch")
        raise AssertionError(request)
    monkeypatch.setattr(controller,"broker",broker)
    with pytest.raises(ValueError,match="项目证据.*变化"):
        controller.install(task,current,proposal["allowed_write_dirs"],proposal["allow_output"],review_sources=[frozen])
    assert "stop" in actions and "launch" not in actions
    with db.connect() as con:
        current=controller.load(con,task)
        assert current["phase"]=="failed" and current["gate"]=="failed"
        assert con.execute("SELECT revoked_at FROM task_credentials WHERE id=?",(old_credential,)).fetchone()[0] is not None
        assert con.execute("SELECT COUNT(*) FROM task_credentials WHERE task_id=? AND revoked_at IS NULL",(task,)).fetchone()[0]==0
        assert con.execute("SELECT status FROM tasks WHERE id=?",(task,)).fetchone()[0]=="failed"


@pytest.mark.parametrize("stored_status,phase,ended_at,closed,ended",[
    ("prepared",None,None,False,False),("running","running",None,False,False),
    ("policy_review","policy_review",None,False,False),("failed","failed",None,False,False),
    ("running","recovering",None,False,False),("completed",None,None,False,True),
    ("stopped",None,None,False,True),("cancelled",None,None,False,True),
    ("running","ended",None,False,True),("failed",None,"2026-10-07T01:00:00Z",False,True),
    ("running","running",None,True,True)])
def test_archive_index_classifies_all_recorded_states_without_live_probes(task,stored_status,phase,ended_at,closed,ended):
    with db.connect() as con:
        con.execute("UPDATE tasks SET status=?,ended_at=? WHERE id=?",(stored_status,ended_at,task))
        if phase:con.execute("INSERT INTO managed_tasks VALUES(?,?,?)",(task,json.dumps({"phase":phase,"version":4}),db.now()))
    if closed:record(task,"closed",{"receipt":{"status":"stopped"}})
    selected=archive.archive_index(q=task,status="ended" if ended else "active")
    excluded=archive.archive_index(q=task,status="active" if ended else "ended")
    assert selected["total"]==1 and excluded["total"]==0
    assert selected["records"][0]["id"]==task and selected["records"][0]["is_ended"] is ended
    assert selected["records"][0]["history_only"] is True

def test_archive_index_sql_pagination_has_one_task_per_generation_and_no_workspace_merge(task,seed_task):
    prefix="archive-index-"+ident()
    ids=[]
    for i in range(17):
        task_id=prefix+"-"+str(i);seed_task(task_id);ids.append(task_id)
        with db.connect() as con:
            con.execute("UPDATE tasks SET name=?,workspace=?,updated_at=? WHERE id=?",(prefix+" task "+str(i),"/same/missing/workspace","2026-10-07T01:00:00Z",task_id))
            con.execute("INSERT INTO managed_tasks VALUES(?,?,?)",(task_id,json.dumps({"phase":"running","version":i+1,"binding_history":[{"domain_id":x,"version":x} for x in range(1,4)]}),db.now()))
        for generation in range(1,4):record(task_id,"policy_active",{"version":generation,"binding":{"domain_id":generation}})
    pages=[archive.archive_index(prefix,page_number=n,limit=5) for n in range(4)]
    flattened=[r for page in pages for r in page["records"]]
    assert all(p["total"]==17 and p["pages"]==4 for p in pages)
    assert len(flattened)==len({r["id"] for r in flattened})==17
    assert {r["id"] for r in flattened}==set(ids)
    assert all(r["workspace"]["path"]=="/same/missing/workspace" for r in flattened)
    assert archive.archive_index(prefix,page_number=8,limit=5)["records"]==[]

def test_archive_index_search_uses_snapshot_source_and_escapes_wildcards(task,seed_task):
    other=ident();seed_task(other)
    with db.connect() as con:
        wid=ident()
        con.execute("UPDATE tasks SET name='literal_%_match' WHERE id=?",(task,))
        con.execute("UPDATE tasks SET name='literalabmatch' WHERE id=?",(other,))
        con.execute("INSERT INTO agent_workspaces(id,agent_id,name,path,origin,created_at) VALUES(?,?,?,?,?,?)",(wid,"later-instance","source","/later/path","native",db.now()))
        con.execute("INSERT INTO workspace_task_sources VALUES(?,?,?,?,?)",(task,wid,"manifest","{}",db.now()))
        con.execute("INSERT INTO bootstrap_contexts VALUES(?,?,?,?,?)",(task,"custom",json.dumps({"workspace_source":{"id":wid,"agent_id":"historical-instance","path":"/historical/source"}}),"ctxhash",db.now()))
    assert archive.archive_index("_%")["total"]==1
    row=archive.archive_index("/historical/source")["records"][0]
    assert row["id"]==task and row["source"]["agent_id"]=="historical-instance"
    assert row["source"]["path"]=="/historical/source"
    assert all(r["id"]!=task for r in archive.archive_index("later-instance")["records"])

def test_archive_index_endpoint_auth_and_input_contract(task):
    from agentscope_app.main import app
    with TestClient(app) as client:
        assert client.get("/api/task-archives").status_code==401
        headers={"Authorization":"Bearer test-admin-token-not-for-production"}
        result=client.get("/api/task-archives",params={"q":task,"status":"all","page":0,"limit":1},headers=headers)
        assert result.status_code==200 and result.json()["records"][0]["id"]==task
        assert result.json()["page"]==0 and result.json()["pages"]==1
        for params in ({"limit":51},{"limit":0},{"page":-1},{"status":"unknown"},{"q":"x"*501}):
            assert client.get("/api/task-archives",params=params,headers=headers).status_code==422


def test_task_creation_event_keeps_creation_semantics_after_failure(task):
    before=archive.event_detail(task,"tasks:"+task+":record")
    with db.connect() as con:
        con.execute("UPDATE tasks SET status='failed',ended_at=? WHERE id=?",(db.now(),task))
    after=archive.event_detail(task,"tasks:"+task+":record")
    assert before["status"]==after["status"]=="created"
    assert after["detail"]["status"]=="created" and "ended_at" not in after["detail"]
    assert archive.archive(task)["header"]["status"]=="failed"



def test_independent_operation_probe_metadata_and_provenance_survive_projection(task,seed_task):
    kernel={"op":"write","target":"/tmp/task/guard.py","pid":321,"process_domain_id":44,"blocked":True,"event_id":"kernel-explicit-1","rule":{"name":"keep","reason":"protect source","clause_op":"write"},"secret":"KERNEL SECRET","raw_stream":"PRIVATE STREAM"}
    payload={"probe":{"operation":"write","target":"/tmp/task/guard.py","pid":321,"ppid":300,"attempted":True,"blocked":True,"success":False,"errno":13,"error":"permission denied; secret=HIDDEN","serialized":"RAW PROBE CONTENT","reasoning":"PRIVATE THOUGHT"},"probe_binding":{"domain_verified":True,"process_cgroup":"/task/scope","starttime":"1234","credential":"BINDING SECRET"},"domain_id":44,"classification":"correct_block","expected":"deny","effect_verified":False,"before_hash":"before","after_hash":"before","kernel_events":[kernel],"kernel_event_ids":["explicit-linked-event"],"authority":"independent_fixed_operation_probe","token":"TOKEN SECRET"}
    event=record(task,"operation_verified",payload)
    summary=next(e for e in archive.events(task)["events"] if e["id"]==event)
    full=archive.event_detail(task,event)
    for item in (summary,full):
        assert item["task_id"]==task
        assert item["source"]==item["storage_source"]=="managed_events"
        assert item["action_source"]==item["detail"]["action_source"]=="independent_probe"
        d=item["detail"]
        assert (d["operation"],d["target"],d["pid"],d["domain_id"])==("write","/tmp/task/guard.py",321,44)
        assert d["classification"]=="correct_block" and d["expected"]=="deny"
        assert d["effect_verified"] is False and d["before_hash"]==d["after_hash"]=="before"
        assert d["probe"]["errno"]==13 and d["probe_binding"]["domain_verified"] is True
        assert d["kernel_events"][0]["event_id"]=="kernel-explicit-1"
        assert d["kernel_event_ids"]==["explicit-linked-event"]
    output=json.dumps([summary,full])
    for secret in ("KERNEL SECRET","PRIVATE STREAM","HIDDEN","RAW PROBE CONTENT","PRIVATE THOUGHT","BINDING SECRET","TOKEN SECRET"):
        assert secret not in output
    other=ident();seed_task(other)
    # A coincident PID/domain on another task never creates a cross-task link.
    record(other,"operation_verified",payload)
    with pytest.raises(HTTPException) as error:archive.event_detail(other,event)
    assert error.value.status_code==404


@pytest.mark.parametrize("flags,expected_source",[
    ({"verification_probe":True,"native_sdk_verification":False},"independent_probe"),
    ({"verification_probe":False,"native_sdk_verification":True},"independent_probe"),
    ({"verification_probe":False,"native_sdk_verification":False},"kernel"),
    ({},"kernel"),
])
def test_kernel_retains_recorded_probe_flags_without_pid_based_attribution(task,flags,expected_source):
    event=record(task,"kernel",{"event":{"op":"unlink","target":"/tmp/task/guard.py","pid":321,"process_domain_id":44,"rule":{"name":"keep"}},"authority":"root_owned_kernel_event","correlation":"exact_process_domain; tool_unresolved",**flags})
    for item in (archive.events(task,"kernel")["events"][0],archive.event_detail(task,event)):
        assert item["storage_source"]=="managed_events" and item["action_source"]==expected_source
        d=item["detail"]
        assert d["operation"]=="unlink" and d["pid"]==321 and d["domain_id"]==44
        assert d["kernel"]["rule"]["name"]=="keep"
        assert d["authority"]=="root_owned_kernel_event"
        for key in ("verification_probe","native_sdk_verification"):
            assert (key in d)==(key in flags)
            if key in flags:assert d[key] is flags[key]


def test_native_tool_and_controller_provenance_is_not_table_name(task):
    tool=record(task,"tool_result",{"pid":321,"name":"read_file","target":"/tmp/task/input","succeeded":True})
    pause=record(task,"control_pause",{"reason":"review required"})
    assert archive.event_detail(task,tool)["action_source"]=="native_tool"
    assert archive.event_detail(task,pause)["action_source"]=="controller"


def test_stage_highlights_find_early_loads_and_closure_beyond_recent_activity(task,seed_task):
    approval=record(task,"startup_confirmed",{"version":1,"authority":"human_review"},"2026-10-07T00:00:00Z")
    loads=[]
    for version in (3,4):
        loads.append(record(task,"policy_active",{"version":version,"binding":{"domain_id":40+version,"runner_pid":300+version,"token":"NEVER EXPORT LOAD SECRET"},"session_id":"retained-session"},f"2026-10-07T00:0{version}:00Z"))
    close=record(task,"closed",{"receipt":{"status":"stopped","quiesced_pids":[304],"secret":"NEVER EXPORT CLOSE SECRET"},"temporary_grants":"revoked"},"2026-10-07T00:05:00Z")
    for i in range(125):
        stamp=f"2026-10-07T01:{i//60:02}:{i%60:02}Z"
        record(task,"tool_result",{"pid":999,"name":"read_file","succeeded":True},stamp)
        record(task,"operation_verified",{"probe":{"operation":"read","target":"/tmp/task/input","pid":999},"classification":"correct_allow"},stamp)
        record(task,"control_pause",{"reason":"frequent assessment"},stamp)
    foreign=ident();seed_task(foreign)
    foreign_load=record(foreign,"policy_active",{"version":99,"binding":{"domain_id":99}},"2026-10-07T03:00:00Z")
    first=archive.events(task,limit=50)
    result=archive.archive(task,limit=50)
    assert result["events"]==first["events"] and result["next_cursor"]==first["next_cursor"] and result["total"]==first["total"]
    assert not set(loads)&{e["id"] for e in result["events"]}
    highlights=result["stage_previews"]["execution"]["highlights"]
    assert {e["id"] for e in highlights}==set(loads)
    assert {e["version"] for e in highlights}=={3,4}
    assert all(e["task_id"]==task and e["history_only"] for e in highlights)
    assert all(e["detail"]["binding"]["runner_pid"] in (303,304) for e in highlights)
    assert foreign_load not in json.dumps(result)
    assert result["stage_previews"]["preparation"]["highlights"][0]["id"]==approval
    assert result["stage_previews"]["closure"]["highlights"][0]["id"]==close
    assert "NEVER EXPORT" not in json.dumps(result)
    # Dedicated highlights add no second timeline facts or pagination cursor.
    assert len(walk(task,limit=37))==result["total"]


def test_stage_highlight_cap_prioritizes_loads_over_frequent_review_receipts(task):
    loads=[record(task,"policy_active",{"version":v,"binding":{"domain_id":v}},f"2026-10-07T00:0{v}:00Z") for v in (3,4)]
    for i in range(45):
        record(task,"change_review",{"decision":"reject","job_id":"job-"+str(i)},f"2026-10-07T02:00:{i:02}Z")
        record(task,"candidate",{"proposal":{"decision":"no_change"}},f"2026-10-07T02:01:{i:02}Z")
        record(task,"candidate",{"proposal":{"decision":"guidance_only"}},f"2026-10-07T02:02:{i:02}Z")
    preview=archive.archive(task)["stage_previews"]["execution"]
    assert preview["highlight_total"]==47 and preview["highlight_limit"]==20
    assert len(preview["highlights"])==20 and set(loads)<={e["id"] for e in preview["highlights"]}
    assert not any(e["kind"] in ("candidate","control_pause","operation_verified") for e in preview["highlights"])


def test_historical_domain_graph_legacy_is_empty_and_never_probes(task,monkeypatch):
    from agentscope_app.archive import historical
    from agentscope_app.managed import topology,records
    monkeypatch.setattr(topology,"graph",lambda *a,**k:pytest.fail("live topology graph forbidden"))
    monkeypatch.setattr(records,"workbench",lambda *a,**k:pytest.fail("workbench forbidden"))
    value=historical.graph(task)
    assert value["version"] is None and value["versions"]==[] and value["nodes"]==[]
    assert value["status"]=="not_recorded" and value["available"] is False
    assert value["live"] is False and value["historical"] is True and value["checked_at"] is None


def test_historical_domains_use_exact_receipt_version_and_verified_dsl(task,monkeypatch,tmp_path,seed_task):
    from agentscope_app.archive import historical
    from agentscope_app.managed import topology,records
    import yaml
    text=yaml.safe_dump({"policy":'source AGENT = process descendants\nrule keep:\n  block write file "/tmp/task/guard" if AGENT\n  because "secret=DO_NOT_EXPORT"\n'})
    monkeypatch.setattr(topology,"POLICY_ROOT",tmp_path)
    reads=[]
    monkeypatch.setattr(topology,"owned_text",lambda path,root:reads.append(str(path)) or text)
    monkeypatch.setattr(topology,"graph",lambda *a,**k:pytest.fail("live graph forbidden"))
    monkeypatch.setattr(records,"workbench",lambda *a,**k:pytest.fail("live workbench forbidden"))
    with db.connect() as con:
        con.execute("INSERT INTO managed_tasks VALUES(?,?,?)",(task,json.dumps({"phase":"running","version":99,"binding":{"domain_id":999,"runner_pid":999},"session_id":"current-unrelated"}),db.now()))
    for version in (1,3):
        record(task,"policy_active",{"version":version,"policy_hash":controller.digest(text),"binding":{"domain_id":40+version,"runner_pid":300+version,"watch_pid":400+version},"verification":{"passed":True}},f"2026-10-07T00:0{version}:00Z")
    value=historical.graph(task)
    assert value["version"]==3 and [v["version"] for v in value["versions"]]==[3,1]
    assert all(n["live"] is False and n["historical"] is True for n in value["nodes"])
    assert {n["pid"] for n in value["nodes"] if n["kind"]=="process"}=={303,403}
    assert {e["kind"] for e in value["edges"]}=={"recorded_binding","load_observation"}
    assert next(e for e in value["edges"] if e["to"].endswith(":watch:403"))["kind"]=="load_observation"
    assert not any(e["kind"] in ("spawn","membership") for e in value["edges"])
    assert not any(n.get("domain_id")==0 for n in value["nodes"])
    assert all("dsl" not in n for n in value["nodes"])
    d=historical.domain_detail(task,"v3:task")
    assert d["available"] and d["historical"] and d["live"] is False
    assert d["domain_id"]==43 and d["loading_verification_passed"] is True and d["labels"]==["AGENT"]
    assert "rule keep" in d["dsl"] and "DO_NOT_EXPORT" not in json.dumps(d)
    assert any("v10003/policy.yaml" in p for p in reads)
    other=ident();seed_task(other)
    for fn,args in ((historical.graph,(other,3)),(historical.domain_detail,(other,"v3:task")),(historical.graph,(task,99)),(historical.domain_detail,(task,"v99:task")),(historical.domain_detail,(task,"../../etc/passwd"))):
        with pytest.raises(HTTPException) as error:fn(*args)
        assert error.value.status_code==404


@pytest.mark.parametrize("artifact",["missing","hash_mismatch"])
def test_historical_domain_missing_or_unverified_material_is_unavailable(task,monkeypatch,tmp_path,artifact):
    from agentscope_app.archive import historical
    from agentscope_app.managed import topology
    monkeypatch.setattr(topology,"POLICY_ROOT",tmp_path)
    if artifact=="hash_mismatch":monkeypatch.setattr(topology,"owned_text",lambda *a:"policy: wrong")
    record(task,"policy_active",{"version":2,"policy_hash":"not-the-file-hash","binding":{"domain_id":22,"runner_pid":202}})
    value=historical.graph(task,2)
    assert value["available"] is False and value["live"] is False
    assert value["missing_sources"] and all(n.get("available") is False for n in value["nodes"] if n["kind"]=="domain")
    d=historical.domain_detail(task,"v2:task")
    assert d["available"] is False and "dsl" not in d
    baseline=historical.domain_detail(task,"v2:baseline")
    assert baseline["available"] is False and baseline["domain_id"] is None and "dsl" not in baseline
    assert baseline["missing_reason"]=="trusted_baseline_material_not_recorded"


def test_historical_baseline_without_expected_hash_never_exports_dsl_or_labels(task,monkeypatch):
    from agentscope_app.archive import historical
    from agentscope_app.managed import topology
    record(task,"policy_active",{"version":1,"policy_hash":"task-hash","binding":{"domain_id":10}})
    monkeypatch.setattr(topology,"domain_sources",lambda *a:[{"key":"v1:baseline","kind":"domain","role":"baseline","version":1,"domain_id":5,"available":True,"dsl":"PRIVATE UNVERIFIED DSL","labels":["UNVERIFIED"],"policy_hash":"computed-without-expected","source":"root_owned_watch_artifact"},{"key":"v1:task","kind":"domain","role":"task","version":1,"domain_id":10,"available":True,"source":"confirmed_policy_hash","labels":[]}])
    d=historical.domain_detail(task,"v1:baseline")
    assert d["available"] is False and d["domain_id"]==5 and d["labels"]==[]
    assert "dsl" not in d and "policy_hash" not in d and d["missing_reason"]=="missing_expected_bundle_hash"
    g=historical.graph(task)
    assert g["missing_sources"][0]["reason"]=="missing_expected_bundle_hash"
    assert g["available"] is True and g["notice"] is not None


def test_archive_domain_routes_have_task_ownership_and_no_live_calls(task,seed_task):
    app=FastAPI();app.include_router(router)
    record(task,"policy_active",{"version":2,"policy_hash":"missing","binding":{"domain_id":22}})
    other=ident();seed_task(other)
    with TestClient(app) as client:
        assert client.get(f"/api/tasks/{task}/archive/domains?version=2").json()["historical"] is True
        detail=client.get(f"/api/tasks/{task}/archive/domains/v2:task")
        assert detail.status_code==200 and detail.json()["available"] is False
        assert client.get(f"/api/tasks/{other}/archive/domains/v2:task").status_code==404
        assert client.get(f"/api/tasks/{task}/archive/domains?version=0").status_code==422


def test_historical_topology_and_dsl_execute_only_reads(task,monkeypatch):
    from agentscope_app.archive import historical
    record(task,"policy_active",{"version":1,"policy_hash":"missing","binding":{"domain_id":11,"runner_pid":101,"watch_pid":102}})
    original=db.connect;sql=[]
    @contextmanager
    def traced():
        with original() as con:
            con.set_trace_callback(sql.append)
            yield con
    monkeypatch.setattr(db,"connect",traced)
    historical.graph(task);historical.domain_detail(task,"v1:task");historical.domain_detail(task,"v1:baseline")
    assert not [q for q in sql if q.lstrip().upper().startswith(("INSERT","UPDATE","DELETE","CREATE","ALTER","REPLACE"))]

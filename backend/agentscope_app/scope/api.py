import json
import time
from fastapi import APIRouter, HTTPException, Request
from .. import db
from . import demo, manager
from .models import ChangeRequest, Review, ToolCall

router = APIRouter()

def run(function, *args, **kwargs):
    try: return function(*args, **kwargs)
    except (ValueError, RuntimeError) as error: raise HTTPException(409, str(error))

@router.post("/api/scope-demo/tasks")
def create(): return demo.create()

@router.get("/api/tasks/{task_id}/scope-manager")
def current(task_id: str): return run(manager.get_scope, task_id)

@router.post("/api/tasks/{task_id}/scope-manager/cold")
def cold(task_id: str): return run(manager.cold_start, task_id)

@router.post("/api/tasks/{task_id}/scope-manager/changes")
def assess(task_id: str, body: ChangeRequest): return run(manager.assess, task_id, body)

@router.post("/api/tasks/{task_id}/scope-manager/changes/{delta_id}/review")
def review(task_id: str, delta_id: str, body: Review): return run(manager.review_and_apply, task_id, delta_id, body)

@router.post("/api/tasks/{task_id}/scope-manager/close")
def close(task_id: str): return run(manager.close_task, task_id)

def agent_task(task_id, request):
    token = request.headers.get("authorization", "").removeprefix("Bearer ")
    with db.connect() as con:
        session = con.execute("SELECT phase FROM scope_sessions WHERE task_id=?", (task_id,)).fetchone()
        if session:
            credential = con.execute("SELECT id FROM task_credentials WHERE task_id=? AND token_sha256=? AND revoked_at IS NULL", (task_id, manager.digest(token))).fetchone()
            if credential and session["phase"] != "ended": return
            raise HTTPException(401, "任务凭据已失效")
    from ..main import require_agent_task
    return require_agent_task(task_id, request)

@router.get("/api/plugin/tasks/{task_id}/scope-manager/gate")
def gate(task_id: str, request: Request):
    agent_task(task_id, request)
    with db.connect() as con:
        row = con.execute("SELECT * FROM scope_sessions WHERE task_id=?", (task_id,)).fetchone()
        if not row: return {"enabled": False}
        snapshot = manager.active(con, dict(row))
        task, _ = manager.task_and_session(con,task_id)
        messages = [db.row_dict(r) for r in con.execute("SELECT * FROM scope_events WHERE task_id=? AND source IN ('user_message','agent_request') ORDER BY id DESC LIMIT 20", (task_id,))]
        return {"enabled": True, "gate": row["gate"], "phase": row["phase"],
                "task":{"workspace":task["workspace"],"fixed_commit":task["commit_sha"],"required_report":task["output_dir"]+"/report.md"},
                "snapshot_id": row["active_snapshot_id"], "message_revision": row["message_revision"],
                "scope": snapshot["payload"] if snapshot else None,
                "messages": list(reversed(messages))}

@router.post("/api/plugin/tasks/{task_id}/scope-manager/changes")
def agent_assess(task_id: str, body: ChangeRequest, request: Request):
    agent_task(task_id, request)
    return run(manager.assess, task_id, body, actor="DSH")

@router.post("/api/plugin/tasks/{task_id}/scope-manager/tool-result")
def tool_result(task_id: str, body: ToolCall, request: Request):
    agent_task(task_id, request)
    with db.connect() as con:
        task, session = manager.task_and_session(con, task_id)
        name = str(body.args.get("name", ""))[:100]
        source_key = str(body.args.get("call_id", ""))[:120]
        if not source_key: raise HTTPException(400, "call_id required")
        manager.event(con, task_id, "tool_result", source_key, {"name": name, "succeeded": body.args.get("succeeded") is True,
                      "scope_snapshot": session["active_snapshot_id"], "message_revision": session["message_revision"],
                      "started": body.args.get("started"), "authority": "native_hook_metadata"})
    return {"stored": True}

@router.post("/api/plugin/tasks/{task_id}/scope-manager/tool-boundary")
def boundary(task_id: str, body: ToolCall, request: Request):
    agent_task(task_id, request)
    kind = body.args.get("kind")
    if kind not in ("pause", "context_delivery"): raise HTTPException(400, "未登记的工具边界事件")
    with db.connect() as con:
        task, session = manager.task_and_session(con, task_id)
        manager.event(con, task_id, "boundary_" + kind, str(body.args.get("call_id"))[:120] + "-" + str(session["message_revision"]),
            {"tool": str(body.args.get("name"))[:100], "snapshot_id": session["active_snapshot_id"],
             "message_revision": session["message_revision"], "gate":session["gate"], "authority":"native_hook_metadata"})
    return {"stored":True}

@router.post("/api/generator/tasks/{task_id}/scope-jobs/{job_id}/tools/{tool}")
def generator_tool(task_id: str, job_id: str, tool: str, body: ToolCall, request: Request):
    token = request.headers.get("authorization", "").removeprefix("Bearer ")
    with db.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        job = con.execute("SELECT * FROM scope_jobs WHERE id=? AND task_id=? AND status='running' AND token_hash=? AND expires_at>?",
                          (job_id, task_id, manager.digest(token), time.time())).fetchone()
        if not job or job["calls"] >= 20: raise HTTPException(401, "生成凭据已过期、撤销或超出预算")
        con.execute("UPDATE scope_jobs SET calls=calls+1 WHERE id=?", (job_id,))
        delta = dict(con.execute("SELECT * FROM scope_deltas WHERE id=?", (job["delta_id"],)).fetchone())
        if tool == "get_runtime_context": return json.loads(job["result_json"])["context"]
        if tool == "search_reviewed_history":
            rows = con.execute("SELECT id,text,source_repo FROM strategies WHERE status='approved' AND is_archived=0 LIMIT 30").fetchall()
            return {"policies": [dict(r) for r in rows], "applicability_requires_evidence": True}
        if tool == "submit_scope_proposal":
            try: return manager.store_proposal(con, delta, body.args)
            except ValueError as error:
                manager.event(con, task_id, "proposal_diagnostic", job_id + "-" + str(job["calls"]),
                              {"error": str(error)[:1500], "decision": body.args.get("decision")})
                con.commit()
                raise HTTPException(409, str(error))
        raise HTTPException(400, "此凭据只允许读取证据、查已审核历史和提交候选")

@router.post("/api/plugin/tasks/{task_id}/scope-manager/report")
def report(task_id: str, body: ToolCall, request: Request):
    agent_task(task_id, request)
    from ..agent_bridge.api import clean
    summary = clean(str(body.args.get("summary", "")))[:2000]
    with db.connect() as con:
        manager.event(con, task_id, "agent_report", str(body.args.get("request_key", ""))[:100],
                      {"kind": str(body.args.get("kind", ""))[:40], "summary": summary, "source": "agent_report"})
    return {"stored": True, "kernel_effect": "not_claimed"}

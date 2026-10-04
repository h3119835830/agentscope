"""Durable pull transport. Task tokens cannot approve, load, or attest enforcement."""
import hashlib
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from .. import db

router = APIRouter()
PROTOCOL = "agentscope.agent-bridge/v1"


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Connect(Body):
    name: str = Field(min_length=1, max_length=80)
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)


class Message(Body):
    text: str = Field(min_length=1, max_length=4000)
    request_key: str = Field(min_length=1, max_length=100)


class BoundOperation(Body):
    request_key: str = Field(min_length=1, max_length=100)
    expected_snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class Feedback(BoundOperation):
    kind: Literal["tool_feedback", "scope_blocked", "progress", "result"]
    operation: str = Field(default="", max_length=120)
    target: str = Field(default="", max_length=1000)
    summary: str = Field(min_length=1, max_length=2000)


class ScopeChange(BoundOperation):
    kind: Literal["restrict", "expand"]
    path: str | None = Field(default=None, max_length=1000)
    justification: str = Field(min_length=4, max_length=1000)


class Ack(Body):
    status: Literal["received", "handled"] = "received"


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def clean(text):
    # Basic credential masking, not an invitation to submit raw traces or private reasoning.
    text = re.sub(r"(?i)\bbearer\s+[^\s,;]+", "Bearer [REDACTED]", text)
    return re.sub(r"(?i)\b(api[_-]?key|access[_-]?token|password)\s*[:=]\s*[^\s,;]+",
                  r"\1=[REDACTED]", text)


def snapshot(con, task_id):
    row = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(404, "任务不存在")
    task = dict(row)
    if task["status"] != "running":
        raise HTTPException(409, "任务当前未运行；连接不能继续使用")
    version = con.execute("SELECT * FROM policy_versions WHERE task_id=? AND version=? AND status='approved'",
                          (task_id, task["active_version"])).fetchone()
    if not version or version["compile_state"] != "compiled":
        raise HTTPException(409, "当前任务没有完整编译且获批的策略版本")
    bundle_hash = hashlib.sha256(version["policy_yaml"].encode()).hexdigest()
    info = json.loads(version["compile_json"] or "{}")
    if info.get("submitted_bundle_hash") and info["submitted_bundle_hash"] != bundle_hash:
        raise HTTPException(409, "批准的策略包 hash 已改变")
    deployment = con.execute("SELECT id,receipt_json FROM history_deployments WHERE task_id=? AND policy_version_id=? AND status='loaded' ORDER BY created_at DESC LIMIT 1",
                             (task_id, version["id"])).fetchone()
    epoch = digest({"task_id": task_id, "deployment_id": deployment["id"] if deployment else None,
                    "policy_id": version["id"], "pid": task["active_pid"],
                    "domain": task["active_domain_id"], "watch": task["watch_pid"]})
    restrictions = [dict(r) for r in con.execute("SELECT id,path,justification,result_json FROM scope_requests WHERE task_id=? AND kind='restrict' AND status='approved' ORDER BY created_at,id", (task_id,))]
    result = {"protocol": PROTOCOL, "task_id": task_id, "run_key": epoch,
              "repository": task["repo"], "fixed_commit": task["commit_sha"],
              "workspace": task["workspace"], "output_dir": task["output_dir"],
              "dsh_profile": task["dsh_profile"],
              "policy_version": version["version"], "bundle_hash": bundle_hash,
              "dsl": version["dsl_text"], "scope_revision": len(restrictions),
              "runtime_restrictions": restrictions,
              "guidance": info.get("policy_ir", {}).get("selected_history", []),
              "task_domain": task["active_domain_id"], "task_runner_pid": task["active_pid"],
              "capabilities": ["read_context", "read_messages", "ack_messages", "report_feedback", "request_scope_change"],
              "execution_capabilities": {"push_into_agent_context": False, "pause_agent": False,
                  "resume_agent_session": False, "launch_remote_agent": False, "verified_delta_apply": False},
              "runtime_pi": "not_connected", "scope_changes_require_review": True}
    result["snapshot_hash"] = digest(result)
    return result, task


def authorized(con, task_id, request):
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""
    if not token:
        raise HTTPException(401, "缺少任务接入凭据")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    connection = con.execute("SELECT * FROM agent_connections WHERE task_id=? AND token_sha256=?", (task_id, token_hash)).fetchone()
    legacy = con.execute("SELECT * FROM task_credentials WHERE task_id=? AND token_sha256=? AND revoked_at IS NULL", (task_id, token_hash)).fetchone()
    if not connection and not legacy:
        raise HTTPException(401, "接入凭据无效或不属于此任务")
    if connection and (connection["revoked_at"] or connection["expires_at"] <= db.now() or (connection["legacy_credential_id"] and not legacy)):
        raise HTTPException(401, "接入凭据已撤销或过期")
    current, task = snapshot(con, task_id)
    if connection and connection["run_key"] != current["run_key"]:
        raise HTTPException(409, "进程批次已改变；旧连接不可用于新运行")
    if not connection:
        ident = uuid.uuid4().hex
        expiry = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        con.execute("INSERT INTO agent_connections(id,task_id,name,adapter,token_sha256,legacy_credential_id,run_key,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (ident, task_id, "DSH 受管插件", "dsh", token_hash, legacy["id"], current["run_key"], db.now(), expiry))
        db.audit(con, task_id, "agent_connected", "AgentScope", {"connection_id": ident, "adapter": "dsh", "run_key": current["run_key"]})
        connection = con.execute("SELECT * FROM agent_connections WHERE id=?", (ident,)).fetchone()
    con.execute("UPDATE agent_connections SET last_seen_at=? WHERE id=?", (db.now(), connection["id"]))
    return dict(connection), current, task


def replay(con, connection, action, body, current):
    data = body.model_dump()
    payload_hash = digest(data)
    row = con.execute("SELECT * FROM agent_operations WHERE connection_id=? AND operation_key=?", (connection["id"], body.request_key)).fetchone()
    if row:
        if row["action"] != action or row["payload_hash"] != payload_hash:
            raise HTTPException(409, "幂等键已用于不同请求")
        return json.loads(row["result_json"])
    if body.expected_snapshot_hash != current["snapshot_hash"]:
        raise HTTPException(409, "Scope 上下文已改变；请重新读取后再提交")
    return None


def remember(con, connection, action, body, result):
    con.execute("INSERT INTO agent_operations VALUES(?,?,?,?,?)", (connection["id"], body.request_key, action, digest(body.model_dump()), json.dumps(result)))
    return result


def put_message(con, current, kind, content, source_ref):
    ident = uuid.uuid4().hex
    con.execute("INSERT INTO agent_messages(id,task_id,run_key,kind,content_json,source_ref,created_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(task_id,run_key,source_ref) DO NOTHING",
                (ident, current["task_id"], current["run_key"], kind, json.dumps(content, ensure_ascii=False), source_ref, db.now()))
    return con.execute("SELECT * FROM agent_messages WHERE task_id=? AND run_key=? AND source_ref=?", (current["task_id"], current["run_key"], source_ref)).fetchone()


def sync_reviews(con, current):
    for row in con.execute("SELECT id,status,resulting_version,result_json FROM scope_requests WHERE task_id=? AND status IN ('approved','rejected','failed') ORDER BY created_at,id", (current["task_id"],)).fetchall():
        data = dict(row)
        data["request_id"] = data.pop("id")
        # Existing 'delta_applied' receipts do not establish probe-confirmed enforcement.
        data["kernel_effect"] = "not_verified_by_bridge"
        put_message(con, current, "scope_review", data, "review:" + row["id"] + ":" + row["status"])


def validate_review_binding(con, task_id, request_id):
    bound = con.execute("SELECT run_key,snapshot_hash FROM agent_scope_bindings WHERE request_id=?", (request_id,)).fetchone()
    if bound:
        current, _ = snapshot(con, task_id)
        if bound["run_key"] != current["run_key"] or bound["snapshot_hash"] != current["snapshot_hash"]:
            raise HTTPException(409, "Agent 申请基于的运行或 Scope 已改变；需重新申请，不能批准旧申请")


@router.post("/api/tasks/{task_id}/agent-connections")
def connect_agent(task_id: str, body: Connect):
    with db.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        current, _ = snapshot(con, task_id)
        token = secrets.token_urlsafe(32)
        ident = uuid.uuid4().hex
        expiry = (datetime.now(timezone.utc) + timedelta(seconds=body.ttl_seconds)).isoformat()
        con.execute("INSERT INTO agent_connections(id,task_id,name,adapter,token_sha256,run_key,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?)",
                    (ident, task_id, clean(body.name), "http", hashlib.sha256(token.encode()).hexdigest(), current["run_key"], db.now(), expiry))
        db.audit(con, task_id, "agent_connection_created", "用户", {"connection_id": ident, "adapter": "http", "expires_at": expiry})
        return {"protocol": PROTOCOL, "connection_id": ident, "task_id": task_id, "token": token,
                "expires_at": expiry, "run_key": current["run_key"], "enforcement": "control_plane_only"}


@router.post("/api/tasks/{task_id}/agent-connections/{connection_id}/revoke")
def revoke_agent(task_id: str, connection_id: str):
    with db.connect() as con:
        row = con.execute("SELECT legacy_credential_id FROM agent_connections WHERE id=? AND task_id=?", (connection_id, task_id)).fetchone()
        if row and row["legacy_credential_id"]:
            con.execute("UPDATE task_credentials SET revoked_at=COALESCE(revoked_at,?) WHERE id=?", (db.now(), row["legacy_credential_id"]))
        changed = con.execute("UPDATE agent_connections SET revoked_at=COALESCE(revoked_at,?) WHERE id=? AND task_id=?", (db.now(), connection_id, task_id)).rowcount
        if not changed:
            raise HTTPException(404, "连接不存在")
        db.audit(con, task_id, "agent_connection_revoked", "用户", {"connection_id": connection_id})
    return {"status": "revoked"}


@router.get("/api/agent/tasks/{task_id}/context")
def context(task_id: str, request: Request):
    with db.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        connection, current, _ = authorized(con, task_id, request)
    current["connection_id"] = connection["id"]
    current["connection_enforcement"] = "control_plane_only" if connection["adapter"] == "http" else "task_binding_only"
    current["connection_process_attested"] = False
    # Live Broker evidence refers to the managed task, never to the remote caller.
    try:
        from ..broker_client import call
        status = call({"action": "status", "task_id": task_id}, timeout=2)
        current["task_binding_confirmed"] = bool(status.get("agent_status") == "running" and
            (status.get("child") or {}).get("child_id") == current["task_domain"] and
            status.get("runner_pid") == current["task_runner_pid"])
    except Exception:
        current["task_binding_confirmed"] = False
    return current


@router.post("/api/agent/tasks/{task_id}/feedback")
def feedback(task_id: str, body: Feedback, request: Request):
    with db.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        connection, current, _ = authorized(con, task_id, request)
        previous = replay(con, connection, "feedback", body, current)
        if previous:
            return previous
        ident = uuid.uuid4().hex
        con.execute("INSERT INTO agent_feedback(id,task_id,connection_id,run_key,snapshot_hash,kind,operation,target,summary,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (ident, task_id, connection["id"], current["run_key"], current["snapshot_hash"], body.kind,
                     clean(body.operation), clean(body.target), clean(body.summary), db.now()))
        db.audit(con, task_id, "agent_feedback_received", connection["name"], {"feedback_id": ident, "connection_id": connection["id"], "kind": body.kind, "source": "agent_report"})
        return remember(con, connection, "feedback", body, {"id": ident, "source": "agent_report", "assessment_status": "not_scheduled"})


@router.post("/api/agent/tasks/{task_id}/scope-requests")
def request_scope(task_id: str, body: ScopeChange, request: Request):
    with db.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        connection, current, task = authorized(con, task_id, request)
        previous = replay(con, connection, "scope_request", body, current)
        if previous:
            return previous
        from ..main import ScopeRequestBody, validate_scope_request
        original = ScopeRequestBody(kind=body.kind, path=body.path, justification=clean(body.justification), requested_by=connection["name"])
        validate_scope_request(task, original, con)
        ident = uuid.uuid4().hex
        con.execute("INSERT INTO scope_requests(id,task_id,kind,requested_change,path,justification,status,requested_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (ident, task_id, body.kind, "限制当前任务 Scope" if body.kind == "restrict" else "增加受控任务输出目录的写入权限",
                     body.path, original.justification, "pending_review", connection["name"], db.now()))
        con.execute("INSERT INTO agent_scope_bindings VALUES(?,?,?)", (ident, current["run_key"], current["snapshot_hash"]))
        db.audit(con, task_id, "scope_requested", connection["name"], {"request_id": ident, "connection_id": connection["id"], "snapshot_hash": current["snapshot_hash"], "kind": body.kind})
        return remember(con, connection, "scope_request", body, {"id": ident, "status": "pending_review"})


@router.post("/api/tasks/{task_id}/agent-messages")
def send_message(task_id: str, body: Message):
    with db.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        current, _ = snapshot(con, task_id)
        source_ref = "user:" + body.request_key
        old = con.execute("SELECT content_json FROM agent_messages WHERE task_id=? AND run_key=? AND source_ref=?", (task_id, current["run_key"], source_ref)).fetchone()
        content = {"text": clean(body.text), "effect": "guidance_only", "snapshot_hash": current["snapshot_hash"]}
        if old and json.loads(old["content_json"])["text"] != content["text"]:
            raise HTTPException(409, "幂等键已用于不同消息")
        row = put_message(con, current, "user_message", content, source_ref)
        if not old:
            db.audit(con, task_id, "agent_message_sent", "用户", {"message_id": row["id"], "run_key": current["run_key"]})
        return {"id": row["id"], "status": "queued", "kernel_effect": "unchanged"}


@router.get("/api/agent/tasks/{task_id}/messages")
def messages(task_id: str, request: Request, after: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    with db.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        connection, current, _ = authorized(con, task_id, request)
        sync_reviews(con, current)
        rows = [dict(r) for r in con.execute("SELECT m.*,r.status AS receipt_status FROM agent_messages m LEFT JOIN agent_message_receipts r ON r.message_id=m.id AND r.connection_id=? WHERE m.task_id=? AND m.run_key=? AND m.seq>? ORDER BY m.seq LIMIT ?",
                                            (connection["id"], task_id, current["run_key"], after, limit))]
        for row in rows:
            row["content"] = json.loads(row.pop("content_json"))
        return {"items": rows, "next_cursor": rows[-1]["seq"] if rows else after, "snapshot_hash": current["snapshot_hash"]}


@router.post("/api/agent/tasks/{task_id}/messages/{message_id}/ack")
def ack_message(task_id: str, message_id: str, body: Ack, request: Request):
    with db.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        connection, current, _ = authorized(con, task_id, request)
        row = con.execute("SELECT 1 FROM agent_messages WHERE id=? AND task_id=? AND run_key=?", (message_id, task_id, current["run_key"])).fetchone()
        if not row:
            raise HTTPException(404, "消息不属于此任务运行")
        old = con.execute("SELECT status FROM agent_message_receipts WHERE connection_id=? AND message_id=?", (connection["id"], message_id)).fetchone()
        state = "handled" if body.status == "handled" or old and old["status"] == "handled" else "received"
        con.execute("INSERT INTO agent_message_receipts VALUES(?,?,?,?,?) ON CONFLICT(connection_id,message_id) DO UPDATE SET status=excluded.status,handled_at=COALESCE(agent_message_receipts.handled_at,excluded.handled_at)",
                    (connection["id"], message_id, state, db.now(), db.now() if state == "handled" else None))
        if not old or old["status"] != state:
            db.audit(con, task_id, "agent_message_acknowledged", connection["name"], {"connection_id": connection["id"], "message_id": message_id, "status": state, "authority": "agent_report"})
        return {"id": message_id, "status": state, "authority": "agent_report", "kernel_effect": "not_verified_by_bridge"}


@router.get("/api/tasks/{task_id}/agent-bridge")
def inspect_bridge(task_id: str):
    with db.connect() as con:
        task = con.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(404, "任务不存在")
        try:
            current, _ = snapshot(con, task_id)
            sync_reviews(con, current)
        except HTTPException:
            current = None
        connections = [dict(r) for r in con.execute("SELECT id,name,adapter,run_key,created_at,expires_at,last_seen_at,revoked_at FROM agent_connections WHERE task_id=? ORDER BY created_at DESC LIMIT 100", (task_id,))]
        for c in connections:
            c["status"] = "revoked" if c["revoked_at"] else "expired" if c["expires_at"] <= db.now() else "ended" if not current else "stale" if c["run_key"] != current["run_key"] else "waiting" if not c["last_seen_at"] else "connected" if c["last_seen_at"] > (datetime.now(timezone.utc)-timedelta(seconds=30)).isoformat() else "offline"
        history = [dict(r) for r in con.execute("SELECT * FROM agent_messages WHERE task_id=? ORDER BY seq DESC LIMIT 100", (task_id,))]
        for m in history:
            m["content"] = json.loads(m.pop("content_json"))
            m["receipts"] = [dict(r) for r in con.execute("SELECT connection_id,status,received_at,handled_at FROM agent_message_receipts WHERE message_id=?", (m["id"],))]
        reports = [dict(r) | {"source": "agent_report"} for r in con.execute("SELECT * FROM agent_feedback WHERE task_id=? ORDER BY seq DESC LIMIT 100", (task_id,))]
        return {"protocol": PROTOCOL, "current": current, "connections": connections,
                "messages": history, "feedback": reports, "runtime_pi": "not_connected"}

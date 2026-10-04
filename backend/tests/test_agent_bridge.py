import hashlib
import importlib.util
import json
import uuid
from pathlib import Path
import pytest
from agentscope_app import db
from agentscope_app.main import issue_task_token, revoke_task_tokens

ADMIN = {"Authorization": "Bearer test-admin-token-not-for-production"}


@pytest.fixture
def running(seed_task):
    task = "bridge-" + uuid.uuid4().hex
    seed_task(task)
    with db.connect() as con:
        con.execute("UPDATE tasks SET active_version=1,active_domain_id=99,active_pid=101,watch_pid=102 WHERE id=?", (task,))
        con.execute("INSERT INTO policy_versions(id,task_id,version,layer,dsl_text,policy_yaml,compile_state,status,change_summary,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (uuid.uuid4().hex, task, 1, "task_start", "# base", "version: 1", "compiled", "approved", "test", db.now()))
    return task


def pair(client, task):
    response = client.post(f"/api/tasks/{task}/agent-connections", headers=ADMIN, json={"name": "External test adapter", "ttl_seconds": 60})
    assert response.status_code == 200, response.text
    value = response.json()
    return value, {"Authorization": "Bearer " + value["token"]}


def get_context(client, task, headers):
    response = client.get(f"/api/agent/tasks/{task}/context", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_http_pairing_has_no_admin_or_generator_authority(client, running):
    pair_data, headers = pair(client, running)
    current = get_context(client, running, headers)
    assert current["connection_enforcement"] == "control_plane_only"
    assert current["connection_process_attested"] is False
    assert current["runtime_pi"] == "not_connected"
    for path in ["/api/tasks", f"/api/tasks/{running}/launch", f"/api/tasks/{running}/versions/1/approve"]:
        response = client.get(path, headers=headers) if path == "/api/tasks" else client.post(path, headers=headers, json={"decision": "approve"})
        assert response.status_code == 401
    assert client.get("/api/agent/tasks/other/context", headers=headers).status_code == 401
    with db.connect() as con:
        serialized = str([dict(r) for r in con.execute("SELECT * FROM audit_log WHERE task_id=?", (running,))])
        saved = con.execute("SELECT token_sha256 FROM agent_connections WHERE id=?", (pair_data["connection_id"],)).fetchone()[0]
    assert pair_data["token"] not in serialized
    assert saved == hashlib.sha256(pair_data["token"].encode()).hexdigest()


def test_dsh_existing_token_attaches_and_revokes(client, running):
    token, _ = issue_task_token(running)
    headers = {"Authorization": "Bearer " + token}
    a = get_context(client, running, headers)
    b = get_context(client, running, headers)
    assert a["connection_id"] == b["connection_id"]
    assert a["connection_enforcement"] == "task_binding_only"
    revoke_task_tokens(running)
    assert client.get(f"/api/agent/tasks/{running}/messages", headers=headers).status_code == 401


def test_feedback_is_idempotent_scoped_and_not_kernel_evidence(client, running):
    _, headers = pair(client, running)
    current = get_context(client, running, headers)
    payload = {"kind": "scope_blocked", "summary": "Bearer secret-value password=bad", "request_key": "once", "expected_snapshot_hash": current["snapshot_hash"]}
    endpoint = f"/api/agent/tasks/{running}/feedback"
    first = client.post(endpoint, headers=headers, json=payload)
    assert first.status_code == 200
    assert client.post(endpoint, headers=headers, json=payload).json() == first.json()
    assert first.json()["assessment_status"] == "not_scheduled"
    assert client.post(endpoint, headers=headers, json={**payload, "summary": "different"}).status_code == 409
    assert client.post(endpoint, headers=headers, json={**payload, "request_key": "fake-kernel", "kind": "kernel_denied"}).status_code == 422
    view = client.get(f"/api/tasks/{running}/agent-bridge", headers=ADMIN).json()
    assert len(view["feedback"]) == 1
    assert "secret-value" not in view["feedback"][0]["summary"]
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM runtime_events WHERE task_id=?", (running,)).fetchone()[0] == 0


def test_stale_scope_hash_requires_reassessment(client, running):
    _, headers = pair(client, running)
    current = get_context(client, running, headers)
    with db.connect() as con:
        con.execute("INSERT INTO scope_requests(id,task_id,kind,requested_change,path,justification,status,requested_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (uuid.uuid4().hex, running, "restrict", "test", "/tmp/work/src", "new restriction", "approved", "test", db.now()))
    body = {"kind": "progress", "summary": "old context", "request_key": "stale", "expected_snapshot_hash": current["snapshot_hash"]}
    assert client.post(f"/api/agent/tasks/{running}/feedback", headers=headers, json=body).status_code == 409


@pytest.mark.parametrize("change", ["expired", "revoked", "ended", "epoch"])
def test_expiry_revocation_stop_and_restart_invalidate_connection(client, running, change):
    data, headers = pair(client, running)
    with db.connect() as con:
        if change == "expired":
            con.execute("UPDATE agent_connections SET expires_at='2000-01-01' WHERE id=?", (data["connection_id"],))
        elif change == "revoked":
            con.execute("UPDATE agent_connections SET revoked_at=? WHERE id=?", (db.now(), data["connection_id"]))
        elif change == "ended":
            con.execute("UPDATE tasks SET status='stopped' WHERE id=?", (running,))
        else:
            con.execute("UPDATE tasks SET active_pid=999 WHERE id=?", (running,))
    assert client.get(f"/api/agent/tasks/{running}/context", headers=headers).status_code in (401, 409)


def test_durable_delivery_and_monotonic_receipts(client, running):
    _, headers = pair(client, running)
    payload = {"text": "请先保存当前进展。", "request_key": "message-1"}
    endpoint = f"/api/tasks/{running}/agent-messages"
    sent = client.post(endpoint, headers=ADMIN, json=payload).json()
    assert client.post(endpoint, headers=ADMIN, json=payload).json() == sent
    assert client.post(endpoint, headers=ADMIN, json={**payload, "text": "changed"}).status_code == 409
    # New clients and service calls see the durable queue; reading alone is not ACK.
    read = client.get(f"/api/agent/tasks/{running}/messages", headers=headers).json()
    msg = read["items"][0]
    assert msg["receipt_status"] is None
    ack = f"/api/agent/tasks/{running}/messages/{sent['id']}/ack"
    assert client.post(ack, headers=headers, json={"status": "handled"}).json()["status"] == "handled"
    assert client.post(ack, headers=headers, json={"status": "received"}).json()["status"] == "handled"
    assert client.get(f"/api/agent/tasks/{running}/messages?after={read['next_cursor']}", headers=headers).json()["items"] == []
    with db.connect() as con:
        con.execute("UPDATE tasks SET active_pid=555 WHERE id=?", (running,))
    _, new_headers = pair(client, running)
    assert client.get(f"/api/agent/tasks/{running}/messages", headers=new_headers).json()["items"] == []
    assert client.post(ack, headers=new_headers, json={"status": "received"}).status_code == 404


def test_scope_request_review_notification_does_not_auto_approve(client, running):
    _, headers = pair(client, running)
    current = get_context(client, running, headers)
    payload = {"kind": "expand", "justification": "need isolated report output", "request_key": "scope-1", "expected_snapshot_hash": current["snapshot_hash"]}
    endpoint = f"/api/agent/tasks/{running}/scope-requests"
    first = client.post(endpoint, headers=headers, json=payload).json()
    assert first["status"] == "pending_review"
    assert client.post(endpoint, headers=headers, json=payload).json() == first
    reviewed = client.post(f"/api/tasks/{running}/scope-requests/{first['id']}/review", headers=ADMIN, json={"decision": "reject"})
    assert reviewed.status_code == 200
    msgs = client.get(f"/api/agent/tasks/{running}/messages", headers=headers).json()["items"]
    assert msgs[0]["kind"] == "scope_review"
    assert msgs[0]["content"]["status"] == "rejected"
    assert msgs[0]["content"]["kernel_effect"] == "not_verified_by_bridge"


def test_rq5_bootstrap_guard_remains(client, running):
    _, headers = pair(client, running)
    current = get_context(client, running, headers)
    with db.connect() as con:
        con.execute("INSERT INTO bootstrap_contexts(task_id,scenario_id,context_hash,context_json,created_at) VALUES(?,?,?,?,?)",
                    (running, "test", "h", "{}", db.now()))
    payload = {"kind": "expand", "justification": "attempt unsupported expansion", "request_key": "rq5", "expected_snapshot_hash": current["snapshot_hash"]}
    assert client.post(f"/api/agent/tasks/{running}/scope-requests", headers=headers, json=payload).status_code == 409


def test_corrupt_approval_hash_blocks_pairing(client, running):
    with db.connect() as con:
        con.execute("UPDATE policy_versions SET compile_json=? WHERE task_id=?", (json.dumps({"submitted_bundle_hash": "bad"}), running))
    assert client.post(f"/api/tasks/{running}/agent-connections", headers=ADMIN, json={"name": "test"}).status_code == 409


def test_stale_agent_request_cannot_be_approved(client, running):
    _, headers = pair(client, running)
    current = get_context(client, running, headers)
    payload = {"kind": "expand", "justification": "test isolated output", "request_key": "stale-approval", "expected_snapshot_hash": current["snapshot_hash"]}
    request = client.post(f"/api/agent/tasks/{running}/scope-requests", headers=headers, json=payload).json()
    with db.connect() as con:
        con.execute("UPDATE tasks SET active_pid=12345 WHERE id=?", (running,))
    result = client.post(f"/api/tasks/{running}/scope-requests/{request['id']}/review", headers=ADMIN, json={"decision": "approve"})
    assert result.status_code == 409
    assert client.post(f"/api/tasks/{running}/scope-requests/{request['id']}/review", headers=ADMIN, json={"decision": "reject"}).status_code == 200


def test_revoking_dsh_connection_revokes_legacy_plugin_credential(client, running):
    token, _ = issue_task_token(running)
    headers = {"Authorization": "Bearer " + token}
    context = get_context(client, running, headers)
    assert client.post(f"/api/tasks/{running}/agent-connections/{context['connection_id']}/revoke", headers=ADMIN).status_code == 200
    assert client.get(f"/api/plugin/tasks/{running}/scope", headers=headers).status_code == 401


def test_adapter_requires_tls_for_remote_origin():
    path = Path(__file__).resolve().parents[2] / "integrations/http-agent/agentscope_client.py"
    spec = importlib.util.spec_from_file_location("bridge_client_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError):
        module.AgentScopeClient("http://remote.example", "task", "token")
    with pytest.raises(ValueError):
        module.AgentScopeClient("https://user:pass@example.com", "task", "token")
    module.AgentScopeClient("https://example.com", "task", "token")


def test_adapter_does_not_forward_credentials_on_redirect():
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread
    path = Path(__file__).resolve().parents[2] / "integrations/http-agent/agentscope_client.py"
    spec = importlib.util.spec_from_file_location("bridge_redirect_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            self.send_response(302)
            self.send_header("Location", "/redirected")
            self.end_headers()
        def log_message(self, *args):
            pass
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True);thread.start()
    try:
        client = module.AgentScopeClient(f"http://127.0.0.1:{server.server_port}", "task", "synthetic-test-token")
        with pytest.raises(module.AgentScopeError) as error:
            client.context()
        assert error.value.status == 302
        assert seen == ["/api/agent/tasks/task/context"]
    finally:
        server.shutdown();server.server_close();thread.join()

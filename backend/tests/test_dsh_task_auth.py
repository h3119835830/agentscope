from agentscope_app.main import issue_task_token
from agentscope_app import db


def test_task_token_is_limited_to_own_scope_request_and_cannot_approve(client, seed_task):
    seed_task("task-one")
    seed_task("task-two")
    token, _ = issue_task_token("task-one")
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/tasks").status_code == 401
    assert client.get("/api/auth/check", headers={"Authorization": "Bearer test-admin-token-not-for-production"}).status_code == 200

    created = client.post(
        "/api/plugin/tasks/task-one/scope-requests",
        headers=headers,
        json={"kind": "expand", "justification": "Need a generated report"},
    )
    assert created.status_code == 200
    assert created.json()["status"] == "pending_review"
    request_id = created.json()["id"]

    with db.connect() as con:
        row = con.execute("SELECT status FROM scope_requests WHERE id=?", (request_id,)).fetchone()
    assert row["status"] == "pending_review"

    cross_task = client.post(
        "/api/plugin/tasks/task-two/scope-requests",
        headers=headers,
        json={"kind": "expand", "justification": "Try to affect another task"},
    )
    assert cross_task.status_code == 401

    approval = client.post(
        f"/api/tasks/task-one/scope-requests/{request_id}/review",
        headers=headers,
        json={"decision": "approve"},
    )
    assert approval.status_code == 401

    admin = {"Authorization": "Bearer test-admin-token-not-for-production"}
    allowed = client.post(
        f"/api/tasks/task-one/scope-requests/{request_id}/review",
        headers=admin,
        json={"decision": "reject", "reviewed_by": "test"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "rejected"

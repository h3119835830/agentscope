import pytest
from agentscope_app import db, main


@pytest.mark.parametrize("exit_status,expected", [
    ({"state": "exited", "code": 0, "signal": None}, "completed"),
    ({"state": "exited", "code": 78, "signal": None}, "failed"),
    ({"state": "exited", "code": None, "signal": 9}, "failed"),
    ({"state": "exited", "code": None, "signal": None}, "failed"),
])
def test_runtime_uses_authoritative_exit_status_and_revokes_task_token(
    client, seed_task, monkeypatch, exit_status, expected
):
    task_id = "runtime-" + str(exit_status.get("code")) + "-" + str(exit_status.get("signal"))
    seed_task(task_id)
    token, _ = main.issue_task_token(task_id)
    calls = []

    def broker(body, **kwargs):
        calls.append(body["action"])
        if body["action"] == "status":
            return {"available": True, "agent_status": "exited", "child": {"status": exit_status}}
        return {"status": "stopped"}

    monkeypatch.setattr(main, "broker_call", broker)
    response = client.get("/api/tasks/" + task_id + "/runtime",
                          headers={"Authorization": "Bearer test-admin-token-not-for-production"})
    assert response.status_code == 200
    assert response.json()["task_status"] == expected
    with db.connect() as con:
        state = con.execute("SELECT status,ended_at FROM tasks WHERE id=?", (task_id,)).fetchone()
        live = con.execute("SELECT count(*) FROM task_credentials WHERE task_id=? AND revoked_at IS NULL", (task_id,)).fetchone()[0]
    assert state["status"] == expected and state["ended_at"] is not None
    assert live == 0
    assert calls == ["status", "stop"]
    assert client.get("/api/plugin/tasks/" + task_id + "/scope",
                      headers={"Authorization": "Bearer " + token}).status_code == 401


def test_runtime_imports_rule_reason_and_deduplicates_kernel_events(
    client, seed_task, monkeypatch, tmp_path
):
    import json
    task_id = "event-projection"
    seed_task(task_id)
    with db.connect() as con:
        con.execute("UPDATE tasks SET workspace=? WHERE id=?", (str(tmp_path), task_id))
    event_dir = tmp_path / ".actplane"
    event_dir.mkdir()
    event = {"event": "taint_violation", "op": "write", "target": "/fixture/blocked",
             "effect": "block", "blocked": True, "domain_id": 42,
             "rule": {"name": "fixture-restriction", "reason": "Approved fixture restriction"}}
    (event_dir / "events.jsonl").write_text(json.dumps(event) + "\n")
    monkeypatch.setattr(main, "broker_call", lambda *args, **kwargs:
                        {"available": True, "agent_status": "running"})
    for _ in range(2):
        response = client.get("/api/tasks/" + task_id + "/runtime",
                              headers={"Authorization": "Bearer test-admin-token-not-for-production"})
        assert response.status_code == 200
        events = response.json()["events"]
        assert len(events) == 1
        assert events[0]["decision"] == "block"
        assert events[0]["reason"] == "Approved fixture restriction"
    with db.connect() as con:
        assert con.execute("SELECT count(*) FROM runtime_events WHERE task_id=?", (task_id,)).fetchone()[0] == 1

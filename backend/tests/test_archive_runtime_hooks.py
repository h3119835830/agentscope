"""Runtime hook archives show public frozen metadata without consulting executors."""
from contextlib import contextmanager
import json
import uuid

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from agentscope_app import db
from agentscope_app.archive import runtime_hooks as hooks
from agentscope_app.archive.api import router
from agentscope_app.managed import controller, records


def ident():
    return uuid.uuid4().hex


@pytest.fixture
def task(seed_task, monkeypatch):
    db.init_db()
    task_id = ident()
    seed_task(task_id)
    with db.connect() as con:
        con.execute("UPDATE tasks SET status='ended',ended_at=? WHERE id=?", (db.now(), task_id))
        con.execute("INSERT INTO managed_tasks VALUES(?,?,?)", (task_id, json.dumps({
            "phase": "ended", "turn": 999, "revision": 999,
            "runtime_observations": {"memory": {"content": "CURRENT_PRIVATE_MEMORY", "seq": 999}},
            "session_id": "CURRENT_SESSION_MUST_NOT_BORROW",
        }), db.now()))
    def forbidden(*args, **kwargs):
        pytest.fail("archive runtime hooks consulted a live executor/state view")
    for module, name in ((controller, "broker"), (controller, "load"), (records, "runtime_record"), (records, "workbench"), (records, "binding")):
        monkeypatch.setattr(module, name, forbidden)
    return task_id


def request(task_id, actor="native_user", **extra):
    with db.connect() as con:
        return str(con.execute(
            "INSERT INTO managed_events(task_id,kind,event_key,payload_json,occurred_at) VALUES(?,?,?,?,?)",
            (task_id, "request", ident(), json.dumps({"actor": actor, "turn": 2, "text": "PRIVATE_RAW_PROMPT", **extra}), db.now()),
        ).lastrowid)


def context(request_id="request:old", actor="native_user", observations=None):
    return {
        "request_evidence_id": request_id,
        "sources": [{"evidence_id": request_id, "source": "request", "content": {"actor": actor, "turn": 2, "text": "PRIVATE_RAW_PROMPT"}}],
        "native_execution_context": observations or {},
        "private_reasoning": "PRIVATE_REASONING", "raw_prompt": "PRIVATE_RAW_PROMPT",
        "project_sources": [{"content": "PRIVATE_PROJECT_BYTES"}],
    }


def job(task_id, ctx=None, status="completed", proposal=None, timestamp=None):
    job_id = ident()
    raw = ctx if isinstance(ctx, str) else json.dumps({} if ctx is None else ctx)
    with db.connect() as con:
        con.execute(
            "INSERT INTO managed_jobs(id,task_id,request_key,revision,policy_hash,status,context_json,proposal_json,token_hash,error,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (job_id, task_id, ident(), 7, "frozen-policy-hash", status, raw,
             json.dumps(proposal) if proposal is not None else None,
             "SECRET_CREDENTIAL", "PRIVATE_FAILURE_STREAM", timestamp or db.now()),
        )
    return job_id


def test_definition_is_current_explanation_not_historical_configuration(task):
    value = hooks.runtime_hooks(task)
    assert value["history_only"] and value["historical"] and value["live"] is False
    assert value["records"] == [] and value["status"] == "unrecorded"
    mechanism = value["mechanism"]
    assert mechanism["source"] == "current_definition"
    assert mechanism["configuration_status"] == "not_historical_configuration"
    assert mechanism["historical_configuration"] is False
    assert mechanism["events"] == records.HOOKS["runtime"]["events"]
    assert mechanism["sequence"] == records.HOOKS["runtime"]["sequence"]
    assert all(isinstance(item, str) for item in mechanism["events"] + mechanism["sequence"])
    mechanism["events"].clear()
    assert hooks.runtime_hooks(task)["mechanism"]["events"]


def test_saved_request_and_dispatched_turn_not_current_state_or_policy_children(task):
    request_id = request(task, dispatched_turn=5)
    job_id = job(task, context(request_id), proposal={
        "identified_statements": [{"statement": "one"}, {"statement": "two"}, {"statement": "three"}],
        "private_reasoning": "PRIVATE_REASONING", "raw_prompt": "PRIVATE_RAW_PROMPT",
    })
    result = hooks.runtime_hooks(task)
    assert result["total"] == len(result["records"]) == 1
    row = result["records"][0]
    assert row["job_id"] == job_id and row["request_id"] == request_id
    assert row["status"] == "recorded"
    assert row["trigger"]["actor"] == "native_user"
    assert row["trigger"]["name"] == "真实用户消息"
    assert row["trigger"]["revision"] == 7
    assert row["trigger"]["accepted_turn"] == 2 and row["trigger"]["turn"] == 5
    assert row["trigger"]["observations_status"] == "unrecorded"
    assert row["evidence_refs"] == ["managed_jobs:" + job_id + ":record", "managed_events:" + request_id + ":record"]
    assert all(isinstance(value, str) for value in row["evidence_refs"])
    public = json.dumps(result)
    for secret in ("PRIVATE_RAW_PROMPT", "PRIVATE_REASONING", "PRIVATE_PROJECT_BYTES", "PRIVATE_FAILURE_STREAM", "SECRET_CREDENTIAL", "CURRENT_SESSION_MUST_NOT_BORROW", "CURRENT_PRIVATE_MEMORY"):
        assert secret not in public


@pytest.mark.parametrize("status", ["queued", "running", "completed", "failed", "cancelled", "interrupted", "rejected", "stale"])
def test_trigger_survives_generation_without_candidate(task, status):
    job_id = job(task, context(actor="kernel"), status)
    row = hooks.runtime_hooks(task)["records"][0]
    assert row["job_id"] == job_id and row["generation_status"] == status
    assert row["trigger"]["name"] == "ActPlane 拒绝反馈" and row["status"] == "recorded"


@pytest.mark.parametrize("raw", ["{}", "null", "[]", "invalid-json", '{"sources":"not-a-list","native_execution_context":[]}'])
def test_missing_old_context_never_defaults_to_native_user(task, raw):
    job(task, raw)
    row = hooks.runtime_hooks(task)["records"][0]
    assert row["status"] == "unrecorded"
    assert row["trigger"]["actor"] is None and row["trigger"]["name"] == "未记录触发来源"
    assert row["trigger"]["turn"] is None and row["trigger"]["observations"] == []
    assert {"actor", "request_id", "turn", "observations"} <= set(row["missing_fields"])


def test_observation_metadata_deduplicated_without_prompt_or_private_stream(task):
    observation = {"category": "memory", "type": "compaction/summary", "seq": 42, "content_hash": "a" * 64,
                   "content": "PRIVATE_RAW_PROMPT", "reasoning": "PRIVATE_REASONING", "serialized": {"content": "PRIVATE_NATIVE_STREAM"}}
    job(task, context(actor="native_context", observations={"memory": observation, "duplicate": dict(observation)}))
    row = hooks.runtime_hooks(task)["records"][0]
    values = row["trigger"]["observations"]
    assert len(values) == 1
    assert {key: values[0][key] for key in ("category", "type", "seq", "content_hash")} == {
        "category": "memory", "type": "compaction/summary", "seq": 42, "content_hash": "a" * 64,
    }
    assert values[0]["status"] == row["trigger"]["observations_status"] == "recorded"
    assert row["trigger"]["observations_meaning"] == "frozen_context_observations; not_each_a_new_trigger"
    assert "PRIVATE_" not in json.dumps(row)


def test_untrusted_metadata_shapes_do_not_export_raw_values_or_raise(task):
    ctx = context(actor={"text": "PRIVATE_RAW_PROMPT"}, observations={
        "bad": {"category": "PRIVATE_RAW_PROMPT", "type": "PRIVATE_RAW_PROMPT", "seq": True, "content_hash": "PRIVATE_RAW_PROMPT"},
        "scalar": "PRIVATE_RAW_PROMPT",
    })
    job(task, ctx)
    row = hooks.runtime_hooks(task)["records"][0]
    assert row["status"] == "unrecorded" and row["trigger"]["actor"] is None
    assert row["trigger"]["observations"][0]["status"] == "unrecorded"
    assert "PRIVATE_" not in json.dumps(row)


def test_ambiguous_frozen_request_source_is_explicit(task):
    ctx = context()
    ctx["sources"].append({"evidence_id": "request:old", "source": "request", "content": {"actor": "kernel", "turn": 3}})
    job(task, ctx)
    row = hooks.runtime_hooks(task)["records"][0]
    assert row["status"] == "unrecorded" and row["trigger"]["actor"] is None
    assert "ambiguous_request_source" in row["missing_fields"]


def test_exact_saved_request_fallback_is_task_scoped(task, seed_task):
    same_id = request(task, "verified_feedback", accepted_turn=1, dispatched_turn=4)
    same = job(task, {"request_evidence_id": same_id})
    other = ident()
    seed_task(other)
    foreign_id = request(other, "kernel", dispatched_turn=987)
    foreign = job(task, {"request_evidence_id": foreign_id})
    job(other, context(actor="control_review"))
    rows = {row["job_id"]: row for row in hooks.runtime_hooks(task)["records"]}
    assert len(rows) == 2
    assert rows[same]["status"] == "recorded" and rows[same]["trigger"]["origin"] == "persisted_request_event"
    assert rows[same]["trigger"]["accepted_turn"] == 1 and rows[same]["trigger"]["turn"] == 4
    assert rows[foreign]["status"] == "unrecorded" and rows[foreign]["trigger"]["actor"] is None
    assert len(rows[foreign]["evidence_refs"]) == 1
    assert rows[foreign]["trigger"]["turn"] is None


def test_distinct_jobs_for_same_request_keep_history_without_statement_duplicates(task):
    for _ in range(2):
        job(task, context("request:shared"), proposal={"identified_statements": [{"statement": "one"}, {"statement": "two"}]})
    result = hooks.runtime_hooks(task)
    assert result["total"] == len(result["records"]) == 2
    assert len({row["job_id"] for row in result["records"]}) == 2
    assert {row["request_id"] for row in result["records"]} == {"request:shared"}


def test_cursor_is_task_and_hook_scoped_and_deterministic(task, seed_task):
    expected = {job(task, context(), timestamp="2026-10-08T00:00:00Z") for _ in range(5)}
    first = hooks.runtime_hooks(task, limit=2)
    found = [row["job_id"] for row in first["records"]]
    cursor = first["next_cursor"]
    while cursor:
        result = hooks.runtime_hooks(task, cursor, 2)
        found.extend(row["job_id"] for row in result["records"])
        cursor = result["next_cursor"]
    assert set(found) == expected and len(found) == len(expected)
    other = ident()
    seed_task(other)
    with pytest.raises(HTTPException) as error:
        hooks.runtime_hooks(other, first["next_cursor"])
    assert error.value.status_code == 422
    wrong = hooks.archive.cursor_encode(task, "policies:runtime", {"time": "time", "id": "id"})
    with pytest.raises(HTTPException):
        hooks.runtime_hooks(task, wrong)


@pytest.mark.parametrize("limit", [0, 201, True, "10"])
def test_invalid_limit_rejected(task, limit):
    with pytest.raises(HTTPException) as error:
        hooks.runtime_hooks(task, limit=limit)
    assert error.value.status_code == 422


def test_missing_task_is_not_a_definition_only_success(task):
    with pytest.raises(HTTPException) as error:
        hooks.runtime_hooks(ident())
    assert error.value.status_code == 404


def test_get_route_is_read_only_at_database_boundary(task, monkeypatch):
    job(task, context())
    statements = []
    original = db.connect
    @contextmanager
    def traced():
        with original() as con:
            con.set_trace_callback(statements.append)
            yield con
    monkeypatch.setattr(db, "connect", traced)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.get("/api/tasks/" + task + "/archive/runtime-hooks?limit=1")
    assert response.status_code == 200
    assert response.json()["history_only"] and response.json()["live"] is False
    assert response.json()["records"][0]["trigger"]["actor"] == "native_user"
    assert "PRAGMA query_only=ON" in statements
    assert all(statement.lstrip().split()[0].upper() in {"SELECT", "PRAGMA", "BEGIN", "COMMIT"} for statement in statements)
    assert set(app.openapi()["paths"]["/api/tasks/{task_id}/archive/runtime-hooks"]) == {"get"}

import hashlib
import json
import sqlite3

from agentscope_app import db
from agentscope_app.main import issue_task_token
from agentscope_app.services import corpus


def test_strategy_create_edit_archive_restore_and_audit(client):
    admin = {"Authorization": "Bearer test-admin-token-not-for-production"}
    created = client.post("/api/strategies", headers=admin, json={
        "text": "Keep private credentials out of logs",
        "category": "per-event",
        "context_scope": "project",
    })
    assert created.status_code == 200
    row = created.json()
    assert row["source_kind"] == "manual"
    assert row["status"] == "pending_review"
    strategy_id = row["id"]
    page = client.get("/api/strategies/page?limit=1&offset=0", headers=admin)
    assert page.status_code == 200
    assert page.json()["total"] == 1
    assert page.json()["items"][0]["id"] == strategy_id
    with db.connect() as con:
        con.execute("UPDATE strategies SET source_repo='example/repo' WHERE id=?", (strategy_id,))
    filtered = client.get("/api/strategies/page?category=per-event&context_scope=project&source_repo=example", headers=admin)
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["id"] == strategy_id

    approved = client.post(f"/api/strategies/{strategy_id}/review", headers=admin, json={"decision": "approve", "reviewed_by": "test"})
    assert approved.status_code == 200
    edited = client.patch(f"/api/strategies/{strategy_id}", headers=admin, json={
        "text": "Keep private credentials out of logs and generated reports",
        "actor": "test",
        "reason": "Clarify the protected output",
    })
    assert edited.status_code == 200
    assert edited.json()["status"] == "pending_review"
    assert edited.json()["revision"] == 2
    history = client.get(f"/api/strategies/{strategy_id}/history", headers=admin)
    assert history.status_code == 200
    assert history.json()[0]["snapshot"]["status"] == "approved"

    archived = client.delete(f"/api/strategies/{strategy_id}?actor=test", headers=admin)
    assert archived.status_code == 200
    assert archived.json()["is_archived"] == 1
    assert all(row["id"] != strategy_id for row in client.get("/api/strategies", headers=admin).json())
    archived_rows = client.get("/api/strategies?archived=archived", headers=admin).json()
    assert any(row["id"] == strategy_id for row in archived_rows)
    restored = client.post(f"/api/strategies/{strategy_id}/restore", headers=admin, json={"actor": "test"})
    assert restored.status_code == 200
    assert restored.json()["is_archived"] == 0
    assert restored.json()["status"] == "pending_review"


def test_rq1_import_is_idempotent_and_does_not_overwrite_reviewed_edits(client, monkeypatch):
    source = {"repo": "example/repo", "files": []}
    monkeypatch.setattr(corpus, "load_local", lambda: [("example__repo", "Keep repository credentials private", source)])
    first = corpus.import_rq1()
    assert first["inserted_count"] == 1
    key = corpus.source_import_key("example__repo", "Keep repository credentials private")
    with db.connect() as con:
        con.execute("UPDATE strategies SET text=?,status='approved',reviewed_by='test' WHERE import_key=?", ("Human-edited policy", key))

    second = corpus.import_rq1()
    assert second["inserted_count"] == 0
    with db.connect() as con:
        row = con.execute("SELECT text,status,reviewed_by FROM strategies WHERE import_key=?", (key,)).fetchone()
    assert dict(row) == {"text": "Human-edited policy", "status": "approved", "reviewed_by": "test"}


def test_pi_token_can_only_submit_current_task_pending_candidates(client, seed_task):
    seed_task("pi-task")
    with db.connect() as con:
        con.execute("UPDATE tasks SET status='prepared' WHERE id='pi-task'")
        con.execute(
            "INSERT INTO evidence(id,task_id,kind,title,excerpt,content_sha256,collected_at) VALUES(?,?,?,?,?,?,?)",
            ("evidence-one", "pi-task", "agent_instruction", "AGENTS.md:1", "Do not expose private credentials", "b" * 64, db.now()),
        )
        con.execute(
            "INSERT INTO pi_runs(id,task_id,status,requested_by,created_at,started_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            ("pi-run-one", "pi-task", "running", "test", db.now(), db.now(), db.now()),
        )

    dsh_token, _ = issue_task_token("pi-task")
    pi_token, _ = issue_task_token("pi-task", scope="pi")
    url = "/api/plugin/tasks/pi-task/pi/context?run_id=pi-run-one"
    assert client.get(url, headers={"Authorization": f"Bearer {dsh_token}"}).status_code == 401

    pi_headers = {"Authorization": f"Bearer {pi_token}"}
    assert client.get(url, headers=pi_headers).status_code == 200
    submitted = client.post(
        "/api/plugin/tasks/pi-task/pi/proposals?run_id=pi-run-one",
        headers=pi_headers,
        json={
            "title": "Protect credentials in logs",
            "content": "Do not write credentials to task logs",
            "rationale": "The task evidence explicitly treats credentials as private.",
            "evidence_ids": ["evidence-one"],
            "strategy_ids": [],
        },
    )
    assert submitted.status_code == 200
    with db.connect() as con:
        proposal = con.execute("SELECT status FROM policy_proposals WHERE id=?", (submitted.json()["id"],)).fetchone()
    assert proposal["status"] == "pending_review"
    assert client.post(
        "/api/plugin/tasks/pi-task/pi/proposals?run_id=pi-run-one",
        headers=pi_headers,
        json={"title": "Wrong evidence", "content": "No evidence relation", "evidence_ids": ["other-task-evidence"]},
    ).status_code == 400


def test_legacy_database_migrates_with_backup_and_preserves_rows(tmp_path, monkeypatch):
    legacy_path = tmp_path / "legacy.sqlite3"
    con = sqlite3.connect(legacy_path)
    con.executescript("""
      CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
      CREATE TABLE strategies (
        id TEXT PRIMARY KEY,text TEXT NOT NULL,category TEXT NOT NULL,category_confidence REAL NOT NULL,
        context_scope TEXT NOT NULL,execution_layer TEXT NOT NULL,status TEXT NOT NULL,
        source_repo TEXT,source_commit TEXT,source_path TEXT,line_start INTEGER,line_end INTEGER,
        raw_url TEXT,source_content_sha256 TEXT,sentence_sha256 TEXT NOT NULL,
        source_verified INTEGER NOT NULL DEFAULT 0,source_kind TEXT NOT NULL DEFAULT 'rq1_corpus',
        metadata_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,reviewed_at TEXT,reviewed_by TEXT
      );
      CREATE TABLE tasks(id TEXT PRIMARY KEY);
      CREATE TABLE task_credentials(id TEXT PRIMARY KEY,task_id TEXT NOT NULL,token_sha256 TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL,revoked_at TEXT);
    """)
    for index in range(733):
        text = f"legacy strategy {index}"
        digest = hashlib.sha256(text.encode()).hexdigest()
        con.execute(
            "INSERT INTO strategies(id,text,category,category_confidence,context_scope,execution_layer,status,source_repo,sentence_sha256,source_kind,metadata_json,created_at,reviewed_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"legacy-{index}", text, "semantic", 0.4, "self-contained", "repository_instruction", "pending_review", "example/repo", digest, "rq1_corpus", json.dumps({"repo_slug": "example__repo"}), db.now(), None),
        )
    con.commit()
    con.close()

    monkeypatch.setattr(db, "DB_PATH", legacy_path)
    db.init_db()
    with db.connect() as migrated:
        assert migrated.execute("SELECT count(*) FROM strategies").fetchone()[0] == 733
        assert migrated.execute("SELECT count(*) FROM strategies WHERE status='pending_review'").fetchone()[0] == 733
        assert migrated.execute("SELECT count(*) FROM strategies WHERE import_key IS NOT NULL").fetchone()[0] == 733
        assert migrated.execute("SELECT count(*) FROM strategies WHERE is_archived=0 AND revision=1").fetchone()[0] == 733
    backups = list((tmp_path / "backups").glob("agentscope-pre-migration-*.sqlite3"))
    assert len(backups) == 1
    db.init_db()
    assert len(list((tmp_path / "backups").glob("agentscope-pre-migration-*.sqlite3"))) == 1

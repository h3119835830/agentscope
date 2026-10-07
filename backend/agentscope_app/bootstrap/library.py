"""FTS over the complete eligible reviewed library. No top-repository shortcut."""
import json
import os
import re
from .. import db
from .scene import digest
from ..history.pipeline import digest as history_digest

def seed_test_library():
    if os.getenv("AGENTSCOPE_BOOTSTRAP_TEST_LIBRARY") != "1": raise ValueError("test library requires isolated acceptance configuration")
    records = [
        {"id": "test-config-v1", "text": "Preserve existing user configuration files during cleanup. Block modification and deletion of the configuration assets in the current workspace.",
         "status": "approved", "parameterization": {"protected_paths": "current-task registered configuration assets"}, "operations": ["write", "unlink"]},
        {"id": "test-deployment-v1", "text": "Production deployment network endpoints require separate administrator authorization.", "status": "approved", "operations": []},
        {"id": "test-pending-v1", "text": "Preserve test files. This test sample is pending review and cannot be used.", "status": "pending_review", "operations": ["write", "unlink"]},
    ]
    with db.connect() as con:
        for record in records:
            record = {**record, "source_kind": "test_sample", "version": 1}
            hashed = digest(record)
            con.execute("INSERT OR IGNORE INTO bootstrap_history VALUES(?,?,?,?,?,?,?)",
                        (record["id"], record["text"], json.dumps(record), hashed, record["status"], hashed if record["status"] == "approved" else None, "test_sample"))

def refresh(con):
    # Production history is copied only from immutable, hash-approved statement versions.
    rows = con.execute("SELECT v.*,s.is_archived FROM strategy_statement_versions v JOIN strategies s ON s.id=v.strategy_id WHERE v.review_status='approved' AND s.is_archived=0").fetchall()
    for row in rows:
        record = json.loads(row["record_json"])
        if history_digest(record) != row["content_sha256"] or row["reviewed_hash"] != row["content_sha256"]: continue
        text = record.get("statement", {}).get("text_original", "")
        con.execute("INSERT OR REPLACE INTO bootstrap_history VALUES(?,?,?,?,?,?,?)", (row["id"], text, row["record_json"], row["content_sha256"], "approved", row["reviewed_hash"], "statement_version"))
    valid_ids = {r["id"] for r in rows if r["reviewed_hash"] == r["content_sha256"] and history_digest(json.loads(r["record_json"])) == r["content_sha256"]}
    for row in con.execute("SELECT id FROM bootstrap_history WHERE source_kind='statement_version'").fetchall():
        if row["id"] not in valid_ids: con.execute("DELETE FROM bootstrap_history WHERE id=?", (row["id"],))
    con.execute("DELETE FROM bootstrap_history_fts")
    con.execute("INSERT INTO bootstrap_history_fts(id,text) SELECT id,text FROM bootstrap_history WHERE status='approved' AND reviewed_hash=content_hash")

def search(query):
    tokens = re.findall(r"[\w\u4e00-\u9fff]+", query)[:32]
    with db.connect() as con:
        refresh(con)
        count = con.execute("SELECT count(*) FROM bootstrap_history_fts").fetchone()[0]
        if not count:
            return {"matches": [], "eligible_count": 0, "status": "empty_eligible_library", "retrieval_complete": True,
                    "next_action": "draft_new_candidate", "diagnostic": "No approved history exists. Changing the query cannot return a reusable policy; use current task and project evidence."}
        if not tokens: return {"matches": [], "eligible_count": count, "status": "invalid_query", "retrieval_complete": False}
        expression = " OR ".join('"' + t.replace('"', '') + '"' for t in tokens)
        rows = con.execute("SELECT h.*,bm25(bootstrap_history_fts) rank FROM bootstrap_history_fts JOIN bootstrap_history h ON h.id=bootstrap_history_fts.id WHERE bootstrap_history_fts MATCH ? ORDER BY rank LIMIT 20", (expression,)).fetchall()
        count = con.execute("SELECT count(*) FROM bootstrap_history_fts").fetchone()[0]
    return {"eligible_count": count, "status": "matches" if rows else "no_query_matches", "retrieval_complete": True, "retrieval": "whole-library FTS5; applicability must be judged against current evidence",
            "matches": [{"id": row["id"], "hash": row["content_hash"], "text": row["text"], "record": json.loads(row["record_json"]), "source_kind": row["source_kind"]} for row in rows]}

def approved_record(ident, expected_hash, con):
    refresh(con)
    row = con.execute("SELECT * FROM bootstrap_history WHERE id=?", (ident,)).fetchone()
    if not row or row["status"] != "approved" or row["content_hash"] != expected_hash or row["reviewed_hash"] != expected_hash:
        raise ValueError("history version is unapproved, stale or unavailable")
    data = json.loads(row["record_json"])
    if (history_digest(data) if row["source_kind"] == "statement_version" else digest(data)) != expected_hash: raise ValueError("history content hash mismatch")
    return data

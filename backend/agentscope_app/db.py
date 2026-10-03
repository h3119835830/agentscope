import json
import os
import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from .config import DB_PATH

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS strategies (
 id TEXT PRIMARY KEY, text TEXT NOT NULL, category TEXT NOT NULL, category_confidence REAL NOT NULL,
 context_scope TEXT NOT NULL, execution_layer TEXT NOT NULL, status TEXT NOT NULL,
 source_repo TEXT, source_commit TEXT, source_path TEXT, line_start INTEGER, line_end INTEGER,
 raw_url TEXT, source_content_sha256 TEXT, sentence_sha256 TEXT NOT NULL,
 source_verified INTEGER NOT NULL DEFAULT 0, source_kind TEXT NOT NULL DEFAULT 'rq1_corpus',
 metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, reviewed_at TEXT, reviewed_by TEXT,
 UNIQUE(source_repo,source_commit,source_path,sentence_sha256)
);
CREATE INDEX IF NOT EXISTS idx_strategies_status ON strategies(status);
CREATE INDEX IF NOT EXISTS idx_strategies_repo ON strategies(source_repo);
CREATE TABLE IF NOT EXISTS tasks (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, repo_url TEXT NOT NULL, repo TEXT NOT NULL,
 commit_sha TEXT NOT NULL, ref_requested TEXT NOT NULL, workspace TEXT NOT NULL,
 output_dir TEXT NOT NULL, prompt TEXT NOT NULL, agent TEXT NOT NULL, dsh_profile TEXT NOT NULL,
 status TEXT NOT NULL, active_version INTEGER NOT NULL DEFAULT 0, active_domain_id INTEGER,
 active_pid INTEGER, watch_pid INTEGER, settings_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, ended_at TEXT
);
CREATE TABLE IF NOT EXISTS task_credentials (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
 token_sha256 TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, revoked_at TEXT,
 scope TEXT NOT NULL DEFAULT 'dsh'
);
CREATE INDEX IF NOT EXISTS idx_task_credentials_task ON task_credentials(task_id, revoked_at);
CREATE TABLE IF NOT EXISTS evidence (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, title TEXT NOT NULL, uri TEXT, file_path TEXT, commit_sha TEXT,
 line_start INTEGER, line_end INTEGER, excerpt TEXT NOT NULL, content_sha256 TEXT NOT NULL,
 collected_at TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS policy_versions (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
 version INTEGER NOT NULL, layer TEXT NOT NULL, dsl_text TEXT NOT NULL, policy_yaml TEXT NOT NULL,
 source_strategy_ids TEXT NOT NULL DEFAULT '[]', evidence_ids TEXT NOT NULL DEFAULT '[]',
 compile_state TEXT NOT NULL, compile_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL,
 change_summary TEXT NOT NULL, approved_by TEXT, approved_at TEXT, created_at TEXT NOT NULL,
 UNIQUE(task_id,version)
);
CREATE TABLE IF NOT EXISTS runtime_events (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, operation TEXT, target TEXT, decision TEXT, reason TEXT NOT NULL,
 occurred_at TEXT NOT NULL, raw_json TEXT NOT NULL DEFAULT '{}', dedupe_key TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS scope_requests (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, requested_change TEXT NOT NULL, path TEXT, justification TEXT NOT NULL,
 status TEXT NOT NULL, requested_by TEXT NOT NULL, reviewed_by TEXT, created_at TEXT NOT NULL,
 reviewed_at TEXT, resulting_version INTEGER, result_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS governance_candidates (
 id TEXT PRIMARY KEY, task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
 kind TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL, source_url TEXT,
 status TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
 reviewed_at TEXT, reviewed_by TEXT, promoted_strategy_id TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
 id TEXT PRIMARY KEY, task_id TEXT, action TEXT NOT NULL, actor TEXT NOT NULL,
 details_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS strategy_revisions (
 id TEXT PRIMARY KEY, strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
 revision INTEGER NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
 snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(strategy_id,revision)
);
CREATE TABLE IF NOT EXISTS pi_runs (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
 status TEXT NOT NULL, requested_by TEXT NOT NULL, input_json TEXT NOT NULL DEFAULT '{}',
 result_json TEXT NOT NULL DEFAULT '{}', diagnostic TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, started_at TEXT, completed_at TEXT, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pi_runs_task ON pi_runs(task_id,created_at DESC);
CREATE TABLE IF NOT EXISTS policy_proposals (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES pi_runs(id) ON DELETE CASCADE,
 task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
 title TEXT NOT NULL, content TEXT NOT NULL, rationale TEXT NOT NULL DEFAULT '',
 evidence_ids_json TEXT NOT NULL DEFAULT '[]', strategy_ids_json TEXT NOT NULL DEFAULT '[]',
 content_sha256 TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending_review',
 created_at TEXT NOT NULL, reviewed_at TEXT, reviewed_by TEXT, review_notes TEXT NOT NULL DEFAULT '',
 UNIQUE(run_id,content_sha256)
);
CREATE INDEX IF NOT EXISTS idx_policy_proposals_task ON policy_proposals(task_id,status,created_at DESC);
"""

def now():
    return datetime.now(timezone.utc).isoformat()

@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def init_db():
    with connect() as con:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        existing = bool(tables)
        columns = {}
        for table in ("strategies", "task_credentials"):
            if table in tables:
                columns[table] = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
            else:
                columns[table] = set()
        needs_migration = existing and (
            "strategies" not in tables or "is_archived" not in columns["strategies"]
            or "revision" not in columns["strategies"] or "import_key" not in columns["strategies"]
            or "archived_at" not in columns["strategies"] or "archived_by" not in columns["strategies"]
            or "scope" not in columns["task_credentials"] or "pi_runs" not in tables
            or "strategy_revisions" not in tables or "policy_proposals" not in tables
        )
        if needs_migration:
            _backup_database()
        con.executescript(SCHEMA)
        strategy_columns = {r[1] for r in con.execute("PRAGMA table_info(strategies)")}
        for name, definition in (
            ("is_archived", "INTEGER NOT NULL DEFAULT 0"),
            ("revision", "INTEGER NOT NULL DEFAULT 1"),
            ("import_key", "TEXT"),
            ("archived_at", "TEXT"),
            ("archived_by", "TEXT"),
        ):
            if name not in strategy_columns:
                con.execute(f"ALTER TABLE strategies ADD COLUMN {name} {definition}")
        credential_columns = {r[1] for r in con.execute("PRAGMA table_info(task_credentials)")}
        if "scope" not in credential_columns:
            con.execute("ALTER TABLE task_credentials ADD COLUMN scope TEXT NOT NULL DEFAULT 'dsh'")
        _backfill_import_keys(con)
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_strategies_import_key ON strategies(import_key) WHERE import_key IS NOT NULL")
        con.execute("CREATE INDEX IF NOT EXISTS idx_strategies_archived ON strategies(is_archived,status)")
        con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version','2')")


def _backup_database():
    """Use SQLite's online backup API so WAL contents are included."""
    if not DB_PATH.exists() or DB_PATH.stat().st_size == 0:
        return
    backup_dir = DB_PATH.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = backup_dir / f"agentscope-pre-migration-{timestamp}.sqlite3"
    with sqlite3.connect(DB_PATH, timeout=30) as source, sqlite3.connect(destination) as target:
        source.backup(target)
    try:
        os.chmod(destination, 0o600)
    except OSError:
        pass


def _backfill_import_keys(con):
    rows = con.execute(
        "SELECT id,source_repo,sentence_sha256,metadata_json FROM strategies "
        "WHERE source_kind='rq1_corpus' AND import_key IS NULL ORDER BY created_at,id"
    ).fetchall()
    used = set()
    for row in rows:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except Exception:
            metadata = {}
        slug = (metadata.get("repo_slug") or (row["source_repo"] or "unknown").replace("/", "__")).strip().lower()
        key = hashlib.sha256(f"rq1\0{slug}\0{row['sentence_sha256']}".encode()).hexdigest()
        if key in used:
            # Preserve legacy duplicates while keeping the canonical key available
            # for the next idempotent import.
            key = hashlib.sha256(f"rq1\0{slug}\0{row['sentence_sha256']}\0{row['id']}".encode()).hexdigest()
        used.add(key)
        con.execute("UPDATE strategies SET import_key=? WHERE id=?", (key, row["id"]))

def row_dict(row):
    if row is None: return None
    obj = dict(row)
    for key, value in list(obj.items()):
        if key.endswith("_json") or key in ("source_strategy_ids", "evidence_ids"):
            try: obj[key[:-5] if key.endswith("_json") else key] = json.loads(value)
            except Exception: pass
            if key.endswith("_json"): obj.pop(key, None)
    return obj

def audit(con, task_id, action, actor, details=None):
    con.execute("INSERT INTO audit_log VALUES(?,?,?,?,?,?)", (
        __import__('uuid').uuid4().hex, task_id, action, actor,
        json.dumps(details or {}, ensure_ascii=False), now()))

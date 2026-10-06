import json
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
 revision INTEGER NOT NULL DEFAULT 1, is_archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by TEXT,
 UNIQUE(source_repo,source_commit,source_path,sentence_sha256)
);
CREATE INDEX IF NOT EXISTS idx_strategies_status ON strategies(status);
CREATE INDEX IF NOT EXISTS idx_strategies_repo ON strategies(source_repo);
CREATE TABLE IF NOT EXISTS strategy_revisions (
 id TEXT PRIMARY KEY, strategy_id TEXT NOT NULL REFERENCES strategies(id),
 revision INTEGER NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
 snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(strategy_id,revision)
);
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
 token_sha256 TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, revoked_at TEXT
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
        columns={r[1] for r in con.execute("PRAGMA table_info(strategies)")}
        additions={"revision":"INTEGER NOT NULL DEFAULT 1","is_archived":"INTEGER NOT NULL DEFAULT 0",
            "archived_at":"TEXT","archived_by":"TEXT"}
        if columns and set(additions)-columns:
            # Include committed WAL contents; keep the migration backup local and private.
            backup_dir=DB_PATH.parent/"backups"
            backup_dir.mkdir(parents=True,exist_ok=True)
            destination=backup_dir/("agentscope-pre-catalog-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")+".sqlite3")
            with sqlite3.connect(DB_PATH) as source,sqlite3.connect(destination) as target: source.backup(target)
            destination.chmod(0o600)
        con.executescript(SCHEMA)
        for name,definition in additions.items():
            if columns and name not in columns: con.execute(f"ALTER TABLE strategies ADD COLUMN {name} {definition}")
        con.execute("CREATE INDEX IF NOT EXISTS idx_strategies_archived ON strategies(is_archived,status)")
        from .history.schema import SCHEMA as HISTORY_SCHEMA
        con.executescript(HISTORY_SCHEMA)
        from .bootstrap.schema import SCHEMA as BOOTSTRAP_SCHEMA
        con.executescript(BOOTSTRAP_SCHEMA)
        from .agent_bridge.schema import SCHEMA as AGENT_BRIDGE_SCHEMA
        con.executescript(AGENT_BRIDGE_SCHEMA)
        from .scope.schema import SCHEMA as SCOPE_SCHEMA
        con.executescript(SCOPE_SCHEMA)
        from .managed.schema import SCHEMA as MANAGED_SCHEMA
        con.executescript(MANAGED_SCHEMA)
        from .local_browser import SCHEMA as LOCAL_BROWSER_SCHEMA
        con.executescript(LOCAL_BROWSER_SCHEMA)
        con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('history_schema_version','1')")

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

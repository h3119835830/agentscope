SCHEMA = """
CREATE TABLE IF NOT EXISTS scope_sessions (
 task_id TEXT PRIMARY KEY REFERENCES tasks(id), active_snapshot_id TEXT,
 phase TEXT NOT NULL DEFAULT 'cold', message_revision INTEGER NOT NULL DEFAULT 0,
 process_epoch TEXT, gate TEXT NOT NULL DEFAULT 'closed', apply_id TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scope_snapshots (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), revision INTEGER NOT NULL,
 parent_id TEXT, payload_json TEXT NOT NULL, content_hash TEXT NOT NULL,
 binding_json TEXT NOT NULL, verification_json TEXT NOT NULL, confirmed_at TEXT NOT NULL,
 UNIQUE(task_id,revision)
);
CREATE TABLE IF NOT EXISTS scope_deltas (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), kind TEXT NOT NULL,
 input_json TEXT NOT NULL, input_hash TEXT NOT NULL, base_snapshot_id TEXT,
 message_revision INTEGER NOT NULL, process_epoch TEXT, request_key TEXT NOT NULL,
 review_status TEXT NOT NULL DEFAULT 'pending', compile_status TEXT NOT NULL DEFAULT 'not_checked',
 apply_status TEXT NOT NULL DEFAULT 'not_applied', verify_status TEXT NOT NULL DEFAULT 'unverified',
 proposal_json TEXT, proposal_hash TEXT, receipt_json TEXT NOT NULL DEFAULT '{}',
 reviewed_by TEXT, created_at TEXT NOT NULL, UNIQUE(task_id,request_key)
);
CREATE TABLE IF NOT EXISTS scope_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL REFERENCES tasks(id),
 source TEXT NOT NULL, source_key TEXT NOT NULL, payload_json TEXT NOT NULL, occurred_at TEXT NOT NULL,
 UNIQUE(task_id,source,source_key)
);
CREATE TABLE IF NOT EXISTS scope_jobs (
 id TEXT PRIMARY KEY, delta_id TEXT NOT NULL UNIQUE REFERENCES scope_deltas(id),
 task_id TEXT NOT NULL REFERENCES tasks(id), status TEXT NOT NULL DEFAULT 'queued',
 token_hash TEXT, expires_at REAL, calls INTEGER NOT NULL DEFAULT 0,
 result_json TEXT NOT NULL DEFAULT '{}', error TEXT, created_at TEXT NOT NULL
);
"""

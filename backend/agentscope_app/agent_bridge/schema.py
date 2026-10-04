SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_connections (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), name TEXT NOT NULL,
 adapter TEXT NOT NULL, token_sha256 TEXT NOT NULL UNIQUE,
 legacy_credential_id TEXT REFERENCES task_credentials(id), run_key TEXT NOT NULL,
 created_at TEXT NOT NULL, expires_at TEXT NOT NULL, last_seen_at TEXT, revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_agent_connections_task ON agent_connections(task_id);
CREATE TABLE IF NOT EXISTS agent_messages (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
 task_id TEXT NOT NULL REFERENCES tasks(id), run_key TEXT NOT NULL,
 kind TEXT NOT NULL, content_json TEXT NOT NULL, source_ref TEXT NOT NULL,
 created_at TEXT NOT NULL, UNIQUE(task_id,run_key,source_ref)
);
CREATE TABLE IF NOT EXISTS agent_message_receipts (
 connection_id TEXT NOT NULL REFERENCES agent_connections(id),
 message_id TEXT NOT NULL REFERENCES agent_messages(id),
 status TEXT NOT NULL, received_at TEXT NOT NULL, handled_at TEXT,
 PRIMARY KEY(connection_id,message_id)
);
CREATE TABLE IF NOT EXISTS agent_feedback (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
 task_id TEXT NOT NULL REFERENCES tasks(id), connection_id TEXT NOT NULL REFERENCES agent_connections(id),
 run_key TEXT NOT NULL, snapshot_hash TEXT NOT NULL, kind TEXT NOT NULL,
 operation TEXT NOT NULL, target TEXT NOT NULL, summary TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_operations (
 connection_id TEXT NOT NULL REFERENCES agent_connections(id), operation_key TEXT NOT NULL,
 action TEXT NOT NULL, payload_hash TEXT NOT NULL, result_json TEXT NOT NULL,
 PRIMARY KEY(connection_id,operation_key)
);
CREATE TABLE IF NOT EXISTS agent_scope_bindings (
 request_id TEXT PRIMARY KEY REFERENCES scope_requests(id),
 run_key TEXT NOT NULL, snapshot_hash TEXT NOT NULL
);
"""

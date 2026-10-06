SCHEMA = """
CREATE TABLE IF NOT EXISTS managed_tasks(task_id TEXT PRIMARY KEY REFERENCES tasks(id), state_json TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS managed_jobs(id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), request_key TEXT NOT NULL, revision INTEGER NOT NULL, policy_hash TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', context_json TEXT NOT NULL, proposal_json TEXT, token_hash TEXT, expires_at REAL, calls INTEGER NOT NULL DEFAULT 0, error TEXT, created_at TEXT NOT NULL, UNIQUE(task_id,request_key));
CREATE TABLE IF NOT EXISTS managed_events(id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL REFERENCES tasks(id), kind TEXT NOT NULL, event_key TEXT NOT NULL, payload_json TEXT NOT NULL, occurred_at TEXT NOT NULL, UNIQUE(task_id,kind,event_key));
"""

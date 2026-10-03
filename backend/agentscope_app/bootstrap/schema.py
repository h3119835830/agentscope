SCHEMA = """
CREATE TABLE IF NOT EXISTS bootstrap_contexts (
 task_id TEXT PRIMARY KEY REFERENCES tasks(id), scenario_id TEXT, context_json TEXT NOT NULL,
 context_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bootstrap_sources (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), role TEXT NOT NULL,
 path TEXT NOT NULL, text TEXT NOT NULL, content_hash TEXT NOT NULL, source_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bootstrap_credentials (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL, job_id TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
 expires_at REAL NOT NULL, calls INTEGER NOT NULL DEFAULT 0, revoked_at TEXT);
CREATE TABLE IF NOT EXISTS bootstrap_proposals (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), job_id TEXT NOT NULL,
 context_hash TEXT NOT NULL, content_hash TEXT NOT NULL, proposal_json TEXT NOT NULL,
 validation_json TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bootstrap_versions (
 policy_version_id TEXT PRIMARY KEY REFERENCES policy_versions(id), proposal_id TEXT NOT NULL,
 context_hash TEXT NOT NULL, proposal_hash TEXT NOT NULL, condition TEXT NOT NULL,
 prompt_text TEXT NOT NULL, prompt_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bootstrap_tool_events (
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL, tool TEXT NOT NULL, input_json TEXT NOT NULL,
 output_json TEXT NOT NULL, occurred_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bootstrap_history (
 id TEXT PRIMARY KEY, text TEXT NOT NULL, record_json TEXT NOT NULL, content_hash TEXT NOT NULL,
 status TEXT NOT NULL, reviewed_hash TEXT, source_kind TEXT NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS bootstrap_history_fts USING fts5(id UNINDEXED, text);
CREATE TABLE IF NOT EXISTS bootstrap_results (
 task_id TEXT PRIMARY KEY REFERENCES tasks(id), result_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bootstrap_validations (
 job_id TEXT NOT NULL, proposal_hash TEXT NOT NULL, task_id TEXT NOT NULL,
 result_json TEXT NOT NULL, PRIMARY KEY(job_id,proposal_hash));
CREATE TABLE IF NOT EXISTS bootstrap_validation_budget (job_id TEXT PRIMARY KEY, calls INTEGER NOT NULL DEFAULT 0);
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS history_documents (
 id TEXT PRIMARY KEY, repository TEXT NOT NULL, requested_ref TEXT NOT NULL,
 commit_sha TEXT NOT NULL, relative_path TEXT NOT NULL, scope_path TEXT NOT NULL,
 snapshot_path TEXT NOT NULL, content_sha256 TEXT NOT NULL, byte_size INTEGER NOT NULL,
 source_url TEXT NOT NULL, collected_at TEXT NOT NULL,
 UNIQUE(repository,commit_sha,relative_path,content_sha256));
CREATE TABLE IF NOT EXISTS history_jobs (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL, input_json TEXT NOT NULL,
 result_json TEXT NOT NULL DEFAULT '{}', error TEXT, created_at TEXT NOT NULL,
 started_at TEXT, finished_at TEXT, retry_of TEXT);
CREATE TABLE IF NOT EXISTS strategy_statement_versions (
 id TEXT PRIMARY KEY, strategy_id TEXT NOT NULL REFERENCES strategies(id),
 version INTEGER NOT NULL, document_id TEXT REFERENCES history_documents(id),
 record_json TEXT NOT NULL, content_sha256 TEXT NOT NULL,
 review_status TEXT NOT NULL, reviewed_hash TEXT, reviewed_by TEXT, reviewed_at TEXT,
 created_at TEXT NOT NULL, UNIQUE(strategy_id,version));
CREATE TABLE IF NOT EXISTS history_artifacts (
 id TEXT PRIMARY KEY, statement_version_id TEXT NOT NULL REFERENCES strategy_statement_versions(id),
 version INTEGER NOT NULL, artifact_json TEXT NOT NULL, content_sha256 TEXT NOT NULL,
 review_status TEXT NOT NULL DEFAULT 'pending_review', reviewed_hash TEXT,
 compile_state TEXT NOT NULL, compile_json TEXT NOT NULL DEFAULT '{}',
 reviewed_by TEXT, reviewed_at TEXT, created_at TEXT NOT NULL,
 UNIQUE(statement_version_id,version));
CREATE TABLE IF NOT EXISTS history_compilations (
 id TEXT PRIMARY KEY, artifact_id TEXT REFERENCES history_artifacts(id), task_id TEXT,
 policy_version_id TEXT, input_hash TEXT NOT NULL, state TEXT NOT NULL,
 compiler_version TEXT NOT NULL, result_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS history_policy_artifacts (
 policy_version_id TEXT NOT NULL REFERENCES policy_versions(id),
 artifact_id TEXT NOT NULL REFERENCES history_artifacts(id), artifact_hash TEXT NOT NULL,
 PRIMARY KEY(policy_version_id,artifact_id));
CREATE TABLE IF NOT EXISTS history_deployments (
 id TEXT PRIMARY KEY, policy_version_id TEXT NOT NULL REFERENCES policy_versions(id),
 task_id TEXT NOT NULL REFERENCES tasks(id), bundle_hash TEXT NOT NULL,
 status TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0,
 domain_id INTEGER, runner_pid INTEGER, receipt_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL, ended_at TEXT);
CREATE INDEX IF NOT EXISTS history_jobs_status ON history_jobs(status,created_at);
CREATE INDEX IF NOT EXISTS statement_versions_strategy ON strategy_statement_versions(strategy_id,version);
CREATE TABLE IF NOT EXISTS history_generations (
 id TEXT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE, status TEXT NOT NULL,
 input_json TEXT NOT NULL, source_json TEXT NOT NULL DEFAULT '{}',
 stage TEXT NOT NULL DEFAULT 'source', cancel_requested INTEGER NOT NULL DEFAULT 0,
 job_id TEXT, retry_of TEXT, created_at TEXT NOT NULL, finished_at TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS history_generation_steps (
 run_id TEXT NOT NULL REFERENCES history_generations(id), step_key TEXT NOT NULL,
 stage TEXT NOT NULL, status TEXT NOT NULL, result_json TEXT NOT NULL DEFAULT '{}',
 error TEXT, updated_at TEXT NOT NULL, PRIMARY KEY(run_id,step_key));
CREATE TABLE IF NOT EXISTS history_generation_results (
 run_id TEXT NOT NULL REFERENCES history_generations(id), statement_version_id TEXT NOT NULL,
 artifact_id TEXT, status TEXT NOT NULL, error TEXT,
 PRIMARY KEY(run_id,statement_version_id));
"""

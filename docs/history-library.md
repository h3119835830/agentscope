# History policy library

AgentScope 0.2.0 keeps 历史策略库 as a first-level entry in the left sidebar. Its four second-level modules — 文档采集、策略语句抽取、策略转 DSL、策略记录与加载 — appear across the top of the main area below the breadcrumb. The sidebar can collapse to icons with accessible labels and remembers that preference; the duplicate body heading is removed. Public GitHub instruction files are input data and are never executed as instructions by the extraction client.

The reusable entry points are `history.pipeline.extract_strategy_statements(MarkdownDocument)` and `generate_policy_artifact(StrategyStatementVersion)`. Inject a provider for tests or configure the independent tool-free DeepSeek client with the protected service environment described in [install-linux.md](install-linux.md). Both functions are independent of HTTP, SQLite and the privileged Broker. English and Chinese text are retained separately from exact source evidence.

The API adds document snapshots, immutable statement/artifact versions and hash-bound review, a single FIFO worker, compiler records and task deployments. `POST /api/tasks/{id}/policy` takes `artifact_version_ids`; selected approved DSL actually enters the full baseline bundle. Approve the compiled task bundle before launch. `ActPlaneProvider.load_task_policy(task_id, approved_policy_version_id)` reads only that stored bundle and confirms the Broker's child domain and runner PID. Submitted bundle hashes are not kernel readback hashes.

Missing context, unsupported semantic/content policies, invalid fragments, partial compilation and deployment failure never advance automatically. Bind task/repository/commit and concrete directories in a new reviewed statement version. Modification scope excludes unlisted repository paths; it does not invent read/network authorization. The API rejects new history selections for running tasks; an existing Scope restart inherits selected fragments.

Deploy with one API process and one history worker. A restart marks running jobs interrupted, with explicit retries. Equal snapshots/outputs reuse versions, while repeated model calls retain audit metadata. A pre-launch failure with no attempted domain/PID may retry the same approved version after cleanup is confirmed. A failed binding attempt cannot use that retry path.

The observed ActPlane write-hook boundary may leave an empty new file entry when content writing is denied. This is shown in artifact details and is separate from compiler success. Complete filesystem metadata invariance, multi-worker operation and concurrent Broker runtimes are not claimed.

See [the real acceptance record](acceptance/history-library-20261002.md) and its sanitized structured evidence. Unit tests use isolated SQLite and fixture providers; real acceptance additionally uses DeepSeek and isolated DSH tasks.

The release design snapshots are in [history-library/](history-library/README.md): technical plan, RFC, ADR, REVIEW and BUG.

The records module adopts the mac branch (41e5c3d) directory view: full statement text, server-side filters/pagination, manual creation, version-aware editing/history, and reversible archive. The catalog joins exact statement, DSL and deployment versions. Document edits never overwrite immutable source/version data; legacy edits preserve source fields and clear review. Archived records cannot enter future conversion or deployment, while previous runtime receipts remain available.

Record management browser evidence and migration/regression checks: [2026-10-03 acceptance](acceptance/history-records-20261003.md).

The default records view uses the persisted RQ1 candidate corpus (721 distinct repository/statement pairs), with 20 rows per page. A hash-verified bundled snapshot initializes SQLite through a background job once; re-imports preserve edits, review and archive state. The sample collection was reversibly archived at the user’s request. See [RQ1 persistence acceptance](acceptance/rq1-persistence-20261003.md).

2026-10-03 按明确永久删除要求，现有非 RQ1 记录、关联产物/采集数据和备份已清除；全部来源归档数为 0，保留 721 条 RQ1。见 [永久清理验收](acceptance/rq1-only-purge-20261003.md)。

# Runtime, session and approval integration

Source integration: `aaebf5d` (independent inline approvals) plus GitHub main `ef85f4e` (runtime records and session directory removal). Worktree: `integration/runtime-approval-20261026`. The original Windows checkout contains another task's in-progress runtime application changes and is not overwritten.

Conflict decisions: retain independent approval identities, inline approval/apply acknowledgement and full-row DSL; retain the new default-action projection with the existing diagnostic/record projection. Session and runtime records retain their scoped read APIs, shared table fields and historical/current status distinction. Earlier approval modal and five-column approval layout are superseded by the later user instruction.

CI's integration command referenced the retired `runtime-observation.test.js`; replace it with the surviving feedback-guard and persistent-memory tests. Frozen fixtures must be exported with `git -c core.autocrlf=false archive`, preserving manifest hashes. Do not rewrite fixtures or their expected hashes. Build the C matching helper from the candidate source instead of reusing a binary predating target exceptions.

Validation of this merge: 1653 backend tests, 437 frontend tests, 34 integration tests and Vite build passed. Backend tests ran from a Linux Git archive with the candidate matching helper and unchanged frozen-fixture hashes. The receipt-contention tests now assert the exact IDs they create, since independent runtime history left by other test modules must not be treated as this fixture's pending approvals. Live release and browser acceptance are pending. A running parallel task has acknowledged the user's local-only development constraint and will supply a tested local commit for integration; do not publish that task's uncommitted files.

Evidence folder: `C:\Users\happy\Desktop\技术文档\AgentScope-统一整合-20261026`. No remote push has been performed.

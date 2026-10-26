# Runtime policy UI reduction

## Final system integration, 2026-10-26

The final runtime table contains policy name, default action and trigger actor, plus an explicit Details action at the right. Details show the exact constraint, actual template reference and saved trigger text; exact DSL is folded by default. No duplicate target field, Hook table, verification badges or generation metrics remain in this view. Default action comes from compiled rules for the exact targets: missing evidence displays “未记录” and multiple effects display “多种动作”. Restriction intent alone never implies block.

The Agent page and runtime archive share RuntimePolicyRecords. GET /api/agent-instances/{id}/runtime-policies requires the current generation and saved instance/session/task binding, matching the managed session and execution domain. No workspace, display-name or latest-task fallback is allowed. GET /api/runtime-tasks/{id}/policies reads one exact task. Both projections filter restrictive execution policies before pagination; detail reads check the same scope. These reads do not call the Broker or start native tasks. Generation, compilation and automatic additive application retain their existing contracts.

Final validation: 299 related backend tests passed; 397 frontend tests passed; Vite build passed. The frontend count dropped from 410 because the retired RuntimeHooks implementation and its 13 tests were removed. Thirteen updated preview browser checks passed, including default action, detail/DSL, cross-task isolation and 375px layout. Full system-route browser checks passed on isolated 18005 and installed 18003, covering the runtime archive, assistant/runtime tab separation and GET-only requests.

The record-bearing acceptance uses previously completed real task c7ae28357e224c7d on isolated 18005. Its single “保护 memory-note.txt” policy has compiled block rules and was triggered by a user message. It retrieved reviewed templates but cited none. No new DSH execution, generated candidate or fabricated display row was introduced. The installed 18003 Agent has no matching saved managed binding and correctly displays an empty list; the isolated record was not copied into that database.

Installed release: /opt/agentscope-runtime-policy-ui-20261026. Only the API service was restarted for the bounded read projection. Broker PID 433 and all saved Agent PID/generation/gate/policy-hash values were checked unchanged. The installed index hash matches the source build: 9b23a3de2c26595512390eeaad822f3574fb875d88932464ff00aa79ebe1b5fe. No backup was created. Obsolete runtime components/styles and unreferenced installed static bundles were removed after acceptance; task, policy and audit evidence remain intact. Deployment and cleanup guards are in scripts/deploy_runtime_policy_ui.py. No remote push was performed.

Installed page: http://127.0.0.1:18003/?view=workbench&policyAgent=instance-1f4469579e8947f4&agentPolicyTab=runtime

Final screenshots, browser assertions and deployment receipt: C:\Users\happy\Desktop\技术文档\AgentScope-运行时正式界面-20261026. Central RFC/ADR/REVIEW/BUG are synchronized. The following notes describe the earlier preview stages, not current publication status.

## Earlier preview acceptance (historical)

2026-10-26. Implemented in the managed workbench runtime branch and available as an isolated preview. Existing product navigation and services on 18000/18003 are unchanged.

The first view contains policy name and trigger actor, with an explicit Details action at the right of each row. Details expand the exact constraint, actual template reference and authenticated trigger text; a duplicate target field is omitted and DSL is initially folded. Diagnostic badges, Hook tables, generation counters and ordinary task guidance were removed from this branch. Original audit and archived evidence remain available elsewhere.

Runtime policy submission already requires context and reviewed-template retrieval receipts. This change preserves that generation gate. Presentation separately records search versus actual citation: only candidate-cited versions from the same task/job retrieval receipt appear as template references; names are not borrowed from a mismatched newer version.

An optional generated_only query flag defaults to false for compatibility. The runtime page uses true to filter actual restrictive target policies before pagination; 45 mixed records verify that all 15 policies remain reachable across two pages. This is a read projection, not a change to authority, compilation or automatic Delta application.

Acceptance uses the previously completed real task c7ae28357e224c7d. It contains one actual generated policy, displayed as “保护 memory-note.txt”, triggered by a user message. The candidate retrieved reviewed templates but cited none, so its detail says so. No native DSH task was rerun and no screenshot rows were fabricated.

Validation: 13 real-browser checks passed (desktop/detail/folded DSL/cross-task/mobile/GET-only/server filter); frontend 410 passed and Vite build passed; backend managed/archive 153 passed. The original first-view source and original acceptance evidence were not rewritten.

Interactive preview: http://127.0.0.1:18006/?task=c7ae28357e224c7d. It reads the isolated local API on 18005; native tasks remain ended. Screenshots and browser assertion evidence: C:\Users\happy\Desktop\技术文档\AgentScope-运行时精简UI-20261026.

The follow-up right-side Details interaction and removal of the duplicate target field passed all 410 frontend tests, build, and 13 updated real-browser checks. Its screenshots are in C:\Users\happy\Desktop\技术文档\AgentScope-运行时详情UI-20261026, including the expanded exact DSL.

Central RFC/ADR/REVIEW/BUG are synchronized under C:\Users\happy\Desktop\归纳梳理\技术文档. No remote push or production publication was performed.

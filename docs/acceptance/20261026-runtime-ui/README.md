# Runtime policy UI reduction

2026-10-26. Implemented in the managed workbench runtime branch and available as an isolated preview. Existing product navigation and services on 18000/18003 are unchanged.

The first view contains policy name and trigger actor, with an explicit Details action at the right of each row. Details expand the exact constraint, actual template reference and authenticated trigger text; a duplicate target field is omitted and DSL is initially folded. Diagnostic badges, Hook tables, generation counters and ordinary task guidance were removed from this branch. Original audit and archived evidence remain available elsewhere.

Runtime policy submission already requires context and reviewed-template retrieval receipts. This change preserves that generation gate. Presentation separately records search versus actual citation: only candidate-cited versions from the same task/job retrieval receipt appear as template references; names are not borrowed from a mismatched newer version.

An optional generated_only query flag defaults to false for compatibility. The runtime page uses true to filter actual restrictive target policies before pagination; 45 mixed records verify that all 15 policies remain reachable across two pages. This is a read projection, not a change to authority, compilation or automatic Delta application.

Acceptance uses the previously completed real task c7ae28357e224c7d. It contains one actual generated policy, displayed as “保护 memory-note.txt”, triggered by a user message. The candidate retrieved reviewed templates but cited none, so its detail says so. No native DSH task was rerun and no screenshot rows were fabricated.

Validation: 13 real-browser checks passed (desktop/detail/folded DSL/cross-task/mobile/GET-only/server filter); frontend 410 passed and Vite build passed; backend managed/archive 153 passed. The original first-view source and original acceptance evidence were not rewritten.

Interactive preview: http://127.0.0.1:18006/?task=c7ae28357e224c7d. It reads the isolated local API on 18005; native tasks remain ended. Screenshots and browser assertion evidence: C:\Users\happy\Desktop\技术文档\AgentScope-运行时精简UI-20261026.

The follow-up right-side Details interaction and removal of the duplicate target field passed all 410 frontend tests, build, and 13 updated real-browser checks. Its screenshots are in C:\Users\happy\Desktop\技术文档\AgentScope-运行时详情UI-20261026, including the expanded exact DSL.

Central RFC/ADR/REVIEW/BUG are synchronized under C:\Users\happy\Desktop\归纳梳理\技术文档. No remote push or production publication was performed.

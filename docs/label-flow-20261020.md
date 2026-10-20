# AgentScope label sources and witnessed information flow

Implementation baseline: `a18229153913c38a736b167a11397a8a56e7dbec`.
Implemented and accepted in an isolated worktree; not deployed.

## Contracts

- Public AGENT is reserved execution identity. Public SECRET is a source category,
  not one global execution label shared by every configuration.
- Sources are scope-isolated, immutable versioned metadata. Configuration refs pin
  ID/version and snapshots. Registration/editing does not approve or apply rules.
- New versions of SECRET-EGRESS and SYS-secret-egress use SECRET. Old definitions,
  approvals and SENSITIVE/REMOTE/CODE DSL remain unchanged. Compiler document
  namespaces and actual label-count limits remain authoritative.
- `RuntimeLabelTransition/1` contains kernel identities and exact predecessor IDs.
  Boot/map/sequence identifies events; process birth and file dev/inode/generation
  prevent path/PID joins. Broker binds trusted generation/domain/bundle hash.
- Session flow requires trusted tool attribution; otherwise use the explicitly
  marked shared-domain view. No inferred edges, byte-flow claims or secret bodies.
- Separate 4 MiB audit ring, bounded LRU witnesses and explicit loss/gap states.
  Existing enforcement remains authoritative. Network coverage is not expanded.
- System label management and session flow are the two new UI entries. Existing
  preview/approval screens receive compact frozen source summaries.

## Acceptance

Backend 1446 passed / 12 skipped; frontend 359 passed and production build;
ActPlane workspace tests, C tests 42, DSL adapter tests 5 passed.
Privileged Rust ignored tests are not claimed as executed.
Real complete-template suite 164/164 and new label-template cases 6/6 passed.
Real chain, rename, replacement, fork/exec and isolated API/Broker/native DSH
tool/kernel/collector/query acceptance passed. Independent loopback receiver
observed only the expected public controls. The DSH caller was deterministic,
test-only, with no model requests.

Identity collision, missing events, conflicting duplicate, reordered/reconnected
delivery and generation checks use deterministic receipt tests; no claim of
forcing actual OS PID reuse. Browser screenshots document real registry version
isolation, preview/approval, shared flow, evidence drawer and request failure.

Bounded 3x2000-file sample: all SECRET file witnesses received, reported loss 0;
median workload 0.11361s vs baseline 0.11230s (~1.2% difference). This is not a
production capacity or long-running loss guarantee; ~4.33 MB audit per sample.

Runtime SHA256:
`fc5570b6fbf029a822264f0c132c42f2d8bc47f0c1b5842b9b746c845685b5c3`.

Reproduction scripts: `accept_label_flow.py`, `accept_label_e2e.py`,
`benchmark_label_flow.py`; separate named BPF pin cleanup after identity-checked
service teardown is provided in `cleanup_label_acceptance.py`.

Authoritative Chinese RFC, ADR, REVIEW and BUG records and sanitized evidence:
`C:\Users\happy\Desktop\归纳梳理\技术文档`.
No deployed service restart or remote push is authorized by this acceptance.

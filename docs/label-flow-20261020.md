# AgentScope label sources and native ActPlane information-flow evidence

Implementation baseline: `a18229153913c38a736b167a11397a8a56e7dbec`.
Implemented and accepted in an isolated worktree; not deployed or pushed.

## Native boundary

AgentScope does not maintain an ActPlane information-flow fork. The ActPlane DSL
compiler, BPF propagation, runtime, event ABI, capability checker and prebuilt
objects remain byte-for-byte at the baseline above. AgentScope consumes native
`taint_violation`, matched label/rule metadata and `provenance_model` only.

ActPlane's authoritative contract is `first_available_matched_label`,
`single_hop_origin`, and `full_causal_chain=false`. A product record therefore
means “first origin reported by ActPlane -> current policy match”; it is not a
complete causal chain. There is no custom ring, transition ABI, predecessor graph
or associated performance claim.

## Product contracts

- Label sources are scope-isolated immutable versions. Configuration references
  pin ID/version and snapshots; registration does not approve or apply policy.
- A configuration may reference multiple sources. Those references are displayed
  as configuration context, never as the exact origin of an event.
- Exact origin is accepted only from native `provenance.origin_target`. A match
  without provenance remains visible as “source not reported by ActPlane”.
- Generation, bundle hash, domain and compiled clause must all match before a
  native event is bound to the current applied configuration.
- A session receives an event only with one trusted tool tag for the same domain
  and generation. Missing, conflicting or cross-domain tags remain in the Agent
  shared execution-domain view.
- Historical `label_transition` rows are retained but never read by the new
  projection. There is no destructive migration.
- Collection states are only `available`, `empty`, and `collection_failed`.

Both GET routes accept `view=session|shared_domain`, optional `generation`,
optional `label`, an event-row `cursor`, and `limit` 1..100 (default 24). They
return record pagination, not chain anchors.

The UI is a compact evidence table plus details drawer. It permanently states
that native evidence reports only the current match and first available origin,
not a complete hop-by-hop chain. Empty, failed collection, historical generation,
unreported origin and shared-domain attribution are distinct states.

## Acceptance

- `git diff --exit-code a182291 -- actplane`: passed with no differences.
- AgentScope backend: 1507 passed; final route regression: 27 passed.
- Frontend: 378 passed; production build passed (148 modules).
- ActPlane C/workspace suites passed; ignored privileged tests are not claimed.
- An isolated native scenario read synthetic secret data, blocked a real loopback
  connect, produced native `taint_violation`, and showed one matching API/UI
  evidence record. The receiver did not observe the restricted connection.
- Browser acceptance verified the shared-domain table, drawer content, monotonic
  timestamp wording and focus restoration.

The final evidence is under
`C:\Users\happy\Desktop\归纳梳理\技术文档\REVIEW\evidence\agentscope-native-information-flow-20261020`.
No deployed service was restarted and no remote push was performed.

# Independent approval records

User requirement: remove the approval detail UI; each policy is its own approval record. Generated selections now create separate proposal IDs, hashes, states and receipts. Approval and rejection are inline; application requires inline acknowledgement. Different policies may be approved independently; overlapping versions and whole-scope changes remain mutually exclusive.

The unapproved 11-policy object `8c7c3fb5d0c0425dab0db657fd6c9f0a` was converted into 11 independent, initially unapproved objects. The original is retained as superseded, with explicit replacement links. Conversion never approves or applies policies. A failed conversion blocks the old object and incomplete children, and can resume with fixed child request keys.

Validation logs:

- Main approval group: 86 passed.
- Existing approval/DSL compatibility: 61 passed.
- Later reader-contention and reference group: 82 passed; overlaps the preceding groups.
- All frontend tests: 439 passed; production build succeeded.

`verify_live.py` checks the actual 11 distinct IDs/hashes, frozen configuration versions, consistent current decision states and the exact applied document set. `check_concurrent_reads.py` performs three waves of four concurrent read-only console/library/record requests against the states observed at its start. Both report concurrent operator state changes rather than restoring earlier data. Neither script submits approval or application decisions. Public evidence is saved in the technical-document evidence directory; private database backups remain on the server with mode 0600.

Record and library polling share successful metadata checks only inside one response, then reset the ContextVar. The reader waits for bounded capacity, and infrastructure unavailability does not become file staleness. Full body verification at write/application boundaries is never skipped. The initial reader failure was observed in the tool transcript; the diagnostic JSON path was subsequently overwritten by the old verifier when an operator approved a record, so that file now proves the approved state, not the original reader failure.

Applying a policy still reloads the shared Agent domain and can invalidate other candidates' old baselines. Those require fresh validation/approval; this change does not silently rebase authority. Initial acceptance observed 11 pending/unapproved records and the unchanged runtime. Subsequent external operator requests approved the records and applied only the report-producer policy. At 2026-10-26T12:54:41Z, read-only acceptance observed 1 applied and 10 stale; the applied document set contained only that policy. DSH PID was 1567601 and generation a0ec4b12ee914adcbf0bc47b393bea2c. These external decisions were preserved. The execution-status gate was closed; no new runtime interception claim is made. Original acceptance files remain unchanged, and later snapshots use separate filenames. A further three waves of four concurrent reads passed against these later states.

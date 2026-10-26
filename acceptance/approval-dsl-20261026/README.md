# Approval DSL and decision latency

Approval rows show their exact frozen DSL in a full-width expansion inside the same table. The bulk confirmation renders that DSL directly, without nested review sections or PID fields. A selected configuration never displays a retained sibling's document or a later draft. Disable records retain their frozen configuration DSL. Generation-program conditions explicitly describe the missing-program trigger and the program-name-only boundary.

The server checks the candidate and potentially overlapping approval owners. Other configurations own independent approval slots and no longer cause repeated source reads. The existing lifecycle lock, exact hashes, same-configuration/whole-scope conflict checks and separate application boundary remain. Metadata reuse ends with the approval request; no cross-request authorization cache is introduced.

The client submits up to three independent approvals concurrently, reports in-progress and completed rows with elapsed time, and uses the authenticated exact receipt to acknowledge a saved decision. Application, revalidation, cleanup and restore remain sequential. Application still requires its receipt and a fresh shared-scope baseline.

Acceptance:

- Backend group: 44 passed, including 11 independent approvals, both whole-scope conflict directions, frozen document identity, read contention, two-phase approval and recovery.
- Frontend final group: 448 passed; production build passed. An earlier build passed 447 before adding the full-width expansion regression.
- Historical decision code intentionally fails the new repeated-check budget: 66 candidate checks for 11 approvals, 4.105 seconds in the isolated fixture. The corrected code performs 11 checks, 1.092 seconds in that fixture. These numbers exclude public-network/browser latency; they are not a live pending-approval benchmark.
- The earlier Windows attempt could not run JSX tests because the existing node_modules contained Linux esbuild. Full acceptance ran in the isolated Linux release candidate with its own frontend dependency install. No business dependency or lockfile was changed.
- `verify_live.py` checks all 11 exact DSL bindings and the deployment identity using GET only. No live approval, rejection, revalidation or application is submitted by this acceptance.

`baseline_plugin.py` is an opt-in historical regression probe for the isolated test database, not a normal passing-test plugin. `deployment.json` records the API release; `static-deployment.json` records the subsequent frontend-only layout correction. Database backups stay private on the server with mode 0600. The original visual overlap screenshot is retained separately from final full-width DSL evidence in the technical-document evidence directory.

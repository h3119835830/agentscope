# Implementation ledger

Baseline: `db870f6`; implementation branch: `codex/value-reliability-20261012`.

The live API and Broker use separate prepared releases. Acceptance must compare each runtime against its own baseline and preserve existing policy authority.

Initial pending list (historical, before implementation): runtime independence, bounded reads, isolated fault and kernel experiments, research catalog, overview, announcement, deployment, 24-hour observation.

Final status is tracked in ../../REVIEW-20261012-execution-independence-and-value.md. Implementation, isolated fault experiments, 72 comparisons, six native tasks, two-instance revocation, research, formal overview and publication-ready announcement delivered. Stability observation remains pending until the full 24-hour window and sufficient samples; numeric IAB timeout remains open. No remote push or external announcement publication.

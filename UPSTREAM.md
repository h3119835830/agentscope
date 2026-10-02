# Upstream provenance

## ActPlane

- Upstream: <https://github.com/eunomia-bpf/ActPlane>
- Snapshot base commit: `4c36aa54da2daf2b64de8782a38f77d5b76ec75a`
- Local working-tree changes included in this snapshot: `README.md`, `actplane.yaml`, `docs/agent-integrations.md`, `docs/support-matrix.md`, `bpf/src/lib.rs`, the untracked `integrations/dsh-feedback/` bundle, and AgentScope-specific BPF hook-budget and runtime-feedback adjustments made for this integration.
- The original ActPlane checkout is left untouched. Its `.git` directory, `docs/papers` submodule, and empirical-study TSV data are not included here.
- `libbpf` and `bpftool` are recorded as top-level Git submodules at the exact commits referenced by the ActPlane snapshot.

## AgentScope

AgentScope is the control-plane implementation in this repository. Its historical corpus and runtime database are private local data and are not part of this source snapshot.

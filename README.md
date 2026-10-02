# AgentScope

AgentScope is a Linux-hosted control plane for Agent access policies. It selects
reviewed historical guidance and repository evidence, creates task policy
versions, and delegates runtime enforcement to ActPlane. DSH is the first
supported agent integration.

## What is included

- `backend/` and `frontend/`: AgentScope API, policy review interface, runtime
  events, Scope requests, and persistent-candidate review.
- `actplane/`: a snapshot of the current ActPlane working tree, including its
  DSH feedback bundle. AgentScope keeps policy metadata in its database; the
  actual enforcement DSL is compiled and enforced by ActPlane.
- `integrations/dsh-agentscope/`: DSH tools for reading the approved task Scope
  and submitting a request for human review.
- `integrations/dsh-agentscope/` and
  `actplane/integrations/dsh-feedback/` are separate DSH bundles. The first
  cannot change enforcement directly; the second forwards ActPlane's violation
  feedback to DSH.

## Supported deployment

The first supported deployment is Ubuntu 24.04 ARM64 running in the Linux VM
with a kernel that provides BTF and BPF-LSM. DSH, the AgentScope services, and
ActPlane run in that guest. The desktop browser is used only to view the local
control plane through a forwarded port.

See [Linux VM installation](docs/install-linux.md) for a clean-clone setup and
the exact DSH profile installation commands.

## Policy and approval boundary

The AgentScope DSH bundle exposes `agentscope_get_current_scope` and
`agentscope_request_scope_change`. The request tool only creates a pending
record. A human must approve or reject it in the control plane. Approved
runtime restrictions can be appended through ActPlane; approved expansions
create a new policy version and restart the managed DSH process because the
current ActPlane process domain cannot be widened in place.

The control API requires `AGENTSCOPE_ADMIN_TOKEN` for operator actions. DSH
receives a separate random task credential that can read that task's approved
Scope and create its Scope requests only. Do not expose the control service to
the public internet.

## License

The AgentScope control-plane additions are MIT licensed. ActPlane retains its
upstream MIT license at `actplane/LICENSE`; bundled third-party dependencies
retain their own licenses and provenance.

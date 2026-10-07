# AgentScope

[Public task history archives on this branch](history-records/README.md) include
299 task dossiers and 27,145 persisted public events from the 2026-10-07 snapshot.
They contain historical evidence, not live sessions or runtime credentials.

AgentScope is a Linux-hosted policy control plane. External task agents such as
DSH execute the user's task. AgentScope manages reviewed policies, task Scope,
and execution evidence; Pi assesses and generates policy candidates internally.

## Implemented modules

- **History library:** GitHub source snapshots, LLM extraction, a separate
  completeness review, PolicyIR/v1, deterministic pseudocode/DSL rendering,
  compilation, and human approval of exact statement/artifact hashes. The UI
  separates current generation review, policy records/loading, and generation
  history/audit. Local-folder ingestion is deferred.
- **Task startup:** a controlled one-shot Pi agent retrieves approved history
  and task evidence, proposes startup policies, and hands approved versions to
  Provider/Broker and ActPlane. Three RQ5 scenario contracts are included.
- **Task-agent communication:** DSH tools and a standard-library HTTP client
  read approved Scope, exchange task messages and acknowledgements, report
  task/tool feedback, and submit Scope requests. Agent reports are kept separate
  from kernel events. This is groundwork for runtime policy increments.
- **Enforcement:** `actplane/` contains the ActPlane source snapshot. AgentScope
  stores policy metadata; ActPlane compiles and enforces supported rules.

The bounded **File Scope Demo** implements cold baseline verification, complete
immutable snapshots, runtime Pi candidates, manual review, same-domain
restrictions and checkpoint-based expansion/restart for a registered local DSH
fixture. The workbench separates permissions, changes and execution records.
General remote-Agent enforcement, dynamic network Scope and automatic history
promotion remain outside this implementation.

## Documentation and acceptance

- [GitHub submission scope and checks](docs/releases/20261004-history-and-task-agent.md)
- [Prepared pull request description](docs/releases/20261004-pr.md)
- [History generation contract](docs/history-generation-v1/RFC.md) and
  [acceptance](docs/history-generation-v1/REVIEW.md)
- [Pi startup workflow](docs/pi-bootstrap/README.md)
- [Task-agent communication contract](docs/agent-bridge-v1/RFC.md) and
  [acceptance and remaining work](docs/agent-bridge-v1/REVIEW.md)
- [Linux VM installation](docs/install-linux.md)
- [File Scope Demo contract and runbook](docs/scope-demo-v1/RFC.md), [decisions](docs/scope-demo-v1/ADR.md),
  [acceptance](docs/scope-demo-v1/REVIEW.md), and [reproduced defects](docs/scope-demo-v1/BUG.md)

On the prepared Windows/WSL Demo host, run [Open-ScopeDemo.cmd](scripts/Open-ScopeDemo.cmd)
to start the supervised local service and open the workbench directly. The local
Demo has no login page, launch ticket or browser session. Passwordless control
access is explicitly enabled only for the loopback Demo; default backend
authentication and DSH/Pi task credentials remain enforced.

The current local revision also includes conservative DSL normalization and
source lineage, task process-group cleanup, and service recovery. See the
[main release review](docs/REVIEW/REVIEW-20261007-AgentScope本机新版合入main.md)
for the tested snapshot and open acceptance items.

## Deployment and reproducibility

The reference installation guide targets Ubuntu 24.04 ARM64 in a Linux VM.
The 2026-10-04 development acceptance used an isolated WSL x86_64 instance on
port 18002 with installed DSH/ActPlane dependencies. The acceptance scripts
require that prepared environment and are not a clean-clone installer.
Kernel enforcement must be verified with real allow/deny probes on the target
host; a successful API response, build, or DSH launch alone is insufficient.

The repository includes the frozen RQ1 corpus and a read-only snapshot import
utility. Runtime databases, imported source caches, credentials, and local
execution logs are excluded. A fresh clone does not include the developer's
721-record database or its review state; see the history contract for import.

## Approval and credentials

Operator APIs require `AGENTSCOPE_ADMIN_TOKEN`. The explicit local development
mode permits passwordless operator access only on loopback. Agent and Pi tool
APIs still require their separate task/job-scoped credentials. Those credentials
cannot approve policies or load enforcement rules.

The DSH tools are listed in [the integration guide](integrations/dsh-agentscope/README.md).
The HTTP adapter is documented in [its guide](integrations/http-agent/README.md).
Remote HTTP connections provide communication, not proof of local kernel
protection. Supported expansions create a new approved policy and restart the
managed DSH process. The file Demo restores authenticated messages, public
progress and workspace hashes through a bounded checkpoint. Private model
reasoning is not collected, and complete native-session replay is not claimed.

## License

AgentScope control-plane additions are MIT licensed. ActPlane retains its
upstream MIT license at `actplane/LICENSE`; bundled dependencies retain their
own licenses and provenance.

# AgentScope DSH policy bundle

This DSH bundle exposes two tools to an AgentScope-managed session:

- `agentscope_get_current_scope` reads the approved policy version and current restrictions.
- `agentscope_request_scope_change` submits a request to the human review queue.

The bundle cannot approve requests, invoke the privileged ActPlane broker, or
apply a policy itself. The per-task token only grants access to these two
operations for the task that launched the DSH process.

Install it together with ActPlane's feedback bundle from the repository root:

```bash
./scripts/install-dsh-plugins.sh headless
```

AgentScope sets `AGENTSCOPE_URL`, `AGENTSCOPE_TASK_ID`, and
`AGENTSCOPE_TASK_TOKEN` when it launches a managed DSH session. A manually
started DSH session has no task credential and cannot use these tools.

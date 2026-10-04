# AgentScope DSH policy bundle

This DSH bundle exposes five tools to an AgentScope-managed session:

- `agentscope_get_current_scope` reads the approved policy version and current restrictions.
- `agentscope_request_scope_change` submits a request to the human review queue.
- `agentscope_read_messages` polls durable user messages and review outcomes.
- `agentscope_acknowledge_message` records received/handled receipts.
- `agentscope_report_feedback` journals bounded, non-sensitive Agent reports.

The bundle cannot approve requests, invoke the privileged ActPlane broker, or
apply a policy itself. The per-task token only grants access to these five
operations for the task that launched the DSH process.

Install it together with ActPlane's feedback bundle from the repository root:

```bash
./scripts/install-dsh-plugins.sh headless
```

AgentScope sets `AGENTSCOPE_URL`, `AGENTSCOPE_TASK_ID`, and
`AGENTSCOPE_TASK_TOKEN` when it launches a managed DSH session. A manually
started DSH session has no task credential and cannot use these tools.

The bridge is durable pull transport, not an asynchronous push into a DSH
conversation. DSH must call the message tool while its session is active. Message
ACKs are Agent reports, not enforcement receipts. Runtime Pi generation is not
connected in this transport release. Use the generic HTTP adapter for other
Agents; it does not attest or constrain the remote process.

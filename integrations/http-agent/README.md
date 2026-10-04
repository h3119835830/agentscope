# Execution Agent HTTP adapter v1

The control operator pairs an external adapter to an **already running, approved
task** with `POST /api/tasks/{task_id}/agent-connections`. The returned token is
shown once, stored only as a SHA-256 digest by AgentScope, expires, and is bound
to this execution epoch. It grants no admin, approval, policy-loading, or Pi
generator access. `agentscope_client.py` uses only Python's standard library.

```python
from agentscope_client import AgentScopeClient

client = AgentScopeClient.from_environment()
context = client.context()
client.report("progress", "Adapter connected; waiting for task instructions.")
batch = client.messages()  # persist cursor only after handling the entire batch
for message in batch["items"]:
    if message["receipt_status"] == "handled":
        continue
    client.acknowledge(message["id"], "received")
    # Deliver to your Agent's actual session/context, using its supported API.
    # handler(message) must be idempotent by message ID and persist completion.
    # Do not claim 'handled' until handler succeeds; otherwise leave it replayable.
```

Poll every 2 seconds while active, back off to at most 30 seconds on network
errors. The caller owns scheduling and the durable cursor. Repeat a failed
submission with the **same request key and body**; changed content with the same
key returns 409. After a 409 due to changed Scope, read context, reassess, and
submit a new request key. Expiry, revocation, stop, or process restart requires
a new connection; never auto-upgrade an old token. Scope review outcomes arrive
as durable `scope_review` messages. Receiving or handling a message is an Agent
report, not proof of kernel enforcement or model compliance.

Use an explicit transport origin and `AGENTSCOPE_TASK_ID` /
`AGENTSCOPE_TASK_TOKEN` in the adapter process environment. Never pass tokens on
the command line or include them in reports. Remote HTTP is rejected by the
client: use HTTPS with a trusted certificate at your reverse proxy. The initial
development API stays loopback-only; remote exposure is a separate deployment.

An HTTP adapter can be used alongside an Agent hosted elsewhere. It does **not**
launch that Agent, read arbitrary files, or put its process under local
ActPlane enforcement. The remote operator must explicitly connect the handler
to that Agent. Managed DSH uses its existing Broker-launched task token and the
DSH tools instead. This release provides the transport and journal; event-driven
runtime Pi generation / delta approval and verified apply remain subsequent work.

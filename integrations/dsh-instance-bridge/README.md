# Native DSH instance bridge

This independent Cordis bundle exposes only workspace observation, workspace adoption over an existing directory, and one-level directory listing. It does not register tools, read model messages, activate Agents, send prompts, load policy, execute commands, or alter sandbox policy.

Installation is an explicit operator step through scripts/install-dsh-instance-bridge.sh web. The installation script does not restart DSH. Configure the bundle's instanceId, socketPath and roots in the operator-owned DSH profile. A dedicated /run/agentscope-dsh directory must exist, be owned by the DSH service UID, and have mode 0700; socket permissions are 0600. The bundle refuses an insecure runtime directory.

The Broker reads the fixed /etc/agentscope/dsh-instances.json path, requiring a regular root-owned file with no group/other writes. Example (replace service and root with the actual operator choices):

```json
{"instances":[{"id":"native-dsh","name":"原生 DSH","service":"dsh.service","socket":"/run/agentscope-dsh/instance.sock","roots":["/srv/projects"]}]}
```

The server must run in the service MainPID. Broker verifies Unix SO_PEERCRED PID and UID, /proc start ticks, systemd MainPID before and after each exchange, protocol version, and a fresh random nonce. Socket addresses and roots never come from browser requests. Both bridge and Broker reject noncanonical paths, symlinks and paths outside operator roots. Native directory listing is filtered to operator roots before reaching the browser. The bridge's follower requires a fresh workspace baseline on reconnect; observations read workspaceRegistry.list() after baseline and never maintain an invented native registry.

AgentScope's independent observer polls every three seconds with a two-second client deadline. Each connection projection expires after eight seconds. A manual check issues a new roundtrip. A running service without a bridge is running_unattached. Configuration readiness alone never yields connected.

Existing historical AgentScope workspace rows remain historical sources; successful native observations synchronize distinct instance-owned rows and mark removed native registrations absent without deleting snapshot history.

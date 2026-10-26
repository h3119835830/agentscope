# Private AgentScope tunnel on Windows

The scheduled task starts at the current user's Windows logon. It forwards only
`127.0.0.1:18030` to the ECS AgentScope API at `127.0.0.1:18003`. Server services
remain under systemd. Windows may reconnect independently of those services.

## Prerequisites

- Windows OpenSSH Client and Windows PowerShell 5.1.
- A dedicated Ed25519 private key at
  `%USERPROFILE%\.ssh\id_ed25519_agentscope_tunnel`, readable only by the user,
  SYSTEM and Administrators. The unattended key has no passphrase.
- A separately verified server host key in
  `%USERPROFILE%\.ssh\known_hosts_agentscope_tunnel`.
- The corresponding public key installed for the server's `agentscope-tunnel`
  account, using `../ssh/install-agentscope-tunnel-user.sh` and its SSH config.
  That account permits public-key authentication and local forwarding only to
  `127.0.0.1:18003`; shell sessions and reverse forwarding are disabled.

Never copy the private key to the server or include it in a repository.

## Install and operate

Run `install-agentscope-tunnel-task.ps1` as the intended Windows user. It checks
the prerequisites, copies the supervisor to `%USERPROFILE%\.agentscope\tunnel`,
registers `AgentScope SSH Tunnel` with limited privileges and an interactive
logon trigger, then starts it. No Windows account password is saved.

The installation path deliberately stays outside packaged-app AppData paths.
Task Scheduler must see the same files as the installing process.

```powershell
Get-ScheduledTask -TaskName 'AgentScope SSH Tunnel'
Invoke-RestMethod http://127.0.0.1:18030/api/health
Stop-ScheduledTask -TaskName 'AgentScope SSH Tunnel'
Start-ScheduledTask -TaskName 'AgentScope SSH Tunnel'
```

The SSH connection uses pinned host-key verification and batch key
authentication. Keepalives detect a broken connection in approximately 45
seconds after transmission is possible. The supervisor retries with a 5 to 30
second delay. A Windows job object terminates SSH if the supervisor exits or the
task is stopped. Duplicate task starts are ignored. There is no execution time
limit and battery power does not stop the task.

Logs are in `%USERPROFILE%\.agentscope\tunnel\logs\tunnel.log`, with one
rotated file. A continuous supervisor can only run while the user is logged in
and the computer is awake. It resumes connectivity after login or network
recovery; it cannot make a powered-off computer's loopback port available.

Acceptance must check HTTP access, deliberate SSH-child termination and
reconnection, task stop/restart without orphaned SSH processes, duplicate
starts, loopback-only binding, and rejection of shell, off-target forwarding
and reverse forwarding.

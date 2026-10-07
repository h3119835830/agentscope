#!/usr/bin/env bash
# Explicit operator action only; never invoked by AgentScope startup.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE="${1:-web}"
command -v dsh >/dev/null || { echo 'Install DSH first.' >&2; exit 1; }
cd "$ROOT"
dsh plugin --profile "$PROFILE" add --config.auto-install-peers=true file:./integrations/dsh-instance-bridge
dsh plugin --profile "$PROFILE" list --depth 0
echo 'Configure instanceId/socketPath/roots in this profile; register the matching systemd service in /etc/agentscope/dsh-instances.json. Restart DSH explicitly after review.'

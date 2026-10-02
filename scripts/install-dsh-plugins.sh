#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE="${1:-headless}"

if ! command -v dsh >/dev/null 2>&1; then
  echo "dsh is not on PATH; install DeepSeek Harness before installing these bundles." >&2
  exit 1
fi

cd "$ROOT"
dsh plugin --profile "$PROFILE" add --config.auto-install-peers=true file:./integrations/dsh-agentscope
dsh plugin --profile "$PROFILE" add --config.auto-install-peers=true file:./actplane/integrations/dsh-feedback

echo "Installed bundles in DSH profile: $PROFILE"
dsh plugin --profile "$PROFILE" list --depth 0
CONFIG="$(dsh --profile "$PROFILE" --dump-config)"
grep -q 'agentscope-policy-tools' <<<"$CONFIG" || { echo "AgentScope bundle missing from composed DSH config." >&2; exit 1; }
grep -q 'actplane-feedback-native' <<<"$CONFIG" || { echo "ActPlane feedback bundle missing from composed DSH config." >&2; exit 1; }

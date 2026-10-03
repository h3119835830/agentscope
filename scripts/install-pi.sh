#!/usr/bin/env bash
set -euo pipefail

AGENTSCOPE_STATE_DIR="${AGENTSCOPE_STATE_DIR:-/var/lib/agentscope}"
AGENTSCOPE_PI_RUNTIME_DIR="${AGENTSCOPE_PI_RUNTIME_DIR:-${AGENTSCOPE_STATE_DIR}/pi-runtime}"
NODE22_BIN="${NODE22_BIN:-/opt/node22/bin}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
export PATH="${NODE22_BIN}:${PATH}"

node -e 'const [major, minor] = process.versions.node.split(".").map(Number); if (major < 22 || (major === 22 && minor < 19)) { console.error("Pi requires Node.js 22.19 or newer"); process.exit(1); }'
mkdir -p "${AGENTSCOPE_PI_RUNTIME_DIR}"
npm install --global --prefix "${AGENTSCOPE_PI_RUNTIME_DIR}" --ignore-scripts @earendil-works/pi-coding-agent@1.0.0
npm ci --prefix "${REPO_ROOT}/integrations/pi-policy-tools"
"${AGENTSCOPE_PI_RUNTIME_DIR}/bin/pi" --version

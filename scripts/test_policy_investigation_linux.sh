#!/usr/bin/env bash
set -euo pipefail
task_source=/mnt/c/Users/happy/Desktop/agentscope
task_checkout=$(mktemp -d /tmp/agentscope-policy-tools-tests.XXXXXX)
git -c safe.directory="$task_source" -c core.autocrlf=false clone -q --shared "$task_source" "$task_checkout"
cd "$task_source"
while IFS= read -r -d '' task_file; do
  cp --parents "$task_file" "$task_checkout"
  case "$task_file" in *.py|*.js|*.jsx|*.mjs|*.ts|*.c|*.sh) sed -i 's/\r$//' "$task_checkout/$task_file";; esac
done < <(git -c safe.directory="$task_source" ls-files -m -o --exclude-standard -z)
mkdir -p "$task_checkout/backend/dsl-adapter/target/release" "$task_checkout/actplane/target/release"
cp backend/dsl-adapter/target/release/agentscope-dsl-adapter "$task_checkout/backend/dsl-adapter/target/release/"
cp actplane/target/release/actplane "$task_checkout/actplane/target/release/"
cd "$task_checkout"
cc -O2 -Wall -Wextra -I actplane/bpf backend/policy_match_preview.c -o backend/dsl-adapter/target/release/agentscope-match-preview
export AGENTSCOPE_MATCH_PREVIEW_BIN="$task_checkout/backend/dsl-adapter/target/release/agentscope-match-preview"
export AGENTSCOPE_COMPILE_PREVIEW_BIN="$task_checkout/actplane/target/release/actplane"
find backend/agentscope_app/bootstrap/fixtures/rq5 -type f -exec sed -i 's/\r$//' {} +
printf '%s\n' "$task_checkout"
/opt/agentscope/.venv/bin/python -m pytest -q backend/tests/test_policy_investigation.py backend/tests/test_policy_context_agent.py backend/tests/test_policy_workspace_references.py backend/tests/test_reference_reader_channel.py

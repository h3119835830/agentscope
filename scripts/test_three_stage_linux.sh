#!/usr/bin/env bash
set -euo pipefail
task_source=/mnt/c/Users/happy/Desktop/agentscope
task_checkout=$(mktemp -d /tmp/agentscope-three-stage-tests.XXXXXX)
git -c safe.directory="$task_source" -c core.autocrlf=false clone -q --shared "$task_source" "$task_checkout"
cd "$task_source"
while IFS= read -r -d '' task_file; do
  cp --parents "$task_file" "$task_checkout"
  case "$task_file" in *.py|*.js|*.jsx|*.mjs|*.ts|*.conf|*.sh) sed -i 's/\r$//' "$task_checkout/$task_file";; esac
done < <(git -c safe.directory="$task_source" ls-files -m -o --exclude-standard -z)
mkdir -p "$task_checkout/backend/dsl-adapter/target/release" "$task_checkout/actplane/target/release"
cp backend/dsl-adapter/target/release/agentscope-dsl-adapter "$task_checkout/backend/dsl-adapter/target/release/"
cp actplane/target/release/actplane "$task_checkout/actplane/target/release/"
cd "$task_checkout"
# Windows checkout paths can arrive with CRLF even for frozen -text assets.
# Normalize only the disposable Linux copy; keep every authoritative hash fixed.
find backend/agentscope_app/bootstrap/fixtures/rq5 -type f -exec sed -i 's/\r$//' {} +
printf '%s\n' "$task_checkout"
/opt/agentscope/.venv/bin/python -m pytest -q backend/tests > "$task_checkout/backend-tests.log" 2>&1
tail -n 20 "$task_checkout/backend-tests.log"

#!/usr/bin/env bash
set -euo pipefail
task_source=/mnt/c/Users/happy/Desktop/agentscope
task_evidence="$task_source/acceptance/policy-response-ui-20261026"
mkdir -p "$task_evidence"
cd "$task_source/frontend"
node --test src/*.test.mjs > "$task_evidence/frontend-tests.txt" 2>&1
npm run build > "$task_evidence/frontend-build.txt" 2>&1
task_checkout=$(mktemp -d /tmp/agentscope-policy-response.XXXXXX)
git -c safe.directory="$task_source" -c core.autocrlf=false clone -q --shared "$task_source" "$task_checkout"
cd "$task_source"
for task_file in backend/agentscope_app/instances/generation_snapshots.py backend/tests/test_generation_snapshots.py; do
 cp --parents "$task_file" "$task_checkout"
 sed -i 's/\r$//' "$task_checkout/$task_file"
done
mkdir -p "$task_checkout/backend/dsl-adapter/target/release" "$task_checkout/actplane/target/release"
cp backend/dsl-adapter/target/release/agentscope-dsl-adapter "$task_checkout/backend/dsl-adapter/target/release/"
cp actplane/target/release/actplane "$task_checkout/actplane/target/release/"
cd "$task_checkout"
/opt/agentscope/.venv/bin/python -m pytest -q backend/tests/test_generation_snapshots.py backend/tests/test_template_configurations.py backend/tests/test_policy_continuation.py > "$task_evidence/backend-tests.txt" 2>&1
printf 'Frontend tests, build and backend snapshot regression passed. Isolated checkout: %s\n' "$task_checkout"

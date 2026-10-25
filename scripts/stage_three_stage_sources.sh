#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/happy/Desktop/agentscope
# Only Git-visible changes: never ignored credentials, local data or dependencies.
git -c safe.directory="$PWD" ls-files -m -o --exclude-standard -z |
  tar --null -T - -cf /mnt/c/Users/happy/AppData/Local/Temp/agentscope-three-stage-sources.tar

#!/usr/bin/env bash
# Stage only the explicitly authorized LSM-return patch, preserving every hook.
set -euo pipefail
task_source=/mnt/c/Users/happy/Desktop/agentscope
task_build=$(mktemp -d /tmp/agentscope-ecs-lsm-return.XXXXXX)
git -c safe.directory="$task_source" -C "$task_source" archive HEAD actplane | tar -x -C "$task_build"
cd "$task_build/actplane"
cp "$task_source/actplane/bpf/process.bpf.c" bpf/process.bpf.c
clang -g -O2 -target bpf -mcpu=v3 -D__TARGET_ARCH_x86 \
  -I/opt/agentscope/actplane/bpf/.output -Ibpf -Ivmlinux/x86 \
  -I/usr/include/x86_64-linux-gnu -c bpf/process.bpf.c -o bpf/prebuilt/process-return.tmp.o
/usr/sbin/bpftool gen object bpf/prebuilt/process.bpf.o bpf/prebuilt/process-return.tmp.o
export PATH=/home/happy/.cargo/bin:$PATH
cargo build --locked --release -p actplane
if [[ "${ACTPLANE_RUN_TESTS:-0}" == 1 ]]; then
  cargo test --locked --workspace
fi
sha256sum target/release/actplane bpf/prebuilt/process.bpf.o
printf 'Compatibility build: %s\n' "$task_build"

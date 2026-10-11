#!/usr/bin/env python3
"""Build isolated worktree objects, never overwrite another checkout's outputs."""
from pathlib import Path
import subprocess,shutil
r=Path(__file__).resolve().parents[1]/'actplane'
cmd=['make','-C','bpf','.output/process.bpf.o','.output/process-legacy.bpf.o',
     'LIBBPF_SRC=/opt/agentscope/actplane/libbpf/src',
     'LIBBPF_OBJ=/opt/agentscope/actplane/bpf/.output/libbpf.a',
     'BPFTOOL=/usr/sbin/bpftool',
     'INCLUDES=-I/opt/agentscope/actplane/bpf/.output -I. -I/opt/agentscope/actplane/libbpf/include/uapi -I../vmlinux/x86']
with open('/tmp/system-policy-bpf-build.log','w') as f:subprocess.run(cmd,cwd=r,stdout=f,stderr=f,check=True)
for name in ['process.bpf.o','process-legacy.bpf.o']:shutil.copy2(r/'bpf/.output'/name,r/'bpf/prebuilt'/name)
subprocess.run(['/home/happy/.cargo/bin/cargo','build','--release','-p','actplane'],cwd=r,check=True)

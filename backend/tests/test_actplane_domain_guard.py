"""Exercise the actual ActPlane BPF domain guard in userspace; never load BPF.

Only bpf_map_lookup_elem is supplied by a fixture. The decision functions are
extracted from the deployed engine source, not reimplemented in this test.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import pytest


def test_actual_bpf_guard_excludes_same_executor_siblings_and_unbound_processes(tmp_path):
    root=Path(os.environ.get('AGENTSCOPE_ACTPLANE_SOURCE','/opt/agentscope/actplane'))
    source=root/'bpf/capability.bpf.h'
    if not source.is_file():pytest.skip('ActPlane BPF source is not installed')
    cc=shutil.which('cc')
    if not cc:pytest.skip('A C compiler is required for the actual guard harness')
    text=source.read_text()
    start=text.index('static __always_inline int cap_domain_matches_pid(')
    end=text.index('static __always_inline void cap_fork(',start)
    guard=text[start:end]
    assert 'cap_labels_for_pid_domain' in guard
    c=r"""
#include <stdint.h>
#include <stdio.h>
#include <assert.h>
#undef __always_inline
#define __always_inline inline
#define CAP_DOMAIN_DEPTH 8
typedef uint32_t __u32;
typedef uint64_t __u64;
typedef int pid_t;
struct cap_state { __u32 parent; __u64 labels; __u64 restrict_mask; };
static int cap_task,cap_state;
static __u32 domains[8]={0,100,101,200,300,400,0,500};
static struct cap_state states[501];
static void *bpf_map_lookup_elem(void *map,const void *key){
    __u32 k=*(const __u32*)key;
    if(map==&cap_task)return k<8&&domains[k]?&domains[k]:0;
    if(map==&cap_state)return k<501&&states[k].labels?&states[k]:0;
    return 0;
}
"""+guard+r"""
int main(void){
    /* 100=current DSH, 101=its child; 200=another DSH; 300=another Agent;
       400=DSH's parent; 0=unbound Node; 500=an unrelated/invalid state. */
    states[100]=(struct cap_state){.parent=400,.labels=1,.restrict_mask=2};
    states[101]=(struct cap_state){.parent=100,.labels=4};
    states[200]=(struct cap_state){.parent=400,.labels=8};
    states[300]=(struct cap_state){.labels=16};
    states[400]=(struct cap_state){.labels=32};
    assert(cap_domain_matches_pid(1,100)==1);
    assert(cap_domain_matches_pid(2,100)==1);
    assert(cap_domain_matches_pid(3,100)==0);
    assert(cap_domain_matches_pid(4,100)==0);
    assert(cap_domain_matches_pid(5,100)==0);
    assert(cap_domain_matches_pid(6,100)==0);
    assert(cap_domain_matches_pid(7,100)==0);
    assert(cap_labels_for_pid_domain(1,100)==3);
    assert(cap_labels_for_pid_domain(2,100)==3);
    assert(cap_labels_for_pid_domain(3,100)==0);
    assert(cap_labels_for_pid_domain(4,100)==0);
    assert(cap_labels_for_pid_domain(6,100)==0);
    /* Shared parent rules are intentionally inherited, unlike sibling rules. */
    assert(cap_domain_matches_pid(1,400)==1);
    assert(cap_domain_matches_pid(3,400)==1);
    puts("14 actual BPF domain/label guard assertions passed; no BPF loaded");
}
"""
    path=tmp_path/'guard.c';path.write_text(c);binary=tmp_path/'guard'
    subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror',str(path),'-o',str(binary)],check=True,capture_output=True,text=True)
    run=subprocess.run([str(binary)],check=True,capture_output=True,text=True)
    assert '14 actual BPF domain/label guard assertions passed' in run.stdout
    print('ActPlane guard source sha256:',hashlib.sha256(guard.encode()).hexdigest())

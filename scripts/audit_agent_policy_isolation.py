"""Read-only live domain audit with two harmless, unbound Node controls.

No policy compile/proposal/confirm/load, Agent calls, service restart, map writes,
or business-file access. Requires root for admitted manifest and bpftool reads.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import selectors
import sqlite3
import subprocess

DB=Path('/var/lib/agentscope-scope-demo/demo.sqlite3')
RUNTIME=Path('/run/agentscope-scope-demo')
NODE=Path('/opt/agentscope/bin/node')


def snapshot():
    with sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True) as con:
        con.row_factory=sqlite3.Row
        agents=[]
        for raw in con.execute('SELECT id,generation,gate,policy_hash,runtime_json FROM agent_instances ORDER BY id'):
            row=dict(raw);runtime=json.loads(row.pop('runtime_json'))
            agents.append({**row,'runtime':{k:runtime.get(k) for k in ('pid','start_ticks','domain_id','generation','dsl_hash','verified')}})
        scopes=[dict(r) for r in con.execute('SELECT scope_id,revision,document_hash,phase FROM instance_dsl_scopes ORDER BY scope_id')]
        proposals=[]
        for raw in con.execute('SELECT id,scope_id,state,proposal_hash,targets_json FROM instance_dsl_proposals ORDER BY id'):
            proposal=dict(raw);proposal['target_ids']=[t['id'] for t in json.loads(proposal.pop('targets_json'))];proposals.append(proposal)
    services=subprocess.check_output(['systemctl','show','agentscope-scope-demo-api.service','agentscope-scope-demo-broker.service','-p','Id','-p','MainPID','-p','ActiveEnterTimestampMonotonic'],text=True)
    return dict(agents=agents,scopes=scopes,proposals=proposals,services=services)


def map_rows(pin,name):
    raw=subprocess.check_output(['/usr/sbin/bpftool','-j','map','dump','pinned',str(pin/'maps'/name)],text=True)
    rows=json.loads(raw)
    assert all('formatted' in r for r in rows),'BTF formatted map facts required'
    return {r['formatted']['key']:r['formatted']['value'] for r in rows}


def process(pid):
    proc=Path('/proc')/str(pid)
    before=(proc/'stat').read_text().rsplit(')',1)[1].split()[19]
    exe=os.readlink(proc/'exe');group=(proc/'cgroup').read_text().strip()
    after=(proc/'stat').read_text().rsplit(')',1)[1].split()[19]
    assert before==after
    return dict(pid=pid,start_ticks=before,executable=exe,cgroup=group)


def audit(ident):
    assert os.geteuid()==0
    assert re.fullmatch(r'instance-[a-f0-9]{16}',ident)
    before=snapshot();row=next(r for r in before['agents'] if r['id']==ident)
    assert row['gate']=='open' and row['runtime']['verified']
    pending=[p for p in before['proposals'] if p['scope_id']==ident and p['state']=='pending']
    assert all(p['target_ids']==[ident] for p in pending),'Pending Agent proposal has a foreign target'
    manifest=RUNTIME/'instances'/ident/'manifest.json'
    info=manifest.lstat();assert not manifest.is_symlink() and info.st_uid==0 and not info.st_mode&0o077
    record=json.loads(manifest.read_text());runid=hashlib.sha256(('agent-instance:'+ident).encode()).hexdigest()[:16]
    assert record['instance_id']==ident and record['task_id']==runid
    assert record['generation']==row['generation'] and record['domain_id']==row['runtime']['domain_id']
    assert record['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    pin=Path(record['pin_root']);assert pin==Path('/sys/fs/bpf/agentscope-managed-v3')/runid
    group=Path(record['process_cgroup']);assert group==Path('/sys/fs/cgroup/agentscope-scope-demo')/(runid+'-'+str(record['domain_id']))
    assert not group.is_symlink() and group.stat().st_uid==0 and group.stat().st_ino==record['cgroup_inode']
    tasks=map_rows(pin,'cap_task');states=map_rows(pin,'cap_state');policies=map_rows(pin,'cap_policy');rules=map_rows(pin,'ts_rules')
    current=process(row['runtime']['pid']);assert current['start_ticks']==row['runtime']['start_ticks']
    assert tasks[current['pid']]==record['domain_id']
    assert current['pid'] in {int(v) for v in (group/'cgroup.procs').read_text().split()}
    assert current['executable']==str(NODE)
    active_rules=[]
    for domain,mask in policies.items():
        for idx,value in rules.items():
            if (mask['lo'] if idx<64 else mask['hi']) & (1<<(idx%64)):
                assert domain!=0 and value['domain_id']==domain
                active_rules.append(dict(index=idx,domain_id=domain))
    assert active_rules and any(r['domain_id']==record['domain_id'] for r in active_rules)
    controls=[];children=[];user=pwd.getpwnam('happy')
    def unprivileged():
        os.setgroups([]);os.setgid(user.pw_gid);os.setuid(user.pw_uid)
    try:
        for _ in range(2):
            child=subprocess.Popen([str(NODE),'-e','process.stdout.write("ready"+String.fromCharCode(10));setInterval(()=>{},1000);'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},start_new_session=True,preexec_fn=unprivileged)
            children.append(child)
            with selectors.DefaultSelector() as select:
                select.register(child.stdout,selectors.EVENT_READ)
                assert select.select(5),'Standalone Node did not become ready'
            assert child.stdout.readline()==b'ready\n'
            fact=process(child.pid);tasks_now=map_rows(pin,'cap_task')
            assert fact['executable']==current['executable']
            assert child.pid not in tasks_now
            assert str(group.relative_to('/sys/fs/cgroup')) not in fact['cgroup']
            controls.append({**fact,'same_executor':True,'present_in_dsh_cap_task':False,'present_in_dsh_cgroup':False})
    finally:
        for child in children:
            if child.poll() is None:child.terminate()
            try:child.communicate(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.communicate(timeout=5)
    after=snapshot();assert after==before,'Runtime or policy state changed during audit'
    assert map_rows(pin,'cap_policy')==policies and map_rows(pin,'ts_rules')==rules,'Loaded policy maps changed'
    return dict(passed=True,instance_id=ident,generation=row['generation'],source='**/node',current={**current,'domain_id':record['domain_id'],'kernel_binding_verified':True},pin_root=str(pin),active_rules=active_rules,domain_parent=states[record['domain_id']]['parent'],pending_agent_proposals=pending,outside_node_controls=controls,unchanged_runtime_and_policy=True,policy_actions=[],agent_actions=[],service_actions=[],before=before,after=after)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--instance',required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=audit(args.instance);args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:result[k] for k in ('passed','instance_id','current','outside_node_controls','unchanged_runtime_and_policy','policy_actions')},ensure_ascii=False,indent=2))

"""Opt-in root acceptance of generated candidates in isolated test domains.

Uses a unique BPF pin root and synthetic files. Never contacts Broker, applies a
product approval, touches the shared engine, or claims a DSH/RQ5 task acceptance.
"""
import errno
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys

assert os.geteuid()==0, 'Explicit root test invocation required'
source=Path(sys.argv[1]).resolve(strict=True)
assert source.name=='model-results.json' and source.parent.parent==Path('/tmp') and source.parent.name.startswith('as-sem-')
data=json.loads(source.read_text())
state=source.parent
workspace=Path(data['workspace']).resolve(strict=True)
binary=Path(data['probe_binary']).resolve(strict=True)
assert workspace.parent==state and binary.parent==state
root=Path(__file__).resolve().parents[1]
cli=root/'actplane/target/release/actplane'
owner=pwd.getpwnam('happy')
pin=Path('/sys/fs/bpf')/('as-sem-accept-'+str(os.getpid()))
assert pin.parent==Path('/sys/fs/bpf') and not pin.exists()
env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':owner.pw_dir,'SUDO_UID':str(owner.pw_uid),'SUDO_GID':str(owner.pw_gid),
    'ACTPLANE_BPF_PIN_ROOT':str(pin),'ACTPLANE_RESERVE_OPEN_RULES':'1','ACTPLANE_HOOK_PROFILE':'full'}
expected={
    'readonly_zh':{'sales.csv':['file_mutate']}, 'readonly_en':{'input.json':['file_mutate']},
    'readonly_paraphrase':{'notes.txt':['file_mutate']}, 'deny_read':{'private.txt':['file_read']},
    'deny_access':{'archive.txt':['file_read','file_mutate']},
    'two_files':{'a.txt':['file_mutate'],'b.txt':['file_read']}}
probe=r'''
import errno,json,os,sys,subprocess
from pathlib import Path
workspace=Path(sys.argv[1]);blocked=json.loads(sys.argv[2]);results=[]
def check(name,fn,deny):
    try:
        fn();actual='allowed';number=None
    except OSError as exc:
        actual='denied' if exc.errno in (errno.EPERM,errno.EACCES) else 'unexpected-error';number=exc.errno
    ok=actual==('denied' if deny else 'allowed')
    results.append(dict(name=name,actual=actual,errno=number,passed=ok))
def open_close(path,flags):
    fd=os.open(path,flags);os.close(fd)
for name,rights in blocked.items():
    p=workspace/name
    check(name+':read',lambda:p.read_bytes(),'file_read' in rights)
    check(name+':append',lambda:open_close(p,os.O_WRONLY|os.O_APPEND),'file_mutate' in rights)
    if 'file_mutate' in rights:
        check(name+':overwrite',lambda:open_close(p,os.O_WRONLY|os.O_TRUNC),True)
        check(name+':read_write_open',lambda:open_close(p,os.O_RDWR),True)
        check(name+':truncate',lambda:os.truncate(p,0),True)
        check(name+':unlink',p.unlink,True)
        check(name+':rename',lambda:p.rename(workspace/(name+'.renamed')),True)
    child=subprocess.run([sys.executable,'-c','import pathlib,sys; pathlib.Path(sys.argv[1]).read_bytes()',str(p)],capture_output=True)
    denied=child.returncode!=0 and b'PermissionError' in child.stderr
    results.append(dict(name=name+':child_read',actual='allowed' if child.returncode==0 else 'denied' if denied else 'unexpected-error',
        passed=denied if 'file_read' in rights else child.returncode==0,exit_code=child.returncode,stderr=child.stderr.decode()))
    child=subprocess.run([sys.executable,'-c','import os,sys; fd=os.open(sys.argv[1],os.O_WRONLY|os.O_APPEND); os.write(fd,b"child"); os.close(fd)',str(p)],capture_output=True)
    denied=child.returncode!=0 and b'PermissionError' in child.stderr
    results.append(dict(name=name+':child_write',actual='allowed' if child.returncode==0 else 'denied' if denied else 'unexpected-error',
        passed=denied if 'file_mutate' in rights else child.returncode==0,exit_code=child.returncode,stderr=child.stderr.decode()))
control=workspace/'control.txt'
check('unrelated:write',lambda:control.write_text('control\n'),False)
check('unrelated:read',control.read_text,False)
print(json.dumps({'pid':os.getpid(),'uid':os.getuid(),'results':results}),flush=True)
sys.exit(0 if all(r['passed'] for r in results) else 2)
'''
summary={'scope':'Real ActPlane/BPF isolated domains and child processes; synthetic fixture identity; no product approval, no DSH/RQ5 claim.',
    'model_results_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'pin_root':str(pin),'cases':[]}
try:
    for case in data['cases']:
        name=case['name'];assert name in expected and case['passed']
        assert case['review_status']==case['artifact_review_status']=='pending_review' and not case['eligible']
        directory=state/'kernel'/name;directory.mkdir(parents=True,exist_ok=True)
        for path in expected[name]:
            target=workspace/path;target.write_text('fixture-data\n');os.chown(target,owner.pw_uid,owner.pw_gid)
        # DAC/source baseline: same unprivileged executable can read and write
        # before test loading. This is independent of the product approval state.
        baseline=subprocess.run([str(binary),'-c',
            'import pathlib,sys; [(pathlib.Path(p).read_bytes(),pathlib.Path(p).write_text("baseline\\n")) for p in sys.argv[1:]]',
            *[str(workspace/p) for p in expected[name]]],user=owner.pw_uid,group=owner.pw_gid,capture_output=True,text=True)
        assert baseline.returncode==0,baseline.stderr
        for path in expected[name]:(workspace/path).write_text('fixture-data\n')
        before={p:hashlib.sha256((workspace/p).read_bytes()).hexdigest() for p in expected[name]}
        document=case['document']['original_dsl']
        assert document.splitlines()[0]=='source AGENT = exec "**/semprobe"'
        for rule in case['artifact']['policy_ir']['rules']:
            for clause in rule['clauses']:
                assert clause['operation'] in ('read','write') and clause['effect']=='block'
                assert Path(clause['pattern']).parent==workspace and not clause['unless']
        policy=directory/'policy.yaml';policy.write_text('version: 1\npolicy: |\n'+''.join('  '+line+'\n' for line in document.splitlines()))
        script=directory/'probe.py';script.write_text(probe)
        prior_events=set(directory.glob('.actplane/runs/*/events.jsonl'))
        result=subprocess.run([str(cli),'--policy',str(policy),'run','--',str(binary),str(script),str(workspace),json.dumps(expected[name])],
            cwd=directory,env=env,capture_output=True,text=True,timeout=60)
        (directory/'stdout.txt').write_text(result.stdout);(directory/'stderr.txt').write_text(result.stderr)
        lines=[line for line in result.stdout.splitlines() if line.startswith('{')]
        observed=json.loads(lines[-1]) if lines else None
        event_files=set(directory.glob('.actplane/runs/*/events.jsonl'))-prior_events
        events=[json.loads(s) for p in event_files for s in p.read_text().splitlines() if s.strip()]
        unchanged=all(hashlib.sha256((workspace/p).read_bytes()).hexdigest()==before[p] for p,rights in expected[name].items() if 'file_mutate' in rights)
        record={'name':name,'passed':result.returncode==0 and unchanged and bool(events),'exit_code':result.returncode,
            'baseline_read_write_allowed':True,'mutation_protected_bytes_unchanged':unchanged,'observed':observed,
            'kernel_events':events,'event_file_owners':[p.stat().st_uid for p in event_files],
            'stderr':result.stderr,'candidate_product_state':'pending_review'}
        summary['cases'].append(record)
        (state/'kernel-results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
        print(json.dumps({'case':name,'passed':record['passed'],'events':len(events),'exit_code':result.returncode}),flush=True)
        assert record['passed'],name
finally:
    # Only this invocation's explicitly bounded pin root is eligible for cleanup.
    if pin.exists():
        assert pin.parent==Path('/sys/fs/bpf') and pin.name=='as-sem-accept-'+str(os.getpid())
        shutil.rmtree(pin)
    summary['test_pin_root_removed']=not pin.exists()
    (state/'kernel-results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps({'passed':len(summary['cases']),'output':str(state/'kernel-results.json'),'test_pin_root_removed':summary['test_pin_root_removed']}),flush=True)

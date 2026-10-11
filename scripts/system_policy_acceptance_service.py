#!/usr/bin/env python3
"""Explicit isolated console/Broker profile; does not restart 18003."""
import argparse,grp,hashlib,json,os,pwd,shutil,signal,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('/opt/aspol-accept-20261011')
STATE=Path('/var/lib/aspol-accept-20261011')
TASKS=Path('/vpt')
RUNTIME=Path('/run/aspol-accept-20261011')
PORT=18143

def environment():
    from scope_service import environment as base_environment
    env=base_environment()
    env.update(AGENTSCOPE_STATE_DIR=str(STATE),AGENTSCOPE_DB=str(STATE/'demo.sqlite3'),
        AGENTSCOPE_TASK_ROOT=str(TASKS),AGENTSCOPE_POLICY_DIR=str(STATE/'policies'),
        AGENTSCOPE_LOG_DIR=str(STATE/'logs'),AGENTSCOPE_RUNTIME_DIR=str(RUNTIME),
        AGENTSCOPE_BROKER_SOCKET=str(RUNTIME/'broker.sock'),AGENTSCOPE_PUBLIC_URL=f'http://127.0.0.1:{PORT}',
        AGENTSCOPE_SERVICE_HOME=str(STATE),AGENTSCOPE_UI_DIST=str(SOURCE/'frontend/dist'),
        PYTHONPATH=str(SOURCE/'backend'),AGENTSCOPE_RUNNER=str(SOURCE/'backend/broker/task_runner.py'),
        AGENTSCOPE_DSL_ADAPTER=str(SOURCE/'backend/dsl-adapter/target/release/agentscope-dsl-adapter'),
        ACTPLANE_BIN=str(STATE/'bin/actplane'),ACTPLANE_BPF_PIN_ROOT='/sys/fs/bpf/aspol-accept-20261011',
        AGENTSCOPE_CONTROLLED_INSTANCE_PROFILE='isolated-acceptance',
        AGENTSCOPE_HISTORY_WORKER='0',AGENTSCOPE_SCOPE_WORKER='0',AGENTSCOPE_WORKSPACE_WORKER='0',
        AGENTSCOPE_BOOTSTRAP_TEST_LIBRARY='0',AGENTSCOPE_INSTANCE_WORKER='1')
    return env

def stop():
    file=STATE/'service-pids.json'
    if not file.exists():return
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/api/agent-instances',timeout=3) as response:rows=json.load(response)['instances']
        for row in rows:
            if row.get('mode')!='controlled':continue
            req=urllib.request.Request(f'http://127.0.0.1:{PORT}/api/agent-instances/'+row['id']+'/stop',data=b'{}',headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=40) as response:response.read()
    except OSError:pass # A dead Broker is recovered from its own manifests on start.
    for role,pid in json.loads(file.read_text()).items():
        process=Path('/proc')/str(pid)
        if not process.exists():continue
        if ('AGENTSCOPE_DB='+str(STATE/'demo.sqlite3')).encode() not in (process/'environ').read_bytes():raise RuntimeError('Isolated service PID identity changed')
        os.kill(pid,signal.SIGTERM)
    time.sleep(1)

def start(report=None):
    if os.getuid()!=0:raise SystemExit('Requires root for the isolated Broker')
    if TASKS.exists() and not (STATE/'ownership.json').exists():raise RuntimeError('Refusing existing unowned task root')
    stop()
    user=pwd.getpwnam('agentscope-api');group=grp.getgrnam('agentscope-task')
    for path in (STATE,TASKS,STATE/'policies',STATE/'logs',STATE/'import/corpus'):
        path.mkdir(parents=True,exist_ok=True);os.chown(path,user.pw_uid,group.gr_gid);path.chmod(0o2770 if path==TASKS else 0o750)
    (STATE/'ownership.json').write_text(json.dumps({'task_root':str(TASKS),'purpose':'system policy isolated acceptance'}))
    SOURCE.mkdir(exist_ok=True)
    shutil.copytree(ROOT/'backend',SOURCE/'backend',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache','target'))
    shutil.copytree(ROOT/'frontend/dist',SOURCE/'frontend/dist',dirs_exist_ok=True)
    for name in ('dsh-managed-web','dsh-instance-runtime','hermes-instance'):
        shutil.copytree(ROOT/'integrations'/name,SOURCE/'integrations'/name,dirs_exist_ok=True)
    adapter=SOURCE/'backend/dsl-adapter/target/release/agentscope-dsl-adapter';adapter.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/'backend/dsl-adapter/target/release/agentscope-dsl-adapter',adapter)
    bindir=STATE/'bin';bindir.mkdir(exist_ok=True);bindir.chmod(0o755)
    binary=bindir/'actplane';candidate=bindir/'actplane.new';shutil.copy2(ROOT/'actplane/target/release/actplane',candidate);candidate.chmod(0o755);os.replace(candidate,binary)
    attestation=bindir/'actplane.capabilities.json'
    if report:
        evidence=json.loads(Path(report).read_text())
        if not evidence.get('runtime_verified') or evidence['binary_sha256']!=hashlib.sha256(binary.read_bytes()).hexdigest():raise RuntimeError('Kernel acceptance evidence does not match the binary')
        attestation.write_text(json.dumps({k:evidence[k] for k in ('schema','runtime_verified','binary_sha256','file_suffix','max_suffix_bytes','kernel_release')}))
        attestation.chmod(0o644)
    elif attestation.exists():attestation.unlink()
    env=environment()
    def demote():os.initgroups(user.pw_name,user.pw_gid);os.setgid(user.pw_gid);os.setuid(user.pw_uid)
    broker=subprocess.Popen(['/opt/agentscope/.venv/bin/python',str(SOURCE/'backend/broker/main.py')],cwd=SOURCE,env=env,stdout=open(STATE/'broker.log','a'),stderr=subprocess.STDOUT,start_new_session=True)
    api=subprocess.Popen(['/opt/agentscope/.venv/bin/python','-m','uvicorn','agentscope_app.main:app','--host','127.0.0.1','--port',str(PORT)],cwd=SOURCE,env=env,preexec_fn=demote,stdout=open(STATE/'api.log','a'),stderr=subprocess.STDOUT,start_new_session=True)
    (STATE/'service-pids.json').write_text(json.dumps({'api':api.pid,'broker':broker.pid}))
    for _ in range(60):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/api/security/system/policy-library',timeout=1) as response:
                if response.status==200:break
        except Exception:time.sleep(.2)
    else:raise RuntimeError('Isolated console failed to start; see isolated service logs')
    print(json.dumps({'url':f'http://127.0.0.1:{PORT}/?view=strategies&systemTab=policies','database':str(STATE/'demo.sqlite3'),'api':api.pid,'broker':broker.pid}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['start','stop']);parser.add_argument('--kernel-report')
    args=parser.parse_args()
    if args.action=='start':start(args.kernel_report)
    else:stop()

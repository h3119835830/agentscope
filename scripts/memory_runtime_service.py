#!/usr/bin/env python3
"""Isolated real-model DSH memory acceptance service; never restarts existing services."""
import argparse,grp,json,os,pwd,shlex,shutil,signal,subprocess,time,urllib.request
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[1]
CODE=Path('/opt/agentscope-memory-code-20261026')
STATE=Path('/var/lib/agentscope-memory-20261026')
TASKS=Path('/m')
PLUGIN=Path('/opt/agentscope-memory-plugin-f7b0375')
ACTPLANE=Path('/opt/agentscope-memory-runtime-20261026/bin/actplane')
PYTHON='/opt/agentscope/.venv/bin/python'

def environment():
    env=dict(os.environ)
    for line in Path('/etc/agentscope/agentscope.env').read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        key,value=line.split('=',1);parts=shlex.split(value);env[key]=parts[0] if len(parts)==1 else value
    env.update(AGENTSCOPE_STATE_DIR=str(STATE),AGENTSCOPE_DB=str(STATE/'acceptance.sqlite3'),
        AGENTSCOPE_TASK_ROOT=str(TASKS),AGENTSCOPE_POLICY_DIR=str(STATE/'policies'),
        AGENTSCOPE_LOG_DIR=str(STATE/'logs'),AGENTSCOPE_RUNTIME_DIR='/run/agentscope-memory-20261026',
        AGENTSCOPE_BROKER_SOCKET='/run/agentscope-memory-20261026/broker.sock',
        AGENTSCOPE_PUBLIC_URL='http://127.0.0.1:18005',AGENTSCOPE_APP_USER='agentscope-api',
        AGENTSCOPE_SERVICE_HOME=str(STATE),AGENTSCOPE_DSH_HOME=str(STATE/'dsh-home'),DSH_HOME=str(STATE/'dsh-home'),
        AGENTSCOPE_UI_DIST=str(CODE/'frontend/dist'),AGENTSCOPE_SCOPE_WORKER='1',AGENTSCOPE_HISTORY_WORKER='1',
        AGENTSCOPE_BOOTSTRAP_TEST_LIBRARY='1',AGENTSCOPE_RQ1_AUTO_IMPORT='0',AGENTSCOPE_DEV_NO_AUTH='1',
        ACTPLANE_BPF_PIN_ROOT='/sys/fs/bpf/agentscope-memory-20261026',ACTPLANE_BIN=str(ACTPLANE),
        DSH_BIN='/opt/agentscope/dsh/node_modules/@deepseek-ai/dsh/lib/bin.js',
        AGENTSCOPE_RUNNER=str(CODE/'backend/broker/task_runner.py'),PYTHONPATH=str(CODE/'backend'),
        AGENTSCOPE_DSH_DISABLE_BYTECODE='1',AGENTSCOPE_POLICY_NORMALIZATION='legacy',
        AGENTSCOPE_EXPERIMENT_PYTHON_RUNTIME='/var/lib/agentscope-rq5-v1/task-python',
        AGENTSCOPE_EXEC_PATH='/var/lib/agentscope-rq5-v1/task-python/bin:/opt/agentscope/bin:/opt/agentscope/dsh/node_modules/.bin:/usr/local/bin:/usr/bin:/bin',
        AGENTSCOPE_MEMORY_PLUGIN_ROOT=str(PLUGIN),AGENTSCOPE_MEMORY_ROOT='/var/lib/dsh-memory-acceptance-20261026')
    env.pop('AGENTSCOPE_ADMIN_TOKEN',None)
    return env

def sync_code():
    ACTPLANE.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2('/var/lib/agentscope-scope-demo/bin/actplane',ACTPLANE)
    ACTPLANE.chmod(0o755)
    CODE.mkdir(exist_ok=True)
    ignored=shutil.ignore_patterns('node_modules','__pycache__','*.pyc','.env','.venv')
    for directory in ('backend','integrations'):
        shutil.copytree(SOURCE/directory,CODE/directory,dirs_exist_ok=True,ignore=ignored)
    shutil.copytree(SOURCE/'frontend/dist',CODE/'frontend/dist',dirs_exist_ok=True)
    for dest,target in ((CODE/'dsh','/opt/agentscope/dsh'),
        (CODE/'integrations/pi-policy-tools/node_modules','/opt/agentscope/integrations/pi-policy-tools/node_modules')):
        if not dest.exists():dest.symlink_to(target,target_is_directory=True)
    (STATE/'source-revision.json').write_text(json.dumps({'source':str(SOURCE),'head':subprocess.check_output(['git','-c','safe.directory='+str(SOURCE),'-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip(),'modified_source_snapshot':True}))

def main():
    action=argparse.ArgumentParser();action.add_argument('action',choices=['start','restart','stop','status']);args=action.parse_args()
    if os.getuid()!=0:raise SystemExit('requires isolated root Broker setup')
    api_user=pwd.getpwnam('agentscope-api');agent=pwd.getpwnam('agentscope-agent');group=grp.getgrnam('agentscope-task')
    if TASKS.exists() and not (STATE/'ownership.json').exists():raise SystemExit('refusing an unowned /m')
    STATE.mkdir(mode=0o750,exist_ok=True);os.chown(STATE,api_user.pw_uid,group.gr_gid);STATE.chmod(0o750)
    TASKS.mkdir(mode=0o2770,exist_ok=True);os.chown(TASKS,api_user.pw_uid,group.gr_gid);TASKS.chmod(0o2770)
    (STATE/'ownership.json').write_text(json.dumps({'task_root':str(TASKS),'purpose':'isolated memory runtime acceptance'}))
    env=environment()
    if args.action=='status':print(json.dumps({'url':env['AGENTSCOPE_PUBLIC_URL'],'state':str(STATE)}));return
    previous=json.loads((STATE/'pids.json').read_text()) if (STATE/'pids.json').exists() else {}
    # Require callers to close native tasks through the authoritative API first.
    scope=Path('/sys/fs/cgroup')/Path(env['ACTPLANE_BPF_PIN_ROOT']).name
    if any(path.read_text().strip() for path in scope.glob('*/cgroup.procs')):
        raise RuntimeError('close the isolated native tasks before stopping or restarting this service')
    for role,pid in previous.items():
        command=Path('/proc',str(pid),'cmdline')
        if not command.exists():continue
        if args.action=='start':raise SystemExit('acceptance instance is already running')
        proc_env=Path('/proc',str(pid),'environ').read_bytes()
        if str(STATE).encode() not in proc_env:raise SystemExit('refusing unrelated process')
        os.kill(pid,signal.SIGTERM)
    for _ in range(50):
        if all(not Path('/proc',str(pid)).exists() for pid in previous.values()):break
        time.sleep(.1)
    if args.action=='stop':print(json.dumps({'isolated':True,'status':'stopped'}));return
    sync_code()
    for name in ('policies','logs','scope-pi','pi-jobs'):
        directory=STATE/name;directory.mkdir(exist_ok=True);os.chown(directory,api_user.pw_uid,group.gr_gid);directory.chmod(0o750)
    home=STATE/'dsh-home'
    if not home.exists():
        home.mkdir(mode=0o750)
        for name in ('.credentials.yaml','settings.yaml'):
            source=Path('/var/lib/agentscope-agent/.dsh')/name
            if source.is_file():shutil.copy2(source,home/name)
        shutil.copytree('/var/lib/agentscope-agent/.dsh/profiles',home/'profiles',symlinks=True)
        for directory,dirs,files in os.walk(home,followlinks=False):
            os.chown(directory,agent.pw_uid,group.gr_gid);os.chmod(directory,0o750)
            for name in files:
                path=Path(directory)/name
                if not path.is_symlink():os.chown(path,agent.pw_uid,group.gr_gid);os.chmod(path,0o600)
    def demote():os.initgroups(api_user.pw_name,api_user.pw_gid);os.setgid(api_user.pw_gid);os.setuid(api_user.pw_uid)
    subprocess.run([PYTHON,'-c','from agentscope_app import db; db.init_db(); from agentscope_app.bootstrap.library import seed_test_library; seed_test_library()'],env=env,preexec_fn=demote,check=True)
    broker=subprocess.Popen([PYTHON,str(CODE/'backend/broker/main.py')],cwd=CODE,env=env,
        stdout=open(STATE/'broker.log','a'),stderr=subprocess.STDOUT,start_new_session=True)
    from urllib.parse import urlparse
    api=subprocess.Popen([PYTHON,'-m','uvicorn','agentscope_app.main:app','--host','127.0.0.1','--port',str(urlparse(env['AGENTSCOPE_PUBLIC_URL']).port)],
        cwd=CODE,env=env,preexec_fn=demote,stdout=open(STATE/'api.log','a'),stderr=subprocess.STDOUT,start_new_session=True)
    (STATE/'pids.json').write_text(json.dumps({'broker':broker.pid,'api':api.pid}))
    for _ in range(50):
        if api.poll() is not None or broker.poll() is not None:raise RuntimeError('isolated service exited during startup')
        try:
            with urllib.request.urlopen(env['AGENTSCOPE_PUBLIC_URL']+'/api/health',timeout=1) as response:
                if json.load(response).get('ok') is True:break
        except OSError:time.sleep(.1)
    else:raise RuntimeError('isolated API did not become ready')
    print(json.dumps({'url':env['AGENTSCOPE_PUBLIC_URL'],'broker_pid':broker.pid,'api_pid':api.pid,'isolated':True}))

if __name__=='__main__':main()

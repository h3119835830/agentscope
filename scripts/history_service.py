#!/usr/bin/env python3
"""Separate loopback preview and acceptance service; retains no credentials in reports."""
import os
import json
import grp
import pwd
import shutil
import subprocess
import argparse
import signal
from pathlib import Path
from rq5_service import environment as installed_environment

ROOT=Path(__file__).resolve().parents[1]
STATE=Path('/var/lib/agentscope-history-v1')
TASKS=Path('/h')
URL='http://127.0.0.1:18002'


def environment():
    env=installed_environment()
    env.update({'AGENTSCOPE_STATE_DIR':str(STATE),'AGENTSCOPE_DB':str(STATE/'acceptance.sqlite3'),
        'AGENTSCOPE_TASK_ROOT':str(TASKS),'AGENTSCOPE_POLICY_DIR':str(STATE/'policies'),
        'AGENTSCOPE_LOG_DIR':str(STATE/'logs'),'AGENTSCOPE_RUNTIME_DIR':'/run/agentscope-history-v1',
        'AGENTSCOPE_BROKER_SOCKET':'/run/agentscope-history-v1/broker.sock','AGENTSCOPE_PUBLIC_URL':URL,
        'AGENTSCOPE_SERVICE_HOME':str(STATE),'AGENTSCOPE_UI_DIST':str(ROOT/'frontend/dist'),
        'AGENTSCOPE_DSH_HOME':str(STATE/'dsh-home'),'DSH_HOME':str(STATE/'dsh-home'),
        'AGENTSCOPE_DEV_NO_AUTH':'1','PYTHONPATH':str(ROOT/'backend')})
    env['AGENTSCOPE_RUNNER']=str(ROOT/'backend/broker/task_runner.py')
    return env


def start(restart=False):
    if os.getuid()!=0:raise SystemExit('Run as root for the separate local broker')
    user=pwd.getpwnam('agentscope-api');group=grp.getgrnam('agentscope-task')
    STATE.mkdir(exist_ok=True);os.chown(STATE,user.pw_uid,group.gr_gid);STATE.chmod(0o750)
    marker=STATE/'task-root.json'
    if TASKS.exists() and not marker.exists():raise SystemExit('Refusing unowned task root /h')
    TASKS.mkdir(exist_ok=True);os.chown(TASKS,user.pw_uid,group.gr_gid);TASKS.chmod(0o2770)
    marker.write_text(json.dumps({'path':str(TASKS),'purpose':'isolated history acceptance'}))
    for folder in ('policies','logs','report','import/corpus'):
        target=STATE/folder;target.mkdir(parents=True,exist_ok=True);os.chown(target,user.pw_uid,group.gr_gid);target.chmod(0o750)
    home=STATE/'dsh-home'
    if not home.exists():
        source=Path('/var/lib/agentscope-rq5-v1/dsh-home')
        shutil.copytree(source,home,symlinks=True,ignore=shutil.ignore_patterns('sessions','storages'))
        agent=pwd.getpwnam('agentscope-agent')
        for directory,dirs,files in os.walk(home):
            os.chown(directory,agent.pw_uid,group.gr_gid);os.chmod(directory,0o750)
            for name in files:
                p=Path(directory)/name
                if not p.is_symlink():os.chown(p,agent.pw_uid,group.gr_gid);os.chmod(p,0o600)
    env=environment()
    def demote():os.initgroups(user.pw_name,user.pw_gid);os.setgid(user.pw_gid);os.setuid(user.pw_uid)
    pidfile=STATE/'service-pids.json'
    pids=json.loads(pidfile.read_text()) if pidfile.exists() else {}
    if pids and not restart:raise SystemExit('Service already registered; use restart')
    if pids:
        for role,pid in pids.items():
            command=Path(f'/proc/{pid}/cmdline')
            if command.exists():
                environ=Path(f'/proc/{pid}/environ').read_bytes()
                if env['AGENTSCOPE_DB'].encode() not in environ:raise SystemExit('Process identity mismatch')
                os.kill(pid,signal.SIGTERM)
        import time
        time.sleep(1)
    broker=subprocess.Popen(['/opt/agentscope/.venv/bin/python',str(ROOT/'backend/broker/main.py')],env=env,cwd=ROOT,
        stdout=open(STATE/'broker-service.log','a'),stderr=subprocess.STDOUT,start_new_session=True)
    api=subprocess.Popen(['/opt/agentscope/.venv/bin/python','-m','uvicorn','agentscope_app.main:app','--host','127.0.0.1','--port','18002'],
        env=env,cwd=ROOT,preexec_fn=demote,stdout=open(STATE/'api-service.log','a'),stderr=subprocess.STDOUT,start_new_session=True)
    pidfile.write_text(json.dumps({'broker':broker.pid,'api':api.pid}))
    import time
    import urllib.request
    for _ in range(30):
        try:
            with urllib.request.urlopen(URL+'/api/health',timeout=1):break
        except OSError:time.sleep(.2)
    else:raise RuntimeError('Isolated API startup failed; inspect its service log')
    print(json.dumps({'url':URL,'database':env['AGENTSCOPE_DB'],'root':str(ROOT),'pids':{'broker':broker.pid,'api':api.pid}}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['start','restart']);args=parser.parse_args();start(args.action=='restart')

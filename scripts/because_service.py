#!/usr/bin/env python3
"""Isolated because acceptance instance; never restarts 18000/18003/18004."""
import json
import os
import pwd
import grp
import shutil
import subprocess
import sys
import signal
import time
import sqlite3
from pathlib import Path
from rq5_service import environment as base_environment

ROOT = Path(__file__).resolve().parents[1]
STATE = Path('/var/lib/agentscope-because-v1')
TASKS = Path('/b')
URL = 'http://127.0.0.1:18005'


def environment():
    env = base_environment()
    env.update({'AGENTSCOPE_STATE_DIR': str(STATE), 'AGENTSCOPE_DB': str(STATE/'acceptance.sqlite3'),
                'AGENTSCOPE_TASK_ROOT': str(TASKS), 'AGENTSCOPE_POLICY_DIR': str(STATE/'policies'),
                'AGENTSCOPE_LOG_DIR': str(STATE/'logs'), 'AGENTSCOPE_RUNTIME_DIR': '/run/agentscope-because-v1',
                'AGENTSCOPE_BROKER_SOCKET': '/run/agentscope-because-v1/broker.sock',
                'AGENTSCOPE_PUBLIC_URL': URL, 'AGENTSCOPE_SERVICE_HOME': str(STATE),
                'AGENTSCOPE_APP_USER': 'agentscope-api', 'AGENTSCOPE_SCOPE_WORKER': '1',
                'AGENTSCOPE_HISTORY_WORKER': '1', 'AGENTSCOPE_INSTANCE_WORKER': '0',
                'AGENTSCOPE_POLICY_NORMALIZATION': 'legacy', 'AGENTSCOPE_DEV_NO_AUTH': '0',
                'AGENTSCOPE_UI_DIST': str(ROOT/'frontend/dist'),
                'AGENTSCOPE_DSH_HOME': str(STATE/'dsh-home'), 'DSH_HOME': str(STATE/'dsh-home'),
                'ACTPLANE_BPF_PIN_ROOT': '/sys/fs/bpf/agentscope-because-v1',
                'ACTPLANE_BIN': str(STATE/'bin/actplane'),
                'AGENTSCOPE_RUNNER': str(ROOT/'backend/broker/task_runner.py'),
                'PYTHONPATH': str(ROOT/'backend')})
    env['DSH_BIN'] = str(STATE/'dsh-home/profiles/headless/node_modules/@deepseek-ai/dsh/lib/bin.js')
    env['AGENTSCOPE_ADMIN_TOKEN'] = (STATE/'admin-token').read_text()
    return env


def start():
    if os.geteuid()!=0:raise SystemExit('Requires isolated Broker setup as root')
    if (STATE/'service-pids.json').exists():raise SystemExit('Instance already prepared; inspect its identity before any restart')
    if TASKS.exists():raise SystemExit('Refusing pre-existing /b without this instance ownership')
    for dependency in [ROOT/'dsh/node_modules/@deepseek-ai/dsh/package.json',ROOT/'integrations/pi-policy-tools/node_modules/@earendil-works/pi-coding-agent/package.json']:
        if not dependency.is_file():raise SystemExit('Prepare the installed read-only runtime dependency before setup: '+str(dependency))
    user=pwd.getpwnam('agentscope-api');group=grp.getgrnam('agentscope-task')
    STATE.mkdir(mode=0o750);os.chown(STATE,user.pw_uid,group.gr_gid)
    TASKS.mkdir(mode=0o2770);os.chown(TASKS,user.pw_uid,group.gr_gid);TASKS.chmod(0o2770)
    (STATE/'ownership.json').write_text(json.dumps({'task_root':str(TASKS),'port':18005,'purpose':'because recovery acceptance'}))
    for name in ['policies','logs','report','import/corpus','bin']:
        path=STATE/name;path.mkdir(parents=True,exist_ok=True);os.chown(path,user.pw_uid,group.gr_gid);path.chmod(0o750)
    import secrets
    token=STATE/'admin-token';token.write_text(secrets.token_urlsafe(40));token.chmod(0o600)
    shutil.copy2('/var/lib/agentscope-scope-demo/bin/actplane',STATE/'bin/actplane')
    shutil.copytree('/var/lib/agentscope-scope-demo/dsh-home',STATE/'dsh-home',symlinks=True,
                    ignore=shutil.ignore_patterns('sessions','storages'))
    launch()


def launch():
    user=pwd.getpwnam('agentscope-api')
    def demote():
        os.initgroups(user.pw_name,user.pw_gid);os.setgid(user.pw_gid);os.setuid(user.pw_uid)
    env=environment()
    broker=subprocess.Popen(['/opt/agentscope/.venv/bin/python',str(ROOT/'backend/broker/main.py')],cwd=ROOT,env=env,
                            stdout=open(STATE/'broker.log','a'),stderr=subprocess.STDOUT,start_new_session=True)
    api=subprocess.Popen(['/opt/agentscope/.venv/bin/python','-m','uvicorn','agentscope_app.main:app','--host','127.0.0.1','--port','18005'],
                         cwd=ROOT,env=env,preexec_fn=demote,stdout=open(STATE/'api.log','a'),stderr=subprocess.STDOUT,start_new_session=True)
    (STATE/'service-pids.json').write_text(json.dumps({'broker':broker.pid,'api':api.pid}))
    print(json.dumps({'url':URL,'task_root':str(TASKS),'state':str(STATE),'broker':broker.pid,'api':api.pid}))


def restart():
    if os.geteuid()!=0:raise SystemExit('Requires root')
    marker=json.loads((STATE/'ownership.json').read_text())
    if marker.get('task_root')!=str(TASKS) or marker.get('port')!=18005:raise SystemExit('Instance ownership mismatch')
    with sqlite3.connect(STATE/'acceptance.sqlite3') as con:
        if con.execute("SELECT 1 FROM managed_tasks WHERE json_extract(state_json,'$.phase') NOT IN ('ended','prepared','failed')").fetchone():
            raise SystemExit('Close this instance tasks before restart')
    pids=json.loads((STATE/'service-pids.json').read_text())
    for pid in pids.values():
        path=Path('/proc',str(pid))
        if not path.exists():continue
        values=(path/'environ').read_bytes().split(b'\0')
        if ('AGENTSCOPE_DB='+str(STATE/'acceptance.sqlite3')).encode() not in values:raise SystemExit('Service PID identity mismatch')
        os.kill(pid,signal.SIGTERM)
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        alive=[]
        for pid in pids.values():
            path=Path('/proc',str(pid),'stat')
            if path.exists():
                value=path.read_text();alive.append(value[value.rfind(')')+2:].split()[0]!='Z')
        if not any(alive):break
        time.sleep(.1)
    else:raise SystemExit('Isolated services did not stop')
    launch()


if __name__=='__main__':
    if sys.argv[1:]==['start']:start()
    elif sys.argv[1:]==['restart']:restart()
    else:raise SystemExit('Expected start or restart')

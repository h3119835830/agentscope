#!/usr/bin/env python3
"""Separate policy-flow lab; never operates the production console or its agents."""
import argparse
import json
import subprocess
import os
import pwd
import shutil
import signal
import time
import urllib.request
from pathlib import Path
import system_policy_acceptance_service as service

service.SOURCE=Path('/opt/asflow-accept-20261013')
service.STATE=Path('/var/lib/asflow-accept-20261013')
service.TASKS=Path('/aft')
service.RUNTIME=Path('/run/asflow-accept-20261013')
service.PORT=18173
base_environment=service.environment
def environment():
    return {**base_environment(),
            'ACTPLANE_BPF_PIN_ROOT':'/sys/fs/bpf/asflow-accept-20261013',
            'AGENTSCOPE_POLICY_SOURCE_CACHE':str(service.RUNTIME/'policy-source-facts.json'),
            'AGENTSCOPE_HISTORY_WORKER':'1'}
service.environment=environment

def reload_api():
    file=service.STATE/'service-pids.json';pids=json.loads(file.read_text());pid=pids['api']
    assert ('AGENTSCOPE_DB='+str(service.STATE/'demo.sqlite3')).encode() in Path('/proc',str(pid),'environ').read_bytes()
    os.kill(pid,signal.SIGTERM)
    for _ in range(50):
        if not Path('/proc',str(pid)).exists():break
        time.sleep(.1)
    else:raise RuntimeError('Isolated API did not stop')
    shutil.copytree(service.ROOT/'backend',service.SOURCE/'backend',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache','target'))
    shutil.copytree(service.ROOT/'frontend/dist',service.SOURCE/'frontend/dist',dirs_exist_ok=True)
    user=pwd.getpwnam('agentscope-api')
    def demote():os.initgroups(user.pw_name,user.pw_gid);os.setgid(user.pw_gid);os.setuid(user.pw_uid)
    api=subprocess.Popen(['/opt/agentscope/.venv/bin/python','-m','uvicorn','agentscope_app.main:app','--host','127.0.0.1','--port',str(service.PORT)],
        cwd=service.SOURCE,env=environment(),preexec_fn=demote,stdout=open(service.STATE/'api.log','a'),stderr=subprocess.STDOUT,start_new_session=True)
    file.write_text(json.dumps({**pids,'api':api.pid}))
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        try:
            with urllib.request.urlopen('http://127.0.0.1:'+str(service.PORT)+'/api/health',timeout=1) as response:
                if response.status==200:break
        except OSError:time.sleep(.1)
    else:raise RuntimeError('Isolated API restart failed')
    print(json.dumps({'isolated_api':api.pid,'broker_preserved':pids['broker']}))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('start','stop'))
    parser.add_argument('--kernel-report',default='/var/lib/agentscope-scope-demo/bin/actplane.capabilities.json')
    parser.add_argument('--api-only',action='store_true')
    options=parser.parse_args()
    if options.action=='start' and options.api_only:reload_api()
    elif options.action=='start':
        service.start(options.kernel_report)
        sampler=subprocess.Popen(['python3',str(service.ROOT/'scripts/observe_agent_policy_sources.py'),
            '--database',str(service.STATE/'demo.sqlite3'),
            '--output',str(service.RUNTIME/'policy-source-facts.json')],
            env=environment(),stdout=open(service.STATE/'source-observer.log','a'),
            stderr=subprocess.STDOUT,start_new_session=True)
        file=service.STATE/'service-pids.json'
        file.write_text(json.dumps({**json.loads(file.read_text()),'source_observer':sampler.pid}))
    else:service.stop()

#!/usr/bin/env python3
"""Single entry point for a resumable, private acceptance instance."""
import os
import argparse
import sqlite3
import subprocess
import json
import urllib.request
from rq5_service import ROOT, STATE, environment

if os.getuid()!=0:raise SystemExit('Use sudo or wsl -d Ubuntu -u root')
parser=argparse.ArgumentParser();parser.add_argument('--fresh',action='store_true');args=parser.parse_args()
python=str(ROOT/'.venv/bin/python')
def run(script,*args):subprocess.run([python,str(ROOT/'scripts'/script),*args],cwd=ROOT,check=True)
query=urllib.request.Request('http://127.0.0.1:18000/api/dashboard',headers={'Authorization':'Bearer '+environment()['AGENTSCOPE_ADMIN_TOKEN']})
with urllib.request.urlopen(query,timeout=10) as response:live=json.load(response)
if live['stats']['active_tasks'] or live['active']:raise SystemExit('Finish the original-instance active domain before RQ5 acceptance')
run('rq5_probe_runtime.py')
run('rq5_task_runtime.py')
if not (STATE/'service-pids.json').exists():
    ui=STATE/'ui-build'
    subprocess.run([str(ROOT/'bin/node'),str(ROOT/'frontend/node_modules/vite/bin/vite.js'),'build','--outDir',str(ui),'--emptyOutDir'],cwd=ROOT/'frontend',check=True)
    run('rq5_service.py','start','--ui-source',str(ui))
else:run('rq5_service.py','status')
active=False
if (STATE/'acceptance.sqlite3').exists():
    with sqlite3.connect(STATE/'acceptance.sqlite3') as con:active=bool(con.execute("SELECT 1 FROM tasks WHERE status IN ('starting','running')").fetchone())
if not active:run('rq5_minimal_probe.py')
run('rq5_acceptance.py',*(['--fresh'] if args.fresh else []))
run('rq5_verify_probes.py')
run('rq5_manual_regression.py')
run('rq5_refresh_report.py')
run('rq5_isolation_audit.py')
print('Acceptance and manual GitHub regression complete; private reports are in '+str(STATE/'report'))

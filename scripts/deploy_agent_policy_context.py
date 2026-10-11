#!/usr/bin/env python3
"""Stage an isolated API release; only --apply restarts the 18003 API.

The Broker, native Agents, loaded policy and other service instances are untouched.
The old release and prior systemd drop-ins are retained for rollback.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
import urllib.request

SOURCE=Path(__file__).resolve().parents[1]
OLD=Path('/opt/agentscope-task-archive-20261007')
RELEASE=Path('/opt/agentscope-agent-context-20261011')
UNIT='agentscope-scope-demo-api.service'
DROP=Path('/etc/systemd/system/'+UNIT+'.d/60-agent-policy-context-20261011.conf')

def stage(refresh=False):
    if os.getuid()!=0:raise SystemExit('Run release preparation as root')
    if (RELEASE/'agent-context-manifest.json').exists() and not refresh:raise SystemExit('Release already prepared; use --refresh for a tested source update')
    RELEASE.mkdir(mode=0o755,exist_ok=True)
    for item in OLD.iterdir():
        dest=RELEASE/item.name
        if dest.exists() or dest.is_symlink():continue
        if item.name in ('backend','scripts'):
            shutil.copytree(item,dest,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        else:dest.symlink_to(item,target_is_directory=item.is_dir())
    changed=subprocess.check_output(['git','-c','safe.directory='+str(SOURCE),'diff','--name-only','90af640fb748216fec23fb1fbaf1a80b9b355ea0','--','backend'],cwd=SOURCE,text=True).splitlines()
    added=subprocess.check_output(['git','-c','safe.directory='+str(SOURCE),'ls-files','--others','--exclude-standard','backend/agentscope_app'],cwd=SOURCE,text=True).splitlines()
    manifest={}
    for name in sorted(set(changed+added)):
        source=SOURCE/name
        if not source.is_file() or name.startswith('backend/tests/'):continue
        dest=RELEASE/name;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,dest);dest.chmod(0o644)
        manifest[name]=hashlib.sha256(dest.read_bytes()).hexdigest()
    (RELEASE/'agent-context-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Prepared API release:',len(manifest),'changed source files')

def apply():
    if not (RELEASE/'agent-context-manifest.json').is_file():raise SystemExit('Prepare and verify the release first')
    manifest=json.loads((RELEASE/'agent-context-manifest.json').read_text())
    for name,expected in manifest.items():
        if hashlib.sha256((RELEASE/name).read_bytes()).hexdigest()!=expected:raise SystemExit('Release hash mismatch: '+name)
    with sqlite3.connect('/var/lib/agentscope-scope-demo/demo.sqlite3') as con:
        if con.execute("SELECT COUNT(*) FROM history_jobs WHERE status IN ('queued','running')").fetchone()[0]:raise SystemExit('Wait for active generation jobs before API restart')
        if con.execute("SELECT COUNT(*) FROM instance_dsl_scopes WHERE phase!='ready'").fetchone()[0]:raise SystemExit('Policy application is not settled')
    unit_text='[Service]\nWorkingDirectory='+str(RELEASE)+'\nExecStart=\nExecStart=/opt/agentscope/.venv/bin/python '+str(RELEASE)+'/scripts/scope_systemd_exec.py api\n'
    if DROP.exists() and DROP.read_text()!=unit_text:raise SystemExit('Release drop-in was changed externally; inspect before deployment')
    DROP.write_text(unit_text)
    subprocess.run(['systemctl','daemon-reload'],check=True)
    started=time.monotonic()
    try:
        subprocess.run(['systemctl','restart',UNIT],check=True,timeout=20)
        with urllib.request.urlopen('http://127.0.0.1:18003/api/health',timeout=2) as response:assert response.status==200
    except Exception:
        DROP.unlink();subprocess.run(['systemctl','daemon-reload'],check=True)
        subprocess.run(['systemctl','restart',UNIT],check=True,timeout=20)
        raise
    print('API ready after restart:',round(time.monotonic()-started,3),'seconds')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');parser.add_argument('--apply',action='store_true');parser.add_argument('--refresh',action='store_true');args=parser.parse_args()
    if args.refresh:stage(refresh=True)
    elif args.prepare:stage()
    elif args.apply:apply()
    else:print('Dry run:',SOURCE,'->',RELEASE,'; API unit:',UNIT,'; no policy application')

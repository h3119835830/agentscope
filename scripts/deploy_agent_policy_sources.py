"""Stage the tested source-reader API separately; restart only the 18003 API."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
PREVIOUS=Path('/opt/agentscope-agent-context-20261011')
RELEASE=Path('/opt/agentscope-agent-sources-20261011')
UNIT='agentscope-scope-demo-api.service'
DROP=Path('/etc/systemd/system/'+UNIT+'.d/70-agent-policy-sources-20261011.conf')
FILES=['backend/agentscope_app/console.py','backend/agentscope_app/history/agent_context.py',
       'backend/agentscope_app/history/capabilities.py','backend/agentscope_app/instances/policy_sources.py','scripts/observe_agent_policy_sources.py']


def stage(refresh=False):
    assert os.geteuid()==0
    if RELEASE.exists():
        assert refresh and (RELEASE/'policy-source-manifest.json').is_file(),'Inspect existing release before replacing'
    else:
        shutil.copytree(PREVIOUS,RELEASE,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    manifest={}
    for rel in FILES:
        dest=RELEASE/rel
        assert dest.resolve().is_relative_to(RELEASE.resolve()),'Source target escaped isolated release'
        shutil.copyfile(ROOT/rel,dest);dest.chmod(0o644)
        manifest[rel]=hashlib.sha256(dest.read_bytes()).hexdigest()
    (RELEASE/'policy-source-manifest.json').write_text(json.dumps(manifest,indent=2))
    print('Staged isolated API source release; previous release unchanged')


def apply():
    assert os.geteuid()==0
    manifest=json.loads((RELEASE/'policy-source-manifest.json').read_text())
    for rel,expected in manifest.items():
        assert hashlib.sha256((RELEASE/rel).read_bytes()).hexdigest()==expected
    with sqlite3.connect('file:/var/lib/agentscope-scope-demo/demo.sqlite3?mode=ro',uri=True) as con:
        assert con.execute("SELECT COUNT(*) FROM history_jobs WHERE status IN ('queued','running')").fetchone()[0]==0,'Active generation jobs'
        assert con.execute("SELECT COUNT(*) FROM instance_dsl_scopes WHERE phase!='ready'").fetchone()[0]==0,'Policy change in progress'
        assert con.execute("SELECT COUNT(*) FROM instance_dsl_proposals WHERE state='applying'").fetchone()[0]==0,'Approval in progress'
    observer=Path('/etc/systemd/system/agentscope-policy-source-observer.service')
    content='[Unit]\nDescription=AgentScope read-only executable source observer\nAfter=local-fs.target\n[Service]\nType=simple\nExecStart=/usr/bin/python3 '+str(RELEASE)+'/scripts/observe_agent_policy_sources.py\nRestart=on-failure\nRestartSec=2\nNoNewPrivileges=yes\nProtectSystem=strict\nProtectHome=yes\nPrivateTmp=yes\nReadWritePaths=/run/agentscope-scope-demo\nCapabilityBoundingSet=CAP_SYS_PTRACE CAP_DAC_READ_SEARCH CAP_CHOWN\nRestrictAddressFamilies=AF_UNIX\nIPAddressDeny=any\n[Install]\nWantedBy=multi-user.target\n'
    assert not observer.exists() or observer.read_text()==content,'Observer unit changed externally'
    observer.write_text(content)
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','enable','--now',observer.name],check=True,timeout=20)
    assert not DROP.exists() or str(RELEASE) in DROP.read_text(),'Deployment drop-in changed externally'
    DROP.write_text('[Service]\nWorkingDirectory='+str(RELEASE)+'\nExecStart=\nExecStart=/opt/agentscope/.venv/bin/python '+str(RELEASE)+'/scripts/scope_systemd_exec.py api\n')
    try:
        subprocess.run(['systemctl','daemon-reload'],check=True)
        subprocess.run(['systemctl','restart',UNIT],check=True,timeout=20)
        with urllib.request.urlopen('http://127.0.0.1:18003/api/health',timeout=5) as r:assert r.status==200
    except Exception:
        DROP.unlink();subprocess.run(['systemctl','daemon-reload'],check=True)
        subprocess.run(['systemctl','restart',UNIT],check=True,timeout=20)
        raise
    print('18003 API ready; Broker, native Agents and policies untouched')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',action='store_true');parser.add_argument('--apply',action='store_true');parser.add_argument('--refresh',action='store_true');args=parser.parse_args()
    if args.stage or args.refresh:stage(args.refresh)
    elif args.apply:apply()
    else:print('Dry run: isolated API release, explicit --stage and --apply required')

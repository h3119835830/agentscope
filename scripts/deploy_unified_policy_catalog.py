#!/usr/bin/env python3
"""Publish control/UI code only; preserve Agent authority, Broker and other ports."""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path
from deploy_policy_semantics import authority, guard, service, listeners, files, sha, api

ROOT = Path(__file__).resolve().parents[1]
STATE = Path('/var/lib/agentscope-scope-demo')
API = 'agentscope-scope-demo-api.service'
BROKER = 'agentscope-scope-demo-broker.service'
DROP = Path('/etc/systemd/system/'+API+'.d/99zzzzzzzz-template-configurations-20261014.conf')
BASE = 'fddc532'


def git(*args):
    return subprocess.check_output(['git','-c','safe.directory='+str(ROOT),'-C',str(ROOT),*args])


def stage():
    assert os.geteuid() == 0
    guard()
    before = service(API); broker = service(BROKER)
    live = Path(before['WorkingDirectory'])
    assert live.parent == Path('/opt')
    # Compare every live application file with the integrated baseline, before overlaying.
    for rel, digest in files(live/'backend/agentscope_app').items():
        original = git('show',BASE+':backend/agentscope_app/'+rel)
        assert hashlib.sha256(original).hexdigest() == digest, 'Live application changed: '+rel
    release = Path('/opt/agentscope-unified-policy-catalog-'+time.strftime('%Y%m%d-%H%M%S'))
    assert not release.exists()
    release.mkdir(mode=0o755)
    for folder in ('backend','scripts','integrations','bin','dsh'):
        if (live/folder).exists():
            shutil.copytree(live/folder,release/folder,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copytree(ROOT/'backend/agentscope_app',release/'backend/agentscope_app',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copytree(ROOT/'frontend/dist',release/'frontend/dist')
    assert files(live/'dsh') == files(release/'dsh'), 'DSH files must stay unchanged'
    subprocess.run(['/opt/agentscope/.venv/bin/python','-m','compileall','-q',str(release/'backend/agentscope_app')],check=True)
    manifest = {'release':str(release),'api':before,'broker':broker,'authority':authority(),'listeners':listeners(),
                'live_files':files(live/'backend/agentscope_app'),'release_files':files(release),
                'dsh_files':files(live/'dsh'),'source_commit':git('rev-parse','HEAD').decode().strip(),'old_drop':DROP.read_text() if DROP.exists() else None}
    path = release/'unified-catalog-deployment.json'
    path.write_text(json.dumps(manifest,indent=2));path.chmod(0o600)
    print(json.dumps({'staged':str(release),'manifest':str(path)}))


def apply(path):
    assert os.geteuid() == 0
    manifest_path = Path(path);m = json.loads(manifest_path.read_text());release = Path(m['release'])
    assert release.parent == Path('/opt') and release.name.startswith('agentscope-unified-policy-catalog-')
    assert manifest_path == release/'unified-catalog-deployment.json'
    assert {k:v for k,v in files(release).items() if k != manifest_path.name} == m['release_files']
    assert service(API) == m['api'] and service(BROKER) == m['broker']
    assert files(Path(m['api']['WorkingDirectory'])/'backend/agentscope_app') == m['live_files']
    assert files(Path(m['api']['WorkingDirectory'])/'dsh') == m['dsh_files']
    assert (DROP.read_text() if DROP.exists() else None) == m['old_drop']
    guard();assert authority() == m['authority'] and listeners() == m['listeners']
    backup = STATE/'release-backups'/release.name;backup.mkdir(parents=True,mode=0o700)
    shutil.copytree(STATE/'ui',backup/'ui')
    with sqlite3.connect(STATE/'demo.sqlite3') as src,sqlite3.connect(backup/'demo.sqlite3') as dst:
        src.backup(dst)
    (backup/'demo.sqlite3').chmod(0o600)
    result = {'published':False,'release':str(release),'source_commit':m['source_commit'],'agent_actions':False,'policy_application':False}
    try:
        # Old entry remains usable until the new API passes health verification.
        shutil.copytree(release/'frontend/dist/assets',STATE/'ui/assets',dirs_exist_ok=True)
        DROP.write_text('[Service]\nTimeoutStopSec=3\nWorkingDirectory='+str(release)+'\nExecStart=\nExecStart=/opt/agentscope/.venv/bin/python '+str(release)+'/scripts/scope_systemd_exec.py api\nExecStartPost=\nExecStartPost=/opt/agentscope/.venv/bin/python '+str(release)+'/scripts/scope_systemd_exec.py api-ready\n')
        subprocess.run(['systemctl','daemon-reload'],check=True)
        started = time.monotonic()
        subprocess.run(['systemctl','restart',API],check=True,timeout=30)
        assert api('/api/health')['ok']
        assert service(BROKER) == m['broker']
        assert authority() == m['authority'] and listeners() == m['listeners']
        assert len(api('/api/policy-templates')['catalog']) == 27
        shutil.copytree(release/'frontend/dist',STATE/'ui',dirs_exist_ok=True)
        assert sha(STATE/'ui/index.html') == sha(release/'frontend/dist/index.html')
        result.update(published=True,restart_seconds=round(time.monotonic()-started,3),broker_unchanged=True,authority_unchanged=True,
                      other_ports_unchanged=True,dsh_files_unchanged=files(Path(m['api']['WorkingDirectory'])/'dsh')==m['dsh_files'],api=service(API),ui_sha256=sha(STATE/'ui/index.html'))
    except BaseException:
        if m['old_drop'] is None:DROP.unlink(missing_ok=True)
        else:DROP.write_text(m['old_drop'])
        shutil.copytree(backup/'ui',STATE/'ui',dirs_exist_ok=True)
        subprocess.run(['systemctl','daemon-reload'],check=True)
        subprocess.run(['systemctl','restart',API],check=True,timeout=30)
        result['code_ui_rolled_back'] = True
        raise
    finally:
        result['finished_at'] = time.time()
        report = backup/'result.json';report.write_text(json.dumps(result,indent=2));report.chmod(0o600)
        print(json.dumps({'published':result['published'],'evidence':str(report)}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--stage',action='store_true');group.add_argument('--apply')
    options=parser.parse_args();stage() if options.stage else apply(options.apply)

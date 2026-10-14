#!/usr/bin/env python3
"""Publish policy lifecycle controls and session names to 18003, preserving Broker and authority."""
import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path
from deploy_policy_semantics import authority, guard, service, listeners, files, sha, api

SOURCE = Path(__file__).resolve().parents[1]
STATE = Path('/var/lib/agentscope-scope-demo')
API = 'agentscope-scope-demo-api.service'
BROKER = 'agentscope-scope-demo-broker.service'
DROP = Path('/etc/systemd/system/' + API + '.d/99zzzz-policy-lifecycle-20261014.conf')
BASE = 'd66605e'


def idle():
    guard()
    with sqlite3.connect('file:' + str(STATE / 'demo.sqlite3') + '?mode=ro', uri=True) as con:
        assert not con.execute("SELECT 1 FROM managed_tasks WHERE json_extract(state_json,'$.phase') IN ('running','starting')").fetchone(), 'Managed task is busy'


def stage():
    assert os.geteuid() == 0
    idle()
    before = service(API)
    broker = service(BROKER)
    live = Path(before['WorkingDirectory'])
    broker_root = Path(broker['WorkingDirectory'])
    assert live.parent == broker_root.parent == Path('/opt')
    # The integrated base contains the deployed API contract. Refuse concurrent overlays.
    paths = subprocess.check_output(['git', '-c', 'safe.directory=' + str(SOURCE), '-C', str(SOURCE), 'ls-tree', '-r', '--name-only', BASE, 'backend/agentscope_app'], text=True).splitlines()
    for relative in paths:
        prior = subprocess.check_output(['git', '-c', 'safe.directory=' + str(SOURCE), '-C', str(SOURCE), 'show', BASE + ':' + relative])
        assert (live / relative).read_bytes() == prior, 'Live baseline changed: ' + relative
    assert files(SOURCE / 'backend/broker') == files(broker_root / 'backend/broker'), 'Broker source changed'
    for name in ('scope_service.py', 'scope_systemd_exec.py', 'rq5_service.py'):
        assert sha(SOURCE / 'scripts' / name) == sha(live / 'scripts' / name)
    release = Path('/opt/agentscope-policy-lifecycle-' + time.strftime('%Y%m%d-%H%M%S'))
    assert not release.exists()
    release.mkdir(mode=0o755)
    for folder in ('backend', 'scripts', 'integrations', 'bin', 'dsh'):
        if (live / folder).exists():
            shutil.copytree(live / folder, release / folder, symlinks=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(SOURCE / 'backend/agentscope_app', release / 'backend/agentscope_app', dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(broker_root / 'backend/broker', release / 'backend/broker', dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(SOURCE / 'frontend/dist', release / 'frontend/dist')
    subprocess.run(['/opt/agentscope/.venv/bin/python', '-m', 'compileall', '-q', str(release / 'backend/agentscope_app')], check=True)
    manifest = {'release': str(release), 'previous_api': before, 'broker': broker,
                'previous_files': files(live / 'backend/agentscope_app'), 'release_files': files(release),
                'authority': authority(), 'listeners': listeners(),
                'source_commit': subprocess.check_output(['git', '-c', 'safe.directory=' + str(SOURCE), '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip(),
                'source_app': files(SOURCE / 'backend/agentscope_app'),
                'previous_drop': DROP.read_text() if DROP.exists() else None}
    path = release / 'policy-lifecycle-deployment.json'
    path.write_text(json.dumps(manifest, indent=2))
    path.chmod(0o600)
    print(json.dumps({'staged': str(release), 'manifest': str(path)}))


def apply(path):
    assert os.geteuid() == 0
    manifest_path = Path(path)
    m = json.loads(manifest_path.read_text())
    release = Path(m['release'])
    assert release.parent == Path('/opt') and release.name.startswith('agentscope-policy-lifecycle-')
    assert manifest_path == release / 'policy-lifecycle-deployment.json'
    assert {k: v for k, v in files(release).items() if k != manifest_path.name} == m['release_files']
    assert (DROP.read_text() if DROP.exists() else None) == m['previous_drop']
    assert service(API) == m['previous_api'] and service(BROKER) == m['broker']
    assert files(Path(m['previous_api']['WorkingDirectory']) / 'backend/agentscope_app') == m['previous_files']
    idle()
    assert authority() == m['authority'] and listeners() == m['listeners']
    backup = STATE / 'release-backups' / release.name
    backup.mkdir(parents=True, mode=0o700)
    shutil.copytree(STATE / 'ui', backup / 'ui')
    with sqlite3.connect(STATE / 'demo.sqlite3') as src, sqlite3.connect(backup / 'demo.sqlite3') as dst:
        src.backup(dst)
    (backup / 'demo.sqlite3').chmod(0o600)
    result = {'release': str(release), 'source_commit': m['source_commit'], 'started_at': time.time(),
              'previous_api': m['previous_api'], 'authority_before': m['authority'], 'published': False}
    try:
        # Preserve cached hashed assets while replacing the entry document.
        shutil.copytree(release / 'frontend/dist', STATE / 'ui', dirs_exist_ok=True)
        DROP.write_text('[Service]\nTimeoutStopSec=3\nWorkingDirectory=' + str(release) + '\nExecStart=\nExecStart=/opt/agentscope/.venv/bin/python ' + str(release) + '/scripts/scope_systemd_exec.py api\nExecStartPost=\nExecStartPost=/opt/agentscope/.venv/bin/python ' + str(release) + '/scripts/scope_systemd_exec.py api-ready\n')
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        started = time.monotonic()
        subprocess.run(['systemctl', 'restart', API], check=True, timeout=30)
        assert api('/api/health')['ok']
        assert service(BROKER) == m['broker'], 'Broker identity changed'
        assert authority() == m['authority'], 'Authority changed during API publication'
        assert listeners() == m['listeners'], 'Other console listener changed'
        assert sha(STATE / 'ui/index.html') == sha(release / 'frontend/dist/index.html')
        result.update(published=True, restart_seconds=round(time.monotonic() - started, 3),
                      authority_after=authority(), broker_unchanged=True, other_ports_unchanged=True,
                      current_api=service(API), ui_sha256=sha(STATE / 'ui/index.html'))
    except BaseException as error:
        result['error'] = str(error)[:800]
        # Keep new database facts; rollback only code and the entry/UI.
        if m['previous_drop'] is None:
            DROP.unlink(missing_ok=True)
        else:
            DROP.write_text(m['previous_drop'])
        shutil.copytree(backup / 'ui', STATE / 'ui', dirs_exist_ok=True)
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'restart', API], check=True, timeout=30)
        result['code_ui_rolled_back'] = True
        raise
    finally:
        result['finished_at'] = time.time()
        report = backup / 'result.json'
        report.write_text(json.dumps(result, indent=2))
        report.chmod(0o600)
        print(json.dumps({'published': result['published'], 'evidence': str(report)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--stage', action='store_true')
    group.add_argument('--apply')
    options = parser.parse_args()
    stage() if options.stage else apply(options.apply)

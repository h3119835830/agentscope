#!/usr/bin/env python3
"""Publish the reviewed preflight/runtime API and UI without restarting Broker."""
import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

from deploy_policy_semantics import api, authority, files, guard, listeners, service, sha

SOURCE = Path(__file__).resolve().parents[1]
STATE = Path('/var/lib/agentscope-scope-demo')
API = 'agentscope-scope-demo-api.service'
BROKER = 'agentscope-scope-demo-broker.service'
DROP = Path('/etc/systemd/system/' + API + '.d/zzzzzzzzz-preflight-runtime-20261020.conf')


def git(*args):
    return subprocess.check_output(['git', '-c', 'safe.directory=' + str(SOURCE), '-C', str(SOURCE), *args], text=True).strip()


def stage():
    assert os.geteuid() == 0
    assert not git('status', '--porcelain'), 'Commit the reviewed source before staging'
    assert all(path == DROP or path.name < DROP.name for path in DROP.parent.glob('*.conf')), 'Deployment drop-in would not be authoritative'
    guard()
    before = service(API)
    broker = service(BROKER)
    live = Path(before['WorkingDirectory'])
    assert live.parent == Path('/opt')
    release = Path('/opt/agentscope-preflight-runtime-' + time.strftime('%Y%m%d-%H%M%S'))
    assert not release.exists()
    release.mkdir(mode=0o755)
    for folder in ('backend', 'scripts', 'integrations', 'bin', 'dsh'):
        if (live / folder).exists():
            shutil.copytree(live / folder, release / folder, symlinks=True,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(SOURCE / 'backend/agentscope_app', release / 'backend/agentscope_app',
                    dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(SOURCE / 'frontend/dist', release / 'frontend/dist')
    subprocess.run(['/opt/agentscope/.venv/bin/python', '-m', 'compileall', '-q',
                    str(release / 'backend/agentscope_app')], check=True)
    manifest = {
        'release': str(release), 'source_commit': git('rev-parse', 'HEAD'),
        'previous_api': before, 'broker': broker,
        'previous_files': files(live / 'backend/agentscope_app'),
        'release_files': files(release), 'authority': authority(),
        'listeners': listeners(), 'previous_drop': DROP.read_text() if DROP.exists() else None,
    }
    path = release / 'preflight-runtime-deployment.json'
    path.write_text(json.dumps(manifest, indent=2))
    path.chmod(0o600)
    print(json.dumps({'staged': str(release), 'manifest': str(path)}))


def apply(path):
    assert os.geteuid() == 0
    manifest_path = Path(path)
    manifest = json.loads(manifest_path.read_text())
    release = Path(manifest['release'])
    previous = Path(manifest['previous_api']['WorkingDirectory'])
    assert release.parent == Path('/opt') and release.name.startswith('agentscope-preflight-runtime-')
    assert manifest_path == release / 'preflight-runtime-deployment.json'
    assert {k: v for k, v in files(release).items() if k != manifest_path.name} == manifest['release_files']
    assert service(API) == manifest['previous_api'] and service(BROKER) == manifest['broker']
    assert files(previous / 'backend/agentscope_app') == manifest['previous_files']
    assert (DROP.read_text() if DROP.exists() else None) == manifest['previous_drop']
    guard()
    assert authority() == manifest['authority'] and listeners() == manifest['listeners']
    backup = STATE / 'release-backups' / release.name
    backup.mkdir(parents=True, mode=0o700)
    shutil.copytree(STATE / 'ui', backup / 'ui')
    with sqlite3.connect(STATE / 'demo.sqlite3') as source, sqlite3.connect(backup / 'demo.sqlite3') as target:
        source.backup(target)
    (backup / 'demo.sqlite3').chmod(0o600)
    result = {'published': False, 'release': str(release), 'source_commit': manifest['source_commit'],
              'previous_api': manifest['previous_api'], 'authority_before': manifest['authority'],
              'broker_restart': False, 'agent_actions': False, 'policy_application': False}
    try:
        DROP.write_text('[Service]\nTimeoutStopSec=3\nWorkingDirectory=' + str(release) +
                        '\nExecStart=\nExecStart=/opt/agentscope/.venv/bin/python ' +
                        str(release) + '/scripts/scope_systemd_exec.py api\nExecStartPost=\nExecStartPost=/opt/agentscope/.venv/bin/python ' +
                        str(release) + '/scripts/scope_systemd_exec.py api-ready\n')
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        started = time.monotonic()
        subprocess.run(['systemctl', 'restart', API], check=True, timeout=30)
        assert api('/api/health')['ok']
        assert service(BROKER) == manifest['broker'], 'Broker identity changed'
        assert authority() == manifest['authority'], 'Agent authority changed'
        assert listeners() == manifest['listeners'], 'Unrelated listeners changed'
        agents = api('/api/agent-instances')['instances']
        controlled = next((row for row in agents if row.get('mode') == 'controlled'), None)
        if controlled:
            loaded = api('/api/console/agents/' + controlled['id'] + '/loaded-policies')
            assert loaded.get('schema') == 'SessionLoadedPolicies/1'
        shutil.copytree(release / 'frontend/dist', STATE / 'ui', dirs_exist_ok=True)
        assert sha(STATE / 'ui/index.html') == sha(release / 'frontend/dist/index.html')
        result.update(published=True, restart_seconds=round(time.monotonic() - started, 3),
                      current_api=service(API), broker_unchanged=True, authority_unchanged=True,
                      other_ports_unchanged=True, ui_sha256=sha(STATE / 'ui/index.html'))
    except BaseException as error:
        result['error'] = str(error)[:800]
        if manifest['previous_drop'] is None:
            DROP.unlink(missing_ok=True)
        else:
            DROP.write_text(manifest['previous_drop'])
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

#!/usr/bin/env python3
"""API-only immutable overlay; preserve Broker, Agent authority and concurrent UI."""
import argparse
import grp
import importlib.util
import json
import os
from pathlib import Path
import pwd
import shutil
import sqlite3
import subprocess
import tempfile
import time
from deploy_policy_semantics import api, authority, files, listeners, service, sha
from deploy_policy_context_agent import idle, protected

ROOT = Path(__file__).resolve().parents[1]
STATE = Path('/var/lib/agentscope-scope-demo')
API = 'agentscope-scope-demo-api.service'
BROKER = 'agentscope-scope-demo-broker.service'
DROP = Path('/etc/systemd/system/'+API+'.d/zzzzzzzzzz-pi-reader-20261020.conf')
BASE = '151d39d'
OVERLAY = (
    'backend/agentscope_app/instances/workspace_references.py',
    'backend/agentscope_app/instances/policy_context_agent.py',
    'backend/reference_file_reader.py',
    'backend/reference_reader_channel.py',
    'scripts/scope_systemd_exec.py',
)
MANIFEST = 'pi-reader-deployment.json'
PYTHON = '/opt/agentscope/.venv/bin/python'


def git(*args):
    return subprocess.check_output(['git', '-c', 'safe.directory='+str(ROOT), '-C', str(ROOT), *args])


def identity(pid):
    status = Path('/proc', str(pid), 'status').read_text().splitlines()
    return {key: next(line.split(':', 1)[1].strip() for line in status if line.startswith(key+':'))
            for key in ('Uid', 'Gid', 'Groups', 'CapEff', 'NoNewPrivs')}


def smoke(release):
    """Installed API wrapper, real API identity, fixed reader, synthetic files."""
    spec = importlib.util.spec_from_file_location('installed_reader_channel', release/'backend/reference_reader_channel.py')
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    user = pwd.getpwnam('agentscope-api');reader = pwd.getpwnam('happy')
    group = grp.getgrnam('agentscope-task').gr_gid
    with tempfile.TemporaryDirectory(prefix='pi-reader-release-') as temporary:
        root = Path(temporary);root.chmod(0o755)
        allowed = root/'allowed.md';allowed.write_text('synthetic release read')
        os.chown(allowed, reader.pw_uid, group);allowed.chmod(0o600)
        denied = root/'denied.md';denied.write_text('synthetic root only');denied.chmod(0o600)
        connection, worker = module.launch(PYTHON, reader.pw_uid, group)
        try:
            code = '''
import json,os,sys
sys.path.insert(0,sys.argv[1])
from agentscope_app.instances import workspace_references as refs
root=sys.argv[2];uid,gid=refs.reader_identity()
try:open(root+'/allowed.md')
except PermissionError:pass
else:raise AssertionError('API DAC unexpectedly expanded')
assert refs.run_reader({'root':root,'paths':['allowed.md']},uid,gid)['files'][0]['text']=='synthetic release read'
try:refs.run_reader({'root':root,'paths':['denied.md']},uid,gid)
except ValueError:pass
else:raise AssertionError('root-only fixture accepted')
assert refs.run_reader({'operation':'list','root':root},uid,gid)['entries']
print(json.dumps({'api_uid':os.geteuid(),'api_gid':os.getegid(),'groups':os.getgroups(),'reader':refs.READER_CHANNEL.identity,'allowed':True,'denied':True}))
'''
            result = subprocess.run([PYTHON, '-I', '-c', code, str(release/'backend'), temporary],
                user=user.pw_uid, group=user.pw_gid, extra_groups=[user.pw_gid, group],
                pass_fds=(connection.fileno(),), env={module.FD_ENV: str(connection.fileno()), 'LANG': 'C.UTF-8'},
                capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, 'Installed wrapper identity smoke failed: '+result.stderr
            return json.loads(result.stdout)
        finally:
            connection.close();worker.wait(timeout=5)


def stage():
    assert os.geteuid() == 0
    idle()
    assert not git('status', '--porcelain').strip(), 'Commit reviewed source before deployment'
    assert not git('diff', 'a182291', '--', 'actplane').strip(), 'ActPlane boundary changed'
    before = service(API);broker = service(BROKER);live = Path(before['WorkingDirectory'])
    assert live.parent == Path('/opt') and not DROP.exists()
    for name in OVERLAY:
        if name.endswith('reference_reader_channel.py'):
            assert not (live/name).exists()
        else:
            import hashlib
            assert sha(live/name) == hashlib.sha256(git('show', BASE+':'+name)).hexdigest(), 'Live source drift: '+name
    release = Path('/opt/agentscope-pi-reader-'+time.strftime('%Y%m%d-%H%M%S'))
    release.mkdir(mode=0o755)
    for directory in ('backend', 'scripts', 'integrations', 'bin', 'dsh'):
        if (live/directory).exists():
            shutil.copytree(live/directory, release/directory, symlinks=True,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in OVERLAY:
        shutil.copyfile(ROOT/name, release/name);(release/name).chmod(0o644)
    for directory in ('backend/broker', 'integrations', 'bin', 'dsh'):
        if (live/directory).exists():
            assert files(live/directory) == files(release/directory), 'Execution bytes changed'
    proof = smoke(release)
    manifest = {'release':str(release), 'api':before, 'broker':broker, 'authority':authority(),
        'protected':protected(), 'listeners':listeners(), 'ui':files(STATE/'ui'),
        'api_identity':identity(before['MainPID']), 'smoke':proof, 'release_files':files(release),
        'live_overlay':{name:sha(live/name) for name in OVERLAY if (live/name).exists()},
        'commit':git('rev-parse','HEAD').decode().strip()}
    path = release/MANIFEST;path.write_text(json.dumps(manifest, indent=2));path.chmod(0o600)
    print(json.dumps({'staged':str(path), 'identity_smoke':proof}, ensure_ascii=False))


def apply(path):
    assert os.geteuid() == 0
    manifest_path = Path(path);m = json.loads(manifest_path.read_text())
    release = Path(m['release']);live = Path(m['api']['WorkingDirectory'])
    assert release.parent == Path('/opt') and release.name.startswith('agentscope-pi-reader-') and manifest_path == release/MANIFEST
    assert not DROP.exists()
    assert {k:v for k,v in files(release).items() if k != MANIFEST} == m['release_files']
    assert service(API) == m['api'] and service(BROKER) == m['broker']
    assert all(sha(live/name) == value for name,value in m['live_overlay'].items())
    idle()
    assert authority() == m['authority'] and protected() == m['protected']
    assert listeners() == m['listeners'] and files(STATE/'ui') == m['ui']
    backup = STATE/'release-backups'/release.name;backup.mkdir(mode=0o700, parents=True)
    with sqlite3.connect(STATE/'demo.sqlite3') as source, sqlite3.connect(backup/'demo.sqlite3') as destination:
        source.backup(destination)
    (backup/'demo.sqlite3').chmod(0o600)
    result = {'published':False, 'commit':m['commit'], 'release':str(release)}
    try:
        DROP.write_text('[Service]\nTimeoutStopSec=3\nWorkingDirectory='+str(release)+
            '\nExecStart=\nExecStart='+PYTHON+' '+str(release)+'/scripts/scope_systemd_exec.py api\n'+
            'ExecStartPost=\nExecStartPost='+PYTHON+' '+str(release)+'/scripts/scope_systemd_exec.py api-ready\n')
        subprocess.run(['systemctl','daemon-reload'],check=True)
        started = time.monotonic()
        subprocess.run(['systemctl','restart',API],check=True,timeout=30)
        assert api('/api/health')['ok']
        assert service(BROKER) == m['broker']
        assert authority() == m['authority'] and protected() == m['protected']
        assert listeners() == m['listeners'] and files(STATE/'ui') == m['ui']
        current = service(API);assert identity(current['MainPID']) == m['api_identity']
        children = Path('/proc',current['MainPID'],'task',current['MainPID'],'children').read_text().split()
        workers = [pid for pid in children if b'reference_reader_channel.py' in Path('/proc',pid,'cmdline').read_bytes()]
        assert len(workers) == 1
        worker_identity = identity(workers[0])
        assert worker_identity['Groups'] == '' and worker_identity['CapEff'] == '0000000000000000' and worker_identity['NoNewPrivs'] == '1'
        result.update(published=True, seconds=round(time.monotonic()-started,3), api=current,
            api_identity=identity(current['MainPID']), reader_pid=workers[0], reader_identity=worker_identity,
            broker_unchanged=True, agent_bindings_unchanged=True, authority_unchanged=True,
            ui_unchanged=True, other_listeners_unchanged=True)
    except BaseException:
        # Recover code pointer only; never restore DB over user actions.
        if DROP.exists():DROP.unlink()
        subprocess.run(['systemctl','daemon-reload'],check=True)
        subprocess.run(['systemctl','restart',API],check=True,timeout=30)
        result['code_pointer_rolled_back'] = True
        raise
    finally:
        report = backup/'result.json';report.write_text(json.dumps(result,indent=2));report.chmod(0o600)
        print(json.dumps({'published':result['published'], 'report':str(report)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser();group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--stage',action='store_true');group.add_argument('--apply')
    options = parser.parse_args()
    stage() if options.stage else apply(options.apply)

"""Guarded local 18003 maintenance; never approve policy or restore Agents."""
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

from deploy_reference_reader import ROOT, STATE, API, BROKER, PYTHON, git, identity, smoke
from deploy_policy_semantics import files, listeners, service, sha

FEATURE = '2d82216412c85d9e6e14dfd38898c1ba0939b524'
# The live Broker predates the already reviewed root-owned short monitor socket.
# Exact bytes were checked in both deployed trees; never accept arbitrary drift.
LIVE_BASES = {'backend/broker/instance_runtime.py': '3c3d36837f52f22135524ebbb0a2f338f809fc3c'}
NATIVE = '5e8d43c279d88bd4215f654746675debfd976e28426c9fabdabeca408865d6da'
PREFIX = 'agentscope-resource-views-'
MANIFEST = 'resource-views-deployment.json'
DROP_NAME = 'zzzzzzzzzzzzzzzz-resource-views-20261021.conf'
DROPS = {unit: Path('/etc/systemd/system') / (unit + '.d') / DROP_NAME for unit in (API, BROKER)}
CGROUP = Path('/sys/fs/cgroup/agentscope-scope-demo')
RUNTIME = Path('/run/agentscope-scope-demo/instances')
ADAPTER = 'backend/dsl-adapter/target/release/agentscope-dsl-adapter'
PROTECTED_TABLES = (
    'instance_local_policies', 'system_security_policy', 'instance_dsl_scopes', 'instance_proposals',
    'instance_dsl_proposals', 'system_security_proposals', 'policy_approval_decisions', 'instance_launch_configs',
    'instance_proposal_locals', 'instance_proposal_contexts', 'policy_approval_baselines', 'local_policy_proposals',
    'policy_application_requests', 'policy_drafts', 'policy_draft_versions', 'template_configurations',
    'template_configuration_versions', 'template_configuration_requests', 'template_configuration_proposals',
    'template_workspace_reads', 'policy_template_versions', 'label_sources', 'label_source_versions',
    'label_source_requests', 'system_policy_library', 'system_policy_library_versions', 'agent_policy_scenes',
    'agent_workspaces', 'instance_session_display_names', 'instance_session_task_bindings')
RETAINED_TABLES = ('instance_events', 'instance_kernel_events', 'audit_log', 'agent_messages',
                   'history_jobs', 'history_generations', 'bootstrap_tool_events')
BUSY_QUERIES = (
    "SELECT 1 FROM history_jobs WHERE status IN ('queued','running')",
    "SELECT 1 FROM instance_dsl_scopes WHERE phase!='ready'",
    'SELECT 1 FROM instance_leases',
    "SELECT 1 FROM instance_dsl_proposals WHERE state='applying'",
    "SELECT 1 FROM agent_instances WHERE gate IN ('starting','updating')",
    "SELECT 1 FROM managed_tasks WHERE json_extract(state_json,'$.phase') IN ('running','starting')",
    "SELECT 1 FROM system_security_policy WHERE phase!='ready'",
    "SELECT 1 FROM template_configuration_requests WHERE state='running'",
    "SELECT 1 FROM managed_jobs WHERE status IN ('queued','running')",
    "SELECT 1 FROM scope_jobs WHERE status IN ('queued','running')",
    "SELECT 1 FROM policy_approval_decisions WHERE state IN ('applying','pause_unverified')",
    "SELECT 1 FROM policy_application_requests WHERE state IN ('running','applying')")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def database():
    return sqlite3.connect('file:' + str(STATE / 'demo.sqlite3') + '?mode=ro', uri=True)


def authority_hashes():
    with database() as con:
        result = {}
        for table in ('agent_instances', *PROTECTED_TABLES):
            columns = 'id,name,agent_type,environment,mode,resources_json,policy_json,policy_hash' if table == 'agent_instances' else '*'
            rows = sorted(con.execute('SELECT ' + columns + ' FROM ' + table).fetchall(), key=repr)
            result[table] = {'count': len(rows), 'sha256': digest(rows)}
        return result


def retained_hashes():
    with database() as con:
        return {table: sorted(digest(row) for row in con.execute('SELECT * FROM ' + table))
                for table in RETAINED_TABLES}


def verify_retained(before, after):
    for table, rows in before.items():
        require(set(rows) <= set(after[table]), 'Historical records changed or removed: ' + table)


def execution_inventory():
    manifests = []
    for path in sorted(RUNTIME.glob('instance-*/manifest.json')):
        info = path.lstat()
        require(not path.is_symlink() and info.st_uid == 0 and not info.st_mode & 0o077,
                'Untrusted execution manifest')
        row = json.loads(path.read_text())
        manifests.append({k: row.get(k) for k in ('instance_id', 'generation', 'process_cgroup')})
    processes = {str(path.relative_to(CGROUP)): path.read_text().split()
                 for path in CGROUP.rglob('cgroup.procs') if path.read_text().strip()}
    return {'manifests': manifests, 'processes': processes}


def idle():
    with database() as con:
        for query in BUSY_QUERIES:
            require(con.execute(query).fetchone() is None, 'In-flight work; postpone maintenance: ' + query)
    # This one-shot release intentionally requires an empty execution plane.
    # A stale DB gate is never evidence of a live Agent, nor authority to restore one.
    inventory = execution_inventory()
    require(not inventory['manifests'] and not inventory['processes'],
            'Live managed execution requires a separately verified quiescence before this release')


def health():
    with urllib.request.urlopen('http://127.0.0.1:18003/api/health', timeout=10) as response:
        require(response.status == 200 and json.load(response).get('ok'), 'API health failed')


def native_hash():
    value = sha(STATE / 'bin/actplane')
    require(value == NATIVE, 'Native engine differs from the reviewed unchanged binary')
    return value


def overlay_names():
    return [name for name in git('diff-tree', '--no-commit-id', '--name-only', '-r', FEATURE).decode().splitlines()
            if name.startswith('backend/') and not name.startswith(('backend/tests/', 'backend/dsl-adapter/'))]


def source_gate(live):
    require(not git('status', '--porcelain').strip(), 'Commit reviewed source before staging')
    require(not git('diff', '--exit-code', 'a182291', '--', 'actplane').strip(), 'Native tree changed')
    names = overlay_names()
    added = git('diff-tree', '--no-commit-id', '--diff-filter=A', '--name-only', '-r', FEATURE).decode().splitlines()
    for name in names:
        require(sha(ROOT / name) == hashlib.sha256(git('show', FEATURE + ':' + name)).hexdigest(),
                'Feature source changed: ' + name)
        if name in added:
            require(not (live / name).exists(), 'New file already exists in live release: ' + name)
        else:
            baseline = LIVE_BASES.get(name, FEATURE + '^')
            require(sha(live / name) == hashlib.sha256(git('show', baseline + ':' + name)).hexdigest(),
                    'Live baseline drift: ' + name)
    # No unrelated Python, launcher or integration changes are shipped.
    for name in git('ls-files', 'backend', 'scripts/scope_service.py', 'scripts/scope_systemd_exec.py',
                    'scripts/rq5_service.py', 'integrations').decode().splitlines():
        if name in names or name.startswith(('backend/tests/', 'backend/dsl-adapter/')):
            continue
        require((live / name).is_file() and sha(ROOT / name) == sha(live / name), 'Unrelated source drift: ' + name)
    return names


def drop_text(unit, release):
    require(unit in DROPS, 'Only 18003 units may be changed')
    role = 'api' if unit == API else 'broker'
    timeout = '3' if role == 'api' else '8'
    return ('[Service]\nTimeoutStopSec=' + timeout + '\nWorkingDirectory=' + str(release) +
            '\nExecStart=\nExecStart=' + PYTHON + ' ' + str(release) + '/scripts/scope_systemd_exec.py ' + role +
            '\nExecStartPost=\nExecStartPost=' + PYTHON + ' ' + str(release) + '/scripts/scope_systemd_exec.py ' + role + '-ready\n')


def write_private(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as out:
        json.dump(value, out, indent=2)


def stage():
    require(os.geteuid() == 0, 'Root maintenance context required')
    require(all(not path.exists() for path in DROPS.values()), 'Deployment drop-in already exists')
    idle()
    current = {unit: service(unit) for unit in DROPS}
    live = Path(current[API]['WorkingDirectory'])
    require(live.parent == Path('/opt'), 'Unexpected deployment source')
    names = source_gate(live)
    native_hash()
    release = Path('/opt') / (PREFIX + time.strftime('%Y%m%d-%H%M%S'))
    release.mkdir(mode=0o755)
    for folder in ('backend', 'scripts', 'integrations', 'bin', 'dsh'):
        if (live / folder).exists():
            shutil.copytree(live / folder, release / folder, symlinks=True,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in names:
        shutil.copyfile(ROOT / name, release / name)
        (release / name).chmod(0o644)
    (release / ADAPTER).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / ADAPTER, release / ADAPTER)
    (release / ADAPTER).chmod(0o755)
    shutil.copytree(ROOT / 'frontend/dist', release / 'frontend/dist')
    for folder in ('integrations', 'bin', 'dsh'):
        if (live / folder).exists():
            require(files(live / folder) == files(release / folder), 'Unrelated runtime bytes changed')
    subprocess.run([PYTHON, '-m', 'compileall', '-q', str(release / 'backend')], check=True)
    proof = smoke(release)
    m = {'release': str(release), 'feature_commit': FEATURE, 'source_commit': git('rev-parse', 'HEAD').decode().strip(),
         'services': current, 'api_identity': identity(current[API]['MainPID']),
         'authority': authority_hashes(), 'retained': retained_hashes(), 'execution': execution_inventory(),
         'listeners': listeners(), 'ui': files(STATE / 'ui'), 'native_sha256': native_hash(),
         'live_backend': {unit: files(Path(s['WorkingDirectory']) / 'backend') for unit, s in current.items()},
         'overlay': names, 'reader_smoke': proof, 'release_files': files(release)}
    write_private(release / MANIFEST, m)
    print(json.dumps({'staged': str(release / MANIFEST), 'reader_smoke': proof, 'execution': m['execution']}))


def publish_static(release):
    source = release / 'frontend/dist'
    for name, value in files(source).items():
        if name in ('index.html', 'terminal.html'):
            continue
        target = STATE / 'ui' / name
        if target.exists():
            require(sha(target) == value, 'Immutable asset name collision: ' + name)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, target)
    for name in ('index.html', 'terminal.html'):
        temporary = STATE / 'ui' / ('.' + name + '.resource-views')
        shutil.copyfile(source / name, temporary)
        os.replace(temporary, STATE / 'ui' / name)


def run_systemctl(*args):
    subprocess.run(['systemctl', *args], check=True, timeout=45)


def verify_release(m, release):
    health()
    current = {unit: service(unit) for unit in DROPS}
    require(all(row['WorkingDirectory'] == str(release) for row in current.values()), 'Release pointer mismatch')
    for row in current.values():
        environment = dict(item.split(b'=', 1) for item in Path('/proc', row['MainPID'], 'environ').read_bytes().split(b'\0') if b'=' in item)
        expected = {b'ACTPLANE_BIN': str(STATE / 'bin/actplane'),
                    b'AGENTSCOPE_DB': str(STATE / 'demo.sqlite3'),
                    b'AGENTSCOPE_RUNTIME_DIR': '/run/agentscope-scope-demo',
                    b'AGENTSCOPE_TASK_ROOT': '/s', b'AGENTSCOPE_RUNNER': str(release / 'backend/broker/task_runner.py')}
        require(all(environment.get(key) == value.encode() for key, value in expected.items()), 'Runtime profile mismatch')
        require(environment.get(b'AGENTSCOPE_DSL_ADAPTER', str(release / ADAPTER).encode()) == str(release / ADAPTER).encode(),
                'Unexpected DSL adapter override')
    require(identity(current[API]['MainPID']) == m['api_identity'], 'API identity changed')
    require(native_hash() == m['native_sha256'], 'Native engine changed')
    require(authority_hashes() == m['authority'], 'Policy/resource/approval state changed')
    verify_retained(m['retained'], retained_hashes())
    require(listeners() == m['listeners'], 'Other listeners changed')
    idle()
    pid = current[API]['MainPID']
    children = Path('/proc', pid, 'task', pid, 'children').read_text().split()
    workers = [child for child in children if b'reference_reader_channel.py' in Path('/proc', child, 'cmdline').read_bytes()]
    require(len(workers) == 1, 'Missing fixed reader')
    worker = identity(workers[0])
    require(worker['Groups'] == '' and worker['CapEff'] == '0000000000000000' and worker['NoNewPrivs'] == '1',
            'Reader security boundary changed')
    require(worker['Uid'].split() == [str(m['reader_smoke']['reader']['uid'])] * 4, 'Reader UID changed')
    return {'services': current, 'api_identity': identity(pid), 'reader_identity': worker,
            'reader_smoke': smoke(release), 'authority_preserved': True, 'historical_rows_preserved': True,
            'other_listeners_unchanged': True, 'native_sha256': native_hash(), 'restored_agents': []}


def apply(path):
    require(os.geteuid() == 0, 'Root maintenance context required')
    manifest_path = Path(path)
    require(manifest_path.name == MANIFEST and manifest_path.parent.parent == Path('/opt') and
            manifest_path.parent.name.startswith(PREFIX) and not manifest_path.is_symlink(), 'Unexpected manifest path')
    m = json.loads(manifest_path.read_text())
    release = manifest_path.parent
    require(m['release'] == str(release) and manifest_path.stat().st_uid == 0 and
            not manifest_path.stat().st_mode & 0o077, 'Untrusted deployment manifest')
    require(all(not path.exists() for path in DROPS.values()), 'Deployment drop-in already exists')
    require({k: v for k, v in files(release).items() if k != MANIFEST} == m['release_files'], 'Staged bytes changed')
    for unit in DROPS:
        require(service(unit) == m['services'][unit], 'Service drift since staging')
        require(files(Path(m['services'][unit]['WorkingDirectory']) / 'backend') == m['live_backend'][unit], 'Live code changed')
    idle()
    require(authority_hashes() == m['authority'] and listeners() == m['listeners'] and files(STATE / 'ui') == m['ui'],
            'State drift since staging')
    native_hash()
    backup = STATE / 'release-backups' / release.name
    backup.mkdir(parents=True, mode=0o700)
    shutil.copytree(STATE / 'ui', backup / 'ui')
    with database() as source, sqlite3.connect(backup / 'demo.sqlite3') as target:
        source.backup(target)
    (backup / 'demo.sqlite3').chmod(0o600)
    result = {'published': False, 'feature_commit': FEATURE, 'source_commit': m['source_commit'],
              'release': str(release), 'restored_agents': [], 'browser_acceptance': 'blocked_by_tool_access_policy'}
    switch(m, release, backup, result)


def switch(m, release, backup, result):
    """Testable pointer switch. No database restore and no Agent start on either path."""
    started = time.monotonic()
    try:
        run_systemctl('stop', API)
        run_systemctl('stop', BROKER)
        idle()
        for unit, drop in DROPS.items():
            with drop.open('x') as output:
                output.write(drop_text(unit, release))
        run_systemctl('daemon-reload')
        run_systemctl('start', BROKER)
        run_systemctl('start', API)
        result.update(verify_release(m, release))
        publish_static(release)
        require(all(sha(STATE / 'ui' / name) == value for name, value in files(release / 'frontend/dist').items()),
                'Static publication mismatch')
        with urllib.request.urlopen('http://127.0.0.1:18003/', timeout=10) as response:
            require(hashlib.sha256(response.read()).hexdigest() == sha(release / 'frontend/dist/index.html'),
                    'HTTP static entry mismatch')
        result.update(published=True, seconds=round(time.monotonic() - started, 3), static_verified=True)
    except BaseException as error:
        result['failure_type'] = type(error).__name__
        # Revert only this release's code/static pointers, never live database or Agents.
        try:
            run_systemctl('stop', API, BROKER)
            for drop in DROPS.values():
                if drop.exists() and str(release) in drop.read_text():
                    drop.unlink()
            for name in ('index.html', 'terminal.html'):
                temporary = STATE / 'ui' / ('.' + name + '.rollback')
                shutil.copyfile(backup / 'ui' / name, temporary)
                os.replace(temporary, STATE / 'ui' / name)
            run_systemctl('daemon-reload')
            run_systemctl('start', BROKER)
            run_systemctl('start', API)
            health()
            result['code_pointers_rolled_back'] = True
        except BaseException as rollback_error:
            result['rollback_failure_type'] = type(rollback_error).__name__
        raise
    finally:
        write_private(backup / 'result.json', result)
        print(json.dumps({'published': result['published'], 'report': str(backup / 'result.json')}))


def inspect():
    assert os.geteuid() == 0
    with database() as con:
        agents = [dict(zip(('id', 'name', 'mode', 'gate', 'generation', 'policy_hash'), row))
                  for row in con.execute('SELECT id,name,mode,gate,generation,policy_hash FROM agent_instances')]
    live = {unit: service(unit) for unit in (API, BROKER)}
    runtime = Path('/run/agentscope-scope-demo/instances')
    manifests = []
    for path in runtime.glob('instance-*/manifest.json'):
        row = json.loads(path.read_text())
        manifests.append({k: row.get(k) for k in ('instance_id', 'generation', 'process_cgroup', 'policy_hash')})
    comparison = {}
    for unit, current in live.items():
        root = Path(current['WorkingDirectory'])
        prefixes = ('backend/broker/',) if unit == BROKER else ('backend/agentscope_app/',)
        shared = ('backend/dsl_documents.py', 'backend/reference_file_reader.py', 'backend/reference_reader_channel.py',
                  'scripts/scope_service.py', 'scripts/scope_systemd_exec.py', 'scripts/rq5_service.py')
        tracked = git('ls-files').decode().splitlines()
        comparison[unit] = [name for name in tracked if (name.startswith(prefixes) or name in shared)
                            and (not (root / name).exists() or sha(ROOT / name) != sha(root / name))]
    print(json.dumps({'services': live, 'agents': agents, 'managed_manifests': manifests,
                      'different_source_files': comparison, 'other_listeners': listeners(),
                      'native_engine_sha256': sha(STATE / 'bin/actplane')}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--inspect', action='store_true')
    group.add_argument('--stage', action='store_true')
    group.add_argument('--apply')
    args = parser.parse_args()
    if args.inspect:
        inspect()
    elif args.stage:
        stage()
    else:
        apply(args.apply)

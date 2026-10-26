"""Run the deployed native Pi on frozen public scenes, using a separate DB.

No Broker, DSH, public listener, approval, or policy application is invoked.
The root setup establishes the same API/reader identities as the live service;
model execution permanently drops privileges before importing application code.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import grp
import sqlite3
import subprocess
import sys
import time
import urllib.request
import uuid


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def live():
    with urllib.request.urlopen('http://127.0.0.1:18003/api/agent-instances', timeout=10) as response:
        rows = json.load(response)['instances']
    return {'services': {name: subprocess.check_output(['systemctl', 'show', name, '--property=MainPID,ActiveState', '--no-pager'], text=True)
                         for name in ('agentscope-preview.service', 'agentscope-preview-broker.service')},
            'instances': [{k: row.get(k) for k in ('id', 'generation', 'policy_hash', 'resources', 'gate')} |
                          {'pid': row.get('runtime', {}).get('pid')} for row in rows]}


def setup(root, release, supplement=False, followup_file='followups.json'):
    assert os.geteuid() == 0
    if (root / 'state').exists() and not supplement:
        raise ValueError('A baseline run already exists; do not overwrite frozen results')
    # Windows scp creates private directories. The two distinct unprivileged
    # identities need traversal of public fixtures, not access to test state.
    if not supplement:
        root.chmod(0o755)
        for path in [root / 'scenes', *(root / 'scenes').rglob('*')]:
            path.chmod(0o755 if path.is_dir() else 0o644)
    label = Path(followup_file).stem
    before_file = root / ('before-' + label + '.json' if supplement else 'before.json')
    before_file.write_text(json.dumps(live()))
    pid = subprocess.check_output(['systemctl', 'show', 'agentscope-preview.service', '--property=MainPID', '--value'], text=True).strip()
    service_env = dict(item.split(b'=', 1) for item in Path('/proc', pid, 'environ').read_bytes().split(b'\0') if b'=' in item)
    names = ('AGENTSCOPE_HISTORY_LLM_KEY', 'DEEPSEEK_API_KEY', 'AGENTSCOPE_HISTORY_LLM_MODEL',
             'AGENTSCOPE_HISTORY_LLM_URL', 'AGENTSCOPE_POLICY_LLM_KEY_FILE', 'AGENTSCOPE_POLICY_AGENT_PROVIDER',
             'AGENTSCOPE_REFERENCE_READER_USER', 'AGENTSCOPE_REFERENCE_READER_GROUP', 'AGENTSCOPE_REFERENCE_READER_RUNTIME')
    env = {k: v for k, v in os.environ.items() if not k.startswith('AGENTSCOPE_') and k not in ('DEEPSEEK_API_KEY', 'ACTPLANE_BIN', 'DSH_BIN')}
    env.update({name: service_env[name.encode()].decode() for name in names if name.encode() in service_env})
    assert env.get('AGENTSCOPE_POLICY_AGENT_PROVIDER') == 'native-pi'
    api = pwd.getpwnam('agentscope')
    reader = pwd.getpwnam(env['AGENTSCOPE_REFERENCE_READER_USER'])
    group = grp.getgrnam(env['AGENTSCOPE_REFERENCE_READER_GROUP'])
    state = root / 'state'
    out = root / 'results'
    if not supplement:
        state.mkdir(mode=0o700); os.chown(state, api.pw_uid, api.pw_gid)
        out.mkdir(mode=0o700); os.chown(out, api.pw_uid, api.pw_gid)
    # Only public published template definitions are copied, not live history,
    # credentials, runtime state, instances, policies, or a production database.
    with sqlite3.connect('file:/var/lib/agentscope/preview/agentscope.sqlite3?mode=ro', uri=True) as con:
        templates = con.execute('SELECT * FROM policy_template_versions').fetchall()
    (root / 'published-templates.json').write_text(json.dumps(templates))
    env.update(AGENTSCOPE_STATE_DIR=str(state), AGENTSCOPE_RUNTIME_DIR=str(state / 'run'),
               AGENTSCOPE_BROKER_SOCKET=str(state / 'no-broker.sock'), AGENTSCOPE_POLICY_AGENT_PROVIDER='native-pi',
               PYTHONPATH=str(release / 'backend'), ACTPLANE_BIN='/missing/actplane', DSH_BIN='/missing/dsh')
    sys.path.insert(0, str(release / 'backend'))
    from reference_reader_channel import launch, FD_ENV
    os.environ['AGENTSCOPE_REFERENCE_READER_RUNTIME'] = env['AGENTSCOPE_REFERENCE_READER_RUNTIME']
    channel, reader_process = launch('/usr/bin/python3', reader.pw_uid, group.gr_gid)
    env[FD_ENV] = str(channel.fileno())
    command = [sys.executable, str(Path(__file__).resolve()), str(root), '--release', str(release), '--worker']
    if supplement:
        command.extend(['--supplement', '--followup-file', followup_file])
    try:
        completed = subprocess.run(command, env=env, user=api.pw_uid, group=api.pw_gid,
                                   extra_groups=[], pass_fds=(channel.fileno(),), cwd=release)
    finally:
        channel.close()
        reader_process.wait(timeout=10)
    after = live()
    before = json.loads(before_file.read_text())
    unchanged = before == after
    (root / ('isolation-' + label + '.json' if supplement else 'isolation.json')).write_text(json.dumps({'before': before, 'after': after, 'unchanged': unchanged,
                                                   'worker_returncode': completed.returncode}, indent=2))
    assert unchanged, 'Live services/instances changed; report and stop'
    return completed.returncode


def worker(root, release):
    assert os.geteuid() != 0
    from agentscope_app import db
    from agentscope_app.instances import store, template_catalog, template_configurations as configurations
    db.init_db(); store.init()
    with db.connect() as con:
        for row in json.loads((root / 'published-templates.json').read_text()):
            con.execute('INSERT OR REPLACE INTO policy_template_versions VALUES(?,?,?,?,?,?,?)', row)
    manifest = json.loads((root / 'manifest.json').read_text())
    catalog = template_catalog.public_catalog()
    (root / 'results/catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2))
    report = {'schema': 'public-policy-scene-results.v1', 'release': str(release),
              'provider': 'native-pi', 'model': os.environ.get('AGENTSCOPE_HISTORY_LLM_MODEL'),
              'template_catalog_sha256': digest(catalog), 'manifest_sha256': hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest(),
              'identities': {'api_uid': os.geteuid(), 'api_gid': os.getegid(), 'groups': os.getgroups()},
              'agent_started': False, 'policy_applied': False, 'prompt_modified': False, 'templates_modified': False,
              'cases': []}
    for scene in manifest['cases']:
        workspace = root / 'scenes' / scene['id']
        assert hashlib.sha256((workspace / 'scene.md').read_bytes()).hexdigest() == scene['scene_sha256']
        row = store.create(scene['title'], 'dsh', [str(workspace)])
        body = {'scope': 'agent', 'workspace_id': None, 'context_mode': 'auto', 'stage': 'preflight',
                'text': scene['requirements'], 'materials': [], 'request_key': uuid.uuid4().hex}
        entry = {'id': scene['id'], 'requirements': scene['requirements'], 'instance_id': row['id'],
                 'request_key': body['request_key'], 'started_at': db.now()}
        started = time.monotonic()
        try:
            result = configurations.generate(row['id'], body)
            entry.update(status='completed', result=result)
        except Exception as error:
            with db.connect() as con:
                saved = con.execute('SELECT result_json FROM template_configuration_requests WHERE request_key=?', ('generate:' + body['request_key'],)).fetchone()
            entry.update(status='failed', error={'type': type(error).__name__, 'message': str(error)[:1200]},
                         result=json.loads(saved[0]) if saved and saved[0] else None)
        entry['seconds'] = round(time.monotonic() - started, 3)
        final_row = store.get(row['id'])
        assert final_row['gate'] == 'closed' and not final_row['runtime']
        report['cases'].append(entry)
        (root / 'results' / (scene['id'] + '.json')).write_text(json.dumps(entry, ensure_ascii=False, indent=2))
        (root / 'results/report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        result = entry.get('result') or {}
        print(json.dumps({'id': scene['id'], 'status': entry['status'], 'seconds': entry['seconds'],
                          'items': len(result.get('items', [])), 'reads': result.get('context_usage', {}).get('file_count'),
                          'error': entry.get('error')}, ensure_ascii=False), flush=True)
    return 0


def supplement(root, release, filename):
    """Additional operator turns, not edits to prior failures or system prompts."""
    assert os.geteuid() != 0
    from agentscope_app.instances import template_configurations as configurations, store
    from agentscope_app import db
    original = json.loads((root / 'results/report.json').read_text())
    scenarios = json.loads((root / filename).read_text())
    output = {'schema': 'public-policy-followups.v1', 'baseline_unchanged': True, 'cases': []}
    for followup in scenarios:
        parent = next(case for case in original['cases'] if case['id'] == followup['parent'])
        instance_id = parent['instance_id']
        if followup.get('workspace'):
            workspace = (root / followup['workspace']).resolve()
            assert workspace.parent == root / 'scenes' and workspace.is_dir()
            instance_id = store.create(followup['id'], 'dsh', [str(workspace)])['id']
        body = {'scope': 'agent', 'workspace_id': None, 'context_mode': 'auto', 'stage': 'preflight',
                'text': followup['text'], 'materials': [], 'request_key': uuid.uuid4().hex,
                'parent_request_id': parent['result']['request_id']}
        if followup.get('mode') == 'fresh':
            body.pop('parent_request_id')
            body['text'] = parent['requirements'] + '\n\n' + followup['text']
        started = time.monotonic()
        entry = {'id': followup['id'], 'parent_case': followup['parent'], 'requirements': followup['text'],
                 'expected': followup['expected'], 'started_at': db.now()}
        try:
            entry.update(status='completed', result=configurations.generate(instance_id, body))
        except Exception as error:
            entry.update(status='failed', error={'type': type(error).__name__, 'message': str(error)[:1200]})
        entry['seconds'] = round(time.monotonic() - started, 3)
        output['cases'].append(entry)
        (root / 'results' / filename).write_text(json.dumps(output, ensure_ascii=False, indent=2))
        print(json.dumps({'id': entry['id'], 'status': entry['status'], 'seconds': entry['seconds'],
                          'items': len(entry.get('result', {}).get('items', []))}, ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument('root', type=Path)
    args.add_argument('--release', type=Path, default=Path('/opt/agentscope/current'))
    args.add_argument('--worker', action='store_true')
    args.add_argument('--supplement', action='store_true')
    args.add_argument('--followup-file', default='followups.json', choices=['followups.json', 'followups-fresh.json', 'followups-clean.json'])
    options = args.parse_args()
    sys.path.insert(0, str(options.release.resolve() / 'backend'))
    if options.worker:
        raise SystemExit(supplement(options.root.resolve(), options.release.resolve(), options.followup_file) if options.supplement else worker(options.root.resolve(), options.release.resolve()))
    raise SystemExit(setup(options.root.resolve(), options.release.resolve(), options.supplement, options.followup_file))

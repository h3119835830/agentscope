"""Publish read-only approval locations to 18003; keep Broker/Agents/policies intact."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS = Path('/opt/agentscope-system-policy-20261011-161846')
RELEASE = Path('/opt/agentscope-approval-locations-20261011')
UNIT = 'agentscope-scope-demo-api.service'
DROP = Path('/etc/systemd/system/' + UNIT + '.d/90-approval-locations-20261011.conf')
BASELINE = Path('/tmp/agentscope-approval-location-baseline.json')
FILES = ['backend/agentscope_app/instances/approval_views.py',
         'backend/agentscope_app/instances/approval_locations.py']


def policy_state():
    with sqlite3.connect('file:/var/lib/agentscope-scope-demo/demo.sqlite3?mode=ro', uri=True) as con:
        tables = ['agent_instances', 'instance_dsl_scopes', 'instance_dsl_proposals',
                  'system_security_policy', 'instance_local_policies', 'instance_proposals']
        fingerprints = {t: hashlib.sha256(json.dumps(con.execute('SELECT * FROM ' + t + ' ORDER BY rowid').fetchall(), sort_keys=True).encode()).hexdigest() for t in tables}
        assert con.execute("SELECT COUNT(*) FROM history_jobs WHERE status IN ('queued','running')").fetchone()[0] == 0, 'Generation in progress'
        assert con.execute("SELECT COUNT(*) FROM instance_dsl_scopes WHERE phase!='ready'").fetchone()[0] == 0, 'Policy change in progress'
        assert con.execute("SELECT COUNT(*) FROM instance_dsl_proposals WHERE state='applying'").fetchone()[0] == 0, 'Approval in progress'
        processes = {}
        for ident, raw in con.execute("SELECT id,runtime_json FROM agent_instances WHERE gate IN ('open','paused')"):
            pid = json.loads(raw).get('pid')
            if pid and Path(f'/proc/{pid}/stat').exists():
                stat = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
                processes[ident] = {'pid': pid, 'start_ticks': stat[19]}
    broker_pid = subprocess.check_output(['systemctl','show','agentscope-scope-demo-broker.service','-p','MainPID','--value'], text=True).strip()
    return {'tables': fingerprints, 'processes': processes, 'broker_pid': broker_pid}


def stage():
    assert os.geteuid() == 0
    assert not RELEASE.exists(), 'Existing release must be inspected; never overwrite it'
    assert subprocess.check_output(['systemctl','show',UNIT,'-p','WorkingDirectory','--value'], text=True).strip() == str(PREVIOUS)
    shutil.copytree(PREVIOUS, RELEASE, symlinks=True, ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    manifest = {}
    for rel in FILES:
        dest = RELEASE / rel
        assert dest.resolve().is_relative_to(RELEASE.resolve())
        shutil.copyfile(ROOT / rel, dest)
        dest.chmod(0o644)
        manifest[rel] = hashlib.sha256(dest.read_bytes()).hexdigest()
    (RELEASE / 'approval-location-manifest.json').write_text(json.dumps({'files':manifest,'ui_index':hashlib.sha256(Path('/var/lib/agentscope-scope-demo/ui/index.html').read_bytes()).hexdigest()}, indent=2))
    print('Isolated approval API release staged; previous release preserved')


def apply():
    assert os.geteuid() == 0
    assert not DROP.exists(), 'Deployment drop-in already exists'
    manifest = json.loads((RELEASE / 'approval-location-manifest.json').read_text())
    assert subprocess.check_output(['systemctl','show',UNIT,'-p','WorkingDirectory','--value'], text=True).strip() == str(PREVIOUS), 'API changed after staging'
    assert hashlib.sha256(Path('/var/lib/agentscope-scope-demo/ui/index.html').read_bytes()).hexdigest() == manifest['ui_index'], 'UI changed after staging'
    assert set(manifest['files']) == set(FILES)
    for rel, expected in manifest['files'].items():
        assert hashlib.sha256((RELEASE / rel).read_bytes()).hexdigest() == expected
    before = policy_state()
    BASELINE.write_text(json.dumps(before, indent=2))
    DROP.write_text('[Service]\nWorkingDirectory=' + str(RELEASE) + '\nExecStart=\nExecStart=/opt/agentscope/.venv/bin/python ' + str(RELEASE) + '/scripts/scope_systemd_exec.py api\n')
    try:
        subprocess.run(['systemctl','daemon-reload'], check=True)
        subprocess.run(['systemctl','restart',UNIT], check=True, timeout=20)
        with urllib.request.urlopen('http://127.0.0.1:18003/api/health', timeout=5) as r:
            assert r.status == 200
    except Exception:
        DROP.unlink()
        subprocess.run(['systemctl','daemon-reload'], check=True)
        subprocess.run(['systemctl','restart',UNIT], check=True, timeout=20)
        raise
    assert policy_state() == before, 'Policy or process state changed; inspect before claiming acceptance'
    print('18003 API ready; policy fingerprints, Agent processes and Broker PID unchanged')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', action='store_true')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.stage: stage()
    elif args.apply: apply()
    elif args.verify:
        assert policy_state() == json.loads(BASELINE.read_text())
        print('Read-only acceptance verified: no policy or Agent process changes')
    else: print('Dry run; explicit --stage / --apply required')

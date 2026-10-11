#!/usr/bin/env python3
"""Integrate a verified shared release with CAS checks and no database rewind."""
import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path
import deploy_system_policy as old

ROOT = Path(__file__).resolve().parents[1]
DROP = '95-because-feedback-20261011.conf'
STATE = old.STATE
FOLDERS = ('backend', 'scripts', 'integrations', 'frontend/dist')


def dsh_metadata(release):
    # The broker's legacy facts path must identify the configured executable's package.
    health = old.api('/api/health')
    live = Path(old.service('api')['WorkingDirectory'])
    import sys
    sys.path.insert(0, str(live / 'scripts'))
    from scope_service import environment
    binary = Path(environment()['DSH_BIN']).resolve(strict=True)
    package = binary.parent.parent
    facts = json.loads((package / 'package.json').read_text())
    assert facts['name'] == '@deepseek-ai/dsh'
    target = release / 'dsh/node_modules/@deepseek-ai/dsh'
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists(): assert target.resolve() == package
    else: target.symlink_to(package, target_is_directory=True)
    return dict(package=str(package),version=facts['version'],package_sha256=old.sha(package/'package.json'))


def source_tree(root):
    return {str(p.relative_to(root)): old.sha(p) for folder in FOLDERS
            for p in (root / folder).rglob('*') if p.is_file()
            and not any(part in ('node_modules', '__pycache__', 'target', '.pytest_cache') for part in p.parts)
            and p.suffix != '.pyc'}


def baseline():
    services = {r: old.service(r) for r in old.UNITS}
    return dict(services=services,
                sources={r: source_tree(Path(s['WorkingDirectory'])) for r, s in services.items()},
                ui=old.tree(STATE / 'ui'), policy_scopes=old.scopes(), other_ports=old.other_ports())


def scope_summary(scopes):
    return {key: {**{k: value[k] for k in ('revision','document_hash','phase')},
                  'document_count': len(value['documents'])} for key, value in scopes.items()}


def stage():
    assert os.geteuid() == 0
    old.guard()
    checks = json.loads((ROOT / 'docs/because-feedback/main18003-evidence/source-checks.json').read_text())
    assert all(c['exit_code'] == 0 for c in checks if c['check'] != 'managed-web')
    assert 'fail 0' in (ROOT / 'docs/because-feedback/main18003-evidence/managed-web-root.txt').read_text()
    release = Path('/opt/agentscope-system-policy-' + time.strftime('%Y%m%d-%H%M%S') + '-because')
    release.mkdir()
    for folder in FOLDERS:
        shutil.copytree(ROOT / folder, release / folder,
                        ignore=shutil.ignore_patterns('node_modules', '__pycache__', '*.pyc', 'target', '.pytest_cache'))
    dependency = (ROOT / 'integrations/pi-policy-tools/node_modules').resolve(strict=True)
    assert json.loads((dependency / '@earendil-works/pi-coding-agent/package.json').read_text())['version'] == '1.0.1'
    (release / 'integrations/pi-policy-tools/node_modules').symlink_to(dependency, target_is_directory=True)
    runtime = dsh_metadata(release)
    # Compiler and already attested kernel binary retain their exact deployed identity.
    live = Path(old.service('api')['WorkingDirectory'])
    for rel in ('backend/dsl-adapter/target/release/agentscope-dsl-adapter',):
        dest = release / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(live / rel, dest)
    (release / 'bin').mkdir()
    for name in ('actplane', 'actplane.capabilities.json'):
        shutil.copy2(STATE / 'bin' / name, release / 'bin' / name)
    for p in release.rglob('*'):
        if not p.is_symlink(): p.chmod(0o755 if p.is_dir() or p.name in ('actplane', 'agentscope-dsl-adapter') else 0o644)
    manifest = dict(release=str(release), before=baseline(), files=old.tree(release),dsh_runtime=runtime)
    file = release / 'because-deployment.json'
    file.write_text(json.dumps(manifest, indent=2)); file.chmod(0o600)
    print(json.dumps(dict(staged=str(release), manifest=str(file))))


def install_ui(source):
    # Existing content-addressed assets remain available to open browser tabs.
    for p in source.rglob('*'):
        if p.is_file() and p.name != 'index.html': old.install_file(p, STATE / 'ui' / p.relative_to(source))
    old.install_file(source / 'index.html', STATE / 'ui/index.html')


def apply(file):
    assert os.geteuid() == 0
    m = json.loads(Path(file).read_text()); release = Path(m['release'])
    assert release.parent == Path('/opt') and release.name.endswith('-because')
    for rel, h in m['files'].items(): assert old.sha(release / rel) == h, rel
    if m.get('dsh_runtime'):
        assert old.sha(Path(m['dsh_runtime']['package'])/'package.json') == m['dsh_runtime']['package_sha256']
    assert baseline() == m['before'], 'Shared source, UI, policy or service changed after staging'
    agents = old.guard(); active = [r['id'] for r in agents if r['active']]
    backup = STATE / 'release-backups' / release.name
    backup.mkdir(parents=True, mode=0o700); backup.chmod(0o700)
    shutil.copytree(STATE / 'ui', backup / 'ui')
    with sqlite3.connect(STATE / 'demo.sqlite3') as src, sqlite3.connect(backup / 'demo.sqlite3') as dest: src.backup(dest)
    result = dict(release=str(release), previous_active=active, policy_scopes=m['before']['policy_scopes'],
                  other_ports=m['before']['other_ports'], preserved_approval_commit='b2a62d8',
                  database_rewind=False, private_backup=str(backup))
    drops = []; restarted = []
    try:
        assert baseline() == m['before'], 'Shared state changed during backup'
        for ident in active: old.api('/api/agent-instances/' + ident + '/stop', {})
        subprocess.run(['systemctl', 'stop', old.UNITS['api'], old.UNITS['broker']], check=True, timeout=60)
        # Both services must be stopped before changing their shared implementation.
        assert all(old.command('systemctl','show',u,'-p','MainPID','--value') == '0' for u in old.UNITS.values())
        install_ui(release / 'frontend/dist')
        for role, unit in old.UNITS.items():
            drop = Path('/etc/systemd/system') / (unit + '.d') / DROP
            assert not drop.exists(), 'Do not overwrite a deployment pointer'
            drop.write_text('[Service]\nWorkingDirectory=' + str(release) + '\nExecStart=\nExecStart=/opt/agentscope/.venv/bin/python ' + str(release) + '/scripts/scope_systemd_exec.py ' + role + '\n')
            drops.append(drop)
        subprocess.run(['systemctl','daemon-reload'], check=True)
        subprocess.run(['systemctl','start',old.UNITS['broker'],old.UNITS['api']], check=True, timeout=60)
        old.wait_ready()
        for ident in active:
            row = old.api('/api/agent-instances/' + ident + '/start', {})
            assert row['active'] and row['runtime']['verified']; restarted.append(ident)
        assert old.scopes() == m['before']['policy_scopes'], 'Shared policy content or revision changed'
        assert old.other_ports() == m['before']['other_ports'], 'Other console listener changed'
        after = old.api('/api/agent-instances')['instances']
        assert {r['id'] for r in after if r['mode']=='controlled' and r['active']} == set(active)
        assert old.sha(STATE / 'ui/index.html') == old.sha(release / 'frontend/dist/index.html')
        assert all(old.service(r)['WorkingDirectory'] == str(release) for r in old.UNITS)
        result.update(published=True, policy_scopes_unchanged=True, other_ports_unchanged=True,
                      services={r: old.service(r) for r in old.UNITS}, ui_index_sha256=old.sha(STATE/'ui/index.html'))
    except Exception as error:
        result.update(published=False,error_type=type(error).__name__)
        for ident in restarted:
            try: old.api('/api/agent-instances/' + ident + '/stop', {})
            except Exception: pass
        subprocess.run(['systemctl','stop',old.UNITS['api'],old.UNITS['broker']],timeout=60)
        for drop in drops: drop.unlink()
        install_ui(backup / 'ui')
        # Additive migrations and concurrent records are preserved; never rewind shared data.
        subprocess.run(['systemctl','daemon-reload'],check=True)
        subprocess.run(['systemctl','start',old.UNITS['broker'],old.UNITS['api']],check=True,timeout=60)
        old.wait_ready()
        for ident in active: assert old.api('/api/agent-instances/' + ident + '/start', {})['active']
        result['rolled_back']=True
        raise
    finally:
        (backup / 'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        evidence=ROOT / 'docs/because-feedback/main18003-evidence/deployment.json'
        public={**result,'policy_scopes':scope_summary(result['policy_scopes'])}
        evidence.write_text(json.dumps(public,ensure_ascii=False,indent=2)); evidence.chmod(0o644)
        print(json.dumps(dict(published=result.get('published'),evidence=str(evidence))))


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',action='store_true');p.add_argument('--apply');a=p.parse_args()
    if a.stage: stage()
    elif a.apply: apply(a.apply)
    else: p.print_help()

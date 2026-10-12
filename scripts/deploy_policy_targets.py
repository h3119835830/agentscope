"""API/UI-only local release. Never restart Broker or change policy authority."""
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

SOURCE=Path(__file__).resolve().parents[1]
STATE=Path('/var/lib/agentscope-scope-demo')
UNIT='agentscope-scope-demo-api.service'
DROP=Path('/etc/systemd/system/'+UNIT+'.d/99z-policy-targets-20261012.conf')
OVERLAY=[
 'history/agent_context.py','history/agent_scene.py','history/generations.py',
 'instances/approval_views.py','instances/controller.py','instances/dsl_api.py','instances/dsl_policy.py',
 'instances/policy_targets.py','instances/local_policy_proposals.py']

def stage():
    assert os.geteuid()==0
    with sqlite3.connect('file:'+str(STATE/'demo.sqlite3')+'?mode=ro',uri=True) as con:
        assert not con.execute("SELECT 1 FROM managed_tasks WHERE json_extract(state_json,'$.phase') IN ('running','starting')").fetchone(), 'Managed execution is busy'
    guard();previous=service(UNIT);live=Path(previous['WorkingDirectory'])
    assert live.parent==Path('/opt')
    # Refuse to overwrite any concurrent changes in files touched by this step.
    previous_manifest=live/'targets-deployment.json'
    previous_overlay=json.loads(previous_manifest.read_text()).get('source_overlay',{}) if previous_manifest.exists() else {}
    for p in OVERLAY:
        relative='backend/agentscope_app/'+p
        if p in previous_overlay:
            assert previous_overlay[p]==sha(live/relative), 'Live overlay differs: '+p
            continue
        prior=subprocess.run(['git','-c','safe.directory='+str(SOURCE),'-C',str(SOURCE),'show','HEAD:'+relative],capture_output=True)
        if prior.returncode==0:
            assert hashlib.sha256(prior.stdout).hexdigest()==sha(live/relative), 'Live baseline differs: '+p
        else: assert not (live/relative).exists(), 'New file exists in live release: '+p
    release=Path('/opt/agentscope-policy-targets-'+time.strftime('%Y%m%d-%H%M%S'))
    assert not release.exists();release.mkdir()
    for folder in ('backend','scripts','integrations','bin','dsh'):
        if (live/folder).exists():
            shutil.copytree(live/folder,release/folder,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for p in OVERLAY: shutil.copy2(SOURCE/'backend/agentscope_app'/p,release/'backend/agentscope_app'/p)
    shutil.copytree(SOURCE/'frontend/dist',release/'frontend/dist')
    manifest={'release':str(release),'previous_api':previous,'broker':service('agentscope-scope-demo-broker.service'),
              'source_overlay':{p:sha(SOURCE/'backend/agentscope_app'/p) for p in OVERLAY},
              'previous_files':files(live/'backend/agentscope_app'),'release_files':files(release),
              'authority':authority(),'listeners':listeners(),
              'previous_drop':DROP.read_text() if DROP.exists() else None}
    path=release/'targets-deployment.json';path.write_text(json.dumps(manifest,indent=2));path.chmod(0o600)
    print(json.dumps({'staged':str(release),'manifest':str(path)}))

def apply(path):
    assert os.geteuid()==0
    m=json.loads(Path(path).read_text());release=Path(m['release']);live=Path(m['previous_api']['WorkingDirectory'])
    assert release.parent==Path('/opt') and release.name.startswith('agentscope-policy-targets-')
    assert (DROP.read_text() if DROP.exists() else None)==m.get('previous_drop')
    assert {k:v for k,v in files(release).items() if k!='targets-deployment.json'}==m['release_files']
    assert service(UNIT)==m['previous_api'] and service('agentscope-scope-demo-broker.service')==m['broker']
    assert files(live/'backend/agentscope_app')==m['previous_files']
    guard();assert authority()==m['authority'] and listeners()==m['listeners']
    with sqlite3.connect('file:'+str(STATE/'demo.sqlite3')+'?mode=ro',uri=True) as con:
        assert not con.execute("SELECT 1 FROM managed_tasks WHERE json_extract(state_json,'$.phase') IN ('running','starting')").fetchone(), 'Managed execution is busy'
    backup=STATE/'release-backups'/release.name;backup.mkdir(parents=True,mode=0o700)
    shutil.copytree(STATE/'ui',backup/'ui')
    with sqlite3.connect(STATE/'demo.sqlite3') as src,sqlite3.connect(backup/'demo.sqlite3') as dest:src.backup(dest)
    result={'release':str(release),'previous_api':m['previous_api'],'authority_before':m['authority']}
    try:
        shutil.copytree(release/'frontend/dist',STATE/'ui',dirs_exist_ok=True)
        # The Broker retains its existing 8s fail-closed API liveness rule.
        # Bound API shutdown after idle/drain guards; do not extend or spoof
        # the Broker heartbeat while releasing the control plane.
        DROP.write_text('[Service]\nTimeoutStopSec=3\nWorkingDirectory='+str(release)+'\nExecStart=\nExecStart=/opt/agentscope/.venv/bin/python '+str(release)+'/scripts/scope_systemd_exec.py api\n')
        subprocess.run(['systemctl','daemon-reload'],check=True)
        subprocess.run(['systemctl','restart',UNIT],check=True,timeout=30)
        assert api('/api/health')['ok']
        assert service('agentscope-scope-demo-broker.service')==m['broker']
        for _ in range(25):
            if authority()==m['authority']:break
            time.sleep(.2)
        assert authority()==m['authority'], 'Authority changed during release'
        assert listeners()==m['listeners']
        assert sha(STATE/'ui/index.html')==sha(release/'frontend/dist/index.html')
        result.update(published=True,authority_after=authority(),broker_unchanged=True,other_ports_unchanged=True,current_api=service(UNIT))
    except Exception:
        if m.get('previous_drop') is None:DROP.unlink(missing_ok=True)
        else:DROP.write_text(m['previous_drop'])
        shutil.copytree(backup/'ui',STATE/'ui',dirs_exist_ok=True)
        subprocess.run(['systemctl','daemon-reload'],check=True)
        subprocess.run(['systemctl','restart',UNIT],check=True,timeout=30)
        result.update(published=False,rolled_back=True)
        raise
    finally:
        p=backup/'result.json';p.write_text(json.dumps(result,indent=2));p.chmod(0o600)
        print(json.dumps({'published':result.get('published',False),'evidence':str(p)}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--stage',action='store_true');group.add_argument('--apply');args=parser.parse_args()
    stage() if args.stage else apply(args.apply)

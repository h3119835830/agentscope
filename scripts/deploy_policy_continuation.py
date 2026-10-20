"""Reviewed API/UI overlay only. Preserve live Broker, native engines and authority."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
from deploy_reference_reader import ROOT, STATE, API, BROKER, PYTHON, git, identity, smoke
from deploy_policy_semantics import api, authority, files, listeners, service, sha
from deploy_policy_context_agent import idle, protected

BASE='da076c3'
PREFIX='agentscope-pi-continuation-'
DROP=Path('/etc/systemd/system/'+API+'.d/zzzzzzzzzzz-pi-continuation-20261020.conf')
MANIFEST='continuation-deployment.json'
EXISTING=tuple('backend/agentscope_app/instances/'+name+'.py' for name in
               ('api','templates_api','template_configurations','policy_context_agent','workspace_references'))
NEW=tuple('backend/agentscope_app/instances/'+name+'.py' for name in ('policy_continuation','write_permissions'))


def stage():
    assert os.geteuid()==0 and not DROP.exists()
    idle()
    assert not git('status','--porcelain','--',*EXISTING,*NEW,'frontend','scripts/deploy_policy_continuation.py').strip()
    assert not git('diff','a182291','--','actplane').strip()
    before=service(API);broker=service(BROKER);live=Path(before['WorkingDirectory'])
    assert live.parent==Path('/opt')
    for name in EXISTING:
        assert sha(live/name)==hashlib.sha256(git('show',BASE+':'+name)).hexdigest(), 'Live source drift: '+name
    for name in NEW:assert not (live/name).exists()
    for name,value in files(ROOT/'frontend/dist').items():
        if name not in ('index.html','terminal.html') and not name.startswith('assets/'):
            assert sha(STATE/'ui'/name)==value, 'Unrelated static content differs: '+name
    release=Path('/opt')/(PREFIX+time.strftime('%Y%m%d-%H%M%S'));release.mkdir(mode=0o755)
    for folder in ('backend','scripts','integrations','bin','dsh'):
        if (live/folder).exists():
            shutil.copytree(live/folder,release/folder,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in (*EXISTING,*NEW):
        shutil.copyfile(ROOT/name,release/name);(release/name).chmod(0o644)
    shutil.copytree(ROOT/'frontend/dist',release/'frontend/dist')
    for folder in ('backend/broker','integrations','bin','dsh'):
        if (live/folder).exists():assert files(live/folder)==files(release/folder)
    manifest={'release':str(release),'api':before,'broker':broker,'authority':authority(),
              'protected':protected(),'listeners':listeners(),'ui':files(STATE/'ui'),
              'api_identity':identity(before['MainPID']),'reader_smoke':smoke(release),
              'live_overlay':{name:sha(live/name) for name in EXISTING},
              'release_files':files(release),'commit':git('rev-parse','HEAD').decode().strip()}
    path=release/MANIFEST;path.write_text(json.dumps(manifest,indent=2));path.chmod(0o600)
    print(json.dumps({'staged':str(path),'reader_smoke':manifest['reader_smoke']}))


def apply(path):
    assert os.geteuid()==0 and not DROP.exists()
    manifest_path=Path(path);m=json.loads(manifest_path.read_text());release=Path(m['release'])
    assert release.parent==Path('/opt') and release.name.startswith(PREFIX) and manifest_path==release/MANIFEST
    assert {k:v for k,v in files(release).items() if k!=MANIFEST}==m['release_files']
    assert service(API)==m['api'] and service(BROKER)==m['broker']
    live=Path(m['api']['WorkingDirectory'])
    assert all(sha(live/name)==value for name,value in m['live_overlay'].items())
    idle()
    assert authority()==m['authority'] and protected()==m['protected']
    assert listeners()==m['listeners'] and files(STATE/'ui')==m['ui']
    backup=STATE/'release-backups'/release.name;backup.mkdir(parents=True,mode=0o700)
    shutil.copytree(STATE/'ui',backup/'ui')
    with sqlite3.connect(STATE/'demo.sqlite3') as src,sqlite3.connect(backup/'demo.sqlite3') as dest:src.backup(dest)
    (backup/'demo.sqlite3').chmod(0o600)
    result={'published':False,'release':str(release),'commit':m['commit']}
    try:
        DROP.write_text('[Service]\nTimeoutStopSec=3\nWorkingDirectory='+str(release)+
            '\nExecStart=\nExecStart='+PYTHON+' '+str(release)+'/scripts/scope_systemd_exec.py api\n'+
            'ExecStartPost=\nExecStartPost='+PYTHON+' '+str(release)+'/scripts/scope_systemd_exec.py api-ready\n')
        subprocess.run(['systemctl','daemon-reload'],check=True)
        started=time.monotonic();subprocess.run(['systemctl','restart',API],check=True,timeout=30)
        assert api('/api/health')['ok'] and service(BROKER)==m['broker']
        assert authority()==m['authority'] and protected()==m['protected'] and listeners()==m['listeners']
        assert identity(service(API)['MainPID'])==m['api_identity']
        # Immutable hashed assets first; retain old assets for existing browser tabs.
        shutil.copytree(release/'frontend/dist/assets',STATE/'ui/assets',dirs_exist_ok=True)
        for name in ('index.html','terminal.html'):
            temporary=STATE/'ui'/('.'+name+'.continuation')
            shutil.copyfile(release/'frontend/dist'/name,temporary)
            os.replace(temporary,STATE/'ui'/name)
        assert all(sha(STATE/'ui'/name)==value for name,value in files(release/'frontend/dist').items())
        result.update(published=True,seconds=round(time.monotonic()-started,3),
            api=service(API),broker_unchanged=True,authority_unchanged=True,other_ports_unchanged=True)
    except BaseException:
        DROP.unlink(missing_ok=True)
        for name in ('index.html','terminal.html'):shutil.copyfile(backup/'ui'/name,STATE/'ui'/name)
        subprocess.run(['systemctl','daemon-reload'],check=True)
        subprocess.run(['systemctl','restart',API],check=True,timeout=30)
        result['code_pointer_rolled_back']=True
        raise
    finally:
        report=backup/'result.json';report.write_text(json.dumps(result,indent=2));report.chmod(0o600)
        print(json.dumps({'published':result['published'],'report':str(report)}))


if __name__=='__main__':
    p=argparse.ArgumentParser();group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--stage',action='store_true');group.add_argument('--apply')
    args=p.parse_args();stage() if args.stage else apply(args.apply)

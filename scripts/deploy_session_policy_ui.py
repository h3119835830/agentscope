#!/usr/bin/env python3
"""Apply only the reviewed session/read-projection delta to the current release."""
import ast,json,shutil,subprocess,tempfile,time
from pathlib import Path
import deploy_runtime_policy_ui as deploy

SOURCE=Path(__file__).resolve().parents[1]
PREFIX='backend/agentscope_app/instances/'
CHANGED=[PREFIX+name for name in ('sessions.py','session_loaded_policies.py','approval_views.py')]
ADDED=PREFIX+'session_policy_records.py'


def main():
    patch=subprocess.check_output(['git','-c','safe.directory='+str(SOURCE),'diff','a8c70e3','--',*CHANGED],cwd=SOURCE)
    if not patch:raise RuntimeError('No reviewed session delta')
    # Temporary staging is discarded after applying; no source backup remains.
    with tempfile.TemporaryDirectory(prefix='agentscope-session-ui-') as directory:
        staged=Path(directory)
        manifest=json.loads((deploy.RELEASE/'runtime-ui-stage.json').read_text())
        if (deploy.RELEASE/ADDED).exists():
            assert deploy.digest(deploy.RELEASE/ADDED)==manifest['files'].get(ADDED),'Session read module changed since release'
        before={name:deploy.digest(deploy.RELEASE/name) for name in CHANGED}
        for name in CHANGED:
            path=staged/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(deploy.RELEASE/name,path)
        check=subprocess.run(['git','apply','--check','-'],input=patch,cwd=staged,capture_output=True)
        if check.returncode==0:subprocess.run(['git','apply','-'],input=patch,cwd=staged,check=True)
        else:subprocess.run(['git','apply','--check','--reverse','-'],input=patch,cwd=staged,check=True)
        shutil.copyfile(SOURCE/ADDED,staged/ADDED)
        for name in CHANGED+[ADDED]:ast.parse((staged/name).read_text())
        deploy.check_idle()
        receipt=json.loads((deploy.RELEASE/'runtime-ui-deployment.json').read_text())
        assert deploy.digest(deploy.STATE/'ui/index.html')==receipt['ui_hash'],'UI baseline changed'
        assert all(deploy.digest(deploy.RELEASE/name)==value for name,value in before.items())
        identities=deploy.identities()
        broker=subprocess.check_output(['systemctl','show','agentscope-scope-demo-broker.service','-p','MainPID','--value'],text=True).strip()
        stage=json.loads((deploy.RELEASE/'runtime-ui-stage.json').read_text())
        for name in CHANGED+[ADDED]:
            target=deploy.RELEASE/name;temporary=target.with_suffix('.session-ui-new')
            shutil.copyfile(staged/name,temporary);temporary.replace(target)
            stage['files'][name]=deploy.digest(target)
        (deploy.RELEASE/'runtime-ui-stage.json').write_text(json.dumps(stage,indent=2))
        subprocess.run(['systemctl','restart',deploy.UNIT],check=True,timeout=25)
        for _ in range(50):
            try:
                if deploy.api('/api/health').get('ok'):break
            except OSError:time.sleep(.2)
        else:raise RuntimeError('API did not become ready')
        assert identities==deploy.identities(),'Agent identity changed'
        assert broker==subprocess.check_output(['systemctl','show','agentscope-scope-demo-broker.service','-p','MainPID','--value'],text=True).strip()
        deploy.refresh()
        print(json.dumps({'session_policy_projection_updated':True,'agent_identities_unchanged':True,'broker_pid_unchanged':broker,'files':CHANGED+[ADDED]}))

if __name__=='__main__':main()

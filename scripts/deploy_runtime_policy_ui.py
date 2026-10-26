#!/usr/bin/env python3
"""Publish the bounded runtime read projection/UI; no Broker or Agent restart."""
import argparse,hashlib,json,os,re,shutil,sqlite3,subprocess,time,urllib.request
from pathlib import Path
SOURCE=Path(__file__).resolve().parents[1]
BASE=Path('/opt/agentscope-resource-views-20261021-144448')
RELEASE=Path('/opt/agentscope-runtime-policy-ui-20261026')
STATE=Path('/var/lib/agentscope-scope-demo')
UNIT='agentscope-scope-demo-api.service'
DROP=Path('/etc/systemd/system/'+UNIT+'.d')/('z'*18+'-runtime-policy-ui-20261026.conf')
FILES=['backend/agentscope_app/managed/records.py','backend/agentscope_app/instances/runtime_policies.py']
def api(path):
    with urllib.request.urlopen('http://127.0.0.1:18003'+path,timeout=12) as response:return json.load(response)
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def identities():return {r['id']:{k:r.get(k) for k in ['pid','generation','gate','policy_hash']} for r in api('/api/agent-instances')['instances']}
def check_idle():
    with sqlite3.connect('file:'+str(STATE/'demo.sqlite3')+'?mode=ro',uri=True) as con:
        for table,predicate in [('history_jobs',"status IN ('queued','running')"),('managed_jobs',"status IN ('queued','running')"),('instance_dsl_scopes',"phase!='ready'")]:
            if con.execute('SELECT count(*) FROM '+table+' WHERE '+predicate).fetchone()[0]:raise RuntimeError('Wait for active generation/application: '+table)
def stage():
    if os.getuid()!=0:raise RuntimeError('root required')
    RELEASE.mkdir(exist_ok=True)
    for item in BASE.iterdir():
        dest=RELEASE/item.name
        if item.name in ('backend','scripts'):
            shutil.copytree(item,dest,dirs_exist_ok=True,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        elif not dest.exists():dest.symlink_to(item,target_is_directory=item.is_dir())
    for name in FILES:shutil.copyfile(SOURCE/name,RELEASE/name)
    original=(BASE/'backend/agentscope_app/instances/api.py').read_text()
    addition='from .runtime_policies import router as runtime_policy_router\nrouter.include_router(runtime_policy_router)\n'
    assert 'runtime_policy_router' not in original
    (RELEASE/'backend/agentscope_app/instances/api.py').write_text(original.replace('router=APIRouter()\n','router=APIRouter()\n'+addition,1))
    manifest={name:digest(RELEASE/name) for name in FILES+['backend/agentscope_app/instances/api.py']}
    data={'base':str(BASE),'release':str(RELEASE),'files':manifest,'prior_ui_hash':digest(STATE/'ui/index.html')}
    (RELEASE/'runtime-ui-stage.json').write_text(json.dumps(data,indent=2))
    print(json.dumps({'staged':True,'files':list(manifest),'prior_ui_hash':data['prior_ui_hash']}))
def apply():
    check_idle();data=json.loads((RELEASE/'runtime-ui-stage.json').read_text())
    assert digest(STATE/'ui/index.html')==data['prior_ui_hash'],'UI changed after staging'
    assert all(digest(RELEASE/name)==hashed for name,hashed in data['files'].items())
    before=identities();broker=subprocess.check_output(['systemctl','show','agentscope-scope-demo-broker.service','-p','MainPID','--value'],text=True).strip()
    DROP.write_text('[Service]\nWorkingDirectory='+str(RELEASE)+'\nExecStart=\nExecStart=/opt/agentscope/.venv/bin/python '+str(RELEASE)+'/scripts/scope_systemd_exec.py api\n')
    subprocess.run(['systemctl','daemon-reload'],check=True)
    assert subprocess.check_output(['systemctl','show',UNIT,'-p','WorkingDirectory','--value'],text=True).strip()==str(RELEASE)
    subprocess.run(['systemctl','restart',UNIT],check=True,timeout=25)
    for _ in range(50):
        try:
            if api('/api/health').get('ok'):break
        except OSError:time.sleep(.2)
    else:raise RuntimeError('API did not become ready')
    assert identities()==before,'Agent identity changed'
    assert subprocess.check_output(['systemctl','show','agentscope-scope-demo-broker.service','-p','MainPID','--value'],text=True).strip()==broker
    live=STATE/'ui';dist=SOURCE/'frontend/dist'
    for source in dist.rglob('*'):
        if not source.is_file() or source.name=='index.html':continue
        dest=live/source.relative_to(dist);dest.parent.mkdir(exist_ok=True,parents=True);shutil.copyfile(source,dest)
    tmp=live/'index.runtime-ui-new';shutil.copyfile(dist/'index.html',tmp);tmp.replace(live/'index.html')
    receipt={'release':str(RELEASE),'broker_pid':broker,'agent_identities':before,'ui_hash':digest(live/'index.html'),'source_ui_hash':digest(dist/'index.html'),'no_backup_created':True,'old_ui_assets_pending_acceptance':True}
    assert receipt['ui_hash']==receipt['source_ui_hash']
    (RELEASE/'runtime-ui-deployment.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
def clean():
    live=STATE/'ui';assets=live/'assets';receipt=json.loads((RELEASE/'runtime-ui-deployment.json').read_text())
    assert live.resolve()==Path('/var/lib/agentscope-scope-demo/ui')
    assert digest(live/'index.html')==receipt['ui_hash']==digest(SOURCE/'frontend/dist/index.html'),'UI changed since acceptance'
    keep={p.name for p in (SOURCE/'frontend/dist/assets').iterdir() if p.is_file()}
    backup_index=live/'index.before-20261023-three-primary-types.html'
    for html in live.rglob('*.html'):
        if html==backup_index:continue
        keep.update(re.findall(r'(?:/assets/|[.]?/assets/)([\w.-]+\.(?:js|css))',html.read_text(errors='replace')))
    while True:
        prior=set(keep)
        for name in list(keep):
            file=assets/name
            if file.is_file():keep.update(re.findall(r'(?:\./|/assets/)([\w.-]+\.(?:js|css))',file.read_text(errors='replace')))
        if prior==keep:break
    candidates=[p for p in assets.iterdir() if p.is_file() and re.fullmatch(r'[\w.-]+-[A-Za-z0-9_-]{6,}\.(?:js|css)',p.name) and p.name not in keep]
    if backup_index.exists():candidates.append(backup_index)
    removed=[]
    for file in candidates:
        assert file.resolve().is_relative_to(live.resolve()) and not file.is_symlink()
        removed.append({'path':str(file.relative_to(live)),'sha256':digest(file)});file.unlink()
    receipt.update(old_ui_assets_pending_acceptance=False,removed_obsolete_ui_files=removed)
    (RELEASE/'runtime-ui-deployment.json').write_text(json.dumps(receipt,indent=2));print(json.dumps({'removed':len(removed),'retained_assets':len(list(assets.iterdir())),'audit_data_deleted':False}))
def refresh():
    receipt=json.loads((RELEASE/'runtime-ui-deployment.json').read_text());live=STATE/'ui';dist=SOURCE/'frontend/dist'
    assert digest(live/'index.html')==receipt['ui_hash'],'UI changed since acceptance'
    name='backend/agentscope_app/instances/runtime_policies.py';api_changed=digest(SOURCE/name)!=digest(RELEASE/name)
    if api_changed:
        check_idle();before=identities();broker=subprocess.check_output(['systemctl','show','agentscope-scope-demo-broker.service','-p','MainPID','--value'],text=True).strip()
        stage=json.loads((RELEASE/'runtime-ui-stage.json').read_text());assert digest(RELEASE/name)==stage['files'][name]
        temporary=(RELEASE/name).with_suffix('.runtime-new');shutil.copyfile(SOURCE/name,temporary);temporary.replace(RELEASE/name)
        stage['files'][name]=digest(RELEASE/name);(RELEASE/'runtime-ui-stage.json').write_text(json.dumps(stage,indent=2))
        subprocess.run(['systemctl','restart',UNIT],check=True,timeout=25)
        for _ in range(50):
            try:
                if api('/api/health').get('ok'):break
            except OSError:time.sleep(.2)
        else:raise RuntimeError('API did not become ready')
        assert identities()==before
        assert subprocess.check_output(['systemctl','show','agentscope-scope-demo-broker.service','-p','MainPID','--value'],text=True).strip()==broker
    for source in dist.rglob('*'):
        if source.is_file() and source.name!='index.html':
            dest=live/source.relative_to(dist);dest.parent.mkdir(exist_ok=True,parents=True);shutil.copyfile(source,dest)
    tmp=live/'index.runtime-ui-new';shutil.copyfile(dist/'index.html',tmp);tmp.replace(live/'index.html')
    receipt.update(ui_hash=digest(live/'index.html'),source_ui_hash=digest(dist/'index.html'),old_ui_assets_pending_acceptance=True)
    (RELEASE/'runtime-ui-deployment.json').write_text(json.dumps(receipt,indent=2));print(json.dumps({'static_refreshed':True,'read_api_updated':api_changed,'ui_hash':receipt['ui_hash']}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['stage','apply','clean','check','refresh']);args=p.parse_args()
    if args.action=='stage':stage()
    elif args.action=='apply':apply()
    elif args.action=='clean':clean()
    elif args.action=='refresh':refresh()
    else:check_idle();print(json.dumps({'idle':True,'instances':identities()}))

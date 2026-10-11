#!/usr/bin/env python3
"""Stage/activate the verified 18003 release with a private rollback snapshot."""
import argparse,hashlib,json,os,re,shutil,sqlite3,subprocess,time,urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STATE=Path('/var/lib/agentscope-scope-demo')
UNITS={role:'agentscope-scope-demo-'+role+'.service' for role in ('api','broker')}
DROP='80-system-policy-20261011.conf'
def api(path,body=None):
    request=urllib.request.Request('http://127.0.0.1:18003'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=160) as response:return json.load(response)
def command(*args):return subprocess.check_output(args,text=True).strip()
def service(role):return {k:command('systemctl','show',UNITS[role],'-p',k,'--value') for k in ('MainPID','WorkingDirectory','ExecStart','DropInPaths')}
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def tree(root):return {str(p.relative_to(root)):sha(p) for p in Path(root).rglob('*') if p.is_file() and not any(x in p.parts for x in ('__pycache__','.git','target')) and p.suffix!='.pyc'}
def scopes():
    rows=api('/api/agent-instances')['instances'];result={}
    for ident in ['system']+[r['id'] for r in rows if r['mode']=='controlled']:
        d=api('/api/security/system/dsl' if ident=='system' else '/api/agent-instances/'+ident+'/dsl')
        result[ident]={k:d[k] for k in ('revision','document_hash','documents','phase')}
    return result
def other_ports():
    rows=[]
    for line in command('ss','-H','-lntp').splitlines():
        fields=line.split();endpoint=fields[3]
        if endpoint.rsplit(':',1)[-1] not in ('18000','18004'):continue
        for pid in re.findall(r'pid=(\d+)',line):
            start=Path('/proc',pid,'stat').read_text().rsplit(') ',1)[1].split()[19]
            rows.append({'endpoint':endpoint,'pid':int(pid),'start_ticks':start})
    return sorted(rows,key=lambda row:(row['endpoint'],row['pid']))
def guard():
    with sqlite3.connect('file:'+str(STATE/'demo.sqlite3')+'?mode=ro',uri=True) as con:
        assert not con.execute("SELECT 1 FROM history_jobs WHERE status IN ('queued','running')").fetchone(),'Generation in progress'
        assert not con.execute("SELECT 1 FROM instance_dsl_scopes WHERE phase!='ready'").fetchone(),'Policy update in progress'
        assert not con.execute("SELECT 1 FROM instance_dsl_proposals WHERE state='applying'").fetchone(),'Approval in progress'
        assert not con.execute('SELECT 1 FROM instance_leases').fetchone(),'Native tool execution in progress'
        for (pid,) in con.execute('SELECT watch_pid FROM tasks WHERE watch_pid IS NOT NULL'):
            assert not Path('/proc',str(pid)).exists(),'Managed task executor still exists'
    rows=[r for r in api('/api/agent-instances')['instances'] if r['mode']=='controlled']
    for r in rows:
        assert r['gate'] not in ('starting','updating'),'Agent lifecycle in progress'
        if r.get('active'):
            sessions=api('/api/agent-instances/'+r['id']+'/sessions')['sessions']
            assert all(s.get('status') in ('idle','stored','stopped') for s in sessions),'Agent session is busy'
    return rows
def stage(kernel_report):
    assert os.geteuid()==0
    report=json.loads(Path(kernel_report).read_text());assert report['runtime_verified'] and report['binary_sha256']==sha(ROOT/'actplane/target/release/actplane')
    guard();stamp=time.strftime('%Y%m%d-%H%M%S');release=Path('/opt/agentscope-system-policy-'+stamp);release.mkdir(mode=0o755)
    for folder in ('backend','scripts','integrations','frontend/dist'):
        shutil.copytree(ROOT/folder,release/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc','target','.pytest_cache'))
    adapter=Path('backend/dsl-adapter/target/release/agentscope-dsl-adapter');(release/adapter).parent.mkdir(parents=True)
    shutil.copy2(ROOT/adapter,release/adapter)
    (release/'bin').mkdir();shutil.copy2(ROOT/'actplane/target/release/actplane',release/'bin/actplane')
    (release/'bin/actplane.capabilities.json').write_text(json.dumps({k:report[k] for k in ('schema','runtime_verified','binary_sha256','file_suffix','max_suffix_bytes','kernel_release')}))
    for p in release.rglob('*'):
        if not p.is_symlink():p.chmod(0o755 if p.is_dir() or p.name in ('actplane','agentscope-dsl-adapter') else 0o644)
    services={r:service(r) for r in UNITS}
    current_sources={r:tree(Path(s['WorkingDirectory'])/'backend') for r,s in services.items()}
    manifest={'release':str(release),'services':services,'current_sources':current_sources,'staged_files':tree(release),'adapter_sha256':sha(release/adapter),'policy_scopes':scopes(),'other_ports':other_ports()}
    file=release/'deployment.json';file.write_text(json.dumps(manifest,indent=2));file.chmod(0o600)
    print(json.dumps({'staged':str(release),'manifest':str(file)}))
def install_file(source,dest):
    dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
    tmp=dest.with_name(dest.name+'.system-policy-new');shutil.copy2(source,tmp);os.replace(tmp,dest)
def wait_ready():
    for _ in range(60):
        try:
            if api('/api/health'):return
        except OSError:time.sleep(.25)
    raise RuntimeError('18003 API did not become ready')
def apply(file):
    assert os.geteuid()==0
    manifest=json.loads(Path(file).read_text());release=Path(manifest['release'])
    assert release.parent==Path('/opt') and release.name.startswith('agentscope-system-policy-')
    for relative,expected in manifest['staged_files'].items():assert sha(release/relative)==expected,relative
    assert sha(release/'backend/dsl-adapter/target/release/agentscope-dsl-adapter')==manifest['adapter_sha256']
    for role in UNITS:
        assert service(role)==manifest['services'][role],'Service changed after staging'
        assert tree(Path(manifest['services'][role]['WorkingDirectory'])/'backend')==manifest['current_sources'][role],'Live source changed after staging'
    assert scopes()==manifest['policy_scopes'],'Policy changed after staging'
    rows=guard();active=[r['id'] for r in rows if r['active']]
    backup=STATE/'release-backups'/release.name;backup.mkdir(parents=True,mode=0o700);backup.chmod(0o700)
    for name in ('actplane','actplane.capabilities.json'):
        p=STATE/'bin'/name
        if p.exists():shutil.copy2(p,backup/name)
    shutil.copytree(STATE/'ui',backup/'ui')
    with sqlite3.connect(STATE/'demo.sqlite3') as source,sqlite3.connect(backup/'demo.sqlite3') as dest:source.backup(dest)
    result={'release':str(release),'backup':str(backup),'previous_active':active,'before_agents':[{k:r.get(k) for k in ('id','agent_type','pid','gate','active','policy_hash')} for r in rows]}
    drops=[];started=[]
    try:
        for ident in active:api('/api/agent-instances/'+ident+'/stop',{})
        subprocess.run(['systemctl','stop',UNITS['api'],UNITS['broker']],check=True,timeout=60)
        for name in ('actplane','actplane.capabilities.json'):install_file(release/'bin'/name,STATE/'bin'/name)
        (STATE/'bin').chmod(0o755);os.chown(STATE/'bin',0,0)
        for name in ('actplane','actplane.capabilities.json'):os.chown(STATE/'bin'/name,0,0)
        # Leave prior hashed assets available to already-open browser tabs.
        shutil.copytree(release/'frontend/dist',STATE/'ui',dirs_exist_ok=True)
        for role,unit in UNITS.items():
            drop=Path('/etc/systemd/system')/(unit+'.d')/DROP;assert not drop.exists();drop.parent.mkdir(exist_ok=True)
            drop.write_text('[Service]\nWorkingDirectory='+str(release)+'\nExecStart=\nExecStart=/opt/agentscope/.venv/bin/python '+str(release)+'/scripts/scope_systemd_exec.py '+role+'\n');drops.append(drop)
        subprocess.run(['systemctl','daemon-reload'],check=True)
        subprocess.run(['systemctl','start',UNITS['broker'],UNITS['api']],check=True,timeout=60);wait_ready()
        capability=api('/api/security/system/execution-capabilities');assert capability['file_suffix'] and capability['binary_sha256']==sha(release/'bin/actplane')
        for ident in active:
            row=api('/api/agent-instances/'+ident+'/start',{});assert row['active'] and row['runtime']['verified'];started.append(ident)
        assert scopes()==manifest['policy_scopes'],'Policy content changed during upgrade'
        after=[r for r in api('/api/agent-instances')['instances'] if r['mode']=='controlled']
        assert {r['id'] for r in after if r['active']}==set(active)
        assert other_ports()==manifest['other_ports'],'Another console listener changed'
        result.update(published=True,capabilities=api('/api/security/system/execution-capabilities'),after_agents=[{k:r.get(k) for k in ('id','agent_type','pid','gate','active','policy_hash')} for r in after],policy_scopes_unchanged=True,other_ports_unchanged=True)
    except Exception:
        for ident in started:
            try:api('/api/agent-instances/'+ident+'/stop',{})
            except Exception:pass
        subprocess.run(['systemctl','stop',UNITS['api'],UNITS['broker']],timeout=60)
        for drop in drops:drop.unlink(missing_ok=True)
        for name in ('actplane','actplane.capabilities.json'):
            if (backup/name).exists():install_file(backup/name,STATE/'bin'/name)
            else:(STATE/'bin'/name).unlink(missing_ok=True)
        shutil.copytree(backup/'ui',STATE/'ui',dirs_exist_ok=True)
        with sqlite3.connect(backup/'demo.sqlite3') as source,sqlite3.connect(STATE/'demo.sqlite3') as dest:source.backup(dest)
        subprocess.run(['systemctl','daemon-reload'],check=True);subprocess.run(['systemctl','start',UNITS['broker'],UNITS['api']],check=True,timeout=60);wait_ready()
        for ident in active:assert api('/api/agent-instances/'+ident+'/start',{})['active']
        result.update(published=False,rolled_back=True);raise
    finally:
        (backup/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps({'published':result.get('published',False),'evidence':str(backup/'result.json')}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',metavar='KERNEL_REPORT');p.add_argument('--apply',metavar='MANIFEST');args=p.parse_args()
    if args.stage:stage(args.stage)
    elif args.apply:apply(args.apply)
    else:p.print_help()

"""18003 API/UI overlay preserving the current Broker, engines and Agent PIDs.

Explicit root --stage/--apply only; verifies source/service/authority snapshots.
The existing release and private database/UI backup remain available to rollback.
"""
import argparse,hashlib,json,os,shutil,sqlite3,subprocess,time,urllib.request
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[1]
STATE=Path('/var/lib/agentscope-scope-demo')
UNIT='agentscope-scope-demo-api.service'
DROP=Path('/etc/systemd/system/'+UNIT+'.d/99-policy-semantics-20261011.conf')
def command(*args):return subprocess.check_output(args,text=True).strip()
def api(path):
    with urllib.request.urlopen('http://127.0.0.1:18003'+path,timeout=30) as r:return json.load(r)
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def files(root):
    return {str(p.relative_to(root)):sha(p) for p in Path(root).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
def service(unit):
    value={k:command('systemctl','show',unit,'-p',k,'--value') for k in ('MainPID','WorkingDirectory')}
    pid=value['MainPID']
    # daemon-reload resets ExecStart's displayed run timestamps even when the
    # same process keeps running. Compare process identity and argv instead.
    value['argv']=Path('/proc',pid,'cmdline').read_bytes().decode().split('\0')[:-1]
    value['start_ticks']=Path('/proc',pid,'stat').read_text().rsplit(') ',1)[1].split()[19]
    return value
def listeners():
    return [line.strip() for line in command('ss','-H','-lntp').splitlines() if line.split()[3].rsplit(':',1)[-1] in ('18000','18004')]
def authority():
    rows=api('/api/agent-instances')['instances']
    agents={r['id']:{k:r.get(k) for k in ('policy_hash','generation','pid','domain_id','active')} for r in rows if r['mode']=='controlled'}
    scopes={key:{k:page[k] for k in ('revision','document_hash','documents','phase')} for key,page in
        [('system',api('/api/security/system/dsl'))]+[(r['id'],api('/api/agent-instances/'+r['id']+'/dsl')) for r in rows if r['mode']=='controlled']}
    return {'agents':agents,'dsl_scopes':scopes,'system':{k:api('/api/security/system')[k] for k in ('revision','policy_hash')}}
def guard():
    with sqlite3.connect('file:'+str(STATE/'demo.sqlite3')+'?mode=ro',uri=True) as con:
        assert not con.execute("SELECT 1 FROM history_jobs WHERE status IN ('queued','running')").fetchone(),'Generation is busy'
        assert not con.execute("SELECT 1 FROM instance_dsl_scopes WHERE phase!='ready'").fetchone(),'Policy update is busy'
        assert not con.execute('SELECT 1 FROM instance_leases').fetchone(),'Native tool is busy'
        assert not con.execute("SELECT 1 FROM instance_dsl_proposals WHERE state='applying'").fetchone(),'Approval is busy'
    for r in api('/api/agent-instances')['instances']:
        if r.get('active'):
            assert r.get('gate') not in ('starting','updating')
            assert all(s.get('status') in ('idle','stored','stopped') for s in api('/api/agent-instances/'+r['id']+'/sessions')['sessions']),'Native session is busy'
def stage():
    assert os.geteuid()==0
    guard();live=Path(service(UNIT)['WorkingDirectory']);release=Path('/opt/agentscope-policy-semantics-'+time.strftime('%Y%m%d-%H%M%S'))
    assert live.parent==Path('/opt') and not release.exists()
    # The merged Broker must exactly preserve the currently running version.
    assert sha(SOURCE/'backend/broker/main.py')==sha(live/'backend/broker/main.py'),'Broker baseline mismatch'
    release.mkdir(mode=0o755)
    for folder in ('backend','scripts','integrations','bin','dsh'):
        if (live/folder).exists():shutil.copytree(live/folder,release/folder,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copytree(SOURCE/'backend/agentscope_app',release/'backend/agentscope_app',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copytree(SOURCE/'frontend/dist',release/'frontend/dist')
    for name in ('scope_service.py','scope_systemd_exec.py'):
        assert sha(SOURCE/'scripts'/name)==sha(live/'scripts'/name)
    manifest={'release':str(release),'previous_api':service(UNIT),'broker':service('agentscope-scope-demo-broker.service'),
        'previous_files':files(live/'backend/agentscope_app'),'release_files':files(release),
        'authority':authority(),'listeners':listeners()}
    p=release/'semantics-deployment.json';p.write_text(json.dumps(manifest,indent=2));p.chmod(0o600)
    print(json.dumps({'staged':str(release),'manifest':str(p)}))
def apply(path):
    assert os.geteuid()==0
    m=json.loads(Path(path).read_text());release=Path(m['release']);live=Path(m['previous_api']['WorkingDirectory'])
    assert release.parent==Path('/opt') and release.name.startswith('agentscope-policy-semantics-') and not DROP.exists()
    assert {k:v for k,v in files(release).items() if k!='semantics-deployment.json'}==m['release_files']
    assert service(UNIT)==m['previous_api'] and service('agentscope-scope-demo-broker.service')==m['broker']
    assert files(live/'backend/agentscope_app')==m['previous_files']
    guard();assert authority()==m['authority'] and listeners()==[line.strip() for line in m['listeners']]
    backup=STATE/'release-backups'/release.name;backup.mkdir(parents=True,mode=0o700)
    shutil.copytree(STATE/'ui',backup/'ui')
    with sqlite3.connect(STATE/'demo.sqlite3') as src,sqlite3.connect(backup/'demo.sqlite3') as dest:src.backup(dest)
    result={'release':str(release),'previous_api':m['previous_api'],'broker_unchanged':False,'authority_before':m['authority']}
    try:
        shutil.copytree(release/'frontend/dist',STATE/'ui',dirs_exist_ok=True)
        DROP.write_text('[Service]\nWorkingDirectory='+str(release)+'\nExecStart=\nExecStart=/opt/agentscope/.venv/bin/python '+str(release)+'/scripts/scope_systemd_exec.py api\n')
        subprocess.run(['systemctl','daemon-reload'],check=True)
        subprocess.run(['systemctl','restart',UNIT],check=True,timeout=30)
        assert api('/api/health')['ok']
        assert service('agentscope-scope-demo-broker.service')==m['broker']
        for attempt in range(25):
            if authority()==m['authority']:break
            time.sleep(.2)
        assert authority()==m['authority'],'Authority changed during API/UI publication'
        assert listeners()==[line.strip() for line in m['listeners']]
        assert sha(STATE/'ui/index.html')==sha(release/'frontend/dist/index.html')
        result.update(published=True,authority_after=authority(),broker_unchanged=True,other_ports_unchanged=True,current_api=service(UNIT))
    except Exception:
        DROP.unlink(missing_ok=True);shutil.copytree(backup/'ui',STATE/'ui',dirs_exist_ok=True)
        subprocess.run(['systemctl','daemon-reload'],check=True);subprocess.run(['systemctl','restart',UNIT],check=True,timeout=30)
        result.update(published=False,rolled_back=True)
        raise
    finally:
        p=backup/'result.json';p.write_text(json.dumps(result,indent=2));p.chmod(0o600)
        print(json.dumps({'published':result.get('published',False),'evidence':str(p)}))
if __name__=='__main__':
    p=argparse.ArgumentParser();group=p.add_mutually_exclusive_group(required=True);group.add_argument('--stage',action='store_true');group.add_argument('--apply');args=p.parse_args()
    stage() if args.stage else apply(args.apply)

#!/usr/bin/env python3
"""Deploy this change only to the isolated 18003 profile, preserving live intent."""
import json,os,shutil,sqlite3,subprocess,time,urllib.request
from pathlib import Path
SOURCE=Path(__file__).resolve().parents[1]
RUNTIME=Path('/opt/agentscope-task-archive-20261007')
STATE=Path('/var/lib/agentscope-scope-demo')
FILES=['backend/dsl_documents.py','backend/agentscope_app/main.py','backend/broker/instance_runtime.py','backend/broker/instance_runner.py']+['backend/agentscope_app/instances/'+s+'.py' for s in ('adapters','controller','store','system_policy','dsl_api','dsl_policy','sessions')]
UNITS=['agentscope-scope-demo-api.service','agentscope-scope-demo-broker.service']
def api(path,body=None):
    req=urllib.request.Request('http://127.0.0.1:18003'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=120) as response:return json.load(response)
def main():
    if os.getuid()!=0:raise SystemExit('Use root for this fixed isolated deployment')
    before=api('/api/agent-instances')['instances']
    resume=[r['id'] for r in before if r['mode']=='controlled' and r.get('active')]
    stamp=time.strftime('%Y%m%d-%H%M%S');backup=STATE/'deploy-backups'/('dsl-'+stamp);backup.mkdir(parents=True,mode=0o700)
    (backup/'intent.json').write_text(json.dumps({'resume':resume,'before':[{'id':r['id'],'mode':r['mode'],'gate':r.get('gate'),'active':r.get('active')} for r in before]}))
    for rel in FILES:
        old=RUNTIME/rel
        if old.exists():dest=backup/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old,dest)
    shutil.copytree(STATE/'ui',backup/'ui')
    subprocess.run(['systemctl','stop',UNITS[0]],check=True)
    with sqlite3.connect(STATE/'demo.sqlite3') as con,sqlite3.connect(backup/'demo.sqlite3') as dest:con.backup(dest)
    subprocess.run(['systemctl','stop',UNITS[1]],check=True)
    for rel in FILES:
        dest=RUNTIME/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(SOURCE/rel,dest);os.chown(dest,0,0);dest.chmod(0o644)
    binary=RUNTIME/'backend/dsl-adapter/target/release/agentscope-dsl-adapter';binary.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(SOURCE/'backend/dsl-adapter/target/release/agentscope-dsl-adapter',binary);os.chown(binary,0,0);binary.chmod(0o755)
    shutil.copytree(SOURCE/'frontend/dist',STATE/'ui',dirs_exist_ok=True)
    subprocess.run(['systemctl','start',UNITS[1]],check=True);subprocess.run(['systemctl','start',UNITS[0]],check=True)
    for ident in resume:
        result=api('/api/agent-instances/'+ident+'/start',{})
        print(json.dumps({'restored':ident,'verified':result.get('runtime',{}).get('verified')},ensure_ascii=False))
    after=api('/api/agent-instances')['instances']
    assert all(next(r for r in after if r['id']==ident).get('active') for ident in resume)
    assert not any(r.get('active') and r['id'] not in resume for r in after if r['mode']=='controlled')
    print(json.dumps({'backup':str(backup),'restored_count':len(resume),'health':api('/api/health')},ensure_ascii=False))
if __name__=='__main__':main()

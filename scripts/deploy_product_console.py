#!/usr/bin/env python3
"""Fixed 18003 presentation deployment; never restart Broker or native Agents.

By default produce an inventory only. --apply requires an explicit JSON list of
{kind,record_id} retention decisions, backed up privately with the old runtime.
"""
import argparse,hashlib,json,os,shutil,sqlite3,subprocess,time,urllib.request
from pathlib import Path
SOURCE=Path(__file__).resolve().parents[1]
RUNTIME=Path('/opt/agentscope-task-archive-20261007')
STATE=Path('/var/lib/agentscope-scope-demo')
UNIT='agentscope-scope-demo-api.service'
FILES=['backend/requirements.txt']+['backend/agentscope_app/'+p for p in ('main.py','db.py','console.py','audit_identity.py','archive/projection.py','history/api.py','history/catalog.py','history/catalog_api.py','history/generations.py','instances/dsl_policy.py','instances/sessions.py','instances/session_names.py')]
def api(path):
    with urllib.request.urlopen('http://127.0.0.1:18003'+path,timeout=20) as response:return json.load(response)
def live(rows):return {r['id']:(r.get('pid'),r.get('generation'),r.get('active'),r.get('connected')) for r in rows if r['mode']=='controlled'}
def counts(con):return {t:con.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('tasks','strategies','agent_instances','instance_policy_receipts','history_generations')}
def ready():
    for _ in range(30):
        try:
            if api('/api/health').get('ok') is True:return
        except OSError:pass
        time.sleep(.3)
    raise RuntimeError('18003 API did not recover')
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--retention-manifest',type=Path);args=parser.parse_args()
    if os.getuid()!=0:raise SystemExit('Root required for this fixed runtime inventory/deployment')
    before=api('/api/agent-instances')['instances'];active=api('/api/dashboard')['active']
    if not args.apply:
        print(json.dumps({'controlled':live(before),'active_legacy_tasks':active}));return
    if not args.retention_manifest:raise SystemExit('An explicit retention manifest is required')
    records=json.loads(args.retention_manifest.read_text())
    assert isinstance(records,list) and all(set(r)=={'kind','record_id'} and r['kind'] in ('agent','task','strategy','generation') for r in records)
    for r in records:
        if r['kind']=='agent':assert any(a['id']==r['record_id'] and not a.get('active') and not a.get('connected') for a in before),'Cannot retain a live Agent'
        if r['kind']=='task':assert r['record_id'] not in {a.get('task_id',a.get('id')) for a in active},'Cannot retain a live legacy task'
    assert all((SOURCE/f).is_file() for f in FILES) and (SOURCE/'frontend/dist/index.html').is_file()
    backup=STATE/'deploy-backups'/('product-console-'+time.strftime('%Y%m%d-%H%M%S'));backup.mkdir(parents=True,mode=0o700)
    existed=[]
    for rel in FILES:
        old=RUNTIME/rel
        if old.is_file():
            existed.append(rel);dest=backup/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old,dest)
    shutil.copytree(STATE/'ui',backup/'ui')
    (backup/'retention-manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2));(backup/'retention-manifest.json').chmod(0o600)
    subprocess.run(['systemctl','stop',UNIT],check=True)
    reason='用户确认：旧实验与诊断资料保留后台，生产控制台不展示；来源记录不删除'
    newly=[]
    try:
        with sqlite3.connect(STATE/'demo.sqlite3') as con,sqlite3.connect(backup/'demo.sqlite3') as dest:
            con.backup(dest);prior=counts(con)
        (backup/'demo.sqlite3').chmod(0o600)
        for rel in FILES:
            dest=RUNTIME/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(SOURCE/rel,dest);os.chown(dest,0,0);dest.chmod(0o644)
        shutil.copytree(SOURCE/'frontend/dist',STATE/'ui',dirs_exist_ok=True)
        from datetime import datetime,timezone
        with sqlite3.connect(STATE/'demo.sqlite3') as con:
            con.execute('CREATE TABLE IF NOT EXISTS console_retained_records(kind TEXT NOT NULL,record_id TEXT NOT NULL,reason TEXT NOT NULL,retained_at TEXT NOT NULL,PRIMARY KEY(kind,record_id))')
            stamp=datetime.now(timezone.utc).isoformat()
            for r in records:
                if not con.execute('SELECT 1 FROM console_retained_records WHERE kind=? AND record_id=?',(r['kind'],r['record_id'])).fetchone():newly.append(r)
                con.execute('INSERT OR IGNORE INTO console_retained_records VALUES(?,?,?,?)',(r['kind'],r['record_id'],reason,stamp))
        subprocess.run(['systemctl','start',UNIT],check=True);ready()
        after=api('/api/agent-instances')['instances'];assert live(before)==live(after),'Native Agent runtime changed'
        with sqlite3.connect(STATE/'demo.sqlite3') as con:assert counts(con)==prior,'Source records changed'
        proof={'backup':str(backup),'retained':{k:sum(r['kind']==k for r in records) for k in ('agent','task','strategy','generation')},'source_counts':prior,'native_runtime_unchanged':True,'ui_sha256':hashlib.sha256((STATE/'ui/index.html').read_bytes()).hexdigest()}
        (backup/'receipt.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2));print(json.dumps(proof,ensure_ascii=False))
    except Exception:
        subprocess.run(['systemctl','stop',UNIT],check=True)
        for rel in FILES:
            dest=RUNTIME/rel
            if rel in existed:shutil.copy2(backup/rel,dest)
            elif dest.is_file():dest.unlink()
        shutil.copytree(backup/'ui',STATE/'ui',dirs_exist_ok=True)
        with sqlite3.connect(STATE/'demo.sqlite3') as con:
            for r in newly:con.execute('DELETE FROM console_retained_records WHERE kind=? AND record_id=?',(r['kind'],r['record_id']))
        subprocess.run(['systemctl','start',UNIT],check=True)
        raise
if __name__=='__main__':main()

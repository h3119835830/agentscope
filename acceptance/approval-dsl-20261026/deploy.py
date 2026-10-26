"""Back up the live database and deploy the tested API/UI, without applying policy."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
import urllib.request

STAGE=Path('/opt/agentscope/releases/approval-dsl-20261026.FMi589')
EXPECTED=Path('/opt/agentscope/releases/individual-approval-final-20261026.KweDkQ')
CURRENT=Path('/opt/agentscope/current')
AGENT='instance-e86886cee6e04d9e'
FILES=['backend/agentscope_app/instances/approval_decisions.py','backend/agentscope_app/instances/approval_configuration_records.py']

def pid(unit):
 return subprocess.check_output(['systemctl','show',unit,'-p','MainPID','--value'],text=True).strip()

def get(path):
 with urllib.request.urlopen('http://127.0.0.1:18003'+path,timeout=15) as response:return json.load(response)

def health():
 for _ in range(40):
  try:
   if get('/api/health').get('ok'):return
  except Exception:pass
  time.sleep(.5)
 raise RuntimeError('API health did not recover')

def identity():
 row=get('/api/agent-instances/'+AGENT)
 assert row['connected'] and row['verified'] and row['gate']=='open'
 return {key:row[key] for key in ('id','pid','generation','policy_hash')}

def main():
 assert os.geteuid()==0 and CURRENT.resolve()==EXPECTED
 assert STAGE.parent==Path('/opt/agentscope/releases') and STAGE.is_dir()
 broker=pid('agentscope-preview-broker.service');assert broker!='0'
 before=identity()
 decision_before={r["id"]:[r["status"],r["approval_status"]] for r in get("/api/console/approvals")["records"]}
 dsl_before=get("/api/console/agents/"+AGENT+"/dsl")["document_hash"]
 # Read only the service's path configuration. Never print its environment.
 environment=dict(item.split('=',1) for item in Path('/proc/'+pid('agentscope-preview.service')+'/environ').read_bytes().decode().split('\0') if '=' in item)
 state=Path(environment.get('AGENTSCOPE_STATE_DIR',str(Path(environment.get('HOME','/root'))/'.local/state/agentscope')))
 database=Path(environment.get('AGENTSCOPE_DB',str(state/'agentscope.sqlite3')))
 assert database.is_file()
 backup=STAGE/'pre-approval-dsl.sqlite3'
 assert not backup.exists()
 with sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(backup) as target:
  stored=source.execute('SELECT proposal_hash,scope_id,state FROM instance_dsl_proposals WHERE id=?',('8c7c3fb5d0c0425dab0db657fd6c9f0a',)).fetchone()
  current=get('/api/console/approvals/8c7c3fb5d0c0425dab0db657fd6c9f0a')
  assert stored and stored[0]==current['candidate_hash'] and stored[1]==AGENT and stored[2] in ('pending','superseded') and stored[2]==current['status']
  source.backup(target)
 backup.chmod(0o600)
 files=FILES+[str(path.relative_to(STAGE)) for path in (STAGE/'frontend/dist').rglob('*') if path.is_file()]
 assert all((STAGE/path).is_file() for path in files) and (STAGE/'frontend/dist/index.html').is_file()
 manifest={'previous':str(EXPECTED),'release':str(STAGE),'broker_pid':broker,'before_agent':before,'database_backup_created':True,
  'files':{path:hashlib.sha256((STAGE/path).read_bytes()).hexdigest() for path in files}}
 pending=Path('/opt/agentscope/current.pending-approval-dsl')
 assert not pending.exists() and not pending.is_symlink()
 pending.symlink_to(STAGE,target_is_directory=True);os.replace(pending,CURRENT)
 try:
  subprocess.run(['systemctl','restart','agentscope-preview.service'],check=True,timeout=35)
  health();assert pid('agentscope-preview-broker.service')==broker
  after=identity();assert after==before
  decision_after={r["id"]:[r["status"],r["approval_status"]] for r in get("/api/console/approvals")["records"]}
  assert decision_before==decision_after
  assert get("/api/console/agents/"+AGENT+"/dsl")["document_hash"]==dsl_before
  manifest.update(approval_states_unchanged=True,dsl_hash_unchanged=True)
  manifest.update(published=True,api_pid=pid('agentscope-preview.service'),after_agent=after)
 except Exception:
  pending.symlink_to(EXPECTED,target_is_directory=True);os.replace(pending,CURRENT)
  subprocess.run(['systemctl','restart','agentscope-preview.service'],check=True,timeout=35)
  health();manifest.update(published=False,rolled_back=True)
  raise
 finally:
  (STAGE/'approval-dsl-deployment.json').write_text(json.dumps(manifest,indent=2))
  print(json.dumps({key:value for key,value in manifest.items() if key!='files'}))

if __name__=='__main__':main()

"""Publish only the tested static layout; keep API, Broker and Agent unchanged."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request

CURRENT=Path('/opt/agentscope/current')
EXPECTED=Path('/opt/agentscope/releases/approval-dsl-20261026.FMi589')
STAGE=Path('/opt/agentscope/releases/approval-dsl-ui-20261026.xPXgKj')
AGENT='instance-e86886cee6e04d9e'

def get(path):
    with urllib.request.urlopen('http://127.0.0.1:18003'+path,timeout=30) as response:return json.load(response)

def pid(unit):return subprocess.check_output(['systemctl','show',unit,'-p','MainPID','--value'],text=True).strip()

def snapshot():
    agent=get('/api/agent-instances/'+AGENT)
    return {'agent':{k:agent[k] for k in ('id','pid','generation','policy_hash')},
            'approvals':{r['id']:[r['status'],r['approval_status']] for r in get('/api/console/approvals')['records']},
            'dsl_hash':get('/api/console/agents/'+AGENT+'/dsl')['document_hash'],
            'api_pid':pid('agentscope-preview.service'),'broker_pid':pid('agentscope-preview-broker.service')}

assert os.geteuid()==0 and CURRENT.resolve()==EXPECTED and STAGE.is_dir()
tests=(STAGE/'frontend-tests.log').read_text()
assert '# pass 448' in tests and '# fail 0' in tests
assert 'built in' in (STAGE/'build.log').read_text()
for name in ('approval_decisions','approval_configuration_records'):
    relative=Path('backend/agentscope_app/instances')/(name+'.py')
    assert (STAGE/relative).read_bytes()==(EXPECTED/relative).read_bytes()
before=snapshot();pending=Path('/opt/agentscope/current.pending-approval-dsl-ui')
assert not pending.exists() and not pending.is_symlink()
pending.symlink_to(STAGE,target_is_directory=True);os.replace(pending,CURRENT)
try:
    assert get('/api/health')['ok'] and snapshot()==before
except Exception:
    pending.symlink_to(EXPECTED,target_is_directory=True);os.replace(pending,CURRENT)
    raise
manifest={'release':str(STAGE),'previous':str(EXPECTED),'static_only':True,'published':True,
          'processes_and_policy_states_unchanged':True,'identity':before['agent'],
          'api_pid':before['api_pid'],'broker_pid':before['broker_pid'],
          'index_sha256':hashlib.sha256((STAGE/'frontend/dist/index.html').read_bytes()).hexdigest()}
(STAGE/'approval-dsl-static-deployment.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest))

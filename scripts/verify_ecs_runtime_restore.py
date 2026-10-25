"""Verify original policy and live isolation survive an API-only restart."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from ecs_three_stage_activate import api

ident='instance-e86886cee6e04d9e'
before=api('/api/agent-instances/'+ident)
if '--restart-api' in sys.argv:
    subprocess.run(['systemctl','restart','agentscope-preview.service'],check=True)
    for _ in range(30):
        try:
            if api('/api/health')['ok']:break
        except OSError:time.sleep(1)
    else:raise RuntimeError('API readiness failed')
time.sleep(4) # one bounded observer cycle, not a substitute for checks below
row=api('/api/agent-instances/'+ident)
assert row['gate']=='open' and row['connected'] and row['runtime']['verified']
assert row['policy_hash']=='fa762610581e4cbad9ef5cf96408010288b514a213ce3380695f03830d28c815'
assert row['runtime']['pid']==before['runtime']['pid'] and row['generation']==before['generation']
assert row['product_status']['loading']['state']=='loaded'
assert api('/api/agent-instances/instance-751ad8a6165f4357')['gate']!='open'
services={s:subprocess.check_output(['systemctl','is-active',s],text=True).strip() for s in ('agentscope-preview.service','agentscope-preview-broker.service')}
assert set(services.values())=={'active'}
pid=int(subprocess.check_output(['systemctl','show','agentscope-preview.service','-p','MainPID','--value'],text=True))
def identity(value):
    result={k:v.strip() for k,v in (line.split(':',1) for line in Path('/proc',str(value),'status').read_text().splitlines() if ':' in line)}
    return {k:result[k] for k in ('Uid','Gid','CapEff','CapAmb','NoNewPrivs')}
api_identity=identity(pid)
children=Path('/proc',str(pid),'task',str(pid),'children').read_text().split()
reader=next(int(p) for p in children if b'reference_reader_channel.py' in Path('/proc',p,'cmdline').read_bytes())
reader_identity=identity(reader)
assert api_identity['Uid']!=reader_identity['Uid']
for value in (api_identity,reader_identity):
    assert int(value['CapEff'],16)==int(value['CapAmb'],16)==0 and value['NoNewPrivs']=='1'
result={'main_restored':True,'main_policy_unchanged':True,'main_generation':row['generation'],'main_pid':row['runtime']['pid'],
    'api_restart_preserved_agent':True,'test_instance_stopped':True,'loading':row['product_status']['loading'],
    'verification':{k:row['runtime'].get('verification',{}).get(k) for k in ('passed','protected_integrity','grants_verified','network_verified')},
    'services':services,'api_identity':api_identity,'reader_identity':reader_identity,
    'engine_sha256':hashlib.sha256(Path('/usr/local/bin/actplane').read_bytes()).hexdigest()}
Path('/var/lib/agentscope/preview/three-stage-restored.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))

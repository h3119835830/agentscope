"""Restore the last working ECS engine/Broker without reverting API evidence."""
import argparse
from pathlib import Path
import subprocess
import time
import uuid
from ecs_three_stage_activate import api

parser=argparse.ArgumentParser();parser.add_argument('instance_id');args=parser.parse_args()
old=Path('/opt/agentscope/runtime/broker/3cac632-ecs-dsh-control6-20261024')
engine=Path('/opt/agentscope/runtime/actplane/0.1.8-fix-20261024/actplane')
row=api('/api/agent-instances/'+args.instance_id)
if row['mode']!='controlled' or not engine.is_file() or not (old/'backend/broker/main.py').is_file():raise ValueError('Rollback target not verified')
for item in api('/api/agent-instances')['instances']:
    if item['mode']=='controlled' and item['gate']=='open':api('/api/agent-instances/'+item['id']+'/stop',{})
link=Path('/usr/local/bin')/('actplane-'+uuid.uuid4().hex+'.link');link.symlink_to(engine);link.replace('/usr/local/bin/actplane')
Path('/etc/systemd/system/agentscope-preview-broker.service.d/40-three-stage.conf').write_text(
    '[Service]\nWorkingDirectory='+str(old)+'\nEnvironment=PYTHONPATH='+str(old/'backend')+'\nExecStart=\nExecStart=/opt/agentscope/current/.venv/bin/python '+str(old/'backend/broker/main.py')+'\n')
subprocess.run(['systemctl','daemon-reload'],check=True);subprocess.run(['systemctl','restart','agentscope-preview-broker.service'],check=True)
result=api('/api/agent-instances/'+args.instance_id+'/start',{})
print({'restored_instance':args.instance_id,'gate':result['gate'],'policy_unchanged':result['policy_hash']==row['policy_hash']})

"""Activate a staged ECS release, preserving each existing controlled connection."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.request

BASE='http://127.0.0.1:18003'
def api(path,body=None):
    request=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=150) as response:return json.load(response)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--engine',type=Path)
    parser.add_argument('--instance')
    args=parser.parse_args()
    rows=api('/api/agent-instances')['instances']
    restore=[r['id'] for r in rows if r['mode']=='controlled' and r['gate']=='open']
    print(json.dumps({'restore':restore}),flush=True)
    for ident in restore:api('/api/agent-instances/'+ident+'/stop',{})
    target=Path('/etc/systemd/system/agentscope-preview-broker.service.d/40-three-stage.conf')
    if args.engine:
        engine=args.engine.resolve(strict=True)
        if not engine.is_file() or not str(engine).startswith('/opt/agentscope/runtime/actplane/'):
            raise ValueError('Engine must be an existing versioned runtime artifact')
        temporary=Path('/usr/local/bin/actplane-three-stage.link')
        if temporary.exists() or temporary.is_symlink():raise ValueError('Unexpected temporary engine link')
        temporary.symlink_to(engine);temporary.replace('/usr/local/bin/actplane')
    target.write_text('[Service]\nWorkingDirectory=/opt/agentscope/current\nEnvironment=PYTHONPATH=/opt/agentscope/current/backend\nExecStart=\nExecStart=/opt/agentscope/current/.venv/bin/python /opt/agentscope/current/backend/broker/main.py\n')
    Path('/etc/systemd/system/agentscope-preview.service.d/50-native-pi.conf').write_text('[Service]\nEnvironment=AGENTSCOPE_POLICY_AGENT_PROVIDER=native-pi\nEnvironment=AGENTSCOPE_POLICY_LIFECYCLE_WORKER=1\n')
    subprocess.run(['systemctl','daemon-reload'],check=True)
    for service in ('agentscope-preview-broker.service','agentscope-preview.service'):
        subprocess.run(['systemctl','restart',service],check=True)
    for _ in range(30):
        try:
            if api('/api/health')['ok']:break
        except OSError:time.sleep(1)
    else:raise RuntimeError('API did not become ready; instances remain stopped')
    for ident in ([args.instance] if args.instance else restore):
        value=api('/api/agent-instances/'+ident+'/start',{})
        print(json.dumps({'instance':ident,'gate':value.get('gate',value.get('instance',{}).get('gate'))}),flush=True)
    print(json.dumps({'activated':True}),flush=True)
if __name__=='__main__':main()

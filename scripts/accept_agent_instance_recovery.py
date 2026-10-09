"""Root acceptance of 18003 control loss; never touches other Demo services."""
import json,pathlib,subprocess,time,urllib.request
BASE='http://127.0.0.1:18003/api/agent-instances/'
ROOT=pathlib.Path('/var/lib/agentscope-scope-demo')
IDS=json.loads((ROOT/'instance-acceptance.json').read_text())
OUT=ROOT/'instance-recovery-evidence.json'
def system(*args):subprocess.run(['/usr/bin/systemctl',*args],check=True)
def ready():
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        try:
            with urllib.request.urlopen('http://127.0.0.1:18003/api/health',timeout=1) as r:
                if r.status==200:return
        except OSError:time.sleep(.1)
    raise RuntimeError('18003 API did not become ready')
def api(i,suffix='',body=None):
    req=urllib.request.Request(BASE+i+suffix,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=150) as response:return json.load(response)
def alive(pid):
    try:
        value=pathlib.Path('/proc',str(pid),'stat').read_text();return value[value.rindex(')')+2:].split()[0] not in ('Z','X')
    except FileNotFoundError:return False
def wait_dead(rows):
    started=time.monotonic()
    while any(alive(row['pid']) for row in rows.values()):
        if time.monotonic()-started>15:raise AssertionError('Controlled process survived the heartbeat deadline')
        time.sleep(.1)
    return round(time.monotonic()-started,2)
evidence={}
try:
    # Graceful upgrade first: old manifests do not acquire new authority.
    for i in IDS.values():api(i,'/stop',{})
    system('restart','agentscope-scope-demo-broker.service')
    system('start','agentscope-scope-demo-api.service');ready()
    for kind,i in IDS.items():
        row=api(i,'/start',{});assert row['active'] and row['host_id'] and row['boot_id']
        print(kind,'new host/boot identity bound',flush=True)
    rows={kind:api(i) for kind,i in IDS.items()}
    system('stop','agentscope-scope-demo-api.service')
    elapsed=wait_dead(rows)
    system('start','agentscope-scope-demo-api.service');ready()
    evidence['api_loss']={'all_controlled_processes_terminated':True,'seconds':elapsed,'instances':{}}
    for kind,i in IDS.items():
        before=api(i);assert not before['active']
        new=api(i,'/start',{});assert new['active'] and new['generation']!=rows[kind]['generation']
        evidence['api_loss']['instances'][kind]={'old_pid':rows[kind]['pid'],'new_pid':new['pid'],'old_generation':rows[kind]['generation'],'new_generation':new['generation'],'paused_until_reverified':True}
    print('API loss: heartbeat termination and reverified recovery PASS',flush=True)
    OUT.write_text(json.dumps(evidence,indent=2));OUT.chmod(0o600)
    rows={kind:api(i) for kind,i in IDS.items()}
    system('kill','--kill-whom=main','--signal=KILL','agentscope-scope-demo-broker.service')
    elapsed=wait_dead(rows)
    system('reset-failed','agentscope-scope-demo-broker.service')
    system('start','agentscope-scope-demo-broker.service')
    # API BindsTo=Broker intentionally stops it on Broker loss.
    system('start','agentscope-scope-demo-api.service');ready()
    assert all(not api(i)['active'] for i in IDS.values())
    evidence['broker_loss']={'independent_relay_terminated_processes':True,'seconds':elapsed,'instances':{}}
    for kind,i in IDS.items():
        assert not pathlib.Path(rows[kind]['process_cgroup']).exists()
        new=api(i,'/start',{});assert new['active'] and new['generation']!=rows[kind]['generation']
        sessions=api(i,'/sessions')['sessions'];assert sessions
        evidence['broker_loss']['instances'][kind]={'old_cgroup_removed':True,'old_pid':rows[kind]['pid'],'new_pid':new['pid'],'old_generation':rows[kind]['generation'],'new_generation':new['generation'],'own_native_sessions_retained':len(sessions)}
    print('Broker SIGKILL: independent relay, abandoned-domain cleanup and recovery PASS',flush=True)
    OUT.write_text(json.dumps(evidence,indent=2));OUT.chmod(0o600)
finally:
    system('start','agentscope-scope-demo-broker.service','agentscope-scope-demo-api.service')

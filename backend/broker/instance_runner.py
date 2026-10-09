#!/usr/bin/env python3
"""Root-only relay. Agent children enter a filesystem namespace before UID drop."""
import json, os, stat, subprocess, sys, threading, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agentscope_app.instances.mapping import translate

def sandbox(config,probe=False):
    state=config['state']
    args=['/usr/bin/bwrap','--die-with-parent','--unshare-user','--unshare-pid','--unshare-ipc','--unshare-uts','--cap-drop','ALL',
          '--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64',
          '--proc','/proc','--dev','/dev','--dir','/etc','--ro-bind','/etc/ssl','/etc/ssl','--ro-bind','/etc/resolv.conf','/etc/resolv.conf',
          '--ro-bind','/etc/hosts','/etc/hosts','--ro-bind','/etc/nsswitch.conf','/etc/nsswitch.conf',
          '--ro-bind','/etc/passwd','/etc/passwd','--ro-bind','/etc/group','/etc/group',
          '--ro-bind','/opt/agentscope/bin','/opt/agentscope/bin',
          '--ro-bind','/var/lib/agentscope-rq5-v1/task-python','/opt/task-python',
          '--bind',state,state,'--bind',config['home'],config['home'],'--symlink',state+'/tmp','/tmp']
    for target in config['resources']: args += ['--bind' if probe else '--ro-bind',target,translate(target,config['resources'])]
    for rule in ([] if probe else config['policy']['rules']):
        if rule['action']=='write' and rule['effect']=='allow': args += ['--bind',rule['target'],translate(rule['target'],config['resources'])]
    # Denies override grants. Separate mount points also prevent hardlink aliases.
    for rule in ([] if probe else config['policy']['rules']):
        target=translate(rule['target'],config['resources']) if rule['action'] in ('read','write') else rule['target']
        if rule['action']=='write' and rule['effect']=='deny': args += ['--ro-bind',rule['target'],target]
        if rule['action']=='read' and rule['effect']=='deny' and Path(rule['target']).is_dir():
            args += ['--tmpfs',target,'--chmod','000',target]
    if config['agent_type']=='dsh': args += ['--ro-bind','/opt/agentscope/dsh','/opt/agentscope/dsh']
    else:
        args += ['--ro-bind',config['hermes_root'],config['hermes_root'],'--ro-bind',config['hermes_dist'],config['hermes_dist']]
        args += ['--ro-bind',config['home']+'/plugins',config['home']+'/plugins']
        for name in ('config.yaml','.env','auth.json'):
            p=Path(config['home'])/name
            if p.is_file(): args += ['--ro-bind',str(p),str(p)]
    args += ['--uid',str(config['uid']),'--gid',str(config['gid']),'--chdir',translate(config['resources'][0],config['resources']),'--']
    return args

PROBE = """
import json,os,socket,sys
from pathlib import Path
result=[]
for value in json.loads(os.environ['PROBE_PATHS']):
    try:
        fd=os.open(value,os.O_WRONLY|os.O_APPEND)
        if Path(value).name=='.agentscope-permission-probe': os.write(fd,b'probe-write\\n')
        os.close(fd)
        result.append({'path':value,'denied':False})
    except OSError as e:result.append({'path':value,'denied':True,'errno':e.errno})
reads=[]
for value in json.loads(os.environ['PROBE_READS']):
    try:
        fd=os.open(value,os.O_RDONLY);os.close(fd);reads.append({'path':value,'denied':False})
    except OSError as e:reads.append({'path':value,'denied':True,'errno':e.errno})
connections=[]
for host,port in json.loads(os.environ['PROBE_NETWORK']):
    family=socket.AF_INET6 if ':' in host else socket.AF_INET
    with socket.socket(family,socket.SOCK_STREAM) as s:
        s.settimeout(1)
        try:s.connect((host,port));connections.append({'host':host,'port':port,'connected':True})
        except OSError as e:connections.append({'host':host,'port':port,'connected':False,'errno':e.errno})
print(json.dumps({'pid':os.getpid(),'writes':result,'reads':reads,'connections':connections}),flush=True)
sys.stdin.read(1)
"""
HOLD = """
import os,mmap,json,time,signal
fd=os.open(os.environ['HOLD_FILE'],os.O_RDWR)
try:
    mapping=mmap.mmap(fd,0,access=mmap.ACCESS_WRITE);mapped=True;mapping_errno=None
except OSError as error:
    mapped=False;mapping_errno=error.errno
child=os.fork()
if child==0:
    os.setsid();signal.signal(signal.SIGTERM,signal.SIG_IGN)
    while True:time.sleep(1)
print(json.dumps({'pid':os.getpid(),'child_pid':child,'fd':True,'writable_mapping':mapped,'mapping_errno':mapping_errno}),flush=True)
while True:time.sleep(1)
"""
def main():
    handoff=Path(sys.argv[1])
    log=os.open(handoff.parent/'native.log',os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NOFOLLOW,0o600)
    os.dup2(log,1);os.dup2(log,2);os.close(log)
    fd=os.open(handoff,os.O_RDONLY|os.O_NOFOLLOW)
    info=os.fstat(fd)
    if info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o600: return 78
    with os.fdopen(fd) as stream: config=json.load(stream)
    handoff.unlink()
    env={'PATH':'/opt/task-python/bin:/opt/agentscope/bin:/usr/local/bin:/usr/bin:/bin','HOME':config['state'],'USER':'happy','LOGNAME':'happy','LANG':'C.UTF-8',
         'TMPDIR':config['state']+'/tmp','PYTHONDONTWRITEBYTECODE':'1','NO_PROXY':'*','no_proxy':'*',
         'AGENTSCOPE_INSTANCE_ID':config['instance_id'],'AGENTSCOPE_INSTANCE_TOKEN':config['token'],'AGENTSCOPE_GENERATION':config['generation'],
         'AGENTSCOPE_INSTANCE_URL':config['api_url'],'AGENTSCOPE_NATIVE_TOKEN':config['native_token'],'AGENTSCOPE_NATIVE_PORT':str(config['web_port']+100),
         'AGENTSCOPE_RESOURCES':json.dumps([translate(p,config['resources']) for p in config['resources']]),'AGENTSCOPE_WEB_PORT':str(config['web_port'])}
    if config['agent_type']=='dsh':
        env['DSH_HOME']=config['home']
        argv=[config['dsh'],'web','--host','127.0.0.1','--port',str(config['web_port']),'--no-open']
    else:
        env.update(HERMES_HOME=config['home'],HERMES_WEB_DIST=config['hermes_dist'],PYTHONPATH=config['hermes_root'],HERMES_ENABLE_PROJECT_PLUGINS='0')
        # Native plugin loader and CLI, without core/prompt modifications.
        code='from hermes_cli.plugins import discover_plugins; discover_plugins(); from hermes_cli.main import main; main()'
        argv=[config['hermes_root']+'/venv/bin/python','-c',code,'dashboard','--isolated','--no-open','--skip-build','--host','127.0.0.1','--port',str(config['web_port'])]
    def demote():
        os.setgroups([]);os.setgid(config['gid']);os.setuid(config['uid'])
    def fixed_program(program,values,hold=False):
        child=subprocess.Popen([*sandbox(config,probe=True),'/usr/bin/python3','-c',program],env=values,preexec_fn=demote,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        line=child.stdout.readline()
        if not line: raise RuntimeError(child.stderr.read()[-1000:])
        result=json.loads(line)
        def host_pid(namespace_pid):
            matches=[]
            for item in (Path(config['process_cgroup'])/'cgroup.procs').read_text().split():
                try:
                    status=(Path('/proc')/item/'status').read_text().splitlines()
                    ids=next(v for v in status if v.startswith('NSpid:')).split()[1:]
                    if len(ids)>1 and int(ids[-1])==namespace_pid and program.encode() in (Path('/proc')/item/'cmdline').read_bytes(): matches.append(int(item))
                except (OSError,StopIteration): pass
            if len(matches)!=1: raise RuntimeError('Fixed probe namespace PID is ambiguous')
            return matches[0]
        result['pid']=host_pid(result['pid'])
        if hold: result['child_pid']=host_pid(result['child_pid'])
        else:
            child.stdin.write('1');child.stdin.flush();child.wait(timeout=5)
            if child.returncode: raise RuntimeError('Fixed probe process failed')
            for key in ('writes','reads'):
                for item in result[key]:
                    item['execution_path']=item['path'];item['path']=translate(item['path'],config['resources'],reverse=True)
        return result
    # Do not carry a host-file descriptor through the mount namespace: its
    # path cannot be resolved by LSM there. The trusted relay drains a pipe.
    env['PYTHONUNBUFFERED']='1'
    process=subprocess.Popen([*sandbox(config),*argv],env=env,preexec_fn=demote,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    def drain():
        for chunk in iter(lambda:process.stdout.read1(8192),b''):
            os.write(1,chunk)
    threading.Thread(target=drain,daemon=True).start()
    req=Path(config['request_path']); last=None
    while process.poll() is None:
        try:
            tick=json.loads(Path(config['heartbeat_path']).read_text())
            if tick['generation']!=config['generation'] or time.monotonic()-tick['at']>=8: raise ValueError('Heartbeat expired')
        except (OSError,ValueError,KeyError):
            # Runs outside the Broker service's cgroup. If that service dies,
            # independently kill this exact root-registered execution scope.
            (Path(config['process_cgroup'])/'cgroup.kill').write_text('1')
            return 75
        if req.exists():
            try:
                value=json.loads(req.read_text())
                if value['request_id']!=last:
                    last=value['request_id']
                    if value.get('operation')=='hold':
                        target=Path(value['path'])
                        grants=[Path(r['target']) for r in config['policy']['rules'] if r['action']=='write' and r['effect']=='allow']
                        if target.name!='.agentscope-held-handle-probe' or not any(p==target.parent or p in target.parents for p in grants): raise ValueError('Unregistered held-handle probe')
                        held=fixed_program(HOLD,{'HOLD_FILE':translate(str(target),config['resources'])},hold=True)
                        output={'request_id':last,'ok':True,'hold':held}
                        p=Path(config['result_path']);tmp=p.with_suffix('.tmp')
                        tmp.write_text(json.dumps(output));tmp.chmod(0o600);os.replace(tmp,p)
                        continue
                    if value.get('operation')!='probe': raise ValueError('Unavailable relay operation')
                    targets=value['paths']
                    registered_denies={r['target'] for r in config['policy']['rules'] if r['action']=='write' and r['effect']=='deny'}
                    if any(not (Path(p).name=='.agentscope-permission-probe' and any(Path(base)==Path(p).parent or Path(base) in Path(p).parents for base in config['resources'])) and p not in registered_denies for p in targets): raise ValueError('Unregistered probe')
                    connections=value.get('connections',[])
                    if any(host not in ('127.0.0.1','::1') or port not in (config['web_port']+200,config['web_port']+300) for host,port in connections): raise ValueError('Unregistered network probe')
                    # Fixed probe deliberately bypasses mount restrictions to test ActPlane itself.
                    read_paths=value.get('reads',[])
                    read_denies=[Path(r['target']) for r in config['policy']['rules'] if r['action']=='read' and r['effect']=='deny']
                    if any(not any(Path(p)==base or base in Path(p).parents for base in read_denies) for p in read_paths): raise ValueError('Unregistered read probe')
                    probe=fixed_program(PROBE,{'PROBE_PATHS':json.dumps([translate(p,config['resources']) for p in targets]),'PROBE_READS':json.dumps([translate(p,config['resources']) for p in read_paths]),'PROBE_NETWORK':json.dumps(connections)})
                    output={'request_id':last,'ok':True,'probe':probe}
                    p=Path(config['result_path']);tmp=p.with_suffix('.tmp')
                    tmp.write_text(json.dumps(output));tmp.chmod(0o600);os.replace(tmp,p)
            except Exception as error:
                p=Path(config['result_path'])
                p.write_text(json.dumps({'request_id':last,'ok':False,'error':type(error).__name__+': '+str(error)[:300]}));p.chmod(0o600)
        time.sleep(.1)
    return process.wait()
if __name__=='__main__': raise SystemExit(main())

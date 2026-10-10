"""Allowlisted controlled DSH/Hermes lifecycle. Imported only by the root Broker."""
import hashlib, hmac, http.server, ipaddress, json, os, pwd, re, secrets, shutil, signal, socket, subprocess, threading, time, urllib.request
import stat
from pathlib import Path
from agentscope_app.instances.policy import canonical, clean_resources, digest
from agentscope_app.instances.mapping import translate,resource_records
from agentscope_app.workspaces import broker_instances as legacy
from dsl_documents import prepare as prepare_documents, fingerprint as dsl_fingerprint

HERMES_ENTRY=Path('/home/happy/.local/bin/hermes')
HERMES_ROOT=Path('/home/happy/.hermes/hermes-agent-v020')
HERMES_DIST=Path('/var/lib/agentscope-scope-demo/native-build/hermes-dist')
REGEX=re.compile(r'^instance-[a-f0-9]{16}$')
RUNS={}; LOCKS={}; LOCK=threading.RLock()
B=None
HEARTBEAT_STOP=threading.Event()
def host_identity():
    return {'host_id':hashlib.sha256(Path('/etc/machine-id').read_bytes().strip()).hexdigest()[:24],'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
def initialize(b):
    global B
    if B is not None: return
    B=b
    recover()
    threading.Thread(target=heartbeat,daemon=True,name='instance-liveness').start()

def heartbeat():
    last_api=time.monotonic()
    while not HEARTBEAT_STOP.wait(1):
        try:
            with urllib.request.urlopen('http://127.0.0.1:18003/api/health',timeout=.7) as response:
                if response.status==200: last_api=time.monotonic()
        except Exception: pass
        for r in list(RUNS.values()):
            try:
                if not r.get('heartbeat_path'): continue
                if time.monotonic()-last_api>=8:
                    r['paused']=True
                    B.kill_task_cgroup(r)
                else: B.write_file(r['heartbeat_path'],json.dumps({'generation':r['generation'],'at':time.monotonic()}),0o600)
            except (OSError,RuntimeError): pass

def manifest(value): return B.RUNTIME/'instances'/ident(value)/'manifest.json'

def persist(record):
    fields=('instance_id','task_id','generation','domain_id','process_cgroup','cgroup_inode','pin_root','web_port','network_chain')
    data={**{k:record[k] for k in fields if k in record},**host_identity()}
    for key in ('watch','anchor'):
        if record.get(key): data[key+'_identity']=identity(record[key].pid)
    p=manifest(record['instance_id']);p.parent.mkdir(parents=True,exist_ok=True)
    p.parent.chmod(0o700)
    temp=p.with_suffix('.tmp');B.write_file(temp,json.dumps(data),0o600);os.replace(temp,p)

def recover():
    # A receipt never restores authority. After Broker loss, kill only the
    # root-owned cgroup whose path AND inode match the launch manifest.
    base=B.RUNTIME/'instances'
    if not base.exists(): return
    for p in base.glob('instance-*/manifest.json'):
        info=p.lstat()
        if p.is_symlink() or info.st_uid!=0 or info.st_mode&0o077: raise RuntimeError('Unsafe instance recovery manifest')
        r=json.loads(p.read_text());value=ident(r['instance_id'])
        if p!=manifest(value) or r['task_id']!=run_id(value): raise RuntimeError('Instance recovery identity mismatch')
        if any(r.get(key)!=value for key,value in host_identity().items()): raise RuntimeError('Instance recovery host or boot mismatch')
        group=Path(r['process_cgroup'])
        if group.exists(): B.kill_task_cgroup(r)
        for key in ('watch_identity','anchor_identity'):
            old=r.get(key)
            if not old: continue
            try:
                if identity(old['pid'])==old:
                    fd=os.pidfd_open(old['pid'])
                    try: signal.pidfd_send_signal(fd,signal.SIGKILL)
                    finally: os.close(fd)
            except (OSError,ValueError): pass
        remove_network(r)
        if group.exists(): B.remove_task_engine(r)
        p.unlink()

def shutdown():
    HEARTBEAT_STOP.set()
    for value in list(RUNS):
        with inst_lock(value): stop(value)
def ident(value):
    if not REGEX.fullmatch(value): raise ValueError('Invalid controlled instance ID')
    return value
def run_id(value): return hashlib.sha256(('agent-instance:'+ident(value)).encode()).hexdigest()[:16]
def inst_lock(value):
    with LOCK: return LOCKS.setdefault(value,threading.RLock())
def root(value): return B.TASK_ROOT/'instances'/ident(value)
def identity(pid): return legacy.process_identity(pid)
def command(args):
    return subprocess.run(args,capture_output=True,text=True,timeout=10,check=True).stdout
def iptables(args,v6=False):
    return command(['/usr/sbin/ip6tables' if v6 else '/usr/sbin/iptables','-w','3',*args])

def network(record, policy, model_hosts):
    """Rules match one cgroup subtree; never change global default policy."""
    chain='ASI'+record['task_id'][:16]
    cg=str(Path(record['process_cgroup']).relative_to('/sys/fs/cgroup'))
    record['network_chain']=chain
    model_ips=set()
    for host in model_hosts:
        model_ips.update(v[4][0] for v in socket.getaddrinfo(host,443,socket.AF_INET,socket.SOCK_STREAM))
    resolvers=[]
    for line in Path('/etc/resolv.conf').read_text().splitlines():
        if line.startswith('nameserver '):
            try: resolvers.append(str(ipaddress.IPv4Address(line.split()[1])))
            except ValueError: pass
    try:
        for v6 in (False,True):
            iptables(['-N',chain],v6)
            iptables(['-I','OUTPUT','1','-m','cgroup','--path',cg,'-j',chain],v6)
            if not v6:
                for r in policy['rules']:
                    if r['action']=='network': iptables(['-A',chain,'-d',r['target'],'-j','REJECT'],v6)
                for port in (record['web_port'],record['web_port']+100,record['web_port']+200):
                    iptables(['-A',chain,'-d','127.0.0.1','-p','tcp','--dport',str(port),'-j','ACCEPT'],v6)
                for port in (record['web_port'],record['web_port']+100):
                    iptables(['-A',chain,'-d','127.0.0.1','-p','tcp','--sport',str(port),'-m','conntrack','--ctstate','ESTABLISHED','-j','ACCEPT'],v6)
                if policy['network']=='model_only':
                    for resolver in resolvers:
                        for proto in ('udp','tcp'): iptables(['-A',chain,'-d',resolver,'-p',proto,'--dport','53','-j','ACCEPT'],v6)
                    for address in sorted(model_ips):
                        iptables(['-A',chain,'-d',address,'-p','tcp','--dport','443','-j','ACCEPT'],v6)
            iptables(['-A',chain,'-j','REJECT'],v6)
        record['network_verified']=True
        record['model_ips']=sorted(model_ips)
    except Exception:
        remove_network(record)
        raise RuntimeError('实例 cgroup 网络过滤不可用，拒绝无保护启动')

def remove_network(record):
    chain=record.get('network_chain')
    if not chain: return
    cg=str(Path(record['process_cgroup']).relative_to('/sys/fs/cgroup'))
    for v6 in (False,True):
        for args in (['-D','OUTPUT','-m','cgroup','--path',cg,'-j',chain],['-F',chain],['-X',chain]):
            try: iptables(args,v6)
            except Exception: pass

def model_hosts(agent_type):
    """Only hostnames, never credentials, leave the local launch layer."""
    import yaml
    from urllib.parse import urlparse
    values=[]
    if agent_type=='hermes':
        data=yaml.safe_load((HERMES_ROOT.parent/'config.yaml').read_text()) or {}
        def visit(value):
            if isinstance(value,dict):
                for k,v in value.items():
                    if k in ('base_url','api_base','endpoint') and isinstance(v,str) and v.startswith('https://'): values.append(urlparse(v).hostname)
                    elif isinstance(v,(dict,list)): visit(v)
            elif isinstance(value,list):
                for v in value: visit(v)
        visit(data)
        # Provider defaults, resolved by the trusted startup layer.
        provider=str((data.get('model') or {}).get('provider','')) if isinstance(data.get('model'),dict) else ''
        if not values: values.append('api.deepseek.com' if provider=='deepseek' else 'openrouter.ai')
        env=HERMES_ROOT.parent/'.env'
        if env.exists():
            for line in env.read_text().splitlines():
                if re.match(r'^[A-Z_]*(BASE_URL|API_BASE)=',line):
                    parsed=urlparse(line.split('=',1)[1].strip().strip('"').strip("'"))
                    if parsed.scheme=='https' and parsed.hostname: values.append(parsed.hostname)
    else:
        # Existing native DSH launch profile selects deepseek-official.
        values=['api.deepseek.com']
    return sorted(set(values))

def protected_targets(resources,policy):
    targets=[]
    allows=[Path(r['target']) for r in policy['rules'] if r['action']=='write' and r['effect']=='allow']
    denies=[Path(r['target']) for r in policy['rules'] if r['action']=='write' and r['effect']=='deny']
    for resource in resources:
        base=Path(resource); grants=[p for p in allows if p==base or base in p.parents]
        if not grants: targets.append(base)
        elif len(grants)==1: targets.append((base,grants[0]))
        else: raise ValueError('每个资源目录暂支持一个连续写入范围；请拆分为独立资源')
    return targets,denies

def policy_dsl(resources,policy):
    targets,denies=protected_targets(resources,policy)
    lines=['source AGENT = exec "**"','']
    i=0
    for target in [*targets,*denies]:
        if isinstance(target,tuple):
            p,allowed=target
            if p==allowed: continue
        else: p=target; allowed=None
        i+=1; pattern=translate(str(p),resources)+('/**' if p.is_dir() else '')
        exception=translate(str(allowed),resources)+('/**' if allowed.is_dir() else '') if allowed else None
        if any(len(value.encode())>=64 for value in (pattern,exception) if value): raise ValueError('ActPlane rule exceeds exact path ABI')
        suffix=' unless target '+json.dumps(exception) if allowed else ''
        lines += [f'rule instance-readonly-{i}:',f'  block write file {json.dumps(pattern)} if AGENT'+suffix,f'  block unlink file {json.dumps(pattern)} if AGENT'+suffix,'  because "Instance resource is read-only or explicitly protected."','']
    for r in policy['rules']:
        if r['action']=='read' and r['effect']=='deny':
            p=Path(r['target']); i+=1
            lines += [f'rule instance-read-deny-{i}:',f'  block read file {json.dumps(translate(str(p),resources)+("/**" if p.is_dir() else ""))} if AGENT','  because "Reading this registered resource was denied."','']
    lines += ['# actplane-rule-source ref=platform.no-publish mode=locked','rule immutable-no-publish:', '  kill exec "git" "push" if AGENT','  because "Publishing is outside the instance execution boundary."']
    return '\n'.join(lines)+'\n'

def compile_documents(value,resources,policy,documents):
    """Compile before loading. User labels never address platform/other documents."""
    parsed=prepare_documents(documents,resources)
    validate_runtime_capabilities(parsed)
    dsl=policy_dsl(resources,policy)+'\n'+'\n'.join(d['effective_dsl'] for d in parsed)
    yaml='version: 1\npolicy: |\n'+'\n'.join('  '+l for l in dsl.splitlines())+'\n'
    directory=root(value)/'dsl-validation';directory.mkdir(parents=True,exist_ok=True)
    compiled=B.compile_policy(run_id(value),int(time.time_ns()),yaml,dsl,directory)
    details=compiled['compile']
    if details.get('ok') is not True:raise ValueError('ActPlane 未返回可核验的编译结果')
    unsupported=[r for r in details.get('backend_support',{}).get('sources',[]) if not r.get('supported')]
    if unsupported:raise ValueError('ActPlane 不支持该来源：'+json.dumps(unsupported,ensure_ascii=False))
    for doc in parsed:
        for rule in doc['rules']:
            refs=[r for r in details.get('rules',[]) if r.get('source_ref')==rule['source_ref'] and r.get('name')==rule['compiled_name']]
            if not refs or any(not r.get('clause_hash') for r in refs):raise ValueError('ActPlane 缺少规则与编译子句映射')
    artifact={'effective_dsl':dsl,'documents':parsed,'compile':compiled['compile'],
        'bundle_hash':hashlib.sha256(yaml.encode()).hexdigest(),'dsl_hash':dsl_fingerprint(documents,resources),'loaded':False}
    return compiled,artifact

def validate_runtime_capabilities(parsed):
    # Static compile support is broader than the pinned engine used by this
    # launch profile. These requirements come from the compiler's lowered ABI.
    for doc in parsed:
        missing=doc.get('pinned_runtime_unsupported',[])
        if missing:raise ValueError('当前 ActPlane 受控引擎不支持 '+ '、'.join(missing)+'（文档 '+doc['name']+'）；请使用明确的资源路径或路径前缀。候选未应用。')

def kernel_events(record,cursor=None):
    """Read bounded root-owned NDJSON, never a user-supplied log path."""
    eventpath=Path(record['workspace'])/'.actplane/events.jsonl'
    if eventpath.parent.is_symlink() or eventpath.parent.stat().st_uid!=0 or eventpath.parent.stat().st_mode&0o022:raise ValueError('Invalid kernel audit directory')
    if not eventpath.exists():return {'events':[],'cursor':cursor,'generation':record['generation']}
    fd=os.open(eventpath,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('Invalid kernel audit ownership')
        identity=f'{info.st_dev}:{info.st_ino}'
        offset=int(cursor['offset']) if cursor and cursor.get('file')==identity else int(record.get('event_start',0))
        if offset<0 or offset>info.st_size:raise ValueError('Kernel audit cursor changed')
        events=[]
        with os.fdopen(fd,'rb',closefd=False) as stream:
            stream.seek(offset)
            for _ in range(100):
                begin=stream.tell();line=stream.readline(65537)
                if len(line)>65536:raise ValueError('Kernel audit event exceeds bound')
                if not line or not line.endswith(b'\n'):stream.seek(begin);break
                try:raw=json.loads(line)
                except ValueError:continue
                if raw.get('event')!='taint_violation':continue
                if raw.get('process_domain_id',raw.get('domain_id'))!=record['domain_id']:continue
                events.append({'offset':begin,'event':raw})
            offset=stream.tell()
        return {'events':events,'cursor':{'file':identity,'offset':offset},'generation':record['generation'],
            'bundle_hash':record.get('policy_artifact',{}).get('bundle_hash'),'domain_id':record['domain_id']}
    finally:os.close(fd)

def own_tree(path,uid,gid):
    for base,dirs,files in os.walk(path,followlinks=False):
        os.chown(base,uid,gid);os.chmod(base,0o750)
        for name in files:
            p=Path(base)/name
            if not p.is_symlink(): os.chown(p,uid,gid);os.chmod(p,0o600)

def seal_dsh(home):
    # Native boot rewrites its include root; seal only after initialization,
    # before the shared tool gate opens. Mutable native storage stays separate.
    for p in (home,home/'profiles'):
        os.chown(p,0,B.TASK_GID);os.chmod(p,0o550)
    for p in home.iterdir():
        if p.is_file() and not p.is_symlink(): os.chown(p,0,B.TASK_GID);os.chmod(p,0o440)
    for base,dirs,files in os.walk(home/'profiles',followlinks=False):
        os.chown(base,0,B.TASK_GID);os.chmod(base,0o550)
        for name in files:
            p=Path(base)/name
            if not p.is_symlink(): os.chown(p,0,B.TASK_GID);os.chmod(p,0o440)

def prepare_home(value,agent_type):
    import yaml
    directory=root(value)/'state'; directory.mkdir(parents=True,exist_ok=True)
    home=directory/('hermes' if agent_type=='hermes' else '.dsh')
    user=pwd.getpwnam('happy')
    if not home.exists():
        if agent_type=='dsh':
            home=B.prepare_task_dsh_home(directory)
        else:
            home.mkdir(mode=0o700)
            # Independent native installation; never consult ERP or inherited HERMES_HOME.
            for name in ('config.yaml','.env','auth.json'):
                src=HERMES_ROOT.parent/name
                if src.is_file(): shutil.copy2(src,home/name)
    if agent_type=='dsh':
        for name in ('sessions','storages','logs'):
            (home/name).mkdir(exist_ok=True)
        port=B.prepare_web_home(home)
        plugin=home/'profiles/web/node_modules/@agentscope/dsh-instance-runtime'
        if plugin.exists(): shutil.rmtree(plugin)
        shutil.copytree(B.REPO_ROOT/'integrations/dsh-instance-runtime',plugin)
        patch=home/'profiles/web/cordis.patch.yml'
        data=yaml.safe_load(patch.read_text())
        for item in data:
            for added in item.get('insert',[]):
                if added.get('name')=='@agentscope/dsh-managed-web': added.update(id='agentscope-instance-runtime',name='@agentscope/dsh-instance-runtime')
        patch.write_text(yaml.safe_dump(data))
    else:
        if not HERMES_ENTRY.is_file() or HERMES_ROOT not in HERMES_ENTRY.resolve().parents: raise ValueError('WSL 原生 Hermes 安装身份不匹配')
        if not (HERMES_DIST/'index.html').exists(): raise ValueError('WSL 原生 Hermes 网页资源未构建')
        plugin=home/'plugins/agentscope-instance'
        if plugin.exists(): shutil.rmtree(plugin)
        shutil.copytree(B.REPO_ROOT/'integrations/hermes-instance',plugin)
        cfg=yaml.safe_load((home/'config.yaml').read_text()) or {}
        cfg['plugins']={'enabled':['agentscope-instance']}
        cfg['terminal']={**cfg.get('terminal',{}),'backend':'local'}
        cfg['check_for_updates']=False
        (home/'config.yaml').write_text(yaml.safe_dump(cfg,allow_unicode=True))
        port=None
        with B.LOCK:
            for n in range(18040,18060):
                if n in B.WEB_PORTS: continue
                try:
                    with socket.socket() as a,socket.socket() as b: a.bind(('127.0.0.1',n)); b.bind(('127.0.0.1',n+100))
                    B.WEB_PORTS.add(n);port=n;break
                except OSError: pass
        if port is None: raise ValueError('No free Hermes demo port')
    own_tree(directory,user.pw_uid,user.pw_gid)
    return home,port,user

def native(record,operation,**fields):
    payload={'operation':operation,**fields}
    request=urllib.request.Request(f"http://127.0.0.1:{record['web_port']+100}/",data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+record['native_token']})
    with urllib.request.urlopen(request,timeout=2 if operation in ('observe','open_url') else 35) as response: result=json.load(response)
    return result

def native_pid(record,namespace_pid):
    """Native plugins report namespace PIDs. Resolve only admitted cgroup members."""
    candidates=[]
    for value in (B.task_cgroup(record)/'cgroup.procs').read_text().split():
        try:
            proc=Path('/proc')/value
            line=next(l for l in (proc/'status').read_text().splitlines() if l.startswith('NSpid:'))
            nsids=line.split()[1:]
            if len(nsids)<2 or int(nsids[-1])!=namespace_pid: continue
            args=(proc/'cmdline').read_bytes()
            expected=str(B.DSH_WEB).encode() if record['agent_type']=='dsh' else str(HERMES_ROOT).encode()
            if expected in args: candidates.append(int(value))
        except (OSError,StopIteration,ValueError): pass
    if len(candidates)!=1: raise ValueError('Native process namespace mapping is ambiguous')
    return candidates[0]

def gateway(record,token):
    """Agent network reaches only this typed proxy, never passwordless control API."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            try:
                if self.path not in ('/lease','/result','/scope','/policy/proposals'): raise ValueError('Unavailable operation')
                if not hmac.compare_digest(self.headers.get('authorization',''),'Bearer '+token): raise ValueError('Invalid credential')
                size=int(self.headers.get('content-length','0'))
                if not 0<size<32000: raise ValueError('Invalid payload size')
                raw=self.rfile.read(size)
                url=os.getenv('AGENTSCOPE_PUBLIC_URL','http://127.0.0.1:18003')+'/api/agent/instances/'+record['instance_id']+self.path
                req=urllib.request.Request(url,data=raw,headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
                with urllib.request.urlopen(req,timeout=90) as response: data=response.read(200000)
                self.send_response(200); self.end_headers(); self.wfile.write(data)
            except Exception:
                self.send_response(409); self.end_headers(); self.wfile.write(b'{"allowed":false,"reason":"Instance control unavailable"}')
    server=http.server.ThreadingHTTPServer(('127.0.0.1',record['web_port']+200),Handler)
    record['gateway']=server
    threading.Thread(target=server.serve_forever,daemon=True).start()

def processes(record):
    members=B.domain_members(record)
    path=B.task_cgroup(record)
    rows=[]
    for p in (path/'cgroup.procs').read_text().split():
        try:
            current=identity(int(p))
            raw=(Path('/proc')/p/'stat').read_text();fields=raw[raw.rindex(')')+2:].split()
            if fields[0] in ('Z','X'): continue
            rows.append({'pid':int(p),'ppid':int(fields[1]),'start_ticks':current['start_ticks'],'role':'control relay' if int(p)==record['runner_pid'] else 'shared agent executor' if int(p)==record.get('agent_pid') else 'child','domain_verified':int(p) in members})
        except OSError: pass
    return rows

def session_records(record):
    result=native(record,'observe')
    pid=native_pid(record,int(result['pid']))
    return [{**r,'execution_resource':r.get('resource'),'resource':translate(r['resource'],record['resources'],reverse=True) if r.get('resource') else None,'process_ids':[pid] if r.get('process_ids') else []} for r in result.get('sessions',[])]

def observe(value):
    record=RUNS.get(value)
    if not record: return {'id':value,'status':'offline','connected':False,'verified':False}
    if not record.get('ready') or record.get('paused'):
        return {'id':value,'status':'paused' if record.get('paused') else 'starting','connected':False,'verified':False,'generation':record['generation']}
    try:
        if record['watch'].poll() is not None: raise ValueError('watch ended')
        result=native(record,'observe')
        pid=native_pid(record,int(result['pid']))
        before=identity(pid)
        if record.get('agent_pid') and pid!=record['agent_pid']: raise ValueError('agent replaced')
        record['agent_pid']=pid
        members=B.domain_members(record)
        group=B.task_cgroup(record)
        cgpids={int(p) for p in (group/'cgroup.procs').read_text().split()}
        if pid not in members or pid not in cgpids or identity(pid)!=before: raise ValueError('agent binding changed')
        return {'id':value,'status':'running','connected':True,'verified':bool(record.get('verification',{}).get('passed')),'pid':pid,'dsl_hash':record.get('dsl_hash'),'start_ticks':before['start_ticks'],'generation':record['generation'],'domain_id':record['domain_id'],'process_cgroup':record['process_cgroup'],'resources':record['resources'],'resource_records':resource_records(record['resources']),'agent_type':record['agent_type'],'environment':'wsl','sessions':result.get('sessions',[]),'session_count':len(result.get('sessions',[])),'executor_shared':True,**host_identity()}
    except Exception:
        # Freeze the whole scope on lost native/control/binding evidence.
        try: (B.task_cgroup(record)/'cgroup.freeze').write_text('1')
        except Exception: pass
        record['paused']=True
        return {'id':value,'status':'unknown','connected':False,'verified':False,'generation':record['generation']}

def request_relay(record,payload,timeout=20):
    rid=secrets.token_hex(16)
    B.write_file(record['request_path'],json.dumps({'request_id':rid,**payload}),0o600)
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            result=json.loads(Path(record['result_path']).read_text())
            if result.get('request_id')==rid:
                if not result.get('ok'): raise RuntimeError(result.get('error','Instance probe failed'))
                return result
        except FileNotFoundError: pass
        time.sleep(.05)
    raise RuntimeError('Instance relay timed out')

def verify(record,policy):
    # Canary probes bypass mount restrictions to verify ActPlane itself.
    canaries=[]; paths=[]; expected=[]; listeners=[]
    def canary(base,denied):
        p=Path(base)/'.agentscope-permission-probe'
        if p.exists(): raise ValueError('保留的验收探针文件已存在，拒绝覆盖')
        p.write_text('AgentScope permission canary\n');p.chmod(0o666)
        canaries.append(p);paths.append(p);expected.append(denied)
    try:
        for base in record['resources']:
            p=Path(base)
            writable=any(r['action']=='write' and r['effect']=='allow' and (p==Path(r['target']) or Path(r['target']) in p.parents) for r in policy['rules'])
            denied=any(r['action']=='write' and r['effect']=='deny' and (p==Path(r['target']) or Path(r['target']) in p.parents) for r in policy['rules'])
            canary(base,denied or not writable)
        for rule in policy['rules']:
            if rule['action']=='write' and rule['effect']=='deny':
                p=Path(rule['target'])
                if p.is_file(): paths.append(p);expected.append(True)
                elif p.is_dir() and p not in [c.parent for c in canaries]: canary(p,True)
        # A deny-only test can hide an over-restrictive compiled rule. Prove
        # every granted directory writable, using a disposable canary only.
        for rule in policy['rules']:
            if rule['action']!='write' or rule['effect']!='allow': continue
            p=Path(rule['target'])
            denied=any(r['action']=='write' and r['effect']=='deny' and (p==Path(r['target']) or Path(r['target']) in p.parents) for r in policy['rules'])
            if denied: continue
            if p.is_dir() and p not in [c.parent for c in canaries]: canary(p,False)
            elif p.is_file() and p not in paths: paths.append(p);expected.append(False)
        read_paths=[]
        for rule in policy['rules']:
            if rule['action']!='read' or rule['effect']!='deny': continue
            p=Path(rule['target'])
            if p.is_dir():
                sample=next((f for f in p.rglob('*') if f.is_file()),None)
                if sample is None:
                    sample=p/'.agentscope-permission-probe'
                    if sample not in canaries:
                        if sample.exists(): raise ValueError('验收读取探针文件已存在')
                        sample.write_text('AgentScope read canary');sample.chmod(0o666);canaries.append(sample)
                p=sample
            read_paths.append(p)
        connections=[['127.0.0.1',record['web_port']+200]]
        for family,host in ((socket.AF_INET,'127.0.0.1'),(socket.AF_INET6,'::1')):
            s=socket.socket(family,socket.SOCK_STREAM)
            try: s.bind((host,record['web_port']+300));s.listen(8)
            except OSError: s.close();raise RuntimeError('无法建立网络隔离核验监听器')
            listeners.append(s);connections.append([host,record['web_port']+300])
        before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        result=request_relay(record,{'operation':'probe','paths':[str(p) for p in paths],'reads':[str(p) for p in read_paths],'connections':connections})
        probe=result['probe']
        consistent=len(probe['writes'])==len(paths) and all(r['denied']==deny for r,deny in zip(probe['writes'],expected)) and len(probe['reads'])==len(read_paths) and all(r['denied'] for r in probe['reads'])
        network_ok=probe['connections'][0]['connected'] and all(not r['connected'] for r in probe['connections'][1:])
        counters={}
        for v6 in (False,True):
            rows=iptables(['-L',record['network_chain'],'-n','-v','-x'],v6)
            counters['ipv6' if v6 else 'ipv4']=sum(int(line.split()[0]) for line in rows.splitlines() if 'REJECT' in line)
        network_ok=network_ok and all(n>0 for n in counters.values())
        required=[(translate(str(p),record['resources']),'write') for p,deny in zip(paths,expected) if deny]+[(translate(str(p),record['resources']),'read') for p in read_paths]
        deadline=time.monotonic()+3;events=[]
        while time.monotonic()<deadline:
            events=[]
            eventpath=Path(record['workspace'])/'.actplane/events.jsonl'
            if eventpath.exists():
                if eventpath.is_symlink() or eventpath.stat().st_uid!=0 or eventpath.stat().st_mode&0o022: raise ValueError('Invalid kernel audit ownership')
                for line in eventpath.read_text().splitlines():
                    try:
                        e=json.loads(line)
                        if e.get('pid')==probe['pid'] and e.get('blocked') and e.get('process_domain_id',e.get('domain_id'))==record['domain_id']: events.append(e)
                    except ValueError: pass
            if all(any(e.get('target')==p and e.get('op')==op for e in events) for p,op in required): break
            time.sleep(.1)
        protected_integrity=all(hashlib.sha256(p.read_bytes()).hexdigest()==before[str(p)] for p,deny in zip(paths,expected) if deny)
        grants_verified=all(hashlib.sha256(p.read_bytes()).hexdigest()!=before[str(p)] for p,deny in zip(paths,expected) if not deny and p in canaries)
        passed=consistent and network_ok and protected_integrity and grants_verified and all(any(e.get('target')==p and e.get('op')==op for e in events) for p,op in required)
        record['network_verified']=network_ok
        return {'passed':passed,'probe':probe,'kernel_events':events,'protected_integrity':protected_integrity,'grants_verified':grants_verified,'root_owned_events':True,'network_verified':network_ok,'network_reject_counters':counters,'handles':'restart_required_on_policy_change'}
    finally:
        for p in canaries: p.unlink(missing_ok=True)
        for s in listeners: s.close()

def start(message):
    if B.RUNTIME.name!='agentscope-scope-demo': raise ValueError('受控实例首轮仅部署于独立 18003 Demo')
    value=ident(message['instance_id'])
    with inst_lock(value):
        if value in RUNS: raise ValueError('Instance already started')
        agent_type=message['agent_type']
        if agent_type not in ('dsh','hermes'): raise ValueError('Unsupported agent adapter')
        resources=clean_resources(message['resources']);policy=canonical(message['policy'],resources)
        if digest(policy)!=message['policy_hash'] or not re.fullmatch('[a-f0-9]{32}',message['generation']) or len(message['token'])<32: raise ValueError('Instance launch identity mismatch')
        directory=root(value);directory.mkdir(parents=True,exist_ok=True)
        # ActPlane resets its feedback files when a watcher starts. Give each
        # generation a fresh trusted directory, preserving older raw evidence
        # and preventing an old byte offset from skipping new events.
        control=directory/'control'/message['generation'];control.mkdir(parents=True,exist_ok=False)
        temp=directory/'state/tmp';temp.mkdir(parents=True,exist_ok=True)
        home,port,user=prepare_home(value,agent_type)
        os.chmod(directory,0o755);os.chmod(directory.parent,0o755)
        os.chown(directory/'state',user.pw_uid,user.pw_gid)
        key=run_id(value)
        documents=message.get('dsl_documents',[])
        if dsl_fingerprint(documents,resources)!=message.get('dsl_hash'):raise ValueError('DSL launch fingerprint mismatch')
        compiled,artifact=compile_documents(value,resources,policy,documents)
        env=B.child_env(task_id=key)
        env.update(ACTPLANE_ATTACH_PID='0',ACTPLANE_RESERVE_FILE_FLOW='1',ACTPLANE_ENABLE_ADVANCED_HOOKS='1',SUDO_UID='0',SUDO_GID='0',TMPDIR=str(temp))
        anchor=subprocess.Popen(['/usr/bin/sleep','infinity'],start_new_session=True)
        env['ACTPLANE_ATTACH_PID']=str(anchor.pid)
        logfile=B.LOG_DIR/(key+'-instance-watch.log');logfile.parent.mkdir(parents=True,exist_ok=True)
        log=open(logfile,'a')
        watch=subprocess.Popen([str(B.ACTPLANE),'--policy',compiled['watch_path'],'watch'],cwd=control,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        record={'instance_id':value,'task_id':key,'workspace':str(control),'agent_type':agent_type,'resources':resources,'generation':message['generation'],'policy_hash':message['policy_hash'],'watch':watch,'watch_pid':watch.pid,'anchor':anchor,'watch_policy':compiled['watch_path'],'watch_log':str(logfile),'pin_root':env.get('ACTPLANE_BPF_PIN_ROOT'),'web_port':port,'native_token':secrets.token_urlsafe(36),'domain_id':secrets.randbelow(1800000000)+100000000}
        record.update(policy_artifact={**artifact,'loaded':True},dsl_hash=artifact['dsl_hash'])
        record['event_start']=0
        RUNS[value]=record
        try:
            deadline=time.monotonic()+45
            while not B.control_state(record['watch_policy']).exists():
                if watch.poll() is not None or time.monotonic()>deadline:
                    log.flush()
                    raise RuntimeError('ActPlane instance watch failed: '+logfile.read_text(errors='replace')[-1500:])
                time.sleep(.1)
            B.grant_agent_control_access(record['watch_policy'],True); B.grant_api_event_access(control,True)
            record.update(B.create_task_cgroup(key,record['domain_id']))
            network(record,policy,model_hosts(agent_type))
            persist(record)
            gateway(record,message['token'])
            commanddir=B.RUNTIME/'instances'/value;commanddir.mkdir(parents=True,exist_ok=True);commanddir.chmod(0o700)
            record.update(request_path=str(commanddir/'request.json'),result_path=str(commanddir/'result.json'))
            record['heartbeat_path']=str(commanddir/'heartbeat.json')
            B.write_file(record['heartbeat_path'],json.dumps({'generation':record['generation'],'at':time.monotonic()}),0o600)
            for p in ('request_path','result_path'): Path(record[p]).unlink(missing_ok=True)
            config={'instance_id':value,'agent_type':agent_type,'resources':resources,'policy':policy,'home':str(home),'state':str(directory/'state'),'web_port':port,'native_token':record['native_token'],'token':message['token'],'generation':record['generation'],'api_url':'http://127.0.0.1:'+str(port+200),'uid':user.pw_uid,'gid':B.TASK_GID,'dsh':str(B.DSH_WEB),'hermes_root':str(HERMES_ROOT),'hermes_dist':str(HERMES_DIST),'request_path':record['request_path'],'result_path':record['result_path'],'heartbeat_path':record['heartbeat_path'],'process_cgroup':record['process_cgroup']}
            handoff=commanddir/'launch.json';B.write_file(handoff,json.dumps(config),0o600)
            ready=commanddir/'ready';ready.unlink(missing_ok=True);nonce=secrets.token_hex(24)
            out=B.run_actplane(['--policy',record['watch_policy'],'control','launch-child','--child-id',record['domain_id'],'--delta',compiled['dsl_path'],'--','/usr/bin/python3','-c',B.RELAY_BOOTSTRAP,str(ready),nonce,str(B.REPO_ROOT/'backend/broker/instance_runner.py'),str(handoff)],control,env,35)
            match=re.search(r'Launched pid (\d+) in child domain (\d+)',out)
            if not match: raise RuntimeError('ActPlane instance child identity missing')
            record['runner_pid']=int(match[1])
            keybytes=[f'{v:02x}' for v in record['runner_pid'].to_bytes(4,'little')]
            command(['/usr/sbin/bpftool','map','update','pinned',str(Path(record['pin_root'])/'maps/te_protected_pids'),'key','hex',*keybytes,'value','hex','01','00','00','00'])
            (B.task_cgroup(record)/'cgroup.procs').write_text(str(record['runner_pid']))
            B.write_file(ready,nonce,0o600)
            deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                try:
                    state=native(record,'observe')
                    record['agent_pid']=native_pid(record,int(state['pid']))
                    with socket.create_connection(('127.0.0.1',port),timeout=.5): pass
                    if record['agent_pid'] in B.domain_members(record): break
                except Exception: pass
                time.sleep(.2)
            else: raise RuntimeError('原生 Agent 桥接未就绪，请检查实例启动日志')
            if agent_type=='dsh': seal_dsh(home)
            record['verification']=verify(record,policy)
            if not record['verification']['passed']: raise RuntimeError('实际权限拦截未通过，实例已暂停')
            record['ready']=True
            return {**observe(value),'compile':compiled['compile'],'policy_artifact':record['policy_artifact'],'dsl_hash':record['dsl_hash'],'verification':record['verification'],'launch_source':'WSL independent native Hermes' if agent_type=='hermes' else 'native DSH','executable':str(HERMES_ENTRY) if agent_type=='hermes' else str(B.DSH_WEB)}
        except Exception:
            stop(value)
            raise
        finally: log.close()

def stop(value):
    record=RUNS.get(value)
    if not record: return {'status':'stopped'}
    persisted=False
    if record.get('ready') and not record.get('paused'):
        try: persisted=bool(native(record,'flush').get('ok'))
        except Exception: pass
    killed=B.quiesce_domain(record) if record.get('runner_pid') else []
    try:
        if record['watch'].poll() is None: record['watch'].send_signal(signal.SIGINT);record['watch'].wait(timeout=5)
    except Exception: record['watch'].kill();record['watch'].wait()
    if record['anchor'].poll() is None: record['anchor'].terminate();record['anchor'].wait()
    remove_network(record)
    if record.get('gateway'): record['gateway'].shutdown(); record['gateway'].server_close()
    B.remove_task_engine(record)
    B.WEB_PORTS.discard(record['web_port'])
    RUNS.pop(value,None)
    manifest(value).unlink(missing_ok=True)
    return {'status':'stopped','quiesced_pids':killed,'domain_id':record['domain_id'],'sessions_flushed':persisted,'writable_fds_and_mappings':'revoked_by_process_termination'}

def inventory():
    result=[]
    for r in legacy.registrations():
        try:
            identity_value=legacy.service_identity(r)
            if not identity_value: raise ValueError('offline')
            observation=legacy.bridge_call(r,identity_value)
            result.append({'id':r['id'],'name':r['name'],'agent_type':'dsh','environment':'wsl','connected':True,'status':'running','resources':[w['path'] for w in observation.get('workspaces',[])],'generation':legacy.generation(r['id'],identity_value),'pid':identity_value['pid'],'start_ticks':identity_value['start_ticks'],'session_count':sum(len(w.get('sessionIds',[])) for w in observation.get('workspaces',[]))})
        except Exception: result.append({'id':r['id'],'name':r['name'],'agent_type':'dsh','environment':'wsl','connected':False,'status':'unknown'})
    if HERMES_ENTRY.is_file() and HERMES_ROOT in HERMES_ENTRY.resolve().parents:
        result.append({'id':'installed-wsl-hermes','name':'WSL 原生 Hermes','agent_type':'hermes','environment':'wsl','connected':False,'status':'installed','executable':str(HERMES_ENTRY),'resources':[]})
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit(): continue
        try:
            argv=(proc/'cmdline').read_bytes().split(b'\x00')
            if not any(str(HERMES_ROOT).encode() in a for a in argv) or b'dashboard' not in argv: continue
            env=dict(part.split(b'=',1) for part in (proc/'environ').read_bytes().split(b'\x00') if b'=' in part)
            if env.get(b'HERMES_HOME')!=str(HERMES_ROOT.parent).encode(): continue
            current=identity(int(proc.name))
            result.append({'id':'wsl-hermes-'+proc.name+'-'+current['start_ticks'],'name':'WSL 原生 Hermes 进程','agent_type':'hermes','environment':'wsl','connected':False,'status':'discovered','pid':current['pid'],'start_ticks':current['start_ticks'],'resources':[],'source':'原生安装路径、独立 HERMES_HOME 与 OS 进程'})
        except (OSError,ValueError): pass
    for value in list(RUNS): result.append(observe(value))
    for row in result:
        # Registered DSH bridges and the explicitly matched Hermes dashboard
        # expose Web entry types; installation alone is not a live CLI process.
        row['entry_kind']='cli_install' if row['id']=='installed-wsl-hermes' else 'web'
    return {'instances':result}

def existing_dsh_url(row,proc):
    try: return legacy.bridge_call(row,proc,'open-url')
    except (RuntimeError,ValueError,OSError):
        # Compatibility with an already-running older bridge. Read only the
        # current native process's own launch receipt; never restart on open.
        lines=command(['/usr/bin/journalctl','--no-pager','-o','json','-n','200','-u',row['service'],'_PID='+str(proc['pid'])])
        birth=int(proc['start_ticks'])*1000000//os.sysconf('SC_CLK_TCK')
        boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        for line in reversed(lines.splitlines()):
            e=json.loads(line)
            if e.get('_BOOT_ID')!=boot or int(e.get('__MONOTONIC_TIMESTAMP','0'))<birth: continue
            found=re.search(r'http://127\.0\.0\.1:(\d+)/\?token=([a-zA-Z0-9_-]{32,})',e.get('MESSAGE',''))
            if found and legacy.service_identity(row)==proc:
                return {'url':found.group(0)}
        # Older launchers use a native log file instead of journald.
        unit=command(['/usr/bin/systemctl','cat',row['service']])
        outputs=re.findall(r'^StandardOutput=append:(/[^\n]+)$',unit,re.M)
        if outputs:
            p=Path(outputs[-1])
            if p.is_symlink() or p.stat().st_uid not in (0,proc['uid']): raise ValueError('Native launch log identity mismatch')
            with p.open('rb') as stream:
                stream.seek(max(0,p.stat().st_size-65536))
                text=stream.read().decode(errors='replace')
            urls=re.findall(r'http://(?:127\.0\.0\.1|localhost):3000/\?token=[a-zA-Z0-9_-]{32,}',text)
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self,*_): return None
            for url in reversed(urls[-3:]):
                try: response=urllib.request.build_opener(NoRedirect).open(url,timeout=1)
                except urllib.error.HTTPError as error: response=error
                if response.headers.get('Set-Cookie') and legacy.service_identity(row)==proc:
                    response.close()
                    return {'url':url.replace('localhost','127.0.0.1')}
                response.close()
        raise ValueError('此运行实例未提供当前网页入口；请部署新版原生桥接')

def dispatch(message):
    action=message['action'].removeprefix('agent-instance-')
    if action=='inventory': return inventory()
    value=message['instance_id']
    if action=='dsl-compile':
        ident(value);resources=clean_resources(message['resources']);policy=canonical(message['policy'],resources)
        return compile_documents(value,resources,policy,message['dsl_documents'])[1]
    if action=='start': return start(message)
    if value in RUNS:
        with inst_lock(value):
            record=RUNS[value]
            if action=='stop': return stop(value)
            if action=='observe': return observe(value)
            if action=='kernel-events':
                if message.get('generation')!=record['generation']:raise ValueError('Kernel audit generation mismatch')
                return kernel_events(record,message.get('cursor'))
            if action=='processes': return {'processes':processes(record),'executor_shared':True}
            if action=='sessions': return {'sessions':session_records(record),'resources':record['resources'],'executor_shared':True}
            if action=='dsl-probe':
                if message.get('generation')!=record['generation'] or message.get('effect') not in ('block','kill','notify'):raise ValueError('Invalid fixed DSL probe')
                return request_relay(record,{'operation':'dsl-probe','effect':message['effect']})
            if action=='handle-probe':
                target=Path(message['target'])
                if target.name!='.agentscope-held-handle-probe' or target.is_symlink() or not target.is_file() or target.stat().st_nlink!=1: raise ValueError('Invalid fixed held-handle probe')
                return request_relay(record,{'operation':'hold','path':str(target)})
            if action=='open': return native(record,'open_url')
            if action=='native':
                op=message.get('operation')
                if op not in ('create','prompt','inspect','cancel','flush'): raise ValueError('Native operation unavailable')
                if op=='create' and message.get('resource') not in record['resources']: raise ValueError('Resource not registered')
                fields={k:message[k] for k in ('resource','session_id','text') if k in message}
                if op=='create': fields['resource']=translate(fields['resource'],record['resources'])
                return native(record,op,**fields)
    if action=='stop' and REGEX.fullmatch(value): return {'status':'stopped'}
    if action=='observe' and REGEX.fullmatch(value): return {'id':value,'status':'offline','connected':False,'verified':False}
    row=next((r for r in legacy.registrations() if r['id']==value),None)
    if row:
        proc=legacy.service_identity(row)
        if not proc: raise ValueError('原生实例当前未运行')
        if action=='open': return existing_dsh_url(row,proc)
        if action=='sessions':
            result=legacy.bridge_call(row,proc)
            return {'sessions':[{'id':s,'resource':w['path'],'process_ids':[proc['pid']],'mapping':'native_registry'} for w in result.get('workspaces',[]) for s in w.get('sessionIds',[])],'resources':[w['path'] for w in result.get('workspaces',[])],'executor_shared':True}
        if action=='processes': return {'processes':[proc|{'role':'shared agent executor','domain_verified':False}],'executor_shared':True}
    raise ValueError('此实例未接入相应操作')

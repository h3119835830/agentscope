#!/usr/bin/env python3
"""Root-only, allowlisted ActPlane broker. FastAPI never receives a shell."""
from contextlib import contextmanager
import grp, hashlib, json, os, pwd, re, secrets, shutil, signal, socket, socketserver, stat, subprocess, sys, tempfile, threading, time
from pathlib import Path

ACTPLANE=Path(os.getenv("ACTPLANE_BIN","/opt/agentscope/bin/actplane"))
DSH_WEB=Path("/opt/agentscope/dsh/node_modules/.bin/dsh").resolve()
DSH=Path(os.getenv("DSH_BIN","/opt/agentscope/dsh/node_modules/.bin/dsh"))
REPO_ROOT=Path(__file__).resolve().parents[2]
RUNNER=Path(os.getenv("AGENTSCOPE_RUNNER",REPO_ROOT/"backend/broker/task_runner.py"))
TASK_ROOT=Path(os.getenv("AGENTSCOPE_TASK_ROOT","/var/lib/agentscope/tasks")).resolve()
WORKSPACES=TASK_ROOT
OUTPUTS=TASK_ROOT
GLOBAL_DSH_HOME=Path(os.getenv("AGENTSCOPE_DSH_HOME","/var/lib/agentscope-agent/.dsh"))
POLICY_ROOT=Path(os.getenv("AGENTSCOPE_POLICY_DIR","/var/lib/agentscope-protected/policies")).resolve()
RUNTIME=Path(os.getenv("AGENTSCOPE_RUNTIME_DIR","/run/agentscope"))
SOCKET=Path(os.getenv("AGENTSCOPE_BROKER_SOCKET","/run/agentscope/broker.sock"))
LOG_DIR=Path(os.getenv("AGENTSCOPE_LOG_DIR","/var/log/agentscope"))
EXEC_PATH=os.getenv("AGENTSCOPE_EXEC_PATH","/opt/node22/bin:/opt/agentscope/bin:/opt/agentscope/dsh/node_modules/.bin:/usr/local/bin:/usr/bin:/bin")
SERVICE_HOME=os.getenv("AGENTSCOPE_SERVICE_HOME","/var/lib/agentscope")
APP_USER=pwd.getpwnam(os.getenv("AGENTSCOPE_APP_USER", "hezhipeng"))
AGENT=pwd.getpwnam(os.getenv("AGENTSCOPE_AGENT_USER","agentscope-agent"))
TASK_GID=grp.getgrnam(os.getenv("AGENTSCOPE_TASK_GROUP","agentscope-task")).gr_gid

TASKS={}; LOCK=threading.RLock()
LAUNCH_LOCK=threading.RLock()
WEB_PORTS=set()
TASK_ID_RE=re.compile(r"^[a-f0-9]{16}$")

def child_env(agent=False,task_id=None):
    home=AGENT.pw_dir if agent else SERVICE_HOME
    result={"PATH":EXEC_PATH,
      "HOME":home,"USER":AGENT.pw_name if agent else "root","LOGNAME":AGENT.pw_name if agent else "root",
      "NO_PROXY":"*","no_proxy":"*","LANG":"C.UTF-8"}
    if os.getenv("ACTPLANE_BPF_PIN_ROOT"):
        result["ACTPLANE_BPF_PIN_ROOT"]=str(Path(os.environ["ACTPLANE_BPF_PIN_ROOT"])/task_id) if task_id else os.environ["ACTPLANE_BPF_PIN_ROOT"]
        result["ACTPLANE_RESERVE_OPEN_RULES"]="1"
    if os.getenv("AGENTSCOPE_DSH_DISABLE_BYTECODE")=="1":result["PYTHONDONTWRITEBYTECODE"]="1"
    return result

def user_preexec():
    os.initgroups(AGENT.pw_name,AGENT.pw_gid)
    os.setgid(AGENT.pw_gid); os.setuid(AGENT.pw_uid)

def checked_task(task_id):
    if not TASK_ID_RE.fullmatch(str(task_id)): raise ValueError("任务 ID 格式不合法")

def path_under(path,base):
    p=Path(path).resolve(strict=True); b=Path(base).resolve(strict=True)
    if p!=b and b not in p.parents: raise ValueError("任务工作区超出 AgentScope 管理目录")
    return p

def write_file(path,text,mode=0o440,gid=TASK_GID):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    os.chown(path.parent,0,gid); os.chmod(path.parent,0o750)
    tmp=path.with_name(path.name+"."+secrets.token_hex(4)+".tmp")
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,"w") as f: f.write(text); f.flush(); os.fsync(f.fileno())
    os.chown(tmp,0,gid); os.chmod(tmp,mode); os.replace(tmp,path)

def run_actplane(args,cwd,env=None,timeout=30):
    p=subprocess.run([str(ACTPLANE),*map(str,args)],cwd=str(cwd),env=env or child_env(),capture_output=True,text=True,timeout=timeout)
    if p.returncode: raise RuntimeError((p.stderr or p.stdout or f"ActPlane exit {p.returncode}")[-5000:])
    return p.stdout.strip()

def validate_restrictive_delta(dsl):
    if not isinstance(dsl,str) or len(dsl)>12000: raise ValueError("Delta 为空或过长")
    for line in dsl.splitlines():
        s=line.strip()
        if not s or s.startswith("#"): continue
        if s.startswith("source "): raise ValueError("运行中 Delta 不能新增或重定义来源标签")
        if s.startswith("rule ") or s.startswith("because "): continue
        if not (s.startswith("block ") or s.startswith("kill ")): raise ValueError("运行期只允许追加 block/kill 限制")
    return dsl

def compile_policy(task_id,version,yaml_text,dsl_text,workspace,normalization=None):
    checked_task(task_id)
    if len(yaml_text)>250000 or len(dsl_text)>60000: raise ValueError("策略内容超过上限")
    version=int(version)
    dest=POLICY_ROOT/task_id/f"v{version}"
    dest.mkdir(parents=True,exist_ok=True)
    os.chown(dest,0,TASK_GID); os.chmod(dest,0o750)
    policy_path=dest/"policy.yaml"; dsl_path=dest/"task.dsl"
    control_root=workspace.parent/".runtime-control"
    control_root.mkdir(parents=True,exist_ok=True)
    os.chown(control_root,0,TASK_GID); os.chmod(control_root,0o2750)
    watch_dir=control_root/f"v{version}-{secrets.token_hex(6)}"
    watch_dir.mkdir(parents=True,exist_ok=True); os.chown(watch_dir,0,TASK_GID); os.chmod(watch_dir,0o750)
    watch_path=watch_dir/"watch.yaml"
    write_file(policy_path,yaml_text,0o440)
    write_file(dsl_path,dsl_text,0o440)
    watch_yaml=(
      'version: 1\npolicy: |\n'
      '  source COMMAND = exec "**"\n'
      '  source AGENTSCOPE_NEVER_MATCH = exec "/__agentscope_reserved_process__"\n'
      '\n'
      '  rule agentscope-reserve-runtime-write:\n'
      '    block write file "/__agentscope_reserved_write__/**" if AGENTSCOPE_NEVER_MATCH\n'
      '    because "Reserve ActPlane write hooks for reviewed runtime Scope restrictions."\n'
    )
    write_file(watch_path,watch_yaml,0o440)
    out=run_actplane(["--policy",policy_path,"compile","--json"],workspace,child_env(),45)
    try: details=json.loads(out)
    except Exception: details={"output":out[-4000:]}
    if normalization:
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from agentscope_app.services.policy_normalization import verify_proof
        def independent_compile(text,_task,index):
            proof_path=dest/("normalization-check-"+str(index)+".yaml")
            write_file(proof_path,text,0o440)
            value=json.loads(run_actplane(["--policy",proof_path,"compile","--json"],workspace,child_env(),45))
            support=value.get('backend_support',{}).get('clauses',[])
            return ('compiled' if value.get('ok') is True and all(c.get('supported') for c in support) else 'partial',value,'Unsupported original policy')
        verify_proof(dsl_text,yaml_text,task_id,str(workspace),normalization,independent_compile)
    clauses=details.get("backend_support",{}).get("clauses",[])
    unsupported=[c for c in clauses if not c.get("supported",False)]
    if unsupported: raise RuntimeError("策略中含 ActPlane 当前不支持的子句："+json.dumps(unsupported[:8],ensure_ascii=False))
    return {"policy_path":str(policy_path),"dsl_path":str(dsl_path),"watch_path":str(watch_path),"compile":details}

def prepare_task_dsh_home(task_root):
    dest=Path(task_root)/".dsh"
    if dest.exists(): return dest
    dest.mkdir(mode=0o700)
    for name in (".credentials.yaml","settings.yaml",".anonymous-user-id"):
        source=GLOBAL_DSH_HOME/name
        if source.is_file(): shutil.copy2(source,dest/name)
    profiles=GLOBAL_DSH_HOME/"profiles"
    if profiles.is_dir(): shutil.copytree(profiles,dest/"profiles",symlinks=True)
    for base,dirs,files in os.walk(dest,followlinks=False):
        os.chown(base,AGENT.pw_uid,TASK_GID); os.chmod(base,0o2770 if base==str(dest) else 0o770)
        for name in files:
            path=Path(base)/name
            os.chown(path,AGENT.pw_uid,TASK_GID,follow_symlinks=False)
            if not path.is_symlink(): os.chmod(path,0o600 if path.name==".credentials.yaml" else 0o660)
        for name in dirs:
            path=Path(base)/name
            if path.is_symlink(): os.chown(path,AGENT.pw_uid,TASK_GID,follow_symlinks=False)
    return dest

def prepare_public_runtime(task_root):
    # Mount targets exist before entering the domain; sandbox construction must
    # not need writes outside the task envelope even on its private tmpfs root.
    task_root=Path(task_root)
    skeleton=task_root/'.sandbox-root'
    for relative in ['usr','etc/ssl','proc','dev','runtime/bin','opt/task-python','opt/dsh-runtime/node_modules',str(task_root/'r').lstrip('/'),str(task_root/'tmp').lstrip('/'),str(task_root/'output').lstrip('/')]:
        (skeleton/relative).mkdir(parents=True,exist_ok=True)
    (skeleton/'runtime/bin/node').touch(exist_ok=True)
    (skeleton/'runtime/bin/rg').touch(exist_ok=True)
    for name,target in [('bin','usr/bin'),('lib','usr/lib'),('lib64','usr/lib64'),('tmp',str(task_root/'tmp'))]:
        path=skeleton/name
        if not path.exists() and not path.is_symlink():path.symlink_to(target)
    for base,dirs,files in os.walk(skeleton,followlinks=False):
        os.chown(base,0,TASK_GID);os.chmod(base,0o550)
        for name in files:
            path=Path(base)/name
            if not path.is_symlink():os.chown(path,0,TASK_GID);os.chmod(path,0o440)
    source=Path('/var/lib/agentscope-rq5-v1/task-python/pyvenv.cfg')
    public=Path(task_root)/'.public-runtime/pyvenv.cfg'
    allowed=('home','include-system-site-packages','version','executable')
    text='\n'.join(line for line in source.read_text().splitlines() if line.split('=',1)[0].strip() in allowed)+'\n'
    write_file(public,text,0o440)
    write_file(public.parent/'control-canary.txt','CONTROL_CANARY_NOT_PROJECT_MATERIAL\n',0o440)

def validate_managed_paths(workspace, paths):
    if not isinstance(paths,list) or len(paths)>100:raise ValueError('Invalid protected path list')
    result=[]
    for p in paths:
        target=Path(p)
        if target.is_symlink() or not target.is_file():raise ValueError('Protected assets must exist as regular files')
        resolved=path_under(p,workspace)
        if target.stat().st_nlink!=1:raise ValueError('Protected asset has a pre-existing hardlink alias; launch blocked')
        result.append(str(resolved))
    return result

def prepare_web_home(home):
    import socket,yaml
    credential=home/".credentials.yaml"
    data=yaml.safe_load(credential.read_text())
    data.setdefault("records",{}).setdefault("client-connection/browser-session",{"kind":"grant","payload":{"version":1,"secret":secrets.token_urlsafe(32)}})
    credential.write_text(yaml.safe_dump(data,sort_keys=False));os.chown(credential,AGENT.pw_uid,TASK_GID);os.chmod(credential,0o600)
    profile=home/'profiles/web';profile.mkdir(parents=True,exist_ok=True)
    nodes=profile/'node_modules';nodes.mkdir(exist_ok=True)
    global_nodes=Path('/opt/agentscope/dsh/node_modules')
    for source in global_nodes.iterdir():
        if source.name.startswith('@') and source.is_dir():
            namespace=nodes/source.name;namespace.mkdir(exist_ok=True)
            for pkg in source.iterdir():
                target=namespace/pkg.name
                if not target.exists():target.symlink_to(pkg,target_is_directory=True)
        elif not (nodes/source.name).exists():(nodes/source.name).symlink_to(source,target_is_directory=source.is_dir())
    plugin=nodes/'@agentscope/dsh-managed-web';plugin.parent.mkdir(exist_ok=True)
    if plugin.exists():shutil.rmtree(plugin)
    shutil.copytree(REPO_ROOT/'integrations/dsh-managed-web',plugin)
    (profile/'package.json').write_text(json.dumps({'name':'managed-dsh-web','private':True,'dsh':{'profile':{'bundles':['@deepseek-ai/dsh-base','@deepseek-ai/dsh-web-app']}}}))
    notice=(global_nodes/'@deepseek-ai/dsh-client-ui-settings-models/lib/types/onboarding-copy.d.ts').read_text()
    version=re.search(r'WELCOME_NOTICE_VERSION = "([^"]+)"',notice).group(1)
    (profile/'cordis.patch.yml').write_text(yaml.safe_dump([{'insert':[{'id':'managed-compaction-basic','name':'@deepseek-ai/dsh-compaction-basic','config':{'headroomTokens':4096,'maxTokens':4096,'retainTokens':4096}},{'id':'agentscope-managed-web','name':'@agentscope/dsh-managed-web'}]},{'id':'ui-settings-general','config':{'welcomeNoticeVersion':version}}]))
    for base,dirs,files in os.walk(profile,followlinks=False):
        os.chown(base,0,TASK_GID);os.chmod(base,0o2770)
        for name in files:
            target=Path(base)/name
            if not target.is_symlink():os.chown(target,0,TASK_GID);os.chmod(target,0o640)
    # The native CLI resets this empty include root before any Agent exists.
    root_config=profile/'cordis.yml'
    if root_config.exists():os.chown(root_config,0,TASK_GID);os.chmod(root_config,0o660)
    with LOCK:
        for port in range(18020,18040):
            if port in WEB_PORTS:continue
            try:
                with socket.socket() as a,socket.socket() as b:a.bind(('127.0.0.1',port));b.bind(('127.0.0.1',port+100))
                WEB_PORTS.add(port)
                return port
            except OSError:continue
    raise RuntimeError('No managed DSH web port available')

def native_session(message):
    import urllib.request,urllib.error
    task_id=message['task_id'];checked_task(task_id)
    with LOCK:record=TASKS.get(task_id)
    if not record or record.get('scope_mode')!='managed-web':raise ValueError('Not a managed native web task')
    operation=message.get('operation')
    if operation not in ('create','prompt','inspect','cancel','flush','resume','open_url','verify_delayed_open','verify_task_sandbox','compact'):raise ValueError('Native operation not allowed')
    body={k:message.get(k) for k in ('operation','session_id','request_id','text','target')}
    if operation=='verify_delayed_open':
        path=Path(str(body.get('target','')));resolved=path.resolve();workspace=Path(record['workspace']).resolve()
        if path!=resolved or workspace not in resolved.parents or not resolved.is_file() or '.actplane' in resolved.parts or '.dsh' in resolved.parts:raise ValueError('Fixed native probe target is not a regular project file')
    if len(str(body.get('text') or ''))>12000:raise ValueError('Prompt too large')
    req=urllib.request.Request(f"http://127.0.0.1:{record['web_port']+100}/",data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+record['native_token']})
    for attempt in range(100):
        try:
            with urllib.request.urlopen(req,timeout=65 if operation=='compact' else 32) as response:
                result=json.load(response)
                if operation=="create":
                    profile=Path(record["workspace"]).parent/".dsh/profiles/web"
                    for base,dirs,files in os.walk(profile,followlinks=False):
                        os.chown(base,0,TASK_GID);os.chmod(base,0o550)
                        for name in files:
                            p=Path(base)/name
                            if not p.is_symlink():os.chown(p,0,TASK_GID);os.chmod(p,0o440)
                return result
        except urllib.error.HTTPError as error:
            data=json.load(error);raise RuntimeError('Native SessionController: '+str(data.get('error')))
        except urllib.error.URLError:
            if operation!='create' or attempt==99:raise
            time.sleep(.25)

def managed_call(message):
    task_id=message['task_id'];checked_task(task_id)
    with LOCK:record=TASKS.get(task_id)
    if not record or record.get('scope_mode')!='managed-web':raise ValueError('Missing managed native binding')
    call_id=str(message.get('call_id',''))
    if not call_id or len(call_id)>180:raise ValueError('Invalid tool call identity')
    pid=int(message['pid'])
    binding=status(task_id)
    if binding['executor']['pid']!=pid or not binding['domain_verified']:raise ValueError('Tool issuer is not the bound native DSH process')
    tag=int.from_bytes(hashlib.sha256((task_id+':'+call_id).encode()).digest()[:8],'little') or 1
    value=tag if message['operation']=='start' else 0
    key=[f'{v:02x}' for v in pid.to_bytes(4,'little')];encoded=[f'{v:02x}' for v in value.to_bytes(8,'little')]
    result=subprocess.run(['/usr/sbin/bpftool','map','update','pinned',str(Path(record['pin_root'])/'maps/audit_call'),'key','hex',*key,'value','hex',*encoded],capture_output=True,text=True,timeout=5)
    if result.returncode:raise RuntimeError('Kernel tool identity registration failed')
    return {'kernel_call_tag':str(tag),'pid':pid,'domain_id':record['domain_id']}

def managed_source_read(message):
    task_id=message['task_id'];checked_task(task_id)
    with LOCK:record=TASKS.get(task_id)
    if not record or record.get('scope_mode')!='managed-web':raise ValueError('No managed source binding')
    relative=Path(str(message.get('path','')))
    if relative.is_absolute() or not relative.parts or any(x in ('.','..','.actplane','.git','.dsh') for x in relative.parts):raise ValueError('Source path outside registered project')
    # Resolve each component through no-follow descriptors. A workspace symlink
    # cannot turn this narrow read operation into arbitrary privileged access.
    directory=os.open(record['workspace'],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in relative.parts[:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory);os.close(directory);directory=child
        fd=os.open(relative.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        with os.fdopen(fd,'rb') as source:
            metadata=os.fstat(source.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size>16*1024*1024:raise ValueError('Source is not a bounded regular project file')
            raw=source.read(16*1024*1024+1)
            if len(raw)>16*1024*1024:raise ValueError('Source exceeds limit')
        return {'hash':hashlib.sha256(raw).hexdigest(),'content':raw.decode('utf-8',errors='replace')[:8000],'authority':'registered_project_read_by_broker'}
    finally:os.close(directory)

def managed_operation(message):
    task_id=message['task_id'];checked_task(task_id)
    with LOCK:record=TASKS.get(task_id)
    if not record or record.get('scope_mode')!='managed-web':raise ValueError('No managed binding')
    supplied=Path(message['target']);target=supplied.resolve()
    ws=Path(record['workspace']).resolve();out=Path(record['output_dir']).resolve()
    if supplied.is_symlink() or not any(target==base or base in target.parents for base in (ws,out)):raise ValueError('Probe target outside task')
    if target==ws or target==out or '.actplane' in target.parts or target.is_dir():raise ValueError('Probe target is control material or directory')
    operation=message['operation']
    if operation not in ('read','write','unlink','rename','replace','symlink_write','hardlink','mmap_new','fd_write','hold','ancestor_rename','grandparent_rename'):raise ValueError('Probe operation not supported')
    moved_parent=target.parent if operation=='ancestor_rename' else target.parent.parent if operation=='grandparent_rename' else None
    if moved_parent and (moved_parent==ws or ws not in moved_parent.parents):raise ValueError('Directory probe would move the workspace boundary')
    ident=secrets.token_hex(16);scratch=ws.parent/'tmp'/('probe-'+ident)
    scratch.mkdir();os.chown(scratch,0,TASK_GID);os.chmod(scratch,0o2770)
    original=target.read_bytes() if target.is_file() else None
    attrs=target.stat() if target.is_file() else None
    events=ws/'.actplane/events.jsonl';baseline=len(events.read_text().splitlines()) if events.exists() else 0
    request={'request_id':ident,'kind':'managed-hold' if operation=='hold' else 'managed-operation','operation':operation,'target':str(target),'scratch':str(scratch)}
    write_file(record['request_path'],json.dumps(request),0o640)
    try:
        for attempt in range(100):
            try:
                result=json.loads(Path(record['result_path']).read_text())
                if result.get('request_id')==ident:break
            except (FileNotFoundError,ValueError):pass
            time.sleep(.1)
        else:raise RuntimeError('Fixed OS operation timed out')
        if result.get('ok') is not True:raise RuntimeError(result.get('error') or 'Fixed operation failed before execution')
        if result.get('binding',{}).get('domain_verified') is not True:raise RuntimeError('Fixed probe was not independently bound before execution')
        probe=result['probe'];raw=[]
        for attempt in range(20):
            raw=[]
            for line in events.read_text().splitlines()[baseline:] if events.exists() else []:
                e=json.loads(line)
                if e.get('pid')==probe['pid'] and e.get('process_domain_id')==record['domain_id'] and e.get('blocked'):raw.append(e)
            if raw or not probe.get('blocked'):break
            time.sleep(.1)
        after=target.read_bytes() if target.is_file() else None
        alias=scratch/'hard-alias'
        effect=after!=original or operation=='read' and probe['success'] or operation=='hardlink' and alias.exists() and alias.stat().st_ino==target.stat().st_ino or operation=='hold' and probe['success']
        return {'probe':probe,'probe_binding':result['binding'],'domain_id':record['domain_id'],'kernel_events':raw,'effect_verified':bool(effect),'before_hash':hashlib.sha256(original).hexdigest() if original is not None else None,'after_hash':hashlib.sha256(after).hexdigest() if after is not None else None}
    finally:
        if operation!='hold':
            if moved_parent and (scratch/'directory-alias').is_dir():os.rename(scratch/'directory-alias',moved_parent)
            if original is None:target.unlink(missing_ok=True)
            elif not target.is_file() or target.read_bytes()!=original:target.write_bytes(original)
            if attrs:os.chown(target,attrs.st_uid,attrs.st_gid);os.chmod(target,attrs.st_mode&0o7777)
            shutil.rmtree(scratch)

def managed_verify(message):
    task_id=message['task_id'];checked_task(task_id)
    with LOCK:record=TASKS.get(task_id)
    if not record or record.get('scope_mode')!='managed-web':raise ValueError('Missing managed task binding')
    protected=validate_managed_paths(record['workspace'],message.get('protected_files',[]))
    allow=Path(message['allow_path']).resolve();ws=Path(record['workspace'])
    if ws not in allow.parents:raise ValueError('Probe target escapes workspace')
    backup={p:Path(p).read_bytes() for p in protected}
    request_id=secrets.token_hex(16)
    request={'request_id':request_id,'kind':'managed-verify','protected_files':protected,'allow_path':str(allow)}
    write_file(record['request_path'],json.dumps(request),0o640)
    result_path=Path(record['result_path'])
    try:
        for attempt in range(120):
            try:
                result=json.loads(result_path.read_text())
                if result.get('request_id')==request_id:break
            except (FileNotFoundError,ValueError):pass
            time.sleep(.2)
        else:raise RuntimeError('Managed permission probe timed out')
        manifest=json.loads((POLICY_ROOT/task_id/'managed-manifest.json').read_text())
        integrity=all(Path(p).exists() and hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in manifest.items())
        # Kernel feedback is drained asynchronously by the watcher.
        deadline=time.monotonic()+3
        events=ws/'.actplane/events.jsonl'
        while time.monotonic()<deadline:
            if events.exists():
                matches=[]
                for line in events.read_text().splitlines():
                    try:
                        e=json.loads(line)
                        if e.get('pid')==result.get('probe',{}).get('pid') and e.get('process_domain_id',e.get('domain_id'))==record['domain_id'] and e.get('blocked') is True:matches.append(e)
                    except ValueError:pass
                if len(matches)>=result.get('probe',{}).get('denied',0):break
            time.sleep(.1)
        raw=[];events=ws/'.actplane/events.jsonl'
        if events.exists():
            st=events.lstat()
            if events.is_symlink() or st.st_uid!=0 or st.st_mode&0o022:raise ValueError('Kernel audit ownership invalid')
            for line in events.read_text().splitlines():
                try:
                    e=json.loads(line)
                    if e.get('pid')==result.get('probe',{}).get('pid') and e.get('process_domain_id',e.get('domain_id'))==record['domain_id'] and e.get('blocked') is True:raw.append(e)
                except ValueError:pass
        probe=result.get('probe',{})
        return {'passed':bool(result.get('ok') and integrity and len(raw)>=probe.get('denied',0)),'domain_id':record['domain_id'],'runner_pid':record['runner_pid'],'probe':probe,'kernel_events':raw,'integrity':integrity,'root_owned_events':True}
    finally:
        # Restore only isolated fixture bytes after a failed adversarial probe.
        for p,original in backup.items():
            if not Path(p).exists() or Path(p).read_bytes()!=original:Path(p).write_bytes(original)
        allow.unlink(missing_ok=True)

def control_state(policy_path): return Path(policy_path).parent/".actplane"/"control.json"

def grant_agent_control_access(policy_path, trusted_relay=False):
    """Expose only this task domain's ActPlane control state to its in-domain relay."""
    root=control_state(policy_path).parent
    if not root.exists(): raise RuntimeError("ActPlane control state directory is missing")
    if trusted_relay:
        state = json.loads(control_state(policy_path).read_text())
        socket_path = Path(state["socket_path"])
        os.chown(socket_path, 0, 0)
        os.chmod(socket_path, 0o600)
    for base,dirs,files in os.walk(root,followlinks=False):
        os.chown(base,0,TASK_GID); os.chmod(base,0o750)
        for name in dirs:
            path=Path(base)/name
            if path.is_symlink(): continue
            os.chown(path,0,TASK_GID); os.chmod(path,0o750)
        for name in files:
            path=Path(base)/name
            if path.is_symlink(): continue
            os.chown(path,0,TASK_GID)
            os.chmod(path,0o640 if trusted_relay else 0o660 if path.name=="control.json" else 0o640)

def grant_api_event_access(workspace, trusted_relay=False):
    """Allow the API task group to read kernel events without write access."""
    event_dir=Path(workspace)/".actplane"
    if not event_dir.exists(): return
    if event_dir.is_symlink(): raise RuntimeError("ActPlane event directory cannot be a symlink")
    event_dir=path_under(event_dir,workspace)
    os.chown(event_dir,0 if trusted_relay else -1,TASK_GID); os.chmod(event_dir,0o2750)
    events=event_dir/"events.jsonl"
    if events.exists():
        if events.is_symlink(): raise RuntimeError("ActPlane events cannot be a symlink")
        events=path_under(events,workspace)
        os.chown(events,0 if trusted_relay else -1,TASK_GID); os.chmod(events,0o640)

RELAY_BOOTSTRAP = """import os,sys,time,stat
path,nonce=sys.argv[1:3]
if os.geteuid()!=0:raise SystemExit(78)
deadline=time.monotonic()+15
while True:
    try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    except FileNotFoundError:
        if time.monotonic()>=deadline:raise SystemExit(78)
        time.sleep(.02);continue
    try:
        info=os.fstat(fd)
        if info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o600 or not stat.S_ISREG(info.st_mode):raise SystemExit(78)
        if os.read(fd,256).decode()!=nonce:raise SystemExit(78)
    finally:os.close(fd)
    break
os.unlink(path)
os.execv('/usr/bin/python3',['/usr/bin/python3',*sys.argv[3:]])
"""


@contextmanager
def launch_slot(task_id,scope_mode):
    # Serialize launch preparation/port leases, never unrelated task reads.
    with LAUNCH_LOCK:
        with LOCK:
            for other in TASKS.values():
                if other.get("watch") and other["watch"].poll() is None and (scope_mode!="managed-web" or other.get("scope_mode")!="managed-web" or other["task_id"]==task_id):
                    raise RuntimeError("ActPlane 当前使用单例运行时；请先停止现有 Agent 任务")
        try:yield
        finally:
            with LOCK:WEB_PORTS.intersection_update(record.get('web_port') for record in TASKS.values() if record.get('web_port'))

def launch(task_id,version,workspace,output_dir,prompt,dsl_text,policy_yaml,dsh_profile="headless",task_token="",agentscope_url="http://127.0.0.1:8000",scope_mode="",protected_files=None,baseline_dsl=None,normalization=None):
    checked_task(task_id)
    if scope_mode not in ("", "cold", "managed", "managed-web"): raise ValueError("Scope runner mode invalid")
    if dsh_profile not in ("headless","web") or (dsh_profile=="web" and scope_mode!="managed-web"): raise ValueError("DSH profile must match the managed launch mode")
    if not DSH.exists(): raise RuntimeError(f"DSH CLI 不存在：{DSH}")
    if not RUNNER.exists(): raise RuntimeError(f"任务运行器不存在：{RUNNER}")
    if len(task_token)<32: raise ValueError("AgentScope 任务凭据缺失或无效")
    workspace=path_under(workspace,WORKSPACES)
    output=path_under(output_dir,OUTPUTS)
    if len(prompt)>8000: raise ValueError("任务提示词过长")
    with launch_slot(task_id,scope_mode):
        files=compile_policy(task_id,version,policy_yaml,dsl_text,workspace,normalization)
        if scope_mode=="managed-web":
            if not baseline_dsl or len(baseline_dsl)>60000:raise ValueError("Missing immutable startup baseline")
            parent_dsl=re.sub(r"\bAGENT\b","COMMAND",baseline_dsl)
            parent_yaml="version: 1\nfeedback:\n  path: "+json.dumps(str(workspace/".actplane/last-violation.txt"))+"\npolicy: |\n"+"\n".join("  "+line for line in parent_dsl.splitlines())+"\n"
            write_file(files["watch_path"],parent_yaml,0o440)
            if normalization:
                parent_check=run_actplane(["--policy",files["watch_path"],"compile","--json"],workspace,child_env(task_id=task_id),20)
                parent_compiled=json.loads(parent_check)
                if parent_compiled.get('ok') is not True:raise ValueError('Immutable parent policy did not compile')
                files['baseline_binding']={'bundle_hash':hashlib.sha256(parent_yaml.encode()).hexdigest(),'compile':parent_compiled}

        if scope_mode and scope_mode!="managed-web":
            protected_manifest = POLICY_ROOT / task_id / "scope-manifest.json"
            if not protected_manifest.exists():
                source = workspace.parent / "scope-manifest.json"
                if source.is_symlink(): raise ValueError("Fixture manifest must not be a symlink")
                manifest = json.loads(source.read_text())
                if set(manifest) != {"backend/stats.py", "frontend/report.py", "tests/test_stats.py", "config/demo.json"}:
                    raise ValueError("Unregistered fixture manifest")
                write_file(protected_manifest, json.dumps(manifest), 0o440)
        policy_path=files["policy_path"]; watch_path=files["watch_path"]
        dsh_home=prepare_task_dsh_home(workspace.parent)
        web_port,native_token=(prepare_web_home(dsh_home),secrets.token_urlsafe(36)) if scope_mode=="managed-web" else (None,None)
        if scope_mode=="managed-web":
            prepare_public_runtime(workspace.parent)
            protected_files=validate_managed_paths(workspace,protected_files or [])
            manifest_path=POLICY_ROOT/task_id/"managed-manifest.json"
            hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in protected_files}
            if manifest_path.exists():
                if json.loads(manifest_path.read_text())!=hashes:raise ValueError("Sealed startup asset integrity changed; refusing launch")
            else:write_file(manifest_path,json.dumps(hashes),0o440)
        log_dir=LOG_DIR; log_dir.mkdir(parents=True,exist_ok=True)
        watch_log=open(log_dir/f"{task_id}-v{version}-watch.log","a",buffering=1)
        # Scope restrictions can be approved during a task, so the ActPlane
        # watch engine must reserve file-flow hooks before its child domain is
        # created. The engine cannot enable write-rule classes retroactively.
        env=child_env(task_id=task_id); env.update({"TMPDIR":str(workspace.parent/"tmp"),"ACTPLANE_ATTACH_PID":"0","ACTPLANE_RESERVE_FILE_FLOW":"1","ACTPLANE_ENABLE_ADVANCED_HOOKS":"1",
                                     "SUDO_UID":str(0 if scope_mode else AGENT.pw_uid),"SUDO_GID":str(0 if scope_mode else TASK_GID)})
        anchor=subprocess.Popen(["/usr/bin/sleep","infinity"],cwd=workspace,env=child_env(True),preexec_fn=user_preexec,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        env["ACTPLANE_ATTACH_PID"]=str(anchor.pid)
        watch=None
        try:
            watch=subprocess.Popen([str(ACTPLANE),"--policy",watch_path,"watch"],cwd=workspace,env=env,stdout=watch_log,stderr=subprocess.STDOUT,start_new_session=True)
            deadline=time.time()+25
            while time.time()<deadline:
                if watch.poll() is not None:
                    anchor.terminate()
                    watch_log.flush(); watch_log.close()
                    raise RuntimeError("ActPlane watch exited "+str(watch.returncode)+": "+(log_dir/f"{task_id}-v{version}-watch.log").read_text(errors="replace")[-4500:])
                if control_state(watch_path).exists():
                    grant_agent_control_access(watch_path, bool(scope_mode))
                    grant_api_event_access(workspace, bool(scope_mode))
                    break
                time.sleep(.2)
            else:
                watch.terminate(); anchor.terminate()
                raise RuntimeError("ActPlane watch 启动超时；请检查 /var/log/agentscope/*-watch.log")
            domain=secrets.randbelow(1_800_000_000)+100_000_000
            process_scope=create_task_cgroup(task_id,domain) if scope_mode=="managed-web" else {}
            result_path=workspace.parent/(".runtime-control/scope-result.json" if scope_mode else "tmp/scope-result.json")
            task_env_path=workspace.parent/"tmp"/"agent-env.json"
            relay_ready=RUNTIME/"commands"/task_id/("relay-"+str(domain)+".ready")
            relay_nonce=secrets.token_hex(24)
            runner_command=["/usr/bin/python3","-c",RELAY_BOOTSTRAP,str(relay_ready),relay_nonce,str(RUNNER)] if scope_mode=="managed-web" else ["/usr/bin/python3",str(RUNNER)]
            command=["--policy",watch_path,"control","launch-child","--child-id",str(domain),"--delta",files["dsl_path"],"--",*runner_command,
              "--task-id",task_id,"--domain-id",str(domain),"--env-file",str(task_env_path),"--request-file",str(RUNTIME/"commands"/task_id/"request.json"),
              "--result-file",str(result_path),"--watch-policy",watch_path,"--actplane",str(ACTPLANE),
              "--workspace",str(workspace),"--dsh",str(DSH_WEB if scope_mode=="managed-web" else DSH),"--dsh-home",str(dsh_home),"--profile",dsh_profile,"--prompt",prompt]
            cmd_root=RUNTIME/"commands"; cmd_root.mkdir(parents=True,exist_ok=True); os.chown(cmd_root,0,0); os.chmod(cmd_root,0o711)
            cmd_dir=cmd_root/task_id; cmd_dir.mkdir(parents=True,exist_ok=True); os.chown(cmd_dir,0,TASK_GID); os.chmod(cmd_dir,0o750)
            request_path=cmd_dir/"request.json"; request_path.unlink(missing_ok=True)
            relay_ready.unlink(missing_ok=True)
            task_env_path.parent.mkdir(parents=True,exist_ok=True); os.chown(task_env_path.parent,0,TASK_GID); os.chmod(task_env_path.parent,0o2770)
            write_file(task_env_path,json.dumps({"task_id":task_id,"task_token":task_token,"agentscope_url":agentscope_url,"scope_mode":scope_mode,"web_port":web_port,"native_token":native_token,"pin_root":env.get("ACTPLANE_BPF_PIN_ROOT"),**process_scope}),0o660)
            os.chown(task_env_path.parent,0,TASK_GID); os.chmod(task_env_path.parent,0o2770)
            result_path.unlink(missing_ok=True)
            # ActPlane's watch daemon launches the child with its own environment,
            # not the launch-child CLI caller's environment. Pass task credentials
            # through a one-time task file; task_runner scrubs it before starting DSH.
            launch_env=child_env(task_id=task_id); launch_env.update({"SUDO_UID":str(0 if scope_mode else AGENT.pw_uid),"SUDO_GID":str(0 if scope_mode else TASK_GID),"TMPDIR":str(workspace.parent/"tmp")})
            try:
                out=run_actplane(command,workspace,launch_env,35)
            except Exception:
                task_env_path.unlink(missing_ok=True)
                watch.send_signal(signal.SIGINT); anchor.terminate(); raise
            m=re.search(r"Launched pid (\d+) in child domain (\d+)",out)
            runner_pid=int(m.group(1)) if m else None
            domain_id=int(m.group(2)) if m else domain
            record={"task_id":task_id,"version":version,"workspace":str(workspace),"output_dir":str(output),"policy_path":policy_path,"watch_policy":watch_path,
              "watch":watch,"anchor":anchor,"watch_log":str(log_dir/f"{task_id}-v{version}-watch.log"),"watch_pid":watch.pid,"runner_pid":runner_pid,"domain_id":domain_id,
              "request_path":str(request_path),"result_path":str(result_path),"dsl_path":files["dsl_path"],"scope_mode":scope_mode,"web_port":web_port,"native_token":native_token,"pin_root":env.get("ACTPLANE_BPF_PIN_ROOT"),**process_scope}
            if scope_mode=="managed-web":
                # The root relay is a designated control process. The exception is
                # keyed by its exact PID and never inherited by low-UID children.
                status=(Path("/proc")/str(runner_pid)/"status").read_text()
                if int(next(l.split()[1] for l in status.splitlines() if l.startswith("Uid:")))!=0:raise RuntimeError("Trusted relay UID mismatch")
                key=[f"{v:02x}" for v in runner_pid.to_bytes(4,"little")]
                updated=subprocess.run(["/usr/sbin/bpftool","map","update","pinned",str(Path(record["pin_root"])/"maps/te_protected_pids"),"key","hex",*key,"value","hex","01","00","00","00"],capture_output=True,text=True,timeout=5)
                if updated.returncode:raise RuntimeError("Trusted relay registration failed: "+updated.stderr[:500])
                # The root bootstrap waits without reading protected repo code.
                # Release only after its exact PID has been registered; no child inherits this exception.
                (task_cgroup(record)/"cgroup.procs").write_text(str(runner_pid))
                write_file(relay_ready,relay_nonce,0o600)
            with LOCK:TASKS[task_id]=record
            return {"task_id":task_id,"status":"running","runner_pid":runner_pid,"domain_id":domain_id,"watch_pid":watch.pid,
                    "web_url":f"http://127.0.0.1:{web_port}/" if web_port else None,"version":version,"compile_state":"loaded","compile":files["compile"],"baseline_binding":files.get("baseline_binding"),**process_scope,"message":"ActPlane 控制平面已加载；DSH 已由 child domain 接管"}
        except Exception:
            record=TASKS.get(task_id) or {"task_id":task_id,"domain_id":locals().get('domain',0),"pin_root":env.get('ACTPLANE_BPF_PIN_ROOT'),**locals().get("process_scope",{})}
            if record.get('domain_id') and record.get('pin_root') and Path(record['pin_root']).exists():
                quiesce_domain(record)
            if watch and watch.poll() is None:
                watch.send_signal(signal.SIGINT)
                try:watch.wait(timeout=5)
                except subprocess.TimeoutExpired:watch.kill();watch.wait(timeout=5)
            if anchor.poll() is None:anchor.terminate();anchor.wait(timeout=5)
            if record.get('pin_root'):remove_task_engine(record)
            with LOCK:TASKS.pop(task_id,None)
            if 'relay_ready' in locals():relay_ready.unlink(missing_ok=True)
            watch_log.close()
            raise

def status(task_id):
    checked_task(task_id)
    with LOCK: record=TASKS.get(task_id)
    if not record: return {"available":False,"status":"unknown"}
    if record["watch"].poll() is not None: state="stopped"
    else: state="running"
    output="[]"
    try: output=run_actplane(["--policy",record["watch_policy"],"control","children"],record["workspace"],child_env(task_id=task_id),6)
    except Exception as e: return {"available":True,"status":state,"error":str(e),"domain_id":record["domain_id"],"runner_pid":record["runner_pid"]}
    try: children=json.loads(output)
    except Exception: children=[]
    child=next((c for c in children if int(c.get("child_id",-1))==record["domain_id"]),None)
    status=(child or {}).get("status",{})
    executor = None
    if record.get("scope_mode") in ("managed","managed-web"):
        try:
            children_file = Path("/proc") / str(record["runner_pid"]) / "task" / str(record["runner_pid"]) / "children"
            for pid in children_file.read_text().split():
                cmdline = (Path("/proc") / pid / "cmdline").read_bytes().split(b"\0")
                if str(DSH_WEB if record.get("scope_mode")=="managed-web" else DSH).encode() in cmdline:
                    executor = int(pid)
                    break
        except OSError: pass
    members=domain_members(record) if record.get("scope_mode")=="managed-web" else []
    domain_verified=executor in members if record.get("scope_mode")=="managed-web" else None
    group=task_cgroup(record)
    scoped_members={int(pid) for pid in (group/'cgroup.procs').read_text().split()} if group else set()
    cgroup_verified=record['runner_pid'] in scoped_members and executor in scoped_members if group else None
    if record.get("scope_mode")=="managed-web" and (not domain_verified or group and not cgroup_verified):state="unbound"
    processes=process_snapshot(task_id,{'verified':state=='running' and domain_verified is True and cgroup_verified is True,'domain_id':record['domain_id'],'domain_members':members,'process_cgroup':record.get('process_cgroup'),'cgroup_inode':record.get('cgroup_inode'),'runner_pid':record.get('runner_pid'),'executor':{'pid':executor}})
    return {"processes":processes,"process_cgroup":record.get('process_cgroup'),"cgroup_inode":record.get('cgroup_inode'),"cgroup_verified":cgroup_verified,"domain_verified":domain_verified,"available":True,"status":state,"agent_status":status.get("state","unknown"),"domain_id":record["domain_id"],"runner_pid":record["runner_pid"],"watch_pid":record["watch_pid"],"child":child,
            "executor":{"mode":record.get("scope_mode"),"pid":executor,"state":"running" if executor else "absent"}}

def process_snapshot(task_id,execution):
    """Read only admitted task-cgroup PIDs. Cgroup membership is not a label proof."""
    if not execution.get('verified'):return []
    path=Path(execution.get('process_cgroup','/missing'))
    if path.parent.parent!=Path('/sys/fs/cgroup') or path.name!=f"{task_id}-{execution['domain_id']}":return []
    try:
        st=path.lstat()
        if path.resolve()!=path or st.st_uid!=0 or st.st_ino!=execution.get('cgroup_inode'):return []
        before={int(p) for p in (path/'cgroup.procs').read_text().split()}
        result=[]
        for pid in sorted(before)[:64]:
            try:
                proc=Path('/proc')/str(pid);raw=(proc/'stat').read_text();fields=raw[raw.rindex(')')+2:].split()
                if fields[0] in ('Z','X'):continue
                # Start ticks bind this sample to a process instance, not a reusable PID.
                again=(proc/'stat').read_text();other=again[again.rindex(')')+2:].split()
                if fields[19]!=other[19] or fields[1]!=other[1]:continue
                name=raw[raw.index('(')+1:raw.rindex(')')]
                role='agent' if pid==execution.get('executor',{}).get('pid') else 'runner' if pid==execution.get('runner_pid') else 'child'
                result.append({'key':f'pid:{pid}:{fields[19]}','kind':'process','pid':pid,'ppid':int(fields[1]),'start_ticks':fields[19],
                    'title':'DSH Agent' if role=='agent' else 'Task runner' if role=='runner' else ''.join(ch for ch in name if ch.isprintable())[:60],
                    'role':role,'membership':'task_cgroup','domain_verified':pid in execution.get('domain_members',[])})
            except (OSError,ValueError,IndexError):continue
        after={int(p) for p in (path/'cgroup.procs').read_text().split()}
        return [p for p in result if p['pid'] in after]
    except (OSError,ValueError):return []


def domain_members(record):
    pin=record.get("pin_root")
    if not pin:return []
    result=subprocess.run(["/usr/sbin/bpftool","-j","map","dump","pinned",str(Path(pin)/"maps/cap_task")],capture_output=True,text=True,timeout=5)
    if result.returncode:raise RuntimeError("Cannot inspect live task domain")
    def integer(value):
        if isinstance(value,int):return value
        return int.from_bytes(bytes(int(x,16) if isinstance(x,str) else x for x in value),"little")
    members=[]
    for row in json.loads(result.stdout):
        if integer(row["value"])!=record["domain_id"]:continue
        pid=integer(row["key"])
        try:
            status=(Path("/proc")/str(pid)/"status").read_text()
            state=next(l.split()[1] for l in status.splitlines() if l.startswith("State:"))
            if state not in ("Z","X"):members.append(pid)
        except (FileNotFoundError,ProcessLookupError):pass
    return sorted(set(members))

def task_cgroup(record):
    value=record.get('process_cgroup')
    if not value:return None
    base=Path('/sys/fs/cgroup')/RUNTIME.name
    path=Path(value)
    expected=base/(record['task_id']+'-'+str(record['domain_id']))
    if path!=expected or path.is_symlink() or path.resolve()!=expected:raise RuntimeError('Task cgroup identity mismatch')
    if path.stat().st_uid!=0 or record.get('cgroup_inode') and path.stat().st_ino!=record['cgroup_inode']:raise RuntimeError('Task cgroup owner/inode mismatch')
    return path

def create_task_cgroup(task_id,domain_id):
    base=Path('/sys/fs/cgroup')/RUNTIME.name
    if not re.fullmatch(r'[a-zA-Z0-9-]+',RUNTIME.name):raise ValueError('Invalid cgroup profile')
    base.mkdir(mode=0o700,exist_ok=True)
    if base.is_symlink() or base.stat().st_uid!=0 or base.stat().st_mode&0o022:raise RuntimeError('Unsafe cgroup profile')
    path=base/(task_id+'-'+str(domain_id));path.mkdir(mode=0o700)
    return {'process_cgroup':str(path),'cgroup_inode':path.stat().st_ino}

def cgroup_state(path):
    return dict(line.split() for line in (path/'cgroup.events').read_text().splitlines())

def kill_task_cgroup(record):
    path=task_cgroup(record)
    if not path:return []
    # A root-owned process scope is independent of policy membership maps. It
    # also owns detached children and old writable FDs/shared mappings.
    (path/'cgroup.freeze').write_text('1')
    deadline=time.monotonic()+5
    while cgroup_state(path).get('frozen')!='1':
        if time.monotonic()>=deadline:raise RuntimeError('Task cgroup did not freeze')
        time.sleep(.02)
    members=[int(pid) for pid in (path/'cgroup.procs').read_text().split()]
    (path/'cgroup.kill').write_text('1')
    deadline=time.monotonic()+5
    while cgroup_state(path).get('populated')!='0':
        if time.monotonic()>=deadline:raise RuntimeError('Task cgroup did not quiesce')
        time.sleep(.02)
    return members

def quiesce_domain(record):
    # Stop every member from the authoritative kernel map, including detached
    # descendants; pidfds prevent signalling an unrelated reused PID.
    scoped_killed=kill_task_cgroup(record)
    handles={}
    for attempt in range(20):
        members=domain_members(record)
        for pid in members:
            try:
                status=(Path("/proc")/str(pid)/"status").read_text()
                tgid=int(next(l.split()[1] for l in status.splitlines() if l.startswith("Tgid:")))
                if tgid not in handles:handles[tgid]=os.pidfd_open(tgid)
                signal.pidfd_send_signal(handles[tgid],signal.SIGSTOP)
            except (ProcessLookupError,FileNotFoundError):pass
        again=domain_members(record)
        if set(again)<=set(members):break
        time.sleep(.05)
    killed=list(scoped_killed)
    for pid,fd in handles.items():
        try:signal.pidfd_send_signal(fd,signal.SIGKILL);killed.append(pid)
        except ProcessLookupError:pass
        finally:os.close(fd)
    for attempt in range(40):
        if not domain_members(record):return killed
        time.sleep(.05)
    raise RuntimeError("Task domain did not quiesce; replacement policy is blocked")

def remove_task_engine(record):
    group=task_cgroup(record)
    if group:
        if cgroup_state(group).get("populated")!="0":raise RuntimeError("Refusing to remove a populated task cgroup")
        group.rmdir()
    if not record.get("pin_root"):return
    base=Path(os.environ["ACTPLANE_BPF_PIN_ROOT"]).resolve()
    target=Path(record["pin_root"]).resolve()
    if target.parent!=base or target.name!=record["task_id"]:raise RuntimeError("Engine cleanup path mismatch")
    if target.exists():shutil.rmtree(target)

def stop(task_id):
    checked_task(task_id)
    with LOCK: record=TASKS.get(task_id)
    if not record: return {"task_id":task_id,"status":"not_running"}
    killed=quiesce_domain(record) if record.get("scope_mode")=="managed-web" else []
    try: run_actplane(["--policy",record["watch_policy"],"control","stop","--child-id",record["domain_id"]],record["workspace"],child_env(task_id=task_id),10)
    except Exception: pass
    try: record["watch"].send_signal(signal.SIGINT)
    except Exception: pass
    try: record["watch"].wait(timeout=5)
    except Exception:
        record["watch"].terminate()
        try: record["watch"].wait(timeout=3)
        except Exception: record["watch"].kill()
    try: record["anchor"].terminate(); record["anchor"].wait(timeout=3)
    except Exception: pass
    try:
        with open(record["watch_log"],"a") as log: log.write("\\nAgentScope: task stopped\\n")
    except Exception: pass
    remove_task_engine(record)
    with LOCK:
        TASKS.pop(task_id,None);WEB_PORTS.discard(record.get("web_port"))
    return {"task_id":task_id,"status":"stopped","domain_id":record["domain_id"],"quiesced_pids":killed,"writable_fds_and_mappings":"revoked_by_process_termination"}

def restrict(message):
    task_id=message["task_id"]; checked_task(task_id); dsl=validate_restrictive_delta(message.get("delta_text"))
    with LOCK: record=TASKS.get(task_id)
    if not record or record["watch"].poll() is not None: raise RuntimeError("任务未处于运行状态")
    if int(message.get("domain_id") or -1)!=int(record["domain_id"]): raise RuntimeError("Scope 申请目标与当前进程域不一致")
    request_id=str(message.get("request_id",""))
    if not re.fullmatch(r"[a-f0-9]{32}",request_id): raise ValueError("Scope request id invalid")
    req={"request_id":request_id,"kind":"restrict","delta_text":dsl,"approved_by":message.get("approved_by","用户"),"approval_ref":message.get("approval_ref",request_id)}
    cmd_dir=RUNTIME/"commands"/task_id; req_path=cmd_dir/"request.json"
    tmp=req_path.with_name("request.json.tmp")
    with open(tmp,"w") as f: json.dump(req,f,ensure_ascii=False); f.flush(); os.fsync(f.fileno())
    os.chown(tmp,0,TASK_GID); os.chmod(tmp,0o640); os.replace(tmp,req_path)
    result_path=Path(record["result_path"]); deadline=time.time()+22
    while time.time()<deadline:
        try:
            result=json.loads(result_path.read_text())
            if result.get("request_id")==request_id:
                if not result.get("ok"): raise RuntimeError(result.get("error") or result.get("output") or "Delta denied")
                return {"task_id":task_id,"status":"delta_applied","domain_id":record["domain_id"],"details":result}
        except FileNotFoundError: pass
        time.sleep(.25)
    raise RuntimeError("Scope relay did not acknowledge the approved Delta within 22 seconds")

_task_relay_locks={}
def dispatch(m):
    if m.get('action') in ('managed-operation','managed-verify','restrict','scope-verify','stop','launch','restart'):
        checked_task(m['task_id'])
        with LOCK:relay_lock=_task_relay_locks.setdefault(m['task_id'],threading.RLock())
        with relay_lock:return _dispatch(m)
    return _dispatch(m)

def _dispatch(m):
    action=m.get("action")
    if action=="managed-call":return managed_call(m)
    if action=="dsh-config-facts":
        import yaml
        patch=GLOBAL_DSH_HOME/"profiles/headless/cordis.patch.yml"
        raw=patch.read_bytes()
        facts={}
        def visit(value):
            if isinstance(value,dict):
                config=value.get("config")
                if isinstance(config,dict) and config.get("provider")=="deepseek-official":
                    facts.update({k:config[k] for k in ("provider","model","thinking") if k in config})
                for item in value.values():
                    if isinstance(item,(dict,list)):visit(item)
            elif isinstance(value,list):
                for item in value:visit(item)
        visit(yaml.safe_load(raw))
        python_runtime=os.getenv('AGENTSCOPE_EXPERIMENT_PYTHON_RUNTIME')
        runtime_facts={}
        if python_runtime:
            raw_runtime=(Path(python_runtime)/'runtime-facts.json').read_bytes()
            runtime_facts={'python':str(Path(python_runtime)/'bin/python'),'runtime_sha256':hashlib.sha256(raw_runtime).hexdigest(),
                           'facts':json.loads(raw_runtime)}
        return {"profile":"headless","profile_sha256":hashlib.sha256((GLOBAL_DSH_HOME/"profiles/headless/cordis.yml").read_bytes()).hexdigest(),
                "patch_sha256":hashlib.sha256(raw).hexdigest(),"model":facts.get("model"),"provider":facts.get("provider"),"thinking":facts.get("thinking","provider-default"),
                "package_version":json.loads((REPO_ROOT/"dsh/node_modules/@deepseek-ai/dsh/package.json").read_text())["version"],
                "execution_path":EXEC_PATH,"python_runtime":runtime_facts}
    if action=="health":
        return {"available":True,"backend":"ActPlaneProvider","kernel":os.uname().release,"architecture":os.uname().machine,
          "btf":Path("/sys/kernel/btf/vmlinux").exists(),"lsm":Path("/sys/kernel/security/lsm").read_text().strip(),"actplane":str(ACTPLANE),"dsh":str(DSH),"compatibility_build":"Installed local ActPlane; identify by binary hash/version and verify enforcement with runtime probes"}
    if action=="active":
        with LOCK:return {"tasks":[{"task_id":k,"version":v["version"],"domain_id":v["domain_id"],"runner_pid":v["runner_pid"],"status":"running" if v["watch"].poll() is None else "stopped"} for k,v in TASKS.items() if v["watch"].poll() is None]}
    if action=="launch": return launch(m["task_id"],m["version"],m["workspace"],m["output_dir"],m["prompt"],m["dsl_text"],m["policy_yaml"],m.get("dsh_profile","headless"),m.get("task_token",""),m.get("agentscope_url","http://127.0.0.1:8000"),m.get("scope_mode",""),m.get("protected_files"),m.get("baseline_dsl"),m.get("normalization"))
    if action=="restart":
        stop(m["task_id"])
        time.sleep(.5)
        return launch(m["task_id"],m["version"],m["workspace"],m["output_dir"],m["prompt"],m["dsl_text"],m["policy_yaml"],m.get("dsh_profile","headless"),m.get("task_token",""),m.get("agentscope_url","http://127.0.0.1:8000"))
    if action=="status": return status(m["task_id"])
    if action=="stop": return stop(m["task_id"])
    if action=="restrict": return restrict(m)
    if action=="scope-verify": return scope_verify(m)
    if action=="native-session": return native_session(m)
    if action=="managed-source-read":return managed_source_read(m)
    if action=="managed-operation":return managed_operation(m)
    if action=="managed-verify": return managed_verify(m)
    raise ValueError("未授权的 broker operation")

def scope_verify(message):
    task_id = message["task_id"]
    checked_task(task_id)
    with LOCK: record = TASKS.get(task_id)
    if not record or record.get("scope_mode") not in ("cold", "managed"): raise ValueError("Scope verification is restricted to registered demo runs")
    if int(message.get("domain_id", -1)) != record["domain_id"]: raise ValueError("Verification domain changed")
    directories = sorted(set(message.get("allowed_write_dirs", [])))
    if not set(directories) <= {"backend", "frontend"}: raise ValueError("Unregistered verification paths")
    events_path = Path(record["workspace"]) / ".actplane/events.jsonl"
    baseline = len(events_path.read_text().splitlines()) if events_path.exists() else 0
    request_id = secrets.token_hex(16)
    request = {"request_id": request_id, "kind": "scope-verify", "directories": directories, "allow_output": message.get("allow_output") is True}
    write_file(record["request_path"], json.dumps(request), 0o640)
    deadline = time.time() + 24
    while time.time() < deadline:
        try:
            result = json.loads(Path(record["result_path"]).read_text())
            if result.get("request_id") == request_id:
                if not result.get("ok"): raise RuntimeError("Scope verifier failed: " + str(result.get("error")))
                probe = result["probe"]
                break
        except FileNotFoundError: pass
        time.sleep(.2)
    else: raise RuntimeError("Scope verification relay timed out")
    time.sleep(.3)
    lines = events_path.read_text().splitlines()[baseline:] if events_path.exists() else []
    raw_events = []
    for line in lines:
        try: raw_events.append(json.loads(line))
        except ValueError: pass
    # Read authoritative kernel output and protected assets independently of Agent reports.
    # First controlled launch seals the manifest outside the Agent writable envelope.
    manifest_path = POLICY_ROOT / task_id / "scope-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    protected = {p: hashlib.sha256((Path(record["workspace"]) / p).read_bytes()).hexdigest()
                 for p in manifest if p.startswith(("tests/", "config/"))}
    integrity = all(protected[p] == manifest[p] for p in protected)
    binding = status(task_id)
    related = [e for e in raw_events if e.get("domain_id") == record["domain_id"] and e.get("blocked") is True
               and (e.get("pid") == probe["probe_pid"] or e.get("ppid") == probe["probe_pid"])]
    events_confirmed = len(related) >= probe["denied_count"] and probe["probe_ppid"] == record["runner_pid"]
    metadata = events_path.lstat()
    trusted_events = not events_path.is_symlink() and metadata.st_uid == 0 and not metadata.st_mode & 0o022
    return {"passed": probe["passed"] and integrity and events_confirmed and trusted_events and binding.get("runner_pid") == record["runner_pid"],
            "domain_id": record["domain_id"], "runner_pid": record["runner_pid"], "probe": probe,
            "kernel_events": related, "kernel_events_confirmed": events_confirmed, "root_owned_events": trusted_events,
            "protected_integrity": integrity, "protected_hashes": protected, "event_baseline": baseline,
            "source": "fixed_control_probe_and_kernel_events"}

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            raw=self.rfile.readline(2_000_001)
            if not raw or len(raw)>2_000_000: raise ValueError("broker request too large")
            cred=self.request.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12)
            pid,uid,gid=__import__('struct').unpack("3i",cred)
            if uid!=APP_USER.pw_uid: raise PermissionError("caller is not the AgentScope service user")
            result=dispatch(json.loads(raw.decode()))
            payload={"ok":True,"result":result}
        except Exception as e: payload={"ok":False,"error":str(e) or type(e).__name__}
        self.wfile.write(json.dumps(payload,ensure_ascii=False).encode()+b"\n")

class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads=True; allow_reuse_address=True

def main():
    RUNTIME.mkdir(parents=True,exist_ok=True); os.chown(RUNTIME,0,0); os.chmod(RUNTIME,0o711)
    SOCKET.parent.mkdir(parents=True,exist_ok=True); SOCKET.unlink(missing_ok=True)
    control_group=grp.getgrnam(os.getenv("AGENTSCOPE_CONTROL_GROUP","agentscope-control")).gr_gid
    server=Server(str(SOCKET),Handler); os.chown(SOCKET,0,control_group); os.chmod(SOCKET,0o660)
    print(f"AgentScope privileged ActPlane broker listening on {SOCKET}",flush=True)
    server.serve_forever()

if __name__=="__main__": main()

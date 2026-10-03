#!/usr/bin/env python3
"""Root-only, allowlisted ActPlane broker. FastAPI never receives a shell."""
import grp, hashlib, json, os, pwd, re, secrets, shutil, signal, socket, socketserver, subprocess, sys, tempfile, threading, time
from pathlib import Path

ACTPLANE=Path(os.getenv("ACTPLANE_BIN","/opt/agentscope/bin/actplane"))
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
TASK_ID_RE=re.compile(r"^[a-f0-9]{16}$")

def child_env(agent=False):
    home=AGENT.pw_dir if agent else SERVICE_HOME
    result={"PATH":EXEC_PATH,
      "HOME":home,"USER":AGENT.pw_name if agent else "root","LOGNAME":AGENT.pw_name if agent else "root",
      "NO_PROXY":"*","no_proxy":"*","LANG":"C.UTF-8"}
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

def compile_policy(task_id,version,yaml_text,dsl_text,workspace):
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

def control_state(policy_path): return Path(policy_path).parent/".actplane"/"control.json"

def grant_agent_control_access(policy_path):
    """Expose only this task domain's ActPlane control state to its in-domain relay."""
    root=control_state(policy_path).parent
    if not root.exists(): raise RuntimeError("ActPlane control state directory is missing")
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
            os.chmod(path,0o660 if path.name=="control.json" else 0o640)

def grant_api_event_access(workspace):
    """Allow the API task group to read kernel events without write access."""
    event_dir=Path(workspace)/".actplane"
    if not event_dir.exists(): return
    if event_dir.is_symlink(): raise RuntimeError("ActPlane event directory cannot be a symlink")
    event_dir=path_under(event_dir,workspace)
    os.chown(event_dir,-1,TASK_GID); os.chmod(event_dir,0o2750)
    events=event_dir/"events.jsonl"
    if events.exists():
        if events.is_symlink(): raise RuntimeError("ActPlane events cannot be a symlink")
        events=path_under(events,workspace)
        os.chown(events,-1,TASK_GID); os.chmod(events,0o640)

def launch(task_id,version,workspace,output_dir,prompt,dsl_text,policy_yaml,dsh_profile="headless",task_token="",agentscope_url="http://127.0.0.1:8000"):
    checked_task(task_id)
    if dsh_profile!="headless": raise ValueError("AgentScope 当前仅开放 DSH headless profile")
    if not DSH.exists(): raise RuntimeError(f"DSH CLI 不存在：{DSH}")
    if not RUNNER.exists(): raise RuntimeError(f"任务运行器不存在：{RUNNER}")
    if len(task_token)<32: raise ValueError("AgentScope 任务凭据缺失或无效")
    workspace=path_under(workspace,WORKSPACES)
    output=path_under(output_dir,OUTPUTS)
    if len(prompt)>8000: raise ValueError("任务提示词过长")
    with LOCK:
        for other in TASKS.values():
            if other.get("watch") and other["watch"].poll() is None:
                raise RuntimeError("ActPlane 当前使用单例运行时；请先停止现有 Agent 任务")
        files=compile_policy(task_id,version,policy_yaml,dsl_text,workspace)
        policy_path=files["policy_path"]; watch_path=files["watch_path"]
        dsh_home=prepare_task_dsh_home(workspace.parent)
        log_dir=LOG_DIR; log_dir.mkdir(parents=True,exist_ok=True)
        watch_log=open(log_dir/f"{task_id}-v{version}-watch.log","a",buffering=1)
        # Scope restrictions can be approved during a task, so the ActPlane
        # watch engine must reserve file-flow hooks before its child domain is
        # created. The engine cannot enable write-rule classes retroactively.
        env=child_env(); env.update({"ACTPLANE_ATTACH_PID":"0","ACTPLANE_RESERVE_FILE_FLOW":"1",
                                     "SUDO_UID":str(AGENT.pw_uid),"SUDO_GID":str(TASK_GID)})
        anchor=subprocess.Popen(["/usr/bin/sleep","infinity"],cwd=workspace,env=child_env(True),preexec_fn=user_preexec,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        env["ACTPLANE_ATTACH_PID"]=str(anchor.pid)
        watch=subprocess.Popen([str(ACTPLANE),"--policy",watch_path,"watch"],cwd=workspace,env=env,stdout=watch_log,stderr=subprocess.STDOUT,start_new_session=True)
        deadline=time.time()+25
        while time.time()<deadline:
            if watch.poll() is not None:
                anchor.terminate()
                watch_log.flush(); watch_log.close()
                raise RuntimeError((log_dir/f"{task_id}-v{version}-watch.log").read_text(errors="replace")[-5000:])
            if control_state(watch_path).exists():
                grant_agent_control_access(watch_path)
                grant_api_event_access(workspace)
                break
            time.sleep(.2)
        else:
            watch.terminate(); anchor.terminate()
            raise RuntimeError("ActPlane watch 启动超时；请检查 /var/log/agentscope/*-watch.log")
        domain=secrets.randbelow(1_800_000_000)+100_000_000
        result_path=workspace.parent/"tmp"/"scope-result.json"
        task_env_path=result_path.parent/"agent-env.json"
        command=["--policy",watch_path,"control","launch-child","--child-id",str(domain),"--delta",files["dsl_path"],"--","/usr/bin/python3",str(RUNNER),
          "--task-id",task_id,"--domain-id",str(domain),"--env-file",str(task_env_path),"--request-file",str(RUNTIME/"commands"/task_id/"request.json"),
          "--result-file",str(workspace.parent/"tmp"/"scope-result.json"),"--watch-policy",watch_path,"--actplane",str(ACTPLANE),
          "--workspace",str(workspace),"--dsh",str(DSH),"--dsh-home",str(dsh_home),"--profile",dsh_profile,"--prompt",prompt]
        cmd_root=RUNTIME/"commands"; cmd_root.mkdir(parents=True,exist_ok=True); os.chown(cmd_root,0,0); os.chmod(cmd_root,0o711)
        cmd_dir=cmd_root/task_id; cmd_dir.mkdir(parents=True,exist_ok=True); os.chown(cmd_dir,0,TASK_GID); os.chmod(cmd_dir,0o750)
        request_path=cmd_dir/"request.json"; request_path.unlink(missing_ok=True)
        result_path.parent.mkdir(parents=True,exist_ok=True); os.chown(result_path.parent,0,TASK_GID); os.chmod(result_path.parent,0o2770)
        write_file(task_env_path,json.dumps({"task_id":task_id,"task_token":task_token,"agentscope_url":agentscope_url}),0o660)
        os.chown(result_path.parent,0,TASK_GID); os.chmod(result_path.parent,0o2770)
        result_path.unlink(missing_ok=True)
        # ActPlane's watch daemon launches the child with its own environment,
        # not the launch-child CLI caller's environment. Pass task credentials
        # through a one-time task file; task_runner scrubs it before starting DSH.
        launch_env=child_env(); launch_env.update({"SUDO_UID":str(AGENT.pw_uid),"SUDO_GID":str(TASK_GID),"TMPDIR":str(workspace.parent/"tmp")})
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
          "request_path":str(request_path),"result_path":str(result_path),"dsl_path":files["dsl_path"]}
        TASKS[task_id]=record
        return {"task_id":task_id,"status":"running","runner_pid":runner_pid,"domain_id":domain_id,"watch_pid":watch.pid,
                "version":version,"compile_state":"loaded","compile":files["compile"],"message":"ActPlane 控制平面已加载；DSH 已由 child domain 接管"}

def status(task_id):
    checked_task(task_id)
    with LOCK: record=TASKS.get(task_id)
    if not record: return {"available":False,"status":"unknown"}
    if record["watch"].poll() is not None: state="stopped"
    else: state="running"
    output="[]"
    try: output=run_actplane(["--policy",record["watch_policy"],"control","children"],record["workspace"],child_env(),6)
    except Exception as e: return {"available":True,"status":state,"error":str(e),"domain_id":record["domain_id"],"runner_pid":record["runner_pid"]}
    try: children=json.loads(output)
    except Exception: children=[]
    child=next((c for c in children if int(c.get("child_id",-1))==record["domain_id"]),None)
    status=(child or {}).get("status",{})
    return {"available":True,"status":state,"agent_status":status.get("state","unknown"),"domain_id":record["domain_id"],"runner_pid":record["runner_pid"],"watch_pid":record["watch_pid"],"child":child}

def stop(task_id):
    checked_task(task_id)
    with LOCK: record=TASKS.pop(task_id,None)
    if not record: return {"task_id":task_id,"status":"not_running"}
    try: run_actplane(["--policy",record["watch_policy"],"control","stop","--child-id",record["domain_id"]],record["workspace"],child_env(),10)
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
    return {"task_id":task_id,"status":"stopped","domain_id":record["domain_id"]}

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

def dispatch(m):
    action=m.get("action")
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
    if action=="launch": return launch(m["task_id"],m["version"],m["workspace"],m["output_dir"],m["prompt"],m["dsl_text"],m["policy_yaml"],m.get("dsh_profile","headless"),m.get("task_token",""),m.get("agentscope_url","http://127.0.0.1:8000"))
    if action=="restart":
        stop(m["task_id"])
        time.sleep(.5)
        return launch(m["task_id"],m["version"],m["workspace"],m["output_dir"],m["prompt"],m["dsl_text"],m["policy_yaml"],m.get("dsh_profile","headless"),m.get("task_token",""),m.get("agentscope_url","http://127.0.0.1:8000"))
    if action=="status": return status(m["task_id"])
    if action=="stop": return stop(m["task_id"])
    if action=="restrict": return restrict(m)
    raise ValueError("未授权的 broker operation")

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
        except Exception as e: payload={"ok":False,"error":str(e)}
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

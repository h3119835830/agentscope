#!/usr/bin/env python3
"""Runs DSH inside one ActPlane child domain and relays approved restrictive deltas."""
import argparse, grp, hashlib, json, os, pwd, stat, subprocess, sys, time
from pathlib import Path

def write_result(path, value):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(".tmp")
    tmp.write_text(json.dumps(value,ensure_ascii=False))
    os.replace(tmp,p)

def consume_agent_env(path, task_id):
    """Read and scrub the one-time, root-created DSH credential handoff."""
    p=Path(path)
    fd=os.open(p,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        st=os.fstat(fd)
        task_gid=grp.getgrnam("agentscope-task").gr_gid
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or st.st_gid!=task_gid:
            raise ValueError("DSH credential handoff is not a protected task file")
        if not st.st_mode & 0o040 or not st.st_mode & 0o020 or st.st_mode & 0o007:
            raise ValueError("DSH credential handoff permissions are invalid")
        if st.st_size>4096:
            raise ValueError("DSH credential handoff is too large")
        raw=os.read(fd,4097)
        os.lseek(fd,0,os.SEEK_SET)
        os.write(fd,b"\0"*len(raw))
        os.ftruncate(fd,0)
        os.fsync(fd)
        value=json.loads(raw)
        if value.get("task_id")!=task_id or len(value.get("task_token",""))<32:
            raise ValueError("DSH task credential is missing or mismatched")
        if not isinstance(value.get("agentscope_url"),str) or not value["agentscope_url"].startswith("http://127.0.0.1:"):
            raise ValueError("AgentScope service URL is invalid")
        return value
    finally:
        os.close(fd)

def handle_request(req, args):
    if req.get("kind") in ("managed-operation","managed-hold","managed-verify"):
        import selectors
        read_fd,write_fd=os.pipe()
        request={**req,"ready_fd":read_fd}
        helper="managed_probe.py" if req["kind"]=="managed-verify" else "managed_operation_probe.py"
        child=subprocess.Popen(["/usr/bin/python3",str(Path(__file__).with_name(helper)),json.dumps(request)],cwd=args.workspace,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True,pass_fds=(read_fd,),preexec_fn=demote_agent if os.getuid()==0 else None)
        os.close(read_fd)
        registry=Path(args.workspace)/".actplane/probes.jsonl"
        fd=os.open(registry,os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o640)
        try:
            os.fchown(fd,0,grp.getgrnam("agentscope-task").gr_gid)
            os.write(fd,(json.dumps({"pid":child.pid,"domain_id":args.domain_id,"request_id":req["request_id"]})+"\n").encode());os.fsync(fd)
        finally:os.close(fd)
        os.write(write_fd,b"1");os.close(write_fd)
        try:
            if req["kind"]=="managed-hold":
                with selectors.DefaultSelector() as selector:
                    selector.register(child.stdout,selectors.EVENT_READ)
                    if not selector.select(10):raise TimeoutError("held capability probe timed out")
                return {"request_id":req["request_id"],"ok":True,"probe":json.loads(child.stdout.readline())}
            stdout,stderr=child.communicate(timeout=20)
            return {"request_id":req["request_id"],"ok":child.returncode==0,"probe":json.loads(stdout)}
        except Exception:
            child.kill();child.wait();raise
    if req.get("kind") == "scope-verify":
        command = ["/usr/bin/python3", str(Path(__file__).with_name("scope_probe.py")),
                   "--workspace", args.workspace, "--dirs", ",".join(req["directories"])]
        if req.get("allow_output"): command.append("--output")
        command += ["--control-state", str(Path(args.watch_policy).parent / ".actplane/control.json")]
        fd = getattr(args, "held_fd", None)
        if fd is not None: command += ["--held-fd", str(fd)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=20, pass_fds=(fd,) if fd is not None else (),
                                preexec_fn=demote_agent if os.getuid()==0 else None)
        try: probe = json.loads(result.stdout)
        except ValueError: return {"request_id": req["request_id"], "ok": False, "error": result.stderr[-1200:]}
        return {"request_id": req["request_id"], "ok": result.returncode == 0, "probe": probe}
    if req.get("kind")!="restrict" or not req.get("delta_text"):
        return {"request_id":req.get("request_id"),"ok":False,"error":"只接受已经审核的限制型 Delta"}
    dsl=req["delta_text"]
    if len(dsl)>12000 or "source " in dsl or any(word in dsl for word in (" allow ","widen","permit")):
        return {"request_id":req.get("request_id"),"ok":False,"error":"Delta 不符合限制型规则格式"}
    cmd=[args.actplane,"--policy",args.watch_policy,"control","delta","add",
         "--target-id",str(args.domain_id),"--delta-text",dsl,
         "--approved-by",str(req.get("approved_by","用户")),
         "--approval-ref",str(req.get("approval_ref",req.get("request_id",""))),
         "--generated-by","AgentScope"]
    env={"PATH":os.environ.get("AGENTSCOPE_EXEC_PATH",os.environ.get("PATH","/usr/local/bin:/usr/bin:/bin")),
         "HOME":os.environ.get("HOME","/var/lib/agentscope-agent"),"USER":os.environ.get("USER","agentscope-agent"),
         "LOGNAME":os.environ.get("LOGNAME","agentscope-agent"),"TMPDIR":str(Path(args.workspace).parent/"tmp"),"NO_PROXY":"*","no_proxy":"*"}
    if os.getenv("ACTPLANE_BPF_PIN_ROOT"): env["ACTPLANE_BPF_PIN_ROOT"]=os.environ["ACTPLANE_BPF_PIN_ROOT"]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=30,env=env,cwd=args.workspace)
    return {"request_id":req.get("request_id"),"ok":p.returncode==0,"output":p.stdout[-4000:],"error":p.stderr[-4000:],"applied_at":time.time()}

def demote_agent():
    agent = pwd.getpwnam(os.getenv("AGENTSCOPE_AGENT_USER", "agentscope-agent"))
    group = grp.getgrnam(os.getenv("AGENTSCOPE_TASK_GROUP", "agentscope-task")).gr_gid
    os.setgroups([group])
    os.setgid(group)
    os.setuid(agent.pw_uid)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--task-id",required=True); ap.add_argument("--domain-id",required=True,type=int)
    ap.add_argument("--env-file",required=True)
    ap.add_argument("--request-file",required=True); ap.add_argument("--result-file",required=True)
    ap.add_argument("--watch-policy",required=True); ap.add_argument("--actplane",required=True)
    ap.add_argument("--workspace",required=True); ap.add_argument("--dsh",required=True)
    ap.add_argument("--dsh-home",required=True)
    ap.add_argument("--profile",default="headless"); ap.add_argument("--prompt",required=True)
    args=ap.parse_args()
    try:
        task_env=consume_agent_env(args.env_file,args.task_id)
    except Exception as e:
        print(f"AgentScope: unable to consume task credential handoff: {e}",file=sys.stderr,flush=True)
        return 78
    env=os.environ.copy()
    env.update({"HOME":str(Path(args.dsh_home).parent),"DSH_HOME":args.dsh_home,
       "PATH":os.environ.get("AGENTSCOPE_EXEC_PATH",os.environ.get("PATH","/usr/local/bin:/usr/bin:/bin")),
       "AGENTSCOPE_TASK_ID":args.task_id,"AGENTSCOPE_TASK_TOKEN":task_env["task_token"],
       "AGENTSCOPE_URL":task_env["agentscope_url"],"NO_PROXY":"*","no_proxy":"*"})
    scope_mode = task_env.get("scope_mode", "")
    if scope_mode:
        agent = pwd.getpwnam(os.getenv("AGENTSCOPE_AGENT_USER", "agentscope-agent"))
        env.update(USER=agent.pw_name, LOGNAME=agent.pw_name)
        env["AGENTSCOPE_SCOPE_MANAGER"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["TMPDIR"] = str(Path(args.workspace).parent / "tmp")
        try: args.held_fd = os.open(str(Path(args.workspace) / "frontend/scope-held.txt"), os.O_RDWR)
        except OSError: args.held_fd = None
    command=[args.dsh,"--profile",args.profile,args.prompt]
    if scope_mode=="managed-web":
        env.update(AGENTSCOPE_MANAGED_WORKSPACE=args.workspace,AGENTSCOPE_NATIVE_PORT=str(task_env["web_port"]+100),AGENTSCOPE_NATIVE_TOKEN=task_env["native_token"])
        command=[args.dsh,"web","--host","127.0.0.1","--port",str(task_env["web_port"]),"--no-open"]
    try:
        # DSH's sandbox binds its session cwd as its single writable root.
        # Use this task's isolated root as the outer envelope; ActPlane still
        # decides the approved repository/output permissions within that root.
        dsh=subprocess.Popen(command,cwd=str(Path(args.workspace).parent),env=env,
                             preexec_fn=demote_agent if scope_mode and os.getuid()==0 else None) if scope_mode != "cold" else None
    except Exception as e:
        print(f"AgentScope: unable to launch DSH: {e}",file=sys.stderr,flush=True); return 127
    print(f"AgentScope: runner mode={scope_mode or 'legacy'} dsh_pid={dsh.pid if dsh else None} profile={args.profile}",flush=True)
    last_request=""
    req_path=Path(args.request_file)
    while scope_mode or (dsh and dsh.poll() is None):
        try:
            if req_path.exists():
                req=json.loads(req_path.read_text())
                rid=str(req.get("request_id",""))
                if rid and rid!=last_request:
                    result=handle_request(req,args)
                    last_request=rid
                    write_result(args.result_file,result)
                    print("AgentScope: approved runtime restriction "+("applied" if result["ok"] else "failed")+f" request={rid}",flush=True)
        except subprocess.TimeoutExpired as e:
            write_result(args.result_file,{"request_id":req.get("request_id"),"ok":False,"error":"ActPlane Delta timed out"})
        except Exception as e:
            print(f"AgentScope: runtime relay error: {e}",file=sys.stderr,flush=True)
        time.sleep(0.25)
    return dsh.wait() if dsh else 0

if __name__=="__main__": raise SystemExit(main())

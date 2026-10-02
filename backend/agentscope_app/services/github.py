from pathlib import Path
import hashlib, json, re, subprocess, uuid, grp, os
from ..config import EXEC_PATH, SERVICE_HOME, WORKSPACE_ROOT, OUTPUT_ROOT
from ..db import connect, now

DOC_NAMES = {"AGENTS.md", "CLAUDE.md", "README.md", "README.rst", "README.txt", "SECURITY.md", "CONTRIBUTING.md"}

def parse_github_url(value: str):
    m=re.fullmatch(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?",value.strip())
    if not m: raise ValueError("请输入 https://github.com/owner/repository 格式的 GitHub 仓库地址")
    owner,name=m.group(1),m.group(2)
    return f"{owner}/{name}",f"https://github.com/{owner}/{name}.git"

def run_git(args, cwd=None):
    env={"PATH":EXEC_PATH,"GIT_TERMINAL_PROMPT":"0","HOME":str(SERVICE_HOME)}
    p=subprocess.run(["/usr/bin/git",*args],cwd=cwd,env=env,text=True,capture_output=True,timeout=300)
    if p.returncode: raise RuntimeError((p.stderr or p.stdout)[-1600:])
    return p.stdout.strip()

def prepare(req: dict):
    repo,git_url=parse_github_url(req["repo_url"])
    task_id=uuid.uuid4().hex[:16]
    task_root=WORKSPACE_ROOT/task_id
    root=task_root/"repo"
    output=task_root/"output"
    task_root.mkdir(parents=True)
    task_gid=grp.getgrnam("agentscope-task").gr_gid
    os.chown(task_root,-1,task_gid); os.chmod(task_root,0o2770)
    root.mkdir(); output.mkdir(); (task_root/"tmp").mkdir()
    run_git(["init","--quiet"],root)
    run_git(["remote","add","origin",git_url],root)
    ref=req.get("ref", "main").strip()
    if not ref or ref.startswith("-") or len(ref)>240: raise ValueError("Git 引用格式不合法")
    run_git(["fetch","--depth=1","origin",ref],root)
    commit=run_git(["rev-parse","FETCH_HEAD"],root)
    run_git(["checkout","--detach","FETCH_HEAD"],root)
    # Group writable worktree lets the isolated DSH account update tracked files.
    os.chown(root,-1,task_gid); os.chown(output,-1,task_gid); os.chown(task_root/"tmp",-1,task_gid)
    os.chmod(root,0o2770); os.chmod(output,0o2770)
    env={"PATH":EXEC_PATH,"GIT_TERMINAL_PROMPT":"0","HOME":str(SERVICE_HOME)}
    subprocess.run(["/usr/bin/find",str(root),"-type","d","-exec","chmod","g+rwx","{}","+"],env=env,check=False,capture_output=True)
    subprocess.run(["/usr/bin/find",str(root),"-type","f","-exec","chmod","g+rw","{}","+"],env=env,check=False,capture_output=True)
    for base, dirs, files in os.walk(root):
        for name in dirs + files:
            os.chown(Path(base)/name,-1,task_gid)
    os.chmod(task_root/"tmp",0o2770)
    os.chmod(root,0o2770); os.chmod(output,0o2770)
    docs=[]
    for p in root.rglob("*"):
        if not p.is_file() or ".git" in p.parts or "node_modules" in p.parts: continue
        if p.name not in DOC_NAMES and not (p.parts and p.parts[0]==".github" and p.suffix in (".yml",".yaml")): continue
        try: body=p.read_text(errors="replace")
        except Exception: continue
        if len(body)>40000: body=body[:40000]
        rel=p.relative_to(root).as_posix()
        digest=hashlib.sha256(body.encode()).hexdigest()
        ghpath=rel.replace(" ","%20")
        uri=f"https://github.com/{repo}/blob/{commit}/{ghpath}"
        # Excerpts are contextual evidence; they are not treated as executable policy.
        for start in range(0,min(len(body.splitlines()),1600),1):
            line=body.splitlines()[start]
            if not line.strip() or len(line)>1200: continue
            if p.name in ("AGENTS.md","CLAUDE.md","SECURITY.md") or start<60:
                docs.append({"kind":"agent_instruction" if p.name in ("AGENTS.md","CLAUDE.md") else "project_document",
                    "title":f"{rel}:{start+1}","uri":uri,"file_path":rel,"commit_sha":commit,
                    "line_start":start+1,"line_end":start+1,"excerpt":line.strip()[:1200],
                    "content_sha256":hashlib.sha256(line.encode()).hexdigest(),"metadata_json":json.dumps({"document":p.name})})
                if len(docs)>=120: break
        if len(docs)>=120: break
    name=f"{repo} @ {commit[:8]}"
    created=now()
    with connect() as con:
        con.execute("INSERT INTO tasks(id,name,repo_url,repo,commit_sha,ref_requested,workspace,output_dir,prompt,agent,dsh_profile,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
           (task_id,name,req["repo_url"],repo,commit,ref,str(root),str(output),req["prompt"],"dsh",req.get("dsh_profile","headless"),"prepared",created,created))
        for ev in docs:
            con.execute("INSERT INTO evidence(id,task_id,kind,title,uri,file_path,commit_sha,line_start,line_end,excerpt,content_sha256,collected_at,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
             (uuid.uuid4().hex,task_id,ev["kind"],ev["title"],ev["uri"],ev["file_path"],ev["commit_sha"],ev["line_start"],ev["line_end"],ev["excerpt"],ev["content_sha256"],created,ev["metadata_json"]))
    return {"id":task_id,"name":name,"repo":repo,"commit_sha":commit,"workspace":str(root),"output_dir":str(output),"evidence_count":len(docs)}

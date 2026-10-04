import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import urllib.parse
import urllib.request
import urllib.error
import subprocess
import uuid
from .. import db
from ..config import STATE_DIR
from ..services.github import parse_github_url
from .models import MarkdownDocument, Origin

ROOT = STATE_DIR / "history-library" / "sources"

def relative_path(value):
    p=PurePosixPath(value)
    if not value or p.is_absolute() or "\\" in value or any(x in ("","..",".") for x in value.split("/")):
        raise ValueError("文件路径必须为规范的仓库相对路径")
    return p.as_posix()

def fetch(url, limit=2_000_000):
    request=urllib.request.Request(url,headers={"User-Agent":"AgentScope-History/1","Accept":"application/vnd.github+json"})
    with urllib.request.urlopen(request,timeout=30) as response:
        if urllib.parse.urlparse(response.geturl()).hostname not in ("api.github.com","raw.githubusercontent.com"):
            raise ValueError("GitHub 下载跳转到非允许主机")
        body=response.read(limit+1)
    if len(body)>limit: raise ValueError("GitHub 响应超过大小限制")
    return body

def git_snapshot(repo,ref):
    from ..config import EXEC_PATH,SERVICE_HOME
    cache=STATE_DIR/"history-library"/"git-cache"/repo
    cache.mkdir(parents=True,exist_ok=True)
    env={"PATH":EXEC_PATH,"HOME":str(SERVICE_HOME),"GIT_TERMINAL_PROMPT":"0"}
    def git(*args):
        result=subprocess.run(["/usr/bin/git","-c","core.hooksPath=/dev/null","-c","protocol.file.allow=never",*args],
            cwd=cache,env=env,capture_output=True,timeout=300)
        if result.returncode: raise RuntimeError("Git 快照读取失败："+result.stderr.decode(errors="replace")[-1000:])
        return result.stdout
    if not (cache/"HEAD").exists(): git("init","--bare","--quiet")
    git("fetch","--depth=1","https://github.com/"+repo+".git",ref)
    commit=git("rev-parse","FETCH_HEAD").decode().strip()
    files={}
    for entry in git("ls-tree","-r","-z",commit).decode("utf-8").split("\0"):
        if not entry: continue
        info,path=entry.split("\t",1);mode,kind,sha=info.split()
        if kind=="blob": files[relative_path(path)]={"mode":mode,"sha":sha}
    def read_blob(path):
        ident=files[path]["sha"]
        size=int(git("cat-file","-s",ident))
        if size>512000: raise ValueError("文档超过 512KB："+path)
        return git("cat-file","blob",ident)
    return commit,files,read_blob


def collect_documents(repo_url, ref="main", additional_paths=None, *, reader=fetch, include_instruction_files=True):
    repo,_=parse_github_url(repo_url)
    if any(p in (".","..") for p in repo.split("/")): raise ValueError("仓库路径不合法")
    if not ref or ref.startswith("-") or len(ref)>240: raise ValueError("Git 引用不合法")
    extra={relative_path(x) for x in (additional_paths or [])}
    try:
        commit=json.loads(reader(f"https://api.github.com/repos/{repo}/commits/{urllib.parse.quote(ref,safe='')}"))["sha"]
        if len(commit)!=40 or not all(x in "0123456789abcdef" for x in commit): raise ValueError("GitHub 未返回完整 SHA")
        tree=json.loads(reader(f"https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1"))
        entries=tree.get("tree",[])
        if tree.get("truncated"):
            entries=[]; stack=[("",commit)]
            while stack:
                prefix,sha=stack.pop()
                node=json.loads(reader(f"https://api.github.com/repos/{repo}/git/trees/{sha}"))
                if node.get("truncated"): raise ValueError("GitHub 子目录仍被截断")
                for item in node.get("tree",[]):
                    path=prefix+item["path"]
                    if item["type"]=="tree": stack.append((path+"/",item["sha"]))
                    else: entries.append({**item,"path":path})
                if len(entries)>50000: raise ValueError("仓库文件数超过上限")
        files={relative_path(x["path"]):x for x in entries if x["type"]=="blob"}
        read_raw=lambda path:reader(f"https://raw.githubusercontent.com/{repo}/{commit}/{urllib.parse.quote(path,safe='/')}")
    except urllib.error.HTTPError as e:
        if e.code not in (403,429): raise
        commit,files,read_raw=git_snapshot(repo,ref)
    missing=sorted(extra-files.keys())
    if missing: raise ValueError("指定文件不存在："+", ".join(missing))
    selected=sorted(p for p in files if (include_instruction_files and PurePosixPath(p).name in ("AGENTS.md","CLAUDE.md")) or p in extra)
    ids=[]; total=0
    for path in selected:
        item=files[path]
        if item.get("mode")=="120000": raise ValueError("采集不跟随符号链接："+path)
        if int(item.get("size",0))>512000: raise ValueError("文档超过 512KB："+path)
        try:
            raw=read_raw(path)
        except urllib.error.HTTPError as e:
            if e.code not in (403,429): raise
            fallback_commit,_,read_raw=git_snapshot(repo,commit)
            if fallback_commit!=commit: raise ValueError("Git 回退快照 commit 不一致")
            raw=read_raw(path)
        total+=len(raw)
        if len(raw)>512000 or total>10_000_000: raise ValueError("文档采集超过大小上限")
        raw.decode("utf-8")
        sha=hashlib.sha256(raw).hexdigest()
        dest=ROOT/repo/commit/path; dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():
            if dest.read_bytes()!=raw: raise ValueError("不可变快照内容冲突")
        else:
            with dest.open("xb") as h: h.write(raw)
            os.chmod(dest,0o440)
        with db.connect() as con:
            old=con.execute("SELECT id FROM history_documents WHERE repository=? AND commit_sha=? AND relative_path=? AND content_sha256=?",(repo,commit,path,sha)).fetchone()
            ident=old["id"] if old else uuid.uuid4().hex
            if not old:
                con.execute("INSERT INTO history_documents VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (ident,repo,ref,commit,path,str(PurePosixPath(path).parent) if "/" in path and PurePosixPath(path).name in ("AGENTS.md","CLAUDE.md") else "",str(dest),sha,len(raw),
                     f"https://github.com/{repo}/blob/{commit}/{urllib.parse.quote(path,safe='/')}",db.now()))
            ids.append(ident)
    return {"repository":repo,"commit":commit,"document_ids":ids,"file_count":len(ids)}

def read_document(ident):
    with db.connect() as con: row=con.execute("SELECT * FROM history_documents WHERE id=?",(ident,)).fetchone()
    if not row: raise ValueError("文档不存在")
    path=Path(row["snapshot_path"]).resolve(); path.relative_to(ROOT.resolve())
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=row["content_sha256"]: raise ValueError("快照 hash 不匹配")
    return MarkdownDocument(text=raw.decode("utf-8"),origin=Origin(document_id=row["id"],repository=row["repository"],
        commit=row["commit_sha"],path=row["relative_path"],content_hash=row["content_sha256"],url=row["source_url"]))

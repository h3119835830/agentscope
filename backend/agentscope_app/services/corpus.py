import csv, hashlib, json, re, urllib.request, urllib.error, uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from ..config import CORPUS_ROOT, STATE_DIR
from ..db import connect, now

CACHE=STATE_DIR/"source-snapshots"

def normal(value):
    s=value.strip().lower().replace("`","").replace("**","").replace("__","")
    s=re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)","",s)
    return " ".join(re.findall(r"[a-z0-9_./:#-]+|[\u4e00-\u9fff]+",s))

def category(text):
    t=text.lower()
    if re.search(r"\b(before|after|until|since|first|then|before committing|after changing|test.*commit)\b",t): return "cross-event",0.78
    if re.search(r"\b(allow|deny|block|forbid|must not|never|only|permission|network|write|read|execute|command|secret|credential|delete|push)\b",t): return "per-event",0.70
    if re.search(r"(提交前|提交后|之后|之前|先.*再|完成.*后)",text): return "cross-event",0.66
    if re.search(r"(禁止|不能|不得|只允许|权限|网络|写入|读取|删除|执行)",text): return "per-event",0.62
    return "semantic",0.42

def scope(text):
    t=text.lower()
    if re.search(r"\b(this task|current task|task-specific|during this task)\b",t): return "task"
    if re.search(r"\b(project|repository|repo|workspace|codebase)\b",t) or re.search(r"(项目|仓库|代码库|工作区)",text): return "project"
    return "self-contained"

def load_local():
    manifest=CORPUS_ROOT/"RQ1/corpus/manifest.jsonl"
    candidates=CORPUS_ROOT/"RQ1/corpus/candidate_rules.tsv"
    if not manifest.exists() or not candidates.exists(): raise FileNotFoundError(f"RQ1 语料文件缺失：{manifest} 或 {candidates}")
    repos={}
    for line in manifest.read_text(errors="replace").splitlines():
        if not line.strip(): continue
        row=json.loads(line); repo=row.get("repo","")
        repos[repo.lower()]=row
    rows=[]
    with candidates.open(encoding="utf-8",errors="replace",newline="") as f:
        for cells in csv.reader(f,delimiter="\t"):
            if len(cells)<2: continue
            slug,text=cells[0].strip(),cells[1].strip()
            if not text: continue
            repo=slug.replace("__","/").lower()
            entry=repos.get(repo)
            if not entry:
                entry=next((v for k,v in repos.items() if k.replace("/","__").lower()==slug.lower()),None)
            rows.append((slug,text,entry))
    return rows

def fetch_one(item):
    repo,file=item
    url=file.get("raw_url","")
    if not url.startswith("https://raw.githubusercontent.com/"): return item,None
    path=CACHE/hashlib.sha256(url.encode()).hexdigest()
    if path.exists():
        try:return item,path.read_text(errors="replace")
        except Exception:pass
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req=urllib.request.Request(url,headers={"User-Agent":"AgentScope-RQ1-provenance-import"})
        with opener.open(req,timeout=10) as response:
            data=response.read(1_500_001)
        if len(data)>1_500_000:return item,None
        CACHE.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
        return item,data.decode("utf-8",errors="replace")
    except Exception:return item,None

def import_rq1():
    CACHE.mkdir(parents=True,exist_ok=True)
    rows=load_local()
    refs=[]
    for _,_,repo in rows:
        if not repo: continue
        for file in repo.get("files",[]):
            refs.append((repo,file))
    unique={f.get("raw_url"): (r,f) for r,f in refs if f.get("raw_url")}
    contents={}
    with ThreadPoolExecutor(max_workers=20) as pool:
        for future in as_completed([pool.submit(fetch_one,item) for item in unique.values()]):
            (repo,file),body=future.result()
            if body is not None: contents[(repo.get("repo","").lower(),file.get("path"),file.get("last_commit_sha"))]=(repo,file,body)
    inserted=verified=unverified=0
    with connect() as con:
        for slug,text,repo in rows:
            repo_name=repo.get("repo") if repo else slug.replace("__","/")
            repo_files=[]
            if repo:
                for file in repo.get("files",[]):
                    value=contents.get((repo.get("repo","").lower(),file.get("path"),file.get("last_commit_sha")))
                    if value: repo_files.append(value)
            needle=normal(text); hit=None
            if needle:
                for source_repo,file,body in repo_files:
                    for n,line in enumerate(body.splitlines(),1):
                        line_n=normal(line)
                        if needle and (needle in line_n or line_n in needle and len(line_n)>50):
                            hit=(source_repo,file,body,n,line); break
                    if hit: break
            cat,confidence=category(text)
            record_id=uuid.uuid4().hex
            status="pending_review"
            commit=path=line_url=file_hash=None; line_start=line_end=None
            if hit:
                source_repo,file,body,n,line=hit
                commit=file.get("last_commit_sha"); path=file.get("path"); line_start=line_end=n
                line_url=f"https://github.com/{repo_name}/blob/{commit}/{file.get('path','')}#L{n}"
                file_hash=hashlib.sha256(body.encode()).hexdigest(); verified+=1
            else: unverified+=1
            source_sentence_hash=hashlib.sha256(text.encode()).hexdigest()
            metadata={"corpus":"RQ1","repo_slug":slug,"category_method":"keyword heuristic; pending human review","line_match":"normalized exact/contained match" if hit else "source line not resolved","source_families":[f.get("family") for f in (repo.get("files",[]) if repo else [])]}
            try:
                cur=con.execute("INSERT OR IGNORE INTO strategies(id,text,category,category_confidence,context_scope,execution_layer,status,source_repo,source_commit,source_path,line_start,line_end,raw_url,source_content_sha256,sentence_sha256,source_verified,source_kind,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (record_id,text,cat,confidence,scope(text),"repository_instruction",status,repo_name,commit,path,line_start,line_end,line_url,file_hash,source_sentence_hash,1 if hit else 0,"rq1_corpus",json.dumps(metadata,ensure_ascii=False),now()))
                inserted+=cur.rowcount
            except Exception: pass
        con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('rq1_imported_at',?)",(now(),))
    return {"input_count":len(rows),"inserted_count":inserted,"verified_count":verified,"unverified_count":unverified,"repositories":len({r.get("repo") for _,_,r in rows if r})}

def search(q="",limit=50,status=None):
    with connect() as con:
        sql="SELECT * FROM strategies WHERE is_archived=0"; params=[]
        if status: sql+=" AND status=?"; params.append(status)
        if q:
            sql+=" AND (text LIKE ? OR source_repo LIKE ? OR source_path LIKE ?)"; pattern=f"%{q}%"; params += [pattern]*3
        sql+=" ORDER BY source_verified DESC, created_at DESC LIMIT ?"; params.append(max(1,min(limit,500)))
        return [dict(r) for r in con.execute(sql,params).fetchall()]

def recommend(query,limit=12):
    from collections import Counter
    terms=Counter(t for t in re.findall(r"[a-z0-9_./-]+|[\u4e00-\u9fff]{2,}",query.lower()) if len(t)>1)
    records=search(limit=500,status=None)
    scored=[]
    for row in records:
        text=row["text"].lower(); words=set(re.findall(r"[a-z0-9_./-]+|[\u4e00-\u9fff]{2,}",text))
        overlap=sum(min(2,terms[w]) for w in words if w in terms)
        if overlap: scored.append((overlap,row))
    scored.sort(key=lambda x:(x[0],x[1]["source_verified"]),reverse=True)
    return [{**r,"relevance":s,"eligible_for_policy":r["status"]=="approved"} for s,r in scored[:limit]]

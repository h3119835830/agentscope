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


BUNDLED_ROOT=Path(__file__).resolve().parents[1]/"data"

def corpus_files():
    root=CORPUS_ROOT
    if not (root/"RQ1/corpus/manifest.jsonl").exists() and not (root/"RQ1/corpus/candidate_rules.tsv").exists():
        root=BUNDLED_ROOT
    directory=root/"RQ1/corpus"
    for name in ("manifest.jsonl","candidate_rules.tsv"):
        if not (directory/name).is_file(): raise FileNotFoundError("RQ1 语料文件缺失："+str(directory/name))
    return directory

def dataset_info():
    directory=corpus_files()
    hashes={name:hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in ("manifest.jsonl","candidate_rules.tsv")}
    provenance={}
    if (directory/"provenance.json").exists():
        provenance=json.loads((directory/"provenance.json").read_text())
        if provenance.get("files")!=hashes: raise ValueError("RQ1 固定快照 hash 不匹配")
    identity=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    return {"identity":identity,"files":hashes,"artifact_commit":provenance.get("commit"),
        "artifact_repository":provenance.get("repository")}

def source_import_key(slug,text):
    value="rq1\0"+slug.strip().lower()+"\0"+hashlib.sha256(text.encode()).hexdigest()
    return hashlib.sha256(value.encode()).hexdigest()

def load_local():
    directory=corpus_files()
    repos={}
    for line in (directory/"manifest.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():continue
        row=json.loads(line);repos[row.get("repo","").lower()]=row
    rows=[]
    with (directory/"candidate_rules.tsv").open(encoding="utf-8",newline="") as f:
        for cells in csv.reader(f,delimiter="\t"):
            if len(cells)<2:continue
            slug,text=cells[0].strip(),cells[1].strip()
            if not text:continue
            repo=slug.replace("__","/").lower()
            rows.append((slug,text,repos.get(repo)))
    return rows

def fetch_one(item):
    repo,file=item
    url=file.get("raw_url","")
    if not url.startswith("https://raw.githubusercontent.com/"):return item,None
    path=CACHE/hashlib.sha256(url.encode()).hexdigest()
    expected=file.get("content_sha256")
    def decode(data):
        if expected and hashlib.sha256(data).hexdigest()!=expected:return None
        return data.decode("utf-8",errors="replace")
    if path.exists():
        try:
            body=decode(path.read_bytes())
            if body is not None:return item,body
        except OSError:pass
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req=urllib.request.Request(url,headers={"User-Agent":"AgentScope-RQ1-provenance-import"})
        with opener.open(req,timeout=10) as response:data=response.read(1_500_001)
        if len(data)>1_500_000:return item,None
        body=decode(data)
        if body is None:return item,None
        CACHE.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        return item,body
    except Exception:return item,None

def import_rq1():
    info=dataset_info()
    raw_rows=load_local()
    rows=list({source_import_key(slug,text):(slug,text,repo) for slug,text,repo in raw_rows}.values())
    refs={(file.get("raw_url")):(repo,file) for _,_,repo in rows if repo for file in repo.get("files",[]) if file.get("raw_url")}
    contents={}
    with ThreadPoolExecutor(max_workers=20) as pool:
        for future in as_completed([pool.submit(fetch_one,item) for item in refs.values()]):
            (repo,file),body=future.result()
            if body is not None:contents[(repo.get("repo","").lower(),file.get("path"),file.get("last_commit_sha"))]=(repo,file,body)
    inserted=verified=unverified=reused=0
    with connect() as con:
        for slug,text,repo in rows:
            repo_name=repo.get("repo") if repo else slug.replace("__","/")
            sentence_hash=hashlib.sha256(text.encode()).hexdigest()
            existing=con.execute("""SELECT source_verified FROM strategies WHERE source_kind='rq1_corpus'
                AND sentence_sha256=? AND (source_repo=? COLLATE NOCASE OR json_extract(metadata_json,'$.repo_slug')=? COLLATE NOCASE) LIMIT 1""",
                (sentence_hash,repo_name,slug)).fetchone()
            if existing:
                reused+=1;verified+=int(bool(existing["source_verified"]));unverified+=int(not existing["source_verified"]);continue
            needle=normal(text);hit=None
            if repo and needle:
                for file in repo.get("files",[]):
                    value=contents.get((repo_name.lower(),file.get("path"),file.get("last_commit_sha")))
                    if not value:continue
                    source_repo,file,body=value
                    for n,line in enumerate(body.splitlines(),1):
                        line_n=normal(line)
                        if needle in line_n or line_n in needle and len(line_n)>50:
                            hit=(file,body,n);break
                    if hit:break
            cat,confidence=category(text)
            commit=path=line_url=file_hash=None;line_start=line_end=None
            if hit:
                file,body,n=hit
                commit=file.get("last_commit_sha");path=file.get("path");line_start=line_end=n
                line_url=f"https://github.com/{repo_name}/blob/{commit}/{path}#L{n}"
                file_hash=hashlib.sha256(body.encode()).hexdigest();verified+=1
            else:unverified+=1
            metadata={"corpus":"RQ1","repo_slug":slug,"category_method":"keyword heuristic; pending human review",
                "line_match":"normalized exact/contained match" if hit else "source line not resolved",
                "source_families":[f.get("family") for f in (repo.get("files",[]) if repo else [])],
                "dataset_identity":info["identity"],"artifact_commit":info["artifact_commit"],
                "artifact_repository":info["artifact_repository"]}
            ident=uuid.uuid5(uuid.NAMESPACE_URL,source_import_key(slug,text)).hex
            cur=con.execute("""INSERT OR IGNORE INTO strategies(id,text,category,category_confidence,context_scope,execution_layer,status,
                source_repo,source_commit,source_path,line_start,line_end,raw_url,source_content_sha256,sentence_sha256,
                source_verified,source_kind,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (ident,text,cat,confidence,scope(text),"repository_instruction","pending_review",repo_name,commit,path,line_start,line_end,
                 line_url,file_hash,sentence_hash,int(bool(hit)),"rq1_corpus",json.dumps(metadata,ensure_ascii=False),now()))
            inserted+=cur.rowcount
            if not cur.rowcount:reused+=1
        con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('rq1_imported_at',?)",(now(),))
        con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('rq1_dataset_identity',?)",(info["identity"],))
        result={"input_count":len(raw_rows),"unique_count":len(rows),"inserted_count":inserted,"reused_count":reused,
            "verified_count":verified,"unverified_count":unverified,"repositories":len({r.get("repo") for _,_,r in rows if r}),
            "dataset_identity":info["identity"],"artifact_commit":info["artifact_commit"]}
        from .. import db
        db.audit(con,None,"rq1_corpus_import","backend",result)
    return result

def ensure_seed_job():
    # Missing/corrupt corpus fails a retryable background job, never control API startup.
    try: identity=dataset_info()["identity"]
    except (OSError,ValueError):identity=None
    with connect() as con:
        current=con.execute("SELECT value FROM meta WHERE key='rq1_dataset_identity'").fetchone()
        if identity and current and current["value"]==identity:return None
        previous=con.execute("""SELECT id,status FROM history_jobs WHERE kind='rq1_import'
            AND json_extract(input_json,'$.dataset_identity') IS ? ORDER BY created_at DESC LIMIT 1""",(identity,)).fetchone()
        if previous:return {"id":previous["id"],"status":previous["status"]}
    from ..history.jobs import enqueue
    return enqueue("rq1_import",{"dataset_identity":identity})

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

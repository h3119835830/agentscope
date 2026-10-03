import asyncio, hashlib, hmac, json, os, re, secrets, subprocess, tempfile, uuid
from pathlib import Path
from typing import Any
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from . import db
from .config import ACTPLANE_BIN, ADMIN_TOKEN, DSH_BIN, EXEC_PATH, PUBLIC_BASE_URL, SERVICE_HOME, UI_DIST, WORKSPACE_ROOT
from .broker_client import call as broker_call
from .services import corpus, github, pi_policy_generator, policy

app=FastAPI(title="AgentScope",version="0.1.0")

@app.middleware("http")
async def protect_control_api(request: Request, call_next):
    path=request.url.path
    if not path.startswith("/api/") or path=="/api/health" or path.startswith("/api/plugin/"):
        return await call_next(request)
    supplied=request.headers.get("authorization","")
    supplied=supplied[7:] if supplied.lower().startswith("bearer ") else ""
    if len(ADMIN_TOKEN)<32 or ADMIN_TOKEN=="replace-with-a-random-secret":
        return JSONResponse({"detail":"管理员口令未配置；请设置 AGENTSCOPE_ADMIN_TOKEN"},status_code=503)
    if not hmac.compare_digest(supplied,ADMIN_TOKEN):
        return JSONResponse({"detail":"需要有效的 AgentScope 管理员口令"},status_code=401)
    return await call_next(request)

class PrepareRequest(BaseModel):
    repo_url:str; ref:str="main"; prompt:str=Field(min_length=3,max_length=8000); dsh_profile:str="headless"
class PolicyRequest(BaseModel):
    strategy_ids:list[str]=[]; settings:dict[str,Any]={}
class ReviewRequest(BaseModel):
    decision:str; reviewed_by:str="研究者"; notes:str=""
class ScopeRequestBody(BaseModel):
    kind:str; path:str|None=None; justification:str=Field(min_length=4,max_length=1000); requested_by:str="用户"
class GovernanceRequest(BaseModel):
    task_id:str|None=None; kind:str; title:str; content:str=Field(min_length=5,max_length=30000); source_url:str|None=None
class StrategyCreateRequest(BaseModel):
    text:str=Field(min_length=5,max_length=12000)
    category:str="semantic"
    category_confidence:float=Field(default=1.0,ge=0,le=1)
    context_scope:str="self-contained"
    execution_layer:str="repository_instruction"
    source_url:str|None=None
    actor:str="研究者"
class StrategyUpdateRequest(BaseModel):
    text:str|None=Field(default=None,min_length=5,max_length=12000)
    category:str|None=None
    category_confidence:float|None=Field(default=None,ge=0,le=1)
    context_scope:str|None=None
    execution_layer:str|None=None
    actor:str="研究者"
    reason:str=Field(default="",max_length=2000)
class PiProposalSubmitRequest(BaseModel):
    title:str=Field(min_length=3,max_length=160)
    content:str=Field(min_length=5,max_length=12000)
    rationale:str=Field(default="",max_length=4000)
    evidence_ids:list[str]=Field(min_length=1,max_length=30)
    strategy_ids:list[str]=Field(default_factory=list,max_length=20)
class PiProposalReviewRequest(BaseModel):
    decision:str
    reviewed_by:str="研究者"
    notes:str=Field(default="",max_length=2000)


def issue_task_token(task_id,scope="dsh"):
    token=secrets.token_urlsafe(32)
    ident=uuid.uuid4().hex
    digest=hashlib.sha256(token.encode()).hexdigest()
    with db.connect() as con:
        con.execute("INSERT INTO task_credentials(id,task_id,token_sha256,created_at,scope) VALUES(?,?,?,?,?)",(ident,task_id,digest,db.now(),scope))
    return token,ident

def revoke_task_tokens(task_id,keep_id=None):
    with db.connect() as con:
        if keep_id:
            con.execute("UPDATE task_credentials SET revoked_at=? WHERE task_id=? AND id<>? AND revoked_at IS NULL",(db.now(),task_id,keep_id))
        else:
            con.execute("UPDATE task_credentials SET revoked_at=? WHERE task_id=? AND revoked_at IS NULL",(db.now(),task_id))

def revoke_task_token(credential_id):
    with db.connect() as con:
        con.execute("UPDATE task_credentials SET revoked_at=? WHERE id=? AND revoked_at IS NULL",(db.now(),credential_id))

def require_agent_task(task_id,request):
    header=request.headers.get("authorization","")
    token=header[7:] if header.lower().startswith("bearer ") else ""
    if not token: raise HTTPException(401,"缺少任务凭据")
    digest=hashlib.sha256(token.encode()).hexdigest()
    with db.connect() as con:
        credential=con.execute("SELECT id FROM task_credentials WHERE task_id=? AND token_sha256=? AND scope='dsh' AND revoked_at IS NULL",(task_id,digest)).fetchone()
        task=con.execute("SELECT * FROM tasks WHERE id=?",(task_id,)).fetchone()
    if not credential or not task: raise HTTPException(401,"任务凭据无效")
    if task["status"]!="running": raise HTTPException(409,"任务当前未运行")
    return dict(task),credential["id"]


def require_pi_run(task_id,run_id,request):
    header=request.headers.get("authorization","")
    token=header[7:] if header.lower().startswith("bearer ") else ""
    if not token: raise HTTPException(401,"缺少 Pi 任务凭据")
    digest=hashlib.sha256(token.encode()).hexdigest()
    with db.connect() as con:
        credential=con.execute("SELECT id FROM task_credentials WHERE task_id=? AND token_sha256=? AND scope='pi' AND revoked_at IS NULL",(task_id,digest)).fetchone()
        task=con.execute("SELECT * FROM tasks WHERE id=?",(task_id,)).fetchone()
        pi_run=con.execute("SELECT id FROM pi_runs WHERE id=? AND task_id=? AND status='running'",(run_id,task_id)).fetchone()
    if not credential or not task or not pi_run: raise HTTPException(401,"Pi 任务凭据无效或已失效")
    if task["status"]!="prepared": raise HTTPException(409,"仅可读取仍处于准备状态的当前任务")
    return dict(task)


def require_task(task_id):
    with db.connect() as con: row=con.execute("SELECT * FROM tasks WHERE id=?",(task_id,)).fetchone()
    if not row: raise HTTPException(404,"任务不存在")
    return dict(row)

def build_policy_ir(task_id, strategy_ids, compile_state, compile_result, runtime_restrictions=None, evidence_ids=None, approved_only=True):
    with db.connect() as con:
        task=con.execute("SELECT commit_sha,repo FROM tasks WHERE id=?",(task_id,)).fetchone()
        evidence_sql="SELECT id,kind,title,uri,file_path,commit_sha,line_start,line_end,content_sha256 FROM evidence WHERE task_id=?"
        evidence_params=[task_id]
        if evidence_ids is not None:
            if evidence_ids:
                evidence_sql+=" AND id IN ("+",".join("?" for _ in evidence_ids)+")"
                evidence_params.extend(evidence_ids)
            else:
                evidence_sql+=" AND 0"
        evidence_sql+=" ORDER BY kind,file_path,line_start LIMIT 250"
        evidence=[dict(r) for r in con.execute(evidence_sql,evidence_params).fetchall()]
        strategies=[]
        if strategy_ids:
            qs=",".join("?" for _ in strategy_ids)
            approved_clause=" AND status='approved'" if approved_only else ""
            strategies=[dict(r) for r in con.execute(f"SELECT id,text,category,category_confidence,context_scope,execution_layer,source_repo,source_commit,source_path,line_start,line_end,raw_url,source_verified FROM strategies WHERE id IN ({qs}){approved_clause}",strategy_ids).fetchall()]
    return {
        "task": {"repository":task["repo"],"fixed_commit":task["commit_sha"]},
        "enforcement": {"source":"AgentScope 基础访问控制配置","compile_state":compile_state,
                        "backend_support":compile_result.get("backend_support",{}),
                        "historical_semantics":"历史自然语言记录不会直接拼入 ActPlane DSL"},
        "selected_history": [{**s,"application":"附加到 DSH 任务提示词，作为经审核的行为约束参考",
                              "kernel_enforcement":"advisory_only"} for s in strategies],
        "runtime_restrictions": runtime_restrictions or [],
        "evidence": evidence,
        "conflict_assessment": {"status":"manual_review_required",
                                "note":"历史自然语言之间的冲突不作自动消解；审核人需结合来源、任务上下文和 DSL 编译结果确认。"}
    }

def build_agent_prompt(task, strategy_ids):
    base=task["prompt"].strip()
    with db.connect() as con:
        rows=[]
        if strategy_ids:
            qs=",".join("?" for _ in strategy_ids)
            rows=[dict(r) for r in con.execute(f"SELECT id,text,category,context_scope,raw_url FROM strategies WHERE id IN ({qs}) AND status='approved'",strategy_ids).fetchall()]
    if not rows: return base
    header=("\n\n[AgentScope：经审核的历史策略参考]\n"
            "以下内容仅作为当前任务的 Agent 行为约束参考；它们不是内核权限规则，不能扩大或覆盖已批准的访问控制策略。遇到冲突时遵循当前任务经审核的 DSL 权限边界，并向用户说明。\n")
    suffix="\n".join(f"- [{r['category']} / {r['context_scope']}] {r['text']}"+(f"（来源：{r['raw_url']}）" if r.get("raw_url") else "") for r in rows)
    combined=base+header+suffix
    if len(combined)>8000: raise HTTPException(413,"任务提示词与所选历史策略超过 DSH 长度限制；请减少候选或缩短任务描述")
    return combined

def compile_policy(yaml_text,task_id,version):
    if not ACTPLANE_BIN.exists(): return "backend_missing",{},"ActPlane CLI 尚未安装"
    temp=Path(tempfile.gettempdir())/f"agentscope-{task_id}-v{version}.yaml"
    temp.write_text(yaml_text)
    try:
        p=subprocess.run([str(ACTPLANE_BIN),"--policy",str(temp),"compile","--json"],capture_output=True,text=True,timeout=45,
                         env={"PATH":EXEC_PATH,"HOME":str(SERVICE_HOME),"NO_PROXY":"*","no_proxy":"*"})
        try: data=json.loads(p.stdout)
        except Exception: data={"diagnostic":p.stderr[-4000:] or p.stdout[-4000:]}
        if p.returncode: return "compile_failed",data,p.stderr[-2500:] or p.stdout[-2500:]
        support=data.get("backend_support",{}).get("clauses",[])
        state="compiled" if all(c.get("supported",False) for c in support) else "partial"
        return state,data,""
    except subprocess.TimeoutExpired: return "compile_timeout",{},"ActPlane 编译超过 45 秒"
    finally: temp.unlink(missing_ok=True)

def create_policy_version(task,version,layer,settings,strategy_ids,summary,extra_rules="",runtime_restrictions=None):
    dsl_text,yaml_text=policy.make_dsl(task["workspace"],task["output_dir"],settings,extra_rules)
    compile_state,compile_result,diagnostic=compile_policy(yaml_text,task["id"],version)
    policy_ir=build_policy_ir(task["id"],strategy_ids,compile_state,compile_result,runtime_restrictions)
    compile_result={"actplane":compile_result,"policy_ir":policy_ir}
    with db.connect() as con:
        ev=[r[0] for r in con.execute("SELECT id FROM evidence WHERE task_id=?",(task["id"],)).fetchall()]
    status="draft" if compile_state in ("compile_failed","compile_timeout","backend_missing") else "compiled"
    policy.save_version(task["id"],version,layer,dsl_text,yaml_text,strategy_ids,ev,compile_state,compile_result,status,summary)
    return {"version":version,"dsl_text":dsl_text,"policy_yaml":yaml_text,"compile_state":compile_state,"compile_result":compile_result,"policy_ir":policy_ir,"diagnostic":diagnostic}

@app.on_event("startup")
async def startup():
    db.init_db()
    pi_policy_generator.recover_interrupted_runs()

@app.get("/api/health")
def health(): return {"ok":True,"service":"AgentScope","version":"0.1.0"}

@app.get("/api/auth/check")
def auth_check(): return {"ok":True}

@app.get("/api/status")
def status():
    lsm="unknown"
    try: lsm=Path("/sys/kernel/security/lsm").read_text().strip()
    except Exception: pass
    broker={"available":False}
    try: broker=broker_call({"action":"health"},timeout=2)
    except Exception as e: broker={"available":False,"error":str(e)}
    pi=pi_policy_generator.availability()
    return {"kernel":os.uname().release,"architecture":os.uname().machine,"btf":Path("/sys/kernel/btf/vmlinux").exists(),"lsm":lsm,
      "bpf_lsm":"bpf" in lsm.split(","),"actplane_cli":ACTPLANE_BIN.exists(),"dsh_cli":DSH_BIN.exists(),
      "broker":broker,"pi_cli":pi["available"],"pi_reason":pi["reason"],"vm":"Linux guest"}

@app.get("/api/dashboard")
def dashboard():
    with db.connect() as con:
        stats={"strategies":con.execute("SELECT count(*) FROM strategies WHERE is_archived=0").fetchone()[0],
          "pending_strategies":con.execute("SELECT count(*) FROM strategies WHERE status='pending_review' AND is_archived=0").fetchone()[0],
          "archived_strategies":con.execute("SELECT count(*) FROM strategies WHERE is_archived=1").fetchone()[0],
          "active_tasks":con.execute("SELECT count(*) FROM tasks WHERE status IN ('running','starting')").fetchone()[0],
          "pending_governance":con.execute("SELECT count(*) FROM governance_candidates WHERE status='pending_review'").fetchone()[0],
          "tasks":con.execute("SELECT count(*) FROM tasks").fetchone()[0]}
    try: active=broker_call({"action":"active"},timeout=2).get("tasks",[])
    except Exception: active=[]
    return {"stats":stats,"active":active}

@app.get("/api/strategies")
def get_strategies(q:str="",status_filter:str|None=Query(default=None,alias="status"),category:str|None=None,archived:str="active",limit:int=100):
    if archived not in ("active","archived","all"):
        raise HTTPException(400,"archived 只能是 active、archived 或 all")
    archive_filter={"active":False,"archived":True,"all":None}[archived]
    records=corpus.search(q,limit,status_filter,archive_filter)
    if category: records=[r for r in records if r["category"]==category]
    return records

@app.get("/api/strategies/page")
def get_strategy_page(q:str="",status_filter:str|None=Query(default=None,alias="status"),archived:str="active",
                      category:str|None=None,context_scope:str|None=None,source_repo:str|None=None,
                      limit:int=Query(default=20,ge=1,le=500),offset:int=Query(default=0,ge=0)):
    if archived not in ("active","archived","all"):
        raise HTTPException(400,"archived 只能是 active、archived 或 all")
    archive_filter={"active":False,"archived":True,"all":None}[archived]
    return corpus.search_page(q,limit,offset,status_filter,archive_filter,category,context_scope,source_repo)

@app.post("/api/strategies/import")
def import_strategies():
    try: return corpus.import_rq1()
    except Exception as e: raise HTTPException(500,f"RQ1 导入失败：{e}")

STRATEGY_CATEGORIES={"semantic","per-event","cross-event"}
STRATEGY_SCOPES={"self-contained","project","task"}

@app.post("/api/strategies")
def create_strategy(body:StrategyCreateRequest):
    if body.category not in STRATEGY_CATEGORIES: raise HTTPException(400,"策略类型不合法")
    if body.context_scope not in STRATEGY_SCOPES: raise HTTPException(400,"策略适用范围不合法")
    if body.source_url and not body.source_url.startswith("https://"):
        raise HTTPException(400,"来源链接必须使用 HTTPS")
    ident=uuid.uuid4().hex
    timestamp=db.now()
    sentence_hash=hashlib.sha256(body.text.encode()).hexdigest()
    metadata={"source":"manual"}
    with db.connect() as con:
        con.execute(
            "INSERT INTO strategies(id,text,category,category_confidence,context_scope,execution_layer,status,raw_url,sentence_sha256,source_verified,source_kind,metadata_json,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ident,body.text.strip(),body.category,body.category_confidence,body.context_scope,body.execution_layer,
             "pending_review",body.source_url,sentence_hash,0,"manual",json.dumps(metadata),timestamp),
        )
        db.audit(con,None,"strategy_created",body.actor,{"strategy_id":ident,"source_kind":"manual"})
        row=con.execute("SELECT * FROM strategies WHERE id=?",(ident,)).fetchone()
    return dict(row)

@app.patch("/api/strategies/{strategy_id}")
def update_strategy(strategy_id:str,body:StrategyUpdateRequest):
    fields=body.model_fields_set.intersection({"text","category","category_confidence","context_scope","execution_layer"})
    if not fields: raise HTTPException(400,"至少提供一个要修改的字段")
    if body.category is not None and body.category not in STRATEGY_CATEGORIES: raise HTTPException(400,"策略类型不合法")
    if body.context_scope is not None and body.context_scope not in STRATEGY_SCOPES: raise HTTPException(400,"策略适用范围不合法")
    timestamp=db.now()
    with db.connect() as con:
        row=con.execute("SELECT * FROM strategies WHERE id=?",(strategy_id,)).fetchone()
        if not row: raise HTTPException(404,"策略记录不存在")
        if row["is_archived"]: raise HTTPException(409,"已归档策略不可编辑；请先恢复")
        before=dict(row)
        revision=row["revision"]+1
        new_values={key:getattr(body,key) for key in fields if getattr(body,key) is not None}
        if "text" in new_values: new_values["text"]=new_values["text"].strip()
        if not new_values: raise HTTPException(400,"没有可应用的修改")
        after={**before,**new_values,"revision":revision,"status":"pending_review","reviewed_at":None,"reviewed_by":None}
        if "text" in new_values and new_values["text"] != before["text"]:
            new_values["source_verified"]=0
            after["source_verified"]=0
        con.execute(
            "INSERT INTO strategy_revisions(id,strategy_id,revision,actor,reason,snapshot_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (uuid.uuid4().hex,strategy_id,before["revision"],body.actor,body.reason,
             json.dumps(before,ensure_ascii=False),timestamp),
        )
        setters=[f"{key}=?" for key in new_values]
        params=list(new_values.values())
        setters.extend(["revision=?","status='pending_review'","reviewed_at=NULL","reviewed_by=NULL"])
        params.extend([revision,strategy_id])
        con.execute(f"UPDATE strategies SET {','.join(setters)} WHERE id=?",params)
        db.audit(con,None,"strategy_updated",body.actor,{"strategy_id":strategy_id,"revision":revision,"reason":body.reason,"fields":sorted(new_values)})
        updated=con.execute("SELECT * FROM strategies WHERE id=?",(strategy_id,)).fetchone()
    return dict(updated)

@app.get("/api/strategies/{strategy_id}/history")
def strategy_history(strategy_id:str):
    with db.connect() as con:
        if not con.execute("SELECT 1 FROM strategies WHERE id=?",(strategy_id,)).fetchone():
            raise HTTPException(404,"策略记录不存在")
        rows=con.execute("SELECT * FROM strategy_revisions WHERE strategy_id=? ORDER BY revision DESC",(strategy_id,)).fetchall()
    return [{**dict(row),"snapshot":json.loads(row["snapshot_json"])} for row in rows]

@app.delete("/api/strategies/{strategy_id}")
def archive_strategy(strategy_id:str,actor:str="研究者"):
    timestamp=db.now()
    with db.connect() as con:
        cur=con.execute("UPDATE strategies SET is_archived=1,archived_at=?,archived_by=? WHERE id=? AND is_archived=0",(timestamp,actor,strategy_id))
        if not cur.rowcount:
            row=con.execute("SELECT is_archived FROM strategies WHERE id=?",(strategy_id,)).fetchone()
            if not row: raise HTTPException(404,"策略记录不存在")
        db.audit(con,None,"strategy_archived",actor,{"strategy_id":strategy_id})
        row=con.execute("SELECT * FROM strategies WHERE id=?",(strategy_id,)).fetchone()
    return dict(row)

@app.post("/api/strategies/{strategy_id}/restore")
def restore_strategy(strategy_id:str,actor:str="研究者"):
    with db.connect() as con:
        row=con.execute("SELECT * FROM strategies WHERE id=?",(strategy_id,)).fetchone()
        if not row: raise HTTPException(404,"策略记录不存在")
        if row["is_archived"]:
            con.execute("UPDATE strategies SET is_archived=0,archived_at=NULL,archived_by=NULL WHERE id=?",(strategy_id,))
            db.audit(con,None,"strategy_restored",actor,{"strategy_id":strategy_id})
        restored=con.execute("SELECT * FROM strategies WHERE id=?",(strategy_id,)).fetchone()
    return dict(restored)

@app.post("/api/strategies/{strategy_id}/review")
def review_strategy(strategy_id:str,body:ReviewRequest):
    if body.decision not in ("approve","reject"): raise HTTPException(400,"decision 只能是 approve 或 reject")
    status="approved" if body.decision=="approve" else "rejected"
    with db.connect() as con:
        row=con.execute("SELECT is_archived FROM strategies WHERE id=?",(strategy_id,)).fetchone()
        if not row: raise HTTPException(404,"策略记录不存在")
        if row["is_archived"]: raise HTTPException(409,"已归档策略不能审核；请先恢复")
        con.execute("UPDATE strategies SET status=?,reviewed_at=?,reviewed_by=? WHERE id=?",(status,db.now(),body.reviewed_by,strategy_id))
        db.audit(con,None,"strategy_review",body.reviewed_by,{"strategy_id":strategy_id,"decision":body.decision,"notes":body.notes})
        row=con.execute("SELECT * FROM strategies WHERE id=?",(strategy_id,)).fetchone()
    return dict(row)

@app.get("/api/tasks")
def get_tasks():
    with db.connect() as con: return [dict(r) for r in con.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT 100").fetchall()]

@app.post("/api/tasks/prepare")
def prepare_task(body:PrepareRequest):
    if body.dsh_profile not in ("headless",): raise HTTPException(400,"当前 Demo 固定使用 DSH headless 会话")
    try: info=github.prepare(body.model_dump())
    except Exception as e: raise HTTPException(400,f"GitHub 仓库准备失败：{e}")
    with db.connect() as con: db.audit(con,info["id"],"task_prepared","用户",{"repo":info["repo"],"commit":info["commit_sha"]})
    return info

@app.get("/api/tasks/{task_id}/context")
def task_context(task_id:str):
    task=require_task(task_id)
    with db.connect() as con:
        ev=[dict(r) for r in con.execute("SELECT * FROM evidence WHERE task_id=? ORDER BY kind,file_path,line_start LIMIT 250",(task_id,)).fetchall()]
    query=task["prompt"]+" "+" ".join(x["excerpt"] for x in ev[:100])
    return {"task":task,"evidence":ev,"history_recommendations":corpus.recommend(query,12)}

def _pi_run_payload(run_row):
    payload=dict(run_row)
    try: payload["input"]=json.loads(payload.pop("input_json") or "{}")
    except Exception: payload["input"]={}
    try: payload["result"]=json.loads(payload.pop("result_json") or "{}")
    except Exception: payload["result"]={}
    with db.connect() as con:
        rows=con.execute("SELECT * FROM policy_proposals WHERE run_id=? ORDER BY created_at,id",(payload["id"],)).fetchall()
    proposals=[]
    for row in rows:
        proposal=dict(row)
        try: proposal["evidence_ids"]=json.loads(proposal.pop("evidence_ids_json") or "[]")
        except Exception: proposal["evidence_ids"]=[]
        try: proposal["strategy_ids"]=json.loads(proposal.pop("strategy_ids_json") or "[]")
        except Exception: proposal["strategy_ids"]=[]
        proposals.append(proposal)
    payload["proposals"]=proposals
    return payload

@app.post("/api/tasks/{task_id}/pi-runs",status_code=202)
def start_pi_run(task_id:str,background_tasks:BackgroundTasks,requested_by:str="研究者"):
    task=require_task(task_id)
    if task["status"]!="prepared": raise HTTPException(409,"Pi 只接受尚未启动的准备中任务")
    available=pi_policy_generator.availability()
    if not available["available"]: raise HTTPException(503,available["reason"])
    with db.connect() as con:
        active=con.execute("SELECT id FROM pi_runs WHERE task_id=? AND status IN ('queued','running')",(task_id,)).fetchone()
        if active: raise HTTPException(409,"该任务已有 Pi 生成流程正在运行")
        evidence=[dict(r) for r in con.execute("SELECT id,content_sha256 FROM evidence WHERE task_id=? ORDER BY id",(task_id,)).fetchall()]
        approved_count=con.execute("SELECT count(*) FROM strategies WHERE status='approved' AND is_archived=0").fetchone()[0]
        run_id=uuid.uuid4().hex
        timestamp=db.now()
        run_input={
            "repository":task["repo"],"commit_sha":task["commit_sha"],
            "prompt_sha256":hashlib.sha256(task["prompt"].encode()).hexdigest(),
            "evidence_count":len(evidence),
            "evidence_sha256":hashlib.sha256("".join(x["content_sha256"] for x in evidence).encode()).hexdigest(),
            "approved_history_count":approved_count,
        }
        con.execute("INSERT INTO pi_runs(id,task_id,status,requested_by,input_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
          (run_id,task_id,"queued",requested_by,json.dumps(run_input),timestamp,timestamp))
        db.audit(con,task_id,"pi_run_started",requested_by,{"run_id":run_id,"commit_sha":task["commit_sha"]})
    token,credential_id=issue_task_token(task_id,scope="pi")
    background_tasks.add_task(pi_policy_generator.run,run_id,task_id,token,credential_id)
    return {"id":run_id,"task_id":task_id,"status":"queued","created_at":timestamp}

@app.get("/api/tasks/{task_id}/pi-runs")
def list_pi_runs(task_id:str):
    require_task(task_id)
    with db.connect() as con:
        rows=con.execute("SELECT * FROM pi_runs WHERE task_id=? ORDER BY created_at DESC LIMIT 20",(task_id,)).fetchall()
    return [_pi_run_payload(row) for row in rows]

@app.get("/api/pi-runs/{run_id}")
def get_pi_run(run_id:str):
    with db.connect() as con: row=con.execute("SELECT * FROM pi_runs WHERE id=?",(run_id,)).fetchone()
    if not row: raise HTTPException(404,"Pi 运行记录不存在")
    return _pi_run_payload(row)

@app.post("/api/tasks/{task_id}/pi-proposals/{proposal_id}/review")
def review_pi_proposal(task_id:str,proposal_id:str,body:PiProposalReviewRequest):
    if body.decision not in ("approve","reject"): raise HTTPException(400,"decision 只能是 approve 或 reject")
    status="approved" if body.decision=="approve" else "rejected"
    with db.connect() as con:
        row=con.execute("SELECT status FROM policy_proposals WHERE id=? AND task_id=?",(proposal_id,task_id)).fetchone()
        if not row: raise HTTPException(404,"任务策略候选不存在")
        if row["status"]!="pending_review": raise HTTPException(409,"该候选已完成审核")
        con.execute("UPDATE policy_proposals SET status=?,reviewed_at=?,reviewed_by=?,review_notes=? WHERE id=?",
          (status,db.now(),body.reviewed_by,body.notes,proposal_id))
        db.audit(con,task_id,"pi_proposal_review",body.reviewed_by,{"proposal_id":proposal_id,"decision":body.decision,"notes":body.notes})
        updated=con.execute("SELECT * FROM policy_proposals WHERE id=?",(proposal_id,)).fetchone()
    result=dict(updated)
    result["evidence_ids"]=json.loads(result.pop("evidence_ids_json") or "[]")
    result["strategy_ids"]=json.loads(result.pop("strategy_ids_json") or "[]")
    return result

@app.get("/api/plugin/tasks/{task_id}/pi/context")
def pi_task_context(task_id:str,request:Request,run_id:str):
    task=require_pi_run(task_id,run_id,request)
    with db.connect() as con:
        evidence=con.execute("SELECT id,kind,title,uri,file_path,commit_sha,line_start,line_end,content_sha256 FROM evidence WHERE task_id=? ORDER BY kind,file_path,line_start LIMIT 250",(task_id,)).fetchall()
    return {
      "task":{"id":task_id,"repository":task["repo"],"fixed_commit":task["commit_sha"],"prompt":task["prompt"]},
      "evidence":[dict(row) for row in evidence],
    }

@app.get("/api/plugin/tasks/{task_id}/pi/evidence/{evidence_id}")
def pi_read_evidence(task_id:str,evidence_id:str,request:Request,run_id:str):
    require_pi_run(task_id,run_id,request)
    with db.connect() as con:
        row=con.execute("SELECT id,kind,title,uri,file_path,commit_sha,line_start,line_end,excerpt,content_sha256 FROM evidence WHERE id=? AND task_id=?",(evidence_id,task_id)).fetchone()
    if not row: raise HTTPException(404,"当前任务中没有该证据")
    return dict(row)

@app.get("/api/plugin/tasks/{task_id}/pi/history")
def pi_search_history(task_id:str,request:Request,run_id:str,q:str=Query(min_length=1,max_length=500)):
    require_pi_run(task_id,run_id,request)
    results=corpus.recommend(q,12,status="approved")
    return [{key:row.get(key) for key in ("id","text","category","context_scope","source_repo","source_path","line_start","line_end","raw_url","source_verified","relevance")} for row in results]

@app.post("/api/plugin/tasks/{task_id}/pi/proposals")
def pi_submit_proposal(task_id:str,request:Request,run_id:str,body:PiProposalSubmitRequest):
    require_pi_run(task_id,run_id,request)
    evidence_ids=list(dict.fromkeys(body.evidence_ids))
    strategy_ids=list(dict.fromkeys(body.strategy_ids))
    content=body.content.strip()
    digest=hashlib.sha256(content.encode()).hexdigest()
    with db.connect() as con:
        allowed_evidence={r[0] for r in con.execute(
          f"SELECT id FROM evidence WHERE task_id=? AND id IN ({','.join('?' for _ in evidence_ids)})",
          [task_id,*evidence_ids],
        ).fetchall()}
        if allowed_evidence!=set(evidence_ids): raise HTTPException(400,"候选引用了不属于当前任务的证据")
        if strategy_ids:
            allowed_history={r[0] for r in con.execute(
              f"SELECT id FROM strategies WHERE status='approved' AND is_archived=0 AND id IN ({','.join('?' for _ in strategy_ids)})",
              strategy_ids,
            ).fetchall()}
            if allowed_history!=set(strategy_ids): raise HTTPException(400,"候选引用了未审核或已归档历史策略")
        proposal_id=uuid.uuid4().hex
        con.execute(
          "INSERT OR IGNORE INTO policy_proposals(id,run_id,task_id,title,content,rationale,evidence_ids_json,strategy_ids_json,content_sha256,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,'pending_review',?)",
          (proposal_id,run_id,task_id,body.title.strip(),content,body.rationale.strip(),json.dumps(evidence_ids),json.dumps(strategy_ids),digest,db.now()),
        )
        if con.execute("SELECT changes()").fetchone()[0]==0:
            row=con.execute("SELECT id FROM policy_proposals WHERE run_id=? AND content_sha256=?",(run_id,digest)).fetchone()
            proposal_id=row["id"]
        else:
            db.audit(con,task_id,"pi_proposal_created","Pi",{"proposal_id":proposal_id,"run_id":run_id,"evidence_ids":evidence_ids})
    return {"id":proposal_id,"status":"pending_review"}

@app.get("/api/plugin/tasks/{task_id}/scope")
def plugin_scope(task_id:str,request:Request):
    task,_=require_agent_task(task_id,request)
    with db.connect() as con:
        version=con.execute("SELECT version,layer,dsl_text,compile_json,change_summary,approved_by,approved_at FROM policy_versions WHERE task_id=? AND version=? AND status='approved'",(task_id,task["active_version"])).fetchone()
        restrictions=[dict(r) for r in con.execute("SELECT id,path,justification,reviewed_by,reviewed_at FROM scope_requests WHERE task_id=? AND kind='restrict' AND status='approved' ORDER BY created_at",(task_id,)).fetchall()]
    if not version: raise HTTPException(409,"当前任务没有已批准的策略版本")
    try: policy_ir=json.loads(version["compile_json"] or "{}").get("policy_ir",{})
    except Exception: policy_ir={}
    return {"task":{"id":task_id,"repository":task["repo"],"fixed_commit":task["commit_sha"],"status":task["status"]},
            "policy":{"version":version["version"],"layer":version["layer"],"dsl":version["dsl_text"],"summary":version["change_summary"],"approved_by":version["approved_by"],"approved_at":version["approved_at"]},
            "selected_history":policy_ir.get("selected_history",[]),"runtime_restrictions":restrictions,
            "scope_request_rule":"所有变更只进入待审核队列；此接口不会批准或执行权限变更。"}

def create_scope_request(task_id,body):
    task=require_task(task_id)
    if task["status"]!="running": raise HTTPException(409,"只有运行中的任务可以申请运行时 Scope 变更")
    if body.kind not in ("restrict","expand"): raise HTTPException(400,"kind 必须为 restrict 或 expand")
    if body.kind=="restrict" and not body.path: raise HTTPException(400,"收紧 Scope 时必须指定仓库内允许写入的路径")
    if body.kind=="restrict" and body.path:
        target=Path(body.path).resolve(); workspace=Path(task["workspace"]).resolve()
        if target!=workspace and workspace not in target.parents: raise HTTPException(400,"收紧范围只能指定当前任务仓库工作区内的路径")
        if not target.is_dir(): raise HTTPException(400,"收紧 Scope 路径必须是当前工作区中已存在的目录")
    reqid=uuid.uuid4().hex
    with db.connect() as con:
        con.execute("INSERT INTO scope_requests(id,task_id,kind,requested_change,path,justification,status,requested_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
          (reqid,task_id,body.kind,"限制当前任务 Scope" if body.kind=="restrict" else "增加受控任务输出目录的写入权限",body.path,body.justification,"pending_review",body.requested_by,db.now()))
        db.audit(con,task_id,"scope_requested",body.requested_by,{"request_id":reqid,"kind":body.kind,"path":body.path,"justification":body.justification})
    return {"id":reqid,"status":"pending_review"}

@app.post("/api/plugin/tasks/{task_id}/scope-requests")
def plugin_scope_request(task_id:str,body:ScopeRequestBody,request:Request):
    require_agent_task(task_id,request)
    return create_scope_request(task_id,body.model_copy(update={"requested_by":"DSH AgentScope 插件"}))

@app.post("/api/tasks/{task_id}/policy")
def generate_policy(task_id:str,body:PolicyRequest):
    task=require_task(task_id)
    settings={"read_only":False,"deny_network":False,"allow_task_output":False,**body.settings}
    # Historical instructions are evidence; only approved records explicitly selected by the user can inform a bundle.
    with db.connect() as con:
        if body.strategy_ids:
            qs=",".join("?" for _ in body.strategy_ids)
            approved=con.execute(f"SELECT id FROM strategies WHERE id IN ({qs}) AND status='approved'",body.strategy_ids).fetchall()
            ids=[r[0] for r in approved]
        else: ids=[]
        version=(con.execute("SELECT COALESCE(MAX(version),0)+1 FROM policy_versions WHERE task_id=?",(task_id,)).fetchone()[0])
        db.audit(con,task_id,"policy_generated","AgentScope",{"version":version,"settings":settings,"strategy_ids":ids})
    result=create_policy_version(task,version,"task_start",settings,ids,"任务启动前策略：基础用户配置、目标仓库证据与审核通过的历史策略")
    with db.connect() as con: con.execute("UPDATE tasks SET settings_json=?,status='policy_review',updated_at=? WHERE id=?",(json.dumps(settings),db.now(),task_id))
    return result

@app.get("/api/tasks/{task_id}/versions")
def get_versions(task_id:str):
    require_task(task_id)
    with db.connect() as con: rows=[dict(r) for r in con.execute("SELECT * FROM policy_versions WHERE task_id=? ORDER BY version DESC",(task_id,)).fetchall()]
    for row in rows:
        try: compile_info=json.loads(row["compile_json"])
        except Exception: compile_info={}
        row["policy_ir"]=compile_info.get("policy_ir")
        if row["policy_ir"] is None:
            try: strategy_ids=json.loads(row["source_strategy_ids"] or "[]")
            except Exception: strategy_ids=[]
            try: evidence_ids=json.loads(row["evidence_ids"] or "[]")
            except Exception: evidence_ids=[]
            row["policy_ir"]=build_policy_ir(task_id,strategy_ids,row["compile_state"],compile_info,
                                               evidence_ids=evidence_ids,approved_only=False)
            row["policy_ir"]["snapshot_note"]="由此版本已保存的来源 ID 与证据 ID 生成展示视图；DSL、审批状态和原版本记录未修改。"
    return rows

@app.post("/api/tasks/{task_id}/versions/{version}/approve")
def approve_version(task_id:str,version:int,body:ReviewRequest):
    task=require_task(task_id)
    with db.connect() as con:
        row=con.execute("SELECT * FROM policy_versions WHERE task_id=? AND version=?",(task_id,version)).fetchone()
        if not row: raise HTTPException(404,"策略版本不存在")
        if body.decision!="approve":
            con.execute("UPDATE policy_versions SET status='rejected',approved_by=?,approved_at=? WHERE task_id=? AND version=?",(body.reviewed_by,db.now(),task_id,version))
            db.audit(con,task_id,"policy_rejected",body.reviewed_by,{"version":version,"notes":body.notes})
            return {"status":"rejected"}
        if row["compile_state"] != "compiled": raise HTTPException(409,"ActPlane 未完整支持该策略中的全部子句；请先调整策略再申请批准")
        con.execute("UPDATE policy_versions SET status='approved',approved_by=?,approved_at=? WHERE task_id=? AND version=?",(body.reviewed_by,db.now(),task_id,version))
        con.execute("UPDATE tasks SET status='approved',active_version=?,updated_at=? WHERE id=?",(version,db.now(),task_id))
        db.audit(con,task_id,"policy_approved",body.reviewed_by,{"version":version,"notes":body.notes})
    return {"status":"approved","version":version}

@app.post("/api/tasks/{task_id}/launch")
def launch_task(task_id:str):
    task=require_task(task_id)
    with db.connect() as con:
        v=con.execute("SELECT * FROM policy_versions WHERE task_id=? AND version=?",(task_id,task["active_version"])).fetchone()
        if not v or v["status"]!="approved": raise HTTPException(409,"请先审核并批准当前策略版本")
    task_token,credential_id=issue_task_token(task_id)
    try:
        strategy_ids=json.loads(v["source_strategy_ids"] or "[]")
        prompt=build_agent_prompt(task,strategy_ids)
        result=broker_call({"action":"launch","task_id":task_id,"version":v["version"],"workspace":task["workspace"],"output_dir":task["output_dir"],"prompt":prompt,"dsl_text":v["dsl_text"],"policy_yaml":v["policy_yaml"],"dsh_profile":task["dsh_profile"],"task_token":task_token,"agentscope_url":PUBLIC_BASE_URL},timeout=35)
        revoke_task_tokens(task_id,credential_id)
    except Exception as e:
        revoke_task_token(credential_id)
        raise HTTPException(503,f"ActPlane/DSH 启动失败：{e}")
    with db.connect() as con:
        con.execute("UPDATE tasks SET status='running',active_pid=?,active_domain_id=?,watch_pid=?,updated_at=? WHERE id=?",(result.get("runner_pid"),result.get("domain_id"),result.get("watch_pid"),db.now(),task_id))
        db.audit(con,task_id,"task_launched","AgentScope",result)
    return result

@app.get("/api/tasks/{task_id}/runtime")
def task_runtime(task_id:str):
    task=require_task(task_id)
    runtime={}
    try: runtime=broker_call({"action":"status","task_id":task_id},timeout=5)
    except Exception as e: runtime={"available":False,"error":str(e)}
    events=[]
    roots=[Path(task["workspace"])/".actplane"/"events.jsonl"]
    control_root=Path(task["workspace"]).parent/".runtime-control"
    if control_root.exists(): roots+=list(control_root.glob("*/.actplane/events.jsonl"))
    runs=Path(task["workspace"])/".actplane"/"runs"
    if runs.exists(): roots+=list(runs.glob("*/events.jsonl"))
    for file in roots:
        try:
            for line in file.read_text(errors="replace").splitlines()[-500:]:
                try: raw=json.loads(line)
                except Exception: continue
                reason=raw.get("reason") or raw.get("because") or raw.get("message") or json.dumps(raw,ensure_ascii=False)[:500]
                op=raw.get("operation") or raw.get("op") or raw.get("kind")
                target=raw.get("target") or raw.get("path") or raw.get("endpoint")
                decision=raw.get("effect") or raw.get("decision") or raw.get("action")
                key=hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest()
                events.append({"id":key,"task_id":task_id,"kind":raw.get("type","policy_match"),"operation":op,"target":target,"decision":decision,"reason":reason,"occurred_at":raw.get("timestamp") or raw.get("time") or "", "raw":raw})
                with db.connect() as con:
                    con.execute("INSERT OR IGNORE INTO runtime_events(id,task_id,kind,operation,target,decision,reason,occurred_at,raw_json,dedupe_key) VALUES(?,?,?,?,?,?,?,?,?,?)",(uuid.uuid4().hex,task_id,raw.get("type","policy_match"),op,target,decision,str(reason),str(raw.get("timestamp") or raw.get("time") or db.now()),json.dumps(raw,ensure_ascii=False),key))
        except Exception: pass
    if runtime.get("agent_status")=="exited" and task["status"]=="running":
        try:
            broker_call({"action":"stop","task_id":task_id},timeout=12)
            task["status"]="completed"
        except Exception: pass
        with db.connect() as con:
            con.execute("UPDATE tasks SET status='completed',ended_at=?,updated_at=? WHERE id=?",(db.now(),db.now(),task_id))
        revoke_task_tokens(task_id)
        runtime["completion_cleanup"]="DSH 一次性会话已退出，ActPlane watch 已清理"
    with db.connect() as con:
        stored=[dict(r) for r in con.execute("SELECT * FROM runtime_events WHERE task_id=? ORDER BY occurred_at DESC LIMIT 100",(task_id,)).fetchall()]
    return {"runtime":runtime,"events":stored or events,"task_status":task["status"]}

@app.post("/api/tasks/{task_id}/scope-requests")
def scope_request(task_id:str,body:ScopeRequestBody):
    return create_scope_request(task_id,body)

@app.get("/api/tasks/{task_id}/scope-requests")
def list_scope_requests(task_id:str):
    require_task(task_id)
    with db.connect() as con:return [dict(r) for r in con.execute("SELECT * FROM scope_requests WHERE task_id=? ORDER BY created_at DESC",(task_id,)).fetchall()]

@app.post("/api/tasks/{task_id}/scope-requests/{request_id}/review")
def review_scope(task_id:str,request_id:str,body:ReviewRequest):
    task=require_task(task_id)
    with db.connect() as con:
        req=con.execute("SELECT * FROM scope_requests WHERE task_id=? AND id=?",(task_id,request_id)).fetchone()
        if not req: raise HTTPException(404,"Scope 申请不存在")
        if req["status"]!="pending_review": raise HTTPException(409,"该申请已处理")
        if body.decision!="approve":
            con.execute("UPDATE scope_requests SET status='rejected',reviewed_by=?,reviewed_at=? WHERE id=?",(body.reviewed_by,db.now(),request_id))
            db.audit(con,task_id,"scope_rejected",body.reviewed_by,{"request_id":request_id})
            return {"status":"rejected"}
    created_version=None
    new_credential_id=None
    try:
        if req["kind"]=="restrict":
            delta=policy.make_restrictive_delta({**task,"id":request_id},dict(req))
            result=broker_call({"action":"restrict","task_id":task_id,"request_id":request_id,"domain_id":task["active_domain_id"],"delta_text":delta,"approved_by":body.reviewed_by,"approval_ref":request_id},timeout=30)
            newver=task["active_version"]
        else:
            settings=json.loads(task["settings_json"] or "{}")
            settings["allow_task_output"]=True
            with db.connect() as con:
                version=con.execute("SELECT COALESCE(MAX(version),0)+1 FROM policy_versions WHERE task_id=?",(task_id,)).fetchone()[0]
                previous=con.execute("SELECT source_strategy_ids FROM policy_versions WHERE task_id=? AND version=?",(task_id,task["active_version"])).fetchone()
                restrictions=[dict(r) for r in con.execute("SELECT id,path,justification,reviewed_by,reviewed_at FROM scope_requests WHERE task_id=? AND kind='restrict' AND status='approved' ORDER BY created_at",(task_id,)).fetchall()]
            inherited_ids=json.loads(previous["source_strategy_ids"] or "[]") if previous else []
            inherited_rules="\n\n".join(policy.make_restrictive_delta({"workspace":task["workspace"]},r) for r in restrictions if r.get("path"))
            restriction_ir=[{"request_id":r["id"],"path":r["path"],"justification":r["justification"],"approved_by":r["reviewed_by"],"approved_at":r["reviewed_at"],"preserved_in_new_version":True} for r in restrictions if r.get("path")]
            created_version=version
            bundle=create_policy_version(task,version,"runtime_restart",settings,inherited_ids,"经审核扩展 Scope：加入隔离的任务输出目录；保留既有运行时限制并按新版本重启",inherited_rules,restriction_ir)
            if bundle["compile_state"]!="compiled": raise RuntimeError("扩展策略未获完整后端支持，不能批准："+bundle["diagnostic"])
            prompt=build_agent_prompt(task,inherited_ids)+"\n\n[AgentScope] 任务权限已审核更新。请从当前工作区现状继续原任务。"
            if len(prompt)>8000: raise RuntimeError("继承历史策略后的重启提示词超过 DSH 长度限制；请缩短任务提示或减少历史策略")
            task_token,new_credential_id=issue_task_token(task_id)
            result=broker_call({"action":"restart","task_id":task_id,"version":version,"workspace":task["workspace"],"output_dir":task["output_dir"],"prompt":prompt,"dsl_text":bundle["dsl_text"],"policy_yaml":bundle["policy_yaml"],"dsh_profile":task["dsh_profile"],"task_token":task_token,"agentscope_url":PUBLIC_BASE_URL},timeout=40)
            revoke_task_tokens(task_id,new_credential_id)
            newver=version
        with db.connect() as con:
            if created_version is not None:
                con.execute("UPDATE policy_versions SET status='approved',approved_by=?,approved_at=? WHERE task_id=? AND version=?",(body.reviewed_by,db.now(),task_id,created_version))
            con.execute("UPDATE scope_requests SET status='approved',reviewed_by=?,reviewed_at=?,resulting_version=?,result_json=? WHERE id=?",(body.reviewed_by,db.now(),newver,json.dumps(result),request_id))
            con.execute("UPDATE tasks SET active_version=?,active_pid=?,active_domain_id=?,watch_pid=?,status='running',updated_at=? WHERE id=?",(newver,result.get("runner_pid",task.get("active_pid")),result.get("domain_id",task.get("active_domain_id")),result.get("watch_pid",task.get("watch_pid")),db.now(),task_id))
            db.audit(con,task_id,"scope_approved",body.reviewed_by,{"request_id":request_id,"result":result,"version":newver})
        return {"status":"approved","version":newver,"result":result}
    except Exception as e:
        if new_credential_id: revoke_task_token(new_credential_id)
        with db.connect() as con:
            if created_version is not None:
                try:
                    current=broker_call({"action":"status","task_id":task_id},timeout=5)
                except Exception:
                    current={"available":False}
                still_running=current.get("available") and current.get("status")=="running"
                con.execute("UPDATE policy_versions SET status='failed' WHERE task_id=? AND version=?",(task_id,created_version))
                con.execute("UPDATE tasks SET active_version=?,status=?,active_pid=?,active_domain_id=?,watch_pid=?,ended_at=?,updated_at=? WHERE id=?",
                    (task["active_version"],"running" if still_running else "stopped",
                     current.get("runner_pid") if still_running else None,
                     current.get("domain_id") if still_running else None,
                     current.get("watch_pid") if still_running else None,
                     None if still_running else db.now(),db.now(),task_id))
            con.execute("UPDATE scope_requests SET status='failed',reviewed_by=?,reviewed_at=?,result_json=? WHERE id=?",(body.reviewed_by,db.now(),json.dumps({"error":str(e)}),request_id))
        raise HTTPException(503,f"Scope 更新失败：{e}")

@app.post("/api/tasks/{task_id}/stop")
def stop_task(task_id:str):
    task=require_task(task_id)
    try: result=broker_call({"action":"stop","task_id":task_id},timeout=20)
    except Exception as e: raise HTTPException(503,f"停止任务失败：{e}")
    revoke_task_tokens(task_id)
    with db.connect() as con:
        con.execute("UPDATE tasks SET status='stopped',ended_at=?,updated_at=? WHERE id=?",(db.now(),db.now(),task_id))
        db.audit(con,task_id,"task_stopped","用户",result)
    return result

@app.get("/api/governance")
def list_governance():
    with db.connect() as con:return [dict(r) for r in con.execute("SELECT * FROM governance_candidates ORDER BY created_at DESC").fetchall()]

@app.post("/api/governance")
def add_governance(body:GovernanceRequest):
    if body.kind not in ("memory_diff","github_pr","manual"): raise HTTPException(400,"kind 必须是 memory_diff、github_pr 或 manual")
    ident=uuid.uuid4().hex
    with db.connect() as con:
        con.execute("INSERT INTO governance_candidates(id,task_id,kind,title,content,source_url,status,created_at) VALUES(?,?,?,?,?,?,?,?)",(ident,body.task_id,body.kind,body.title,body.content,body.source_url,"pending_review",db.now()))
        db.audit(con,body.task_id,"governance_candidate_created","用户",{"candidate_id":ident,"kind":body.kind,"source_url":body.source_url})
    return {"id":ident,"status":"pending_review"}

@app.post("/api/governance/{candidate_id}/review")
def review_governance(candidate_id:str,body:ReviewRequest):
    if body.decision not in ("approve","reject"): raise HTTPException(400,"decision 只能是 approve 或 reject")
    with db.connect() as con:
        row=con.execute("SELECT * FROM governance_candidates WHERE id=?",(candidate_id,)).fetchone()
        if not row: raise HTTPException(404,"候选记录不存在")
        new_status="approved" if body.decision=="approve" else "rejected"
        strategy_id=None
        if new_status=="approved":
            strategy_id=uuid.uuid4().hex
            digest=hashlib.sha256(row["content"].encode()).hexdigest()
            con.execute("INSERT INTO strategies(id,text,category,category_confidence,context_scope,execution_layer,status,source_repo,raw_url,sentence_sha256,source_verified,source_kind,metadata_json,created_at,reviewed_at,reviewed_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (strategy_id,row["content"],"semantic",0.6,"task","governance","approved",None,row["source_url"],digest,0,"governance",json.dumps({"candidate_id":candidate_id,"kind":row["kind"]}),db.now(),db.now(),body.reviewed_by))
        con.execute("UPDATE governance_candidates SET status=?,reviewed_at=?,reviewed_by=?,promoted_strategy_id=? WHERE id=?",(new_status,db.now(),body.reviewed_by,strategy_id,candidate_id))
        db.audit(con,row["task_id"],"governance_review",body.reviewed_by,{"candidate_id":candidate_id,"decision":body.decision,"strategy_id":strategy_id})
    return {"status":new_status,"promoted_strategy_id":strategy_id}

@app.get("/{asset_path:path}")
def spa(asset_path:str):
    file=(UI_DIST/asset_path).resolve()
    try: file.relative_to(UI_DIST.resolve())
    except Exception: raise HTTPException(404)
    if asset_path and file.is_file(): return FileResponse(file)
    index=UI_DIST/"index.html"
    if index.exists(): return FileResponse(index)
    return HTMLResponse("<h1>AgentScope UI 尚未构建</h1><p>请在 Linux 虚拟机里运行前端构建脚本。</p>",status_code=503)

import asyncio, hashlib, hmac, json, os, re, secrets, subprocess, tempfile, uuid
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from . import db
from .config import ACTPLANE_BIN, ADMIN_TOKEN, DSH_BIN, EXEC_PATH, PUBLIC_BASE_URL, SERVICE_HOME, UI_DIST, WORKSPACE_ROOT
from .broker_client import call as broker_call
from .services import corpus, github, policy
from .history.api import router as history_router
from .history.catalog_api import router as catalog_router
from .history import jobs as history_jobs
from .history.registry import selected_artifacts, review_statement as review_statement_version
from .history.provider import ActPlaneProvider
from .bootstrap.api import router as bootstrap_router, approved_prompt
from .bootstrap.validation import verify_version
from . import development
from .agent_bridge.api import router as agent_bridge_router

app=FastAPI(title="AgentScope",version="0.2.0")
app.include_router(history_router)
app.include_router(catalog_router)
app.include_router(bootstrap_router)
app.include_router(agent_bridge_router)
from .scope.api import router as scope_router
from .scope.worker import worker as scope_worker
app.include_router(scope_router)
from .managed.api import router as managed_router
from .managed.worker import worker as managed_worker
app.include_router(managed_router)

@app.middleware("http")
async def protect_control_api(request: Request, call_next):
    path=request.url.path
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and path.startswith("/api/tasks/"):
        pieces = path.split("/")
        if len(pieces) > 4:
            with db.connect() as con:
                native_managed = con.execute("SELECT 1 FROM managed_tasks WHERE task_id=?", (pieces[3],)).fetchone()
                managed = con.execute("SELECT 1 FROM scope_sessions WHERE task_id=?", (pieces[3],)).fetchone()
            if native_managed or (managed and pieces[4] != "scope-manager"):
                return JSONResponse({"detail":"此任务由受管工作台管理，请通过相应任务接口提交和应用变更"}, status_code=409)
    if not path.startswith("/api/") or path in ("/api/health","/api/auth/mode") or path.startswith("/api/plugin/") or path.startswith("/api/generator/tasks/") or path.startswith("/api/agent/tasks/"):
        return await call_next(request)
    supplied=request.headers.get("authorization","")
    supplied=supplied[7:] if supplied.lower().startswith("bearer ") else ""
    if development.passwordless(request):
        if supplied:
            return JSONResponse({"detail":"任务凭据不能调用本机控制接口"}, status_code=401)
        return await call_next(request)
    if len(ADMIN_TOKEN)<32 or ADMIN_TOKEN=="replace-with-a-random-secret":
        return JSONResponse({"detail":"管理员口令未配置；请设置 AGENTSCOPE_ADMIN_TOKEN"},status_code=503)
    if not hmac.compare_digest(supplied,ADMIN_TOKEN):
        return JSONResponse({"detail":"需要有效的 AgentScope 管理员口令"},status_code=401)
    return await call_next(request)

class PrepareRequest(BaseModel):
    repo_url:str; ref:str="main"; prompt:str=Field(min_length=3,max_length=8000); dsh_profile:str="headless"
class PolicyRequest(BaseModel):
    strategy_ids:list[str]=[]; artifact_version_ids:list[str]=[]; settings:dict[str,Any]={}
class ReviewRequest(BaseModel):
    decision:str; reviewed_by:str="研究者"; notes:str=""
    expected_context_hash:str|None=None; expected_proposal_hash:str|None=None
class ScopeRequestBody(BaseModel):
    kind:str; path:str|None=None; justification:str=Field(min_length=4,max_length=1000); requested_by:str="用户"
class GovernanceRequest(BaseModel):
    task_id:str|None=None; kind:str; title:str; content:str=Field(min_length=5,max_length=30000); source_url:str|None=None


def issue_task_token(task_id):
    token=secrets.token_urlsafe(32)
    ident=uuid.uuid4().hex
    digest=hashlib.sha256(token.encode()).hexdigest()
    with db.connect() as con:
        con.execute("INSERT INTO task_credentials(id,task_id,token_sha256,created_at) VALUES(?,?,?,?)",(ident,task_id,digest,db.now()))
    return token,ident

def revoke_task_tokens(task_id,keep_id=None):
    with db.connect() as con:
        if keep_id:
            con.execute("UPDATE task_credentials SET revoked_at=? WHERE task_id=? AND id<>? AND revoked_at IS NULL",(db.now(),task_id,keep_id))
        else:
            con.execute("UPDATE task_credentials SET revoked_at=? WHERE task_id=? AND revoked_at IS NULL",(db.now(),task_id))
        con.execute("UPDATE agent_connections SET revoked_at=? WHERE task_id=? AND revoked_at IS NULL AND (legacy_credential_id IS NULL OR legacy_credential_id<>? OR ? IS NULL)", (db.now(),task_id,keep_id,keep_id))

def revoke_task_token(credential_id):
    with db.connect() as con:
        con.execute("UPDATE task_credentials SET revoked_at=? WHERE id=? AND revoked_at IS NULL",(db.now(),credential_id))
        con.execute("UPDATE agent_connections SET revoked_at=? WHERE legacy_credential_id=? AND revoked_at IS NULL", (db.now(),credential_id))

def require_agent_task(task_id,request):
    header=request.headers.get("authorization","")
    token=header[7:] if header.lower().startswith("bearer ") else ""
    if not token: raise HTTPException(401,"缺少任务凭据")
    digest=hashlib.sha256(token.encode()).hexdigest()
    with db.connect() as con:
        credential=con.execute("SELECT id FROM task_credentials WHERE task_id=? AND token_sha256=? AND revoked_at IS NULL",(task_id,digest)).fetchone()
        task=con.execute("SELECT * FROM tasks WHERE id=?",(task_id,)).fetchone()
    if not credential or not task: raise HTTPException(401,"任务凭据无效")
    if task["status"]!="running": raise HTTPException(409,"任务当前未运行")
    return dict(task),credential["id"]


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
    bootstrap_prompt=approved_prompt(task)
    if bootstrap_prompt is not None: return bootstrap_prompt
    project_context=(f"[AgentScope 工作区] 工作仓库：{task['workspace']}\n"
                     f"隔离输出目录：{task['output_dir']}\n"
                     "文件路径与命令工作目录以工作仓库为准；当前权限请读取任务 Scope。\n\n")
    base=project_context+task["prompt"].strip()
    if len(base)>8000: raise HTTPException(413,"任务提示词与工作区上下文超过 DSH 长度限制")
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
    fd,name=tempfile.mkstemp(prefix=f"agentscope-{re.sub('[^a-zA-Z0-9-]','',task_id)[:40]}-v{version}-",suffix=".yaml")
    os.close(fd);temp=Path(name)
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

def create_policy_version(task,version,layer,settings,strategy_ids,summary,extra_rules="",runtime_restrictions=None,artifact_ids=None):
    artifacts=selected_artifacts(task,artifact_ids or [])
    extra_rules="\n\n".join([extra_rules,*[a["data"]["actplane_dsl"] for a in artifacts]])
    dsl_text,yaml_text=policy.make_dsl(task["workspace"],task["output_dir"],settings,extra_rules)
    compile_state,compile_result,diagnostic=compile_policy(yaml_text,task["id"],version)
    policy_ir=build_policy_ir(task["id"],strategy_ids,compile_state,compile_result,runtime_restrictions)
    policy_ir["selected_dsl_artifacts"]=[{"id":a["id"],"version":a["version"],"content_hash":a["content_sha256"],
        "statement_version_id":a["statement_version_id"],"text":a["statement"].statement.text_original,
        "origin":a["statement"].origin.model_dump(),"kernel_enforcement":"compiled_fragment"} for a in artifacts]
    compile_result={"actplane":compile_result,"policy_ir":policy_ir,
                    "submitted_bundle_hash":hashlib.sha256(yaml_text.encode()).hexdigest()}
    with db.connect() as con:
        ev=[r[0] for r in con.execute("SELECT id FROM evidence WHERE task_id=?",(task["id"],)).fetchall()]
    status="draft" if compile_state in ("compile_failed","compile_timeout","backend_missing") else "compiled"
    policy.save_version(task["id"],version,layer,dsl_text,yaml_text,strategy_ids,ev,compile_state,compile_result,status,summary)
    with db.connect() as con:
        policy_id=con.execute("SELECT id FROM policy_versions WHERE task_id=? AND version=?",(task["id"],version)).fetchone()[0]
        for artifact in artifacts:
            con.execute("INSERT INTO history_policy_artifacts VALUES(?,?,?)",(policy_id,artifact["id"],artifact["content_sha256"]))
        con.execute("INSERT INTO history_compilations VALUES(?,?,?,?,?,?,?,?,?)",
            (uuid.uuid4().hex,None,task["id"],policy_id,compile_result["submitted_bundle_hash"],compile_state,
             compile_result["actplane"].get("compiler_version","ActPlane CLI"),json.dumps(compile_result["actplane"]),db.now()))
    return {"id":policy_id,"version":version,"dsl_text":dsl_text,"policy_yaml":yaml_text,"compile_state":compile_state,"compile_result":compile_result,"policy_ir":policy_ir,"diagnostic":diagnostic}

@app.on_event("startup")
async def startup():
    db.init_db()
    if os.getenv("AGENTSCOPE_HISTORY_WORKER","1")!="0" and os.getenv("AGENTSCOPE_RQ1_AUTO_IMPORT","1")!="0": corpus.ensure_seed_job()
    history_jobs.worker.start()
    scope_worker.start()
    managed_worker.start()

@app.on_event("shutdown")
async def shutdown():
    history_jobs.worker.stop()
    scope_worker.stop()
    managed_worker.stop()

@app.get("/api/health")
def health(): return {"ok":True,"service":"AgentScope","version":"0.2.0"}

@app.get("/api/auth/check")
def auth_check(): return {"ok":True}

@app.get('/api/auth/mode')
def auth_mode(request:Request):
    no_password=development.passwordless(request)
    return {'development_no_password':no_password,'authentication_required':not no_password}

@app.get("/api/status")
def status():
    lsm="unknown"
    try: lsm=Path("/sys/kernel/security/lsm").read_text().strip()
    except Exception: pass
    broker={"available":False}
    try: broker=broker_call({"action":"health"},timeout=2)
    except Exception as e: broker={"available":False,"error":str(e)}
    return {"kernel":os.uname().release,"architecture":os.uname().machine,"btf":Path("/sys/kernel/btf/vmlinux").exists(),"lsm":lsm,
      "bpf_lsm":"bpf" in lsm.split(","),"actplane_cli":ACTPLANE_BIN.exists(),"dsh_cli":DSH_BIN.exists(),
      "broker":broker,"vm":"Linux guest"}

@app.get("/api/dashboard")
def dashboard():
    with db.connect() as con:
        stats={"strategies":con.execute("SELECT count(*) FROM strategies WHERE is_archived=0 AND source_kind='rq1_corpus'").fetchone()[0],
          "pending_strategies":con.execute("SELECT count(*) FROM strategies s WHERE is_archived=0 AND source_kind='rq1_corpus' AND COALESCE((SELECT review_status FROM strategy_statement_versions WHERE strategy_id=s.id ORDER BY version DESC LIMIT 1),s.status)='pending_review'").fetchone()[0],
          "active_tasks":con.execute("SELECT count(*) FROM tasks WHERE status IN ('running','starting')").fetchone()[0],
          "pending_governance":con.execute("SELECT count(*) FROM governance_candidates WHERE status='pending_review'").fetchone()[0],
          "tasks":con.execute("SELECT count(*) FROM tasks").fetchone()[0]}
    try: active=broker_call({"action":"active"},timeout=2).get("tasks",[])
    except Exception: active=[]
    return {"stats":stats,"active":active}

@app.get("/api/strategies")
def get_strategies(q:str="",status_filter:str|None=Query(default=None,alias="status"),category:str|None=None,limit:int=100):
    records=corpus.search(q,limit,status_filter)
    if category: records=[r for r in records if r["category"]==category]
    return records

@app.post("/api/strategies/import")
def import_strategies():
    try: return corpus.import_rq1()
    except Exception as e: raise HTTPException(500,f"RQ1 导入失败：{e}")

@app.post("/api/strategies/{strategy_id}/review")
def review_strategy(strategy_id:str,body:ReviewRequest):
    if body.decision not in ("approve","reject"): raise HTTPException(400,"decision 只能是 approve 或 reject")
    status="approved" if body.decision=="approve" else "rejected"
    from .history.catalog import mutable_strategy
    from .history.api import invoke
    with db.connect() as con:
        row=invoke(mutable_strategy,con,strategy_id)
        latest=con.execute("SELECT id FROM strategy_statement_versions WHERE strategy_id=? ORDER BY version DESC LIMIT 1",(strategy_id,)).fetchone()
        if latest:
            invoke(review_statement_version,latest["id"],body.decision,body.reviewed_by)
            return dict(con.execute("SELECT * FROM strategies WHERE id=?",(strategy_id,)).fetchone())
        cur=con.execute("UPDATE strategies SET status=?,reviewed_at=?,reviewed_by=? WHERE id=?",(status,db.now(),body.reviewed_by,strategy_id))
        if not cur.rowcount: raise HTTPException(404,"策略记录不存在")
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

@app.get("/api/plugin/tasks/{task_id}/scope")
def plugin_scope(task_id:str,request:Request):
    with db.connect() as con:
        managed = con.execute("SELECT * FROM scope_sessions WHERE task_id=?", (task_id,)).fetchone()
        if managed:
            from .scope.api import agent_task
            from .scope.manager import active
            agent_task(task_id, request)
            current = active(con, dict(managed))
            task = require_task(task_id)
            directories = current["payload"]["allowed_write_dirs"] if current else []
            return {"task":{"id":task_id,"status":task["status"]},
                    "policy":{"version":current["revision"] if current else None,"dsl":current["payload"]["dsl"] if current else ""},
                    "runtime_restrictions":[{"path":str(Path(task["workspace"])/directories[0])}] if len(directories)==1 else [],
                    "scope_request_rule":"使用 scope-manager 工具；此接口仅返回已核验快照。"}
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

def validate_scope_request(task,body,con):
    if con.execute("SELECT 1 FROM scope_sessions WHERE task_id=?", (task["id"],)).fetchone():
        raise HTTPException(409,"此任务的变更只能通过 ScopeManager 分析、审核与核验")
    if con.execute("SELECT 1 FROM bootstrap_contexts WHERE task_id=?",(task["id"],)).fetchone(): raise HTTPException(409,"RQ5 首版只接收第三层上下文与事件；不启用运行中策略修改")
    if task["status"]!="running": raise HTTPException(409,"只有运行中的任务可以申请运行时 Scope 变更")
    if body.kind not in ("restrict","expand"): raise HTTPException(400,"kind 必须为 restrict 或 expand")
    if body.kind=="restrict" and not body.path: raise HTTPException(400,"收紧 Scope 时必须指定仓库内允许写入的路径")
    if body.kind=="restrict" and body.path:
        target=Path(body.path).resolve(); workspace=Path(task["workspace"]).resolve()
        if target!=workspace and workspace not in target.parents: raise HTTPException(400,"收紧范围只能指定当前任务仓库工作区内的路径")
        if not target.is_dir(): raise HTTPException(400,"收紧 Scope 路径必须是当前工作区中已存在的目录")

def create_scope_request(task_id,body):
    task=require_task(task_id)
    reqid=uuid.uuid4().hex
    with db.connect() as con:
        validate_scope_request(task,body,con)
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
    with db.connect() as con:
        if con.execute("SELECT 1 FROM bootstrap_contexts WHERE task_id=?",(task_id,)).fetchone(): raise HTTPException(409,"RQ5 任务必须通过 Pi 候选整包入口生成")
    if task["status"] not in ("prepared","policy_review","approved"): raise HTTPException(409,"历史策略只能在任务启动前选择")
    try: selected_artifacts(task,body.artifact_version_ids)
    except ValueError as e: raise HTTPException(409,str(e))
    settings={"read_only":False,"deny_network":False,"allow_task_output":False,**json.loads(task["settings_json"] or "{}"),**body.settings}
    with db.connect() as con:
        claimed=con.execute("UPDATE tasks SET status='policy_generating',updated_at=? WHERE id=? AND status IN ('prepared','policy_review','approved')",(db.now(),task_id)).rowcount
        if not claimed: raise HTTPException(409,"任务已在生成、启动或运行，不能重新生成启动策略")
        if body.strategy_ids:
            qs=",".join("?" for _ in body.strategy_ids)
            approved=con.execute(f"SELECT id FROM strategies WHERE id IN ({qs}) AND status='approved' AND is_archived=0",body.strategy_ids).fetchall()
            ids=[r[0] for r in approved]
        else: ids=[]
        version=con.execute("SELECT COALESCE(MAX(version),0)+1 FROM policy_versions WHERE task_id=?",(task_id,)).fetchone()[0]
        db.audit(con,task_id,"policy_generated","AgentScope",{"version":version,"settings":settings,"strategy_ids":ids,"artifact_version_ids":body.artifact_version_ids})
    try:
        result=create_policy_version(task,version,"task_start",settings,ids,"任务启动前策略：基础配置、已选历史 DSL 与仓库证据",artifact_ids=body.artifact_version_ids)
        with db.connect() as con:
            changed=con.execute("UPDATE tasks SET settings_json=?,status='policy_review',updated_at=? WHERE id=? AND status='policy_generating'",(json.dumps(settings),db.now(),task_id)).rowcount
            if not changed: raise HTTPException(409,"任务状态已改变；本次生成版本未批准")
        return result
    except Exception:
        with db.connect() as con:
            con.execute("UPDATE tasks SET status=?,updated_at=? WHERE id=? AND status='policy_generating'",(task["status"],db.now(),task_id))
        raise

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
    if task["status"] not in ("prepared","policy_review","approved"): raise HTTPException(409,"运行中任务不能重新批准启动版本")
    with db.connect() as con:
        row=con.execute("SELECT * FROM policy_versions WHERE task_id=? AND version=?",(task_id,version)).fetchone()
        if not row: raise HTTPException(404,"策略版本不存在")
        try: verify_version(con,task_id,row["id"],body.expected_context_hash,body.expected_proposal_hash,approval=body.decision=="approve")
        except ValueError as error: raise HTTPException(409,str(error))
        if body.decision!="approve":
            con.execute("UPDATE policy_versions SET status='rejected',approved_by=?,approved_at=? WHERE task_id=? AND version=?",(body.reviewed_by,db.now(),task_id,version))
            db.audit(con,task_id,"policy_rejected",body.reviewed_by,{"version":version,"notes":body.notes})
            return {"status":"rejected"}
        if row["compile_state"] != "compiled": raise HTTPException(409,"ActPlane 未完整支持该策略中的全部子句；请先调整策略再申请批准")
        con.execute("UPDATE policy_versions SET status='approved',approved_by=?,approved_at=? WHERE task_id=? AND version=?",(body.reviewed_by,db.now(),task_id,version))
        changed=con.execute("UPDATE tasks SET status='approved',active_version=?,updated_at=? WHERE id=? AND status IN ('prepared','policy_review','approved')",(version,db.now(),task_id)).rowcount
        if not changed: raise HTTPException(409,"任务已经启动或正在生成策略，不能批准启动版本")
        db.audit(con,task_id,"policy_approved",body.reviewed_by,{"version":version,"notes":body.notes})
    return {"status":"approved","version":version}

@app.post("/api/tasks/{task_id}/launch")
def launch_task(task_id:str):
    task=require_task(task_id)
    with db.connect() as con:
        v=con.execute("SELECT * FROM policy_versions WHERE task_id=? AND version=?",(task_id,task["active_version"])).fetchone()
        if not v or v["status"]!="approved": raise HTTPException(409,"请先审核并批准当前策略版本")
    provider=ActPlaneProvider(broker_call,build_agent_prompt,issue_task_token,revoke_task_token,revoke_task_tokens,PUBLIC_BASE_URL)
    try: return provider.load_task_policy(task_id,v["id"])
    except ValueError as e: raise HTTPException(409,str(e))
    except Exception as e: raise HTTPException(503,f"ActPlane/DSH 启动失败：{e}")

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
                rule_meta=raw.get("rule") if isinstance(raw.get("rule"),dict) else {}
                reason=raw.get("reason") or raw.get("because") or raw.get("message") or rule_meta.get("reason") or json.dumps(raw,ensure_ascii=False)[:500]
                op=raw.get("operation") or raw.get("op") or raw.get("kind")
                target=raw.get("target") or raw.get("path") or raw.get("endpoint")
                decision=raw.get("effect") or raw.get("decision") or raw.get("action")
                key=hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest()
                events.append({"id":key,"task_id":task_id,"kind":raw.get("type","policy_match"),"operation":op,"target":target,"decision":decision,"reason":reason,"occurred_at":raw.get("timestamp") or raw.get("time") or "", "raw":raw})
                with db.connect() as con:
                    con.execute("INSERT INTO runtime_events(id,task_id,kind,operation,target,decision,reason,occurred_at,raw_json,dedupe_key) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(dedupe_key) DO UPDATE SET reason=excluded.reason",(uuid.uuid4().hex,task_id,raw.get("type","policy_match"),op,target,decision,str(reason),str(raw.get("timestamp") or raw.get("time") or db.now()),json.dumps(raw,ensure_ascii=False),key))
        except Exception: pass
    if runtime.get("agent_status")=="exited" and task["status"]=="running" and task["dsh_profile"]!="web":
        exit_status=(runtime.get("child") or {}).get("status") or {}
        exit_code=exit_status.get("code")
        signal=exit_status.get("signal")
        succeeded=type(exit_code) is int and exit_code==0 and signal is None
        task["status"]="completed" if succeeded else "failed"
        cleanup_confirmed=False
        try:
            cleanup=broker_call({"action":"stop","task_id":task_id},timeout=12)
            cleanup_confirmed=cleanup.get('status') in ('stopped','not_running')
            runtime["completion_cleanup"]="DSH 一次性会话已退出，ActPlane watch 已清理" if cleanup_confirmed else "DSH 已退出；ActPlane watch 清理未确认"
        except Exception:
            runtime["completion_cleanup"]="DSH 已退出；ActPlane watch 清理未确认"
        runtime["execution_exit"]={"code":exit_code,"signal":signal,"succeeded":succeeded}
        with db.connect() as con:
            con.execute("UPDATE tasks SET status=?,ended_at=?,updated_at=? WHERE id=?",(task["status"],db.now(),db.now(),task_id))
            if cleanup_confirmed:con.execute('UPDATE tasks SET active_pid=NULL,active_domain_id=NULL,watch_pid=NULL WHERE id=?',(task_id,))
            db.audit(con,task_id,"task_execution_finished","AgentScope",runtime["execution_exit"])
            con.execute("UPDATE history_deployments SET active=0,ended_at=? WHERE task_id=? AND active=1",(db.now(),task_id))
        revoke_task_tokens(task_id)
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
        from .agent_bridge.api import validate_review_binding
        validate_review_binding(con,task_id,request_id)
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
                previous=con.execute("SELECT id,source_strategy_ids FROM policy_versions WHERE task_id=? AND version=?",(task_id,task["active_version"])).fetchone()
                restrictions=[dict(r) for r in con.execute("SELECT id,path,justification,reviewed_by,reviewed_at FROM scope_requests WHERE task_id=? AND kind='restrict' AND status='approved' ORDER BY created_at",(task_id,)).fetchall()]
            inherited_ids=json.loads(previous["source_strategy_ids"] or "[]") if previous else []
            with db.connect() as con:
                inherited_artifacts=[r[0] for r in con.execute("SELECT artifact_id FROM history_policy_artifacts WHERE policy_version_id=?",(previous["id"],))] if previous else []
            inherited_rules="\n\n".join(policy.make_restrictive_delta({"workspace":task["workspace"]},r) for r in restrictions if r.get("path"))
            restriction_ir=[{"request_id":r["id"],"path":r["path"],"justification":r["justification"],"approved_by":r["reviewed_by"],"approved_at":r["reviewed_at"],"preserved_in_new_version":True} for r in restrictions if r.get("path")]
            created_version=version
            bundle=create_policy_version(task,version,"runtime_restart",settings,inherited_ids,"经审核扩展 Scope：加入隔离的任务输出目录；保留既有运行时限制并按新版本重启",inherited_rules,restriction_ir,artifact_ids=inherited_artifacts)
            if bundle["compile_state"]!="compiled": raise RuntimeError("扩展策略未获完整后端支持，不能批准："+bundle["diagnostic"])
            prompt=build_agent_prompt(task,inherited_ids)+"\n\n[AgentScope] 任务权限已审核更新。请从当前工作区现状继续原任务。"
            if len(prompt)>8000: raise RuntimeError("继承历史策略后的重启提示词超过 DSH 长度限制；请缩短任务提示或减少历史策略")
            task_token,new_credential_id=issue_task_token(task_id)
            result=broker_call({"action":"restart","task_id":task_id,"version":version,"workspace":task["workspace"],"output_dir":task["output_dir"],"prompt":prompt,"dsl_text":bundle["dsl_text"],"policy_yaml":bundle["policy_yaml"],"dsh_profile":task["dsh_profile"],"task_token":task_token,"agentscope_url":PUBLIC_BASE_URL},timeout=40)
            binding=broker_call({"action":"status","task_id":task_id},timeout=8)
            if (binding.get("child") or {}).get("child_id")!=result.get("domain_id") or binding.get("runner_pid")!=result.get("runner_pid"):
                raise RuntimeError("Scope 重启后的进程域绑定未确认")
            result.update(binding_confirmed=True,bundle_hash=bundle["compile_result"]["submitted_bundle_hash"],artifact_version_ids=inherited_artifacts)
            revoke_task_tokens(task_id,new_credential_id)
            newver=version
        with db.connect() as con:
            if created_version is not None:
                con.execute("UPDATE history_deployments SET active=0,ended_at=? WHERE task_id=? AND active=1",(db.now(),task_id))
                con.execute("INSERT INTO history_deployments(id,policy_version_id,task_id,bundle_hash,status,active,domain_id,runner_pid,receipt_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (uuid.uuid4().hex,bundle["id"],task_id,result["bundle_hash"],"loaded",int(binding.get("agent_status")=="running"),result["domain_id"],result["runner_pid"],json.dumps(result),db.now()))
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
                still_running=current.get("available") and current.get("status")=="running" and current.get("domain_id")==task.get("active_domain_id")
                if not still_running:
                    con.execute("UPDATE history_deployments SET active=0,ended_at=? WHERE task_id=? AND active=1",(db.now(),task_id))
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
        con.execute('UPDATE tasks SET active_pid=NULL,active_domain_id=NULL,watch_pid=NULL WHERE id=?',(task_id,))
        con.execute("UPDATE history_deployments SET active=0,ended_at=? WHERE task_id=? AND active=1",(db.now(),task_id))
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

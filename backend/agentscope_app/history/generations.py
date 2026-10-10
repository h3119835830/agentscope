"""Checkpointed first-layer pipeline. Model outputs never carry approval authority."""
import json
import re
import uuid
from .. import db
from . import registry, sources
from .models import Statement, ExtractionResult, StrategyStatementVersion
from .pipeline import (digest, extract_strategy_statements, generate_policy_artifact,
    verify_evidence, SINGLE_COMPLETENESS_PROMPT)
from .llm import DeepSeekProvider
from .capabilities import translation_capabilities


class Cancelled(Exception):
    pass


def check_cancel(ident):
    with db.connect() as con:
        row = con.execute("SELECT cancel_requested FROM history_generations WHERE id=?",(ident,)).fetchone()
    if not row or row[0]: raise Cancelled()


class CheckedProvider:
    def __init__(self, ident, delegate): self.ident, self.delegate = ident, delegate
    def generate(self, *args):
        check_cancel(self.ident)
        value = self.delegate.generate(*args)
        check_cancel(self.ident)
        return value


def create(payload):
    if bool(payload.get("repo_url")) == bool(payload.get("statement_version_id")):
        raise ValueError("选择 GitHub 或确切语句版本作为唯一输入")
    if payload.get("repo_url"):
        from ..services.github import parse_github_url
        parse_github_url(payload["repo_url"])
        for path in payload.get("additional_paths",[]): sources.relative_path(path)
    else: registry.load_statement(payload["statement_version_id"])
    public = {k:v for k,v in payload.items() if k != "request_key"}
    key = payload.get("request_key") or (digest(public) if re.fullmatch(r"[0-9a-f]{40}",payload.get("ref","")) else uuid.uuid4().hex)
    with db.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        existing = con.execute("SELECT * FROM history_generations WHERE request_key=?",(key,)).fetchone()
        if existing:
            if json.loads(existing["input_json"]) != public: raise ValueError("重复请求 key 对应不同输入")
            return {"id":existing["id"],"status":existing["status"],"reused":True}
        active = con.execute("SELECT * FROM history_generations WHERE input_json=? AND status IN ('queued','running')",(json.dumps(public,sort_keys=True),)).fetchone()
        if active: return {"id":active["id"],"status":active["status"],"reused":True}
        ident=uuid.uuid4().hex
        con.execute("INSERT INTO history_generations(id,request_key,status,input_json,created_at) VALUES(?,?,?,?,?)",
            (ident,key,"queued",json.dumps(public,sort_keys=True),db.now()))
        job_id=uuid.uuid4().hex
        con.execute("INSERT INTO history_jobs(id,kind,status,input_json,created_at) VALUES(?,?,?,?,?)",(job_id,"history_generation","queued",json.dumps({"run_id":ident}),db.now()))
        con.execute("UPDATE history_generations SET job_id=? WHERE id=?",(job_id,ident))
        db.audit(con,None,"history_generation_created","用户",{"run_id":ident,"input":public})
    from .jobs import worker
    worker.wake.set()
    return {"id":ident,"status":"queued","job_id":job_id}


def get(ident):
    with db.connect() as con:
        row=con.execute("SELECT * FROM history_generations WHERE id=?",(ident,)).fetchone()
        if not row: raise ValueError("生成批次不存在")
        value=db.row_dict(row)
        project_source(con,value)
        value["steps"]=[db.row_dict(r) for r in con.execute("SELECT * FROM history_generation_steps WHERE run_id=? ORDER BY updated_at,step_key",(ident,))]
        value["statistics"]={r[0]:r[1] for r in con.execute("SELECT status,COUNT(*) FROM history_generation_results WHERE run_id=? GROUP BY status",(ident,))}
    return value


def project_source(con,item):
    if not item["source"] and item["input"].get("statement_version_id"):
        statement=con.execute("SELECT record_json FROM strategy_statement_versions WHERE id=?",(item["input"]["statement_version_id"],)).fetchone()
        if statement:item["source"]={k:v for k,v in json.loads(statement[0])["origin"].items() if k in ("repository","commit","path")}


def list_runs():
    with db.connect() as con:
        return [db.row_dict(r) for r in con.execute("SELECT * FROM history_generations ORDER BY created_at DESC LIMIT 100")]


def page_runs(q="",status="",limit=20,offset=0,console=False):
    if status not in ("","queued","running","completed","partial","failed","cancelled","interrupted"):
        raise ValueError("生成记录状态不合法")
    filters=[];params=[]
    if console:filters.append("g.id NOT IN (SELECT record_id FROM console_retained_records WHERE kind='generation')")
    if status:filters.append("g.status=?");params.append(status)
    if q:
        filters.append("(g.id LIKE ? OR g.input_json LIKE ? OR g.source_json LIKE ? OR json_extract(v.record_json,'$.origin.repository') LIKE ? OR json_extract(v.record_json,'$.origin.commit') LIKE ? OR json_extract(v.record_json,'$.origin.path') LIKE ?)")
        params.extend(["%"+q+"%"]*6)
    where=" WHERE "+" AND ".join(filters) if filters else ""
    joined=" FROM history_generations g LEFT JOIN strategy_statement_versions v ON v.id=json_extract(g.input_json,'$.statement_version_id')"
    with db.connect() as con:
        total=con.execute("SELECT COUNT(*)"+joined+where,params).fetchone()[0]
        rows=con.execute("SELECT g.*"+joined+where+" ORDER BY g.created_at DESC,g.id DESC LIMIT ? OFFSET ?",[*params,limit,offset]).fetchall()
        items=[]
        for row in rows:
            item=db.row_dict(row)
            item["statistics"]={r[0]:r[1] for r in con.execute("SELECT r.status,COUNT(*) FROM history_generation_results r JOIN strategy_statement_versions v ON v.id=r.statement_version_id WHERE r.run_id=? AND json_extract(v.record_json,'$.statement.content_type')!='description' GROUP BY r.status",(row["id"],))}
            project_source(con,item)
            items.append(item)
    return {"items":items,"total":total,"limit":limit,"offset":offset}


def cancel(ident):
    value=get(ident)
    if value["status"] not in ("queued","running"): raise ValueError("只有排队或运行批次可取消")
    with db.connect() as con:
        changed=con.execute("UPDATE history_generations SET cancel_requested=1 WHERE id=? AND status IN ('queued','running')",(ident,)).rowcount
        if not changed:raise ValueError("生成已结束，无法取消")
        db.audit(con,None,"history_generation_cancel_requested","用户",{"run_id":ident})
    return {"status":"cancelling"}


def retry(ident):
    value=get(ident)
    if value["status"] not in ("failed","partial","interrupted","cancelled"): raise ValueError("当前批次不可重试")
    with db.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        changed=con.execute("UPDATE history_generations SET status='queued',cancel_requested=0,error=NULL,finished_at=NULL WHERE id=? AND status=?",(ident,value["status"])).rowcount
        if not changed: raise ValueError("批次已被其他请求重试")
        for row in con.execute("SELECT statement_version_id FROM history_generation_results WHERE run_id=? AND status='failed'",(ident,)):
            con.execute("UPDATE history_generation_steps SET status='failed' WHERE run_id=? AND step_key=?",(ident,"artifact:"+row[0]))
        for row in con.execute("SELECT step_key,result_json FROM history_generation_steps WHERE run_id=? AND stage='extract_and_review' AND status='completed'",(ident,)):
            if not json.loads(row['result_json']).get('coverage',{}).get('complete'):
                con.execute("UPDATE history_generation_steps SET status='failed',error='原文覆盖不完整，重试该文档' WHERE run_id=? AND step_key=?",(ident,row['step_key']))
        job_id=uuid.uuid4().hex
        con.execute("INSERT INTO history_jobs(id,kind,status,input_json,retry_of,created_at) VALUES(?,?,?,?,?,?)",(job_id,"history_generation","queued",json.dumps({"run_id":ident}),value["job_id"],db.now()))
        con.execute("UPDATE history_generations SET job_id=? WHERE id=?",(job_id,ident))
        db.audit(con,None,"history_generation_retried","用户",{"run_id":ident,"job_id":job_id})
    from .jobs import worker
    worker.wake.set()
    return {"id":ident,"status":"queued","job_id":job_id}


def step(ident,key,stage,fn):
    check_cancel(ident)
    with db.connect() as con:
        prior=con.execute("SELECT * FROM history_generation_steps WHERE run_id=? AND step_key=?",(ident,key)).fetchone()
        if prior and prior["status"]=="completed": return json.loads(prior["result_json"])
        con.execute("UPDATE history_generations SET stage=? WHERE id=?",(stage,ident))
        con.execute("INSERT INTO history_generation_steps VALUES(?,?,?,?,?,?,?) ON CONFLICT(run_id,step_key) DO UPDATE SET status='running',error=NULL,updated_at=excluded.updated_at",
            (ident,key,stage,"running","{}",None,db.now()))
    try:
        result=fn()
        check_cancel(ident)
        with db.connect() as con:
            con.execute("UPDATE history_generation_steps SET status='completed',result_json=?,updated_at=? WHERE run_id=? AND step_key=?",(json.dumps(result,ensure_ascii=False),db.now(),ident,key))
        return result
    except Exception as e:
        with db.connect() as con:
            con.execute("UPDATE history_generation_steps SET status=?,error=?,updated_at=? WHERE run_id=? AND step_key=?",("cancelled" if isinstance(e,Cancelled) else "failed",str(e)[:1000],db.now(),ident,key))
        raise


def review_single(version,provider):
    document=sources.read_document(version.origin.document_id)
    lines=document.text.splitlines()
    if len(document.text.encode()) > 80000: raise ValueError("原文完整上下文超限，需人工拆分")
    result,meta=provider.generate(SINGLE_COMPLETENESS_PROMPT,
        {"first_line":1,"last_line":len(lines),"lines":[{"line":i+1,"text":t} for i,t in enumerate(lines)],
         "statement_schema":Statement.model_json_schema(),"ENFORCEMENT_CAPABILITIES":translation_capabilities(),
         "VERIFIED_CONTEXT":version.resolved_context,
         "heading_context":[],"adjacent_context":[],"first_pass":[version.statement.model_dump()],
         "review":"Review ONLY the selected candidate. Preserve its intent; no unrelated candidates."},"history-completeness-v2")
    candidates=result.get("statements",[])
    if len(candidates)!=1: raise ValueError("单条复核必须返回一个完整候选")
    s=verify_evidence(document,Statement.model_validate(candidates[0]))
    if s.evidence_state!="verified": raise ValueError("二审原文证据未通过校验")
    with db.connect() as con:
        number=con.execute("SELECT MAX(version)+1 FROM strategy_statement_versions WHERE strategy_id=?",(version.strategy_id,)).fetchone()[0]
        new=version.model_copy(update={"id":uuid.uuid4().hex,"version":number,"statement":s,"review_status":"pending_review"})
        data=new.model_dump(exclude={"review_status"})
        con.execute("INSERT INTO strategy_statement_versions(id,strategy_id,version,document_id,record_json,content_sha256,review_status,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (new.id,new.strategy_id,number,new.origin.document_id,json.dumps(data,ensure_ascii=False),digest(data),"pending_review",db.now()))
        db.audit(con,None,"history_completeness_review","DeepSeek",{"statement_version_id":new.id,"parent":version.id,"llm_run":meta,"conclusion":s.completeness,"issues":s.review_issues})
    return {"statement_version_ids":[new.id],"llm_runs":[meta]}


def compile_candidate(version,provider):
    from ..main import compile_policy
    attempts=[]; diagnostic=None
    for attempt in range(2):
        candidate=generate_policy_artifact(version,provider=provider,compiler_diagnostic=diagnostic,structured=True,allow_unreviewed=True)
        state=candidate.state; info={}
        if candidate.actplane_dsl:
            dsl='source AGENT = exec "**"\n'+candidate.actplane_dsl
            yaml="version: 1\npolicy: |\n"+"\n".join("  "+line for line in dsl.splitlines())+"\n"
            state,info,diagnostic=compile_policy(yaml,uuid.uuid4().hex,attempt+1)
        elif state=="invalid_candidate": diagnostic="; ".join(candidate.policy_record["compile_check"]["diagnostics"])
        aid=registry.save_artifact(candidate,state,{**info,"diagnostic":diagnostic})
        attempts.append(aid)
        if state not in ("compile_failed","invalid_candidate","partial"): break
    return {"artifact_id":aid,"attempt_ids":attempts,"compile_state":state,"diagnostic":diagnostic}


def execute(run_id,provider=None):
    provider=CheckedProvider(run_id,provider or DeepSeekProvider())
    with db.connect() as con:
        row=con.execute("SELECT * FROM history_generations WHERE id=?",(run_id,)).fetchone()
        if not row or row["status"]!="queued": raise ValueError("批次未排队")
        con.execute("UPDATE history_generations SET status='running' WHERE id=?",(run_id,))
    payload=json.loads(row["input_json"]); failures=0
    try:
        if payload.get("statement_version_id"):
            reviewed=step(run_id,"single-review","completeness_review",lambda:review_single(registry.load_statement(payload["statement_version_id"]),provider))
            ids=reviewed["statement_version_ids"]
        else:
            source=step(run_id,"source","source",lambda:sources.collect_documents(payload["repo_url"],payload.get("ref","main"),payload.get("additional_paths",[]),include_instruction_files=payload.get("include_instruction_files",True)))
            with db.connect() as con: con.execute("UPDATE history_generations SET source_json=? WHERE id=?",(json.dumps(source),run_id))
            if not source["document_ids"]: raise ValueError("未找到指令文档，请指定附加文件")
            ids=[]
            for did in source["document_ids"]:
                def extract(did=did):
                    doc=sources.read_document(did)
                    result=extract_strategy_statements(doc,provider=provider)
                    return {"statement_version_ids":registry.save_extraction(doc,result),"coverage":result.coverage,"llm_runs":result.llm_runs}
                try:
                    extracted=step(run_id,"extract:"+did,"extract_and_review",extract)
                    ids.extend(extracted["statement_version_ids"])
                    if not extracted.get("coverage",{}).get("complete"): failures+=1
                except Cancelled: raise
                except Exception: failures+=1
        for sid in ids:
            version=registry.load_statement(sid)
            with db.connect() as con:
                con.execute("INSERT OR IGNORE INTO history_generation_results(run_id,statement_version_id,status) VALUES(?,?,?)",(run_id,sid,"pending"))
            try:
                if version.statement.completeness not in ("complete","description"):
                    with db.connect() as con: con.execute("UPDATE history_generation_results SET status='needs_clarification',error='完整性二审未通过' WHERE run_id=? AND statement_version_id=?",(run_id,sid))
                    continue
                value=step(run_id,"artifact:"+sid,"ir_and_compile",lambda:compile_candidate(version,provider))
                state=value["compile_state"]
                status={"compiled":"ready","unsupported":"ready","requires_context":"needs_adaptation","needs_clarification":"needs_clarification"}.get(state,"failed")
                if status=="failed": failures+=1
                error=(value.get("diagnostic") or "产物校验/编译未通过："+state) if status=="failed" else None
                with db.connect() as con: con.execute("UPDATE history_generation_results SET artifact_id=?,status=?,error=? WHERE run_id=? AND statement_version_id=?",(value["artifact_id"],status,error,run_id,sid))
            except Cancelled: raise
            except Exception as e:
                failures+=1
                with db.connect() as con: con.execute("UPDATE history_generation_results SET status='failed',error=? WHERE run_id=? AND statement_version_id=?",(str(e)[:1000],run_id,sid))
        check_cancel(run_id)
        with db.connect() as con:
            retained=con.execute("SELECT COUNT(*) FROM history_generation_results WHERE run_id=? AND status IN ('ready','needs_adaptation','needs_clarification')",(run_id,)).fetchone()[0]
        status=("partial" if retained else "failed") if failures else "completed"
        with db.connect() as con: con.execute("UPDATE history_generations SET status=?,stage='review',finished_at=? WHERE id=?",(status,db.now(),run_id))
    except Exception as e:
        status="cancelled" if isinstance(e,Cancelled) else "failed"
        with db.connect() as con: con.execute("UPDATE history_generations SET status=?,error=?,finished_at=? WHERE id=?",(status,str(e)[:1000],db.now(),run_id))
    return get(run_id)


def results(ident,limit=20,offset=0,**filters):
    get(ident)
    with db.connect() as con:
        rows=con.execute("SELECT r.*,v.record_json,v.content_sha256 AS statement_hash,v.review_status,v.version,a.artifact_json,a.compile_json,a.content_sha256 AS artifact_hash,a.compile_state,a.review_status AS artifact_review_status FROM history_generation_results r JOIN strategy_statement_versions v ON v.id=r.statement_version_id LEFT JOIN history_artifacts a ON a.id=r.artifact_id WHERE r.run_id=? ORDER BY v.created_at,r.statement_version_id",(ident,)).fetchall()
    items=[]
    from .eligibility import blockers
    for row in rows:
        item=dict(row); item["record"]=json.loads(item.pop("record_json")); item["artifact"]=json.loads(item.pop("artifact_json") or "null")
        item["compilation"]=json.loads(item.pop("compile_json") or "{}");
        s=item["record"]["statement"]; a=item["artifact"]
        from .pipeline import reviewed_phrase_errors
        item["review_blockers"]=reviewed_phrase_errors(s)
        if s.get("evidence_state")!="verified":item["review_blockers"].append("原文证据未定位")
        if item["status"] in ("failed","pending","needs_clarification"):item["review_blockers"].append("候选生成或校验未完成，请修订或重试")
        item["adaptation"]=(a or {}).get("policy_record",{}).get("metadata",{}).get("adaptation",{"state":"not_required"})
        item["load_blockers"]=blockers(a,item["record"]) if a else ["尚无产物"]
        if item["review_status"]!="approved" or item["artifact_review_status"]!="approved": item["load_blockers"].append("尚未最终人工审核")
        if not a or not a.get("actplane_dsl"): item["load_blockers"].append("没有执行 DSL")
        elif item["compile_state"]!="compiled": item["load_blockers"].append("尚未编译通过")
        item["eligible"]=not item["load_blockers"]
        haystack=json.dumps(item["record"],ensure_ascii=False).lower()
        if filters.get("q") and filters["q"].lower() not in haystack: continue
        if filters.get("execution_level") and s["enforcement_level"]!=filters["execution_level"]: continue
        if filters.get("context_scope") and s["context_requirement"]!=filters["context_scope"]: continue
        if filters.get("completeness") and s.get("completeness","unreviewed")!=filters["completeness"]: continue
        if filters.get("adaptation") and item["adaptation"]["state"]!=filters["adaptation"]: continue
        if filters.get("loadable") and item["eligible"]!=(filters["loadable"]=="yes"): continue
        if s["content_type"]=="description" and not filters.get("include_descriptions"): continue
        items.append(item)
    return {"items":items[offset:offset+limit],"total":len(items),"limit":limit,"offset":offset}


def final_review(ident,items,decision,actor):
    if decision not in ("approve","reject") or not items: raise ValueError("无效审核请求")
    get(ident)
    validated=[]
    with db.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        for item in items:
            row=con.execute("SELECT r.*,v.content_sha256,v.record_json,a.content_sha256 AS artifact_hash,a.artifact_json,a.compile_state FROM history_generation_results r JOIN strategy_statement_versions v ON v.id=r.statement_version_id LEFT JOIN history_artifacts a ON a.id=r.artifact_id WHERE r.run_id=? AND r.statement_version_id=?",(ident,item["statement_version_id"])).fetchone()
            if not row or row["content_sha256"]!=item["expected_statement_hash"] or row["artifact_id"]!=item.get("artifact_id") or row["artifact_hash"]!=item.get("expected_artifact_hash"): raise ValueError("候选版本或预期 hash 已变化")
            version=registry.load_statement(row["statement_version_id"])
            from .catalog import mutable_strategy
            mutable_strategy(con,version.strategy_id)
            if decision=="approve":
                if row["status"] not in ("ready","needs_adaptation"): raise ValueError("候选生成或校验未完成，请修订或重试")
                checked=verify_evidence(sources.read_document(version.origin.document_id),version.statement)
                if checked.completeness!="complete" or checked.evidence_state!="verified": raise ValueError("完整性或原文证据未通过")
                if not row["artifact_id"]: raise ValueError("尚无候选产物")
                data=json.loads(row["artifact_json"])
                if digest(data)!=row["artifact_hash"]: raise ValueError("候选内容 hash 不一致")
                if data.get("actplane_dsl") and row["compile_state"]!="compiled": raise ValueError("执行 DSL 未编译通过")
            validated.append((version,row["artifact_id"]))
        status="approved" if decision=="approve" else "rejected"
        for version,aid in validated:
            con.execute("UPDATE strategy_statement_versions SET review_status=?,reviewed_hash=content_sha256,reviewed_by=?,reviewed_at=? WHERE id=?",(status,actor,db.now(),version.id))
            con.execute("UPDATE strategies SET status=?,reviewed_by=?,reviewed_at=? WHERE id=?",(status,actor,db.now(),version.strategy_id))
            if aid: con.execute("UPDATE history_artifacts SET review_status=?,reviewed_hash=content_sha256,reviewed_by=?,reviewed_at=? WHERE id=?",(status,actor,db.now(),aid))
        db.audit(con,None,"history_generation_final_review",actor,{"run_id":ident,"items":items,"decision":decision})
    return {"status":status,"count":len(validated)}

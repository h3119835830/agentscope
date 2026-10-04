import json
from pathlib import Path
import uuid
from .. import db
from .models import StrategyStatementVersion
from .pipeline import digest, verify_evidence, validate_fragment

def load_statement(ident):
    with db.connect() as con: row=con.execute("SELECT * FROM strategy_statement_versions WHERE id=?",(ident,)).fetchone()
    if not row: raise ValueError("语句版本不存在")
    data=json.loads(row["record_json"]); data["review_status"]=row["review_status"]
    if digest(json.loads(row["record_json"]))!=row["content_sha256"]: raise ValueError("语句内容 hash 不一致")
    return StrategyStatementVersion.model_validate(data)

def save_extraction(document,result):
    ids=[]
    with db.connect() as con:
        doc=con.execute("SELECT scope_path FROM history_documents WHERE id=?",(document.origin.document_id,)).fetchone()
        for s in result.statements:
            sentence_hash=digest([s.source_quote,s.text_original,s.line_start,s.line_end])
            old=con.execute("SELECT id FROM strategies WHERE source_repo=? AND source_commit=? AND source_path=? AND sentence_sha256=?",
                (document.origin.repository,document.origin.commit,document.origin.path,sentence_hash)).fetchone()
            if old:
                prior=con.execute("SELECT id,record_json FROM strategy_statement_versions WHERE strategy_id=? ORDER BY version",(old["id"],)).fetchall()
                matching=next((v for v in prior if json.loads(v["record_json"])["statement"]==s.model_dump() and not json.loads(v["record_json"])["resolved_context"]),None)
                if matching: ids.append(matching["id"]); continue
            sid=old["id"] if old else uuid.uuid4().hex
            if not old:
                con.execute("""INSERT INTO strategies(id,text,category,category_confidence,context_scope,execution_layer,status,
                 source_repo,source_commit,source_path,line_start,line_end,raw_url,source_content_sha256,sentence_sha256,
                 source_verified,source_kind,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (sid,s.text_original,s.enforcement_level.replace("_","-"),0,s.context_requirement.replace("_","-"),
                  "llm_candidate","pending_review",document.origin.repository,document.origin.commit,document.origin.path,
                  s.line_start,s.line_end,document.origin.url,document.origin.content_hash,sentence_hash,
                  int(s.evidence_state=="verified"),"history_document",json.dumps({"content_type":s.content_type}),db.now()))
            ident=uuid.uuid4().hex
            version=con.execute("SELECT COALESCE(MAX(version),0)+1 FROM strategy_statement_versions WHERE strategy_id=?",(sid,)).fetchone()[0]
            record=StrategyStatementVersion(id=ident,strategy_id=sid,version=version,origin=document.origin,
                statement=s,scope_path=doc["scope_path"] if doc else "")
            data=record.model_dump(exclude={"review_status"})
            con.execute("INSERT INTO strategy_statement_versions(id,strategy_id,version,document_id,record_json,content_sha256,review_status,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (ident,sid,version,document.origin.document_id,json.dumps(data,ensure_ascii=False),digest(data),"pending_review",db.now()))
            ids.append(ident)
        db.audit(con,None,"history_extracted","DeepSeek",{"document_id":document.origin.document_id,
            "statement_version_ids":ids,"coverage":result.coverage,"llm_runs":result.llm_runs})
    return ids

def revise_statement(ident,changes):
    old=load_statement(ident)
    from .catalog import mutable_strategy
    with db.connect() as con: mutable_strategy(con,old.strategy_id)
    if set(changes)-{"statement","resolved_context"}: raise ValueError("只能修改语句标签/翻译或任务上下文")
    content=old.model_dump()
    if "statement" in changes: content["statement"]={**content["statement"],**changes["statement"]}
    if "resolved_context" in changes:
        ctx=changes["resolved_context"]; task_id=ctx.get("task_id")
        if set(ctx)-{'task_id','allowed_paths','target_paths','context_note'}:raise ValueError('未知的上下文输入字段')
        for field in ('allowed_paths','target_paths'):
            if not isinstance(ctx.get(field,[]),list) or len(ctx.get(field,[]))>100:raise ValueError('上下文路径必须是最多 100 项的列表')
        with db.connect() as con: task=con.execute("SELECT * FROM tasks WHERE id=?",(task_id,)).fetchone()
        if not task or task["status"] not in ("prepared","policy_review","approved"):
            raise ValueError("上下文只能绑定尚未启动的任务")
        if task["repo"]!=old.origin.repository or task["commit_sha"]!=old.origin.commit:
            raise ValueError("任务仓库/commit 与来源不一致")
        paths=[]; workspace=Path(task["workspace"]).resolve()
        from .sources import relative_path
        for rel in ctx.get("allowed_paths",[]):
            path=(workspace/relative_path(rel)).resolve(strict=True); path.relative_to(workspace)
            if not path.is_dir(): raise ValueError("允许路径必须是目录")
            if old.scope_path:
                path.relative_to((workspace/old.scope_path).resolve())
            paths.append(str(path))
        targets=[]
        for rel in ctx.get('target_paths',[]):
            path=(workspace/relative_path(rel)).resolve(strict=True);path.relative_to(workspace)
            if old.scope_path:path.relative_to((workspace/old.scope_path).resolve())
            if not path.is_file() and not path.is_dir():raise ValueError('策略操作对象必须为文件或目录')
            targets.append({'relative_path':rel,'absolute_path':str(path),'kind':'directory' if path.is_dir() else 'file'})
        content["resolved_context"]={"task_id":task_id,"repository":task["repo"],"commit":task["commit_sha"],
            "workspace":str(workspace),"allowed_paths":paths,"verified_targets":targets,"context_note":str(ctx.get("context_note",""))[:2000],
            "modification_scope": {"universe":str(workspace)+"/**","authorized_subtrees":[p+"/**" for p in paths],
                "unlisted_repository_paths":"not_authorized_for_modification", "outside_repository":"outside_this_scope",
                "pattern_utf8_bytes":{p:len(p.encode()) for p in [str(workspace)+"/**",*[p+"/**" for p in paths]]}} if paths else None}
    from .sources import read_document
    document=read_document(old.origin.document_id)
    checked=old.statement.model_validate(content["statement"])
    content["statement"]=verify_evidence(document,checked).model_dump()
    content["review_status"]="pending_review"
    with db.connect() as con:
        version=con.execute("SELECT MAX(version)+1 FROM strategy_statement_versions WHERE strategy_id=?",(old.strategy_id,)).fetchone()[0]
        content.update(id=uuid.uuid4().hex,version=version)
        validated=StrategyStatementVersion.model_validate(content)
        data=validated.model_dump(exclude={"review_status"})
        con.execute("INSERT INTO strategy_statement_versions(id,strategy_id,version,document_id,record_json,content_sha256,review_status,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (validated.id,old.strategy_id,version,old.origin.document_id,json.dumps(data,ensure_ascii=False),digest(data),"pending_review",db.now()))
        db.audit(con,None,"history_statement_revised","用户",{"old_id":ident,"new_id":validated.id})
    return validated.id

def review_statement(ident,decision,actor):
    record=load_statement(ident)
    from .catalog import mutable_strategy
    with db.connect() as con: mutable_strategy(con,record.strategy_id)
    if decision not in ("approve","reject"): raise ValueError("decision 必须为 approve/reject")
    if decision=="approve":
        from .sources import read_document
        if verify_evidence(read_document(record.origin.document_id),record.statement).evidence_state!="verified":
            raise ValueError("原文证据未定位，不能批准")
        with db.connect() as con:source_kind=con.execute('SELECT source_kind FROM strategies WHERE id=?',(record.strategy_id,)).fetchone()[0]
        if source_kind=='history_document':
            if not record.statement.text_en.strip(): raise ValueError("语句缺少英文译文")
            if not record.statement.text_zh.strip(): raise ValueError("语句缺少中文译文")
    state="approved" if decision=="approve" else "rejected"
    with db.connect() as con:
        con.execute("UPDATE strategy_statement_versions SET review_status=?,reviewed_hash=content_sha256,reviewed_by=?,reviewed_at=? WHERE id=?",
            (state,actor,db.now(),ident))
        con.execute("UPDATE strategies SET status=?,reviewed_by=?,reviewed_at=? WHERE id=?",(state,actor,db.now(),record.strategy_id))
        db.audit(con,None,"history_statement_review",actor,{"id":ident,"decision":decision})
    return {"status":state}

def save_artifact(candidate,compile_state,compile_info):
    data=candidate.model_dump()
    with db.connect() as con:
        semantic_data={k:v for k,v in data.items() if k!="llm_runs"}
        for prior in con.execute("SELECT id,artifact_json,compile_state FROM history_artifacts WHERE statement_version_id=?",(candidate.statement_version_id,)):
            previous=json.loads(prior["artifact_json"]); previous.pop("llm_runs",None)
            if previous==semantic_data and prior["compile_state"]==compile_state:
                db.audit(con,None,"history_artifact_duplicate_result","DeepSeek",{"artifact_id":prior["id"],"llm_runs":candidate.llm_runs})
                return prior["id"]
        version=con.execute("SELECT COALESCE(MAX(version),0)+1 FROM history_artifacts WHERE statement_version_id=?",(candidate.statement_version_id,)).fetchone()[0]
        ident=uuid.uuid4().hex
        con.execute("""INSERT INTO history_artifacts(id,statement_version_id,version,artifact_json,content_sha256,
         review_status,compile_state,compile_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
         (ident,candidate.statement_version_id,version,json.dumps(data,ensure_ascii=False),digest(data),
          "pending_review",compile_state,json.dumps(compile_info),db.now()))
        if candidate.actplane_dsl:
            con.execute("INSERT INTO history_compilations VALUES(?,?,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex,ident,None,None,digest(candidate.actplane_dsl),compile_state,
                 compile_info.get("compiler_version","unknown"),json.dumps(compile_info),db.now()))
    return ident

def review_artifact(ident,decision,actor):
    if decision not in ("approve","reject"): raise ValueError("decision 必须为 approve/reject")
    with db.connect() as con:
        row=con.execute("SELECT * FROM history_artifacts WHERE id=?",(ident,)).fetchone()
        if not row: raise ValueError("DSL 产物不存在")
        data=json.loads(row["artifact_json"])
        source=con.execute("SELECT review_status,reviewed_hash,content_sha256,strategy_id FROM strategy_statement_versions WHERE id=?",(row["statement_version_id"],)).fetchone()
        from .catalog import mutable_strategy
        mutable_strategy(con,source["strategy_id"])
        if decision=="approve":
            if source["review_status"]!="approved" or source["reviewed_hash"]!=source["content_sha256"]: raise ValueError("来源版本未批准")
            if digest(data)!=row["content_sha256"]: raise ValueError("DSL 内容 hash 不一致")
            if data["actplane_dsl"]:
                validate_fragment(data["actplane_dsl"],"h_"+row["statement_version_id"].replace("-","")[:16]+"_")
                if row["compile_state"]!="compiled": raise ValueError("DSL 未获完整编译支持")
        state="approved" if decision=="approve" else "rejected"
        con.execute("UPDATE history_artifacts SET review_status=?,reviewed_hash=content_sha256,reviewed_by=?,reviewed_at=? WHERE id=?",
            (state,actor,db.now(),ident))
        db.audit(con,None,"history_artifact_review",actor,{"id":ident,"decision":decision})
    return {"status":state}

def selected_artifacts(task,ids):
    if len(ids)!=len(set(ids)): raise ValueError("重复选择 DSL 版本")
    result=[]; seen=set()
    with db.connect() as con:
        for ident in ids:
            row=con.execute("SELECT * FROM history_artifacts WHERE id=?",(ident,)).fetchone()
            if not row or row["review_status"]!="approved" or row["reviewed_hash"]!=row["content_sha256"]: raise ValueError("DSL 版本未批准")
            data=json.loads(row["artifact_json"])
            if digest(data)!=row["content_sha256"]: raise ValueError("DSL 内容 hash 不一致")
            if row["compile_state"]!="compiled" or not data["actplane_dsl"]: raise ValueError("DSL 尚不可执行")
            validate_fragment(data["actplane_dsl"],"h_"+row["statement_version_id"].replace("-","")[:16]+"_")
            statement=load_statement(row["statement_version_id"])
            from .catalog import mutable_strategy
            mutable_strategy(con,statement.strategy_id)
            source=con.execute("SELECT reviewed_hash,content_sha256 FROM strategy_statement_versions WHERE id=?",(statement.id,)).fetchone()
            if source["reviewed_hash"]!=source["content_sha256"]: raise ValueError("来源语句批准 hash 不一致")
            if statement.strategy_id in seen: raise ValueError("同一策略只能选一个版本")
            seen.add(statement.strategy_id)
            if statement.review_status!="approved": raise ValueError("来源版本未批准")
            if statement.origin.repository!=task["repo"] or statement.origin.commit!=task["commit_sha"]: raise ValueError("策略不适用于任务仓库/commit")
            if statement.resolved_context.get("task_id") not in (None,task["id"]): raise ValueError("DSL 已绑定其他任务")
            result.append({**dict(row),"data":data,"statement":statement})
    return result

"""Strategy directory and immutable history projections, adapted from mac 41e5c3d."""
import hashlib
import json
import uuid
from .. import db
from .capabilities import runtime_limits_for

CATEGORIES={"semantic","semantic-only","content","per-event","cross-event","not-applicable"}
SCOPES={"self-contained","project","task","not-applicable"}

def require_strategy(con,ident):
    row=con.execute("SELECT * FROM strategies WHERE id=?",(ident,)).fetchone()
    if not row: raise ValueError("策略记录不存在")
    return dict(row)

def mutable_strategy(con,ident):
    row=require_strategy(con,ident)
    if row["is_archived"]: raise ValueError("已归档策略不可修改；请先恢复")
    return row

def create(values,actor):
    if values["category"] not in CATEGORIES or values["context_scope"] not in SCOPES:
        raise ValueError("执行层级或上下文范围不合法")
    text=values["text"].strip()
    if len(text)<5: raise ValueError("策略内容至少五个字符")
    url=values.get("source_url")
    if url and not url.startswith("https://"): raise ValueError("来源链接必须使用 HTTPS")
    ident=uuid.uuid4().hex
    with db.connect() as con:
        con.execute("""INSERT INTO strategies(id,text,category,category_confidence,context_scope,execution_layer,
            status,raw_url,sentence_sha256,source_verified,source_kind,metadata_json,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ident,text,values["category"],1,values["context_scope"],values["execution_layer"],
             "pending_review",url,hashlib.sha256(text.encode()).hexdigest(),0,"manual",
             json.dumps({"source":"manual"}),db.now()))
        db.audit(con,None,"strategy_created",actor,{"strategy_id":ident})
        return require_strategy(con,ident)

def revise(ident,values,actor,reason=""):
    fields={"text","category","context_scope","execution_layer"}
    if set(values)-fields or not values: raise ValueError("没有可应用的目录修改")
    if "category" in values and values["category"] not in CATEGORIES: raise ValueError("执行层级不合法")
    if "context_scope" in values and values["context_scope"] not in SCOPES: raise ValueError("上下文范围不合法")
    if "text" in values:
        values={**values,"text":values["text"].strip()}
        if len(values["text"])<5: raise ValueError("策略内容至少五个字符")
    with db.connect() as con:
        row=mutable_strategy(con,ident)
        if row["source_kind"]=="history_document" or con.execute('SELECT 1 FROM strategy_statement_versions WHERE strategy_id=?',(ident,)).fetchone():
            raise ValueError("已有转换语句的策略必须修订确切语句版本，不能覆盖目录原文")
        revision=row["revision"]+1
        con.execute("INSERT INTO strategy_revisions VALUES(?,?,?,?,?,?,?)",
            (uuid.uuid4().hex,ident,row["revision"],actor,reason,json.dumps(row,ensure_ascii=False),db.now()))
        if values.get("text",row["text"])!=row["text"]: values={**values,"source_verified":0}
        setters=",".join(key+"=?" for key in values)
        con.execute(f"UPDATE strategies SET {setters},revision=?,status='pending_review',reviewed_by=NULL,reviewed_at=NULL WHERE id=?",
            [*values.values(),revision,ident])
        db.audit(con,None,"strategy_updated",actor,{"strategy_id":ident,"revision":revision,"fields":list(values),"reason":reason})
        return require_strategy(con,ident)

def archive(ident,archived,actor):
    with db.connect() as con:
        row=require_strategy(con,ident)
        if bool(row["is_archived"])!=archived:
            con.execute("UPDATE strategies SET is_archived=?,archived_at=?,archived_by=? WHERE id=?",
                (int(archived),db.now() if archived else None,actor if archived else None,ident))
            db.audit(con,None,"strategy_archived" if archived else "strategy_restored",actor,{"strategy_id":ident})
        return require_strategy(con,ident)

def artifact_rows(con,ident):
    rows=con.execute("""SELECT a.*,v.record_json,v.strategy_id,v.version AS statement_version,
        v.review_status AS statement_review_status,v.reviewed_hash AS statement_reviewed_hash,
        v.content_sha256 AS statement_hash FROM history_artifacts a
        JOIN strategy_statement_versions v ON v.id=a.statement_version_id
        WHERE v.strategy_id=? ORDER BY v.version DESC,a.version DESC""",(ident,))
    result=[]
    for row in rows:
        item=db.row_dict(row)
        item["eligible"]=bool(item["review_status"]=="approved" and item["reviewed_hash"]==item["content_sha256"]
            and item["statement_review_status"]=="approved" and item["statement_reviewed_hash"]==item["statement_hash"]
            and item["compile_state"]=="compiled" and item["artifact"]["actplane_dsl"])
        item["runtime_limits"]=runtime_limits_for(item["artifact"].get("actplane_dsl"))
        from .eligibility import blockers
        item["load_blockers"]=blockers(item["artifact"],item["record"])
        item["eligible"]=item["eligible"] and not item["load_blockers"]
        item["deployments"]=[db.row_dict(r) for r in con.execute("""SELECT d.*,t.name AS task_name,t.repo AS task_repo,
            p.version AS task_policy_version FROM history_deployments d
            JOIN history_policy_artifacts l ON l.policy_version_id=d.policy_version_id
            JOIN policy_versions p ON p.id=d.policy_version_id JOIN tasks t ON t.id=d.task_id
            WHERE l.artifact_id=? ORDER BY d.created_at DESC""",(item["id"],))]
        result.append(item)
    return result

def record(con,row,details=False):
    item=dict(row)
    current=con.execute("SELECT * FROM strategy_statement_versions WHERE strategy_id=? ORDER BY version DESC LIMIT 1",(item["id"],)).fetchone()
    item["statement_version"]=db.row_dict(current)
    if current: item["status"]=current["review_status"]
    item["artifacts"]=artifact_rows(con,item["id"])
    s=item["statement_version"]["record"]["statement"] if current else {}
    from .pipeline import reviewed_phrase_errors
    item["review_blockers"]=reviewed_phrase_errors(s)
    item["completeness"]=s.get("completeness","unreviewed")
    item["adaptation"]=next((a["artifact"].get("policy_record",{}).get("metadata",{}).get("adaptation",{}).get("state","not_required") for a in item["artifacts"]),"not_required")
    item["loadable"]=any(a["eligible"] for a in item["artifacts"])
    if details:
        from .inputs import directory_preview
        item['metadata_preview']=directory_preview(item)
        item["statement_versions"]=[db.row_dict(r) for r in con.execute("SELECT * FROM strategy_statement_versions WHERE strategy_id=? ORDER BY version DESC",(item["id"],))]
        item["revisions"]=[db.row_dict(r) for r in con.execute("SELECT * FROM strategy_revisions WHERE strategy_id=? ORDER BY revision DESC",(item["id"],))]
    return item

def page(q="",status="",category="",context_scope="",source_repo="",archived="active",limit=20,offset=0,source_kind="",execution_layer="",completeness="",adaptation="",loadable=""):
    if archived not in {"active","archived","all"}: raise ValueError("归档筛选不合法")
    if source_kind not in {"","rq1_corpus","history_document","manual"}: raise ValueError("策略来源筛选不合法")
    filters=["COALESCE(json_extract(v.record_json,'$.statement.content_type'),'policy')!='description'"];params=[]
    if source_kind: filters.append("s.source_kind=?");params.append(source_kind)
    if archived!="all": filters.append("s.is_archived=?");params.append(int(archived=="archived"))
    if q:
        filters.append("(s.text LIKE ? OR s.source_repo LIKE ? OR s.source_path LIKE ? OR json_extract(v.record_json,'$.statement.text_zh') LIKE ? OR json_extract(v.record_json,'$.statement.text_original') LIKE ? OR json_extract(v.record_json,'$.statement.text_en') LIKE ?)")
        params.extend(["%"+q+"%"]*6)
    if status=="loaded":
        filters.append("""EXISTS(SELECT 1 FROM strategy_statement_versions sv JOIN history_artifacts a ON a.statement_version_id=sv.id
            JOIN history_policy_artifacts l ON l.artifact_id=a.id JOIN history_deployments d ON d.policy_version_id=l.policy_version_id
            WHERE sv.strategy_id=s.id AND d.status='loaded')""")
    elif status:
        filters.append("COALESCE(v.review_status,s.status)=?");params.append(status)
    if category:
        if category=="semantic":
            filters.append("COALESCE(REPLACE(json_extract(v.record_json,'$.statement.enforcement_level'),'_','-'),s.category) IN ('semantic','semantic-only')")
        else:
            filters.append("COALESCE(REPLACE(json_extract(v.record_json,'$.statement.enforcement_level'),'_','-'),s.category)=?")
            params.append(category)
    if context_scope:
        filters.append("COALESCE(REPLACE(json_extract(v.record_json,'$.statement.context_requirement'),'_','-'),s.context_scope)=?")
        params.append(context_scope)
    if source_repo: filters.append("s.source_repo LIKE ?");params.append("%"+source_repo+"%")
    if execution_layer: filters.append('s.execution_layer=?');params.append(execution_layer)
    where=" WHERE "+" AND ".join(filters) if filters else ""
    join=""" FROM strategies s LEFT JOIN strategy_statement_versions v ON v.id=(
        SELECT id FROM strategy_statement_versions WHERE strategy_id=s.id ORDER BY version DESC LIMIT 1)"""
    with db.connect() as con:
        total=con.execute("SELECT COUNT(*)"+join+where,params).fetchone()[0]
        extra_filters=bool(completeness or adaptation or loadable)
        rows=con.execute("SELECT s.*"+join+where+" ORDER BY s.source_verified DESC,s.created_at DESC,s.id"+("" if extra_filters else " LIMIT ? OFFSET ?"),params if extra_filters else [*params,limit,offset])
        items=[record(con,r) for r in rows]
        if extra_filters:
            items=[r for r in items if (not completeness or r["completeness"]==completeness) and (not adaptation or r["adaptation"]==adaptation) and (not loadable or r["loadable"]==(loadable=="yes"))]
            total=len(items);items=items[offset:offset+limit]
    return {"items":items,"total":total,"limit":limit,"offset":offset}

def detail(ident):
    with db.connect() as con: return record(con,require_strategy(con,ident),True)
